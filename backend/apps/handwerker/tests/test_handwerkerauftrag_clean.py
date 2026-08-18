"""
Tests für Handwerkerauftrag.clean() (Phase A, Orchestrator-Vorgabe 6).

Deckt ab:
  - Kreditor ohne ist_handwerker=True wird abgewiesen
  - Kreditor mit leerer E-Mail wird abgewiesen
  - Objekt weicht vom Objekt des verknüpften Vorgangs ab -> abgewiesen
  - Objekt weicht vom Objekt der Einheit des verknüpften Vorgangs ab -> abgewiesen
  - gültiger Fall geht durch (full_clean() wirft nicht)
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.handwerker.models import Handwerkerauftrag
from apps.objekte.models import Einheit, Objekt
from apps.rechnungen.models import Kreditor
from apps.vorgaenge.models import Vorgang, VorgangTyp

User = get_user_model()


def _objekt(nr="H001", bundesland="HE"):
    return Objekt.objects.create(
        bezeichnung="Test-WEG Handwerker", objektnummer=nr, objekt_typ="weg",
        ort="Teststadt", verwaltung_seit=date(2020, 1, 1), bundesland=bundesland,
    )


def _einheit(objekt, nr="WE01"):
    return Einheit.objects.create(
        objekt=objekt, einheit_nr=nr, einheit_typ="Wohnung", lage="EG",
    )


def _user(username="handwerker-tester"):
    return User.objects.create_user(username=username, password="x")


def _kreditor(name="Meister Sanitär GmbH", ist_handwerker=True, email="meister@example.de"):
    return Kreditor.objects.create(name=name, ist_handwerker=ist_handwerker, email=email)


def _vorgang(user, objekt=None, einheit=None):
    typ = VorgangTyp.objects.get(code="maengelmeldung")
    return Vorgang.objects.create(
        typ=typ, betreff="Testvorgang", erstellt_von=user, objekt=objekt, einheit=einheit,
    )


class HandwerkerauftragCleanTest(TestCase):
    def setUp(self):
        self.objekt = _objekt()
        self.anderes_objekt = _objekt("H002")
        self.user = _user()
        self.kreditor = _kreditor()

    def _auftrag(self, **kwargs):
        defaults = dict(
            objekt=self.objekt, kreditor=self.kreditor, titel="Wasserhahn undicht",
            erstellt_von=self.user,
        )
        defaults.update(kwargs)
        return Handwerkerauftrag(**defaults)

    def test_kreditor_ohne_ist_handwerker_wird_abgewiesen(self):
        kreditor = _kreditor(name="Kein Handwerker AG", ist_handwerker=False)
        auftrag = self._auftrag(kreditor=kreditor)
        with self.assertRaises(ValidationError):
            auftrag.full_clean()

    def test_kreditor_mit_leerer_email_wird_abgewiesen(self):
        kreditor = _kreditor(name="Ohne Mail GmbH", email="")
        auftrag = self._auftrag(kreditor=kreditor)
        with self.assertRaises(ValidationError):
            auftrag.full_clean()

    def test_objekt_weicht_vom_vorgang_objekt_ab_wird_abgewiesen(self):
        vorgang = _vorgang(self.user, objekt=self.anderes_objekt)
        auftrag = self._auftrag(objekt=self.objekt, vorgang=vorgang)
        with self.assertRaises(ValidationError):
            auftrag.full_clean()

    def test_objekt_weicht_von_vorgang_einheit_objekt_ab_wird_abgewiesen(self):
        einheit_fremd = _einheit(self.anderes_objekt)
        vorgang = _vorgang(self.user, einheit=einheit_fremd)
        auftrag = self._auftrag(objekt=self.objekt, vorgang=vorgang)
        with self.assertRaises(ValidationError):
            auftrag.full_clean()

    def test_gueltiger_fall_geht_durch(self):
        einheit = _einheit(self.objekt)
        vorgang = _vorgang(self.user, einheit=einheit)
        auftrag = self._auftrag(objekt=self.objekt, vorgang=vorgang)
        auftrag.full_clean()  # darf nicht werfen
        auftrag.save()
        self.assertRegex(auftrag.nummer, r"^HWA-\d{2}-\d{5}$")

    def test_gueltiger_fall_ohne_vorgang_geht_durch(self):
        auftrag = self._auftrag()
        auftrag.full_clean()  # darf nicht werfen
        auftrag.save()
        self.assertRegex(auftrag.nummer, r"^HWA-\d{2}-\d{5}$")
