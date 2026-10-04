"""Anbindung des Mahnwesens an das Modul Vorlagen & Korrespondenz (Spec 9.1).

Der Mahnlauf (``buchhaltung.services.mahnwesen.fuehre_mahnlauf_aus``) rechnet und
bucht unverändert. Nur bei ``settings.KORRESPONDENZ_MAHNWESEN_AKTIV`` ruft er dieses
Modul an drei Stellen auf; ohne den Schalter (Default) verhält er sich exakt wie zuvor::

    1. pruefe_vorlagen          vor jeder Buchung: gibt es für alle vorkommenden Stufen
                                eine aktive Vorlage mit freigegebener Version?
    2. erfasse_snapshots        vor jeder Änderung: offene Posten und Kontoauszug je
                                Personenkonto einfrieren (Stand des Mahnlaufs)
    3. erstelle_schreiben       nach dem Anlegen der Mahnungen, noch IN der Transaktion:
                                je Mahnung ein Schreiben anlegen und rendern. Ist etwas nicht
                                erzeugbar -> ``MahnBlockade``, die Transaktion rollt komplett
                                zurück (kein halber Lauf).
       plane_freigabe           per ``transaction.on_commit``: Schreiben freigeben (PDF samt
                                Kontoauszug-Anlage -> DMS), ``Mahnung.pdf_pfad`` setzen und den
                                Versand über die bestehende Pipeline anstoßen.

Dass Rendern und Layoutprüfung schon in der Transaktion laufen, ist die Blockade: Erst
nach dem Commit gibt es nur noch das (dateibasierte) PDF, dessen Fehler den Lauf nicht
mehr zurückrollen können - sie werden als Frontoffice-Aufgabe gemeldet.

Offene-Posten-Konsistenz: Die Tabelle ``mahnung.offene_posten`` liest den zum Mahnlauf
eingefrorenen Stand aus ``Schreiben.eingabewerte`` (siehe ``kontext_service``), nicht
den Live-Stand. Ein Schreiben, das später neu gerendert wird, zeigt daher dieselben
Posten wie der Mahnlauf, auch wenn inzwischen gezahlt oder auf ``forderungsfall`` gesetzt wurde.
"""
import logging
from datetime import date
from decimal import Decimal

from django.conf import settings

from . import kontoauszug_anlage_service, kontext_service, schreiben_service, vorlage_service
from .kontext_service import MAHNUNG_OP_SNAPSHOT
from .vorlage_service import VorlageNichtGefunden

logger = logging.getLogger(__name__)

KONTOAUSZUG_SNAPSHOT = '_mahnung_kontoauszug'

# Mahnstufe des Mahnlaufs -> Vorlagen-Code (Spec 9.1), RELATIV zur Stufenzahl des Objekts
# (``MahnEinstellung.anzahl_mahnstufen``):
#
#   letzte Stufe (== anzahl_mahnstufen)   -> mahnung_stufe_3   (+ Brief-Pflicht, ``kanal_service``)
#   alle früheren Stufen                  -> mahnung_stufe_2
#   mahnung_stufe_1                       bleibt ungenutzt (der Lauf erzeugt keine Zahlungserinnerung)
#
# Bei 2 Stufen: Stufe 1 -> mahnung_stufe_2, Stufe 2 -> mahnung_stufe_3. Bei 1 Stufe: Stufe 1
# ist die letzte -> mahnung_stufe_3. ``simuliere_mahnlauf`` erzeugt nur Stufen 1..anzahl_mahnstufen.
VORLAGE_LETZTE_STUFE = 'mahnung_stufe_3'
VORLAGE_FRUEHERE_STUFE = 'mahnung_stufe_2'


class MahnBlockade(ValueError):
    """Mahnlauf wegen fehlender Vorlage oder nicht erzeugbarer Schreiben blockiert.

    ``ValueError``, damit die bestehende Ansicht (``except ValueError`` -> HTTP 400)
    die Meldung ohne Änderung ausliefert.
    """


def ist_aktiv() -> bool:
    return bool(getattr(settings, 'KORRESPONDENZ_MAHNWESEN_AKTIV', False))


def vorlage_code(mahnstufe: int, anzahl_mahnstufen: int) -> str:
    """Vorlagen-Code der Stufe: letzte Stufe -> ``mahnung_stufe_3``, frühere -> ``mahnung_stufe_2``."""
    try:
        stufe, letzte = int(mahnstufe), int(anzahl_mahnstufen)
    except (TypeError, ValueError):
        stufe = letzte = 0
    if not 1 <= stufe <= letzte:
        raise MahnBlockade(
            f'Mahnstufe {mahnstufe!r} ist keiner Mahn-Vorlage zugeordnet '
            f'(gültig: 1 bis {anzahl_mahnstufen!r}).'
        )
    return VORLAGE_LETZTE_STUFE if stufe == letzte else VORLAGE_FRUEHERE_STUFE


def _name(personenkonto) -> str:
    return f'{personenkonto.eigentuemer.name} (Personenkonto {personenkonto.kontonummer})'


# --------------------------------------------------------------------------
# 1. Vorlagen-Prüfung (vor jeder Buchung)
# --------------------------------------------------------------------------

def pruefe_vorlagen(mahnstufen, objekt, anzahl_mahnstufen: int) -> None:
    """Blockiert, wenn für eine vorkommende Stufe keine aktive Vorlage mit freigegebener Version existiert."""
    codes = sorted({vorlage_code(s, anzahl_mahnstufen) for s in mahnstufen})
    fehlend = []
    for code in codes:
        try:
            vorlage_service.aktive_version(vorlage_service.aufloesen(code, objekt))
        except VorlageNichtGefunden as exc:
            fehlend.append(str(exc))
    if fehlend:
        raise MahnBlockade(
            'Mahnlauf blockiert - Vorlage fehlt: ' + ' '.join(fehlend)
            + ' Bitte Vorlage anlegen und freigeben (oder den Schalter KORRESPONDENZ_MAHNWESEN_AKTIV abschalten).'
        )


# --------------------------------------------------------------------------
# 2. Snapshots (vor jeder Änderung des Mahnlaufs)
# --------------------------------------------------------------------------

def erfasse_snapshots(vorschau_mahnungen, stichtag: date) -> dict:
    """``{personenkonto_id: {eingabewerte-Schlüssel: Momentaufnahme}}`` für alle zu mahnenden Konten."""
    from apps.konten.models import Personenkonto

    ids = [m['personenkonto_id'] for m in vorschau_mahnungen]
    konten = {
        str(pk): konto for pk, konto in Personenkonto.objects.select_related(
            'eigentuemer', 'objekt', 'vertrag__einheit',
        ).in_bulk(ids).items()
    }
    return {
        pk_id: {
            MAHNUNG_OP_SNAPSHOT: kontext_service.friere_offene_posten_ein(konten[pk_id], stichtag),
            KONTOAUSZUG_SNAPSHOT: kontoauszug_anlage_service.baue_daten(konten[pk_id], stichtag),
        }
        for pk_id in ids
    }


# --------------------------------------------------------------------------
# 3. Schreiben anlegen (in der Transaktion) und freigeben (nach dem Commit)
# --------------------------------------------------------------------------

def _pruefe_summe(mahnung, snapshot: dict) -> None:
    summe = sum((Decimal(z['betrag_offen']) for z in snapshot[MAHNUNG_OP_SNAPSHOT]), Decimal('0'))
    if summe != mahnung.offene_posten_summe:
        raise MahnBlockade(
            f'Offene Posten ({summe}) weichen von der Mahnung ({mahnung.offene_posten_summe}) ab.'
        )


def _lege_schreiben_an(lauf, mahnung, snapshot: dict, user, anzahl_mahnstufen: int):
    _pruefe_summe(mahnung, snapshot)
    vorlage = vorlage_service.aufloesen(
        vorlage_code(mahnung.mahnstufe, anzahl_mahnstufen), lauf.objekt,
    )
    version = vorlage_service.aktive_version(vorlage)
    konto = mahnung.personenkonto
    ev = konto.vertrag
    return schreiben_service.erstelle_aus_version(
        version, konto.eigentuemer, objekt=lauf.objekt,
        einheit=ev.einheit if ev is not None else None,
        eigentumsverhaeltnis=ev, mahnung=mahnung, eingabewerte=dict(snapshot),
        unterzeichner=lauf.objekt.betreuer, user=user,
    )


def erstelle_schreiben(lauf, mahnungen, snapshots: dict, user, anzahl_mahnstufen: int) -> list:
    """Legt je Mahnung ein gerendertes Schreiben (``zur_pruefung``) an; Rückgabe: deren Ids.

    Muss innerhalb der Transaktion des Mahnlaufs laufen. Ist auch nur ein Schreiben nicht
    erzeugbar, wird ``MahnBlockade`` mit ALLEN Ursachen geworfen (Rollback des ganzen Laufs).
    """
    ids, fehler = [], []
    for mahnung in mahnungen:
        try:
            schreiben = _lege_schreiben_an(
                lauf, mahnung, snapshots[str(mahnung.personenkonto_id)], user, anzahl_mahnstufen,
            )
        except (MahnBlockade, VorlageNichtGefunden) as exc:
            fehler.append(f'{_name(mahnung.personenkonto)}: {exc}')
            continue
        if schreiben.status != 'zur_pruefung':
            fehler.append(f'{_name(mahnung.personenkonto)}: nicht erzeugbar - {schreiben.fehler}')
        else:
            ids.append(schreiben.pk)
    if fehler:
        raise MahnBlockade(
            f'Mahnlauf blockiert - {len(fehler)} Schreiben nicht erzeugbar: ' + ' | '.join(fehler)
        )
    return ids


def anlagen_fuer(schreiben):
    """Kontoauszug-Anlage eines Mahnschreibens (aus dem gespeicherten Stand); ``None`` ohne Auszugsdaten."""
    daten = (schreiben.eingabewerte or {}).get(KONTOAUSZUG_SNAPSHOT)
    if not daten:
        return None
    return [kontoauszug_anlage_service.erzeuge_anlage(daten)]


def _melde_nicht_erzeugbar(schreiben, user, grund: str) -> None:
    from apps.buchhaltung.models import FrontofficeAufgabe

    ev = schreiben.eigentumsverhaeltnis
    FrontofficeAufgabe.objects.create(
        objekt=schreiben.objekt, aufgabe_typ='schreiben_nicht_erzeugbar',
        beschreibung=(
            f'Mahnschreiben {schreiben.nummer} für {schreiben.empfaenger.name} konnte nicht '
            f'freigegeben werden (PDF/Kontoauszug): {grund}'
        ),
        ev_id=ev.pk if ev is not None else None,
        einheit_nr=schreiben.einheit.einheit_nr if schreiben.einheit_id else '',
        erstellt_von=user,
    )


def _stosse_versand_an(schreiben, user) -> None:
    from apps.korrespondenz.tasks import versende_schreiben

    versende_schreiben.delay(str(schreiben.pk), user.pk if user is not None else None)


def _gib_frei(schreiben_id, user) -> None:
    """Ein Schreiben: freigeben (PDF + Kontoauszug), ``pdf_pfad`` setzen, Versand anstoßen.

    Wirft nie: nach dem Commit kann ein Fehler den Mahnlauf nicht mehr zurückrollen.
    """
    from apps.buchhaltung.models import Mahnung
    from apps.korrespondenz.models import Schreiben

    schreiben = Schreiben.objects.select_related(
        'objekt', 'einheit', 'eigentumsverhaeltnis', 'empfaenger', 'mahnung',
    ).get(pk=schreiben_id)
    try:
        schreiben_service.freigeben(schreiben, user)
        Mahnung.objects.filter(pk=schreiben.mahnung_id).update(pdf_pfad=schreiben.dokument.datei.name)
    except Exception as exc:  # noqa: BLE001 - siehe Docstring
        logger.exception('Mahnschreiben %s konnte nicht freigegeben werden.', schreiben.nummer)
        _melde_nicht_erzeugbar(schreiben, user, str(exc))
        return
    try:
        _stosse_versand_an(schreiben, user)
    except Exception:  # noqa: BLE001 - Broker nicht erreichbar: bleibt freigegeben, manuell versendbar
        logger.exception('Versand für Mahnschreiben %s konnte nicht angestoßen werden.', schreiben.nummer)


def plane_freigabe(schreiben_ids, user) -> None:
    """Gibt die Schreiben nach dem Commit des Mahnlaufs frei (``transaction.on_commit``)."""
    from django.db import transaction

    def _nach_commit():
        for schreiben_id in schreiben_ids:
            _gib_frei(schreiben_id, user)

    transaction.on_commit(_nach_commit)
