"""
Tests für Vorgang.clean() (Phase A, Spec Vorgang & DMS Kap. 1.2 + 4).

Deckt ab:
  - kein Kontext (weder objekt noch einheit noch person) -> abgewiesen
  - einheit aus fremdem Objekt -> abgewiesen
  - wiedervorlage_am bei falschem Status -> abgewiesen
  - gültiger Vorgang (objekt gesetzt) -> full_clean() geht durch, nummer im
    Format V-{JJ}-{LFD5}, status='offen'
"""
import re
from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.objekte.models import Objekt, Einheit
from apps.vorgaenge.models import Vorgang, VorgangTyp

User = get_user_model()


def _objekt(nr="V001"):
    return Objekt.objects.create(
        bezeichnung="Test-WEG Vorgang", objektnummer=nr, objekt_typ="weg",
        ort="Teststadt", verwaltung_seit=date(2020, 1, 1),
    )


def _einheit(objekt, nr="WE01"):
    return Einheit.objects.create(
        objekt=objekt, einheit_nr=nr, einheit_typ="Wohnung", lage="EG",
    )


def _user(username="vorgang-tester"):
    return User.objects.create_user(username=username, password="x")


def _typ():
    return VorgangTyp.objects.get(code="maengelmeldung")


class VorgangCleanTest(TestCase):
    def setUp(self):
        self.objekt = _objekt()
        self.anderes_objekt = _objekt("V002")
        self.user = _user()
        self.typ = _typ()

    def _vorgang(self, **kwargs):
        defaults = dict(
            typ=self.typ, betreff="Testvorgang", erstellt_von=self.user,
        )
        defaults.update(kwargs)
        return Vorgang(**defaults)

    def test_ohne_jeden_kontext_wird_abgewiesen(self):
        vorgang = self._vorgang()
        with self.assertRaises(ValidationError):
            vorgang.full_clean()

    def test_einheit_aus_fremdem_objekt_wird_abgewiesen(self):
        einheit_fremd = _einheit(self.anderes_objekt)
        vorgang = self._vorgang(objekt=self.objekt, einheit=einheit_fremd)
        with self.assertRaises(ValidationError):
            vorgang.full_clean()

    def test_einheit_aus_richtigem_objekt_ist_ok(self):
        einheit = _einheit(self.objekt)
        vorgang = self._vorgang(objekt=self.objekt, einheit=einheit)
        vorgang.full_clean()  # darf nicht werfen

    def test_wiedervorlage_am_bei_falschem_status_wird_abgewiesen(self):
        vorgang = self._vorgang(objekt=self.objekt, status="offen", wiedervorlage_am=date(2026, 1, 1))
        with self.assertRaises(ValidationError):
            vorgang.full_clean()

    def test_wiedervorlage_am_bei_richtigem_status_ist_ok(self):
        vorgang = self._vorgang(
            objekt=self.objekt, status="wiedervorlage", wiedervorlage_am=date(2026, 1, 1),
        )
        vorgang.full_clean()  # darf nicht werfen

    def test_anlage_mit_objekt_erzeugt_gueltige_nummer_und_status_offen(self):
        vorgang = self._vorgang(objekt=self.objekt)
        vorgang.full_clean()
        vorgang.save()
        self.assertRegex(vorgang.nummer, r"^V-\d{2}-\d{5}$")
        self.assertEqual(vorgang.status, "offen")

    def test_nur_person_gesetzt_ist_ausreichend(self):
        from apps.personen.models import Person
        person = Person.objects.create(person_typ="100", nachname="Melder")
        vorgang = self._vorgang(person=person)
        vorgang.full_clean()  # darf nicht werfen
