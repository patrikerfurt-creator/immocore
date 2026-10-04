"""Test 14: KI-Assistent im Vorlagen-Editor (Spec 6).

Der KI-Client (``anthropic.Anthropic``) ist überall gemockt - es findet kein echter API-Aufruf statt.
"""
import json
from types import SimpleNamespace
from unittest import mock

import anthropic
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.korrespondenz.models import Textbaustein
from apps.korrespondenz.services import registry, vorlagen_assistent_service as assistent

from . import fixtures
from .basis_versand import neue_person

URL = '/api/v1/korrespondenz/vorlagen-assistent/'
MIT_KEY = override_settings(ANTHROPIC_API_KEY='test-key')

SAUBER = [
    {'typ': 'text', 'inhalt': 'wir begrüßen Sie in {{ objekt.bezeichnung }}. Ihr Hausgeld beträgt '
                              '{{ hausgeld.monatsbetrag | euro }} ab dem {{ hausgeld.gueltig_ab | datum }}.'},
    {'typ': 'tabelle', 'quelle': 'hausgeld.positionen'},
    {'typ': 'bedingt', 'bedingung': 'ev.sepa_mandat_fehlt',
     'inhalt': 'Bitte senden Sie uns das SEPA-Mandat (IBAN {{ bank.iban | iban }}).'},
]


def ki_antwort(inhalt) -> mock.MagicMock:
    """Gemockter ``anthropic.Anthropic``-Client, der ``inhalt`` (dict/list/str) als Text liefert."""
    text = inhalt if isinstance(inhalt, str) else json.dumps(inhalt, ensure_ascii=False)
    client = mock.MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type='text', text=text)])
    return client


def entwerfe(inhalt, anlass='eigentuemer_begruessung', stichworte='freundlich', **kw):
    client = ki_antwort(inhalt)
    with mock.patch('anthropic.Anthropic', return_value=client):
        ergebnis = assistent.entwerfe(anlass, stichworte, **kw)
    return ergebnis, client


@MIT_KEY
class OutputValidierungTest(TestCase):
    """Markierung von Verstößen im KI-Output in ``hinweise``."""

    def test_sauberer_entwurf_ohne_hinweise(self):
        ergebnis, _ = entwerfe({'betreff': 'Willkommen', 'bloecke': SAUBER})
        self.assertEqual(ergebnis['hinweise'], [])
        self.assertEqual(ergebnis['bloecke'], SAUBER)
        self.assertEqual(ergebnis['betreff'], 'Willkommen')

    def test_literaler_betrag_wird_markiert(self):
        for text in ('Das Hausgeld beträgt 350,00 € monatlich.', 'Bitte zahlen Sie 1.250,50 EUR.',
                     'Die Gebühr liegt bei 5 Euro.', 'Der Betrag von € 40 ist fällig.',
                     'Es sind 350,00 offen.'):
            with self.subTest(text=text):
                ergebnis, _ = entwerfe({'bloecke': [{'typ': 'text', 'inhalt': text}]})
                self.assertEqual(len(ergebnis['hinweise']), 1, ergebnis)
                self.assertIn('Betrag', ergebnis['hinweise'][0])
                self.assertIn('Block 1', ergebnis['hinweise'][0])

    def test_literale_iban_wird_markiert(self):
        for iban in ('DE02 5019 0000 6300 2110 10', 'DE02501900006300211010'):
            with self.subTest(iban=iban):
                ergebnis, _ = entwerfe({'bloecke': [{'typ': 'text', 'inhalt': f'Bitte überweisen Sie auf {iban}.'}]})
                self.assertTrue(any('IBAN' in h for h in ergebnis['hinweise']), ergebnis)

    def test_literales_datum_wird_markiert(self):
        for text in ('Die Versammlung ist am 15.10.2026.', 'Bitte bis 15.10. zahlen.',
                     'Termin: 15. Oktober 2026.', 'Im Oktober 2026 folgt die Abrechnung.',
                     'Stichtag 2026-10-15.'):
            with self.subTest(text=text):
                ergebnis, _ = entwerfe({'bloecke': [{'typ': 'text', 'inhalt': text}]})
                self.assertTrue(any('Datum' in h for h in ergebnis['hinweise']), ergebnis)

    def test_literal_in_platzhalter_und_allgemeine_zahlen_sind_kein_verstoss(self):
        ergebnis, _ = entwerfe({'bloecke': [{
            'typ': 'text',
            'inhalt': "Zahlung {{ mahnung.gesamtbetrag | euro }} bis {{ mahnung.frist | datum }}, "
                      "Vorgang 42, 14 Tage Frist, {{ verwaltung.betreuer_telefon | default('069-1234') }}."}]},
            anlass='mahnung_stufe_1')
        self.assertEqual(ergebnis['hinweise'], [])

    def test_literale_in_titel_der_anlageseite_werden_erkannt(self):
        ergebnis, _ = entwerfe({'bloecke': [{'typ': 'anlage_seite', 'titel': 'Vollmacht vom 01.01.2026',
                                             'inhalt': 'Hiermit bevollmächtige ich ...'}]})
        self.assertTrue(any('Datum' in h and 'anlage_seite' in h for h in ergebnis['hinweise']))

    def test_unbekannter_platzhalter_wird_markiert(self):
        ergebnis, _ = entwerfe({'bloecke': [
            {'typ': 'text', 'inhalt': 'Hallo {{ empfaenger.geburtstag }}, Konto {{ konto.saldo }}.'}]})
        hinweise = ' | '.join(ergebnis['hinweise'])
        self.assertIn('empfaenger.geburtstag', hinweise)
        self.assertIn('konto.saldo', hinweise)

    def test_platzhalter_eines_anderen_anlasses_ist_unbekannt(self):
        # mahnung.* gehört nicht zur Begrüßung
        ergebnis, _ = entwerfe({'bloecke': [{'typ': 'text', 'inhalt': 'Offen: {{ mahnung.gesamtbetrag | euro }}'}]})
        self.assertTrue(any('mahnung.gesamtbetrag' in h for h in ergebnis['hinweise']))

    def test_unbekannter_platzhalter_in_bedingung_liste_und_betreff(self):
        ergebnis, _ = entwerfe({'betreff': 'Hallo {{ empfaenger.spitzname }}', 'bloecke': [
            {'typ': 'bedingt', 'bedingung': 'ev.gibt_es_nicht', 'inhalt': 'Text'},
            {'typ': 'liste', 'quelle': 'eingabe.tagesordnung'}]})
        hinweise = ' | '.join(ergebnis['hinweise'])
        self.assertIn('ev.gibt_es_nicht', hinweise)
        self.assertIn('eingabe.tagesordnung', hinweise)          # ohne Eingabefeld-Definition unbekannt
        self.assertIn('Betreff', hinweise)
        self.assertIn('empfaenger.spitzname', hinweise)

    def test_eingabefelder_machen_eingabe_platzhalter_bekannt(self):
        felder = [{'name': 'tagesordnung', 'label': 'Tagesordnung', 'typ': 'liste', 'pflicht': True}]
        ergebnis, _ = entwerfe({'bloecke': [{'typ': 'liste', 'quelle': 'eingabe.tagesordnung'}]},
                               anlass='etv_einladung', eingabefelder=felder)
        self.assertEqual(ergebnis['hinweise'], [])

    def test_syntaxfehler_im_platzhalter(self):
        ergebnis, _ = entwerfe({'bloecke': [{'typ': 'text', 'inhalt': 'Hallo {{ empfaenger.name '}]})
        self.assertTrue(any('Platzhalter-Syntax' in h for h in ergebnis['hinweise']))

    def test_ungueltige_blockstruktur_wird_gemeldet(self):
        ergebnis, _ = entwerfe({'bloecke': [
            {'typ': 'text', 'inhalt': 'ok'},
            {'typ': 'gedicht', 'inhalt': 'Rosen sind rot'},        # unbekannter Typ -> verworfen
            'kein objekt',                                         # verworfen
            {'typ': 'tabelle'},                                    # quelle fehlt
            {'typ': 'bedingt', 'inhalt': 'x'},                     # bedingung fehlt
            {'typ': 'anlage_seite', 'inhalt': 'x'},                # titel fehlt
            {'typ': 'liste'},                                      # quelle fehlt
            {'typ': 'seitenumbruch'},
        ]})
        self.assertEqual([b['typ'] for b in ergebnis['bloecke']],
                         ['text', 'tabelle', 'bedingt', 'anlage_seite', 'liste', 'seitenumbruch'])
        hinweise = ' | '.join(ergebnis['hinweise'])
        for erwartet in ('Block 2 hat keine gültige Struktur', 'Block 3 hat keine gültige Struktur',
                         '"quelle" fehlt', '"bedingung" fehlt', '"titel" fehlt'):
            self.assertIn(erwartet, hinweise)

    def test_unbekannte_tabellenquelle_und_baustein(self):
        Textbaustein.objects.create(code='da', bezeichnung='Da', inhalt='x')
        ergebnis, _ = entwerfe({'bloecke': [
            {'typ': 'tabelle', 'quelle': 'hausgeld.gibt_es_nicht'},
            {'typ': 'baustein', 'code': 'da'}, {'typ': 'baustein', 'code': 'fehlt'}]})
        hinweise = ' | '.join(ergebnis['hinweise'])
        self.assertIn('Tabellenquelle "hausgeld.gibt_es_nicht"', hinweise)
        self.assertIn('Textbaustein "fehlt"', hinweise)
        self.assertNotIn('Textbaustein "da"', hinweise)

    def test_antwort_als_json_im_codezaun_und_als_liste(self):
        ergebnis, _ = entwerfe('```json\n' + json.dumps({'bloecke': SAUBER}) + '\n```')
        self.assertEqual(ergebnis['bloecke'], SAUBER)
        ergebnis, _ = entwerfe(SAUBER)
        self.assertEqual(ergebnis['bloecke'], SAUBER)

    def test_unlesbare_antwort_ist_fehler(self):
        for text in ('Leider kann ich das nicht.', '{"bloecke": [', '{"anderes": 1}'):
            with self.subTest(text=text), self.assertRaises(assistent.AssistentFehler):
                entwerfe(text)

    def test_leere_bloecke_werden_gemeldet(self):
        ergebnis, _ = entwerfe({'bloecke': []})
        self.assertEqual(ergebnis['bloecke'], [])
        self.assertTrue(ergebnis['hinweise'])


@MIT_KEY
class KeinePersonenbezogenenWerteTest(TestCase):
    """Die KI erhält nur Anlass, Stichworte und Platzhalter-Metadaten - nie Werte."""

    @classmethod
    def setUpTestData(cls):
        cls.s = fixtures.szenario()
        cls.person = neue_person('Zzyzxbergstein', email='geheim.person@example.org')

    def gesendet(self, **kw):
        _, client = entwerfe({'bloecke': SAUBER}, **kw)
        self.assertEqual(client.messages.create.call_count, 1)
        aufruf = client.messages.create.call_args.kwargs
        (nachricht,) = aufruf['messages']
        return aufruf, aufruf['system'] + '\n' + nachricht['content']

    def test_prompt_enthaelt_nur_metadaten(self):
        aufruf, alles = self.gesendet(stichworte='freundliche Begrüßung, SEPA-Hinweis')
        self.assertIn('freundliche Begrüßung, SEPA-Hinweis', alles)
        self.assertIn('eigentuemer_begruessung', alles)
        for p in registry.metadaten('eigentuemer_begruessung'):        # Name + Beschreibung sind drin
            self.assertIn(p['name'], alles)
            self.assertIn(p['beschreibung'], alles)
        # ... aber weder Beispielwerte der Registry ...
        beispiele = [str(p['beispiel']) for p in registry.PLATZHALTER
                     if isinstance(p['beispiel'], str) and len(p['beispiel']) > 5]
        self.assertTrue(beispiele)
        for beispiel in beispiele:
            self.assertNotIn(beispiel, alles)
        # ... noch Werte aus der Datenbank
        s = self.s
        for wert in (self.person.nachname, 'geheim.person@example.org', s.person.nachname, s.person.name,
                     s.objekt.bezeichnung, fixtures.TEST_IBAN):
            self.assertNotIn(str(wert), alles)
        self.assertEqual(aufruf['max_tokens'], assistent.MAX_TOKENS)

    def test_prompt_je_anlass_nur_dessen_platzhalter(self):
        _, alles = self.gesendet(anlass='mahnung_stufe_1')
        self.assertIn('mahnung.gesamtbetrag', alles)
        self.assertNotIn('wechsel.voreigentuemer_name', alles)
        self.assertNotIn('vorgang.betreff', alles)

    def test_ueberarbeiten_uebergibt_nur_den_block(self):
        block = {'typ': 'text', 'inhalt': 'wir freuen uns, {{ empfaenger.name }} zu begrüßen.'}
        _, alles = self.gesendet(stichworte='kürzer und förmlicher', block=block)
        self.assertIn('kürzer und förmlicher', alles)
        self.assertIn('wir freuen uns, {{ empfaenger.name }} zu begrüßen.', alles)
        self.assertIn('Überarbeite genau diesen einen Block', alles)
        self.assertNotIn('Zzyzxbergstein', alles)

    def test_eingabefelder_nur_name_und_label(self):
        felder = [{'name': 'versammlung_ort', 'label': 'Ort der Versammlung', 'typ': 'text',
                   'pflicht': True, 'default': 'GEHEIMER-DEFAULT'}]
        _, alles = self.gesendet(anlass='etv_einladung', eingabefelder=felder)
        self.assertIn('eingabe.versammlung_ort', alles)
        self.assertIn('Ort der Versammlung', alles)
        self.assertNotIn('GEHEIMER-DEFAULT', alles)

    def test_client_mit_timeout_60(self):
        client = ki_antwort({'bloecke': SAUBER})
        with mock.patch('anthropic.Anthropic', return_value=client) as klasse:
            assistent.entwerfe('eigentuemer_begruessung', 'x')
        self.assertEqual(klasse.call_args.kwargs['timeout'], 60.0)
        self.assertEqual(klasse.call_args.kwargs['api_key'], 'test-key')


class FehlerfaelleTest(TestCase):

    @override_settings(ANTHROPIC_API_KEY='')
    def test_ohne_api_key_nicht_verfuegbar(self):
        self.assertFalse(assistent.ist_verfuegbar())
        with mock.patch('anthropic.Anthropic') as klasse, self.assertRaises(assistent.AssistentNichtVerfuegbar):
            assistent.entwerfe('eigentuemer_begruessung', 'x')
        klasse.assert_not_called()

    @MIT_KEY
    def test_unbekannter_anlass(self):
        with self.assertRaises(ValueError):
            assistent.entwerfe('gibt_es_nicht', 'x')

    @MIT_KEY
    def test_zeitueberschreitung(self):
        client = mock.MagicMock()
        client.messages.create.side_effect = anthropic.APITimeoutError(request=mock.MagicMock())
        with mock.patch('anthropic.Anthropic', return_value=client):
            with self.assertRaises(assistent.AssistentFehler) as ctx:
                assistent.entwerfe('eigentuemer_begruessung', 'x')
        self.assertTrue(ctx.exception.zeitueberschreitung)

    @MIT_KEY
    def test_api_fehler(self):
        client = mock.MagicMock()
        client.messages.create.side_effect = anthropic.APIConnectionError(request=mock.MagicMock())
        with mock.patch('anthropic.Anthropic', return_value=client):
            with self.assertRaises(assistent.AssistentFehler) as ctx:
                assistent.entwerfe('eigentuemer_begruessung', 'x')
        self.assertFalse(ctx.exception.zeitueberschreitung)


class AssistentApiTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model
        cls.user = get_user_model().objects.create_user('editor')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def post(self, **daten):
        daten.setdefault('anlass', 'eigentuemer_begruessung')
        daten.setdefault('stichworte', 'freundlich')
        return self.client.post(URL, daten, format='json')

    def test_ohne_anmeldung(self):
        self.assertEqual(APIClient().post(URL, {}, format='json').status_code, 401)
        self.assertEqual(APIClient().get(URL).status_code, 401)

    @override_settings(ANTHROPIC_API_KEY='')
    def test_ohne_api_key_meldet_nicht_verfuegbar(self):
        self.assertEqual(self.client.get(URL).json(), {'verfuegbar': False})
        antwort = self.post()
        self.assertEqual(antwort.status_code, 503)
        self.assertFalse(antwort.json()['verfuegbar'])
        self.assertIn('nicht verfügbar', antwort.json()['detail'])

    @MIT_KEY
    def test_verfuegbar_und_entwurf(self):
        self.assertEqual(self.client.get(URL).json(), {'verfuegbar': True})
        client = ki_antwort({'bloecke': SAUBER + [{'typ': 'text', 'inhalt': 'Zahlen Sie 99,00 €.'}]})
        with mock.patch('anthropic.Anthropic', return_value=client):
            antwort = self.post()
        self.assertEqual(antwort.status_code, 200, antwort.content)
        daten = antwort.json()
        self.assertEqual(len(daten['bloecke']), 4)
        self.assertEqual(len(daten['hinweise']), 1)
        self.assertIn('Block 4', daten['hinweise'][0])

    @MIT_KEY
    def test_eingabe_wird_geprueft(self):
        with mock.patch('anthropic.Anthropic') as klasse:
            self.assertEqual(self.post(anlass='gibt_es_nicht').status_code, 400)
            self.assertEqual(self.post(stichworte='   ').status_code, 400)
            self.assertEqual(self.post(eingabefelder=[{'name': 'Ungültig!', 'typ': 'text'}]).status_code, 400)
        klasse.assert_not_called()

    @MIT_KEY
    def test_ki_fehler_werden_uebersetzt(self):
        client = mock.MagicMock()
        request = mock.MagicMock()
        with mock.patch('anthropic.Anthropic', return_value=client):
            client.messages.create.side_effect = anthropic.APITimeoutError(request=request)
            self.assertEqual(self.post().status_code, 504)
            client.messages.create.side_effect = anthropic.APIConnectionError(request=request)
            self.assertEqual(self.post().status_code, 502)
        with mock.patch('anthropic.Anthropic', return_value=ki_antwort('kein json')):
            self.assertEqual(self.post().status_code, 502)
