"""
Tests für die Zuordnungs-Vorschläge beim manuellen Upload.

Zwei Dienste wirken zusammen:
  - ``kontext_vorschlag_service`` schlägt den Owner (Objekt/Einheit/Person) vor,
  - ``register_vorschlag_service`` das Aktenregister.

Der Endpunkt ``POST /dokumente/upload-vorschlag/`` führt beides zusammen, SETZT
aber nichts — deshalb liegt der Schwerpunkt hier auf: richtiger Vorschlag,
sauberer Rückzug ohne Treffer, und vor allem die deterministische Auflösung,
die eine halluzinierte KI-Antwort ins Leere laufen lässt.
"""
import json
import shutil
import tempfile
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.dokumente.services import kontext_vorschlag_service, upload_analyse_service
from apps.objekte.models import Einheit, Objekt
from apps.personen.models import Person

User = get_user_model()

_MEDIA_TMP = tempfile.mkdtemp(prefix="immocore_test_media_uploadvorschlag_")


def tearDownModule():
    shutil.rmtree(_MEDIA_TMP, ignore_errors=True)


def ki_kontext_antwort(**felder):
    """Baut eine Claude-Antwort für den Kontextdienst (JSON-Textblock)."""
    class Block:
        type = 'text'

        def __init__(self, text):
            self.text = text

    class Antwort:
        def __init__(self, text):
            self.content = [Block(text)]

    daten = {'objektnummer': None, 'objektadresse': None, 'person_name': None,
             'einheit': None, 'konfidenz': 0.9, 'begruendung': 'Test'}
    daten.update(felder)
    return Antwort(json.dumps(daten))


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class KontextVorschlagTest(TestCase):
    def setUp(self):
        self.objekt = Objekt.objects.create(
            bezeichnung='WEG Musterstraße', objektnummer='UV001', objekt_typ='weg',
            strasse='Musterstraße 12', plz='99999', ort='Teststadt',
            verwaltung_seit=date(2015, 1, 1))

    # -- Stufe 1: Dateiname, ohne KI --------------------------------------

    def test_objektnummer_im_dateinamen_ohne_ki(self):
        with patch('anthropic.Anthropic') as mock_api:
            erg = kontext_vorschlag_service.schlage_kontext_vor(
                'UV001_Wartungsvertrag.pdf', inhalt_text='egal')
        self.assertEqual(erg['owner'], 'objekt')
        self.assertEqual(erg['objekt'], self.objekt)
        self.assertEqual(erg['quelle'], 'dateiname')
        mock_api.assert_not_called()

    def test_kein_treffer_im_dateinamen_ohne_ki_bleibt_leer(self):
        # Ohne KI-Schlüssel darf Stufe 2 nicht hart fehlschlagen.
        with override_settings(ANTHROPIC_API_KEY=''):
            erg = kontext_vorschlag_service.schlage_kontext_vor(
                'voellig-neutral.pdf', inhalt_text='nichts Erkennbares')
        self.assertIsNone(erg['owner'])
        self.assertIsNone(erg['objekt'])

    # -- Stufe 2: KI über den Inhalt, deterministisch aufgelöst -----------

    @override_settings(ANTHROPIC_API_KEY='test-key')
    def test_ki_adresse_wird_zu_objekt_aufgeloest(self):
        with patch('anthropic.Anthropic') as mock_api:
            mock_api.return_value.messages.create.return_value = ki_kontext_antwort(
                objektadresse='Musterstraße 12', konfidenz=0.9)
            erg = kontext_vorschlag_service.schlage_kontext_vor(
                'scan-01.pdf', inhalt_text='Ein längerer Rechnungstext.')
        self.assertEqual(erg['owner'], 'objekt')
        self.assertEqual(erg['objekt'], self.objekt)
        self.assertEqual(erg['quelle'], 'ki')

    @override_settings(ANTHROPIC_API_KEY='test-key')
    def test_ki_person_wird_zu_person_aufgeloest(self):
        person = Person.objects.create(
            person_typ='100', vorname='Erika', nachname='Mustermann')
        with patch('anthropic.Anthropic') as mock_api:
            mock_api.return_value.messages.create.return_value = ki_kontext_antwort(
                person_name='Erika Mustermann', konfidenz=0.9)
            erg = kontext_vorschlag_service.schlage_kontext_vor(
                'brief.pdf', inhalt_text='Sehr geehrte Frau Mustermann, ...')
        self.assertEqual(erg['owner'], 'person')
        self.assertEqual(erg['person'], person)

    @override_settings(ANTHROPIC_API_KEY='test-key')
    def test_halluzinierter_name_findet_nichts(self):
        with patch('anthropic.Anthropic') as mock_api:
            mock_api.return_value.messages.create.return_value = ki_kontext_antwort(
                person_name='Niemand Gibtsnicht', konfidenz=0.95)
            erg = kontext_vorschlag_service.schlage_kontext_vor(
                'brief.pdf', inhalt_text='irgendein Text')
        self.assertIsNone(erg['owner'])
        self.assertIsNone(erg['person'])

    @override_settings(ANTHROPIC_API_KEY='test-key')
    def test_einheit_schlaegt_objekt(self):
        einheit = Einheit.objects.create(
            objekt=self.objekt, einheit_nr='7', einheit_typ='wohnung',
            lage='3. OG links')
        with patch('anthropic.Anthropic') as mock_api:
            mock_api.return_value.messages.create.return_value = ki_kontext_antwort(
                objektadresse='Musterstraße 12', einheit='7', konfidenz=0.9)
            erg = kontext_vorschlag_service.schlage_kontext_vor(
                'nk.pdf', inhalt_text='Nebenkostenabrechnung Wohnung 7')
        self.assertEqual(erg['owner'], 'einheit')
        self.assertEqual(erg['einheit'], einheit)
        # Das Objekt bleibt als Alternative sichtbar.
        self.assertEqual(erg['objekt'], self.objekt)


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class ExtraktionTest(TestCase):
    def test_textdatei_wird_gelesen(self):
        import os
        with tempfile.NamedTemporaryFile(
                suffix='.txt', delete=False, mode='w', encoding='utf-8') as fh:
            fh.write('Hallo Welt')
            pfad = fh.name
        try:
            self.assertEqual(
                upload_analyse_service.extrahiere_text(pfad, 'x.txt'), 'Hallo Welt')
        finally:
            os.unlink(pfad)

    def test_unbekannte_endung_liefert_leer(self):
        self.assertEqual(
            upload_analyse_service.extrahiere_text('/nicht/da.xyz', 'da.xyz'), '')


@override_settings(MEDIA_ROOT=_MEDIA_TMP, ANTHROPIC_API_KEY='')
class UploadVorschlagEndpunktTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='uv-tester', password='x')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.objekt = Objekt.objects.create(
            bezeichnung='WEG Endpunkt', objektnummer='UV777', objekt_typ='weg',
            ort='Teststadt', verwaltung_seit=date(2015, 1, 1))

    def test_endpunkt_schlaegt_objekt_aus_dateiname_vor(self):
        datei = SimpleUploadedFile(
            'UV777_Vertrag.txt', b'Beliebiger Inhalt', content_type='text/plain')
        antwort = self.client.post(
            reverse('dokumente-upload-vorschlag'), {'datei': datei}, format='multipart')
        self.assertEqual(antwort.status_code, 200)
        daten = antwort.json()
        self.assertEqual(daten['kontext']['owner'], 'objekt')
        self.assertEqual(daten['kontext']['objekt']['id'], str(self.objekt.id))
        # Register-Block ist immer vollständig vorhanden (hier ohne Treffer).
        self.assertIn('register_id', daten['register'])

    def test_endpunkt_ohne_datei_gibt_400(self):
        antwort = self.client.post(
            reverse('dokumente-upload-vorschlag'), {}, format='multipart')
        self.assertEqual(antwort.status_code, 400)

    def test_upload_ohne_dateiname_leitet_ihn_aus_der_datei_ab(self):
        # Die Upload-Maske schickt nur die Datei, nicht das Pflichtfeld
        # dateiname — der View muss es ableiten statt mit 400 abzuweisen.
        datei = SimpleUploadedFile(
            'TE_Teilungserklaerung.pdf', b'%PDF-1.4 x', content_type='application/pdf')
        antwort = self.client.post('/api/v1/dokumente/', {
            'datei': datei, 'kategorie': 'allgemein',
            'objekt': str(self.objekt.id), 'dokument_typ': 'vertrag',
        }, format='multipart')
        self.assertEqual(antwort.status_code, 201, antwort.content)
        self.assertEqual(antwort.json()['dateiname'], 'TE_Teilungserklaerung.pdf')
