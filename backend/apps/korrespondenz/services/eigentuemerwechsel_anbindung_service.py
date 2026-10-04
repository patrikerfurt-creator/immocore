"""Anbindung des Eigentümerwechsels an das Modul Vorlagen & Korrespondenz (Spec 9.2).

Die Wechsel-Freigabe (``buchhaltung.services.eigentuemerwechsel_korrektur_service.vorschau_committen``)
korrigiert und bucht unverändert. Als LETZTEN Schritt ruft sie ``plane_schreiben`` auf
(expliziter Service-Aufruf, kein Signal). Das registriert per ``transaction.on_commit``::

    * Begrüßungsschreiben ``eigentuemer_begruessung`` an den Neueigentümer (Status ``zur_pruefung``,
      NICHT automatisch freigegeben - es wartet im Postausgang auf die Prüfung)
    * optional ``eigentuemer_verabschiedung`` an den Voreigentümer - nur, wenn dafür eine aktive
      Vorlage existiert

Bedingte Blöcke und Anlagen (SEPA-Hinweis + Pflichtanlage "SEPA-Formular", Hausordnung) stecken
in den Vorlagen (Block ``bedingt`` bzw. ``VorlageAnlage.bedingung``/``art``) und werden von
``schreiben_service``/``anlagen_service`` aufgelöst; dieser Service kennt sie nicht.

Fehlerverhalten: ``on_commit`` läuft NACH dem Commit der Freigabe. Kein Fehler hier kann die
Freigabe zurückrollen oder den Aufrufer erreichen. Fehlt die Begrüßungs-Vorlage, ist das
Schreiben nicht erzeugbar (fehlende Pflichtanlage, fehlender Pflichtwert, ...) oder
scheitert etwas unerwartet, entsteht eine ``FrontofficeAufgabe`` ``schreiben_nicht_erzeugbar``.
Ein nicht erzeugbares Schreiben bleibt zusätzlich als ``entwurf`` mit ``fehler`` im Postausgang.
"""
import logging
from dataclasses import dataclass, field

from django.db import transaction

from . import schreiben_service, vorlage_service
from .vorlage_service import VorlageNichtGefunden

logger = logging.getLogger(__name__)

CODE_BEGRUESSUNG = 'eigentuemer_begruessung'
CODE_VERABSCHIEDUNG = 'eigentuemer_verabschiedung'


@dataclass
class WechselSchreibenErgebnis:
    """``schreiben``: erzeugte Schreiben (``zur_pruefung``); ``fehler``: gemeldete Probleme (Texte)."""
    schreiben: list = field(default_factory=list)
    fehler: list = field(default_factory=list)


class SchreibenNichtErzeugbar(Exception):
    """Vorlage vorhanden, Schreiben aber nicht erzeugbar (Ursache in der Meldung)."""


# --------------------------------------------------------------------------
# Meldung
# --------------------------------------------------------------------------

def _melde_nicht_erzeugbar(vorgang, ev, bezeichnung: str, grund: str) -> None:
    from apps.buchhaltung.models import FrontofficeAufgabe

    FrontofficeAufgabe.objects.create(
        objekt=vorgang.objekt, aufgabe_typ='schreiben_nicht_erzeugbar',
        beschreibung=(
            f'{bezeichnung} zum Eigentümerwechsel (Einheit {vorgang.einheit.einheit_nr}, '
            f'ab {vorgang.wechsel_datum}) für {ev.person.name} konnte nicht erzeugt werden: {grund}'
        ),
        ev_id=ev.pk, einheit_nr=vorgang.einheit.einheit_nr,
        erstellt_von=vorgang.freigegeben_von,
    )


def _melde_sicher(vorgang, ev, bezeichnung: str, grund: str, ergebnis: WechselSchreibenErgebnis) -> None:
    """Meldet das Problem als Aufgabe; scheitert auch das, wird nur protokolliert (nach dem Commit)."""
    ergebnis.fehler.append(f'{bezeichnung}: {grund}')
    try:
        _melde_nicht_erzeugbar(vorgang, ev, bezeichnung, grund)
    except Exception:  # noqa: BLE001 - nach dem Commit darf nichts mehr durchschlagen
        logger.exception('Eigentümerwechsel %s: Aufgabe "nicht erzeugbar" konnte nicht angelegt werden.', vorgang.pk)


# --------------------------------------------------------------------------
# Erzeugen
# --------------------------------------------------------------------------

def _erzeuge(vorgang, ev, version):
    """Legt ein Schreiben an ``ev.person`` an; nicht erzeugbar -> ``SchreibenNichtErzeugbar``."""
    schreiben = schreiben_service.erstelle_aus_version(
        version, ev.person, objekt=vorgang.objekt, einheit=vorgang.einheit,
        eigentumsverhaeltnis=ev, eigentuemerwechsel=vorgang,
        unterzeichner=vorgang.objekt.betreuer, user=vorgang.freigegeben_von,
    )
    if schreiben.status != 'zur_pruefung':
        raise SchreibenNichtErzeugbar(f'{schreiben.nummer} nicht erzeugbar - {schreiben.fehler}')
    return schreiben


def _begruessung(vorgang, ergebnis: WechselSchreibenErgebnis) -> None:
    ev = vorgang.neueigentuemer_ev
    try:
        version = vorlage_service.aktive_version(vorlage_service.aufloesen(CODE_BEGRUESSUNG, vorgang.objekt))
        ergebnis.schreiben.append(_erzeuge(vorgang, ev, version))
    except VorlageNichtGefunden as exc:
        _melde_sicher(vorgang, ev, 'Begrüßungsschreiben', f'Vorlage fehlt - {exc}', ergebnis)
    except SchreibenNichtErzeugbar as exc:
        _melde_sicher(vorgang, ev, 'Begrüßungsschreiben', str(exc), ergebnis)
    except Exception as exc:  # noqa: BLE001 - siehe Modul-Docstring
        logger.exception('Eigentümerwechsel %s: Begrüßungsschreiben fehlgeschlagen.', vorgang.pk)
        _melde_sicher(vorgang, ev, 'Begrüßungsschreiben', f'Unerwarteter Fehler: {exc}', ergebnis)


def _verabschiedung(vorgang, ergebnis: WechselSchreibenErgebnis) -> None:
    ev = vorgang.voreigentuemer_ev
    if ev.person_id == vorgang.neueigentuemer_ev.person_id:
        return  # gleiche Person: nichts zu verabschieden
    try:
        vorlage = vorlage_service.aufloesen(CODE_VERABSCHIEDUNG, vorgang.objekt)
    except VorlageNichtGefunden:
        return  # optional: ohne aktive Vorlage passiert nichts
    try:
        version = vorlage_service.aktive_version(vorlage)
        ergebnis.schreiben.append(_erzeuge(vorgang, ev, version))
    except (VorlageNichtGefunden, SchreibenNichtErzeugbar) as exc:
        _melde_sicher(vorgang, ev, 'Verabschiedungsschreiben', str(exc), ergebnis)
    except Exception as exc:  # noqa: BLE001 - siehe Modul-Docstring
        logger.exception('Eigentümerwechsel %s: Verabschiedungsschreiben fehlgeschlagen.', vorgang.pk)
        _melde_sicher(vorgang, ev, 'Verabschiedungsschreiben', f'Unerwarteter Fehler: {exc}', ergebnis)


def erzeuge_schreiben(vorgang) -> WechselSchreibenErgebnis:
    """Erzeugt Begrüßung (Neueigentümer) und - falls Vorlage aktiv - Verabschiedung (Voreigentümer).

    Wirft nie; Probleme stehen im Ergebnis und als ``FrontofficeAufgabe``. Der Vorgang muss
    freigegeben sein (``freigegeben_von`` ist Ersteller der Schreiben/Aufgaben).
    """
    ergebnis = WechselSchreibenErgebnis()
    _begruessung(vorgang, ergebnis)
    _verabschiedung(vorgang, ergebnis)
    return ergebnis


# --------------------------------------------------------------------------
# Einstieg aus der Freigabe
# --------------------------------------------------------------------------

def _nach_commit(vorgang_id) -> None:
    from apps.buchhaltung.models import EigentuemerwechselVorgang

    try:
        vorgang = EigentuemerwechselVorgang.objects.select_related(
            'objekt__betreuer', 'einheit', 'freigegeben_von',
            'voreigentuemer_ev__person', 'neueigentuemer_ev__person',
        ).get(pk=vorgang_id)
        erzeuge_schreiben(vorgang)
    except Exception:  # noqa: BLE001 - die Freigabe ist bereits committet
        logger.exception('Eigentümerwechsel %s: Schreiben-Erzeugung fehlgeschlagen.', vorgang_id)


def plane_schreiben(vorgang) -> None:
    """Registriert die Schreiben-Erzeugung per ``transaction.on_commit`` (Aufruf aus der Wechsel-Freigabe)."""
    vorgang_id = vorgang.pk
    transaction.on_commit(lambda: _nach_commit(vorgang_id))
