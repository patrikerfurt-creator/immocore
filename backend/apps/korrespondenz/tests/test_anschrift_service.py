"""Test 8 (Spec 11): Anschriftzeilen."""
from django.test import SimpleTestCase

from apps.korrespondenz.services.anschrift_service import AnschriftZuLang, anschrift_zeilen
from apps.personen.models import Person


def _person(**kw):
    """Ungespeicherte Person - anschrift_zeilen liest nur Felder."""
    basis = dict(person_typ='100', strasse='Musterweg', hausnummer='5', plz='60311', ort='Frankfurt am Main')
    basis.update(kw)
    return Person(**basis)


class AnschriftZeilenTest(SimpleTestCase):

    def test_einzelperson(self):
        p = _person(anrede='Herr', vorname='Max', nachname='Mustermann')
        self.assertEqual(anschrift_zeilen(p), [
            'Herrn', 'Max Mustermann', 'Musterweg 5', '60311 Frankfurt am Main',
        ])

    def test_frau(self):
        p = _person(anrede='Frau', vorname='Erika', nachname='Muster')
        self.assertEqual(anschrift_zeilen(p)[:2], ['Frau', 'Erika Muster'])

    def test_eheleute_zweite_person_in_eigener_zeile(self):
        p = _person(anrede='Eheleute', vorname='Max', nachname='Mustermann', vorname2='Erika')
        self.assertEqual(anschrift_zeilen(p), [
            'Eheleute', 'Max Mustermann', 'Erika Mustermann', 'Musterweg 5', '60311 Frankfurt am Main',
        ])

    def test_eheleute_mit_abweichendem_zweiten_nachnamen(self):
        p = _person(anrede='Eheleute', vorname='Max', nachname='Mustermann',
                    vorname2='Erika', nachname2='Beispiel')
        self.assertEqual(anschrift_zeilen(p)[1:3], ['Max Mustermann', 'Erika Beispiel'])

    def test_firma(self):
        p = _person(anrede='Firma', ist_firma=True, firmenname='Muster GmbH')
        self.assertEqual(anschrift_zeilen(p), [
            'Firma', 'Muster GmbH', 'Musterweg 5', '60311 Frankfurt am Main',
        ])

    def test_firma_ohne_anrede_feld_bekommt_zeile_firma(self):
        p = _person(anrede='', ist_firma=True, firmenname='Muster GmbH')
        self.assertEqual(anschrift_zeilen(p)[:2], ['Firma', 'Muster GmbH'])

    def test_titel_beider_personen(self):
        p = _person(anrede='Eheleute', titel='Prof. Dr.', vorname='Max', nachname='Mustermann',
                    titel2='Dr.', vorname2='Erika')
        self.assertEqual(anschrift_zeilen(p)[1:3], ['Prof. Dr. Max Mustermann', 'Dr. Erika Mustermann'])

    def test_auslandsadresse_mehrzeilig_in_strasse_bleibt_unveraendert(self):
        p = _person(anrede='Herr', vorname='Jean', nachname='Dupont',
                    strasse='12 Rue de Rivoli\n75001 Paris\nFRANKREICH', hausnummer='', plz='', ort='')
        self.assertEqual(anschrift_zeilen(p), [
            'Herrn', 'Jean Dupont', '12 Rue de Rivoli', '75001 Paris', 'FRANKREICH',
        ])

    def test_sonderfall_komplette_adresse_in_strasse(self):
        p = _person(anrede='Frau', vorname='Erika', nachname='Muster',
                    strasse='Postfach 12 34, 60001 Frankfurt', hausnummer='', plz='', ort='')
        self.assertEqual(anschrift_zeilen(p)[-1], 'Postfach 12 34, 60001 Frankfurt')
        self.assertEqual(len(anschrift_zeilen(p)), 3)

    def test_leere_zeilen_entfallen(self):
        p = _person(anrede='', vorname='', nachname='Mustermann', hausnummer='', ort='')
        self.assertEqual(anschrift_zeilen(p), ['Mustermann', 'Musterweg', '60311'])

    def test_ohne_anrede_keine_anredezeile(self):
        p = _person(anrede='', vorname='Max', nachname='Mustermann')
        self.assertEqual(anschrift_zeilen(p)[0], 'Max Mustermann')

    def test_hausnummer_haengt_an_letzter_strassenzeile(self):
        p = _person(anrede='Herr', vorname='Max', nachname='Muster',
                    strasse='c/o Verwaltung\nMusterweg', hausnummer='5b')
        self.assertIn('Musterweg 5b', anschrift_zeilen(p))
        self.assertIn('c/o Verwaltung', anschrift_zeilen(p))

    def test_maximal_sieben_zeilen_sieben_ist_erlaubt(self):
        p = _person(anrede='Eheleute', vorname='Max', nachname='Muster', vorname2='Erika',
                    strasse='c/o A\nc/o B\nMusterweg', hausnummer='5')
        zeilen = anschrift_zeilen(p)
        self.assertEqual(len(zeilen), 7)

    def test_mehr_als_sieben_zeilen_ist_fehler_statt_kuerzung(self):
        p = _person(anrede='Eheleute', vorname='Max', nachname='Muster', vorname2='Erika',
                    strasse='c/o A\nc/o B\nc/o C\nMusterweg', hausnummer='5')
        with self.assertRaises(AnschriftZuLang):
            anschrift_zeilen(p)

    def test_nie_leere_zeile(self):
        p = _person(anrede='Herr', vorname='Max', nachname='Muster', strasse='A\n\n  \nB')
        self.assertNotIn('', anschrift_zeilen(p))
