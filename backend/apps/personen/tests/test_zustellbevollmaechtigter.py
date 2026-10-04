"""Tests für den Zustellungsbevollmächtigten (Person-Typ 500).

Ist an einer Person ein Zustellungsbevollmächtigter hinterlegt, gehen alle
Schreiben/Mails/PDFs an ihn. Zentraler Einstieg ist ``Person.zustell_adressat``;
die Umleitung in den Versandwegen baut darauf auf.
"""
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.personen.models import Person
from apps.personen.serializers import PersonSerializer


def _person(nr, typ='100', **felder):
    basis = dict(
        personennummer=nr, person_typ=typ, anrede='Herr', vorname='Hans',
        nachname='Muster', strasse='Testweg', hausnummer='1', plz='60311',
        ort='Frankfurt',
    )
    basis.update(felder)
    return Person.objects.create(**basis)


class ZustellAdressatTest(TestCase):
    def test_ohne_bevollmaechtigten_liefert_sich_selbst(self):
        p = _person('Z-1')
        self.assertEqual(p.zustell_adressat(), p)

    def test_mit_bevollmaechtigtem_liefert_diesen(self):
        zb = _person('Z-2', typ='500', nachname='Bevoll')
        p = _person('Z-3', zustellungsbevollmaechtigter=zb)
        self.assertEqual(p.zustell_adressat(), zb)

    def test_nur_ein_hop_keine_kette(self):
        """Ein Bevollmächtigter bekommt selbst keinen Bevollmächtigten."""
        zb = _person('Z-4', typ='500', nachname='Bevoll')
        p = _person('Z-5', zustellungsbevollmaechtigter=zb)
        # zb.zustell_adressat() bleibt zb — es gibt keine Weiterleitung.
        self.assertEqual(zb.zustell_adressat(), zb)
        self.assertEqual(p.zustell_adressat().zustell_adressat(), zb)


class CleanValidierungTest(TestCase):
    def test_selbstreferenz_verboten(self):
        p = _person('Z-6', typ='500')
        p.zustellungsbevollmaechtigter = p
        with self.assertRaises(ValidationError):
            p.clean()

    def test_bevollmaechtigter_muss_typ_500_sein(self):
        falsch = _person('Z-7', typ='100')
        p = _person('Z-8')
        p.zustellungsbevollmaechtigter = falsch
        with self.assertRaises(ValidationError):
            p.clean()

    def test_typ_500_darf_keinen_bevollmaechtigten_haben(self):
        zb = _person('Z-9', typ='500', nachname='Bevoll')
        p = _person('Z-10', typ='500')
        p.zustellungsbevollmaechtigter = zb
        with self.assertRaises(ValidationError):
            p.clean()

    def test_gueltige_zuordnung_ist_ok(self):
        zb = _person('Z-11', typ='500', nachname='Bevoll')
        p = _person('Z-12', zustellungsbevollmaechtigter=zb)
        p.clean()  # wirft nicht


class SerializerTest(TestCase):
    def test_name_wird_ausgegeben(self):
        zb = _person('Z-13', typ='500', nachname='Bevoll', vorname='Berta')
        p = _person('Z-14', zustellungsbevollmaechtigter=zb)
        daten = PersonSerializer(p).data
        self.assertEqual(daten['zustellungsbevollmaechtigter'], zb.id)
        self.assertEqual(daten['zustellungsbevollmaechtigter_name'], zb.name)

    def test_validierung_lehnt_falschen_typ_ab(self):
        falsch = _person('Z-15', typ='100')
        p = _person('Z-16')
        ser = PersonSerializer(p, data={'zustellungsbevollmaechtigter': str(falsch.id)}, partial=True)
        self.assertFalse(ser.is_valid())
        self.assertIn('zustellungsbevollmaechtigter', ser.errors)

    def test_validierung_akzeptiert_typ_500(self):
        zb = _person('Z-17', typ='500', nachname='Bevoll')
        p = _person('Z-18')
        ser = PersonSerializer(p, data={'zustellungsbevollmaechtigter': str(zb.id)}, partial=True)
        self.assertTrue(ser.is_valid(), ser.errors)
