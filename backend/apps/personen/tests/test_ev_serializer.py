"""Der EigentumsVerhaeltnisSerializer liefert Objektbezug mit.

In der Personen-Detailansicht listet die Tabelle "Verknüpfte Einheiten" je
Eigentumsverhältnis auch das Objekt — damit erkennbar ist, in welchem Objekt
eine Person eine Einheit hat, wenn sie in mehreren Objekten Einheiten besitzt.
"""
from datetime import date

from django.test import TestCase

from apps.objekte.models import Einheit, Objekt
from apps.personen.models import EigentumsVerhaeltnis, Person
from apps.personen.serializers import EigentumsVerhaeltnisSerializer


class EVSerializerObjektbezugTest(TestCase):
    def setUp(self):
        self.objekt = Objekt.objects.create(
            objektnummer='53', objekt_typ='WEG', bezeichnung='WEG Musterstraße 1',
            strasse='Musterstraße 1', plz='60311', ort='Frankfurt',
            verwaltung_seit=date(2020, 1, 1),
        )
        self.einheit = Einheit.objects.create(
            objekt=self.objekt, einheit_nr='12', einheit_typ='Wohnung', lage='2. OG links',
        )
        self.person = Person.objects.create(
            personennummer='100123', person_typ='100', anrede='Herr',
            vorname='Hans', nachname='Muster',
        )
        self.ev = EigentumsVerhaeltnis.objects.create(
            einheit=self.einheit, person=self.person, beginn=date(2020, 1, 1),
        )

    def test_objekt_bezeichnung_und_nummer_werden_geliefert(self):
        daten = EigentumsVerhaeltnisSerializer(self.ev).data
        self.assertEqual(daten['objekt_bezeichnung'], 'WEG Musterstraße 1')
        self.assertEqual(daten['objekt_nummer'], '53')
        self.assertEqual(daten['einheit_nr'], '12')
