"""
Adress-Hilfsfunktionen für ``Person``.

Hintergrund: ``Person.adresse`` war lange ein einzelnes ``TextField`` im
Format::

    Otto-Hahn-Straße 60
    63303 Dreieich

Seit der Aufteilung in ``strasse``/``hausnummer``/``plz``/``ort`` sind die
Einzelfelder führend; ``adresse`` bleibt als zusammengesetzter Textblock
erhalten, weil mehrere Stellen ihn direkt als Anschrift verwenden
(Anschreiben-PDF der Jahresabrechnung, Postversand der
Eigentümerversammlung). ``Person.save()`` hält beides synchron.

Dieses Modul enthält bewusst nur reine String-Funktionen ohne Model-Bezug —
so kann die Datenmigration sie unverändert mitbenutzen.
"""
import re

# Hausnummer am Zeilenende: Ziffern, optional Buchstabe, optional Bereich
# ("15-21", "12 a", "3/5"). Der Straßenname ist alles davor.
_HAUSNUMMER = re.compile(
    r'^(?P<strasse>.*?)\s+'
    r'(?P<hausnummer>\d+\s*[a-zA-Z]?(?:\s*[-/]\s*\d+\s*[a-zA-Z]?)?)$'
)

# Postleitzahl am Zeilenanfang, danach der Ort ("63303 Dreieich").
_PLZ_ORT = re.compile(r'^(?P<plz>\d{4,5})\s+(?P<ort>.+)$')


def trenne_strasse_hausnummer(zeile: str) -> tuple[str, str]:
    """``"Otto-Hahn-Straße 60"`` → ``("Otto-Hahn-Straße", "60")``.

    Ohne erkennbare Hausnummer landet die ganze Zeile im Straßennamen —
    das ist die verlustfreie Variante: lieber eine Straße ohne Hausnummer
    als eine falsch abgeschnittene Adresse.
    """
    zeile = (zeile or '').strip()
    if not zeile:
        return '', ''

    treffer = _HAUSNUMMER.match(zeile)
    if treffer is None:
        return zeile, ''
    return treffer.group('strasse').strip(), treffer.group('hausnummer').strip()


def trenne_plz_ort(zeile: str) -> tuple[str, str]:
    """``"63303 Dreieich"`` → ``("63303", "Dreieich")``."""
    zeile = (zeile or '').strip()
    if not zeile:
        return '', ''

    treffer = _PLZ_ORT.match(zeile)
    if treffer is None:
        return '', zeile
    return treffer.group('plz'), treffer.group('ort').strip()


def zerlege_adresse(adresse: str) -> dict:
    """Zerlegt einen Adress-Textblock in die vier Einzelfelder.

    Erwartet wird der im Bestand übliche zweizeilige Aufbau (Straße +
    Hausnummer / PLZ + Ort). Zusätzliche Zeilen davor (z.B. ein
    Adresszusatz) werden dem Straßenteil vorangestellt, damit nichts
    verloren geht.

    Rückgabe: ``{'strasse', 'hausnummer', 'plz', 'ort'}`` — bei nicht
    interpretierbarem Text stehen die unklaren Anteile in ``strasse``.
    """
    leer = {'strasse': '', 'hausnummer': '', 'plz': '', 'ort': ''}
    zeilen = [z.strip() for z in (adresse or '').splitlines() if z.strip()]
    if not zeilen:
        return leer

    # Einzeiler: keine PLZ-Zeile vorhanden — alles als Straße behandeln.
    if len(zeilen) == 1:
        strasse, hausnummer = trenne_strasse_hausnummer(zeilen[0])
        return {'strasse': strasse, 'hausnummer': hausnummer, 'plz': '', 'ort': ''}

    plz, ort = trenne_plz_ort(zeilen[-1])
    strassen_teil = ' '.join(zeilen[:-1])
    strasse, hausnummer = trenne_strasse_hausnummer(strassen_teil)

    return {'strasse': strasse, 'hausnummer': hausnummer, 'plz': plz, 'ort': ort}


def baue_adresse(strasse: str, hausnummer: str, plz: str, ort: str) -> str:
    """Setzt die vier Einzelfelder zum Anschrift-Textblock zusammen."""
    zeile1 = ' '.join(t for t in [(strasse or '').strip(), (hausnummer or '').strip()] if t)
    zeile2 = ' '.join(t for t in [(plz or '').strip(), (ort or '').strip()] if t)
    return '\n'.join(z for z in [zeile1, zeile2] if z)
