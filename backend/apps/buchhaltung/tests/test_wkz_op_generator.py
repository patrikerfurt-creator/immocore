"""
Tests für WKZ OP-Generator:
- Idempotenz-Verhalten
- Fälligkeits-Berechnung je Rhythmus
- Wochenend-Regel
- Vorlauf-Tage-Fenster
- gueltig_bis-Stopp
"""
from decimal import Decimal
from datetime import date, timedelta

from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.objekte.models import Objekt
from apps.konten.models import Konto
from apps.rechnungen.models import Kreditor
from apps.buchhaltung.models import (
    WiederkehrendeBuchungVorlage,
    WiederkehrendeBuchungOP,
    KreditorOP,
)
from apps.buchhaltung.services.wkz.vorlage_service import erstelle_vorlage, aktiviere_vorlage
from apps.buchhaltung.services.wkz.op_generator_service import (
    wende_wochenend_regel_an,
    berechne_fallige_perioden,
    erzeuge_einzelnen_op,
    erzeuge_faellige_ops,
)

User = get_user_model()


def _setup():
    user = User.objects.create_user('gen_user', password='x')
    objekt = Objekt.objects.create(
        bezeichnung='Test-WEG', objektnummer='G001', objekt_typ='WEG',
        ort='Frankfurt', verwaltung_seit=date(2020, 1, 1),
        zahlungsfreigabe_grenzen=[],
    )
    Konto.objects.create(objekt=objekt, kontonummer='50100', kontoname='Wasser',
                         kontoart='standard', direktes_buchen=False, aktiv=True)
    kreditor = Kreditor.objects.create(name='Stadtwerke', iban='DE11111111111111111111')
    return user, objekt, kreditor


def _aktive_vorlage(objekt, kreditor, user, **overrides):
    defaults = {
        'objekt': objekt,
        'kreditor': kreditor,
        'bezeichnung': 'Test WKZ',
        'typ': 'vertrag',
        'betrag_gesamt': Decimal('100.00'),
        'rhythmus': 'quartalsweise',
        'erste_faelligkeit': date(2026, 1, 1),
        'bei_wochenende': 'unveraendert',
        'vorlauf_tage': 7,
        'toleranz_betrag': Decimal('5.00'),
        'toleranz_tage': 14,
        'bescheid_pflicht': False,
        'gueltig_ab': date(2025, 12, 1),  # Muss vor dem Stichtag liegen
    }
    defaults.update(overrides)
    splits = [{'kontonummer': '50100', 'bezeichnung': 'Test', 'betrag': defaults['betrag_gesamt']}]
    vorlage = erstelle_vorlage(defaults, splits, user)
    aktiviere_vorlage(vorlage, user)
    return vorlage


# ---------------------------------------------------------------------------
# Wochenend-Regel
# ---------------------------------------------------------------------------

class WochenendRegelTest(TestCase):
    def test_werktag_unveraendert(self):
        montag = date(2026, 1, 5)  # Montag
        self.assertEqual(wende_wochenend_regel_an(montag, 'vor'), montag)

    def test_samstag_vor(self):
        samstag = date(2026, 1, 3)  # Samstag
        freitag = date(2026, 1, 2)
        self.assertEqual(wende_wochenend_regel_an(samstag, 'vor'), freitag)

    def test_sonntag_vor(self):
        sonntag = date(2026, 1, 4)
        freitag = date(2026, 1, 2)
        self.assertEqual(wende_wochenend_regel_an(sonntag, 'vor'), freitag)

    def test_samstag_zurueck(self):
        samstag = date(2026, 1, 3)
        montag = date(2026, 1, 5)
        self.assertEqual(wende_wochenend_regel_an(samstag, 'zurueck'), montag)

    def test_sonntag_zurueck(self):
        sonntag = date(2026, 1, 4)
        montag = date(2026, 1, 5)
        self.assertEqual(wende_wochenend_regel_an(sonntag, 'zurueck'), montag)

    def test_unveraendert_bleibt(self):
        samstag = date(2026, 1, 3)
        self.assertEqual(wende_wochenend_regel_an(samstag, 'unveraendert'), samstag)


# ---------------------------------------------------------------------------
# Fälligkeits-Berechnung
# ---------------------------------------------------------------------------

class FaelligkeitenBerechnung(TestCase):
    def setUp(self):
        self.user, self.objekt, self.kreditor = _setup()

    def test_quartalsweise_perioden(self):
        """Quartalsweise mit 7 Tagen Vorlauf: 1 Quartal im Fenster."""
        vorlage = _aktive_vorlage(
            self.objekt, self.kreditor, self.user,
            erste_faelligkeit=date(2026, 1, 1),
            vorlauf_tage=7,
        )
        # Stichtag 1 Woche vor erster Fälligkeit → 1 Periode im Fenster
        stichtag = date(2025, 12, 31)
        perioden = berechne_fallige_perioden(vorlage, stichtag)
        self.assertEqual(len(perioden), 1)
        self.assertEqual(perioden[0].faellig_am, date(2026, 1, 1))

    def test_frei_rhythmus_leer(self):
        """Rhythmus 'frei' → immer leere Liste."""
        vorlage = _aktive_vorlage(
            self.objekt, self.kreditor, self.user,
            rhythmus='frei',
            erste_faelligkeit=date(2026, 1, 1),
        )
        perioden = berechne_fallige_perioden(vorlage, date(2026, 6, 1))
        self.assertEqual(perioden, [])

    def test_gueltig_bis_stopp(self):
        """Keine OPs nach gueltig_bis."""
        vorlage = _aktive_vorlage(
            self.objekt, self.kreditor, self.user,
            erste_faelligkeit=date(2026, 1, 1),
            gueltig_bis=date(2026, 3, 31),
            vorlauf_tage=365,
            gueltig_ab=date(2025, 12, 1),
        )
        perioden = berechne_fallige_perioden(vorlage, date(2026, 1, 1))
        # Q1 (Jan) liegt innerhalb, Q2 (Apr) liegt außerhalb gueltig_bis
        self.assertGreater(len(perioden), 0)
        for p in perioden:
            self.assertLessEqual(p.faellig_am, date(2026, 3, 31))

    def test_idempotenz_bereits_vorhanden(self):
        """Bereits vorhandener OP wird nicht doppelt geliefert."""
        vorlage = _aktive_vorlage(
            self.objekt, self.kreditor, self.user,
            erste_faelligkeit=date(2026, 1, 1),
            vorlauf_tage=7,
        )
        stichtag = date(2025, 12, 31)
        perioden = berechne_fallige_perioden(vorlage, stichtag)
        self.assertEqual(len(perioden), 1)

        # OP erzeugen
        erzeuge_einzelnen_op(vorlage, perioden[0])

        # Nochmal berechnen → leer (bereits vorhanden)
        perioden_2 = berechne_fallige_perioden(vorlage, stichtag)
        self.assertEqual(len(perioden_2), 0)


# ---------------------------------------------------------------------------
# Hauptlauf
# ---------------------------------------------------------------------------

class HauptlaufTest(TestCase):
    def setUp(self):
        self.user, self.objekt, self.kreditor = _setup()

    def test_lauf_erzeugt_ops(self):
        vorlage = _aktive_vorlage(
            self.objekt, self.kreditor, self.user,
            erste_faelligkeit=date(2026, 1, 1),
            vorlauf_tage=7,
        )
        ergebnis = erzeuge_faellige_ops(stichtag=date(2025, 12, 31))
        self.assertGreater(ergebnis.erzeugt, 0)
        self.assertEqual(len(ergebnis.fehler), 0)
        # KreditorOP wurde angelegt
        self.assertTrue(KreditorOP.objects.filter(kreditor=self.kreditor).exists())

    def test_lauf_idempotent(self):
        _aktive_vorlage(
            self.objekt, self.kreditor, self.user,
            erste_faelligkeit=date(2026, 1, 1),
            vorlauf_tage=7,
        )
        ergebnis1 = erzeuge_faellige_ops(stichtag=date(2025, 12, 31))
        ergebnis2 = erzeuge_faellige_ops(stichtag=date(2025, 12, 31))
        self.assertGreater(ergebnis1.erzeugt, 0)
        self.assertEqual(ergebnis2.erzeugt, 0)  # zweiter Lauf erzeugt nichts

    def test_op_herkunft_wkz(self):
        vorlage = _aktive_vorlage(
            self.objekt, self.kreditor, self.user,
            erste_faelligkeit=date(2026, 1, 1),
            vorlauf_tage=7,
        )
        erzeuge_faellige_ops(stichtag=date(2025, 12, 31))
        op = KreditorOP.objects.filter(kreditor=self.kreditor).first()
        self.assertEqual(op.herkunft, 'wkz_vorlage')
        self.assertIsNone(op.buchung)  # noch keine Buchung (erst bei Bankabgang)
