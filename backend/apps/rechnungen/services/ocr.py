"""
KI-OCR für Rechnungs-PDFs via Claude API.
Extrahiert: Lieferant, IBAN, Betrag, Datum, MwSt.
"""
import base64
import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def ki_ocr_rechnung(rechnung) -> dict:
    """
    Liest ein hochgeladenes Rechnungs-PDF via Claude API aus.

    Gibt ein Dict zurück:
    {
        "lieferant_name": "...",
        "lieferant_iban": "...",
        "rechnungsnummer": "...",
        "rechnungsdatum": "YYYY-MM-DD",
        "faelligkeitsdatum": "YYYY-MM-DD",
        "betrag_netto": 0.00,
        "betrag_brutto": 0.00,
        "mwst_satz": 19,
        "leistungsbeschreibung": "..."
    }
    """
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic-Paket nicht installiert")

    api_key = getattr(settings, 'ANTHROPIC_API_KEY', None)
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY nicht konfiguriert")

    with rechnung.pdf_upload.open('rb') as f:
        pdf_data = base64.standard_b64encode(f.read()).decode('utf-8')

    prompt = """Extrahiere aus dieser Rechnung folgende Felder als JSON:
{
  "lieferant_name": "...",
  "lieferant_iban": "...",
  "rechnungsnummer": "...",
  "rechnungsdatum": "YYYY-MM-DD",
  "faelligkeitsdatum": "YYYY-MM-DD",
  "betrag_netto": 0.00,
  "betrag_brutto": 0.00,
  "mwst_satz": 19,
  "leistungsbeschreibung": "..."
}
Antworte NUR mit dem JSON-Objekt, kein Markdown."""

    client = anthropic.Anthropic(api_key=api_key)
    model = getattr(settings, 'ANTHROPIC_MODEL', 'claude-sonnet-4-5')

    message = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{
            'role': 'user',
            'content': [
                {
                    'type': 'document',
                    'source': {
                        'type': 'base64',
                        'media_type': 'application/pdf',
                        'data': pdf_data,
                    },
                },
                {'type': 'text', 'text': prompt},
            ]
        }]
    )

    try:
        return json.loads(message.content[0].text.strip())
    except json.JSONDecodeError:
        logger.error("Claude API lieferte kein gültiges JSON: %s", message.content[0].text)
        raise RuntimeError("Claude API lieferte kein gültiges JSON")
