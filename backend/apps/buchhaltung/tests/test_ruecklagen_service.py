"""
Tests: jahresabrechnung/ruecklagen_service (HGA-Spec v1.0 Kap. 4.5, Phase B)

Zuführung aus SollstellungZahlung (Nebenbuch), Entnahmen über Rücklagen-
Sachkonto als Gegenkonto, Bankauszug-Abgleich (Klärungsfall blockiert Schritt 5),
Anteil Eigentümer = Endbestand × MEA.
"""
from datetime import date
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.buchhaltung.models import (
    Buchung,
    Buchungsart,
    HausgeldSollstellung,
    Kontoumsatz,
    SollstellungSplit,
    SollstellungZahlung,
)
from apps.buchhaltung.services.jahresabrechnung.ruecklagen_service import (
    anteil_eigentuemer,
    pruefe_schritt5_blocker,
    ruecklagen_uebersicht,
)
from apps.konten.models import Konto
from apps.objekte.models import (
    Bankkonto,
    Einheit,
    Objekt,
    Verteilerschluessel,
    VerteilerschluesselWert,
    Wirtschaftsjahr,
)
from apps.personen.models import EigentumsVerhaeltnis, Person

User = get_user_model()


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _user(username='rl-user'):
    u, _ = User.objects.get_or_create(username=username, defaults={'is_staff': True})
    return u


def _create_objekt(kuerzel='RL1'):
    return Objekt.objects.create(
        objekt_typ='WEG',
        bezeichnung=f'RL-Test-Objekt {kuerzel}',
        kurzbezeichnung=kuerzel,
        strasse='Teststraße 1',
        plz='60311',
        ort='Frankfurt',
        verwaltung_seit=date(2020, 1, 1),
        glaeubiger_id='DE98ZZZ09999999999',
    )


def _create_umsatz(bankkonto, betrag, datum, status='verbucht'):
    return Kontoumsatz.objects.create(
        objekt=bankkonto.objekt,
        bankkonto=bankkonto,
        sha256_hash=uuid4().hex + uuid4().hex[:32],
        betrag=Decimal(betrag),
        buchungsdatum=datum,
        status=status,
    )


def _get_or_create_ba(nr='911'):
    ba, _ = Buchungsart.objects.get_or_create(
        nr=nr,
        defaults=dict(
            bezeichnung=f'BA {nr}', ruecklagen_relevant=True,
            bankkonto_typ='ruecklage_nach_index',
        ),
    )
    return ba


class RuecklagenServiceTestBase(TestCase):
    def setUp(self):
        self.user = _user()
        self.objekt = _create_objekt()
        self.wj = Wirtschaftsjahr.objects.create(
            objekt=self.objekt, jahr=2025, beginn_monat=1)
        self.bk = Bankkonto.objects.create(
            objekt=self.objekt, konto_typ='ruecklage',
            bezeichnung='Rücklage 1', reihenfolge=1,
        )
        self.ba_911 = _get_or_create_ba('911')

    # -- Nebenbuch-Zuführung -------------------------------------------------

    def _create_zufuehrung(self, betrag, buchungsdatum):
        """Sollstellung (hausgeld) mit 911-Split + tilgender Zahlung."""
        einheit = Einheit.objects.create(
            objekt=self.objekt, einheit_nr=f'WE{uuid4().hex[:4]}',
            einheit_typ='Wohnung', lage='EG',
        )
        person = Person.objects.create(
            person_typ='100', anrede='Herr', vorname='Test', nachname='Zahler',
        )
        ev = EigentumsVerhaeltnis.objects.create(
            einheit=einheit, person=person, beginn=date(2020, 1, 1),
        )
        ss = HausgeldSollstellung.objects.create(
            objekt=self.objekt,
            eigentumsverhaeltnis=ev,
            sollstellungs_typ='hausgeld',
            periode=buchungsdatum.replace(day=1),
            faellig_am=buchungsdatum,
            opos_nr=f'OP-{uuid4().hex[:8]}',
            soll_betrag=Decimal(betrag),
            erstellt_von=self.user,
        )
        split = SollstellungSplit.objects.create(
            sollstellung=ss, ba=self.ba_911, betrag=Decimal(betrag),
        )
        buchung = Buchung.objects.create(
            objekt=self.objekt, betrag=Decimal(betrag),
            buchungsdatum=buchungsdatum, status='festgeschrieben',
        )
        zahlung = SollstellungZahlung.objects.create(
            sollstellung=ss, split=split, buchung=buchung,
            betrag=Decimal(betrag), erstellt_von=self.user,
        )
        return zahlung

    # -- Entnahme über Rücklagen-Sachkonto ------------------------------------

    def _create_entnahme(self, betrag, buchungsdatum):
        ruecklagen_konto = Konto.objects.create(
            wirtschaftsjahr=self.wj, kontonummer='30911',
            kontoname='Rücklage 1 (Sachkonto)', abrechnungsart='911',
        )
        return Buchung.objects.create(
            objekt=self.objekt, betrag=Decimal(betrag),
            buchungsdatum=buchungsdatum, status='festgeschrieben',
            haben_konto=ruecklagen_konto,
        )


class RuecklagenUebersichtTest(RuecklagenServiceTestBase):
    def test_anfangsbestand_aus_umsaetzen_vor_wj(self):
        _create_umsatz(self.bk, '10000.00', date(2024, 6, 1))
        _create_umsatz(self.bk, '500.00', date(2024, 12, 31))
        rows = ruecklagen_uebersicht(self.objekt, self.wj)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['anfangsbestand'], Decimal('10500.00'))
        self.assertEqual(rows[0]['ba_nr'], '911')

    def test_stornierter_umsatz_zaehlt_nicht(self):
        _create_umsatz(self.bk, '10000.00', date(2024, 6, 1))
        _create_umsatz(self.bk, '999.00', date(2024, 7, 1), status='storniert')
        rows = ruecklagen_uebersicht(self.objekt, self.wj)
        self.assertEqual(rows[0]['anfangsbestand'], Decimal('10000.00'))

    def test_zufuehrung_aus_nebenbuch(self):
        self._create_zufuehrung('500.00', date(2025, 6, 15))
        rows = ruecklagen_uebersicht(self.objekt, self.wj)
        self.assertEqual(rows[0]['zufuehrungen'], Decimal('500.00'))

    def test_zufuehrung_ausserhalb_wj_zaehlt_nicht(self):
        self._create_zufuehrung('500.00', date(2024, 6, 15))
        rows = ruecklagen_uebersicht(self.objekt, self.wj)
        self.assertEqual(rows[0]['zufuehrungen'], Decimal('0'))

    def test_entnahme_ueber_gegenkonto(self):
        self._create_entnahme('200.00', date(2025, 7, 1))
        rows = ruecklagen_uebersicht(self.objekt, self.wj)
        self.assertEqual(rows[0]['entnahmen'], Decimal('200.00'))

    def test_abgleich_ohne_abweichung(self):
        # Bank: 10000 Anfang, +500 Zuführung, -200 Entnahme
        _create_umsatz(self.bk, '10000.00', date(2024, 6, 1))
        _create_umsatz(self.bk, '500.00', date(2025, 6, 16))
        _create_umsatz(self.bk, '-200.00', date(2025, 7, 2))
        # Nebenbuch/Hauptbuch spiegeln dieselben Bewegungen
        self._create_zufuehrung('500.00', date(2025, 6, 15))
        self._create_entnahme('200.00', date(2025, 7, 1))
        rows = ruecklagen_uebersicht(self.objekt, self.wj)
        self.assertEqual(rows[0]['endbestand_berechnet'], Decimal('10300.00'))
        self.assertEqual(rows[0]['endbestand_bank'], Decimal('10300.00'))
        self.assertEqual(rows[0]['abweichung'], Decimal('0.00'))
        self.assertFalse(rows[0]['klaerungsfall'])
        self.assertEqual(pruefe_schritt5_blocker(self.objekt, self.wj), [])

    def test_abweichung_blockiert_schritt5(self):
        """Spec Kap. 5 Schritt 5: Differenz > 0,01 € → Klärungsfall."""
        _create_umsatz(self.bk, '10000.00', date(2024, 6, 1))
        self._create_zufuehrung('500.00', date(2025, 6, 15))
        # Bank hat die Zuführung nie gesehen → Abweichung 500 €
        rows = ruecklagen_uebersicht(self.objekt, self.wj)
        self.assertTrue(rows[0]['klaerungsfall'])
        blocker = pruefe_schritt5_blocker(self.objekt, self.wj)
        self.assertEqual(len(blocker), 1)
        self.assertEqual(blocker[0]['abweichung'], Decimal('500.00'))

    def test_toleranz_ein_cent_ist_kein_klaerungsfall(self):
        _create_umsatz(self.bk, '10000.00', date(2024, 6, 1))
        _create_umsatz(self.bk, '0.01', date(2025, 3, 1))
        rows = ruecklagen_uebersicht(self.objekt, self.wj)
        self.assertEqual(rows[0]['abweichung'], Decimal('-0.01'))
        self.assertFalse(rows[0]['klaerungsfall'])

    def test_zwei_ruecklagen_getrennt(self):
        bk2 = Bankkonto.objects.create(
            objekt=self.objekt, konto_typ='ruecklage',
            bezeichnung='Rücklage 2', reihenfolge=2,
        )
        _create_umsatz(self.bk, '1000.00', date(2024, 6, 1))
        _create_umsatz(bk2, '2000.00', date(2024, 6, 1))
        rows = ruecklagen_uebersicht(self.objekt, self.wj)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['ba_nr'], '911')
        self.assertEqual(rows[1]['ba_nr'], '912')
        self.assertEqual(rows[0]['anfangsbestand'], Decimal('1000.00'))
        self.assertEqual(rows[1]['anfangsbestand'], Decimal('2000.00'))

    def test_bewirtschaftungskonto_erscheint_nicht(self):
        Bankkonto.objects.create(
            objekt=self.objekt, konto_typ='bewirtschaftung',
            bezeichnung='Girokonto', reihenfolge=1,
        )
        rows = ruecklagen_uebersicht(self.objekt, self.wj)
        self.assertEqual(len(rows), 1)


class AnteilEigentuemerTest(RuecklagenServiceTestBase):
    def test_anteil_endbestand_mal_mea(self):
        e1 = Einheit.objects.create(
            objekt=self.objekt, einheit_nr='WE01', einheit_typ='Wohnung', lage='EG')
        e2 = Einheit.objects.create(
            objekt=self.objekt, einheit_nr='WE02', einheit_typ='Wohnung', lage='OG')
        vs = Verteilerschluessel.objects.create(
            objekt=self.objekt, schluessel='010', bezeichnung='MEA', vs_typ='mea')
        VerteilerschluesselWert.objects.create(
            schluessel=vs, einheit=e1, wirtschaftsjahr=0, wert=Decimal('250'))
        VerteilerschluesselWert.objects.create(
            schluessel=vs, einheit=e2, wirtschaftsjahr=0, wert=Decimal('750'))
        anteil = anteil_eigentuemer(Decimal('10000.00'), e1, self.wj)
        self.assertEqual(anteil, Decimal('2500.00'))
