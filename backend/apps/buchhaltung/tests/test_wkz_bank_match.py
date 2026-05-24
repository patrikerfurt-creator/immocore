"""
Tests für WKZ Bank-Match-Service:
- Eindeutiger Match (automatisch)
- Mehrdeutiger Match (Vorschlag)
- Kein Treffer → Weiterreichung
- Mandats-ID vs. IBAN-Priorität
- Toleranzfenster
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
    WiederkehrendeBuchungVorlage,
    WiederkehrendeBuchungOP,
    KreditorOP,
)
from apps.buchhaltung.services.wkz.vorlage_service import erstelle_vorlage, aktiviere_vorlage
from apps.buchhaltung.services.wkz.op_generator_service import erzeuge_einzelnen_op, Periode
from apps.buchhaltung.services.wkz.bank_match_service import (
    identifiziere_kreditor_aus_eingang,
    finde_kandidaten,
    ist_eindeutiger_auto_match,
    _extrahiere_mandats_id,
)

User = get_user_model()


def _setup():
    user = User.objects.create_user('match_user', password='x')
    objekt = Objekt.objects.create(
        bezeichnung='Test-WEG', objektnummer='M001', objekt_typ='WEG',
        ort='Frankfurt', verwaltung_seit=date(2020, 1, 1),
        zahlungsfreigabe_grenzen=[],
    )
    bankkonto = Bankkonto.objects.create(
        objekt=objekt, konto_typ='bewirtschaftung',
        bezeichnung='Hauptkonto', iban='DE00000000000000000000',
    )
    Konto.objects.create(objekt=objekt, kontonummer='50100', kontoname='Wasser',
                         kontoart='standard', direktes_buchen=False, aktiv=True)
    Konto.objects.create(objekt=objekt, kontonummer='18000', kontoname='Bank',
                         kontoart='standard', direktes_buchen=True, aktiv=True)
    kreditor = Kreditor.objects.create(
        name='Stadtwerke FFM', iban='DE99999999999999999999'
    )
    return user, objekt, bankkonto, kreditor


def _aktive_vorlage_mit_op(objekt, bankkonto, kreditor, user, betrag=Decimal('850.00'),
                            erste_faelligkeit=date(2026, 4, 1),
                            toleranz_betrag=Decimal('5.00'),
                            toleranz_tage=14,
                            sepa_mandat_id=''):
    data = {
        'objekt': objekt,
        'kreditor': kreditor,
        'bezeichnung': 'Versorgung',
        'typ': 'vertrag',
        'betrag_gesamt': betrag,
        'rhythmus': 'quartalsweise',
        'erste_faelligkeit': erste_faelligkeit,
        'bei_wochenende': 'unveraendert',
        'vorlauf_tage': 7,
        'toleranz_betrag': toleranz_betrag,
        'toleranz_tage': toleranz_tage,
        'bescheid_pflicht': False,
        'gueltig_ab': date(2026, 1, 1),
        'sepa_mandat_id': sepa_mandat_id,
    }
    splits = [{'kontonummer': '50100', 'bezeichnung': 'Wasser', 'betrag': betrag}]
    vorlage = erstelle_vorlage(data, splits, user)
    aktiviere_vorlage(vorlage, user)

    periode = Periode(
        periode_von=erste_faelligkeit,
        periode_bis=date(erste_faelligkeit.year, erste_faelligkeit.month + 2, 28),
        faellig_am=erste_faelligkeit,
    )
    wkz_op = erzeuge_einzelnen_op(vorlage, periode)
    return vorlage, wkz_op


def _kontoumsatz(bankkonto, objekt, betrag, buchungsdatum, auftraggeber_iban='', verwendungszweck=''):
    import hashlib
    h = hashlib.sha256(f"{betrag}{buchungsdatum}{auftraggeber_iban}".encode()).hexdigest()
    return Kontoumsatz.objects.create(
        objekt=objekt,
        bankkonto=bankkonto,
        sha256_hash=h,
        betrag=betrag,
        buchungsdatum=buchungsdatum,
        auftraggeber_iban=auftraggeber_iban,
        verwendungszweck=verwendungszweck,
    )


class MandatsIDExtraktionTest(TestCase):
    def test_mref_extrahiert(self):
        zveck = 'SEPA/MREF/DE98ZZZ09999999999/SVWZ/Wasser Q2'
        self.assertEqual(_extrahiere_mandats_id(zveck), 'DE98ZZZ09999999999')

    def test_ohne_mandats_id_none(self):
        self.assertIsNone(_extrahiere_mandats_id('Nur Text'))

    def test_leer_none(self):
        self.assertIsNone(_extrahiere_mandats_id(''))


class KreditorIdentifikationTest(TestCase):
    def setUp(self):
        self.user, self.objekt, self.bankkonto, self.kreditor = _setup()

    def test_iban_match(self):
        ku = _kontoumsatz(
            self.bankkonto, self.objekt,
            betrag=Decimal('-850.00'),
            buchungsdatum=date(2026, 4, 1),
            auftraggeber_iban='DE99999999999999999999',
        )
        gefunden = identifiziere_kreditor_aus_eingang(ku)
        self.assertEqual(gefunden, self.kreditor)

    def test_kein_iban_match_none(self):
        ku = _kontoumsatz(
            self.bankkonto, self.objekt,
            betrag=Decimal('-850.00'),
            buchungsdatum=date(2026, 4, 1),
            auftraggeber_iban='DE11111111111111111100',
        )
        self.assertIsNone(identifiziere_kreditor_aus_eingang(ku))

    def test_mandats_id_hat_prioritaet(self):
        """SEPA-Mandats-ID match soll vor IBAN-Match gefunden werden."""
        _aktive_vorlage_mit_op(
            self.objekt, self.bankkonto, self.kreditor, self.user,
            sepa_mandat_id='MEIN-MANDAT-123',
        )
        ku = _kontoumsatz(
            self.bankkonto, self.objekt,
            betrag=Decimal('-850.00'),
            buchungsdatum=date(2026, 4, 1),
            auftraggeber_iban='DE00000000000000000000',  # andere IBAN
            verwendungszweck='MREF/MEIN-MANDAT-123/',
        )
        gefunden = identifiziere_kreditor_aus_eingang(ku)
        self.assertEqual(gefunden, self.kreditor)


class KandidatenFindungTest(TestCase):
    def setUp(self):
        self.user, self.objekt, self.bankkonto, self.kreditor = _setup()
        self.vorlage, self.wkz_op = _aktive_vorlage_mit_op(
            self.objekt, self.bankkonto, self.kreditor, self.user
        )

    def test_eindeutiger_match(self):
        ku = _kontoumsatz(
            self.bankkonto, self.objekt,
            betrag=Decimal('-850.00'),
            buchungsdatum=date(2026, 4, 1),
            auftraggeber_iban='DE99999999999999999999',
        )
        kandidaten = finde_kandidaten(ku)
        self.assertEqual(len(kandidaten), 1)
        self.assertEqual(kandidaten[0], self.wkz_op)

    def test_ausserhalb_toleranz_kein_match(self):
        """Betrag weit außerhalb toleranz_betrag → kein Kandidat."""
        ku = _kontoumsatz(
            self.bankkonto, self.objekt,
            betrag=Decimal('-500.00'),  # 350€ Abweichung > 5€ Toleranz
            buchungsdatum=date(2026, 4, 1),
            auftraggeber_iban='DE99999999999999999999',
        )
        kandidaten = finde_kandidaten(ku)
        self.assertEqual(len(kandidaten), 0)

    def test_datum_ausserhalb_toleranz_kein_match(self):
        """Datum weit außerhalb toleranz_tage → kein Kandidat."""
        ku = _kontoumsatz(
            self.bankkonto, self.objekt,
            betrag=Decimal('-850.00'),
            buchungsdatum=date(2026, 1, 1),  # 3 Monate vor Fälligkeit
            auftraggeber_iban='DE99999999999999999999',
        )
        kandidaten = finde_kandidaten(ku)
        self.assertEqual(len(kandidaten), 0)

    def test_kein_kreditor_leer(self):
        ku = _kontoumsatz(
            self.bankkonto, self.objekt,
            betrag=Decimal('-850.00'),
            buchungsdatum=date(2026, 4, 1),
            auftraggeber_iban='',  # keine IBAN
        )
        kandidaten = finde_kandidaten(ku)
        self.assertEqual(kandidaten, [])


class AutoMatchTest(TestCase):
    def setUp(self):
        self.user, self.objekt, self.bankkonto, self.kreditor = _setup()
        self.vorlage, self.wkz_op = _aktive_vorlage_mit_op(
            self.objekt, self.bankkonto, self.kreditor, self.user
        )

    def test_exakter_betrag_ist_auto_match(self):
        ku = _kontoumsatz(
            self.bankkonto, self.objekt,
            betrag=Decimal('-850.00'),
            buchungsdatum=date(2026, 4, 1),
        )
        self.assertTrue(ist_eindeutiger_auto_match(self.wkz_op, ku))

    def test_kleiner_abweichung_1_prozent_auto(self):
        """Abweichung < 1% → Auto-Match."""
        ku = _kontoumsatz(
            self.bankkonto, self.objekt,
            betrag=Decimal('-851.00'),  # 0.12% Abweichung
            buchungsdatum=date(2026, 4, 1),
        )
        self.assertTrue(ist_eindeutiger_auto_match(self.wkz_op, ku))

    def test_grosse_abweichung_kein_auto(self):
        """Abweichung > 1% → kein Auto-Match."""
        ku = _kontoumsatz(
            self.bankkonto, self.objekt,
            betrag=Decimal('-859.00'),  # ~1.06% Abweichung
            buchungsdatum=date(2026, 4, 1),
        )
        self.assertFalse(ist_eindeutiger_auto_match(self.wkz_op, ku))
