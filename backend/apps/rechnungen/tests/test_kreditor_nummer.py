"""
Tests für Kreditorennummer-Auto-Vergabe und Duplikat-Prüfung.
"""
from django.test import TestCase

from apps.rechnungen.models import Kreditor
from apps.rechnungen.views import _finde_dubletten_kandidaten


class KreditorennummerTest(TestCase):
    def test_erste_nummer_ist_70000(self):
        k = Kreditor.objects.create(name='Erster Kreditor')
        self.assertEqual(k.kreditorennummer, '70000')

    def test_zweite_nummer_ist_70001(self):
        Kreditor.objects.create(name='Kreditor A')
        k2 = Kreditor.objects.create(name='Kreditor B')
        self.assertEqual(k2.kreditorennummer, '70001')

    def test_nummer_bleibt_unveraendert(self):
        k = Kreditor.objects.create(name='Unveraendert')
        k.name = 'Geaendert'
        k.save()
        k.refresh_from_db()
        self.assertEqual(k.kreditorennummer, '70000')

    def test_nummer_nicht_ueberschrieben_wenn_manuell(self):
        k = Kreditor.objects.create(name='Manuell', kreditorennummer='99999')
        self.assertEqual(k.kreditorennummer, '99999')


class DublikatPruefungTest(TestCase):
    def setUp(self):
        Kreditor.objects.create(
            name='Techem Energy Services GmbH',
            name_normalisiert='techem energy services gmbh',
            iban='DE12345678901234567890',
        )
        Kreditor.objects.create(
            name='Klöber Versicherung',
            name_normalisiert='klöber versicherung',
        )

    def test_iban_match_gibt_exakten_treffer(self):
        result = _finde_dubletten_kandidaten('Irgendwer', 'DE12345678901234567890')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['score'], 1.0)
        self.assertEqual(result[0]['match_typ'], 'iban')

    def test_name_exakt_match(self):
        result = _finde_dubletten_kandidaten('Techem Energy Services GmbH')
        self.assertTrue(any(k['match_typ'] == 'name_exakt' for k in result))

    def test_fuzzy_match(self):
        result = _finde_dubletten_kandidaten('Techem Energy Service')
        self.assertTrue(len(result) > 0)
        self.assertTrue(result[0]['score'] >= 0.65)

    def test_kein_treffer_fuer_fremden_namen(self):
        result = _finde_dubletten_kandidaten('Voellig unbekanntes Unternehmen AG XYZ')
        self.assertEqual(result, [])

    def test_kreditorennummer_in_ergebnis(self):
        result = _finde_dubletten_kandidaten('Techem Energy Services GmbH')
        self.assertIn('kreditorennummer', result[0])
        self.assertTrue(result[0]['kreditorennummer'].startswith('7'))
