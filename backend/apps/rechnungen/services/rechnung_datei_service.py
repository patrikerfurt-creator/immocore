"""
Zentrale Pfadauflösung für Rechnungs-Belege (v1_1 Phase B).

Bündelt die Übergangslogik Alt-Feld (Rechnung.pfad) vs. neue Beleg-Dokument-
Kopplung (Rechnung.beleg_dokument) an einer einzigen Stelle, damit alle
Lesepfade (PDF-Endpoint, OCR) synchron bleiben.
"""
from pathlib import Path

from apps.dokumente.services.beleg_service import dokument_pfad


def rechnung_datei_pfad(rechnung) -> Path | None:
    """Physischer Pfad des Rechnungs-Belegs. Bevorzugt das gekoppelte
    Beleg-Dokument (v1_1); Fallback: Alt-Feld rechnung.pfad (Doppelbetrieb).

    Prüft NICHT, ob die Datei tatsächlich existiert — das bleibt Aufgabe
    des Aufrufers.
    """
    if rechnung.beleg_dokument_id:
        return dokument_pfad(rechnung.beleg_dokument)
    if rechnung.pfad:
        return Path(rechnung.pfad)
    return None
