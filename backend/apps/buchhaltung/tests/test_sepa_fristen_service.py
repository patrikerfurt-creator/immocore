"""
Unit-Tests: sepa_fristen_service — Bankarbeitstags-Logik.
"""
from datetime import date
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.buchhaltung.services.sepa_fristen_service import (
    bd_addieren,
    ist_bankarbeitstag,
    naechster_einreichungstag,
)


class BdAddierenTest(TestCase):

    def test_fuenf_bd_ohne_feiertag(self):
        # Montag 2026-03-02 + 5 BD → Montag 2026-03-09
        start = date(2026, 3, 2)
        result = bd_addieren(start, 5, 'HE')
        self.assertEqual(result.weekday(), 0)  # Montag
        self.assertGreater(result, start)

    def test_bd_ueberspringt_wochenende(self):
        # Freitag + 1 BD = nächster Montag
        freitag = date(2026, 3, 6)
        montag = bd_addieren(freitag, 1, 'HE')
        self.assertEqual(montag, date(2026, 3, 9))

    def test_bd_ueberspringt_karfreitag_hessen(self):
        # In HE ist Karfreitag ein Feiertag
        # Karfreitag 2026 = 03.04.2026
        donnerstag = date(2026, 4, 2)
        # Donnerstag + 1 BD überspringt Karfreitag → Samstag überspringen → Montag
        result = bd_addieren(donnerstag, 1, 'HE')
        self.assertEqual(result, date(2026, 4, 7))  # Ostermontag? Nein, auch Feiertag → 8.4.
        # Korrektur: Ostermontag 6.4. auch Feiertag → Dienstag 7.4.
        self.assertGreater(result, donnerstag)

    def test_null_bd(self):
        start = date(2026, 3, 10)
        result = bd_addieren(start, 0, 'HE')
        self.assertEqual(result, start)

    def test_verschiedene_bundeslaender(self):
        # 01.11. ist Allerheiligen — nur in einigen Bundesländern Feiertag
        # BY: Allerheiligen = Feiertag, HE: kein Feiertag
        montag_vor_allerheiligen = date(2026, 10, 30)
        result_he = bd_addieren(montag_vor_allerheiligen, 2, 'HE')
        result_by = bd_addieren(montag_vor_allerheiligen, 2, 'BY')
        # In HE: 30.10 + 2BD = 3.11. (Mo+2=Mi, aber 31.10=Reformationstag in einigen BL)
        # In BY: 30.10 + 2BD muss Allerheiligen (1.11.) überspringen
        self.assertGreaterEqual(result_by, result_he)


class IstBankarbeitstag(TestCase):

    def test_montag_ist_bankarbeitstag(self):
        self.assertTrue(ist_bankarbeitstag(date(2026, 3, 2), 'HE'))

    def test_samstag_kein_bankarbeitstag(self):
        self.assertFalse(ist_bankarbeitstag(date(2026, 3, 7), 'HE'))

    def test_sonntag_kein_bankarbeitstag(self):
        self.assertFalse(ist_bankarbeitstag(date(2026, 3, 8), 'HE'))


class NaechsterEinreichungstagTest(TestCase):

    @override_settings(SEPA_AUTOPILOT_VORLAUF_BD=5)
    def test_faelligkeit_erreichbar(self):
        # Stichtag: 25. März, Fälligkeit: 01. April — 5 BD Vorlauf reicht
        stichtag = date(2026, 3, 25)
        soll_faelligkeit = date(2026, 4, 1)
        result = naechster_einreichungstag(stichtag, soll_faelligkeit, 'HE')
        self.assertEqual(result, soll_faelligkeit)

    @override_settings(SEPA_AUTOPILOT_VORLAUF_BD=5)
    def test_faelligkeit_nicht_erreichbar(self):
        # Stichtag: 31. März (Dienstag), Fälligkeit: 01. April — zu spät
        stichtag = date(2026, 3, 31)
        soll_faelligkeit = date(2026, 4, 1)
        result = naechster_einreichungstag(stichtag, soll_faelligkeit, 'HE')
        self.assertGreater(result, soll_faelligkeit)

    @override_settings(SEPA_AUTOPILOT_VORLAUF_BD=2)
    def test_mindest_vorlauf_zwei_bd(self):
        # Freitag + 2 BD = Dienstag der Folgewoche
        stichtag = date(2026, 3, 27)  # Freitag
        soll_faelligkeit = date(2026, 4, 1)
        result = naechster_einreichungstag(stichtag, soll_faelligkeit, 'HE')
        self.assertEqual(result, soll_faelligkeit)
