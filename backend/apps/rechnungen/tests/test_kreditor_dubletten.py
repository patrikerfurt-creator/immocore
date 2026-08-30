"""
Tests für die Kreditor-Dublettenprüfung beim Rechnungsimport.

Schwerpunkte:
  - vereinheitlichte Normalisierung (die eigentliche Ursache der Doppelungen)
  - dreiwertiger Abgleich: sicher / verdacht / neu
  - die drei menschlichen Entscheidungen inkl. Audit-Feldern
  - keine Buchbarkeit, solange der Fall offen ist
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.rechnungen.models import (
    Kreditor,
    KreditorBankverbindung,
    KreditorDublettenPruefung,
    Rechnung,
)
from apps.rechnungen.normalisierung import normalisiere_kreditorname
from apps.rechnungen.services import kreditor_dubletten
from apps.rechnungen.services.kreditor_matching import (
    ANLASS_IBAN_ABWEICHUNG,
    ANLASS_NAME_ABWEICHUNG,
    gleiche_kreditoren,
)

User = get_user_model()

IBAN_A = 'DE89370400440532013000'
IBAN_B = 'DE02120300000000202051'
IBAN_C = 'DE43500400000373801000'


class NormalisierungTest(TestCase):
    def test_rechtsformen_werden_entfernt(self):
        self.assertEqual(normalisiere_kreditorname('Meier GmbH'), 'meier')
        self.assertEqual(normalisiere_kreditorname('Meier & Sohn KG'), 'meier & sohn')

    def test_gross_klein_und_sonderzeichen(self):
        self.assertEqual(
            normalisiere_kreditorname('EMG Evzi Memeti Gebäudeservice GmbH'),
            'emg evzi memeti gebäudeservice',
        )

    def test_leerer_name(self):
        self.assertEqual(normalisiere_kreditorname(''), '')

    def test_save_leitet_immer_ab(self):
        """Der Kern der Ursachenbehebung: egal wer anlegt, das Feld ist gleich."""
        k = Kreditor.objects.create(name='Meier GmbH')
        self.assertEqual(k.name_normalisiert, 'meier')

    def test_save_ignoriert_von_aussen_gesetzten_wert(self):
        k = Kreditor.objects.create(name='Meier GmbH', name_normalisiert='meier gmbh')
        self.assertEqual(k.name_normalisiert, 'meier')

    def test_namensaenderung_zieht_normalisierung_nach(self):
        k = Kreditor.objects.create(name='Meier GmbH')
        k.name = 'Schmidt AG'
        k.save(update_fields=['name'])
        k.refresh_from_db()
        self.assertEqual(k.name_normalisiert, 'schmidt')


class AbgleichTest(TestCase):
    def setUp(self):
        self.bestand = Kreditor.objects.create(name='EMG Gebäudeservice GmbH', iban=IBAN_A)

    def test_iban_treffer_ist_sicher(self):
        e = gleiche_kreditoren('EMG Gebäudeservice GmbH', IBAN_A)
        self.assertTrue(e.sicher)
        self.assertEqual(e.kreditor, self.bestand)

    def test_name_exakt_ohne_iban_ist_sicher(self):
        e = gleiche_kreditoren('EMG Gebäudeservice GmbH', '')
        self.assertTrue(e.sicher)

    def test_voellig_anderer_name_ist_neu(self):
        e = gleiche_kreditoren('Gärtnerei Sonnenschein', IBAN_B)
        self.assertTrue(e.neu)

    def test_aehnlicher_name_ist_verdacht(self):
        e = gleiche_kreditoren('EMG Gebäudeservice', IBAN_B)
        self.assertTrue(e.verdacht)
        self.assertTrue(e.kandidaten)

    def test_bekannter_name_mit_neuer_iban_ist_verdacht(self):
        """Rechnungsbetrug-Muster — wichtiger als reine Namensähnlichkeit."""
        e = gleiche_kreditoren('EMG Gebäudeservice GmbH', IBAN_B)
        self.assertTrue(e.verdacht)
        self.assertEqual(e.anlass, ANLASS_IBAN_ABWEICHUNG)

    def test_bekannte_iban_mit_fremdem_namen_ist_verdacht(self):
        e = gleiche_kreditoren('Völlig Andere Firma', IBAN_A)
        self.assertTrue(e.verdacht)
        self.assertEqual(e.anlass, ANLASS_NAME_ABWEICHUNG)

    def test_zweitkonto_wird_gefunden(self):
        KreditorBankverbindung.objects.create(kreditor=self.bestand, iban=IBAN_C)
        e = gleiche_kreditoren('EMG Gebäudeservice GmbH', IBAN_C)
        self.assertTrue(e.sicher)
        self.assertEqual(e.kreditor, self.bestand)

    def test_deaktivierter_kreditor_wird_nicht_uebergangen(self):
        """Sonst legt der Import beim naechsten Beleg stillschweigend neu an."""
        self.bestand.aktiv = False
        self.bestand.save(update_fields=['aktiv'])

        e = gleiche_kreditoren('EMG Gebäudeservice GmbH', IBAN_A)
        self.assertFalse(e.sicher)
        self.assertTrue(e.verdacht)

    def test_rechtsform_allein_erzeugt_keinen_verdacht(self):
        """Zwei beliebige GmbHs duerfen sich nicht wegen 'gmbh' aehneln."""
        e = gleiche_kreditoren('Zimmerei Nordwind GmbH', IBAN_B)
        self.assertTrue(e.neu, f'Unerwartete Kandidaten: {[k.kreditor.name for k in e.kandidaten]}')


class EntscheidungTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='pruefer')
        self.bestand = Kreditor.objects.create(name='EMG Gebäudeservice GmbH', iban=IBAN_A)
        self.rechnung = Rechnung.objects.create(
            dateiname='r.pdf', pfad='/tmp/r.pdf', sha256_hash='h1',
            status='prueffall', duplikat_typ='kreditor_dublette',
            lieferant_name='EMG Gebaeudeservice', lieferant_iban=IBAN_B,
            rechnungsnummer='R-1', rechnungsdatum=date(2026, 5, 1),
            betrag_brutto=100,
        )
        ergebnis = gleiche_kreditoren('EMG Gebäudeservice', IBAN_B)
        self.pruefung = kreditor_dubletten.lege_pruefung_an(
            self.rechnung, ergebnis, 'EMG Gebäudeservice', IBAN_B,
        )

    def test_pruefung_haelt_rechnung_ohne_kreditor(self):
        self.assertIsNone(self.rechnung.kreditor)
        self.assertEqual(self.pruefung.status, KreditorDublettenPruefung.STATUS_OFFEN)

    def test_kandidaten_sind_eingefroren(self):
        self.assertTrue(self.pruefung.kandidaten)
        self.assertEqual(self.pruefung.kandidaten[0]['name'], 'EMG Gebäudeservice GmbH')

    def test_zuordnen_setzt_kreditor_und_audit(self):
        kreditor = kreditor_dubletten.zuordnen(self.pruefung, self.bestand.id, self.user)

        self.assertEqual(kreditor, self.bestand)
        self.rechnung.refresh_from_db()
        self.pruefung.refresh_from_db()
        self.assertEqual(self.rechnung.kreditor, self.bestand)
        self.assertEqual(self.pruefung.status, KreditorDublettenPruefung.STATUS_ZUGEORDNET)
        self.assertEqual(self.pruefung.entschieden_von, self.user)
        self.assertIsNotNone(self.pruefung.entschieden_am)

    def test_zuordnen_ergaenzt_iban_als_zweitkonto(self):
        kreditor_dubletten.zuordnen(self.pruefung, self.bestand.id, self.user)

        self.bestand.refresh_from_db()
        self.assertEqual(self.bestand.iban, IBAN_A, 'Primaere IBAN darf sich nicht aendern')
        self.assertTrue(
            KreditorBankverbindung.objects.filter(kreditor=self.bestand, iban=IBAN_B).exists()
        )

    def test_zuordnen_ohne_iban_uebernahme(self):
        kreditor_dubletten.zuordnen(
            self.pruefung, self.bestand.id, self.user, iban_uebernehmen=False,
        )
        self.assertFalse(KreditorBankverbindung.objects.filter(iban=IBAN_B).exists())

    def test_als_neu_anlegen_erzeugt_kreditor(self):
        kreditor = kreditor_dubletten.als_neu_anlegen(self.pruefung, self.user)

        self.assertNotEqual(kreditor, self.bestand)
        self.assertEqual(kreditor.iban, IBAN_B)
        self.rechnung.refresh_from_db()
        self.assertEqual(self.rechnung.kreditor, kreditor)

    def test_ablehnen_setzt_rechnung_abgelehnt_ohne_kreditor(self):
        kreditor_dubletten.ablehnen(self.pruefung, self.user, notiz='Kein gueltiger Beleg')

        self.rechnung.refresh_from_db()
        self.pruefung.refresh_from_db()
        self.assertEqual(self.rechnung.status, 'abgelehnt')
        self.assertIsNone(self.rechnung.kreditor)
        self.assertEqual(self.pruefung.notiz, 'Kein gueltiger Beleg')

    def test_zweite_entscheidung_wird_abgelehnt(self):
        kreditor_dubletten.zuordnen(self.pruefung, self.bestand.id, self.user)
        self.pruefung.refresh_from_db()

        with self.assertRaises(kreditor_dubletten.DublettenPruefungFehler):
            kreditor_dubletten.ablehnen(self.pruefung, self.user)

    def test_als_neu_anlegen_bei_belegter_iban_wird_abgelehnt(self):
        """Kreditor.iban ist unique — verstaendliche Meldung statt IntegrityError."""
        self.pruefung.erkannte_iban = IBAN_A
        self.pruefung.save(update_fields=['erkannte_iban'])

        with self.assertRaises(kreditor_dubletten.DublettenPruefungFehler):
            kreditor_dubletten.als_neu_anlegen(self.pruefung, self.user)


class DublettenApiTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='api-pruefer')
        self.client.force_authenticate(user=self.user)
        self.bestand = Kreditor.objects.create(name='EMG Gebäudeservice GmbH', iban=IBAN_A)
        self.rechnung = Rechnung.objects.create(
            dateiname='r.pdf', pfad='/tmp/r.pdf', sha256_hash='h2',
            status='prueffall', lieferant_name='EMG Gebaeudeservice',
            rechnungsnummer='R-2', betrag_brutto=50,
        )
        self.pruefung = kreditor_dubletten.lege_pruefung_an(
            self.rechnung, gleiche_kreditoren('EMG Gebäudeservice', IBAN_B),
            'EMG Gebäudeservice', IBAN_B,
        )
        self.basis = f'/api/v1/kreditor-dubletten/{self.pruefung.id}/'

    def test_liste_zeigt_offene_faelle(self):
        response = self.client.get('/api/v1/kreditor-dubletten/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['anlass'], self.pruefung.anlass)

    def test_zuordnen_ueber_api(self):
        response = self.client.post(f'{self.basis}zuordnen/', {
            'kreditor_id': str(self.bestand.id),
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], KreditorDublettenPruefung.STATUS_ZUGEORDNET)

    def test_zuordnen_ohne_kreditor_id(self):
        response = self.client.post(f'{self.basis}zuordnen/', {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_als_neu_anlegen_ueber_api(self):
        response = self.client.post(f'{self.basis}als-neu-anlegen/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], KreditorDublettenPruefung.STATUS_NEU_ANGELEGT)

    def test_ablehnen_ueber_api(self):
        response = self.client.post(f'{self.basis}ablehnen/', {'notiz': 'Spam'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], KreditorDublettenPruefung.STATUS_ABGELEHNT)

    def test_erledigte_faelle_nicht_in_der_arbeitsliste(self):
        self.client.post(f'{self.basis}ablehnen/')
        response = self.client.get('/api/v1/kreditor-dubletten/')
        self.assertEqual(len(response.data), 0)

    def test_ohne_login_kein_zugriff(self):
        self.client.force_authenticate(user=None)
        response = self.client.get('/api/v1/kreditor-dubletten/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
