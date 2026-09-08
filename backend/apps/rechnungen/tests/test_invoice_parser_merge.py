"""
Tests für die Zusammenführung XML + KI in ``extract_invoice_data``.

Geprüft wird die Rangfolge, nicht das Parsen — das deckt
``test_facturx_parser`` ab. Der KI-Aufruf ist durchgängig ersetzt; kein
Test spricht mit einer API.

Der wichtigste Fall ist ``test_leeres_sellertradeparty_laesst_ki_namen_stehen``:
daran entscheidet sich, ob die Erweiterung Belege verbessert oder manche
verschlechtert.

Ohne Datenbank (``SimpleTestCase``).
"""
import tempfile
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.rechnungen.services import invoice_parser
from apps.rechnungen.services.invoice_parser import extract_invoice_data
from apps.rechnungen.tests.test_facturx_parser import (
    POSITIONEN, VERKAEUFER_LEER, VERKAEUFER_VOLL, ZAHLUNGSMITTEL, _xml,
)

try:
    import pymupdf
except ImportError:                                   # pragma: no cover
    import fitz as pymupdf


# Genug Text, damit der Textlayer-Pfad greift (>= PDF_MIN_TEXT_LENGTH) und
# nicht der PDF-Direkt-Fallback — beide sind trotzdem ersetzt.
SEITENTEXT = (
    'Rechnung Nummer R021376 vom 07.09.2026 ueber das Erneuern des '
    'Wasserfiltereinsatzes. Nettosumme 204,00 EUR zuzueglich 19 Prozent '
    'Umsatzsteuer, Endsumme 242,76 EUR. Zahlbar sofort und ohne Abzug.'
)

# Was die KI liefern würde — bewusst mit ANDEREN Werten als die XML,
# damit jeder Test zeigt, welche Quelle tatsächlich gewonnen hat.
KI_ERGEBNIS = {
    'supplier': 'KI-Lieferant AG',
    'iban': 'DE02120300000000202051',
    'invoice_number': 'KI-4711',
    'invoice_date': '2026-01-02',
    'due_date': '2026-01-31',
    'gross_amount': '99.99',
    'net_amount': '84.02',
    'vat_rate': '19',
    'currency': 'CHF',
    'description': 'Zusammenfassung der KI zur Leistung.',
    'property_address': 'Kronberger Str. 7-9, 61462 Koenigstein',
    'customer_number': 'KI-999',
}


class MergeTest(SimpleTestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ordner = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _pdf(self, name: str, xml: bytes | None = None) -> str:
        pfad = self.ordner / name
        doc = pymupdf.open()
        seite = doc.new_page()
        seite.insert_textbox(pymupdf.Rect(50, 50, 550, 300), SEITENTEXT, fontsize=11)
        if xml is not None:
            doc.embfile_add('factur-x.xml', xml)
        doc.save(str(pfad))
        doc.close()
        return str(pfad)

    @contextmanager
    def _ki(self, ergebnis):
        """Ersetzt beide KI-Wege — welcher greift, hängt am Textlayer."""
        with patch.object(invoice_parser, '_parse_with_ai', return_value=ergebnis), \
             patch.object(invoice_parser, '_parse_pdf_direct_with_ai', return_value=ergebnis):
            yield

    # --- Rangfolge XML vor KI --------------------------------------------

    def test_xml_gewinnt_ueber_ki(self):
        pfad = self._pdf('voll.pdf', _xml(VERKAEUFER_VOLL, zahlungsmittel=ZAHLUNGSMITTEL))
        with self._ki(KI_ERGEBNIS):
            d = extract_invoice_data(pfad)

        self.assertEqual(d['supplier'], 'Daniel Muster GmbH')
        self.assertEqual(d['iban'], 'DE89370400440532013000')
        self.assertEqual(d['invoice_number'], 'R021376')
        self.assertEqual(d['invoice_date'], date(2026, 9, 7))
        self.assertEqual(d['due_date'], date(2026, 9, 17))
        self.assertEqual(d['gross_amount'], Decimal('242.76'))
        self.assertEqual(d['net_amount'], Decimal('204.00'))
        self.assertEqual(d['currency'], 'EUR')
        self.assertEqual(d['customer_number'], '12933')
        for feld in ('supplier', 'iban', 'invoice_number', 'gross_amount'):
            self.assertEqual(d['quellen'][feld], 'xml', feld)

    def test_normalisierung_greift_auch_auf_xml_werte(self):
        """Die XML-Werte laufen durch dieselbe Normalisierung wie KI-Werte —
        sonst matcht die IBAN aus der XML nie gegen die Stammdaten."""
        pfad = self._pdf('norm.pdf', _xml(VERKAEUFER_VOLL, zahlungsmittel=ZAHLUNGSMITTEL))
        with self._ki(KI_ERGEBNIS):
            d = extract_invoice_data(pfad)
        self.assertEqual(d['iban'], 'DE89370400440532013000')      # Leerzeichen weg
        self.assertEqual(d['supplier_normalized'], 'daniel muster')  # GmbH entfernt
        self.assertEqual(d['invoice_number_normalized'], 'R021376')

    # --- Der Bestandsfall ------------------------------------------------

    def test_leeres_sellertradeparty_laesst_ki_namen_stehen(self):
        """Der Live-Fall R021376/R021343: die XML ist da, ihr Verkäufer-Element
        aber leer. Sie darf den erkannten Namen nicht mit Leere überschreiben —
        sonst verschlechtert die Erweiterung genau diese Belege."""
        pfad = self._pdf('leer.pdf', _xml(VERKAEUFER_LEER))
        with self._ki(KI_ERGEBNIS):
            d = extract_invoice_data(pfad)

        self.assertEqual(d['supplier'], 'KI-Lieferant AG')
        self.assertEqual(d['quellen']['supplier'], 'ki')
        self.assertEqual(d['iban'], 'DE02120300000000202051')
        self.assertEqual(d['quellen']['iban'], 'ki')
        # Der brauchbare Teil der XML gewinnt trotzdem:
        self.assertEqual(d['invoice_number'], 'R021376')
        self.assertEqual(d['quellen']['invoice_number'], 'xml')
        self.assertEqual(d['customer_number'], '12933')
        self.assertEqual(d['quellen']['customer_number'], 'xml')

    def test_leere_xml_felder_ohne_ki_bleiben_leer(self):
        """KI ausgefallen UND leeres Verkäufer-Element: kein Lieferant. Der
        Fall muss ohne Ausnahme durchlaufen und darf nichts erfinden."""
        pfad = self._pdf('nichts.pdf', _xml(VERKAEUFER_LEER))
        with self._ki({}):
            d = extract_invoice_data(pfad)
        self.assertIsNone(d['supplier'])
        self.assertIsNone(d['iban'])
        self.assertNotIn('supplier', d['quellen'])
        self.assertEqual(d['invoice_number'], 'R021376')

    # --- Rückfall ohne XML -----------------------------------------------

    def test_ohne_xml_unveraendertes_verhalten(self):
        pfad = self._pdf('ohnexml.pdf', xml=None)
        with self._ki(KI_ERGEBNIS):
            d = extract_invoice_data(pfad)

        self.assertEqual(d['supplier'], 'KI-Lieferant AG')
        self.assertEqual(d['invoice_number'], 'KI-4711')
        self.assertEqual(d['gross_amount'], Decimal('99.99'))
        self.assertEqual(d['currency'], 'CHF')
        self.assertEqual(d['customer_number'], 'KI-999')
        self.assertEqual(d['e_rechnung_profil'], '')
        self.assertTrue(all(q == 'ki' for q in d['quellen'].values()), d['quellen'])

    def test_xml_traegt_wenn_ki_ausfaellt(self):
        """Kein API-Schlüssel, Zeitüberschreitung: ``_parse_with_ai`` gibt {}
        zurück. Bei einer E-Rechnung ist die Rechnung trotzdem vollständig."""
        pfad = self._pdf('kiaus.pdf', _xml(VERKAEUFER_VOLL, zahlungsmittel=ZAHLUNGSMITTEL))
        with self._ki({}):
            d = extract_invoice_data(pfad)
        self.assertEqual(d['supplier'], 'Daniel Muster GmbH')
        self.assertEqual(d['gross_amount'], Decimal('242.76'))
        self.assertEqual(d['invoice_number'], 'R021376')

    # --- Die beiden Ausnahmen von "XML gewinnt" --------------------------

    def test_leistungstext_kommt_von_der_ki(self):
        """Aus description entsteht der leistungstext_hash, an dem die
        gelernten Match-Regeln hängen. Ein Quellenwechsel würde sie
        wirkungslos machen."""
        pfad = self._pdf('desc.pdf', _xml(VERKAEUFER_VOLL, positionen=POSITIONEN))
        with self._ki(KI_ERGEBNIS):
            d = extract_invoice_data(pfad)
        self.assertEqual(d['description'], 'Zusammenfassung der KI zur Leistung.')
        self.assertEqual(d['quellen']['description'], 'ki')

    def test_leistungstext_faellt_auf_xml_positionen_zurueck(self):
        pfad = self._pdf('desc2.pdf', _xml(VERKAEUFER_VOLL, positionen=POSITIONEN))
        with self._ki({**KI_ERGEBNIS, 'description': None}):
            d = extract_invoice_data(pfad)
        self.assertIn('Ersatzfilterkerzen', d['description'])
        self.assertEqual(d['quellen']['description'], 'xml')

    def test_liegenschaft_nur_von_der_ki(self):
        """Die XML-Lieferanschrift ist bei WEG-Belegen die Verwalteradresse.
        Sie darf die Objekterkennung nicht speisen."""
        pfad = self._pdf('objekt.pdf', _xml(VERKAEUFER_VOLL))
        with self._ki(KI_ERGEBNIS):
            d = extract_invoice_data(pfad)
        self.assertEqual(d['property_address'], 'Kronberger Str. 7-9, 61462 Koenigstein')
        self.assertNotIn('Coventrystr', d['property_address'])
        self.assertEqual(d['quellen']['property_address'], 'ki')

    # --- Gutschrift ------------------------------------------------------

    def test_gutschrift_aus_xml_typcode(self):
        pfad = self._pdf('gs.pdf', _xml(VERKAEUFER_VOLL, typcode='381'))
        with self._ki({**KI_ERGEBNIS, 'is_credit_note': False}):
            d = extract_invoice_data(pfad)
        self.assertTrue(d['is_credit_note'])
        self.assertEqual(d['gross_amount'], Decimal('242.76'))   # Betrag bleibt positiv

    def test_gutschrift_aus_negativem_ki_betrag_ohne_xml(self):
        pfad = self._pdf('gs2.pdf', xml=None)
        with self._ki({**KI_ERGEBNIS, 'gross_amount': '-150.00'}):
            d = extract_invoice_data(pfad)
        self.assertTrue(d['is_credit_note'])
        self.assertEqual(d['gross_amount'], Decimal('150.00'))

    # --- Herkunftsprotokoll ----------------------------------------------

    def test_profil_wird_protokolliert(self):
        pfad = self._pdf('profil.pdf', _xml(VERKAEUFER_VOLL))
        with self._ki(KI_ERGEBNIS):
            d = extract_invoice_data(pfad)
        self.assertIn('factur-x.eu:1p0:extended', d['e_rechnung_profil'])
