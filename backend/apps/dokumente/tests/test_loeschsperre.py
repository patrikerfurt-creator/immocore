"""
Tests für die Löschsperre geprüfter Belege (API-Vertrag Nachtrag v1.1).

Bezug: docs/API_VERTRAG_BELEGUEBERSICHT_v1_0.md, Nachtrag v1.1.

Deckt ab:
  - DELETE /api/dokumente/{id}/ für Belege mit geprüfter Rechnung (mehrere Status)
    -> 400, nicht 500, Dokument bleibt erhalten.
  - DELETE /api/dokumente/{id}/ für Belege mit ungeprüfter Rechnung -> 400 mit dem
    "zuerst Rechnung entfernen"-Grund (nicht dem Geprüft-Grund).
  - DELETE /api/dokumente/{id}/ ohne Rechnung und nicht revisionssicher -> 204.
  - DELETE /api/dokumente/{id}/ für revisionssicheres Dokument -> 400 (Regression,
    Reihenfolge der Gründe).
  - DELETE /api/rechnungen/{id}/ für jeden Status aus Rechnung.STATUS_GEPRUEFT -> 400;
    für in_buchhaltung/abgelehnt -> 204.
  - DokumentSerializer: loeschbar/loeschsperre_grund für alle vier Konstellationen.
  - Rechnung.delete() und der Django-Admin: die Sperre muss auch dort greifen, wo der
    RechnungViewSet nicht beteiligt ist (Admin unter /admin/, Massenlöschung).
"""
import shutil
import tempfile
from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.dokumente.models import Dokument
from apps.objekte.models import Objekt
from apps.rechnungen.models import Rechnung

User = get_user_model()

_MEDIA_TMP = tempfile.mkdtemp(prefix="immocore_test_media_loeschsperre_")


def tearDownModule():
    shutil.rmtree(_MEDIA_TMP, ignore_errors=True)


def _objekt(nr="B930"):
    return Objekt.objects.create(
        bezeichnung="Test-WEG Löschsperre", objektnummer=nr, objekt_typ="weg",
        ort="Teststadt", verwaltung_seit=timezone.datetime(2020, 1, 1).date(),
    )


def _user(username="loeschsperre-tester"):
    return User.objects.create_user(username=username, password="x")


def _dokument(objekt, user, dateiname, revisionssicher=False):
    return Dokument.objects.create(
        datei=ContentFile(b"Inhalt", name=dateiname),
        dateiname=dateiname,
        kategorie="Beleg",
        dokument_typ="beleg",
        objekt=objekt,
        hochgeladen_von=user,
        revisionssicher=revisionssicher,
        revisionssicher_seit=timezone.now() if revisionssicher else None,
    )


def _rechnung(objekt, beleg, status, betrag=Decimal("100.00")):
    return Rechnung.objects.create(
        objekt=objekt, status=status, betrag_brutto=betrag,
        leistungsbeschreibung="Testleistung", beleg_dokument=beleg,
    )


DOK_URL_NAME = "dokumente-list"
DOK_DETAIL_NAME = "dokumente-detail"
RECHNUNG_DETAIL_NAME = "rechnungen-detail"


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class DokumentLoeschsperreTest(TestCase):
    def setUp(self):
        self.objekt = _objekt()
        self.user = _user()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _delete(self, dokument):
        return self.client.delete(reverse(DOK_DETAIL_NAME, args=[dokument.id]))

    def test_beleg_mit_rechnung_zur_freigabe_nicht_loeschbar(self):
        beleg = _dokument(self.objekt, self.user, "zur-freigabe.pdf")
        _rechnung(self.objekt, beleg, "zur_freigabe")

        resp = self._delete(beleg)

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self.assertIn("error", resp.json())
        self.assertTrue(Dokument.objects.filter(pk=beleg.pk).exists())

    def test_beleg_mit_rechnung_wkz_beleg_nicht_loeschbar(self):
        beleg = _dokument(self.objekt, self.user, "wkz-beleg.pdf")
        _rechnung(self.objekt, beleg, "wkz_beleg")

        resp = self._delete(beleg)

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self.assertTrue(Dokument.objects.filter(pk=beleg.pk).exists())

    def test_beleg_mit_rechnung_in_buchhaltung_gibt_ungeprueft_grund(self):
        """in_buchhaltung ist NICHT in STATUS_GEPRUEFT — die Sperre greift trotzdem,
        aber mit dem 'zuerst Rechnung entfernen'-Grund, nicht dem Geprüft-Grund."""
        beleg = _dokument(self.objekt, self.user, "in-buchhaltung.pdf")
        _rechnung(self.objekt, beleg, "in_buchhaltung")

        resp = self._delete(beleg)

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        fehler = resp.json()["error"]
        self.assertIn("zuerst die Rechnung entfernen", fehler)
        self.assertNotIn("geprüft", fehler)
        self.assertTrue(Dokument.objects.filter(pk=beleg.pk).exists())

    def test_dokument_ohne_rechnung_und_nicht_revisionssicher_loeschbar(self):
        dok = _dokument(self.objekt, self.user, "ohne-rechnung.pdf")

        resp = self._delete(dok)

        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT, resp.content)
        self.assertFalse(Dokument.objects.filter(pk=dok.pk).exists())

    def test_revisionssicheres_dokument_nicht_loeschbar(self):
        """Regression: revisionssicher bleibt die erste, unveränderte Prüfung."""
        dok = _dokument(self.objekt, self.user, "revisionssicher.pdf", revisionssicher=True)

        resp = self._delete(dok)

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self.assertIn("GoBD", resp.json()["error"])
        self.assertTrue(Dokument.objects.filter(pk=dok.pk).exists())


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class RechnungLoeschsperreTest(TestCase):
    def setUp(self):
        self.objekt = _objekt("B931")
        self.user = _user("loeschsperre-rechnung-tester")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _delete(self, rechnung):
        return self.client.delete(reverse(RECHNUNG_DETAIL_NAME, args=[rechnung.id]))

    def test_alle_geprueften_status_nicht_loeschbar(self):
        for s in sorted(Rechnung.STATUS_GEPRUEFT):
            with self.subTest(status=s):
                rechnung = Rechnung.objects.create(
                    objekt=self.objekt, status=s, betrag_brutto=Decimal("50.00"),
                )
                resp = self._delete(rechnung)
                self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
                self.assertIn("error", resp.json())
                self.assertTrue(Rechnung.objects.filter(pk=rechnung.pk).exists())

    def test_ungeprueft_status_loeschbar(self):
        for s in ("in_buchhaltung", "abgelehnt"):
            with self.subTest(status=s):
                rechnung = Rechnung.objects.create(
                    objekt=self.objekt, status=s, betrag_brutto=Decimal("50.00"),
                )
                resp = self._delete(rechnung)
                self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT, resp.content)
                self.assertFalse(Rechnung.objects.filter(pk=rechnung.pk).exists())


class RechnungLoeschsperreModelUndAdminTest(TestCase):
    """Die Sperre muss auch greifen, wo der RechnungViewSet nicht beteiligt ist —
    allen voran der Django-Admin unter /admin/ (Nachtrag v1.1)."""

    def setUp(self):
        self.objekt = _objekt("B933")

    def _rechnung(self, status_):
        return Rechnung.objects.create(
            objekt=self.objekt, status=status_, betrag_brutto=Decimal("50.00"),
        )

    def test_model_delete_blockt_gepruefte_rechnung(self):
        for s in sorted(Rechnung.STATUS_GEPRUEFT):
            with self.subTest(status=s):
                rechnung = self._rechnung(s)
                with self.assertRaises(ValidationError):
                    rechnung.delete()
                self.assertTrue(Rechnung.objects.filter(pk=rechnung.pk).exists())

    def test_model_delete_erlaubt_ungepruefte_rechnung(self):
        rechnung = self._rechnung("in_buchhaltung")
        rechnung.delete()
        self.assertFalse(Rechnung.objects.filter(pk=rechnung.pk).exists())

    def test_admin_verweigert_loeschrecht_fuer_gepruefte_rechnung(self):
        admin_instanz = admin.site._registry[Rechnung]
        anfrage = RequestFactory().get("/admin/")
        anfrage.user = User.objects.create_superuser("admin-loeschsperre", password="x")

        self.assertFalse(admin_instanz.has_delete_permission(anfrage, self._rechnung("bezahlt")))
        self.assertTrue(admin_instanz.has_delete_permission(anfrage, self._rechnung("in_buchhaltung")))

    def test_admin_hat_keine_massenloeschung(self):
        # 'delete_selected' löscht über das QuerySet und würde Rechnung.delete()
        # überspringen — die Aktion muss entfernt sein.
        admin_instanz = admin.site._registry[Rechnung]
        anfrage = RequestFactory().get("/admin/")
        anfrage.user = User.objects.create_superuser("admin-massenloeschung", password="x")

        self.assertNotIn("delete_selected", admin_instanz.get_actions(anfrage))


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class DokumentSerializerLoeschsperreFelderTest(TestCase):
    """loeschbar/loeschsperre_grund über die Dokumente-Liste — alle vier Konstellationen."""

    def setUp(self):
        self.objekt = _objekt("B932")
        self.user = _user("loeschsperre-serializer-tester")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _url(self):
        return reverse(DOK_URL_NAME)

    def _eintrag(self, dateiname):
        daten = self.client.get(self._url()).json()
        treffer = [d for d in daten if d["dateiname"] == dateiname]
        self.assertEqual(len(treffer), 1, daten)
        return treffer[0]

    def test_revisionssicher(self):
        _dokument(self.objekt, self.user, "ser-revisionssicher.pdf", revisionssicher=True)
        eintrag = self._eintrag("ser-revisionssicher.pdf")
        self.assertIs(eintrag["loeschbar"], False)
        self.assertIn("GoBD", eintrag["loeschsperre_grund"])

    def test_geprueft(self):
        beleg = _dokument(self.objekt, self.user, "ser-geprueft.pdf")
        _rechnung(self.objekt, beleg, "freigegeben")
        eintrag = self._eintrag("ser-geprueft.pdf")
        self.assertIs(eintrag["loeschbar"], False)
        self.assertIn("geprüft", eintrag["loeschsperre_grund"])
        self.assertIn("Freigegeben", eintrag["loeschsperre_grund"])

    def test_ungeprueft_mit_rechnung(self):
        beleg = _dokument(self.objekt, self.user, "ser-ungeprueft.pdf")
        _rechnung(self.objekt, beleg, "erfasst")
        eintrag = self._eintrag("ser-ungeprueft.pdf")
        self.assertIs(eintrag["loeschbar"], False)
        self.assertIn("zuerst die Rechnung entfernen", eintrag["loeschsperre_grund"])

    def test_ohne_rechnung(self):
        _dokument(self.objekt, self.user, "ser-ohne-rechnung.pdf")
        eintrag = self._eintrag("ser-ohne-rechnung.pdf")
        self.assertIs(eintrag["loeschbar"], True)
        self.assertIsNone(eintrag["loeschsperre_grund"])
