"""
Tests: Jahresabrechnung Wizard-API (HGA-Spec v1.0 Kap. 9, Phase E)

Routing, WEG-Guard (501), Schritt-1-Anlage inkl. Entwurf-Fortsetzung,
Schritt-Navigation, Schritt-Endpunkte, PDF-Vorschau, Freigabe über HTTP.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.buchhaltung.models import Buchungsart, Jahresabrechnung
from apps.buchhaltung.services.jahresabrechnung.einzelabrechnung_service import (
    berechne_alle_einzelabrechnungen,
)
from apps.buchhaltung.tests.test_einzelabrechnung_service import (
    EinzelAbrechnungServiceTestBase,
    _create_objekt,
)
from apps.objekte.models import Objekt, Wirtschaftsjahr

User = get_user_model()

BASE = '/api/v1/jahresabrechnungen/'


class JahresabrechnungApiTest(EinzelAbrechnungServiceTestBase):
    """Nutzt das Fixture der Service-Tests (2 Einheiten, MEA 300/700)."""

    client_class = APIClient

    def setUp(self):
        super().setUp()
        Buchungsart.objects.get_or_create(
            nr='950', defaults=dict(bezeichnung='Abrechnungsergebnis'))
        self.client.force_authenticate(self.user)
        # setUp der Basisklasse legt bereits eine JA an — für die
        # Anlage-Tests wird sie gelöscht, für die übrigen genutzt.

    # -- Schritt 1: Anlage ----------------------------------------------------

    def test_anlage_neu(self):
        prozess = self.ja.prozess
        self.ja.delete()
        prozess.delete()
        resp = self.client.post(BASE, {
            'objekt': str(self.objekt.id),
            'wirtschaftsjahr': str(self.wj.id),
        })
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data['status'], 'entwurf')
        ja = Jahresabrechnung.objects.get(pk=resp.data['id'])
        self.assertEqual(ja.prozess.prozess_typ, 'jahresabrechnung')

    def test_anlage_setzt_entwurf_fort(self):
        resp = self.client.post(BASE, {
            'objekt': str(self.objekt.id),
            'wirtschaftsjahr': str(self.wj.id),
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['id'], str(self.ja.id))  # kein Duplikat

    def test_anlage_blockiert_bei_gesperrter_abrechnung(self):
        self.ja.status = 'gesperrt'
        self.ja.save(update_fields=['status'])
        resp = self.client.post(BASE, {
            'objekt': str(self.objekt.id),
            'wirtschaftsjahr': str(self.wj.id),
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn('bereits', resp.data['error'])

    def test_weg_guard_501(self):
        zh = Objekt.objects.create(
            objekt_typ='ZH', bezeichnung='Zinshaus', kurzbezeichnung='ZH1',
            strasse='Str. 1', plz='60311', ort='FFM',
            verwaltung_seit=date(2020, 1, 1), glaeubiger_id='DE98ZZZ09999999999',
        )
        wj_zh = Wirtschaftsjahr.objects.create(objekt=zh, jahr=2025, beginn_monat=1)
        resp = self.client.post(BASE, {
            'objekt': str(zh.id), 'wirtschaftsjahr': str(wj_zh.id),
        })
        self.assertEqual(resp.status_code, 501)

    def test_wj_nicht_offen_blockiert(self):
        self.ja.delete()
        self.wj.status = 'abgeschlossen'
        self.wj.save(update_fields=['status'])
        resp = self.client.post(BASE, {
            'objekt': str(self.objekt.id), 'wirtschaftsjahr': str(self.wj.id),
        })
        self.assertEqual(resp.status_code, 400)

    # -- Navigation + Schritt-Endpunkte ----------------------------------------

    def test_schritt_navigation(self):
        url = f'{BASE}{self.ja.id}/schritt/2/'
        resp = self.client.patch(url, {'daten': {'bestaetigt': True}}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['current_step'], 2)
        self.assertEqual(resp.data['steps_data'], {'bestaetigt': True})
        self.assertIn('blockiert', resp.data['daten'])  # Buchungsprüfung

    def test_schritt2_ohne_offene_ops_nicht_blockiert(self):
        resp = self.client.get(f'{BASE}{self.ja.id}/schritt/2/')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data['daten']['blockiert'])
        self.assertEqual(resp.data['daten']['folgejahr'], self.wj.jahr + 1)

    # -- Schritt 2: Saldovortrag offener Kreditor-OPs ---------------------------

    def _offener_kreditor_op(self):
        """Offener OP mit festgeschriebener Ursprungsbuchung 15900 / 70xxx."""
        from apps.buchhaltung.models import Buchung, KreditorOP
        from apps.konten.models import Konto
        from apps.rechnungen.models import Kreditor
        from apps.rechnungen.services.rechnung_op_service import (
            get_or_create_kreditor_konto,
        )
        Wirtschaftsjahr.objects.create(
            objekt=self.objekt, jahr=self.wj.jahr + 1,
            beginn_monat=self.wj.beginn_monat, vorjahr=self.wj, status='offen',
        )
        kreditor = Kreditor.objects.create(name='API Handwerk GmbH')
        schwebe = {
            wj.jahr: Konto.objects.get_or_create(
                wirtschaftsjahr=wj, kontonummer='15900',
                defaults=dict(kontoname='Schwebende Eingangsrechnungen',
                              direktes_buchen=False))[0]
            for wj in Wirtschaftsjahr.objects.filter(objekt=self.objekt)
        }
        buchung = Buchung.objects.create(
            objekt=self.objekt,
            soll_konto=schwebe[self.wj.jahr],
            haben_konto=get_or_create_kreditor_konto(
                kreditor, self.objekt, jahr=self.wj.jahr),
            betrag=Decimal('750.00'),
            buchungsdatum=self.wj.ende_datum,
            buchungstext='Eingangsrechnung API-Test',
            wirtschaftsjahr=self.wj,
            wirtschaftsjahr_nr=self.wj.jahr,
            status='festgeschrieben',
            erstellt_von=self.user,
        )
        return KreditorOP.objects.create(
            op_nummer=95000001, kreditor=kreditor, objekt=self.objekt,
            buchung=buchung,
            betrag_ursprung=Decimal('750.00'), betrag_offen=Decimal('750.00'),
            faellig_ab=self.wj.ende_datum, status='offen',
        )

    def test_kreditor_vortrag_entsperrt_schritt2(self):
        op = self._offener_kreditor_op()
        resp = self.client.get(f'{BASE}{self.ja.id}/schritt/2/')
        self.assertTrue(resp.data['daten']['blockiert'])

        resp = self.client.post(
            f'{BASE}{self.ja.id}/kreditor-vortrag/',
            {'op_nummern': [op.op_nummer]}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['vorgetragen_nach'], self.wj.jahr + 1)
        self.assertEqual(resp.data['anzahl_gebucht'], 1)
        self.assertFalse(resp.data['pruefung']['blockiert'])
        self.assertEqual(len(resp.data['pruefung']['vorgetragene_ops']), 1)

        resp = self.client.get(f'{BASE}{self.ja.id}/schritt/2/')
        self.assertFalse(resp.data['daten']['blockiert'])

    def test_kreditor_vortrag_leere_auswahl_400(self):
        resp = self.client.post(
            f'{BASE}{self.ja.id}/kreditor-vortrag/', {'op_nummern': []}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('error', resp.data)

    def test_kreditor_vortrag_unbekannte_op_400(self):
        self._offener_kreditor_op()
        resp = self.client.post(
            f'{BASE}{self.ja.id}/kreditor-vortrag/', {'op_nummern': [999]}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('nicht gefunden', resp.data['error'])

    def test_freigabe_nach_vortrag_nicht_mehr_durch_ops_gesperrt(self):
        op = self._offener_kreditor_op()
        resp = self.client.post(f'{BASE}{self.ja.id}/freigeben/')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Kreditoren-OPs', resp.data['error'])

        self.client.post(f'{BASE}{self.ja.id}/kreditor-vortrag/',
                         {'op_nummern': [op.op_nummer]}, format='json')
        resp = self.client.post(f'{BASE}{self.ja.id}/freigeben/')
        # Freigabe kann an anderen Schritten scheitern, aber nicht mehr an den OPs
        if resp.status_code == 400:
            self.assertNotIn('Kreditoren-OPs', resp.data['error'])

    def test_kostenstellen(self):
        self._create_kosten('1000.00')
        resp = self.client.get(f'{BASE}{self.ja.id}/kostenstellen/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['positionen']), 1)
        self.assertEqual(resp.data['summe_ist'], '1000.00')
        self.assertFalse(resp.data['wirtschaftsplan_vorhanden'])

    def test_umlageschluessel_get_und_patch(self):
        konto = self._create_kosten('1000.00')
        resp = self.client.get(f'{BASE}{self.ja.id}/umlageschluessel/')
        self.assertEqual(resp.status_code, 200)
        zeile = next(z for z in resp.data['konten'] if z['kontonummer'] == '50100')
        self.assertEqual(zeile['vs_code'], '010')
        # Korrektur auf Fläche
        resp = self.client.patch(
            f'{BASE}{self.ja.id}/umlageschluessel/',
            {'konto_id': str(konto.id), 'vs_code': '001'}, format='json')
        self.assertEqual(resp.status_code, 200)
        zeile = next(z for z in resp.data['konten'] if z['kontonummer'] == '50100')
        self.assertEqual(zeile['vs_code'], '001')

    def test_ruecklagen(self):
        resp = self.client.get(f'{BASE}{self.ja.id}/ruecklagen/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['ruecklagen'], [])
        self.assertFalse(resp.data['blockiert'])

    def test_einzelabrechnungen_berechnen_und_lesen(self):
        self._create_kosten('1000.00')
        resp = self.client.post(f'{BASE}{self.ja.id}/einzelabrechnungen/berechnen/')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(len(resp.data), 2)
        resp = self.client.get(f'{BASE}{self.ja.id}/einzelabrechnungen/')
        self.assertEqual(len(resp.data), 2)
        # Detail je Einheit
        resp = self.client.get(f'{BASE}{self.ja.id}/einzelabrechnungen/{self.e1.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['kostenanteil_gesamt'], '300.00')

    def test_einzelabrechnung_manuelle_korrektur(self):
        self._create_kosten('1000.00')
        berechne_alle_einzelabrechnungen(self.ja)
        ea = self.ja.einzelabrechnungen.get(einheit=self.e1)
        positionen = ea.positionen
        positionen[0]['betrag'] = '250.00'
        positionen[0]['manuell_korrigiert'] = True
        resp = self.client.patch(
            f'{BASE}{self.ja.id}/einzelabrechnungen/{self.e1.id}/',
            {'positionen': positionen, 'grund': 'Rechnungskorrektur Hausmeister'},
            format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['kostenanteil_gesamt'], '250.00')
        korrekturen = self.ja.prozess.steps_data.get('6_korrekturen') or []
        # refresh
        self.ja.prozess.refresh_from_db()
        korrekturen = self.ja.prozess.steps_data['6_korrekturen']
        self.assertEqual(korrekturen[0]['grund'], 'Rechnungskorrektur Hausmeister')

    def test_korrektur_ohne_grund_blockiert(self):
        self._create_kosten('1000.00')
        berechne_alle_einzelabrechnungen(self.ja)
        resp = self.client.patch(
            f'{BASE}{self.ja.id}/einzelabrechnungen/{self.e1.id}/',
            {'positionen': [], 'grund': ''}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_pdf_vorschau(self):
        self._create_kosten('1000.00')
        berechne_alle_einzelabrechnungen(self.ja)
        resp = self.client.get(
            f'{BASE}{self.ja.id}/pdf-vorschau/', {'einheit': str(self.e1.id)})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertTrue(resp.content.startswith(b'%PDF'))

    # -- Schritt 8: Freigabe -----------------------------------------------------

    def test_freigeben(self):
        self._create_kosten('1000.00')
        self._create_soll(self.ev1, '200.00', date(2025, 1, 1))
        self._create_soll(self.ev2, '900.00', date(2025, 1, 1))
        berechne_alle_einzelabrechnungen(self.ja)
        resp = self.client.post(f'{BASE}{self.ja.id}/freigeben/')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['jahresabrechnung']['status'], 'gesperrt')
        self.assertEqual(resp.data['guthaben_einheiten'], 1)
        self.assertIn('Auszahlungslauf', resp.data['hinweis'])

    def test_freigeben_blockiert_bei_offenem_kreditor_op(self):
        from apps.buchhaltung.models import KreditorOP
        from apps.rechnungen.models import Kreditor
        kreditor = Kreditor.objects.create(name='Testfirma GmbH')
        KreditorOP.objects.create(
            op_nummer=990001, kreditor=kreditor, objekt=self.objekt,
            betrag_ursprung=Decimal('100.00'), betrag_offen=Decimal('100.00'),
            faellig_ab=date(2025, 6, 1), status='offen',
        )
        self._create_kosten('1000.00')
        berechne_alle_einzelabrechnungen(self.ja)
        resp = self.client.post(f'{BASE}{self.ja.id}/freigeben/')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Kreditoren-OP', resp.data['error'])

    # -- Entwurf löschen -----------------------------------------------------------

    def test_entwurf_loeschen(self):
        resp = self.client.delete(f'{BASE}{self.ja.id}/')
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(Jahresabrechnung.objects.filter(pk=self.ja.pk).exists())

    def test_gesperrte_nicht_loeschbar(self):
        self.ja.status = 'gesperrt'
        self.ja.save(update_fields=['status'])
        resp = self.client.delete(f'{BASE}{self.ja.id}/')
        self.assertEqual(resp.status_code, 400)
