"""
Tests für die WKZ-Freigabe unter „Rechnungsfreigabe" (Stufe 2):
- /wkz-vorlagen/freigabe-liste/ zeigt eingereichte Vorlagen mit Belegbezug
- Zuständigkeit über objektbasierte zahlungsfreigabe_grenzen (GF sieht alles)
- freigeben / ablehnen inkl. Berechtigungsprüfung
- WKZ-Entkopplung: eine aus einer Rechnung abgeleitete WKZ lässt die Rechnung
  unberührt (sie bleibt eine normale Rechnung im regulären Zahlweg)
"""
from decimal import Decimal
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.buchhaltung.services.wkz.freigabe_service import darf_wkz_vorlage_freigeben
from apps.buchhaltung.services.wkz.vorlage_service import (
    erstelle_vorlage,
    reiche_vorlage_zur_freigabe_ein,
)
from apps.konten.models import Konto
from apps.objekte.models import Objekt, Wirtschaftsjahr
from apps.rechnungen.models import Kreditor, Rechnung
from apps.rechnungen.services.rechnung_freigabe_service import route_zur_freigabe

User = get_user_model()

URL_LISTE = '/api/v1/wkz-vorlagen/freigabe-liste/'

# Alles über die GF-Stufe → keine automatische Freigabe beim Einreichen
GRENZEN_NUR_GF = [{'bis': None, 'rolle': 'geschaeftsfuehrer', 'frist_tage': 5}]


class WKZFreigabeTests(TestCase):
    def setUp(self):
        self.gf = User.objects.create_superuser('gf', 'gf@example.de', 'x')
        self.fremd = User.objects.create_user('fremd', password='x')

        self.objekt = Objekt.objects.create(
            bezeichnung='Test-WEG', objektnummer='T900', objekt_typ='WEG',
            ort='Teststadt', verwaltung_seit=date(2020, 1, 1),
            zahlungsfreigabe_grenzen=GRENZEN_NUR_GF,
        )
        wj = Wirtschaftsjahr.objects.create(objekt=self.objekt, jahr=2026, beginn_monat=1)
        Konto.objects.create(
            wirtschaftsjahr=wj, kontonummer='50100', kontoname='Wasser',
            kontoart='standard', direktes_buchen=False, aktiv=True,
        )
        self.kreditor = Kreditor.objects.create(
            name='Stadt Frankfurt', iban='DE12345678901234567890',
        )
        self.client = APIClient()

    # -- Hilfsfunktionen ---------------------------------------------------

    def _rechnung(self):
        return Rechnung.objects.create(
            dateiname='bescheid.pdf', rechnungsnummer='RG-4711',
            kreditor=self.kreditor, objekt=self.objekt,
            betrag_brutto=Decimal('850.00'),
        )

    def _vorlage(self, rechnung=None, eingereicht=True):
        vorlage = erstelle_vorlage(
            {
                'objekt': self.objekt,
                'kreditor': self.kreditor,
                'bezeichnung': 'Versorgungsgebühren',
                'typ': 'bescheid',
                'betrag_gesamt': Decimal('850.00'),
                'rhythmus': 'quartalsweise',
                'erste_faelligkeit': date(2026, 1, 15),
                'gueltig_ab': date(2026, 1, 1),
                'rechnung': rechnung,
            },
            [{'kontonummer': '50100', 'bezeichnung': 'Wasser', 'betrag': Decimal('850.00')}],
            user=self.gf,
        )
        if eingereicht:
            reiche_vorlage_zur_freigabe_ein(vorlage.id, self.gf)
            vorlage.refresh_from_db()
        return vorlage

    # -- Tests -------------------------------------------------------------

    def test_wkz_anlegen_laesst_rechnung_im_rechnungseingang(self):
        """Das Anlegen der WKZ allein darf die Rechnung NICHT aus dem
        Rechnungseingang nehmen — erst der Abschluss ihrer Erfassung."""
        rechnung = self._rechnung()
        vorlage = self._vorlage(rechnung=rechnung)
        rechnung.refresh_from_db()
        self.assertEqual(rechnung.status, 'importiert')
        self.assertEqual(vorlage.status, 'eingereicht')

    def test_abschluss_mit_wkz_laesst_rechnung_normal(self):
        """Entkopplung: Auch wenn aus der Rechnung eine WKZ-Vorlage abgeleitet
        wurde, bleibt die Rechnung eine normale Rechnung und geht regulär in die
        Freigabe (Status 'zur_freigabe', NICHT 'wkz_beleg'). Ihr Zahlweg bleibt
        erhalten (kein OP gelöscht), und die Vorlage behält ihren PDF-Bezug."""
        rechnung = self._rechnung()
        vorlage = self._vorlage(rechnung=rechnung)

        route_zur_freigabe(rechnung, geprueft_von=self.gf)
        rechnung.refresh_from_db()
        vorlage.refresh_from_db()
        self.assertEqual(rechnung.status, 'zur_freigabe')
        self.assertIsNone(rechnung.op_buchung_id)
        self.assertEqual(vorlage.rechnung_id, rechnung.id)

    def test_beleg_verknuepfen_laesst_rechnung_unberuehrt(self):
        """'Beleg verknüpfen' teilt nur das PDF: vorlage.rechnung wird gesetzt,
        die Rechnung behält aber ihren Status und ihren Zahlweg (nicht wkz_beleg)."""
        from apps.buchhaltung.services.wkz.vorlage_service import (
            verknuepfe_rechnung_als_wkz_beleg,
        )
        rechnung = self._rechnung()
        vorlage = self._vorlage(eingereicht=False)   # noch keine Rechnung verknüpft
        self.assertIsNone(vorlage.rechnung_id)

        verknuepfe_rechnung_als_wkz_beleg(vorlage, rechnung, self.gf)
        rechnung.refresh_from_db()
        vorlage.refresh_from_db()
        self.assertEqual(vorlage.rechnung_id, rechnung.id)
        self.assertEqual(rechnung.status, 'importiert')   # unverändert, nicht wkz_beleg

    def test_abschluss_ohne_wkz_geht_regulaer_in_die_freigabe(self):
        rechnung = self._rechnung()
        route_zur_freigabe(rechnung, geprueft_von=self.gf)
        rechnung.refresh_from_db()
        self.assertEqual(rechnung.status, 'zur_freigabe')

    def test_beendete_vorlage_haelt_rechnung_nicht_aus_dem_zahlweg(self):
        rechnung = self._rechnung()
        vorlage = self._vorlage(rechnung=rechnung)
        vorlage.status = 'beendet'
        vorlage.save(update_fields=['status'])

        route_zur_freigabe(rechnung, geprueft_von=self.gf)
        rechnung.refresh_from_db()
        self.assertEqual(rechnung.status, 'zur_freigabe')

    def test_freigabe_liste_zeigt_eingereichte_vorlage_mit_beleg(self):
        # Der Belegbezug steht unabhängig vom Rechnungsstatus
        rechnung = self._rechnung()
        vorlage = self._vorlage(rechnung=rechnung)

        self.client.force_authenticate(self.gf)
        resp = self.client.get(URL_LISTE)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        zeile = resp.data[0]
        self.assertEqual(zeile['id'], str(vorlage.id))
        self.assertEqual(str(zeile['rechnung_id']), str(rechnung.id))
        self.assertEqual(zeile['rechnung_nummer'], 'RG-4711')
        # Jahresbetrag ist die Bewertungsgrundlage der Freigabestufe
        self.assertEqual(Decimal(zeile['jahresbetrag']), Decimal('3400.00'))
        self.assertEqual(len(zeile['splits']), 1)

    def test_freigabe_liste_ohne_zustaendigkeit_leer(self):
        self._vorlage()
        self.client.force_authenticate(self.fremd)
        resp = self.client.get(URL_LISTE)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, [])

    def test_nur_eingereichte_vorlagen_in_der_liste(self):
        self._vorlage(eingereicht=False)   # bleibt Entwurf
        self.client.force_authenticate(self.gf)
        resp = self.client.get(URL_LISTE)
        self.assertEqual(resp.data, [])

    def test_freigeben_aktiviert_vorlage(self):
        vorlage = self._vorlage()
        self.client.force_authenticate(self.gf)
        resp = self.client.post(f'/api/v1/wkz-vorlagen/{vorlage.id}/freigeben/')
        self.assertEqual(resp.status_code, 200)
        vorlage.refresh_from_db()
        self.assertEqual(vorlage.status, 'aktiv')
        self.assertEqual(vorlage.freigegeben_von, self.gf)
        self.assertEqual(vorlage.freigabe_jahresbetrag, Decimal('3400.00'))

    def test_freigeben_ohne_berechtigung_403(self):
        vorlage = self._vorlage()
        self.client.force_authenticate(self.fremd)
        resp = self.client.post(f'/api/v1/wkz-vorlagen/{vorlage.id}/freigeben/')
        self.assertEqual(resp.status_code, 403)
        vorlage.refresh_from_db()
        self.assertEqual(vorlage.status, 'eingereicht')

    def test_ablehnen_setzt_zurueck_auf_entwurf(self):
        vorlage = self._vorlage()
        self.client.force_authenticate(self.gf)
        resp = self.client.post(
            f'/api/v1/wkz-vorlagen/{vorlage.id}/ablehnen/', {'grund': 'Bescheid unklar'},
        )
        self.assertEqual(resp.status_code, 200)
        vorlage.refresh_from_db()
        self.assertEqual(vorlage.status, 'entwurf')
        self.assertIsNone(vorlage.freigegeben_am)

    def test_ablehnen_nur_aus_eingereicht(self):
        vorlage = self._vorlage(eingereicht=False)
        self.client.force_authenticate(self.gf)
        resp = self.client.post(f'/api/v1/wkz-vorlagen/{vorlage.id}/ablehnen/', {'grund': 'x'})
        self.assertEqual(resp.status_code, 400)

    def test_auto_grenze_braucht_keine_freigabe(self):
        """Objekt ohne Grenzen → 'auto': Einreichen aktiviert direkt, die
        Vorlage taucht nicht in der Freigabeliste auf."""
        self.objekt.zahlungsfreigabe_grenzen = []
        self.objekt.save(update_fields=['zahlungsfreigabe_grenzen'])
        vorlage = self._vorlage()
        self.assertEqual(vorlage.status, 'aktiv')
        self.assertTrue(darf_wkz_vorlage_freigeben(vorlage, self.fremd))
        self.client.force_authenticate(self.gf)
        self.assertEqual(self.client.get(URL_LISTE).data, [])
