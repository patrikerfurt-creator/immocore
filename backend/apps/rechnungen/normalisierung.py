"""
Namens-Normalisierung für Kreditoren.

Bewusst ein eigenes, abhängigkeitsfreies Modul: die Funktion lag bisher in
``services/invoice_parser`` — das zieht beim Import PyMuPDF, Tesseract und
den Anthropic-Client mit. ``Kreditor.save()`` und die Dubletten-Prüfung
brauchen davon nichts.

``normalisiere_kreditorname`` ist die EINZIGE Stelle, an der ein
``name_normalisiert`` entsteht. Vorher gab es zwei Fassungen — der Parser
entfernte Rechtsformen, die manuelle Anlage in ``views.py`` nicht. Ein
manuell angelegtes "Meier GmbH" (normalisiert: ``meier gmbh``) wurde
deshalb von einer später eingelesenen Rechnung desselben Lieferanten
(normalisiert: ``meier``) nie gefunden — und ein zweiter Kreditor
angelegt. Genau diese Doppelungen soll die Vereinheitlichung verhindern.
"""
import re

# Rechtsformen und Zusätze, die für die Identität der Firma nichts
# beitragen. Sie fliegen raus, BEVOR verglichen wird — sonst teilen sich
# zwei beliebige GmbHs die Bigramme von "gmbh" und der Ähnlichkeitswert
# steigt ohne inhaltlichen Grund.
_RECHTSFORMEN = (
    r'gmbh|mbh|ug|ag|kg|ohg|gbr|kgaa|se|ev|e\.v\.|'
    r'e\.k\.|ek|eg|inc|ltd|llc|plc|co|cie|und co|u\. co'
)

_RECHTSFORM_RE = re.compile(rf'\b({_RECHTSFORMEN})\b')
_ERLAUBTE_ZEICHEN_RE = re.compile(r'[^a-z0-9äöüß&\-\s]')
_MEHRFACH_LEERZEICHEN_RE = re.compile(r'\s+')


def normalisiere_kreditorname(name: str) -> str:
    """Vergleichsform eines Firmennamens.

    Kleinschreibung, Sonderzeichen zu Leerzeichen, Rechtsformen entfernt,
    Mehrfach-Leerzeichen zusammengezogen.

    ``"EMG Evzi Memeti Gebäudeservice GmbH"`` → ``"emg evzi memeti gebäudeservice"``

    Liefert immer einen String (nie ``None``) — ``name_normalisiert`` ist
    ein ``CharField`` mit ``blank=True``, kein Nullable.
    """
    if not name:
        return ''
    text = name.strip().lower()
    text = _ERLAUBTE_ZEICHEN_RE.sub(' ', text)
    text = _RECHTSFORM_RE.sub(' ', text)
    text = _MEHRFACH_LEERZEICHEN_RE.sub(' ', text).strip()
    return text


def normalisiere_iban(wert: str) -> str:
    """Vergleichsform einer IBAN: ohne Leerzeichen und Bindestriche, groß."""
    if not wert:
        return ''
    return re.sub(r'[^A-Z0-9]', '', wert.upper().strip())
