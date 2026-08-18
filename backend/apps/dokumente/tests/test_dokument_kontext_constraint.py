"""
Tests für die Owner-Regel B-Hybrid am Dokument (Phase A, Spec Vorgang & DMS
Kap. 1.6 + 4): höchstens ein Kontext-FK (objekt/einheit/vorgang/person),
0 Kontext-FKs nur zulässig bei Kopplung über Rechnung.beleg_dokument.

Deckt ab:
  - DB-CheckConstraint: >1 Kontext-FK wird auf DB-Ebene abgewiesen (IntegrityError)
  - clean(): >1 Kontext-FK wird abgewiesen
  - clean(): 0 Kontext-FKs ohne Rechnungskopplung wird abgewiesen
  - clean(): 0 Kontext-FKs MIT Rechnungskopplung ist ok
  - clean(): genau 1 Kontext-FK ist ok
  - DokumentQuerySet.fuer_objekt()/fuer_einheit()/fuer_person(): Beziehungsgraph
"""
import shutil
import tempfile
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from apps.dokumente.models import Dokument
from apps.objekte.models import Objekt, Einheit
from apps.personen.models import Person
from apps.rechnungen.models import Rechnung
from apps.vorgaenge.models import Vorgang, VorgangTyp

User = get_user_model()

_MEDIA_TMP = tempfile.mkdtemp(prefix="immocore_test_media_kontext_")


def tearDownModule():
    shutil.rmtree(_MEDIA_TMP, ignore_errors=True)


def _objekt(nr="K001"):
    return Objekt.objects.create(
        bezeichnung="Test-WEG Kontext", objektnummer=nr, objekt_typ="weg",
        ort="Teststadt", verwaltung_seit=date(2020, 1, 1),
    )


def _einheit(objekt, nr="WE01"):
    return Einheit.objects.create(
        objekt=objekt, einheit_nr=nr, einheit_typ="Wohnung", lage="EG",
    )


def _user(username="kontext-tester"):
    return User.objects.create_user(username=username, password="x")


def _vorgang(objekt, user, einheit=None):
    typ = VorgangTyp.objects.get(code="sonstiges")
    v = Vorgang(typ=typ, betreff="Testvorgang", objekt=objekt, einheit=einheit, erstellt_von=user)
    v.full_clean()
    v.save()
    return v


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class DokumentKontextConstraintTest(TestCase):
    def setUp(self):
        self.objekt = _objekt()
        self.einheit = _einheit(self.objekt)
        self.user = _user()
        self.person = Person.objects.create(person_typ="100", nachname="Melder")
        self.vorgang = _vorgang(self.objekt, self.user)

    def _dokument(self, **kwargs):
        defaults = dict(
            datei=ContentFile(b"Inhalt", name="dok.pdf"),
            dateiname="dok.pdf",
            kategorie="Sonstiges",
            hochgeladen_von=self.user,
        )
        defaults.update(kwargs)
        return Dokument(**defaults)

    # ── clean() ──────────────────────────────────────────────────────────
    def test_clean_genau_ein_kontext_ist_ok(self):
        self._dokument(objekt=self.objekt).full_clean(exclude=["datei"])

    def test_clean_zwei_kontexte_wird_abgewiesen(self):
        dok = self._dokument(objekt=self.objekt, einheit=self.einheit)
        with self.assertRaises(ValidationError):
            dok.full_clean(exclude=["datei"])

    def test_clean_alle_vier_kontexte_wird_abgewiesen(self):
        dok = self._dokument(
            objekt=self.objekt, einheit=self.einheit,
            vorgang=self.vorgang, person=self.person,
        )
        with self.assertRaises(ValidationError):
            dok.full_clean(exclude=["datei"])

    def test_clean_kein_kontext_ohne_rechnungskopplung_wird_abgewiesen(self):
        dok = self._dokument()
        with self.assertRaises(ValidationError):
            dok.full_clean(exclude=["datei"])

    def test_clean_kein_kontext_mit_rechnungskopplung_ist_ok(self):
        dok = self._dokument()
        dok.save()
        Rechnung.objects.create(
            objekt=self.objekt, betrag_brutto=Decimal("100.00"),
            rechnungsnummer="RE-KONTEXT-001", status="in_pruefung",
            beleg_dokument=dok,
        )
        dok.refresh_from_db()
        dok.full_clean(exclude=["datei"])  # darf nicht werfen

    def test_clean_nur_vorgang_ist_ok(self):
        self._dokument(vorgang=self.vorgang).full_clean(exclude=["datei"])

    def test_clean_nur_person_ist_ok(self):
        self._dokument(person=self.person).full_clean(exclude=["datei"])

    # ── DB-CheckConstraint ───────────────────────────────────────────────
    def test_db_constraint_weist_zwei_kontexte_ab(self):
        dok = self._dokument(objekt=self.objekt, einheit=self.einheit)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                dok.save()

    def test_db_constraint_erlaubt_einen_kontext(self):
        dok = self._dokument(objekt=self.objekt)
        dok.save()  # darf nicht werfen
        self.assertTrue(Dokument.objects.filter(pk=dok.pk).exists())

    def test_db_constraint_erlaubt_keinen_kontext(self):
        dok = self._dokument()
        dok.save()  # darf nicht werfen (DB prüft nur <= 1, nicht die 0-Ausnahme)
        self.assertTrue(Dokument.objects.filter(pk=dok.pk).exists())


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class DokumentQuerySetTest(TestCase):
    """Zentrale Abfrage-API: fuer_objekt()/fuer_einheit()/fuer_person()."""

    def setUp(self):
        self.objekt = _objekt("K010")
        self.einheit = _einheit(self.objekt)
        self.fremdes_objekt = _objekt("K011")
        self.user = _user("qs-tester")
        self.person = Person.objects.create(person_typ="100", nachname="QS-Melder")
        self.vorgang = _vorgang(self.objekt, self.user, einheit=self.einheit)

        self.dok_direkt_objekt = Dokument.objects.create(
            datei=ContentFile(b"a", name="a.pdf"), dateiname="a.pdf",
            kategorie="x",
            objekt=self.objekt, hochgeladen_von=self.user,
        )
        self.dok_ueber_einheit = Dokument.objects.create(
            datei=ContentFile(b"b", name="b.pdf"), dateiname="b.pdf",
            kategorie="x",
            einheit=self.einheit, hochgeladen_von=self.user,
        )
        self.dok_ueber_vorgang = Dokument.objects.create(
            datei=ContentFile(b"c", name="c.pdf"), dateiname="c.pdf",
            kategorie="x",
            vorgang=self.vorgang, hochgeladen_von=self.user,
        )
        self.dok_ueber_person = Dokument.objects.create(
            datei=ContentFile(b"d", name="d.pdf"), dateiname="d.pdf",
            kategorie="x",
            person=self.person, hochgeladen_von=self.user,
        )
        self.dok_ueber_rechnung = Dokument.objects.create(
            datei=ContentFile(b"e", name="e.pdf"), dateiname="e.pdf",
            kategorie="x",
            hochgeladen_von=self.user,
        )
        Rechnung.objects.create(
            objekt=self.objekt, betrag_brutto=Decimal("50.00"),
            rechnungsnummer="RE-QS-001", status="in_pruefung",
            beleg_dokument=self.dok_ueber_rechnung,
        )
        self.dok_fremd = Dokument.objects.create(
            datei=ContentFile(b"f", name="f.pdf"), dateiname="f.pdf",
            kategorie="x",
            objekt=self.fremdes_objekt, hochgeladen_von=self.user,
        )

    def test_fuer_objekt_findet_alle_vier_wege(self):
        ids = set(Dokument.objects.fuer_objekt(self.objekt).values_list("pk", flat=True))
        erwartet = {
            self.dok_direkt_objekt.pk, self.dok_ueber_einheit.pk,
            self.dok_ueber_vorgang.pk, self.dok_ueber_rechnung.pk,
        }
        self.assertEqual(ids, erwartet)
        self.assertNotIn(self.dok_fremd.pk, ids)

    def test_fuer_einheit_findet_direkt_und_ueber_vorgang(self):
        ids = set(Dokument.objects.fuer_einheit(self.einheit).values_list("pk", flat=True))
        self.assertEqual(ids, {self.dok_ueber_einheit.pk, self.dok_ueber_vorgang.pk})

    def test_fuer_person_findet_direkt_und_ueber_vorgang(self):
        vorgang_mit_person = Vorgang(
            typ=VorgangTyp.objects.get(code="sonstiges"), betreff="Mit Person",
            person=self.person, erstellt_von=self.user,
        )
        vorgang_mit_person.full_clean()
        vorgang_mit_person.save()
        dok_vorgang_person = Dokument.objects.create(
            datei=ContentFile(b"g", name="g.pdf"), dateiname="g.pdf",
            kategorie="x",
            vorgang=vorgang_mit_person, hochgeladen_von=self.user,
        )
        ids = set(Dokument.objects.fuer_person(self.person).values_list("pk", flat=True))
        self.assertEqual(ids, {self.dok_ueber_person.pk, dok_vorgang_person.pk})
