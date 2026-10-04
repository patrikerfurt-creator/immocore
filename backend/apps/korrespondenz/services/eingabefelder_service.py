"""Validierung und Typisierung der Eingabefelder einer Vorlagenversion (Spec 3.5).

Eingabefelder sind Werte, die nicht in der Datenbank stehen, sondern je
Schreiben bzw. Serienlauf einmal eingegeben werden::

    [{"name": "versammlung_datum", "label": "Datum", "typ": "datum",
      "pflicht": true, "default": null}, ...]

``validiere`` prüft die Eingaben gegen diese Definition (Pflicht + Typ) und
liefert die getypten Werte, die die Render-Engine als ``eingabe.<name>``
sieht. Die Funktion ist rein (kein DB-Zugriff) und daher direkt testbar;
die Serienlauf-Freigabe (Phase 4) ruft sie auf.
"""
import re
from dataclasses import dataclass, field
from datetime import date, time
from decimal import Decimal, InvalidOperation

EINGABE_TYPEN = ('text', 'mehrzeilig', 'datum', 'uhrzeit', 'betrag', 'liste', 'ja_nein')

_NAME = re.compile(r'^[a-z_][a-z0-9_]*$')
_JA = {'1', 'true', 'ja', 'yes', 'on', 'j'}
_NEIN = {'0', 'false', 'nein', 'no', 'off', 'n'}


@dataclass
class EingabeValidierung:
    """Ergebnis von ``validiere``: getypte Werte + Fehlermeldungen (leer = gültig)."""
    werte: dict = field(default_factory=dict)
    fehler: list = field(default_factory=list)

    @property
    def gueltig(self) -> bool:
        return not self.fehler


def _ist_leer(wert) -> bool:
    if wert is None:
        return True
    if isinstance(wert, str):
        return not wert.strip()
    if isinstance(wert, (list, tuple)):
        return not any(not _ist_leer(x) for x in wert)
    return False


def _konvertiere_datum(wert) -> date:
    if isinstance(wert, date):
        return wert
    text = str(wert).strip()
    treffer = re.fullmatch(r'(\d{1,2})\.(\d{1,2})\.(\d{4})', text)
    if treffer:
        return date(int(treffer.group(3)), int(treffer.group(2)), int(treffer.group(1)))
    return date.fromisoformat(text[:10])


def _konvertiere_uhrzeit(wert) -> time:
    if isinstance(wert, time):
        return wert
    treffer = re.fullmatch(r'\s*(\d{1,2})[:.](\d{2})(?::\d{2})?\s*', str(wert))
    if not treffer:
        raise ValueError('keine Uhrzeit')
    return time(int(treffer.group(1)), int(treffer.group(2)))


def _konvertiere_betrag(wert) -> Decimal:
    if isinstance(wert, bool):
        raise ValueError('kein Betrag')
    if isinstance(wert, (int, Decimal)):
        return Decimal(wert)
    text = str(wert).strip().replace('€', '').replace(' ', '')
    if ',' in text:  # deutsches Format: 1.234,56
        text = text.replace('.', '').replace(',', '.')
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError('kein Betrag') from exc


def _konvertiere_liste(wert) -> list:
    if isinstance(wert, str):
        wert = wert.splitlines()
    if not isinstance(wert, (list, tuple)):
        raise ValueError('keine Liste')
    return [str(x).strip() for x in wert if not _ist_leer(x)]


def _konvertiere_ja_nein(wert) -> bool:
    if isinstance(wert, bool):
        return wert
    text = str(wert).strip().lower()
    if text in _JA:
        return True
    if text in _NEIN:
        return False
    raise ValueError('kein Ja/Nein-Wert')


def _konvertiere_text(wert) -> str:
    if isinstance(wert, (dict, list, tuple)):
        raise ValueError('kein Text')
    return str(wert).strip()


_KONVERTER = {
    'text': _konvertiere_text,
    'mehrzeilig': _konvertiere_text,
    'datum': _konvertiere_datum,
    'uhrzeit': _konvertiere_uhrzeit,
    'betrag': _konvertiere_betrag,
    'liste': _konvertiere_liste,
    'ja_nein': _konvertiere_ja_nein,
}


def pruefe_definition(eingabefelder) -> list:
    """Fehlermeldungen zur Felddefinition selbst (leer = in Ordnung)."""
    fehler = []
    if not isinstance(eingabefelder, list):
        return ['Eingabefelder müssen eine Liste sein.']
    gesehen = set()
    for nr, feld in enumerate(eingabefelder, start=1):
        if not isinstance(feld, dict):
            fehler.append(f'Eingabefeld {nr}: kein Objekt.')
            continue
        name = feld.get('name')
        if not isinstance(name, str) or not _NAME.match(name):
            fehler.append(f'Eingabefeld {nr}: ungültiger Name {name!r}.')
        elif name in gesehen:
            fehler.append(f'Eingabefeld {name!r} ist doppelt definiert.')
        else:
            gesehen.add(name)
        if feld.get('typ') not in EINGABE_TYPEN:
            fehler.append(f'Eingabefeld {name!r}: unbekannter Typ {feld.get("typ")!r}.')
    return fehler


def _pruefe_feld(feld: dict, eingabewerte: dict):
    """(wert, fehlermeldung) für ein einzelnes Feld; wert ``None`` = nicht gesetzt."""
    name = feld['name']
    label = feld.get('label') or name
    roh = eingabewerte.get(name)
    if _ist_leer(roh):
        roh = feld.get('default')

    if _ist_leer(roh):
        if feld.get('pflicht'):
            return None, f'Pflichtfeld "{label}" fehlt.'
        return None, None

    try:
        return _KONVERTER[feld['typ']](roh), None
    except (ValueError, TypeError):
        return None, f'Feld "{label}": Wert {roh!r} passt nicht zum Typ "{feld["typ"]}".'


def validiere(eingabefelder, eingabewerte) -> EingabeValidierung:
    """Prüft ``eingabewerte`` gegen ``eingabefelder`` (Pflicht + Typ).

    Nicht definierte Schlüssel in ``eingabewerte`` werden ignoriert (nicht
    übernommen). Optionale, nicht gesetzte Felder fehlen in ``werte``
    (Zugriff im Template ohne ``default`` -> Render-Fehler, nie ein leerer
    Wert). ``ja_nein=False`` zählt als gesetzt.
    """
    ergebnis = EingabeValidierung()
    definitionsfehler = pruefe_definition(eingabefelder)
    if definitionsfehler:
        ergebnis.fehler.extend(definitionsfehler)
        return ergebnis

    eingabewerte = eingabewerte or {}
    for feld in eingabefelder:
        wert, meldung = _pruefe_feld(feld, eingabewerte)
        if meldung:
            ergebnis.fehler.append(meldung)
        elif wert is not None:
            ergebnis.werte[feld['name']] = wert
    return ergebnis
