"""
Tests für ``auftrag_service.versende_erneut`` (Phase B, Orchestrator-Vorgabe
Schritt 2/5; erweitert in der Phase-D-Abnahme um den Status ``entwurf``).

Deckt ab:
  - nur aus 'entwurf' (nach Versandfehler) oder 'versendet' zulässig, sonst
    ValidationError (z.B. 'in_arbeit', 'abgeschlossen', 'storniert')
  - erneuter Versand aus 'entwurf' (Auftrag mit vorangegangenem Versandfehler
    hängt sonst dauerhaft unversendbar fest) löst den Versandtask aus
  - Mailversand-Task wird erst NACH Commit erneut ausgelöst
"""
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.handwerker.models import Handwerkerauftrag
from apps.handwerker.services import auftrag_service
from apps.objekte.models import Objekt
from apps.rechnungen.models import Kreditor

User = get_user_model()


def _objekt(nr="H700"):
    return Objekt.objects.create(
        bezeichnung="Test-WEG Erneuter Versand", objektnummer=nr, objekt_typ="weg",
        ort="Teststadt", verwaltung_seit=date(2020, 1, 1), bundesland="HE",
    )


def _kreditor():
    return Kreditor.objects.create(
        name="Meister Sanitär GmbH", ist_handwerker=True, email="meister@example.de",
    )


def _user():
    return User.objects.create_user(username="erneut-tester", password="x")


class VersendeErneutTest(TestCase):
    def setUp(self):
        self.user = _user()
        self.objekt = _objekt()
        self.kreditor = _kreditor()

    def _auftrag(self, status):
        return Handwerkerauftrag.objects.create(
            objekt=self.objekt, kreditor=self.kreditor, titel="Testauftrag",
            erstellt_von=self.user, status=status,
        )

    def test_aus_in_arbeit_nicht_erlaubt(self):
        auftrag = self._auftrag("in_arbeit")
        with self.assertRaises(ValidationError):
            auftrag_service.versende_erneut(auftrag, self.user)

    def test_aus_storniert_nicht_erlaubt(self):
        auftrag = self._auftrag("storniert")
        with self.assertRaises(ValidationError):
            auftrag_service.versende_erneut(auftrag, self.user)

    def test_aus_abgeschlossen_nicht_erlaubt(self):
        auftrag = self._auftrag("abgeschlossen")
        with self.assertRaises(ValidationError):
            auftrag_service.versende_erneut(auftrag, self.user)

    @patch("apps.handwerker.tasks.versende_auftragsmail.delay")
    def test_aus_entwurf_nach_versandfehler_erneut_versendbar(self, mock_delay):
        """Auftrag hängt nach einem fehlgeschlagenen ERSTEN Versand in
        'entwurf' — ohne diese Erweiterung gäbe es keinen Weg mehr, den
        Versand erneut auszulösen (Phase-D-Abnahme, Fehler 2)."""
        auftrag = self._auftrag("entwurf")
        auftrag_service.protokolliere_versandfehler(auftrag, "SMTP nicht erreichbar")

        with self.captureOnCommitCallbacks(execute=True):
            ergebnis = auftrag_service.versende_erneut(auftrag, self.user)

        self.assertEqual(ergebnis.status, "entwurf")
        mock_delay.assert_called_once_with(str(auftrag.id))

    @patch("apps.handwerker.tasks.versende_auftragsmail.delay")
    def test_aus_versendet_erneut_versendbar_mit_kommentar_ereignis(self, mock_delay):
        auftrag = self._auftrag("versendet")

        with self.captureOnCommitCallbacks(execute=True):
            ergebnis = auftrag_service.versende_erneut(auftrag, self.user)

        self.assertEqual(ergebnis.status, "versendet")
        self.assertEqual(auftrag.ereignisse.filter(typ="kommentar").count(), 1)
        mock_delay.assert_called_once_with(str(auftrag.id))

    @patch("apps.handwerker.tasks.versende_auftragsmail.delay")
    def test_mailversand_erst_nach_commit(self, mock_delay):
        auftrag = self._auftrag("versendet")

        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            auftrag_service.versende_erneut(auftrag, self.user)
            mock_delay.assert_not_called()
        self.assertEqual(len(callbacks), 1)
