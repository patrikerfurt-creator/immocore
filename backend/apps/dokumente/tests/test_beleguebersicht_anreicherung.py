"""
Tests für die Belegübersicht-Anreicherung (Arbeitspaket C).

Bezug: docs/CLAUDE_CODE_ANLEITUNG_BELEGUEBERSICHT_ANREICHERUNG_v1_0.md, Abschnitt 7,
und docs/API_VERTRAG_BELEGUEBERSICHT_v1_0.md.

Deckt ab:
  - Vollständig erkannte Rechnung mit Kreditor -> alle sieben Felder korrekt.
  - Fallback auf lieferant_name, wenn kein Kreditor gesetzt ist.
  - kreditor_name/-unbestaetigt, wenn weder Kreditor noch lieferant_name vorhanden sind.
  - Alle sieben Felder None bei dokument_typ != 'beleg'.
  - Alle sieben Felder None bei dokument_typ == 'beleg' ohne verknüpfte Rechnung
    (kein RelatedObjectDoesNotExist).
  - Kürzungsregel für kurztext/kurztext_volltext an der 120-Zeichen-Grenze.
  - Sortierung über rechnung__rechnungsdatum und rechnung__betrag_brutto.
  - Kein N+1 bei wachsender Beleganzahl.
"""
import shutil
import tempfile
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.dokumente.models import Dokument
from apps.dokumente.serializers import KURZTEXT_MAX_LAENGE
from apps.objekte.models import Objekt
from apps.rechnungen.models import Kreditor, Rechnung

User = get_user_model()

_MEDIA_TMP = tempfile.mkdtemp(prefix="immocore_test_media_beleguebersicht_")


def tearDownModule():
    shutil.rmtree(_MEDIA_TMP, ignore_errors=True)


def _objekt(nr="B920"):
    return Objekt.objects.create(
        bezeichnung="Test-WEG Belegübersicht", objektnummer=nr, objekt_typ="weg",
        ort="Teststadt", verwaltung_seit=date(2020, 1, 1),
    )


def _user(username="beleguebersicht-tester"):
    return User.objects.create_user(username=username, password="x")


def _dokument(objekt, user, dateiname, dokument_typ="beleg", kategorie="Beleg"):
    return Dokument.objects.create(
        datei=ContentFile(b"Inhalt", name=dateiname),
        dateiname=dateiname,
        kategorie=kategorie,
        dokument_typ=dokument_typ,
        objekt=objekt,
        hochgeladen_von=user,
    )


LISTE_URL_NAME = "dokumente-list"


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class BeleguebersichtAnreicherungTest(TestCase):
    def setUp(self):
        self.objekt = _objekt()
        self.user = _user()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _url(self):
        return reverse(LISTE_URL_NAME)

    def _eintrag(self, resp, dateiname):
        # Über resp.json() lesen, nicht resp.data: die API_VERTRAG-Typen (Datum als
        # ISO-String, Decimal als String) gelten für die tatsächlich gerenderte
        # JSON-Antwort. resp.data enthält dagegen die rohen Python-Objekte der
        # SerializerMethodFields (date/Decimal) vor dem Rendering.
        daten = resp.json()
        treffer = [d for d in daten if d["dateiname"] == dateiname]
        self.assertEqual(len(treffer), 1, daten)
        return treffer[0]

    # -- Fall 1: vollständig erkannte Rechnung mit gesetztem Kreditor ------

    def test_vollstaendig_erkannte_rechnung_mit_kreditor(self):
        kreditor = Kreditor.objects.create(name="Muster Handwerk GmbH")
        beleg = _dokument(self.objekt, self.user, "voll-erkannt.pdf")
        Rechnung.objects.create(
            objekt=self.objekt,
            kreditor=kreditor,
            rechnungsdatum=date(2026, 3, 15),
            betrag_brutto=Decimal("123.45"),
            leistungsbeschreibung="Wartung Heizungsanlage",
            beleg_dokument=beleg,
        )

        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        eintrag = self._eintrag(resp, "voll-erkannt.pdf")

        self.assertEqual(eintrag["rechnungsdatum"], "2026-03-15")
        self.assertIsNotNone(eintrag["eingangsdatum"])
        self.assertEqual(eintrag["kreditor_name"], kreditor.name)
        self.assertIs(eintrag["kreditor_unbestaetigt"], False)
        # Laut API-Vertrag ein Decimal-STRING, kein JSON-Float: der DRF-JSONEncoder
        # würde einen rohen Decimal aus einem SerializerMethodField als float
        # rendern, deshalb koerziert get_betrag_brutto selbst per str().
        self.assertEqual(eintrag["betrag_brutto"], "123.45")
        self.assertEqual(eintrag["kurztext"], "Wartung Heizungsanlage")

    # -- Fall 2: kein Kreditor, aber lieferant_name gesetzt -----------------

    def test_fallback_auf_lieferant_name(self):
        beleg = _dokument(self.objekt, self.user, "fallback-lieferant.pdf")
        Rechnung.objects.create(
            objekt=self.objekt,
            kreditor=None,
            lieferant_name="Unbekannte Firma KG",
            betrag_brutto=Decimal("50.00"),
            beleg_dokument=beleg,
        )

        resp = self.client.get(self._url())
        eintrag = self._eintrag(resp, "fallback-lieferant.pdf")

        self.assertEqual(eintrag["kreditor_name"], "Unbekannte Firma KG")
        self.assertIs(eintrag["kreditor_unbestaetigt"], True)

    # -- Fall 3: weder Kreditor noch lieferant_name --------------------------

    def test_weder_kreditor_noch_lieferant_name(self):
        beleg = _dokument(self.objekt, self.user, "ohne-kreditor-und-name.pdf")
        Rechnung.objects.create(
            objekt=self.objekt,
            kreditor=None,
            lieferant_name="",
            betrag_brutto=Decimal("10.00"),
            beleg_dokument=beleg,
        )

        resp = self.client.get(self._url())
        eintrag = self._eintrag(resp, "ohne-kreditor-und-name.pdf")

        self.assertIsNone(eintrag["kreditor_name"])
        self.assertIs(eintrag["kreditor_unbestaetigt"], True)

    # -- Fall 4: dokument_typ != 'beleg' -> alle Felder None -----------------

    def test_alle_felder_none_bei_nicht_beleg_typ(self):
        vertrag = _dokument(
            self.objekt, self.user, "vertrag-mit-rechnung.pdf",
            dokument_typ="vertrag", kategorie="Vertrag",
        )
        # Technisch verknüpfte Rechnung — darf trotzdem nicht ausgewertet werden,
        # weil dokument_typ != 'beleg' ist (siehe DokumentSerializer._rechnung).
        Rechnung.objects.create(
            objekt=self.objekt,
            betrag_brutto=Decimal("77.00"),
            rechnungsdatum=date(2026, 1, 1),
            leistungsbeschreibung="Sollte nicht erscheinen",
            beleg_dokument=vertrag,
        )

        resp = self.client.get(self._url())
        eintrag = self._eintrag(resp, "vertrag-mit-rechnung.pdf")

        for feld in (
            "rechnungsdatum", "eingangsdatum", "kreditor_name",
            "kreditor_unbestaetigt", "betrag_brutto", "kurztext", "kurztext_volltext",
        ):
            self.assertIsNone(eintrag[feld], feld)

    # -- Fall 5: dokument_typ == 'beleg' ohne verknüpfte Rechnung ------------

    def test_alle_felder_none_bei_beleg_ohne_rechnung_kein_fehler(self):
        _dokument(self.objekt, self.user, "beleg-ohne-rechnung.pdf")

        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        eintrag = self._eintrag(resp, "beleg-ohne-rechnung.pdf")

        for feld in (
            "rechnungsdatum", "eingangsdatum", "kreditor_name",
            "kreditor_unbestaetigt", "betrag_brutto", "kurztext", "kurztext_volltext",
        ):
            self.assertIsNone(eintrag[feld], feld)

    # -- Fall 6: Kürzungsregel kurztext / kurztext_volltext -------------------

    def _rechnung_mit_text(self, dateiname, text):
        beleg = _dokument(self.objekt, self.user, dateiname)
        Rechnung.objects.create(
            objekt=self.objekt,
            leistungsbeschreibung=text,
            beleg_dokument=beleg,
        )
        return beleg

    def test_kurztext_leere_leistungsbeschreibung(self):
        self._rechnung_mit_text("kurztext-leer.pdf", "")
        resp = self.client.get(self._url())
        eintrag = self._eintrag(resp, "kurztext-leer.pdf")
        self.assertIsNone(eintrag["kurztext"])
        self.assertIsNone(eintrag["kurztext_volltext"])

    def test_kurztext_genau_119_zeichen_unveraendert(self):
        text = "x" * 119
        self._rechnung_mit_text("kurztext-119.pdf", text)
        resp = self.client.get(self._url())
        eintrag = self._eintrag(resp, "kurztext-119.pdf")
        self.assertEqual(eintrag["kurztext"], text)
        self.assertIsNone(eintrag["kurztext_volltext"])

    def test_kurztext_genau_120_zeichen_unveraendert(self):
        text = "x" * KURZTEXT_MAX_LAENGE
        self._rechnung_mit_text("kurztext-120.pdf", text)
        resp = self.client.get(self._url())
        eintrag = self._eintrag(resp, "kurztext-120.pdf")
        self.assertEqual(eintrag["kurztext"], text)
        self.assertEqual(len(eintrag["kurztext"]), 120)
        self.assertIsNone(eintrag["kurztext_volltext"])

    def test_kurztext_121_zeichen_wird_gekuerzt(self):
        text = "x" * (KURZTEXT_MAX_LAENGE + 1)
        self._rechnung_mit_text("kurztext-121.pdf", text)
        resp = self.client.get(self._url())
        eintrag = self._eintrag(resp, "kurztext-121.pdf")
        self.assertEqual(len(eintrag["kurztext"]), 120)
        self.assertTrue(eintrag["kurztext"].endswith("…"))
        self.assertEqual(eintrag["kurztext"], text[:119] + "…")
        self.assertEqual(eintrag["kurztext_volltext"], text)


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class BeleguebersichtSortierungTest(TestCase):
    """Sortierung über rechnung__rechnungsdatum und rechnung__betrag_brutto.

    NULL-Handling ist DB-abhängig: Postgres sortiert NULLs bei ASC zuletzt und
    bei DESC zuerst (so auch im API-Vertrag dokumentiert). Da die Tests aber
    ggf. auf einer anderen Datenbank laufen, wird hier NICHT die absolute
    Position der NULL-Einträge geprüft, sondern nur, dass die Reihenfolge der
    NICHT-NULL-Werte relativ zueinander stimmt.
    """

    def setUp(self):
        self.objekt = _objekt("B921")
        self.user = _user("sortier-tester")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

        # Drei Belege mit unterschiedlichem Rechnungsdatum/Betrag + einer ohne Rechnung.
        beleg_a = _dokument(self.objekt, self.user, "sortier-a.pdf")
        Rechnung.objects.create(
            objekt=self.objekt, rechnungsdatum=date(2026, 1, 10),
            betrag_brutto=Decimal("30.00"), beleg_dokument=beleg_a,
        )
        beleg_b = _dokument(self.objekt, self.user, "sortier-b.pdf")
        Rechnung.objects.create(
            objekt=self.objekt, rechnungsdatum=date(2026, 3, 5),
            betrag_brutto=Decimal("10.00"), beleg_dokument=beleg_b,
        )
        beleg_c = _dokument(self.objekt, self.user, "sortier-c.pdf")
        Rechnung.objects.create(
            objekt=self.objekt, rechnungsdatum=date(2026, 2, 1),
            betrag_brutto=Decimal("20.00"), beleg_dokument=beleg_c,
        )
        # Beleg ohne verknüpfte Rechnung -> rechnungsdatum/betrag_brutto beide None.
        _dokument(self.objekt, self.user, "sortier-ohne-rechnung.pdf")

    def _url(self):
        return reverse(LISTE_URL_NAME)

    def test_sortierung_nach_rechnungsdatum_aufsteigend(self):
        resp = self.client.get(self._url(), {"ordering": "rechnung__rechnungsdatum"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        daten = resp.json()
        werte = [d["rechnungsdatum"] for d in daten if d["rechnungsdatum"] is not None]
        self.assertEqual(werte, sorted(werte))
        self.assertEqual(werte, ["2026-01-10", "2026-02-01", "2026-03-05"])

    def test_sortierung_nach_betrag_brutto_absteigend(self):
        resp = self.client.get(self._url(), {"ordering": "-rechnung__betrag_brutto"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        daten = resp.json()
        # betrag_brutto kommt als Decimal-String (API-Vertrag) — Decimal() darauf ist
        # exakt, ein Umweg über float wäre es nicht.
        werte = [
            Decimal(d["betrag_brutto"]) for d in daten if d["betrag_brutto"] is not None
        ]
        self.assertEqual(werte, sorted(werte, reverse=True))
        self.assertEqual(werte, [Decimal("30.00"), Decimal("20.00"), Decimal("10.00")])


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class BeleguebersichtKeinNPlus1Test(TestCase):
    """Query-Anzahl der Liste muss unabhängig von der Beleganzahl konstant bleiben."""

    def setUp(self):
        self.objekt = _objekt("B922")
        self.user = _user("nplus1-tester")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _url(self):
        return reverse(LISTE_URL_NAME)

    def _erzeuge_belege(self, anzahl, praefix):
        kreditor = Kreditor.objects.create(name=f"Kreditor {praefix}")
        for i in range(anzahl):
            beleg = _dokument(self.objekt, self.user, f"{praefix}-{i}.pdf")
            Rechnung.objects.create(
                objekt=self.objekt,
                kreditor=kreditor,
                rechnungsdatum=date(2026, 1, 1),
                betrag_brutto=Decimal("10.00"),
                leistungsbeschreibung="Testleistung",
                beleg_dokument=beleg,
            )

    def test_query_anzahl_bleibt_konstant(self):
        self._erzeuge_belege(3, "klein")
        with CaptureQueriesContext(connection) as klein:
            resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.assertEqual(len(resp.json()), 3)

        self._erzeuge_belege(10, "gross")
        with CaptureQueriesContext(connection) as gross:
            resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.assertEqual(len(resp.json()), 13)

        self.assertEqual(len(klein.captured_queries), len(gross.captured_queries))
