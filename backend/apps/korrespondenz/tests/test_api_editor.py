"""Phase 5a: Editor-Endpoints (Spec 8) - Vorlagen, Versionen, Freigabe, Vorschau, Textbausteine, Briefbögen."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from rest_framework.test import APIClient

from apps.korrespondenz.models import (
    Briefbogen, Textbaustein, Vorlage, VorlagenVersion, Schreiben,
)
from apps.dokumente.models import Dokument
from apps.objekte.models import Bankkonto

from .basis_versand import VersandTestBasis

BASIS = '/api/v1/korrespondenz/'
User = get_user_model()

INHALT = [{'typ': 'text', 'inhalt': 'wir informieren Sie über {{ objekt.bezeichnung }}.'}]


class EditorBasis(VersandTestBasis):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @classmethod
    def user_mit_freigaberecht(cls):
        user = User.objects.create_user('freigeber')
        user.user_permissions.add(Permission.objects.get(codename='vorlage_freigeben'))
        return user

    def neue_vorlage(self, **kw):
        daten = {'code': 'neu', 'bezeichnung': 'Neue Vorlage', 'anlass': 'eigentuemer_allgemein'}
        daten.update(kw)
        antwort = self.client.post(BASIS + 'vorlagen/', daten, format='json')
        self.assertEqual(antwort.status_code, 201, antwort.content)
        return antwort.json()

    def neue_version(self, vorlage_id, **kw):
        daten = {'betreff': 'Betreff', 'inhalt': INHALT}
        daten.update(kw)
        antwort = self.client.post(BASIS + f'vorlagen/{vorlage_id}/versionen/', daten, format='json')
        self.assertEqual(antwort.status_code, 201, antwort.content)
        return antwort.json()


class ZugriffTest(EditorBasis):

    def test_ohne_anmeldung(self):
        anonym = APIClient()
        for methode, url in (
            ('get', 'vorlagen/'), ('post', 'vorlagen/'), ('get', 'textbausteine/'),
            ('post', 'textbausteine/'), ('get', 'briefboegen/'), ('post', 'briefboegen/'),
            ('patch', f'versionen/{self.vorlage().pk}/'),
        ):
            with self.subTest(url=url):
                self.assertEqual(getattr(anonym, methode)(BASIS + url).status_code, 401)

    def test_methoden(self):
        v = self.neue_vorlage()
        self.assertEqual(self.client.delete(BASIS + f'vorlagen/{v["id"]}/').status_code, 405)
        self.assertEqual(self.client.put(BASIS + f'vorlagen/{v["id"]}/', {}, format='json').status_code, 405)


class VorlagenApiTest(EditorBasis):

    def test_anlegen_und_lesen(self):
        daten = self.neue_vorlage(kanal_standard='email')
        self.assertEqual(daten['code'], 'neu')
        self.assertEqual(daten['anlass_anzeige'], 'Allgemeines Eigentümerschreiben')
        self.assertEqual(daten['kanal_standard'], 'email')
        self.assertIsNone(daten['aktive_version'])
        self.assertEqual(daten['versionen'], [])
        self.assertEqual(Vorlage.objects.get(pk=daten['id']).erstellt_von, self.user)
        detail = self.client.get(BASIS + f'vorlagen/{daten["id"]}/').json()
        self.assertEqual(detail['id'], daten['id'])

    def test_anlegen_ungueltig(self):
        self.neue_vorlage()
        for fehler in (
            {'code': 'neu'},                                # doppelt (global)
            {'code': 'x', 'anlass': 'gibt_es_nicht'},
            {'code': 'x', 'kanal_standard': 'fax'},
            {'code': ''},
        ):
            with self.subTest(fehler=fehler):
                daten = {'code': 'zwei', 'bezeichnung': 'Zwei', 'anlass': 'eigentuemer_allgemein', **fehler}
                self.assertEqual(self.client.post(BASIS + 'vorlagen/', daten, format='json').status_code, 400)
        self.assertEqual(self.client.post(BASIS + 'vorlagen/', {'code': 'nur_code'}, format='json').status_code, 400)

    def test_gleicher_code_je_objekt_ist_erlaubt_aber_nicht_doppelt(self):
        self.neue_vorlage()
        objekt = str(self.s.objekt.pk)
        self.neue_vorlage(objekt=objekt)
        antwort = self.client.post(BASIS + 'vorlagen/', {
            'code': 'neu', 'bezeichnung': 'x', 'anlass': 'eigentuemer_allgemein', 'objekt': objekt,
        }, format='json')
        self.assertEqual(antwort.status_code, 400)
        self.assertIn('bereits', antwort.json()['detail'])

    def test_liste_und_filter(self):
        a = self.neue_vorlage(code='a', anlass='mahnung_stufe_1')
        b = self.neue_vorlage(code='b', objekt=str(self.s.objekt.pk))
        Vorlage.objects.filter(pk=b['id']).update(aktiv=False)

        def ids(query):
            antwort = self.client.get(BASIS + 'vorlagen/' + query)
            self.assertEqual(antwort.status_code, 200, antwort.content)
            return {v['id'] for v in antwort.json()}

        self.assertEqual(ids(''), {a['id'], b['id']})
        self.assertEqual(ids('?anlass=mahnung_stufe_1'), {a['id']})
        self.assertEqual(ids('?code=b'), {b['id']})
        self.assertEqual(ids('?aktiv=1'), {a['id']})
        self.assertEqual(ids('?aktiv=0'), {b['id']})
        self.assertEqual(ids('?objekt=null'), {a['id']})
        self.assertEqual(ids(f'?objekt={self.s.objekt.pk}'), {b['id']})

    def test_patch_aendert_nur_erlaubte_felder(self):
        daten = self.neue_vorlage()
        antwort = self.client.patch(BASIS + f'vorlagen/{daten["id"]}/', {
            'bezeichnung': 'Umbenannt', 'einzeln_bearbeitbar': True, 'aktiv': False,
            'code': 'anders', 'anlass': 'mahnung_stufe_1',
        }, format='json')
        self.assertEqual(antwort.status_code, 200, antwort.content)
        vorlage = Vorlage.objects.get(pk=daten['id'])
        self.assertEqual((vorlage.bezeichnung, vorlage.einzeln_bearbeitbar, vorlage.aktiv),
                         ('Umbenannt', True, False))
        self.assertEqual((vorlage.code, vorlage.anlass), ('neu', 'eigentuemer_allgemein'))

    def test_detail_zeigt_versionen_und_aktive_version(self):
        version = self.vorlage('mit_v', 'eigentuemer_allgemein')
        detail = self.client.get(BASIS + f'vorlagen/{version.vorlage_id}/').json()
        self.assertEqual(detail['aktive_version_info'], {'id': str(version.pk), 'version': 1, 'status': 'freigegeben'})
        self.assertEqual([v['version'] for v in detail['versionen']], [1])

    def test_unbekannte_vorlage(self):
        self.assertEqual(self.client.get(BASIS + 'vorlagen/00000000-0000-0000-0000-000000000000/').status_code, 404)


class VersionenApiTest(EditorBasis):

    def test_version_anlegen_und_listen(self):
        vorlage = self.neue_vorlage()
        v1 = self.neue_version(vorlage['id'], eingabefelder=[
            {'name': 'ort', 'label': 'Ort', 'typ': 'text', 'pflicht': True}])
        v2 = self.neue_version(vorlage['id'])
        self.assertEqual((v1['version'], v1['status']), (1, 'entwurf'))
        self.assertEqual(v2['version'], 2)
        self.assertEqual(VorlagenVersion.objects.get(pk=v1['id']).erstellt_von, self.user)
        liste = self.client.get(BASIS + f'vorlagen/{vorlage["id"]}/versionen/').json()
        self.assertEqual([v['version'] for v in liste], [2, 1])
        self.assertEqual(liste[1]['inhalt'], INHALT)

    def test_version_ungueltig(self):
        vorlage = self.neue_vorlage()
        url = BASIS + f'vorlagen/{vorlage["id"]}/versionen/'
        for daten in (
            {'inhalt': INHALT},                                             # Betreff fehlt
            {'betreff': 'x', 'inhalt': [{'typ': 'gedicht'}]},               # Blocktyp
            {'betreff': 'x', 'inhalt': [{'typ': 'tabelle'}]},               # quelle fehlt
            {'betreff': 'x', 'inhalt': 'kein Array'},
            {'betreff': 'x', 'eingabefelder': [{'name': 'Ohne Typ'}]},
            {'betreff': 'x', 'parameter': [1]},
        ):
            with self.subTest(daten=daten):
                self.assertEqual(self.client.post(url, daten, format='json').status_code, 400)
        self.assertEqual(vorlage_versionen(vorlage['id']), 0)

    def test_neue_version_aus_freigegebener_basis(self):
        frei = self.vorlage('basis', 'eigentuemer_allgemein')
        antwort = self.client.post(BASIS + f'vorlagen/{frei.vorlage_id}/versionen/', {
            'basis_version': str(frei.pk), 'betreff': 'Neuer Betreff'}, format='json')
        self.assertEqual(antwort.status_code, 201, antwort.content)
        daten = antwort.json()
        self.assertEqual((daten['version'], daten['status'], daten['betreff']), (2, 'entwurf', 'Neuer Betreff'))
        self.assertEqual(daten['inhalt'], frei.inhalt)                     # Inhalt übernommen
        frei.refresh_from_db()
        self.assertEqual((frei.status, frei.betreff), ('freigegeben', 'Information zum Objekt'))

    def test_basis_einer_anderen_vorlage_wird_abgelehnt(self):
        fremd = self.vorlage('fremd', 'eigentuemer_allgemein')
        vorlage = self.neue_vorlage()
        antwort = self.client.post(BASIS + f'vorlagen/{vorlage["id"]}/versionen/', {
            'basis_version': str(fremd.pk)}, format='json')
        self.assertEqual(antwort.status_code, 400)

    def test_patch_entwurf(self):
        version = self.neue_version(self.neue_vorlage()['id'])
        antwort = self.client.patch(BASIS + f'versionen/{version["id"]}/', {
            'betreff': 'Geändert', 'email_begleittext': 'Guten Tag', 'pflicht_platzhalter': ['objekt.bezeichnung'],
            'status': 'freigegeben',                                       # schreibgeschützt -> ignoriert
        }, format='json')
        self.assertEqual(antwort.status_code, 200, antwort.content)
        gespeichert = VorlagenVersion.objects.get(pk=version['id'])
        self.assertEqual((gespeichert.betreff, gespeichert.email_begleittext), ('Geändert', 'Guten Tag'))
        self.assertEqual(gespeichert.pflicht_platzhalter, ['objekt.bezeichnung'])
        self.assertEqual(gespeichert.status, 'entwurf')
        self.assertEqual(gespeichert.inhalt, INHALT)

    def test_patch_ungueltiger_inhalt(self):
        version = self.neue_version(self.neue_vorlage()['id'])
        antwort = self.client.patch(BASIS + f'versionen/{version["id"]}/', {
            'inhalt': [{'typ': 'liste'}]}, format='json')
        self.assertEqual(antwort.status_code, 400)
        self.assertEqual(VorlagenVersion.objects.get(pk=version['id']).inhalt, INHALT)

    def test_patch_freigegebene_version_ist_gesperrt(self):
        frei = self.vorlage('gesperrt', 'eigentuemer_allgemein')
        antwort = self.client.patch(BASIS + f'versionen/{frei.pk}/', {'betreff': 'Hacken'}, format='json')
        self.assertEqual(antwort.status_code, 409)
        self.assertIn('unveränderlich', antwort.json()['detail'])
        frei.refresh_from_db()
        self.assertEqual(frei.betreff, 'Information zum Objekt')

    def test_get_version(self):
        frei = self.vorlage('lesen', 'eigentuemer_allgemein')
        daten = self.client.get(BASIS + f'versionen/{frei.pk}/').json()
        self.assertEqual((daten['status'], daten['status_anzeige']), ('freigegeben', 'Freigegeben'))


def vorlage_versionen(vorlage_id) -> int:
    return VorlagenVersion.objects.filter(vorlage_id=vorlage_id).count()


class FreigabeApiTest(EditorBasis):

    def entwurf(self):
        vorlage = self.neue_vorlage()
        return vorlage, self.neue_version(vorlage['id'])

    def test_ohne_berechtigung_403(self):
        vorlage, version = self.entwurf()
        antwort = self.client.post(BASIS + f'versionen/{version["id"]}/freigeben/')
        self.assertEqual(antwort.status_code, 403)
        self.assertEqual(VorlagenVersion.objects.get(pk=version['id']).status, 'entwurf')

    def test_mit_berechtigung(self):
        vorlage, version = self.entwurf()
        freigeber = self.user_mit_freigaberecht()
        self.client.force_authenticate(freigeber)
        antwort = self.client.post(BASIS + f'versionen/{version["id"]}/freigeben/')
        self.assertEqual(antwort.status_code, 200, antwort.content)
        self.assertEqual(antwort.json()['status'], 'freigegeben')
        self.assertEqual(antwort.json()['freigegeben_von'], freigeber.pk)
        gespeichert = Vorlage.objects.get(pk=vorlage['id'])
        self.assertEqual(str(gespeichert.aktive_version_id), version['id'])

    def test_neue_freigabe_loest_alte_ab_und_doppelte_freigabe_ist_gesperrt(self):
        vorlage, v1 = self.entwurf()
        self.client.force_authenticate(self.user_mit_freigaberecht())
        self.assertEqual(self.client.post(BASIS + f'versionen/{v1["id"]}/freigeben/').status_code, 200)
        self.assertEqual(self.client.post(BASIS + f'versionen/{v1["id"]}/freigeben/').status_code, 409)
        v2 = self.neue_version(vorlage['id'], basis_version=v1['id'])
        self.assertEqual(self.client.post(BASIS + f'versionen/{v2["id"]}/freigeben/').status_code, 200)
        self.assertEqual(VorlagenVersion.objects.get(pk=v1['id']).status, 'abgeloest')
        self.assertEqual(str(Vorlage.objects.get(pk=vorlage['id']).aktive_version_id), v2['id'])


class VorschauApiTest(EditorBasis):

    def setUp(self):
        super().setUp()
        self.version = self.vorlage('vorschau', 'eigentuemer_allgemein')

    def url(self, version=None):
        return BASIS + f'versionen/{(version or self.version).pk}/vorschau/'

    def daten(self, **kw):
        daten = {'person_id': str(self.s.person.pk), 'einheit_id': str(self.s.einheit.pk)}
        daten.update(kw)
        return daten

    def test_liefert_pdf_ohne_persistierung(self):
        vorher = (Schreiben.objects.count(), Dokument.objects.count())
        antwort = self.client.post(self.url(), self.daten(), format='json')
        self.assertEqual(antwort.status_code, 200, antwort.content[:300])
        self.assertEqual(antwort['Content-Type'], 'application/pdf')
        self.assertTrue(antwort.content.startswith(b'%PDF'))
        self.assertEqual((Schreiben.objects.count(), Dokument.objects.count()), vorher)

    def test_ohne_einheit_und_fuer_entwurf(self):
        entwurf = VorlagenVersion.objects.create(
            vorlage=self.version.vorlage, version=2, betreff='Entwurf',
            inhalt=[{'typ': 'text', 'inhalt': 'wir schreiben Ihnen, {{ empfaenger.name }}.'}])
        antwort = self.client.post(self.url(entwurf), {'person_id': str(self.s.person.pk)}, format='json')
        self.assertEqual(antwort.status_code, 200, antwort.content[:300])
        self.assertTrue(antwort.content.startswith(b'%PDF'))

    def test_eingabewerte_werden_verwendet(self):
        version = self.vorlage(
            'mit_eingabe', 'eigentuemer_allgemein', inhalt=[{'typ': 'text', 'inhalt': 'Ort: {{ eingabe.ort }}'}],
            eingabefelder=[{'name': 'ort', 'label': 'Ort', 'typ': 'text', 'pflicht': True}])
        antwort = self.client.post(self.url(version), self.daten(eingabewerte={'ort': 'Kaminzimmer'}), format='json')
        self.assertEqual(antwort.status_code, 200, antwort.content[:300])
        self.assertEqual(antwort['Content-Type'], 'application/pdf')

    def test_fehlender_pflichtwert_wird_in_der_vorschau_durch_beispiel_ersetzt(self):
        version = self.vorlage(
            'pflicht', 'eigentuemer_allgemein', inhalt=[{'typ': 'text', 'inhalt': 'Ort: {{ eingabe.ort }}'}],
            eingabefelder=[{'name': 'ort', 'label': 'Ort', 'typ': 'text', 'pflicht': True}])
        antwort = self.client.post(self.url(version), self.daten(), format='json')
        self.assertEqual(antwort.status_code, 200, antwort.content[:300])
        self.assertEqual(antwort['Content-Type'], 'application/pdf')

    def test_ungueltiger_eingabewert_ist_4xx_mit_ursache(self):
        version = self.vorlage(
            'betrag', 'eigentuemer_allgemein', inhalt=[{'typ': 'text', 'inhalt': '{{ eingabe.b|euro }}'}],
            eingabefelder=[{'name': 'b', 'label': 'Betrag', 'typ': 'betrag', 'pflicht': True}])
        antwort = self.client.post(self.url(version), self.daten(eingabewerte={'b': 'abc'}), format='json')
        self.assertEqual(antwort.status_code, 400)
        self.assertNotEqual(antwort['Content-Type'], 'application/pdf')
        self.assertIn('Vorschau nicht erzeugbar', antwort.json()['detail'])
        self.assertIn('Feld "Betrag"', antwort.json()['detail'])

    def test_fehlender_betreuer_wird_in_der_vorschau_durch_beispiel_ersetzt(self):
        version = self.vorlage(
            'ohne_wert', 'eigentuemer_allgemein',
            inhalt=[{'typ': 'text', 'inhalt': 'Betreuer: {{ verwaltung.betreuer_name }}'}])
        from apps.objekte.models import Objekt
        Objekt.objects.filter(pk=self.s.objekt.pk).update(betreuer=None)
        antwort = self.client.post(self.url(version), self.daten(), format='json')
        self.assertEqual(antwort.status_code, 200, antwort.content[:300])
        self.assertEqual(antwort['Content-Type'], 'application/pdf')

    def test_unbekannter_platzhalter_ist_4xx(self):
        version = self.vorlage(
            'unbekannt', 'eigentuemer_allgemein',
            inhalt=[{'typ': 'text', 'inhalt': 'Wert: {{ verwaltung.gibt_es_nicht }}'}])
        antwort = self.client.post(self.url(version), self.daten(), format='json')
        self.assertEqual(antwort.status_code, 400, antwort.content[:300])
        self.assertIn('Vorschau nicht erzeugbar', antwort.json()['detail'])
        self.assertIn('verwaltung.gibt_es_nicht', antwort.json()['detail'])

    def test_fehlendes_bankkonto_beim_weg_nutzt_in_der_vorschau_beispielbank(self):
        Bankkonto.objects.filter(objekt=self.s.objekt).delete()
        antwort = self.client.post(self.url(), self.daten(), format='json')
        self.assertEqual(antwort.status_code, 200, antwort.content[:300])
        self.assertEqual(antwort['Content-Type'], 'application/pdf')

    def test_kein_briefbogen(self):
        Briefbogen.objects.update(ist_standard=False)
        antwort = self.client.post(self.url(), self.daten(), format='json')
        self.assertEqual(antwort.status_code, 400)
        self.assertIn('Briefbogen', antwort.json()['detail'])

    def test_eingabe_ungueltig(self):
        for daten in ({}, {'person_id': '00000000-0000-0000-0000-000000000000'},
                      {'person_id': 'kein-uuid'}, self.daten(einheit_id='00000000-0000-0000-0000-000000000000')):
            with self.subTest(daten=daten):
                self.assertEqual(self.client.post(self.url(), daten, format='json').status_code, 400)

    def test_ohne_anmeldung_und_unbekannte_version(self):
        self.assertEqual(APIClient().post(self.url(), self.daten(), format='json').status_code, 401)
        antwort = self.client.post(BASIS + 'versionen/00000000-0000-0000-0000-000000000000/vorschau/',
                                   self.daten(), format='json')
        self.assertEqual(antwort.status_code, 404)


class TextbausteineApiTest(EditorBasis):

    def anlegen(self, **kw):
        daten = {'code': 'gruss', 'bezeichnung': 'Gruß', 'inhalt': 'Mit freundlichen Grüßen'}
        daten.update(kw)
        return self.client.post(BASIS + 'textbausteine/', daten, format='json')

    def test_crud(self):
        antwort = self.anlegen()
        self.assertEqual(antwort.status_code, 201, antwort.content)
        pk = antwort.json()['id']
        self.assertEqual(self.client.get(BASIS + f'textbausteine/{pk}/').json()['inhalt'], 'Mit freundlichen Grüßen')
        antwort = self.client.patch(BASIS + f'textbausteine/{pk}/', {'inhalt': 'Viele Grüße', 'aktiv': False},
                                    format='json')
        self.assertEqual(antwort.status_code, 200, antwort.content)
        baustein = Textbaustein.objects.get(pk=pk)
        self.assertEqual((baustein.inhalt, baustein.aktiv), ('Viele Grüße', False))
        self.assertEqual(len(self.client.get(BASIS + 'textbausteine/').json()), 1)
        self.assertEqual(self.client.delete(BASIS + f'textbausteine/{pk}/').status_code, 204)
        self.assertFalse(Textbaustein.objects.exists())

    def test_code_je_objekt_eindeutig(self):
        self.assertEqual(self.anlegen().status_code, 201)
        self.assertEqual(self.anlegen().status_code, 400)                       # global doppelt
        self.assertEqual(self.anlegen(objekt=str(self.s.objekt.pk)).status_code, 201)
        self.assertEqual(self.anlegen(objekt=str(self.s.objekt.pk)).status_code, 400)
        pk = Textbaustein.objects.get(code='gruss', objekt__isnull=True).pk
        self.assertEqual(self.client.patch(BASIS + f'textbausteine/{pk}/', {'bezeichnung': 'Neu'},
                                           format='json').status_code, 200)     # sich selbst nicht als Duplikat

    def test_filter(self):
        self.anlegen(code='a')
        self.anlegen(code='b', objekt=str(self.s.objekt.pk), aktiv=False)
        codes = lambda q: {b['code'] for b in self.client.get(BASIS + 'textbausteine/' + q).json()}  # noqa: E731
        self.assertEqual(codes('?objekt=null'), {'a'})
        self.assertEqual(codes(f'?objekt={self.s.objekt.pk}'), {'b'})
        self.assertEqual(codes('?aktiv=0'), {'b'})
        self.assertEqual(codes('?code=a'), {'a'})

    def test_baustein_wird_in_der_vorschau_verwendet(self):
        self.anlegen(code='hinweis', inhalt='Bitte beachten Sie {{ objekt.bezeichnung }}.')
        version = self.vorlage('mit_baustein', 'eigentuemer_allgemein', inhalt=[{'typ': 'baustein', 'code': 'hinweis'}])
        antwort = self.client.post(BASIS + f'versionen/{version.pk}/vorschau/', {
            'person_id': str(self.s.person.pk), 'einheit_id': str(self.s.einheit.pk)}, format='json')
        self.assertEqual(antwort.status_code, 200, antwort.content[:300])


class BriefbogenApiTest(EditorBasis):

    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user('admin', is_staff=True)

    def test_normaler_benutzer_hat_keinen_zugriff(self):
        for methode, url in (('get', 'briefboegen/'), ('post', 'briefboegen/'),
                             ('get', f'briefboegen/{self.briefbogen.pk}/'),
                             ('patch', f'briefboegen/{self.briefbogen.pk}/'),
                             ('delete', f'briefboegen/{self.briefbogen.pk}/')):
            with self.subTest(methode=methode, url=url):
                self.assertEqual(getattr(self.client, methode)(BASIS + url).status_code, 403)
        self.assertTrue(Briefbogen.objects.filter(pk=self.briefbogen.pk).exists())

    def test_admin_crud(self):
        self.client.force_authenticate(self.admin)
        liste = self.client.get(BASIS + 'briefboegen/')
        self.assertEqual(liste.status_code, 200)
        self.assertEqual([b['id'] for b in liste.json()], [str(self.briefbogen.pk)])

        antwort = self.client.post(BASIS + 'briefboegen/', {
            'bezeichnung': 'Zweiter', 'firma_name': 'Zweite GmbH', 'logo': str(self.briefbogen.logo_id)},
            format='json')
        self.assertEqual(antwort.status_code, 201, antwort.content)
        pk = antwort.json()['id']
        self.assertFalse(antwort.json()['ist_standard'])

        antwort = self.client.patch(BASIS + f'briefboegen/{pk}/', {'telefon': '069-1'}, format='json')
        self.assertEqual(antwort.status_code, 200, antwort.content)
        self.assertEqual(Briefbogen.objects.get(pk=pk).telefon, '069-1')

        self.assertEqual(self.client.delete(BASIS + f'briefboegen/{pk}/').status_code, 204)
        self.assertFalse(Briefbogen.objects.filter(pk=pk).exists())

    def test_anlegen_ohne_pflichtfelder(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(BASIS + 'briefboegen/', {'bezeichnung': 'x'}, format='json').status_code, 400)

    def test_briefbogen_mit_zugeordneter_vorlage_nicht_loeschbar(self):
        vorlage = self.vorlage('mit_bogen', 'eigentuemer_allgemein').vorlage
        Vorlage.objects.filter(pk=vorlage.pk).update(briefbogen=self.briefbogen)
        self.client.force_authenticate(self.admin)
        antwort = self.client.delete(BASIS + f'briefboegen/{self.briefbogen.pk}/')
        self.assertEqual(antwort.status_code, 409)
        self.assertTrue(Briefbogen.objects.filter(pk=self.briefbogen.pk).exists())
