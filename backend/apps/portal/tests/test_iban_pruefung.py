"""
Tests für die IBAN-Prüfung im Portal (Eingabehilfe + Speicherprüfung).

Der Prüf-Endpunkt liegt bewusst hinter der Portal-Sitzung: anonym wäre er
ein IBAN-/Bankleitzahl-Orakel, das jeder abfragen könnte.
"""
from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.portal.services import zugang_service
from .basis import erstelle_eigentuemer, erstelle_mandat

IBAN_CHECK_URL = '/api/v1/portal/iban-check/'
BANK_URL = '/api/v1/portal/meine-daten/bankverbindung/'

GUELTIGE_IBAN = 'DE89370400440532013000'


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class IbanPruefEndpunktTest(APITestCase):
    def setUp(self):
        cache.clear()
        self.person = erstelle_eigentuemer()
        self.zugang, token = zugang_service.lade_ein(self.person)
        self.session, _ = zugang_service.melde_an(token.token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Portal {self.session.token}')

    def test_gueltige_iban_wird_bestaetigt(self):
        response = self.client.get(IBAN_CHECK_URL, {'iban': GUELTIGE_IBAN})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['valid'])
        self.assertEqual(response.data['iban'], GUELTIGE_IBAN)

    def test_leerzeichen_werden_toleriert(self):
        response = self.client.get(IBAN_CHECK_URL, {'iban': 'DE89 3704 0044 0532 0130 00'})
        self.assertTrue(response.data['valid'])

    def test_ungueltige_pruefsumme_wird_erkannt(self):
        response = self.client.get(IBAN_CHECK_URL, {'iban': 'DE89370400440532013001'})
        self.assertFalse(response.data['valid'])

    def test_unsinn_wird_erkannt(self):
        response = self.client.get(IBAN_CHECK_URL, {'iban': 'NICHTEINEIBAN'})
        self.assertFalse(response.data['valid'])

    def test_leere_eingabe(self):
        response = self.client.get(IBAN_CHECK_URL, {'iban': ''})
        self.assertFalse(response.data['valid'])

    def test_fehlermeldung_ist_deutsch_und_ohne_technikjargon(self):
        response = self.client.get(IBAN_CHECK_URL, {'iban': 'DE00000000000000000000'})
        self.assertFalse(response.data['valid'])
        self.assertEqual(response.data['error'], 'Diese IBAN ist ungültig.')

    def test_ohne_portal_sitzung_kein_zugriff(self):
        self.client.credentials()
        response = self.client.get(IBAN_CHECK_URL, {'iban': GUELTIGE_IBAN})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_endpunkt_veraendert_nichts(self):
        """Reine Eingabehilfe — die Bankverbindung bleibt unangetastet."""
        mandat = erstelle_mandat(self.person)
        alte_iban = mandat.iban

        self.client.get(IBAN_CHECK_URL, {'iban': GUELTIGE_IBAN})

        mandat.refresh_from_db()
        self.person.refresh_from_db()
        self.assertEqual(mandat.iban, alte_iban)
        self.assertEqual(self.person.ibans, [alte_iban])


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class IbanPruefungBeimSpeichernTest(APITestCase):
    """Die Eingabehilfe ist unverbindlich — beim Speichern wird erneut
    geprüft, damit ein manipulierter Client keine Müll-IBAN ins
    Lastschriftmandat schreiben kann."""

    def setUp(self):
        cache.clear()
        self.person = erstelle_eigentuemer()
        self.mandat = erstelle_mandat(self.person)
        self.zugang, token = zugang_service.lade_ein(self.person)
        session, _ = zugang_service.melde_an(token.token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Portal {session.token}')

    def test_falsche_pruefsumme_wird_beim_speichern_abgelehnt(self):
        alt = self.mandat.iban
        response = self.client.patch(BANK_URL, {'iban': 'DE89370400440532013001'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.mandat.refresh_from_db()
        self.assertEqual(self.mandat.iban, alt)

    def test_zu_kurze_iban_wird_abgelehnt(self):
        response = self.client.patch(BANK_URL, {'iban': 'DE89'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_gueltige_iban_wird_gespeichert(self):
        response = self.client.patch(BANK_URL, {'iban': GUELTIGE_IBAN})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.mandat.refresh_from_db()
        self.assertEqual(self.mandat.iban, GUELTIGE_IBAN)
