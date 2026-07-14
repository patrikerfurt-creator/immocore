"""
Pflichttests Umbau Rechnungseingang v1.0 (Spec Kap. 10.1 + 10.2).

Deckt ab: darf_freigeben/braucht_freigabe, Skonto, clean()-Validierungen,
baue_buchungstext (Debitor), Verifikations-Ampel (feld_konfidenz/gesamt_ampel/
deterministische Validierungen) und die Skonto-Integrationsbuchung.
"""
from decimal import Decimal
from datetime import date, timedelta
from types import SimpleNamespace

from django.test import TestCase, SimpleTestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.objekte.models import Objekt, Wirtschaftsjahr, Einheit
from apps.konten.models import Konto, Personenkonto
from apps.personen.models import Person, EigentumsVerhaeltnis
from apps.mitarbeiter.models import Mitarbeiter
from apps.rechnungen.models import Rechnung, Kreditor
from apps.rechnungen.services import (
    rechnung_freigabe_service as frs,
    erkennung_ampel_service as amp,
)
from apps.rechnungen.services.rechnung_buchungstext_service import baue_buchungstext
from apps.rechnungen.services.rechnung_op_service import rechnung_freigeben
from apps.rechnungen.services.rechnung_zahlung_service import (
    rechnung_bezahlen, skonto_anwendbar,
)

User = get_user_model()

VALID_IBAN = "DE89370400440532013000"   # gültige Prüfziffer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _objekt_und_konten():
    objekt = Objekt.objects.create(
        bezeichnung="Test-WEG", objektnummer="T900", objekt_typ="weg",
        ort="Teststadt", verwaltung_seit=date(2020, 1, 1),
    )
    wj = Wirtschaftsjahr.objects.create(objekt=objekt, jahr=date.today().year, beginn_monat=1)
    aufwand = Konto.objects.create(
        wirtschaftsjahr=wj, kontonummer="50100", kontoname="Hauswartkosten",
        kontoart="standard", direktes_buchen=False,
    )
    bank = Konto.objects.create(
        wirtschaftsjahr=wj, kontonummer="18000", kontoname="Bank",
        kontoart="standard", direktes_buchen=True,
    )
    Konto.objects.get_or_create(
        wirtschaftsjahr=wj, kontonummer="15900",
        defaults={"kontoname": "Schwebende ER", "kontoart": "standard", "direktes_buchen": False},
    )
    Konto.objects.get_or_create(
        wirtschaftsjahr=wj, kontonummer="13600",
        defaults={"kontoname": "Zahlungsausgang", "kontoart": "standard", "direktes_buchen": False},
    )
    return objekt, aufwand, bank


def _user_mit_limit(username, limit):
    u = User.objects.create_user(username=username, password="x")
    Mitarbeiter.objects.create(user=u, freigabe_limit=limit)
    return u


# ---------------------------------------------------------------------------
# 10.1 — reine Funktionen (ohne DB)
# ---------------------------------------------------------------------------

class AmpelPureTest(SimpleTestCase):
    def test_feld_konfidenz_fehler_ist_null(self):
        self.assertEqual(amp.feld_konfidenz(0.99, "fehler"), 0.0)

    def test_feld_konfidenz_ok_ueberstimmt_niedrige_llm(self):
        self.assertGreaterEqual(amp.feld_konfidenz(0.30, "ok"), 0.95)

    def test_feld_konfidenz_warnung_behaelt_llm(self):
        self.assertEqual(amp.feld_konfidenz(0.70, "warnung"), 0.70)

    def test_gesamt_kritisches_fehler_ist_rot(self):
        felder = {
            "kreditor": {"konfidenz": 0.0, "validierung": "fehler"},
            "betrag_brutto": {"konfidenz": 0.99, "validierung": "ok"},
            "rechnungsnummer": {"konfidenz": 0.99, "validierung": "ok"},
        }
        ampel, gesamt = amp.gesamt_ampel(felder)
        self.assertEqual(ampel, "rot")
        self.assertEqual(gesamt, 0.0)

    def test_gesamt_alle_kritisch_gruen(self):
        felder = {
            "kreditor": {"konfidenz": 0.99, "validierung": "ok"},
            "betrag_brutto": {"konfidenz": 0.99, "validierung": "ok"},
            "rechnungsnummer": {"konfidenz": 0.99, "validierung": "ok"},
        }
        ampel, gesamt = amp.gesamt_ampel(felder)
        self.assertEqual(ampel, "gruen")
        self.assertGreaterEqual(gesamt, 95)

    def test_gesamt_ist_minimum_nicht_mittelwert(self):
        # krit. Felder 100/100/85 → gelb bei 85, NICHT grün bei 95er-Schnitt
        felder = {
            "kreditor": {"konfidenz": 1.0, "validierung": "ok"},
            "betrag_brutto": {"konfidenz": 1.0, "validierung": "ok"},
            "rechnungsnummer": {"konfidenz": 0.85, "validierung": "keine"},
        }
        ampel, gesamt = amp.gesamt_ampel(felder)
        self.assertEqual(gesamt, 85.0)
        self.assertEqual(ampel, "gelb")

    def test_gesamt_ein_gelbes_feld_deckelt_auf_gelb(self):
        felder = {
            "kreditor": {"konfidenz": 1.0, "validierung": "ok"},
            "betrag_brutto": {"konfidenz": 1.0, "validierung": "ok"},
            "rechnungsnummer": {"konfidenz": 1.0, "validierung": "ok"},
            "rechnungsdatum": {"konfidenz": 0.85, "validierung": "warnung"},
        }
        ampel, _ = amp.gesamt_ampel(felder)
        self.assertEqual(ampel, "gelb")

    def test_iban_pruefziffer(self):
        self.assertTrue(amp.iban_gueltig(VALID_IBAN))
        self.assertFalse(amp.iban_gueltig("DE00370400440532013000"))
        self.assertFalse(amp.iban_gueltig("Quatsch"))

    def test_rechenprobe_kippt_ist_fehler(self):
        v, _ = amp.validiere_betrag_brutto(brutto="200", netto="100", ust_betrag="10")
        self.assertEqual(v, "fehler")
        v, _ = amp.validiere_betrag_brutto(brutto="119", netto="100", ust_betrag="19")
        self.assertEqual(v, "ok")


class SkontoPureTest(SimpleTestCase):
    def _rechnung(self, betrag, faellig):
        return SimpleNamespace(
            skonto_betrag=betrag, skonto_faellig_bis=faellig, skonto_genutzt=False,
            betrag_brutto=Decimal("1000"),
        )

    def test_skonto_anwendbar_an_fristgrenze(self):
        frist = date(2026, 8, 1)
        r = self._rechnung(Decimal("20"), frist)
        self.assertTrue(skonto_anwendbar(r, frist))            # == Frist → True
        self.assertFalse(skonto_anwendbar(r, frist + timedelta(days=1)))  # +1 Tag → False

    def test_skonto_ohne_betrag_nicht_anwendbar(self):
        r = self._rechnung(None, date(2026, 8, 1))
        self.assertFalse(skonto_anwendbar(r, date(2026, 7, 1)))


# ---------------------------------------------------------------------------
# 10.1 — Freigabe-Berechtigung
# ---------------------------------------------------------------------------

class DarfFreigebenTest(TestCase):
    def setUp(self):
        self.objekt, *_ = _objekt_und_konten()
        self.kreditor = Kreditor.objects.create(name="K", kreditorennummer="70001")

    def _rechnung(self, betrag):
        return Rechnung(objekt=self.objekt, kreditor=self.kreditor,
                        betrag_brutto=Decimal(betrag), rechnungsnummer="RE-1")

    def test_limit_none_keine_berechtigung(self):
        u = User.objects.create_user(username="ohne", password="x")
        Mitarbeiter.objects.create(user=u, freigabe_limit=None)
        self.assertFalse(frs.darf_freigeben(self._rechnung("100"), u))

    def test_betrag_gleich_limit_erlaubt(self):
        u = _user_mit_limit("gleich", Decimal("500"))
        self.assertTrue(frs.darf_freigeben(self._rechnung("500"), u))

    def test_betrag_ueber_limit_verboten(self):
        u = _user_mit_limit("drueber", Decimal("500"))
        self.assertFalse(frs.darf_freigeben(self._rechnung("500.01"), u))

    def test_braucht_freigabe_bagatell(self):
        self.objekt.zahlungsfreigabe_grenzen = [
            {"bis": 500, "rolle": "auto"}, {"bis": None, "rolle": "gf"},
        ]
        self.assertFalse(frs.braucht_freigabe(self._rechnung("500")))     # == Bagatell
        self.assertTrue(frs.braucht_freigabe(self._rechnung("500.01")))   # darüber


# ---------------------------------------------------------------------------
# 10.1 — clean()-Validierungen
# ---------------------------------------------------------------------------

class CleanTest(TestCase):
    def setUp(self):
        self.objekt, *_ = _objekt_und_konten()
        self.objekt2 = Objekt.objects.create(
            bezeichnung="Fremd", objektnummer="T901", objekt_typ="weg",
            ort="X", verwaltung_seit=date(2020, 1, 1),
        )

    def test_haushaltsnah_groesser_brutto(self):
        r = Rechnung(objekt=self.objekt, betrag_brutto=Decimal("100"),
                     betrag_haushaltsnah=Decimal("150"))
        with self.assertRaises(ValidationError) as cm:
            r.clean()
        self.assertIn("betrag_haushaltsnah", cm.exception.message_dict)

    def test_skonto_ohne_frist(self):
        r = Rechnung(objekt=self.objekt, betrag_brutto=Decimal("1000"),
                     skonto_prozent=Decimal("2"))
        with self.assertRaises(ValidationError) as cm:
            r.clean()
        self.assertIn("skonto_faellig_bis", cm.exception.message_dict)

    def test_kostenverursacher_fremdes_objekt(self):
        einheit = Einheit.objects.create(
            objekt=self.objekt2, einheit_nr="WE1", einheit_typ="Wohnung", lage="EG",
        )
        r = Rechnung(objekt=self.objekt, betrag_brutto=Decimal("100"),
                     kostenverursacher=einheit)
        with self.assertRaises(ValidationError) as cm:
            r.clean()
        self.assertIn("kostenverursacher", cm.exception.message_dict)


# ---------------------------------------------------------------------------
# 10.1 — baue_buchungstext + Debitornummer
# ---------------------------------------------------------------------------

class BuchungstextTest(TestCase):
    def setUp(self):
        self.objekt, *_ = _objekt_und_konten()
        self.kreditor = Kreditor.objects.create(name="Handwerk GmbH", kreditorennummer="70001")
        self.einheit = Einheit.objects.create(
            objekt=self.objekt, einheit_nr="WE05", einheit_typ="Wohnung", lage="1.OG links",
        )
        self.person = Person.objects.create(
            person_typ="100", personennummer="P1", vorname="Max", nachname="Müller",
        )
        self.ev = EigentumsVerhaeltnis.objects.create(
            einheit=self.einheit, person=self.person, beginn=date(2017, 1, 1), ende=None,
        )
        # Personenkonto wird per Signal automatisch zum EV angelegt → holen + Kontonummer setzen
        pk, _ = Personenkonto.objects.get_or_create(
            vertrag=self.ev,
            defaults={"objekt": self.objekt, "eigentuemer": self.person, "kontonummer": "0005"},
        )
        pk.kontonummer = "0005"
        pk.save(update_fields=["kontonummer"])

    def test_ohne_kostenverursacher(self):
        r = Rechnung(objekt=self.objekt, kreditor=self.kreditor, rechnungsnummer="RE-7")
        text = baue_buchungstext(r)
        self.assertEqual(text, "OP Rechnung RE-7 – Handwerk GmbH")

    def test_mit_kostenverursacher_enthaelt_debitor(self):
        r = Rechnung(objekt=self.objekt, kreditor=self.kreditor, rechnungsnummer="RE-8",
                     kostenverursacher=self.einheit, rechnungsdatum=date(2026, 6, 1))
        text = baue_buchungstext(r)
        self.assertIn("PKto 0005", text)
        self.assertIn("WE05", text)
        self.assertIn("Max Müller", text)


# ---------------------------------------------------------------------------
# 10.1 — deterministische Validierungen mit Stammdaten
# ---------------------------------------------------------------------------

class ValidierungDBTest(TestCase):
    def setUp(self):
        self.objekt, *_ = _objekt_und_konten()

    def test_kreditor_iban_in_stammdaten_ok(self):
        Kreditor.objects.create(name="K", kreditorennummer="70001", iban=VALID_IBAN)
        v, _ = amp.validiere_kreditor(VALID_IBAN)
        self.assertEqual(v, "ok")

    def test_kreditor_iban_gueltig_aber_unbekannt_warnung(self):
        v, _ = amp.validiere_kreditor(VALID_IBAN)
        self.assertEqual(v, "warnung")

    def test_rechnungsnummer_duplikat_fehler(self):
        k = Kreditor.objects.create(name="K", kreditorennummer="70002")
        Rechnung.objects.create(objekt=self.objekt, kreditor=k,
                                betrag_brutto=Decimal("10"), rechnungsnummer="DUP-1")
        v, _ = amp.validiere_rechnungsnummer("DUP-1", kreditor_id=k.id)
        self.assertEqual(v, "fehler")
        v, _ = amp.validiere_rechnungsnummer("NEU-1", kreditor_id=k.id)
        self.assertEqual(v, "ok")


# ---------------------------------------------------------------------------
# 10.2 — Integration: Skonto-Zahlung
# ---------------------------------------------------------------------------

class SkontoIntegrationTest(TestCase):
    def setUp(self):
        self.objekt, self.aufwand, self.bank = _objekt_und_konten()
        self.kreditor = Kreditor.objects.create(name="Test GmbH", kreditorennummer="70001")
        self.user = User.objects.create_user(username="bh", password="x")

    def _freigegebene_rechnung(self):
        r = Rechnung.objects.create(
            objekt=self.objekt, kreditor=self.kreditor, betrag_brutto=Decimal("1000.00"),
            rechnungsnummer="RE-SK", status="in_pruefung",
            skonto_prozent=Decimal("2"), skonto_betrag=Decimal("20.00"),
            skonto_faellig_bis=date.today() + timedelta(days=14),
        )
        rechnung_freigeben(r, self.aufwand, self.user)
        r.refresh_from_db()
        return r

    def test_zahlung_innerhalb_frist_zieht_skonto(self):
        r = self._freigegebene_rechnung()
        bu_aufwand, _ = rechnung_bezahlen(r, date.today() + timedelta(days=10), self.user)
        r.refresh_from_db()
        self.assertTrue(r.skonto_genutzt)
        self.assertEqual(bu_aufwand.betrag, Decimal("980.00"))   # Aufwand = Zahlbetrag
        # Skonto-Buchung Soll 70xxx / Haben 15900 über 20,00 existiert
        from apps.buchhaltung.models import Buchung
        skonto_bu = Buchung.objects.filter(
            objekt=self.objekt, betrag=Decimal("20.00"), buchungstext__contains="Skonto",
        ).first()
        self.assertIsNotNone(skonto_bu)
        self.assertEqual(skonto_bu.haben_konto.kontonummer, "15900")
        # Kein Ertragskonto (4xxxx) berührt
        self.assertFalse(
            Buchung.objects.filter(objekt=self.objekt, soll_konto__kontonummer__startswith="4").exists()
            or Buchung.objects.filter(objekt=self.objekt, haben_konto__kontonummer__startswith="4").exists()
        )

    def test_zahlung_ausserhalb_frist_kein_skonto(self):
        r = self._freigegebene_rechnung()
        bu_aufwand, _ = rechnung_bezahlen(r, date.today() + timedelta(days=20), self.user)
        r.refresh_from_db()
        self.assertFalse(r.skonto_genutzt)
        self.assertEqual(bu_aufwand.betrag, Decimal("1000.00"))


# ---------------------------------------------------------------------------
# 10.2 — Integration: Erfassen/Inbox/Freigabe-Endpunkte
# ---------------------------------------------------------------------------

class ErfassenApiTest(TestCase):
    def setUp(self):
        self.objekt, self.aufwand, self.bank = _objekt_und_konten()
        self.kreditor = Kreditor.objects.create(name="Test GmbH", kreditorennummer="70001")
        self.client = APIClient()

    def _payload(self, betrag, modus):
        return {
            "objekt_id": str(self.objekt.id),
            "kreditor_id": str(self.kreditor.id),
            "aufwandskonto_id": str(self.aufwand.id),
            "rechnungsnummer": f"RE-{betrag}-{modus}",
            "rechnungsdatum": date.today().isoformat(),
            "betrag_netto": "100.00",
            "betrag_brutto": str(betrag),
            "mwst_satz": "19",
            "modus": modus,
        }

    def test_erfassen_entwurf(self):
        u = _user_mit_limit("erf1", Decimal("500"))
        self.client.force_authenticate(u)
        resp = self.client.post(reverse("rechnungen-erfassen"), self._payload("250.00", "entwurf"), format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["status"], "erfasst")
        self.assertIn(resp.data["erkennung_ampel"], ("gruen", "gelb", "rot"))

    def test_erfassen_freigeben_im_limit_bucht_op(self):
        u = _user_mit_limit("erf2", Decimal("500"))
        self.client.force_authenticate(u)
        resp = self.client.post(reverse("rechnungen-erfassen"), self._payload("250.00", "freigeben"), format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["status"], "gebucht")     # OP gebucht (Enum-Rename → Phase D)
        self.assertIsNotNone(resp.data["op_buchung"])

    def test_erfassen_freigeben_ueber_limit_eskaliert(self):
        u = _user_mit_limit("erf3", Decimal("500"))
        self.client.force_authenticate(u)
        resp = self.client.post(reverse("rechnungen-erfassen"), self._payload("5000.00", "freigeben"), format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["status"], "in_freigabe")

    def test_erfassen_haushaltsnah_ueber_brutto_400(self):
        u = _user_mit_limit("erf4", Decimal("500"))
        self.client.force_authenticate(u)
        payload = self._payload("250.00", "entwurf")
        payload["betrag_haushaltsnah"] = "300.00"
        resp = self.client.post(reverse("rechnungen-erfassen"), payload, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_inbox_listet_offene(self):
        u = _user_mit_limit("erf5", Decimal("500"))
        self.client.force_authenticate(u)
        self.client.post(reverse("rechnungen-erfassen"), self._payload("250.00", "entwurf"), format="json")
        self.client.post(reverse("rechnungen-erfassen"), self._payload("5000.00", "zur_freigabe"), format="json")
        resp = self.client.get(reverse("rechnungen-inbox"))
        self.assertEqual(resp.status_code, 200)
        stati = {r["status"] for r in resp.data}
        self.assertTrue(stati <= {"erfasst", "in_freigabe"})
        self.assertEqual(len(resp.data), 2)

    def test_freigeben_endpoint_ueber_limit_403(self):
        u = _user_mit_limit("erf6", Decimal("100"))
        self.client.force_authenticate(u)
        r = Rechnung.objects.create(
            objekt=self.objekt, kreditor=self.kreditor, aufwandskonto=self.aufwand,
            betrag_brutto=Decimal("5000.00"), rechnungsnummer="RE-FG", status="in_freigabe",
        )
        resp = self.client.post(reverse("rechnungen-freigeben", args=[r.id]), {}, format="json")
        self.assertEqual(resp.status_code, 403)
