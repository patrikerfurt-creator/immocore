"""
Rechnungsparser – portiert aus DOPRE
OCR (PyMuPDF + Tesseract) + Claude-KI-Extraktion
"""
import base64
import hashlib
import json
import os
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from django.conf import settings

try:
    import fitz
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False

try:
    import pytesseract
    from pdf2image import convert_from_path
    from PIL import Image, ImageFilter, ImageOps
    OCR_AVAILABLE = True
    tesseract_cmd = getattr(settings, 'TESSERACT_CMD',
                            r'C:\Program Files\Tesseract-OCR\tesseract.exe')
    if os.path.exists(tesseract_cmd):
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
except ImportError:
    OCR_AVAILABLE = False

PDF_MIN_TEXT_LENGTH = 80
PDF_OCR_MAX_PAGES = 2

_SYSTEM_PROMPT = """\
Du bist ein spezialisierter Rechnungsparser für ein deutsches Buchhaltungssystem.
Du erhältst den extrahierten Textinhalt einer Rechnung und gibst ausschließlich
ein gültiges JSON-Objekt zurück – ohne Markdown, ohne Erklärungen.

Extrahiere folgende Felder:
- invoice_number   : Rechnungsnummer als String
- invoice_date     : Rechnungsdatum im Format YYYY-MM-DD
- due_date         : Fälligkeitsdatum im Format YYYY-MM-DD (falls vorhanden, sonst null)
- gross_amount     : Bruttobetrag als Dezimalzahl (ohne Währungssymbol)
- net_amount       : Nettobetrag als Dezimalzahl (ohne Währungssymbol, falls vorhanden)
- vat_rate         : MwSt-Satz als Zahl (z.B. 19 für 19%)
- currency         : Währungskürzel, fast immer "EUR"
- supplier         : Firmenname des Lieferanten (NICHT die eigene Firma)
- iban             : IBAN des Lieferanten falls vorhanden, sonst null
- description      : Kurze Leistungsbeschreibung (1-2 Sätze), sonst null
- property_address : Liegenschaft/Objektadresse (Straße + Hausnummer) für die die Leistung erbracht wurde – NUR wenn explizit auf der Rechnung angegeben, sonst null
- customer_number  : Kundennummer des Rechnungsempfängers beim Lieferanten (z.B. "Kundennr. 100001", "Kunden-ID: 4711") – NUR die Zahl/ID, sonst null

Regeln:
- Felder die du nicht sicher erkennen kannst → null (niemals raten)
- gross_amount ist der Gesamtbetrag inkl. MwSt
- Zahlen: Dezimaltrennzeichen immer Punkt, kein Tausendertrennzeichen
- Datumsformat strikt: YYYY-MM-DD

Antworte NUR mit dem JSON-Objekt.
"""


def get_file_hash(filepath: str) -> str:
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()


def normalize_invoice_number(value: str) -> Optional[str]:
    if not value:
        return None
    value = value.upper().strip()
    for ch in [' ', ':', '.', '_', '\\', '/', '-']:
        value = value.replace(ch, '')
    value = re.sub(r'[^A-Z0-9]', '', value)
    return value or None


def normalize_supplier_name(name: str) -> Optional[str]:
    if not name:
        return None
    text = name.strip().lower()
    text = re.sub(r'[^a-z0-9äöüß&\-\s]', ' ', text)
    text = re.sub(r'\b(gmbh|mbh|ug|ag|kg|ohg|e\.k\.|ek|inc|ltd|llc|co)\b', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text or None


def normalize_iban(value: str) -> Optional[str]:
    if not value:
        return None
    value = value.upper().strip()
    value = re.sub(r'[\s\-]', '', value)
    value = re.sub(r'[^A-Z0-9]', '', value)
    if len(value) < 15 or len(value) > 34:
        return None
    return value


def _extract_text_from_pdf(filepath: str) -> str:
    if not FITZ_AVAILABLE:
        return ''
    with fitz.open(filepath) as doc:
        return '\n'.join(page.get_text('text') for page in doc).strip()


def _best_ocr_text(image) -> str:
    base = image.convert('L')
    base = ImageOps.autocontrast(base)
    sharp = base.filter(ImageFilter.SHARPEN)
    for variant in [sharp, base, image]:
        text = pytesseract.image_to_string(variant, lang='deu+eng', config='--oem 3 --psm 6').strip()
        if len(text) >= PDF_MIN_TEXT_LENGTH:
            return text
    binary = sharp.point(lambda p: 255 if p > 170 else 0)
    return pytesseract.image_to_string(binary, lang='deu+eng', config='--oem 3 --psm 6').strip()


def _extract_text_with_ocr(filepath: str) -> str:
    if not OCR_AVAILABLE:
        return ''
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.pdf':
        images = convert_from_path(filepath, first_page=1, last_page=PDF_OCR_MAX_PAGES, dpi=300)
        return '\n'.join(_best_ocr_text(img) for img in images).strip()
    return _best_ocr_text(Image.open(filepath))


def _normalize_text(text: str) -> str:
    if not text:
        return ''
    text = text.replace('\xa0', ' ').replace('\u00ad', '')
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def extract_text(filepath: str) -> str:
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.pdf':
        text = _normalize_text(_extract_text_from_pdf(filepath))
        if len(text) < PDF_MIN_TEXT_LENGTH:
            return _normalize_text(_extract_text_with_ocr(filepath))
        return text
    return _normalize_text(_extract_text_with_ocr(filepath))


def _parse_with_ai(text: str) -> dict:
    try:
        import anthropic
    except ImportError:
        return {}

    api_key = getattr(settings, 'ANTHROPIC_API_KEY', None)
    if not api_key:
        return {}

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=getattr(settings, 'ANTHROPIC_MODEL', 'claude-sonnet-4-6'),
            max_tokens=512,
            system=_SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': f'Rechnungstext:\n\n{text[:8000]}'}],
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r'^```[a-z]*\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)
        return json.loads(raw)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning('KI-Parsing fehlgeschlagen: %s', exc)
        return {}


def _parse_pdf_direct_with_ai(filepath: str) -> dict:
    """Fallback: PDF direkt als base64 an Claude — wenn Texterkennung nichts liefert."""
    try:
        import anthropic
    except ImportError:
        return {}

    api_key = getattr(settings, 'ANTHROPIC_API_KEY', None)
    if not api_key:
        return {}

    try:
        with open(filepath, 'rb') as f:
            pdf_data = base64.standard_b64encode(f.read()).decode('utf-8')
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=getattr(settings, 'ANTHROPIC_MODEL', 'claude-sonnet-4-6'),
            max_tokens=512,
            system=_SYSTEM_PROMPT,
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
                    {'type': 'text', 'text': 'Extrahiere die Rechnungsdaten aus diesem PDF.'},
                ],
            }],
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r'^```[a-z]*\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)
        return json.loads(raw)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning('KI-PDF-Direkt-Parsing fehlgeschlagen: %s', exc)
        return {}


def _safe_decimal(value) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        d = Decimal(str(value))
        return d if d > 0 else None
    except InvalidOperation:
        return None


def _safe_date(value):
    if not value:
        return None
    for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
        try:
            return datetime.strptime(str(value), fmt).date()
        except ValueError:
            pass
    return None


def extract_invoice_data(filepath: str) -> dict:
    """Hauptfunktion: OCR + KI-Parsing. Gibt strukturiertes Dict zurück."""
    text = extract_text(filepath)
    if len(text) < PDF_MIN_TEXT_LENGTH and filepath.lower().endswith('.pdf'):
        ai = _parse_pdf_direct_with_ai(filepath)
    else:
        ai = _parse_with_ai(text)

    invoice_number_raw = ai.get('invoice_number')
    iban_raw = ai.get('iban')

    return {
        'text': text,
        'invoice_number': invoice_number_raw,
        'invoice_number_normalized': normalize_invoice_number(invoice_number_raw),
        'invoice_date': _safe_date(ai.get('invoice_date')),
        'due_date': _safe_date(ai.get('due_date')),
        'gross_amount': _safe_decimal(ai.get('gross_amount')),
        'net_amount': _safe_decimal(ai.get('net_amount')),
        'vat_rate': _safe_decimal(ai.get('vat_rate')),
        'currency': ai.get('currency') or 'EUR',
        'supplier': ai.get('supplier'),
        'supplier_normalized': normalize_supplier_name(ai.get('supplier')),
        'iban': normalize_iban(iban_raw),
        'description': ai.get('description'),
        'property_address': ai.get('property_address'),
        'customer_number': str(ai.get('customer_number')).strip() if ai.get('customer_number') else '',
    }
