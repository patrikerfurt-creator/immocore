"""
Tests für ObjektHandwerker (Phase A, Orchestrator-Vorgabe 4).

Deckt ab:
  - doppelte (objekt, kreditor)-Zuordnung wird vom UniqueConstraint abgewiesen
  - Sortierung nach prioritaet (Meta.ordering)
"""
from datetime import date

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.handwerker.models import ObjektHandwerker
from apps.objekte.models import Objekt
from apps.rechnungen.models import Kreditor


def _objekt(nr="H200"):
    return Objekt.objects.create(
        bezeichnung="Test-WEG ObjektHandwerker", objektnummer=nr, objekt_typ="weg",
        ort="Teststadt", verwaltung_seit=date(2020, 1, 1),
    )


def _kreditor(name):
    return Kreditor.objects.create(name=name, ist_handwerker=True, email=f"{name}@example.de")


class ObjektHandwerkerUniqueConstraintTest(TestCase):
    def test_doppelte_zuordnung_wird_abgewiesen(self):
        objekt = _objekt()
        kreditor = _kreditor("Doppel-Handwerker GmbH")
        ObjektHandwerker.objects.create(objekt=objekt, kreditor=kreditor)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ObjektHandwerker.objects.create(objekt=objekt, kreditor=kreditor)


class ObjektHandwerkerOrderingTest(TestCase):
    def test_sortierung_nach_prioritaet(self):
        objekt = _objekt("H201")
        k1 = _kreditor("Handwerker Eins")
        k2 = _kreditor("Handwerker Zwei")
        k3 = _kreditor("Handwerker Drei")
        z_hoch = ObjektHandwerker.objects.create(objekt=objekt, kreditor=k1, prioritaet=3)
        z_niedrig = ObjektHandwerker.objects.create(objekt=objekt, kreditor=k2, prioritaet=1)
        z_mittel = ObjektHandwerker.objects.create(objekt=objekt, kreditor=k3, prioritaet=2)

        ergebnis = list(ObjektHandwerker.objects.filter(objekt=objekt))
        self.assertEqual(ergebnis, [z_niedrig, z_mittel, z_hoch])
