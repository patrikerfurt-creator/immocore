"""
API-Tests für das EV-Modul (Spec v1.1 Kap. 10.1, Phase B).

Deckt ab:
  - /versammlungen/: Anlage (inkl. Ablehnung von Nicht-WEG), Liste mit Filtern,
    Detail mit Task-Status und Ladungsfrist, PATCH (Termin über den Service)
  - Task-Aktionen: task-erledigt, task-zuruecksetzen, ereignisse
  - /tagesordnungspunkte/: Anlage mit Nummernvergabe, Einfügen, PATCH, DELETE,
    Sperre nach Einladungsversand, Nummer nicht direkt änderbar
  - teilnehmer-ermitteln / teilnehmer
  - einladung-pdf, versandplan, einladungen-versenden (sofort und asynchron),
    versandprotokoll
  - Authentifizierung: ohne Login 401
"""
import shutil
import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.versammlung.models import Eigentuemerversammlung, Tagesordnungspunkt
from apps.versammlung.services import (
    einladung_service, ev_service, stimmkraft_service, tagesordnung_service,
)
from apps.versammlung.tests import factories as f

VERSAMMLUNGEN = '/api/v1/versammlungen/'
TOPS = '/api/v1/tagesordnungspunkte/'

_MEDIA_TMP = tempfile.mkdtemp(prefix='immocore_test_media_ev_api_')


def tearDownModule():
    shutil.rmtree(_MEDIA_TMP, ignore_errors=True)


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class ZugriffTest(APITestCase):
    def test_ohne_login_kein_zugriff(self):
        response = self.client.get(VERSAMMLUNGEN)
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class AnlageUndListeTest(APITestCase):
    def setUp(self):
        self.user = f.user()
        self.client.force_authenticate(self.user)
        self.objekt = f.objekt(bezeichnung='WEG API-Test')

    def test_anlage(self):
        response = self.client.post(VERSAMMLUNGEN, {
            'objekt': str(self.objekt.id),
            'arbeitsname': 'EV 2026',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['status'], 'entwurf')
        # Default ist der gesetzliche Regelfall.
        self.assertEqual(response.data['stimmprinzip'], 'kopf')
        self.assertEqual(response.data['task_status']['anzahl_erledigt'], 0)
        self.assertTrue(response.data['einladungstext'])

    def test_erstellt_von_ist_request_user(self):
        response = self.client.post(
            VERSAMMLUNGEN, {'objekt': str(self.objekt.id)}, format='json',
        )
        ev = Eigentuemerversammlung.objects.get(pk=response.data['id'])
        self.assertEqual(ev.erstellt_von, self.user)

    def test_anlage_mit_verteilerschluessel(self):
        einheit = f.einheit(self.objekt, nr='001')
        vs = f.einheiten_schluessel(self.objekt, [einheit])
        response = self.client.post(VERSAMMLUNGEN, {
            'objekt': str(self.objekt.id),
            'stimmprinzip': 'verteilerschluessel',
            'stimm_verteilerschluessel': str(vs.id),
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['stimmprinzip'], 'verteilerschluessel')
        self.assertEqual(
            response.data['stimm_verteilerschluessel_text'],
            '030 Anzahl Einheiten Gesamt',
        )

    def test_anlage_mit_prinzip_ohne_schluessel_400(self):
        response = self.client.post(VERSAMMLUNGEN, {
            'objekt': str(self.objekt.id),
            'stimmprinzip': 'verteilerschluessel',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Verteilerschlüssel', response.data['detail'])

    def test_anlage_fuer_sev_wird_abgelehnt(self):
        response = self.client.post(
            VERSAMMLUNGEN, {'objekt': str(f.objekt(typ='SEV').id)}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('WEG-Objekte', response.data['detail'])

    def test_liste_filtert_nach_objekt_und_status(self):
        ev_service.erstelle_ev(objekt=self.objekt, erstellt_von=self.user)
        anderes = f.objekt(bezeichnung='WEG Zweitobjekt')
        ev_service.erstelle_ev(objekt=anderes, erstellt_von=self.user)

        response = self.client.get(VERSAMMLUNGEN, {'objekt': str(self.objekt.id)})
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['objekt'], self.objekt.id)

        response = self.client.get(VERSAMMLUNGEN, {'status': 'durchgefuehrt'})
        self.assertEqual(len(response.data), 0)

    def test_liste_filtert_nach_jahr(self):
        ev = ev_service.erstelle_ev(objekt=self.objekt, erstellt_von=self.user)
        termin = timezone.now() + timedelta(days=30)
        ev_service.aktualisiere_terminierung(ev, self.user, termin=termin, ort='Saal')

        response = self.client.get(VERSAMMLUNGEN, {'jahr': str(termin.year)})
        self.assertEqual(len(response.data), 1)
        response = self.client.get(VERSAMMLUNGEN, {'jahr': '1999'})
        self.assertEqual(len(response.data), 0)

    def test_detail_enthaelt_ladungsfrist(self):
        ev = ev_service.erstelle_ev(objekt=self.objekt, erstellt_von=self.user)
        ev_service.aktualisiere_terminierung(
            ev, self.user, termin=timezone.now() + timedelta(days=5), ort='Saal',
        )
        response = self.client.get(f'{VERSAMMLUNGEN}{ev.id}/')
        self.assertFalse(response.data['ladungsfrist']['eingehalten'])
        self.assertIn('§ 24 Abs. 4 WEG', response.data['ladungsfrist']['warnung'])

    def test_kein_loeschen(self):
        ev = ev_service.erstelle_ev(objekt=self.objekt, erstellt_von=self.user)
        response = self.client.delete(f'{VERSAMMLUNGEN}{ev.id}/')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class TerminierungApiTest(APITestCase):
    def setUp(self):
        self.user = f.user()
        self.client.force_authenticate(self.user)
        self.ev = ev_service.erstelle_ev(objekt=f.objekt(), erstellt_von=self.user)

    def test_patch_setzt_termin_und_protokolliert(self):
        termin = (timezone.now() + timedelta(days=30)).replace(microsecond=0)
        response = self.client.patch(f'{VERSAMMLUNGEN}{self.ev.id}/', {
            'termin': termin.isoformat(),
            'ort': 'Gemeinschaftsraum EG',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.ort, 'Gemeinschaftsraum EG')
        self.assertTrue(self.ev.ereignisse.filter(typ='termin_geaendert').exists())

    def test_patch_setzt_stammfelder(self):
        response = self.client.patch(f'{VERSAMMLUNGEN}{self.ev.id}/', {
            'arbeitsname': 'Neuer Name',
            'versammlungsleiter': 'Frau Demme',
            'protokollfuehrer': 'Herr Maurer',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.arbeitsname, 'Neuer Name')
        self.assertEqual(self.ev.versammlungsleiter, 'Frau Demme')
        self.assertEqual(self.ev.protokollfuehrer, 'Herr Maurer')

    def test_status_ist_per_patch_nicht_setzbar(self):
        self.client.patch(
            f'{VERSAMMLUNGEN}{self.ev.id}/', {'status': 'durchgefuehrt'}, format='json',
        )
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.status, 'entwurf')


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class TaskAktionenTest(APITestCase):
    def setUp(self):
        self.user = f.user()
        self.client.force_authenticate(self.user)
        self.ev = ev_service.erstelle_ev(objekt=f.objekt(), erstellt_von=self.user)

    def test_task_erledigt_ohne_termin_400(self):
        response = self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/task-erledigt/', {'task_nr': 1}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Termin', response.data['detail'])

    def test_task_erledigt(self):
        ev_service.aktualisiere_terminierung(
            self.ev, self.user, termin=timezone.now() + timedelta(days=30), ort='Saal',
        )
        response = self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/task-erledigt/', {'task_nr': 1}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data['task_status']['task1']['erledigt'])
        self.assertEqual(response.data['status'], 'in_bearbeitung')

    def test_task_nr_fehlt(self):
        response = self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/task-erledigt/', {}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_task_zuruecksetzen_ohne_grund_400(self):
        self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/task-erledigt/', {'task_nr': 3}, format='json',
        )
        response = self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/task-zuruecksetzen/',
            {'task_nr': 3}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_task_zuruecksetzen_mit_grund(self):
        self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/task-erledigt/', {'task_nr': 3}, format='json',
        )
        response = self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/task-zuruecksetzen/',
            {'task_nr': 3, 'grund': 'Anlage fehlte'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['task_status']['task3']['erledigt'])

    def test_ereignisse_listet_audit_verlauf(self):
        response = self.client.get(f'{VERSAMMLUNGEN}{self.ev.id}/ereignisse/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]['typ'], 'erstellt')
        self.assertEqual(response.data[0]['erstellt_von_name'], self.user.get_username())


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class TagesordnungApiTest(APITestCase):
    def setUp(self):
        self.user = f.user()
        self.client.force_authenticate(self.user)
        self.ev = ev_service.erstelle_ev(objekt=f.objekt(), erstellt_von=self.user)

    def _anlegen(self, titel, **extra):
        daten = {
            'ev': str(self.ev.id), 'titel': titel,
            'beschlussvorlage': 'Es wird beschlossen.',
        }
        daten.update(extra)
        return self.client.post(TOPS, daten, format='json')

    def test_anlage_vergibt_nummer(self):
        self.assertEqual(self._anlegen('Erster').data['nummer'], 1)
        self.assertEqual(self._anlegen('Zweiter').data['nummer'], 2)

    def test_anlage_ohne_beschlussvorlage_400(self):
        response = self.client.post(TOPS, {
            'ev': str(self.ev.id), 'titel': 'Ohne Vorlage',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Beschlussvorlage', str(response.data))

    def test_qualifizierte_mehrheit_ohne_schwelle_400(self):
        response = self._anlegen(
            'Sanierung', abstimmungsmodus='qualifizierte_mehrheit',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_einfuegen_mit_position(self):
        self._anlegen('Erster')
        self._anlegen('Zweiter')
        response = self._anlegen('Eingeschoben', nummer=2)
        self.assertEqual(response.data['nummer'], 2)
        titel = list(
            self.ev.tagesordnung.order_by('nummer').values_list('titel', flat=True)
        )
        self.assertEqual(titel, ['Erster', 'Eingeschoben', 'Zweiter'])

    def test_liste_filtert_nach_ev(self):
        self._anlegen('Erster')
        andere_ev = ev_service.erstelle_ev(objekt=f.objekt(), erstellt_von=self.user)
        tagesordnung_service.top_anlegen(
            ev=andere_ev, titel='Fremder', erstellt_von=self.user,
            beschlussvorlage='Text.',
        )
        response = self.client.get(TOPS, {'ev': str(self.ev.id)})
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['titel'], 'Erster')

    def test_patch_aendert_titel(self):
        top_id = self._anlegen('Alter Titel').data['id']
        response = self.client.patch(
            f'{TOPS}{top_id}/', {'titel': 'Neuer Titel'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['titel'], 'Neuer Titel')

    def test_nummer_ist_nicht_direkt_aenderbar(self):
        top_id = self._anlegen('Erster').data['id']
        response = self.client.patch(f'{TOPS}{top_id}/', {'nummer': 5}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Tagesordnungspunkt.objects.get(pk=top_id).nummer, 1)

    def test_delete_schliesst_luecke(self):
        erster = self._anlegen('Erster').data['id']
        self._anlegen('Zweiter')
        response = self.client.delete(f'{TOPS}{erster}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        nummern = list(
            self.ev.tagesordnung.order_by('nummer').values_list('nummer', flat=True)
        )
        self.assertEqual(nummern, [1])

    def test_sperre_nach_versand(self):
        top_id = self._anlegen('Erster').data['id']
        ev_service.wechsle_status(self.ev, 'in_bearbeitung', self.user)
        ev_service.wechsle_status(self.ev, 'einladungen_versendet', self.user)

        self.assertEqual(
            self._anlegen('Nachtrag').status_code, status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            self.client.delete(f'{TOPS}{top_id}/').status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        gesperrt = self.client.patch(
            f'{TOPS}{top_id}/', {'beschlussvorlage': 'Anders.'}, format='json',
        )
        self.assertEqual(gesperrt.status_code, status.HTTP_400_BAD_REQUEST)
        erlaubt = self.client.patch(
            f'{TOPS}{top_id}/', {'erlaeuterung': 'Zusatz'}, format='json',
        )
        self.assertEqual(erlaubt.status_code, status.HTTP_200_OK)

    def test_tagesordnung_action_liefert_probleme(self):
        response = self.client.get(f'{VERSAMMLUNGEN}{self.ev.id}/tagesordnung/')
        self.assertEqual(response.data['tagesordnung'], [])
        self.assertIn('keinen Punkt', response.data['probleme'][0])


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class TeilnehmerApiTest(APITestCase):
    def setUp(self):
        self.user = f.user()
        self.client.force_authenticate(self.user)
        self.objekt = f.objekt()
        self.ev = ev_service.erstelle_ev(objekt=self.objekt, erstellt_von=self.user)

    def test_ermitteln_ohne_eigentuemer_400(self):
        response = self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/teilnehmer-ermitteln/', {}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Eigentumsverhältnisse', response.data['detail'])

    def test_ermitteln_und_liste(self):
        f.eigentuemer(self.objekt, f.person(nachname='Alpha'), nr='001')
        f.eigentuemer(self.objekt, f.person(nachname='Beta'), nr='002')

        response = self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/teilnehmer-ermitteln/', {}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['teilnehmer'], 2)

        liste = self.client.get(f'{VERSAMMLUNGEN}{self.ev.id}/teilnehmer/')
        self.assertEqual(len(liste.data), 2)
        self.assertEqual(liste.data[0]['person_name'], 'Max Alpha')
        self.assertEqual(len(liste.data[0]['anteile']), 1)

    def test_schluessel_ohne_werte_400(self):
        einheit, _ = f.eigentuemer(self.objekt, nr='001')
        vs = f.mea_schluessel(self.objekt, {einheit: None})
        self.ev.stimmprinzip = 'verteilerschluessel'
        self.ev.stimm_verteilerschluessel = vs
        self.ev.save(update_fields=['stimmprinzip', 'stimm_verteilerschluessel'])

        response = self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/teilnehmer-ermitteln/', {}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('fehlen Werte', response.data['detail'])

    def test_einheit_ohne_eigentuemer_400(self):
        einheit, _ = f.eigentuemer(self.objekt, nr='001')
        verwaist = f.einheit(self.objekt, nr='002')
        vs = f.einheiten_schluessel(self.objekt, [einheit, verwaist])
        self.ev.stimmprinzip = 'verteilerschluessel'
        self.ev.stimm_verteilerschluessel = vs
        self.ev.save(update_fields=['stimmprinzip', 'stimm_verteilerschluessel'])

        response = self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/teilnehmer-ermitteln/', {}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('keinen aktiven Eigentümer', response.data['detail'])


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class EinladungApiTest(APITestCase):
    def setUp(self):
        self.user = f.user()
        self.client.force_authenticate(self.user)
        self.objekt = f.objekt()
        self.ev = ev_service.erstelle_ev(objekt=self.objekt, erstellt_von=self.user)
        ev_service.aktualisiere_terminierung(
            self.ev, self.user,
            termin=timezone.now() + timedelta(days=30), ort='Gemeinschaftsraum',
        )
        tagesordnung_service.top_anlegen(
            ev=self.ev, titel='Jahresabrechnung', erstellt_von=self.user,
            beschlussvorlage='Die Jahresabrechnung wird beschlossen.',
        )
        person = f.person(nachname='Mailempfaenger')
        person.emails = ['mail@example.org']
        person.save(update_fields=['emails'])
        f.eigentuemer(self.objekt, person, nr='001')
        stimmkraft_service.ermittle_teilnehmer(self.ev, self.user)
        self.person = person

    def test_pdf_erzeugen(self):
        response = self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/einladung-pdf/', {}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(response.data['dateiname'].endswith('.pdf'))
        self.assertIn('/api/v1/dokumente/', response.data['download_url'])
        self.ev.refresh_from_db()
        self.assertIsNotNone(self.ev.einladungs_pdf_id)

    def test_anlagen_ids_muss_liste_sein(self):
        response = self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/einladung-pdf/',
            {'anlagen_ids': 'keine-liste'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_versandplan(self):
        response = self.client.get(f'{VERSAMMLUNGEN}{self.ev.id}/versandplan/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['anzahl'], 1)
        self.assertEqual(response.data['eintraege'][0]['kanal'], 'email')
        self.assertFalse(response.data['portal_verfuegbar'])

    def test_versand_ohne_pdf_400(self):
        response = self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/einladungen-versenden/', {}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_versand_sofort(self):
        einladung_service.erzeuge_einladungs_pdf(self.ev, self.user)
        response = self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/einladungen-versenden/',
            {'sofort': True}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['erfolgreich'], 1)
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.status, 'einladungen_versendet')

    def test_versand_asynchron_beauftragt_task(self):
        einladung_service.erzeuge_einladungs_pdf(self.ev, self.user)
        # Der Versand wird über transaction.on_commit beauftragt — in einer
        # TestCase-Transaktion feuern diese Callbacks nur innerhalb von
        # captureOnCommitCallbacks(execute=True).
        with patch('apps.versammlung.tasks.versende_ev_einladungen.delay') as delay:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    f'{VERSAMMLUNGEN}{self.ev.id}/einladungen-versenden/',
                    {}, format='json',
                )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED, response.data)
        self.assertEqual(response.data['anzahl_empfaenger'], 1)
        delay.assert_called_once()
        self.assertEqual(delay.call_args[0][0], str(self.ev.id))

    def test_plan_muss_objekt_sein(self):
        einladung_service.erzeuge_einladungs_pdf(self.ev, self.user)
        response = self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/einladungen-versenden/',
            {'plan': ['liste']}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_versandprotokoll(self):
        einladung_service.erzeuge_einladungs_pdf(self.ev, self.user)
        einladung_service.versende_einladungen(self.ev, self.user)
        response = self.client.get(f'{VERSAMMLUNGEN}{self.ev.id}/versandprotokoll/')
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['kanal'], 'email')
        self.assertEqual(response.data[0]['status'], 'erfolgreich')
        self.assertEqual(response.data[0]['person_name'], 'Max Mailempfaenger')
