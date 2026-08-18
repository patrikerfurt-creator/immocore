"""
Tests für die minimale DMS-Lesezugriff-API (Phase D, Spec Abschnitt 7).

Deckt ab:
  - GET /objekte/{id}/dokumente/: nur Dokumente des Objekts, typ-Filter,
    rechnung_nummer gefüllt bzw. null
  - Unauthentifiziert -> 401
  - GET /dokumente/{id}/datei/: liefert Bytes mit korrektem Content-Type
    für media- UND rechnungen-Wurzel; fehlende Datei -> 404
"""
import shutil
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.buchhaltung.models import ImportOrdnerEinstellung
from apps.dokumente.models import Dokument
from apps.objekte.models import Objekt
from apps.rechnungen.models import Rechnung

User = get_user_model()

_MEDIA_TMP = tempfile.mkdtemp(prefix="immocore_test_media_objdok_")


def tearDownModule():
    shutil.rmtree(_MEDIA_TMP, ignore_errors=True)


def _objekt(nr="B910"):
    return Objekt.objects.create(
        bezeichnung="Test-WEG Dokumente", objektnummer=nr, objekt_typ="weg",
        ort="Teststadt", verwaltung_seit=date(2020, 1, 1),
    )


def _user(username="dms-tester"):
    return User.objects.create_user(username=username, password="x")


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class ObjektDokumenteListeTest(TestCase):
    def setUp(self):
        self.objekt = _objekt()
        self.anderes_objekt = _objekt("B911")
        self.user = _user()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

        self.beleg = Dokument.objects.create(
            datei=ContentFile(b"Inhalt", name="beleg.pdf"),
            dateiname="beleg.pdf",
            kategorie="Beleg",
            dokument_typ="beleg",
            objekt=self.objekt,
            hochgeladen_von=self.user,
        )
        self.vertrag = Dokument.objects.create(
            datei=ContentFile(b"Inhalt", name="vertrag.pdf"),
            dateiname="vertrag.pdf",
            kategorie="Vertrag",
            dokument_typ="vertrag",
            objekt=self.objekt,
            hochgeladen_von=self.user,
        )
        # Dokument eines anderen Objekts darf nicht in der Liste erscheinen
        Dokument.objects.create(
            datei=ContentFile(b"Inhalt", name="fremd.pdf"),
            dateiname="fremd.pdf",
            kategorie="Beleg",
            dokument_typ="beleg",
            objekt=self.anderes_objekt,
            hochgeladen_von=self.user,
        )

        self.rechnung = Rechnung.objects.create(
            objekt=self.objekt, betrag_brutto=Decimal("100.00"),
            rechnungsnummer="RE-DMS-001", status="in_pruefung",
            beleg_dokument=self.beleg,
        )

    def _url(self):
        return reverse("objekte-dokumente", args=[self.objekt.pk])

    def test_liste_enthaelt_nur_dokumente_des_objekts(self):
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        dateinamen = {d["dateiname"] for d in resp.data}
        self.assertEqual(dateinamen, {"beleg.pdf", "vertrag.pdf"})

    def test_typ_filter_wirkt(self):
        resp = self.client.get(self._url(), {"typ": "beleg"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual([d["dateiname"] for d in resp.data], ["beleg.pdf"])

    def test_rechnung_nummer_gefuellt_bei_gekoppeltem_beleg(self):
        resp = self.client.get(self._url(), {"typ": "beleg"})
        eintrag = resp.data[0]
        self.assertEqual(eintrag["rechnung_nummer"], "RE-DMS-001")
        self.assertEqual(eintrag["rechnung_id"], str(self.rechnung.id))

    def test_rechnung_nummer_null_ohne_kopplung(self):
        resp = self.client.get(self._url(), {"typ": "vertrag"})
        eintrag = resp.data[0]
        self.assertIsNone(eintrag["rechnung_nummer"])
        self.assertIsNone(eintrag["rechnung_id"])

    def test_unauthentifiziert_gibt_401(self):
        client = APIClient()
        resp = client.get(self._url())
        self.assertIn(resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class DokumentDateiEndpointTest(TestCase):
    def setUp(self):
        self.objekt = _objekt("B912")
        self.user = _user("datei-tester")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _url(self, dok):
        return reverse("dokumente-datei", args=[dok.pk])

    def test_media_wurzel_liefert_bytes_mit_content_type(self):
        dok = Dokument.objects.create(
            datei=ContentFile(b"%PDF-1.4 Inhalt", name="media-beleg.pdf"),
            dateiname="media-beleg.pdf",
            kategorie="Beleg",
            dokument_typ="beleg",
            objekt=self.objekt,
            hochgeladen_von=self.user,
            ablage_wurzel="media",
        )
        resp = self.client.get(self._url(dok))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        inhalt = b"".join(resp.streaming_content)
        self.assertEqual(inhalt, b"%PDF-1.4 Inhalt")

    def test_rechnungen_wurzel_liefert_bytes(self):
        tmp = tempfile.mkdtemp(prefix="immocore_test_rechnungen_objdok_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        archiv_dir = Path(tmp) / "archiv"
        archiv_dir.mkdir(parents=True, exist_ok=True)
        ImportOrdnerEinstellung.objects.create(bereich="rechnungen", archiv_ordner=str(archiv_dir))

        relativ = "2026/08/rechnungen-wurzel-beleg.png"
        (Path(tmp) / relativ).parent.mkdir(parents=True, exist_ok=True)
        (Path(tmp) / relativ).write_bytes(b"\x89PNG Testinhalt")

        dok = Dokument.objects.create(
            datei=relativ,
            dateiname="rechnungen-wurzel-beleg.png",
            kategorie="Beleg",
            dokument_typ="beleg",
            objekt=self.objekt,
            hochgeladen_von=self.user,
            ablage_wurzel="rechnungen",
        )
        resp = self.client.get(self._url(dok))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp["Content-Type"], "image/png")
        inhalt = b"".join(resp.streaming_content)
        self.assertEqual(inhalt, b"\x89PNG Testinhalt")

    def test_fehlende_datei_gibt_404(self):
        dok = Dokument.objects.create(
            datei="dokumente/nicht-vorhanden.pdf",
            dateiname="nicht-vorhanden.pdf",
            kategorie="Beleg",
            dokument_typ="beleg",
            objekt=self.objekt,
            hochgeladen_von=self.user,
            ablage_wurzel="media",
        )
        resp = self.client.get(self._url(dok))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error", resp.data)
