"""
Tests: Buchungsarten für die kreditorische Zahlung (Dialogbuchhaltung,
Modus "Kreditorenbuchung"). Prüft Katalog, Migrationsstand und den
Endpunkt, der das BA-Dropdown füllt.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.buchhaltung.management.commands.seed_buchungsarten import BA_KATALOG
from apps.buchhaltung.models import Buchungsart

User = get_user_model()
URL = '/api/v1/buchungsarten/manuell-waehlbar/'


class KreditorZahlungsBuchungsartenTest(TestCase):

    client_class = APIClient

    def setUp(self):
        self.user = User.objects.create_user('ba-tester', password='x')
        self.client.force_authenticate(self.user)

    # -- Migration 0053 ------------------------------------------------------

    def test_migration_legt_beide_zahlungsarten_an(self):
        for nr, kuerzel, bezeichnung in (('054', 'ZE-K', 'Zahlungseingang'),
                                         ('055', 'ZA-K', 'Zahlungsausgang')):
            ba = Buchungsart.objects.get(nr=nr)
            self.assertEqual(ba.kuerzel, kuerzel)
            self.assertEqual(ba.bezeichnung, bezeichnung)
            self.assertEqual(ba.buchungstyp, 'kreditor')
            self.assertTrue(ba.aktiv)
            # manuell wählbar: darf keine System-BA sein
            self.assertFalse(ba.system_buchungsart)

    def test_richtung_steuert_die_kreditorseite(self):
        """
        Zahlungsausgang baut die Verbindlichkeit ab → Kreditorkonto im Soll,
        Bank im Haben. Zahlungseingang umgekehrt. Die Dialogbuchhaltung leitet
        die Seiten aus diesem Feld ab.
        """
        self.assertEqual(Buchungsart.objects.get(nr='055').richtung, 'abgang')
        self.assertEqual(Buchungsart.objects.get(nr='054').richtung, 'eingang')

    def test_richtung_wird_ans_frontend_ausgeliefert(self):
        resp = self.client.get(URL, {'buchungstyp': 'kreditor'})
        richtungen = {ba['nr']: ba['richtung'] for ba in resp.data}
        self.assertEqual(richtungen['055'], 'abgang')
        self.assertEqual(richtungen['054'], 'eingang')

    def test_seed_katalog_setzt_gleiche_richtung_wie_migration(self):
        from apps.buchhaltung.management.commands.seed_buchungsarten import RICHTUNGEN
        for nr in ('054', '055'):
            self.assertEqual(RICHTUNGEN.get(nr),
                             Buchungsart.objects.get(nr=nr).richtung,
                             f'Seed und Migration weichen bei BA {nr} ab')

    def test_seed_katalog_kennt_beide_zahlungsarten(self):
        """Katalog und Migration dürfen nicht auseinanderlaufen."""
        katalog = {row[0]: row for row in BA_KATALOG}
        for nr, kuerzel, bezeichnung in (('054', 'ZE-K', 'Zahlungseingang'),
                                         ('055', 'ZA-K', 'Zahlungsausgang')):
            self.assertIn(nr, katalog, f'BA {nr} fehlt im Seed-Katalog')
            row = katalog[nr]
            self.assertEqual(row[1], kuerzel)
            self.assertEqual(row[2], bezeichnung)
            self.assertEqual(row[-1], 'kreditor')
            ba = Buchungsart.objects.get(nr=nr)
            self.assertEqual(row[1], ba.kuerzel)
            self.assertEqual(row[2], ba.bezeichnung)
            self.assertEqual(row[-1], ba.buchungstyp)

    # -- Endpunkt, der das Dropdown füllt ------------------------------------

    def test_dropdown_kreditor_enthaelt_beide_zahlungsarten(self):
        resp = self.client.get(URL, {'buchungstyp': 'kreditor'})
        self.assertEqual(resp.status_code, 200, resp.content)
        nummern = [ba['nr'] for ba in resp.data]
        self.assertIn('054', nummern)
        self.assertIn('055', nummern)
        bezeichnungen = {ba['nr']: ba['bezeichnung'] for ba in resp.data}
        self.assertEqual(bezeichnungen['054'], 'Zahlungseingang')
        self.assertEqual(bezeichnungen['055'], 'Zahlungsausgang')

    def test_dropdown_kreditor_enthaelt_keine_fremden_typen(self):
        Buchungsart.objects.create(
            nr='777', kuerzel='FREMD', bezeichnung='Sachkonto-BA',
            buchungstyp='sachkonto', aktiv=True, system_buchungsart=False)
        resp = self.client.get(URL, {'buchungstyp': 'kreditor'})
        nummern = [ba['nr'] for ba in resp.data]
        self.assertNotIn('777', nummern)

    def test_zahlungsarten_nicht_im_personenkonto_dropdown(self):
        resp = self.client.get(URL, {'buchungstyp': 'personenkonto'})
        nummern = [ba['nr'] for ba in resp.data]
        self.assertNotIn('054', nummern)
        self.assertNotIn('055', nummern)

    def test_inaktive_ba_verschwindet_aus_dem_dropdown(self):
        Buchungsart.objects.filter(nr='054').update(aktiv=False)
        resp = self.client.get(URL, {'buchungstyp': 'kreditor'})
        nummern = [ba['nr'] for ba in resp.data]
        self.assertNotIn('054', nummern)
        self.assertIn('055', nummern)


class KreditorOPFilterTest(TestCase):
    """
    Offene Posten je Kreditor — füllt die OP-Anzeige der Dialogbuchhaltung
    bei Zahlungseingang und Zahlungsausgang.
    """

    client_class = APIClient
    URL = '/api/v1/e-banking/kreditor-ops/'

    def setUp(self):
        from datetime import date
        from decimal import Decimal
        from apps.buchhaltung.models import KreditorOP
        from apps.objekte.models import Objekt
        from apps.rechnungen.models import Kreditor

        self.user = User.objects.create_user('op-tester', password='x')
        self.client.force_authenticate(self.user)
        self.objekt = Objekt.objects.create(
            objektnummer='OP-1', objekt_typ='WEG', bezeichnung='OP Testobjekt',
            strasse='Teststr. 1', plz='12345', ort='Teststadt',
            verwaltung_seit=date(2020, 1, 1),
        )
        self.k1 = Kreditor.objects.create(name='Kreditor Eins')
        self.k2 = Kreditor.objects.create(name='Kreditor Zwei')

        def op(nr, kreditor, betrag_offen, status='offen'):
            return KreditorOP.objects.create(
                op_nummer=nr, kreditor=kreditor, objekt=self.objekt,
                betrag_ursprung=Decimal('100.00'),
                betrag_offen=Decimal(betrag_offen),
                faellig_ab=date(2025, 6, 1), status=status,
            )

        self.op_k1_offen = op(96000001, self.k1, '100.00')
        self.op_k1_teil = op(96000002, self.k1, '40.00', 'teilbezahlt')
        self.op_k1_bezahlt = op(96000003, self.k1, '0.00', 'bezahlt')
        self.op_k2_offen = op(96000004, self.k2, '55.00')

    def test_filter_liefert_nur_ops_des_kreditors(self):
        resp = self.client.get(self.URL, {
            'objekt': str(self.objekt.id), 'kreditor': str(self.k1.id)})
        self.assertEqual(resp.status_code, 200, resp.content)
        nummern = {op['op_nummer'] for op in resp.data}
        self.assertEqual(nummern, {96000001, 96000002})
        self.assertNotIn(96000004, nummern)

    def test_filter_blendet_bezahlte_ops_aus(self):
        resp = self.client.get(self.URL, {
            'objekt': str(self.objekt.id), 'kreditor': str(self.k1.id)})
        self.assertNotIn(96000003, {op['op_nummer'] for op in resp.data})

    def test_ohne_kreditor_filter_alle_offenen_des_objekts(self):
        resp = self.client.get(self.URL, {'objekt': str(self.objekt.id)})
        self.assertEqual({op['op_nummer'] for op in resp.data},
                         {96000001, 96000002, 96000004})

    def test_anzeigefelder_vorhanden(self):
        resp = self.client.get(self.URL, {
            'objekt': str(self.objekt.id), 'kreditor': str(self.k1.id)})
        for feld in ('op_nummer', 'betrag_ursprung', 'betrag_offen',
                     'faellig_ab', 'status', 'kreditor_name', 'rechnung_nr', 'betreff'):
            self.assertIn(feld, resp.data[0], f'Feld {feld} fehlt für die OP-Anzeige')
