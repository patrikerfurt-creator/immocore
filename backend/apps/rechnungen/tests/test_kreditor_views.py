"""
Tests für die additiven Filter am ``/api/v1/kreditoren/``-Endpunkt
(Handwerker-Beauftragungsdialog): ``ist_handwerker`` und ``gewerk``
(M2M-Filter über ``Kreditor.gewerke``).
"""
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.handwerker.models import Gewerk
from apps.rechnungen.models import Kreditor

User = get_user_model()

KREDITOREN = '/api/v1/kreditoren/'


class KreditorGewerkeFilterTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='kreditor-filter-tester')
        self.client.force_authenticate(self.user)
        self.sanitaer = Gewerk.objects.create(code='test-sanitaer', bezeichnung='Sanitär')
        self.heizung = Gewerk.objects.create(code='test-heizung', bezeichnung='Heizung')

        self.mehrgewerk_kreditor = Kreditor.objects.create(
            name='Sanitär & Heizung Meier', ist_handwerker=True, email='meier@example.de',
        )
        self.mehrgewerk_kreditor.gewerke.set([self.sanitaer, self.heizung])

        self.nur_sanitaer_kreditor = Kreditor.objects.create(
            name='Nur Sanitär Schulz', ist_handwerker=True, email='schulz@example.de',
        )
        self.nur_sanitaer_kreditor.gewerke.set([self.sanitaer])

        self.kein_handwerker = Kreditor.objects.create(
            name='Kein Handwerker GmbH', ist_handwerker=False,
        )

    def test_gewerk_filter_findet_kreditor_mit_mehreren_gewerken_ueber_beide_gewerke(self):
        response_sanitaer = self.client.get(KREDITOREN, {'gewerk': str(self.sanitaer.id)})
        response_heizung = self.client.get(KREDITOREN, {'gewerk': str(self.heizung.id)})

        ids_sanitaer = {k['id'] for k in response_sanitaer.data}
        ids_heizung = {k['id'] for k in response_heizung.data}

        self.assertIn(str(self.mehrgewerk_kreditor.id), ids_sanitaer)
        self.assertIn(str(self.mehrgewerk_kreditor.id), ids_heizung)
        self.assertIn(str(self.nur_sanitaer_kreditor.id), ids_sanitaer)
        self.assertNotIn(str(self.nur_sanitaer_kreditor.id), ids_heizung)

    def test_gewerk_filter_liefert_keine_duplikate(self):
        response = self.client.get(KREDITOREN, {'gewerk': str(self.sanitaer.id)})
        ids = [k['id'] for k in response.data]
        self.assertEqual(len(ids), len(set(ids)))

    def test_ist_handwerker_ohne_gewerk_liefert_alle_handwerker(self):
        response = self.client.get(KREDITOREN, {'ist_handwerker': 'true'})
        ids = {k['id'] for k in response.data}

        self.assertIn(str(self.mehrgewerk_kreditor.id), ids)
        self.assertIn(str(self.nur_sanitaer_kreditor.id), ids)
        self.assertNotIn(str(self.kein_handwerker.id), ids)

    def test_gewerke_bezeichnungen_im_serializer(self):
        response = self.client.get(KREDITOREN, {'ist_handwerker': 'true'})
        eintrag = next(k for k in response.data if k['id'] == str(self.mehrgewerk_kreditor.id))
        self.assertEqual(
            set(eintrag['gewerke_bezeichnungen']), {'Sanitär', 'Heizung'},
        )
