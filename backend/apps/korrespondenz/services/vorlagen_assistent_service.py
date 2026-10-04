"""KI-Assistent im Vorlagen-Editor (Spec 6).

Wird ausschließlich beim Erstellen/Überarbeiten einer VORLAGE genutzt, nie beim
Erzeugen eines Schreibens. Ablauf von ``entwerfe``:

1. Prompt bauen (``baue_prompt``): NUR Anlass, Stichworte, optional der zu
   überarbeitende Block und die Platzhalterliste MIT Beschreibungen, OHNE Werte
   (auch ohne die Beispielwerte der Registry). Es gehen nie personenbezogene
   Werte aus der Datenbank an die KI.
2. Anthropic-API synchron, Timeout 60 s (``_rufe_ki``; gleiche Anbindung wie der
   KI-Antwortvorschlag in ``apps.vorgaenge``: ``anthropic.Anthropic``,
   ``ANTHROPIC_API_KEY``/``ANTHROPIC_MODEL`` aus den Settings).
3. Output-Validierung VOR der Rückgabe (``validiere_ausgabe``): gültige
   Blockstruktur (3.4), nur bekannte Platzhalter (Registry), keine literalen
   Beträge, IBANs oder Kalenderdaten außerhalb von Platzhaltern. Verstöße
   werden nicht stillschweigend korrigiert, sondern als ``hinweise`` gemeldet.

Der Entwurf wird hier nicht gespeichert; er landet im Editor und wird dort als
normaler ``entwurf`` einer Version gesichert und regulär freigegeben.
"""
import json
import logging
import re
from types import SimpleNamespace

from django.conf import settings

from apps.korrespondenz.models import Textbaustein, Vorlage

from . import blockstruktur_service, registry, render_service
from .render_service import RenderFehler

logger = logging.getLogger(__name__)

TIMEOUT_SEKUNDEN = 60.0
MAX_TOKENS = 6000
MAX_STICHWORTE = 2000


class AssistentNichtVerfuegbar(Exception):
    """Kein ``ANTHROPIC_API_KEY`` konfiguriert."""


class AssistentFehler(Exception):
    """Die KI ist nicht erreichbar, zu langsam oder lieferte nichts Brauchbares."""

    def __init__(self, nachricht: str, *, zeitueberschreitung: bool = False):
        super().__init__(nachricht)
        self.zeitueberschreitung = zeitueberschreitung


# --------------------------------------------------------------------------
# Prompt
# --------------------------------------------------------------------------

SYSTEM_PROMPT = """Du bist Assistent einer WEG-Hausverwaltung (Demme GmbH) und entwirfst \
VORLAGEN für Schreiben an Eigentümer. Eine Vorlage besteht aus Blöcken mit \
Platzhaltern; die konkreten Werte (Namen, Beträge, Daten) setzt das System später ein. \
Du kennst und erhältst NIE echte Werte.

REGELN - halte dich strikt daran:
- Sie-Form, sachlich, freundlich. Keine Rechtsauskünfte, kein Gesetzeszitat.
- Verwende Platzhalter AUSSCHLIESSLICH aus der übergebenen Platzhalterliste, in der Form \
{{ gruppe.name }}. Erfinde keine Platzhalter.
- Schreibe NIEMALS Beträge, IBANs, Kontonummern oder Kalenderdaten als festen Text. \
Dafür gibt es Platzhalter (Filter: | euro, | datum, | datum_lang, | uhrzeit, | iban). \
Gibt es keinen passenden Platzhalter, formuliere ohne die konkrete Angabe.
- Absender, Anschrift, Betreff, Anrede und Grußformel liefert der Briefbogen: \
schreibe sie NICHT. Der Text beginnt nach der Anrede (z. B. "wir freuen uns ...").
- Verwende keine Textbaustein-Blöcke.

AUSGABEFORMAT - antworte NUR mit einem JSON-Objekt, ohne Einleitung und ohne Markdown:
{"betreff": "kurzer Betreff (optional)", "bloecke": [ ... ]}

Erlaubte Blocktypen:
- {"typ": "text", "inhalt": "Fließtext mit Platzhaltern; Leerzeile = neuer Absatz"}
- {"typ": "tabelle", "quelle": "<Tabellenquelle aus der Liste>"}
- {"typ": "liste", "quelle": "<Platzhalter vom Typ liste>", "nummeriert": true}
- {"typ": "bedingt", "bedingung": "<Platzhalter vom Typ bool>", "inhalt": "Text, nur wenn die Bedingung gilt"}
- {"typ": "seitenumbruch"}
- {"typ": "anlage_seite", "titel": "Titel", "inhalt": "Text der Folgeseite"}"""


def _anlass_label(anlass: str) -> str:
    return dict(Vorlage.ANLASS_CHOICES).get(anlass, anlass)


def _platzhalter_zeilen(anlass: str, eingabefelder) -> list:
    """Platzhalter mit Beschreibung und Typ - bewusst ohne ``beispiel``-Werte."""
    return [
        f"- {p['name']} ({p['typ']}): {p['beschreibung']}"
        for p in registry.metadaten(anlass, eingabefelder)
    ]


def baue_prompt(anlass: str, stichworte: str, block=None, eingabefelder=None) -> str:
    """User-Prompt: Anlass, Stichworte, Platzhalterliste (ohne Werte), optional der Block."""
    zeilen = [
        f'Anlass der Vorlage: {_anlass_label(anlass)} ({anlass})',
        '',
        'Verfügbare Platzhalter (Name, Typ, Beschreibung - ohne Werte):',
        *_platzhalter_zeilen(anlass, eingabefelder),
        '',
        'Verfügbare Tabellenquellen (Blocktyp "tabelle"): '
        + ', '.join(sorted(registry.TABELLEN)) + '.',
        '',
    ]
    if block:
        zeilen += [
            'Aufgabe: Überarbeite genau diesen einen Block gemäß der Anweisung und gib ihn '
            'als einziges Element von "bloecke" zurück.',
            f'Anweisung: {stichworte}',
            'Bisheriger Block:',
            json.dumps(block, ensure_ascii=False),
        ]
    else:
        zeilen += [
            'Aufgabe: Entwirf die Blöcke einer neuen Vorlage.',
            f'Stichworte: {stichworte}',
        ]
    return '\n'.join(zeilen)


# --------------------------------------------------------------------------
# KI-Aufruf
# --------------------------------------------------------------------------

def ist_verfuegbar() -> bool:
    return bool(getattr(settings, 'ANTHROPIC_API_KEY', None))


def _rufe_ki(prompt: str) -> str:
    """Ruft die Anthropic-API auf und gibt den Antworttext zurück (Timeout 60 s)."""
    import anthropic

    api_key = getattr(settings, 'ANTHROPIC_API_KEY', None)
    if not api_key:
        raise AssistentNichtVerfuegbar('ANTHROPIC_API_KEY nicht konfiguriert.')
    modell = getattr(settings, 'ANTHROPIC_MODEL', 'claude-sonnet-4-5')
    client = anthropic.Anthropic(api_key=api_key, timeout=TIMEOUT_SEKUNDEN, max_retries=0)
    try:
        nachricht = client.messages.create(
            model=modell, max_tokens=MAX_TOKENS, system=SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': prompt}],
        )
    except anthropic.APITimeoutError as exc:
        raise AssistentFehler('Die KI hat nicht innerhalb von 60 Sekunden geantwortet.',
                              zeitueberschreitung=True) from exc
    except anthropic.APIError as exc:
        logger.warning('Vorlagen-Assistent: KI-Aufruf fehlgeschlagen: %s', exc)
        raise AssistentFehler('Die KI ist derzeit nicht erreichbar.') from exc
    text = next((b.text for b in nachricht.content if getattr(b, 'type', None) == 'text'), '').strip()
    if not text:
        raise AssistentFehler('Die KI lieferte keinen Antworttext.')
    return text


# --------------------------------------------------------------------------
# Antwort lesen
# --------------------------------------------------------------------------

_CODE_ZAUN = re.compile(r'^```[a-zA-Z]*\s*|\s*```$')


def lese_antwort(text: str) -> tuple:
    """Zerlegt die KI-Antwort in ``(bloecke, betreff)``. ``AssistentFehler`` bei unlesbarer Antwort."""
    roh = _CODE_ZAUN.sub('', text.strip()).strip()
    anfang, ende = roh.find('{'), roh.rfind('}')
    if roh.startswith('['):
        kandidat = roh
    elif anfang != -1 and ende > anfang:
        kandidat = roh[anfang:ende + 1]
    else:
        raise AssistentFehler('Die Antwort der KI war nicht lesbar (kein JSON).')
    try:
        daten = json.loads(kandidat)
    except ValueError as exc:
        raise AssistentFehler('Die Antwort der KI war nicht lesbar (ungültiges JSON).') from exc
    if isinstance(daten, list):
        return daten, ''
    if not isinstance(daten, dict) or 'bloecke' not in daten:
        raise AssistentFehler('Die Antwort der KI enthielt keine Blöcke.')
    betreff = daten.get('betreff')
    return daten['bloecke'], betreff.strip() if isinstance(betreff, str) else ''


# --------------------------------------------------------------------------
# Output-Validierung
# --------------------------------------------------------------------------

_PLATZHALTER_TEIL = re.compile(r'\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}', re.DOTALL)
_IBAN = re.compile(r'\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}(?: ?[A-Z0-9]{1,4})?\b')
_MONATE = 'Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember'
_BETRAG = re.compile(
    r'(?:€|EUR|Euro)\s*\d'                               # € 350
    r'|\d[\d.]*(?:,\d{1,2})?\s*(?:€|EUR\b|Euro\b)'       # 350,00 € / 350 Euro
    r'|\b\d{1,3}(?:\.\d{3})*,\d{2}\b'                    # 1.350,00
)
_DATUM = re.compile(
    r'\b(?:0?[1-9]|[12]\d|3[01])\.\s?(?:0?[1-9]|1[0-2])\.(?:\s?(?:\d{4}|\d{2})\b)?'   # 15.10.2026 / 15.10.
    r'|\b\d{4}-\d{2}-\d{2}\b'                                                          # 2026-10-15
    rf'|\b(?:0?[1-9]|[12]\d|3[01])\.\s?(?:{_MONATE})\b(?:\s+\d{{4}})?'                   # 15. Oktober 2026
    rf'|\b(?:{_MONATE})\s+\d{{4}}\b'                                                     # Oktober 2026
)


def _ohne_platzhalter(text: str) -> str:
    return _PLATZHALTER_TEIL.sub(' ', text)


def _kuerzen(treffer: str) -> str:
    treffer = ' '.join(treffer.split())
    return treffer if len(treffer) <= 40 else treffer[:37] + '...'


def _literale(text: str) -> list:
    """``[(art, treffer)]`` literaler Beträge/IBANs/Datumsangaben außerhalb von Platzhaltern."""
    frei = _ohne_platzhalter(text)
    funde = []
    for art, muster in (('IBAN', _IBAN), ('Betrag', _BETRAG), ('Datum', _DATUM)):
        funde += [(art, m.group(0)) for m in muster.finditer(frei)]
    return funde


def _beschreibe(nr: int, block) -> str:
    typ = block.get('typ') if isinstance(block, dict) else None
    return f'Block {nr} ({typ})' if typ else f'Block {nr}'


def _saubere_bloecke(bloecke, hinweise: list) -> list:
    """Behält nur Objekte mit bekanntem Blocktyp; alles andere wird verworfen und gemeldet."""
    if not isinstance(bloecke, list):
        hinweise.append('Die KI lieferte keine Liste von Blöcken.')
        return []
    behalten = []
    for nr, block in enumerate(bloecke, start=1):
        if isinstance(block, dict) and block.get('typ') in blockstruktur_service.BLOCKTYPEN:
            behalten.append(block)
        else:
            hinweise.append(f'Block {nr} hat keine gültige Struktur und wurde verworfen.')
    return behalten


def _pruefe_platzhalter(nr: int, block: dict, bekannt: set, hinweise: list) -> None:
    einzel = SimpleNamespace(betreff='', inhalt=[block])
    try:
        verwendet = render_service.verwendete_platzhalter(einzel)
    except (RenderFehler, TypeError) as exc:
        hinweise.append(f'{_beschreibe(nr, block)}: Platzhalter-Syntax nicht gültig ({exc}).')
        return
    for name in sorted(verwendet):
        if not any(name == k or name.startswith(k + '.') for k in bekannt):
            hinweise.append(f'{_beschreibe(nr, block)}: unbekannter Platzhalter "{name}".')


def _pruefe_quellen(nr: int, block: dict, hinweise: list) -> None:
    if block.get('typ') == 'tabelle' and not block.get('spalten') and \
            block.get('quelle') not in registry.TABELLEN:
        hinweise.append(f'{_beschreibe(nr, block)}: unbekannte Tabellenquelle "{block.get("quelle")}".')


def _pruefe_baustein(nr: int, block: dict, hinweise: list) -> None:
    if block.get('typ') == 'baustein' and not Textbaustein.objects.filter(
            code=block.get('code'), aktiv=True).exists():
        hinweise.append(f'{_beschreibe(nr, block)}: Textbaustein "{block.get("code")}" existiert nicht.')


def _pruefe_literale(nr: int, block: dict, hinweise: list) -> None:
    for schluessel in blockstruktur_service.TEXT_SCHLUESSEL:
        wert = block.get(schluessel)
        if not isinstance(wert, str):
            continue
        for art, treffer in _literale(wert):
            hinweise.append(
                f'{_beschreibe(nr, block)}: fester Text enthält {art} "{_kuerzen(treffer)}" - '
                f'stattdessen einen Platzhalter verwenden.')


def validiere_ausgabe(bloecke, anlass: str, eingabefelder=None) -> tuple:
    """Prüft den KI-Output. Gibt ``(bloecke, hinweise)`` zurück.

    ``bloecke``: nur Blöcke mit bekanntem Typ (der Rest wird verworfen und gemeldet);
    ``hinweise``: eine Meldung je gefundenem Verstoß (leer = unauffällig).
    """
    hinweise = []
    behalten = _saubere_bloecke(bloecke, hinweise)
    hinweise += blockstruktur_service.pruefe_blockstruktur(behalten)
    bekannt = registry.dokumentierte_namen(anlass, eingabefelder)
    for nr, block in enumerate(behalten, start=1):
        _pruefe_platzhalter(nr, block, bekannt, hinweise)
        _pruefe_quellen(nr, block, hinweise)
        _pruefe_baustein(nr, block, hinweise)
        _pruefe_literale(nr, block, hinweise)
    return behalten, hinweise


def _pruefe_betreff(betreff: str, anlass: str, eingabefelder) -> list:
    """Der (optionale) Betreff unterliegt denselben Regeln wie ein Textblock."""
    if not betreff:
        return []
    _, hinweise = validiere_ausgabe([{'typ': 'text', 'inhalt': betreff}], anlass, eingabefelder)
    return [h.replace('Block 1 (text)', 'Betreff', 1) for h in hinweise]


# --------------------------------------------------------------------------
# Öffentliche API
# --------------------------------------------------------------------------

def entwerfe(anlass: str, stichworte: str, block=None, eingabefelder=None) -> dict:
    """Entwurf bzw. Überarbeitung per KI: ``{'bloecke': [...], 'hinweise': [...], 'betreff': str}``.

    Raises ``AssistentNichtVerfuegbar`` (kein API-Key), ``AssistentFehler`` (KI-Fehler,
    Zeitüberschreitung, unlesbare Antwort), ``ValueError`` (unbekannter Anlass).
    """
    if anlass not in registry.ANLAESSE:
        raise ValueError(f'Unbekannter Anlass "{anlass}".')
    if not ist_verfuegbar():
        raise AssistentNichtVerfuegbar('ANTHROPIC_API_KEY nicht konfiguriert.')
    text = _rufe_ki(baue_prompt(anlass, stichworte, block, eingabefelder))
    bloecke, betreff = lese_antwort(text)
    bloecke, hinweise = validiere_ausgabe(bloecke, anlass, eingabefelder)
    hinweise += _pruefe_betreff(betreff, anlass, eingabefelder)
    if not bloecke:
        hinweise.append('Die KI lieferte keinen verwertbaren Block.')
    return {'bloecke': bloecke, 'hinweise': hinweise, 'betreff': betreff}
