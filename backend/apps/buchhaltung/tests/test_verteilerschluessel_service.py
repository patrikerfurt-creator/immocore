"""
Tests: jahresabrechnung/verteilerschluessel_service (HGA-Spec v1.0 Kap. 4.3, Phase B)

Alle VS-Kategorien (Stammdaten Fläche/MEA/Kopf, Verbrauch), gueltig_ab-Auflösung,
Fallback auf Konto-Stammdaten, Fehlerfälle bei fehlenden Werten.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.buchhaltung.services.jahresabrechnung.verteilerschluessel_service import (
    VerteilerschluesselFehler,
    aktiver_vs_code,
    anteil_einheit,
    anteil_einheit_fuer_vs_code,
    mea_anteil,
)
from apps.konten.models import Konto, KontoVerteilerSchluessel
from apps.objekte.models import (
    Einheit,
    EinheitVerbrauch,
    Objekt,
    Verteilerschluessel,
    VerteilerschluesselWert,
    Wirtschaftsjahr,
)


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _create_objekt(kuerzel='VS1'):
    return Objekt.objects.create(
        objekt_typ='WEG',
        bezeichnung=f'VS-Test-Objekt {kuerzel}',
        kurzbezeichnung=kuerzel,
        strasse='Teststraße 1',
        plz='60311',
        ort='Frankfurt',
        verwaltung_seit=date(2020, 1, 1),
        glaeubiger_id='DE98ZZZ09999999999',
    )


def _create_wj(objekt, jahr=2025):
    return Wirtschaftsjahr.objects.create(objekt=objekt, jahr=jahr, beginn_monat=1)


def _create_einheit(objekt, nr):
    return Einheit.objects.create(
        objekt=objekt, einheit_nr=nr, einheit_typ='Wohnung', lage=f'Lage {nr}',
    )


def _create_konto(wj, kontonummer='50100', vs=None):
    return Konto.objects.create(
        wirtschaftsjahr=wj, kontonummer=kontonummer,
        kontoname=f'Konto {kontonummer}', verteilerschluessel=vs,
    )


def _create_vs_config(objekt, schluessel, vs_typ, bezeichnung=None):
    return Verteilerschluessel.objects.create(
        objekt=objekt, schluessel=schluessel,
        bezeichnung=bezeichnung or f'VS {schluessel}', vs_typ=vs_typ,
    )


def _create_vs_wert(vs_config, einheit, wert, wj_jahr=0, beteiligt=True):
    return VerteilerschluesselWert.objects.create(
        schluessel=vs_config, einheit=einheit,
        wirtschaftsjahr=wj_jahr, beteiligt=beteiligt,
        wert=Decimal(wert) if wert is not None else None,
    )


class VerteilerschluesselServiceTestBase(TestCase):
    def setUp(self):
        self.objekt = _create_objekt()
        self.wj = _create_wj(self.objekt)
        self.e1 = _create_einheit(self.objekt, 'WE01')
        self.e2 = _create_einheit(self.objekt, 'WE02')


# ---------------------------------------------------------------------------
# aktiver_vs_code — Auflösung über gueltig_ab (Abweichung 2 der Phase-0-Doku)
# ---------------------------------------------------------------------------

class AktiverVsCodeTest(VerteilerschluesselServiceTestBase):
    def test_juengste_zuordnung_mit_gueltig_ab_vor_stichtag_gewinnt(self):
        konto = _create_konto(self.wj)
        KontoVerteilerSchluessel.objects.create(
            konto=konto, vs_code='001', gueltig_ab=date(2020, 1, 1))
        KontoVerteilerSchluessel.objects.create(
            konto=konto, vs_code='010', gueltig_ab=date(2025, 1, 1))
        self.assertEqual(aktiver_vs_code(konto), '010')

    def test_zukuenftige_zuordnung_wird_ignoriert(self):
        konto = _create_konto(self.wj)
        KontoVerteilerSchluessel.objects.create(
            konto=konto, vs_code='001', gueltig_ab=date(2020, 1, 1))
        KontoVerteilerSchluessel.objects.create(
            konto=konto, vs_code='140', gueltig_ab=date(2099, 1, 1))
        # Stichtag = WJ-Ende 2025 → 140 gilt noch nicht
        self.assertEqual(aktiver_vs_code(konto), '001')

    def test_fallback_auf_konto_stammdaten(self):
        konto = _create_konto(self.wj, vs='010')
        self.assertEqual(aktiver_vs_code(konto), '010')

    def test_kein_vs_wirft_fehler(self):
        konto = _create_konto(self.wj, vs=None)
        with self.assertRaises(VerteilerschluesselFehler):
            aktiver_vs_code(konto)


# ---------------------------------------------------------------------------
# Stammdaten-VS (Fläche / MEA / Kopf) über VerteilerschluesselWert
# ---------------------------------------------------------------------------

class StammdatenAnteilTest(VerteilerschluesselServiceTestBase):
    def test_mea_anteil(self):
        vs = _create_vs_config(self.objekt, '010', 'mea')
        _create_vs_wert(vs, self.e1, '300')
        _create_vs_wert(vs, self.e2, '700')
        self.assertEqual(mea_anteil(self.e1, self.wj), Decimal('0.3'))
        self.assertEqual(mea_anteil(self.e2, self.wj), Decimal('0.7'))

    def test_flaechen_anteil_ueber_konto(self):
        vs = _create_vs_config(self.objekt, '001', 'flaeche')
        _create_vs_wert(vs, self.e1, '80')
        _create_vs_wert(vs, self.e2, '120')
        konto = _create_konto(self.wj)
        KontoVerteilerSchluessel.objects.create(
            konto=konto, vs_code='001', gueltig_ab=date(2020, 1, 1))
        self.assertEqual(anteil_einheit(konto, self.e1, self.wj), Decimal('0.4'))

    def test_kopf_anteil(self):
        vs = _create_vs_config(self.objekt, '030', 'kopf')
        _create_vs_wert(vs, self.e1, '2')
        _create_vs_wert(vs, self.e2, '3')
        self.assertEqual(
            anteil_einheit_fuer_vs_code('030', self.e1, self.wj), Decimal('0.4'))

    def test_jahresspezifischer_wert_ueberschreibt_zeitlos(self):
        vs = _create_vs_config(self.objekt, '010', 'mea')
        _create_vs_wert(vs, self.e1, '500', wj_jahr=0)
        _create_vs_wert(vs, self.e1, '250', wj_jahr=2025)  # Override fürs WJ
        _create_vs_wert(vs, self.e2, '750', wj_jahr=0)
        self.assertEqual(mea_anteil(self.e1, self.wj), Decimal('0.25'))

    def test_nicht_beteiligte_einheit_zaehlt_nicht_zum_gesamt(self):
        vs = _create_vs_config(self.objekt, '010', 'mea')
        _create_vs_wert(vs, self.e1, '300')
        _create_vs_wert(vs, self.e2, '700', beteiligt=False)
        self.assertEqual(mea_anteil(self.e1, self.wj), Decimal('1'))

    def test_vs_nicht_konfiguriert_wirft_fehler(self):
        with self.assertRaises(VerteilerschluesselFehler):
            anteil_einheit_fuer_vs_code('010', self.e1, self.wj)

    def test_fehlender_wert_fuer_einheit_wirft_fehler(self):
        vs = _create_vs_config(self.objekt, '010', 'mea')
        _create_vs_wert(vs, self.e2, '700')  # e1 hat keinen Wert
        with self.assertRaises(VerteilerschluesselFehler):
            mea_anteil(self.e1, self.wj)

    def test_null_wert_bei_anderer_einheit_wirft_fehler(self):
        vs = _create_vs_config(self.objekt, '010', 'mea')
        _create_vs_wert(vs, self.e1, '300')
        _create_vs_wert(vs, self.e2, None)
        with self.assertRaises(VerteilerschluesselFehler):
            mea_anteil(self.e1, self.wj)


# ---------------------------------------------------------------------------
# Verbrauchs-VS (140–145) über EinheitVerbrauch
# ---------------------------------------------------------------------------

class VerbrauchAnteilTest(VerteilerschluesselServiceTestBase):
    def _verbrauch(self, einheit, wert, vs_code='140'):
        return EinheitVerbrauch.objects.create(
            wirtschaftsjahr=self.wj, einheit=einheit, vs_code=vs_code,
            wert=Decimal(wert) if wert is not None else None,
        )

    def test_verbrauchs_anteil(self):
        self._verbrauch(self.e1, '25')
        self._verbrauch(self.e2, '75')
        konto = _create_konto(self.wj, kontonummer='50200')
        KontoVerteilerSchluessel.objects.create(
            konto=konto, vs_code='140', gueltig_ab=date(2020, 1, 1))
        self.assertEqual(anteil_einheit(konto, self.e1, self.wj), Decimal('0.25'))

    def test_fehlender_verbrauchswert_blockiert(self):
        """Spec Kap. 4.3: kein automatischer Fallback auf anderen Schlüssel."""
        self._verbrauch(self.e2, '75')  # e1 hat keinen Datensatz
        with self.assertRaises(VerteilerschluesselFehler):
            anteil_einheit_fuer_vs_code('140', self.e1, self.wj)

    def test_null_verbrauchswert_blockiert(self):
        self._verbrauch(self.e1, '25')
        self._verbrauch(self.e2, None)
        with self.assertRaises(VerteilerschluesselFehler):
            anteil_einheit_fuer_vs_code('140', self.e1, self.wj)

    def test_verbrauch_anderes_wj_zaehlt_nicht(self):
        wj_alt = _create_wj(self.objekt, jahr=2024)
        EinheitVerbrauch.objects.create(
            wirtschaftsjahr=wj_alt, einheit=self.e1, vs_code='140', wert=Decimal('99'))
        with self.assertRaises(VerteilerschluesselFehler):
            anteil_einheit_fuer_vs_code('140', self.e1, self.wj)

    def test_fehler_traegt_konto_und_einheit_kontext(self):
        konto = _create_konto(self.wj, kontonummer='50300')
        KontoVerteilerSchluessel.objects.create(
            konto=konto, vs_code='140', gueltig_ab=date(2020, 1, 1))
        try:
            anteil_einheit(konto, self.e1, self.wj)
            self.fail('VerteilerschluesselFehler erwartet')
        except VerteilerschluesselFehler as exc:
            self.assertEqual(exc.konto, konto)
            self.assertEqual(exc.einheit, self.e1)
            self.assertEqual(exc.vs_code, '140')
