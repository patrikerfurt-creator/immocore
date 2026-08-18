"""
Tests für ``auftrag_service.akzeptiere_via_token`` /
``auftrag_service.lehne_ab_via_token`` (Phase B, Orchestrator-Vorgabe
Schritt 2/5).

Deckt ab:
  - Annahme setzt Status 'angenommen' + verbraucht_am + genau ein Ereignis
  - zweite Verwendung desselben Tokens -> TokenVerbraucht
  - abgelaufener Token -> TokenAbgelaufen
  - Ablehnung speichert den Grund und setzt Status 'abgelehnt'
  - interne Benachrichtigung wird erst NACH Commit ausgelöst
"""
from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.handwerker.models import AuftragsbestaetigungsToken, Handwerkerauftrag
from apps.handwerker.services import auftrag_service
from apps.objekte.models import Objekt
from apps.rechnungen.models import Kreditor

User = get_user_model()


def _objekt(nr="H600"):
    return Objekt.objects.create(
        bezeichnung="Test-WEG Token", objektnummer=nr, objekt_typ="weg",
        ort="Teststadt", verwaltung_seit=date(2020, 1, 1), bundesland="HE",
    )


def _kreditor():
    return Kreditor.objects.create(
        name="Meister Sanitär GmbH", ist_handwerker=True, email="meister@example.de",
    )


def _user():
    return User.objects.create_user(username="token-tester", password="x")


class AkzeptiereViaTokenTest(TestCase):
    def setUp(self):
        self.user = _user()
        self.objekt = _objekt()
        self.kreditor = _kreditor()
        self.auftrag = Handwerkerauftrag.objects.create(
            objekt=self.objekt, kreditor=self.kreditor, titel="Testauftrag",
            erstellt_von=self.user, status="versendet",
        )
        self.token = AuftragsbestaetigungsToken.objects.create(auftrag=self.auftrag)

    def test_annahme_setzt_status_und_verbraucht_am_und_ereignis(self):
        auftrag = auftrag_service.akzeptiere_via_token(self.token.accept_token)
        auftrag.refresh_from_db()
        self.token.refresh_from_db()

        self.assertEqual(auftrag.status, "angenommen")
        self.assertIsNotNone(auftrag.angenommen_am)
        self.assertIsNotNone(self.token.verbraucht_am)
        self.assertEqual(auftrag.ereignisse.count(), 1)
        ereignis = auftrag.ereignisse.first()
        self.assertIsNone(ereignis.erstellt_von)
        self.assertIn("Token", ereignis.text)

    def test_zweite_verwendung_wird_abgewiesen(self):
        auftrag_service.akzeptiere_via_token(self.token.accept_token)
        with self.assertRaises(auftrag_service.TokenVerbraucht):
            auftrag_service.akzeptiere_via_token(self.token.accept_token)

    def test_abgelaufener_token_wird_abgewiesen(self):
        self.token.gueltig_bis = timezone.now() - timedelta(days=1)
        self.token.save(update_fields=["gueltig_bis"])
        with self.assertRaises(auftrag_service.TokenAbgelaufen):
            auftrag_service.akzeptiere_via_token(self.token.accept_token)
        self.auftrag.refresh_from_db()
        self.assertEqual(self.auftrag.status, "versendet")

    @patch("apps.handwerker.tasks.benachrichtige_intern.delay")
    def test_benachrichtigung_erst_nach_commit(self, mock_delay):
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            auftrag_service.akzeptiere_via_token(self.token.accept_token)
            mock_delay.assert_not_called()
        self.assertEqual(len(callbacks), 1)


class LehneAbViaTokenTest(TestCase):
    def setUp(self):
        self.user = _user()
        self.objekt = _objekt()
        self.kreditor = _kreditor()
        self.auftrag = Handwerkerauftrag.objects.create(
            objekt=self.objekt, kreditor=self.kreditor, titel="Testauftrag",
            erstellt_von=self.user, status="versendet",
        )
        self.token = AuftragsbestaetigungsToken.objects.create(auftrag=self.auftrag)

    def test_ablehnung_speichert_grund_und_status(self):
        auftrag = auftrag_service.lehne_ab_via_token(
            self.token.reject_token, grund="Keine Kapazität diese Woche.",
        )
        auftrag.refresh_from_db()
        self.token.refresh_from_db()

        self.assertEqual(auftrag.status, "abgelehnt")
        self.assertIsNotNone(auftrag.abgelehnt_am)
        self.assertEqual(auftrag.ablehnung_grund, "Keine Kapazität diese Woche.")
        self.assertIsNotNone(self.token.verbraucht_am)

    def test_zweite_verwendung_wird_abgewiesen(self):
        auftrag_service.lehne_ab_via_token(self.token.reject_token)
        with self.assertRaises(auftrag_service.TokenVerbraucht):
            auftrag_service.lehne_ab_via_token(self.token.reject_token)

    def test_abgelaufener_token_wird_abgewiesen(self):
        self.token.gueltig_bis = timezone.now() - timedelta(days=1)
        self.token.save(update_fields=["gueltig_bis"])
        with self.assertRaises(auftrag_service.TokenAbgelaufen):
            auftrag_service.lehne_ab_via_token(self.token.reject_token)
