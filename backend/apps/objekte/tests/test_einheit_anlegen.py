"""Tests für das Einzel-Anlegen einer Einheit zu einem bestehenden Objekt
(EinheitViewSet.anlegen) — z. B. nach einer Aufstockung.

Schwerpunkte:
- nur Administratoren (is_staff) dürfen anlegen,
- Verteilerschlüssel-Werte (MEA 010, Fläche 001, Kopf 030) entstehen mit,
- MEA kommt additiv obendrauf, bestehende Einheiten bleiben unverändert,
- Eindeutigkeit von einheit_nr je Objekt wird geprüft.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.objekte.models import (
    Objekt, Einheit, Verteilerschluessel, VerteilerschluesselWert,
)
from apps.konten.services import verteilerschluessel_anlegen


class EinheitAnlegenTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user('admin', password='x', is_staff=True)
        self.mitarbeiter = User.objects.create_user('sachbearbeiter', password='x')

        self.objekt = Objekt.objects.create(
            objektnummer='T001', objekt_typ='WEG', bezeichnung='WEG Teststraße',
            strasse='Teststraße 1', plz='60311', ort='Frankfurt',
            verwaltung_seit=date(2020, 1, 1),
        )
        # Bestandseinheit mit gesetzter MEA (zeitlos, wj=0).
        self.bestand = Einheit.objects.create(
            objekt=self.objekt, einheit_nr='W-01', einheit_typ='Wohnung',
            lage='1. OG links', flaechennummer='0001',
        )
        verteilerschluessel_anlegen(self.objekt.id)
        self.vs_mea = Verteilerschluessel.objects.get(objekt=self.objekt, schluessel='010')
        VerteilerschluesselWert.objects.update_or_create(
            schluessel=self.vs_mea, einheit=self.bestand, wirtschaftsjahr=0,
            defaults={'wert': Decimal('500.0000'), 'beteiligt': True},
        )
        self.url = reverse('einheiten-anlegen')

    def _daten(self, **overrides):
        daten = {
            'objekt': str(self.objekt.id),
            'einheit_nr': 'W-02',
            'einheit_typ': 'Wohnung',
            'lage': '3. OG rechts (Aufstockung)',
            'mea': '100',
            'flaeche_qm': '78,5',
        }
        daten.update(overrides)
        return daten

    def test_admin_legt_einheit_mit_vs_werten_an(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(self.url, self._daten(), format='json')
        self.assertEqual(resp.status_code, 201, resp.data)

        neu = Einheit.objects.get(objekt=self.objekt, einheit_nr='W-02')
        # MEA aus dem Formular gesetzt
        mea_wert = VerteilerschluesselWert.objects.get(
            schluessel=self.vs_mea, einheit=neu, wirtschaftsjahr=0,
        )
        self.assertEqual(mea_wert.wert, Decimal('100.0000'))
        # Fläche gesetzt
        vs_flaeche = Verteilerschluessel.objects.get(objekt=self.objekt, schluessel='001')
        flaeche_wert = VerteilerschluesselWert.objects.get(
            schluessel=vs_flaeche, einheit=neu, wirtschaftsjahr=0,
        )
        self.assertEqual(flaeche_wert.wert, Decimal('78.5000'))
        # Kopf-Schlüssel "Anzahl Einheiten Gesamt" = 1
        vs_kopf = Verteilerschluessel.objects.get(objekt=self.objekt, schluessel='030')
        kopf_wert = VerteilerschluesselWert.objects.get(schluessel=vs_kopf, einheit=neu)
        self.assertEqual(kopf_wert.wert, Decimal('1.0000'))

    def test_mea_kommt_additiv_obendrauf(self):
        self.client.force_authenticate(self.admin)
        self.client.post(self.url, self._daten(), format='json')

        # Bestands-MEA unverändert
        bestand_mea = VerteilerschluesselWert.objects.get(
            schluessel=self.vs_mea, einheit=self.bestand, wirtschaftsjahr=0,
        )
        self.assertEqual(bestand_mea.wert, Decimal('500.0000'))

        # Summe = 500 (Bestand) + 100 (neu)
        from django.db.models import Sum
        summe = (
            VerteilerschluesselWert.objects
            .filter(schluessel=self.vs_mea, beteiligt=True, wirtschaftsjahr=0)
            .aggregate(s=Sum('wert'))['s']
        )
        self.assertEqual(summe, Decimal('600.0000'))

    def test_nicht_admin_bekommt_403(self):
        self.client.force_authenticate(self.mitarbeiter)
        resp = self.client.post(self.url, self._daten(), format='json')
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Einheit.objects.filter(objekt=self.objekt, einheit_nr='W-02').exists())

    def test_doppelte_einheit_nr_abgelehnt(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(self.url, self._daten(einheit_nr='W-01'), format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('einheit_nr', resp.data)

    def test_pflichtfeld_lage_fehlt(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(self.url, self._daten(lage=''), format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('lage', resp.data)

    def test_ungueltiger_typ_abgelehnt(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(self.url, self._daten(einheit_typ='Garage'), format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('einheit_typ', resp.data)

    def test_zu_lange_einheit_nr_gibt_400_statt_500(self):
        """Bezeichnung > 20 Zeichen muss sauber mit 400 abgelehnt werden
        (ohne Validierung würde die DB einen DataError/500 werfen)."""
        self.client.force_authenticate(self.admin)
        resp = self.client.post(self.url, self._daten(einheit_nr='Aufstockung Whg. 2.06'), format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('einheit_nr', resp.data)
        self.assertFalse(Einheit.objects.filter(objekt=self.objekt, einheit_nr='Aufstockung Whg. 2.06').exists())

    def test_ohne_mea_keine_wert_zeile_mit_wert(self):
        """Ohne MEA-Angabe wird die Einheit angelegt, die MEA-Wertzeile bleibt leer (NULL)."""
        self.client.force_authenticate(self.admin)
        resp = self.client.post(self.url, self._daten(mea='', flaeche_qm=''), format='json')
        self.assertEqual(resp.status_code, 201, resp.data)
        neu = Einheit.objects.get(objekt=self.objekt, einheit_nr='W-02')
        mea_wert = VerteilerschluesselWert.objects.get(
            schluessel=self.vs_mea, einheit=neu, wirtschaftsjahr=0,
        )
        self.assertIsNone(mea_wert.wert)
