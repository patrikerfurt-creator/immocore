"""
Tests für WKZ Vorlage-Service:
- Split-Summen-Validierung
- Konto-Bereich-Validierung
- Freigabe-Workflow
- Statusübergänge
- ersetze_vorlage (Versionierung)
"""
from decimal import Decimal
from datetime import date

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.objekte.models import Objekt
from apps.konten.models import Konto
from apps.rechnungen.models import Kreditor
from apps.buchhaltung.models import WiederkehrendeBuchungVorlage, WiederkehrendeBuchungSplit
from apps.buchhaltung.services.wkz.vorlage_service import (
    erstelle_vorlage,
    validiere_splits,
    validiere_split_kontonummer,
    reiche_vorlage_zur_freigabe_ein,
    aktiviere_vorlage,
    pausiere_vorlage,
    reaktiviere_vorlage,
    beende_vorlage,
    ersetze_vorlage,
)

User = get_user_model()


def _setup():
    """Legt Basisobjekte für alle Tests an."""
    user = User.objects.create_user('testuser', password='x')
    objekt = Objekt.objects.create(
        bezeichnung='Test-WEG',
        objektnummer='T001',
        objekt_typ='WEG',
        ort='Teststadt',
        verwaltung_seit=date(2020, 1, 1),
        zahlungsfreigabe_grenzen=[],
    )
    # Aufwandskonten
    konto_50100 = Konto.objects.create(
        objekt=objekt, kontonummer='50100', kontoname='Wasser',
        kontoart='standard', direktes_buchen=False, aktiv=True,
    )
    konto_50200 = Konto.objects.create(
        objekt=objekt, kontonummer='50200', kontoname='Müll',
        kontoart='standard', direktes_buchen=False, aktiv=True,
    )
    # Bankkonto (kein split-zulässiges Konto)
    Konto.objects.create(
        objekt=objekt, kontonummer='18000', kontoname='Bank',
        kontoart='standard', direktes_buchen=True, aktiv=True,
    )
    kreditor = Kreditor.objects.create(name='Stadt Frankfurt', iban='DE12345678901234567890')
    return user, objekt, konto_50100, konto_50200, kreditor


def _vorlage_data(objekt, kreditor, **kwargs):
    defaults = {
        'objekt': objekt,
        'kreditor': kreditor,
        'bezeichnung': 'Versorgungsgebühren',
        'typ': 'bescheid',
        'betrag_gesamt': Decimal('850.00'),
        'rhythmus': 'quartalsweise',
        'erste_faelligkeit': date(2026, 1, 15),
        'bei_wochenende': 'zurueck',
        'vorlauf_tage': 7,
        'toleranz_betrag': Decimal('5.00'),
        'toleranz_tage': 14,
        'bescheid_pflicht': True,
        'gueltig_ab': date(2026, 1, 1),
    }
    defaults.update(kwargs)
    return defaults


def _splits_data():
    return [
        {'kontonummer': '50100', 'bezeichnung': 'Wasser', 'betrag': Decimal('570.00')},
        {'kontonummer': '50200', 'bezeichnung': 'Müll', 'betrag': Decimal('280.00')},
    ]


class VorlageAnlageTest(TestCase):
    def setUp(self):
        self.user, self.objekt, self.k50100, self.k50200, self.kreditor = _setup()

    def test_vorlage_anlegen_ok(self):
        data = _vorlage_data(self.objekt, self.kreditor)
        vorlage = erstelle_vorlage(data, _splits_data(), self.user)
        self.assertEqual(vorlage.status, 'entwurf')
        self.assertEqual(vorlage.splits.count(), 2)

    def test_split_summe_falsch_raises(self):
        data = _vorlage_data(self.objekt, self.kreditor)
        splits = [
            {'kontonummer': '50100', 'bezeichnung': 'Wasser', 'betrag': Decimal('400.00')},
            # 400 + 280 = 680 ≠ 850
            {'kontonummer': '50200', 'bezeichnung': 'Müll', 'betrag': Decimal('280.00')},
        ]
        with self.assertRaises(ValidationError):
            erstelle_vorlage(data, splits, self.user)

    def test_split_konto_ausserhalb_bereich_raises(self):
        data = _vorlage_data(self.objekt, self.kreditor, betrag_gesamt=Decimal('100.00'))
        # 18000 liegt außerhalb 50000–55999 (wird in _setup bereits angelegt)
        splits = [{'kontonummer': '18000', 'bezeichnung': 'Bank', 'betrag': Decimal('100.00')}]
        with self.assertRaises(ValidationError):
            erstelle_vorlage(data, splits, self.user)

    def test_split_direktes_buchen_raises(self):
        """Konto mit direktes_buchen=True darf nicht als Split verwendet werden."""
        data = _vorlage_data(self.objekt, self.kreditor, betrag_gesamt=Decimal('100.00'))
        Konto.objects.create(
            objekt=self.objekt, kontonummer='50999', kontoname='Direkt',
            kontoart='standard', direktes_buchen=True, aktiv=True,
        )
        splits = [{'kontonummer': '50999', 'bezeichnung': 'Test', 'betrag': Decimal('100.00')}]
        with self.assertRaises(ValidationError):
            erstelle_vorlage(data, splits, self.user)

    def test_jahresbetrag_berechnung(self):
        data = _vorlage_data(self.objekt, self.kreditor)
        vorlage = erstelle_vorlage(data, _splits_data(), self.user)
        # Quartalsweise: 4 × 850 = 3400
        self.assertEqual(vorlage.jahresbetrag, Decimal('3400.00'))

    def test_perioden_pro_jahr(self):
        data = _vorlage_data(self.objekt, self.kreditor)
        vorlage = erstelle_vorlage(data, _splits_data(), self.user)
        self.assertEqual(vorlage.perioden_pro_jahr, 4)


class FreigabeWorkflowTest(TestCase):
    def setUp(self):
        self.user, self.objekt, _, _, self.kreditor = _setup()

    def test_auto_freigabe_ohne_grenzen(self):
        """Ohne zahlungsfreigabe_grenzen → automatische Aktivierung."""
        data = _vorlage_data(self.objekt, self.kreditor)
        vorlage = erstelle_vorlage(data, _splits_data(), self.user)
        reiche_vorlage_zur_freigabe_ein(vorlage.id, self.user)
        vorlage.refresh_from_db()
        self.assertEqual(vorlage.status, 'aktiv')

    def test_einreichen_nur_von_entwurf(self):
        data = _vorlage_data(self.objekt, self.kreditor)
        vorlage = erstelle_vorlage(data, _splits_data(), self.user)
        aktiviere_vorlage(vorlage, self.user)
        with self.assertRaises(ValueError):
            reiche_vorlage_zur_freigabe_ein(vorlage.id, self.user)


class StatusUebergangsTest(TestCase):
    def setUp(self):
        self.user, self.objekt, _, _, self.kreditor = _setup()
        data = _vorlage_data(self.objekt, self.kreditor)
        self.vorlage = erstelle_vorlage(data, _splits_data(), self.user)
        aktiviere_vorlage(self.vorlage, self.user)

    def test_pausieren(self):
        pausiere_vorlage(self.vorlage.id, 'Test', self.user)
        self.vorlage.refresh_from_db()
        self.assertEqual(self.vorlage.status, 'pausiert')

    def test_reaktivieren_nach_pause(self):
        pausiere_vorlage(self.vorlage.id, 'Test', self.user)
        reaktiviere_vorlage(self.vorlage.id, self.user)
        self.vorlage.refresh_from_db()
        self.assertEqual(self.vorlage.status, 'aktiv')

    def test_pausieren_nur_aktiv(self):
        pausiere_vorlage(self.vorlage.id, 'Test', self.user)
        with self.assertRaises(ValueError):
            pausiere_vorlage(self.vorlage.id, 'Nochmal', self.user)

    def test_beenden(self):
        beende_vorlage(self.vorlage.id, date(2026, 12, 31), 'Ende', self.user)
        self.vorlage.refresh_from_db()
        self.assertEqual(self.vorlage.status, 'beendet')
        self.assertEqual(self.vorlage.gueltig_bis, date(2026, 12, 31))


class ErsetzVorlageTest(TestCase):
    def setUp(self):
        self.user, self.objekt, k50100, k50200, self.kreditor = _setup()
        # Weitere Konten für neue Splits
        Konto.objects.get_or_create(
            objekt=self.objekt, kontonummer='50300',
            defaults={'kontoname': 'Abwasser', 'kontoart': 'standard', 'direktes_buchen': False, 'aktiv': True},
        )
        data = _vorlage_data(self.objekt, self.kreditor)
        self.alte_vorlage = erstelle_vorlage(data, _splits_data(), self.user)
        aktiviere_vorlage(self.alte_vorlage, self.user)

    def test_ersetzen_beendet_alte(self):
        neue_daten = {
            'betrag_gesamt': Decimal('900.00'),
            'erste_faelligkeit': date(2026, 4, 15),
            'gueltig_ab': date(2026, 4, 1),
        }
        neue_splits = [
            {'kontonummer': '50100', 'bezeichnung': 'Wasser', 'betrag': Decimal('600.00')},
            {'kontonummer': '50300', 'bezeichnung': 'Abwasser', 'betrag': Decimal('300.00')},
        ]
        neue_vorlage = ersetze_vorlage(self.alte_vorlage.id, neue_daten, neue_splits, self.user)
        self.alte_vorlage.refresh_from_db()

        self.assertEqual(self.alte_vorlage.status, 'beendet')
        self.assertEqual(self.alte_vorlage.gueltig_bis, date(2026, 3, 31))
        self.assertEqual(neue_vorlage.ersetzt_vorlage, self.alte_vorlage)
        self.assertEqual(neue_vorlage.betrag_gesamt, Decimal('900.00'))
