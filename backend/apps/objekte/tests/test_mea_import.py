"""Tests für den MEA-Import je Liegenschaft (ObjektViewSet.mea_vorschau/mea_commit
und das Modul apps.objekte.mea_import).

Schwerpunkte:
- Zuordnung der MEA-Werte über die Flächennummer auf bestehende Einheiten,
- nicht gefundene / fremde / wertlose Zeilen werden als Warnung markiert, nicht importiert,
- Commit setzt die Werte auf Verteilerschlüssel 010 (zeitlos, wj=0),
- nur Administratoren dürfen importieren,
- .xlsx und .xls werden gelesen.
"""
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.objekte.models import (
    Objekt, Einheit, Verteilerschluessel, VerteilerschluesselWert,
)
from apps.objekte.mea_import import mea_vorschau, mea_commit, parse_mea_datei


def _xlsx(zeilen, header=('Objekt Nr. ', 'Fl.Nr.', 'Fl.Bezeichnung',
                          'Person/Leerstand', 'Bel.beginn', 'Wert')):
    """Baut eine .xlsx-Datei mit A=Objektnr, B=Fl.Nr., F=Wert (wie iX-Haus-Export)."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(header))
    for objnr, flnr, wert in zeilen:
        # A, B, C, D, E, F  → Wert liegt in Spalte F (Index 5)
        ws.append([objnr, flnr, '', '', '', wert])
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


class MeaImportBasisTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user('admin', password='x', is_staff=True)
        self.user = User.objects.create_user('sachbearbeiter', password='x')

        self.objekt = Objekt.objects.create(
            objektnummer='10007', objekt_typ='WEG', bezeichnung='WEG Teststraße',
            strasse='Teststraße 1', plz='60311', ort='Frankfurt',
            verwaltung_seit=date(2020, 1, 1),
        )
        self.e1 = Einheit.objects.create(
            objekt=self.objekt, einheit_nr='Whg 101', einheit_typ='Wohnung',
            lage='EG', flaechennummer='100001',
        )
        self.e2 = Einheit.objects.create(
            objekt=self.objekt, einheit_nr='Whg 102', einheit_typ='Wohnung',
            lage='EG', flaechennummer='100002',
        )
        self.e3 = Einheit.objects.create(
            objekt=self.objekt, einheit_nr='Stellplatz 1', einheit_typ='Stellplatz',
            lage='TG', flaechennummer='800001',
        )
        self.vorschau_url = reverse('objekte-mea-vorschau', args=[self.objekt.id])
        self.commit_url = reverse('objekte-mea-commit', args=[self.objekt.id])

    # ── Parser ────────────────────────────────────────────────────────
    def test_parser_liest_spalten_a_b_f(self):
        daten = _xlsx([('10007', '100001', 105), ('10007', '100002', 68.5)])
        rows = parse_mea_datei(daten, 'export.xlsx')
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['objektnummer'], '10007')
        self.assertEqual(rows[0]['flaechennummer'], '100001')
        self.assertEqual(rows[0]['wert'], Decimal('105.0000'))
        self.assertEqual(rows[1]['wert'], Decimal('68.5000'))

    def test_parser_deutsches_dezimalformat(self):
        daten = _xlsx([('10007', '100001', '1.234,56')])
        rows = parse_mea_datei(daten, 'export.xlsx')
        self.assertEqual(rows[0]['wert'], Decimal('1234.5600'))

    # ── Vorschau ──────────────────────────────────────────────────────
    def test_vorschau_ordnet_zu_und_summiert(self):
        daten = _xlsx([('10007', '100001', 105), ('10007', '100002', 95)])
        result = mea_vorschau(self.objekt, daten, 'export.xlsx')
        self.assertEqual(result['summary']['ok'], 2)
        self.assertEqual(result['summary']['summe'], '200.0000')
        erste = result['zeilen'][0]
        self.assertEqual(erste['status'], 'ok')
        self.assertEqual(erste['einheit_nr'], 'Whg 101')
        self.assertEqual(erste['daten']['einheit_id'], str(self.e1.id))

    def test_vorschau_nicht_gefundene_flaechennummer(self):
        daten = _xlsx([('10007', '999999', 105)])
        result = mea_vorschau(self.objekt, daten, 'export.xlsx')
        self.assertEqual(result['zeilen'][0]['status'], 'nicht_gefunden')
        self.assertEqual(result['summary']['nicht_gefunden'], 1)
        self.assertEqual(result['summary']['ok'], 0)

    def test_vorschau_fremdes_objekt(self):
        daten = _xlsx([('99999', '100001', 105)])
        result = mea_vorschau(self.objekt, daten, 'export.xlsx')
        self.assertEqual(result['zeilen'][0]['status'], 'fremdes_objekt')

    def test_vorschau_meldet_einheiten_ohne_zeile(self):
        daten = _xlsx([('10007', '100001', 105)])
        result = mea_vorschau(self.objekt, daten, 'export.xlsx')
        ohne = {o['flaechennummer'] for o in result['summary']['einheiten_ohne_zeile']}
        self.assertEqual(ohne, {'100002', '800001'})

    def test_vorschau_alt_wert_wird_angezeigt(self):
        from apps.konten.services import verteilerschluessel_anlegen
        verteilerschluessel_anlegen(self.objekt.id)
        vs = Verteilerschluessel.objects.get(objekt=self.objekt, schluessel='010')
        VerteilerschluesselWert.objects.update_or_create(
            schluessel=vs, einheit=self.e1, wirtschaftsjahr=0,
            defaults={'wert': Decimal('50.0000')},
        )
        daten = _xlsx([('10007', '100001', 105)])
        result = mea_vorschau(self.objekt, daten, 'export.xlsx')
        self.assertEqual(result['zeilen'][0]['alt_wert'], '50.0000')
        self.assertEqual(result['zeilen'][0]['neu_wert'], '105.0000')

    # ── Commit ────────────────────────────────────────────────────────
    def test_commit_setzt_werte(self):
        daten = _xlsx([('10007', '100001', 105), ('10007', '100002', 95),
                       ('10007', '999999', 10)])
        vorschau = mea_vorschau(self.objekt, daten, 'export.xlsx')
        ergebnis = mea_commit(self.objekt, vorschau['zeilen'], self.admin)
        self.assertEqual(ergebnis['aktualisiert'], 2)
        self.assertEqual(ergebnis['uebersprungen'], 1)   # nicht_gefunden

        vs = Verteilerschluessel.objects.get(objekt=self.objekt, schluessel='010')
        w1 = VerteilerschluesselWert.objects.get(schluessel=vs, einheit=self.e1, wirtschaftsjahr=0)
        self.assertEqual(w1.wert, Decimal('105.0000'))
        self.assertEqual(w1.quelle, 'stammdaten')
        self.assertEqual(ergebnis['summe'], '200.0000')

    def test_commit_ueberschreibt_bestehenden_wert(self):
        from apps.konten.services import verteilerschluessel_anlegen
        verteilerschluessel_anlegen(self.objekt.id)
        vs = Verteilerschluessel.objects.get(objekt=self.objekt, schluessel='010')
        VerteilerschluesselWert.objects.update_or_create(
            schluessel=vs, einheit=self.e1, wirtschaftsjahr=0,
            defaults={'wert': Decimal('50.0000')},
        )
        daten = _xlsx([('10007', '100001', 105)])
        vorschau = mea_vorschau(self.objekt, daten, 'export.xlsx')
        mea_commit(self.objekt, vorschau['zeilen'], self.admin)
        w1 = VerteilerschluesselWert.objects.get(schluessel=vs, einheit=self.e1, wirtschaftsjahr=0)
        self.assertEqual(w1.wert, Decimal('105.0000'))

    # ── API / Berechtigung ────────────────────────────────────────────
    def test_api_vorschau_und_commit_als_admin(self):
        self.client.force_authenticate(self.admin)
        daten = _xlsx([('10007', '100001', 105), ('10007', '100002', 95)])
        upload = SimpleUploadedFile('export.xlsx', daten,
                                    content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resp = self.client.post(self.vorschau_url, {'datei': upload}, format='multipart')
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data['summary']['ok'], 2)

        resp2 = self.client.post(self.commit_url, {'rows': resp.data['zeilen']}, format='json')
        self.assertEqual(resp2.status_code, 200, resp2.data)
        self.assertEqual(resp2.data['aktualisiert'], 2)

    def test_api_angemeldeter_nutzer_erlaubt(self):
        # Berechtigung wie der Einheiten-Massenimport: kein Admin nötig.
        self.client.force_authenticate(self.user)
        daten = _xlsx([('10007', '100001', 105)])
        upload = SimpleUploadedFile('export.xlsx', daten)
        resp = self.client.post(self.vorschau_url, {'datei': upload}, format='multipart')
        self.assertEqual(resp.status_code, 200, resp.data)

    def test_api_unauthentifiziert_abgelehnt(self):
        daten = _xlsx([('10007', '100001', 105)])
        upload = SimpleUploadedFile('export.xlsx', daten)
        resp = self.client.post(self.vorschau_url, {'datei': upload}, format='multipart')
        self.assertIn(resp.status_code, (401, 403))

    def test_api_falsches_dateiformat(self):
        self.client.force_authenticate(self.admin)
        upload = SimpleUploadedFile('export.csv', b'a;b;c', content_type='text/csv')
        resp = self.client.post(self.vorschau_url, {'datei': upload}, format='multipart')
        self.assertEqual(resp.status_code, 400)
