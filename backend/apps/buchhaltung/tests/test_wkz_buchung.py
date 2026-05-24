"""
Tests für WKZ Buchungs-Service:
- Korrekte Soll/Haben-Buchung (Kassenprinzip §28 WEG)
- Multi-Split-Buchung
- Konto-Auflösung im aktiven WJ
- Abweichende Beträge (splits_override)
- KontoNichtImWJException
"""
from decimal import Decimal
from datetime import date

from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.objekte.models import Objekt, Bankkonto
from apps.konten.models import Konto
from apps.rechnungen.models import Kreditor
from apps.buchhaltung.models import (
    Kontoumsatz,
    Buchung,
    KreditorOP,
    WiederkehrendeBuchungOP,
)
from apps.buchhaltung.services.wkz.vorlage_service import erstelle_vorlage, aktiviere_vorlage
from apps.buchhaltung.services.wkz.op_generator_service import erzeuge_einzelnen_op, Periode
from apps.buchhaltung.services.wkz.buchungs_service import (
    verbuche_bankabgang,
    verbuche_mit_anpassung,
    bestimme_aktives_wj,
    KontoNichtImWJException,
)

User = get_user_model()


def _setup():
    user = User.objects.create_user('buch_user', password='x', is_superuser=True)
    objekt = Objekt.objects.create(
        bezeichnung='Test-WEG', objektnummer='B001', objekt_typ='WEG',
        ort='Frankfurt', verwaltung_seit=date(2020, 1, 1),
        zahlungsfreigabe_grenzen=[],
    )
    bankkonto = Bankkonto.objects.create(
        objekt=objekt, konto_typ='bewirtschaftung',
        bezeichnung='Hauptkonto', iban='DE00000000000000000000',
    )
    konto_50100 = Konto.objects.create(
        objekt=objekt, kontonummer='50100', kontoname='Wasser',
        kontoart='standard', direktes_buchen=False, aktiv=True,
    )
    konto_50200 = Konto.objects.create(
        objekt=objekt, kontonummer='50200', kontoname='Müll',
        kontoart='standard', direktes_buchen=False, aktiv=True,
    )
    konto_18000 = Konto.objects.create(
        objekt=objekt, kontonummer='18000', kontoname='Bank Bewirtschaftung',
        kontoart='standard', direktes_buchen=True, aktiv=True,
    )
    kreditor = Kreditor.objects.create(name='Stadtwerke', iban='DE99999999999999999999')
    return user, objekt, bankkonto, kreditor, konto_50100, konto_50200, konto_18000


def _vorlage_und_op(objekt, kreditor, user, splits_daten=None, betrag=Decimal('850.00')):
    if splits_daten is None:
        splits_daten = [
            {'kontonummer': '50100', 'bezeichnung': 'Wasser', 'betrag': Decimal('570.00')},
            {'kontonummer': '50200', 'bezeichnung': 'Müll', 'betrag': Decimal('280.00')},
        ]
    data = {
        'objekt': objekt,
        'kreditor': kreditor,
        'bezeichnung': 'Test WKZ',
        'typ': 'vertrag',
        'betrag_gesamt': betrag,
        'rhythmus': 'quartalsweise',
        'erste_faelligkeit': date(2026, 4, 1),
        'bei_wochenende': 'unveraendert',
        'vorlauf_tage': 7,
        'toleranz_betrag': Decimal('5.00'),
        'toleranz_tage': 14,
        'bescheid_pflicht': False,
        'gueltig_ab': date(2026, 1, 1),
    }
    vorlage = erstelle_vorlage(data, splits_daten, user)
    aktiviere_vorlage(vorlage, user)
    periode = Periode(
        periode_von=date(2026, 4, 1),
        periode_bis=date(2026, 6, 30),
        faellig_am=date(2026, 4, 1),
    )
    wkz_op = erzeuge_einzelnen_op(vorlage, periode)
    return vorlage, wkz_op


def _kontoumsatz(bankkonto, objekt, betrag=Decimal('-850.00'), datum=date(2026, 4, 1)):
    import hashlib
    h = hashlib.sha256(f"{betrag}{datum}".encode()).hexdigest()
    return Kontoumsatz.objects.create(
        objekt=objekt,
        bankkonto=bankkonto,
        sha256_hash=h,
        betrag=betrag,
        buchungsdatum=datum,
        auftraggeber_iban='DE99999999999999999999',
    )


class BestimmeAktivesWJTest(TestCase):
    def test_gibt_jahr_zurueck(self):
        class FakeObjekt:
            pass
        self.assertEqual(bestimme_aktives_wj(FakeObjekt(), date(2026, 4, 15)), 2026)
        self.assertEqual(bestimme_aktives_wj(FakeObjekt(), date(2025, 12, 31)), 2025)


class BuchungErzeugenTest(TestCase):
    def setUp(self):
        self.user, self.objekt, self.bankkonto, self.kreditor, \
            self.k50100, self.k50200, self.k18000 = _setup()
        self.vorlage, self.wkz_op = _vorlage_und_op(self.objekt, self.kreditor, self.user)

    def test_buchung_wird_angelegt(self):
        ku = _kontoumsatz(self.bankkonto, self.objekt)
        buchung = verbuche_bankabgang(self.wkz_op, ku, user=self.user)
        self.assertIsNotNone(buchung)
        self.assertIsInstance(buchung, Buchung)

    def test_wkz_op_status_bankabgang(self):
        ku = _kontoumsatz(self.bankkonto, self.objekt)
        verbuche_bankabgang(self.wkz_op, ku, user=self.user)
        self.wkz_op.refresh_from_db()
        self.assertEqual(self.wkz_op.status, 'bankabgang_erfolgt')

    def test_kreditor_op_bezahlt(self):
        ku = _kontoumsatz(self.bankkonto, self.objekt)
        verbuche_bankabgang(self.wkz_op, ku, user=self.user)
        kreditor_op = self.wkz_op.kreditor_op
        kreditor_op.refresh_from_db()
        self.assertEqual(kreditor_op.status, 'bezahlt')
        self.assertEqual(kreditor_op.betrag_offen, Decimal('0'))

    def test_teilbuchungen_pro_split(self):
        """Für 2 Splits müssen 2 Teilbuchungen entstehen."""
        ku = _kontoumsatz(self.bankkonto, self.objekt)
        buchung = verbuche_bankabgang(self.wkz_op, ku, user=self.user)
        teilbuchungen = buchung.teilbuchungen.all()
        self.assertEqual(teilbuchungen.count(), 2)

    def test_wirtschaftsjahr_korrekt(self):
        ku = _kontoumsatz(self.bankkonto, self.objekt, datum=date(2026, 4, 1))
        buchung = verbuche_bankabgang(self.wkz_op, ku, user=self.user)
        self.assertEqual(buchung.wirtschaftsjahr, 2026)

    def test_haben_konto_bank(self):
        ku = _kontoumsatz(self.bankkonto, self.objekt)
        buchung = verbuche_bankabgang(self.wkz_op, ku, user=self.user)
        self.assertEqual(buchung.haben_konto, self.k18000)

    def test_kassenprinzip_kein_aufwand_vorher(self):
        """Vor Verbuchung darf keine Buchung zum WKZ-OP existieren."""
        self.assertIsNone(self.wkz_op.bank_match_buchung)
        self.assertFalse(Buchung.objects.filter(
            kreditor_op_erstellung=self.wkz_op.kreditor_op
        ).exists())


class KontoFehltTest(TestCase):
    def setUp(self):
        self.user, self.objekt, self.bankkonto, self.kreditor, \
            self.k50100, self.k50200, self.k18000 = _setup()

    def test_fehlendes_konto_raises_exception(self):
        """Wenn ein Split-Konto zum Buchungszeitpunkt nicht aktiv ist → Exception."""
        from apps.konten.models import Konto
        # Konto 55500 anlegen (im Aufwandsbereich), damit Vorlage erstellt werden kann
        k = Konto.objects.create(
            objekt=self.objekt, kontonummer='55500', kontoname='Wird deaktiviert',
            kontoart='standard', direktes_buchen=False, aktiv=True,
        )
        splits_daten = [
            {'kontonummer': '55500', 'bezeichnung': 'Testposten', 'betrag': Decimal('850.00')},
        ]
        vorlage, wkz_op = _vorlage_und_op(
            self.objekt, self.kreditor, self.user,
            splits_daten=splits_daten,
            betrag=Decimal('850.00'),
        )
        # Konto nach Vorlage-Anlage deaktivieren → _finde_konto() schlägt fehl
        k.aktiv = False
        k.save(update_fields=['aktiv'])
        ku = _kontoumsatz(self.bankkonto, self.objekt)
        with self.assertRaises(KontoNichtImWJException):
            verbuche_bankabgang(wkz_op, ku, user=self.user)


class VerbuchemitAnpassungTest(TestCase):
    def setUp(self):
        self.user, self.objekt, self.bankkonto, self.kreditor, \
            self.k50100, self.k50200, self.k18000 = _setup()
        self.vorlage, self.wkz_op = _vorlage_und_op(self.objekt, self.kreditor, self.user)

    def test_override_summe_stimmt(self):
        ku = _kontoumsatz(self.bankkonto, self.objekt, betrag=Decimal('-852.00'))
        splits_override = {
            '50100': Decimal('572.00'),
            '50200': Decimal('280.00'),
        }
        buchung = verbuche_mit_anpassung(self.wkz_op, ku, splits_override, self.user)
        self.assertIsNotNone(buchung)
        self.wkz_op.refresh_from_db()
        self.assertEqual(self.wkz_op.status, 'abweichend_geklaert')
        self.assertEqual(self.wkz_op.abweichung_betrag, Decimal('2.00'))

    def test_override_summe_falsch_raises(self):
        ku = _kontoumsatz(self.bankkonto, self.objekt, betrag=Decimal('-850.00'))
        splits_override = {
            '50100': Decimal('400.00'),
            '50200': Decimal('200.00'),  # 600 ≠ 850
        }
        with self.assertRaises(ValueError):
            verbuche_mit_anpassung(self.wkz_op, ku, splits_override, self.user)
