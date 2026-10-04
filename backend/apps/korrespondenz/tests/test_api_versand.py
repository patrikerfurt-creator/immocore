"""Phase 4: API-Endpoints Schreiben / Druckstapel / Serienläufe (Spec 8) und Celery-Tasks."""
from unittest import mock

from django.core import mail
from django.test import override_settings
from rest_framework.test import APIClient

from apps.korrespondenz import tasks
from apps.korrespondenz.models import Schreiben, Serienlauf
from apps.korrespondenz.services import druckstapel_service, schreiben_service, serienlauf_service
from apps.objekte.models import Objekt

from . import fixtures
from .basis_versand import VersandTestBasis, neue_einheit, neue_person, neues_ev

BASIS = '/api/v1/korrespondenz/'
KONSOLE = 'django.core.mail.backends.console.EmailBackend'


class ApiBasis(VersandTestBasis):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.version = self.vorlage('brief', 'eigentuemer_allgemein', kanal_standard='brief')

    def erstelle(self, **kw):
        daten = {
            'vorlage_code': 'brief', 'empfaenger': str(self.s.person.pk),
            'objekt': str(self.s.objekt.pk), 'einheit': str(self.s.einheit.pk),
        }
        daten.update(kw)
        return self.client.post(BASIS + 'schreiben/', daten, format='json')

    def erstelle_id(self, **kw):
        antwort = self.erstelle(**kw)
        self.assertEqual(antwort.status_code, 201, antwort.content)
        return antwort.json()['id']


class ZugriffTest(ApiBasis):

    def test_ohne_anmeldung(self):
        anonym = APIClient()
        for methode, url in (
            ('get', 'schreiben/'), ('post', 'schreiben/'), ('post', 'druckstapel/'),
            ('post', 'serienlaeufe/'),
        ):
            with self.subTest(url=url):
                self.assertEqual(getattr(anonym, methode)(BASIS + url).status_code, 401)

    def test_put_und_delete_sind_nicht_erlaubt(self):
        sid = self.erstelle_id()
        self.assertEqual(self.client.put(BASIS + f'schreiben/{sid}/', {}, format='json').status_code, 405)
        self.assertEqual(self.client.delete(BASIS + f'schreiben/{sid}/').status_code, 405)


class SchreibenApiTest(ApiBasis):

    def test_erstellen(self):
        antwort = self.erstelle()
        self.assertEqual(antwort.status_code, 201, antwort.content)
        daten = antwort.json()
        self.assertEqual(daten['status'], 'zur_pruefung')
        self.assertRegex(daten['nummer'], r'^KS-\d{4}-\d{6}$')
        self.assertEqual(daten['vorlage']['code'], 'brief')
        self.assertEqual(daten['betreff'], 'Information zum Objekt')
        self.assertIn('wir informieren Sie', daten['html_gerendert'])
        self.assertEqual(daten['empfaenger']['id'], str(self.s.person.pk))
        self.assertEqual(daten['kanal'], 'brief')
        self.assertFalse(daten['nicht_erzeugbar'])

    def test_erstellen_nicht_erzeugbar_liefert_201_mit_fehler(self):
        self.vorlage(
            'mit_pflicht', 'eigentuemer_allgemein',
            inhalt=[{'typ': 'text', 'inhalt': '{{ eingabe.x }}'}],
            eingabefelder=[{'name': 'x', 'label': 'X', 'typ': 'text', 'pflicht': True}])
        antwort = self.erstelle(vorlage_code='mit_pflicht')
        self.assertEqual(antwort.status_code, 201)
        self.assertEqual(antwort.json()['status'], 'entwurf')
        self.assertTrue(antwort.json()['nicht_erzeugbar'])
        self.assertTrue(antwort.json()['fehler'])

    def test_erstellen_ungueltig(self):
        self.assertEqual(self.erstelle(vorlage_code='gibt_es_nicht').status_code, 400)
        self.assertIn('Vorlage', self.erstelle(vorlage_code='gibt_es_nicht').json()['detail'])
        self.assertEqual(self.client.post(BASIS + 'schreiben/', {'vorlage_code': 'brief'}, format='json').status_code, 400)
        self.assertEqual(self.erstelle(kanal='fax').status_code, 400)

    def test_liste_ist_standardmaessig_der_postausgang(self):
        offen = self.erstelle_id()
        frei = self.erstelle_id()
        self.client.post(BASIS + f'schreiben/{frei}/freigeben/')
        ids = [s['id'] for s in self.client.get(BASIS + 'schreiben/').json()]
        self.assertEqual(ids, [offen])

    def test_liste_filter(self):
        a = self.erstelle_id()
        b = fixtures.szenario(wechsel=False, mahnung=False, vorgang=False)
        s_b = self.erstelle_id(empfaenger=str(b.person.pk), objekt=str(b.objekt.pk), einheit=str(b.einheit.pk))
        def ids(query):
            antwort = self.client.get(BASIS + 'schreiben/' + query)
            self.assertEqual(antwort.status_code, 200, antwort.content)
            return {s['id'] for s in antwort.json()}
        self.assertEqual(ids(''), {a, s_b})
        self.assertEqual(ids(f'?objekt={self.s.objekt.pk}'), {a})
        self.assertEqual(ids(f'?objekt={b.objekt.pk}'), {s_b})
        self.assertEqual(ids('?anlass=eigentuemer_allgemein'), {a, s_b})
        self.assertEqual(ids('?anlass=mahnung_stufe_1'), set())
        self.assertEqual(ids(f'?betreuer={self.s.betreuer.pk}'), {a})
        self.client.post(BASIS + f'schreiben/{a}/freigeben/')
        self.assertEqual(ids('?status=freigegeben'), {a})
        self.assertEqual(ids('?status=alle'), {a, s_b})
        self.assertEqual(ids('?status=zur_pruefung,freigegeben'), {a, s_b})

    def test_liste_nicht_erzeugbar_und_ungueltiger_status(self):
        self.vorlage(
            'mit_pflicht', 'eigentuemer_allgemein',
            inhalt=[{'typ': 'text', 'inhalt': '{{ eingabe.x }}'}],
            eingabefelder=[{'name': 'x', 'label': 'X', 'typ': 'text', 'pflicht': True}])
        kaputt = self.erstelle_id(vorlage_code='mit_pflicht')
        self.erstelle_id()
        antwort = self.client.get(BASIS + 'schreiben/?status=nicht_erzeugbar')
        self.assertEqual([s['id'] for s in antwort.json()], [kaputt])
        self.assertEqual(self.client.get(BASIS + 'schreiben/?status=quatsch').status_code, 400)
        self.assertEqual(self.client.get(BASIS + 'schreiben/?objekt=kein-objekt').status_code, 400)

    def test_detail(self):
        sid = self.erstelle_id()
        antwort = self.client.get(BASIS + f'schreiben/{sid}/')
        self.assertEqual(antwort.status_code, 200)
        self.assertIn('html_gerendert', antwort.json())
        self.assertEqual(self.client.get(BASIS + 'schreiben/00000000-0000-0000-0000-000000000000/').status_code, 404)

    def test_freigeben(self):
        sid = self.erstelle_id()
        antwort = self.client.post(BASIS + f'schreiben/{sid}/freigeben/')
        self.assertEqual(antwort.status_code, 200, antwort.content)
        self.assertEqual(antwort.json()['status'], 'freigegeben')
        self.assertIsNotNone(antwort.json()['dokument'])
        self.assertEqual(antwort.json()['freigegeben_von'], self.user.pk)
        zweite = self.client.post(BASIS + f'schreiben/{sid}/freigeben/')
        self.assertEqual(zweite.status_code, 400)

    def test_verwerfen(self):
        sid = self.erstelle_id()
        antwort = self.client.post(BASIS + f'schreiben/{sid}/verwerfen/')
        self.assertEqual((antwort.status_code, antwort.json()['status']), (200, 'verworfen'))
        self.assertEqual(self.client.post(BASIS + f'schreiben/{sid}/verwerfen/').status_code, 400)

    def test_pdf_vorschau_und_freigegeben(self):
        sid = self.erstelle_id()
        vorschau = self.client.get(BASIS + f'schreiben/{sid}/pdf/')
        self.assertEqual(vorschau.status_code, 200)
        self.assertEqual(vorschau['Content-Type'], 'application/pdf')
        self.assertTrue(vorschau.content.startswith(b'%PDF'))
        self.assertEqual(Schreiben.objects.get(pk=sid).dokument_id, None)

        self.client.post(BASIS + f'schreiben/{sid}/freigeben/')
        final = self.client.get(BASIS + f'schreiben/{sid}/pdf/')
        self.assertEqual(final.status_code, 200)
        self.assertTrue(final.content.startswith(b'%PDF'))
        self.assertIn('.pdf', final['Content-Disposition'])

        self.client.post(BASIS + f'schreiben/{self.erstelle_id()}/verwerfen/')
        verworfen = Schreiben.objects.get(status='verworfen')
        self.assertEqual(self.client.get(BASIS + f'schreiben/{verworfen.pk}/pdf/').status_code, 400)

    def test_versenden_brief_und_druckstapel(self):
        sid = self.erstelle_id()
        self.assertEqual(self.client.post(BASIS + f'schreiben/{sid}/versenden/').status_code, 400)   # noch nicht freigegeben
        self.client.post(BASIS + f'schreiben/{sid}/freigeben/')
        antwort = self.client.post(BASIS + f'schreiben/{sid}/versenden/')
        self.assertEqual(antwort.status_code, 200, antwort.content)
        self.assertEqual(antwort.json()['versand']['ergebnis'], 'druckstapel')
        self.assertEqual(antwort.json()['status'], 'freigegeben')

        liste = self.client.get(BASIS + 'schreiben/?druckbereit=1').json()
        self.assertEqual([s['id'] for s in liste], [sid])

        stapel = self.client.post(BASIS + 'druckstapel/', {}, format='json')
        self.assertEqual(stapel.status_code, 201, stapel.content)
        self.assertEqual(stapel.json()['status'], 'offen')
        self.assertEqual(stapel.json()['anzahl'], 1)
        self.assertIsNotNone(stapel.json()['dokument'])
        self.assertEqual(self.client.get(BASIS + 'schreiben/?druckbereit=1').json(), [])

        bestaetigt = self.client.post(BASIS + f"druckstapel/{stapel.json()['id']}/bestaetigen/")
        self.assertEqual(bestaetigt.status_code, 200, bestaetigt.content)
        self.assertEqual(bestaetigt.json()['status'], 'bestaetigt')
        self.assertEqual(self.client.get(BASIS + f'schreiben/{sid}/').json()['status'], 'versendet')
        self.assertEqual(
            self.client.post(BASIS + f"druckstapel/{stapel.json()['id']}/bestaetigen/").status_code, 400)

    def test_druckstapel_ohne_briefe(self):
        antwort = self.client.post(BASIS + 'druckstapel/', {}, format='json')
        self.assertEqual(antwort.status_code, 400)
        self.assertIn('druckbereit', antwort.json()['detail'])

    def test_druckstapel_mit_auswahl(self):
        a, b = self.erstelle_id(), self.erstelle_id()
        for sid in (a, b):
            self.client.post(BASIS + f'schreiben/{sid}/freigeben/')
        antwort = self.client.post(BASIS + 'druckstapel/', {'schreiben_ids': [a]}, format='json')
        self.assertEqual(antwort.status_code, 201)
        self.assertEqual([s['id'] for s in antwort.json()['schreiben']], [a])

    def test_versenden_email(self):
        self.mail_aktiv()
        person = self.mail_person()
        self.vorlage('mail', 'eigentuemer_allgemein', kanal_standard='email')
        sid = self.erstelle_id(vorlage_code='mail', empfaenger=str(person.pk))
        self.client.post(BASIS + f'schreiben/{sid}/freigeben/')
        antwort = self.client.post(BASIS + f'schreiben/{sid}/versenden/')
        self.assertEqual(antwort.json()['versand']['ergebnis'], 'versendet')
        self.assertEqual(antwort.json()['status'], 'versendet')
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(EMAIL_BACKEND=KONSOLE)
    def test_versenden_ohne_smtp_und_dann_als_brief(self):
        self.mail_aktiv()
        person = self.mail_person()
        self.vorlage('mail', 'eigentuemer_allgemein', kanal_standard='email')
        sid = self.erstelle_id(vorlage_code='mail', empfaenger=str(person.pk))
        self.client.post(BASIS + f'schreiben/{sid}/freigeben/')
        antwort = self.client.post(BASIS + f'schreiben/{sid}/versenden/')
        self.assertEqual(antwort.status_code, 200)
        self.assertEqual(antwort.json()['status'], 'versand_fehlgeschlagen')
        self.assertEqual(antwort.json()['versand']['ergebnis'], 'fehlgeschlagen')
        self.assertIn('nicht konfiguriert', antwort.json()['fehler'])
        # Postausgang zeigt den Fehlversand, Brief bleibt möglich
        self.assertEqual([s['id'] for s in self.client.get(BASIS + 'schreiben/').json()], [sid])
        brief = self.client.post(BASIS + f'schreiben/{sid}/versenden/', {'kanal': 'brief'}, format='json')
        self.assertEqual(brief.json()['versand']['ergebnis'], 'druckstapel')
        self.assertEqual(brief.json()['kanal'], 'brief')
        self.assertEqual(self.client.post(
            BASIS + f'schreiben/{sid}/versenden/', {'kanal': 'email'}, format='json').status_code, 400)

    def test_patch_textanpassung(self):
        self.vorlage('bearbeitbar', 'eigentuemer_allgemein', einzeln_bearbeitbar=True)
        sid = self.erstelle_id(vorlage_code='bearbeitbar')
        neu = [{'typ': 'text', 'inhalt': 'Neuer Text.'}]
        antwort = self.client.patch(BASIS + f'schreiben/{sid}/', {'inhalt_angepasst': neu}, format='json')
        self.assertEqual(antwort.status_code, 200, antwort.content)
        self.assertEqual(antwort.json()['inhalt_angepasst'], neu)
        self.assertIn('Neuer Text', antwort.json()['html_gerendert'])
        self.assertEqual(self.client.patch(BASIS + f'schreiben/{sid}/', {}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(
            BASIS + f'schreiben/{sid}/', {'inhalt_angepasst': 'kein Array'}, format='json').status_code, 400)

    def test_patch_nur_bei_einzeln_bearbeitbar_und_zur_pruefung(self):
        neu = {'inhalt_angepasst': [{'typ': 'text', 'inhalt': 'X'}]}
        fest = self.erstelle_id()                                        # Vorlage nicht bearbeitbar
        self.assertEqual(self.client.patch(BASIS + f'schreiben/{fest}/', neu, format='json').status_code, 400)
        self.vorlage('bearbeitbar', 'eigentuemer_allgemein', einzeln_bearbeitbar=True)
        sid = self.erstelle_id(vorlage_code='bearbeitbar')
        self.client.post(BASIS + f'schreiben/{sid}/freigeben/')
        self.assertEqual(self.client.patch(BASIS + f'schreiben/{sid}/', neu, format='json').status_code, 400)


class DruckstapelApiTest(ApiBasis):

    def test_bestaetigen_unbekannter_stapel(self):
        self.assertEqual(
            self.client.post(BASIS + 'druckstapel/00000000-0000-0000-0000-000000000000/bestaetigen/').status_code, 404)


class SerienlaufApiTest(ApiBasis):

    def setUp(self):
        super().setUp()
        self.anna = neue_person('Anna')
        neues_ev(neue_einheit(self.s.objekt, '2'), self.anna)
        self.mail_aktiv()

    def anlegen(self, **kw):
        daten = {'vorlage_code': 'brief', 'objekt': str(self.s.objekt.pk)}
        daten.update(kw)
        return self.client.post(BASIS + 'serienlaeufe/', daten, format='json')

    def test_anlegen_liefert_vorschau(self):
        antwort = self.anlegen()
        self.assertEqual(antwort.status_code, 201, antwort.content)
        daten = antwort.json()
        self.assertEqual(daten['status'], 'zur_pruefung')
        self.assertEqual(daten['anzahl'], 2)
        self.assertEqual(daten['vorschau']['erzeugbar_anzahl'], 2)
        self.assertEqual(len(daten['vorschau']['zufaellig']), 2)
        self.assertIn('wir informieren Sie', daten['vorschau']['zufaellig'][0]['html_gerendert'])
        self.assertEqual(daten['nicht_erzeugbar'], [])
        self.assertTrue(daten['freigebbar'])
        self.assertEqual(daten['vorlage']['code'], 'brief')

    def test_anlegen_mit_version_und_filter(self):
        antwort = self.client.post(BASIS + 'serienlaeufe/', {
            'vorlage_version': str(self.version.pk), 'objekt': str(self.s.objekt.pk),
            'empfaenger_filter': {'ausschliessen': [str(self.s.ev.pk)]},
        }, format='json')
        self.assertEqual(antwort.status_code, 201, antwort.content)
        self.assertEqual(antwort.json()['anzahl'], 1)

    def test_anlegen_ungueltig(self):
        self.assertEqual(self.anlegen(vorlage_code='gibt_es_nicht').status_code, 400)
        self.assertEqual(self.anlegen(vorlage_version=str(self.version.pk)).status_code, 400)   # beides
        self.assertEqual(self.client.post(BASIS + 'serienlaeufe/', {'vorlage_code': 'brief'}, format='json').status_code, 400)
        self.assertEqual(self.anlegen(empfaenger_filter={'quatsch': 1}).status_code, 400)
        self.assertEqual(self.anlegen(empfaenger_filter={'einheit_typ': ['Gewerbe']}).status_code, 400)
        self.assertEqual(Serienlauf.objects.count(), 0)

    def test_detail(self):
        lauf_id = self.anlegen().json()['id']
        antwort = self.client.get(BASIS + f'serienlaeufe/{lauf_id}/')
        self.assertEqual(antwort.status_code, 200)
        self.assertEqual(antwort.json()['zaehler']['gesamt'], 2)
        self.assertEqual(self.client.get(BASIS + 'serienlaeufe/00000000-0000-0000-0000-000000000000/').status_code, 404)

    def test_nicht_erzeugbare_im_detail_mit_ursache(self):
        self.vorlage('lage', 'eigentuemer_allgemein', inhalt=[{'typ': 'text', 'inhalt': '{{ einheit.lage }}'}])
        self.s.einheit.__class__.objects.filter(pk=self.s.einheit.pk).update(lage='')
        daten = self.anlegen(vorlage_code='lage').json()
        self.assertEqual(len(daten['nicht_erzeugbar']), 1)
        self.assertIn('einheit.lage', daten['nicht_erzeugbar'][0]['ursache'])
        self.assertEqual(daten['zaehler']['nicht_erzeugbar'], 1)
        self.assertEqual(daten['vorschau']['erzeugbar_anzahl'], 1)
        self.assertTrue(daten['freigebbar'])

    def test_freigeben_stoesst_verarbeitung_an(self):
        lauf_id = self.anlegen().json()['id']
        with mock.patch.object(tasks.serienlauf_verarbeiten, 'delay') as delay:
            with self.captureOnCommitCallbacks(execute=True):
                antwort = self.client.post(BASIS + f'serienlaeufe/{lauf_id}/freigeben/')
        self.assertEqual(antwort.status_code, 202, antwort.content)
        self.assertEqual(antwort.json()['status'], 'freigegeben')
        delay.assert_called_once_with(lauf_id, self.user.pk)

    def test_freigeben_blockiert_bei_fehlendem_pflichtwert(self):
        self.vorlage(
            'mit_pflicht', 'eigentuemer_allgemein',
            inhalt=[{'typ': 'text', 'inhalt': '{{ eingabe.x }}'}],
            eingabefelder=[{'name': 'x', 'label': 'X', 'typ': 'text', 'pflicht': True}])
        antwort = self.anlegen(vorlage_code='mit_pflicht')
        self.assertEqual(antwort.status_code, 201)
        self.assertFalse(antwort.json()['freigebbar'])
        self.assertTrue(antwort.json()['blocker'])
        with mock.patch.object(tasks.serienlauf_verarbeiten, 'delay') as delay:
            with self.captureOnCommitCallbacks(execute=True):
                freigabe = self.client.post(BASIS + f"serienlaeufe/{antwort.json()['id']}/freigeben/")
        self.assertEqual(freigabe.status_code, 400)
        delay.assert_not_called()

    def test_broker_ausfall_macht_freigabe_nicht_kaputt(self):
        lauf_id = self.anlegen().json()['id']
        with mock.patch.object(tasks.serienlauf_verarbeiten, 'delay', side_effect=ConnectionError('redis')):
            with self.assertLogs('apps.korrespondenz.views', 'ERROR'):
                with self.captureOnCommitCallbacks(execute=True):
                    antwort = self.client.post(BASIS + f'serienlaeufe/{lauf_id}/freigeben/')
        self.assertEqual(antwort.status_code, 202)
        self.assertEqual(Serienlauf.objects.get(pk=lauf_id).status, 'freigegeben')

    def test_ende_zu_ende_ueber_task(self):
        lauf_id = self.anlegen().json()['id']
        self.client.post(BASIS + f'serienlaeufe/{lauf_id}/freigeben/')
        ergebnis = tasks.serienlauf_verarbeiten(lauf_id, self.user.pk)
        self.assertEqual(ergebnis, {'ok': True, 'status': 'versendet'})
        daten = self.client.get(BASIS + f'serienlaeufe/{lauf_id}/').json()
        self.assertEqual(daten['status'], 'versendet')
        self.assertIsNotNone(daten['druck_dokument'])
        self.assertEqual(len(daten['druckstapel_ids']), 1)
        bestaetigt = self.client.post(BASIS + f"druckstapel/{daten['druckstapel_ids'][0]}/bestaetigen/")
        self.assertEqual(bestaetigt.status_code, 200)
        self.assertEqual(Schreiben.objects.filter(serienlauf_id=lauf_id, status='versendet').count(), 2)


class TaskTest(ApiBasis):

    def freigegeben(self):
        return schreiben_service.freigeben(
            schreiben_service.erstellen('brief', self.s.person, objekt=self.s.objekt, user=self.user), self.user)

    def test_versende_schreiben(self):
        s = self.freigegeben()
        ergebnis = tasks.versende_schreiben(str(s.pk), self.user.pk)
        self.assertEqual(ergebnis, {'ok': True, 'ergebnis': 'druckstapel', 'hinweis': ''})
        self.assertIn(s, druckstapel_service.druckbereite_schreiben())

    def test_versende_schreiben_kanal_brief(self):
        self.mail_aktiv()
        person = self.mail_person()
        self.vorlage('mail', 'eigentuemer_allgemein', kanal_standard='email')
        s = schreiben_service.freigeben(
            schreiben_service.erstellen('mail', person, objekt=self.s.objekt, user=self.user), self.user)
        ergebnis = tasks.versende_schreiben(str(s.pk), self.user.pk, 'brief')
        self.assertEqual(ergebnis['ergebnis'], 'druckstapel')
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_BACKEND=KONSOLE)
    def test_versende_schreiben_meldet_fehlversand_ohne_zu_werfen(self):
        self.mail_aktiv()
        person = self.mail_person()
        self.vorlage('mail', 'eigentuemer_allgemein', kanal_standard='email')
        s = schreiben_service.freigeben(
            schreiben_service.erstellen('mail', person, objekt=self.s.objekt, user=self.user), self.user)
        ergebnis = tasks.versende_schreiben(str(s.pk), self.user.pk)
        self.assertFalse(ergebnis['ok'])
        self.assertEqual(ergebnis['ergebnis'], 'fehlgeschlagen')
        self.assertEqual(Schreiben.objects.get(pk=s.pk).status, 'versand_fehlgeschlagen')

    def test_tasks_werfen_nie_durch(self):
        unbekannt = '00000000-0000-0000-0000-000000000000'
        self.assertEqual(tasks.versende_schreiben(unbekannt)['ergebnis'], 'nicht_gefunden')
        self.assertEqual(tasks.serienlauf_verarbeiten(unbekannt)['status'], 'nicht_gefunden')
        # zur_pruefung ist nicht versendbar -> Fehler wird gemeldet statt geworfen
        s = schreiben_service.erstellen('brief', self.s.person, objekt=self.s.objekt, user=self.user)
        with self.assertLogs('apps.korrespondenz.tasks', 'ERROR'):
            ergebnis = tasks.versende_schreiben(str(s.pk), self.user.pk)
        self.assertEqual((ergebnis['ok'], ergebnis['ergebnis']), (False, 'fehler'))

    def test_serienlauf_task_bei_falschem_status(self):
        lauf = serienlauf_service.starte(self.version, self.s.objekt, user=self.user)
        with self.assertLogs('apps.korrespondenz.tasks', 'ERROR'):
            self.assertEqual(tasks.serienlauf_verarbeiten(str(lauf.pk))['status'], 'fehler')

    def test_task_namen(self):
        self.assertEqual(tasks.versende_schreiben.name, 'korrespondenz.versende_schreiben')
        self.assertEqual(tasks.serienlauf_verarbeiten.name, 'korrespondenz.serienlauf_verarbeiten')
