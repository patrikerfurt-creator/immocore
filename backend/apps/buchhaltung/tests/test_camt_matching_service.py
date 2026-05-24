"""
Tests: camt_matching_service (CAMT_BUCHUNGSLOGIK.md, Fall 2 + 8)
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.buchhaltung.models import KreditorOP, Kontoumsatz
from apps.buchhaltung.services.camt_matching_service import (
    matche_kreditor_op,
    matche_eigentuemer_erstattung,
    buche_camt_dbit_kreditor,
    erkenne_dbit,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _user(username='camt-user'):
    u, _ = User.objects.get_or_create(username=username, defaults={'is_staff': True})
    return u


def _create_objekt(kuerzel='CM1'):
    from apps.objekte.models import Objekt
    return Objekt.objects.create(
        objekt_typ='WEG',
        bezeichnung=f'CAMT-Test {kuerzel}',
        kurzbezeichnung=kuerzel,
        strasse='Teststr. 1',
        plz='60311',
        ort='Frankfurt',
        verwaltung_seit=date(2020, 1, 1),
        glaeubiger_id='DE98ZZZ09999999999',
    )


def _create_wj_und_konten(objekt, jahr=2026):
    from apps.objekte.models import Wirtschaftsjahr
    from apps.konten.models import Konto
    wj = Wirtschaftsjahr.objects.create(objekt=objekt, jahr=jahr, beginn_monat=1)
    Konto.objects.create(wirtschaftsjahr=wj, kontonummer='15900', kontoname='Schweb. ER', kontoart='standard', direktes_buchen=False)
    Konto.objects.create(wirtschaftsjahr=wj, kontonummer='13600', kontoname='Zahlungsausgang', kontoart='standard', direktes_buchen=False)
    Konto.objects.create(wirtschaftsjahr=wj, kontonummer='18000', kontoname='Bank', kontoart='standard', direktes_buchen=True)
    aufwand = Konto.objects.create(wirtschaftsjahr=wj, kontonummer='50100', kontoname='Hauswartkosten', kontoart='standard', direktes_buchen=False)
    return wj, aufwand


def _create_kreditor(name='Test GmbH', iban='DE12500105170648489890'):
    from apps.rechnungen.models import Kreditor
    return Kreditor.objects.create(name=name, iban=iban, name_normalisiert=name.lower())


def _create_rechnung_und_op(objekt, wj, aufwand, kreditor, betrag=Decimal('1200.00'), rechnungsnummer='RE-2026-001'):
    from apps.rechnungen.models import Rechnung
    from apps.rechnungen.services.rechnung_op_service import rechnung_freigeben
    rechnung = Rechnung.objects.create(
        objekt=objekt,
        kreditor=kreditor,
        betrag_brutto=betrag,
        rechnungsnummer=rechnungsnummer,
        leistungstext='Hausmeister',
        status='in_pruefung',
        erfasst_von=_user(),
    )
    rechnung_freigeben(rechnung, aufwand, _user())
    rechnung.refresh_from_db()
    return rechnung


def _create_kontoumsatz(objekt, betrag, auftraggeber_iban='', verwendungszweck=''):
    return Kontoumsatz.objects.create(
        objekt=objekt,
        sha256_hash=f'hash-{betrag}-{auftraggeber_iban}-{verwendungszweck}'[:64],
        betrag=betrag,
        buchungsdatum=date(2026, 3, 15),
        auftraggeber_name='Test GmbH',
        auftraggeber_iban=auftraggeber_iban,
        empfaenger_iban='DE07501900000300275532',
        verwendungszweck=verwendungszweck,
        status='importiert',
    )


# ---------------------------------------------------------------------------
# matche_kreditor_op: Stufe 1 (IBAN)
# ---------------------------------------------------------------------------

class KreditorOpMatchStufe1Test(TestCase):

    def setUp(self):
        self.user = _user()
        self.objekt = _create_objekt()
        self.wj, self.aufwand = _create_wj_und_konten(self.objekt)
        self.kreditor = _create_kreditor(iban='DE98508501500000752363')
        self.rechnung = _create_rechnung_und_op(
            self.objekt, self.wj, self.aufwand, self.kreditor, betrag=Decimal('1200.00')
        )

    def test_match_per_iban_und_betrag(self):
        umsatz = _create_kontoumsatz(
            self.objekt, betrag=Decimal('-1200.00'),
            auftraggeber_iban='DE98508501500000752363',
        )
        op = matche_kreditor_op(umsatz)
        self.assertIsNotNone(op)
        self.assertEqual(op.rechnung, self.rechnung)

    def test_kein_match_bei_falschem_betrag(self):
        umsatz = _create_kontoumsatz(
            self.objekt, betrag=Decimal('-999.00'),
            auftraggeber_iban='DE98508501500000752363',
        )
        op = matche_kreditor_op(umsatz)
        self.assertIsNone(op)

    def test_kein_match_bei_crdt(self):
        umsatz = _create_kontoumsatz(
            self.objekt, betrag=Decimal('1200.00'),
            auftraggeber_iban='DE98508501500000752363',
        )
        op = matche_kreditor_op(umsatz)
        self.assertIsNone(op)

    def test_kein_match_bei_falscher_iban(self):
        umsatz = _create_kontoumsatz(
            self.objekt, betrag=Decimal('-1200.00'),
            auftraggeber_iban='DE00000000000000000000',
        )
        op = matche_kreditor_op(umsatz)
        self.assertIsNone(op)


# ---------------------------------------------------------------------------
# matche_kreditor_op: Stufe 2 (Rechnungsnummer)
# ---------------------------------------------------------------------------

class KreditorOpMatchStufe2Test(TestCase):

    def setUp(self):
        self.user = _user()
        self.objekt = _create_objekt('CM2')
        self.wj, self.aufwand = _create_wj_und_konten(self.objekt)
        self.kreditor = _create_kreditor(iban=None)
        self.kreditor.iban = None
        self.kreditor.save()
        self.rechnung = _create_rechnung_und_op(
            self.objekt, self.wj, self.aufwand, self.kreditor,
            betrag=Decimal('850.00'), rechnungsnummer='RE-164622',
        )

    def test_match_per_rechnungsnummer_im_verwendungszweck(self):
        umsatz = _create_kontoumsatz(
            self.objekt, betrag=Decimal('-850.00'),
            auftraggeber_iban='',
            verwendungszweck='RE.164622(55028) vom 15.12.2025',
        )
        op = matche_kreditor_op(umsatz)
        self.assertIsNotNone(op)
        self.assertEqual(op.rechnung, self.rechnung)

    def test_kein_match_ohne_rechnungsnummer(self):
        umsatz = _create_kontoumsatz(
            self.objekt, betrag=Decimal('-850.00'),
            verwendungszweck='Zahlung Hausmeister',
        )
        op = matche_kreditor_op(umsatz)
        self.assertIsNone(op)


# ---------------------------------------------------------------------------
# erkenne_dbit: Dispatch-Logik
# ---------------------------------------------------------------------------

class ErkenneDbitTest(TestCase):

    def setUp(self):
        self.user = _user()
        self.objekt = _create_objekt('CM3')
        self.wj, self.aufwand = _create_wj_und_konten(self.objekt)
        self.kreditor = _create_kreditor(iban='DE55200400600200462100')
        self.rechnung = _create_rechnung_und_op(
            self.objekt, self.wj, self.aufwand, self.kreditor, betrag=Decimal('500.00')
        )

    def test_dbit_kreditor_op_vorschlag(self):
        umsatz = _create_kontoumsatz(
            self.objekt, betrag=Decimal('-500.00'),
            auftraggeber_iban='DE55200400600200462100',
        )
        vorschlag = erkenne_dbit(umsatz)
        self.assertIsNotNone(vorschlag)
        self.assertEqual(vorschlag['typ'], 'kreditor_op')
        self.assertEqual(vorschlag['konfidenz'], 'hoch')
        self.assertIsNotNone(vorschlag['kreditor_op_id'])

    def test_crdt_gibt_kein_ergebnis(self):
        umsatz = _create_kontoumsatz(
            self.objekt, betrag=Decimal('500.00'),
            auftraggeber_iban='DE55200400600200462100',
        )
        vorschlag = erkenne_dbit(umsatz)
        self.assertIsNone(vorschlag)

    def test_unbekannte_dbit_gibt_none(self):
        umsatz = _create_kontoumsatz(
            self.objekt, betrag=Decimal('-999.00'),
            auftraggeber_iban='DE99000000000000000099',
        )
        vorschlag = erkenne_dbit(umsatz)
        self.assertIsNone(vorschlag)


# ---------------------------------------------------------------------------
# buche_camt_dbit_kreditor: Phase-2/3-Buchung
# ---------------------------------------------------------------------------

class BucheCamtDbitKreditorTest(TestCase):

    def setUp(self):
        self.user = _user()
        self.objekt = _create_objekt('CM4')
        self.wj, self.aufwand = _create_wj_und_konten(self.objekt)
        self.kreditor = _create_kreditor(iban='DE75200400600200467200')
        self.rechnung = _create_rechnung_und_op(
            self.objekt, self.wj, self.aufwand, self.kreditor, betrag=Decimal('2400.00')
        )

    def test_buchung_aus_camt_setzt_status_gebucht(self):
        umsatz = _create_kontoumsatz(
            self.objekt, betrag=Decimal('-2400.00'),
            auftraggeber_iban='DE75200400600200467200',
        )
        ergebnis = buche_camt_dbit_kreditor(umsatz, self.user)

        self.assertTrue(ergebnis['matched'])
        self.assertTrue(ergebnis['gebucht'])

        umsatz.refresh_from_db()
        self.assertEqual(umsatz.status, 'gebucht')

    def test_buchung_schliesst_kreditor_op(self):
        umsatz = _create_kontoumsatz(
            self.objekt, betrag=Decimal('-2400.00'),
            auftraggeber_iban='DE75200400600200467200',
        )
        buche_camt_dbit_kreditor(umsatz, self.user)

        op = KreditorOP.objects.get(rechnung=self.rechnung)
        self.assertEqual(op.status, 'bezahlt')
        self.assertEqual(op.betrag_offen, Decimal('0.00'))

    def test_kein_match_gibt_matched_false(self):
        umsatz = _create_kontoumsatz(
            self.objekt, betrag=Decimal('-9999.00'),
            auftraggeber_iban='DE00000000000000000099',
        )
        ergebnis = buche_camt_dbit_kreditor(umsatz, self.user)
        self.assertFalse(ergebnis['matched'])


# ---------------------------------------------------------------------------
# Fall 8: Eigentümer-Erstattung
# ---------------------------------------------------------------------------

class EigentueermerErstattungTest(TestCase):

    def setUp(self):
        self.user = _user()
        self.objekt = _create_objekt('CM5')
        self.wj, _ = _create_wj_und_konten(self.objekt)

    def _create_ev_mit_iban(self, iban):
        from apps.objekte.models import Einheit
        from apps.personen.models import Person, EigentumsVerhaeltnis
        einheit = Einheit.objects.create(
            objekt=self.objekt, einheit_nr='WE01', einheit_typ='Wohnung', lage='EG'
        )
        person = Person.objects.create(
            person_typ='100', anrede='Herr', vorname='Test', nachname='Eigentümer',
            ibans=[iban],
        )
        return EigentumsVerhaeltnis.objects.create(
            einheit=einheit, person=person, beginn=date(2020, 1, 1), ende=None,
        )

    def test_match_per_person_iban(self):
        iban = 'DE89370400440532013002'
        self._create_ev_mit_iban(iban)
        umsatz = _create_kontoumsatz(
            self.objekt, betrag=Decimal('-500.00'), auftraggeber_iban=iban
        )
        ergebnis = matche_eigentuemer_erstattung(umsatz)
        self.assertIsNotNone(ergebnis)
        person, ev = ergebnis
        self.assertEqual(person.nachname, 'Eigentümer')

    def test_kein_match_unbekannte_iban(self):
        self._create_ev_mit_iban('DE89370400440532013002')
        umsatz = _create_kontoumsatz(
            self.objekt, betrag=Decimal('-500.00'), auftraggeber_iban='DE00000000000000000000'
        )
        ergebnis = matche_eigentuemer_erstattung(umsatz)
        self.assertIsNone(ergebnis)

    def test_erkenne_dbit_gibt_eigentuemer_erstattung_vorschlag(self):
        iban = 'DE89370400440532013003'
        self._create_ev_mit_iban(iban)
        umsatz = _create_kontoumsatz(
            self.objekt, betrag=Decimal('-300.00'), auftraggeber_iban=iban
        )
        vorschlag = erkenne_dbit(umsatz)
        self.assertIsNotNone(vorschlag)
        self.assertEqual(vorschlag['typ'], 'eigentuemer_erstattung')
