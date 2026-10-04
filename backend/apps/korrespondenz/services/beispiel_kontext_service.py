"""Beispieldaten für die Layout-Vorschau einer Vorlage (NUR Vorschau, nie ein echtes Schreiben).

Die PDF-Vorschau im Editor soll JEDE Vorlage zeigen können - auch Begrüßung, Mahnung,
Eigentümerwechsel und Vorgang, deren anlassspezifische Gruppen (``wechsel``, ``mahnung``,
``vorgang``) sich aus Person + Einheit nicht auflösen lassen, und auch Objekte ohne
Betreuer oder Bankkonto. Dieses Modul füllt dafür den echten Kontext aus
``kontext_service.baue_kontext`` mit den Beispielwerten der ``registry`` auf:

* Reale Werte haben VORRANG; ein Beispielwert kommt nur dort zum Einsatz, wo der reale
  Wert fehlt oder leer ist (``None``, ``''``, leere Liste).
* Ausdrücklich optionale leere Angaben einer realen Gruppe (``empfaenger.briefanrede2``
  bei einer Einzelperson, ``schreiben.ihr_zeichen``) bleiben leer.
* ``eingabe.*``: vom Aufrufer übergebene Werte (und Feld-Defaults) haben Vorrang, fehlende
  Felder bekommen ein Beispiel passend zum Feldtyp.

Der Aufruf geschieht ausschließlich im ``vorschau_service``. ``render_service`` und der
Erzeugungs-/Freigabepfad (``schreiben_service``) kennen dieses Modul nicht und bleiben streng
(``StrictUndefined``, keine leeren Werte).
"""
import copy
from datetime import date, datetime, time
from decimal import Decimal

from . import kontext_service, registry

# Gruppe ``eingabe`` wird über ``fuelle_eingabewerte`` behandelt, nicht über den Kontext.
_EINGABE = 'eingabe'


# --------------------------------------------------------------------------
# Beispielwerte typisieren
# --------------------------------------------------------------------------

def _beispiel_datum(wert, heute: date):
    if wert in (None, ''):
        return heute
    if isinstance(wert, (date, datetime)):
        return wert
    text = str(wert).strip()
    if 'T' in text:
        return datetime.fromisoformat(text)
    return date.fromisoformat(text[:10])


def _beispiel_zeile(zeile: dict, spalten: list, heute: date) -> dict:
    formate = {s['feld']: s.get('format', 'text') for s in spalten}
    typisiert = {}
    for feld, wert in zeile.items():
        format_ = formate.get(feld, 'text')
        if format_ == 'datum':
            typisiert[feld] = _beispiel_datum(wert, heute)
        elif format_ == 'euro':
            typisiert[feld] = Decimal(str(wert))
        else:
            typisiert[feld] = wert
    return typisiert


def _beispiel_tabelle(name: str, wert, heute: date) -> list:
    spalten = registry.TABELLEN.get(name)
    zeilen = copy.deepcopy(wert) if wert else []
    if not spalten:
        return zeilen
    return [_beispiel_zeile(z, spalten, heute) for z in zeilen]


def _standard_beispiel(typ: str, name: str, heute: date):
    """Sinnvoller Platzhalterwert, wenn die Registry kein ``beispiel`` hat."""
    return {
        'datum': heute,
        'betrag': Decimal('100.00'),
        'zahl': 1,
        'bool': True,
        'liste': ['Beispiel 1', 'Beispiel 2'],
        'tabelle': [],
    }.get(typ, f'Beispiel {name.rpartition(".")[2]}')


def beispielwert(eintrag: dict, heute: date):
    """Typisierter Beispielwert eines Registry-Eintrags (``{name, typ, beispiel, ...}``)."""
    typ, name, roh = eintrag['typ'], eintrag['name'], eintrag.get('beispiel')
    if roh is None:
        roh = _standard_beispiel(typ, name, heute)
    if typ == 'datum':
        return _beispiel_datum(roh, heute)
    if typ == 'betrag':
        return Decimal(str(roh))
    if typ == 'zahl':
        return int(roh)
    if typ == 'tabelle':
        return _beispiel_tabelle(name, roh, heute)
    return copy.deepcopy(roh)


def baue_beispiel_kontext(anlass: str, heute: date) -> dict:
    """Vollständiger Beispiel-Kontext ``{gruppe: {name: wert}}`` aller Registry-Gruppen des Anlasses.

    Die dynamische Gruppe ``eingabe`` ist nicht enthalten (siehe ``fuelle_eingabewerte``).
    """
    kontext = {}
    for eintrag in registry.metadaten(anlass):
        gruppe, _, name = eintrag['name'].partition('.')
        if gruppe == _EINGABE:
            continue
        kontext.setdefault(gruppe, {})[name] = beispielwert(eintrag, heute)
    return kontext


# --------------------------------------------------------------------------
# Real vor Beispiel
# --------------------------------------------------------------------------

def _ist_leer(wert) -> bool:
    return wert is None or wert == '' or (isinstance(wert, (list, tuple, dict)) and not wert)


def _reale_gruppe_gewinnt(gruppe: str, name: str, wert) -> bool:
    if not _ist_leer(wert):
        return True
    # Optionales Leer (z. B. Einzelperson ohne briefanrede2) ist ein realer Wert.
    return wert == '' and (gruppe, name) in kontext_service.OPTIONAL_LEER


def mische_real_vor_beispiel(real: dict, beispiel: dict) -> dict:
    """Tiefer Merge je Gruppe: realer, nicht leerer Wert gewinnt, sonst der Beispielwert."""
    ergebnis = {}
    for gruppe, beispiel_werte in beispiel.items():
        werte = dict(beispiel_werte)
        for name, wert in (real.get(gruppe) or {}).items():
            if _reale_gruppe_gewinnt(gruppe, name, wert):
                werte[name] = wert
        ergebnis[gruppe] = werte
    for gruppe, real_werte in real.items():     # reale Gruppen ohne Beispielpendant bleiben erhalten
        if gruppe not in ergebnis:
            ergebnis[gruppe] = real_werte
    return ergebnis


def fuelle_kontext_mit_beispielen(anlass: str, echter_kontext: dict, heute: date) -> dict:
    """Echter Kontext, aufgefüllt mit den Registry-Beispielen des Anlasses (real vor Beispiel)."""
    return mische_real_vor_beispiel(echter_kontext, baue_beispiel_kontext(anlass, heute))


# --------------------------------------------------------------------------
# Eingabefelder
# --------------------------------------------------------------------------

def _beispiel_eingabe(feld: dict, heute: date):
    label = feld.get('label') or feld.get('name')
    typ = feld.get('typ')
    if typ == 'mehrzeilig':
        return f'Beispieltext für "{label}".'
    if typ == 'datum':
        return heute
    if typ == 'uhrzeit':
        return time(10, 0)
    if typ == 'betrag':
        return Decimal('100.00')
    if typ == 'liste':
        return ['Beispiel 1', 'Beispiel 2']
    if typ == 'ja_nein':
        return True
    return f'Beispiel {label}'


def _eingabe_fehlt(wert) -> bool:
    if wert is None:
        return True
    if isinstance(wert, str):
        return not wert.strip()
    if isinstance(wert, (list, tuple)):
        return not any(not _eingabe_fehlt(x) for x in wert)
    return False


def fuelle_eingabewerte(eingabefelder, eingabewerte, heute: date) -> dict:
    """Eingabewerte des Aufrufers + Beispiele für jedes Feld ohne Wert und ohne Default."""
    ergebnis = dict(eingabewerte or {})
    for feld in eingabefelder or []:
        if not isinstance(feld, dict) or not feld.get('name'):
            continue                       # kaputte Felddefinition meldet die Validierung
        if _eingabe_fehlt(ergebnis.get(feld['name'])) and _eingabe_fehlt(feld.get('default')):
            ergebnis[feld['name']] = _beispiel_eingabe(feld, heute)
    return ergebnis
