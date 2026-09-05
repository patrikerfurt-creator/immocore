"""
Tests für Einladung, Magic-Link-Login und Sitzung (Spec 1a, Kap. 3 und 8).

Schwerpunkt sind die drei Akzeptanzkriterien aus Kap. 8:
  - Einladungslink genau einmal verwendbar
  - abgelaufene/verwendete Magic Links werden abgelehnt
  - keine Auskunft darüber, ob eine E-Mail-Adresse existiert
"""
from datetime import timedelta

from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.portal.models import PortalSession, PortalToken, PortalZugang
from apps.portal.services import zugang_service
from .basis import erstelle_eigentuemer

REQUEST_URL = '/api/v1/portal/auth/magic-link/request/'
VERIFY_URL = '/api/v1/portal/auth/magic-link/verify/'


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class MagicLinkAnfrageTest(APITestCase):
    def setUp(self):
        cache.clear()
        mail.outbox.clear()
        self.person = erstelle_eigentuemer(email='login@example.org')
        self.zugang, _ = zugang_service.lade_ein(self.person)

    def test_versendet_magic_link_an_bekannte_adresse(self):
        response = self.client.post(REQUEST_URL, {'email': 'login@example.org'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(
            PortalToken.objects.filter(
                zugang=self.zugang, typ=PortalToken.TYP_MAGIC,
            ).exists()
        )

    def test_unbekannte_adresse_liefert_identische_antwort_ohne_mail(self):
        """Enumeration-Schutz (Spec Kap. 3.2) — der wichtigste Test hier."""
        bekannt = self.client.post(REQUEST_URL, {'email': 'login@example.org'})
        mail.outbox.clear()
        unbekannt = self.client.post(REQUEST_URL, {'email': 'gibtsnicht@example.org'})

        self.assertEqual(unbekannt.status_code, bekannt.status_code)
        self.assertEqual(unbekannt.data, bekannt.data)
        self.assertEqual(len(mail.outbox), 0)

    def test_gesperrter_zugang_bekommt_keinen_link_aber_gleiche_antwort(self):
        self.zugang.aktiv = False
        self.zugang.save(update_fields=['aktiv'])
        mail.outbox.clear()

        response = self.client.post(REQUEST_URL, {'email': 'login@example.org'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)

    def test_neue_anfrage_entwertet_den_vorherigen_magic_link(self):
        self.client.post(REQUEST_URL, {'email': 'login@example.org'})
        erster = PortalToken.objects.filter(typ=PortalToken.TYP_MAGIC).first()

        self.client.post(REQUEST_URL, {'email': 'login@example.org'})
        erster.refresh_from_db()
        self.assertIsNotNone(
            erster.verbraucht_am,
            'Ein älterer Magic Link muss beim Nachfordern entwertet werden.',
        )

    def test_rate_limit_fuenf_pro_stunde(self):
        """Spec Kap. 3.3 — ab der sechsten Anfrage geht keine Mail mehr raus,
        die Antwort bleibt aber unverändert neutral."""
        for _ in range(zugang_service.MAGIC_LINK_MAX_PRO_STUNDE):
            self.client.post(REQUEST_URL, {'email': 'login@example.org'})
        self.assertEqual(len(mail.outbox), zugang_service.MAGIC_LINK_MAX_PRO_STUNDE)

        response = self.client.post(REQUEST_URL, {'email': 'login@example.org'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            len(mail.outbox), zugang_service.MAGIC_LINK_MAX_PRO_STUNDE,
            'Nach dem Limit darf keine weitere Mail versendet werden.',
        )


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class TokenEinloesenTest(APITestCase):
    def setUp(self):
        cache.clear()
        mail.outbox.clear()
        self.person = erstelle_eigentuemer(email='login@example.org')
        self.zugang, self.einladung = zugang_service.lade_ein(self.person)

    def test_einladung_loggt_ein_und_setzt_erstaktivierung(self):
        response = self.client.post(VERIFY_URL, {'token': self.einladung.token})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['erstanmeldung'])
        self.assertTrue(PortalSession.objects.filter(token=response.data['token']).exists())

        self.zugang.refresh_from_db()
        self.assertIsNotNone(self.zugang.erstaktivierung_am)
        self.assertIsNotNone(self.zugang.letzter_login)

    def test_einladungslink_ist_genau_einmal_verwendbar(self):
        """Akzeptanzkriterium Kap. 8, Punkt 1."""
        erste = self.client.post(VERIFY_URL, {'token': self.einladung.token})
        self.assertEqual(erste.status_code, status.HTTP_200_OK)

        zweite = self.client.post(VERIFY_URL, {'token': self.einladung.token})
        self.assertEqual(zweite.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(PortalSession.objects.count(), 1)

    def test_abgelaufener_token_wird_abgelehnt(self):
        self.einladung.gueltig_bis = timezone.now() - timedelta(minutes=1)
        self.einladung.save(update_fields=['gueltig_bis'])

        response = self.client.post(VERIFY_URL, {'token': self.einladung.token})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(PortalSession.objects.exists())

    def test_unbekannter_token_wird_abgelehnt(self):
        response = self.client.post(VERIFY_URL, {'token': 'voellig-erfunden'})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_gesperrter_zugang_kann_sich_nicht_anmelden(self):
        self.zugang.aktiv = False
        self.zugang.save(update_fields=['aktiv'])

        response = self.client.post(VERIFY_URL, {'token': self.einladung.token})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_zweite_einladung_legt_keinen_zweiten_zugang_an(self):
        zugang2, token2 = zugang_service.lade_ein(self.person)
        self.assertEqual(PortalZugang.objects.count(), 1)
        self.assertEqual(zugang2.pk, self.zugang.pk)

        self.einladung.refresh_from_db()
        self.assertIsNotNone(
            self.einladung.verbraucht_am,
            'Die alte Einladung muss beim Nachfordern entwertet werden.',
        )
        self.assertNotEqual(token2.token, self.einladung.token)

    def test_magic_link_aktiviert_zugang_ebenfalls(self):
        """Verfaellt der Einladungslink, aktiviert der erste Magic-Link-Login.

        Sonst stuende ein nachweislich genutzter Zugang in der Verwaltung
        dauerhaft als "eingeladen — noch nicht aktiviert".
        """
        self.einladung.gueltig_bis = timezone.now() - timedelta(hours=1)
        self.einladung.save(update_fields=['gueltig_bis'])
        magic = zugang_service.erzeuge_magic_link(self.zugang)

        response = self.client.post(VERIFY_URL, {'token': magic.token})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['erstanmeldung'])
        self.zugang.refresh_from_db()
        self.assertIsNotNone(self.zugang.erstaktivierung_am)
        self.assertEqual(self.zugang.status, 'aktiv')

    def test_zweiter_magic_link_login_ist_keine_erstanmeldung(self):
        erster = zugang_service.erzeuge_magic_link(self.zugang)
        self.client.post(VERIFY_URL, {'token': erster.token})
        self.zugang.refresh_from_db()
        aktivierung = self.zugang.erstaktivierung_am

        zweiter = zugang_service.erzeuge_magic_link(self.zugang)
        response = self.client.post(VERIFY_URL, {'token': zweiter.token})

        self.assertFalse(response.data['erstanmeldung'])
        self.zugang.refresh_from_db()
        self.assertEqual(self.zugang.erstaktivierung_am, aktivierung)

    def test_erneute_einladung_setzt_erstaktivierung_nicht_zurueck(self):
        self.client.post(VERIFY_URL, {'token': self.einladung.token})
        self.zugang.refresh_from_db()
        aktivierung = self.zugang.erstaktivierung_am

        _, neuer_token = zugang_service.lade_ein(self.person)
        self.client.post(VERIFY_URL, {'token': neuer_token.token})

        self.zugang.refresh_from_db()
        self.assertEqual(self.zugang.erstaktivierung_am, aktivierung)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class SitzungTest(APITestCase):
    def setUp(self):
        cache.clear()
        self.person = erstelle_eigentuemer(email='login@example.org')
        self.zugang, token = zugang_service.lade_ein(self.person)
        self.session, _, _ = zugang_service.melde_an(token.token)

    def _auth(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Portal {self.session.token}')

    def test_gueltige_sitzung_erreicht_geschuetzten_endpunkt(self):
        self._auth()
        response = self.client.get('/api/v1/portal/meine-daten/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_ohne_token_kein_zugriff(self):
        response = self.client.get('/api/v1/portal/meine-daten/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_abgelaufene_sitzung_wird_abgelehnt(self):
        self.session.gueltig_bis = timezone.now() - timedelta(minutes=1)
        self.session.save(update_fields=['gueltig_bis'])
        self._auth()

        response = self.client.get('/api/v1/portal/meine-daten/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_sperren_des_zugangs_wirkt_sofort_auf_laufende_sitzung(self):
        self.zugang.aktiv = False
        self.zugang.save(update_fields=['aktiv'])
        self._auth()

        response = self.client.get('/api/v1/portal/meine-daten/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_bearer_schema_wird_nicht_als_portal_token_akzeptiert(self):
        """Ein Portal-Token darf nicht in die Mitarbeiter-JWT-Kette rutschen."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.session.token}')
        response = self.client.get('/api/v1/portal/meine-daten/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_beendet_die_sitzung(self):
        self._auth()
        response = self.client.post('/api/v1/portal/auth/logout/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        folge = self.client.get('/api/v1/portal/meine-daten/')
        self.assertEqual(folge.status_code, status.HTTP_401_UNAUTHORIZED)
