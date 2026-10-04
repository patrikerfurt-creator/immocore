"""Erzeugt ``docs/korrespondenz_platzhalter.md`` aus der Platzhalter-Registry.

Einzige Quelle ist ``registry.metadaten(anlass)`` (dieselbe wie Editor, Vorschau und
Validierung). Die dynamische Gruppe ``eingabe`` hängt an den Eingabefeldern der jeweiligen
Vorlagenversion und steht deshalb nur als Hinweis im Dokument.
"""
import json

from . import registry

_KOPF = (
    '# Korrespondenz — Platzhalter\n\n'
    '> Generiert aus der Platzhalter-Registry (`apps/korrespondenz/services/registry.py`) '
    'mit `python manage.py erzeuge_platzhalter_doku`. Nicht von Hand ändern.\n\n'
    'Im Vorlagentext werden Platzhalter als `{{ gruppe.name }}` geschrieben, optional mit '
    'Filtern (`{{ mahnung.frist | datum }}`). Filter: `euro`, `datum`, `datum_lang`, '
    '`datum_mittel`, `uhrzeit`, `iban`, `upper`, `default`.\n\n'
    'Die Gruppe `eingabe` ist dynamisch: sie enthält die Eingabefelder der jeweiligen '
    'Vorlagenversion (`{{ eingabe.<feldname> }}`) und ist deshalb hier nicht aufgelistet.\n'
)


def _zelle(text) -> str:
    return str(text).replace('|', '\\|').replace('\n', ' ')


def _beispiel(wert) -> str:
    if wert is None or wert == '':
        return '—'
    if isinstance(wert, (list, dict)):
        text = json.dumps(wert, ensure_ascii=False)
        return '`' + (text if len(text) <= 80 else text[:77] + '...') + '`'
    return f'`{wert}`'


def _tabelle(eintraege: list) -> str:
    zeilen = ['| Platzhalter | Beschreibung | Typ | Beispiel |', '|---|---|---|---|']
    for p in eintraege:
        zeilen.append(
            f"| `{p['name']}` | {_zelle(p['beschreibung'])} | {p['typ']} | {_zelle(_beispiel(p['beispiel']))} |"
        )
    return '\n'.join(zeilen)


def _gruppen_in_reihenfolge(eintraege: list) -> list:
    gruppen = []
    for p in eintraege:
        if p['gruppe'] not in gruppen:
            gruppen.append(p['gruppe'])
    return gruppen


def _abschnitt_anlass(anlass: str) -> str:
    eintraege = [p for p in registry.metadaten(anlass) if p['gruppe'] != 'eingabe']
    teile = [f'## Anlass `{anlass}`\n']
    for gruppe in _gruppen_in_reihenfolge(eintraege):
        teile.append(f'### Gruppe `{gruppe}`\n')
        teile.append(_tabelle([p for p in eintraege if p['gruppe'] == gruppe]) + '\n')
    return '\n'.join(teile)


def erzeuge_markdown() -> str:
    """Vollständiges Markdown-Dokument aller Anlässe (deterministisch)."""
    abschnitte = [_KOPF] + [_abschnitt_anlass(a) for a in registry.ANLAESSE]
    return '\n'.join(abschnitte).rstrip() + '\n'
