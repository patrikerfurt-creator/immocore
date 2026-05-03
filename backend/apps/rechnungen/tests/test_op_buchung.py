"""
9 Pflichttests für den OP-Buchung-Workflow (§28 WEG Kassenprinzip).
"""
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.objekte.models import Objekt
from apps.konten.models import Konto
from apps.rechnungen.models import Rechnung, Kreditor
from apps.rechnungen.services.rechnung_op_service import rechnung_freigeben
from apps.rechnungen.services.rechnung_zahlung_service import rechnung_bezahlen

User = get_user_model()


def _objekt_und_konten():
    from datetime import date
    objekt = Objekt.objects.create(
        bezeichnung="Test-WEG",
        objektnummer="T001",
        objekt_typ="weg",
        ort="Teststadt",
        verwaltung_seit=date(2020, 1, 1),
    )
    aufwand = Konto.objects.create(
        objekt=objekt,
        kontonummer="50100",
        kontoname="Hauswartkosten",
        kontoart="standard",
        direktes_buchen=False,
    )
    bank = Konto.objects.create(
        objekt=objekt,
        kontonummer="18000",
        kontoname="Bank",
        kontoart="standard",
        direktes_buchen=True,
    )
    konto_15900, _ = Konto.objects.get_or_create(
        objekt=objekt,
        kontonummer="15900",
        defaults={
            "kontoname": "Schwebende Eingangsrechnungen",
            "kontoart": "standard",
            "direktes_buchen": False,
        },
    )
    return objekt, aufwand, bank, konto_15900


def _rechnung(objekt, betrag="1000.00", status="in_pruefung"):
    kreditor = Kreditor.objects.create(name="Test GmbH")
    return Rechnung.objects.create(
        objekt=objekt,
        kreditor=kreditor,
        betrag_brutto=Decimal(betrag),
        rechnungsnummer="RE-001",
        status=status,
    )


def _user():
    return User.objects.create_user(username="tester", password="x")


class FreigebenTest(TestCase):
    def setUp(self):
        self.objekt, self.aufwand, self.bank, _ = _objekt_und_konten()
        self.user = _user()

    def test_1_freigabe_setzt_aufwandskonto_und_status(self):
        r = _rechnung(self.objekt)
        rechnung_freigeben(r, self.aufwand, self.user)
        r.refresh_from_db()
        self.assertEqual(r.status, "freigegeben")
        self.assertEqual(r.aufwandskonto_id, self.aufwand.id)
        self.assertIsNone(r.op_buchung_id)

    def test_2_vollzahlung_erstellt_buchung(self):
        from datetime import date
        r = _rechnung(self.objekt)
        rechnung_freigeben(r, self.aufwand, self.user)
        buchung = rechnung_bezahlen(r, self.bank, Decimal("1000.00"), date.today(), self.user)
        r.refresh_from_db()
        self.assertEqual(r.status, "bezahlt")
        self.assertEqual(buchung.soll_konto_id, self.aufwand.id)
        self.assertEqual(buchung.haben_konto_id, self.bank.id)
        self.assertEqual(buchung.betrag, Decimal("1000.00"))
        self.assertIsNotNone(r.aufwand_buchung_id)

    def test_3_aufwandskonto_nicht_in_5xxxx_wirft_fehler(self):
        falsches_konto = Konto.objects.create(
            objekt=self.objekt,
            kontonummer="41900",
            kontoname="Erlöse Hausgeld",
            kontoart="standard",
            direktes_buchen=False,
        )
        r = _rechnung(self.objekt)
        with self.assertRaises(ValidationError):
            rechnung_freigeben(r, falsches_konto, self.user)

    def test_4_aufwandskonto_summierungskonto_wirft_fehler(self):
        summierung = Konto.objects.create(
            objekt=self.objekt,
            kontonummer="50299",
            kontoname="Summe Betriebskosten",
            kontoart="summierung",
            direktes_buchen=False,
        )
        r = _rechnung(self.objekt)
        with self.assertRaises(ValidationError):
            rechnung_freigeben(r, summierung, self.user)

    def test_5_aufwandskonto_direktes_buchen_wirft_fehler(self):
        direkt = Konto.objects.create(
            objekt=self.objekt,
            kontonummer="55100",
            kontoname="Verwaltungskosten (direkt)",
            kontoart="standard",
            direktes_buchen=True,
        )
        r = _rechnung(self.objekt)
        with self.assertRaises(ValidationError):
            rechnung_freigeben(r, direkt, self.user)

    def test_6_doppelte_freigabe_wirft_fehler(self):
        r = _rechnung(self.objekt)
        rechnung_freigeben(r, self.aufwand, self.user)
        with self.assertRaises(ValidationError):
            rechnung_freigeben(r, self.aufwand, self.user)

    def test_7_zahlung_ohne_aufwandskonto_verwendet_kostenstelle(self):
        from datetime import date
        r = _rechnung(self.objekt)
        r.kostenstelle = self.aufwand
        r.save(update_fields=["kostenstelle"])
        buchung = rechnung_bezahlen(r, self.bank, Decimal("1000.00"), date.today(), self.user)
        self.assertEqual(buchung.soll_konto_id, self.aufwand.id)

    def test_8_zahlung_ohne_sachkonto_wirft_fehler(self):
        from datetime import date
        r = _rechnung(self.objekt)
        with self.assertRaises(ValidationError):
            rechnung_bezahlen(r, self.bank, Decimal("1000.00"), date.today(), self.user)

    def test_9_doppelte_zahlung_wirft_fehler(self):
        from datetime import date
        r = _rechnung(self.objekt)
        rechnung_freigeben(r, self.aufwand, self.user)
        rechnung_bezahlen(r, self.bank, Decimal("1000.00"), date.today(), self.user)
        with self.assertRaises(ValidationError):
            rechnung_bezahlen(r, self.bank, Decimal("1000.00"), date.today(), self.user)
