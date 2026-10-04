"""Test 7 (Spec 11): Pflicht-Eingabefeld fehlt -> Validierung schlägt fehl.

Hinweis: Spec-Test 7 lautet "Serienlauf nicht freigebbar". Die Serienlauf-
Freigabe entsteht erst in Phase 4; sie ruft ``eingabefelder_service.validiere``
auf. Deshalb wird hier die Validierungsfunktion direkt getestet.
"""
from datetime import date, time
from decimal import Decimal

from django.test import SimpleTestCase

from apps.korrespondenz.services.eingabefelder_service import pruefe_definition, validiere

ETV_FELDER = [
    {'name': 'versammlung_datum', 'label': 'Datum der Versammlung', 'typ': 'datum', 'pflicht': True},
    {'name': 'versammlung_uhrzeit', 'label': 'Uhrzeit', 'typ': 'uhrzeit', 'pflicht': True},
    {'name': 'versammlung_ort', 'label': 'Ort / Adresse', 'typ': 'text', 'pflicht': True},
    {'name': 'tagesordnung', 'label': 'Tagesordnungspunkte', 'typ': 'liste', 'pflicht': True},
    {'name': 'art', 'label': 'Art', 'typ': 'text', 'pflicht': False, 'default': 'ordentliche'},
]
VOLL = {
    'versammlung_datum': '2026-10-15', 'versammlung_uhrzeit': '16:00',
    'versammlung_ort': 'Gemeindesaal', 'tagesordnung': ['Eröffnung', 'Wirtschaftsplan'],
}


class PflichtfelderTest(SimpleTestCase):

    def test_vollstaendig_ist_gueltig_und_getypt(self):
        erg = validiere(ETV_FELDER, VOLL)
        self.assertTrue(erg.gueltig, erg.fehler)
        self.assertEqual(erg.werte['versammlung_datum'], date(2026, 10, 15))
        self.assertEqual(erg.werte['versammlung_uhrzeit'], time(16, 0))
        self.assertEqual(erg.werte['tagesordnung'], ['Eröffnung', 'Wirtschaftsplan'])
        self.assertEqual(erg.werte['art'], 'ordentliche')   # Default

    def test_fehlendes_pflichtfeld(self):
        for name in VOLL:
            werte = {k: v for k, v in VOLL.items() if k != name}
            erg = validiere(ETV_FELDER, werte)
            self.assertFalse(erg.gueltig, f'{name} fehlt, aber gültig')
            self.assertEqual(len(erg.fehler), 1)
            self.assertNotIn(name, erg.werte)

    def test_leere_werte_zaehlen_als_fehlend(self):
        for leer in (None, '', '   ', [], ['', '  ']):
            erg = validiere(ETV_FELDER, dict(VOLL, versammlung_ort=leer, tagesordnung=leer))
            self.assertEqual(len(erg.fehler), 2, f'{leer!r}')

    def test_meldung_nennt_das_label(self):
        erg = validiere(ETV_FELDER, {})
        self.assertTrue(any('Datum der Versammlung' in f for f in erg.fehler))
        self.assertEqual(len(erg.fehler), 4)

    def test_optionales_feld_ohne_default_fehlt_einfach(self):
        felder = [{'name': 'zusatz', 'typ': 'text', 'pflicht': False}]
        erg = validiere(felder, {})
        self.assertTrue(erg.gueltig)
        self.assertNotIn('zusatz', erg.werte)

    def test_unbekannte_schluessel_werden_nicht_uebernommen(self):
        erg = validiere(ETV_FELDER, dict(VOLL, fremd='x'))
        self.assertTrue(erg.gueltig)
        self.assertNotIn('fremd', erg.werte)


class TypenTest(SimpleTestCase):

    def _eins(self, typ, wert, pflicht=True):
        return validiere([{'name': 'f', 'label': 'F', 'typ': typ, 'pflicht': pflicht}], {'f': wert})

    def test_datum(self):
        self.assertEqual(self._eins('datum', '15.10.2026').werte['f'], date(2026, 10, 15))
        self.assertEqual(self._eins('datum', date(2026, 10, 15)).werte['f'], date(2026, 10, 15))
        self.assertFalse(self._eins('datum', 'morgen').gueltig)
        self.assertFalse(self._eins('datum', '2026-13-45').gueltig)

    def test_uhrzeit(self):
        self.assertEqual(self._eins('uhrzeit', '16.30').werte['f'], time(16, 30))
        self.assertFalse(self._eins('uhrzeit', '25:00').gueltig)
        self.assertFalse(self._eins('uhrzeit', 'abends').gueltig)

    def test_betrag(self):
        self.assertEqual(self._eins('betrag', '1.234,56').werte['f'], Decimal('1234.56'))
        self.assertEqual(self._eins('betrag', '12.5').werte['f'], Decimal('12.5'))
        self.assertEqual(self._eins('betrag', 7).werte['f'], Decimal('7'))
        self.assertFalse(self._eins('betrag', 'viel').gueltig)
        self.assertFalse(self._eins('betrag', True).gueltig)

    def test_liste_aus_mehrzeiligem_text(self):
        self.assertEqual(self._eins('liste', 'A\n\nB \n').werte['f'], ['A', 'B'])
        self.assertFalse(self._eins('liste', 5).gueltig)

    def test_ja_nein_false_ist_ein_gueltiger_wert(self):
        erg = self._eins('ja_nein', False)
        self.assertTrue(erg.gueltig)
        self.assertIs(erg.werte['f'], False)
        self.assertIs(self._eins('ja_nein', 'ja').werte['f'], True)
        self.assertFalse(self._eins('ja_nein', 'vielleicht').gueltig)

    def test_text_lehnt_strukturen_ab(self):
        self.assertFalse(self._eins('text', {'a': 1}).gueltig)
        self.assertEqual(self._eins('mehrzeilig', ' a\nb ').werte['f'], 'a\nb')


class DefinitionTest(SimpleTestCase):

    def test_unbekannter_typ_und_doppelter_name(self):
        fehler = pruefe_definition([
            {'name': 'a', 'typ': 'zauber'}, {'name': 'a', 'typ': 'text'}, {'name': 'X y', 'typ': 'text'},
        ])
        self.assertEqual(len(fehler), 3)

    def test_ungueltige_definition_blockiert_validierung(self):
        erg = validiere([{'name': 'a', 'typ': 'zauber'}], {'a': 1})
        self.assertFalse(erg.gueltig)

    def test_etv_definition_ist_gueltig(self):
        self.assertEqual(pruefe_definition(ETV_FELDER), [])
