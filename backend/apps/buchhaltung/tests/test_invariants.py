"""
Invarianten-Suite Jahresabrechnung (HGA-Spec v1.0 Kap. 11.3, Phase D)

Läuft gegen einen vollständigen Freigabe-Durchlauf (Schritt 6 + 8) mit
Nachzahlungs- und Guthaben-Fall.
"""
from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.buchhaltung.models import (
    Buchungsart,
    EinzelAbrechnung,
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


class InvariantenTest(EinzelAbrechnungServiceTestBase):
    def setUp(self):
        super().setUp()
        Buchungsart.objects.get_or_create(
            nr='950', defaults=dict(bezeichnung='Abrechnungsergebnis'))
        self._create_kosten('1000.00')
        self._create_soll(self.ev1, '200.00', date(2025, 1, 1))   # e1: +100
        self._create_soll(self.ev2, '900.00', date(2025, 1, 1))   # e2: −200
        berechne_alle_einzelabrechnungen(self.ja)
        freigebe_jahresabrechnung(self.ja, self.user)

    def test_abrechnungsergebnis_konsistent(self):
        """abrechnungsergebnis == kostenanteil_gesamt - hausgeld_soll_gesamt für alle EinzelAbrechnung."""
        for ea in EinzelAbrechnung.objects.all():
            self.assertEqual(
                ea.abrechnungsergebnis,
                ea.kostenanteil_gesamt - ea.hausgeld_soll_gesamt,
                f"Invariante verletzt bei {ea}",
            )

    def test_gesperrte_abrechnung_hat_sollstellung(self):
        """Jede EinzelAbrechnung einer gesperrten Jahresabrechnung mit Ergebnis != 0 hat eine sollstellung-FK."""
        for ea in EinzelAbrechnung.objects.filter(
            jahresabrechnung__status='gesperrt',
        ).exclude(abrechnungsergebnis=0):
            self.assertIsNotNone(
                ea.sollstellung, f"Sollstellung fehlt bei {ea}")
            self.assertEqual(
                ea.sollstellung.sollstellungs_typ, 'abrechnungsergebnis')

    def test_keine_doppelte_einzelabrechnung(self):
        """UniqueConstraint (jahresabrechnung, einheit) wird eingehalten."""
        vorlage = EinzelAbrechnung.objects.filter(einheit=self.e1).first()
        with self.assertRaises(IntegrityError), transaction.atomic():
            EinzelAbrechnung.objects.create(
                jahresabrechnung=vorlage.jahresabrechnung,
                einheit=vorlage.einheit,
                eigentuemer=vorlage.eigentuemer,
                eigentumsverhaeltnis=vorlage.eigentumsverhaeltnis,
                hausgeld_soll_gesamt=Decimal('0'),
                kostenanteil_gesamt=Decimal('0'),
                abrechnungsergebnis=Decimal('0'),
            )

    def test_kein_automatischer_auszahlungslauf(self):
        """
        Nach freigebe_jahresabrechnung existiert kein Auszahlungslauf.
        Ein Auszahlungslauf-Modell existiert im System noch nicht
        (Nebenbuch-Spec Kap. 10.5 offen) — abgesichert wird, dass die
        Freigabe keinen weiteren Lauf neben dem Abrechnungsergebnis-Lauf
        angestoßen hat.
        """
        laeufe = HausgeldSollstellungslauf.objects.filter(objekt=self.objekt)
        self.assertEqual(laeufe.count(), 1)
        self.assertEqual(laeufe.first(), self.ja.sollstellungslauf)
        self.assertEqual(laeufe.first().typ, 'abrechnungsergebnis_jahr')
