"""
Integrationstests Jahresabrechnung (HGA-Spec v1.0 Kap. 11.2 / 12, Phase F)

Vollständiger Wizard-Durchlauf 1→8 über die API mit 5 Einheiten, davon
1 mit Eigentümerwechsel im WJ und 1 mit Guthaben-Ergebnis. Plus die
Blocker-Szenarien aus Kap. 11.2.

Szenario (MEA je Einheit 200 von 1.000 → Anteil 0,2; Aufwand 50100 = 1.000 €):
    WE01  Soll 100  → Kostenanteil 200 − 100 = +100  (Nachzahlung)
    WE02  Soll 200  → 200 − 200 =   0                (keine Sollstellung)
    WE03  Soll 150  → 200 − 150 = +50                (Nachzahlung)
    WE04  Soll 150  → 200 − 150 = +50                (Nachzahlung)
    WE05  Soll 500  → 200 − 500 = −300               (Guthaben; Eigentümerwechsel)
"""
from datetime import date
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.buchhaltung.models import (
    Buchung,
    Buchungsart,
    HausgeldSollstellung,
    HausgeldSollstellungslauf,
    Jahresabrechnung,
    Kontoumsatz,
    KreditorOP,
)
from apps.konten.models import Konto
from apps.objekte.models import (
    Bankkonto,
    Einheit,
    EinheitVerbrauch,
    Objekt,
    Verteilerschluessel,
    VerteilerschluesselWert,
    Wirtschaftsjahr,
)
from apps.personen.models import EigentumsVerhaeltnis, Person

User = get_user_model()
BASE = '/api/v1/jahresabrechnungen/'


class JahresabrechnungIntegrationTest(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='hga-integration', is_staff=True)
        self.client.force_authenticate(self.user)
        Buchungsart.objects.get_or_create(
            nr='950', defaults=dict(bezeichnung='Abrechnungsergebnis'))

        self.objekt = Objekt.objects.create(
            objekt_typ='WEG', bezeichnung='WEG Integrationstest',
            kurzbezeichnung='INT', strasse='Teststr. 1', plz='60311', ort='Frankfurt',
            verwaltung_seit=date(2019, 1, 1), glaeubiger_id='DE98ZZZ09999999999',
        )
        self.wj = Wirtschaftsjahr.objects.create(
            objekt=self.objekt, jahr=2025, beginn_monat=1, status='offen')

        # 5 Einheiten mit MEA je 200 (Summe 1000)
        self.einheiten = []
        vs_mea = Verteilerschluessel.objects.create(
            objekt=self.objekt, schluessel='010', bezeichnung='MEA', vs_typ='mea')
        for i in range(1, 6):
            e = Einheit.objects.create(
                objekt=self.objekt, einheit_nr=f'WE0{i}',
                einheit_typ='Wohnung', lage=f'Lage {i}')
            self.einheiten.append(e)
            VerteilerschluesselWert.objects.create(
                schluessel=vs_mea, einheit=e, wirtschaftsjahr=0, wert=Decimal('200'))

        # Eigentumsverhältnisse — WE05 mit Eigentümerwechsel im WJ
        self.evs = {}
        for idx, e in enumerate(self.einheiten[:4], start=1):
            p = Person.objects.create(
                person_typ='100', anrede='Herr', vorname='E', nachname=f'Eigentuemer{idx}')
            self.evs[e.einheit_nr] = EigentumsVerhaeltnis.objects.create(
                einheit=e, person=p, beginn=date(2020, 1, 1))

        we05 = self.einheiten[4]
        verkaeufer = Person.objects.create(
            person_typ='100', anrede='Herr', vorname='V', nachname='Verkaeufer')
        EigentumsVerhaeltnis.objects.create(
            einheit=we05, person=verkaeufer, beginn=date(2020, 1, 1), ende=date(2025, 6, 30))
        self.kaeuferin = Person.objects.create(
            person_typ='100', anrede='Frau', vorname='K', nachname='Kaeuferin')
        self.evs['WE05'] = EigentumsVerhaeltnis.objects.create(
            einheit=we05, person=self.kaeuferin, beginn=date(2025, 7, 1))

        # Aufwandskonto 50100 (VS 010) mit Ist-Kosten 1.000 €
        self.konto = Konto.objects.create(
            wirtschaftsjahr=self.wj, kontonummer='50100',
            kontoname='Betriebskosten', verteilerschluessel='010')
        Buchung.objects.create(
            objekt=self.objekt, betrag=Decimal('1000.00'),
            buchungsdatum=date(2025, 5, 10), status='festgeschrieben',
            soll_konto=self.konto, wirtschaftsjahr=self.wj)

        # Hausgeld-Sollstellungen je EV (Nachhol-Soll für WE05 auf Käuferin)
        soll_je_einheit = {
            'WE01': '100.00', 'WE02': '200.00', 'WE03': '150.00',
            'WE04': '150.00', 'WE05': '500.00',
        }
        for nr, betrag in soll_je_einheit.items():
            self._create_hausgeld_soll(self.evs[nr], betrag)

    def _create_hausgeld_soll(self, ev, betrag, periode=date(2025, 1, 1)):
        return HausgeldSollstellung.objects.create(
            objekt=self.objekt, eigentumsverhaeltnis=ev,
            sollstellungs_typ='hausgeld', periode=periode, faellig_am=periode,
            opos_nr=f'OP-{uuid4().hex[:10]}', soll_betrag=Decimal(betrag),
            erstellt_von=self.user)

    # -----------------------------------------------------------------------
    # Kap. 11.2 — vollständiger Durchlauf 1→8
    # -----------------------------------------------------------------------

    def test_voller_wizard_durchlauf(self):
        # Schritt 1 — Anlage
        resp = self.client.post(BASE, {
            'objekt': str(self.objekt.id), 'wirtschaftsjahr': str(self.wj.id)})
        self.assertEqual(resp.status_code, 201, resp.content)
        ja_id = resp.data['id']

        # Schritt 2 — Buchungsprüfung: keine offenen Kreditor-OPs → nicht blockiert
        resp = self.client.get(f'{BASE}{ja_id}/schritt/2/')
        self.assertFalse(resp.data['daten']['blockiert'])

        # Schritt 3 — Kostenstellen: Ist 1.000, kein WP
        resp = self.client.get(f'{BASE}{ja_id}/kostenstellen/')
        self.assertEqual(resp.data['summe_ist'], '1000.00')
        self.assertFalse(resp.data['wirtschaftsplan_vorhanden'])

        # Schritt 4 — Umlageschlüssel: Konto 50100 → VS 010
        resp = self.client.get(f'{BASE}{ja_id}/umlageschluessel/')
        zeile = next(z for z in resp.data['konten'] if z['kontonummer'] == '50100')
        self.assertEqual(zeile['vs_code'], '010')

        # Schritt 5 — Rücklagen: keine Rücklagenkonten → nicht blockiert
        resp = self.client.get(f'{BASE}{ja_id}/ruecklagen/')
        self.assertFalse(resp.data['blockiert'])

        # Schritt 6 — Einzelabrechnungen berechnen
        resp = self.client.post(f'{BASE}{ja_id}/einzelabrechnungen/berechnen/')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(len(resp.data), 5)
        ergebnis = {ea['einheit_nr']: Decimal(ea['abrechnungsergebnis']) for ea in resp.data}
        self.assertEqual(ergebnis['WE01'], Decimal('100.00'))
        self.assertEqual(ergebnis['WE02'], Decimal('0.00'))
        self.assertEqual(ergebnis['WE03'], Decimal('50.00'))
        self.assertEqual(ergebnis['WE04'], Decimal('50.00'))
        self.assertEqual(ergebnis['WE05'], Decimal('-300.00'))
        # WE05 trägt Eigentümerwechsel-Fußnote, Adressat = Käuferin
        we05 = next(ea for ea in resp.data if ea['einheit_nr'] == 'WE05')
        self.assertTrue(we05['hinweis_eigentuemerwechsel'])
        self.assertIn('Kaeuferin', we05['eigentuemer_name'])

        # Schritt 7 — PDF-Vorschau (Fußnote bei WE05)
        we05_id = str(self.einheiten[4].id)
        resp = self.client.get(f'{BASE}{ja_id}/pdf-vorschau/', {'einheit': we05_id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertTrue(resp.content.startswith(b'%PDF'))

        # Schritt 8 — Freigabe
        resp = self.client.post(f'{BASE}{ja_id}/freigeben/')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['jahresabrechnung']['status'], 'gesperrt')
        self.assertEqual(resp.data['guthaben_einheiten'], 1)
        self.assertIn('Auszahlungslauf', resp.data['hinweis'])

        # 4 Sollstellungen 'abrechnungsergebnis' (WE02 mit 0 wird übersprungen)
        ja = Jahresabrechnung.objects.get(pk=ja_id)
        ss = HausgeldSollstellung.objects.filter(
            sollstellungslauf=ja.sollstellungslauf,
            sollstellungs_typ='abrechnungsergebnis')
        self.assertEqual(ss.count(), 4)
        # Guthaben WE05: negative Sollstellung
        guthaben = ss.filter(soll_betrag__lt=0)
        self.assertEqual(guthaben.count(), 1)
        self.assertEqual(guthaben.first().soll_betrag, Decimal('-300.00'))
        # keine Sachkontenbuchung durch Schritt 8
        self.assertEqual(
            Buchung.objects.filter(objekt=self.objekt).exclude(status='storniert').count(), 1)

    def test_guthaben_kein_automatischer_auszahlungslauf(self):
        """Kap. 11.2 / 12: Guthaben erzeugt keinen Auszahlungslauf automatisch."""
        resp = self.client.post(BASE, {
            'objekt': str(self.objekt.id), 'wirtschaftsjahr': str(self.wj.id)})
        ja_id = resp.data['id']
        self.client.post(f'{BASE}{ja_id}/einzelabrechnungen/berechnen/')
        self.client.post(f'{BASE}{ja_id}/freigeben/')
        # Genau ein Lauf (abrechnungsergebnis), kein weiterer Auszahlungslauf
        laeufe = HausgeldSollstellungslauf.objects.filter(objekt=self.objekt)
        self.assertEqual(laeufe.count(), 1)
        self.assertEqual(laeufe.first().typ, 'abrechnungsergebnis_jahr')

    def test_wiederanlage_blockiert(self):
        """Kap. 12 Punkt 6: erneute Anlage für dieselbe Objekt/WJ-Kombi blockiert."""
        resp = self.client.post(BASE, {
            'objekt': str(self.objekt.id), 'wirtschaftsjahr': str(self.wj.id)})
        ja_id = resp.data['id']
        self.client.post(f'{BASE}{ja_id}/einzelabrechnungen/berechnen/')
        self.client.post(f'{BASE}{ja_id}/freigeben/')
        resp = self.client.post(BASE, {
            'objekt': str(self.objekt.id), 'wirtschaftsjahr': str(self.wj.id)})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('bereits', resp.data['error'])

    # -----------------------------------------------------------------------
    # Kap. 11.2 — Blocker-Szenarien
    # -----------------------------------------------------------------------

    def test_schritt2_offener_kreditor_op_blockiert(self):
        from apps.rechnungen.models import Kreditor
        kreditor = Kreditor.objects.create(name='Handwerk GmbH')
        KreditorOP.objects.create(
            op_nummer=970001, kreditor=kreditor, objekt=self.objekt,
            betrag_ursprung=Decimal('500.00'), betrag_offen=Decimal('500.00'),
            faellig_ab=date(2025, 8, 1), status='offen')
        resp = self.client.post(BASE, {
            'objekt': str(self.objekt.id), 'wirtschaftsjahr': str(self.wj.id)})
        ja_id = resp.data['id']
        # Schritt 2 meldet Blockade
        resp = self.client.get(f'{BASE}{ja_id}/schritt/2/')
        self.assertTrue(resp.data['daten']['blockiert'])
        # Freigabe wird trotz berechneter EAs verweigert
        self.client.post(f'{BASE}{ja_id}/einzelabrechnungen/berechnen/')
        resp = self.client.post(f'{BASE}{ja_id}/freigeben/')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Kreditoren-OP', resp.data['error'])

    def test_schritt5_bankabweichung_blockiert(self):
        """Rücklagen-Endbestand != Bankauszug → Freigabe gesperrt."""
        bk = Bankkonto.objects.create(
            objekt=self.objekt, konto_typ='ruecklage',
            bezeichnung='Erhaltungsrücklage', reihenfolge=1)
        # Bankauszug 10.000, aber keine passenden Nebenbuch-Bewegungen → Abweichung
        Kontoumsatz.objects.create(
            objekt=self.objekt, bankkonto=bk,
            sha256_hash=uuid4().hex + uuid4().hex[:32],
            betrag=Decimal('10000.00'), buchungsdatum=date(2025, 3, 1),
            status='verbucht')
        # Zuführung im Nebenbuch, die der Bankauszug NICHT zeigt → Differenz
        ev = self.evs['WE01']
        ss = HausgeldSollstellung.objects.create(
            objekt=self.objekt, eigentumsverhaeltnis=ev,
            sollstellungs_typ='hausgeld', periode=date(2025, 2, 1),
            faellig_am=date(2025, 2, 1), opos_nr=f'OP-{uuid4().hex[:10]}',
            soll_betrag=Decimal('500.00'), erstellt_von=self.user)
        from apps.buchhaltung.models import SollstellungSplit, SollstellungZahlung
        ba911, _ = Buchungsart.objects.get_or_create(
            nr='911', defaults=dict(bezeichnung='Zuführung Rücklage',
                                    bankkonto_typ='ruecklage_nach_index'))
        split = SollstellungSplit.objects.create(
            sollstellung=ss, ba=ba911, betrag=Decimal('500.00'))
        buchung = Buchung.objects.create(
            objekt=self.objekt, betrag=Decimal('500.00'),
            buchungsdatum=date(2025, 2, 2), status='festgeschrieben')
        SollstellungZahlung.objects.create(
            sollstellung=ss, split=split, buchung=buchung,
            betrag=Decimal('500.00'), erstellt_von=self.user)

        resp = self.client.post(BASE, {
            'objekt': str(self.objekt.id), 'wirtschaftsjahr': str(self.wj.id)})
        ja_id = resp.data['id']
        resp = self.client.get(f'{BASE}{ja_id}/ruecklagen/')
        self.assertTrue(resp.data['blockiert'])
        self.client.post(f'{BASE}{ja_id}/einzelabrechnungen/berechnen/')
        resp = self.client.post(f'{BASE}{ja_id}/freigeben/')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Rücklagen', resp.data['error'])

    def test_schritt6_fehlender_verbrauchswert_blockiert_freigabe(self):
        """Konto mit Verbrauchs-VS 140 ohne EinheitVerbrauch → VS-Fehler → Freigabe gesperrt."""
        Konto.objects.create(
            wirtschaftsjahr=self.wj, kontonummer='50200',
            kontoname='Heizung', verteilerschluessel='140')
        Buchung.objects.create(
            objekt=self.objekt, betrag=Decimal('600.00'),
            buchungsdatum=date(2025, 4, 1), status='festgeschrieben',
            soll_konto=Konto.objects.get(wirtschaftsjahr=self.wj, kontonummer='50200'),
            wirtschaftsjahr=self.wj)
        self.assertEqual(
            EinheitVerbrauch.objects.filter(einheit__objekt=self.objekt).count(), 0)

        resp = self.client.post(BASE, {
            'objekt': str(self.objekt.id), 'wirtschaftsjahr': str(self.wj.id)})
        ja_id = resp.data['id']
        resp = self.client.post(f'{BASE}{ja_id}/einzelabrechnungen/berechnen/')
        # Berechnung läuft, aber Positionen tragen VS-Fehler
        self.assertTrue(any(
            any(p.get('fehler') for p in ea['positionen']) for ea in resp.data))
        resp = self.client.post(f'{BASE}{ja_id}/freigeben/')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Verteilerschlüssel', resp.data['error'])
