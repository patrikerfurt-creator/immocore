"""
Tests für ``apps.vorgaenge.services.dokument_service`` (Phase B, Spec Vorgang &
DMS Kap. 1.6 / 4).

Deckt ab:
  - Kontext-Validierung: zwei Kontexte -> abgewiesen, kein Kontext -> abgewiesen
  - Upload mit Kontext vorgang erzeugt VorgangEreignis 'dokument_verknuepft'
  - Duplikat-Erkennung: gleiche Datei im selben Kontext -> Warnung; in
    verschiedenen Kontexten -> keine Warnung
  - Versionierung: neue Version -> alte Zeile unverändert, neue hat version=2
    und vorgaenger_version gesetzt
  - Versionieren eines Beleg-Dokuments (Rechnung.beleg_dokument) -> Exception
"""
import shutil
import tempfile
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from apps.dokumente.models import Dokument
from apps.dokumente.services.beleg_service import lege_rechnungsbeleg_ab
from apps.objekte.models import Objekt, Einheit
from apps.personen.models import Person
from apps.rechnungen.models import Rechnung
from apps.vorgaenge.models import Vorgang, VorgangEreignis, VorgangTyp
from apps.vorgaenge.services import dokument_service

User = get_user_model()

_MEDIA_TMP = tempfile.mkdtemp(prefix="immocore_test_media_vorgaenge_dok_")


def tearDownModule():
    shutil.rmtree(_MEDIA_TMP, ignore_errors=True)


def _objekt(nr="DS001"):
    return Objekt.objects.create(
        bezeichnung="Test-WEG Dokument-Service", objektnummer=nr, objekt_typ="weg",
        ort="Teststadt", verwaltung_seit=date(2020, 1, 1),
    )


def _einheit(objekt, nr="WE01"):
    return Einheit.objects.create(
        objekt=objekt, einheit_nr=nr, einheit_typ="Wohnung", lage="EG",
    )


def _user(username="dokument-service-tester"):
    return User.objects.create_user(username=username, password="x")


def _vorgang(objekt, user):
    typ = VorgangTyp.objects.get(code="sonstiges")
    v = Vorgang(typ=typ, betreff="Testvorgang", objekt=objekt, erstellt_von=user)
    v.full_clean()
    v.save()
    return v


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class LadeDokumentHochKontextTest(TestCase):
    def setUp(self):
        self.objekt = _objekt()
        self.einheit = _einheit(self.objekt)
        self.user = _user()

    def test_zwei_kontexte_wird_abgewiesen(self):
        with self.assertRaises(ValidationError):
            dokument_service.lade_dokument_hoch(
                b"Inhalt", "a.pdf", self.user, objekt=self.objekt, einheit=self.einheit,
            )
        self.assertEqual(Dokument.objects.count(), 0)

    def test_kein_kontext_wird_abgewiesen(self):
        with self.assertRaises(ValidationError):
            dokument_service.lade_dokument_hoch(b"Inhalt", "a.pdf", self.user)
        self.assertEqual(Dokument.objects.count(), 0)

    def test_genau_ein_kontext_funktioniert(self):
        ergebnis = dokument_service.lade_dokument_hoch(
            b"Inhalt", "a.pdf", self.user, objekt=self.objekt,
        )
        self.assertEqual(ergebnis.dokument.objekt_id, self.objekt.id)
        self.assertEqual(ergebnis.dokument.version, 1)
        self.assertFalse(ergebnis.duplikat_warnung)


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class LadeDokumentHochVorgangEreignisTest(TestCase):
    def setUp(self):
        self.objekt = _objekt("DS010")
        self.user = _user("vorgang-ereignis-tester")
        self.vorgang = _vorgang(self.objekt, self.user)

    def test_upload_mit_vorgang_kontext_erzeugt_ereignis(self):
        ergebnis = dokument_service.lade_dokument_hoch(
            b"Inhalt", "beleg.pdf", self.user, vorgang=self.vorgang,
        )
        self.assertEqual(ergebnis.dokument.vorgang_id, self.vorgang.id)
        ereignis = VorgangEreignis.objects.get(vorgang=self.vorgang, typ="dokument_verknuepft")
        self.assertIn("beleg.pdf", ereignis.text)

    def test_dokument_verknuepft_ist_eigentuemer_sichtbar(self):
        """Patrik-Entscheidung: der Hinweis 'Dokument hinzugefügt' ist für den
        Eigentümer sichtbar (intern=False) — anders als die meisten übrigen
        Ereignistypen."""
        dokument_service.lade_dokument_hoch(
            b"Inhalt", "beleg.pdf", self.user, vorgang=self.vorgang,
        )
        ereignis = VorgangEreignis.objects.get(vorgang=self.vorgang, typ="dokument_verknuepft")
        self.assertFalse(ereignis.intern)

    def test_upload_mit_objekt_kontext_erzeugt_kein_vorgang_ereignis(self):
        dokument_service.lade_dokument_hoch(b"Inhalt", "a.pdf", self.user, objekt=self.objekt)
        self.assertEqual(VorgangEreignis.objects.count(), 0)


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class DuplikatErkennungTest(TestCase):
    def setUp(self):
        self.objekt = _objekt("DS020")
        self.anderes_objekt = _objekt("DS021")
        self.user = _user("duplikat-tester")

    def test_gleiche_datei_im_selben_kontext_erzeugt_warnung(self):
        dokument_service.lade_dokument_hoch(b"Gleicher Inhalt", "a.pdf", self.user, objekt=self.objekt)
        ergebnis = dokument_service.lade_dokument_hoch(
            b"Gleicher Inhalt", "a-kopie.pdf", self.user, objekt=self.objekt,
        )
        self.assertTrue(ergebnis.duplikat_warnung)
        # Kein Hard-Block: das zweite Dokument wird trotzdem angelegt.
        self.assertEqual(Dokument.objects.filter(objekt=self.objekt).count(), 2)

    def test_gleiche_datei_in_verschiedenen_kontexten_ohne_warnung(self):
        dokument_service.lade_dokument_hoch(b"Gleicher Inhalt", "a.pdf", self.user, objekt=self.objekt)
        ergebnis = dokument_service.lade_dokument_hoch(
            b"Gleicher Inhalt", "a.pdf", self.user, objekt=self.anderes_objekt,
        )
        self.assertFalse(ergebnis.duplikat_warnung)

    def test_erste_ablage_ohne_warnung(self):
        ergebnis = dokument_service.lade_dokument_hoch(b"Neuer Inhalt", "a.pdf", self.user, objekt=self.objekt)
        self.assertFalse(ergebnis.duplikat_warnung)


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class NeueVersionAnlegenTest(TestCase):
    def setUp(self):
        self.objekt = _objekt("DS030")
        self.person = Person.objects.create(person_typ="100", nachname="Versions-Melder")
        self.user = _user("version-tester")

    def test_neue_version_alte_zeile_unveraendert(self):
        ergebnis = dokument_service.lade_dokument_hoch(
            b"Version 1", "dok.pdf", self.user, objekt=self.objekt,
        )
        altes_dokument = ergebnis.dokument
        alter_dateiname = altes_dokument.dateiname
        alter_sha256 = altes_dokument.sha256

        neues_dokument = dokument_service.neue_version_anlegen(
            altes_dokument, b"Version 2", "dok-v2.pdf", self.user,
        )

        self.assertEqual(neues_dokument.version, 2)
        self.assertEqual(neues_dokument.vorgaenger_version_id, altes_dokument.id)
        self.assertEqual(neues_dokument.objekt_id, self.objekt.id)
        self.assertNotEqual(neues_dokument.sha256, alter_sha256)

        altes_dokument.refresh_from_db()
        self.assertEqual(altes_dokument.version, 1)
        self.assertEqual(altes_dokument.dateiname, alter_dateiname)
        self.assertEqual(altes_dokument.sha256, alter_sha256)
        self.assertIsNone(altes_dokument.vorgaenger_version_id)

    def test_neue_version_uebernimmt_kontext_person(self):
        ergebnis = dokument_service.lade_dokument_hoch(
            b"Version 1", "dok.pdf", self.user, person=self.person,
        )
        neues_dokument = dokument_service.neue_version_anlegen(
            ergebnis.dokument, b"Version 2", "dok-v2.pdf", self.user,
        )
        self.assertEqual(neues_dokument.person_id, self.person.id)
        self.assertIsNone(neues_dokument.objekt_id)

    def test_versionieren_von_beleg_dokument_wirft_fehler(self):
        rechnung = Rechnung.objects.create(
            objekt=self.objekt, betrag_brutto=Decimal("100.00"),
            rechnungsnummer="RE-VERSION-001", status="in_pruefung",
        )
        beleg = lege_rechnungsbeleg_ab(rechnung, b"%PDF-1.4 Inhalt", "beleg.pdf", self.objekt, self.user)

        with self.assertRaises(ValidationError):
            dokument_service.neue_version_anlegen(beleg, b"Neuer Inhalt", "beleg-v2.pdf", self.user)

        beleg.refresh_from_db()
        self.assertEqual(beleg.version, 1)
