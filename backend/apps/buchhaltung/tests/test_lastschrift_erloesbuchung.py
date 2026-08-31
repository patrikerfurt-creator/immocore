"""
Tests: Erlösbein beim SEPA-Lastschrifteinzug.

Die Kopfbuchung (13650 Soll / Personenkonto Haben) bildet nur den Zahlungsweg
ab. Je Split muss zusätzlich Personenkonto Soll / Erlöskonto der Buchungsart
Haben entstehen — BA 900 auf 41900, BA 911 auf 41911. Ohne dieses Bein bleibt
der Ertrag ungebucht und das Personenkonto trägt einen reinen Haben-Saldo.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.buchhaltung.models import (
    Buchung, Buchungsart, HausgeldSollstellung, SollstellungSplit,
    SollstellungZahlung,
)
from apps.buchhaltung.services.sepa_lastschrift import _tilge_sollstellungen
from apps.buchhaltung.services.sollstellung_service import _erloeskonto_fuer_ba
from apps.konten.models import Konto, Personenkonto
from apps.objekte.models import Einheit, Objekt, Wirtschaftsjahr
from apps.personen.models import EigentumsVerhaeltnis, Person

User = get_user_model()


class LastschriftErloesTestBase(TestCase):

    def setUp(self):
        self.user = User.objects.create_user('ls-tester', password='x')
        self.objekt = Objekt.objects.create(
            objektnummer='90001', objekt_typ='WEG', bezeichnung='Lastschrift Testobjekt',
            strasse='Teststr. 1', plz='12345', ort='Teststadt',
            verwaltung_seit=date(2020, 1, 1),
        )
        self.wj25 = Wirtschaftsjahr.objects.create(
            objekt=self.objekt, jahr=2025, beginn_monat=1, status='offen')
        self.wj26 = Wirtschaftsjahr.objects.create(
            objekt=self.objekt, jahr=2026, beginn_monat=1, vorjahr=self.wj25, status='offen')

        self.konten = {}
        for wj in (self.wj25, self.wj26):
            for nr, name in (('13650', 'DCL-Debitor'),
                             ('41900', 'Erlöse Hausgeld VZ'),
                             ('41911', 'Erlöse Rücklage I')):
                self.konten[(wj.jahr, nr)] = Konto.objects.create(
                    wirtschaftsjahr=wj, kontonummer=nr, kontoname=name)

        self.ba900, _ = Buchungsart.objects.get_or_create(
            nr='900', defaults=dict(kuerzel='HG', bezeichnung='Hausgeld'))
        Buchungsart.objects.filter(nr='900').update(erloeskonto_default_nr='41900')
        self.ba911, _ = Buchungsart.objects.get_or_create(
            nr='911', defaults=dict(kuerzel='RL1', bezeichnung='Rücklage I'))
        Buchungsart.objects.filter(nr='911').update(erloeskonto_default_nr='41911')
        self.ba900.refresh_from_db()
        self.ba911.refresh_from_db()

        person = Person.objects.create(person_typ='100', vorname='Test', nachname='Zahler')
        einheit = Einheit.objects.create(
            objekt=self.objekt, einheit_nr='1', einheit_typ='Wohnung', lage='EG')
        self.ev = EigentumsVerhaeltnis.objects.create(
            einheit=einheit, person=person, beginn=date(2020, 1, 1))
        self.pk = Personenkonto.objects.get(vertrag=self.ev)

    def _sollstellung(self, periode=date(2025, 5, 1), hg='320.97', rl='76.15',
                      erloes_jahr=2026):
        """Sollstellung mit zwei Splits. erloes_jahr bildet den Jahres-Bug nach."""
        from apps.buchhaltung.services.opos_nr_service import naechste_opos_nr
        ss = HausgeldSollstellung.objects.create(
            objekt=self.objekt, eigentumsverhaeltnis=self.ev,
            sollstellungs_typ='hausgeld', ba=None, periode=periode,
            faellig_am=periode, opos_nr=naechste_opos_nr(self.objekt),
            soll_betrag=Decimal(hg) + Decimal(rl), ist_betrag=Decimal('0'),
            status_cached='offen', erstellt_von=self.user,
        )
        for ba, betrag, nr in ((self.ba900, hg, '41900'), (self.ba911, rl, '41911')):
            SollstellungSplit.objects.create(
                sollstellung=ss, ba=ba, betrag=Decimal(betrag),
                erloeskonto=self.konten[(erloes_jahr, nr)],
            )
        return ss

    def _zahlungsbuchung(self, betrag, datum=date(2025, 5, 2)):
        """Kopfbuchung des Lastschrifteinzugs: 13650 Soll / Personenkonto Haben."""
        return Buchung.objects.create(
            objekt=self.objekt,
            soll_konto=self.konten[(2025, '13650')],
            personenkonto=self.pk,
            betrag=Decimal(betrag),
            buchungsdatum=datum,
            buchungstext='SEPA-Lastschrift Test',
            wirtschaftsjahr=self.wj25, wirtschaftsjahr_nr=2025,
            status='festgeschrieben', erstellt_von=self.user,
        )

    def _teilbuchungen(self, parent):
        return list(Buchung.objects.filter(parent_buchung=parent)
                    .select_related('haben_konto__wirtschaftsjahr', 'buchungsart')
                    .order_by('buchungsart__nr'))


class ErloesbeinTest(LastschriftErloesTestBase):

    def test_je_split_entsteht_das_erloesbein(self):
        ss = self._sollstellung()
        parent = self._zahlungsbuchung('397.12')

        getilgt = _tilge_sollstellungen([ss.id], parent, self.user)
        self.assertEqual(getilgt, 1)

        teile = self._teilbuchungen(parent)
        self.assertEqual(len(teile), 2, 'je Split eine Teilbuchung erwartet')
        b900, b911 = teile
        self.assertEqual(b900.buchungsart.nr, '900')
        self.assertEqual(b900.haben_konto.kontonummer, '41900')
        self.assertEqual(b900.betrag, Decimal('320.97'))
        self.assertEqual(b911.buchungsart.nr, '911')
        self.assertEqual(b911.haben_konto.kontonummer, '41911')
        self.assertEqual(b911.betrag, Decimal('76.15'))
        for b in teile:
            self.assertIsNone(b.soll_konto, 'Soll-Seite ist das Personenkonto')
            self.assertEqual(b.personenkonto_id, self.pk.id)
            self.assertEqual(b.status, 'festgeschrieben')
            self.assertEqual(b.buchungsdatum, parent.buchungsdatum)

    def test_erloeskonto_wird_ins_buchungsjahr_aufgeloest(self):
        """Der Split zeigt auf 2026 — gebucht werden muss trotzdem in 2025."""
        ss = self._sollstellung(erloes_jahr=2026)
        parent = self._zahlungsbuchung('397.12')
        _tilge_sollstellungen([ss.id], parent, self.user)

        for b in self._teilbuchungen(parent):
            self.assertEqual(b.haben_konto.wirtschaftsjahr.jahr, 2025,
                             f'{b.haben_konto.kontonummer} im falschen Jahr')
            self.assertEqual(b.wirtschaftsjahr.jahr, 2025)

    def test_personenkonto_gleicht_sich_aus(self):
        ss = self._sollstellung()
        parent = self._zahlungsbuchung('397.12')
        _tilge_sollstellungen([ss.id], parent, self.user)

        alle = [parent] + self._teilbuchungen(parent)
        # PK im Haben, wenn die Buchung ein Soll-Konto trägt; sonst im Soll
        haben = sum((b.betrag for b in alle if b.soll_konto_id), Decimal('0'))
        soll = sum((b.betrag for b in alle if b.haben_konto_id), Decimal('0'))
        self.assertEqual(soll, haben)
        self.assertEqual(soll, Decimal('397.12'))

    def test_erloese_landen_auf_den_richtigen_konten(self):
        ss = self._sollstellung()
        parent = self._zahlungsbuchung('397.12')
        _tilge_sollstellungen([ss.id], parent, self.user)

        def haben(nr, jahr=2025):
            k = self.konten[(jahr, nr)]
            return sum((b.betrag for b in Buchung.objects.filter(haben_konto=k)),
                       Decimal('0'))
        self.assertEqual(haben('41900'), Decimal('320.97'))
        self.assertEqual(haben('41911'), Decimal('76.15'))
        self.assertEqual(haben('41900', 2026), Decimal('0'))
        self.assertEqual(haben('41911', 2026), Decimal('0'))

    def test_nebenbuch_wird_weiterhin_getilgt(self):
        ss = self._sollstellung()
        parent = self._zahlungsbuchung('397.12')
        _tilge_sollstellungen([ss.id], parent, self.user)

        ss.refresh_from_db()
        self.assertEqual(ss.status_cached, 'ausgeglichen')
        self.assertEqual(ss.ist_betrag, ss.soll_betrag)
        for split in ss.splits.all():
            self.assertEqual(split.ist_betrag_split, split.betrag)
        self.assertEqual(SollstellungZahlung.objects.filter(sollstellung=ss).count(), 2)

    def test_bereits_getilgter_split_erzeugt_nichts(self):
        ss = self._sollstellung()
        ss.splits.filter(ba=self.ba911).update(ist_betrag_split=Decimal('76.15'))
        parent = self._zahlungsbuchung('320.97')
        _tilge_sollstellungen([ss.id], parent, self.user)

        teile = self._teilbuchungen(parent)
        self.assertEqual(len(teile), 1)
        self.assertEqual(teile[0].buchungsart.nr, '900')

    def test_ohne_erloeskonto_kein_teilbein_aber_tilgung(self):
        """Fehlt das Erlöskonto, darf keine einbeinige Buchung entstehen."""
        ss = self._sollstellung()
        ss.splits.update(erloeskonto=None)
        parent = self._zahlungsbuchung('397.12')

        with self.assertLogs('apps.buchhaltung.services.sepa_lastschrift', level='WARNING'):
            _tilge_sollstellungen([ss.id], parent, self.user)

        self.assertEqual(self._teilbuchungen(parent), [])
        ss.refresh_from_db()
        self.assertEqual(ss.status_cached, 'ausgeglichen')

    def test_bereits_ausgeglichene_sollstellung_wird_uebersprungen(self):
        ss = self._sollstellung()
        ss.status_cached = 'ausgeglichen'
        ss.save(update_fields=['status_cached'])
        parent = self._zahlungsbuchung('397.12')
        self.assertEqual(_tilge_sollstellungen([ss.id], parent, self.user), 0)
        self.assertEqual(self._teilbuchungen(parent), [])

    def test_mehrere_sollstellungen_in_einem_einzug(self):
        ss1 = self._sollstellung(periode=date(2025, 5, 1))
        ss2 = self._sollstellung(periode=date(2025, 6, 1))
        parent = self._zahlungsbuchung('794.24')
        self.assertEqual(_tilge_sollstellungen([ss1.id, ss2.id], parent, self.user), 2)
        self.assertEqual(len(self._teilbuchungen(parent)), 4)


class SaldovortragSonderfallTest(LastschriftErloesTestBase):
    """
    Beim Saldovortrag bucht saldovortrag_service die Forderung
    (Personenkonto ↔ 90080) bereits selbst. Die Zahlung darf sie nicht ein
    zweites Mal einbuchen — sonst steht die Forderung doppelt.
    """

    def setUp(self):
        super().setUp()
        for wj in (self.wj25, self.wj26):
            self.konten[(wj.jahr, '90080')] = Konto.objects.create(
                wirtschaftsjahr=wj, kontonummer='90080',
                kontoname='Saldenvorträge Debitoren')

    def _saldovortrag_ss(self, betrag='354.88'):
        from apps.buchhaltung.services.opos_nr_service import naechste_opos_nr
        ss = HausgeldSollstellung.objects.create(
            objekt=self.objekt, eigentumsverhaeltnis=self.ev,
            sollstellungs_typ='saldovortrag', ba=self.ba900,
            periode=date(2025, 1, 1), faellig_am=date(2025, 1, 1),
            opos_nr=naechste_opos_nr(self.objekt),
            soll_betrag=Decimal(betrag), ist_betrag=Decimal('0'),
            status_cached='offen', erstellt_von=self.user,
        )
        SollstellungSplit.objects.create(
            sollstellung=ss, ba=self.ba900, betrag=Decimal(betrag),
            erloeskonto=self.konten[(2025, '90080')],
        )
        # Forderung, wie saldovortrag_service sie bucht: PK Soll / 90080 Haben
        Buchung.objects.create(
            objekt=self.objekt, buchungsart=self.ba900, betrag=Decimal(betrag),
            soll_konto=None, haben_konto=self.konten[(2025, '90080')],
            personenkonto=self.pk, buchungsdatum=date(2025, 1, 1),
            buchungstext='Saldovortrag 2025 — 900',
            wirtschaftsjahr=self.wj25, wirtschaftsjahr_nr=2025,
            status='festgeschrieben', erstellt_von=self.user,
        )
        return ss

    def test_lastschrift_bucht_kein_zweites_bein(self):
        ss = self._saldovortrag_ss('354.88')
        parent = self._zahlungsbuchung('354.88', datum=date(2025, 1, 13))
        _tilge_sollstellungen([ss.id], parent, self.user)

        self.assertEqual(self._teilbuchungen(parent), [],
                         'Forderung war schon gebucht — kein Erlösbein erwartet')
        ss.refresh_from_db()
        self.assertEqual(ss.status_cached, 'ausgeglichen')
        self.assertEqual(SollstellungZahlung.objects.filter(sollstellung=ss).count(), 1)

    def test_90080_traegt_die_forderung_genau_einmal(self):
        ss = self._saldovortrag_ss('354.88')
        parent = self._zahlungsbuchung('354.88', datum=date(2025, 1, 13))
        _tilge_sollstellungen([ss.id], parent, self.user)

        k = self.konten[(2025, '90080')]
        haben = sum((b.betrag for b in Buchung.objects.filter(haben_konto=k)), Decimal('0'))
        self.assertEqual(haben, Decimal('354.88'))

    def test_personenkonto_gleicht_sich_auch_hier_aus(self):
        ss = self._saldovortrag_ss('354.88')
        parent = self._zahlungsbuchung('354.88', datum=date(2025, 1, 13))
        _tilge_sollstellungen([ss.id], parent, self.user)

        pk_buchungen = Buchung.objects.filter(personenkonto=self.pk)
        soll = sum((b.betrag for b in pk_buchungen if b.haben_konto_id), Decimal('0'))
        haben = sum((b.betrag for b in pk_buchungen if b.soll_konto_id), Decimal('0'))
        self.assertEqual(soll - haben, Decimal('0.00'))

    def test_ueberweisung_bucht_ebenfalls_kein_zweites_bein(self):
        """Derselbe Schutz im Zahlungseingang über die Bank."""
        from apps.buchhaltung.services.zahlungs_zuordnung_service import (
            verrechne_eingang_manuell,
        )
        ss = self._saldovortrag_ss('354.88')
        bank = Konto.objects.create(
            wirtschaftsjahr=self.wj25, kontonummer='18000', kontoname='Bank 1')

        verrechne_eingang_manuell(
            personenkonto=self.pk, bank_sachkonto=bank, betrag=Decimal('354.88'),
            buchungsdatum=date(2025, 1, 13), buchungstext='Zahlungseingang',
            wirtschaftsjahr=self.wj25, user=self.user,
            sollstellungs_ids=[str(ss.id)],
        )
        k = self.konten[(2025, '90080')]
        haben = sum((b.betrag for b in Buchung.objects.filter(haben_konto=k)), Decimal('0'))
        self.assertEqual(haben, Decimal('354.88'), 'Forderung darf nicht doppelt stehen')

    def test_regulaeres_hausgeld_bleibt_unberuehrt(self):
        """Der Schutz greift nur beim Saldovortrag."""
        ss = self._sollstellung()
        parent = self._zahlungsbuchung('397.12')
        _tilge_sollstellungen([ss.id], parent, self.user)
        self.assertEqual(len(self._teilbuchungen(parent)), 2)


class UeberweisungJahrTest(LastschriftErloesTestBase):
    """
    Auch der Überweisungseingang muss das Erlöskonto ins Jahr des
    Buchungsdatums auflösen — der am Split hinterlegte Verweis kann aus einem
    anderen Wirtschaftsjahr stammen.
    """

    def test_erloesbein_folgt_dem_buchungsdatum(self):
        from apps.buchhaltung.services.zahlungs_zuordnung_service import (
            verrechne_eingang_manuell,
        )
        ss = self._sollstellung(periode=date(2025, 5, 1), erloes_jahr=2026)
        bank = Konto.objects.create(
            wirtschaftsjahr=self.wj25, kontonummer='18000', kontoname='Bank 1')

        verrechne_eingang_manuell(
            personenkonto=self.pk, bank_sachkonto=bank, betrag=Decimal('397.12'),
            buchungsdatum=date(2025, 5, 2), buchungstext='Überweisung',
            wirtschaftsjahr=self.wj25, user=self.user,
            sollstellungs_ids=[str(ss.id)],
        )

        teile = Buchung.objects.filter(parent_buchung__isnull=False)\
            .select_related('haben_konto__wirtschaftsjahr')
        self.assertEqual(teile.count(), 2)
        for b in teile:
            self.assertEqual(b.haben_konto.wirtschaftsjahr.jahr, 2025,
                             f'{b.haben_konto.kontonummer} ins falsche Jahr gebucht')


class WkzKontoJahrTest(LastschriftErloesTestBase):
    """WKZ-Kontosuche darf nicht in ein beliebiges Wirtschaftsjahr greifen."""

    def setUp(self):
        super().setUp()
        for wj in (self.wj25, self.wj26):
            Konto.objects.create(
                wirtschaftsjahr=wj, kontonummer='50100', kontoname='Hausmeister')

    def test_finde_konto_trifft_das_gewuenschte_jahr(self):
        from apps.buchhaltung.services.wkz.buchungs_service import _finde_konto
        for jahr in (2025, 2026):
            konto = _finde_konto(self.objekt, '50100', jahr=jahr)
            self.assertEqual(konto.wirtschaftsjahr.jahr, jahr)

    def test_fehlendes_konto_im_jahr_wird_zum_fehler(self):
        """Kein stilles Ausweichen in ein anderes Jahr."""
        from apps.buchhaltung.services.wkz.buchungs_service import (
            KontoNichtImWJException, _finde_konto,
        )
        Konto.objects.filter(wirtschaftsjahr=self.wj25, kontonummer='50100').delete()
        with self.assertRaises(KontoNichtImWJException) as ctx:
            _finde_konto(self.objekt, '50100', jahr=2025)
        self.assertIn('2025', str(ctx.exception))
        # im Folgejahr existiert es weiterhin
        self.assertIsNotNone(_finde_konto(self.objekt, '50100', jahr=2026))


class ErloeskontoJahrTest(LastschriftErloesTestBase):

    def test_mit_jahr_wird_das_konto_des_jahres_gewaehlt(self):
        konto = _erloeskonto_fuer_ba(self.ba900, self.objekt, jahr=2025)
        self.assertEqual(konto, self.konten[(2025, '41900')])

    def test_ohne_jahr_faellt_auf_das_juengste_offene_wj_zurueck(self):
        konto = _erloeskonto_fuer_ba(self.ba900, self.objekt)
        self.assertEqual(konto, self.konten[(2026, '41900')])

    def test_fehlendes_konto_im_jahr_faellt_zurueck(self):
        self.konten[(2025, '41911')].delete()
        konto = _erloeskonto_fuer_ba(self.ba911, self.objekt, jahr=2025)
        self.assertEqual(konto, self.konten[(2026, '41911')])

    def test_ba_ohne_default_konto(self):
        ba = Buchungsart.objects.create(
            nr='777', kuerzel='X', bezeichnung='Ohne Konto', erloeskonto_default_nr='')
        self.assertIsNone(_erloeskonto_fuer_ba(ba, self.objekt, jahr=2025))

    def test_sollstellung_erhaelt_konto_des_periodenjahres(self):
        """Der Lauf selbst muss das Jahr der Periode durchreichen."""
        from apps.buchhaltung.services.sollstellung_service import (
            lege_hausgeld_sollstellung_an,
        )
        ss = lege_hausgeld_sollstellung_an(
            self.ev, date(2025, 7, 1),
            {self.ba900: Decimal('320.97'), self.ba911: Decimal('76.15')},
            user=self.user,
        )
        for split in ss.splits.all():
            self.assertEqual(split.erloeskonto.wirtschaftsjahr.jahr, 2025,
                             f'Split {split.ba.nr} zeigt ins falsche Jahr')
