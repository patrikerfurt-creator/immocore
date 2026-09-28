"""
Tests für ``apps.versammlung.services.checkout_service``
(Spec v1.1 Kap. 4, ersetzt Task 4+5 — Checkout/Checkout-Rücknahme/Abschluss/
Protokoll-Upload) inkl. der zugehörigen API-Endpunkte.

Deckt ab:
  - checkout: Voraussetzungen (Tagesordnung vollständig, Stimmgrundlage je
    TOP), Statuswechsel, Task4, EVEreignis
  - checkout_zuruecknehmen: Grund ist Pflicht, Statuswechsel zurück
  - abschluss: Voraussetzung Status "ausgecheckt", offene TOPs blockieren,
    Beschlussnummern in der Response, KEIN Statuswechsel, KEIN eigenes
    Protokoll
  - protokoll_upload: Reihenfolge (erst abschluss), PDF-Validierung
    (Magic-Bytes, Größe), Statuswechsel auf beschluesse_verarbeitet
  - API: PATCH /ev-teilnehmer/ und POST einzelstimmen/ nur im Status
    "ausgecheckt" (siehe auch test_api_phase_d.py)
"""
import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.versammlung.models import Beschluss
from apps.versammlung.services import (
    checkout_service, durchfuehrung_service, ev_service, stimmkraft_service,
    tagesordnung_service,
)
from apps.versammlung.tests import factories as f

VERSAMMLUNGEN = '/api/v1/versammlungen/'

_MEDIA_TMP = tempfile.mkdtemp(prefix='immocore_test_media_ev_checkout_')


def tearDownModule():
    shutil.rmtree(_MEDIA_TMP, ignore_errors=True)


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class _Basis(TestCase):
    def setUp(self):
        self.user = f.user()
        self.objekt = f.objekt()
        einheiten = [
            f.eigentuemer(self.objekt, nr=f'{index:03d}')[0]
            for index in range(1, 4)
        ]
        self.vs = f.einheiten_schluessel(self.objekt, einheiten)
        self.ev = ev_service.erstelle_ev(
            objekt=self.objekt, erstellt_von=self.user,
            stimmprinzip='verteilerschluessel', stimm_verteilerschluessel=self.vs,
        )
        ev_service.aktualisiere_terminierung(
            self.ev, self.user,
            termin=timezone.now() - timedelta(hours=2), ort='Gemeinschaftsraum',
        )
        stimmkraft_service.ermittle_teilnehmer(self.ev, self.user)

    def _top(self, titel='TOP', **extra):
        return tagesordnung_service.top_anlegen(
            ev=self.ev, titel=titel, erstellt_von=self.user,
            beschlussvorlage=f'Wortlaut zu {titel}.', **extra,
        )

    def _checkout(self):
        checkout_service.checkout(self.ev, self.user)
        self.ev.refresh_from_db()


class CheckoutTest(_Basis):
    def test_ohne_tagesordnung_400(self):
        with self.assertRaises(ValidationError) as ctx:
            checkout_service.checkout(self.ev, self.user)
        self.assertIn('keinen Punkt', str(ctx.exception))

    def test_top_ohne_stimmgrundlage_400(self):
        top = self._top()
        top.stimmgrundlage = None
        top.save(update_fields=['stimmgrundlage'])
        with self.assertRaises(ValidationError) as ctx:
            checkout_service.checkout(self.ev, self.user)
        self.assertIn('Stimmgrundlage', str(ctx.exception))

    def test_kein_beschluss_top_braucht_keine_stimmgrundlage(self):
        top = tagesordnung_service.top_anlegen(
            ev=self.ev, titel='Bericht', erstellt_von=self.user,
            beschlussvorlage='', abstimmungsmodus='kein_beschluss',
        )
        top.stimmgrundlage = None
        top.save(update_fields=['stimmgrundlage'])
        checkout_service.checkout(self.ev, self.user)
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.status, 'ausgecheckt')

    def test_erfolgreicher_checkout(self):
        self._top()
        checkout_service.checkout(self.ev, self.user)
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.status, 'ausgecheckt')
        self.assertTrue(self.ev.task4_durchfuehrung_erledigt)
        self.assertTrue(self.ev.ereignisse.filter(typ='checkout').exists())

    def test_top_anlegen_nach_checkout_gesperrt(self):
        self._top()
        self._checkout()
        with self.assertRaises(ValidationError):
            tagesordnung_service.top_anlegen(
                ev=self.ev, titel='Nachtrag', erstellt_von=self.user,
                beschlussvorlage='Text.',
            )


class CheckoutZuruecknahmeTest(_Basis):
    def setUp(self):
        super().setUp()
        self._top()
        self._checkout()

    def test_grund_ist_pflicht(self):
        with self.assertRaises(ValidationError):
            checkout_service.checkout_zuruecknehmen(self.ev, self.user, '  ')

    def test_rueckname_setzt_status_zurueck(self):
        checkout_service.checkout_zuruecknehmen(
            self.ev, self.user, 'Termin verschoben.',
        )
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.status, 'einladungen_versendet')
        self.assertFalse(self.ev.task4_durchfuehrung_erledigt)
        ereignis = self.ev.ereignisse.get(typ='checkout_zurueckgenommen')
        self.assertIn('Termin verschoben', ereignis.text)

    def test_top_anlegen_nach_ruecknahme_wieder_gesperrt(self):
        # Zurück ist 'einladungen_versendet' — TOPs bleiben gesperrt
        # (§ 23 Abs. 2 WEG), nur eine erneute Checkout-Rücknahme ändert das
        # nicht: eine neue Tagesordnung braucht eine neue Einladung.
        checkout_service.checkout_zuruecknehmen(self.ev, self.user, 'Grund')
        with self.assertRaises(ValidationError):
            tagesordnung_service.top_anlegen(
                ev=self.ev, titel='Nachtrag', erstellt_von=self.user,
                beschlussvorlage='Text.',
            )

    def test_erneuter_checkout_nach_ruecknahme(self):
        checkout_service.checkout_zuruecknehmen(self.ev, self.user, 'Grund')
        checkout_service.checkout(self.ev, self.user)
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.status, 'ausgecheckt')


class AbschlussTest(_Basis):
    def setUp(self):
        super().setUp()
        self.top = self._top(titel='Jahresabrechnung')
        self._checkout()
        for teilnehmer in self.ev.teilnehmer.all():
            durchfuehrung_service.erfasse_anwesenheit(
                teilnehmer, self.user, ist_anwesend=True,
            )

    def test_vor_checkout_nicht_moeglich(self):
        andere = ev_service.erstelle_ev(objekt=self.objekt, erstellt_von=self.user)
        with self.assertRaises(ValidationError) as ctx:
            checkout_service.abschluss(andere, self.user)
        self.assertIn('ausgecheckt', str(ctx.exception))

    def test_offene_tops_blockieren(self):
        with self.assertRaises(ValidationError) as ctx:
            checkout_service.abschluss(self.ev, self.user)
        self.assertIn('TOP 1', str(ctx.exception))

    def test_abschluss_liefert_beschlussnummern(self):
        durchfuehrung_service.erfasse_abstimmung(self.top, self.user, ja=3, nein=0)
        ergebnis = checkout_service.abschluss(self.ev, self.user)

        self.assertEqual(len(ergebnis['beschluesse']), 1)
        eintrag = ergebnis['beschluesse'][0]
        self.assertEqual(eintrag['top_id'], str(self.top.id))
        self.assertEqual(eintrag['beschluss_nummer'], 1)
        self.assertEqual(eintrag['wortlaut'], self.top.beschlussvorlage)

    def test_abschluss_wechselt_status_nicht(self):
        durchfuehrung_service.erfasse_abstimmung(self.top, self.user, ja=3, nein=0)
        checkout_service.abschluss(self.ev, self.user)
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.status, 'ausgecheckt')
        self.assertIsNotNone(self.ev.abschluss_erledigt_am)
        self.assertIsNone(self.ev.protokoll_pdf_id)

    def test_abschluss_ist_idempotent(self):
        durchfuehrung_service.erfasse_abstimmung(self.top, self.user, ja=3, nein=0)
        checkout_service.abschluss(self.ev, self.user)
        zweiter = checkout_service.abschluss(self.ev, self.user)
        self.assertEqual(len(zweiter['beschluesse']), 1)
        self.assertEqual(Beschluss.objects.filter(ev=self.ev).count(), 1)


class ProtokollUploadTest(_Basis):
    def setUp(self):
        super().setUp()
        self.top = self._top(titel='Jahresabrechnung')
        self._checkout()
        for teilnehmer in self.ev.teilnehmer.all():
            durchfuehrung_service.erfasse_anwesenheit(
                teilnehmer, self.user, ist_anwesend=True,
            )
        durchfuehrung_service.erfasse_abstimmung(self.top, self.user, ja=3, nein=0)

    def _pdf(self, inhalt=b'%PDF-1.4 Testinhalt'):
        from django.core.files.base import ContentFile

        return ContentFile(inhalt, name='protokoll.pdf')

    def test_ohne_abschluss_400(self):
        with self.assertRaises(ValidationError) as ctx:
            checkout_service.protokoll_upload(self.ev, self.user, self._pdf())
        self.assertIn('Abschluss', str(ctx.exception))

    def test_kein_echtes_pdf_400(self):
        checkout_service.abschluss(self.ev, self.user)
        with self.assertRaises(ValidationError) as ctx:
            checkout_service.protokoll_upload(
                self.ev, self.user, self._pdf(b'Kein PDF, nur Text.'),
            )
        self.assertIn('PDF', str(ctx.exception))

    def test_zu_gross_400(self):
        checkout_service.abschluss(self.ev, self.user)
        zu_gross = b'%PDF-1.4' + b'0' * (checkout_service.MAX_PROTOKOLL_BYTES + 1)
        with self.assertRaises(ValidationError) as ctx:
            checkout_service.protokoll_upload(self.ev, self.user, self._pdf(zu_gross))
        self.assertIn('zu groß', str(ctx.exception))

    def test_erfolgreicher_upload(self):
        checkout_service.abschluss(self.ev, self.user)
        dokument = checkout_service.protokoll_upload(self.ev, self.user, self._pdf())

        self.assertEqual(dokument.dokument_typ, 'korrespondenz')
        self.assertTrue(dokument.revisionssicher)
        self.assertIsNotNone(dokument.sha256)
        self.assertEqual(dokument.objekt_id, self.objekt.id)

        self.ev.refresh_from_db()
        self.assertEqual(self.ev.status, 'beschluesse_verarbeitet')
        self.assertEqual(self.ev.protokoll_pdf_id, dokument.id)
        self.assertTrue(
            self.ev.ereignisse.filter(typ='protokoll_hochgeladen').exists()
        )


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class CheckoutApiTest(APITestCase):
    def setUp(self):
        self.user = f.user()
        self.client.force_authenticate(self.user)
        self.objekt = f.objekt()
        einheiten = [
            f.eigentuemer(self.objekt, nr=f'{index:03d}')[0]
            for index in range(1, 4)
        ]
        self.vs = f.einheiten_schluessel(self.objekt, einheiten)
        self.ev = ev_service.erstelle_ev(
            objekt=self.objekt, erstellt_von=self.user,
            stimmprinzip='verteilerschluessel', stimm_verteilerschluessel=self.vs,
        )
        ev_service.aktualisiere_terminierung(
            self.ev, self.user,
            termin=timezone.now() - timedelta(hours=2), ort='Gemeinschaftsraum',
        )
        stimmkraft_service.ermittle_teilnehmer(self.ev, self.user)
        self.top = tagesordnung_service.top_anlegen(
            ev=self.ev, titel='Jahresabrechnung', erstellt_von=self.user,
            beschlussvorlage='Die Jahresabrechnung wird beschlossen.',
        )

    def test_checkout_ueber_api(self):
        response = self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/checkout/', {}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['status'], 'ausgecheckt')

    def test_checkout_zuruecknehmen_ohne_grund_400(self):
        self.client.post(f'{VERSAMMLUNGEN}{self.ev.id}/checkout/', {}, format='json')
        response = self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/checkout-zuruecknehmen/', {}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_vollstaendiger_ablauf_bis_protokoll_upload(self):
        self.client.post(f'{VERSAMMLUNGEN}{self.ev.id}/checkout/', {}, format='json')

        for teilnehmer in self.ev.teilnehmer.all():
            durchfuehrung_service.erfasse_anwesenheit(
                teilnehmer, self.user, ist_anwesend=True,
            )

        einzel = self.client.post(
            f'/api/v1/tagesordnungspunkte/{self.top.id}/einzelstimmen/',
            {'voten': {
                str(t.id): 'ja' for t in self.ev.teilnehmer.all()
            }}, format='json',
        )
        self.assertEqual(einzel.status_code, status.HTTP_200_OK, einzel.data)

        abschluss = self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/abschluss/', {}, format='json',
        )
        self.assertEqual(abschluss.status_code, status.HTTP_200_OK, abschluss.data)
        self.assertEqual(len(abschluss.data['beschluesse']), 1)

        datei = SimpleUploadedFile(
            'protokoll.pdf', b'%PDF-1.4 Inhalt', content_type='application/pdf',
        )
        upload = self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/protokoll-upload/',
            {'datei': datei}, format='multipart',
        )
        self.assertEqual(upload.status_code, status.HTTP_201_CREATED, upload.data)
        self.assertIn('dokument_id', upload.data)

        self.ev.refresh_from_db()
        self.assertEqual(self.ev.status, 'beschluesse_verarbeitet')

    def test_protokoll_upload_ohne_datei_400(self):
        self.client.post(f'{VERSAMMLUNGEN}{self.ev.id}/checkout/', {}, format='json')
        response = self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/protokoll-upload/', {}, format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
