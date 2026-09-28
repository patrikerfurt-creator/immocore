"""
Tests für den Katalog ``Versammlungsort`` (Spec v1.1 Kap. 1).

Deckt ab:
  - Modell: Deaktivieren statt Löschen (PROTECT-Referenz aus einer EV)
  - API: CRUD ohne destroy, Authentifizierung
  - Eigentuemerversammlung.versammlungsort ist optional und beeinflusst
    ``ort`` NICHT automatisch
"""
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.versammlung.models import Eigentuemerversammlung, Versammlungsort
from apps.versammlung.services import ev_service
from apps.versammlung.tests import factories as f

VERSAMMLUNGSORTE = '/api/v1/versammlungsorte/'
VERSAMMLUNGEN = '/api/v1/versammlungen/'


class VersammlungsortModelTest(TestCase):
    def test_str_ist_bezeichnung(self):
        ort = Versammlungsort.objects.create(bezeichnung='Gemeinschaftsraum EG')
        self.assertEqual(str(ort), 'Gemeinschaftsraum EG')

    def test_aktiv_ist_default_true(self):
        ort = Versammlungsort.objects.create(bezeichnung='Saal')
        self.assertTrue(ort.aktiv)

    def test_protect_verhindert_loeschen_bei_referenz(self):
        ort = Versammlungsort.objects.create(bezeichnung='Vereinsheim')
        user = f.user()
        ev = Eigentuemerversammlung.objects.create(
            objekt=f.objekt(), erstellt_von=user, versammlungsort=ort,
        )
        with self.assertRaises(Exception):
            ort.delete()
        ev.refresh_from_db()
        self.assertEqual(ev.versammlungsort_id, ort.id)


class VersammlungsortApiTest(APITestCase):
    def setUp(self):
        self.user = f.user()
        self.client.force_authenticate(self.user)

    def test_ohne_login_kein_zugriff(self):
        self.client.force_authenticate(None)
        response = self.client.get(VERSAMMLUNGSORTE)
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_anlage_und_liste(self):
        response = self.client.post(VERSAMMLUNGSORTE, {
            'bezeichnung': 'Gemeinschaftsraum EG',
            'strasse': 'Teststraße 1', 'plz': '12345', 'ort_text': 'Teststadt',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        liste = self.client.get(VERSAMMLUNGSORTE)
        self.assertEqual(len(liste.data['results'] if 'results' in liste.data else liste.data), 1)

    def test_deaktivieren_statt_loeschen(self):
        ort = Versammlungsort.objects.create(bezeichnung='Saal A')
        response = self.client.patch(
            f'{VERSAMMLUNGSORTE}{ort.id}/', {'aktiv': False}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        ort.refresh_from_db()
        self.assertFalse(ort.aktiv)

    def test_kein_destroy(self):
        ort = Versammlungsort.objects.create(bezeichnung='Saal B')
        response = self.client.delete(f'{VERSAMMLUNGSORTE}{ort.id}/')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class VersammlungsortVorbelegungApiTest(APITestCase):
    """``versammlungsort`` befüllt ``ort`` NICHT automatisch (Spec Kap. 1)."""

    def setUp(self):
        self.user = f.user()
        self.client.force_authenticate(self.user)
        self.objekt = f.objekt()
        self.ort = Versammlungsort.objects.create(
            bezeichnung='Gemeinschaftsraum EG', strasse='Teststraße 1',
            plz='12345', ort_text='Teststadt',
        )
        self.ev = ev_service.erstelle_ev(objekt=self.objekt, erstellt_von=self.user)

    def test_versammlungsort_setzen_aendert_ort_nicht(self):
        response = self.client.patch(f'{VERSAMMLUNGEN}{self.ev.id}/', {
            'versammlungsort': str(self.ort.id),
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.versammlungsort_id, self.ort.id)
        self.assertEqual(self.ev.ort, '')

    def test_ort_bleibt_frei_aenderbar_nach_versammlungsort(self):
        self.client.patch(f'{VERSAMMLUNGEN}{self.ev.id}/', {
            'versammlungsort': str(self.ort.id), 'ort': 'Wie im Katalog, Raum 2',
        }, format='json')
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.ort, 'Wie im Katalog, Raum 2')
