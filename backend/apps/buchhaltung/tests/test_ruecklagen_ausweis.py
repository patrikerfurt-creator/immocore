"""
Tests: Rücklagen-Ausweis im Einzelabrechnungs-PDF
(Rücklagenausweis-Spec v1.0 Kap. 8.1 + 8.2).

Deckt den Spiegel je Rücklage ab: die vier Positionen, die Summenzeile ab
zwei Rücklagen, den Klärungsfall samt 0,01-€-Toleranz, den Eigentümeranteil
auf beiden Endbestands-Basen und die Darstellung im gerenderten PDF.
"""
from datetime import date
from decimal import Decimal
from uuid import uuid4

from apps.buchhaltung.models import Buchungsart, Kontoumsatz, SollstellungSplit
from apps.buchhaltung.services.jahresabrechnung.einzelabrechnung_service import (
    berechne_einzelabrechnung,
)
from apps.buchhaltung.services.jahresabrechnung.pdf_service import (
    _ruecklagenspiegel_kontext,
    render_einzelabrechnung_pdf,
)
from apps.objekte.models import Bankkonto

from .test_einzelabrechnung_service import EinzelAbrechnungServiceTestBase


class RuecklagenAusweisTestBase(EinzelAbrechnungServiceTestBase):
    """MEA aus der Basisklasse: WE01 = 300/1000, WE02 = 700/1000."""

    def _ruecklage(self, reihenfolge, bezeichnung=None):
        """Rücklagen-Bankkonto; reihenfolge 1 → BA 911, 2 → 912, …"""
        return Bankkonto.objects.create(
            objekt=self.objekt, konto_typ='ruecklage',
            bezeichnung=bezeichnung or 'Rücklage %d' % reihenfolge,
            reihenfolge=reihenfolge)

    def _umsatz(self, bk, betrag, datum):
        return Kontoumsatz.objects.create(
            objekt=self.objekt, bankkonto=bk,
            sha256_hash=uuid4().hex + uuid4().hex[:32],
            betrag=Decimal(betrag), buchungsdatum=datum, status='verbucht')

    def _kontext(self, einheit=None):
        ea = berechne_einzelabrechnung(self.ja, einheit or self.e1)
        return ea, _ruecklagenspiegel_kontext(ea, self.objekt, self.wj)


class EinzelneRuecklageTest(RuecklagenAusweisTestBase):
    """Kap. 8.1: eine Rücklage — vier Positionen, keine Summenzeile."""

    def test_vier_positionen_und_metadaten(self):
        # Umsatz vor WJ-Beginn ⇒ Anfangsbestand, keine Bewegung im WJ
        self._umsatz(self._ruecklage(1), '12500.00', date(2024, 6, 1))
        _, ctx = self._kontext()
        self.assertEqual(len(ctx['ruecklagenspiegel']), 1)
        z = ctx['ruecklagenspiegel'][0]
        self.assertEqual(z['anfangsbestand'], '12.500,00')
        self.assertEqual(z['zufuehrungen'], '0,00')
        self.assertEqual(z['entnahmen'], '0,00')
        self.assertEqual(z['endbestand'], '12.500,00')
        self.assertEqual(z['nummer_roemisch'], 'I')
        self.assertEqual(z['suffix'], '911')
        self.assertEqual(z['mea_anteil_einheit'], '300/1000')

    def test_keine_summenzeile_bei_einer_ruecklage(self):
        """Kap. 3.2: bei genau einer Rücklage wäre die Summe redundant."""
        self._umsatz(self._ruecklage(1), '12500.00', date(2024, 6, 1))
        _, ctx = self._kontext()
        self.assertIsNone(ctx['ruecklagenspiegel_summe'])


class MehrereRuecklagenTest(RuecklagenAusweisTestBase):
    """Kap. 8.1: drei Rücklagen — getrennter Ausweis + Summenzeile."""

    def setUp(self):
        super().setUp()
        for i, betrag in enumerate(('10000.00', '4000.00', '1000.00'), start=1):
            self._umsatz(self._ruecklage(i), betrag, date(2024, 6, 1))

    def test_je_ruecklage_eine_zeile_in_nummern_reihenfolge(self):
        _, ctx = self._kontext()
        zeilen = ctx['ruecklagenspiegel']
        self.assertEqual([z['nummer_roemisch'] for z in zeilen], ['I', 'II', 'III'])
        self.assertEqual([z['suffix'] for z in zeilen], ['911', '912', '913'])
        self.assertEqual(
            [z['endbestand'] for z in zeilen],
            ['10.000,00', '4.000,00', '1.000,00'])

    def test_summenzeile_ist_summe_der_einzelwerte(self):
        _, ctx = self._kontext()
        s = ctx['ruecklagenspiegel_summe']
        self.assertIsNotNone(s)
        self.assertEqual(s['endbestand'], '15.000,00')
        self.assertEqual(s['anteil_eigentuemer'], '4.500,00')  # 30 % von 15.000


class KlaerungsfallTest(RuecklagenAusweisTestBase):
    """Kap. 8.1: Abweichung Bankauszug ↔ berechneter Endbestand."""

    def _mit_abweichung(self, differenz):
        bk = self._ruecklage(1)
        self._umsatz(bk, '10000.00', date(2024, 6, 1))  # Anfangsbestand
        if differenz is not None:
            # Bankbewegung im WJ ohne Gegenstück in Neben-/Hauptbuch ⇒ der
            # Bankauszug läuft dem rechnerischen Endbestand davon.
            self._umsatz(bk, differenz, date(2025, 3, 1))
        return self._kontext()

    def test_abweichung_setzt_klaerungsfall(self):
        ea, ctx = self._mit_abweichung('250.00')
        r = ea.ruecklagen[0]
        self.assertEqual(r['abweichung'], '-250.00')
        self.assertTrue(r['klaerungsfall'])
        self.assertTrue(ctx['ruecklagenspiegel_klaerungsfall'])

    def test_toleranz_von_einem_cent_loest_nicht_aus(self):
        """|Abweichung| > 0,01 € — genau ein Cent ist noch kein Klärungsfall."""
        ea, ctx = self._mit_abweichung('0.01')
        r = ea.ruecklagen[0]
        self.assertEqual(r['abweichung'], '-0.01')
        self.assertFalse(r['klaerungsfall'])
        self.assertFalse(ctx['ruecklagenspiegel_klaerungsfall'])

    def test_ohne_abweichung_kein_klaerungsfall(self):
        ea, ctx = self._mit_abweichung(None)
        self.assertFalse(ea.ruecklagen[0]['klaerungsfall'])
        self.assertFalse(ctx['ruecklagenspiegel_klaerungsfall'])


class AnteilEigentuemerTest(RuecklagenAusweisTestBase):
    """Kap. 8.1: Anteil = Endbestand × MEA, auf beiden Endbestands-Basen."""

    def test_anteil_ist_endbestand_mal_mea(self):
        self._umsatz(self._ruecklage(1), '10000.00', date(2024, 6, 1))
        ea = berechne_einzelabrechnung(self.ja, self.e1)
        r = ea.ruecklagen[0]
        self.assertEqual(r['anteil_eigentuemer'], '3000.00')
        self.assertEqual(r['mea_anteil_einheit'], '300/1000')

    def test_summe_aller_einheiten_ergibt_den_objekt_endbestand(self):
        self._umsatz(self._ruecklage(1), '10000.00', date(2024, 6, 1))
        summe = sum(
            Decimal(berechne_einzelabrechnung(self.ja, e).ruecklagen[0]['anteil_eigentuemer'])
            for e in (self.e1, self.e2)
        )
        self.assertAlmostEqual(summe, Decimal('10000.00'), delta=Decimal('0.01'))

    def test_im_klaerungsfall_werden_beide_basen_ausgewiesen(self):
        """Bankauszug bleibt maßgeblich, der rechnerische Wert kommt daneben."""
        bk = self._ruecklage(1)
        self._umsatz(bk, '10000.00', date(2024, 6, 1))
        self._umsatz(bk, '1000.00', date(2025, 3, 1))
        ea = berechne_einzelabrechnung(self.ja, self.e1)
        r = ea.ruecklagen[0]
        self.assertEqual(r['anteil_eigentuemer'], '3300.00')            # 30 % v. 11.000
        self.assertEqual(r['anteil_eigentuemer_berechnet'], '3000.00')  # 30 % v. 10.000


class ZufuehrungGesamtAbgrenzungTest(RuecklagenAusweisTestBase):
    """
    Kap. 8.1 fordert `ruecklagen_zufuehrung_gesamt == Σ zufuehrungen`. Diese
    Gleichheit kann im Ist-Code nicht gelten, weil beide Werte verschiedene
    Größen messen — dieser Test hält die Abgrenzung fest, damit sie nicht
    versehentlich „geradegezogen" wird:

        ruecklagen_zufuehrung_gesamt  Soll EINES Eigentümers (Σ 91x-Splits)
        zufuehrungen (Spiegel)        Ist des GESAMTEN Objekts (Σ gezahlte
                                      Beträge auf diesen Splits)
    """

    def test_soll_je_eigentuemer_und_ist_objektweit_sind_getrennt(self):
        self._umsatz(self._ruecklage(1), '10000.00', date(2024, 6, 1))
        ba_911, _ = Buchungsart.objects.get_or_create(
            nr='911',
            defaults=dict(bezeichnung='BA 911', ruecklagen_relevant=True,
                          bankkonto_typ='ruecklage_nach_index'),
        )
        SollstellungSplit.objects.create(
            sollstellung=self._create_soll(self.ev1, '600.00', date(2025, 1, 1)),
            ba=ba_911, betrag=Decimal('600.00'), ist_betrag_split=Decimal('0.00'),
        )
        ea, ctx = self._kontext()
        # Soll des Eigentümers ist gestellt …
        self.assertEqual(ea.ruecklagen_zufuehrung_gesamt, Decimal('600.00'))
        # … aber nichts gezahlt ⇒ objektweite Ist-Zuführung bleibt 0.
        self.assertEqual(ctx['ruecklagenspiegel'][0]['zufuehrungen'], '0,00')


class RuecklagenspiegelPdfTest(RuecklagenAusweisTestBase):
    """Kap. 8.2: der Spiegel muss im gerenderten PDF ankommen."""

    def _pdf_text(self, einheit=None):
        import pymupdf
        ea = berechne_einzelabrechnung(self.ja, einheit or self.e1)
        doc = pymupdf.open(stream=render_einzelabrechnung_pdf(ea), filetype='pdf')
        try:
            return '\n'.join(seite.get_text() for seite in doc)
        finally:
            doc.close()

    def test_jede_ruecklage_erscheint_mit_ihren_positionen(self):
        self._umsatz(self._ruecklage(1, 'Erhaltungsrücklage'), '10000.00', date(2024, 6, 1))
        self._umsatz(self._ruecklage(2, 'Sonderrücklage Aufzug'), '4000.00', date(2024, 6, 1))
        text = self._pdf_text()
        self.assertIn('Entwicklung der Rücklagen', text)
        self.assertIn('Erhaltungsrücklage', text)
        self.assertIn('Sonderrücklage Aufzug', text)
        self.assertIn('10.000,00', text)
        self.assertIn('4.000,00', text)
        # Summenzeile bei zwei Rücklagen (Kap. 3.2)
        self.assertIn('Summe aller Rücklagen', text)

    def test_einzelne_ruecklage_ohne_summenzeile(self):
        self._umsatz(self._ruecklage(1, 'Erhaltungsrücklage'), '10000.00', date(2024, 6, 1))
        text = self._pdf_text()
        self.assertIn('Entwicklung der Rücklage', text)
        self.assertNotIn('Summe aller Rücklagen', text)

    def test_klaerungsfall_erzeugt_fussnote_und_zweite_basis(self):
        bk = self._ruecklage(1, 'Erhaltungsrücklage')
        self._umsatz(bk, '10000.00', date(2024, 6, 1))
        self._umsatz(bk, '1000.00', date(2025, 3, 1))
        text = self._pdf_text()
        self.assertIn('wird durch die Verwaltung geklärt', text)
        self.assertIn('davon rechnerisch', text)


class RuecklagenSnapshotTest(RuecklagenAusweisTestBase):
    """
    Kap. 6.1 „Unveränderlichkeit": die Beträge des Spiegels stammen aus dem
    Snapshot in EinzelAbrechnung.ruecklagen, nicht aus einer Neuberechnung.
    Eine spätere Bankbewegung darf eine bereits erzeugte Abrechnung nicht
    rückwirkend verändern.
    """

    def test_spaetere_bankbewegung_aendert_den_spiegel_nicht(self):
        bk = self._ruecklage(1, 'Erhaltungsrücklage')
        self._umsatz(bk, '10000.00', date(2024, 6, 1))
        ea, vorher = self._kontext()

        self._umsatz(bk, '5000.00', date(2025, 7, 1))  # nach der Erstellung
        ea.refresh_from_db()
        nachher = _ruecklagenspiegel_kontext(ea, self.objekt, self.wj)

        self.assertEqual(
            vorher['ruecklagenspiegel'][0]['endbestand'],
            nachher['ruecklagenspiegel'][0]['endbestand'])
        self.assertEqual(
            vorher['ruecklagenspiegel'][0]['anteil_eigentuemer'],
            nachher['ruecklagenspiegel'][0]['anteil_eigentuemer'])


class SollstellungenJeWohnungTest(RuecklagenAusweisTestBase):
    """
    Aufstellung je Wohnung unter dem Spiegel: Wohnung, Soll, Haben, Saldo,
    alle drei Betragsspalten summiert.
    """

    def setUp(self):
        super().setUp()
        self._umsatz(self._ruecklage(1, 'Erhaltungsrücklage'), '10000.00', date(2024, 6, 1))
        self.ba_911, _ = Buchungsart.objects.get_or_create(
            nr='911',
            defaults=dict(bezeichnung='BA 911', ruecklagen_relevant=True,
                          bankkonto_typ='ruecklage_nach_index'),
        )
        # WE01 zahlt voll, WE02 bleibt 450 schuldig
        for ev, soll, ist in ((self.ev1, '300.00', '300.00'),
                              (self.ev2, '700.00', '250.00')):
            SollstellungSplit.objects.create(
                sollstellung=self._create_soll(ev, soll, date(2025, 1, 1)),
                ba=self.ba_911, betrag=Decimal(soll), ist_betrag_split=Decimal(ist))

    def test_je_wohnung_eine_zeile_mit_saldo(self):
        _, ctx = self._kontext()
        zeilen = ctx['ruecklagenspiegel'][0]['sollstellungen']
        self.assertEqual([s['einheit_nr'] for s in zeilen], ['WE01', 'WE02'])
        self.assertEqual(zeilen[0]['soll'], '300,00')
        self.assertEqual(zeilen[0]['haben'], '300,00')
        self.assertEqual(zeilen[0]['saldo'], '0,00')
        self.assertEqual(zeilen[1]['saldo'], '450,00')

    def test_summenzeile_ueber_alle_wohnungen(self):
        _, ctx = self._kontext()
        self.assertEqual(
            ctx['ruecklagenspiegel'][0]['sollstellungen_summe'],
            {'soll': '1.000,00', 'haben': '550,00', 'saldo': '450,00'})

    def test_ohne_sollstellungen_keine_tabelle(self):
        SollstellungSplit.objects.all().delete()
        _, ctx = self._kontext()
        z = ctx['ruecklagenspiegel'][0]
        self.assertEqual(z['sollstellungen'], [])
        self.assertIsNone(z['sollstellungen_summe'])

    def test_tabelle_erscheint_im_pdf(self):
        import pymupdf
        ea = berechne_einzelabrechnung(self.ja, self.e1)
        doc = pymupdf.open(stream=render_einzelabrechnung_pdf(ea), filetype='pdf')
        try:
            text = '\n'.join(seite.get_text() for seite in doc)
        finally:
            doc.close()
        self.assertIn('Sollstellungen je Wohnung', text)
        self.assertIn('1.000,00', text)  # Summe Soll
        self.assertIn('550,00', text)    # Summe Haben
