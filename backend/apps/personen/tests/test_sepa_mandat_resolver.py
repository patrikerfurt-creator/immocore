"""Resolver fuer SEPA-Mandate (Portal-SEPA-Mandat, Phase 3).

Rangfolge: Einheitenmandat > Sammelmandat der Person > Legacy-Rueckfall
(``Person.sepa_mandat``) > None.
"""
from datetime import date

from django.test import TestCase

from apps.personen.models import EigentumsVerhaeltnis, SEPAMandat
from apps.personen.services.sepa_mandat import (
    mandat_fuer_ev, mandate_fuer_evs, sammelmandat_fuer_person,
)
from apps.portal.tests.basis import (
    erstelle_eigentuemer, erstelle_einheit, erstelle_objekt, verknuepfe,
)


def _mandat(referenz, person=None, ev=None, aktiv=True, iban='DE02120300000000202051'):
    return SEPAMandat.objects.create(
        mandatsreferenz=referenz, iban=iban, unterzeichnet_am=date(2026, 1, 1),
        aktiv=aktiv, person=person, eigentumsverhaeltnis=ev,
    )


def _legacy(person, mandat):
    person.sepa_mandat = mandat
    person.save(update_fields=['sepa_mandat'])


def _lade(*evs):
    """EVs mit geladener Person, wie es der Resolver von Aufrufern erwartet."""
    ids = [e.id for e in evs]
    by_id = {e.id: e for e in EigentumsVerhaeltnis.objects.select_related('person').filter(id__in=ids)}
    return [by_id[i] for i in ids]


class ResolverRangfolgeTest(TestCase):

    def setUp(self):
        self.person = erstelle_eigentuemer()
        self.objekt = erstelle_objekt()
        self.ev1 = verknuepfe(self.person, erstelle_einheit(self.objekt, nr='0001'))
        self.ev2 = verknuepfe(self.person, erstelle_einheit(self.objekt, nr='0002'))

    def test_einheitenmandat_schlaegt_sammelmandat(self):
        einheit = _mandat('R-EV1', person=self.person, ev=self.ev1)
        sammel = _mandat('R-SAMMEL', person=self.person)
        ev1, ev2 = _lade(self.ev1, self.ev2)
        ergebnis = mandate_fuer_evs([ev1, ev2])
        self.assertEqual(ergebnis[ev1.id], einheit)
        self.assertEqual(ergebnis[ev2.id], sammel)
        self.assertEqual(mandat_fuer_ev(ev1), einheit)
        self.assertEqual(mandat_fuer_ev(ev2), sammel)

    def test_nur_sammelmandat_gilt_fuer_alle_evs(self):
        sammel = _mandat('R-SAMMEL', person=self.person)
        ev1, ev2 = _lade(self.ev1, self.ev2)
        ergebnis = mandate_fuer_evs([ev1, ev2])
        self.assertEqual(ergebnis[ev1.id], sammel)
        self.assertEqual(ergebnis[ev2.id], sammel)

    def test_kein_mandat_liefert_none(self):
        ev1, ev2 = _lade(self.ev1, self.ev2)
        self.assertEqual(mandate_fuer_evs([ev1, ev2]), {ev1.id: None, ev2.id: None})
        self.assertIsNone(mandat_fuer_ev(ev1))

    def test_leere_eingabe(self):
        self.assertEqual(mandate_fuer_evs([]), {})

    def test_inaktives_einheitenmandat_wird_uebersprungen(self):
        _mandat('R-EV1-ALT', person=self.person, ev=self.ev1, aktiv=False)
        sammel = _mandat('R-SAMMEL', person=self.person)
        ev1, = _lade(self.ev1)
        self.assertEqual(mandat_fuer_ev(ev1), sammel)

    def test_inaktives_sammelmandat_liefert_none(self):
        _mandat('R-SAMMEL-ALT', person=self.person, aktiv=False)
        ev1, = _lade(self.ev1)
        self.assertIsNone(mandat_fuer_ev(ev1))

    def test_ev_aktivitaet_wird_nicht_geprueft(self):
        sammel = _mandat('R-SAMMEL', person=self.person)
        self.ev1.ende = date(2021, 12, 31)
        self.ev1.save()
        ev1, = _lade(self.ev1)
        self.assertEqual(mandat_fuer_ev(ev1), sammel)


class ResolverLegacyTest(TestCase):

    def setUp(self):
        self.person = erstelle_eigentuemer()
        self.fremde = erstelle_eigentuemer(
            nachname='Fremd', email='fremd@example.org', personennummer='P-PORTAL-2')
        objekt = erstelle_objekt()
        self.ev = verknuepfe(self.person, erstelle_einheit(objekt))

    def test_legacy_mandat_ohne_person_wird_geliefert(self):
        mandat = _mandat('L-1')
        _legacy(self.person, mandat)
        ev, = _lade(self.ev)
        self.assertEqual(mandat_fuer_ev(ev), mandat)

    def test_legacy_mandat_mit_eigener_person_wird_geliefert(self):
        mandat = _mandat('L-2', person=self.person)
        _legacy(self.person, mandat)
        ev, = _lade(self.ev)
        self.assertEqual(mandat_fuer_ev(ev), mandat)

    def test_legacy_mandat_einer_fremden_person_wird_nicht_geliefert(self):
        mandat = _mandat('L-3', person=self.fremde)
        _legacy(self.person, mandat)
        ev, = _lade(self.ev)
        self.assertIsNone(mandat_fuer_ev(ev))

    def test_inaktives_legacy_mandat_wird_nicht_geliefert(self):
        _legacy(self.person, _mandat('L-4', aktiv=False))
        ev, = _lade(self.ev)
        self.assertIsNone(mandat_fuer_ev(ev))

    def test_sammelmandat_hat_vorrang_vor_legacy(self):
        _legacy(self.person, _mandat('L-5'))
        sammel = _mandat('L-SAMMEL', person=self.person)
        ev, = _lade(self.ev)
        self.assertEqual(mandat_fuer_ev(ev), sammel)


class ResolverBulkTest(TestCase):

    def test_mehrere_personen_je_ev_richtiges_mandat_mit_zwei_queries(self):
        objekt = erstelle_objekt()
        p1 = erstelle_eigentuemer()
        p2 = erstelle_eigentuemer(
            nachname='Zwei', email='zwei@example.org', personennummer='P-PORTAL-2')
        p3 = erstelle_eigentuemer(
            nachname='Drei', email='drei@example.org', personennummer='P-PORTAL-3')
        ev1 = verknuepfe(p1, erstelle_einheit(objekt, nr='0001'))
        ev2 = verknuepfe(p2, erstelle_einheit(objekt, nr='0002'))
        ev3 = verknuepfe(p2, erstelle_einheit(objekt, nr='0003'))
        ev4 = verknuepfe(p3, erstelle_einheit(objekt, nr='0004'))
        m1 = _mandat('B-P1', person=p1)
        m2_ev = _mandat('B-P2-EV2', person=p2, ev=ev2)
        m2_sammel = _mandat('B-P2', person=p2)
        m3 = _mandat('B-P3-LEGACY')
        _legacy(p3, m3)

        evs = list(EigentumsVerhaeltnis.objects.select_related('person').filter(
            id__in=[ev1.id, ev2.id, ev3.id, ev4.id]))
        with self.assertNumQueries(1):
            ergebnis = mandate_fuer_evs(evs)
        self.assertEqual(ergebnis[ev1.id], m1)
        self.assertEqual(ergebnis[ev2.id], m2_ev)
        self.assertEqual(ergebnis[ev3.id], m2_sammel)
        self.assertEqual(ergebnis[ev4.id], m3)


class SammelmandatFuerPersonTest(TestCase):

    def setUp(self):
        self.person = erstelle_eigentuemer()
        self.ev = verknuepfe(self.person, erstelle_einheit(erstelle_objekt()))

    def test_sammelmandat_wird_geliefert(self):
        sammel = _mandat('S-1', person=self.person)
        self.assertEqual(sammelmandat_fuer_person(self.person), sammel)

    def test_nur_einheitenmandat_liefert_none(self):
        _mandat('S-EV', person=self.person, ev=self.ev)
        self.assertIsNone(sammelmandat_fuer_person(self.person))

    def test_legacy_wird_geliefert(self):
        mandat = _mandat('S-LEGACY')
        _legacy(self.person, mandat)
        self.assertEqual(sammelmandat_fuer_person(self.person), mandat)

    def test_legacy_als_einheitenmandat_wird_nicht_geliefert(self):
        mandat = _mandat('S-LEGACY-EV', person=self.person, ev=self.ev)
        _legacy(self.person, mandat)
        self.assertIsNone(sammelmandat_fuer_person(self.person))

    def test_inaktives_sammelmandat_liefert_none(self):
        _mandat('S-INAKTIV', person=self.person, aktiv=False)
        self.assertIsNone(sammelmandat_fuer_person(self.person))
