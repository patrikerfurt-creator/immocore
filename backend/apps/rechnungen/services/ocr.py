"""
KI-OCR für Rechnungs-PDFs via Claude API (Vorbefüllung, keine Buchung).

Extrahiert je Feld { wert, konfidenz } (Spec Kap. 5.1). Die LLM-Konfidenz ist
nur der Basiswert der Verifikations-Ampel — verlässlich sind die
deterministischen Prüfungen im erkennung_ampel_service (Kap. 5.2).
"""
import base64
import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

# Felder, die der OCR-Prompt je { wert, konfidenz } liefern soll.
OCR_FELDER = [
    "lieferant_name", "lieferant_iban", "rechnungsnummer", "rechnungsdatum",
    "faelligkeitsdatum", "betrag_netto", "betrag_brutto", "mwst_satz",
    "leistungsbeschreibung",
    # --- Umbau v1.0 (Spec 5.1) ---
    "betrag_haushaltsnah", "skonto_prozent", "skonto_betrag",
    "skonto_frist_tage", "skonto_faellig_bis", "ist_schlussrechnung",
    "ist_gutschrift", "kostenverursacher_vorschlag",
]

_PROMPT = """Extrahiere aus dieser Rechnung die folgenden Felder. Antworte NUR
mit einem JSON-Objekt der Form {"felder": {"<feld>": {"wert": <wert|null>,
"konfidenz": <0.0-1.0>}}}, kein Markdown.

Felder:
- lieferant_name, lieferant_iban, rechnungsnummer
- rechnungsdatum, faelligkeitsdatum (YYYY-MM-DD)
- betrag_netto, betrag_brutto (Zahl), mwst_satz (Prozent als Zahl)
- leistungsbeschreibung
- betrag_haushaltsnah: Lohn-/Arbeitskostenanteil gem. §35a EStG
  ("Lohnanteil", "Arbeitskosten", "darin enthaltene Lohnkosten"). Diese
  Angabe steht oft NICHT bei den Kopfdaten, sondern als eigene kleine
  Tabelle/Zeile unterhalb der Summen oder des MwSt.-Nachweises — auch auf
  einer Folgeseite eines mehrseitigen Dokuments. Prüfe ALLE Seiten,
  besonders den Bereich nach dem Bruttoendbetrag. Wenn NICHT ausgewiesen:
  wert=null (nicht schätzen).
- skonto_prozent, skonto_betrag, skonto_frist_tage, skonto_faellig_bis:
  aus Zahlungsbedingungen ("2% Skonto bei Zahlung innerhalb 14 Tagen").
- ist_schlussrechnung: true bei "Schlussrechnung"/"Endabrechnung"/"Schlussrg.".
- ist_gutschrift: true bei Gutschrift/Guthaben ("Gutschrift", "Storno",
  negativer Rechnungsbetrag, "wir schreiben Ihnen gut"). Sonst false.
- kostenverursacher_vorschlag: falls im Leistungstext eine Wohnungs-/
  Einheitsbezeichnung genannt ist (z.B. "WE05", "Wohnung Müller, 1.OG links").

konfidenz = deine Selbsteinschätzung 0.0-1.0 je Feld. Nicht gefunden → wert=null, konfidenz=0.0."""


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


def ki_ocr_rechnung(rechnung) -> dict:
    """Liest das hochgeladene Rechnungs-PDF aus.
    Rückgabe: {"felder": {feld: {"wert":..., "konfidenz":0..1}}}."""
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic-Paket nicht installiert")

    api_key = getattr(settings, "ANTHROPIC_API_KEY", None)
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY nicht konfiguriert")

    # PDF-Quelle: zentrale Auflösung (gekoppeltes Beleg-Dokument bevorzugt,
    # Fallback Alt-Feld rechnung.pfad).
    from .rechnung_datei_service import rechnung_datei_pfad
    pfad = rechnung_datei_pfad(rechnung)
    if not pfad:
        raise RuntimeError("Kein PDF (weder Beleg-Dokument noch pfad) vorhanden")
    with open(pfad, "rb") as f:
        roh = f.read()
    pdf_data = base64.standard_b64encode(roh).decode("utf-8")

    client = anthropic.Anthropic(api_key=api_key)
    model = getattr(settings, "ANTHROPIC_MODEL", "claude-sonnet-4-6")

    message = client.messages.create(
        model=model,
        max_tokens=4000,  # claude-sonnet-5 denkt zuerst — Budget für Thinking + JSON
        messages=[{
            "role": "user",
            "content": [
                {"type": "document", "source": {
                    "type": "base64", "media_type": "application/pdf", "data": pdf_data}},
                {"type": "text", "text": _PROMPT},
            ],
        }],
    )

    try:
        _msg_text = next((b.text for b in message.content if getattr(b, 'type', None) == 'text'), '')
        parsed = _parse_json(_msg_text)
    except (json.JSONDecodeError, IndexError):
        logger.error("Claude API lieferte kein gültiges JSON: %s", _msg_text)
        raise RuntimeError("Claude API lieferte kein gültiges JSON")

    felder = parsed.get("felder", parsed)
    # Normalisieren: fehlende Felder als leer ergänzen
    return {f: felder.get(f, {"wert": None, "konfidenz": 0.0}) for f in OCR_FELDER}


def flache_extraktion(felder: dict) -> dict:
    """Reduziert {feld: {wert, konfidenz}} auf {feld: wert} (Vorbefüllung)."""
    return {f: (v or {}).get("wert") for f, v in (felder or {}).items()}
