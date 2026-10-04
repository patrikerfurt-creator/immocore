"""Tests 3, 4, 5 (Spec 11) sowie Filter und Blocktypen der Render-Engine."""
from datetime import date, time
from decimal import Decimal

from django.test import SimpleTestCase

from apps.korrespondenz.models import VorlagenVersion
from apps.korrespondenz.services import filters, render_service


def _version(inhalt, betreff='Betreff', **kw):
    """Ungespeicherte Version - die Engine liest nur Attribute."""
    return VorlagenVersion(betreff=betreff, inhalt=inhalt, **kw)


KONTEXT = {
    'empfaenger': {'anschrift_zeilen': ['Herrn', 'Max <Mustermann>', '60311 Frankfurt'],
                   'briefanrede': 'Sehr geehrter Herr Mustermann,'},
    'objekt': {'bezeichnung': 'WEG Musterstraße 1', 'ist_weg': True},
    'mahnung': {
        'gebuehr': Decimal('5.00'), 'gesamtbetrag': Decimal('1234.5'), 'frist': date(2026, 10, 13),
        'offene_posten': [
            {'faellig_ab': date(2026, 8, 1), 'bezeichnung': 'Hausgeld 08/2026',
             'betrag_ursprung': Decimal('350'), 'betrag_offen': Decimal('350')},
        ],
    },
    'ev': {'sepa_mandat_fehlt': True},
}


class DeterminismusTest(SimpleTestCase):
    """Test 3."""

    def test_zweimal_rendern_liefert_byte_gleiches_html(self):
        version = _version(
            [
                {'typ': 'text', 'inhalt': '{{ empfaenger.briefanrede }}\n\nBetrag {{ mahnung.gesamtbetrag | euro }} bis {{ mahnung.frist | datum_lang }}.'},
                {'typ': 'tabelle', 'quelle': 'mahnung.offene_posten'},
                {'typ': 'liste', 'quelle': 'eingabe.tagesordnung'},
                {'typ': 'bedingt', 'bedingung': 'ev.sepa_mandat_fehlt', 'inhalt': 'SEPA fehlt.'},
                {'typ': 'seitenumbruch'},
                {'typ': 'anlage_seite', 'titel': 'Vollmacht', 'inhalt': '{{ empfaenger.anschrift_zeilen }}'},
            ],
            betreff='Mahnung {{ objekt.bezeichnung }}',
            eingabefelder=[{'name': 'tagesordnung', 'typ': 'liste', 'pflicht': True}],
        )
        eingabe = {'tagesordnung': ['Eröffnung', 'Wirtschaftsplan']}
        a = render_service.render(version, KONTEXT, eingabe)
        b = render_service.render(version, KONTEXT, eingabe)
        self.assertEqual(a.fehler, '')
        self.assertEqual(a.html.encode('utf-8'), b.html.encode('utf-8'))
        self.assertEqual(a.snapshot, b.snapshot)
        self.assertEqual(a.betreff, 'Mahnung WEG Musterstraße 1')


class StrictUndefinedTest(SimpleTestCase):
    """Test 4 (Render-Teil): fehlender Pflichtwert -> Fehler, kein HTML."""

    def test_fehlender_wert_im_text(self):
        erg = render_service.render(
            _version([{'typ': 'text', 'inhalt': 'Bis {{ mahnung.gibt_es_nicht }}'}]), KONTEXT, {})
        self.assertTrue(erg.fehler)
        self.assertIn('mahnung.gibt_es_nicht', erg.fehler)
        self.assertEqual((erg.html, erg.betreff, erg.snapshot), ('', '', {}))

    def test_fehlende_gruppe(self):
        erg = render_service.render(_version([{'typ': 'text', 'inhalt': '{{ bank.iban }}'}]), KONTEXT, {})
        self.assertTrue(erg.fehler)
        self.assertEqual(erg.html, '')

    def test_fehlender_wert_im_betreff(self):
        erg = render_service.render(_version([], betreff='X {{ bank.iban }}'), KONTEXT, {})
        self.assertTrue(erg.fehler)
        self.assertEqual(erg.html, '')

    def test_fehlender_wert_in_bedingung(self):
        erg = render_service.render(
            _version([{'typ': 'bedingt', 'bedingung': 'ev.gibt_es_nicht', 'inhalt': 'x'}]), KONTEXT, {})
        self.assertTrue(erg.fehler)

    def test_default_filter_faengt_fehlenden_wert_ab(self):
        erg = render_service.render(
            _version([{'typ': 'text', 'inhalt': 'Zusatz: {{ objekt.zusatz | default("keiner") }}'}]),
            KONTEXT, {})
        self.assertEqual(erg.fehler, '')
        self.assertIn('Zusatz: keiner', erg.html)

    def test_pflichtfeld_der_eingabe_fehlt(self):
        version = _version(
            [{'typ': 'text', 'inhalt': '{{ eingabe.ort }}'}],
            eingabefelder=[{'name': 'ort', 'typ': 'text', 'pflicht': True, 'label': 'Ort'}],
        )
        erg = render_service.render(version, KONTEXT, {})
        self.assertIn('Ort', erg.fehler)
        self.assertEqual(erg.html, '')

    def test_pflicht_platzhalter_muss_vorkommen(self):
        version = _version([{'typ': 'text', 'inhalt': 'ohne'}], pflicht_platzhalter=['mahnung.frist'])
        erg = render_service.render(version, KONTEXT, {})
        self.assertIn('mahnung.frist', erg.fehler)

    def test_nicht_gerenderter_bedingter_block_braucht_seine_werte_nicht(self):
        kontext = dict(KONTEXT, ev={'sepa_mandat_fehlt': False})
        version = _version(
            [{'typ': 'bedingt', 'bedingung': 'ev.sepa_mandat_fehlt', 'inhalt': '{{ bank.iban }}'}])
        erg = render_service.render(version, kontext, {})
        self.assertEqual((erg.fehler, erg.html), ('', ''))


class SandboxTest(SimpleTestCase):
    """Test 5: __class__, .objects und {% import %} werden abgewiesen."""

    def _abgewiesen(self, quelle):
        erg = render_service.render(_version([{'typ': 'text', 'inhalt': quelle}]), KONTEXT, {})
        self.assertTrue(erg.fehler, f'{quelle!r} wurde nicht abgewiesen')
        self.assertEqual(erg.html, '')

    def test_dunder_class(self):
        self._abgewiesen('{{ objekt.__class__ }}')

    def test_dunder_class_ueber_getitem(self):
        self._abgewiesen("{{ objekt['__class__'] }}")

    def test_dunder_mro_kette(self):
        self._abgewiesen('{{ objekt.__class__.__mro__ }}')

    def test_objects_manager(self):
        self._abgewiesen('{{ objekt.objects.all }}')

    def test_import(self):
        self._abgewiesen("{% import 'os' as os %}{{ os }}")

    def test_from_import(self):
        self._abgewiesen("{% from 'os' import path %}")

    def test_include_extends_macro_set(self):
        for quelle in ("{% include 'x' %}", "{% extends 'x' %}",
                       '{% macro m() %}x{% endmacro %}', '{% set a = 1 %}{{ a }}'):
            self._abgewiesen(quelle)

    def test_funktionsaufruf_und_globals(self):
        for quelle in ('{{ range(3) }}', '{{ objekt.bezeichnung.upper() }}', '{{ cycler }}'):
            self._abgewiesen(quelle)

    def test_unbekannter_filter(self):
        self._abgewiesen('{{ objekt.bezeichnung | attr("x") }}')

    def test_syntaxfehler(self):
        self._abgewiesen('{{ objekt.bezeichnung ')

    def test_einschleusen_ueber_bedingung(self):
        erg = render_service.render(
            _version([{'typ': 'bedingt', 'bedingung': "1 %}{% import 'os' as o %}{% if 1", 'inhalt': 'x'}]),
            KONTEXT, {})
        self.assertTrue(erg.fehler)

    def test_verbotenes_konstrukt_im_betreff(self):
        erg = render_service.render(_version([], betreff='{{ objekt.__class__ }}'), KONTEXT, {})
        self.assertTrue(erg.fehler)


class BlockTest(SimpleTestCase):
    def test_werte_werden_escaped(self):
        erg = render_service.render(
            _version([{'typ': 'text', 'inhalt': '{{ empfaenger.anschrift_zeilen }}'}]), KONTEXT, {})
        self.assertIn('Max &lt;Mustermann&gt;', erg.html)
        self.assertIn('Herrn<br>Max', erg.html)

    def test_text_ohne_tags_wird_zu_absaetzen(self):
        erg = render_service.render(_version([{'typ': 'text', 'inhalt': 'a\nb\n\nc'}]), KONTEXT, {})
        self.assertEqual(erg.html, '<p>a<br>\nb</p>\n<p>c</p>')

    def test_html_text_bleibt_unveraendert(self):
        erg = render_service.render(
            _version([{'typ': 'text', 'inhalt': '<p><b>{{ objekt.bezeichnung }}</b></p>'}]), KONTEXT, {})
        self.assertEqual(erg.html, '<p><b>WEG Musterstraße 1</b></p>')

    def test_tabelle_formatiert_datum_und_euro(self):
        erg = render_service.render(
            _version([{'typ': 'tabelle', 'quelle': 'mahnung.offene_posten'}]), KONTEXT, {})
        self.assertIn('01.08.2026', erg.html)
        self.assertIn('350,00 €', erg.html)
        self.assertIn('Hausgeld 08/2026', erg.html)

    def test_leere_tabelle_ist_fehler(self):
        kontext = {'mahnung': {'offene_posten': []}}
        erg = render_service.render(
            _version([{'typ': 'tabelle', 'quelle': 'mahnung.offene_posten'}]), kontext, {})
        self.assertTrue(erg.fehler)

    def test_liste_nummeriert(self):
        version = _version(
            [{'typ': 'liste', 'quelle': 'eingabe.top'}],
            eingabefelder=[{'name': 'top', 'typ': 'liste', 'pflicht': True}],
        )
        erg = render_service.render(version, KONTEXT, {'top': 'Eins\nZwei & drei'})
        self.assertEqual(erg.html, '<ol>\n<li>Eins</li>\n<li>Zwei &amp; drei</li>\n</ol>')

    def test_bedingung_mit_vergleich(self):
        version = _version(
            [{'typ': 'bedingt', 'bedingung': 'mahnung.gebuehr > 0', 'inhalt': 'Gebühr beschlossen.'}])
        self.assertIn('Gebühr beschlossen.', render_service.render(version, KONTEXT, {}).html)
        null = dict(KONTEXT, mahnung=dict(KONTEXT['mahnung'], gebuehr=Decimal('0')))
        self.assertEqual(render_service.render(version, null, {}).html, '')

    def test_seitenumbruch_und_anlage_seite(self):
        erg = render_service.render(_version([
            {'typ': 'seitenumbruch'},
            {'typ': 'anlage_seite', 'titel': 'Vollmacht', 'inhalt': 'Text'},
        ]), KONTEXT, {})
        self.assertIn('class="seitenumbruch"', erg.html)
        self.assertIn('<h1 class="anlage-titel">Vollmacht</h1>', erg.html)
        self.assertIn('class="anlage-seite"', erg.html)

    def test_baustein(self):
        version = _version([{'typ': 'baustein', 'code': 'gruss'}])
        erg = render_service.render(
            version, KONTEXT, {}, bausteine={'gruss': 'Hallo {{ objekt.bezeichnung }}'})
        self.assertEqual(erg.html, '<p>Hallo WEG Musterstraße 1</p>')
        self.assertTrue(render_service.render(version, KONTEXT, {}).fehler)

    def test_unbekannter_blocktyp(self):
        self.assertTrue(render_service.render(_version([{'typ': 'zauber'}]), KONTEXT, {}).fehler)

    def test_unformatierte_werte_werden_deutsch_ausgegeben(self):
        erg = render_service.render(
            _version([{'typ': 'text', 'inhalt': '{{ mahnung.gesamtbetrag }} / {{ mahnung.frist }}'}]),
            KONTEXT, {})
        self.assertIn('1.234,50 € / 13.10.2026', erg.html)

    def test_snapshot_enthaelt_verwendete_werte_json_sicher(self):
        version = _version(
            [{'typ': 'text', 'inhalt': '{{ mahnung.gesamtbetrag | euro }} {{ mahnung.frist | datum }} {{ eingabe.t | uhrzeit }}'}],
            eingabefelder=[{'name': 't', 'typ': 'uhrzeit', 'pflicht': True}],
        )
        erg = render_service.render(version, KONTEXT, {'t': '16:00'})
        self.assertEqual(erg.snapshot, {
            'eingabe.t': '16:00', 'mahnung.frist': '2026-10-13', 'mahnung.gesamtbetrag': '1234.5',
        })

    def test_betreff_wird_einzeilig(self):
        erg = render_service.render(_version([], betreff='  A\n{{ objekt.bezeichnung }}  '), KONTEXT, {})
        self.assertEqual(erg.betreff, 'A WEG Musterstraße 1')


class FilterTest(SimpleTestCase):
    def test_euro(self):
        self.assertEqual(filters.euro(Decimal('1234.56')), '1.234,56 €')
        self.assertEqual(filters.euro(5), '5,00 €')
        self.assertEqual(filters.euro('1234567.895'), '1.234.567,90 €')
        self.assertEqual(filters.euro(Decimal('-3.5')), '-3,50 €')

    def test_datumsfilter(self):
        d = date(2026, 9, 29)
        self.assertEqual(filters.datum(d), '29.09.2026')
        self.assertEqual(filters.datum('2026-01-05'), '05.01.2026')
        self.assertEqual(filters.datum_mittel(d), '29. September 2026')
        self.assertEqual(filters.datum_lang(d), 'Dienstag, den 29. September 2026')
        self.assertEqual(filters.datum_lang(date(2026, 3, 1)), 'Sonntag, den 1. März 2026')

    def test_uhrzeit(self):
        self.assertEqual(filters.uhrzeit(time(16, 0)), '16.00 Uhr')
        self.assertEqual(filters.uhrzeit('9:05'), '9.05 Uhr')

    def test_iban(self):
        self.assertEqual(filters.iban('de02 5019 0000 6300 2110 10'), 'DE02 5019 0000 6300 2110 10')
        self.assertEqual(filters.iban('DE02501900006300211010'), 'DE02 5019 0000 6300 2110 10')

    def test_upper_und_default(self):
        self.assertEqual(filters.upper('abc'), 'ABC')
        self.assertEqual(filters.default('', 'x'), 'x')
        self.assertEqual(filters.default(None, 'x'), 'x')
        self.assertEqual(filters.default(0, 'x'), 0)
        self.assertIs(filters.default(False, 'x'), False)

    def test_falscher_typ_ist_renderfehler_statt_leerer_stelle(self):
        version = _version([{'typ': 'text', 'inhalt': '{{ objekt.bezeichnung | euro }}'}])
        erg = render_service.render(version, KONTEXT, {})
        self.assertTrue(erg.fehler)
        self.assertEqual(erg.html, '')
