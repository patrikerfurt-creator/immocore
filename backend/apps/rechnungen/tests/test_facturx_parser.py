"""
Tests für den E-Rechnungs-Leser (``services.facturx_parser``).

Die Fixture-PDFs werden zur Laufzeit erzeugt statt echte Belege ins Repo
zu legen — das hält Kundendaten aus der Versionsverwaltung und macht
sichtbar, welche XML-Struktur der jeweilige Fall prüft.

Nachgebaut sind die Konstellationen, die im Bestand tatsächlich auftreten:
vollständige Factur-X mit IBAN, mehrere Anhänge mit der XML an letzter
Stelle, und der Beleg mit leerem ``<ram:SellerTradeParty/>``, an dem die
Kreditorerkennung scheitert.

Ohne Datenbank (``SimpleTestCase``) — der Leser kennt kein Django.
"""
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.test import SimpleTestCase

from apps.rechnungen.services.facturx_parser import lese_facturx

try:
    import pymupdf
except ImportError:                                   # pragma: no cover
    import fitz as pymupdf


NS = (
    'xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100" '
    'xmlns:ram="urn:un:unece:uncefact:data:standard:'
    'ReusableAggregateBusinessInformationEntity:100" '
    'xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100"'
)


def _xml(verkaeufer: str, *, typcode: str = '380', zahlungsmittel: str = '',
         steuern: str = '', positionen: str = '', wurzel: str = 'CrossIndustryInvoice') -> bytes:
    """Baut eine CII-Rechnung. ``verkaeufer`` wird roh eingesetzt, damit der
    Test auch ein LEERES SellerTradeParty-Element ausdrücken kann."""
    if not steuern:
        steuern = (
            '<ram:ApplicableTradeTax>'
            '<ram:CalculatedAmount>38.76</ram:CalculatedAmount>'
            '<ram:TypeCode>VAT</ram:TypeCode>'
            '<ram:BasisAmount>204.00</ram:BasisAmount>'
            '<ram:RateApplicablePercent>19.00</ram:RateApplicablePercent>'
            '</ram:ApplicableTradeTax>'
        )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rsm:{wurzel} {NS}>
  <rsm:ExchangedDocumentContext>
    <ram:GuidelineSpecifiedDocumentContextParameter>
      <ram:ID>urn:cen.eu:en16931:2017#conformant#urn:factur-x.eu:1p0:extended</ram:ID>
    </ram:GuidelineSpecifiedDocumentContextParameter>
  </rsm:ExchangedDocumentContext>
  <rsm:ExchangedDocument>
    <ram:ID>R021376</ram:ID>
    <ram:TypeCode>{typcode}</ram:TypeCode>
    <ram:IssueDateTime>
      <udt:DateTimeString format="102">20260907</udt:DateTimeString>
    </ram:IssueDateTime>
  </rsm:ExchangedDocument>
  <rsm:SupplyChainTradeTransaction>
    {positionen}
    <ram:ApplicableHeaderTradeAgreement>
      {verkaeufer}
      <ram:BuyerTradeParty>
        <ram:ID>12933</ram:ID>
        <ram:Name>00010 WEG Kronberger Str. 7-9, Koenigstein vertr. d. Verwaltung GmbH</ram:Name>
      </ram:BuyerTradeParty>
    </ram:ApplicableHeaderTradeAgreement>
    <ram:ApplicableHeaderTradeDelivery>
      <ram:ShipToTradeParty>
        <ram:Name>00010 WEG Kronberger Str. 7-9, Koenigstein</ram:Name>
        <ram:PostalTradeAddress>
          <ram:PostcodeCode>65934</ram:PostcodeCode>
          <ram:LineOne>Coventrystr. 32</ram:LineOne>
          <ram:CityName>Frankfurt</ram:CityName>
        </ram:PostalTradeAddress>
      </ram:ShipToTradeParty>
    </ram:ApplicableHeaderTradeDelivery>
    <ram:ApplicableHeaderTradeSettlement>
      <ram:InvoiceCurrencyCode>EUR</ram:InvoiceCurrencyCode>
      {zahlungsmittel}
      {steuern}
      <ram:SpecifiedTradePaymentTerms>
        <ram:DueDateDateTime>
          <udt:DateTimeString format="102">20260917</udt:DateTimeString>
        </ram:DueDateDateTime>
      </ram:SpecifiedTradePaymentTerms>
      <ram:SpecifiedTradeSettlementHeaderMonetarySummation>
        <ram:LineTotalAmount>204.00</ram:LineTotalAmount>
        <ram:TaxBasisTotalAmount>204.00</ram:TaxBasisTotalAmount>
        <ram:TaxTotalAmount currencyID="EUR">38.76</ram:TaxTotalAmount>
        <ram:GrandTotalAmount>242.76</ram:GrandTotalAmount>
        <ram:DuePayableAmount>242.76</ram:DuePayableAmount>
      </ram:SpecifiedTradeSettlementHeaderMonetarySummation>
    </ram:ApplicableHeaderTradeSettlement>
  </rsm:SupplyChainTradeTransaction>
</rsm:{wurzel}>""".encode('utf-8')


VERKAEUFER_VOLL = (
    '<ram:SellerTradeParty>'
    '<ram:Name>Daniel Muster GmbH</ram:Name>'
    '<ram:SpecifiedTaxRegistration><ram:ID schemeID="FC">040/123/456</ram:ID>'
    '</ram:SpecifiedTaxRegistration>'
    '<ram:SpecifiedTaxRegistration><ram:ID schemeID="VA">DE811234567</ram:ID>'
    '</ram:SpecifiedTaxRegistration>'
    '</ram:SellerTradeParty>'
)
VERKAEUFER_LEER = '<ram:SellerTradeParty/>'

ZAHLUNGSMITTEL = (
    '<ram:SpecifiedTradeSettlementPaymentMeans>'
    '<ram:TypeCode>58</ram:TypeCode>'
    '<ram:PayeePartyCreditorFinancialAccount>'
    '<ram:IBANID>DE89 3704 0044 0532 0130 00</ram:IBANID>'
    '</ram:PayeePartyCreditorFinancialAccount>'
    '<ram:PayeeSpecifiedCreditorFinancialInstitution>'
    '<ram:BICID>COBADEFFXXX</ram:BICID>'
    '</ram:PayeeSpecifiedCreditorFinancialInstitution>'
    '</ram:SpecifiedTradeSettlementPaymentMeans>'
)

POSITIONEN = (
    '<ram:IncludedSupplyChainTradeLineItem>'
    '<ram:SpecifiedTradeProduct><ram:Name>Ersatzfilterkerzen 80 my</ram:Name>'
    '</ram:SpecifiedTradeProduct></ram:IncludedSupplyChainTradeLineItem>'
    '<ram:IncludedSupplyChainTradeLineItem>'
    '<ram:SpecifiedTradeProduct><ram:Name>Arbeitszeit\nKundendienstmonteur</ram:Name>'
    '</ram:SpecifiedTradeProduct></ram:IncludedSupplyChainTradeLineItem>'
)


class FacturxLeserTest(SimpleTestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ordner = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _pdf(self, name: str, anhaenge=()) -> str:
        """Erzeugt ein einseitiges PDF mit den angegebenen Anhängen."""
        pfad = self.ordner / name
        doc = pymupdf.open()
        seite = doc.new_page()
        seite.insert_text((72, 72), 'Rechnung R021376')
        for anhang_name, daten in anhaenge:
            doc.embfile_add(anhang_name, daten)
        doc.save(str(pfad))
        doc.close()
        return str(pfad)

    # --- Normalfall ------------------------------------------------------

    def test_vollstaendige_facturx(self):
        pfad = self._pdf('voll.pdf', [
            ('factur-x.xml', _xml(VERKAEUFER_VOLL, zahlungsmittel=ZAHLUNGSMITTEL,
                                  positionen=POSITIONEN)),
        ])
        d = lese_facturx(pfad)
        self.assertEqual(d['supplier'], 'Daniel Muster GmbH')
        self.assertEqual(d['iban'], 'DE89370400440532013000')   # Leerzeichen entfernt
        self.assertEqual(d['bic'], 'COBADEFFXXX')
        self.assertEqual(d['invoice_number'], 'R021376')
        self.assertEqual(d['invoice_date'], date(2026, 9, 7))
        self.assertEqual(d['due_date'], date(2026, 9, 17))
        self.assertEqual(d['gross_amount'], Decimal('242.76'))
        self.assertEqual(d['net_amount'], Decimal('204.00'))
        self.assertEqual(d['vat_amount'], Decimal('38.76'))
        self.assertEqual(d['vat_rate'], Decimal('19.00'))
        self.assertEqual(d['currency'], 'EUR')
        self.assertEqual(d['customer_number'], '12933')
        self.assertNotIn('is_credit_note', d)

    def test_ust_id_statt_steuernummer(self):
        """schemeID VA ist die USt-IdNr., FC die Steuernummer — nicht vertauschen."""
        pfad = self._pdf('ustid.pdf', [('factur-x.xml', _xml(VERKAEUFER_VOLL))])
        self.assertEqual(lese_facturx(pfad)['supplier_ust_id'], 'DE811234567')

    def test_leistungstext_aus_positionen(self):
        pfad = self._pdf('pos.pdf', [
            ('factur-x.xml', _xml(VERKAEUFER_VOLL, positionen=POSITIONEN)),
        ])
        text = lese_facturx(pfad)['description']
        self.assertIn('Ersatzfilterkerzen 80 my', text)
        self.assertIn('Arbeitszeit Kundendienstmonteur', text)   # Zeilenumbruch geglättet

    # --- Der Bestandsfall: leeres SellerTradeParty -----------------------

    def test_leeres_sellertradeparty_liefert_keinen_lieferanten(self):
        """Der Live-Fall R021376. Entscheidend ist, dass der Schlüssel FEHLT
        und nicht leer gesetzt wird — sonst überschreibt er später den vom
        Textpfad erkannten Namen mit Leere."""
        pfad = self._pdf('leer.pdf', [('factur-x.xml', _xml(VERKAEUFER_LEER))])
        d = lese_facturx(pfad)
        self.assertIsNotNone(d)
        self.assertNotIn('supplier', d)
        self.assertNotIn('iban', d)
        # Der Rest der XML bleibt trotzdem nutzbar:
        self.assertEqual(d['invoice_number'], 'R021376')
        self.assertEqual(d['gross_amount'], Decimal('242.76'))
        self.assertEqual(d['customer_number'], '12933')

    def test_ohne_zahlungsmittel_keine_iban(self):
        pfad = self._pdf('ohneiban.pdf', [('factur-x.xml', _xml(VERKAEUFER_VOLL))])
        self.assertNotIn('iban', lese_facturx(pfad))

    # --- Anhang finden ---------------------------------------------------

    def test_xml_hinter_anderen_anhaengen(self):
        """Bestandsbeleg mit drei Anhängen — die XML liegt an letzter Stelle."""
        pfad = self._pdf('mehrere.pdf', [
            ('Pruefergebnis.pdf', b'%PDF-1.4 nicht relevant'),
            ('L_3305314.pdf', b'%PDF-1.4 auch nicht'),
            ('factur-x.xml', _xml(VERKAEUFER_VOLL)),
        ])
        self.assertEqual(lese_facturx(pfad)['supplier'], 'Daniel Muster GmbH')

    def test_abweichender_dateiname_wird_am_inhalt_erkannt(self):
        pfad = self._pdf('fremd.pdf', [('rechnung_export.xml', _xml(VERKAEUFER_VOLL))])
        self.assertEqual(lese_facturx(pfad)['supplier'], 'Daniel Muster GmbH')

    def test_zugferd_1_wurzelelement(self):
        """Namensraum-agnostisch: ZUGFeRD 1.0 heißt CrossIndustryDocument."""
        pfad = self._pdf('alt.pdf', [
            ('zugferd-invoice.xml', _xml(VERKAEUFER_VOLL, wurzel='CrossIndustryDocument')),
        ])
        self.assertEqual(lese_facturx(pfad)['supplier'], 'Daniel Muster GmbH')

    # --- Kein Ergebnis ---------------------------------------------------

    def test_pdf_ohne_anhang(self):
        self.assertIsNone(lese_facturx(self._pdf('nackt.pdf')))

    def test_fremder_xml_anhang(self):
        pfad = self._pdf('fremd2.pdf', [('daten.xml', b'<?xml version="1.0"?><foo/>')])
        self.assertIsNone(lese_facturx(pfad))

    def test_nicht_pdf(self):
        bild = self.ordner / 'scan.jpg'
        bild.write_bytes(b'\xff\xd8\xff\xe0 kein pdf')
        self.assertIsNone(lese_facturx(str(bild)))

    def test_kaputtes_pdf_wirft_nicht(self):
        pfad = self.ordner / 'kaputt.pdf'
        pfad.write_bytes(b'%PDF-1.4 abgeschnitten')
        self.assertIsNone(lese_facturx(str(pfad)))

    def test_fehlende_datei_wirft_nicht(self):
        self.assertIsNone(lese_facturx(str(self.ordner / 'gibtsnicht.pdf')))

    def test_xml_mit_dtd_wird_abgelehnt(self):
        """Entity-Angriffe brauchen eine DTD; gültige Factur-X hat keine."""
        boese = (
            b'<?xml version="1.0"?>\n'
            b'<!DOCTYPE rsm:CrossIndustryInvoice [<!ENTITY a "aaaaaaaaaa">]>\n'
            b'<rsm:CrossIndustryInvoice ' + NS.encode() + b'><ram:X>&a;</ram:X>'
            b'</rsm:CrossIndustryInvoice>'
        )
        pfad = self._pdf('dtd.pdf', [('factur-x.xml', boese)])
        self.assertIsNone(lese_facturx(pfad))

    # --- Sonderfälle -----------------------------------------------------

    def test_gutschrift_ueber_typcode(self):
        pfad = self._pdf('gutschrift.pdf', [
            ('factur-x.xml', _xml(VERKAEUFER_VOLL, typcode='381')),
        ])
        self.assertTrue(lese_facturx(pfad)['is_credit_note'])

    def test_zwei_steuersaetze_ergeben_keinen_satz(self):
        """Ein einzelnes vat_rate wäre bei gemischten Sätzen zwangsläufig
        falsch — dann lieber keine Angabe."""
        steuern = (
            '<ram:ApplicableTradeTax><ram:TypeCode>VAT</ram:TypeCode>'
            '<ram:RateApplicablePercent>19.00</ram:RateApplicablePercent>'
            '</ram:ApplicableTradeTax>'
            '<ram:ApplicableTradeTax><ram:TypeCode>VAT</ram:TypeCode>'
            '<ram:RateApplicablePercent>7.00</ram:RateApplicablePercent>'
            '</ram:ApplicableTradeTax>'
        )
        pfad = self._pdf('zweisaetze.pdf', [
            ('factur-x.xml', _xml(VERKAEUFER_VOLL, steuern=steuern)),
        ])
        d = lese_facturx(pfad)
        self.assertNotIn('vat_rate', d)
        self.assertEqual(d['gross_amount'], Decimal('242.76'))   # Rest bleibt lesbar

    def test_lieferadresse_wird_nicht_zur_liegenschaft(self):
        """Bei WEG-Belegen steht in der Lieferanschrift die Verwalteradresse,
        die Liegenschaft steckt im Namen. Der Leser darf das nicht vermischen."""
        pfad = self._pdf('shipto.pdf', [('factur-x.xml', _xml(VERKAEUFER_VOLL))])
        d = lese_facturx(pfad)
        self.assertNotIn('property_address', d)
        self.assertIn('Kronberger Str. 7-9', d['ship_to_name'])
        self.assertIn('Coventrystr. 32', d['ship_to_address'])

    def test_profil_wird_gemeldet(self):
        pfad = self._pdf('profil.pdf', [('factur-x.xml', _xml(VERKAEUFER_VOLL))])
        self.assertIn('factur-x.eu:1p0:extended', lese_facturx(pfad)['profil'])
