"""
Validierung beim Abschluss eines Eigentümerwechsels.

Zwei Fehler haben auf Live zusammen dazu geführt, dass ein Wechsel „erfolgreich"
durchlief und die Einheit danach unbelastet war:

1. Der Wizard schickte durch einen Zeitzonenfehler eine Wirkungsperiode, die
   kein Monatserster war (2025-12-31 statt 2026-01-01).
2. Weil die Hausgeld-Vorbelegung zu diesem Datum nichts fand, kam ein leeres
   `hausgeld_je_ba` an — der Commit stornierte die Sollstellungen des
   Verkäufers und legte für den Käufer keine an.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.buchhaltung.models import Buchungsart, HausgeldSollstellung
from apps.konten.models import Abrechnungsart
from apps.objekte.models import Einheit, Objekt, Wirtschaftsjahr
from apps.personen.models import EigentumsVerhaeltnis, Person
from apps.prozesse.models import Prozess
from apps.prozesse.views import ProzessViewSet


class EWAbschlussValidierungTest(TestCase):

    def setUp(self):
        self.user = get_user_model().objects.create_user(username='ew_abschluss', password='x')
        self.objekt = Objekt.objects.create(
            bezeichnung='Test-WEG-Abschluss', objektnummer='990099', objekt_typ='WEG',
            strasse='Teststr. 4', plz='60000', ort='Teststadt',
            verwaltung_seit=date(2020, 1, 1),
        )
        Wirtschaftsjahr.objects.create(objekt=self.objekt, jahr=2026, beginn_monat=1)
        self.einheit = Einheit.objects.create(
            objekt=self.objekt, einheit_nr='W11', lage='DG',
        )
        Buchungsart.objects.get_or_create(nr='900', defaults={'bezeichnung': 'Hausgeld'})
        Abrechnungsart.objects.get_or_create(
            objekt=self.objekt, code='900', defaults={'bezeichnung': 'Hausgeld'},
        )
        verkaeufer = Person.objects.create(vorname='Vera', nachname='Verkauf', person_typ='100')
        self.kaeufer = Person.objects.create(vorname='Karl', nachname='Kauf', person_typ='100')
        self.verkaeufer_ev = EigentumsVerhaeltnis.objects.create(
            einheit=self.einheit, person=verkaeufer, beginn=date(2020, 1, 1),
        )

    def _prozess(self, hausgeld_je_ba, wirkungs_periode='2026-01-01'):
        return Prozess.objects.create(
            objekt=self.objekt, prozess_typ='eigentuemerwechsel',
            gestartet_von=self.user,
            steps_data={
                '1': {
                    'einheit_id': str(self.einheit.id),
                    'stichtag': '2025-12-12',
                    'wirkungs_periode': wirkungs_periode,
                },
                '2': {'kaeufer_person_id': str(self.kaeufer.id)},
                '3': {'hausgeld_je_ba': hausgeld_je_ba},
                '4': {'stornieren_ids': [], 'erstatten': []},
            },
        )

    def _abschliessen(self, prozess):
        req = APIRequestFactory().post('/')
        force_authenticate(req, user=self.user)
        req.user = self.user
        view = ProzessViewSet.as_view({'post': 'abschliessen'})
        return view(req, pk=str(prozess.id))

    def test_leeres_hausgeld_wird_abgelehnt(self):
        resp = self._abschliessen(self._prozess({}))
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Schritt 3', resp.data['errors'][0])
        self.assertFalse(
            EigentumsVerhaeltnis.objects.filter(person=self.kaeufer).exists(),
            'Käufer-EV darf bei abgelehntem Abschluss nicht entstehen',
        )

    def test_nur_leerstrings_werden_abgelehnt(self):
        resp = self._abschliessen(self._prozess({'.900': '', '.911': '  '}))
        self.assertEqual(resp.status_code, 400)

    def test_nullbetrag_wird_abgelehnt(self):
        resp = self._abschliessen(self._prozess({'.900': '0.00'}))
        self.assertEqual(resp.status_code, 400)

    def test_unparsbarer_betrag_wird_abgelehnt(self):
        resp = self._abschliessen(self._prozess({'.900': 'abc'}))
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Ungültiger Hausgeld-Betrag', resp.data['errors'][0])

    def test_wirkungsperiode_ohne_monatsersten_wird_korrigiert(self):
        """
        Der Live-Fall: 2025-12-31 kam an, richtig ist 2026-01-01. Der Käufer
        muss ab dem Monatsersten beginnen, nicht am 31.12.
        """
        prozess = self._prozess({'.900': '132.42'}, wirkungs_periode='2025-12-31')
        resp = self._abschliessen(prozess)

        self.assertEqual(resp.status_code, 200, getattr(resp, 'data', None))
        kaeufer_ev = EigentumsVerhaeltnis.objects.get(person=self.kaeufer)
        self.assertEqual(kaeufer_ev.beginn, date(2026, 1, 1))

    def test_gueltige_angaben_laufen_durch(self):
        prozess = self._prozess({'.900': '132.42'})
        resp = self._abschliessen(prozess)

        self.assertEqual(resp.status_code, 200, getattr(resp, 'data', None))
        self.assertIsNotNone(resp.data['kaeufer_personenkonto_nr'])
        kaeufer_ev = EigentumsVerhaeltnis.objects.get(person=self.kaeufer)
        self.assertEqual(
            kaeufer_ev.hausgeld_eintraege.get(ba__nr='900').betrag,
            Decimal('132.42'),
        )
        # Verkäufer beendet zum Tag vor dem Stichtag.
        self.verkaeufer_ev.refresh_from_db()
        self.assertEqual(self.verkaeufer_ev.ende, date(2025, 12, 11))
        # Nachhol-Sollstellungen für die abgelaufenen Monate.
        self.assertGreater(
            HausgeldSollstellung.objects.filter(eigentumsverhaeltnis=kaeufer_ev).count(),
            0,
        )

    def test_vorgang_wird_als_freigegeben_gespeichert(self):
        """
        Der Commit ist die Ausführung. Bleibt der Vorgang auf 'vorschau', fehlt
        er im Hinweis-Banner der Jahresabrechnung — dort wird auf 'freigegeben'
        gefiltert, und einen Freigabeschritt für Wechsel gibt es nicht.
        """
        from apps.buchhaltung.models import EigentuemerwechselVorgang
        from apps.buchhaltung.services.jahresabrechnung.wizard_service import (
            eigentuemerwechsel_im_wj,
        )

        resp = self._abschliessen(self._prozess({'.900': '132.42'}))
        self.assertEqual(resp.status_code, 200, getattr(resp, 'data', None))

        vorgang = EigentuemerwechselVorgang.objects.get(id=resp.data['wechsel_id'])
        self.assertEqual(vorgang.status, 'freigegeben')
        self.assertIsNotNone(vorgang.freigegeben_am)
        self.assertIsNone(vorgang.freigegeben_von, 'Vier-Augen-Constraint erlaubt nur NULL')

        wj = Wirtschaftsjahr.objects.get(objekt=self.objekt, jahr=2026)
        treffer = eigentuemerwechsel_im_wj(self.objekt, wj)
        self.assertEqual([t['einheit_nr'] for t in treffer], ['W11'])
