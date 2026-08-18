"""
API-Tests für den KI-Antwortvorschlag (Folgeauftrag, nicht Teil der
ursprünglichen Vorgang & DMS-Spec).

Endpunkte:
  POST  /api/v1/vorgaenge/{id}/antwort-vorschlag/           — neu generieren
  PATCH /api/v1/vorgaenge/{id}/antwort-vorschlag/           — Text bearbeiten
  POST  /api/v1/vorgaenge/{id}/antwort-vorschlag/freigeben/ — freigeben
  POST  /api/v1/vorgaenge/{id}/antwort-vorschlag/verwerfen/ — verwerfen

Der Anthropic-Client wird in jedem Test gemockt.
"""
from datetime import date
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.objekte.models import Objekt
from apps.vorgaenge.models import Vorgang, VorgangAntwortVorschlag, VorgangEreignis, VorgangTyp

User = get_user_model()


def _objekt(nr='AA001'):
    return Objekt.objects.create(
        bezeichnung='Test-WEG Antwort-API', objektnummer=nr, objekt_typ='weg',
        ort='Teststadt', verwaltung_seit=date(2020, 1, 1),
    )


def _typ(code='anfrage'):
    return VorgangTyp.objects.get(code=code)


def _mock_anthropic_response(text='Sehr geehrte Damen und Herren,\n\nvielen Dank für Ihre Nachricht.\n\nMit freundlichen Grüßen'):
    block = MagicMock()
    block.type = 'text'
    block.text = text
    message = MagicMock()
    message.content = [block]
    return message


class AntwortVorschlagGenerierenTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='antwort-api-generieren-tester')
        self.client.force_authenticate(self.user)
        self.objekt = _objekt()
        self.vorgang = Vorgang.objects.create(
            typ=_typ(), betreff='Test', objekt=self.objekt, erstellt_von=self.user,
        )

    @patch('anthropic.Anthropic')
    def test_generieren_legt_entwurf_an(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response()
        mock_anthropic_cls.return_value = mock_client

        with self.settings(ANTHROPIC_API_KEY='dummy-key'):
            response = self.client.post(f'/api/v1/vorgaenge/{self.vorgang.id}/antwort-vorschlag/')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['status'], 'entwurf')
        self.assertTrue(response.data['text'])

    def test_generieren_ohne_api_key_liefert_fehlgeschlagen(self):
        with self.settings(ANTHROPIC_API_KEY=''):
            response = self.client.post(f'/api/v1/vorgaenge/{self.vorgang.id}/antwort-vorschlag/')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['status'], 'fehlgeschlagen')

    @patch('anthropic.Anthropic')
    def test_vorgang_detail_enthaelt_aktuellen_vorschlag(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response()
        mock_anthropic_cls.return_value = mock_client

        with self.settings(ANTHROPIC_API_KEY='dummy-key'):
            self.client.post(f'/api/v1/vorgaenge/{self.vorgang.id}/antwort-vorschlag/')

        response = self.client.get(f'/api/v1/vorgaenge/{self.vorgang.id}/')
        self.assertIsNotNone(response.data['antwort_vorschlag'])
        self.assertEqual(response.data['antwort_vorschlag']['status'], 'entwurf')


class AntwortVorschlagBearbeitenTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='antwort-api-bearbeiten-tester')
        self.client.force_authenticate(self.user)
        self.objekt = _objekt('AA010')
        self.vorgang = Vorgang.objects.create(
            typ=_typ(), betreff='Test', objekt=self.objekt, erstellt_von=self.user,
        )
        self.vorschlag = VorgangAntwortVorschlag.objects.create(
            vorgang=self.vorgang, text_ki='KI-Text', text='KI-Text', status='entwurf',
        )

    def test_bearbeiten_aendert_text(self):
        response = self.client.patch(
            f'/api/v1/vorgaenge/{self.vorgang.id}/antwort-vorschlag/',
            {'text': 'Bearbeiteter Text'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.vorschlag.refresh_from_db()
        self.assertEqual(self.vorschlag.text, 'Bearbeiteter Text')
        self.assertEqual(self.vorschlag.text_ki, 'KI-Text')

    def test_bearbeiten_ohne_entwurf_liefert_400(self):
        self.vorschlag.status = 'freigegeben'
        self.vorschlag.save(update_fields=['status'])
        response = self.client.patch(
            f'/api/v1/vorgaenge/{self.vorgang.id}/antwort-vorschlag/',
            {'text': 'Neuer Text'},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class AntwortVorschlagFreigebenTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='antwort-api-freigeben-tester')
        self.client.force_authenticate(self.user)
        self.objekt = _objekt('AA020')
        self.vorgang = Vorgang.objects.create(
            typ=_typ(), betreff='Test', objekt=self.objekt, erstellt_von=self.user,
        )
        self.vorschlag = VorgangAntwortVorschlag.objects.create(
            vorgang=self.vorgang, text_ki='KI-Text', text='Freizugebender Text', status='entwurf',
        )

    def test_freigeben_setzt_status_und_ereignis(self):
        response = self.client.post(
            f'/api/v1/vorgaenge/{self.vorgang.id}/antwort-vorschlag/freigeben/',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['status'], 'freigegeben')
        ereignis = VorgangEreignis.objects.get(
            vorgang=self.vorgang, typ='antwort_vorschlag_freigegeben',
        )
        self.assertEqual(ereignis.text, 'Freizugebender Text')

    def test_doppelte_freigabe_liefert_400(self):
        self.client.post(f'/api/v1/vorgaenge/{self.vorgang.id}/antwort-vorschlag/freigeben/')
        response = self.client.post(
            f'/api/v1/vorgaenge/{self.vorgang.id}/antwort-vorschlag/freigeben/',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_freigeben_ohne_entwurf_liefert_400(self):
        self.vorschlag.status = 'verworfen'
        self.vorschlag.save(update_fields=['status'])
        response = self.client.post(
            f'/api/v1/vorgaenge/{self.vorgang.id}/antwort-vorschlag/freigeben/',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class AntwortVorschlagVerwerfenTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='antwort-api-verwerfen-tester')
        self.client.force_authenticate(self.user)
        self.objekt = _objekt('AA030')
        self.vorgang = Vorgang.objects.create(
            typ=_typ(), betreff='Test', objekt=self.objekt, erstellt_von=self.user,
        )
        self.vorschlag = VorgangAntwortVorschlag.objects.create(
            vorgang=self.vorgang, text_ki='KI-Text', text='KI-Text', status='entwurf',
        )

    def test_verwerfen_setzt_status(self):
        response = self.client.post(
            f'/api/v1/vorgaenge/{self.vorgang.id}/antwort-vorschlag/verwerfen/',
            {'grund': 'Nicht mehr relevant'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['status'], 'verworfen')
        ereignis = VorgangEreignis.objects.get(
            vorgang=self.vorgang, typ='antwort_vorschlag_verworfen',
        )
        self.assertEqual(ereignis.text, 'Nicht mehr relevant')

    def test_doppeltes_verwerfen_liefert_400(self):
        self.client.post(f'/api/v1/vorgaenge/{self.vorgang.id}/antwort-vorschlag/verwerfen/')
        response = self.client.post(
            f'/api/v1/vorgaenge/{self.vorgang.id}/antwort-vorschlag/verwerfen/',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
