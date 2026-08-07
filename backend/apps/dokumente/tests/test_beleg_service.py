"""
Tests für die Beleg↔Dokument-Kopplung (Phase B, GoBD-Sperre).

Deckt ab:
  - lege_rechnungsbeleg_ab: Ablage + Kopplung + Idempotenzschutz
  - sperre_beleg_revisionssicher: GoBD-Sperre, idempotent
  - Dokument.delete()/save(): Lösch-/Austauschsperre bei revisionssicher
  - rechnung_freigeben(): setzt die Sperre auf dem gekoppelten Beleg
  - DRF: GoBD-Sperre lässt sich nicht per API umgehen
"""
import hashlib
import re
import shutil
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.buchhaltung.models import ImportOrdnerEinstellung
from apps.dokumente.models import Dokument
from apps.dokumente.services.beleg_service import (
    koppel_rechnungsbeleg,
    lege_rechnungsbeleg_ab,
    rechnungen_root,
    sperre_beleg_revisionssicher,
)
from apps.konten.models import Konto
from apps.objekte.models import Objekt, Wirtschaftsjahr
from apps.rechnungen.models import Kreditor, Rechnung
from apps.rechnungen.services.rechnung_op_service import rechnung_freigeben

User = get_user_model()

_MEDIA_TMP = tempfile.mkdtemp(prefix="immocore_test_media_")


def _tearDownModule():
    shutil.rmtree(_MEDIA_TMP, ignore_errors=True)


def tearDownModule():
    _tearDownModule()


def _objekt():
    return Objekt.objects.create(
        bezeichnung="Test-WEG Beleg",
        objektnummer="B001",
        objekt_typ="weg",
        ort="Teststadt",
        verwaltung_seit=date(2020, 1, 1),
    )


def _user(username="beleg-tester"):
    return User.objects.create_user(username=username, password="x")


def _rechnung(objekt, kreditor=None, betrag="1000.00", status="in_pruefung"):
    return Rechnung.objects.create(
        objekt=objekt, kreditor=kreditor,
        betrag_brutto=Decimal(betrag),
        rechnungsnummer="RE-BELEG-001",
        status=status,
    )


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class LegeRechnungsbelegAbTest(TestCase):
    def setUp(self):
        self.objekt = _objekt()
        self.user = _user()
        self.rechnung = _rechnung(self.objekt)
        self.datei_bytes = b"%PDF-1.4 Testinhalt Rechnung"

    def test_dokument_korrekt_angelegt_und_gekoppelt(self):
        dok = lege_rechnungsbeleg_ab(
            self.rechnung, self.datei_bytes, "rechnung-a.pdf", self.objekt, self.user,
        )
        self.assertEqual(dok.dokument_typ, "beleg")
        self.assertEqual(dok.kategorie, "Beleg")
        self.assertEqual(dok.sha256, hashlib.sha256(self.datei_bytes).hexdigest())
        self.assertRegex(dok.beleg_nummer, r"^[A-Z]{2}\d{8}$")
        self.assertEqual(dok.objekt_id, self.objekt.id)
        self.assertFalse(dok.revisionssicher)

        self.rechnung.refresh_from_db()
        self.assertEqual(self.rechnung.beleg_dokument_id, dok.id)
        # Reverse-Zugriff dokument.rechnung
        self.assertEqual(dok.rechnung, self.rechnung)

    def test_zweite_ablage_auf_derselben_rechnung_wirft_fehler(self):
        lege_rechnungsbeleg_ab(
            self.rechnung, self.datei_bytes, "rechnung-a.pdf", self.objekt, self.user,
        )
        self.rechnung.refresh_from_db()
        with self.assertRaises(ValidationError):
            lege_rechnungsbeleg_ab(
                self.rechnung, self.datei_bytes, "rechnung-b.pdf", self.objekt, self.user,
            )


class KoppelRechnungsbelegTest(TestCase):
    """koppel_rechnungsbeleg: reine Referenz-Übernahme von Rechnung.pfad (v1_1 Phase A)."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="immocore_test_rechnungen_")
        self.addCleanup(shutil.rmtree, self._tmp, ignore_errors=True)
        self.archiv_dir = Path(self._tmp) / "archiv"
        self.archiv_dir.mkdir(parents=True, exist_ok=True)
        ImportOrdnerEinstellung.objects.create(
            bereich="rechnungen", archiv_ordner=str(self.archiv_dir),
        )
        self.root = rechnungen_root()
        self.objekt = _objekt()
        self.user = _user("koppel-tester")

    def _rechnung_mit_datei(self, name="re1.pdf", **kwargs):
        pfad = self.archiv_dir / "2026" / "08" / name
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_bytes(b"%PDF-1.4 Testinhalt")
        return self._create_rechnung(str(pfad), **kwargs)

    def _create_rechnung(self, pfad, sha256="", betrag="1000.00"):
        r = Rechnung.objects.create(
            objekt=self.objekt, pfad=pfad, dateiname=Path(pfad).name,
            sha256_hash=sha256, status="in_pruefung",
            betrag_brutto=Decimal(betrag), rechnungsnummer="RE-KOPPEL-001",
        )
        return r

    def test_koppelt_dokument_korrekt(self):
        r = self._rechnung_mit_datei("re1.pdf", sha256="b" * 64)
        dok = koppel_rechnungsbeleg(r, hochgeladen_von=self.user)

        self.assertEqual(dok.ablage_wurzel, "rechnungen")
        self.assertTrue(dok.datei.name.startswith("archiv/"))
        self.assertFalse(dok.datei.name.startswith("/"))
        self.assertEqual(dok.dokument_typ, "beleg")
        self.assertEqual(dok.kategorie, "Beleg")
        self.assertEqual(dok.verknuepfung_typ, "Rechnung")
        self.assertEqual(dok.sha256, "b" * 64)
        self.assertEqual(dok.objekt_id, self.objekt.id)
        self.assertFalse(dok.revisionssicher)
        self.assertRegex(dok.beleg_nummer, r"^[A-Z]{2}\d{8}$")

        r.refresh_from_db()
        self.assertEqual(r.beleg_dokument_id, dok.id)

    def test_doppelaufruf_wirft_fehler(self):
        r = self._rechnung_mit_datei("re2.pdf")
        koppel_rechnungsbeleg(r, hochgeladen_von=self.user)
        r.refresh_from_db()
        with self.assertRaises(ValidationError):
            koppel_rechnungsbeleg(r, hochgeladen_von=self.user)

    def test_leerer_pfad_wirft_fehler(self):
        r = self._create_rechnung(pfad="")
        with self.assertRaises(ValidationError):
            koppel_rechnungsbeleg(r, hochgeladen_von=self.user)

    def test_fremde_wurzel_wirft_fehler(self):
        r = self._create_rechnung(pfad="/anderswo/rechnung.pdf")
        with self.assertRaises(ValidationError):
            koppel_rechnungsbeleg(r, hochgeladen_von=self.user)


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class DokumentGobdSperreTest(TestCase):
    def setUp(self):
        self.objekt = _objekt()
        self.user = _user("gobd-tester")

    def _dokument(self, revisionssicher=False):
        return Dokument.objects.create(
            datei=ContentFile(b"Inhalt", name="dok.pdf"),
            dateiname="dok.pdf",
            kategorie="Beleg",
            dokument_typ="beleg",
            verknuepfung_typ="Rechnung",
            objekt=self.objekt,
            hochgeladen_von=self.user,
            revisionssicher=revisionssicher,
        )

    def test_nicht_revisionssicheres_dokument_kann_geloescht_werden(self):
        dok = self._dokument(revisionssicher=False)
        dok.delete()
        self.assertFalse(Dokument.objects.filter(pk=dok.pk).exists())

    def test_sperre_setzt_beide_felder(self):
        dok = self._dokument(revisionssicher=False)
        gesperrt = sperre_beleg_revisionssicher(dok)
        self.assertTrue(gesperrt.revisionssicher)
        self.assertIsNotNone(gesperrt.revisionssicher_seit)

    def test_sperre_ist_idempotent(self):
        dok = self._dokument(revisionssicher=False)
        sperre_beleg_revisionssicher(dok)
        dok.refresh_from_db()
        erster_zeitpunkt = dok.revisionssicher_seit

        sperre_beleg_revisionssicher(dok)
        dok.refresh_from_db()
        self.assertEqual(dok.revisionssicher_seit, erster_zeitpunkt)

    def test_revisionssicheres_dokument_delete_wirft_fehler(self):
        dok = self._dokument(revisionssicher=True)
        with self.assertRaises(ValidationError):
            dok.delete()
        self.assertTrue(Dokument.objects.filter(pk=dok.pk).exists())

    def test_revisionssicheres_dokument_datei_austausch_wirft_fehler(self):
        dok = self._dokument(revisionssicher=True)
        dok.datei = ContentFile(b"Anderer Inhalt", name="ausgetauscht.pdf")
        with self.assertRaises(ValidationError):
            dok.save()

    def test_revisionssicheres_dokument_unkritisches_save_bleibt_moeglich(self):
        dok = self._dokument(revisionssicher=True)
        dok.beschreibung = "Neue Notiz"
        dok.save()  # darf keine Exception werfen
        dok.refresh_from_db()
        self.assertEqual(dok.beschreibung, "Neue Notiz")


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class RechnungFreigebenSperrtBelegTest(TestCase):
    """Integration: rechnung_freigeben() muss den gekoppelten Beleg sperren."""

    def setUp(self):
        self.objekt = _objekt()
        self.wj = Wirtschaftsjahr.objects.create(objekt=self.objekt, jahr=2025, beginn_monat=1)
        self.aufwand = Konto.objects.create(
            wirtschaftsjahr=self.wj, kontonummer="50100", kontoname="Hauswartkosten",
            kontoart="standard", direktes_buchen=False,
        )
        Konto.objects.get_or_create(
            wirtschaftsjahr=self.wj, kontonummer="15900",
            defaults={"kontoname": "Schwebende Eingangsrechnungen", "kontoart": "standard", "direktes_buchen": False},
        )
        self.kreditor = Kreditor.objects.create(name="Beleg GmbH", kreditorennummer="70010")
        self.user = _user("freigabe-tester")
        self.rechnung = _rechnung(self.objekt, self.kreditor)
        self.dok = lege_rechnungsbeleg_ab(
            self.rechnung, b"%PDF-1.4 Inhalt", "beleg.pdf", self.objekt, self.user,
        )
        self.rechnung.refresh_from_db()

    def test_freigabe_sperrt_gekoppelten_beleg(self):
        self.assertFalse(self.dok.revisionssicher)
        rechnung_freigeben(self.rechnung, self.aufwand, self.user)
        self.dok.refresh_from_db()
        self.assertTrue(self.dok.revisionssicher)
        self.assertIsNotNone(self.dok.revisionssicher_seit)

    def test_freigabe_ohne_beleg_wirft_keinen_fehler(self):
        rechnung_ohne_beleg = _rechnung(self.objekt, self.kreditor, betrag="200.00")
        rechnung_ohne_beleg.rechnungsnummer = "RE-BELEG-002"
        rechnung_ohne_beleg.save(update_fields=["rechnungsnummer"])
        # Darf nicht crashen, auch wenn kein beleg_dokument gesetzt ist
        rechnung_freigeben(rechnung_ohne_beleg, self.aufwand, self.user)
        rechnung_ohne_beleg.refresh_from_db()
        self.assertEqual(rechnung_ohne_beleg.status, "freigegeben")


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class DokumentApiGobdSperreTest(TestCase):
    """DRF-Absicherung: GoBD-Sperre darf per API nicht umgangen werden können."""

    def setUp(self):
        self.objekt = _objekt()
        self.user = _user("api-tester")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.dok = Dokument.objects.create(
            datei=ContentFile(b"Inhalt", name="api-dok.pdf"),
            dateiname="api-dok.pdf",
            kategorie="Beleg",
            dokument_typ="beleg",
            verknuepfung_typ="Rechnung",
            objekt=self.objekt,
            hochgeladen_von=self.user,
            revisionssicher=True,
        )

    def test_patch_revisionssicher_wird_ignoriert(self):
        resp = self.client.patch(
            reverse("dokumente-detail", args=[self.dok.pk]),
            {"revisionssicher": False},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.dok.refresh_from_db()
        self.assertTrue(self.dok.revisionssicher)

    def test_delete_revisionssicheres_dokument_gibt_400(self):
        resp = self.client.delete(reverse("dokumente-detail", args=[self.dok.pk]))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", resp.data)
        self.assertTrue(Dokument.objects.filter(pk=self.dok.pk).exists())

    def test_patch_neue_datei_gibt_400(self):
        neue_datei = ContentFile(b"Neuer Inhalt", name="neu.pdf")
        resp = self.client.patch(
            reverse("dokumente-detail", args=[self.dok.pk]),
            {"datei": neue_datei},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
