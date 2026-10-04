"""Objektspezifische Mahn-Konfiguration (``MahnEinstellung``) und die Mahnberechnung.

* Pflicht: ohne Konfiguration wird nicht gemahnt (ValueError / HTTP 400).
* Feste Gebühr je Objekt, bei jeder Stufe gleich.
* Zinsen nur mit Schalter (Default aus).
* Globale Staffel: Stufe 1 Verzug 15 / Frist 14, Stufe 2 Verzug 30 / Frist 10.
* Forderungsfall nach der letzten konfigurierten Stufe.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from rest_framework.test import APITestCase

from apps.buchhaltung.models import (
    Basiszinssatz, Buchung, Buchungsart, MahnEinstellung, Mahnlauf, Mahnung, OffenerPosten,
)
from apps.buchhaltung.services import mahn_einstellung_service, mahnwesen
from apps.buchhaltung.services.mahnwesen import MahnKonfigFehlt
from apps.konten.models import Konto
from apps.korrespondenz.tests import fixtures
from apps.objekte.models import Wirtschaftsjahr

HEUTE = date(2026, 9, 30)


class MahnBasis(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.s = fixtures.szenario(wechsel=False, mahnung=False, vorgang=False)
        cls.objekt = cls.s.objekt
        cls.konto = cls.s.konto
        Basiszinssatz.objects.get_or_create(gueltig_ab=date(2020, 1, 1), defaults={'satz': Decimal('3.62')})

    def konfiguriere(self, mahngebuehr='7.50', anzahl=2, zinsen=False):
        return MahnEinstellung.objects.create(
            objekt=self.objekt, mahngebuehr=Decimal(mahngebuehr),
            anzahl_mahnstufen=anzahl, zinsen_erheben=zinsen,
        )

    def op(self, tage, betrag='350.00', mahnstufe=0):
        faellig = HEUTE - timedelta(days=tage)
        buchung = Buchung.objects.create(
            objekt=self.objekt, betrag=Decimal(betrag), buchungsdatum=faellig,
            buchungstext=f'Hausgeld {faellig:%m/%Y}',
        )
        return OffenerPosten.objects.create(
            buchung=buchung, personenkonto=self.konto, betrag_ursprung=Decimal(betrag),
            betrag_offen=Decimal(betrag), faellig_ab=faellig, mahnstufe=mahnstufe,
        )

    def vorschau(self):
        return mahnwesen.simuliere_mahnlauf(str(self.objekt.pk), HEUTE)

    def buchungsarten_und_konto(self):
        """MAHNG/VERZZ (kommen produktiv aus seed_buchungsarten) und ein Konto für die Buchungen."""
        for nr, kuerzel in (('991', 'MAHNG'), ('992', 'VERZZ')):
            Buchungsart.objects.create(nr=nr, kuerzel=kuerzel, bezeichnung=kuerzel, beleg_pflicht=False)
        wj = Wirtschaftsjahr.objects.create(objekt=self.objekt, jahr=HEUTE.year, beginn_monat=1)
        Konto.objects.create(wirtschaftsjahr=wj, kontonummer='18000', kontoname='Bank', kontoart='standard')

    def fuehre_aus(self):
        """Mahnlauf mit Stichtag ``HEUTE`` (der Lauf nimmt sein Erstellungsdatum als Stichtag)."""
        lauf = Mahnlauf.objects.create(objekt=self.objekt, ausgefuehrt_von=self.s.ersteller)
        Mahnlauf.objects.filter(pk=lauf.pk).update(erstellt_am=lauf.erstellt_am.replace(
            year=HEUTE.year, month=HEUTE.month, day=HEUTE.day, hour=12))
        return lauf, mahnwesen.fuehre_mahnlauf_aus(str(lauf.pk), self.s.ersteller)


class BlockadeOhneKonfigurationTest(MahnBasis):

    def test_simulieren_wirft_value_error(self):
        self.op(60)
        with self.assertRaises(ValueError) as ctx:
            self.vorschau()
        self.assertIsInstance(ctx.exception, MahnKonfigFehlt)
        self.assertIn('keine Mahn-Konfiguration hinterlegt', str(ctx.exception))

    def test_ausfuehren_wirft_value_error_und_bucht_nichts(self):
        self.op(60)
        lauf = Mahnlauf.objects.create(objekt=self.objekt, ausgefuehrt_von=self.s.ersteller)
        buchungen = Buchung.objects.count()
        with self.assertRaises(ValueError):
            mahnwesen.fuehre_mahnlauf_aus(str(lauf.pk), self.s.ersteller)
        self.assertEqual((Mahnung.objects.count(), Buchung.objects.count()), (0, buchungen))

    def test_api_simulieren_und_ausfuehren_geben_400(self):
        self.op(60)
        self.client.force_authenticate(self.s.ersteller)
        antwort = self.client.post('/api/v1/mahnlaeufe/simulieren/', {'objekt': str(self.objekt.pk)}, format='json')
        self.assertEqual(antwort.status_code, 400)
        self.assertIn('keine Mahn-Konfiguration', antwort.json()['error'])
        lauf = Mahnlauf.objects.create(objekt=self.objekt, ausgefuehrt_von=self.s.ersteller)
        antwort = self.client.post(f'/api/v1/mahnlaeufe/{lauf.pk}/ausfuehren/', format='json')
        self.assertEqual(antwort.status_code, 400)

    def test_batch_kann_das_objekt_sauber_abfangen(self):
        """Ein Batch fängt ``MahnKonfigFehlt`` je Objekt ab und mahnt die übrigen weiter."""
        self.op(60)
        ergebnisse = {}
        for objekt in (self.objekt,):
            try:
                ergebnisse[objekt.pk] = self.vorschau()
            except MahnKonfigFehlt:
                ergebnisse[objekt.pk] = None
        self.assertIsNone(ergebnisse[self.objekt.pk])

    def test_konfiguration_pflichtfeld_und_constraint(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            MahnEinstellung.objects.create(objekt=self.objekt, mahngebuehr=None)
        for anzahl in (0, 3):
            with self.subTest(anzahl=anzahl), self.assertRaises(IntegrityError), transaction.atomic():
                MahnEinstellung.objects.create(objekt=self.objekt, mahngebuehr=Decimal('5'), anzahl_mahnstufen=anzahl)


class StaffelTest(MahnBasis):

    def test_staffel_konstanten(self):
        self.assertEqual(
            [(s['stufe'], s['verzug_tage'], s['frist']) for s in mahnwesen.MAHNSTUFEN],
            [(1, 15, 14), (2, 30, 10)],
        )
        self.assertNotIn('gebuehr', mahnwesen.MAHNSTUFEN[0])
        self.assertEqual((mahnwesen.zahlungsfrist_tage(1), mahnwesen.zahlungsfrist_tage(2)), (14, 10))
        self.assertIsNone(mahnwesen.zahlungsfrist_tage(3))

    def test_stufe_1_erst_ab_15_tagen_verzug(self):
        self.konfiguriere()
        self.op(14)
        self.assertEqual(self.vorschau()['anzahl'], 0)
        OffenerPosten.objects.all().delete()
        self.op(15)
        vorschau = self.vorschau()
        self.assertEqual([(m['mahnstufe'], m['zahlungsfrist_tage']) for m in vorschau['mahnungen']], [(1, 14)])

    def test_stufe_2_erst_ab_30_tagen_verzug(self):
        self.konfiguriere()
        self.op(29, mahnstufe=1)
        self.assertEqual(self.vorschau()['anzahl'], 0)
        OffenerPosten.objects.all().delete()
        self.op(30, mahnstufe=1)
        vorschau = self.vorschau()
        self.assertEqual([(m['mahnstufe'], m['zahlungsfrist_tage']) for m in vorschau['mahnungen']], [(2, 10)])


class GebuehrTest(MahnBasis):

    def test_feste_gebuehr_bei_jeder_stufe_gleich(self):
        self.konfiguriere(mahngebuehr='7.50')
        self.op(60)
        stufe_1 = self.vorschau()['mahnungen'][0]
        OffenerPosten.objects.all().delete()
        self.op(60, mahnstufe=1)
        stufe_2 = self.vorschau()['mahnungen'][0]
        self.assertEqual((stufe_1['mahnstufe'], stufe_2['mahnstufe']), (1, 2))
        self.assertEqual((stufe_1['gebuehr'], stufe_2['gebuehr']), (7.5, 7.5))

    def test_gebuehr_wird_in_mahnung_eingefroren_und_gebucht(self):
        self.buchungsarten_und_konto()
        einstellung = self.konfiguriere(mahngebuehr='7.50')
        self.op(60)
        _, ergebnis = self.fuehre_aus()
        self.assertEqual(ergebnis, {'ok': 1})
        mahnung = Mahnung.objects.get()
        self.assertEqual(mahnung.gebuehr, Decimal('7.50'))
        self.assertEqual(mahnung.buchung_gebuehr.betrag, Decimal('7.50'))
        # Spätere Änderung der Konfiguration ändert die bereits erzeugte Mahnung/Buchung nicht.
        einstellung.mahngebuehr = Decimal('20.00')
        einstellung.save()
        mahnung.refresh_from_db()
        self.assertEqual(mahnung.gebuehr, Decimal('7.50'))
        self.assertEqual(mahnung.buchung_gebuehr.betrag, Decimal('7.50'))

    def test_gebuehr_null_erzeugt_keine_buchung(self):
        self.buchungsarten_und_konto()
        self.konfiguriere(mahngebuehr='0.00')
        self.op(60)
        self.fuehre_aus()
        self.assertIsNone(Mahnung.objects.get().buchung_gebuehr)


class ZinsenTest(MahnBasis):

    def test_default_aus_keine_zinsen_keine_verzz_buchung(self):
        self.buchungsarten_und_konto()
        self.konfiguriere()                       # zinsen_erheben Default False
        self.assertFalse(MahnEinstellung.objects.get().zinsen_erheben)
        self.op(60)
        self.assertEqual(self.vorschau()['mahnungen'][0]['zinsen'], 0.0)
        self.fuehre_aus()
        mahnung = Mahnung.objects.get()
        self.assertEqual(mahnung.zinsen, Decimal('0.00'))
        self.assertIsNone(mahnung.buchung_zinsen)
        self.assertFalse(Buchung.objects.filter(buchungsart__kuerzel='VERZZ').exists())

    def test_schalter_an_zinsen_wie_bisher(self):
        self.buchungsarten_und_konto()
        self.konfiguriere(zinsen=True)
        self.op(60)
        erwartet = mahnwesen.berechne_verzugszinsen(Decimal('350.00'), HEUTE - timedelta(days=60), HEUTE)
        self.assertGreater(erwartet, 0)
        self.assertEqual(Decimal(str(self.vorschau()['mahnungen'][0]['zinsen'])), erwartet.quantize(Decimal('0.01')))
        self.fuehre_aus()
        mahnung = Mahnung.objects.get()
        self.assertEqual(mahnung.zinsen, erwartet.quantize(Decimal('0.01')))
        self.assertEqual(mahnung.buchung_zinsen.buchungsart.kuerzel, 'VERZZ')


class ForderungsfallTest(MahnBasis):

    def test_zwei_stufen_forderungsfall_erst_nach_stufe_2(self):
        self.konfiguriere(anzahl=2)
        self.op(60)
        self.assertFalse(self.vorschau()['mahnungen'][0]['eskaliert_zu_forderungsfall'])
        OffenerPosten.objects.all().delete()
        self.op(60, mahnstufe=1)
        m = self.vorschau()['mahnungen'][0]
        self.assertEqual(m['mahnstufe'], 2)
        self.assertTrue(m['eskaliert_zu_forderungsfall'])

    def test_ausfuehren_setzt_posten_auf_forderungsfall(self):
        self.konfiguriere(anzahl=2)
        posten = self.op(60, mahnstufe=1)
        self.fuehre_aus()
        posten.refresh_from_db()
        self.assertEqual((posten.mahnstufe, posten.status), (2, 'forderungsfall'))

    def test_eine_stufe_ist_stufe_1_die_letzte(self):
        self.konfiguriere(anzahl=1)
        self.op(60)
        m = self.vorschau()['mahnungen'][0]
        self.assertEqual(m['mahnstufe'], 1)
        self.assertTrue(m['eskaliert_zu_forderungsfall'])

    def test_letzte_stufe_erreicht_kein_weiterer_lauf(self):
        """Posten noch offen, aber Stufe == anzahl_mahnstufen: kein Lauf, kein Rückschritt."""
        self.konfiguriere(anzahl=2)
        posten = self.op(120, mahnstufe=2)
        self.assertEqual(self.vorschau()['anzahl'], 0)
        self.fuehre_aus()
        posten.refresh_from_db()
        self.assertEqual((Mahnung.objects.count(), posten.mahnstufe), (0, 2))

    def test_reduzierte_stufenzahl_mahnt_nicht_weiter(self):
        self.konfiguriere(anzahl=1)
        self.op(120, mahnstufe=2)
        self.assertEqual(self.vorschau()['anzahl'], 0)


class MahnEinstellungApiTest(MahnBasis):

    def url(self):
        return f'/api/v1/objekte/{self.objekt.pk}/mahn-einstellung/'

    def setUp(self):
        self.client.force_authenticate(self.s.ersteller)

    def test_anonym_abgelehnt(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.url()).status_code, (401, 403))

    def test_get_ohne_konfiguration_404(self):
        self.assertEqual(self.client.get(self.url()).status_code, 404)

    def test_put_legt_an_und_aktualisiert(self):
        antwort = self.client.put(self.url(), {'mahngebuehr': '7.50'}, format='json')
        self.assertEqual(antwort.status_code, 201)
        self.assertEqual(antwort.json(), {'mahngebuehr': '7.50', 'anzahl_mahnstufen': 2, 'zinsen_erheben': False})
        antwort = self.client.put(
            self.url(), {'mahngebuehr': '10.00', 'anzahl_mahnstufen': 1, 'zinsen_erheben': True}, format='json')
        self.assertEqual(antwort.status_code, 200)
        self.assertEqual(self.client.get(self.url()).json(),
                         {'mahngebuehr': '10.00', 'anzahl_mahnstufen': 1, 'zinsen_erheben': True})
        self.assertEqual(MahnEinstellung.objects.filter(objekt=self.objekt).count(), 1)

    def test_put_validiert(self):
        for daten in ({}, {'mahngebuehr': '-1'}, {'mahngebuehr': '5', 'anzahl_mahnstufen': 3},
                      {'mahngebuehr': '5', 'anzahl_mahnstufen': 0}, {'mahngebuehr': 'abc'}):
            with self.subTest(daten=daten):
                self.assertEqual(self.client.put(self.url(), daten, format='json').status_code, 400)
        self.assertFalse(MahnEinstellung.objects.exists())

    def test_nach_put_ist_mahnen_freigeschaltet(self):
        self.op(60)
        self.client.put(self.url(), {'mahngebuehr': '5.00'}, format='json')
        antwort = self.client.post('/api/v1/mahnlaeufe/simulieren/', {'objekt': str(self.objekt.pk)}, format='json')
        self.assertEqual(antwort.status_code, 200)

    def test_service_hole_setze(self):
        self.assertIsNone(mahn_einstellung_service.hole(self.objekt))
        einstellung, angelegt = mahn_einstellung_service.setze(self.objekt, Decimal('3.00'))
        self.assertTrue(angelegt)
        self.assertEqual(mahn_einstellung_service.hole(self.objekt), einstellung)
