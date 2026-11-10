"""SEPAMandat-Datenmodell (Portal-SEPA-Mandat, Phase 2).

Deckt ab: Constraints (je Geltungsbereich hoechstens ein aktives Mandat,
Einheitenmandat braucht Mandatsgeber), Legacy-Weg ohne Person und die
Bestands-Datenmigration ``0025_sepamandat_bestand_zu_sammelmandat``.
"""
from datetime import date

from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from apps.personen.models import SEPAMandat
from apps.portal.tests.basis import (
    erstelle_eigentuemer, erstelle_einheit, erstelle_objekt, verknuepfe,
)


def _mandat(referenz, aktiv=True, person=None, ev=None, iban='DE02120300000000202051'):
    return SEPAMandat.objects.create(
        mandatsreferenz=referenz, iban=iban, unterzeichnet_am=date(2026, 1, 1),
        aktiv=aktiv, person=person, eigentumsverhaeltnis=ev,
    )


class SepaMandatConstraintTest(TestCase):

    def setUp(self):
        self.person = erstelle_eigentuemer()
        self.objekt = erstelle_objekt()
        self.einheit = erstelle_einheit(self.objekt)
        self.ev = verknuepfe(self.person, self.einheit)

    def test_zweites_aktives_sammelmandat_je_person_verboten(self):
        _mandat('T-SAMMEL-1', person=self.person)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _mandat('T-SAMMEL-2', person=self.person)

    def test_zweites_aktives_einheitenmandat_je_ev_verboten(self):
        _mandat('T-EV-1', person=self.person, ev=self.ev)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _mandat('T-EV-2', person=self.person, ev=self.ev)

    def test_inaktives_zweites_mandat_im_selben_bereich_erlaubt(self):
        _mandat('T-SAMMEL-A', person=self.person)
        _mandat('T-SAMMEL-B', person=self.person, aktiv=False)
        _mandat('T-EV-A', person=self.person, ev=self.ev)
        _mandat('T-EV-B', person=self.person, ev=self.ev, aktiv=False)
        self.assertEqual(SEPAMandat.objects.count(), 4)

    def test_sammel_und_einheitenmandat_nebeneinander_erlaubt(self):
        _mandat('T-SAMMEL-C', person=self.person)
        _mandat('T-EV-C', person=self.person, ev=self.ev)
        self.assertEqual(SEPAMandat.objects.filter(aktiv=True).count(), 2)

    def test_einheitenmandat_ohne_person_verboten(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _mandat('T-EV-OHNE-PERSON', person=None, ev=self.ev)

    def test_mandat_ohne_person_und_ev_bleibt_anlegbar(self):
        m1 = _mandat('T-LEGACY-1')
        m2 = _mandat('T-LEGACY-2', iban='DE89370400440532013000')
        self.assertTrue(m1.ist_sammelmandat)
        self.assertTrue(m2.ist_sammelmandat)
        self.assertEqual(m1.quelle, SEPAMandat.QUELLE_VERWALTUNG)

    def test_einheitenmandat_ist_kein_sammelmandat(self):
        m = _mandat('T-EV-D', person=self.person, ev=self.ev)
        self.assertFalse(m.ist_sammelmandat)


class SepaMandatBestandsMigrationTest(TransactionTestCase):
    """Datenmigration 0025 ueber den MigrationExecutor (0024 -> 0025)."""

    vor = [('personen', '0024_sepamandat_person_ev_quelle')]
    nach = [('personen', '0025_sepamandat_bestand_zu_sammelmandat')]
    aktuell = [('personen', '0026_sepamandat_constraints')]

    def _migriere(self, ziel):
        executor = MigrationExecutor(connection)
        executor.migrate(ziel)
        return MigrationExecutor(connection).loader.project_state(ziel).apps

    def tearDown(self):
        # DB fuer nachfolgende Tests wieder auf den aktuellen Stand bringen.
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_bestand_wird_nur_bei_eindeutigem_referenten_zugeordnet(self):
        alt = self._migriere(self.vor)
        Mandat = alt.get_model('personen', 'SEPAMandat')
        Person = alt.get_model('personen', 'Person')

        def mandat(ref):
            return Mandat.objects.create(
                mandatsreferenz=ref, iban='DE02120300000000202051',
                unterzeichnet_am=date(2026, 1, 1),
            )

        m1, m2, m3 = mandat('MIG-M1'), mandat('MIG-M2'), mandat('MIG-M3')
        p1 = Person.objects.create(personennummer='MIG-P1', person_typ='100', sepa_mandat=m1)
        Person.objects.create(personennummer='MIG-P2', person_typ='100', sepa_mandat=m2)
        Person.objects.create(personennummer='MIG-P3', person_typ='100', sepa_mandat=m2)

        neu = self._migriere(self.nach)
        Mandat = neu.get_model('personen', 'SEPAMandat')
        self.assertEqual(Mandat.objects.get(pk=m1.pk).person_id, p1.pk)
        self.assertIsNone(Mandat.objects.get(pk=m1.pk).eigentumsverhaeltnis_id)
        self.assertIsNone(Mandat.objects.get(pk=m2.pk).person_id)
        self.assertIsNone(Mandat.objects.get(pk=m3.pk).person_id)

        # Zweiter Lauf (zurueck auf 0024, erneut 0025): idempotent.
        self._migriere(self.vor)
        neu = self._migriere(self.nach)
        Mandat = neu.get_model('personen', 'SEPAMandat')
        self.assertEqual(Mandat.objects.get(pk=m1.pk).person_id, p1.pk)
        self.assertIsNone(Mandat.objects.get(pk=m2.pk).person_id)
        self.assertIsNone(Mandat.objects.get(pk=m3.pk).person_id)

        # Constraints (0026) lassen sich auf dem migrierten Bestand anlegen.
        self._migriere(self.aktuell)
