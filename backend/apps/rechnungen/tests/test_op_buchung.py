"""
Pflichttests für den 3-Phasen OP-Buchung-Workflow (§28 WEG).

Phase 1 – Freigabe:   Soll 15900 / Haben Kreditorenkonto (70xxx) + KreditorOP JJNNNNNN
Phase 2 – Zahlung:    Soll Aufwand / Haben 15900  +  Soll Kreditor / Haben 13600
Phase 3 – Bank:       Soll 13600 / Haben Bank
"""
from decimal import Decimal
from datetime import date
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.objekte.models import Objekt, Wirtschaftsjahr
from apps.konten.models import Konto
from apps.buchhaltung.models import KreditorOP
from apps.rechnungen.models import Rechnung, Kreditor
from apps.rechnungen.services.rechnung_op_service import rechnung_freigeben
from apps.rechnungen.services.rechnung_zahlung_service import rechnung_bezahlen, bank_abgang_buchen

User = get_user_model()


def _objekt_und_konten():
    objekt = Objekt.objects.create(
        bezeichnung="Test-WEG",
        objektnummer="T001",
        objekt_typ="weg",
        ort="Teststadt",
        verwaltung_seit=date(2020, 1, 1),
    )
    wj = Wirtschaftsjahr.objects.create(objekt=objekt, jahr=2025, beginn_monat=1)
    aufwand = Konto.objects.create(
        wirtschaftsjahr=wj, kontonummer="50100", kontoname="Hauswartkosten",
        kontoart="standard", direktes_buchen=False,
    )
    bank = Konto.objects.create(
        wirtschaftsjahr=wj, kontonummer="18000", kontoname="Bank",
        kontoart="standard", direktes_buchen=True,
    )
    konto_15900, _ = Konto.objects.get_or_create(
        wirtschaftsjahr=wj, kontonummer="15900",
        defaults={"kontoname": "Schwebende Eingangsrechnungen", "kontoart": "standard", "direktes_buchen": False},
    )
    konto_13600, _ = Konto.objects.get_or_create(
        wirtschaftsjahr=wj, kontonummer="13600",
        defaults={"kontoname": "Schwebender Zahlungsausgang", "kontoart": "standard", "direktes_buchen": False},
    )
    return objekt, aufwand, bank, konto_15900, konto_13600


def _kreditor(nummer="70001"):
    return Kreditor.objects.create(name="Test GmbH", kreditorennummer=nummer)


def _rechnung(objekt, kreditor, betrag="1000.00", status="in_pruefung"):
    return Rechnung.objects.create(
        objekt=objekt, kreditor=kreditor,
        betrag_brutto=Decimal(betrag),
        rechnungsnummer="RE-001",
        status=status,
    )


def _user():
    return User.objects.create_user(username="tester", password="x")


class FreigebenTest(TestCase):
    def setUp(self):
        self.objekt, self.aufwand, self.bank, self.konto_15900, self.konto_13600 = _objekt_und_konten()
        self.kreditor = _kreditor()
        self.user = _user()

    def test_1_freigabe_buchung_soll_15900_haben_kreditor(self):
        r = _rechnung(self.objekt, self.kreditor)
        rechnung_freigeben(r, self.aufwand, self.user)
        r.refresh_from_db()
        self.assertEqual(r.status, "gebucht")
        self.assertIsNotNone(r.op_buchung_id)
        # Soll: 15900 / Haben: Kreditorenkonto
        self.assertEqual(r.op_buchung.soll_konto_id, self.konto_15900.id)
        kreditor_konto = Konto.objects.get(wirtschaftsjahr__objekt=self.objekt, kontonummer=self.kreditor.kreditorennummer)
        self.assertEqual(r.op_buchung.haben_konto_id, kreditor_konto.id)

    def test_2_freigabe_erstellt_kreditor_op_jjnnnnnn(self):
        from datetime import date
        r = _rechnung(self.objekt, self.kreditor)
        rechnung_freigeben(r, self.aufwand, self.user)
        op = KreditorOP.objects.get(rechnung=r)
        jahr_kurz = date.today().year % 100
        self.assertGreaterEqual(op.op_nummer, jahr_kurz * 1_000_000 + 1)
        self.assertLess(op.op_nummer, (jahr_kurz + 1) * 1_000_000)
        self.assertEqual(op.betrag_ursprung, Decimal("1000.00"))
        self.assertEqual(op.betrag_offen, Decimal("1000.00"))
        self.assertEqual(op.status, "offen")
        self.assertEqual(op.kreditor_id, self.kreditor.id)

    def test_3_kreditorenkonto_wird_automatisch_angelegt(self):
        # Kein Konto 70001 vorhanden vor der Freigabe
        Konto.objects.filter(wirtschaftsjahr__objekt=self.objekt, kontonummer="70001").delete()
        r = _rechnung(self.objekt, self.kreditor)
        rechnung_freigeben(r, self.aufwand, self.user)
        self.assertTrue(Konto.objects.filter(wirtschaftsjahr__objekt=self.objekt, kontonummer="70001").exists())

    def test_4_zahlungslauf_erzeugt_zwei_buchungen(self):
        r = _rechnung(self.objekt, self.kreditor)
        rechnung_freigeben(r, self.aufwand, self.user)
        bu1, bu2 = rechnung_bezahlen(r, date.today(), self.user)
        # Buchung 1: Soll Aufwand / Haben 15900
        self.assertEqual(bu1.soll_konto_id, self.aufwand.id)
        self.assertEqual(bu1.haben_konto_id, self.konto_15900.id)
        # Buchung 2: Soll Kreditor / Haben 13600
        kreditor_konto = Konto.objects.get(wirtschaftsjahr__objekt=self.objekt, kontonummer=self.kreditor.kreditorennummer)
        self.assertEqual(bu2.soll_konto_id, kreditor_konto.id)
        self.assertEqual(bu2.haben_konto_id, self.konto_13600.id)
        self.assertEqual(bu1.betrag, Decimal("1000.00"))
        self.assertEqual(bu2.betrag, Decimal("1000.00"))

    def test_5_zahlungslauf_schliesst_op(self):
        r = _rechnung(self.objekt, self.kreditor)
        rechnung_freigeben(r, self.aufwand, self.user)
        rechnung_bezahlen(r, date.today(), self.user)
        r.refresh_from_db()
        self.assertEqual(r.status, "bezahlt")
        op = KreditorOP.objects.get(rechnung=r)
        self.assertEqual(op.status, "bezahlt")
        self.assertEqual(op.betrag_offen, Decimal("0.00"))

    def test_6_bankabgang_bucht_13600_gegen_bank(self):
        r = _rechnung(self.objekt, self.kreditor)
        rechnung_freigeben(r, self.aufwand, self.user)
        rechnung_bezahlen(r, date.today(), self.user)
        buchung = bank_abgang_buchen(r, self.bank, date.today(), self.user)
        self.assertEqual(buchung.soll_konto_id, self.konto_13600.id)
        self.assertEqual(buchung.haben_konto_id, self.bank.id)
        self.assertEqual(buchung.betrag, Decimal("1000.00"))

    def test_7_aufwandskonto_nicht_in_5xxxx_wirft_fehler(self):
        wj = Wirtschaftsjahr.objects.get(objekt=self.objekt)
        falsches_konto = Konto.objects.create(
            wirtschaftsjahr=wj, kontonummer="41900", kontoname="Erlöse",
            kontoart="standard", direktes_buchen=False,
        )
        r = _rechnung(self.objekt, self.kreditor)
        with self.assertRaises(ValidationError):
            rechnung_freigeben(r, falsches_konto, self.user)

    def test_8_aufwandskonto_summierungskonto_wirft_fehler(self):
        wj = Wirtschaftsjahr.objects.get(objekt=self.objekt)
        summierung = Konto.objects.create(
            wirtschaftsjahr=wj, kontonummer="50299", kontoname="Summe BK",
            kontoart="summierung", direktes_buchen=False,
        )
        r = _rechnung(self.objekt, self.kreditor)
        with self.assertRaises(ValidationError):
            rechnung_freigeben(r, summierung, self.user)

    def test_9_doppelte_freigabe_wirft_fehler(self):
        r = _rechnung(self.objekt, self.kreditor)
        rechnung_freigeben(r, self.aufwand, self.user)
        with self.assertRaises(ValidationError):
            rechnung_freigeben(r, self.aufwand, self.user)

    def test_10_doppelter_zahlungslauf_wirft_fehler(self):
        r = _rechnung(self.objekt, self.kreditor)
        rechnung_freigeben(r, self.aufwand, self.user)
        rechnung_bezahlen(r, date.today(), self.user)
        with self.assertRaises(ValidationError):
            rechnung_bezahlen(r, date.today(), self.user)

    def test_11_freigabe_ohne_kreditor_wirft_fehler(self):
        r = Rechnung.objects.create(
            objekt=self.objekt, betrag_brutto=Decimal("500.00"),
            rechnungsnummer="RE-002", status="in_pruefung",
        )
        with self.assertRaises(ValidationError):
            rechnung_freigeben(r, self.aufwand, self.user)

    def test_12_op_nummern_fortlaufend(self):
        k2 = _kreditor("70002")
        r1 = _rechnung(self.objekt, self.kreditor)
        r2 = _rechnung(self.objekt, k2, betrag="500.00")
        r2.rechnungsnummer = "RE-002"
        r2.save(update_fields=["rechnungsnummer"])
        rechnung_freigeben(r1, self.aufwand, self.user)
        rechnung_freigeben(r2, self.aufwand, self.user)
        op1 = KreditorOP.objects.get(rechnung=r1)
        op2 = KreditorOP.objects.get(rechnung=r2)
        self.assertEqual(op2.op_nummer, op1.op_nummer + 1)
