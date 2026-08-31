"""
Tests: Ausbuchung offener Kreditor-Posten (BA 056 AUSB-K).

Kern ist die Seitenwahl je Posten: eine Verbindlichkeit wird im Soll des
Kreditorkontos aufgelöst, eine Forderung im Haben. Dazu Statuswechsel,
Guards und die Wirkung auf Schritt 2 der Jahresabrechnung.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.buchhaltung.models import Buchung, KreditorOP
from apps.buchhaltung.services import kreditor_ausbuchung_service
from apps.buchhaltung.services.jahresabrechnung import wizard_service
from apps.konten.models import Konto
from apps.objekte.models import Objekt, Wirtschaftsjahr
from apps.rechnungen.models import Kreditor

User = get_user_model()


class KreditorAusbuchungTestBase(TestCase):

    def setUp(self):
        self.user = User.objects.create_user('ausb-tester', password='x')
        self.objekt = Objekt.objects.create(
            objektnummer='AB-1', objekt_typ='WEG', bezeichnung='Ausbuchung Testobjekt',
            strasse='Teststr. 1', plz='12345', ort='Teststadt',
            verwaltung_seit=date(2020, 1, 1),
        )
        self.wj = Wirtschaftsjahr.objects.create(
            objekt=self.objekt, jahr=2025, beginn_monat=1, status='offen')
        self.gegenkonto = Konto.objects.create(
            wirtschaftsjahr=self.wj, kontonummer='55900',
            kontoname='Periodenfremde Erträge/Aufwendungen')
        self.kreditor = Kreditor.objects.create(name='Ausbuch Handwerk GmbH')
        self.nr = 97000000

    def _op(self, betrag='500.00', urspr=None, status='offen'):
        """urspr negativ → Forderung (Gutschrift), positiv → Verbindlichkeit."""
        self.nr += 1
        betrag = Decimal(betrag)
        return KreditorOP.objects.create(
            op_nummer=self.nr, kreditor=self.kreditor, objekt=self.objekt,
            betrag_ursprung=Decimal(urspr) if urspr is not None else betrag,
            betrag_offen=betrag,
            faellig_ab=date(2025, 3, 1), status=status,
        )

    def _kreditorkonto(self):
        return Konto.objects.get(
            wirtschaftsjahr=self.wj, kontonummer=self.kreditor.kreditorennummer)

    def _ausbuchen(self, ops, datum='2025-12-31', gegenkonto=None):
        return kreditor_ausbuchung_service.ausbuchen(
            objekt=self.objekt,
            op_nummern=[op.op_nummer for op in ops],
            gegenkonto=gegenkonto or self.gegenkonto,
            buchungsdatum=datum,
            user=self.user,
        )


class SeitenwahlTest(KreditorAusbuchungTestBase):

    def test_verbindlichkeit_kreditor_ins_soll(self):
        op = self._op('500.00')
        ergebnis = self._ausbuchen([op])

        self.assertEqual(ergebnis['anzahl'], 1)
        self.assertEqual(ergebnis['ops'][0]['art'], 'verbindlichkeit')
        b = Buchung.objects.get(beleg_referenz=f'KREDITOR-OP-AUSBUCHUNG-{op.op_nummer}')
        self.assertEqual(b.soll_konto, self._kreditorkonto())
        self.assertEqual(b.haben_konto, self.gegenkonto)
        self.assertEqual(b.betrag, Decimal('500.00'))
        self.assertEqual(b.buchungsart.nr, '056')
        self.assertEqual(b.status, 'festgeschrieben')
        self.assertEqual(b.kreditor, self.kreditor)

    def test_forderung_kreditor_ins_haben(self):
        op = self._op('142.09', urspr='-142.09')
        ergebnis = self._ausbuchen([op])

        self.assertEqual(ergebnis['ops'][0]['art'], 'forderung')
        b = Buchung.objects.get(beleg_referenz=f'KREDITOR-OP-AUSBUCHUNG-{op.op_nummer}')
        self.assertEqual(b.soll_konto, self.gegenkonto)
        self.assertEqual(b.haben_konto, self._kreditorkonto())
        # Betrag immer ohne Vorzeichen
        self.assertEqual(b.betrag, Decimal('142.09'))

    def test_gemischte_auswahl_bucht_je_posten_die_richtige_seite(self):
        verb = self._op('300.00')
        ford = self._op('50.00', urspr='-50.00')
        ergebnis = self._ausbuchen([verb, ford])

        self.assertEqual(ergebnis['anzahl'], 2)
        self.assertEqual(Decimal(ergebnis['summe']), Decimal('350.00'))
        self.assertEqual(Decimal(ergebnis['summe_verbindlichkeiten']), Decimal('300.00'))
        self.assertEqual(Decimal(ergebnis['summe_forderungen']), Decimal('50.00'))

        kk = self._kreditorkonto()
        b_verb = Buchung.objects.get(beleg_referenz=f'KREDITOR-OP-AUSBUCHUNG-{verb.op_nummer}')
        b_ford = Buchung.objects.get(beleg_referenz=f'KREDITOR-OP-AUSBUCHUNG-{ford.op_nummer}')
        self.assertEqual(b_verb.soll_konto, kk)
        self.assertEqual(b_ford.haben_konto, kk)
        # Kreditorkonto saldiert auf 300 - 50 = 250 im Soll
        soll = sum((b.betrag for b in Buchung.objects.filter(soll_konto=kk)), Decimal('0'))
        haben = sum((b.betrag for b in Buchung.objects.filter(haben_konto=kk)), Decimal('0'))
        self.assertEqual(soll - haben, Decimal('250.00'))

    def test_kein_kostenkonto_wird_geraten(self):
        """Gegenkonto ist immer genau das gewählte — nichts anderes."""
        op = self._op()
        self._ausbuchen([op])
        b = Buchung.objects.get(beleg_referenz=f'KREDITOR-OP-AUSBUCHUNG-{op.op_nummer}')
        self.assertIn(self.gegenkonto, (b.soll_konto, b.haben_konto))


class StatusUndWirkungTest(KreditorAusbuchungTestBase):

    def test_op_wird_ausgebucht_und_auf_null_gesetzt(self):
        op = self._op('500.00')
        self._ausbuchen([op])
        op.refresh_from_db()
        self.assertEqual(op.status, 'ausgebucht')
        self.assertEqual(op.betrag_offen, Decimal('0.00'))
        self.assertEqual(op.betrag_ursprung, Decimal('500.00'), 'Ursprung muss erhalten bleiben')
        self.assertEqual(op.ausgebucht_von_id, self.user.id)
        self.assertIsNotNone(op.ausgebucht_am)

    def test_ausgebuchter_op_blockiert_schritt_2_nicht_mehr(self):
        op = self._op('500.00')
        vorher = wizard_service.buchungspruefung(self.objekt, self.wj)
        self.assertTrue(vorher['blockiert'])

        self._ausbuchen([op])

        nachher = wizard_service.buchungspruefung(self.objekt, self.wj)
        self.assertFalse(nachher['blockiert'])
        self.assertEqual(nachher['kreditor_ops'], [])

    def test_ausgebuchter_op_kann_nicht_erneut_ausgebucht_werden(self):
        op = self._op('500.00')
        self._ausbuchen([op])
        with self.assertRaises(ValidationError) as ctx:
            self._ausbuchen([op])
        self.assertIn('kann nicht ausgebucht werden', ctx.exception.messages[0])
        self.assertEqual(Buchung.objects.filter(
            beleg_referenz=f'KREDITOR-OP-AUSBUCHUNG-{op.op_nummer}').count(), 1)

    def test_ausgebuchter_op_kann_nicht_vorgetragen_werden(self):
        from apps.buchhaltung.models import Jahresabrechnung
        from apps.buchhaltung.services.jahresabrechnung import kreditor_vortrag_service
        from apps.prozesse.models import Prozess
        op = self._op('500.00')
        self._ausbuchen([op])
        prozess = Prozess.objects.create(
            prozess_typ='jahresabrechnung', objekt=self.objekt,
            gestartet_von=self.user, current_step=1)
        ja = Jahresabrechnung.objects.create(
            objekt=self.objekt, wirtschaftsjahr=self.wj,
            prozess=prozess, erstellt_von=self.user)
        with self.assertRaises(ValidationError):
            kreditor_vortrag_service.vortrage_kreditor_ops(ja, [op.op_nummer], self.user)


class GuardTest(KreditorAusbuchungTestBase):

    def test_leere_auswahl(self):
        with self.assertRaises(ValidationError) as ctx:
            self._ausbuchen([])
        self.assertIn('Keine offenen Posten', ctx.exception.messages[0])

    def test_bezahlter_op_wird_abgelehnt(self):
        op = self._op('500.00', status='bezahlt')
        with self.assertRaises(ValidationError):
            self._ausbuchen([op])

    def test_op_ohne_offenen_betrag_wird_abgelehnt(self):
        op = self._op('0.00')
        with self.assertRaises(ValidationError) as ctx:
            self._ausbuchen([op])
        self.assertIn('keinen offenen Betrag', ctx.exception.messages[0])

    def test_ursprungsbetrag_null_ist_nicht_bestimmbar(self):
        op = self._op('100.00', urspr='0.00')
        with self.assertRaises(ValidationError) as ctx:
            self._ausbuchen([op])
        self.assertIn('nicht bestimmbar', ctx.exception.messages[0])

    def test_summierungskonto_wird_abgelehnt(self):
        summe = Konto.objects.create(
            wirtschaftsjahr=self.wj, kontonummer='50299',
            kontoname='Summe', kontoart='summierung')
        with self.assertRaises(ValidationError) as ctx:
            self._ausbuchen([self._op()], gegenkonto=summe)
        self.assertIn('Summierungskonto', ctx.exception.messages[0])

    def test_gegenkonto_fremdes_objekt_wird_abgelehnt(self):
        fremd = Objekt.objects.create(
            objektnummer='AB-2', objekt_typ='WEG', bezeichnung='Fremdobjekt',
            strasse='X', plz='1', ort='Y', verwaltung_seit=date(2020, 1, 1))
        fremd_wj = Wirtschaftsjahr.objects.create(
            objekt=fremd, jahr=2025, beginn_monat=1, status='offen')
        fremd_konto = Konto.objects.create(
            wirtschaftsjahr=fremd_wj, kontonummer='55900', kontoname='Fremd')
        with self.assertRaises(ValidationError) as ctx:
            self._ausbuchen([self._op()], gegenkonto=fremd_konto)
        self.assertIn('anderen Objekt', ctx.exception.messages[0])

    def test_datum_ausserhalb_des_wirtschaftsjahres(self):
        with self.assertRaises(ValidationError) as ctx:
            self._ausbuchen([self._op()], datum='2026-01-15')
        self.assertIn('außerhalb des Wirtschaftsjahres', ctx.exception.messages[0])

    def test_geschlossenes_wirtschaftsjahr(self):
        self.wj.status = 'abgeschlossen'
        self.wj.save(update_fields=['status'])
        with self.assertRaises(ValidationError) as ctx:
            self._ausbuchen([self._op()])
        self.assertIn('nicht offen', ctx.exception.messages[0])

    def test_unbekannte_op_nummer(self):
        with self.assertRaises(ValidationError) as ctx:
            kreditor_ausbuchung_service.ausbuchen(
                objekt=self.objekt, op_nummern=[123456789],
                gegenkonto=self.gegenkonto, buchungsdatum='2025-12-31',
                user=self.user)
        self.assertIn('nicht gefunden', ctx.exception.messages[0])

    def test_rollback_bei_fehler_in_der_auswahl(self):
        gut = self._op('100.00')
        schlecht = self._op('50.00', status='storniert')
        with self.assertRaises(ValidationError):
            self._ausbuchen([gut, schlecht])
        gut.refresh_from_db()
        self.assertEqual(gut.status, 'offen')
        self.assertEqual(gut.betrag_offen, Decimal('100.00'))
        self.assertFalse(Buchung.objects.filter(
            beleg_referenz__startswith='KREDITOR-OP-AUSBUCHUNG').exists())


class AusbuchungApiTest(KreditorAusbuchungTestBase):

    client_class = APIClient
    URL = '/api/v1/e-banking/kreditor-ops/ausbuchen/'

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _payload(self, ops, **extra):
        daten = {
            'objekt': str(self.objekt.id),
            'op_nummern': [op.op_nummer for op in ops],
            'gegenkonto': str(self.gegenkonto.id),
            'buchungsdatum': '2025-12-31',
        }
        daten.update(extra)
        return daten

    def test_api_bucht_aus(self):
        verb = self._op('300.00')
        ford = self._op('50.00', urspr='-50.00')
        resp = self.client.post(self.URL, self._payload([verb, ford]), format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['anzahl'], 2)
        self.assertEqual(resp.data['wirtschaftsjahr'], 2025)
        arten = {o['op_nummer']: o['art'] for o in resp.data['ops']}
        self.assertEqual(arten[verb.op_nummer], 'verbindlichkeit')
        self.assertEqual(arten[ford.op_nummer], 'forderung')

    def test_api_fehler_liefert_400(self):
        resp = self.client.post(self.URL, self._payload([], op_nummern=[]), format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('error', resp.data)

    def test_api_ungueltiges_datum_liefert_400(self):
        resp = self.client.post(
            self.URL, self._payload([self._op()], buchungsdatum='kaputt'), format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('error', resp.data)

    def test_api_unbekanntes_gegenkonto_liefert_400(self):
        import uuid
        resp = self.client.post(
            self.URL, self._payload([self._op()], gegenkonto=str(uuid.uuid4())),
            format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Gegenkonto', resp.data['error'])

    def test_op_liste_liefert_art_mit(self):
        self._op('300.00')
        self._op('50.00', urspr='-50.00')
        resp = self.client.get('/api/v1/e-banking/kreditor-ops/', {
            'objekt': str(self.objekt.id), 'kreditor': str(self.kreditor.id)})
        self.assertEqual(resp.status_code, 200)
        arten = sorted(op['art'] for op in resp.data)
        self.assertEqual(arten, ['forderung', 'verbindlichkeit'])
