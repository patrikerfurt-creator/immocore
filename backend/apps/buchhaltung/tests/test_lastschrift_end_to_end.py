"""
End-to-End: Was löst ein Lastschriftlauf aus — und was passiert, wenn die
Lastschrift auf dem Bankkonto eingeht?

Der Zahlungsweg läuft über das Clearingkonto 13650 (DCL-Debitor):

  Schritt 1 (Lauf erstellen/exportieren):  13650 Soll / Personenkonto Haben
                                           + je Split: PK Soll / Erlöskonto Haben
  Schritt 2 (Gutschrift auf dem Konto):    18000 Soll / 13650 Haben

Erst beide Schritte zusammen stellen 13650 glatt. Fehlt Schritt 2, steht der
Einzug als offene Forderung gegen die Bank im Kontenplan.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.test import TestCase

from apps.buchhaltung.models import (
    Buchung, Buchungsart, HausgeldSollstellung, Kontoumsatz, LastschriftLauf,
    SollstellungSplit,
)
from apps.buchhaltung.services.ebanking_buchungs_service import verbuche
from apps.buchhaltung.services.ebanking_erkennungs_service import fuehre_erkennung_aus
from apps.buchhaltung.services.sepa_lastschrift import (
    commite_lastschriftlauf, erstelle_lastschrift_buchungen, generiere_pain008,
)
from apps.konten.models import Konto, Personenkonto
from apps.objekte.models import Bankkonto, Einheit, Objekt, Wirtschaftsjahr
from apps.personen.models import EigentumsVerhaeltnis, Person, SEPAMandat

User = get_user_model()

HG = Decimal('320.97')
RL = Decimal('76.15')
GESAMT = HG + RL
FAELLIG = date(2025, 5, 5)


class LastschriftEndeZuEndeTest(TestCase):
    """Kompletter Durchlauf: Lauf anlegen → buchen → Bankeingang verbuchen."""

    def setUp(self):
        self.user = User.objects.create_user('ls-e2e', password='x')
        self.objekt = Objekt.objects.create(
            objektnummer='90002', objekt_typ='WEG', bezeichnung='E2E Testobjekt',
            kurzbezeichnung='E2E', strasse='Teststr. 2', plz='12345', ort='Teststadt',
            verwaltung_seit=date(2020, 1, 1),
            glaeubiger_id='DE98ZZZ09999999999',
        )
        self.wj = Wirtschaftsjahr.objects.create(
            objekt=self.objekt, jahr=2025, beginn_monat=1, status='offen')

        self.konten = {}
        for nr, name, direkt in (('13650', 'DCL-Debitor', False),
                                 ('18000', 'Bank Bewirtschaftung', True),
                                 ('41900', 'Erlöse Hausgeld VZ', False),
                                 ('41911', 'Erlöse Rücklage I', False)):
            self.konten[nr] = Konto.objects.create(
                wirtschaftsjahr=self.wj, kontonummer=nr, kontoname=name,
                kontoart='standard', direktes_buchen=direkt,
            )

        self.bankkonto = Bankkonto.objects.create(
            objekt=self.objekt, konto_typ='bewirtschaftung',
            bezeichnung='Bewirtschaftungskonto', iban='DE02120300000000202051',
            bic='BYLADEM1001', kontoinhaber='WEG E2E Testobjekt',
            reihenfolge=1, aktiv=True, zahlungsverkehr=True,
        )

        self.ba900, _ = Buchungsart.objects.get_or_create(
            nr='900', defaults=dict(kuerzel='HG', bezeichnung='Hausgeld'))
        Buchungsart.objects.filter(nr='900').update(erloeskonto_default_nr='41900')
        self.ba911, _ = Buchungsart.objects.get_or_create(
            nr='911', defaults=dict(kuerzel='RL1', bezeichnung='Rücklage I'))
        Buchungsart.objects.filter(nr='911').update(erloeskonto_default_nr='41911')
        self.ba900.refresh_from_db()
        self.ba911.refresh_from_db()

        mandat = SEPAMandat.objects.create(
            mandatsreferenz='M2024-090', iban='DE89370400440532013000',
            bic='COBADEFF', unterzeichnet_am=date(2024, 1, 15), sequence_type='RCUR',
        )
        person = Person.objects.create(
            person_typ='100', vorname='Erika', nachname='Zahler', sepa_mandat=mandat)
        einheit = Einheit.objects.create(
            objekt=self.objekt, einheit_nr='1', einheit_typ='Wohnung', lage='EG')
        self.ev = EigentumsVerhaeltnis.objects.create(
            einheit=einheit, person=person, beginn=date(2020, 1, 1))
        self.pk = Personenkonto.objects.get(vertrag=self.ev)

        self.ss = self._sollstellung()

    # -- Helfer ----------------------------------------------------------

    def _sollstellung(self, periode=date(2025, 5, 1)):
        from apps.buchhaltung.services.opos_nr_service import naechste_opos_nr
        ss = HausgeldSollstellung.objects.create(
            objekt=self.objekt, eigentumsverhaeltnis=self.ev,
            sollstellungs_typ='hausgeld', ba=None, periode=periode,
            faellig_am=periode, opos_nr=naechste_opos_nr(self.objekt),
            soll_betrag=GESAMT, ist_betrag=Decimal('0'),
            status_cached='offen', erstellt_von=self.user,
        )
        for ba, betrag, knr in ((self.ba900, HG, '41900'), (self.ba911, RL, '41911')):
            SollstellungSplit.objects.create(
                sollstellung=ss, ba=ba, betrag=betrag,
                bankkonto_ziel=self.bankkonto, erloeskonto=self.konten[knr],
            )
        return ss

    def _lauf(self):
        return commite_lastschriftlauf(
            self.objekt, FAELLIG, [self.ss], self.user, zweck_prefix='Hausgeld')

    def _kontoumsatz(self, betrag, datum=FAELLIG, **kwargs):
        felder = dict(
            objekt=self.objekt, bankkonto=self.bankkonto, betrag=betrag,
            buchungsdatum=datum, auftraggeber_name='Sammel-Lastschrift',
            verwendungszweck='SEPA-Lastschrift Sammler', end_to_end_id='',
            auftraggeber_iban='', sha256_hash=f'hash-{betrag}-{datum}-{len(kwargs)}',
            status='importiert',
        )
        felder.update(kwargs)
        return Kontoumsatz.objects.create(**felder)

    def _saldo(self, kontonummer):
        """Soll minus Haben auf einem Sachkonto."""
        konto = self.konten[kontonummer]
        soll = Buchung.objects.filter(soll_konto=konto).aggregate(
            s=Sum('betrag'))['s'] or Decimal('0')
        haben = Buchung.objects.filter(haben_konto=konto).aggregate(
            s=Sum('betrag'))['s'] or Decimal('0')
        return soll - haben

    # -- Schritt 1: Lauf erstellen ---------------------------------------

    def test_1_lauf_fasst_alle_splits_zu_einer_position_zusammen(self):
        lauf = self._lauf()
        self.assertEqual(lauf.anzahl_positionen, 1)
        self.assertEqual(lauf.gesamt_summe, GESAMT)
        self.assertEqual(lauf.status, 'erstellt')
        self.assertFalse(lauf.buchungen_erstellt)

        pos = lauf.positionen[0]
        self.assertEqual(Decimal(pos['betrag']), GESAMT)
        self.assertEqual(pos['mandatsreferenz'], 'M2024-090')
        self.assertEqual(pos['schuldner_iban'], 'DE89370400440532013000')
        self.assertEqual(pos['kreditorkonto_iban'], self.bankkonto.iban)
        self.assertEqual(pos['seq_typ'], 'RCUR')
        self.assertEqual(pos['end_to_end_id'], self.ss.opos_nr)
        self.assertEqual(pos['verwendungszweck'], 'Hausgeld 05/2025 - 1 - Objekt E2E')

    def test_1_pain008_enthaelt_die_position(self):
        xml = generiere_pain008(self._lauf())
        for erwartet in ('CstmrDrctDbtInitn', '<PmtMtd>DD</PmtMtd>',
                         '<SeqTp>RCUR</SeqTp>', '<ReqdColltnDt>2025-05-05',
                         '>397.12<', 'M2024-090', 'DE89370400440532013000',
                         'DE98ZZZ09999999999'):
            self.assertIn(erwartet, xml, f'{erwartet} fehlt im pain.008')

    def test_1_buchungen_erzeugen_kopf_und_erloesbeine(self):
        lauf = self._lauf()
        erstelle_lastschrift_buchungen(lauf, self.user)
        lauf.refresh_from_db()

        self.assertTrue(lauf.buchungen_erstellt)
        self.assertEqual(lauf.status, 'exportiert')
        self.assertEqual(lauf.buchungen_datum, FAELLIG)

        kopf = Buchung.objects.get(parent_buchung__isnull=True,
                                   belegnr__startswith='LS-2025-')
        self.assertEqual(kopf.soll_konto, self.konten['13650'])
        self.assertIsNone(kopf.haben_konto)
        self.assertEqual(kopf.personenkonto, self.pk)
        self.assertEqual(kopf.betrag, GESAMT)
        self.assertEqual(kopf.buchungsdatum, FAELLIG)
        self.assertEqual(kopf.wirtschaftsjahr, self.wj)
        self.assertEqual(kopf.status, 'festgeschrieben')

        beine = {b.buchungsart.nr: b for b in
                 Buchung.objects.filter(parent_buchung=kopf).select_related('buchungsart')}
        self.assertEqual(set(beine), {'900', '911'})
        self.assertEqual(beine['900'].haben_konto, self.konten['41900'])
        self.assertEqual(beine['900'].betrag, HG)
        self.assertEqual(beine['911'].haben_konto, self.konten['41911'])
        self.assertEqual(beine['911'].betrag, RL)

    def test_1_sollstellung_ist_nach_dem_lauf_ausgeglichen(self):
        lauf = self._lauf()
        erstelle_lastschrift_buchungen(lauf, self.user)

        self.ss.refresh_from_db()
        self.assertEqual(self.ss.status_cached, 'ausgeglichen')
        self.assertEqual(self.ss.ist_betrag, GESAMT)
        self.assertEqual(
            [s.ist_betrag_split for s in self.ss.splits.order_by('ba__nr')], [HG, RL])
        self.assertEqual(
            self.ss.zahlungen.aggregate(s=Sum('betrag'))['s'], GESAMT)

    def test_1_zweiter_aufruf_bucht_nicht_doppelt(self):
        lauf = self._lauf()
        erstelle_lastschrift_buchungen(lauf, self.user)
        vorher = Buchung.objects.count()
        erstelle_lastschrift_buchungen(lauf, self.user)
        self.assertEqual(Buchung.objects.count(), vorher)

    def test_1_offen_bleibt_die_forderung_gegen_die_bank(self):
        """Vor dem Kontoeingang steht der Einzug als Soll-Saldo auf 13650."""
        lauf = self._lauf()
        erstelle_lastschrift_buchungen(lauf, self.user)
        self.assertEqual(self._saldo('13650'), GESAMT)
        self.assertEqual(self._saldo('18000'), Decimal('0'))

    # -- Schritt 2: Eingang auf dem Bankkonto ----------------------------

    def test_2_sammelgutschrift_wird_als_lastschriftlauf_erkannt(self):
        lauf = self._lauf()
        erstelle_lastschrift_buchungen(lauf, self.user)

        ku = fuehre_erkennung_aus(self._kontoumsatz(GESAMT))
        self.assertEqual(ku.status, 'erkannt')
        self.assertEqual(ku.erkennungs_quelle, 'sammellastschrift')
        self.assertEqual(ku.erkennungs_konfidenz, Decimal('1.00'))
        self.assertEqual(ku.erkannt_gegenkonto, self.konten['13650'])
        self.assertIn('13650', ku.erkennungs_begruendung)

    def test_2_erkennung_greift_in_der_7_tage_toleranz(self):
        lauf = self._lauf()
        erstelle_lastschrift_buchungen(lauf, self.user)

        ku = fuehre_erkennung_aus(
            self._kontoumsatz(GESAMT, datum=FAELLIG + timedelta(days=6)))
        self.assertEqual(ku.erkennungs_quelle, 'sammellastschrift')

        ku2 = fuehre_erkennung_aus(
            self._kontoumsatz(GESAMT, datum=FAELLIG + timedelta(days=8),
                              sha256_hash='hash-ausserhalb'))
        self.assertNotEqual(ku2.erkennungs_quelle, 'sammellastschrift')

    def test_2_erkennung_wird_nicht_automatisch_verbucht(self):
        """Stufe 1b2 setzt nur 'erkannt' — die Verbuchung bleibt ein eigener Schritt."""
        lauf = self._lauf()
        erstelle_lastschrift_buchungen(lauf, self.user)
        ku = fuehre_erkennung_aus(self._kontoumsatz(GESAMT))
        self.assertIsNone(ku.buchung)
        self.assertIsNone(ku.verbucht_am)

    def test_2_verbuchung_stellt_das_clearingkonto_glatt(self):
        lauf = self._lauf()
        erstelle_lastschrift_buchungen(lauf, self.user)
        ku = fuehre_erkennung_aus(self._kontoumsatz(GESAMT))

        b = verbuche(ku, self.user)
        ku.refresh_from_db()

        self.assertEqual(ku.status, 'verbucht')
        self.assertEqual(ku.buchung, b)
        self.assertEqual(b.soll_konto, self.konten['18000'])
        self.assertEqual(b.haben_konto, self.konten['13650'])
        self.assertEqual(b.betrag, GESAMT)
        self.assertEqual(b.buchungsdatum, FAELLIG)
        self.assertEqual(b.wirtschaftsjahr, self.wj)

        self.assertEqual(self._saldo('13650'), Decimal('0'))
        self.assertEqual(self._saldo('18000'), GESAMT)
        self.assertEqual(self._saldo('41900'), -HG)
        self.assertEqual(self._saldo('41911'), -RL)

    def test_2_einzelgutschrift_mit_e2e_id_bucht_nicht_doppelt(self):
        """
        Liefert die Bank statt des Sammlers Einzelgutschriften mit EndToEndId,
        darf Stufe 1a die bereits getilgte Sollstellung nicht erneut verrechnen.
        """
        lauf = self._lauf()
        erstelle_lastschrift_buchungen(lauf, self.user)
        vorher = Buchung.objects.count()

        ku = fuehre_erkennung_aus(self._kontoumsatz(
            GESAMT, end_to_end_id=f'{self.ss.opos_nr}-B', sha256_hash='hash-e2e'))

        self.assertNotEqual(ku.erkennungs_quelle, 'e2e_id')
        self.assertNotEqual(ku.status, 'verbucht')
        self.assertEqual(Buchung.objects.count(), vorher)
        self.ss.refresh_from_db()
        self.assertEqual(self.ss.ist_betrag, GESAMT)
