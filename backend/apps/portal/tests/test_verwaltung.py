"""
Tests für den internen Bereich „Portal-Zugang einladen" (Spec 1a, Kap. 3.1).
"""
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.mitarbeiter.models import Mitarbeiter
from apps.personen.models import Person
from apps.portal.models import PortalSession, PortalToken, PortalZugang
from apps.portal.services import zugang_service
from .basis import erstelle_eigentuemer

EINLADEN_URL = '/api/v1/portal-verwaltung/zugaenge/einladen/'
LISTE_URL = '/api/v1/portal-verwaltung/zugaenge/'

User = get_user_model()


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PortalZugangVerwaltungTest(APITestCase):
    def setUp(self):
        cache.clear()
        mail.outbox.clear()
        self.user = User.objects.create_user(
            username='sachbearbeiterin', first_name='Sabine', last_name='Sachbearbeit',
        )
        self.mitarbeiter = Mitarbeiter.objects.create(
            user=self.user, abteilungen=['objektmanagement'],
        )
        self.client.force_authenticate(user=self.user)
        self.person = erstelle_eigentuemer(email='eig@example.org')

    def test_einladen_legt_zugang_an_und_versendet_mail(self):
        response = self.client.post(EINLADEN_URL, {'person_id': str(self.person.id)})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(PortalZugang.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['eig@example.org'])

        zugang = PortalZugang.objects.get()
        self.assertEqual(zugang.eingeladen_von, self.mitarbeiter)
        self.assertEqual(zugang.status, 'eingeladen')

    def test_einladungsmail_enthaelt_den_link(self):
        self.client.post(EINLADEN_URL, {'person_id': str(self.person.id)})
        token = PortalToken.objects.get(typ=PortalToken.TYP_EINLADUNG)
        self.assertIn(token.token, mail.outbox[0].body)

    def test_nur_eigentuemer_bekommen_einen_zugang(self):
        mieter = Person.objects.create(
            personennummer='P-MIETER', person_typ='200', nachname='Mieter',
            email='mieter@example.org', emails=['mieter@example.org'],
        )
        response = self.client.post(EINLADEN_URL, {'person_id': str(mieter.id)})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(PortalZugang.objects.count(), 0)

    def test_person_ohne_email_kann_nicht_eingeladen_werden(self):
        ohne_mail = Person.objects.create(
            personennummer='P-OHNE', person_typ='100', nachname='Ohnemail',
        )
        response = self.client.post(EINLADEN_URL, {'person_id': str(ohne_mail.id)})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(len(mail.outbox), 0)

    def test_sperren_beendet_laufende_sitzungen(self):
        zugang, token = zugang_service.lade_ein(self.person)
        zugang_service.melde_an(token.token)
        self.assertEqual(PortalSession.objects.count(), 1)

        response = self.client.post(f'{LISTE_URL}{zugang.id}/sperren/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        zugang.refresh_from_db()
        self.assertFalse(zugang.aktiv)
        self.assertEqual(PortalSession.objects.count(), 0)

    def test_entsperren_reaktiviert_den_zugang(self):
        zugang, _ = zugang_service.lade_ein(self.person)
        zugang.aktiv = False
        zugang.save(update_fields=['aktiv'])

        self.client.post(f'{LISTE_URL}{zugang.id}/entsperren/')
        zugang.refresh_from_db()
        self.assertTrue(zugang.aktiv)

    def test_liste_ist_nach_person_filterbar(self):
        zugang_service.lade_ein(self.person)
        andere = erstelle_eigentuemer(
            nachname='Andere', email='andere@example.org', personennummer='P-ANDERE',
        )
        zugang_service.lade_ein(andere)

        response = self.client.get(LISTE_URL, {'person': str(self.person.id)})
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['person_id'], str(self.person.id))

    def test_ohne_login_kein_zugriff(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(EINLADEN_URL, {'person_id': str(self.person.id)})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_portal_token_erreicht_den_internen_bereich_nicht(self):
        """Ein Eigentümer darf sich nicht selbst weitere Zugänge anlegen."""
        _, token = zugang_service.lade_ein(self.person)
        session, _, _ = zugang_service.melde_an(token.token)

        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=f'Portal {session.token}')
        response = self.client.get(LISTE_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
