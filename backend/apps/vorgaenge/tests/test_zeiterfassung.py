"""
Tests für die optionale Zeiterfassung an Vorgängen (Sonderkosten-Nachweis).

Deckt ab: Schalter ``abrechenbar``, Anlage/Löschen von Zeiteinträgen inkl.
Freischalt-Guard (nur bei ``abrechenbar``), Validierung (Dauer ODER Kilometer),
Summenberechnung im Detail und den CSV-Export.
"""
from datetime import date

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.objekte.models import Objekt
from apps.vorgaenge.models import Vorgang, VorgangTyp, VorgangZeiteintrag

User = get_user_model()

VORGAENGE = '/api/v1/vorgaenge/'


def _objekt(nr='ZE001'):
    return Objekt.objects.create(
        bezeichnung='Test-WEG Zeiterfassung', objektnummer=nr, objekt_typ='weg',
        ort='Teststadt', verwaltung_seit=date(2020, 1, 1),
    )


def _typ(code='maengelmeldung'):
    return VorgangTyp.objects.get(code=code)


class ZeiterfassungTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='zeit-tester')
        self.client.force_authenticate(self.user)
        self.objekt = _objekt()
        self.vorgang = Vorgang.objects.create(
            typ=_typ(), betreff='Fassadensanierung', objekt=self.objekt,
            erstellt_von=self.user, status='in_bearbeitung', quelle='manuell',
        )

    def _url(self, suffix=''):
        return f'{VORGAENGE}{self.vorgang.id}/{suffix}'

    def _abrechenbar_an(self):
        return self.client.post(self._url('abrechenbar/'), {'abrechenbar': True})

    def _eintrag(self, **override):
        daten = {
            'mitarbeiter': self.user.id,
            'datum': '2026-10-14',
            'taetigkeit': 'Telefonat mit Architekt',
            'dauer_minuten': 30,
            'kilometer': '0',
        }
        daten.update(override)
        return self.client.post(self._url('zeiteintraege/'), daten)

    # ── Schalter ──────────────────────────────────────────────────────────
    def test_abrechenbar_schalter_default_aus_und_setzbar(self):
        self.assertFalse(self.vorgang.abrechenbar)
        response = self._abrechenbar_an()
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data['abrechenbar'])
        self.vorgang.refresh_from_db()
        self.assertTrue(self.vorgang.abrechenbar)

    # ── Guard: nur bei abrechenbar ───────────────────────────────────────
    def test_zeiteintrag_ohne_abrechenbar_abgewiesen(self):
        response = self._eintrag()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(VorgangZeiteintrag.objects.count(), 0)

    # ── Anlage + Summe ───────────────────────────────────────────────────
    def test_zeiteintrag_anlegen_und_summe(self):
        self._abrechenbar_an()
        r1 = self._eintrag(dauer_minuten=90, kilometer='12.5')
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED, r1.data)
        self._eintrag(dauer_minuten=30, taetigkeit='Ortstermin', kilometer='7.5')

        detail = self.client.get(self._url()).data
        self.assertEqual(len(detail['zeiteintraege']), 2)
        self.assertEqual(detail['zeit_summe']['anzahl'], 2)
        self.assertEqual(detail['zeit_summe']['minuten'], 120)
        self.assertEqual(detail['zeit_summe']['kilometer'], '20.0')
        # Mitarbeitername ist mitserialisiert
        self.assertTrue(detail['zeiteintraege'][0]['mitarbeiter_name'])

    def test_nur_kilometer_ohne_dauer_erlaubt(self):
        self._abrechenbar_an()
        response = self._eintrag(dauer_minuten=0, kilometer='15.0')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_dauer_und_km_beide_null_abgewiesen(self):
        self._abrechenbar_an()
        response = self._eintrag(dauer_minuten=0, kilometer='0')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ── Löschen ──────────────────────────────────────────────────────────
    def test_zeiteintrag_loeschen(self):
        self._abrechenbar_an()
        self._eintrag()
        eintrag = VorgangZeiteintrag.objects.get()
        response = self.client.delete(self._url(f'zeiteintraege/{eintrag.id}/'))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(VorgangZeiteintrag.objects.count(), 0)

    def test_storniert_blockt_anlage(self):
        self._abrechenbar_an()
        self.vorgang.status = 'storniert'
        self.vorgang.save(update_fields=['status'])
        response = self._eintrag()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ── CSV-Export ───────────────────────────────────────────────────────
    def test_csv_export(self):
        self._abrechenbar_an()
        self._eintrag(dauer_minuten=90, taetigkeit='Telefonat', kilometer='12.5')
        response = self.client.get(self._url('zeiten-export/'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('text/csv', response['Content-Type'])
        self.assertIn('attachment', response['Content-Disposition'])
        inhalt = response.content.decode('utf-8')
        self.assertIn('Telefonat', inhalt)
        self.assertIn('1:30', inhalt)        # 90 min als hh:mm
        self.assertIn('12,5', inhalt)        # deutsche Dezimalschreibweise
        self.assertIn('Summe', inhalt)
