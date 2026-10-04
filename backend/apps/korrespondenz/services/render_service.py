"""Render-Engine für Vorlagen (Spec 4.1, Blockstruktur 3.4).

Jinja2 ``SandboxedEnvironment`` + ``StrictUndefined``: ein fehlender Wert ist
ein Fehler, nie eine leere Stelle im Brief. Die Engine sieht ausschließlich das
flache Kontext-Dict der Registry (``kontext_service.baue_kontext``) - nie
Django-Modelle - und verwendet nur die Filter aus ``filters.FILTER``.

Zusätzlich zur Sandbox wird jede Vorlagenquelle vor dem Rendern auf dem AST
geprüft und auf ein Minimum beschränkt (Ausgabe, if/for, Filter, Vergleiche):
kein ``import``/``include``/``extends``/``macro``/``set``, keine Funktionsaufrufe
und kein Zugriff auf Attribute/Schlüssel mit führendem Unterstrich.

Blocktypen ``text``/``bedingt``/``baustein``/``anlage_seite`` enthalten HTML-
Fragmente (Editor-Ausgabe) mit Platzhaltern; ersetzte Werte werden HTML-escaped.
Ein Text ohne Block-Tags wird in Absätze (``<p>``) gewandelt.

Determinismus: kein Zugriff auf Uhr, Zufall oder Locale - gleicher Kontext ->
byte-gleiches HTML (Test 3).
"""
import re
from dataclasses import dataclass, field
from datetime import date, time
from decimal import Decimal

from jinja2 import StrictUndefined, TemplateError, nodes
from jinja2.sandbox import SandboxedEnvironment
from markupsafe import Markup, escape

from . import eingabefelder_service, filters, registry


class RenderFehler(Exception):
    """Fachlicher Render-Fehler (Blockstruktur, Quelle, fehlende Vorgabe)."""


@dataclass
class RenderErgebnis:
    """Ergebnis von ``render``. Bei gesetztem ``fehler`` sind ``html``/``betreff`` leer."""
    html: str = ''
    betreff: str = ''
    snapshot: dict = field(default_factory=dict)
    fehler: str = ''

    @property
    def ok(self) -> bool:
        return not self.fehler


# --------------------------------------------------------------------------
# Umgebung
# --------------------------------------------------------------------------

def _finalize_html(wert):
    """Ausgabe-Aufbereitung: Listen mit <br>, Datum/Betrag/Uhrzeit deutsch formatiert."""
    if isinstance(wert, (list, tuple)):
        return Markup('<br>').join(_finalize_html(x) for x in wert)
    return _finalize_text(wert)


def _finalize_text(wert):
    if isinstance(wert, (list, tuple)):
        return ', '.join(str(_finalize_text(x)) for x in wert)
    if isinstance(wert, date):
        return filters.datum(wert)
    if isinstance(wert, time):
        return filters.uhrzeit(wert)
    if isinstance(wert, Decimal):
        return filters.euro(wert)
    return wert


class _Sandbox(SandboxedEnvironment):
    """Sandbox ohne Standard-Globals und -Filter (nur ``filters.FILTER``)."""

    def __init__(self, autoescape, finalize):
        super().__init__(
            autoescape=autoescape, undefined=StrictUndefined, finalize=finalize,
            trim_blocks=False, lstrip_blocks=False, keep_trailing_newline=False,
        )
        self.globals = {}
        self.filters = dict(filters.FILTER)


_UMGEBUNGEN = {}


def _umgebung(html: bool) -> _Sandbox:
    if html not in _UMGEBUNGEN:
        _UMGEBUNGEN[html] = (
            _Sandbox(True, _finalize_html) if html else _Sandbox(False, _finalize_text)
        )
    return _UMGEBUNGEN[html]


_VERBOTENE_KNOTEN = (
    nodes.Import, nodes.FromImport, nodes.Extends, nodes.Include, nodes.Block,
    nodes.Macro, nodes.CallBlock, nodes.FilterBlock, nodes.Call, nodes.Assign,
    nodes.AssignBlock, nodes.ExprStmt, nodes.EvalContextModifier,
    nodes.ScopedEvalContextModifier, nodes.ContextReference, nodes.Break,
    nodes.Continue,
)


# Django-Manager/ORM-Einstieg: nie erlaubt, auch wenn der Kontext (heute) keine Modelle enthält.
_VERBOTENE_ATTRIBUTE = {'objects', 'pk'}


def _pruefe_ast(baum) -> None:
    """Wirft ``RenderFehler``, wenn die Quelle unerlaubte Konstrukte enthält."""
    for knoten in baum.find_all(_VERBOTENE_KNOTEN):
        raise RenderFehler(f'Nicht erlaubtes Vorlagen-Konstrukt: {type(knoten).__name__}')
    for knoten in baum.find_all(nodes.Getattr):
        if knoten.attr.startswith('_') or knoten.attr in _VERBOTENE_ATTRIBUTE:
            raise RenderFehler(f'Nicht erlaubter Zugriff auf Attribut "{knoten.attr}".')
    for knoten in baum.find_all(nodes.Getitem):
        if isinstance(knoten.arg, nodes.Const) and str(knoten.arg.value).startswith('_'):
            raise RenderFehler('Nicht erlaubter Zugriff auf einen Schlüssel mit Unterstrich.')
    for knoten in baum.find_all(nodes.Name):
        if knoten.name.startswith('_'):
            raise RenderFehler(f'Nicht erlaubter Name "{knoten.name}".')


def _parse(env: _Sandbox, quelle: str):
    """Parst und prüft eine Quelle; Syntaxfehler werden zu ``RenderFehler``."""
    try:
        baum = env.parse(quelle)
    except TemplateError as exc:
        raise RenderFehler(f'Vorlagen-Syntaxfehler: {exc}') from exc
    _pruefe_ast(baum)
    return baum


def _rendere_quelle(quelle: str, kontext: dict, html: bool) -> str:
    env = _umgebung(html)
    _parse(env, quelle)
    return env.from_string(quelle).render(kontext)


# --------------------------------------------------------------------------
# Platzhalter-Ermittlung (Snapshot, Pflicht-Platzhalter)
# --------------------------------------------------------------------------

def _kette(knoten):
    """Dotted-Name einer Getattr/Getitem-Kette über einem Namen, sonst ``None``."""
    teile = []
    while isinstance(knoten, (nodes.Getattr, nodes.Getitem)):
        if isinstance(knoten, nodes.Getattr):
            teile.append(knoten.attr)
        elif isinstance(knoten.arg, nodes.Const) and isinstance(knoten.arg.value, str):
            teile.append(knoten.arg.value)
        else:
            return None
        knoten = knoten.node
    if isinstance(knoten, nodes.Name):
        return '.'.join([knoten.name] + teile[::-1])
    return None


def _platzhalter_aus_quelle(quelle: str) -> set:
    env = _umgebung(True)
    ketten = {
        k for k in (_kette(n) for n in _parse(env, quelle).find_all((nodes.Getattr, nodes.Getitem)))
        if k
    }
    # Nur maximale Ketten: "mahnung.frist" statt zusätzlich "mahnung".
    return {k for k in ketten if not any(o.startswith(k + '.') for o in ketten)}


def _jinja_quellen(betreff, bloecke, bausteine) -> list:
    """Alle Jinja-Quellen einer Version (für Platzhalter-Ermittlung)."""
    quellen = [betreff]
    for block in bloecke:
        typ = block.get('typ')
        if typ in ('text', 'anlage_seite'):
            quellen.append(block.get('inhalt', ''))
        elif typ == 'bedingt':
            quellen.append('{{ ' + block.get('bedingung', 'true') + ' }}')
            quellen.append(block.get('inhalt', ''))
        elif typ == 'baustein':
            quellen.append((bausteine or {}).get(block.get('code'), ''))
        elif typ in ('liste', 'tabelle'):
            quellen.append('{{ ' + block.get('quelle', 'x') + ' }}')
    return quellen


def verwendete_platzhalter(version, bausteine=None) -> set:
    """Menge der im Text verwendeten Platzhalter (``gruppe.name``) einer Version."""
    gefunden = set()
    for quelle in _jinja_quellen(version.betreff, version.inhalt or [], bausteine):
        gefunden |= _platzhalter_aus_quelle(quelle)
    return gefunden


def _hole(kontext: dict, dotted: str):
    """Wert zu ``gruppe.name`` oder ``KeyError``."""
    wert = kontext
    for teil in dotted.split('.'):
        if not isinstance(wert, dict) or teil not in wert:
            raise KeyError(dotted)
        wert = wert[teil]
    return wert


def _json_sicher(wert):
    if isinstance(wert, Decimal):
        return str(wert)
    if isinstance(wert, date):
        return wert.isoformat()
    if isinstance(wert, time):
        return wert.strftime('%H:%M')
    if isinstance(wert, dict):
        return {str(k): _json_sicher(v) for k, v in wert.items()}
    if isinstance(wert, (list, tuple)):
        return [_json_sicher(v) for v in wert]
    return wert


def _baue_snapshot(verwendet: set, kontext: dict) -> dict:
    snapshot = {}
    for name in sorted(verwendet):
        try:
            snapshot[name] = _json_sicher(_hole(kontext, name))
        except KeyError:
            continue  # z. B. in einem nicht gerenderten bedingten Block
    return snapshot


# --------------------------------------------------------------------------
# Blöcke
# --------------------------------------------------------------------------

_BLOCK_TAG = re.compile(r'<\s*(p|ul|ol|li|div|table|h[1-6]|br)\b', re.IGNORECASE)


def _als_absaetze(quelle: str) -> str:
    """Text ohne Block-Tags -> ``<p>``-Absätze (Leerzeile = neuer Absatz)."""
    if _BLOCK_TAG.search(quelle):
        return quelle
    absaetze = [a.strip() for a in re.split(r'\n\s*\n', quelle.strip()) if a.strip()]
    return '\n'.join('<p>' + a.replace('\n', '<br>\n') + '</p>' for a in absaetze)


def _block_text(block, kontext, bausteine) -> str:
    return _rendere_quelle(_als_absaetze(block.get('inhalt', '')), kontext, True)


def _block_baustein(block, kontext, bausteine) -> str:
    code = block.get('code')
    if not bausteine or code not in bausteine:
        raise RenderFehler(f'Textbaustein "{code}" nicht verfügbar.')
    return _rendere_quelle(_als_absaetze(bausteine[code]), kontext, True)


def _wert_formatiert(wert, format_: str) -> str:
    if format_ == 'datum':
        return filters.datum(wert)
    if format_ == 'euro':
        return filters.euro(wert)
    return str(wert)


def _block_tabelle(block, kontext, bausteine) -> str:
    quelle = block.get('quelle')
    spalten = block.get('spalten') or registry.TABELLEN.get(quelle)
    if not spalten:
        raise RenderFehler(f'Unbekannte Tabelle "{quelle}".')
    try:
        zeilen = _hole(kontext, quelle)
    except KeyError:
        raise RenderFehler(f'Tabellendaten "{quelle}" nicht verfügbar.') from None
    if not zeilen:
        raise RenderFehler(f'Tabelle "{quelle}" ist leer.')
    kopf = ''.join(
        f'<th class="{"rechts" if s.get("format") == "euro" else "links"}">{escape(s["titel"])}</th>'
        for s in spalten
    )
    zeilen_html = []
    for zeile in zeilen:
        try:
            zellen = ''.join(
                f'<td class="{"rechts" if s.get("format") == "euro" else "links"}">'
                f'{escape(_wert_formatiert(zeile[s["feld"]], s.get("format", "text")))}</td>'
                for s in spalten
            )
        except KeyError as exc:
            raise RenderFehler(f'Tabelle "{quelle}": Spalte {exc} fehlt in den Daten.') from None
        zeilen_html.append(f'<tr>{zellen}</tr>')
    return (
        f'<table class="tabelle"><thead><tr>{kopf}</tr></thead>'
        f'<tbody>\n{chr(10).join(zeilen_html)}\n</tbody></table>'
    )


def _block_liste(block, kontext, bausteine) -> str:
    quelle = block.get('quelle')
    try:
        eintraege = _hole(kontext, quelle)
    except KeyError:
        raise RenderFehler(f'Listenquelle "{quelle}" nicht verfügbar.') from None
    if not isinstance(eintraege, (list, tuple)) or not eintraege:
        raise RenderFehler(f'Listenquelle "{quelle}" ist keine gefüllte Liste.')
    tag = 'ol' if block.get('nummeriert', True) else 'ul'
    punkte = '\n'.join(f'<li>{escape(str(e))}</li>' for e in eintraege)
    return f'<{tag}>\n{punkte}\n</{tag}>'


def bedingung_erfuellt(bedingung: str, kontext: dict) -> bool:
    """Wertet eine Bedingung (z. B. ``ev.sepa_mandat_fehlt``) in der Sandbox gegen den Kontext aus.

    Dieselbe Auswertung wie beim Block ``bedingt``; auch für bedingte Vorlagen-Anlagen.
    Nicht auswertbar (Syntax, unbekannter Platzhalter) -> ``RenderFehler``.
    """
    try:
        return _rendere_quelle('{% if ' + bedingung + ' %}1{% endif %}', kontext, False) == '1'
    except RenderFehler:
        raise
    except Exception as exc:  # noqa: BLE001 - jinja2.UndefinedError u. a.
        raise RenderFehler(f'Bedingung "{bedingung}" nicht auswertbar: {exc}') from exc


def _block_bedingt(block, kontext, bausteine) -> str:
    bedingung = block.get('bedingung')
    if not bedingung:
        raise RenderFehler('Bedingter Block ohne Bedingung.')
    treffer = _rendere_quelle('{% if ' + bedingung + ' %}1{% endif %}', kontext, False)
    if treffer != '1':
        return ''
    return _rendere_quelle(_als_absaetze(block.get('inhalt', '')), kontext, True)


def _block_seitenumbruch(block, kontext, bausteine) -> str:
    return '<div class="seitenumbruch" style="break-after: page; page-break-after: always;"></div>'


def _block_anlage_seite(block, kontext, bausteine) -> str:
    titel = escape(block.get('titel', ''))
    inhalt = _rendere_quelle(_als_absaetze(block.get('inhalt', '')), kontext, True)
    kopf = f'<h1 class="anlage-titel">{titel}</h1>\n' if titel else ''
    return (
        '<section class="anlage-seite" '
        'style="break-before: page; page-break-before: always;">\n'
        f'{kopf}{inhalt}\n</section>'
    )


_BLOCK_RENDERER = {
    'text': _block_text,
    'baustein': _block_baustein,
    'tabelle': _block_tabelle,
    'liste': _block_liste,
    'bedingt': _block_bedingt,
    'seitenumbruch': _block_seitenumbruch,
    'anlage_seite': _block_anlage_seite,
}


def _rendere_block(block, kontext, bausteine) -> str:
    if not isinstance(block, dict) or block.get('typ') not in _BLOCK_RENDERER:
        typ = block.get('typ') if isinstance(block, dict) else block
        raise RenderFehler(f'Unbekannter Blocktyp: {typ!r}')
    return _BLOCK_RENDERER[block['typ']](block, kontext, bausteine)


def _rendere_bloecke(bloecke, kontext, bausteine) -> str:
    if not isinstance(bloecke, list):
        raise RenderFehler('Inhalt muss eine Liste von Blöcken sein.')
    teile = [_rendere_block(b, kontext, bausteine) for b in bloecke]
    return '\n'.join(t for t in teile if t)


def _rendere_betreff(betreff: str, kontext: dict) -> str:
    return ' '.join(_rendere_quelle(betreff, kontext, False).split())


# --------------------------------------------------------------------------
# Öffentliche API
# --------------------------------------------------------------------------

def _pruefe_pflicht_platzhalter(version, verwendet: set) -> None:
    fehlend = [p for p in (version.pflicht_platzhalter or []) if p not in verwendet]
    if fehlend:
        raise RenderFehler('Pflicht-Platzhalter kommen im Text nicht vor: ' + ', '.join(fehlend))


def _fehlermeldung(exc: Exception, verwendet: set, kontext: dict) -> str:
    meldung = str(exc)
    fehlend = sorted(n for n in verwendet if not _versuche_hole(kontext, n))
    if fehlend:
        meldung += ' (im Kontext nicht vorhanden: ' + ', '.join(fehlend) + ')'
    return meldung


def _versuche_hole(kontext: dict, name: str) -> bool:
    try:
        _hole(kontext, name)
        return True
    except KeyError:
        return False


def render(version, kontext: dict, eingabewerte: dict, *, bausteine: dict = None) -> RenderErgebnis:
    """Rendert Betreff und Inhalt einer Vorlagenversion.

    ``version``: Objekt mit ``betreff``, ``inhalt``, ``eingabefelder``,
    ``pflicht_platzhalter`` (i. d. R. ``VorlagenVersion``; die Engine liest
    nur diese Attribute).
    ``kontext``: Ergebnis von ``kontext_service.baue_kontext``.
    ``eingabewerte``: Rohwerte der Eingabefelder; sie werden gegen
    ``version.eingabefelder`` validiert und getypt als ``eingabe.*`` bereitgestellt.
    ``bausteine``: ``{code: inhalt}`` der im Inhalt referenzierten Textbausteine.

    Bei jedem Fehler (fehlender Pflichtwert, ungültige Eingabe, verbotenes
    Konstrukt ...) ist ``fehler`` gesetzt und es wird KEIN HTML geliefert.
    """
    pruefung = eingabefelder_service.validiere(version.eingabefelder, eingabewerte)
    if pruefung.fehler:
        return RenderErgebnis(fehler=' '.join(pruefung.fehler))

    voll = dict(kontext)
    voll['eingabe'] = pruefung.werte
    verwendet = set()
    try:
        verwendet = verwendete_platzhalter(version, bausteine)
        _pruefe_pflicht_platzhalter(version, verwendet)
        betreff = _rendere_betreff(version.betreff, voll)
        html = _rendere_bloecke(version.inhalt, voll, bausteine)
    except (RenderFehler, TemplateError, ValueError, TypeError, ArithmeticError) as exc:
        return RenderErgebnis(fehler=_fehlermeldung(exc, verwendet, voll))
    return RenderErgebnis(html=html, betreff=betreff, snapshot=_baue_snapshot(verwendet, voll))
