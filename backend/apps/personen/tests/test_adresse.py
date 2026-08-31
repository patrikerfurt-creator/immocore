"""
Tests für die Adress-Zerlegung und die Synchronisation von
``Person.adresse`` mit den Einzelfeldern.

Die Beispiele sind an den realen Bestandsformaten orientiert (593
Adressen, davon 591 zweizeilig „Straße Hausnummer / PLZ Ort").
"""
from django.test import TestCase

from apps.personen.adresse import (
    baue_adresse,
    trenne_plz_ort,
    trenne_strasse_hausnummer,
    zerlege_adresse,
)
from apps.personen.models import Person


class TrenneStrasseHausnummerTest(TestCase):
    def test_einfache_hausnummer(self):
        self.assertEqual(trenne_strasse_hausnummer('Otto-Hahn-Straße 60'),
                         ('Otto-Hahn-Straße', '60'))

    def test_hausnummer_mit_buchstabe(self):
        self.assertEqual(trenne_strasse_hausnummer('Wittelsbacherallee 35A'),
                         ('Wittelsbacherallee', '35A'))

    def test_hausnummer_als_bereich(self):
        self.assertEqual(trenne_strasse_hausnummer('Mergenthaler Allee 15-21'),
                         ('Mergenthaler Allee', '15-21'))

    def test_mehrfache_leerzeichen_werden_normalisiert(self):
        self.assertEqual(trenne_strasse_hausnummer('Zur Pappelallee  33'),
                         ('Zur Pappelallee', '33'))

    def test_strassenname_mit_zahl_bleibt_erhalten(self):
        """„Straße des 17. Juni 5" — nur die letzte Zahl ist die Hausnummer."""
        self.assertEqual(trenne_strasse_hausnummer('Straße des 17. Juni 5'),
                         ('Straße des 17. Juni', '5'))

    def test_ohne_hausnummer_bleibt_alles_in_der_strasse(self):
        """Verlustfrei statt falsch abgeschnitten."""
        self.assertEqual(trenne_strasse_hausnummer('Kausche Immob. Verw. GbR'),
                         ('Kausche Immob. Verw. GbR', ''))

    def test_leer(self):
        self.assertEqual(trenne_strasse_hausnummer(''), ('', ''))


class TrennePlzOrtTest(TestCase):
    def test_fuenfstellige_plz(self):
        self.assertEqual(trenne_plz_ort('63303 Dreieich'), ('63303', 'Dreieich'))

    def test_ort_mit_leerzeichen(self):
        self.assertEqual(trenne_plz_ort('60388 Frankfurt am Main'),
                         ('60388', 'Frankfurt am Main'))

    def test_ohne_plz_bleibt_alles_im_ort(self):
        self.assertEqual(trenne_plz_ort('Frankfurt'), ('', 'Frankfurt'))


class ZerlegeAdresseTest(TestCase):
    def test_bestandsformat(self):
        self.assertEqual(
            zerlege_adresse('Otto-Hahn-Straße 60\n63303 Dreieich'),
            {'strasse': 'Otto-Hahn-Straße', 'hausnummer': '60',
             'plz': '63303', 'ort': 'Dreieich'},
        )

    def test_einzeiler_ohne_plz(self):
        self.assertEqual(
            zerlege_adresse('Polna 13F'),
            {'strasse': 'Polna', 'hausnummer': '13F', 'plz': '', 'ort': ''},
        )

    def test_leere_adresse(self):
        self.assertEqual(
            zerlege_adresse(''),
            {'strasse': '', 'hausnummer': '', 'plz': '', 'ort': ''},
        )

    def test_zusatzzeile_geht_nicht_verloren(self):
        teile = zerlege_adresse('c/o Verwaltung\nHauptstraße 5\n12345 Musterstadt')
        self.assertIn('c/o Verwaltung', teile['strasse'])
        self.assertEqual(teile['plz'], '12345')

    def test_rueckweg_ist_verlustfrei(self):
        original = 'Hessenring 12\n63071 Offenbach'
        teile = zerlege_adresse(original)
        self.assertEqual(
            baue_adresse(teile['strasse'], teile['hausnummer'], teile['plz'], teile['ort']),
            original,
        )


class PersonAdressSynchronisationTest(TestCase):
    def test_einzelfelder_erzeugen_den_textblock(self):
        person = Person.objects.create(
            personennummer='P-ADR-1', person_typ='100', nachname='Test',
            strasse='Hauptstraße', hausnummer='5', plz='12345', ort='Musterstadt',
        )
        self.assertEqual(person.adresse, 'Hauptstraße 5\n12345 Musterstadt')

    def test_nur_textblock_gesetzt_fuellt_die_einzelfelder(self):
        """Altcode, der weiterhin nur ``adresse`` setzt, darf die neuen
        Felder nicht leer lassen."""
        person = Person.objects.create(
            personennummer='P-ADR-2', person_typ='100', nachname='Test',
            adresse='Bahnhofstraße 7\n54321 Neustadt',
        )
        self.assertEqual(person.strasse, 'Bahnhofstraße')
        self.assertEqual(person.hausnummer, '7')
        self.assertEqual(person.plz, '54321')
        self.assertEqual(person.ort, 'Neustadt')

    def test_aenderung_eines_einzelfeldes_aktualisiert_den_textblock(self):
        person = Person.objects.create(
            personennummer='P-ADR-3', person_typ='100', nachname='Test',
            strasse='Hauptstraße', hausnummer='5', plz='12345', ort='Musterstadt',
        )
        person.hausnummer = '9'
        person.save(update_fields=['hausnummer'])

        person.refresh_from_db()
        self.assertEqual(person.adresse, 'Hauptstraße 9\n12345 Musterstadt')

    def test_update_fields_ohne_adressbezug_bleibt_unberuehrt(self):
        """Ein Teil-Save auf einem anderen Feld darf nicht plötzlich die
        Adressspalten mitschreiben."""
        person = Person.objects.create(
            personennummer='P-ADR-4', person_typ='100', nachname='Test',
            strasse='Hauptstraße', hausnummer='5', plz='12345', ort='Musterstadt',
        )
        person.telefon = '0123'
        person.save(update_fields=['telefon'])

        person.refresh_from_db()
        self.assertEqual(person.telefon, '0123')
        self.assertEqual(person.adresse, 'Hauptstraße 5\n12345 Musterstadt')

    def test_person_ohne_adresse_bleibt_leer(self):
        person = Person.objects.create(
            personennummer='P-ADR-5', person_typ='100', nachname='Test',
        )
        self.assertEqual(person.adresse, '')
        self.assertEqual(person.strasse, '')
