"""
Tests: Zeilentext im „Kontoauszug der Zahlungen" der Einzelabrechnung.

Format: „Hausgeld 01/2025 - Wohnung 1 - 0007" — Buchungsart, Periode,
Einheit, Personenkontonummer. Die Nummer kommt je Zahlung aus dem
Eigentumsverhältnis der Sollstellung, nach einem Eigentümerwechsel stehen
daher unterschiedliche Nummern in derselben Tabelle.
"""
from datetime import date
from decimal import Decimal
from uuid import uuid4

from apps.buchhaltung.models import (
    Buchung,
    Buchungsart,
    SollstellungSplit,
    SollstellungZahlung,
)
from apps.buchhaltung.services.jahresabrechnung.pdf_service import (
    _pk_nummer,
    _zahlungs_bemerkung,
)
from apps.konten.models import Personenkonto
from apps.personen.models import EigentumsVerhaeltnis, Person

from .test_einzelabrechnung_service import EinzelAbrechnungServiceTestBase


class KontoauszugBemerkungTest(EinzelAbrechnungServiceTestBase):
    def setUp(self):
        super().setUp()
        self.ba_900, _ = Buchungsart.objects.get_or_create(
            nr='900', defaults=dict(bezeichnung='Hausgeld'))
        # Personenkonten legt ein Signal beim Eigentumsverhältnis an —
        # hier nur die Nummer auf einen sprechenden Wert setzen.
        self.pk1 = self._setze_pk_nummer(self.ev1, '0007')

    def _setze_pk_nummer(self, ev, nummer):
        pk, _ = Personenkonto.objects.get_or_create(
            vertrag=ev,
            defaults=dict(objekt=self.objekt, eigentuemer=ev.person,
                          kontonummer=nummer))
        if pk.kontonummer != nummer:
            pk.kontonummer = nummer
            pk.save(update_fields=['kontonummer'])
        # Das Signal legt das Personenkonto mit vertrag=instance an; Django
        # cached die Reverse-Relation dabei am EV. Ohne refresh liefert
        # ev.personenkonto weiter die alte, automatisch vergebene Nummer.
        ev.refresh_from_db()
        return pk

    def _zahlung(self, ev, periode, betrag='313.68', ba=None):
        ss = self._create_soll(ev, betrag, periode)
        split = SollstellungSplit.objects.create(
            sollstellung=ss, ba=ba or self.ba_900, betrag=Decimal(betrag))
        buchung = Buchung.objects.create(
            objekt=self.objekt, betrag=Decimal(betrag), buchungsdatum=periode,
            status='festgeschrieben',
            buchungstext='Hausgeld 01/2025 - Wohnung 1 - Objekt WEG Alt')
        return SollstellungZahlung.objects.create(
            sollstellung=ss, split=split, buchung=buchung,
            betrag=Decimal(betrag), erstellt_von=self.user)

    def test_format_mit_personenkontonummer(self):
        z = self._zahlung(self.ev1, date(2025, 1, 1))
        self.assertEqual(
            _zahlungs_bemerkung(z, self.ba_900),
            'Hausgeld 01/2025 - WE01 - 0007')

    def test_objektname_aus_dem_buchungstext_erscheint_nicht_mehr(self):
        """Der gespeicherte Text trägt noch 'Objekt …' — angezeigt wird er nicht."""
        z = self._zahlung(self.ev1, date(2025, 1, 1))
        self.assertIn('Objekt', z.buchung.buchungstext)
        self.assertNotIn('Objekt', _zahlungs_bemerkung(z, self.ba_900))

    def test_periode_folgt_der_sollstellung(self):
        z = self._zahlung(self.ev1, date(2025, 11, 1))
        self.assertEqual(
            _zahlungs_bemerkung(z, self.ba_900),
            'Hausgeld 11/2025 - WE01 - 0007')

    def test_eigentuemerwechsel_liefert_verschiedene_nummern(self):
        """Zweiter Eigentümer derselben Einheit → eigenes Personenkonto."""
        nachfolger = Person.objects.create(
            person_typ='100', anrede='Herr', vorname='Neu', nachname='Nachfolger')
        alt = self._zahlung(self.ev1, date(2025, 1, 1))

        # Je Einheit darf nur ein Vertrag offen sein (uniq_aktiver_vertrag_je_einheit)
        self.ev1.ende = date(2025, 6, 30)
        self.ev1.save(update_fields=['ende'])
        ev_neu = EigentumsVerhaeltnis.objects.create(
            einheit=self.e1, person=nachfolger, beginn=date(2025, 7, 1))
        self._setze_pk_nummer(ev_neu, '0012')

        neu = self._zahlung(ev_neu, date(2025, 8, 1))
        self.assertEqual(
            _zahlungs_bemerkung(alt, self.ba_900), 'Hausgeld 01/2025 - WE01 - 0007')
        self.assertEqual(
            _zahlungs_bemerkung(neu, self.ba_900), 'Hausgeld 08/2025 - WE01 - 0012')

    def test_ohne_personenkonto_kein_leerer_anhang(self):
        """Fehlt das Personenkonto, endet die Zeile nach der Einheit."""
        Personenkonto.objects.filter(vertrag=self.ev2).delete()
        z = self._zahlung(self.ev2, date(2025, 1, 1))
        self.ev2.refresh_from_db()
        self.assertEqual(_pk_nummer(self.ev2), '')
        self.assertEqual(
            _zahlungs_bemerkung(z, self.ba_900), 'Hausgeld 01/2025 - WE02')

    def test_ohne_buchungsart_faellt_auf_zahlung_zurueck(self):
        z = self._zahlung(self.ev1, date(2025, 1, 1))
        self.assertEqual(
            _zahlungs_bemerkung(z, None), 'Zahlung 01/2025 - WE01 - 0007')

    def test_ruecklagen_ba_nutzt_ihre_bezeichnung(self):
        ba_911, _ = Buchungsart.objects.get_or_create(
            nr='911', defaults=dict(bezeichnung='Rücklage I'))
        z = self._zahlung(self.ev1, date(2025, 3, 1), ba=ba_911)
        self.assertEqual(
            _zahlungs_bemerkung(z, ba_911), 'Rücklage I 03/2025 - WE01 - 0007')
