"""
Tests für die Einheiten-Ansicht (Spec 1a, Kap. 6.1) und — der wichtigste
Test dieser Spec — die Datenisolation zwischen zwei Eigentümern
(Akzeptanzkriterium Kap. 8, letzter Punkt).
"""
from datetime import date

from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.portal.services import zugang_service
from .basis import (
    erstelle_eigentuemer,
    erstelle_einheit,
    erstelle_objekt,
    verknuepfe,
)

EINHEITEN_URL = '/api/v1/portal/meine-einheiten/'
DATEN_URL = '/api/v1/portal/meine-daten/'


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class MeineEinheitenTest(APITestCase):
    def setUp(self):
        cache.clear()
        self.person = erstelle_eigentuemer()

        self.weg_a = erstelle_objekt('PORTAL-A', 'WEG Portalweg 1')
        self.einheit_a1 = erstelle_einheit(self.weg_a, '0001', 'EG links', mea='125.5000')
        self.einheit_a2 = erstelle_einheit(self.weg_a, '0002', 'OG rechts', mea='98.0000')
        self.weg_b = erstelle_objekt('PORTAL-B', 'WEG Zweitstraße 7')
        self.einheit_b1 = erstelle_einheit(self.weg_b, '0001', 'DG')

        for einheit in (self.einheit_a1, self.einheit_a2, self.einheit_b1):
            verknuepfe(self.person, einheit)

        self.zugang, token = zugang_service.lade_ein(self.person)
        session, _, _ = zugang_service.melde_an(token.token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Portal {session.token}')

    def test_liefert_eine_karte_je_weg(self):
        response = self.client.get(EINHEITEN_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

        bezeichnungen = {karte['bezeichnung'] for karte in response.data}
        self.assertEqual(bezeichnungen, {'WEG Portalweg 1', 'WEG Zweitstraße 7'})

    def test_einheiten_sind_der_richtigen_weg_zugeordnet(self):
        response = self.client.get(EINHEITEN_URL)
        karten = {k['bezeichnung']: k for k in response.data}

        self.assertEqual(len(karten['WEG Portalweg 1']['einheiten']), 2)
        self.assertEqual(len(karten['WEG Zweitstraße 7']['einheiten']), 1)

    def test_liefert_stammdaten_inklusive_mea_und_nutzungsart(self):
        response = self.client.get(EINHEITEN_URL)
        karten = {k['bezeichnung']: k for k in response.data}
        einheit = karten['WEG Portalweg 1']['einheiten'][0]

        self.assertEqual(einheit['einheit_nr'], '0001')
        self.assertEqual(einheit['lage'], 'EG links')
        self.assertEqual(einheit['nutzungsart'], 'Wohnung')
        self.assertEqual(str(einheit['miteigentumsanteil']), '125.5000')

    def test_einheit_ohne_mea_liefert_null_statt_fehler(self):
        response = self.client.get(EINHEITEN_URL)
        karten = {k['bezeichnung']: k for k in response.data}
        self.assertIsNone(karten['WEG Zweitstraße 7']['einheiten'][0]['miteigentumsanteil'])

    def test_kein_saldo_und_keine_buchungen_in_der_antwort(self):
        """Spec Kap. 6.1 — Mini-Version zeigt ausschließlich Stammdaten."""
        response = self.client.get(EINHEITEN_URL)
        einheit = response.data[0]['einheiten'][0]
        for verbotenes_feld in ('saldo', 'buchungen', 'personenkonto', 'sollstellungen'):
            self.assertNotIn(verbotenes_feld, einheit)

    def test_beendetes_eigentumsverhaeltnis_wird_nicht_mehr_angezeigt(self):
        weg_alt = erstelle_objekt('PORTAL-ALT', 'WEG Verkauft 3')
        einheit_alt = erstelle_einheit(weg_alt, '0001', 'Verkauft')
        verknuepfe(
            self.person, einheit_alt,
            beginn=date(2018, 1, 1), ende=date(2020, 12, 31),
        )

        response = self.client.get(EINHEITEN_URL)
        bezeichnungen = {karte['bezeichnung'] for karte in response.data}
        self.assertNotIn('WEG Verkauft 3', bezeichnungen)

    def test_ohne_sitzung_kein_zugriff(self):
        self.client.credentials()
        response = self.client.get(EINHEITEN_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class DatenisolationTest(APITestCase):
    """Zwei Eigentümer, Stichprobe über alle Endpunkte (Kap. 8, letzter Punkt).

    Kein Endpunkt darf Daten einer anderen Person als der des Sitzungs-
    Tokens liefern — auch dann nicht, wenn der Client eine fremde ID
    mitschickt.
    """

    def setUp(self):
        cache.clear()

        self.person_a = erstelle_eigentuemer(
            nachname='Ampel', email='a@example.org', personennummer='P-A',
            strasse='A-Straße', hausnummer='1', telefon='0111 111',
        )
        self.person_b = erstelle_eigentuemer(
            nachname='Bemme', email='b@example.org', personennummer='P-B',
            strasse='B-Straße', hausnummer='2', telefon='0222 222',
        )

        self.weg_a = erstelle_objekt('ISO-A', 'WEG Alpha')
        self.weg_b = erstelle_objekt('ISO-B', 'WEG Beta')
        self.einheit_a = erstelle_einheit(self.weg_a, '0001', 'Wohnung A')
        self.einheit_b = erstelle_einheit(self.weg_b, '0001', 'Wohnung B')
        verknuepfe(self.person_a, self.einheit_a)
        verknuepfe(self.person_b, self.einheit_b)

        _, token_a = zugang_service.lade_ein(self.person_a)
        self.session_a, _, _ = zugang_service.melde_an(token_a.token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Portal {self.session_a.token}')

    def test_einheiten_zeigen_nur_die_eigene_weg(self):
        response = self.client.get(EINHEITEN_URL)
        bezeichnungen = {karte['bezeichnung'] for karte in response.data}
        self.assertEqual(bezeichnungen, {'WEG Alpha'})

    def test_stammdaten_sind_die_der_eigenen_person(self):
        response = self.client.get(DATEN_URL)
        self.assertEqual(response.data['personennummer'], 'P-A')
        self.assertEqual(response.data['email'], 'a@example.org')

    def test_mitgeschickte_fremde_person_id_wird_ignoriert(self):
        response = self.client.get(DATEN_URL, {'person': str(self.person_b.id)})
        self.assertEqual(response.data['personennummer'], 'P-A')

    def test_patch_mit_fremder_person_id_aendert_die_eigene_person(self):
        """Der Client darf über eine mitgeschickte ID keine fremden
        Stammdaten umschreiben."""
        self.client.patch(DATEN_URL, {
            'person': str(self.person_b.id),
            'person_id': str(self.person_b.id),
            'strasse': 'Fremdzugriff',
        })

        self.person_a.refresh_from_db()
        self.person_b.refresh_from_db()
        self.assertEqual(self.person_a.strasse, 'Fremdzugriff')
        self.assertEqual(self.person_b.strasse, 'B-Straße')

    def test_bankverbindung_mit_fremder_person_id_trifft_die_eigene_person(self):
        self.client.patch('/api/v1/portal/meine-daten/bankverbindung/', {
            'person_id': str(self.person_b.id),
            'iban': 'DE89370400440532013000',
        })

        self.person_a.refresh_from_db()
        self.person_b.refresh_from_db()
        self.assertEqual(self.person_a.ibans[0], 'DE89370400440532013000')
        self.assertEqual(self.person_b.ibans, [])
