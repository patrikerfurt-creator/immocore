"""
Pflichttests Umbau Rechnungseingang v1.0 (Spec Kap. 10.1 + 10.2).

Deckt ab (v1.1): objektbasiertes darf_freigeben/route_zur_freigabe,
Match-Regel-Gating (nur Stufe 2 mit Rückfrage), Skonto, clean()-Validierungen,
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
from apps.mitarbeiter.models import Mitarbeiter, MitarbeiterObjektZuordnung
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


def _gf(username):
    """Geschäftsführer (Abteilung) — darf jede Freigabestufe (v1.1)."""
    u = User.objects.create_user(username=username, password="x")
    Mitarbeiter.objects.create(user=u, abteilungen=["geschaeftsfuehrer"])
    return u


def _objektmanager(username, objekt=None):
    """Objektmanagement-Mitarbeiter, optional dem Objekt zugeordnet
    (Stufe-2-Freigeber der Sachbearbeiter-Stufe, v1.1)."""
    u = User.objects.create_user(username=username, password="x")
    m = Mitarbeiter.objects.create(user=u, abteilungen=["objektmanagement"])
    if objekt is not None:
        MitarbeiterObjektZuordnung.objects.create(
            mitarbeiter=m, objekt=objekt, aufgabe="objektmanagement")
    return u


def _buchhalter(username, objekt=None):
    """Buchhaltung, optional dem Objekt zugeordnet (Stufe-1-Inbox, E1)."""
    u = User.objects.create_user(username=username, password="x")
    m = Mitarbeiter.objects.create(user=u, abteilungen=["buchhaltung"])
    if objekt is not None:
        MitarbeiterObjektZuordnung.objects.create(
            mitarbeiter=m, objekt=objekt, aufgabe="buchhaltung")
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
# 11.1 — Stufe-2-Freigabe-Berechtigung (objektbasiert, v1.1)
# ---------------------------------------------------------------------------

class DarfFreigebenTest(TestCase):
    """darf_freigeben läuft über objektbasierte zahlungsfreigabe_grenzen
    (Rolle + Betragsschwelle) — kein persönliches Limit (Spec v1.1 Kap. 5.2)."""

    def setUp(self):
        self.objekt, *_ = _objekt_und_konten()
        self.objekt.zahlungsfreigabe_grenzen = [
            {"bis": 500,  "rolle": "auto",              "frist_tage": 0},
            {"bis": 5000, "rolle": "sachbearbeiter",    "frist_tage": 3},
            {"bis": None, "rolle": "geschaeftsfuehrer", "frist_tage": 5},
        ]
        self.objekt.save(update_fields=["zahlungsfreigabe_grenzen"])
        self.kreditor = Kreditor.objects.create(name="K", kreditorennummer="70001")
        self.om = _objektmanager("om1", objekt=self.objekt)
        self.gf = _gf("gf1")
        self.fremd = _objektmanager("fremd1", objekt=None)   # keinem Objekt zugeordnet

    def _rechnung(self, betrag):
        return Rechnung(objekt=self.objekt, kreditor=self.kreditor,
                        betrag_brutto=Decimal(betrag), rechnungsnummer="RE-1")

    def test_sachbearbeiter_stufe_nur_zugeordnete(self):
        r = self._rechnung("3000")   # sachbearbeiter-Stufe
        self.assertTrue(frs.darf_freigeben(r, self.om))
        self.assertFalse(frs.darf_freigeben(r, self.fremd))

    def test_bagatell_auto_stufe_geht_an_naechste_manuelle(self):
        # B1: auch Bagatellen durch Stufe 2 → zuständig ist die
        # nächste manuelle Stufe (sachbearbeiter)
        r = self._rechnung("250")
        self.assertTrue(frs.darf_freigeben(r, self.om))
        self.assertEqual(frs.freigabestufe_fuer(r).get("rolle"), "sachbearbeiter")

    def test_gf_stufe_nur_gf(self):
        r = self._rechnung("8000")   # geschaeftsfuehrer-Stufe
        self.assertFalse(frs.darf_freigeben(r, self.om))
        self.assertTrue(frs.darf_freigeben(r, self.gf))

    def test_gf_darf_jede_stufe(self):
        self.assertTrue(frs.darf_freigeben(self._rechnung("250"), self.gf))
        self.assertTrue(frs.darf_freigeben(self._rechnung("3000"), self.gf))

    def test_objektbetreuer_darf_sachbearbeiter_stufe(self):
        betreuer = User.objects.create_user(username="betr1", password="x")
        self.objekt.betreuer = betreuer
        self.objekt.save(update_fields=["betreuer"])
        self.assertTrue(frs.darf_freigeben(self._rechnung("3000"), betreuer))

    def test_route_zur_freigabe_setzt_status_und_person(self):
        r = Rechnung.objects.create(
            objekt=self.objekt, kreditor=self.kreditor,
            betrag_brutto=Decimal("3000"), rechnungsnummer="RE-RZF",
            status="in_buchhaltung",
        )
        frs.route_zur_freigabe(r)
        r.refresh_from_db()
        self.assertEqual(r.status, "zur_freigabe")


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

    def test_erfassen_entwurf_bleibt_stufe_1(self):
        u = _buchhalter("erf1", objekt=self.objekt)
        self.client.force_authenticate(u)
        resp = self.client.post(reverse("rechnungen-erfassen"), self._payload("250.00", "entwurf"), format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["status"], "in_buchhaltung")
        self.assertIn(resp.data["erkennung_ampel"], ("gruen", "gelb", "rot"))

    def test_erfassen_zur_freigabe_bucht_nicht(self):
        """v1.1: Stufe 1 bucht NIE — 'zur_freigabe' übergibt an Stufe 2."""
        u = _buchhalter("erf2", objekt=self.objekt)
        self.client.force_authenticate(u)
        resp = self.client.post(reverse("rechnungen-erfassen"), self._payload("250.00", "zur_freigabe"), format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["status"], "zur_freigabe")
        self.assertIsNone(resp.data["op_buchung"])

    def test_erfassen_legacy_modus_freigeben_geht_zur_freigabe(self):
        """v1.0-Legacy-Modus 'freigeben' bucht nicht mehr, sondern eskaliert."""
        u = _buchhalter("erf3", objekt=self.objekt)
        self.client.force_authenticate(u)
        resp = self.client.post(reverse("rechnungen-erfassen"), self._payload("5000.00", "freigeben"), format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["status"], "zur_freigabe")
        self.assertIsNone(resp.data["op_buchung"])

    def test_erfassen_haushaltsnah_ueber_brutto_400(self):
        u = _buchhalter("erf4", objekt=self.objekt)
        self.client.force_authenticate(u)
        payload = self._payload("250.00", "entwurf")
        payload["betrag_haushaltsnah"] = "300.00"
        resp = self.client.post(reverse("rechnungen-erfassen"), payload, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_inbox_zeigt_stufe_1_nicht_stufe_2(self):
        u = _gf("erf5")
        self.client.force_authenticate(u)
        self.client.post(reverse("rechnungen-erfassen"), self._payload("250.00", "entwurf"), format="json")
        self.client.post(reverse("rechnungen-erfassen"), self._payload("5000.00", "zur_freigabe"), format="json")
        resp = self.client.get(reverse("rechnungen-inbox"))
        self.assertEqual(resp.status_code, 200)
        stati = {r["status"] for r in resp.data}
        self.assertEqual(stati, {"in_buchhaltung"})   # zur_freigabe gehört zu Stufe 2
        resp2 = self.client.get(reverse("rechnungen-freigabe-liste"))
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual({r["status"] for r in resp2.data}, {"zur_freigabe"})

    def test_erfassen_gutschrift_zahlweg_splits(self):
        u = _buchhalter("erf7", objekt=self.objekt)
        self.client.force_authenticate(u)
        aufwand2 = Konto.objects.create(
            wirtschaftsjahr=self.aufwand.wirtschaftsjahr, kontonummer="50200",
            kontoname="Reinigung", kontoart="standard", direktes_buchen=False,
        )
        payload = self._payload("250.00", "entwurf")
        payload.update({
            "ist_gutschrift": True,
            "sepa_lastschrift": True,
            "splits": [
                {"aufwandskonto": str(self.aufwand.id), "betrag": "100.00"},
                {"aufwandskonto": str(aufwand2.id), "betrag": "150.00"},
            ],
        })
        resp = self.client.post(reverse("rechnungen-erfassen"), payload, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertTrue(resp.data["ist_gutschrift"])
        self.assertTrue(resp.data["sepa_lastschrift"])
        self.assertEqual(len(resp.data["splits"]), 2)

    def test_erfassen_split_summe_falsch_400(self):
        u = _buchhalter("erf8", objekt=self.objekt)
        self.client.force_authenticate(u)
        aufwand2 = Konto.objects.create(
            wirtschaftsjahr=self.aufwand.wirtschaftsjahr, kontonummer="50200",
            kontoname="Reinigung", kontoart="standard", direktes_buchen=False,
        )
        payload = self._payload("250.00", "entwurf")
        payload["splits"] = [
            {"aufwandskonto": str(self.aufwand.id), "betrag": "100.00"},
            {"aufwandskonto": str(aufwand2.id), "betrag": "100.00"},  # Summe 200 ≠ 250
        ]
        resp = self.client.post(reverse("rechnungen-erfassen"), payload, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_freigeben_endpoint_ohne_berechtigung_403(self):
        # Nicht zugeordneter Objektmanager darf nicht freigeben (objektbasiert)
        u = _objektmanager("erf6", objekt=None)
        self.client.force_authenticate(u)
        r = Rechnung.objects.create(
            objekt=self.objekt, kreditor=self.kreditor, aufwandskonto=self.aufwand,
            betrag_brutto=Decimal("5000.00"), rechnungsnummer="RE-FG", status="zur_freigabe",
        )
        resp = self.client.post(reverse("rechnungen-freigeben", args=[r.id]), {}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_freigeben_endpoint_gf_bucht_op(self):
        # P2: Stufe-2-Freigabe durch GF → freigegeben + OP-Buchung
        u = _gf("erf9")
        self.client.force_authenticate(u)
        r = Rechnung.objects.create(
            objekt=self.objekt, kreditor=self.kreditor, aufwandskonto=self.aufwand,
            betrag_brutto=Decimal("5000.00"), rechnungsnummer="RE-FG2", status="zur_freigabe",
        )
        resp = self.client.post(reverse("rechnungen-freigeben", args=[r.id]), {}, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        r.refresh_from_db()
        self.assertIsNotNone(r.op_buchung_id)


# ---------------------------------------------------------------------------
# 11.1 — Match-Regel: nur Stufe 2, mit Rückfrage (Spec 5.3)
# ---------------------------------------------------------------------------

class MatchRegelStufenTest(TestCase):
    def setUp(self):
        self.objekt, self.aufwand, _ = _objekt_und_konten()
        self.aufwand2 = Konto.objects.create(
            wirtschaftsjahr=self.aufwand.wirtschaftsjahr, kontonummer="50200",
            kontoname="Reinigung", kontoart="standard", direktes_buchen=False,
        )
        self.kreditor = Kreditor.objects.create(name="Test GmbH", kreditorennummer="70001")
        self.gf = _gf("mr_gf")
        self.client = APIClient()

    def _rechnung(self, status_="zur_freigabe"):
        return Rechnung.objects.create(
            objekt=self.objekt, kreditor=self.kreditor, aufwandskonto=self.aufwand,
            betrag_brutto=Decimal("300.00"), rechnungsnummer=f"RE-MR-{status_}",
            leistungstext="Treppenhausreinigung Mai", status=status_,
        )

    def test_stufe2_kontoaenderung_mit_ja_erzeugt_regel(self):
        from apps.rechnungen.models import RechnungsMatchRegel
        r = self._rechnung()
        self.client.force_authenticate(self.gf)
        resp = self.client.post(
            reverse("rechnungen-freigeben", args=[r.id]),
            {"aufwandskonto_id": str(self.aufwand2.id), "lernen": True},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        regel = RechnungsMatchRegel.objects.filter(kreditor=self.kreditor, objekt=self.objekt).first()
        self.assertIsNotNone(regel)
        self.assertEqual(regel.erstellt_aus, "freigabe_korrektur")
        self.assertEqual(regel.aufwandskonto_id, self.aufwand2.id)

    def test_stufe2_kontoaenderung_ohne_ja_keine_regel(self):
        from apps.rechnungen.models import RechnungsMatchRegel
        r = self._rechnung()
        self.client.force_authenticate(self.gf)
        resp = self.client.post(
            reverse("rechnungen-freigeben", args=[r.id]),
            {"aufwandskonto_id": str(self.aufwand2.id)},   # kein lernen → Default False
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(RechnungsMatchRegel.objects.count(), 0)
        r.refresh_from_db()
        self.assertIsNotNone(r.op_buchung_id)   # Freigabe trotzdem abgeschlossen

    def test_stufe1_identifizieren_erzeugt_nie_regel(self):
        from apps.rechnungen.models import RechnungsMatchRegel
        r = self._rechnung(status_="pruefung_match")
        buchhalter = _buchhalter("mr_bh", objekt=self.objekt)
        self.client.force_authenticate(buchhalter)
        resp = self.client.post(
            reverse("rechnungen-identifizieren", args=[r.id]),
            {"kreditor_id": str(self.kreditor.id), "objekt_id": str(self.objekt.id),
             "aufwandskonto_id": str(self.aufwand2.id), "modus": "speichern"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(RechnungsMatchRegel.objects.count(), 0)
        r.refresh_from_db()
        self.assertEqual(r.status, "in_buchhaltung")


# ---------------------------------------------------------------------------
# Inbox-Sichtbarkeit Stufe 1 / Stufe-2-Liste (v1.1)
# ---------------------------------------------------------------------------

class InboxSichtbarkeitTest(TestCase):
    def setUp(self):
        self.objektA, self.aufwand, _ = _objekt_und_konten()
        self.objektB = Objekt.objects.create(
            bezeichnung="Objekt B", objektnummer="T950", objekt_typ="weg",
            ort="X", verwaltung_seit=date(2020, 1, 1),
        )
        self.kreditor = Kreditor.objects.create(name="K", kreditorennummer="70001")
        self.client = APIClient()

        # Stufe 1: A / B / objektlos; Stufe 2: eine kleine + eine große auf B
        self.rA = self._re(self.objektA, "in_buchhaltung", "100")
        self.rB = self._re(self.objektB, "in_buchhaltung", "100")
        self.rNull = self._re(None, "in_buchhaltung", "100")
        self.rFrei = self._re(self.objektB, "zur_freigabe", "500")
        self.rFreiHoch = self._re(self.objektB, "zur_freigabe", "15000")

    def _re(self, objekt, status_, betrag):
        return Rechnung.objects.create(
            objekt=objekt, kreditor=self.kreditor, betrag_brutto=Decimal(betrag),
            rechnungsnummer=f"RE-{status_}-{betrag}-{objekt.objektnummer if objekt else 'x'}",
            status=status_,
        )

    def _inbox_ids(self, user):
        self.client.force_authenticate(user)
        resp = self.client.get(reverse("rechnungen-inbox"))
        self.assertEqual(resp.status_code, 200)
        return {r["id"] for r in resp.data}

    def _freigabe_ids(self, user):
        self.client.force_authenticate(user)
        resp = self.client.get(reverse("rechnungen-freigabe-liste"))
        self.assertEqual(resp.status_code, 200)
        return {r["id"] for r in resp.data}

    def test_gf_sieht_alle_stufe_1(self):
        gf = _gf("gf")
        self.assertEqual(self._inbox_ids(gf),
                         {str(self.rA.id), str(self.rB.id), str(self.rNull.id)})

    def test_buchhaltung_nur_eigene_objekte_plus_objektlos(self):
        bh = _buchhalter("bh", objekt=self.objektA)
        self.assertEqual(self._inbox_ids(bh), {str(self.rA.id), str(self.rNull.id)})

    def test_objektmanager_sieht_stufe_1_nicht(self):
        om = _objektmanager("om", objekt=self.objektB)
        self.assertEqual(self._inbox_ids(om), set())

    def test_freigabe_liste_objektmanager_nur_eigene_stufe(self):
        # Default-Grenzen: auto 500 / objektmanager 5000 / geschaeftsfuehrer None.
        # 500 → auto → nächste manuelle (objektmanager) → OM darf;
        # 15000 → GF-Stufe → OM nicht.
        om = _objektmanager("om2", objekt=self.objektB)
        self.assertEqual(self._freigabe_ids(om), {str(self.rFrei.id)})

    def test_freigabe_liste_gf_sieht_alle(self):
        gf = _gf("gf2")
        self.assertEqual(self._freigabe_ids(gf),
                         {str(self.rFrei.id), str(self.rFreiHoch.id)})
