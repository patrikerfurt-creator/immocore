"""
Tests für die zentrale Rechnungs-Beleg-Pfadauflösung (v1_1 Phase B).

Deckt ab:
  - rechnung_datei_pfad(): Beleg-Dokument bevorzugt vor Alt-Feld pfad,
    Fallback auf pfad ohne Kopplung, None ohne beides
  - PDF-Endpoint: liefert Bytes über Beleg-Dokument bzw. Alt-Feld pfad,
    404 ohne beides, 401/403 unauthentifiziert
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
from apps.rechnungen.services.rechnung_datei_service import rechnung_datei_pfad

User = get_user_model()

_MEDIA_TMP = tempfile.mkdtemp(prefix="immocore_test_media_rds_")


def tearDownModule():
    shutil.rmtree(_MEDIA_TMP, ignore_errors=True)


def _objekt(nr="B950"):
    return Objekt.objects.create(
        bezeichnung="Test-WEG Dateipfad", objektnummer=nr, objekt_typ="weg",
        ort="Teststadt", verwaltung_seit=date(2020, 1, 1),
    )


def _user(username="dateipfad-tester"):
    return User.objects.create_user(username=username, password="x")


def _rechnung(objekt, pfad="", beleg_dokument=None):
    return Rechnung.objects.create(
        objekt=objekt, pfad=pfad, dateiname=Path(pfad).name if pfad else "",
        status="importiert", betrag_brutto=Decimal("100.00"),
        beleg_dokument=beleg_dokument,
    )


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class RechnungDateiPfadTest(TestCase):
    """Unit-Tests der reinen Pfadauflösung (ohne HTTP)."""

    def setUp(self):
        self.objekt = _objekt()
        self.user = _user()

    def test_gekoppeltes_dokument_gewinnt_auch_bei_gesetztem_pfad(self):
        dok = Dokument.objects.create(
            datei=ContentFile(b"%PDF-1.4 Beleg", name="beleg.pdf"),
            dateiname="beleg.pdf", kategorie="Beleg", dokument_typ="beleg",
            objekt=self.objekt,
            hochgeladen_von=self.user, ablage_wurzel="media",
        )
        rechnung = _rechnung(self.objekt, pfad="/app/rechnungen/altablage.pdf", beleg_dokument=dok)

        pfad = rechnung_datei_pfad(rechnung)

        self.assertEqual(pfad, Path(_MEDIA_TMP) / dok.datei.name)

    def test_ohne_kopplung_faellt_auf_pfad_zurueck(self):
        rechnung = _rechnung(self.objekt, pfad="/app/rechnungen/nachzuegler.pdf")

        pfad = rechnung_datei_pfad(rechnung)

        self.assertEqual(pfad, Path("/app/rechnungen/nachzuegler.pdf"))

    def test_ohne_kopplung_und_ohne_pfad_liefert_none(self):
        rechnung = _rechnung(self.objekt)

        self.assertIsNone(rechnung_datei_pfad(rechnung))


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class RechnungPdfEndpointTest(TestCase):
    """API-Tests des 'pdf'-Actions (bevorzugt Beleg-Dokument, Fallback pfad)."""

    def setUp(self):
        self.objekt = _objekt("B951")
        self.user = _user("pdf-endpoint-tester")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _url(self, rechnung):
        return reverse("rechnungen-pdf", args=[rechnung.pk])

    def test_gekoppeltes_dokument_liefert_bytes(self):
        dok = Dokument.objects.create(
            datei=ContentFile(b"%PDF-1.4 Inhalt gekoppelt", name="gekoppelt.pdf"),
            dateiname="gekoppelt.pdf", kategorie="Beleg", dokument_typ="beleg",
            objekt=self.objekt,
            hochgeladen_von=self.user, ablage_wurzel="media",
        )
        rechnung = _rechnung(self.objekt, beleg_dokument=dok)

        resp = self.client.get(self._url(rechnung))

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        inhalt = b"".join(resp.streaming_content)
        self.assertEqual(inhalt, b"%PDF-1.4 Inhalt gekoppelt")

    def test_nur_pfad_rechnung_liefert_bytes(self):
        tmp = tempfile.mkdtemp(prefix="immocore_test_rechnungen_pdf_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        archiv_dir = Path(tmp) / "archiv"
        archiv_dir.mkdir(parents=True, exist_ok=True)
        ImportOrdnerEinstellung.objects.create(bereich="rechnungen", archiv_ordner=str(archiv_dir))

        datei = Path(tmp) / "nachzuegler.pdf"
        datei.write_bytes(b"%PDF-1.4 Inhalt Nachzuegler")
        rechnung = _rechnung(self.objekt, pfad=str(datei))

        resp = self.client.get(self._url(rechnung))

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        inhalt = b"".join(resp.streaming_content)
        self.assertEqual(inhalt, b"%PDF-1.4 Inhalt Nachzuegler")

    def test_ohne_beleg_und_pfad_gibt_404(self):
        rechnung = _rechnung(self.objekt)

        resp = self.client.get(self._url(rechnung))

        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthentifiziert_gibt_401_oder_403(self):
        rechnung = _rechnung(self.objekt)
        client = APIClient()

        resp = client.get(self._url(rechnung))

        self.assertIn(resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
