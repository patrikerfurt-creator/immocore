"""Layout-Vorschau mit Beispieldaten: real vor Beispiel, Kennzeichnung im PDF, echtes Schreiben bleibt streng."""
from datetime import date
from decimal import Decimal

import pymupdf
from django.core.exceptions import ValidationError

from apps.korrespondenz.services import (
    beispiel_kontext_service as bk, eingabefelder_service, registry, schreiben_service, seed_daten,
    seed_service, vorschau_service,
)
from apps.objekte.models import Bankkonto, Objekt

from .basis_versand import VersandTestBasis, neue_einheit, neue_person, neues_ev

HEUTE = date(2026, 10, 1)


def seitentext(pdf: bytes) -> str:
    with pymupdf.open(stream=pdf, filetype='pdf') as doc:
        return '\n'.join(seite.get_text() for seite in doc)


def normalisiert(text: str) -> str:
    return ' '.join(text.split())


class BeispielKontextTest(VersandTestBasis):
    """Reine Funktionen des ``beispiel_kontext_service``."""

    def test_beispielkontext_deckt_alle_registry_platzhalter_ab(self):
        for anlass in registry.ANLAESSE:
            with self.subTest(anlass=anlass):
                kontext = bk.baue_beispiel_kontext(anlass, HEUTE)
                erwartet = {p['name'] for p in registry.metadaten(anlass) if p['gruppe'] != 'eingabe'}
                vorhanden = {f'{g}.{n}' for g, werte in kontext.items() for n in werte}
                self.assertEqual(vorhanden, erwartet)
                self.assertNotIn('eingabe', kontext)

    def test_anlassspezifische_gruppen_sind_enthalten(self):
        self.assertIn('wechsel', bk.baue_beispiel_kontext('eigentuemer_begruessung', HEUTE))
        self.assertIn('mahnung', bk.baue_beispiel_kontext('mahnung_stufe_1', HEUTE))
        self.assertIn('vorgang', bk.baue_beispiel_kontext('vorgang_antwort', HEUTE))
        self.assertIn('versammlung', bk.baue_beispiel_kontext('etv_einladung', HEUTE))

    def test_beispiele_sind_typisiert(self):
        k = bk.baue_beispiel_kontext('mahnung_stufe_2', HEUTE)
        self.assertEqual(k['mahnung']['gebuehr'], Decimal('5.00'))
        self.assertEqual(k['mahnung']['frist'], date(2026, 10, 13))
        self.assertEqual(k['mahnung']['stufe'], 1)
        zeile = k['mahnung']['offene_posten'][0]
        self.assertEqual(zeile['faellig_ab'], date(2026, 8, 1))
        self.assertEqual(zeile['betrag_offen'], Decimal('350.00'))
        h = bk.baue_beispiel_kontext('eigentuemer_begruessung', HEUTE)['hausgeld']
        self.assertEqual(h['monatsbetrag'], Decimal('350.00'))
        self.assertEqual(h['positionen'][1]['betrag'], Decimal('50.00'))
        self.assertEqual(h['gueltig_ab'], date(2026, 9, 1))

    def test_fehlendes_registry_beispiel_wird_typgerecht_ersetzt(self):
        def eintrag(typ):
            return {'name': 'x.y_z', 'typ': typ, 'beispiel': None}
        self.assertEqual(bk.beispielwert(eintrag('datum'), HEUTE), HEUTE)
        self.assertEqual(bk.beispielwert(eintrag('betrag'), HEUTE), Decimal('100.00'))
        self.assertEqual(bk.beispielwert(eintrag('text'), HEUTE), 'Beispiel y_z')
        self.assertEqual(bk.beispielwert(eintrag('zahl'), HEUTE), 1)

    def test_merge_real_gewinnt_nur_wenn_nicht_leer(self):
        beispiel = {'g': {'a': 'B-a', 'b': 'B-b', 'c': 'B-c', 'd': 'B-d', 'e': 'B-e'}}
        real = {'g': {'a': 'R-a', 'b': '', 'c': None, 'd': [], 'e': False}}
        self.assertEqual(
            bk.mische_real_vor_beispiel(real, beispiel)['g'],
            {'a': 'R-a', 'b': 'B-b', 'c': 'B-c', 'd': 'B-d', 'e': False},   # False ist ein realer Wert
        )

    def test_merge_fehlende_gruppe_kommt_aus_beispiel(self):
        beispiel = {'wechsel': {'wechsel_datum': HEUTE}}
        self.assertEqual(bk.mische_real_vor_beispiel({}, beispiel), beispiel)

    def test_merge_optionales_leer_bleibt_leer(self):
        beispiel = {'empfaenger': {'briefanrede2': 'B2', 'name': 'B'}}
        real = {'empfaenger': {'briefanrede2': '', 'name': ''}}
        self.assertEqual(
            bk.mische_real_vor_beispiel(real, beispiel)['empfaenger'], {'briefanrede2': '', 'name': 'B'})

    def test_eingabewerte_je_typ(self):
        felder = [
            {'name': 'a', 'typ': 'text', 'label': 'Ort'}, {'name': 'b', 'typ': 'datum'},
            {'name': 'c', 'typ': 'betrag'}, {'name': 'd', 'typ': 'liste'},
            {'name': 'e', 'typ': 'ja_nein'}, {'name': 'f', 'typ': 'uhrzeit'},
            {'name': 'g', 'typ': 'mehrzeilig'}, {'name': 'h', 'typ': 'text', 'default': 'Vorgabe'},
            {'name': 'i', 'typ': 'text'},
        ]
        werte = bk.fuelle_eingabewerte(felder, {'i': 'Eigener Wert'}, HEUTE)
        self.assertEqual(werte['a'], 'Beispiel Ort')
        self.assertEqual(werte['b'], HEUTE)
        self.assertEqual(werte['c'], Decimal('100.00'))
        self.assertEqual(werte['d'], ['Beispiel 1', 'Beispiel 2'])
        self.assertIs(werte['e'], True)
        self.assertNotIn('h', werte)                    # Default des Feldes greift in der Validierung
        self.assertEqual(werte['i'], 'Eigener Wert')    # Aufrufer hat Vorrang
        self.assertTrue(eingabefelder_service.validiere(felder, werte).gueltig)


class VorschauBeispieldatenTest(VersandTestBasis):

    def setUp(self):
        # reale Person/Einheit mit eindeutigen Werten (unterscheidbar von den Registry-Beispielen)
        self.person = neue_person('Eichhorn')
        self.einheit = neue_einheit(self.s.objekt, '77')
        neues_ev(self.einheit, self.person)

    def vorschau(self, version, **kw):
        kw.setdefault('einheit', self.einheit)
        return vorschau_service.erzeuge_vorschau_pdf(version, self.person, user=self.user, **kw)

    def begruessung(self, inhalt=None):
        inhalt = inhalt or [{'typ': 'text', 'inhalt': (
            'Wechsel am {{ wechsel.wechsel_datum|datum }}, Vorbesitzer {{ wechsel.voreigentuemer_name }}. '
            'Betreuer {{ verwaltung.betreuer_name }} ({{ verwaltung.betreuer_email }}).')}]
        return self.vorlage('begruessung_test', 'eigentuemer_begruessung', inhalt=inhalt)

    def test_begruessung_ohne_wechsel_und_betreuer_rendert(self):
        Objekt.objects.filter(pk=self.s.objekt.pk).update(betreuer=None)
        pdf = self.vorschau(self.begruessung())
        self.assertTrue(pdf.startswith(b'%PDF'))
        text = normalisiert(seitentext(pdf))
        self.assertIn('Vorbesitzer Hans Alt', text)                 # wechsel.voreigentuemer_name (Beispiel)
        self.assertIn('Wechsel am 01.09.2026', text)                # wechsel.wechsel_datum (Beispiel)
        self.assertIn('Betreuer Anna Beispiel', text)               # verwaltung.betreuer_name (Beispiel)
        self.assertIn('Anna Beispiel (a.beispiel@demme-', text)

    def test_reale_werte_gewinnen(self):
        pdf = self.vorschau(self.begruessung([{'typ': 'text', 'inhalt': (
            '{{ empfaenger.name }} / {{ objekt.bezeichnung }} / Einheit {{ einheit.einheit_nr }}')}]))
        text = normalisiert(seitentext(pdf))
        self.assertIn('Sehr geehrter Herr Eichhorn', text)          # echte Anrede
        self.assertIn('Testweg', text)                              # echte Anschrift
        self.assertIn('Einheit 77', text)
        self.assertIn(self.s.objekt.bezeichnung, text)
        self.assertNotIn('Mustermann', text.replace('Musterweg', ''))   # Fixture-Person ist nicht der Empfänger
        self.assertNotIn('Musterweg 5', text)                       # Beispielanschrift
        self.assertIn(f'{self.s.objekt.objektnummer}/', text)                            # echtes Zeichen, nicht Beispiel 53/0012
        self.assertNotIn('53/0012', text)

    def test_einzelperson_bekommt_keine_zweite_beispielanrede(self):
        text = normalisiert(seitentext(self.vorschau(self.begruessung())))
        self.assertNotIn('sehr geehrter Herr Mustermann', text)

    def test_pdf_enthaelt_beispieldaten_hinweis_auf_jeder_seite(self):
        lang = ' '.join(['Absatz.'] * 40)
        inhalt = [{'typ': 'text', 'inhalt': lang}, {'typ': 'seitenumbruch'}, {'typ': 'text', 'inhalt': lang}]
        pdf = self.vorschau(self.vorlage('zweiseitig', 'eigentuemer_allgemein', inhalt=inhalt))
        with pymupdf.open(stream=pdf, filetype='pdf') as doc:
            self.assertGreaterEqual(len(doc), 2)
            for seite in doc:
                self.assertIn(vorschau_service.VORSCHAU_HINWEIS, normalisiert(seite.get_text()))

    def test_ohne_bankkonto_rendert_weg_fusszeile_mit_beispielbank(self):
        Bankkonto.objects.filter(objekt=self.s.objekt).delete()
        text = seitentext(self.vorschau(self.vorlage('allg', 'eigentuemer_allgemein')))
        self.assertIn('DE00 0000 0000 0000 0000 00', text)

    def test_pflicht_eingabefeld_ohne_wert_nutzt_beispiel(self):
        version = self.vorlage(
            'mit_eingabe', 'eigentuemer_allgemein',
            inhalt=[{'typ': 'text', 'inhalt': 'Ort: {{ eingabe.ort }}, Tag: {{ eingabe.tag|datum }}'}],
            eingabefelder=[{'name': 'ort', 'label': 'Ort', 'typ': 'text', 'pflicht': True},
                           {'name': 'tag', 'label': 'Tag', 'typ': 'datum', 'pflicht': True}])
        self.assertIn('Ort: Beispiel Ort', seitentext(self.vorschau(version)))
        # Eingabe des Aufrufers hat Vorrang
        self.assertIn('Ort: Kaminzimmer', seitentext(self.vorschau(version, eingabewerte={'ort': 'Kaminzimmer'})))

    def test_ungueltiger_eingabewert_bleibt_fehler(self):
        version = self.vorlage(
            'betrag_eingabe', 'eigentuemer_allgemein', inhalt=[{'typ': 'text', 'inhalt': '{{ eingabe.b|euro }}'}],
            eingabefelder=[{'name': 'b', 'label': 'B', 'typ': 'betrag', 'pflicht': True}])
        with self.assertRaises(ValidationError):
            self.vorschau(version, eingabewerte={'b': 'abc'})

    def test_unbekannter_platzhalter_bleibt_fehler(self):
        version = self.vorlage('kaputt', 'eigentuemer_allgemein',
                               inhalt=[{'typ': 'text', 'inhalt': '{{ gibt.es_nicht }}'}])
        with self.assertRaises(ValidationError) as ctx:
            self.vorschau(version)
        self.assertIn('Vorschau nicht erzeugbar', str(ctx.exception))

    def test_alle_seed_vorlagen_lassen_sich_als_vorschau_rendern(self):
        for daten in seed_daten.VORLAGEN:
            with self.subTest(code=daten['code']):
                vorlage = seed_service._lege_vorlage_an(daten)
                pdf = self.vorschau(vorlage.versionen.get())
                self.assertTrue(pdf.startswith(b'%PDF'))
                self.assertIn(vorschau_service.VORSCHAU_HINWEIS, normalisiert(seitentext(pdf)))


class EchtesSchreibenBleibtStrengTest(VersandTestBasis):
    """Gegenprobe: kein Beispiel-Fallback im Erzeugungspfad."""

    def erstelle(self, code):
        return schreiben_service.erstellen(
            code, self.s.person, objekt=self.s.objekt, einheit=self.s.einheit, user=self.user)

    def test_fehlender_wechsel_ist_nicht_erzeugbar(self):
        self.vorlage('begruessung_streng', 'eigentuemer_begruessung',
                     inhalt=[{'typ': 'text', 'inhalt': 'Wechsel {{ wechsel.wechsel_datum|datum }}.'}])
        s = self.erstelle('begruessung_streng')
        self.assertEqual(s.status, 'entwurf')
        self.assertIn('wechsel', s.fehler)
        self.assertEqual(s.html_gerendert, '')

    def test_fehlender_betreuer_ist_nicht_erzeugbar(self):
        Objekt.objects.filter(pk=self.s.objekt.pk).update(betreuer=None)
        self.s.objekt.refresh_from_db()
        self.vorlage('betreuer_streng', 'eigentuemer_allgemein',
                     inhalt=[{'typ': 'text', 'inhalt': 'Betreuer {{ verwaltung.betreuer_name }}.'}])
        s = self.erstelle('betreuer_streng')
        self.assertEqual(s.status, 'entwurf')
        self.assertIn('verwaltung.betreuer_name', s.fehler)

    def test_fehlendes_bankkonto_ist_nicht_erzeugbar(self):
        self.vorlage('bank_streng', 'eigentuemer_allgemein')
        Bankkonto.objects.filter(objekt=self.s.objekt).delete()
        s = self.erstelle('bank_streng')
        self.assertEqual(s.status, 'entwurf')
        self.assertIn('nicht erzeugbar', s.fehler)

    def test_fehlendes_pflicht_eingabefeld_ist_nicht_erzeugbar(self):
        self.vorlage('eingabe_streng', 'eigentuemer_allgemein',
                     inhalt=[{'typ': 'text', 'inhalt': '{{ eingabe.ort }}'}],
                     eingabefelder=[{'name': 'ort', 'label': 'Ort', 'typ': 'text', 'pflicht': True}])
        s = self.erstelle('eingabe_streng')
        self.assertEqual(s.status, 'entwurf')
        self.assertIn('Pflichtfeld "Ort" fehlt', s.fehler)

    def test_echtes_pdf_hat_keinen_vorschau_hinweis(self):
        self.vorlage('echt', 'eigentuemer_allgemein')
        s = schreiben_service.freigeben(self.erstelle('echt'), self.user)
        text = normalisiert(seitentext(schreiben_service.pdf_bytes(s)))
        self.assertNotIn('Beispieldaten', text)
        self.assertNotIn('VORSCHAU', text)
