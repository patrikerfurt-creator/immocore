"""
Tests für ``apps.vorgaenge.tasks.erzeuge_antwort_vorschlag`` (Folgeauftrag
KI-Antwortvorschlag, asynchrone Auslösung bei Vorgangsanlage).

Der Anthropic-Client wird gemockt — kein echter API-Call.
"""
import uuid
from datetime import date
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.objekte.models import Objekt
from apps.vorgaenge.models import VorgangAntwortVorschlag, VorgangTyp
from apps.vorgaenge.services import vorgang_service
from apps.vorgaenge.tasks import erzeuge_antwort_vorschlag

User = get_user_model()


def _objekt(nr="TT001"):
    return Objekt.objects.create(
        bezeichnung="Test-WEG Task", objektnummer=nr, objekt_typ="weg",
        ort="Teststadt", verwaltung_seit=date(2020, 1, 1),
    )


def _user(username="antwort-task-tester"):
    return User.objects.create_user(username=username, password="x")


def _typ(code="anfrage"):
    return VorgangTyp.objects.get(code=code)


def _mock_anthropic_response(text="Sehr geehrte Damen und Herren,\n\nvielen Dank.\n\nMit freundlichen Grüßen"):
    block = MagicMock()
    block.type = "text"
    block.text = text
    message = MagicMock()
    message.content = [block]
    return message


class ErzeugeAntwortVorschlagTaskTest(TestCase):
    def setUp(self):
        self.objekt = _objekt()
        self.user = _user()
        self.vorgang = vorgang_service.erstelle_vorgang(
            typ=_typ(), betreff="Test", erstellt_von=self.user, objekt=self.objekt,
        )

    @patch("anthropic.Anthropic")
    def test_task_erzeugt_vorschlag_fuer_bestehenden_vorgang(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response()
        mock_anthropic_cls.return_value = mock_client

        with self.settings(ANTHROPIC_API_KEY="dummy-key"):
            erzeuge_antwort_vorschlag(str(self.vorgang.id))

        self.assertTrue(
            VorgangAntwortVorschlag.objects.filter(vorgang=self.vorgang, status="entwurf").exists()
        )

    def test_task_bei_geloeschtem_vorgang_bricht_nicht_ab(self):
        unbekannte_id = str(uuid.uuid4())
        # Darf keine Exception werfen.
        erzeuge_antwort_vorschlag(unbekannte_id)

    @patch(
        "apps.vorgaenge.services.antwort_vorschlag_service.erzeuge_vorschlag",
        side_effect=RuntimeError("Unerwarteter Fehler"),
    )
    def test_task_faengt_unerwarteten_fehler_ab(self, mock_erzeuge):
        # Darf keine Exception nach außen werfen — der Vorgang selbst bleibt
        # davon unberührt.
        erzeuge_antwort_vorschlag(str(self.vorgang.id))
        self.vorgang.refresh_from_db()
        self.assertEqual(self.vorgang.betreff, "Test")
