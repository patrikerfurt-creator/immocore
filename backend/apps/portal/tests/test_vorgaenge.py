"""
Tests für die Portal-Vorgangs-Endpunkte (Spec Portal-Erweiterung v1.1,
Kap. 4/5) — Liste, Detail, Anlage und die Sichtbarkeitsregel (Kap. 4.2).
"""
from datetime import date, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.portal.services import zugang_service
from apps.vorgaenge.models import Vorgang, VorgangTyp
from apps.vorgaenge.services import vorgang_service

from .basis import (
    erstelle_eigentuemer,
    erstelle_einheit,
    erstelle_objekt,
    verknuepfe,
)

VORGANG_TYPEN_URL = '/api/v1/portal/vorgang-typen/'
VORGAENGE_URL = '/api/v1/portal/vorgaenge/'

User = get_user_model()


def _detail_url(vorgang_id):
    return f'/api/v1/portal/vorgaenge/{vorgang_id}/'


def _mitarbeiter(username='vorgang-tester'):
    return User.objects.create_user(username=username, password='x')


def _typ(code='portal-melde', portal_erstellbar=True, aktiv=True, antwort_vorschlag_aktiv=False):
    return VorgangTyp.objects.create(
        code=code, bezeichnung='Mängelmeldung', portal_erstellbar=portal_erstellbar,
        aktiv=aktiv, antwort_vorschlag_aktiv=antwort_vorschlag_aktiv,
    )


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PortalVorgangTypenTest(APITestCase):
    """Deckt den Filter (``portal_erstellbar=True``, ``aktiv=True``) und die
    Sortierung von ``GET /portal/vorgang-typen/`` ab."""

    def setUp(self):
        cache.clear()
        self.person = erstelle_eigentuemer(personennummer='P-TYP-A')
        _, token = zugang_service.lade_ein(self.person)
        session, _, _ = zugang_service.melde_an(token.token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Portal {session.token}')

        self.sichtbar = VorgangTyp.objects.create(
            code='typ-sichtbar', bezeichnung='Mängelmeldung',
            portal_erstellbar=True, aktiv=True, sortierung=1,
        )
        VorgangTyp.objects.create(
            code='typ-inaktiv', bezeichnung='Inaktiv', portal_erstellbar=True, aktiv=False,
        )
        VorgangTyp.objects.create(
            code='typ-nicht-portal', bezeichnung='Nur intern', portal_erstellbar=False, aktiv=True,
        )

    def test_liefert_nur_aktive_portal_erstellbare_typen(self):
        response = self.client.get(VORGANG_TYPEN_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            [{'id': str(self.sichtbar.id), 'bezeichnung': 'Mängelmeldung'}],
        )


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PortalVorgaengeSichtbarkeitTest(APITestCase):
    """Test 1 der Spec — Sichtbarkeitsregel Kap. 4.2 samt Gegenproben."""

    def setUp(self):
        cache.clear()
        self.mitarbeiter = _mitarbeiter()
        self.typ = _typ()

        self.person_a = erstelle_eigentuemer(
            nachname='Ampel', email='a@example.org', personennummer='P-VG-A',
        )
        self.person_b = erstelle_eigentuemer(
            nachname='Bemme', email='b@example.org', personennummer='P-VG-B',
        )

        self.weg_a = erstelle_objekt('VG-A', 'WEG Vorgangsweg 1')
        self.einheit_a1 = erstelle_einheit(self.weg_a, '0001')
        self.einheit_a2 = erstelle_einheit(self.weg_a, '0002')  # fremde Einheit, gleiches Objekt
        self.weg_b = erstelle_objekt('VG-B', 'WEG Vorgangsweg 2')
        self.einheit_b1 = erstelle_einheit(self.weg_b, '0001')

        verknuepfe(self.person_a, self.einheit_a1)
        verknuepfe(self.person_b, self.einheit_a2)
        verknuepfe(self.person_b, self.einheit_b1)

        _, token = zugang_service.lade_ein(self.person_a)
        session, _, _ = zugang_service.melde_an(token.token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Portal {session.token}')

        # Sichtbar: eigene Einheit, portal_sichtbar=True.
        self.sichtbar_eigene_einheit = vorgang_service.erstelle_vorgang(
            typ=self.typ, betreff='Wasserschaden', erstellt_von=self.mitarbeiter,
            objekt=self.weg_a, einheit=self.einheit_a1, portal_sichtbar=True,
        )
        # Nicht sichtbar: eigene Einheit, aber portal_sichtbar=False.
        self.nicht_freigegeben = vorgang_service.erstelle_vorgang(
            typ=self.typ, betreff='Interner Vermerk', erstellt_von=self.mitarbeiter,
            objekt=self.weg_a, einheit=self.einheit_a1, portal_sichtbar=False,
        )
        # Nicht sichtbar: fremde Einheit in fremdem Objekt.
        self.fremdes_objekt = vorgang_service.erstelle_vorgang(
            typ=self.typ, betreff='Fremde WEG', erstellt_von=self.mitarbeiter,
            objekt=self.weg_b, einheit=self.einheit_b1, portal_sichtbar=True,
        )
        # Sichtbar: einheitenloser Vorgang der eigenen WEG.
        self.einheitenlos_eigene_weg = vorgang_service.erstelle_vorgang(
            typ=self.typ, betreff='Beschluss WEG Vorgangsweg 1', erstellt_von=self.mitarbeiter,
            objekt=self.weg_a, portal_sichtbar=True,
        )
        # Nicht sichtbar: fremde Einheit im SELBEN Objekt (Nachbareinheit).
        self.fremde_einheit_selbes_objekt = vorgang_service.erstelle_vorgang(
            typ=self.typ, betreff='Nachbarwohnung', erstellt_von=self.mitarbeiter,
            objekt=self.weg_a, einheit=self.einheit_a2, portal_sichtbar=True,
        )

    def test_liefert_nur_eigene_freigegebene_vorgaenge(self):
        response = self.client.get(VORGAENGE_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {eintrag['id'] for eintrag in response.data}
        self.assertEqual(
            ids,
            {str(self.sichtbar_eigene_einheit.id), str(self.einheitenlos_eigene_weg.id)},
        )

    def test_antwort_ist_reine_liste_ohne_pagination(self):
        response = self.client.get(VORGAENGE_URL)
        self.assertIsInstance(response.data, list)

    def test_person_zweig_macht_eigenen_vorgang_ohne_einheit_sichtbar(self):
        eigener_ohne_einheit = vorgang_service.erstelle_vorgang(
            typ=self.typ, betreff='Direkte Anfrage', erstellt_von=self.mitarbeiter,
            person=self.person_a, portal_sichtbar=True,
        )
        response = self.client.get(VORGAENGE_URL)
        ids = {eintrag['id'] for eintrag in response.data}
        self.assertIn(str(eigener_ohne_einheit.id), ids)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PortalVorgangDetailTest(APITestCase):
    """Test 2 der Spec."""

    def setUp(self):
        cache.clear()
        self.mitarbeiter = _mitarbeiter('detail-tester')
        self.typ = _typ(code='portal-detail')

        self.person_a = erstelle_eigentuemer(
            nachname='Ampel', email='a2@example.org', personennummer='P-DT-A',
        )
        self.person_b = erstelle_eigentuemer(
            nachname='Bemme', email='b2@example.org', personennummer='P-DT-B',
        )
        self.weg_a = erstelle_objekt('DT-A', 'WEG Detailweg 1')
        self.einheit_a = erstelle_einheit(self.weg_a, '0001')
        self.weg_b = erstelle_objekt('DT-B', 'WEG Detailweg 2')
        self.einheit_b = erstelle_einheit(self.weg_b, '0001')
        verknuepfe(self.person_a, self.einheit_a)
        verknuepfe(self.person_b, self.einheit_b)

        _, token = zugang_service.lade_ein(self.person_a)
        session, _, _ = zugang_service.melde_an(token.token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Portal {session.token}')

        self.eigener_vorgang = vorgang_service.erstelle_vorgang(
            typ=self.typ, betreff='Heizungsausfall', beschreibung='Details zum Ausfall.',
            erstellt_von=self.mitarbeiter, objekt=self.weg_a, einheit=self.einheit_a,
            portal_sichtbar=True,
        )
        self.fremder_vorgang = vorgang_service.erstelle_vorgang(
            typ=self.typ, betreff='Fremdes Anliegen', erstellt_von=self.mitarbeiter,
            objekt=self.weg_b, einheit=self.einheit_b, portal_sichtbar=True,
        )

    def test_eigener_vorgang_liefert_details(self):
        response = self.client.get(_detail_url(self.eigener_vorgang.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['betreff'], 'Heizungsausfall')
        self.assertEqual(response.data['beschreibung'], 'Details zum Ausfall.')

    def test_fremder_vorgang_liefert_404(self):
        response = self.client.get(_detail_url(self.fremder_vorgang.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unbekannte_id_liefert_404(self):
        import uuid
        response = self.client.get(_detail_url(uuid.uuid4()))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PortalVorgangAnlageTest(APITestCase):
    """Tests 3-5 der Spec plus Anlage für eine beendete EV."""

    def setUp(self):
        cache.clear()
        self.mitarbeiter = _mitarbeiter('anlage-tester')

        self.person_a = erstelle_eigentuemer(
            nachname='Ampel', email='a3@example.org', personennummer='P-AN-A',
        )
        self.person_b = erstelle_eigentuemer(
            nachname='Bemme', email='b3@example.org', personennummer='P-AN-B',
        )
        self.weg_a = erstelle_objekt('AN-A', 'WEG Anlageweg 1')
        self.einheit_a = erstelle_einheit(self.weg_a, '0001')
        self.weg_b = erstelle_objekt('AN-B', 'WEG Anlageweg 2')
        self.einheit_b = erstelle_einheit(self.weg_b, '0001')
        verknuepfe(self.person_a, self.einheit_a)
        verknuepfe(self.person_b, self.einheit_b)

        _, token = zugang_service.lade_ein(self.person_a)
        session, _, _ = zugang_service.melde_an(token.token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Portal {session.token}')

        self.typ = _typ(code='portal-anlage')

    def test_anlage_mit_fremder_einheit_liefert_400_und_legt_nichts_an(self):
        anzahl_vorher = Vorgang.objects.count()
        response = self.client.post(VORGAENGE_URL, {
            'typ_id': str(self.typ.id),
            'betreff': 'Sollte nicht funktionieren',
            'einheit_id': str(self.einheit_b.id),
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Vorgang.objects.count(), anzahl_vorher)

    def test_anlage_mit_nicht_portal_erstellbarem_typ_liefert_400(self):
        typ_gesperrt = _typ(code='portal-gesperrt', portal_erstellbar=False)
        response = self.client.post(VORGAENGE_URL, {
            'typ_id': str(typ_gesperrt.id),
            'betreff': 'Sollte nicht funktionieren',
            'einheit_id': str(self.einheit_a.id),
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_anlage_mit_inaktivem_typ_liefert_400(self):
        typ_inaktiv = _typ(code='portal-inaktiv', aktiv=False)
        response = self.client.post(VORGAENGE_URL, {
            'typ_id': str(typ_inaktiv.id),
            'betreff': 'Sollte nicht funktionieren',
            'einheit_id': str(self.einheit_a.id),
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_anlage_mit_beendeter_ev_liefert_400(self):
        weg_alt = erstelle_objekt('AN-ALT', 'WEG Verkauft')
        einheit_alt = erstelle_einheit(weg_alt, '0001')
        verknuepfe(
            self.person_a, einheit_alt,
            beginn=date(2018, 1, 1), ende=date(2020, 12, 31),
        )
        response = self.client.post(VORGAENGE_URL, {
            'typ_id': str(self.typ.id),
            'betreff': 'Nachfrage zur Schlussabrechnung',
            'einheit_id': str(einheit_alt.id),
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_anlage_setzt_erwartete_felder_und_loest_ki_task_aus(self):
        typ_mit_ki = _typ(code='portal-ki', antwort_vorschlag_aktiv=True)
        with mock.patch('apps.vorgaenge.tasks.erzeuge_antwort_vorschlag.delay') as delay:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(VORGAENGE_URL, {
                    'typ_id': str(typ_mit_ki.id),
                    'betreff': 'Klingel defekt',
                    'beschreibung': 'Die Klingel an Wohnung 1 funktioniert nicht.',
                    'einheit_id': str(self.einheit_a.id),
                }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        vorgang = Vorgang.objects.get(id=response.data['id'])
        self.assertEqual(vorgang.quelle, 'portal')
        self.assertTrue(vorgang.portal_sichtbar)
        self.assertEqual(vorgang.person_id, self.person_a.id)
        self.assertEqual(vorgang.objekt_id, self.einheit_a.objekt_id)
        self.assertEqual(vorgang.status, 'offen')
        self.assertEqual(vorgang.prioritaet, typ_mit_ki.standard_prioritaet)
        delay.assert_called_once_with(str(vorgang.id))


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PortalVorgangDatenschutzTest(APITestCase):
    """Tests 6 und 7 der Spec — keine internen Ereignisse/Felder in der Antwort."""

    def setUp(self):
        cache.clear()
        self.mitarbeiter = _mitarbeiter('datenschutz-tester')
        self.zweiter_mitarbeiter = _mitarbeiter('datenschutz-tester-2')
        self.typ = _typ(code='portal-datenschutz')

        self.person_a = erstelle_eigentuemer(
            nachname='Ampel', email='a4@example.org', personennummer='P-DS-A',
        )
        self.weg_a = erstelle_objekt('DS-A', 'WEG Datenschutzweg 1')
        self.einheit_a = erstelle_einheit(self.weg_a, '0001')
        verknuepfe(self.person_a, self.einheit_a)

        _, token = zugang_service.lade_ein(self.person_a)
        session, _, _ = zugang_service.melde_an(token.token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Portal {session.token}')

        self.vorgang = vorgang_service.erstelle_vorgang(
            typ=self.typ, betreff='Feuchtigkeit im Keller', erstellt_von=self.mitarbeiter,
            objekt=self.weg_a, einheit=self.einheit_a, portal_sichtbar=True,
            faellig_am=date.today() + timedelta(days=7),
            mail_referenz='<abc@example.org>', telefon_rufnummer='0151 1234567',
        )
        vorgang_service.weise_zu(self.vorgang, self.zweiter_mitarbeiter, self.mitarbeiter)
        vorgang_service.kommentiere(self.vorgang, 'Interner Vermerk', self.mitarbeiter, intern=True)
        vorgang_service.kommentiere(self.vorgang, 'Wir kümmern uns darum.', self.mitarbeiter, intern=False)
        vorgang_service.wechsle_status(self.vorgang, 'in_bearbeitung', erstellt_von=self.mitarbeiter)

    def test_interne_ereignisse_erscheinen_nicht_in_der_detailantwort(self):
        response = self.client.get(_detail_url(self.vorgang.id))
        texte = [ereignis['text'] for ereignis in response.data['ereignisse']]
        self.assertIn('Wir kümmern uns darum.', texte)
        self.assertNotIn('Interner Vermerk', texte)
        typen = [ereignis['typ'] for ereignis in response.data['ereignisse']]
        self.assertNotIn('zuweisung_geaendert', typen)

    def test_antwort_enthaelt_keinen_antwort_vorschlag(self):
        response = self.client.get(_detail_url(self.vorgang.id))
        self.assertNotIn('antwort_vorschlag', response.data)
        for ereignis in response.data['ereignisse']:
            self.assertNotIn('antwort_vorschlag', str(ereignis).lower())

    def test_interne_felder_fehlen_in_liste_und_detail(self):
        verbotene_felder = [
            'zugewiesen_an', 'wiedervorlage_am', 'mail_referenz',
            'telefon_rufnummer', 'erstellt_von', 'geschlossen_von',
            'status_anzeige',
        ]
        liste = self.client.get(VORGAENGE_URL)
        for eintrag in liste.data:
            for feld in verbotene_felder:
                self.assertNotIn(feld, eintrag)

        detail = self.client.get(_detail_url(self.vorgang.id))
        for feld in verbotene_felder:
            self.assertNotIn(feld, detail.data)
