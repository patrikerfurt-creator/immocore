"""Jinja-Filter der Render-Engine (Spec 4.1).

Monats- und Wochentagsnamen stehen bewusst FEST im Code: keine Abhängigkeit
von ``locale`` oder der Django-Sprachumgebung, damit dasselbe Eingabe-Paar
auf jedem Server byte-gleiche Ausgabe liefert (Determinismus, Test 3).

Alle Filter sind reine Funktionen. Sie akzeptieren neben den nativen Typen
(``date``, ``Decimal``) auch deren String-Formen (ISO-Datum, Dezimalzahl),
weil Kontextwerte aus JSON-Feldern (``Schreiben.eingabewerte``) stammen können.
"""
import re
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

MONATE = (
    'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
    'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember',
)
WOCHENTAGE = (
    'Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag',
)


def _als_datum(wert) -> date:
    if isinstance(wert, datetime):
        return wert.date()
    if isinstance(wert, date):
        return wert
    if isinstance(wert, str):
        return date.fromisoformat(wert.strip()[:10])
    raise ValueError(f'Kein Datum: {wert!r}')


def _als_uhrzeit(wert) -> time:
    if isinstance(wert, datetime):
        return wert.time()
    if isinstance(wert, time):
        return wert
    if isinstance(wert, str):
        treffer = re.fullmatch(r'\s*(\d{1,2})[:.](\d{2})(?::\d{2})?\s*', wert)
        if treffer:
            return time(int(treffer.group(1)), int(treffer.group(2)))
    raise ValueError(f'Keine Uhrzeit: {wert!r}')


def _als_decimal(wert) -> Decimal:
    if isinstance(wert, bool):
        raise ValueError(f'Kein Betrag: {wert!r}')
    try:
        return Decimal(str(wert))
    except InvalidOperation as exc:
        raise ValueError(f'Kein Betrag: {wert!r}') from exc


def euro(wert) -> str:
    """``Decimal('1234.5')`` -> ``'1.234,50 €'``."""
    betrag = _als_decimal(wert).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    vorzeichen = '-' if betrag < 0 else ''
    ganz, _, cent = f'{abs(betrag):.2f}'.partition('.')
    gruppiert = f'{int(ganz):,}'.replace(',', '.')
    return f'{vorzeichen}{gruppiert},{cent} €'


def datum(wert) -> str:
    """``29.09.2026``."""
    d = _als_datum(wert)
    return f'{d.day:02d}.{d.month:02d}.{d.year}'


def datum_mittel(wert) -> str:
    """``29. September 2026``."""
    d = _als_datum(wert)
    return f'{d.day}. {MONATE[d.month - 1]} {d.year}'


def datum_lang(wert) -> str:
    """``Dienstag, den 29. September 2026``."""
    d = _als_datum(wert)
    return f'{WOCHENTAGE[d.weekday()]}, den {datum_mittel(d)}'


def uhrzeit(wert) -> str:
    """``16.00 Uhr``."""
    t = _als_uhrzeit(wert)
    return f'{t.hour}.{t.minute:02d} Uhr'


def iban(wert) -> str:
    """Vierergruppen: ``DE0250190000...`` -> ``DE02 5019 0000 ...``."""
    kompakt = re.sub(r'\s+', '', str(wert)).upper()
    return ' '.join(kompakt[i:i + 4] for i in range(0, len(kompakt), 4))


def upper(wert) -> str:
    return str(wert).upper()


def default(wert, ersatz=''):
    """Ersatzwert bei ``None``, leerem String oder nicht definiertem Wert.

    Bewusst NICHT der Jinja-Builtin: der prüft nur auf ``Undefined``. Hier
    zählt auch ``None``/``''`` als "nicht vorhanden". ``False``/``0`` bleiben
    gültige Werte.
    """
    from jinja2 import Undefined
    if isinstance(wert, Undefined) or wert is None or wert == '':
        return ersatz
    return wert


FILTER = {
    'euro': euro,
    'datum': datum,
    'datum_lang': datum_lang,
    'datum_mittel': datum_mittel,
    'uhrzeit': uhrzeit,
    'iban': iban,
    'upper': upper,
    'default': default,
}
