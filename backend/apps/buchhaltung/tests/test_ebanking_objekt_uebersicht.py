"""
Tests: E-Banking Objekt-Übersicht (/e-banking/bank-buchungen/objekt-uebersicht/).

Zeigt objektübergreifend, bei welchem Objekt noch unverbuchte Kontoumsätze
liegen. Umsätze ohne Objektzuordnung erscheinen als eigene Zeile.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.buchhaltung.models import Kontoumsatz
from apps.objekte.models import Objekt

User = get_user_model()
URL = '/api/v1/e-banking/bank-buchungen/objekt-uebersicht/'


def _objekt(nummer, bezeichnung):
    return Objekt.objects.create(
        objektnummer=nummer,
        bezeichnung=bezeichnung,
        objekt_typ='WEG',
        strasse='Teststr. 1',
        plz='60000',
        ort='Teststadt',
        verwaltung_seit=date(2020, 1, 1),
    )


def _umsatz(objekt, betrag, status, tag, hash_suffix):
    return Kontoumsatz.objects.create(
        objekt=objekt,
        sha256_hash=f'{hash_suffix:064d}',
        betrag=Decimal(betrag),
        buchungsdatum=date(2026, 8, tag),
        status=status,
    )


class ObjektUebersichtTest(TestCase):

    client_class = APIClient

    def setUp(self):
        self.user = User.objects.create_user('eb-uebersicht', password='x')
        self.client.force_authenticate(self.user)

        self.objekt_a = _objekt('UEB01', 'WEG Alpha')
        self.objekt_b = _objekt('UEB02', 'WEG Beta')

        # Objekt A: 3 offene (unklar, vorschlag, erkannt) + 1 verbuchter
        _umsatz(self.objekt_a, '100.00', 'unklar',    3, 1)
        _umsatz(self.objekt_a, '250.50', 'vorschlag', 5, 2)
        _umsatz(self.objekt_a, '-80.00', 'erkannt',  10, 3)
        _umsatz(self.objekt_a, '999.00', 'verbucht',  7, 4)
        # Objekt B: 1 offener
        _umsatz(self.objekt_b, '-40.00', 'importiert', 2, 5)
        # ohne Objektzuordnung
        _umsatz(None, '12.00', 'unbekannt', 9, 6)

    def _zeile(self, daten, objektnummer):
        return next(z for z in daten['objekte'] if z['objektnummer'] == objektnummer)

    def test_zaehlt_nur_unverbuchte_umsaetze(self):
        daten = self.client.get(URL).json()
        a = self._zeile(daten, 'UEB01')
        self.assertEqual(a['anzahl_gesamt'], 3)
        self.assertEqual(a['anzahl_unklar'], 1)
        self.assertEqual(a['anzahl_vorschlag'], 1)
        self.assertEqual(a['anzahl_erkannt'], 1)

    def test_summen_und_zeitraum_je_objekt(self):
        daten = self.client.get(URL).json()
        a = self._zeile(daten, 'UEB01')
        self.assertEqual(Decimal(a['summe_eingang']), Decimal('350.50'))
        self.assertEqual(Decimal(a['summe_ausgang']), Decimal('-80.00'))
        self.assertEqual(a['aeltestes_datum'], '2026-08-03')
        self.assertEqual(a['neuestes_datum'],  '2026-08-10')

    def test_objekt_ohne_eingaenge_hat_summe_null(self):
        daten = self.client.get(URL).json()
        b = self._zeile(daten, 'UEB02')
        self.assertEqual(Decimal(b['summe_eingang']), Decimal('0'))
        self.assertEqual(Decimal(b['summe_ausgang']), Decimal('-40.00'))

    def test_umsaetze_ohne_objekt_als_eigene_zeile(self):
        daten = self.client.get(URL).json()
        ohne = next(z for z in daten['objekte'] if z['objekt_id'] is None)
        self.assertEqual(ohne['bezeichnung'], 'Ohne Objektzuordnung')
        self.assertEqual(ohne['anzahl_gesamt'], 1)

    def test_kopfzahlen_und_sortierung(self):
        daten = self.client.get(URL).json()
        self.assertEqual(daten['summe_offen'], 5)
        self.assertEqual(daten['objekte_mit_offenen'], 3)
        # absteigend nach Anzahl → Objekt A zuerst
        self.assertEqual(daten['objekte'][0]['objektnummer'], 'UEB01')

    def test_datumsfilter_greift(self):
        daten = self.client.get(URL, {'datum_von': '2026-08-08'}).json()
        self.assertEqual(daten['summe_offen'], 2)
        a = self._zeile(daten, 'UEB01')
        self.assertEqual(a['anzahl_gesamt'], 1)

    def test_objekte_ohne_offene_umsaetze_fehlen(self):
        leer = _objekt('UEB03', 'WEG Gamma')
        _umsatz(leer, '5.00', 'verbucht', 1, 7)
        daten = self.client.get(URL).json()
        self.assertNotIn('UEB03', [z['objektnummer'] for z in daten['objekte']])
