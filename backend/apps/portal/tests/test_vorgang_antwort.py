"""Tests für ``POST /api/v1/portal/vorgaenge/<id>/antwort/`` — die Rückantwort
des Eigentümers auf einen bestehenden Vorgang (Chat-Umbau).

Deckt ab:
  - eigener, freigegebener Vorgang: 201 + Ereignis ``portal_antwort``
    (intern=False, damit es im Chat UND im Portal erscheint).
  - fremder/nicht freigegebener Vorgang: 404 (keine Existenzbestätigung).
  - leerer Text: 400.
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.portal.services import zugang_service
from apps.vorgaenge.models import VorgangEreignis, VorgangTyp
from apps.vorgaenge.services import vorgang_service

from .basis import erstelle_eigentuemer, erstelle_einheit, erstelle_objekt, verknuepfe

User = get_user_model()


def _antwort_url(vorgang_id):
    return f'/api/v1/portal/vorgaenge/{vorgang_id}/antwort/'


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PortalVorgangAntwortTest(APITestCase):
    def setUp(self):
        cache.clear()
        self.mitarbeiter = User.objects.create_user(username='antwort-tester', password='x')
        self.typ = VorgangTyp.objects.create(
            code='portal-antwort', bezeichnung='Mängelmeldung',
            portal_erstellbar=True, aktiv=True,
        )

        self.person_a = erstelle_eigentuemer(nachname='Ampel', email='a@example.org', personennummer='P-AN-A')
        self.person_b = erstelle_eigentuemer(nachname='Bemme', email='b@example.org', personennummer='P-AN-B')
        self.weg_a = erstelle_objekt('AN-A', 'WEG Antwortweg 1')
        self.einheit_a = erstelle_einheit(self.weg_a, '0001')
        self.weg_b = erstelle_objekt('AN-B', 'WEG Antwortweg 2')
        self.einheit_b = erstelle_einheit(self.weg_b, '0001')
        verknuepfe(self.person_a, self.einheit_a)
        verknuepfe(self.person_b, self.einheit_b)

        _, token = zugang_service.lade_ein(self.person_a)
        session, _, _ = zugang_service.melde_an(token.token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Portal {session.token}')

        self.eigener = vorgang_service.erstelle_vorgang(
            typ=self.typ, betreff='Heizung', erstellt_von=self.mitarbeiter,
            objekt=self.weg_a, einheit=self.einheit_a, portal_sichtbar=True,
        )
        self.fremder = vorgang_service.erstelle_vorgang(
            typ=self.typ, betreff='Fremd', erstellt_von=self.mitarbeiter,
            objekt=self.weg_b, einheit=self.einheit_b, portal_sichtbar=True,
        )
        self.nicht_freigegeben = vorgang_service.erstelle_vorgang(
            typ=self.typ, betreff='Intern', erstellt_von=self.mitarbeiter,
            objekt=self.weg_a, einheit=self.einheit_a, portal_sichtbar=False,
        )

    def test_eigener_vorgang_nimmt_antwort_an(self):
        resp = self.client.post(_antwort_url(self.eigener.id), {'text': 'Danke, passt.'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        ereignis = VorgangEreignis.objects.get(vorgang=self.eigener, typ='portal_antwort')
        self.assertFalse(ereignis.intern)
        self.assertEqual(ereignis.text, 'Danke, passt.')

    def test_fremder_vorgang_404(self):
        resp = self.client.post(_antwort_url(self.fremder.id), {'text': 'Hallo'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(VorgangEreignis.objects.filter(vorgang=self.fremder, typ='portal_antwort').exists())

    def test_nicht_freigegebener_vorgang_404(self):
        resp = self.client.post(_antwort_url(self.nicht_freigegeben.id), {'text': 'Hallo'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_leerer_text_400(self):
        resp = self.client.post(_antwort_url(self.eigener.id), {'text': '   '}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
