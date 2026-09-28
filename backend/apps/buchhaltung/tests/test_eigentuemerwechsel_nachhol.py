"""
Nachhol-Sollstellungen beim Eigentümerwechsel.

Der Fall aus der Praxis: der Wechsel wirkt zum laufenden Monat, dessen
Sollstellung beim Verkäufer bereits gestellt und im Wechsel storniert wurde.
`nachhol_perioden` liefert nur vollständig abgelaufene Monate — der laufende
Monat blieb dadurch für den Käufer ungestellt, und sein (neu angelegtes)
Personenkonto blieb leer.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.buchhaltung.models import Buchungsart, HausgeldSollstellung
from apps.buchhaltung.services.eigentuemerwechsel_service import (
    commite_wechsel,
    nachhol_perioden,
)
from apps.konten.models import Abrechnungsart, Personenkonto
from apps.objekte.models import Einheit, Objekt, Wirtschaftsjahr
from apps.personen.models import EigentumsVerhaeltnis, Person


class NachholPeriodenTest(TestCase):
    """Reine Periodenrechnung — ohne DB-Zustand."""

    def test_nur_abgelaufene_monate(self):
        self.assertEqual(
            nachhol_perioden(date(2026, 6, 1), date(2026, 9, 7)),
            [date(2026, 6, 1), date(2026, 7, 1), date(2026, 8, 1)],
        )

    def test_laufender_monat_nicht_enthalten(self):
        self.assertEqual(nachhol_perioden(date(2026, 9, 1), date(2026, 9, 7)), [])

    def test_zukuenftige_periode_leer(self):
        self.assertEqual(nachhol_perioden(date(2026, 11, 1), date(2026, 9, 7)), [])

    def test_jahreswechsel(self):
        self.assertEqual(
            nachhol_perioden(date(2025, 12, 1), date(2026, 2, 3)),
            [date(2025, 12, 1), date(2026, 1, 1)],
        )


class CommiteWechselNachholTest(TestCase):

    HEUTE = date(2026, 9, 7)

    def setUp(self):
        self.user = get_user_model().objects.create_user(username='ew_nachhol', password='x')
        self.objekt = Objekt.objects.create(
            bezeichnung='Test-WEG-Nachhol', objektnummer='990088', objekt_typ='WEG',
            strasse='Teststr. 3', plz='60000', ort='Teststadt',
            verwaltung_seit=date(2020, 1, 1),
        )
        Wirtschaftsjahr.objects.create(objekt=self.objekt, jahr=2026, beginn_monat=1)
        self.einheit = Einheit.objects.create(
            objekt=self.objekt, einheit_nr='W07', lage='2. OG',
        )
        self.ba900, _ = Buchungsart.objects.get_or_create(
            nr='900', defaults={'bezeichnung': 'Hausgeld'},
        )
        Abrechnungsart.objects.get_or_create(
            objekt=self.objekt, code='900', defaults={'bezeichnung': 'Hausgeld'},
        )

        verkaeufer = Person.objects.create(vorname='Vera', nachname='Verkauf', person_typ='100')
        self.kaeufer = Person.objects.create(vorname='Karl', nachname='Kauf', person_typ='100')
        self.verkaeufer_ev = EigentumsVerhaeltnis.objects.create(
            einheit=self.einheit, person=verkaeufer, beginn=date(2020, 1, 1),
        )

        self.entscheidungen = {
            'kaeufer_person_id': str(self.kaeufer.id),
            'kaeufer_iban': '',
            'hausgeld_je_ba': {'.900': '300.00'},
            'stornieren_ids': [],
            'erstatten': [],
            'verkaeufer_iban': None,
        }

    def _sollstellung(self, ev, periode, **kwargs):
        return HausgeldSollstellung.objects.create(
            objekt=self.objekt, eigentumsverhaeltnis=ev,
            sollstellungs_typ='hausgeld', periode=periode, faellig_am=periode,
            opos_nr=kwargs.pop('opos_nr'), soll_betrag=Decimal('300.00'),
            status_cached='offen', erstellt_von=self.user, **kwargs,
        )

    def _commit(self, wirkungs_periode, stichtag):
        return commite_wechsel(
            einheit=self.einheit, stichtag=stichtag,
            wirkungs_periode=wirkungs_periode,
            entscheidungen=self.entscheidungen, user=self.user,
            heute=self.HEUTE,
        )

    def _kaeufer_perioden(self, result):
        return sorted(
            HausgeldSollstellung.objects
            .filter(eigentumsverhaeltnis_id=result['kaeufer_ev_id'])
            .values_list('periode', flat=True)
        )

    def test_laufender_monat_wird_nachgeholt_wenn_lauf_schon_lief(self):
        """September-Lauf ist gelaufen → der Käufer bekommt September gestellt."""
        self._sollstellung(self.verkaeufer_ev, date(2026, 9, 1), opos_nr='990088000000019')
        result = self._commit(date(2026, 9, 1), date(2026, 9, 1))

        self.assertEqual(self._kaeufer_perioden(result), [date(2026, 9, 1)])
        self.assertEqual(len(result['nachhol_sollstellungs_ids']), 1)

    def test_laufender_monat_bleibt_offen_wenn_lauf_noch_nicht_lief(self):
        """Kein September-Lauf → der reguläre Lauf holt den Käufer mit ab."""
        result = self._commit(date(2026, 9, 1), date(2026, 9, 1))

        self.assertEqual(self._kaeufer_perioden(result), [])
        self.assertEqual(result['nachhol_sollstellungs_ids'], [])

    def test_rueckwirkend_holt_abgelaufene_monate_und_laufenden_monat(self):
        for i, periode in enumerate([date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1)]):
            self._sollstellung(
                self.verkaeufer_ev, periode, opos_nr=f'99008800000002{i}',
            )
        result = self._commit(date(2026, 7, 1), date(2026, 7, 1))

        self.assertEqual(
            self._kaeufer_perioden(result),
            [date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1)],
        )

    def test_keine_doppelstellung_bei_vorhandener_periode(self):
        """
        Hat der Käufer für die Periode schon eine Sollstellung, wird sie nicht
        ein zweites Mal angelegt. Die UniqueConstraint greift hier nicht, weil
        `ba` NULL ist und PostgreSQL NULLs als verschieden behandelt.
        """
        self._sollstellung(self.verkaeufer_ev, date(2026, 9, 1), opos_nr='990088000000035')
        kaeufer_ev = EigentumsVerhaeltnis.objects.create(
            einheit=Einheit.objects.create(objekt=self.objekt, einheit_nr='W08', lage='EG'),
            person=self.kaeufer, beginn=date(2026, 9, 1),
        )
        self._sollstellung(kaeufer_ev, date(2026, 9, 1), opos_nr='990088000000043')

        # Wechsel auf W07 — der Käufer bekommt dort ein eigenes EV, die
        # bestehende Sollstellung auf W08 darf ihn nicht blockieren.
        result = self._commit(date(2026, 9, 1), date(2026, 9, 1))
        self.assertEqual(self._kaeufer_perioden(result), [date(2026, 9, 1)])

    def test_kaeufer_erhaelt_neues_personenkonto_mit_eigener_nummer(self):
        """
        Der Käufer bekommt NICHT die Kontonummer des Verkäufers, sondern die
        nächste freie im Objekt. Genau das führt in der Debitorenliste zu einem
        vermeintlich leeren „alten" Konto.
        """
        verkaeufer_nr = Personenkonto.objects.get(vertrag=self.verkaeufer_ev).kontonummer
        result = self._commit(date(2026, 9, 1), date(2026, 9, 1))

        self.assertIsNotNone(result['kaeufer_personenkonto_nr'])
        self.assertNotEqual(result['kaeufer_personenkonto_nr'], verkaeufer_nr)
        self.assertEqual(result['verkaeufer_personenkonto_nr'], verkaeufer_nr)


class WirkungsPeriodeTest(TestCase):
    """
    Die Wirkungsperiode ist immer der Monatserste nach dem Stichtag. Auf Live
    kam durch einen Zeitzonenfehler im Wizard „2025-12-31" an — ein Datum, das
    als Periode fachlich nicht existiert und Storno-Grenze wie Nachhol-Perioden
    verschiebt.
    """

    def test_monatsmitte_ergibt_folgemonat(self):
        from apps.buchhaltung.services.eigentuemerwechsel_service import (
            bestimme_wirkungs_periode,
        )
        self.assertEqual(bestimme_wirkungs_periode(date(2026, 8, 15)), date(2026, 9, 1))

    def test_dezember_ergibt_januar_des_folgejahres(self):
        from apps.buchhaltung.services.eigentuemerwechsel_service import (
            bestimme_wirkungs_periode,
        )
        self.assertEqual(bestimme_wirkungs_periode(date(2025, 12, 12)), date(2026, 1, 1))

    def test_monatserster_bleibt(self):
        from apps.buchhaltung.services.eigentuemerwechsel_service import (
            bestimme_wirkungs_periode,
        )
        self.assertEqual(bestimme_wirkungs_periode(date(2026, 3, 1)), date(2026, 3, 1))
