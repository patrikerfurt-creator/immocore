"""
Tests fuer die Spiegelung der Legacy-Kontaktfelder.

``Person.email``/``Person.telefon`` stammen aus der Import-Zeit; gelesen
wird im Projekt zuerst aus ``emails``/``telefonnummern``. Das
Bearbeitungsformular schreibt nur die Listen — ohne Spiegelung zeigte die
Personenliste dauerhaft die Import-Adresse (Fall Person 100419:
Liste ``patrik.erfurt@gmail.com``, Legacy-Feld ``torsten.steinruecken@gmx.de``).
"""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.personen.models import Person, erster_listenwert


class ErsterListenwertTest(TestCase):
    def test_strings(self):
        self.assertEqual(erster_listenwert(['a@b.de', 'c@d.de'], ('email',)), 'a@b.de')

    def test_dicts(self):
        self.assertEqual(
            erster_listenwert([{'adresse': 'a@b.de'}], ('adresse', 'email', 'wert')),
            'a@b.de',
        )

    def test_leere_eintraege_werden_uebersprungen(self):
        self.assertEqual(erster_listenwert(['', '  ', 'c@d.de'], ('email',)), 'c@d.de')

    def test_leere_liste(self):
        self.assertEqual(erster_listenwert([], ('email',)), '')
        self.assertEqual(erster_listenwert(None, ('email',)), '')


class LegacyfeldSpiegelungTest(TestCase):
    def test_speichern_zieht_legacyfeld_nach(self):
        p = Person.objects.create(
            personennummer='T-1', nachname='Test',
            email='alt@gmx.de', emails=['neu@gmail.com'],
        )
        p.refresh_from_db()
        self.assertEqual(p.email, 'neu@gmail.com')

    def test_aenderung_der_liste_wirkt_auf_legacyfeld(self):
        p = Person.objects.create(personennummer='T-2', nachname='Test',
                                  emails=['erst@gmail.com'])
        p.emails = ['zweit@gmail.com']
        p.save()
        p.refresh_from_db()
        self.assertEqual(p.email, 'zweit@gmail.com')

    def test_leere_liste_laesst_legacyfeld_stehen(self):
        """Die Mehrheit der Bestandspersonen hat nur das Legacy-Feld."""
        p = Person.objects.create(personennummer='T-3', nachname='Test',
                                  email='nur-legacy@gmx.de', emails=[])
        p.refresh_from_db()
        self.assertEqual(p.email, 'nur-legacy@gmx.de')

    def test_telefon_analog(self):
        p = Person.objects.create(personennummer='T-4', nachname='Test',
                                  telefon='0611-111', telefonnummern=['0611-222'])
        p.refresh_from_db()
        self.assertEqual(p.telefon, '0611-222')

    def test_dict_eintraege(self):
        p = Person.objects.create(
            personennummer='T-5', nachname='Test',
            email='alt@gmx.de', emails=[{'adresse': 'neu@gmail.com', 'typ': 'privat'}],
        )
        p.refresh_from_db()
        self.assertEqual(p.email, 'neu@gmail.com')

    def test_teilsave_der_liste_schreibt_legacyfeld_mit(self):
        """update_fields=['emails'] darf 'email' nicht zurueckbleiben lassen."""
        p = Person.objects.create(personennummer='T-6', nachname='Test',
                                  email='alt@gmx.de', emails=['alt@gmx.de'])
        p.emails = ['neu@gmail.com']
        p.save(update_fields=['emails'])
        p.refresh_from_db()
        self.assertEqual(p.email, 'neu@gmail.com')


class SyncCommandTest(TestCase):
    def test_dry_run_aendert_nichts(self):
        p = Person.objects.create(personennummer='T-7', nachname='Test')
        Person.objects.filter(pk=p.pk).update(email='alt@gmx.de', emails=['neu@gmail.com'])

        ausgabe = StringIO()
        call_command('sync_kontakt_legacyfelder', '--dry-run', stdout=ausgabe)

        p.refresh_from_db()
        self.assertEqual(p.email, 'alt@gmx.de')
        self.assertIn('Probelauf', ausgabe.getvalue())

    def test_lauf_korrigiert_bestand(self):
        p = Person.objects.create(personennummer='T-8', nachname='Test')
        # update() umgeht save() — so entsteht der Bestandszustand.
        Person.objects.filter(pk=p.pk).update(email='alt@gmx.de', emails=['neu@gmail.com'])

        ausgabe = StringIO()
        call_command('sync_kontakt_legacyfelder', stdout=ausgabe)

        p.refresh_from_db()
        self.assertEqual(p.email, 'neu@gmail.com')
        self.assertIn('1 Feld(er) aktualisiert', ausgabe.getvalue())
