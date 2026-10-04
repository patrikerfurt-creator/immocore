"""Nacharbeiten Korrespondenz-API: Druckstapel lesen, ``vorlage_version`` im Schreiben-Detail,
Serienlauf-Abbruch."""
from django.core.exceptions import ValidationError

from apps.korrespondenz.models import Schreiben, Serienlauf
from apps.korrespondenz.services import schreiben_service, serienlauf_service

from . import fixtures
from .test_api_versand import BASIS, ApiBasis
from .basis_versand import neue_einheit, neue_person, neues_ev

NULL_ID = '00000000-0000-0000-0000-000000000000'


class DruckstapelLesenTest(ApiBasis):

    def stapel(self, **kw):
        """Ein freigegebenes Brief-Schreiben -> Druckstapel."""
        sid = self.erstelle_id(**kw)
        self.client.post(BASIS + f'schreiben/{sid}/freigeben/')
        self.client.post(BASIS + f'schreiben/{sid}/versenden/')
        antwort = self.client.post(BASIS + 'druckstapel/', {'schreiben_ids': [sid]}, format='json')
        self.assertEqual(antwort.status_code, 201, antwort.content)
        return antwort.json()['id'], sid

    def test_ohne_anmeldung(self):
        from rest_framework.test import APIClient
        anonym = APIClient()
        self.assertEqual(anonym.get(BASIS + 'druckstapel/').status_code, 401)
        self.assertEqual(anonym.get(BASIS + f'druckstapel/{NULL_ID}/').status_code, 401)

    def test_liste_und_detail(self):
        stapel_id, sid = self.stapel()
        liste = self.client.get(BASIS + 'druckstapel/')
        self.assertEqual(liste.status_code, 200, liste.content)
        self.assertEqual([d['id'] for d in liste.json()], [stapel_id])
        eintrag = liste.json()[0]
        self.assertEqual(eintrag['status'], 'offen')
        self.assertEqual(eintrag['anzahl'], 1)

        detail = self.client.get(BASIS + f'druckstapel/{stapel_id}/')
        self.assertEqual(detail.status_code, 200, detail.content)
        daten = detail.json()
        self.assertEqual(daten['anzahl'], 1)
        self.assertIsNotNone(daten['dokument'])
        self.assertEqual(daten['dokument_info']['id'], str(daten['dokument']))
        self.assertTrue(daten['dokument_info']['dateiname'])
        self.assertEqual(len(daten['schreiben']), 1)
        s = daten['schreiben'][0]
        self.assertEqual(s['id'], sid)
        self.assertEqual(s['empfaenger']['id'], str(self.s.person.pk))
        self.assertEqual(s['objekt']['id'], str(self.s.objekt.pk))

    def test_unbekannter_stapel(self):
        self.assertEqual(self.client.get(BASIS + f'druckstapel/{NULL_ID}/').status_code, 404)

    def test_filter_status(self):
        offen_id, _ = self.stapel()
        fertig_id, _ = self.stapel()
        self.client.post(BASIS + f'druckstapel/{fertig_id}/bestaetigen/')

        def ids(query):
            antwort = self.client.get(BASIS + 'druckstapel/' + query)
            self.assertEqual(antwort.status_code, 200, antwort.content)
            return {d['id'] for d in antwort.json()}

        self.assertEqual(ids(''), {offen_id, fertig_id})
        self.assertEqual(ids('?status=offen'), {offen_id})
        self.assertEqual(ids('?status=bestaetigt'), {fertig_id})
        self.assertEqual(self.client.get(BASIS + 'druckstapel/?status=quatsch').status_code, 400)

    def test_filter_objekt(self):
        a_id, _ = self.stapel()
        b = fixtures.szenario(wechsel=False, mahnung=False, vorgang=False)
        b_id, _ = self.stapel(
            empfaenger=str(b.person.pk), objekt=str(b.objekt.pk), einheit=str(b.einheit.pk))

        def ids(objekt):
            antwort = self.client.get(BASIS + f'druckstapel/?objekt={objekt.pk}')
            self.assertEqual(antwort.status_code, 200, antwort.content)
            return {d['id'] for d in antwort.json()}

        self.assertEqual(ids(self.s.objekt), {a_id})
        self.assertEqual(ids(b.objekt), {b_id})
        self.assertEqual(self.client.get(BASIS + 'druckstapel/?objekt=kein-objekt').status_code, 400)

    def test_schreiben_verschiedener_objekte_liefern_stapel_nur_einmal(self):
        """Ein Stapel mit mehreren Schreiben desselben Objekts erscheint bei ``?objekt=`` genau einmal."""
        a = self.erstelle_id()
        b = self.erstelle_id()
        for sid in (a, b):
            self.client.post(BASIS + f'schreiben/{sid}/freigeben/')
            self.client.post(BASIS + f'schreiben/{sid}/versenden/')
        stapel = self.client.post(BASIS + 'druckstapel/', {}, format='json').json()
        antwort = self.client.get(BASIS + f'druckstapel/?objekt={self.s.objekt.pk}').json()
        self.assertEqual([d['id'] for d in antwort], [stapel['id']])
        self.assertEqual(antwort[0]['anzahl'], 2)


class SchreibenDetailVersionTest(ApiBasis):

    def test_vorlage_version_im_detail(self):
        sid = self.erstelle_id()
        daten = self.client.get(BASIS + f'schreiben/{sid}/').json()
        self.assertEqual(daten['vorlage_version'], str(self.version.pk))
        info = daten['vorlage_version_info']
        self.assertEqual(info['id'], str(self.version.pk))
        self.assertEqual(info['version'], 1)
        self.assertEqual(info['status'], 'freigegeben')
        self.assertEqual(info['vorlage_code'], 'brief')
        self.assertEqual(info['vorlage_id'], str(self.version.vorlage_id))
        # Ausgangstext ueber den bestehenden Versionen-Endpoint ladbar
        version = self.client.get(BASIS + f"versionen/{daten['vorlage_version']}/")
        self.assertEqual(version.status_code, 200)
        self.assertEqual(version.json()['inhalt'], self.version.inhalt)

    def test_vorlage_version_auch_nach_aktionen(self):
        sid = self.erstelle_id()
        antwort = self.client.post(BASIS + f'schreiben/{sid}/freigeben/')
        self.assertEqual(antwort.json()['vorlage_version'], str(self.version.pk))

    def test_liste_bleibt_unveraendert(self):
        self.erstelle_id()
        eintrag = self.client.get(BASIS + 'schreiben/').json()[0]
        self.assertNotIn('vorlage_version', eintrag)
        self.assertNotIn('vorlage_version_info', eintrag)


class SerienlaufAbbruchTest(ApiBasis):

    def setUp(self):
        super().setUp()
        self.anna = neue_person('Anna')
        neues_ev(neue_einheit(self.s.objekt, '2'), self.anna)

    def lauf(self):
        antwort = self.client.post(
            BASIS + 'serienlaeufe/', {'vorlage_code': 'brief', 'objekt': str(self.s.objekt.pk)}, format='json')
        self.assertEqual(antwort.status_code, 201, antwort.content)
        return antwort.json()['id']

    def abbrechen(self, lauf_id):
        return self.client.post(BASIS + f'serienlaeufe/{lauf_id}/abbrechen/')

    def test_ohne_anmeldung(self):
        from rest_framework.test import APIClient
        self.assertEqual(APIClient().post(BASIS + f'serienlaeufe/{NULL_ID}/abbrechen/').status_code, 401)

    def test_abbruch_verwirft_offene_schreiben(self):
        lauf_id = self.lauf()
        antwort = self.abbrechen(lauf_id)
        self.assertEqual(antwort.status_code, 200, antwort.content)
        daten = antwort.json()
        self.assertEqual(daten['status'], 'abgebrochen')
        self.assertEqual(daten['status_anzeige'], 'Abgebrochen')
        self.assertEqual(daten['zaehler']['je_status'], {'verworfen': 2})
        self.assertFalse(daten['freigebbar'])
        self.assertEqual(Schreiben.objects.filter(serienlauf_id=lauf_id, status='verworfen').count(), 2)

    def test_versendete_schreiben_bleiben(self):
        lauf_id = self.lauf()
        versendet, offen = list(Schreiben.objects.filter(serienlauf_id=lauf_id).order_by('nummer'))
        Schreiben.objects.filter(pk=versendet.pk).update(status='versendet')
        antwort = self.abbrechen(lauf_id)
        self.assertEqual(antwort.status_code, 200, antwort.content)
        versendet.refresh_from_db()
        offen.refresh_from_db()
        self.assertEqual(versendet.status, 'versendet')
        self.assertEqual(offen.status, 'verworfen')

    def test_nicht_erzeugbare_entwuerfe_werden_ebenfalls_verworfen(self):
        lauf_id = self.lauf()
        Schreiben.objects.filter(serienlauf_id=lauf_id).update(status='entwurf', fehler='x')
        self.assertEqual(self.abbrechen(lauf_id).status_code, 200)
        self.assertEqual(Schreiben.objects.filter(serienlauf_id=lauf_id, status='verworfen').count(), 2)

    def test_abgebrochener_lauf_nicht_erneut_freigebbar_oder_abbrechbar(self):
        lauf_id = self.lauf()
        self.abbrechen(lauf_id)
        self.assertEqual(self.client.post(BASIS + f'serienlaeufe/{lauf_id}/freigeben/').status_code, 400)
        self.assertEqual(self.abbrechen(lauf_id).status_code, 400)
        self.assertEqual(Serienlauf.objects.get(pk=lauf_id).status, 'abgebrochen')
        lauf = Serienlauf.objects.get(pk=lauf_id)
        with self.assertRaises(ValidationError):
            serienlauf_service.verarbeite(lauf, self.user)

    def test_freigegebener_lauf_vor_verarbeitung_ist_abbrechbar(self):
        lauf_id = self.lauf()
        serienlauf_service.freigeben(Serienlauf.objects.get(pk=lauf_id), self.user)
        antwort = self.abbrechen(lauf_id)
        self.assertEqual(antwort.status_code, 200, antwort.content)
        self.assertEqual(antwort.json()['status'], 'abgebrochen')
        self.assertEqual(Schreiben.objects.filter(serienlauf_id=lauf_id, status='verworfen').count(), 2)

    def test_lauf_mit_angelaufener_verarbeitung_nicht_abbrechbar(self):
        lauf_id = self.lauf()
        lauf = serienlauf_service.freigeben(Serienlauf.objects.get(pk=lauf_id), self.user)
        einzelnes = lauf.schreiben.order_by('nummer').first()
        schreiben_service.freigeben(einzelnes, self.user)
        antwort = self.abbrechen(lauf_id)
        self.assertEqual(antwort.status_code, 400)
        self.assertIn('angelaufen', antwort.json()['detail'])
        self.assertEqual(Serienlauf.objects.get(pk=lauf_id).status, 'freigegeben')
        self.assertFalse(Schreiben.objects.filter(serienlauf_id=lauf_id, status='verworfen').exists())

    def test_versendeter_lauf_nicht_abbrechbar(self):
        lauf_id = self.lauf()
        serienlauf_service.freigeben(Serienlauf.objects.get(pk=lauf_id), self.user)
        serienlauf_service.verarbeite(Serienlauf.objects.get(pk=lauf_id), self.user)
        self.assertEqual(Serienlauf.objects.get(pk=lauf_id).status, 'versendet')
        antwort = self.abbrechen(lauf_id)
        self.assertEqual(antwort.status_code, 400)
        self.assertEqual(Serienlauf.objects.get(pk=lauf_id).status, 'versendet')
        self.assertFalse(Schreiben.objects.filter(serienlauf_id=lauf_id, status='verworfen').exists())

    def test_unbekannter_lauf(self):
        self.assertEqual(self.abbrechen(NULL_ID).status_code, 404)

    def test_service_direkt_ohne_user(self):
        lauf = serienlauf_service.abbrechen(
            serienlauf_service.starte(self.version, self.s.objekt, user=self.user))
        self.assertEqual(lauf.status, 'abgebrochen')
        self.assertEqual(lauf.schreiben.exclude(status='verworfen').count(), 0)
