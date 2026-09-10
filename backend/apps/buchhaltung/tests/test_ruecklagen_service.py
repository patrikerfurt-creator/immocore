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
    ruecklagen_sollstellungen_je_einheit,
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


class RuecklagenSollstellungenJeEinheitTest(RuecklagenServiceTestBase):
    """
    Aufstellung je Wohnung: Soll, Haben (gezahlt) und Saldo der
    Rücklagen-Sollstellungen des Wirtschaftsjahres aus dem Nebenbuch.
    """

    def _soll_split(self, einheit_nr, soll, ist, periode, ba=None, storniert=False,
                    typ='hausgeld'):
        """Sollstellung mit Split auf die Rücklagen-AA. typ='saldovortrag' = SAVO."""
        from django.utils import timezone
        einheit, _ = Einheit.objects.get_or_create(
            objekt=self.objekt, einheit_nr=einheit_nr,
            defaults=dict(einheit_typ='Wohnung', lage='EG'))
        ev = EigentumsVerhaeltnis.objects.filter(einheit=einheit).first()
        if ev is None:
            person = Person.objects.create(
                person_typ='100', anrede='Herr', vorname='Test', nachname=einheit_nr)
            ev = EigentumsVerhaeltnis.objects.create(
                einheit=einheit, person=person, beginn=date(2020, 1, 1))
        ss = HausgeldSollstellung.objects.create(
            objekt=self.objekt, eigentumsverhaeltnis=ev,
            sollstellungs_typ=typ,
            ba=_get_or_create_ba('99') if typ == 'saldovortrag' else None,
            periode=periode, faellig_am=periode,
            opos_nr=f'OP-{uuid4().hex[:8]}', soll_betrag=Decimal(soll),
            erstellt_von=self.user,
            storniert_am=timezone.now() if storniert else None)
        return SollstellungSplit.objects.create(
            sollstellung=ss, ba=ba or self.ba_911,
            betrag=Decimal(soll), ist_betrag_split=Decimal(ist))

    def _savo(self, einheit_nr, betrag, ist='0.00', periode=date(2025, 1, 1), ba=None):
        return self._soll_split(einheit_nr, betrag, ist, periode, ba=ba,
                                typ='saldovortrag')

    def test_leer_ohne_sollstellungen(self):
        self.assertEqual(
            ruecklagen_sollstellungen_je_einheit(self.objekt, self.wj, '911'), [])

    def test_soll_haben_saldo_je_wohnung(self):
        self._soll_split('WE01', '50.00', '20.00', date(2025, 1, 1))
        zeilen = ruecklagen_sollstellungen_je_einheit(self.objekt, self.wj, '911')
        self.assertEqual(len(zeilen), 1)
        self.assertEqual(zeilen[0]['einheit_nr'], 'WE01')
        self.assertEqual(zeilen[0]['savo'], Decimal('0'))
        self.assertEqual(zeilen[0]['soll'], Decimal('50.00'))
        self.assertEqual(zeilen[0]['haben'], Decimal('20.00'))
        self.assertEqual(zeilen[0]['saldo'], Decimal('30.00'))

    def test_savo_auf_die_ruecklagen_aa_wird_ausgewiesen(self):
        """BA-99-Saldovortrag auf AA 911 erhöht SAVO und Saldo, nicht Soll."""
        self._savo('WE01', '80.00')
        self._soll_split('WE01', '50.00', '20.00', date(2025, 2, 1))
        zeilen = ruecklagen_sollstellungen_je_einheit(self.objekt, self.wj, '911')
        self.assertEqual(len(zeilen), 1)
        self.assertEqual(zeilen[0]['savo'], Decimal('80.00'))
        self.assertEqual(zeilen[0]['soll'], Decimal('50.00'))
        self.assertEqual(zeilen[0]['haben'], Decimal('20.00'))
        self.assertEqual(zeilen[0]['saldo'], Decimal('110.00'))  # 80 + 50 − 20

    def test_getilgter_savo_erscheint_im_haben(self):
        """Wird der Saldovortrag gezahlt, gleicht das Haben ihn wieder aus."""
        self._savo('WE01', '80.00', ist='80.00')
        zeilen = ruecklagen_sollstellungen_je_einheit(self.objekt, self.wj, '911')
        self.assertEqual(zeilen[0]['savo'], Decimal('80.00'))
        self.assertEqual(zeilen[0]['haben'], Decimal('80.00'))
        self.assertEqual(zeilen[0]['saldo'], Decimal('0.00'))

    def test_savo_als_guthaben_zaehlt_negativ(self):
        """richtung='haben' legt den Split mit negativem Betrag an."""
        self._savo('WE01', '-30.00')
        zeilen = ruecklagen_sollstellungen_je_einheit(self.objekt, self.wj, '911')
        self.assertEqual(zeilen[0]['savo'], Decimal('-30.00'))
        self.assertEqual(zeilen[0]['saldo'], Decimal('-30.00'))

    def test_savo_auf_andere_aa_bleibt_draussen(self):
        """Der übliche Fall: SAVO auf AA 900 (Hausgeld), nicht auf die Rücklage."""
        self._savo('WE01', '80.00', ba=_get_or_create_ba('900'))
        self.assertEqual(
            ruecklagen_sollstellungen_je_einheit(self.objekt, self.wj, '911'), [])

    def test_stornierter_savo_zaehlt_nicht(self):
        self._soll_split('WE01', '80.00', '0.00', date(2025, 1, 1),
                         typ='saldovortrag', storniert=True)
        self.assertEqual(
            ruecklagen_sollstellungen_je_einheit(self.objekt, self.wj, '911'), [])

    def test_perioden_derselben_wohnung_werden_summiert(self):
        self._soll_split('WE01', '50.00', '50.00', date(2025, 1, 1))
        self._soll_split('WE01', '50.00', '10.00', date(2025, 2, 1))
        zeilen = ruecklagen_sollstellungen_je_einheit(self.objekt, self.wj, '911')
        self.assertEqual(len(zeilen), 1)
        self.assertEqual(zeilen[0]['soll'], Decimal('100.00'))
        self.assertEqual(zeilen[0]['haben'], Decimal('60.00'))
        self.assertEqual(zeilen[0]['saldo'], Decimal('40.00'))

    def test_mehrere_wohnungen_nach_nummer_sortiert(self):
        self._soll_split('WE02', '50.00', '50.00', date(2025, 1, 1))
        self._soll_split('WE01', '30.00', '30.00', date(2025, 1, 1))
        zeilen = ruecklagen_sollstellungen_je_einheit(self.objekt, self.wj, '911')
        self.assertEqual([z['einheit_nr'] for z in zeilen], ['WE01', 'WE02'])

    def test_sollstellung_ausserhalb_wj_nicht_enthalten(self):
        self._soll_split('WE01', '50.00', '50.00', date(2024, 6, 1))
        self.assertEqual(
            ruecklagen_sollstellungen_je_einheit(self.objekt, self.wj, '911'), [])

    def test_stornierte_sollstellung_zaehlt_nicht(self):
        self._soll_split('WE01', '50.00', '0.00', date(2025, 1, 1), storniert=True)
        self.assertEqual(
            ruecklagen_sollstellungen_je_einheit(self.objekt, self.wj, '911'), [])

    def test_andere_ba_nr_nicht_vermischt(self):
        self._soll_split('WE01', '50.00', '50.00', date(2025, 1, 1),
                         ba=_get_or_create_ba('912'))
        self.assertEqual(
            ruecklagen_sollstellungen_je_einheit(self.objekt, self.wj, '911'), [])


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
