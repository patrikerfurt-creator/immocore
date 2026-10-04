"""Layout-Daten für den Briefbogen (Spec 5.2-5.4).

Dieses Modul entscheidet, WAS auf dem Briefbogen steht (Fußzeile WEG oder
Firma, Infoblock, Bezugszeichen, Objekt-/Flächenzeile, Anrede, Schluss) und
liefert dafür ein reines Dict für ``templates/korrespondenz/brief_base.html``.
Das Template enthält nur Darstellung. Das WeasyPrint-Rendering selbst steht in
``pdf_service``.

Grundsatz wie in der Registry: kein leerer oder falscher Wert im Brief. Was ein
WEG-Brief zwingend braucht (Bankverbindung der WEG, Unterzeichner), fehlt es
im Kontext, endet der Aufbau mit ``RenderFehler`` -> Schreiben "nicht erzeugbar".
"""
import base64
import math
import mimetypes
import re
from pathlib import Path

from . import filters
from .render_service import RenderFehler

ASSET_DIR = Path(__file__).resolve().parent.parent / 'assets'

# Abstand der Fußzeilen-Unterkante vom Blattrand und Mindest-Unterrand (Spec 5.2).
FUSS_ABSTAND_MM = 8.0
MIN_RAND_UNTEN_MM = 20.0
FUSS_PUFFER_MM = 3.0

_ANLAGE_BEGINN = '<section class="anlage-seite"'
_SEITENUMBRUCH_AM_ENDE = re.compile(
    r'(?:\s*<div class="seitenumbruch"[^>]*></div>)+\s*$'
)
_PFLICHT_ZEICHEN_JE_ZEILE = 125   # 6 pt Arial auf 160 mm Satzbreite, konservativ


# --------------------------------------------------------------------------
# Bilder
# --------------------------------------------------------------------------

def _data_uri(inhalt: bytes, dateiname: str) -> str:
    mime = mimetypes.guess_type(dateiname)[0] or 'application/octet-stream'
    return f'data:{mime};base64,{base64.b64encode(inhalt).decode("ascii")}'


def dokument_als_data_uri(dokument, was: str) -> str:
    """Liest die Bilddatei eines ``Dokument`` und liefert sie als data-URI.

    ``was`` nur für die Fehlermeldung ("Logo", "Verbandslogo").
    """
    try:
        with dokument.datei.open('rb') as f:
            inhalt = f.read()
    except (OSError, ValueError) as exc:
        raise RenderFehler(f'{was} des Briefbogens nicht lesbar: {exc}') from exc
    return _data_uri(inhalt, dokument.dateiname or dokument.datei.name)


def font_url(dateiname: str) -> str:
    return (ASSET_DIR / 'fonts' / dateiname).as_uri()


# --------------------------------------------------------------------------
# Fußzeile (5.4)
# --------------------------------------------------------------------------

def _ist_weg(kontext: dict) -> bool:
    return bool(kontext.get('objekt', {}).get('ist_weg'))


def _weg_fusszeile_zeilen(bank: dict) -> list:
    """Zeile 1 = WEG-Name, Zeile 2 = ``IBAN: … · BIC: … · Bank``."""
    teile = [f'IBAN: {filters.iban(bank["iban"])}', f'BIC: {bank["bic"]}']
    if bank.get('bankname'):
        teile.append(bank['bankname'])
    return [bank['weg_name'], ' · '.join(teile)]


def _pruefe_weg_bank(kontext: dict) -> dict:
    bank = kontext.get('bank') or {}
    fehlend = [k for k in ('weg_name', 'iban', 'bic') if not bank.get(k)]
    if fehlend:
        raise RenderFehler(
            'Fußzeilen-Bankkonto (Zahlungsverkehrskonto) des WEG-Objekts nicht eindeutig '
            'oder unvollständig - WEG-Brief nicht erzeugbar (fehlt: ' + ', '.join(fehlend) + ').'
        )
    return bank


def _pflichtangaben(briefbogen) -> str:
    if not briefbogen.pflichtangaben_anzeigen:
        return ''
    return (briefbogen.pflichtangaben or '').strip()


def _firma_fusszeile_zeilen(briefbogen) -> list:
    zeilen = (briefbogen.fuss_firma_zeile1, briefbogen.fuss_firma_zeile2, briefbogen.fuss_firma_zeile3)
    return [z.strip() for z in zeilen if z and z.strip()]


def _weg_fusszeile_hoehe_mm(pflicht: str) -> float:
    hoehe = 2 * 3.6                                   # 2 Zeilen 8 pt
    if pflicht:
        hoehe += 1.0 + math.ceil(len(pflicht) / _PFLICHT_ZEICHEN_JE_ZEILE) * 2.7   # 6 pt
    return hoehe


def _firma_fusszeile_hoehe_mm(zeilen: list) -> float:
    return len(zeilen) * 3.3                          # 7 pt


def baue_fusszeile(briefbogen, kontext: dict) -> dict:
    """Fußzeile je Objektart. ``typ`` = ``weg`` oder ``firma``."""
    if _ist_weg(kontext):
        pflicht = _pflichtangaben(briefbogen)
        return {
            'typ': 'weg',
            'zeilen': _weg_fusszeile_zeilen(_pruefe_weg_bank(kontext)),
            'pflichtangaben': pflicht,
            'logo_uri': '',
            'hoehe_mm': _weg_fusszeile_hoehe_mm(pflicht),
        }
    zeilen = _firma_fusszeile_zeilen(briefbogen)
    return {
        'typ': 'firma',
        'zeilen': zeilen,
        'pflichtangaben': '',
        'logo_uri': '',
        'hoehe_mm': _firma_fusszeile_hoehe_mm(zeilen),
    }


def rand_unten_mm(fusszeile: dict) -> float:
    """Unterer Seitenrand: 20 mm, mehr nur wenn die Fußzeile sonst in den Text ragt."""
    return round(max(MIN_RAND_UNTEN_MM, FUSS_ABSTAND_MM + fusszeile['hoehe_mm'] + FUSS_PUFFER_MM), 1)


# --------------------------------------------------------------------------
# Infoblock, Absender, Bezugszeichen, Betreff (5.3)
# --------------------------------------------------------------------------

def _sprechzeit_zeile(zeile: str) -> dict:
    tag, _, zeit = zeile.partition('\t')
    return {'tag': tag.strip(), 'zeit': zeit.strip()}


def _firma_zeilen(name: str) -> list:
    """Firmenname auf zwei etwa gleich lange Zeilen ("Demme Immobilien" / "Verwaltung GmbH")."""
    woerter = name.split()
    if len(woerter) < 3:
        return [name]
    beste = min(
        range(1, len(woerter)),
        key=lambda i: abs(len(' '.join(woerter[:i])) - len(' '.join(woerter[i:]))),
    )
    return [' '.join(woerter[:beste]), ' '.join(woerter[beste:])]


def baue_infoblock(briefbogen) -> dict:
    return {
        'firma_zeilen': _firma_zeilen(briefbogen.firma_name),
        'strasse': briefbogen.firma_strasse,
        'ort': f'{briefbogen.firma_plz} {briefbogen.firma_ort}'.strip(),
        'telefon': briefbogen.telefon,
        'email': briefbogen.email,
        'web': briefbogen.web,
        'sprechzeiten': [
            _sprechzeit_zeile(z) for z in (briefbogen.sprechzeiten or '').splitlines() if z.strip()
        ],
        'hinweis': (briefbogen.hinweis_infoblock or '').strip(),
    }


def baue_absenderzeile(briefbogen) -> list:
    ort = f'{briefbogen.firma_plz} {briefbogen.firma_ort}'.strip()
    zweite = ' · '.join(t for t in (briefbogen.firma_strasse, ort) if t)
    return [z for z in (briefbogen.firma_name, zweite) if z]


def baue_bezugszeichen(kontext: dict) -> dict:
    schreiben = kontext.get('schreiben', {})
    vom = schreiben.get('ihr_schreiben_vom')
    datum = schreiben.get('datum')
    return {
        'ihr_zeichen': schreiben.get('ihr_zeichen', ''),
        'ihr_schreiben_vom': filters.datum_mittel(vom) if vom else '',
        'unser_zeichen': schreiben.get('unser_zeichen', ''),
        'datum': filters.datum_mittel(datum) if datum else '',
    }


def baue_objektzeilen(kontext: dict) -> list:
    """``Objekt: 53-WEG …`` / ``Fläche: 0012-Wohnung …``; entfällt ohne Objekt/Einheit."""
    zeilen = []
    objekt = kontext.get('objekt') or {}
    if objekt.get('bezeichnung'):
        nummer = objekt.get('objektnummer')
        zeilen.append('Objekt: ' + (f'{nummer}-' if nummer else '') + objekt['bezeichnung'])
    einheit = kontext.get('einheit') or {}
    if einheit.get('lage') or einheit.get('flaechennummer'):
        nummer = einheit.get('flaechennummer')
        zeilen.append('Fläche: ' + '-'.join(t for t in (nummer, einheit.get('lage')) if t))
    return zeilen


def baue_anschrift(kontext: dict) -> list:
    zeilen = (kontext.get('empfaenger') or {}).get('anschrift_zeilen') or []
    if not zeilen:
        raise RenderFehler('Anschriftfeld leer - Brief ohne Empfängeranschrift nicht erzeugbar.')
    return list(zeilen[:7])


def baue_anrede(kontext: dict) -> list:
    empfaenger = kontext.get('empfaenger') or {}
    if not empfaenger.get('briefanrede'):
        raise RenderFehler('Briefanrede fehlt - Brief nicht erzeugbar.')
    return [a for a in (empfaenger['briefanrede'], empfaenger.get('briefanrede2')) if a]


def baue_schluss(kontext: dict, nur_firma: bool = False) -> dict:
    """Grußformel. ``nur_firma``: die Firma unterzeichnet, kein persönliches „gez. Name“.

    Für Schreiben, die im Namen der Verwaltung ergehen (z. B. das Anschreiben zur
    Eigentümerversammlung). Es genügt dann die Firma; ``unterzeichner`` bleibt leer
    und das Template lässt die „gez.“-Zeile weg.
    """
    verwaltung = kontext.get('verwaltung') or {}
    if nur_firma:
        if not verwaltung.get('firma'):
            raise RenderFehler('Firma fehlt - Grußformel nicht erzeugbar.')
        return {'firma': verwaltung['firma'], 'unterzeichner': ''}
    vorname = verwaltung.get('unterzeichner_vorname')
    nachname = verwaltung.get('unterzeichner_nachname')
    if not (vorname or nachname) or not verwaltung.get('firma'):
        raise RenderFehler('Unterzeichner oder Firma fehlt - Grußformel nicht erzeugbar.')
    return {
        'firma': verwaltung['firma'],
        'unterzeichner': ' '.join(t for t in (vorname, nachname) if t),
    }


# --------------------------------------------------------------------------
# Body-Aufteilung
# --------------------------------------------------------------------------

def teile_body(body_html: str) -> tuple:
    """Trennt gerenderten Body in Brieftext und Anlage-Seiten.

    Die Grußformel gehört ans Ende des Brieftexts, also VOR die erste
    ``anlage_seite`` (Vollmacht, Rückantwort ...). Ein Seitenumbruch direkt vor
    der Anlage würde sonst eine Leerseite bzw. die Grußformel auf die
    Folgeseite schieben und wird entfernt.
    """
    pos = body_html.find(_ANLAGE_BEGINN)
    brief, anlagen = (body_html, '') if pos < 0 else (body_html[:pos], body_html[pos:])
    return _SEITENUMBRUCH_AM_ENDE.sub('', brief), anlagen


# --------------------------------------------------------------------------
# Gesamt
# --------------------------------------------------------------------------

def baue_layout(briefbogen, kontext: dict, betreff: str, body_html: str,
                anlagen_bezeichnungen=None, nur_firma: bool = False) -> dict:
    """Template-Kontext für ``korrespondenz/brief_base.html`` (``nur_firma``: siehe ``baue_schluss``)."""
    fusszeile = baue_fusszeile(briefbogen, kontext)
    brief_html, anlagen_html = teile_body(body_html)
    return {
        'schrift_regular': font_url('LiberationSans-Regular.ttf'),
        'schrift_bold': font_url('LiberationSans-Bold.ttf'),
        'schrift_italic': font_url('LiberationSans-Italic.ttf'),
        'schrift_bolditalic': font_url('LiberationSans-BoldItalic.ttf'),
        'logo_uri': dokument_als_data_uri(briefbogen.logo, 'Logo'),
        'steuerzeichen': briefbogen.steuerzeichen_unsichtbar,
        'absender': baue_absenderzeile(briefbogen),
        'infoblock': baue_infoblock(briefbogen),
        'anschrift': baue_anschrift(kontext),
        'bezug': baue_bezugszeichen(kontext),
        'objektzeilen': baue_objektzeilen(kontext),
        'betreff': betreff,
        'anrede': baue_anrede(kontext),
        'brief_html': brief_html,
        'anlagen_html': anlagen_html,
        'schluss': baue_schluss(kontext, nur_firma),
        'anlagen_hinweis': list(anlagen_bezeichnungen or []),
        'fusszeile': fusszeile,
        'rand_unten_mm': rand_unten_mm(fusszeile),
        'fuss_unten_mm': FUSS_ABSTAND_MM - rand_unten_mm(fusszeile),
    }
