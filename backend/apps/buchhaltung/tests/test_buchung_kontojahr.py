"""
Tests: Buchung.save() löst Konto-FKs ins Jahr des Buchungsdatums auf.

Konten sind jahresgebunden. Ein durchgereichter Verweis aus einem anderen
Jahr (Kontenplan-Auswahl im Frontend, gespeicherte Regeln, Vorlagen) hängt
die Buchung sonst an das Kontoblatt des falschen Jahres — die Buchung ist im
Journal unauffällig, fehlt aber in jahresbezogenen Auswertungen.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.buchhaltung.models import Buchung
from apps.konten.models import Konto
from apps.objekte.models import Objekt, Wirtschaftsjahr


class BuchungKontoJahrTest(TestCase):
    def setUp(self):
        self.objekt = Objekt.objects.create(
            objekt_typ='WEG', bezeichnung='KJ-Test', kurzbezeichnung='KJ1',
            strasse='Teststraße 1', plz='60311', ort='Frankfurt',
            verwaltung_seit=date(2020, 1, 1), glaeubiger_id='DE98ZZZ09999999999')
        self.wj2025 = Wirtschaftsjahr.objects.create(
            objekt=self.objekt, jahr=2025, beginn_monat=1)
        self.wj2026 = Wirtschaftsjahr.objects.create(
            objekt=self.objekt, jahr=2026, beginn_monat=1)
        self.bank2025 = self._konto('18000', self.wj2025)
        self.bank2026 = self._konto('18000', self.wj2026)
        self.rl2025 = self._konto('09911', self.wj2025)
        self.rl2026 = self._konto('09911', self.wj2026)

    def _konto(self, nr, wj):
        return Konto.objects.create(
            wirtschaftsjahr=wj, kontonummer=nr, kontoname='Konto %s' % nr)

    def _buche(self, buchungsdatum, soll=None, haben=None, **extra):
        return Buchung.objects.create(
            objekt=self.objekt, betrag=Decimal('100.00'),
            buchungsdatum=buchungsdatum, status='entwurf',
            soll_konto=soll, haben_konto=haben, **extra)

    def test_fremdjaehriges_konto_wird_ins_buchungsjahr_gezogen(self):
        """Der Fall aus der Praxis: SAVO 2025 gebucht auf die 2026er 09911."""
        b = self._buche(date(2025, 1, 1), soll=self.bank2026, haben=self.rl2026)
        b.refresh_from_db()
        self.assertEqual(b.soll_konto, self.bank2025)
        self.assertEqual(b.haben_konto, self.rl2025)

    def test_passendes_konto_bleibt_unveraendert(self):
        b = self._buche(date(2025, 6, 1), soll=self.bank2025, haben=self.rl2025)
        b.refresh_from_db()
        self.assertEqual(b.soll_konto, self.bank2025)
        self.assertEqual(b.haben_konto, self.rl2025)

    def test_ohne_konto_im_zieljahr_bleibt_der_verweis_stehen(self):
        """Besser ein Verweis aus dem Nachbarjahr als gar keiner."""
        nur2026 = self._konto('55500', self.wj2026)
        b = self._buche(date(2025, 6, 1), soll=nur2026)
        b.refresh_from_db()
        self.assertEqual(b.soll_konto, nur2026)

    def test_einseitige_buchung_ohne_gegenkonto(self):
        b = self._buche(date(2025, 6, 1), soll=self.bank2026, haben=None)
        b.refresh_from_db()
        self.assertEqual(b.soll_konto, self.bank2025)
        self.assertIsNone(b.haben_konto)

    def test_spaetere_aenderung_wird_ebenfalls_aufgeloest(self):
        b = self._buche(date(2025, 6, 1), soll=self.bank2025)
        b.haben_konto = self.rl2026
        b.save(update_fields=['haben_konto'])
        b.refresh_from_db()
        self.assertEqual(b.haben_konto, self.rl2025)

    def test_update_fields_ohne_konto_laesst_den_verweis_unangetastet(self):
        """Ein reiner Status-Wechsel darf keine Konto-Umhängung mitschreiben."""
        b = self._buche(date(2025, 6, 1), soll=self.bank2025)
        Buchung.objects.filter(pk=b.pk).update(soll_konto=self.bank2026)
        b.refresh_from_db()
        b.status = 'festgeschrieben'
        b.save(update_fields=['status'])
        b.refresh_from_db()
        self.assertEqual(b.soll_konto, self.bank2026)
