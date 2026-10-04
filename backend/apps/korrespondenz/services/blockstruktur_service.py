"""Prüfung der Blockstruktur von ``VorlagenVersion.inhalt`` (Spec 3.4).

Reine Funktionen ohne DB-Zugriff. Genutzt vom Versions-Endpoint (Editor speichert
nur strukturell gültige Blöcke) und vom KI-Assistenten (Output-Validierung).

Contract je Blocktyp:

* ``text``          ``inhalt`` (str)
* ``baustein``      ``code`` (str)
* ``tabelle``       ``quelle`` (str)
* ``liste``         ``quelle`` (str)
* ``bedingt``       ``bedingung`` (str), ``inhalt`` (str)
* ``seitenumbruch`` -
* ``anlage_seite``  ``titel`` (str), ``inhalt`` (str)

Pflicht ist nur, was den Blocktyp ausmacht (``inhalt`` bei ``text``, ``code``,
``quelle``, ``bedingung``, ``titel``); ein vorhandenes ``inhalt`` muss stets ein
String sein.
"""

BLOCKTYPEN = ('text', 'baustein', 'tabelle', 'liste', 'bedingt', 'seitenumbruch', 'anlage_seite')

# Pflichtschlüssel (jeweils nichtleerer String) je Blocktyp.
_PFLICHT_TEXTE = {
    'text': ('inhalt',),
    'baustein': ('code',),
    'tabelle': ('quelle',),
    'liste': ('quelle',),
    'bedingt': ('bedingung',),
    'seitenumbruch': (),
    'anlage_seite': ('titel',),
}

# Schlüssel, deren Inhalt Fließtext mit Platzhaltern ist (Prüfung auf Literale/Platzhalter).
TEXT_SCHLUESSEL = ('inhalt', 'titel')


def pruefe_blockstruktur(bloecke) -> list:
    """Fehlermeldungen zur Blockstruktur (leer = gültig)."""
    if not isinstance(bloecke, list):
        return ['Der Inhalt muss eine Liste von Blöcken sein.']
    fehler = []
    for nr, block in enumerate(bloecke, start=1):
        if not isinstance(block, dict):
            fehler.append(f'Block {nr}: kein Objekt.')
            continue
        typ = block.get('typ')
        if typ not in BLOCKTYPEN:
            fehler.append(f'Block {nr}: unbekannter Blocktyp {typ!r}.')
            continue
        for schluessel in _PFLICHT_TEXTE[typ]:
            wert = block.get(schluessel)
            if not isinstance(wert, str) or not wert.strip():
                fehler.append(f'Block {nr} ({typ}): "{schluessel}" fehlt oder ist leer.')
        if 'inhalt' in block and not isinstance(block['inhalt'], str):
            fehler.append(f'Block {nr} ({typ}): "inhalt" muss ein Text sein.')
    return fehler
