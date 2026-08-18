"""
Tests für ``auftrag_service.erstelle_auftrag`` (Phase B, Orchestrator-Vorgabe
Schritt 2/5).

Deckt ab:
  - Objektermittlung aus vorgang.objekt
  - Objektermittlung aus vorgang.einheit.objekt (falls vorgang.objekt leer)
  - explizit übergebenes Objekt hat Vorrang vor dem Vorgang
  - Vorgang nur mit person (kein Objektbezug) -> ValidationError
  - Anlage löst den Mailversand-Task erst NACH Commit aus
    (``captureOnCommitCallbacks``)
"""
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.handwerker.models import AuftragsbestaetigungsToken, Handwerkerauftrag
from apps.handwerker.services import auftrag_service
from apps.objekte.models import Einheit, Objekt
from apps.personen.models import Person
from apps.rechnungen.models import Kreditor
from apps.vorgaenge.models import Vorgang, VorgangTyp

User = get_user_model()


def _objekt(nr="H400"):
    return Objekt.objects.create(
        bezeichnung="Test-WEG Auftrag Erstellen", objektnummer=nr, objekt_typ="weg",
        ort="Teststadt", verwaltung_seit=date(2020, 1, 1), bundesland="HE",
    )


def _einheit(objekt, nr="WE01"):
    return Einheit.objects.create(objekt=objekt, einheit_nr=nr, einheit_typ="Wohnung", lage="EG")


def _user():
    return User.objects.create_user(username="auftrag-ersteller", password="x")


def _kreditor(email="meister@example.de"):
    return Kreditor.objects.create(
        name="Meister Sanitär GmbH", ist_handwerker=True, email=email,
    )


def _person():
    return Person.objects.create(person_typ="100", vorname="Max", nachname="Mustermann")


def _vorgang(user, objekt=None, einheit=None, person=None, prioritaet=None):
    typ = VorgangTyp.objects.get(code="maengelmeldung")
    kwargs = dict(typ=typ, betreff="Testvorgang", erstellt_von=user,
                  objekt=objekt, einheit=einheit, person=person)
    if prioritaet is not None:
        kwargs['prioritaet'] = prioritaet
    return Vorgang.objects.create(**kwargs)


class ErstelleAuftragObjektermittlungTest(TestCase):
    def setUp(self):
        self.user = _user()
        self.kreditor = _kreditor()
        self.objekt = _objekt()

    def test_objekt_aus_vorgang_objekt(self):
        vorgang = _vorgang(self.user, objekt=self.objekt)
        auftrag = auftrag_service.erstelle_auftrag(
            kreditor=self.kreditor, titel="Heizung defekt", erstellt_von=self.user,
            vorgang=vorgang,
        )
        self.assertEqual(auftrag.objekt_id, self.objekt.id)

    def test_objekt_aus_vorgang_einheit_objekt(self):
        einheit = _einheit(self.objekt)
        vorgang = _vorgang(self.user, einheit=einheit)
        auftrag = auftrag_service.erstelle_auftrag(
            kreditor=self.kreditor, titel="Fenster undicht", erstellt_von=self.user,
            vorgang=vorgang,
        )
        self.assertEqual(auftrag.objekt_id, self.objekt.id)

    def test_explizites_objekt_hat_vorrang_und_verhindert_fehler_bei_vorgang_ohne_objektbezug(self):
        # Vorgang hat NUR eine Person (keinen Objekt-/Einheitsbezug) — ohne
        # explizites Objekt würde das einen ValidationError auslösen (siehe
        # test_vorgang_nur_mit_person_wird_abgewiesen). Das explizit übergebene
        # Objekt hat Vorrang und verhindert genau diesen Fehler.
        vorgang = _vorgang(self.user, person=_person())
        auftrag = auftrag_service.erstelle_auftrag(
            kreditor=self.kreditor, titel="Dach undicht", erstellt_von=self.user,
            vorgang=vorgang, objekt=self.objekt,
        )
        self.assertEqual(auftrag.objekt_id, self.objekt.id)

    def test_vorgang_nur_mit_person_wird_abgewiesen(self):
        vorgang = _vorgang(self.user, person=_person())
        with self.assertRaises(ValidationError):
            auftrag_service.erstelle_auftrag(
                kreditor=self.kreditor, titel="Kein Objektbezug", erstellt_von=self.user,
                vorgang=vorgang,
            )
        self.assertEqual(Handwerkerauftrag.objects.count(), 0)

    def test_kein_objekt_und_kein_vorgang_wird_abgewiesen(self):
        with self.assertRaises(ValidationError):
            auftrag_service.erstelle_auftrag(
                kreditor=self.kreditor, titel="Ohne alles", erstellt_von=self.user,
            )

    def test_prioritaet_aus_vorgang_uebernommen(self):
        vorgang = _vorgang(self.user, objekt=self.objekt, prioritaet="hoch")
        auftrag = auftrag_service.erstelle_auftrag(
            kreditor=self.kreditor, titel="Dringend", erstellt_von=self.user, vorgang=vorgang,
        )
        self.assertEqual(auftrag.prioritaet, "hoch")

    def test_prioritaet_default_normal_ohne_vorgang(self):
        auftrag = auftrag_service.erstelle_auftrag(
            kreditor=self.kreditor, titel="Ohne Vorgang", erstellt_von=self.user,
            objekt=self.objekt,
        )
        self.assertEqual(auftrag.prioritaet, "normal")

    def test_status_ist_entwurf_und_token_wird_angelegt(self):
        auftrag = auftrag_service.erstelle_auftrag(
            kreditor=self.kreditor, titel="Wasserschaden", erstellt_von=self.user,
            objekt=self.objekt,
        )
        self.assertEqual(auftrag.status, "entwurf")
        self.assertTrue(AuftragsbestaetigungsToken.objects.filter(auftrag=auftrag).exists())


class ErstelleAuftragAsyncTest(TestCase):
    def setUp(self):
        self.user = _user()
        self.kreditor = _kreditor()
        self.objekt = _objekt()

    @patch("apps.handwerker.tasks.versende_auftragsmail.delay")
    def test_mailversand_wird_erst_nach_commit_ausgeloest(self, mock_delay):
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            auftrag = auftrag_service.erstelle_auftrag(
                kreditor=self.kreditor, titel="Rohrbruch", erstellt_von=self.user,
                objekt=self.objekt,
            )
            mock_delay.assert_not_called()

        self.assertEqual(len(callbacks), 1)

    @patch("apps.handwerker.tasks.versende_auftragsmail.delay")
    def test_mailversand_task_wird_mit_auftrag_id_ausgeloest(self, mock_delay):
        with self.captureOnCommitCallbacks(execute=True):
            auftrag = auftrag_service.erstelle_auftrag(
                kreditor=self.kreditor, titel="Rohrbruch", erstellt_von=self.user,
                objekt=self.objekt,
            )
        mock_delay.assert_called_once_with(str(auftrag.id))
