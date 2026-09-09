"""
Tests für die Portal-Konto-Endpunkte (Spec Portal-Erweiterung v1.1, Kap. 6/7).

Kernaussage dieser Tests: der Portal-Saldo ist NICHT selbst gerechnet,
sondern identisch mit der internen Debitorenansicht (``mit-saldo``) — beide
rufen `saldi_je_personenkonto` auf. Zusätzlich: Datenisolation zwischen
zwei Eigentümern und die Fälligkeiten-Liste (paginiert, nur offene/
teilbezahlte, nicht-stornierte Sollstellungen der eigenen Verträge).
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory, APITestCase

from apps.buchhaltung.models import Buchung, Buchungsart, HausgeldSollstellung
from apps.konten.models import Konto, Personenkonto
from apps.konten.views import PersonenkontoViewSet
from apps.portal.services import zugang_service

from .basis import (
    erstelle_eigentuemer,
    erstelle_einheit,
    erstelle_objekt,
    verknuepfe,
)

SALDO_URL = '/api/v1/portal/personenkonto/saldo/'
FAELLIGKEITEN_URL = '/api/v1/portal/faelligkeiten/'


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PortalKontoTest(APITestCase):
    """Ein Objekt, zwei Einheiten, zwei Eigentümer — Basis für Isolation,
    Saldo-Vergleich und Fälligkeiten."""

    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username='pk-test', password='x')

        self.objekt = erstelle_objekt('PORTAL-KONTO', 'WEG Kontoweg 1')
        self.einheit_a = erstelle_einheit(self.objekt, '0001', 'EG links')
        self.einheit_b = erstelle_einheit(self.objekt, '0002', 'OG rechts')

        self.person_a = erstelle_eigentuemer(
            nachname='Saldo-A', email='saldo-a@example.org', personennummer='P-SALDO-A',
            strasse='A-Straße', hausnummer='1', telefon='0111 111',
        )
        self.person_b = erstelle_eigentuemer(
            nachname='Saldo-B', email='saldo-b@example.org', personennummer='P-SALDO-B',
            strasse='B-Straße', hausnummer='2', telefon='0222 222',
        )

        self.ev_a = verknuepfe(self.person_a, self.einheit_a)
        self.ev_b = verknuepfe(self.person_b, self.einheit_b)
        # Personenkonto wird per post_save-Signal angelegt (apps.personen.signals).
        self.pk_a = Personenkonto.objects.get(vertrag=self.ev_a)
        self.pk_b = Personenkonto.objects.get(vertrag=self.ev_b)

        self.ba_sonderumlage, _ = Buchungsart.objects.get_or_create(
            nr='930', defaults=dict(kuerzel='SU', bezeichnung='Sonderumlage'),
        )

        gemeinsam_a = dict(objekt=self.objekt, eigentumsverhaeltnis=self.ev_a, erstellt_von=self.user)

        # Zählt für den Saldo (nicht storniert), erscheint in den Fälligkeiten
        # (offen, überfällig — Fälligkeit in der Vergangenheit).
        self.ss_offen = HausgeldSollstellung.objects.create(
            sollstellungs_typ='hausgeld', periode=date(2026, 1, 1),
            faellig_am=date(2026, 1, 5), opos_nr='PK-A-0001',
            soll_betrag='300.00', status_cached='offen', **gemeinsam_a,
        )
        # Teilbezahlt: zählt mit dem VOLLEN Soll-Betrag zum Saldo, aber mit dem
        # OFFENEN Rest in den Fälligkeiten.
        self.ss_teilbezahlt = HausgeldSollstellung.objects.create(
            sollstellungs_typ='hausgeld', periode=date(2026, 2, 1),
            faellig_am=date(2026, 2, 5), opos_nr='PK-A-0002',
            soll_betrag='300.00', ist_betrag='100.00', status_cached='teilbezahlt',
            **gemeinsam_a,
        )
        # Offen, aber Fälligkeit in der Zukunft — ueberfaellig muss False sein.
        self.ss_zukunft = HausgeldSollstellung.objects.create(
            sollstellungs_typ='sonderumlage', ba=self.ba_sonderumlage,
            periode=date(2026, 3, 1), faellig_am=date(2027, 1, 5), opos_nr='PK-A-0003',
            soll_betrag='150.00', status_cached='offen', **gemeinsam_a,
        )
        # Ausgeglichen: zählt zum Saldo, darf NICHT in den Fälligkeiten stehen.
        self.ss_ausgeglichen = HausgeldSollstellung.objects.create(
            sollstellungs_typ='hausgeld', periode=date(2026, 4, 1),
            faellig_am=date(2026, 4, 5), opos_nr='PK-A-0004',
            soll_betrag='300.00', ist_betrag='300.00', status_cached='ausgeglichen',
            **gemeinsam_a,
        )
        # Storniert: darf WEDER zum Saldo NOCH zu den Fälligkeiten zählen.
        self.ss_storniert = HausgeldSollstellung.objects.create(
            sollstellungs_typ='hausgeld', periode=date(2026, 5, 1),
            faellig_am=date(2026, 5, 5), opos_nr='PK-A-0005',
            soll_betrag='999.00', status_cached='offen',
            storniert_am=timezone.now(), **gemeinsam_a,
        )

        # Fremde Sollstellung (Eigentümer B) — darf in keiner Antwort von A auftauchen.
        self.ss_fremd = HausgeldSollstellung.objects.create(
            objekt=self.objekt, eigentumsverhaeltnis=self.ev_b, erstellt_von=self.user,
            sollstellungs_typ='hausgeld', periode=date(2026, 1, 1),
            faellig_am=date(2026, 1, 5), opos_nr='PK-B-0001',
            soll_betrag='222.00', status_cached='offen',
        )

        # Haben-Seite: Zahlungseingang auf das Personenkonto A.
        self.bank_konto = Konto.objects.create(
            kontonummer='18000', kontoname='Bank Bewirtschaftung', kontoart='standard',
        )
        Buchung.objects.create(
            objekt=self.objekt, betrag='700.00', soll_konto=self.bank_konto,
            personenkonto=self.pk_a, buchungsdatum=date(2026, 2, 10),
            buchungstext='Zahlungseingang Hausgeld', status='festgeschrieben',
            erstellt_von=self.user,
        )

        # Portal-Sitzung für Eigentümer A.
        self.zugang_a, token_a = zugang_service.lade_ein(self.person_a)
        self.session_a, _, _ = zugang_service.melde_an(token_a.token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Portal {self.session_a.token}')

    # ------------------------------------------------------------------
    # Saldo
    # ------------------------------------------------------------------

    def test_saldo_liefert_nur_das_eigene_personenkonto(self):
        """Test 6: Eigentümer A bekommt nicht den Saldo von Eigentümer B."""
        response = self.client.get(SALDO_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        eintrag = response.data[0]
        self.assertEqual(eintrag['kontonummer'], self.pk_a.kontonummer)
        self.assertNotEqual(eintrag['kontonummer'], self.pk_b.kontonummer)

    def test_saldo_stimmt_mit_interner_mit_saldo_ansicht_ueberein(self):
        """Test 7: derselbe Wert wie in der internen Debitorenansicht."""
        response = self.client.get(SALDO_URL)
        portal_saldo = response.data[0]['gesamtsaldo']

        req = APIRequestFactory().get('/', {'objekt': str(self.objekt.id)})
        req.user = self.user
        interne_antwort = PersonenkontoViewSet.as_view({'get': 'mit_saldo'})(req).data
        intern = next(e for e in interne_antwort if e['id'] == str(self.pk_a.id))

        self.assertEqual(str(portal_saldo), f"{intern['saldo_offen']:.2f}")

    def test_saldo_wert_ist_rueckstand(self):
        """Soll (300+300+150+300=1050) − Haben (700) = −350 Rückstand."""
        response = self.client.get(SALDO_URL)
        self.assertEqual(response.data[0]['gesamtsaldo'], '-350.00')

    def test_aufschluesselung_summiert_sich_zum_gesamtsaldo(self):
        response = self.client.get(SALDO_URL)
        eintrag = response.data[0]
        summe = sum(Decimal(z['betrag']) for z in eintrag['aufschluesselung'])
        self.assertEqual(summe, Decimal(eintrag['gesamtsaldo']))

    def test_aufschluesselung_enthaelt_portalfreundliche_bezeichnungen(self):
        response = self.client.get(SALDO_URL)
        bezeichnungen = {z['bezeichnung'] for z in response.data[0]['aufschluesselung']}
        self.assertIn('Hausgeld', bezeichnungen)
        self.assertIn('Sonderumlage', bezeichnungen)
        self.assertIn('Ihre Zahlungen', bezeichnungen)

    def test_saldo_ohne_sitzung_kein_zugriff(self):
        self.client.credentials()
        response = self.client.get(SALDO_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_saldo_liefert_keine_internen_felder(self):
        response = self.client.get(SALDO_URL)
        eintrag = response.data[0]
        for verbotenes_feld in ('status', 'sepa_mandat', 'eigentuemer_id', 'eigentuemer_ibans'):
            self.assertNotIn(verbotenes_feld, eintrag)

    # ------------------------------------------------------------------
    # Fälligkeiten
    # ------------------------------------------------------------------

    def test_faelligkeiten_liefert_nur_offene_und_teilbezahlte_eigene(self):
        """Test 8: fremde EV, storniert und status='ausgeglichen' fallen raus."""
        response = self.client.get(FAELLIGKEITEN_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 3)

        opos_nummern = [item['periode'] for item in response.data['results']]
        # Sortierung nach faellig_am: 01/2026, 02/2026, dann Zukunft.
        self.assertEqual(opos_nummern, ['2026-01-01', '2026-02-01', '2026-03-01'])

    def test_faelligkeiten_hat_paginierten_contract(self):
        response = self.client.get(FAELLIGKEITEN_URL)
        for schluessel in ('count', 'next', 'previous', 'results'):
            self.assertIn(schluessel, response.data)

    def test_faelligkeiten_offener_betrag_bei_teilbezahlt(self):
        response = self.client.get(FAELLIGKEITEN_URL)
        teilbezahlt = next(
            item for item in response.data['results'] if item['periode'] == '2026-02-01'
        )
        self.assertEqual(teilbezahlt['offener_betrag'], '200.00')

    def test_faelligkeiten_ueberfaellig_flag(self):
        response = self.client.get(FAELLIGKEITEN_URL)
        nach_periode = {item['periode']: item for item in response.data['results']}
        self.assertTrue(nach_periode['2026-01-01']['ueberfaellig'])
        self.assertFalse(nach_periode['2026-03-01']['ueberfaellig'])

    def test_faelligkeiten_bezeichnung_ist_portalfreundlich(self):
        response = self.client.get(FAELLIGKEITEN_URL)
        nach_periode = {item['periode']: item for item in response.data['results']}
        self.assertEqual(nach_periode['2026-03-01']['bezeichnung'], 'Sonderumlage')
        self.assertEqual(nach_periode['2026-01-01']['bezeichnung'], 'Hausgeld')

    def test_faelligkeiten_liefert_keine_internen_felder(self):
        response = self.client.get(FAELLIGKEITEN_URL)
        item = response.data['results'][0]
        for verbotenes_feld in (
            'mahnkarenz_bis', 'korrektur_grund', 'nachhol_aus_wp_id',
            'opos_nr', 'status_cached', 'storniert_am',
        ):
            self.assertNotIn(verbotenes_feld, item)

    def test_faelligkeiten_ohne_sitzung_kein_zugriff(self):
        self.client.credentials()
        response = self.client.get(FAELLIGKEITEN_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

