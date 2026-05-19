"""
Auto-Pipeline-Service — Orchestrierung der monatlichen Hausgeld-Sollstellung
und SEPA-Lastschrift-Generierung (Spec AutoPipeline v1.0 Kap. 8–9).
"""
import logging
import traceback
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.buchhaltung.models import (
    AutoLaufProtokoll,
    FrontofficeAufgabe,
    HausgeldSollstellungslauf,
    LastschriftLauf,
)
from apps.buchhaltung.services import sepa_fristen_service
from apps.buchhaltung.services.sepa_lastschrift import (
    commite_lastschriftlauf,
    generiere_pain008,
)
from apps.buchhaltung.services.sollstellungslauf_service import run_hausgeld_monat

logger = logging.getLogger(__name__)


@transaction.atomic
def run_objekt(objekt, periode: date, user) -> AutoLaufProtokoll:
    """
    Atomarer Lauf pro Objekt. Bei Fehler an einer beliebigen Stelle:
    Rollback des gesamten Objekt-Laufs. AutoLaufProtokoll bleibt
    bestehen (eigene Transaktion im Außenrahmen des Tasks).

    Schritte:
      1. Idempotenz-Check
      2. Sollstellungslauf erzeugen
      3. EVs für Lastschrift filtern
      4. SEPA-Frist berechnen
      5. Lastschriftlauf erzeugen
      6. pain.008-XML generieren
      7. Datei schreiben
      8. Protokoll-Eintrag schreiben
    """
    ausgefuehrt_am = timezone.now()

    # 1. Idempotenz
    existierender_lauf = HausgeldSollstellungslauf.objects.filter(
        objekt=objekt,
        periode=periode,
        lauf_quelle='autopilot',
        status='commited',
    ).first()
    if existierender_lauf:
        logger.info('%s: Auto-Lauf für %s bereits vorhanden — übersprungen.', objekt.objektnummer, periode)
        return _protokoll_uebersprungen(objekt, periode, ausgefuehrt_am, existierender_lauf)

    warnungen = []

    # 2. Sollstellungslauf erzeugen
    sollstellungslauf = run_hausgeld_monat(
        objekt=objekt,
        periode=periode,
        user=user,
        skip_freigabe=True,
        lauf_quelle='autopilot',
    )

    # 3. EVs für Lastschrift filtern
    kandidaten, ausgeschlossen = _filtere_lastschrift_kandidaten(sollstellungslauf)
    for eintrag in ausgeschlossen:
        warnungen.append(eintrag)
        _erzeuge_frontoffice_aufgabe(objekt, eintrag, user)

    if not kandidaten:
        logger.info('%s: Keine Lastschrift-Kandidaten — nur Sollstellungen erzeugt.', objekt.objektnummer)
        return _protokoll_teilerfolg_nur_sollstellung(
            objekt, periode, ausgefuehrt_am, sollstellungslauf, warnungen
        )

    # 4. SEPA-Frist berechnen
    bundesland = objekt.bundesland or 'HE'
    faelligkeit = sepa_fristen_service.naechster_einreichungstag(
        stichtag=timezone.localdate(),
        soll_faelligkeit=periode,
        bundesland=bundesland,
    )
    if faelligkeit > periode:
        warnung = {
            'warnung_typ': 'sepa_frist_unterschritten',
            'nachricht': f'Fälligkeit verschoben auf {faelligkeit}',
        }
        warnungen.append(warnung)
        _erzeuge_frontoffice_aufgabe(objekt, warnung, user)

    # 5. Lastschriftlauf erzeugen
    lastschriftlauf = commite_lastschriftlauf(
        objekt=objekt,
        stichtag=faelligkeit,
        kandidaten=kandidaten,
        user=user,
        lauf_quelle='autopilot',
    )

    # 6. pain.008-XML generieren
    xml = generiere_pain008(lastschriftlauf)

    # 7. Datei schreiben
    datei_pfad = _schreibe_pain008_datei(
        xml=xml,
        objekt=objekt,
        periode=periode,
        lauf=lastschriftlauf,
    )
    lastschriftlauf.datei_pfad = datei_pfad
    lastschriftlauf.save(update_fields=['datei_pfad'])

    # 8. Protokoll
    return AutoLaufProtokoll.objects.create(
        objekt=objekt,
        ausgefuehrt_am=ausgefuehrt_am,
        periode=periode,
        status='erfolg' if not warnungen else 'teilweise_erfolg',
        sollstellungslauf=sollstellungslauf,
        lastschriftlauf=lastschriftlauf,
        anzahl_evs_geplant=sollstellungslauf.anzahl_sollstellungen,
        anzahl_evs_erfolgreich=len(kandidaten),
        anzahl_evs_uebersprungen=len(ausgeschlossen),
        summe_sollstellungen=sollstellungslauf.summe,
        summe_lastschrift=lastschriftlauf.gesamt_summe,
        datei_pfad=datei_pfad,
        warnungen=warnungen,
    )


def _filtere_lastschrift_kandidaten(sollstellungslauf):
    """
    Filtert aus allen Sollstellungen des Laufs die EVs heraus, die NICHT per
    Lastschrift einziehbar sind. Sammelt Ausschlussgründe als Warnungen.

    Returns: (kandidaten, ausgeschlossen) — beide Listen von HausgeldSollstellung.
    """
    kandidaten = []
    ausgeschlossen = []

    for sollstellung in sollstellungslauf.sollstellungen.filter(
        sollstellungs_typ='hausgeld'
    ).select_related('eigentumsverhaeltnis__person__sepa_mandat', 'eigentumsverhaeltnis__einheit'):
        ev = sollstellung.eigentumsverhaeltnis
        person = ev.person

        if not person.sepa_mandat:
            ausgeschlossen.append({
                'ev_id': str(ev.id),
                'name': person.name,
                'einheit': ev.einheit.einheit_nr,
                'warnung_typ': 'kein_sepa_mandat',
                'nachricht': f'{person.name}: SEPA-Mandat fehlt',
            })
            continue

        if person.sepa_mandat.sequence_type != 'RCUR':
            ausgeschlossen.append({
                'ev_id': str(ev.id),
                'name': person.name,
                'einheit': ev.einheit.einheit_nr,
                'warnung_typ': 'mandat_typ_frst',
                'nachricht': f'{person.name}: FRST-Mandat — manuelle Lastschrift nötig',
            })
            continue

        if not person.sepa_mandat.iban:
            ausgeschlossen.append({
                'ev_id': str(ev.id),
                'name': person.name,
                'einheit': ev.einheit.einheit_nr,
                'warnung_typ': 'keine_iban',
                'nachricht': f'{person.name}: Keine IBAN im SEPA-Mandat hinterlegt',
            })
            continue

        kandidaten.append(sollstellung)

    return kandidaten, ausgeschlossen


def _schreibe_pain008_datei(xml: str, objekt, periode: date, lauf) -> str:
    """
    Schreibt pain.008 in SEPA_OUTPUT_DIR.

    Atomares Schreiben via Temp-File + Rename (Windata sieht nie eine halb-
    geschriebene Datei). Bei Namenskonflikt wird _v2, _v3 etc. angehängt.

    Dateinamen-Schema: {JJJJ-MM-TT}_{objekt_nr}_LS_{JJJJ-MM}.xml
    Beispiel: 2026-03-25_100001_LS_2026-04.xml
    """
    basis_name = (
        f'{timezone.localdate().isoformat()}_'
        f'{objekt.objektnummer}_LS_'
        f'{periode.strftime("%Y-%m")}.xml'
    )

    zielordner = Path(settings.SEPA_OUTPUT_DIR)
    zielordner.mkdir(parents=True, exist_ok=True)

    # Namenskonflikt auflösen
    ziel_pfad = zielordner / basis_name
    version = 2
    while ziel_pfad.exists():
        stem = basis_name[:-4]  # ohne .xml
        ziel_pfad = zielordner / f'{stem}_v{version}.xml'
        version += 1

    temp_pfad = zielordner / f'.{ziel_pfad.name}.tmp'

    try:
        temp_pfad.write_text(xml, encoding='utf-8')
        # os.replace ist atomar auf demselben Dateisystem (UNC-kompatibel)
        import os
        os.replace(str(temp_pfad), str(ziel_pfad))
    except OSError:
        try:
            temp_pfad.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    logger.info('pain.008 geschrieben: %s', ziel_pfad)
    return str(ziel_pfad)


def _erzeuge_frontoffice_aufgabe(objekt, warnung: dict, user) -> FrontofficeAufgabe:
    """
    Legt eine FrontofficeAufgabe für den Bearbeiter an (Phase B).
    Jede Auto-Pipeline-Warnung wird als eigene Aufgabe erfasst.
    """
    aufgabe_typ = warnung.get('warnung_typ', 'kein_sepa_mandat')
    ev_id_raw = warnung.get('ev_id')
    aufgabe = FrontofficeAufgabe.objects.create(
        objekt=objekt,
        aufgabe_typ=aufgabe_typ,
        beschreibung=warnung.get('nachricht', ''),
        ev_id=ev_id_raw or None,
        einheit_nr=warnung.get('einheit', ''),
        erstellt_von=user,
    )
    logger.info(
        'FrontofficeAufgabe %s erstellt [%s] Objekt %s',
        aufgabe.id, aufgabe_typ, objekt.objektnummer,
    )
    return aufgabe


def _protokoll_uebersprungen(objekt, periode, ausgefuehrt_am, existierender_lauf) -> AutoLaufProtokoll:
    return AutoLaufProtokoll.objects.create(
        objekt=objekt,
        ausgefuehrt_am=ausgefuehrt_am,
        periode=periode,
        status='uebersprungen',
        sollstellungslauf=existierender_lauf,
        anzahl_evs_geplant=existierender_lauf.anzahl_sollstellungen,
        anzahl_evs_erfolgreich=existierender_lauf.anzahl_sollstellungen,
        anzahl_evs_uebersprungen=0,
        summe_sollstellungen=existierender_lauf.summe,
        summe_lastschrift=Decimal('0'),
        warnungen=[],
    )


def _protokoll_teilerfolg_nur_sollstellung(
    objekt, periode, ausgefuehrt_am, sollstellungslauf, warnungen
) -> AutoLaufProtokoll:
    return AutoLaufProtokoll.objects.create(
        objekt=objekt,
        ausgefuehrt_am=ausgefuehrt_am,
        periode=periode,
        status='teilweise_erfolg',
        sollstellungslauf=sollstellungslauf,
        anzahl_evs_geplant=sollstellungslauf.anzahl_sollstellungen,
        anzahl_evs_erfolgreich=0,
        anzahl_evs_uebersprungen=sollstellungslauf.anzahl_sollstellungen,
        summe_sollstellungen=sollstellungslauf.summe,
        summe_lastschrift=Decimal('0'),
        warnungen=warnungen,
    )
