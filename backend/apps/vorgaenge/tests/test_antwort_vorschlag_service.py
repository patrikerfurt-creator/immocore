"""
Tests für ``apps.vorgaenge.services.antwort_vorschlag_service`` (Folgeauftrag
KI-Antwortvorschlag).

WICHTIG: Der Anthropic-Client wird in JEDEM Test gemockt — niemals ein
echter API-Call in der Testsuite.

Deckt ab:
  - erzeuge_vorschlag: Erfolgsfall (status='entwurf', text_ki==text,
    VorgangEreignis 'antwort_vorschlag_erzeugt'), Prompt enthält
    Person-/Objekt-Kontext; System-Prompt verbietet Entwurfs-/KI-/
    Prüfhinweise im erzeugten Brieftext.
  - erzeuge_vorschlag: API-Fehler / kein Key -> status='fehlgeschlagen',
    kein Crash.
  - erzeuge_vorschlag: verwirft einen bestehenden Entwurf automatisch
    (Constraint: höchstens ein Entwurf je Vorgang).
  - bearbeite_vorschlag: text ändert sich, text_ki bleibt unverändert; nur
    im Status 'entwurf' erlaubt.
  - gib_frei: status='freigegeben', VorgangEreignis enthält den Text; nur aus
    'entwurf'; doppelte Freigabe -> Fehler.
  - verwirf: nur aus 'entwurf'.
"""
from datetime import date
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.objekte.models import Objekt
from apps.personen.models import Person
from apps.vorgaenge.models import VorgangAntwortVorschlag, VorgangEreignis, VorgangTyp
from apps.vorgaenge.services import antwort_vorschlag_service, vorgang_service

User = get_user_model()


def _objekt(nr="AV001"):
    return Objekt.objects.create(
        bezeichnung="Test-WEG Antwort-Vorschlag", objektnummer=nr, objekt_typ="weg",
        ort="Teststadt", verwaltung_seit=date(2020, 1, 1),
    )


def _user(username="antwort-vorschlag-tester"):
    return User.objects.create_user(username=username, password="x")


def _typ(code="anfrage"):
    return VorgangTyp.objects.get(code=code)


def _person(nachname="Musterfrau", person_typ="100"):
    return Person.objects.create(person_typ=person_typ, nachname=nachname, vorname="Erika")


def _mock_anthropic_response(text="Sehr geehrte Frau Musterfrau,\n\nvielen Dank für Ihre Anfrage.\n\nMit freundlichen Grüßen"):
    block = MagicMock()
    block.type = "text"
    block.text = text
    message = MagicMock()
    message.content = [block]
    return message


class ErzeugeVorschlagErfolgTest(TestCase):
    def setUp(self):
        self.objekt = _objekt()
        self.user = _user()
        self.person = _person()
        self.vorgang = vorgang_service.erstelle_vorgang(
            typ=_typ(), betreff="Frage zur Nebenkostenabrechnung",
            beschreibung="Bitte um Erläuterung der Position Hausmeister.",
            erstellt_von=self.user, objekt=self.objekt, person=self.person,
        )

    @patch("anthropic.Anthropic")
    def test_erfolgreiche_erzeugung_setzt_entwurf(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response()
        mock_anthropic_cls.return_value = mock_client

        with self.settings(ANTHROPIC_API_KEY="dummy-key"):
            vorschlag = antwort_vorschlag_service.erzeuge_vorschlag(self.vorgang, erstellt_von=self.user)

        self.assertEqual(vorschlag.status, "entwurf")
        self.assertEqual(vorschlag.text, vorschlag.text_ki)
        self.assertTrue(vorschlag.text)
        self.assertEqual(vorschlag.erzeugt_von, self.user)
        ereignis = VorgangEreignis.objects.get(
            vorgang=self.vorgang, typ="antwort_vorschlag_erzeugt",
        )
        self.assertTrue(ereignis.intern)

    @patch("anthropic.Anthropic")
    def test_prompt_enthaelt_person_und_objekt_kontext(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response()
        mock_anthropic_cls.return_value = mock_client

        with self.settings(ANTHROPIC_API_KEY="dummy-key"):
            antwort_vorschlag_service.erzeuge_vorschlag(self.vorgang, erstellt_von=self.user)

        _, kwargs = mock_client.messages.create.call_args
        user_message = kwargs["messages"][0]["content"]
        self.assertIn(self.person.name, user_message)
        self.assertIn("Eigentümer", user_message)
        self.assertIn(self.objekt.bezeichnung, user_message)
        self.assertIn("Frage zur Nebenkostenabrechnung", user_message)
        # System-Prompt untersagt Zusagen/Fristen/Kosten/Rechtsauskünfte.
        self.assertIn("system", kwargs)
        self.assertIn("Rechtsauskünfte", kwargs["system"])

    @patch("anthropic.Anthropic")
    def test_system_prompt_verbietet_entwurfs_und_pruefhinweise(self, mock_anthropic_cls):
        """Der Text muss versandfähig sein — der System-Prompt darf NICHT
        dazu anleiten, im Brieftext auf Entwurfscharakter, interne Prüfung
        oder KI-Erzeugung hinzuweisen (das leistet ausschließlich das
        Frontend-Badge "KI-Entwurf — bitte prüfen")."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response()
        mock_anthropic_cls.return_value = mock_client

        with self.settings(ANTHROPIC_API_KEY="dummy-key"):
            antwort_vorschlag_service.erzeuge_vorschlag(self.vorgang, erstellt_von=self.user)

        _, kwargs = mock_client.messages.create.call_args
        system_prompt = kwargs["system"]
        self.assertIn("NIEMALS", system_prompt)
        self.assertIn("Entwurf", system_prompt)
        self.assertIn("intern", system_prompt)
        self.assertIn("KI", system_prompt)

    @patch("anthropic.Anthropic")
    def test_erneutes_erzeugen_verwirft_alten_entwurf(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response()
        mock_anthropic_cls.return_value = mock_client

        with self.settings(ANTHROPIC_API_KEY="dummy-key"):
            erster = antwort_vorschlag_service.erzeuge_vorschlag(self.vorgang, erstellt_von=self.user)
            zweiter = antwort_vorschlag_service.erzeuge_vorschlag(self.vorgang, erstellt_von=self.user)

        erster.refresh_from_db()
        self.assertEqual(erster.status, "verworfen")
        self.assertEqual(zweiter.status, "entwurf")
        # Constraint hält: nur ein Entwurf je Vorgang.
        self.assertEqual(
            VorgangAntwortVorschlag.objects.filter(vorgang=self.vorgang, status="entwurf").count(),
            1,
        )
        self.assertTrue(
            VorgangEreignis.objects.filter(
                vorgang=self.vorgang, typ="antwort_vorschlag_verworfen",
            ).exists()
        )


class ErzeugeVorschlagFehlerTest(TestCase):
    def setUp(self):
        self.objekt = _objekt("AV010")
        self.user = _user("antwort-vorschlag-fehler-tester")
        self.vorgang = vorgang_service.erstelle_vorgang(
            typ=_typ(), betreff="Test", erstellt_von=self.user, objekt=self.objekt,
        )

    def test_kein_api_key_fuehrt_zu_fehlgeschlagen_ohne_crash(self):
        with self.settings(ANTHROPIC_API_KEY=""):
            vorschlag = antwort_vorschlag_service.erzeuge_vorschlag(self.vorgang, erstellt_von=self.user)

        self.assertEqual(vorschlag.status, "fehlgeschlagen")
        self.assertTrue(vorschlag.fehler)
        self.assertTrue(
            VorgangEreignis.objects.filter(
                vorgang=self.vorgang, typ="antwort_vorschlag_erzeugt",
            ).exists()
        )

    @patch("anthropic.Anthropic")
    def test_api_fehler_fuehrt_zu_fehlgeschlagen_ohne_crash(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("API nicht erreichbar")
        mock_anthropic_cls.return_value = mock_client

        with self.settings(ANTHROPIC_API_KEY="dummy-key"):
            vorschlag = antwort_vorschlag_service.erzeuge_vorschlag(self.vorgang, erstellt_von=self.user)

        self.assertEqual(vorschlag.status, "fehlgeschlagen")
        self.assertIn("API nicht erreichbar", vorschlag.fehler)


class BearbeiteVorschlagTest(TestCase):
    def setUp(self):
        self.objekt = _objekt("AV020")
        self.user = _user("antwort-vorschlag-bearbeiten-tester")
        self.vorgang = vorgang_service.erstelle_vorgang(
            typ=_typ(), betreff="Test", erstellt_von=self.user, objekt=self.objekt,
        )
        self.vorschlag = VorgangAntwortVorschlag.objects.create(
            vorgang=self.vorgang, text_ki="Original-KI-Text", text="Original-KI-Text",
            status="entwurf",
        )

    def test_bearbeiten_aendert_text_text_ki_bleibt(self):
        antwort_vorschlag_service.bearbeite_vorschlag(
            self.vorschlag, "Angepasster Text", self.user,
        )
        self.vorschlag.refresh_from_db()
        self.assertEqual(self.vorschlag.text, "Angepasster Text")
        self.assertEqual(self.vorschlag.text_ki, "Original-KI-Text")
        self.assertEqual(self.vorschlag.bearbeitet_von, self.user)
        self.assertTrue(
            VorgangEreignis.objects.filter(
                vorgang=self.vorgang, typ="antwort_vorschlag_bearbeitet",
            ).exists()
        )

    def test_bearbeiten_ausserhalb_entwurf_wirft_fehler(self):
        self.vorschlag.status = "freigegeben"
        self.vorschlag.save(update_fields=["status"])
        with self.assertRaises(ValidationError):
            antwort_vorschlag_service.bearbeite_vorschlag(self.vorschlag, "Neuer Text", self.user)

    def test_leerer_text_wirft_fehler(self):
        with self.assertRaises(ValidationError):
            antwort_vorschlag_service.bearbeite_vorschlag(self.vorschlag, "   ", self.user)


class GibFreiTest(TestCase):
    def setUp(self):
        self.objekt = _objekt("AV030")
        self.user = _user("antwort-vorschlag-freigabe-tester")
        self.vorgang = vorgang_service.erstelle_vorgang(
            typ=_typ(), betreff="Test", erstellt_von=self.user, objekt=self.objekt,
        )
        self.vorschlag = VorgangAntwortVorschlag.objects.create(
            vorgang=self.vorgang, text_ki="KI-Text", text="Freigegebener Text",
            status="entwurf",
        )

    def test_freigabe_setzt_status_und_ereignis_mit_text(self):
        antwort_vorschlag_service.gib_frei(self.vorschlag, self.user)
        self.vorschlag.refresh_from_db()
        self.assertEqual(self.vorschlag.status, "freigegeben")
        self.assertEqual(self.vorschlag.freigegeben_von, self.user)
        self.assertIsNotNone(self.vorschlag.freigegeben_am)

        ereignis = VorgangEreignis.objects.get(
            vorgang=self.vorgang, typ="antwort_vorschlag_freigegeben",
        )
        self.assertEqual(ereignis.text, "Freigegebener Text")
        self.assertFalse(ereignis.intern)

    def test_doppelte_freigabe_wirft_fehler(self):
        antwort_vorschlag_service.gib_frei(self.vorschlag, self.user)
        with self.assertRaises(ValidationError):
            antwort_vorschlag_service.gib_frei(self.vorschlag, self.user)


class VerwirfTest(TestCase):
    def setUp(self):
        self.objekt = _objekt("AV040")
        self.user = _user("antwort-vorschlag-verwerfen-tester")
        self.vorgang = vorgang_service.erstelle_vorgang(
            typ=_typ(), betreff="Test", erstellt_von=self.user, objekt=self.objekt,
        )
        self.vorschlag = VorgangAntwortVorschlag.objects.create(
            vorgang=self.vorgang, text_ki="KI-Text", text="KI-Text", status="entwurf",
        )

    def test_verwerfen_setzt_status_und_ereignis(self):
        antwort_vorschlag_service.verwirf(self.vorschlag, self.user, grund="Nicht relevant")
        self.vorschlag.refresh_from_db()
        self.assertEqual(self.vorschlag.status, "verworfen")
        ereignis = VorgangEreignis.objects.get(
            vorgang=self.vorgang, typ="antwort_vorschlag_verworfen",
        )
        self.assertEqual(ereignis.text, "Nicht relevant")
        self.assertTrue(ereignis.intern)

    def test_doppeltes_verwerfen_wirft_fehler(self):
        antwort_vorschlag_service.verwirf(self.vorschlag, self.user)
        with self.assertRaises(ValidationError):
            antwort_vorschlag_service.verwirf(self.vorschlag, self.user)


class ErstelleVorgangAusloesungTest(TestCase):
    """Deckt die Auslösung des KI-Antwortvorschlags bei Vorgangsanlage ab
    (nur wenn ``typ.antwort_vorschlag_aktiv``), über den Celery-Task."""

    def setUp(self):
        self.objekt = _objekt("AV050")
        self.user = _user("antwort-vorschlag-ausloesung-tester")

    def test_erzeuge_antwort_vorschlag_task_wird_bei_aktivem_typ_beauftragt(self):
        typ = _typ("anfrage")
        self.assertTrue(typ.antwort_vorschlag_aktiv)

        with patch(
            "apps.vorgaenge.tasks.erzeuge_antwort_vorschlag.delay",
        ) as mock_delay:
            with self.captureOnCommitCallbacks(execute=True):
                vorgang = vorgang_service.erstelle_vorgang(
                    typ=typ, betreff="Test", erstellt_von=self.user, objekt=self.objekt,
                )
        mock_delay.assert_called_once_with(str(vorgang.id))

    def test_kein_task_bei_inaktivem_typ(self):
        typ = _typ("maengelmeldung")
        self.assertFalse(typ.antwort_vorschlag_aktiv)

        with patch(
            "apps.vorgaenge.tasks.erzeuge_antwort_vorschlag.delay",
        ) as mock_delay:
            with self.captureOnCommitCallbacks(execute=True):
                vorgang_service.erstelle_vorgang(
                    typ=typ, betreff="Test", erstellt_von=self.user, objekt=self.objekt,
                )
        mock_delay.assert_not_called()
