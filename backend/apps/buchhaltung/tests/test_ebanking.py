"""
E-Banking Tests (Phase G — Kap. 12.1 + 12.2).

Unit-Tests:
  - normalisiere_verwendungszweck / verwendungszweck_hash
  - regel_anlegen_oder_aktualisieren (Idempotenz)
  - verbuche (Vorzeichen-Logik, Validierungen)

Integrationstests (Pfade 3, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14):
  Pfade 1 + 2 (Hausgeld-Tilgung) setzen vollständige Nebenbuch-Daten voraus
  und werden in einem separaten Nebenbuch-Integrationstest abgedeckt.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.objekte.models import Objekt, Bankkonto, Wirtschaftsjahr
from apps.konten.models import Konto
from apps.personen.models import Person, EigentumsVerhaeltnis, HausgeldHistorie
from apps.objekte.models import Einheit
from apps.konten.models import Personenkonto, Abrechnungsart
from apps.buchhaltung.models import (
    Kontoumsatz, BankMatchRegel, BankErkennungsLog, CamtImportLog,
    KreditorOP, Buchung,
)
from apps.rechnungen.models import Kreditor as KreditorModel, Rechnung
from apps.buchhaltung.services.ebanking_erkennungs_service import (
    normalisiere_verwendungszweck,
    verwendungszweck_hash,
    regel_anlegen_oder_aktualisieren,
    fuehre_erkennung_aus,
    hausgeld_soll_zum_stichtag,
)
from apps.buchhaltung.services.ebanking_buchungs_service import verbuche, storniere
from apps.buchhaltung.services.camt054_service import erkenne_camt_typ, verarbeite_camt054

User = get_user_model()


# ---------------------------------------------------------------------------
# Test-Fixtures
# ---------------------------------------------------------------------------

def _setup_objekt_und_konten():
    objekt = Objekt.objects.create(
        bezeichnung='Test-WEG-EB',
        objektnummer='EB001',
        objekt_typ='WEG',
        strasse='Teststr. 1',
        plz='60000',
        ort='Teststadt',
        verwaltung_seit=date(2020, 1, 1),
        auto_verbuchen_aktiv=True,
    )
    wj = Wirtschaftsjahr.objects.create(objekt=objekt, jahr=2026, beginn_monat=1)
    bank_konto = Konto.objects.create(
        wirtschaftsjahr=wj, kontonummer='18000', kontoname='Bank',
        kontoart='standard', direktes_buchen=True,
    )
    aufwand_konto = Konto.objects.create(
        wirtschaftsjahr=wj, kontonummer='55400', kontoname='Strom',
        kontoart='standard', direktes_buchen=True,
    )
    erloes_konto = Konto.objects.create(
        wirtschaftsjahr=wj, kontonummer='41900', kontoname='Hausgeld-Erlös',
        kontoart='standard', direktes_buchen=True,
    )
    summierung_konto = Konto.objects.create(
        wirtschaftsjahr=wj, kontonummer='50000', kontoname='Summierung',
        kontoart='summierung', direktes_buchen=False,
    )
    bankkonto = Bankkonto.objects.create(
        objekt=objekt, konto_typ='bewirtschaftung',
        bezeichnung='Girokonto', iban='DE07501900000300275532',
    )
    return objekt, wj, bank_konto, aufwand_konto, erloes_konto, summierung_konto, bankkonto


def _make_user():
    return User.objects.create_user(username='test_eb', password='x')


def _make_ku(objekt, bankkonto, betrag='-500.00', iban='DE12345678901234567890'):
    return Kontoumsatz.objects.create(
        objekt=objekt,
        bankkonto=bankkonto,
        sha256_hash=f'hash_{betrag}_{iban}',
        betrag=Decimal(betrag),
        buchungsdatum=date(2026, 1, 15),
        auftraggeber_name='Test GmbH',
        auftraggeber_iban=iban,
        verwendungszweck='Strom Januar 2026',
    )


# ---------------------------------------------------------------------------
# Unit-Tests: normalisiere_verwendungszweck / verwendungszweck_hash
# ---------------------------------------------------------------------------

class NormalisierungTest(TestCase):

    def test_datumsangaben_werden_entfernt(self):
        result = normalisiere_verwendungszweck("Miete 01.01.2026 fällig")
        self.assertNotIn('01.01.2026', result)
        self.assertNotIn('2026', result)

    def test_belegnummern_werden_entfernt(self):
        result = normalisiere_verwendungszweck("RE-12345 Strom")
        self.assertNotIn('12345', result)

    def test_whitespace_normalisiert(self):
        result = normalisiere_verwendungszweck("  Strom   Januar  ")
        self.assertEqual(result, "strom januar")

    def test_grosskleinschreibung(self):
        result = normalisiere_verwendungszweck("HAUSGELD JANUAR")
        self.assertEqual(result, "hausgeld januar")

    def test_hash_stabil_gegen_whitespace(self):
        h1 = verwendungszweck_hash("Hausgeld  Januar 2026")
        h2 = verwendungszweck_hash("Hausgeld Januar 2026")
        self.assertEqual(h1, h2)

    def test_hash_stabil_gegen_belegnummer_variation(self):
        h1 = verwendungszweck_hash("Strom RE-001")
        h2 = verwendungszweck_hash("Strom RE-999")
        self.assertEqual(h1, h2)

    def test_hash_stabil_gegen_datum_variation(self):
        h1 = verwendungszweck_hash("Hausgeld 01.2026")
        h2 = verwendungszweck_hash("Hausgeld 02.2026")
        self.assertEqual(h1, h2)

    def test_hash_64_zeichen_hex(self):
        h = verwendungszweck_hash("irgendwas")
        self.assertEqual(len(h), 64)
        int(h, 16)  # muss hex-parsierbar sein

    def test_hash_leerstring_stabil(self):
        h1 = verwendungszweck_hash("")
        h2 = verwendungszweck_hash("   ")
        self.assertEqual(h1, h2)


# ---------------------------------------------------------------------------
# Unit-Tests: regel_anlegen_oder_aktualisieren (Idempotenz)
# ---------------------------------------------------------------------------

class RegelIdempotenzTest(TestCase):

    def setUp(self):
        (self.objekt, self.wj, self.bank_konto, self.aufwand_konto,
         self.erloes_konto, self.summierung_konto, self.bankkonto) = _setup_objekt_und_konten()
        self.user = _make_user()
        self.ku = _make_ku(self.objekt, self.bankkonto)

    def test_erste_bestätigung_legt_regel_an(self):
        regel = regel_anlegen_oder_aktualisieren(
            self.ku, self.aufwand_konto, 'bestaetigung', self.user
        )
        self.assertIsNotNone(regel.id)
        self.assertEqual(regel.trefferzahl, 1)
        self.assertEqual(regel.status, 'aktiv')
        self.assertEqual(regel.erstellt_aus, 'bestaetigung')

    def test_gleiche_bestaetigung_zweimal_idempotent(self):
        regel_anlegen_oder_aktualisieren(self.ku, self.aufwand_konto, 'bestaetigung', self.user)
        regel2 = regel_anlegen_oder_aktualisieren(self.ku, self.aufwand_konto, 'bestaetigung', self.user)
        self.assertEqual(regel2.trefferzahl, 2)
        self.assertEqual(BankMatchRegel.objects.filter(status='aktiv').count(), 1)

    def test_korrektur_veraltet_alte_regel(self):
        regel_anlegen_oder_aktualisieren(self.ku, self.aufwand_konto, 'bestaetigung', self.user)
        neue_regel = regel_anlegen_oder_aktualisieren(self.ku, self.erloes_konto, 'korrektur', self.user)
        alte_regel = BankMatchRegel.objects.filter(gegenkonto=self.aufwand_konto).first()
        self.assertEqual(alte_regel.status, 'veraltet')
        self.assertEqual(neue_regel.status, 'aktiv')
        self.assertEqual(neue_regel.erstellt_aus, 'korrektur')

    def test_keine_doppelte_aktive_regel(self):
        regel_anlegen_oder_aktualisieren(self.ku, self.aufwand_konto, 'bestaetigung', self.user)
        regel_anlegen_oder_aktualisieren(self.ku, self.aufwand_konto, 'bestaetigung', self.user)
        self.assertEqual(BankMatchRegel.objects.filter(status='aktiv').count(), 1)


# ---------------------------------------------------------------------------
# Unit-Tests: verbuche — Vorzeichen-Logik
# ---------------------------------------------------------------------------

class VerbuchungsVorzeichenTest(TestCase):

    def setUp(self):
        (self.objekt, self.wj, self.bank_konto, self.aufwand_konto,
         self.erloes_konto, self.summierung_konto, self.bankkonto) = _setup_objekt_und_konten()
        self.user = _make_user()

    def test_ausgang_soll_gegenkonto_haben_bank(self):
        ku = Kontoumsatz.objects.create(
            objekt=self.objekt, bankkonto=self.bankkonto,
            sha256_hash='h_ausgang',
            betrag=Decimal('-500.00'), buchungsdatum=date(2026, 1, 15),
            auftraggeber_name='Stadtwerke', verwendungszweck='Strom',
        )
        b = verbuche(ku, verbucht_von=self.user, gegenkonto=self.aufwand_konto)
        self.assertEqual(b.soll_konto_id, self.aufwand_konto.id)
        self.assertEqual(b.haben_konto_id, self.bank_konto.id)
        self.assertEqual(b.betrag, Decimal('500.00'))

    def test_eingang_soll_bank_haben_gegenkonto(self):
        ku = Kontoumsatz.objects.create(
            objekt=self.objekt, bankkonto=self.bankkonto,
            sha256_hash='h_eingang',
            betrag=Decimal('300.00'), buchungsdatum=date(2026, 1, 15),
            auftraggeber_name='Mieter',
        )
        b = verbuche(ku, verbucht_von=self.user, gegenkonto=self.erloes_konto)
        self.assertEqual(b.soll_konto_id, self.bank_konto.id)
        self.assertEqual(b.haben_konto_id, self.erloes_konto.id)
        self.assertEqual(b.betrag, Decimal('300.00'))

    def test_validierung_summierungskonto_abgelehnt(self):
        ku = Kontoumsatz.objects.create(
            objekt=self.objekt, bankkonto=self.bankkonto,
            sha256_hash='h_summ',
            betrag=Decimal('-100.00'), buchungsdatum=date(2026, 1, 15),
        )
        with self.assertRaises(ValidationError):
            verbuche(ku, verbucht_von=self.user, gegenkonto=self.summierung_konto)

    def test_validierung_kein_direktes_buchen_ausserhalb_aufwandsbereich_abgelehnt(self):
        """Konto außerhalb 50000–55999 und kein Kreditorkonto (70xxx) mit
        direktes_buchen=False ist weiterhin nicht buchbar."""
        konto_nd = Konto.objects.create(
            wirtschaftsjahr=self.wj, kontonummer='46000', kontoname='ND',
            kontoart='standard', direktes_buchen=False,
        )
        ku = Kontoumsatz.objects.create(
            objekt=self.objekt, bankkonto=self.bankkonto,
            sha256_hash='h_nd',
            betrag=Decimal('-100.00'), buchungsdatum=date(2026, 1, 15),
        )
        with self.assertRaises(ValidationError):
            verbuche(ku, verbucht_von=self.user, gegenkonto=konto_nd)

    def test_aufwandskonto_50xxx_ohne_direktes_buchen_buchbar(self):
        """Aufwandskonten im Bereich 50000–55999 sind auch mit
        direktes_buchen=False direkt buchbar (Sonderregel wie im
        Rechnungs-Modul)."""
        konto_aufwand_50xxx = Konto.objects.create(
            wirtschaftsjahr=self.wj, kontonummer='52000', kontoname='Instandhaltung',
            kontoart='standard', direktes_buchen=False,
        )
        ku = Kontoumsatz.objects.create(
            objekt=self.objekt, bankkonto=self.bankkonto,
            sha256_hash='h_50xxx',
            betrag=Decimal('-100.00'), buchungsdatum=date(2026, 1, 15),
        )
        b = verbuche(ku, verbucht_von=self.user, gegenkonto=konto_aufwand_50xxx)
        self.assertEqual(b.soll_konto_id, konto_aufwand_50xxx.id)
        self.assertEqual(b.haben_konto_id, self.bank_konto.id)
        self.assertEqual(b.betrag, Decimal('100.00'))

    def test_bereits_verbuchter_umsatz_wirft_fehler(self):
        ku = Kontoumsatz.objects.create(
            objekt=self.objekt, bankkonto=self.bankkonto,
            sha256_hash='h_doppelt',
            betrag=Decimal('-200.00'), buchungsdatum=date(2026, 1, 15),
        )
        verbuche(ku, verbucht_von=self.user, gegenkonto=self.aufwand_konto)
        with self.assertRaises(ValidationError):
            verbuche(ku, verbucht_von=self.user, gegenkonto=self.aufwand_konto)

    def test_kein_bank_sachkonto_wirft_fehler(self):
        objekt2 = Objekt.objects.create(
            bezeichnung='Objekt ohne Bank', objektnummer='EB002', objekt_typ='WEG',
            strasse='X', plz='60000', ort='X', verwaltung_seit=date(2020, 1, 1),
        )
        ku = Kontoumsatz.objects.create(
            objekt=objekt2, sha256_hash='h_nobank',
            betrag=Decimal('-100.00'), buchungsdatum=date(2026, 1, 15),
        )
        with self.assertRaises(ValidationError):
            verbuche(ku, verbucht_von=self.user, gegenkonto=self.aufwand_konto)


# ---------------------------------------------------------------------------
# Integration: Pfad 3 — BankMatchRegel-Treffer + Auto-Verbuchen aktiv
# ---------------------------------------------------------------------------

class PfadDreiAutoVerbuchenTest(TestCase):

    def setUp(self):
        (self.objekt, self.wj, self.bank_konto, self.aufwand_konto,
         self.erloes_konto, self.summierung_konto, self.bankkonto) = _setup_objekt_und_konten()
        self.user = _make_user()
        self.objekt.auto_verbuchen_aktiv = True
        self.objekt.save(update_fields=['auto_verbuchen_aktiv'])
        # Bestehende Regel anlegen
        iban_key = 'DE12345678901234567890'
        vz_hash = verwendungszweck_hash('Strom Januar 2026')
        BankMatchRegel.objects.create(
            bankkonto=self.bankkonto,
            kontrahent_iban=iban_key,
            verwendungszweck_hash=vz_hash,
            gegenkonto=self.aufwand_konto,
            status='aktiv',
            erstellt_aus='bestaetigung',
            trefferzahl=1,
            erstellt_von=self.user,
        )

    def test_stufe2_treffer_auto_verbucht(self):
        ku = _make_ku(self.objekt, self.bankkonto)
        fuehre_erkennung_aus(ku)
        ku.refresh_from_db()
        self.assertEqual(ku.status, 'verbucht')
        self.assertIsNotNone(ku.buchung)
        self.assertEqual(ku.erkennungs_quelle, 'bank_match_regel')
        self.assertEqual(ku.erkennungs_konfidenz, Decimal('1.00'))

    def test_stufe2_trefferzahl_erhoehen(self):
        regel = BankMatchRegel.objects.get(bankkonto=self.bankkonto, status='aktiv')
        ku = _make_ku(self.objekt, self.bankkonto)
        fuehre_erkennung_aus(ku)
        regel.refresh_from_db()
        self.assertEqual(regel.trefferzahl, 2)

    def test_erkennungslog_geschrieben(self):
        ku = _make_ku(self.objekt, self.bankkonto)
        fuehre_erkennung_aus(ku)
        log = BankErkennungsLog.objects.filter(kontoumsatz=ku).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.stufe_erreicht, '2')
        self.assertTrue(log.auto_verbucht)


# ---------------------------------------------------------------------------
# Integration: Pfad 4 — BankMatchRegel-Treffer + Auto-Verbuchen INAKTIV
# ---------------------------------------------------------------------------

class PfadVierAutoVerbuchenInaktivTest(TestCase):

    def setUp(self):
        (self.objekt, self.wj, self.bank_konto, self.aufwand_konto,
         self.erloes_konto, self.summierung_konto, self.bankkonto) = _setup_objekt_und_konten()
        self.user = _make_user()
        self.objekt.auto_verbuchen_aktiv = False
        self.objekt.save(update_fields=['auto_verbuchen_aktiv'])
        iban_key = 'DE12345678901234567890'
        vz_hash = verwendungszweck_hash('Strom Januar 2026')
        BankMatchRegel.objects.create(
            bankkonto=self.bankkonto,
            kontrahent_iban=iban_key,
            verwendungszweck_hash=vz_hash,
            gegenkonto=self.aufwand_konto,
            status='aktiv', erstellt_aus='bestaetigung', trefferzahl=1,
            erstellt_von=self.user,
        )

    def test_stufe2_erkannt_kein_auto_verbuchen(self):
        ku = _make_ku(self.objekt, self.bankkonto)
        fuehre_erkennung_aus(ku)
        ku.refresh_from_db()
        self.assertEqual(ku.status, 'erkannt')
        self.assertIsNone(ku.buchung)
        self.assertEqual(ku.erkennungs_quelle, 'bank_match_regel')


# ---------------------------------------------------------------------------
# Integration: Pfad 5 — IBAN-Match auf Kreditor (Person typ=300)
# ---------------------------------------------------------------------------

class PfadFuenfKreditorMatchTest(TestCase):

    def setUp(self):
        (self.objekt, self.wj, self.bank_konto, self.aufwand_konto,
         self.erloes_konto, self.summierung_konto, self.bankkonto) = _setup_objekt_und_konten()
        self.user = _make_user()
        self.kreditor = Person.objects.create(
            person_typ='300',
            firmenname='Stadtwerke',
            ibans=['DE12345678901234567890'],
        )

    def test_iban_kreditor_ergibt_vorschlag(self):
        ku = _make_ku(self.objekt, self.bankkonto)
        fuehre_erkennung_aus(ku)
        ku.refresh_from_db()
        self.assertEqual(ku.status, 'vorschlag')
        self.assertEqual(ku.erkennungs_quelle, 'iban_kreditor')
        self.assertEqual(ku.erkennungs_konfidenz, Decimal('0.80'))
        self.assertEqual(ku.erkannt_kreditor_id, self.kreditor.id)
        self.assertIsNone(ku.erkannt_gegenkonto)

    def test_kein_journaleintrag_bei_vorschlag(self):
        ku = _make_ku(self.objekt, self.bankkonto)
        fuehre_erkennung_aus(ku)
        ku.refresh_from_db()
        self.assertIsNone(ku.buchung)


# ---------------------------------------------------------------------------
# Aufwandsnachtrag aus 15900 beim OP-Ausgleich über die Bankseite
# ---------------------------------------------------------------------------

class AufwandNachtragTest(TestCase):
    """
    Wird eine Kreditorrechnung über einen Bankumsatz direkt gegen das
    Kreditorkonto ausgeglichen, schloss _versuche_op_ausgleich() bisher nur den
    OP und setzte die Rechnung auf 'bezahlt' — der Betrag blieb auf 15900 und
    das kontierte Aufwandskonto leer.
    """

    def setUp(self):
        (self.objekt, self.wj, self.bank_konto, self.aufwand_konto,
         self.erloes_konto, self.summierung_konto, self.bankkonto) = _setup_objekt_und_konten()
        self.user = _make_user()
        self.konto_15900 = Konto.objects.create(
            wirtschaftsjahr=self.wj, kontonummer='15900', kontoname='Schwebende ER',
            kontoart='standard', direktes_buchen=False,
        )
        self.konto_70020 = Konto.objects.create(
            wirtschaftsjahr=self.wj, kontonummer='70020', kontoname='Kreditor Test',
            kontoart='standard', direktes_buchen=False,
        )
        self.kreditor = KreditorModel.objects.create(
            kreditorennummer='70020', name='Testlieferant', iban='DE44444444444444444444',
        )

    def _rechnung_mit_op(self, betrag='150.00', gutschrift=False):
        r = Rechnung.objects.create(
            objekt=self.objekt, kreditor=self.kreditor, dateiname='r.pdf',
            sha256_hash=f'h_{betrag}_{gutschrift}', rechnungsnummer='R-1',
            rechnungsdatum=date(2026, 1, 10), betrag_brutto=Decimal(betrag),
            status='freigegeben', aufwandskonto=self.aufwand_konto,
            ist_gutschrift=gutschrift,
        )
        op = KreditorOP.objects.create(
            op_nummer=26000900, kreditor=self.kreditor, objekt=self.objekt, rechnung=r,
            betrag_ursprung=Decimal(betrag), betrag_offen=Decimal(betrag),
            faellig_ab=date(2026, 1, 10), status='offen',
        )
        return r, op

    def test_bankausgleich_bucht_aufwand_aus_15900(self):
        r, op = self._rechnung_mit_op('150.00')
        ku = _make_ku(self.objekt, self.bankkonto, betrag='-150.00', iban='DE44444444444444444444')
        verbuche(ku, verbucht_von=self.user, gegenkonto=self.konto_70020)
        r.refresh_from_db(); op.refresh_from_db()
        self.assertEqual(op.status, 'bezahlt')
        self.assertEqual(r.status, 'bezahlt')
        self.assertIsNotNone(r.aufwand_buchung_id)
        b = r.aufwand_buchung
        self.assertEqual(b.soll_konto_id, self.aufwand_konto.id)
        self.assertEqual(b.haben_konto_id, self.konto_15900.id)
        self.assertEqual(b.betrag, Decimal('150.00'))

    def test_gutschrift_wird_gedreht_gebucht(self):
        r, op = self._rechnung_mit_op('150.00', gutschrift=True)
        ku = _make_ku(self.objekt, self.bankkonto, betrag='-150.00', iban='DE44444444444444444444')
        verbuche(ku, verbucht_von=self.user, gegenkonto=self.konto_70020)
        r.refresh_from_db()
        b = r.aufwand_buchung
        self.assertEqual(b.soll_konto_id, self.konto_15900.id)
        self.assertEqual(b.haben_konto_id, self.aufwand_konto.id)

    def test_idempotent(self):
        """Ein zweiter Aufruf darf keine zweite Aufwandsbuchung erzeugen."""
        from apps.rechnungen.services.rechnung_zahlung_service import buche_aufwand_aus_schwebe
        r, op = self._rechnung_mit_op('150.00')
        ku = _make_ku(self.objekt, self.bankkonto, betrag='-150.00', iban='DE44444444444444444444')
        verbuche(ku, verbucht_von=self.user, gegenkonto=self.konto_70020)
        r.refresh_from_db()
        vorher = Buchung.objects.filter(haben_konto=self.konto_15900).count()
        self.assertIsNone(buche_aufwand_aus_schwebe(r, date(2026, 1, 10), self.user))
        self.assertEqual(Buchung.objects.filter(haben_konto=self.konto_15900).count(), vorher)

    def test_ohne_aufwandskonto_kein_nachtrag(self):
        from apps.rechnungen.services.rechnung_zahlung_service import buche_aufwand_aus_schwebe
        r, op = self._rechnung_mit_op('150.00')
        r.aufwandskonto = None
        r.save(update_fields=['aufwandskonto'])
        self.assertIsNone(buche_aufwand_aus_schwebe(r, date(2026, 1, 10), self.user))


# ---------------------------------------------------------------------------
# Wirtschaftsjahr-Auflösung jahresgebundener Konto-Verweise
# ---------------------------------------------------------------------------

class KontoImJahrTest(TestCase):
    """
    Konto-FKs (BankMatchRegel.gegenkonto, Rechnung.aufwandskonto, ...) zeigen auf
    EIN Wirtschaftsjahr. Beim Buchen müssen sie ins Jahr des Buchungsdatums
    aufgelöst werden, sonst landen Buchungen im Jahr des Verweises.
    """

    def setUp(self):
        (self.objekt, self.wj, self.bank_konto, self.aufwand_konto,
         self.erloes_konto, self.summierung_konto, self.bankkonto) = _setup_objekt_und_konten()
        self.user = _make_user()
        # _setup legt WJ 2026 an; Vorjahr ergänzen
        self.wj_vorjahr = Wirtschaftsjahr.objects.create(objekt=self.objekt, jahr=2025, beginn_monat=1)
        self.aufwand_2025 = Konto.objects.create(
            wirtschaftsjahr=self.wj_vorjahr, kontonummer='55400', kontoname='Strom',
            kontoart='standard', direktes_buchen=True,
        )
        self.bank_2025 = Konto.objects.create(
            wirtschaftsjahr=self.wj_vorjahr, kontonummer='18000', kontoname='Bank',
            kontoart='standard', direktes_buchen=True,
        )

    def test_loest_konto_ins_zieljahr_auf(self):
        from apps.konten.services import konto_im_jahr
        # self.aufwand_konto liegt im WJ 2026, gleiche Nummer 55400 in 2025
        self.assertEqual(konto_im_jahr(self.aufwand_konto, 2025).id, self.aufwand_2025.id)
        self.assertEqual(konto_im_jahr(self.aufwand_2025, 2026).id, self.aufwand_konto.id)

    def test_gibt_original_zurueck_wenn_jahr_passt(self):
        from apps.konten.services import konto_im_jahr
        self.assertEqual(konto_im_jahr(self.aufwand_konto, 2026).id, self.aufwand_konto.id)

    def test_gibt_original_zurueck_wenn_zieljahr_fehlt(self):
        from apps.konten.services import konto_im_jahr
        self.assertEqual(konto_im_jahr(self.aufwand_konto, 2019).id, self.aufwand_konto.id)

    def test_none_bleibt_none(self):
        from apps.konten.services import konto_im_jahr
        self.assertIsNone(konto_im_jahr(None, 2025))

    def test_bank_match_regel_bucht_ins_umsatzjahr(self):
        """
        Eine Regel, die auf ein 2026er Konto zeigt, darf einen Umsatz aus 2025
        nicht ins Jahr 2026 buchen.
        """
        ku_alt = Kontoumsatz.objects.create(
            objekt=self.objekt, bankkonto=self.bankkonto, sha256_hash='h_regel_2025',
            betrag=Decimal('-77.00'), buchungsdatum=date(2025, 6, 15),
            auftraggeber_iban='DE99999999999999999999', verwendungszweck='Stromabschlag',
        )
        # Regel zeigt bewusst auf das Konto im WJ 2026
        regel_anlegen_oder_aktualisieren(ku_alt, self.aufwand_konto, 'bestaetigung', self.user)

        ku_neu = Kontoumsatz.objects.create(
            objekt=self.objekt, bankkonto=self.bankkonto, sha256_hash='h_regel_2025b',
            betrag=Decimal('-77.00'), buchungsdatum=date(2025, 7, 15),
            auftraggeber_iban='DE99999999999999999999', verwendungszweck='Stromabschlag',
        )
        fuehre_erkennung_aus(ku_neu)
        ku_neu.refresh_from_db()
        self.assertEqual(ku_neu.erkennungs_quelle, 'bank_match_regel')
        self.assertEqual(ku_neu.erkannt_gegenkonto.kontonummer, '55400')
        self.assertEqual(ku_neu.erkannt_gegenkonto.wirtschaftsjahr.jahr, 2025)
        self.assertEqual(ku_neu.erkannt_gegenkonto_id, self.aufwand_2025.id)


# ---------------------------------------------------------------------------
# Stufe 2b: Eigentümer per IBAN erkannt, Betrag weicht vom Soll ab
# ---------------------------------------------------------------------------

class EigentuemerAbweichenderBetragTest(TestCase):
    """
    Zahlt ein Eigentümer einen vom Soll abweichenden Betrag (Teilzahlung oder
    runder Dauerauftrag), darf nicht automatisch getilgt werden — der Umsatz
    soll aber der Person zugeordnet als Vorschlag erscheinen statt beim
    KI-Fallback ohne Personenbezug zu landen.

    Deckt zusätzlich ab, dass das Soll zum BUCHUNGSDATUM verglichen wird und
    nicht zum heutigen Tag (neuer Wirtschaftsplan ab Folgejahr).
    """

    ZAHLER_IBAN = 'DE36512500000013496846'

    def setUp(self):
        (self.objekt, self.wj, self.bank_konto, self.aufwand_konto,
         self.erloes_konto, self.summierung_konto, self.bankkonto) = _setup_objekt_und_konten()
        self.user = _make_user()
        self.person = Person.objects.create(
            person_typ='100', vorname='Ella', nachname='Petrovic',
            ibans=['DE58512500000013492182', self.ZAHLER_IBAN],
        )
        self.einheit = Einheit.objects.create(
            objekt=self.objekt, einheit_nr='2', einheit_typ='wohnung', lage='EG rechts',
        )
        self.ev = EigentumsVerhaeltnis.objects.create(
            person=self.person, einheit=self.einheit, beginn=date(2020, 1, 1),
        )
        # Personenkonto wird beim Anlegen des EV automatisch erzeugt
        self.pk = Personenkonto.objects.get(vertrag=self.ev)
        # Wirtschaftsplan: 400.72 ab 2025, 483.11 ab 2026
        self.abr = Abrechnungsart.objects.create(objekt=self.objekt, code='900', bezeichnung='Hausgeld')
        for ab, betrag in ((date(2025, 1, 1), '400.72'), (date(2026, 1, 1), '483.11')):
            HausgeldHistorie.objects.create(
                eigentumsverhaeltnis=self.ev, abrechnungsart=self.abr,
                betrag=Decimal(betrag), gueltig_ab=ab, quelle='import',
                import_referenz='testdaten', erstellt_von=self.user,
            )

    def _make_eingang(self, betrag, datum=date(2025, 4, 1)):
        return Kontoumsatz.objects.create(
            objekt=self.objekt, bankkonto=self.bankkonto,
            sha256_hash=f'hash_ev_{betrag}_{datum}', betrag=Decimal(betrag),
            buchungsdatum=datum,
            auftraggeber_name='', auftraggeber_iban=self.ZAHLER_IBAN,
            verwendungszweck='Liegenschaft Theresenstr TSUmlage',
        )

    def test_abweichender_betrag_ergibt_vorschlag_mit_eigentuemer(self):
        ku = self._make_eingang('400.00')          # Soll 04/2025 ist 400.72
        fuehre_erkennung_aus(ku)
        ku.refresh_from_db()
        self.assertEqual(ku.status, 'vorschlag')
        self.assertEqual(ku.erkennungs_quelle, 'iban_ev_abweichend')
        self.assertEqual(ku.erkannt_eigentumsverhaeltnis_id, self.ev.id)
        self.assertIsNone(ku.buchung)               # nie automatisch gebucht

    def test_zweitiban_des_angehoerigen_wird_gefunden(self):
        """Die Zahlung kommt nicht von der Haupt-IBAN der Eigentümerin."""
        ku = self._make_eingang('400.00')
        fuehre_erkennung_aus(ku)
        ku.refresh_from_db()
        self.assertEqual(ku.erkannt_eigentumsverhaeltnis_id, self.ev.id)

    def test_soll_wird_zum_buchungsdatum_ermittelt_nicht_zu_heute(self):
        """
        Ein Umsatz vom 01.04.2025 muss gegen den ab 2025 gültigen Satz (400.72)
        geprüft werden — nicht gegen den ab 2026 gültigen (483.11), den die
        Property ev.hausgeld_soll mit date.today() liefert.
        """
        self.assertEqual(
            hausgeld_soll_zum_stichtag(self.ev, date(2025, 4, 1)), Decimal('400.72'))
        self.assertEqual(
            hausgeld_soll_zum_stichtag(self.ev, date(2026, 6, 1)), Decimal('483.11'))
        self.assertEqual(self.ev.hausgeld_soll, Decimal('483.11'))

    def test_soll_ohne_historie_ist_none(self):
        ev_leer = EigentumsVerhaeltnis.objects.create(
            person=Person.objects.create(person_typ='100', vorname='Ohne', nachname='Plan'),
            einheit=Einheit.objects.create(
                objekt=self.objekt, einheit_nr='9', einheit_typ='wohnung', lage='DG'),
            beginn=date(2020, 1, 1),
        )
        self.assertIsNone(hausgeld_soll_zum_stichtag(ev_leer, date(2025, 4, 1)))

    def test_unbekannte_iban_greift_nicht(self):
        ku = Kontoumsatz.objects.create(
            objekt=self.objekt, bankkonto=self.bankkonto,
            sha256_hash='hash_fremd', betrag=Decimal('400.00'),
            buchungsdatum=date(2025, 4, 1),
            auftraggeber_iban='DE00000000000000000000',
            verwendungszweck='Fremdzahlung',
        )
        fuehre_erkennung_aus(ku)
        ku.refresh_from_db()
        self.assertNotEqual(ku.erkennungs_quelle, 'iban_ev_abweichend')

    def test_ausgang_greift_nicht(self):
        """Stufe 2b gilt nur für Eingänge."""
        ku = self._make_eingang('-400.00')
        fuehre_erkennung_aus(ku)
        ku.refresh_from_db()
        self.assertNotEqual(ku.erkennungs_quelle, 'iban_ev_abweichend')


# ---------------------------------------------------------------------------
# Zahllauf-Clearing: bereits per Zahllauf beglichene OPs gehören gegen 13600
# ---------------------------------------------------------------------------

class ZahllaufClearingTest(TestCase):
    """
    Wird eine Kreditorrechnung über den Zahllauf bezahlt, bucht
    rechnung_zahlung_service Phase 2 bereits Soll 70xxx / Haben 13600.
    Der später eintreffende camt-Bankabgang darf deshalb NICHT noch einmal
    gegen das Kreditorkonto vorgeschlagen werden, sondern gegen 13600.
    """

    KREDITOR_IBAN = 'DE22500502010200758802'

    def setUp(self):
        (self.objekt, self.wj, self.bank_konto, self.aufwand_konto,
         self.erloes_konto, self.summierung_konto, self.bankkonto) = _setup_objekt_und_konten()
        self.user = _make_user()
        self.konto_13600 = Konto.objects.create(
            wirtschaftsjahr=self.wj, kontonummer='13600', kontoname='DCL-Kreditor',
            kontoart='standard', direktes_buchen=False,
        )
        self.konto_70012 = Konto.objects.create(
            wirtschaftsjahr=self.wj, kontonummer='70012', kontoname='Kreditor Planwerk',
            kontoart='standard', direktes_buchen=False,
        )
        self.kreditor = KreditorModel.objects.create(
            kreditorennummer='70012', name='Planwerk S GmbH', iban=self.KREDITOR_IBAN,
        )

    def _make_op(self, status, zahlung_gegen_13600, betrag='222.14'):
        zahlung_buchung = None
        if zahlung_gegen_13600:
            zahlung_buchung = Buchung.objects.create(
                objekt=self.objekt, betrag=Decimal(betrag), buchungsdatum=date(2026, 1, 10),
                soll_konto=self.konto_70012, haben_konto=self.konto_13600,
                buchungstext='Zahllauf — Verbindlichkeit ausgleichen',
            )
        return KreditorOP.objects.create(
            op_nummer=26000020, kreditor=self.kreditor, objekt=self.objekt,
            betrag_ursprung=Decimal(betrag),
            betrag_offen=Decimal('0.00') if status == 'bezahlt' else Decimal(betrag),
            faellig_ab=date(2026, 1, 1), status=status, zahlung_buchung=zahlung_buchung,
        )

    def test_bezahlter_op_ergibt_13600_statt_kreditorkonto(self):
        self._make_op('bezahlt', zahlung_gegen_13600=True)
        ku = _make_ku(self.objekt, self.bankkonto, betrag='-222.14', iban=self.KREDITOR_IBAN)
        fuehre_erkennung_aus(ku)
        ku.refresh_from_db()
        self.assertEqual(ku.erkannt_gegenkonto_id, self.konto_13600.id)
        self.assertNotEqual(ku.erkannt_gegenkonto_id, self.konto_70012.id)
        self.assertEqual(ku.erkennungs_quelle, 'zahllauf_clearing')
        self.assertEqual(ku.status, 'erkannt')

    def test_offener_op_bleibt_kreditorisch(self):
        """Ein noch offener OP hat Vorrang — dort ist die Kreditorbuchung korrekt."""
        self._make_op('offen', zahlung_gegen_13600=False)
        ku = _make_ku(self.objekt, self.bankkonto, betrag='-222.14', iban=self.KREDITOR_IBAN)
        fuehre_erkennung_aus(ku)
        ku.refresh_from_db()
        self.assertEqual(ku.erkannt_gegenkonto_id, self.konto_70012.id)
        self.assertNotEqual(ku.erkennungs_quelle, 'zahllauf_clearing')

    def test_offener_op_hat_vorrang_vor_bezahltem(self):
        """Gleicher Betrag offen und bezahlt → kreditorisch buchen (OP ausgleichen)."""
        self._make_op('bezahlt', zahlung_gegen_13600=True)
        op_offen = KreditorOP.objects.create(
            op_nummer=26000099, kreditor=self.kreditor, objekt=self.objekt,
            betrag_ursprung=Decimal('222.14'), betrag_offen=Decimal('222.14'),
            faellig_ab=date(2026, 1, 1), status='offen',
        )
        ku = _make_ku(self.objekt, self.bankkonto, betrag='-222.14', iban=self.KREDITOR_IBAN)
        fuehre_erkennung_aus(ku)
        ku.refresh_from_db()
        self.assertEqual(ku.erkannt_gegenkonto_id, self.konto_70012.id)
        self.assertTrue(op_offen.pk)

    def test_bezahlt_ohne_zahllaufbuchung_bleibt_kreditorisch(self):
        """Ohne Zahlungsbuchung gegen 13600 greift die Sonderregel nicht."""
        self._make_op('bezahlt', zahlung_gegen_13600=False)
        ku = _make_ku(self.objekt, self.bankkonto, betrag='-222.14', iban=self.KREDITOR_IBAN)
        fuehre_erkennung_aus(ku)
        ku.refresh_from_db()
        self.assertNotEqual(ku.erkennungs_quelle, 'zahllauf_clearing')

    def test_abweichender_betrag_greift_nicht(self):
        self._make_op('bezahlt', zahlung_gegen_13600=True)
        ku = _make_ku(self.objekt, self.bankkonto, betrag='-999.00', iban=self.KREDITOR_IBAN)
        fuehre_erkennung_aus(ku)
        ku.refresh_from_db()
        self.assertNotEqual(ku.erkennungs_quelle, 'zahllauf_clearing')


# ---------------------------------------------------------------------------
# Integration: Pfad 7 — Kein Treffer → unklar
# ---------------------------------------------------------------------------

class PfadSiebenUnklarTest(TestCase):

    def setUp(self):
        (self.objekt, self.wj, self.bank_konto, self.aufwand_konto,
         self.erloes_konto, self.summierung_konto, self.bankkonto) = _setup_objekt_und_konten()

    def test_kein_treffer_ergibt_unklar(self):
        ku = _make_ku(self.objekt, self.bankkonto, iban='DEUNBEKANNT')
        fuehre_erkennung_aus(ku)
        ku.refresh_from_db()
        self.assertEqual(ku.status, 'unklar')
        self.assertEqual(ku.erkennungs_quelle, 'keine')
        self.assertEqual(ku.erkennungs_konfidenz, Decimal('0.00'))

    def test_erkennungslog_stufe5_geschrieben(self):
        ku = _make_ku(self.objekt, self.bankkonto, iban='DEUNBEKANNT')
        fuehre_erkennung_aus(ku)
        log = BankErkennungsLog.objects.filter(kontoumsatz=ku).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.stufe_erreicht, '5')
        self.assertFalse(log.auto_verbucht)


# ---------------------------------------------------------------------------
# Integration: Pfad 8 — Manuelle Bestätigung (gleiche Gegenkonto) → Regel anlegen
# ---------------------------------------------------------------------------

class PfadAchtBestaetigung(TestCase):

    def setUp(self):
        (self.objekt, self.wj, self.bank_konto, self.aufwand_konto,
         self.erloes_konto, self.summierung_konto, self.bankkonto) = _setup_objekt_und_konten()
        self.user = _make_user()

    def test_bestaetigung_legt_regel_an_und_verbucht(self):
        ku = _make_ku(self.objekt, self.bankkonto)
        fuehre_erkennung_aus(ku)  # → unklar oder vorschlag
        # Manuelle Bestätigung via verbuche + Lernlogik
        regel = regel_anlegen_oder_aktualisieren(ku, self.aufwand_konto, 'bestaetigung', self.user)
        verbuche(ku, verbucht_von=self.user, gegenkonto=self.aufwand_konto)
        ku.refresh_from_db()
        self.assertEqual(ku.status, 'verbucht')
        self.assertIsNotNone(ku.buchung)
        self.assertEqual(regel.erstellt_aus, 'bestaetigung')
        self.assertEqual(regel.trefferzahl, 1)


# ---------------------------------------------------------------------------
# Integration: Pfad 9 — Korrektur (Gegenkonto wechseln) → alte Regel veraltet
# ---------------------------------------------------------------------------

class PfadNeunKorrekturTest(TestCase):

    def setUp(self):
        (self.objekt, self.wj, self.bank_konto, self.aufwand_konto,
         self.erloes_konto, self.summierung_konto, self.bankkonto) = _setup_objekt_und_konten()
        # Korrektur-Szenario: Nutzer sieht erkannten Vorschlag und ändert Gegenkonto manuell.
        # Auto-Verbuchen muss deaktiviert sein, damit fuehre_erkennung_aus nicht bereits bucht.
        self.objekt.auto_verbuchen_aktiv = False
        self.objekt.save(update_fields=['auto_verbuchen_aktiv'])
        self.user = _make_user()
        # Bestehende Regel mit aufwand_konto
        ku_first = _make_ku(self.objekt, self.bankkonto)
        fuehre_erkennung_aus(ku_first)
        regel_anlegen_oder_aktualisieren(ku_first, self.aufwand_konto, 'bestaetigung', self.user)

    def test_korrektur_veraltet_alte_legt_neue_an(self):
        ku = Kontoumsatz.objects.create(
            objekt=self.objekt, bankkonto=self.bankkonto,
            sha256_hash='h_korrektur',
            betrag=Decimal('-500.00'), buchungsdatum=date(2026, 1, 20),
            auftraggeber_name='Test GmbH',
            auftraggeber_iban='DE12345678901234567890',
            verwendungszweck='Strom Januar 2026',
        )
        fuehre_erkennung_aus(ku)  # Soll Regel treffen → erkannt
        # Nutzer wählt andere Gegenkonto (Korrektur)
        neue_regel = regel_anlegen_oder_aktualisieren(ku, self.erloes_konto, 'korrektur', self.user)
        verbuche(ku, verbucht_von=self.user, gegenkonto=self.erloes_konto)

        alte = BankMatchRegel.objects.filter(gegenkonto=self.aufwand_konto).first()
        self.assertEqual(alte.status, 'veraltet')
        self.assertEqual(neue_regel.status, 'aktiv')
        self.assertEqual(neue_regel.erstellt_aus, 'korrektur')


# ---------------------------------------------------------------------------
# Integration: Pfad 10 — Manuelle Vollerfassung (unklar → verbucht)
# ---------------------------------------------------------------------------

class PfadZehnManuellTest(TestCase):

    def setUp(self):
        (self.objekt, self.wj, self.bank_konto, self.aufwand_konto,
         self.erloes_konto, self.summierung_konto, self.bankkonto) = _setup_objekt_und_konten()
        self.user = _make_user()

    def test_manuell_unklar_verbucht(self):
        ku = _make_ku(self.objekt, self.bankkonto, iban='DEUNBEKANNT')
        fuehre_erkennung_aus(ku)
        ku.refresh_from_db()
        self.assertEqual(ku.status, 'unklar')

        regel = regel_anlegen_oder_aktualisieren(ku, self.aufwand_konto, 'manuell', self.user)
        verbuche(ku, verbucht_von=self.user, gegenkonto=self.aufwand_konto)
        ku.refresh_from_db()
        self.assertEqual(ku.status, 'verbucht')
        self.assertEqual(regel.erstellt_aus, 'manuell')


# ---------------------------------------------------------------------------
# Integration: Pfad 11 — Opt-out "Einzelfall"
# ---------------------------------------------------------------------------

class PfadElfOptOutTest(TestCase):

    def setUp(self):
        (self.objekt, self.wj, self.bank_konto, self.aufwand_konto,
         self.erloes_konto, self.summierung_konto, self.bankkonto) = _setup_objekt_und_konten()
        self.user = _make_user()

    def test_opt_out_keine_regel_angelegt(self):
        ku = _make_ku(self.objekt, self.bankkonto, iban='DEUNBEKANNT')
        fuehre_erkennung_aus(ku)
        # Verbuchen ohne Regelanlage (Opt-out)
        verbuche(ku, verbucht_von=self.user, gegenkonto=self.aufwand_konto)
        ku.refresh_from_db()
        self.assertEqual(ku.status, 'verbucht')
        # Keine Regel angelegt
        self.assertEqual(BankMatchRegel.objects.filter(bankkonto=self.bankkonto).count(), 0)


# ---------------------------------------------------------------------------
# Integration: Pfad 12 — Idempotenz (doppelte Bestätigung)
# ---------------------------------------------------------------------------

class PfadZwoelfIdempotenzTest(TestCase):

    def setUp(self):
        (self.objekt, self.wj, self.bank_konto, self.aufwand_konto,
         self.erloes_konto, self.summierung_konto, self.bankkonto) = _setup_objekt_und_konten()
        self.user = _make_user()
        self.ku = _make_ku(self.objekt, self.bankkonto)

    def test_doppelte_bestaetigung_eine_aktive_regel(self):
        regel_anlegen_oder_aktualisieren(self.ku, self.aufwand_konto, 'bestaetigung', self.user)
        regel_anlegen_oder_aktualisieren(self.ku, self.aufwand_konto, 'bestaetigung', self.user)
        aktive = BankMatchRegel.objects.filter(status='aktiv').count()
        self.assertEqual(aktive, 1)
        regel = BankMatchRegel.objects.get(status='aktiv')
        self.assertEqual(regel.trefferzahl, 2)


# ---------------------------------------------------------------------------
# Integration: Pfad 13 — Storno einer verbuchten BankBuchung
# ---------------------------------------------------------------------------

class PfadDreizehnStornoTest(TestCase):

    def setUp(self):
        (self.objekt, self.wj, self.bank_konto, self.aufwand_konto,
         self.erloes_konto, self.summierung_konto, self.bankkonto) = _setup_objekt_und_konten()
        self.user = _make_user()

    def test_storno_setzt_status_storniert(self):
        ku = _make_ku(self.objekt, self.bankkonto)
        verbuche(ku, verbucht_von=self.user, gegenkonto=self.aufwand_konto)
        storno_b = storniere(ku, begruendung='Fehlbuchung', storniert_von=self.user)
        ku.refresh_from_db()
        self.assertEqual(ku.status, 'storniert')
        self.assertIsNotNone(storno_b)

    def test_storno_erstellt_gegenbuchung(self):
        from apps.buchhaltung.models import Buchung
        ku = _make_ku(self.objekt, self.bankkonto)
        original_buchung = verbuche(ku, verbucht_von=self.user, gegenkonto=self.aufwand_konto)
        storno_b = storniere(ku, begruendung='Test', storniert_von=self.user)
        # Storno ist Gegenbuchung
        self.assertEqual(storno_b.soll_konto_id, original_buchung.haben_konto_id)
        self.assertEqual(storno_b.haben_konto_id, original_buchung.soll_konto_id)
        self.assertEqual(storno_b.betrag, original_buchung.betrag)
        self.assertEqual(storno_b.storno_von_id, original_buchung.id)

    def test_original_buchung_status_storniert(self):
        from apps.buchhaltung.models import Buchung
        ku = _make_ku(self.objekt, self.bankkonto)
        original_buchung = verbuche(ku, verbucht_von=self.user, gegenkonto=self.aufwand_konto)
        storniere(ku, begruendung='Test', storniert_von=self.user)
        original_buchung.refresh_from_db()
        self.assertEqual(original_buchung.status, 'storniert')

    def test_storno_nicht_verbuchter_umsatz_wirft_fehler(self):
        ku = _make_ku(self.objekt, self.bankkonto)
        with self.assertRaises(ValidationError):
            storniere(ku, begruendung='Test', storniert_von=self.user)


# ---------------------------------------------------------------------------
# Integration: Pfad 14 — camt.054-Upload
# ---------------------------------------------------------------------------

class PfadVierzehnCamt054Test(TestCase):

    CAMT054_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.054.001.02">
  <BkToCstmrDbtCdtNtfctn>
    <GrpHdr><MsgId>TEST001</MsgId></GrpHdr>
    <Ntfctn><Id>NTFCTN001</Id><Ntry><Amt Ccy="EUR">100.00</Amt></Ntry></Ntfctn>
  </BkToCstmrDbtCdtNtfctn>
</Document>"""

    CAMT053_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
  <BkToCstmrStmt>
    <GrpHdr><MsgId>TEST002</MsgId></GrpHdr>
  </BkToCstmrStmt>
</Document>"""

    def test_erkenne_camt054(self):
        self.assertEqual(erkenne_camt_typ(self.CAMT054_XML), 'camt054')

    def test_erkenne_camt053(self):
        self.assertEqual(erkenne_camt_typ(self.CAMT053_XML), 'camt053')

    def test_verarbeite_camt054_erstellt_log(self):
        log = CamtImportLog.objects.create(typ='camt054')
        log._xml_inhalt = self.CAMT054_XML.decode()
        verarbeite_camt054(log)
        log.refresh_from_db()
        self.assertEqual(log.typ, 'camt054')
        self.assertEqual(log.status, 'pending_mahnwesen_spec')
        self.assertIn('Mahnwesen-Spec', log.notiz)

    def test_verarbeite_camt054_kein_kontoumsatz(self):
        log = CamtImportLog.objects.create(typ='camt054')
        log._xml_inhalt = self.CAMT054_XML.decode()
        verarbeite_camt054(log)
        self.assertEqual(Kontoumsatz.objects.count(), 0)

    def test_erkenne_camt_typ_unbekannt_gibt_camt053(self):
        self.assertEqual(erkenne_camt_typ(b'<Unknown><Test/></Unknown>'), 'camt053')
