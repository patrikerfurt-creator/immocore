"""
Tests: jahresabrechnung/freigabe_service + run_abrechnungsergebnis
(HGA-Spec v1.0 Kap. 6, Phase D)

Atomic-Verhalten, Aufruf run_abrechnungsergebnis, Verknüpfung sollstellung-FK,
Guthaben als negative Sollstellung (Constraint 0045), kein Auszahlungslauf-Trigger.
"""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.buchhaltung.models import (
    Buchungsart,
    HausgeldSollstellung,
    HausgeldSollstellungslauf,
)
from apps.buchhaltung.services.jahresabrechnung.einzelabrechnung_service import (
    berechne_alle_einzelabrechnungen,
)
from apps.buchhaltung.services.jahresabrechnung.freigabe_service import (
    freigebe_jahresabrechnung,
)
from apps.buchhaltung.tests.test_einzelabrechnung_service import (
    EinzelAbrechnungServiceTestBase,
)


class FreigabeTestBase(EinzelAbrechnungServiceTestBase):
    """
    Ausgangslage je Test: 2 Einheiten (MEA 300/700), Kosten 1.000 €.
    e1: Kostenanteil 300, Soll 200 → Nachzahlung +100
    e2: Kostenanteil 700, Soll 900 → Guthaben −200
    """

    def setUp(self):
        super().setUp()
        self.ba_950, _ = Buchungsart.objects.get_or_create(
            nr='950', defaults=dict(bezeichnung='Abrechnungsergebnis'))
        self._create_kosten('1000.00')
        self._create_soll(self.ev1, '200.00', date(2025, 1, 1))
        self._create_soll(self.ev2, '900.00', date(2025, 1, 1))
        self.eas = berechne_alle_einzelabrechnungen(self.ja)


class FreigabeAblaufTest(FreigabeTestBase):
    def test_kompletter_ablauf(self):
        ja = freigebe_jahresabrechnung(self.ja, self.user)

        # Jahresabrechnung gesperrt + Metadaten
        self.assertEqual(ja.status, 'gesperrt')
        self.assertIsNotNone(ja.freigegeben_am)
        self.assertEqual(ja.freigegeben_von, self.user)
        self.assertIsNotNone(ja.sollstellungslauf)

        # Lauf korrekt
        lauf = ja.sollstellungslauf
        self.assertEqual(lauf.typ, 'abrechnungsergebnis_jahr')
        self.assertEqual(lauf.status, 'commited')
        self.assertEqual(lauf.periode, self.wj.ende_datum)
        self.assertEqual(lauf.anzahl_sollstellungen, 2)
        self.assertEqual(lauf.summe, Decimal('-100.00'))  # +100 − 200

        # Sollstellungen je EA verknüpft, Typ + BA korrekt
        for ea in self.ja.einzelabrechnungen.all():
            self.assertIsNotNone(ea.sollstellung)
            self.assertEqual(ea.sollstellung.sollstellungs_typ, 'abrechnungsergebnis')
            self.assertEqual(ea.sollstellung.ba, self.ba_950)
            self.assertEqual(ea.sollstellung.soll_betrag, ea.abrechnungsergebnis)
            self.assertEqual(
                ea.sollstellung.eigentumsverhaeltnis, ea.eigentumsverhaeltnis)
            # PDF als Dokument persistiert
            self.assertIsNotNone(ea.dokument)
            self.assertEqual(ea.dokument.kategorie, 'Jahresabrechnung')

    def test_guthaben_erzeugt_negative_sollstellung(self):
        """Kap. 6.2 + Constraint-Erweiterung 0045: Guthaben = negativer soll_betrag."""
        freigebe_jahresabrechnung(self.ja, self.user)
        ea2 = self.ja.einzelabrechnungen.get(einheit=self.e2)
        self.assertEqual(ea2.abrechnungsergebnis, Decimal('-200.00'))
        self.assertEqual(ea2.sollstellung.soll_betrag, Decimal('-200.00'))

    def test_keine_sachkontenbuchung(self):
        """Kap. 6.3: Schritt 8 erzeugt keine Buchung im Hauptbuch."""
        from apps.buchhaltung.models import Buchung
        vorher = Buchung.objects.count()
        freigebe_jahresabrechnung(self.ja, self.user)
        self.assertEqual(Buchung.objects.count(), vorher)

    def test_kein_automatischer_auszahlungslauf(self):
        """
        Kap. 6.3: kein Auszahlungslauf-Trigger. Ein Auszahlungslauf-Modell
        existiert noch nicht (Nebenbuch-Spec Kap. 10.5 offen) — es darf nach
        der Freigabe genau EIN Lauf existieren: der Abrechnungsergebnis-Lauf.
        """
        freigebe_jahresabrechnung(self.ja, self.user)
        laeufe = HausgeldSollstellungslauf.objects.filter(objekt=self.objekt)
        self.assertEqual(laeufe.count(), 1)
        self.assertEqual(laeufe.first().typ, 'abrechnungsergebnis_jahr')


class ErgebnisNullTest(FreigabeTestBase):
    def test_ergebnis_null_keine_sollstellung(self):
        """Kap. 6.2: EVs mit Ergebnis == 0 werden übersprungen (kein leerer OP)."""
        # e1 Soll auf exakt Kostenanteil anheben → Ergebnis 0
        self._create_soll(self.ev1, '100.00', date(2025, 2, 1))
        berechne_alle_einzelabrechnungen(self.ja)
        freigebe_jahresabrechnung(self.ja, self.user)

        ea1 = self.ja.einzelabrechnungen.get(einheit=self.e1)
        self.assertEqual(ea1.abrechnungsergebnis, Decimal('0.00'))
        self.assertIsNone(ea1.sollstellung)
        self.assertEqual(self.ja.sollstellungslauf.anzahl_sollstellungen, 1)
        # e2 hat weiterhin eine Sollstellung
        ea2 = self.ja.einzelabrechnungen.get(einheit=self.e2)
        self.assertIsNotNone(ea2.sollstellung)


class FreigabeValidierungTest(FreigabeTestBase):
    def test_nur_entwurf_freigebbar(self):
        freigebe_jahresabrechnung(self.ja, self.user)
        with self.assertRaises(ValidationError):
            freigebe_jahresabrechnung(self.ja, self.user)

    def test_fehlende_einzelabrechnung_blockiert(self):
        self.ja.einzelabrechnungen.get(einheit=self.e2).delete()
        with self.assertRaisesMessage(ValidationError, 'WE02'):
            freigebe_jahresabrechnung(self.ja, self.user)
        self.ja.refresh_from_db()
        self.assertEqual(self.ja.status, 'entwurf')

    def test_vs_fehler_blockiert(self):
        """Kap. 7: ungeklärte Verteilerschlüssel-Fehler verhindern die Freigabe."""
        self._create_kosten('500.00', kontonummer='50200', vs='140')  # ohne Verbräuche
        berechne_alle_einzelabrechnungen(self.ja)
        with self.assertRaisesMessage(ValidationError, 'Verteilerschlüssel'):
            freigebe_jahresabrechnung(self.ja, self.user)
        self.ja.refresh_from_db()
        self.assertEqual(self.ja.status, 'entwurf')

    def test_atomic_rollback_bei_lauffehler(self):
        """
        Schlägt run_abrechnungsergebnis fehl (Duplikat-Lauf), wird alles
        zurückgerollt: Status bleibt entwurf, keine Sollstellungen,
        keine Dokument-Verknüpfungen.
        """
        HausgeldSollstellungslauf.objects.create(
            objekt=self.objekt, typ='abrechnungsergebnis_jahr',
            periode=self.wj.ende_datum, status='commited',
            erstellt_von=self.user,
        )
        with self.assertRaises(ValidationError):
            freigebe_jahresabrechnung(self.ja, self.user)
        self.ja.refresh_from_db()
        self.assertEqual(self.ja.status, 'entwurf')
        self.assertIsNone(self.ja.sollstellungslauf)
        self.assertEqual(
            HausgeldSollstellung.objects.filter(
                sollstellungs_typ='abrechnungsergebnis').count(), 0)
        for ea in self.ja.einzelabrechnungen.all():
            self.assertIsNone(ea.dokument)
            self.assertIsNone(ea.sollstellung)
