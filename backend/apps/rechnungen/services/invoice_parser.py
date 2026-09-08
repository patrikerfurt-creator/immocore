"""
Rechnungsparser – portiert aus DOPRE

Drei Quellen in fester Rangfolge:

1. **E-Rechnungs-XML** (ZUGFeRD 2.x / Factur-X), sofern im PDF eingebettet.
   Exakte Feldwerte des Ausstellers — nichts daran ist geschätzt.
2. **PDF-Textlayer** (PyMuPDF), ersatzweise OCR (Tesseract).
3. **Claude-Extraktion** über diesen Text, bzw. direkt über das PDF, wenn
   der Textlayer zu dünn ist.

Die XML hat Vorrang, aber nur mit einem ECHTEN Wert — Details in
``extract_invoice_data``.
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

from .facturx_parser import lese_facturx

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
- gross_amount     : Endbetrag inkl. MwSt als Dezimalzahl (ohne Währungssymbol).
                     WICHTIG: Bei Gutschriften, Guthaben oder negativen Salden (z.B. Jahresabrechnung
                     Gas/Strom bei der der Verbrauch kleiner als die geleisteten Abschläge ist)
                     muss gross_amount NEGATIV sein (z.B. -150.00). Der Betrag spiegelt immer
                     den tatsächlichen Endsaldo des Dokuments wider.
- net_amount       : Nettobetrag als Dezimalzahl (ohne Währungssymbol, falls vorhanden, sonst null).
                     Ebenfalls negativ bei Gutschrift/Guthaben.
- vat_rate         : MwSt-Satz als Zahl (z.B. 19 für 19%), bei Gutschrift meist 0 oder null
- is_credit_note   : true wenn das Dokument eine Gutschrift, ein Guthaben oder einen negativen
                     Endsaldo ausweist (gross_amount < 0), sonst false
- currency         : Währungskürzel, fast immer "EUR"
- supplier         : Firmenname des Lieferanten (NICHT die eigene Firma)
- iban             : IBAN des Lieferanten falls vorhanden, sonst null
- description      : Kurze Leistungsbeschreibung (1-2 Sätze), sonst null
- property_address : Liegenschaft/Objektadresse (Straße + Hausnummer) für die die Leistung erbracht wurde – NUR wenn explizit auf der Rechnung angegeben, sonst null
- customer_number  : Kundennummer des Rechnungsempfängers beim Lieferanten (z.B. "Kundennr. 100001", "Kunden-ID: 4711") – NUR die Zahl/ID, sonst null

Regeln:
- Felder die du nicht sicher erkennen kannst → null (niemals raten)
- Zahlen: Dezimaltrennzeichen immer Punkt, kein Tausendertrennzeichen
- Datumsformat strikt: YYYY-MM-DD
- Beispiel Gutschrift: "Ihr Guthaben: 150,00 EUR" → gross_amount: -150.00, is_credit_note: true

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
            max_tokens=4000,  # claude-sonnet-5 denkt zuerst — Budget für Thinking + JSON
            system=_SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': f'Rechnungstext:\n\n{text[:8000]}'}],
        )
        raw = next((b.text for b in response.content if getattr(b, 'type', None) == 'text'), '').strip()
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
            max_tokens=4000,  # claude-sonnet-5 denkt zuerst — Budget für Thinking + JSON
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
        raw = next((b.text for b in response.content if getattr(b, 'type', None) == 'text'), '').strip()
        raw = re.sub(r'^```[a-z]*\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)
        return json.loads(raw)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning('KI-PDF-Direkt-Parsing fehlgeschlagen: %s', exc)
        return {}


def _safe_decimal(value) -> Optional[Decimal]:
    """
    Konvertiert Wert sicher in Decimal.
    Negative Werte (Gutschriften/Guthaben) sind erlaubt — nur exakt 0 wird verworfen.
    """
    if value is None:
        return None
    try:
        d = Decimal(str(value))
        return d if d != 0 else None
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


def _leer(wert) -> bool:
    """Ist der Wert eine Lücke? ``False`` und ``0`` sind KEINE Lücke."""
    return wert is None or wert == '' or wert == []


def _waehle(feld: str, bevorzugt: dict, ersatz: dict,
            quellen: dict, namen: tuple = ('xml', 'ki')):
    """Feldwert aus zwei Quellen, mit Herkunftsprotokoll.

    Die bevorzugte Quelle gewinnt nur mit einem ECHTEN Wert. Das ist der
    Kern der Zusammenführung: ein leeres XML-Element ist keine Aussage
    "unbekannt", sondern eine Lücke. Ein Lieferant im Bestand liefert
    ``<ram:SellerTradeParty/>`` — würde die XML dort trotzdem "gewinnen",
    ersetzte sie den vom Textpfad korrekt erkannten Namen durch Leere und
    die Erweiterung machte solche Belege schlechter als vorher.
    """
    wert = bevorzugt.get(feld)
    if not _leer(wert):
        quellen[feld] = namen[0]
        return wert
    wert = ersatz.get(feld)
    if not _leer(wert):
        quellen[feld] = namen[1]
        return wert
    return None


def extract_invoice_data(filepath: str) -> dict:
    """Hauptfunktion: E-Rechnungs-XML + OCR + KI-Parsing.

    Rangfolge je Feld: XML vor KI — mit zwei begründeten Ausnahmen.

    ``description`` kommt bevorzugt von der KI. Aus diesem Feld entsteht
    ``leistungstext`` und daraus der ``leistungstext_hash``, an dem die
    gelernten ``RechnungsMatchRegel`` hängen (auf Live 61 aktive Regeln,
    206 Rechnungen mit Hash). Die XML liefert rohe Positionsbezeichnungen,
    die KI einen zusammenfassenden Satz — ein Quellenwechsel würde jeden
    bestehenden Hash verschieben und die gelernten Regeln wirkungslos
    machen. Die XML-Positionen bleiben der Rückfall, wenn die KI nichts
    liefert.

    ``property_address`` kommt ausschließlich von der KI. Die XML hat für
    die Liegenschaft kein verlässliches Feld: in ``ShipToTradeParty``
    steht bei WEG-Belegen die Adresse der Verwaltung, während die
    Liegenschaft im Namen der Lieferpartei steckt. Siehe
    ``facturx_parser.lese_facturx``.

    Der KI-Aufruf entfällt NICHT, auch wenn die XML vollständig ist. Das
    wäre die naheliegende Ersparnis (13 von 25 Belegen tragen eine XML),
    kostet aber ``property_address`` und damit die Objekterkennung über
    die Anschrift. Diese Optimierung braucht zuerst eine Objekterkennung,
    die nicht an einem KI-Feld hängt.

    Zusätzlich im Ergebnis: ``quellen`` (Feld → 'xml'|'ki') und
    ``e_rechnung_profil`` — damit später nachvollziehbar ist, welcher Wert
    belegt und welcher geschätzt war.
    """
    xml = lese_facturx(filepath) or {}
    text = extract_text(filepath)
    if len(text) < PDF_MIN_TEXT_LENGTH and filepath.lower().endswith('.pdf'):
        ai = _parse_pdf_direct_with_ai(filepath)
    else:
        ai = _parse_with_ai(text)

    quellen: dict = {}

    invoice_number_raw = _waehle('invoice_number', xml, ai, quellen)
    iban_raw           = _waehle('iban', xml, ai, quellen)
    supplier           = _waehle('supplier', xml, ai, quellen)
    kundennummer       = _waehle('customer_number', xml, ai, quellen)

    gross_raw = _safe_decimal(_waehle('gross_amount', xml, ai, quellen))
    net_raw   = _safe_decimal(_waehle('net_amount', xml, ai, quellen))

    # is_credit_note: XML-Typcode 381, KI-Flag oder negativer Betrag.
    is_credit_note = bool(_waehle('is_credit_note', xml, ai, quellen)) \
        or (gross_raw is not None and gross_raw < 0)

    # betrag_brutto / betrag_netto immer positiv speichern — Flag ist_gutschrift trägt das Vorzeichen
    gross_amount = abs(gross_raw) if gross_raw is not None else None
    net_amount   = abs(net_raw)   if net_raw   is not None else None

    if not _leer(ai.get('property_address')):
        quellen['property_address'] = 'ki'

    return {
        'text': text,
        'invoice_number': invoice_number_raw,
        'invoice_number_normalized': normalize_invoice_number(invoice_number_raw),
        'invoice_date': _safe_date(_waehle('invoice_date', xml, ai, quellen)),
        'due_date': _safe_date(_waehle('due_date', xml, ai, quellen)),
        'gross_amount': gross_amount,
        'net_amount': net_amount,
        'vat_rate': _safe_decimal(_waehle('vat_rate', xml, ai, quellen)),
        'currency': _waehle('currency', xml, ai, quellen) or 'EUR',
        'supplier': supplier,
        'supplier_normalized': normalize_supplier_name(supplier),
        'iban': normalize_iban(iban_raw),
        # Rangfolge bewusst umgekehrt — siehe Docstring.
        'description': _waehle('description', ai, xml, quellen, namen=('ki', 'xml')),
        'property_address': ai.get('property_address'),
        'customer_number': str(kundennummer).strip() if kundennummer else '',
        'is_credit_note': is_credit_note,
        'quellen': quellen,
        'e_rechnung_profil': xml.get('profil') or '',
    }
