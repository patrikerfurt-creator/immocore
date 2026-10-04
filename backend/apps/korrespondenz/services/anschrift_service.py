"""Anschriftzeilen für das Anschriftfeld (Spec 4.2, ersetzt ``EmpfAnsZeile1-7``).

Quelle sind die führenden Einzelfelder ``Person.strasse/hausnummer/plz/ort``
(Abw. 009). Das Modell ``Person`` hat KEIN Länderfeld: eine Auslandsanschrift
steht - wie die 7 Sonderfälle mit komplett in ``strasse`` stehender Adresse -
mehrzeilig in ``strasse`` und wird unverändert übernommen.
"""

MAX_ZEILEN = 7

# Person.anrede -> erste Anschriftzeile (DIN 5008: Akkusativ bei "Herr").
_ANREDE_ZEILE = {
    'Herr': 'Herrn',
    'Frau': 'Frau',
    'Eheleute': 'Eheleute',
    'Herren': 'Herren',
    'Damen': 'Damen',
    'Herr und Frau': 'Herrn und Frau',
    'Firma': 'Firma',
}


class AnschriftZuLang(ValueError):
    """Die Anschrift ergäbe mehr als 7 Zeilen - nie stillschweigend kürzen."""


def _zusammen(*teile) -> str:
    return ' '.join(t.strip() for t in teile if t and t.strip())


def _anredezeile(person) -> str:
    if person.ist_firma:
        return 'Firma'
    return _ANREDE_ZEILE.get(person.anrede, '')


def _namenszeilen(person) -> list:
    if person.ist_firma:
        return [_zusammen(person.firmenname) or _zusammen(person.vorname, person.nachname)]
    zeilen = [_zusammen(person.titel, person.vorname, person.nachname)]
    if person.vorname2.strip() or person.nachname2.strip():
        # Fehlt der 2. Nachname, gilt der 1. (gemeinsamer Familienname).
        zeilen.append(_zusammen(person.titel2, person.vorname2, person.nachname2 or person.nachname))
    return zeilen


def _strassenzeilen(person) -> list:
    zeilen = [z.strip() for z in (person.strasse or '').splitlines() if z.strip()]
    hausnummer = (person.hausnummer or '').strip()
    if zeilen and hausnummer:
        zeilen[-1] = f'{zeilen[-1]} {hausnummer}'
    return zeilen


def anschrift_zeilen(person) -> list:
    """Anschriftzeilen als Liste (höchstens 7, leere Zeilen entfallen)."""
    zeilen = [_anredezeile(person)]
    zeilen += _namenszeilen(person)
    zeilen += _strassenzeilen(person)
    zeilen.append(_zusammen(person.plz, person.ort))
    zeilen = [z for z in zeilen if z]
    if len(zeilen) > MAX_ZEILEN:
        raise AnschriftZuLang(
            f'Anschrift hat {len(zeilen)} Zeilen (maximal {MAX_ZEILEN}): {zeilen!r}'
        )
    return zeilen
