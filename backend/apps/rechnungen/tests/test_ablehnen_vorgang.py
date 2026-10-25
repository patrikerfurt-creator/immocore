"""
Tests für ``POST /rechnungen/{id}/ablehnen-und-vorgang/`` — Rechnung ablehnen
und in einem Schritt einen Vorgang anlegen, an den der Rechnungsbeleg (PDF)
verknüpft wird.

Deckt ab:
  - Erfolgsfall: Status abgelehnt, Vorgang angelegt, Beleg am Vorgang verknüpft
    (inkl. Verlaufseintrag ``dokument_verknuepft``), Freigabe-Entscheidung + Log.
  - Pflichtfeld Vorgangstyp fehlt → 400, Rechnung NICHT abgelehnt.
  - Gesperrter Status (abgelehnt) → 400.
  - Atomar: schlägt die Vorgangsanlage fehl, bleibt die Rechnung unverändert.
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.dokumente.models import Dokument
from apps.objekte.models import Objekt
from apps.rechnungen.models import Rechnung, Kreditor, Freigabe, Verarbeitungslog
from apps.vorgaenge.models import Vorgang, VorgangTyp, VorgangEreignis

User = get_user_model()


class AblehnenUndVorgangTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="pruefer", password="x")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

        self.objekt = Objekt.objects.create(
            bezeichnung="Test-WEG", objektnummer="T910", objekt_typ="weg",
            ort="Teststadt", verwaltung_seit=date(2020, 1, 1),
        )
        self.kreditor = Kreditor.objects.create(name="Mustermann GmbH")
        self.typ = VorgangTyp.objects.create(code="rklaerung", bezeichnung="Rechnungsklärung")

        self.beleg = Dokument.objects.create(
            datei=SimpleUploadedFile("beleg.pdf", b"%PDF-1.4 test"),
            dateiname="beleg.pdf", titel="Rechnung", kategorie="Beleg",
            dokument_typ="beleg", hochgeladen_von=self.user,
        )
        self.rechnung = Rechnung.objects.create(
            objekt=self.objekt, kreditor=self.kreditor,
            rechnungsnummer="R-1", betrag_brutto="119.00", status="importiert",
            beleg_dokument=self.beleg,
        )

    def _url(self, pk=None):
        return reverse("rechnungen-ablehnen-und-vorgang", kwargs={"pk": pk or self.rechnung.id})

    def test_erfolgsfall_legt_vorgang_an_und_verknuepft_beleg(self):
        resp = self.client.post(self._url(), {
            "typ": str(self.typ.id), "betreff": "Rechnung unklar",
            "beschreibung": "Bitte prüfen", "begruendung": "Position strittig",
        }, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)

        self.rechnung.refresh_from_db()
        self.assertEqual(self.rechnung.status, "abgelehnt")

        vorgang = Vorgang.objects.get(id=resp.data["vorgang_id"])
        self.assertEqual(vorgang.betreff, "Rechnung unklar")
        self.assertEqual(vorgang.objekt_id, self.objekt.id)
        self.assertEqual(resp.data["vorgang_nummer"], vorgang.nummer)

        # Beleg hängt jetzt am Vorgang + Verlaufseintrag
        self.beleg.refresh_from_db()
        self.assertEqual(self.beleg.vorgang_id, vorgang.id)
        self.assertTrue(VorgangEreignis.objects.filter(
            vorgang=vorgang, typ="dokument_verknuepft").exists())

        # Ablehnung ist dokumentiert
        self.assertTrue(Freigabe.objects.filter(
            rechnung=self.rechnung, entscheidung="abgelehnt").exists())
        self.assertTrue(Verarbeitungslog.objects.filter(
            rechnung=self.rechnung, status="abgelehnt").exists())

    def test_fehlender_typ_lehnt_nicht_ab(self):
        resp = self.client.post(self._url(), {"betreff": "x"}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.rechnung.refresh_from_db()
        self.assertEqual(self.rechnung.status, "importiert")
        self.assertFalse(Vorgang.objects.exists())

    def test_gesperrter_status(self):
        self.rechnung.status = "abgelehnt"
        self.rechnung.save(update_fields=["status"])
        resp = self.client.post(self._url(), {
            "typ": str(self.typ.id), "betreff": "x",
        }, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Vorgang.objects.exists())

    def test_atomar_bei_fehler_keine_ablehnung(self):
        # Kein Kontext (Rechnung ohne Objekt, kein objekt_id im Request) → 400,
        # Rechnung bleibt unverändert, kein Vorgang.
        self.rechnung.objekt = None
        self.rechnung.save(update_fields=["objekt"])
        resp = self.client.post(self._url(), {
            "typ": str(self.typ.id), "betreff": "x",
        }, format="json")
        self.assertEqual(resp.status_code, 400)
        self.rechnung.refresh_from_db()
        self.assertEqual(self.rechnung.status, "importiert")
        self.assertFalse(Vorgang.objects.exists())
