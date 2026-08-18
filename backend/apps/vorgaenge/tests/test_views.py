"""
API-Tests für ``apps.vorgaenge`` (Kap. 2 der Spec Vorgang & DMS v1.0, Phase D).

Deckt ab: Anlage (inkl. serverseitig erzwungener ``quelle='manuell'``),
Listen-Filter, Statuswechsel gültig/ungültig, Kommentar, Zuweisung,
Dokument-Upload mit Duplikat-Warnung, ``vorgang-typen``-Liste (nur aktive),
Admin-Endpoint (nur ``is_staff``).
"""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.objekte.models import Einheit, Objekt
from apps.vorgaenge.models import Vorgang, VorgangEreignis, VorgangTyp

User = get_user_model()

VORGAENGE = '/api/v1/vorgaenge/'
VORGANG_TYPEN = '/api/v1/vorgang-typen/'
VORGANG_TYPEN_ADMIN = '/api/v1/vorgang-typen/admin/'


def _objekt(nr='VW001'):
    return Objekt.objects.create(
        bezeichnung='Test-WEG Vorgang-API', objektnummer=nr, objekt_typ='weg',
        ort='Teststadt', verwaltung_seit=date(2020, 1, 1),
    )


def _typ(code='maengelmeldung'):
    return VorgangTyp.objects.get(code=code)


class VorgangAnlageTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='vorgang-api-tester')
        self.client.force_authenticate(self.user)
        self.objekt = _objekt()

    def test_anlage_setzt_quelle_manuell_und_status_offen(self):
        response = self.client.post(VORGAENGE, {
            'typ': str(_typ().id),
            'objekt': str(self.objekt.id),
            'betreff': 'Wasserschaden Keller',
            'quelle': 'mail',  # Client versucht, quelle zu setzen — wird ignoriert
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['quelle'], 'manuell')
        self.assertEqual(response.data['status'], 'offen')
        self.assertRegex(response.data['nummer'], r'^V-\d{2}-\d{5}$')

    def test_anlage_ohne_kontext_wird_abgewiesen(self):
        response = self.client.post(VORGAENGE, {
            'typ': str(_typ().id),
            'betreff': 'Ohne Kontext',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_erstellt_von_ist_request_user(self):
        response = self.client.post(VORGAENGE, {
            'typ': str(_typ().id),
            'objekt': str(self.objekt.id),
            'betreff': 'Test',
        })
        vorgang = Vorgang.objects.get(pk=response.data['id'])
        self.assertEqual(vorgang.erstellt_von, self.user)


class VorgangListeFilterTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='vorgang-filter-tester')
        self.client.force_authenticate(self.user)
        self.objekt1 = _objekt('VW010')
        self.objekt2 = _objekt('VW011')
        self.einheit = Einheit.objects.create(
            objekt=self.objekt1, einheit_nr='WE01', einheit_typ='Wohnung', lage='EG',
        )
        self.v1 = Vorgang.objects.create(
            typ=_typ('maengelmeldung'), betreff='V1', objekt=self.objekt1,
            einheit=self.einheit, erstellt_von=self.user, status='offen', quelle='manuell',
        )
        self.v2 = Vorgang.objects.create(
            typ=_typ('anfrage'), betreff='V2', objekt=self.objekt2,
            erstellt_von=self.user, status='in_bearbeitung', quelle='mail',
        )

    def test_filter_objekt(self):
        response = self.client.get(VORGAENGE, {'objekt': str(self.objekt1.id)})
        ids = {r['id'] for r in response.data}
        self.assertIn(str(self.v1.id), ids)
        self.assertNotIn(str(self.v2.id), ids)

    def test_filter_einheit(self):
        response = self.client.get(VORGAENGE, {'einheit': str(self.einheit.id)})
        ids = {r['id'] for r in response.data}
        self.assertEqual(ids, {str(self.v1.id)})

    def test_filter_status(self):
        response = self.client.get(VORGAENGE, {'status': 'in_bearbeitung'})
        ids = {r['id'] for r in response.data}
        self.assertEqual(ids, {str(self.v2.id)})

    def test_filter_quelle(self):
        response = self.client.get(VORGAENGE, {'quelle': 'mail'})
        ids = {r['id'] for r in response.data}
        self.assertEqual(ids, {str(self.v2.id)})

    def test_filter_typ(self):
        response = self.client.get(VORGAENGE, {'typ': str(_typ('anfrage').id)})
        ids = {r['id'] for r in response.data}
        self.assertEqual(ids, {str(self.v2.id)})

    def test_filter_zugewiesen_an(self):
        self.v2.zugewiesen_an = self.user
        self.v2.save(update_fields=['zugewiesen_an'])
        response = self.client.get(VORGAENGE, {'zugewiesen_an': str(self.user.id)})
        ids = {r['id'] for r in response.data}
        self.assertEqual(ids, {str(self.v2.id)})


class VorgangDetailTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='vorgang-detail-tester')
        self.client.force_authenticate(self.user)
        self.objekt = _objekt('VW020')
        self.vorgang = Vorgang.objects.create(
            typ=_typ(), betreff='Detail-Test', objekt=self.objekt, erstellt_von=self.user,
        )

    def test_detail_enthaelt_ereignisse_und_dokumente(self):
        VorgangEreignis.objects.create(
            vorgang=self.vorgang, typ='kommentar', text='Hallo', erstellt_von=self.user,
        )
        response = self.client.get(f'{VORGAENGE}{self.vorgang.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['ereignisse']), 1)
        self.assertEqual(response.data['dokumente'], [])


class VorgangStatuswechselTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='vorgang-status-tester')
        self.client.force_authenticate(self.user)
        self.objekt = _objekt('VW030')
        self.vorgang = Vorgang.objects.create(
            typ=_typ(), betreff='Status-Test', objekt=self.objekt, erstellt_von=self.user,
        )

    def test_gueltiger_uebergang(self):
        response = self.client.post(
            f'{VORGAENGE}{self.vorgang.id}/status/', {'status': 'in_bearbeitung'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['status'], 'in_bearbeitung')
        self.assertEqual(
            VorgangEreignis.objects.filter(vorgang=self.vorgang, typ='statuswechsel').count(), 1,
        )

    def test_uebergang_nach_wiedervorlage_braucht_datum(self):
        self.vorgang.status = 'in_bearbeitung'
        self.vorgang.save(update_fields=['status'])
        response = self.client.post(
            f'{VORGAENGE}{self.vorgang.id}/status/', {'status': 'wiedervorlage'},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        morgen = (date.today() + timedelta(days=1)).isoformat()
        response = self.client.post(
            f'{VORGAENGE}{self.vorgang.id}/status/',
            {'status': 'wiedervorlage', 'wiedervorlage_am': morgen},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.vorgang.refresh_from_db()
        self.assertEqual(str(self.vorgang.wiedervorlage_am), morgen)

    def test_ungueltiger_uebergang_wird_abgewiesen(self):
        response = self.client.post(
            f'{VORGAENGE}{self.vorgang.id}/status/', {'status': 'erledigt'},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.vorgang.refresh_from_db()
        self.assertEqual(self.vorgang.status, 'offen')


class VorgangKommentarTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='vorgang-kommentar-tester')
        self.client.force_authenticate(self.user)
        self.objekt = _objekt('VW040')
        self.vorgang = Vorgang.objects.create(
            typ=_typ(), betreff='Kommentar-Test', objekt=self.objekt, erstellt_von=self.user,
        )

    def test_kommentar_wird_angelegt(self):
        response = self.client.post(
            f'{VORGAENGE}{self.vorgang.id}/kommentar/', {'text': 'Rückruf erfolgt'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        ereignis = VorgangEreignis.objects.get(vorgang=self.vorgang, typ='kommentar')
        self.assertEqual(ereignis.text, 'Rückruf erfolgt')

    def test_leerer_kommentar_wird_abgewiesen(self):
        response = self.client.post(f'{VORGAENGE}{self.vorgang.id}/kommentar/', {'text': ''})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_kommentar_ohne_angabe_ist_intern(self):
        self.client.post(f'{VORGAENGE}{self.vorgang.id}/kommentar/', {'text': 'Intern'})
        ereignis = VorgangEreignis.objects.get(vorgang=self.vorgang, text='Intern')
        self.assertTrue(ereignis.intern)

    def test_kommentar_mit_sichtbar_fuer_eigentuemer_ist_nicht_intern(self):
        self.client.post(
            f'{VORGAENGE}{self.vorgang.id}/kommentar/',
            {'text': 'Für den Eigentümer', 'sichtbar_fuer_eigentuemer': True},
        )
        ereignis = VorgangEreignis.objects.get(vorgang=self.vorgang, text='Für den Eigentümer')
        self.assertFalse(ereignis.intern)


class VorgangZuweisenTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='vorgang-zuweisen-tester')
        self.anderer_user = User.objects.create_user(username='vorgang-zuweisen-ziel')
        self.client.force_authenticate(self.user)
        self.objekt = _objekt('VW050')
        self.vorgang = Vorgang.objects.create(
            typ=_typ(), betreff='Zuweisen-Test', objekt=self.objekt, erstellt_von=self.user,
        )

    def test_zuweisung_setzen(self):
        response = self.client.post(
            f'{VORGAENGE}{self.vorgang.id}/zuweisen/', {'user_id': str(self.anderer_user.id)},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.vorgang.refresh_from_db()
        self.assertEqual(self.vorgang.zugewiesen_an, self.anderer_user)

    def test_zuweisung_aufheben_mit_null(self):
        self.vorgang.zugewiesen_an = self.anderer_user
        self.vorgang.save(update_fields=['zugewiesen_an'])
        response = self.client.post(
            f'{VORGAENGE}{self.vorgang.id}/zuweisen/', {'user_id': ''},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.vorgang.refresh_from_db()
        self.assertIsNone(self.vorgang.zugewiesen_an)


class VorgangDokumentUploadTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='vorgang-dokument-tester')
        self.client.force_authenticate(self.user)
        self.objekt = _objekt('VW060')
        self.vorgang = Vorgang.objects.create(
            typ=_typ(), betreff='Dokument-Test', objekt=self.objekt, erstellt_von=self.user,
        )

    def _upload(self, inhalt=b'Testinhalt', name='beleg.pdf'):
        from django.core.files.uploadedfile import SimpleUploadedFile
        datei = SimpleUploadedFile(name, inhalt, content_type='application/pdf')
        return self.client.post(
            f'{VORGAENGE}{self.vorgang.id}/dokumente/', {'datei': datei}, format='multipart',
        )

    def test_upload_ohne_duplikat(self):
        response = self._upload()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertFalse(response.data['duplikat_warnung'])
        self.assertEqual(response.data['dokument']['dateiname'], 'beleg.pdf')

    def test_upload_mit_duplikat_warnung(self):
        self._upload(inhalt=b'Gleicher Inhalt', name='a.pdf')
        response = self._upload(inhalt=b'Gleicher Inhalt', name='a-kopie.pdf')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(response.data['duplikat_warnung'])


class VorgangTypenListeTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='vorgang-typen-tester')
        self.client.force_authenticate(self.user)

    def test_nur_aktive_typen(self):
        inaktiv = _typ('sonstiges')
        inaktiv.aktiv = False
        inaktiv.save(update_fields=['aktiv'])

        response = self.client.get(VORGANG_TYPEN)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = {t['code'] for t in response.data}
        self.assertNotIn('sonstiges', codes)
        self.assertIn('maengelmeldung', codes)


class VorgangTypAdminTest(APITestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(username='vorgang-typ-admin', is_staff=True)
        self.normal_user = User.objects.create_user(username='vorgang-typ-normal', is_staff=False)

    def test_non_staff_wird_abgewiesen(self):
        self.client.force_authenticate(self.normal_user)
        response = self.client.get(VORGANG_TYPEN_ADMIN)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_kann_typ_anlegen_und_patchen(self):
        self.client.force_authenticate(self.staff_user)
        response = self.client.post(VORGANG_TYPEN_ADMIN, {
            'code': 'testtyp-admin', 'bezeichnung': 'Admin-Test-Typ',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        typ_id = response.data['id']

        response = self.client.patch(f'{VORGANG_TYPEN_ADMIN}{typ_id}/', {'aktiv': False})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertFalse(response.data['aktiv'])

    def test_staff_sieht_auch_inaktive_typen_in_admin_liste(self):
        self.client.force_authenticate(self.staff_user)
        inaktiv = _typ('sonstiges')
        inaktiv.aktiv = False
        inaktiv.save(update_fields=['aktiv'])

        response = self.client.get(VORGANG_TYPEN_ADMIN)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = {t['code'] for t in response.data}
        self.assertIn('sonstiges', codes)


class VorgangPortalSichtbarTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='vorgang-portal-sichtbar-tester')
        self.client.force_authenticate(self.user)
        self.objekt = _objekt('VW070')
        self.vorgang = Vorgang.objects.create(
            typ=_typ(), betreff='Portal-Sichtbar-Test', objekt=self.objekt, erstellt_von=self.user,
        )

    def test_setzen_auf_true(self):
        response = self.client.post(
            f'{VORGAENGE}{self.vorgang.id}/portal-sichtbar/', {'portal_sichtbar': True},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.vorgang.refresh_from_db()
        self.assertTrue(self.vorgang.portal_sichtbar)

    def test_zuruecksetzen_auf_false(self):
        self.vorgang.portal_sichtbar = True
        self.vorgang.save(update_fields=['portal_sichtbar'])
        response = self.client.post(
            f'{VORGAENGE}{self.vorgang.id}/portal-sichtbar/', {'portal_sichtbar': False},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.vorgang.refresh_from_db()
        self.assertFalse(self.vorgang.portal_sichtbar)


class VorgangPortalVorschauTest(APITestCase):
    """Deckt den Mitarbeiter-Vorschau-Endpunkt ``portal-vorschau`` ab —
    ausdrücklich ``IsAuthenticated``, KEIN ``AllowAny``."""

    def setUp(self):
        self.user = User.objects.create_user(username='vorgang-portal-vorschau-tester')
        self.objekt = _objekt('VW080')
        self.vorgang = Vorgang.objects.create(
            typ=_typ(), betreff='Portal-Vorschau-Test', objekt=self.objekt, erstellt_von=self.user,
        )

    def test_ohne_login_wird_abgewiesen(self):
        response = self.client.get(f'{VORGAENGE}{self.vorgang.id}/portal-vorschau/')
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_mit_login_erfolgreich(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(f'{VORGAENGE}{self.vorgang.id}/portal-vorschau/')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_ohne_portal_sichtbar_liefert_nichts_inhaltliches(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(f'{VORGAENGE}{self.vorgang.id}/portal-vorschau/')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data, {'sichtbar': False})

    def test_mit_portal_sichtbar_liefert_erwartete_ereignisse(self):
        self.client.force_authenticate(self.user)
        self.vorgang.portal_sichtbar = True
        self.vorgang.save(update_fields=['portal_sichtbar'])

        VorgangEreignis.objects.create(
            vorgang=self.vorgang, typ='kommentar', text='Intern', erstellt_von=self.user, intern=True,
        )
        VorgangEreignis.objects.create(
            vorgang=self.vorgang, typ='kommentar', text='Sichtbar', erstellt_von=self.user, intern=False,
        )
        for typ in (
            'handwerker_beauftragt', 'handwerker_angenommen', 'handwerker_abgelehnt',
            'handwerker_abgeschlossen', 'handwerker_abgelaufen',
        ):
            VorgangEreignis.objects.create(
                vorgang=self.vorgang, typ=typ, text=f'{typ}-text', intern=False,
            )
        VorgangEreignis.objects.create(
            vorgang=self.vorgang, typ='zuweisung_geaendert', erstellt_von=self.user, intern=True,
        )

        response = self.client.get(f'{VORGAENGE}{self.vorgang.id}/portal-vorschau/')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        typen = [e['typ'] for e in response.data['ereignisse']]

        self.assertIn('kommentar', typen)
        self.assertIn('handwerker_beauftragt', typen)
        self.assertIn('handwerker_angenommen', typen)
        self.assertIn('handwerker_abgelehnt', typen)
        self.assertIn('handwerker_abgeschlossen', typen)
        self.assertIn('handwerker_abgelaufen', typen)
        self.assertNotIn('zuweisung_geaendert', typen)

        texte = [e['text'] for e in response.data['ereignisse']]
        self.assertNotIn('Intern', texte)
        self.assertIn('Sichtbar', texte)
