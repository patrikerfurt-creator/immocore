"""
Leser für hybride E-Rechnungen (ZUGFeRD 2.x / Factur-X / XRechnung-CII).

Eine ZUGFeRD-Rechnung ist ein normales PDF, dem eine XML-Datei als Anhang
beiliegt: der Mensch liest das PDF, die Software liest die XML. Damit
stehen Lieferant, IBAN, Rechnungsnummer und Beträge als exakte Feldwerte
bereit — ohne OCR, ohne Sprachmodell, ohne Raten.

Dieses Modul macht genau einen Schritt: PDF rein, Dict raus. Es entscheidet
NICHTS über die Rechnung und schreibt nichts in die Datenbank. Das
Zusammenführen mit dem bisherigen Text-/KI-Pfad passiert in
``invoice_parser.extract_invoice_data``.

Bewusst ohne Django-Import, damit der Leser für sich prüfbar bleibt.

Zentraler Vertrag
-----------------
Ein Schlüssel erscheint im Ergebnis nur, wenn dahinter ein ECHTER Wert
steht. Ein leeres XML-Element ist kein Wert, sondern eine Lücke, und darf
den Text-/KI-Pfad später nicht überschreiben. Das ist nicht theoretisch:
ein Lieferant im Bestand liefert ``<ram:SellerTradeParty/>`` — leer, ohne
Name, ohne Anschrift. Eine Implementierung, die "XML gewinnt" wörtlich
nimmt, würde dort einen erkannten Lieferantennamen durch Leere ersetzen.

Robustheit
----------
* ``lese_facturx`` wirft nie. Kein Beleg darf am Leser scheitern —
  im Zweifel ``None``, dann läuft der bisherige Weg unverändert weiter.
* Namensräume werden ignoriert und nur lokale Tag-Namen verglichen. So
  greift derselbe Code für ZUGFeRD 1.0 (``CrossIndustryDocument``),
  ZUGFeRD 2.x / Factur-X (``CrossIndustryInvoice``) und CII-XRechnung.
* Die XML kommt von außen. Zwei Schranken: Größenobergrenze und
  Ablehnung jeder DTD. Beide Entity-Angriffe auf ``xml.etree``
  (Billion Laughs, Quadratic Blowup) brauchen eine interne DTD; gültige
  Factur-X-XML hat nie eine. Damit fällt die Angriffsklasse weg, ohne
  eine zusätzliche Abhängigkeit ins Prod-Image zu holen.
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

# Anhangsnamen der gängigen Profile (klein geschrieben verglichen).
XML_DATEINAMEN = frozenset({
    'factur-x.xml',            # Factur-X / ZUGFeRD 2.x
    'zugferd-invoice.xml',     # ZUGFeRD 1.0 / 2.0
    'xrechnung.xml',           # CII-XRechnung im PDF
    'cii.xml',
})

# Wurzelelemente, an denen eine unbenannte XML als Rechnung erkannt wird.
CII_WURZELN = frozenset({'crossindustryinvoice', 'crossindustrydocument'})

MAX_XML_BYTES = 4 * 1024 * 1024

# Dokumentarten nach UNTDID 1001. 381 ist die Gutschrift; 380/384/389
# sind Rechnung, Korrekturrechnung und Selbstfakturierung.
TYPCODE_GUTSCHRIFT = {'381', '396'}


# ===========================================================================
# XML-Anhang aus dem PDF holen
# ===========================================================================

def _xml_anhang(doc) -> bytes | None:
    """Sucht den Rechnungs-XML-Anhang im PDF.

    Nicht einfach Anhang 0 nehmen: Belege im Bestand führen mehrere
    Anhänge, bei einem liegt die ``factur-x.xml`` an dritter Stelle hinter
    zwei mitgeschickten PDFs. Erst wird über die Namensliste gesucht,
    danach über den Inhalt jeder .xml — manche Erzeuger benennen die Datei
    abweichend, das Wurzelelement ist aber eindeutig.
    """
    try:
        anzahl = doc.embfile_count()
    except Exception:
        return None

    kandidaten = []
    for i in range(anzahl):
        try:
            name = (doc.embfile_info(i).get('filename') or '').strip()
        except Exception:
            continue
        if name.lower() in XML_DATEINAMEN:
            kandidaten.insert(0, i)          # Namenstreffer haben Vorrang
        elif name.lower().endswith('.xml'):
            kandidaten.append(i)

    for i in kandidaten:
        try:
            rohdaten = doc.embfile_get(i)
        except Exception:
            continue
        if rohdaten and _ist_rechnungs_xml(rohdaten):
            return rohdaten
    return None


def _ist_rechnungs_xml(rohdaten: bytes) -> bool:
    """Trägt der Anhang eine CII-Rechnung — und ist er gefahrlos parsebar?"""
    if len(rohdaten) > MAX_XML_BYTES:
        logger.warning('E-Rechnungs-XML übersprungen: %d Bytes über Grenze', len(rohdaten))
        return False
    kopf = rohdaten[:4096].lower()
    if b'<!doctype' in kopf or b'<!entity' in kopf:
        # Keine gültige Factur-X-XML hat eine DTD. Wer eine mitschickt,
        # will nicht gelesen werden.
        logger.warning('E-Rechnungs-XML mit DTD abgelehnt.')
        return False
    return any(w in kopf for w in (b'crossindustryinvoice', b'crossindustrydocument'))


# ===========================================================================
# Baumnavigation ohne Namensräume
# ===========================================================================

def _lokal(tag: str) -> str:
    """``{urn:…}SellerTradeParty`` → ``sellertradeparty``."""
    return tag.rsplit('}', 1)[-1].lower()


def _kinder(element, name: str) -> list:
    if element is None:
        return []
    gesucht = name.lower()
    return [k for k in element if _lokal(k.tag) == gesucht]


def _pfad(element, *namen: str):
    """Erstes Element entlang des Pfades lokaler Tag-Namen, sonst None."""
    aktuell = element
    for name in namen:
        treffer = _kinder(aktuell, name)
        if not treffer:
            return None
        aktuell = treffer[0]
    return aktuell


def _text(element, *namen: str) -> str:
    """Zusammengezogener Text am Pfadende. Leer, wenn nichts dort steht."""
    ziel = _pfad(element, *namen) if namen else element
    if ziel is None or ziel.text is None:
        return ''
    return re.sub(r'\s+', ' ', ziel.text).strip()


def _dezimal(element, *namen: str):
    wert = _text(element, *namen)
    if not wert:
        return None
    try:
        return Decimal(wert.replace(' ', ''))
    except InvalidOperation:
        return None


def _datum(element, *namen: str):
    """CII-Datum. ``format="102"`` ist JJJJMMTT, daneben kommt ISO vor."""
    ziel = _pfad(element, *namen)
    if ziel is None:
        return None
    # Der Wert steht in einem udt:DateTimeString unter dem Element.
    roh = (_text(ziel, 'DateTimeString') or _text(ziel)).strip()
    if not roh:
        return None
    for muster in ('%Y%m%d', '%Y-%m-%d'):
        try:
            return datetime.strptime(roh, muster).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(roh).date()
    except ValueError:
        return None


# ===========================================================================
# Hauptfunktion
# ===========================================================================

def lese_facturx(filepath: str) -> dict | None:
    """Liest die eingebettete E-Rechnungs-XML eines PDFs.

    Rückgabe: Dict mit ausschließlich befüllten Schlüsseln, oder ``None``
    wenn das PDF keine (lesbare) Rechnungs-XML enthält. Wirft nie.

    Mögliche Schlüssel: ``supplier``, ``supplier_ust_id``, ``iban``,
    ``bic``, ``invoice_number``, ``invoice_date``, ``due_date``,
    ``gross_amount``, ``net_amount``, ``vat_amount``, ``vat_rate``,
    ``currency``, ``is_credit_note``, ``customer_number``,
    ``description``, ``ship_to_name``, ``ship_to_address``, ``profil``.

    ``ship_to_*`` sind bewusst NICHT auf ``property_address`` gemappt: bei
    WEG-Belegen steht in der Lieferanschrift regelmäßig die Adresse der
    Verwaltung, während die Liegenschaft im Namen der Lieferpartei steckt
    ("00010 WEG Kronberger Str. 7-9 vertr. d. …"). Wer das verwechselt,
    ordnet Rechnungen dem Objekt der Verwalteradresse zu. Die Auswertung
    gehört daher in die Objekterkennung, nicht in den Leser.
    """
    if not str(filepath).lower().endswith('.pdf'):
        return None
    try:
        import pymupdf
    except ImportError:                          # pragma: no cover
        try:
            import fitz as pymupdf
        except ImportError:
            logger.warning('PyMuPDF fehlt — E-Rechnungs-XML wird nicht gelesen.')
            return None

    try:
        with pymupdf.open(filepath) as doc:
            rohdaten = _xml_anhang(doc)
    except Exception as exc:
        logger.warning('PDF für E-Rechnungs-XML nicht lesbar (%s): %s', filepath, exc)
        return None

    if not rohdaten:
        return None

    try:
        return _auswerten(rohdaten)
    except Exception as exc:
        logger.warning('E-Rechnungs-XML nicht auswertbar (%s): %s', filepath, exc)
        return None


def _auswerten(rohdaten: bytes) -> dict | None:
    wurzel = ET.fromstring(rohdaten)
    if _lokal(wurzel.tag) not in CII_WURZELN:
        return None

    dokument = _pfad(wurzel, 'ExchangedDocument')
    transaktion = _pfad(wurzel, 'SupplyChainTradeTransaction')
    vereinbarung = _pfad(transaktion, 'ApplicableHeaderTradeAgreement')
    lieferung = _pfad(transaktion, 'ApplicableHeaderTradeDelivery')
    abrechnung = _pfad(transaktion, 'ApplicableHeaderTradeSettlement')
    summen = _pfad(abrechnung, 'SpecifiedTradeSettlementHeaderMonetarySummation')

    verkaeufer = _pfad(vereinbarung, 'SellerTradeParty')
    kaeufer = _pfad(vereinbarung, 'BuyerTradeParty')

    ergebnis: dict = {}

    def setze(schluessel, wert):
        """Nur echte Werte aufnehmen — siehe Modul-Docstring."""
        if wert not in (None, '', []):
            ergebnis[schluessel] = wert

    # --- Wer ---------------------------------------------------------------
    setze('supplier', _text(verkaeufer, 'Name'))
    setze('supplier_ust_id', _ust_id(verkaeufer))
    setze('customer_number', _text(kaeufer, 'ID'))

    # --- Wohin -------------------------------------------------------------
    konto = _pfad(abrechnung, 'SpecifiedTradeSettlementPaymentMeans',
                  'PayeePartyCreditorFinancialAccount')
    if konto is None:
        konto = _pfad(abrechnung, 'SpecifiedTradeSettlementPaymentMeans',
                      'PayeeSpecifiedCreditorFinancialAccount')
    setze('iban', _text(konto, 'IBANID').replace(' ', '').upper())
    setze('bic', _text(
        _pfad(abrechnung, 'SpecifiedTradeSettlementPaymentMeans',
              'PayeeSpecifiedCreditorFinancialInstitution'), 'BICID',
    ))

    # --- Was ---------------------------------------------------------------
    setze('invoice_number', _text(dokument, 'ID'))
    setze('invoice_date', _datum(dokument, 'IssueDateTime'))
    setze('due_date', _datum(abrechnung, 'SpecifiedTradePaymentTerms', 'DueDateDateTime'))
    setze('currency', _text(abrechnung, 'InvoiceCurrencyCode'))

    brutto = _dezimal(summen, 'GrandTotalAmount')
    if brutto is None:
        brutto = _dezimal(summen, 'DuePayableAmount')
    setze('gross_amount', brutto)
    setze('net_amount', _dezimal(summen, 'TaxBasisTotalAmount'))
    setze('vat_amount', _dezimal(summen, 'TaxTotalAmount'))
    setze('vat_rate', _steuersatz(abrechnung))

    typcode = _text(dokument, 'TypeCode')
    if typcode in TYPCODE_GUTSCHRIFT or (brutto is not None and brutto < 0):
        ergebnis['is_credit_note'] = True

    setze('description', _leistungstext(transaktion))

    # --- Lieferort (roh, siehe Docstring) ----------------------------------
    lieferpartei = _pfad(lieferung, 'ShipToTradeParty')
    setze('ship_to_name', _text(lieferpartei, 'Name'))
    setze('ship_to_address', _anschrift(_pfad(lieferpartei, 'PostalTradeAddress')))

    setze('profil', _text(
        _pfad(wurzel, 'ExchangedDocumentContext',
              'GuidelineSpecifiedDocumentContextParameter'), 'ID',
    ))

    # Ein Ergebnis ohne jeden Inhalt ist wie kein Ergebnis.
    return ergebnis or None


def _ust_id(partei) -> str:
    """USt-IdNr. der Partei (schemeID ``VA``), nicht die Steuernummer (``FC``)."""
    for eintrag in _kinder(partei, 'SpecifiedTaxRegistration'):
        for kennung in _kinder(eintrag, 'ID'):
            if (kennung.get('schemeID') or '').upper() == 'VA':
                return (kennung.text or '').strip()
    return ''


def _steuersatz(abrechnung):
    """Steuersatz nur bei Eindeutigkeit.

    Eine Rechnung darf mehrere Steuersätze tragen (19 % Material, 7 %
    Sonstiges). Ein einzelnes Feld ``vat_rate`` wäre dann zwangsläufig
    falsch — dann lieber keine Angabe.
    """
    saetze = set()
    for steuer in _kinder(abrechnung, 'ApplicableTradeTax'):
        wert = _dezimal(steuer, 'RateApplicablePercent')
        if wert is not None:
            saetze.add(wert)
    return saetze.pop() if len(saetze) == 1 else None


def _leistungstext(transaktion, max_laenge: int = 500) -> str:
    """Positionsbezeichnungen zu einem Leistungstext zusammenziehen."""
    teile: list[str] = []
    for position in _kinder(transaktion, 'IncludedSupplyChainTradeLineItem'):
        name = _text(_pfad(position, 'SpecifiedTradeProduct'), 'Name')
        if name and name not in teile:
            teile.append(name)
    text = '; '.join(teile)
    return text[:max_laenge].strip()


def _anschrift(adresse) -> str:
    if adresse is None:
        return ''
    strasse = ' '.join(filter(None, [
        _text(adresse, 'LineOne'), _text(adresse, 'LineTwo'),
    ])).strip()
    ort = ' '.join(filter(None, [
        _text(adresse, 'PostcodeCode'), _text(adresse, 'CityName'),
    ])).strip()
    return ', '.join(filter(None, [strasse, ort]))
