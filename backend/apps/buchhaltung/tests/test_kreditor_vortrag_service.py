"""
Tests: Saldovortrag offener Kreditor-OPs ins Folgejahr (Jahresabrechnung
Schritt 2). Prüft Buchungspaar, Erfolgsneutralität, Entsperrung von
Schritt 2, den Sonderfall ohne festgeschriebene Buchung und die Guards.
"""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError

from apps.buchhaltung.models import Buchung, KreditorOP
from apps.buchhaltung.services.jahresabrechnung import (
    kreditor_vortrag_service,
    wizard_service,
)
from apps.buchhaltung.tests.test_einzelabrechnung_service import (
    EinzelAbrechnungServiceTestBase,
)
from apps.konten.models import Konto
from apps.objekte.models import Wirtschaftsjahr
from apps.rechnungen.models import Kreditor


class KreditorVortragServiceTest(EinzelAbrechnungServiceTestBase):

    def setUp(self):
        super().setUp()
        self.wj_neu = Wirtschaftsjahr.objects.create(
            objekt=self.objekt,
            jahr=self.wj.jahr + 1,
            beginn_monat=self.wj.beginn_monat,
            vorjahr=self.wj,
            status='offen',
        )
        # Schwebekonto in beiden Jahren — Gegenkonto der Eingangsrechnung
        for wj in (self.wj, self.wj_neu):
            Konto.objects.get_or_create(
                wirtschaftsjahr=wj, kontonummer='15900',
                defaults=dict(kontoname='Schwebende Eingangsrechnungen',
                              direktes_buchen=False),
            )
        self.kreditor = Kreditor.objects.create(name='Muster Handwerk GmbH')

    # -- Hilfsmittel ---------------------------------------------------------

    def _kreditorkonto(self, jahr):
        from apps.rechnungen.services.rechnung_op_service import (
            get_or_create_kreditor_konto,
        )
        return get_or_create_kreditor_konto(self.kreditor, self.objekt, jahr=jahr)

    def _op(self, betrag='500.00', buchung_status='festgeschrieben', faellig=None,
            op_nummer=90000001):
        """Offener Kreditor-OP mit Ursprungsbuchung 15900 Soll / 70xxx Haben."""
        betrag = Decimal(betrag)
        buchung = None
        if buchung_status is not None:
            buchung = Buchung.objects.create(
                objekt=self.objekt,
                soll_konto=Konto.objects.get(wirtschaftsjahr=self.wj, kontonummer='15900'),
                haben_konto=self._kreditorkonto(self.wj.jahr),
                betrag=betrag,
                buchungsdatum=date(self.wj.jahr, 12, 1),
                buchungstext='Eingangsrechnung Test',
                wirtschaftsjahr=self.wj,
                wirtschaftsjahr_nr=self.wj.jahr,
                status=buchung_status,
                erstellt_von=self.user,
            )
        return KreditorOP.objects.create(
            op_nummer=op_nummer,
            kreditor=self.kreditor,
            objekt=self.objekt,
            buchung=buchung,
            betrag_ursprung=betrag,
            betrag_offen=betrag,
            faellig_ab=faellig or date(self.wj.jahr, 12, 31),
            status='offen',
        )

    def _saldo(self, kontonummer, wj):
        """Soll minus Haben auf einem Konto im gegebenen Wirtschaftsjahr."""
        konto = Konto.objects.get(wirtschaftsjahr=wj, kontonummer=kontonummer)
        soll = sum((b.betrag for b in Buchung.objects.filter(
            soll_konto=konto).exclude(status='storniert')), Decimal('0'))
        haben = sum((b.betrag for b in Buchung.objects.filter(
            haben_konto=konto).exclude(status='storniert')), Decimal('0'))
        return soll - haben

    # -- Kernfall ------------------------------------------------------------

    def test_vortrag_bucht_paar_und_ist_erfolgsneutral(self):
        op = self._op(betrag='500.00')
        kk_nr = self._kreditorkonto(self.wj.jahr).kontonummer

        # Ausgangslage: Verbindlichkeit im Altjahr (Haben-Saldo)
        self.assertEqual(self._saldo(kk_nr, self.wj), Decimal('-500.00'))
        self.assertEqual(self._saldo('15900', self.wj), Decimal('500.00'))

        ergebnis = kreditor_vortrag_service.vortrage_kreditor_ops(
            self.ja, [op.op_nummer], self.user)

        self.assertEqual(ergebnis['vorgetragen_nach'], self.wj_neu.jahr)
        self.assertEqual(ergebnis['anzahl'], 1)
        self.assertEqual(ergebnis['anzahl_gebucht'], 1)
        self.assertEqual(Decimal(ergebnis['summe']), Decimal('500.00'))

        # Altjahr saldiert auf null, Folgejahr trägt die Rechnung wieder
        self.assertEqual(self._saldo(kk_nr, self.wj), Decimal('0.00'))
        self.assertEqual(self._saldo('15900', self.wj), Decimal('0.00'))
        self.assertEqual(self._saldo(kk_nr, self.wj_neu), Decimal('-500.00'))
        self.assertEqual(self._saldo('15900', self.wj_neu), Decimal('500.00'))

        vortragsbuchungen = Buchung.objects.filter(
            beleg_referenz=f'KREDITOR-OP-VORTRAG-{op.op_nummer}')
        self.assertEqual(vortragsbuchungen.count(), 2)
        self.assertEqual({b.wirtschaftsjahr.jahr for b in vortragsbuchungen},
                         {self.wj.jahr, self.wj_neu.jahr})
        # Kein Kostenkonto berührt — der Vortrag ist erfolgsneutral
        for b in vortragsbuchungen:
            self.assertEqual(b.status, 'festgeschrieben')
            for konto in (b.soll_konto, b.haben_konto):
                self.assertFalse(konto.kontonummer.startswith('5'))

        op.refresh_from_db()
        self.assertEqual(op.vortrag_wj_id, self.wj_neu.id)
        self.assertEqual(op.vortrag_von_id, self.user.id)
        self.assertIsNotNone(op.vortrag_am)
        # Der OP bleibt offen und zahlbar
        self.assertEqual(op.status, 'offen')
        self.assertEqual(op.betrag_offen, Decimal('500.00'))

    def test_vortrag_entsperrt_schritt_2(self):
        op = self._op()
        vorher = wizard_service.buchungspruefung(self.objekt, self.wj)
        self.assertTrue(vorher['blockiert'])
        self.assertEqual(len(vorher['kreditor_ops']), 1)

        kreditor_vortrag_service.vortrage_kreditor_ops(self.ja, [op.op_nummer], self.user)

        nachher = wizard_service.buchungspruefung(self.objekt, self.wj)
        self.assertFalse(nachher['blockiert'])
        self.assertEqual(nachher['kreditor_ops'], [])
        self.assertEqual(len(nachher['vorgetragene_ops']), 1)
        self.assertEqual(nachher['vorgetragene_ops'][0]['vorgetragen_nach'],
                         self.wj_neu.jahr)

    def test_vortrag_blockiert_das_folgejahr_weiterhin(self):
        """Im Folgejahr ist die Zahlung offen — dort muss der OP wieder sperren."""
        op = self._op()
        kreditor_vortrag_service.vortrage_kreditor_ops(self.ja, [op.op_nummer], self.user)

        pruefung_neu = wizard_service.buchungspruefung(self.objekt, self.wj_neu)
        self.assertTrue(pruefung_neu['blockiert'])
        self.assertEqual([o['op_nummer'] for o in pruefung_neu['kreditor_ops']],
                         [op.op_nummer])

    # -- Sonderfall: keine festgeschriebene Buchung ---------------------------

    def test_op_ohne_festgeschriebene_buchung_wird_ohne_buchung_vorgetragen(self):
        op = self._op(betrag='0.05', buchung_status='entwurf')

        ergebnis = kreditor_vortrag_service.vortrage_kreditor_ops(
            self.ja, [op.op_nummer], self.user)

        self.assertEqual(ergebnis['anzahl'], 1)
        self.assertEqual(ergebnis['anzahl_gebucht'], 0)
        self.assertFalse(ergebnis['ops'][0]['gebucht'])
        self.assertIn('nur der offene Posten', ergebnis['ops'][0]['hinweis'])
        self.assertFalse(Buchung.objects.filter(
            beleg_referenz=f'KREDITOR-OP-VORTRAG-{op.op_nummer}').exists())
        op.refresh_from_db()
        self.assertEqual(op.vortrag_wj_id, self.wj_neu.id)

    def test_op_ohne_buchung_wird_vorgetragen(self):
        op = self._op(betrag='195.00', buchung_status=None)
        ergebnis = kreditor_vortrag_service.vortrage_kreditor_ops(
            self.ja, [op.op_nummer], self.user)
        self.assertEqual(ergebnis['anzahl_gebucht'], 0)
        op.refresh_from_db()
        self.assertEqual(op.vortrag_wj_id, self.wj_neu.id)

    # -- Guards --------------------------------------------------------------

    def test_ohne_folgejahr_klare_fehlermeldung(self):
        op = self._op()
        self.wj_neu.delete()
        with self.assertRaises(ValidationError) as ctx:
            kreditor_vortrag_service.vortrage_kreditor_ops(
                self.ja, [op.op_nummer], self.user)
        self.assertIn('kein Wirtschaftsjahr', ctx.exception.messages[0])

    def test_folgejahr_nicht_offen_wird_abgelehnt(self):
        op = self._op()
        self.wj_neu.status = 'abgeschlossen'
        self.wj_neu.save(update_fields=['status'])
        with self.assertRaises(ValidationError) as ctx:
            kreditor_vortrag_service.vortrage_kreditor_ops(
                self.ja, [op.op_nummer], self.user)
        self.assertIn('nicht offen', ctx.exception.messages[0])

    def test_doppelter_vortrag_wird_abgelehnt(self):
        op = self._op()
        kreditor_vortrag_service.vortrage_kreditor_ops(self.ja, [op.op_nummer], self.user)
        with self.assertRaises(ValidationError) as ctx:
            kreditor_vortrag_service.vortrage_kreditor_ops(
                self.ja, [op.op_nummer], self.user)
        self.assertIn('bereits nach', ctx.exception.messages[0])
        self.assertEqual(Buchung.objects.filter(
            beleg_referenz=f'KREDITOR-OP-VORTRAG-{op.op_nummer}').count(), 2)

    def test_bezahlter_op_wird_abgelehnt(self):
        op = self._op()
        op.status = 'bezahlt'
        op.save(update_fields=['status'])
        with self.assertRaises(ValidationError) as ctx:
            kreditor_vortrag_service.vortrage_kreditor_ops(
                self.ja, [op.op_nummer], self.user)
        self.assertIn('kann nicht vorgetragen werden', ctx.exception.messages[0])

    def test_unbekannte_op_nummer_wird_abgelehnt(self):
        with self.assertRaises(ValidationError) as ctx:
            kreditor_vortrag_service.vortrage_kreditor_ops(self.ja, [123456789], self.user)
        self.assertIn('nicht gefunden', ctx.exception.messages[0])

    def test_leere_auswahl_wird_abgelehnt(self):
        with self.assertRaises(ValidationError):
            kreditor_vortrag_service.vortrage_kreditor_ops(self.ja, [], self.user)

    def test_mehrere_ops_in_einem_lauf(self):
        op1 = self._op(betrag='100.00', op_nummer=90000101)
        op2 = self._op(betrag='250.00', op_nummer=90000102)
        ergebnis = kreditor_vortrag_service.vortrage_kreditor_ops(
            self.ja, [op1.op_nummer, op2.op_nummer], self.user)
        self.assertEqual(ergebnis['anzahl'], 2)
        self.assertEqual(Decimal(ergebnis['summe']), Decimal('350.00'))
        kk_nr = self._kreditorkonto(self.wj.jahr).kontonummer
        self.assertEqual(self._saldo(kk_nr, self.wj), Decimal('0.00'))
        self.assertEqual(self._saldo(kk_nr, self.wj_neu), Decimal('-350.00'))

    def test_rollback_bei_fehler_in_der_auswahl(self):
        """Ein untauglicher OP darf die ganze Auswahl nicht halb buchen."""
        op_ok = self._op(betrag='100.00', op_nummer=90000201)
        op_bad = self._op(betrag='50.00', op_nummer=90000202)
        op_bad.status = 'storniert'
        op_bad.save(update_fields=['status'])
        with self.assertRaises(ValidationError):
            kreditor_vortrag_service.vortrage_kreditor_ops(
                self.ja, [op_ok.op_nummer, op_bad.op_nummer], self.user)
        op_ok.refresh_from_db()
        self.assertIsNone(op_ok.vortrag_wj_id)
        self.assertFalse(Buchung.objects.filter(
            beleg_referenz__startswith='KREDITOR-OP-VORTRAG').exists())
