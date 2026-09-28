"""
Eigentümerwechsel-Service — angepasst an das Hauptprojekt-Datenmodell.

Enthält:
  - bestimme_wirkungs_periode: nächster Monatserster >= stichtag
  - nachhol_perioden: alle Monatsersten von wirkungs_periode bis aktuellen Monat
  - analysiere_wechsel: Read-only Klassifizierung der Verkäufer-Sollstellungen
  - commite_wechsel: atomarer Commit (neue Signatur, arbeitet mit Hauptprojekt-Modellen)
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.buchhaltung.models import (
    Buchungsart,
    EigentuemerwechselVorgang,
    HausgeldSollstellung,
)
from apps.konten.models import Abrechnungsart
from apps.personen.models import EigentumsVerhaeltnis, HausgeldHistorie


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def bestimme_wirkungs_periode(stichtag: date) -> date:
    if stichtag.day == 1:
        return stichtag
    if stichtag.month == 12:
        return date(stichtag.year + 1, 1, 1)
    return date(stichtag.year, stichtag.month + 1, 1)


def nachhol_perioden(wirkungs_periode: date, heute: date) -> List[date]:
    """Vollständig abgelaufene Monate von der Wirkungsperiode bis vor den
    aktuellen Monat. Der laufende Monat wird hier NICHT geliefert — er wird in
    ``commite_wechsel`` separat behandelt, weil dort erst geprüft werden muss,
    ob der Sollstellungslauf für ihn schon gelaufen ist."""
    erster_aktueller_monat = date(heute.year, heute.month, 1)
    result = []
    p = wirkungs_periode
    while p < erster_aktueller_monat:
        result.append(p)
        p = date(p.year + 1, 1, 1) if p.month == 12 else date(p.year, p.month + 1, 1)
    return result


# ---------------------------------------------------------------------------
# Analyse-Datenstrukturen
# ---------------------------------------------------------------------------

@dataclass
class WechselAnalyseSollstellung:
    sollstellung_id: str
    opos_nr: str
    periode: date
    soll_betrag: Decimal
    ist_betrag: Decimal
    bucket: str  # 'stornieren' | 'erstatten'
    lastschrift_juenger_56_tage: bool = False


@dataclass
class WechselAnalyse:
    einheit_id: str
    verkaeufer_ev_id: str
    wirkungs_periode: date
    art: str  # 'zukuenftig' | 'rueckwirkend'
    stornieren: List[WechselAnalyseSollstellung] = field(default_factory=list)
    erstatten: List[WechselAnalyseSollstellung] = field(default_factory=list)
    verkaeufer_iban: Optional[str] = None
    warnung_keine_iban: bool = False
    erstattung_summe: Decimal = Decimal('0')


# ---------------------------------------------------------------------------
# Analyse (Read-only)
# ---------------------------------------------------------------------------

def analysiere_wechsel(einheit, stichtag: date) -> WechselAnalyse:
    verkaeufer_ev = EigentumsVerhaeltnis.objects.filter(
        einheit=einheit, ende__isnull=True,
    ).first()
    if not verkaeufer_ev:
        raise ValidationError(f"Keine aktive Eigentümerschaft für Einheit {einheit.id}.")

    wirkungs_periode = bestimme_wirkungs_periode(stichtag)
    heute_erster = date(timezone.now().date().year, timezone.now().date().month, 1)
    art = 'rueckwirkend' if wirkungs_periode < heute_erster else 'zukuenftig'

    ibans = getattr(verkaeufer_ev.person, 'ibans', None) or []
    verkaeufer_iban = ibans[0] if ibans else None

    analyse = WechselAnalyse(
        einheit_id=str(einheit.id),
        verkaeufer_ev_id=str(verkaeufer_ev.id),
        wirkungs_periode=wirkungs_periode,
        art=art,
        verkaeufer_iban=verkaeufer_iban,
        warnung_keine_iban=(not verkaeufer_iban),
    )

    if art == 'zukuenftig':
        return analyse

    sollstellungen = HausgeldSollstellung.objects.filter(
        eigentumsverhaeltnis=verkaeufer_ev,
        periode__gte=wirkungs_periode,
        storniert_am__isnull=True,
    ).order_by('periode')

    heute = timezone.now().date()
    erstattung_summe = Decimal('0')

    for ss in sollstellungen:
        ist = ss.ist_betrag
        soll = ss.soll_betrag

        letzte_zahlung = ss.zahlungen.exclude(buchung__status='storniert').order_by('-erstellt_am').first()
        juenger_56 = bool(
            letzte_zahlung and (heute - letzte_zahlung.erstellt_am.date()).days < 56
        )

        if ist == 0:
            analyse.stornieren.append(WechselAnalyseSollstellung(
                sollstellung_id=str(ss.id),
                opos_nr=ss.opos_nr,
                periode=ss.periode,
                soll_betrag=soll,
                ist_betrag=ist,
                bucket='stornieren',
            ))
        else:
            erstattung_summe += ist
            analyse.erstatten.append(WechselAnalyseSollstellung(
                sollstellung_id=str(ss.id),
                opos_nr=ss.opos_nr,
                periode=ss.periode,
                soll_betrag=soll,
                ist_betrag=ist,
                bucket='erstatten',
                lastschrift_juenger_56_tage=juenger_56,
            ))

    analyse.erstattung_summe = erstattung_summe
    return analyse


# ---------------------------------------------------------------------------
# Commit (atomar) — Hauptprojekt-Modell
# ---------------------------------------------------------------------------

@transaction.atomic
def commite_wechsel(
    einheit,
    stichtag: date,
    wirkungs_periode: date,
    entscheidungen: dict,
    user,
    heute: Optional[date] = None,
) -> dict:
    """
    Führt den gesamten Wechselvorgang atomar aus.

    entscheidungen = {
        "kaeufer_person_id": UUID,
        "kaeufer_iban": str,
        "hausgeld_je_ba": {kontoart_str: Decimal},   # z.B. {'.900': 250, '.911': 80}
        "stornieren_ids": [str, ...],
        "erstatten": [{"ss_id": str, "ist_betrag": str}, ...],
        "verkaeufer_iban": str | None,
    }

    `heute` bestimmt, welche Perioden als abgelaufen gelten (nur für Tests
    explizit setzen — produktiv immer der heutige Tag).
    """
    from apps.personen.models import Person

    verkaeufer_ev = EigentumsVerhaeltnis.objects.select_for_update().filter(
        einheit=einheit, ende__isnull=True,
    ).first()
    if not verkaeufer_ev:
        raise ValidationError("Kein aktiver Eigentümer gefunden.")

    # 1) Verkäufer-EV beenden
    verkaeufer_ev.ende = stichtag - timedelta(days=1)
    verkaeufer_ev.save(update_fields=['ende'])

    # 2) Käufer-EV anlegen
    kaeufer_person = Person.objects.get(id=entscheidungen['kaeufer_person_id'])
    kaeufer_ev = EigentumsVerhaeltnis.objects.create(
        einheit=einheit,
        person=kaeufer_person,
        beginn=wirkungs_periode,
        ende=None,
    )

    # 3) HausgeldHistorie für Käufer anlegen (ggf. offene Einträge schließen)
    hausgeld_je_ba = entscheidungen.get('hausgeld_je_ba', {})
    vortag = wirkungs_periode - timedelta(days=1)
    for kontoart, betrag in hausgeld_je_ba.items():
        betrag_d = Decimal(str(betrag)) if betrag else Decimal('0')
        if betrag_d <= 0:
            continue
        ba_nr = kontoart.lstrip('.')  # '.900' → '900'
        ba_obj = Buchungsart.objects.filter(nr=ba_nr).first()
        abr_obj = Abrechnungsart.objects.filter(objekt=einheit.objekt, code=ba_nr).first()
        # Offene Einträge für diese BA schließen
        HausgeldHistorie.objects.filter(
            eigentumsverhaeltnis=kaeufer_ev,
            ba=ba_obj,
            gueltig_bis__isnull=True,
        ).update(gueltig_bis=vortag)
        HausgeldHistorie.objects.create(
            eigentumsverhaeltnis=kaeufer_ev,
            ba=ba_obj,
            abrechnungsart=abr_obj,
            betrag=betrag_d,
            gueltig_ab=wirkungs_periode,
            quelle='import',
            import_referenz=f'eigentümerwechsel_{stichtag}',
            erstellt_von=user,
        )

    # 4) Storno-Liste verarbeiten (direkt, ohne Korrektur-Sollstellung)
    stornieren_ids = entscheidungen.get('stornieren_ids', [])
    now = timezone.now()
    for ss_id in stornieren_ids:
        ss = HausgeldSollstellung.objects.select_for_update().get(id=ss_id)
        if ss.ist_betrag != Decimal('0'):
            raise ValidationError(
                f"Sollstellung {ss.opos_nr} hat ist_betrag={ss.ist_betrag}, Storno nicht möglich."
            )
        ss.storniert_am = now
        ss.storniert_von = user
        ss.storniert_grund = f'Eigentümerwechsel Stichtag {stichtag}'
        ss.status_cached = 'storniert'
        ss.save(update_fields=['storniert_am', 'storniert_von', 'storniert_grund', 'status_cached'])

    # 5) Erstattungsbetrag summieren (Auszahlung muss manuell ausgeführt werden)
    erstatten_liste = entscheidungen.get('erstatten', [])
    erstattung_summe = Decimal('0')
    for item in erstatten_liste:
        erstattung_summe += Decimal(str(item.get('ist_betrag', 0)))
    verkaeufer_iban = entscheidungen.get('verkaeufer_iban') or ''

    # 6) Nachhol-Sollstellungen für Käufer anlegen
    #
    # Abgelaufene Monate werden immer nachgeholt. Der laufende Monat nur dann,
    # wenn der Sollstellungslauf für ihn im Objekt bereits gelaufen ist — sonst
    # holt der reguläre Lauf den Käufer ohnehin mit ab. Ohne diese Ergänzung
    # blieb genau die Periode ungestellt, deren Verkäufer-Sollstellung eben
    # storniert wurde (Wechsel wirkt zum laufenden Monat).
    nachhol_ids = []
    heute_datum = heute or timezone.now().date()
    perioden = nachhol_perioden(wirkungs_periode, heute_datum)

    laufender_monat = date(heute_datum.year, heute_datum.month, 1)
    if wirkungs_periode <= laufender_monat and laufender_monat not in perioden:
        lauf_bereits_gelaufen = HausgeldSollstellung.objects.filter(
            objekt=einheit.objekt,
            periode=laufender_monat,
            sollstellungs_typ='hausgeld',
        ).exists()
        if lauf_bereits_gelaufen:
            perioden.append(laufender_monat)

    if perioden and hausgeld_je_ba:
        from apps.buchhaltung.services.sollstellung_service import lege_hausgeld_sollstellung_an
        for periode in perioden:
            # Doppelstellung vermeiden (ba=NULL wird von der UniqueConstraint
            # in PostgreSQL nicht erfasst, deshalb hier explizit prüfen).
            if HausgeldSollstellung.objects.filter(
                eigentumsverhaeltnis=kaeufer_ev,
                periode=periode,
                sollstellungs_typ='hausgeld',
                storniert_am__isnull=True,
            ).exists():
                continue
            ba_betraege = {}
            for kontoart, betrag in hausgeld_je_ba.items():
                betrag_d = Decimal(str(betrag)) if betrag else Decimal('0')
                if betrag_d <= 0:
                    continue
                ba_obj = Buchungsart.objects.filter(nr=kontoart.lstrip('.')).first()
                if ba_obj:
                    ba_betraege[ba_obj] = betrag_d
            if ba_betraege:
                ss = lege_hausgeld_sollstellung_an(
                    ev=kaeufer_ev,
                    periode=periode,
                    betraege_je_ba=ba_betraege,
                    lauf=None,
                    user=user,
                )
                nachhol_ids.append(str(ss.id))

    # 7) EigentuemerwechselVorgang anlegen
    #
    # Status 'freigegeben': dieser Aufruf IST die Ausführung — Eigentums-
    # verhältnisse sind umgestellt, Storni gesetzt, Sollstellungen angelegt.
    # Als 'vorschau' stehengelassen fiel der Wechsel aus dem Hinweis-Banner der
    # Jahresabrechnung (`eigentuemerwechsel_im_wj` filtert auf 'freigegeben'),
    # und niemand hätte ihn dort je freigegeben — es gibt keinen solchen Schritt.
    # `freigegeben_von` bleibt None, das erlaubt der Vier-Augen-Constraint
    # ausdrücklich; ein Wert gleich `erstellt_von` würde ihn verletzen.
    vorgang = EigentuemerwechselVorgang.objects.create(
        objekt=einheit.objekt,
        einheit=einheit,
        voreigentuemer_ev=verkaeufer_ev,
        neueigentuemer_ev=kaeufer_ev,
        wechsel_datum=wirkungs_periode,
        meldedatum=stichtag,
        status='freigegeben',
        freigegeben_am=now,
        erstellt_von=user,
        auszahlungsbetrag=erstattung_summe,
        auszahlungs_iban=verkaeufer_iban,
    )

    # Das Personenkonto des Käufers legt das post_save-Signal auf
    # EigentumsVerhaeltnis an — mit der nächsten freien Nummer im Objekt, also
    # NICHT der Nummer des Verkäufers. Die Nummer wird mit zurückgegeben, damit
    # der Abschlussdialog zeigt, wo die neuen Sollstellungen zu finden sind.
    kaeufer_pk = getattr(kaeufer_ev, 'personenkonto', None)
    verkaeufer_pk = getattr(verkaeufer_ev, 'personenkonto', None)

    return {
        'wechsel_id': str(vorgang.id),
        'kaeufer_ev_id': str(kaeufer_ev.id),
        'kaeufer_personenkonto_nr': kaeufer_pk.kontonummer if kaeufer_pk else None,
        'verkaeufer_personenkonto_nr': verkaeufer_pk.kontonummer if verkaeufer_pk else None,
        'auszahlungslauf_id': None,
        'nachhol_sollstellungs_ids': nachhol_ids,
        'stornierte_sollstellungs_ids': stornieren_ids,
    }
