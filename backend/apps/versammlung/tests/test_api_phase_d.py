"""
API-Tests für Phase D (Spec v1.1 Kap. 10.1) — Durchführung und Beschlussfassung.

Deckt ab:
  - /versammlungen/{id}/quorum/ (informativ)
  - PATCH /ev-teilnehmer/{id}/ (Anwesenheit, Vertretung, Zusage; Stimmkraft nicht setzbar)
  - /tagesordnungspunkte/{id}/abstimmung/, /einzelstimmen/, /stimmen/, /ergebnis-status/
  - /versammlungen/{id}/durchfuehrung-abschliessen/
  - /versammlungen/{id}/beschluesse-uebernehmen/, /protokoll-pdf/, /beschluesse/
  - /beschluesse/ mit Filtern, /beschluesse/{id}/anfechtung/, keine Schreibrouten
"""
import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal

from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.versammlung.models import Beschluss
from apps.versammlung.services import (
    durchfuehrung_service, ev_service, stimmkraft_service, tagesordnung_service,
)
from apps.versammlung.tests import factories as f

VERSAMMLUNGEN = '/api/v1/versammlungen/'
TOPS = '/api/v1/tagesordnungspunkte/'
TEILNEHMER = '/api/v1/ev-teilnehmer/'
BESCHLUESSE = '/api/v1/beschluesse/'

_MEDIA_TMP = tempfile.mkdtemp(prefix='immocore_test_media_ev_api_d_')


def tearDownModule():
    shutil.rmtree(_MEDIA_TMP, ignore_errors=True)


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class _Basis(APITestCase):
    def setUp(self):
        self.user = f.user()
        self.client.force_authenticate(self.user)
        self.objekt = f.objekt()
        self.objekt.betreuer = self.user
        self.objekt.save(update_fields=['betreuer'])

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
        self.teilnehmer = list(self.ev.teilnehmer.select_related('person').all())

    def _top(self, titel='TOP', **extra):
        return tagesordnung_service.top_anlegen(
            ev=self.ev, titel=titel, erstellt_von=self.user,
            beschlussvorlage=f'Wortlaut zu {titel}.', **extra,
        )

    def _alle_anwesend(self):
        for teilnehmer in self.teilnehmer:
            durchfuehrung_service.erfasse_anwesenheit(
                teilnehmer, self.user, ist_anwesend=True,
            )


class QuorumApiTest(_Basis):
    def test_quorum_ist_informativ(self):
        self._alle_anwesend()
        response = self.client.get(f'{VERSAMMLUNGEN}{self.ev.id}/quorum/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['anwesend_prozent'], Decimal('100.00'))
        self.assertNotIn('quorum_erreicht', response.data)
        self.assertIn('beschlussfähig', response.data['hinweis'])


class AnwesenheitApiTest(_Basis):
    def test_anwesenheit_setzen(self):
        teilnehmer = self.teilnehmer[0]
        response = self.client.patch(
            f'{TEILNEHMER}{teilnehmer.id}/', {'ist_anwesend': True}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data['ist_anwesend'])
        teilnehmer.refresh_from_db()
        self.assertTrue(teilnehmer.ist_anwesend)

    def test_vertretung_setzen(self):
        teilnehmer, vertreter = self.teilnehmer[0], self.teilnehmer[1]
        response = self.client.patch(f'{TEILNEHMER}{teilnehmer.id}/', {
            'ist_anwesend': True,
            'vertreten_durch': str(vertreter.person_id),
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['vertreten_durch_name'], vertreter.person.name)

    def test_selbstvertretung_400(self):
        teilnehmer = self.teilnehmer[0]
        response = self.client.patch(f'{TEILNEHMER}{teilnehmer.id}/', {
            'ist_anwesend': True,
            'vertreten_durch': str(teilnehmer.person_id),
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_zusage_erfassen(self):
        teilnehmer = self.teilnehmer[0]
        response = self.client.patch(
            f'{TEILNEHMER}{teilnehmer.id}/', {'zusage_status': 'zugesagt'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        teilnehmer.refresh_from_db()
        self.assertEqual(teilnehmer.zusage_status, 'zugesagt')
        self.assertEqual(teilnehmer.zusage_quelle, 'manuell')

    def test_stimmkraft_ist_nicht_setzbar(self):
        teilnehmer = self.teilnehmer[0]
        self.client.patch(
            f'{TEILNEHMER}{teilnehmer.id}/', {'stimmkraft': '99'}, format='json',
        )
        teilnehmer.refresh_from_db()
        self.assertEqual(teilnehmer.stimmkraft, Decimal('1'))

    def test_keine_sammelroute(self):
        # Ohne ListModelMixin registriert der Router die Sammel-URL gar nicht —
        # Teilnehmer werden über /versammlungen/{id}/teilnehmer/ gelesen und
        # ausschließlich über den Stimmkraft-Service angelegt.
        self.assertEqual(
            self.client.get(TEILNEHMER).status_code, status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.post(TEILNEHMER, {'ev': str(self.ev.id)}, format='json').status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_kein_loeschen(self):
        loeschen = self.client.delete(f'{TEILNEHMER}{self.teilnehmer[0].id}/')
        self.assertEqual(loeschen.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class AbstimmungApiTest(_Basis):
    def test_summenerfassung(self):
        self._alle_anwesend()
        top = self._top()
        response = self.client.post(f'{TOPS}{top.id}/abstimmung/', {
            'ja': '2', 'nein': '1', 'enthaltung': '0',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['abstimmungsergebnis'], 'angenommen')

    def test_summe_ueber_anwesenheit_400(self):
        durchfuehrung_service.erfasse_anwesenheit(
            self.teilnehmer[0], self.user, ist_anwesend=True,
        )
        top = self._top()
        response = self.client.post(
            f'{TOPS}{top.id}/abstimmung/', {'ja': '3', 'nein': '0'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('übersteigen', response.data['detail'])

    def test_kein_beschluss_top_400(self):
        self._alle_anwesend()
        top = tagesordnung_service.top_anlegen(
            ev=self.ev, titel='Bericht', erstellt_von=self.user,
            beschlussvorlage='', abstimmungsmodus='kein_beschluss',
        )
        response = self.client.post(
            f'{TOPS}{top.id}/abstimmung/', {'ja': '3', 'nein': '0'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_einzelstimmen_und_abruf(self):
        self._alle_anwesend()
        top = self._top()
        voten = {
            str(self.teilnehmer[0].id): 'ja',
            str(self.teilnehmer[1].id): 'ja',
            str(self.teilnehmer[2].id): 'enthaltung',
        }
        response = self.client.post(
            f'{TOPS}{top.id}/einzelstimmen/', {'voten': voten}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['abstimmungsergebnis'], 'angenommen')
        self.assertEqual(Decimal(response.data['abstimmung_enthaltung']), Decimal('1'))

        stimmen = self.client.get(f'{TOPS}{top.id}/stimmen/')
        self.assertEqual(len(stimmen.data), 3)
        self.assertIn('person_name', stimmen.data[0])

    def test_einzelstimmen_fuer_abwesende_400(self):
        durchfuehrung_service.erfasse_anwesenheit(
            self.teilnehmer[0], self.user, ist_anwesend=True,
        )
        top = self._top()
        response = self.client.post(f'{TOPS}{top.id}/einzelstimmen/', {
            'voten': {str(self.teilnehmer[1].id): 'ja'},
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_ungueltiges_votum_400(self):
        self._alle_anwesend()
        top = self._top()
        response = self.client.post(f'{TOPS}{top.id}/einzelstimmen/', {
            'voten': {str(self.teilnehmer[0].id): 'enthalten'},
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_ergebnis_status_vertagt(self):
        top = self._top()
        response = self.client.post(f'{TOPS}{top.id}/ergebnis-status/', {
            'ergebnis': 'vertagt', 'bemerkung': 'Unterlagen fehlten.',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['abstimmungsergebnis'], 'vertagt')

    def test_ergebnis_status_nur_vertagt_oder_entfallen(self):
        top = self._top()
        response = self.client.post(
            f'{TOPS}{top.id}/ergebnis-status/', {'ergebnis': 'angenommen'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_ergebnisfelder_sind_per_patch_nicht_setzbar(self):
        top = self._top()
        self.client.patch(
            f'{TOPS}{top.id}/', {'abstimmungsergebnis': 'angenommen'}, format='json',
        )
        top.refresh_from_db()
        self.assertEqual(top.abstimmungsergebnis, 'offen')


class DurchfuehrungApiTest(_Basis):
    def test_abschluss_mit_offenem_top_400(self):
        self._top()
        response = self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/durchfuehrung-abschliessen/', {},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('TOP 1', response.data['detail'])

    def test_abschluss(self):
        self._alle_anwesend()
        top = self._top()
        self.client.post(
            f'{TOPS}{top.id}/abstimmung/', {'ja': '3', 'nein': '0'}, format='json',
        )
        response = self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/durchfuehrung-abschliessen/', {},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['status'], 'durchgefuehrt')
        self.assertTrue(response.data['task_status']['task4']['erledigt'])


class BeschlussApiTest(_Basis):
    def setUp(self):
        super().setUp()
        self._alle_anwesend()
        self.top = self._top('Wirtschaftsplan 2026', triggert_wirtschaftsplan=True)
        durchfuehrung_service.erfasse_abstimmung(self.top, self.user, ja=3, nein=0)
        durchfuehrung_service.schliesse_durchfuehrung_ab(self.ev, self.user)
        self.ev.refresh_from_db()

    def test_uebernahme(self):
        response = self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/beschluesse-uebernehmen/', {}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['beschluesse'], 1)
        self.assertEqual(response.data['mit_wp_trigger'], 1)
        self.assertEqual(response.data['nummern'], [1])
        self.assertIn('protokoll_dokument_id', response.data)

    def test_uebernahme_vor_durchfuehrung_400(self):
        andere_ev = ev_service.erstelle_ev(
            objekt=self.objekt, erstellt_von=self.user, arbeitsname='Zweite EV',
        )
        response = self.client.post(
            f'{VERSAMMLUNGEN}{andere_ev.id}/beschluesse-uebernehmen/', {},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_beschluesse_der_ev(self):
        self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/beschluesse-uebernehmen/', {}, format='json',
        )
        response = self.client.get(f'{VERSAMMLUNGEN}{self.ev.id}/beschluesse/')
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['nummer'], 1)
        self.assertEqual(response.data[0]['top_nummer'], self.top.nummer)
        self.assertIsNotNone(response.data[0]['dokument_dateiname'])

    def test_protokoll_neu_erzeugen(self):
        response = self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/protokoll-pdf/', {}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(response.data['dateiname'].startswith('Protokoll_EV_'))
        self.assertIn('/api/v1/dokumente/', response.data['download_url'])

    def test_sammlung_filtert_nach_objekt(self):
        self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/beschluesse-uebernehmen/', {}, format='json',
        )
        response = self.client.get(BESCHLUESSE, {'objekt': str(self.objekt.id)})
        self.assertEqual(len(response.data), 1)

        leer = self.client.get(BESCHLUESSE, {'objekt': str(f.objekt().id)})
        self.assertEqual(len(leer.data), 0)

    def test_sammlung_filtert_nach_jahr_und_anfechtung(self):
        self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/beschluesse-uebernehmen/', {}, format='json',
        )
        jahr = self.ev.termin.year
        self.assertEqual(len(self.client.get(BESCHLUESSE, {'jahr': str(jahr)}).data), 1)
        self.assertEqual(len(self.client.get(BESCHLUESSE, {'jahr': '1999'}).data), 0)
        self.assertEqual(
            len(self.client.get(BESCHLUESSE, {'anfechtung_status': 'keine'}).data), 1,
        )

    def test_anfechtung_vermerken(self):
        self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/beschluesse-uebernehmen/', {}, format='json',
        )
        beschluss = Beschluss.objects.get(ev=self.ev)
        response = self.client.post(f'{BESCHLUESSE}{beschluss.id}/anfechtung/', {
            'anfechtung_status': 'anhaengig', 'notiz': 'AG Frankfurt 2 C 123/26',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['anfechtung_status'], 'anhaengig')

    def test_aufhebung_ohne_datum_400(self):
        self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/beschluesse-uebernehmen/', {}, format='json',
        )
        beschluss = Beschluss.objects.get(ev=self.ev)
        response = self.client.post(
            f'{BESCHLUESSE}{beschluss.id}/anfechtung/',
            {'anfechtung_status': 'aufgehoben'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_keine_schreibrouten_auf_beschluessen(self):
        self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/beschluesse-uebernehmen/', {}, format='json',
        )
        beschluss = Beschluss.objects.get(ev=self.ev)
        self.assertEqual(
            self.client.post(BESCHLUESSE, {}, format='json').status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.delete(f'{BESCHLUESSE}{beschluss.id}/').status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        # Wortlaut ist auch über PATCH nicht änderbar (read_only im Serializer).
        self.assertEqual(
            self.client.patch(
                f'{BESCHLUESSE}{beschluss.id}/', {'wortlaut': 'Anders.'},
                format='json',
            ).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_ohne_login_kein_zugriff(self):
        self.client.force_authenticate(None)
        response = self.client.get(BESCHLUESSE)
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )
