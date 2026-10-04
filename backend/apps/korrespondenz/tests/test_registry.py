"""Test 6 (Spec 11): Registry liefert je Anlass nur dokumentierte Platzhalter.

Dazu die Kontext-Aufbereitung aus echten Referenzen (Personenkonto-Auflösung
für "Unser Zeichen", Bankkonto-Regel, Mahnfrist, Hausgeld, OP-Tabelle) und
der Platzhalter-Endpoint (Spec 4.3).
"""
from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.korrespondenz.models import VorlagenVersion
from apps.korrespondenz.services import kontext_service, registry, render_service
from apps.objekte.models import Bankkonto
from apps.versammlung.models import Eigentuemerversammlung, Tagesordnungspunkt
from apps.korrespondenz.tests import fixtures

HEUTE = date(2026, 9, 29)


def _versammlung(s):
    """Eigentümerversammlung mit Termin, Ort und Tagesordnung für die Gruppe ``versammlung`` (Spec 9.4)."""
    ev = Eigentuemerversammlung.objects.create(
        objekt=s.objekt, erstellt_von=s.ersteller, art='ordentlich', ort='Gemeinschaftsraum',
        termin=datetime(2026, 12, 18, 16, 0, tzinfo=timezone.get_current_timezone()),
    )
    for nummer, titel in enumerate(('Jahresabrechnung 2025', 'Wirtschaftsplan 2027'), start=1):
        Tagesordnungspunkt.objects.create(ev=ev, nummer=nummer, titel=titel, beschlussvorlage='x')
    return ev


def _kontext(anlass, s, **extra):
    """Kontext mit allen Referenzen des Szenarios; ``extra`` übersteuert."""
    refs = dict(
        person=s.person, objekt=s.objekt, einheit=s.einheit, mahnung=s.mahnung,
        eigentuemerwechsel=s.wechsel, vorgang=s.vorgang, briefbogen=s.briefbogen,
        eingabewerte={'x': 1}, parameter={'frist_tage': 14}, schreiben_nummer='KS-2026-000001',
        heute=HEUTE,
    )
    if anlass == 'etv_einladung':
        refs['versammlung'] = _versammlung(s)
    refs.update(extra)
    return kontext_service.baue_kontext(anlass, **refs)


def _namen(kontext):
    return {f'{g}.{n}' for g, werte in kontext.items() for n in werte if g != 'eingabe'}


class RegistryMetadatenTest(APITestCase):

    def test_alle_anlaesse_sind_registriert_und_haben_metadaten(self):
        self.assertEqual(set(registry.ANLAESSE), set(registry.GRUPPEN_JE_ANLASS))
        for anlass in registry.ANLAESSE:
            self.assertTrue(registry.metadaten(anlass), anlass)

    def test_metadaten_haben_das_vertragsformat(self):
        for anlass in registry.ANLAESSE:
            for eintrag in registry.metadaten(anlass):
                self.assertEqual(
                    set(eintrag), {'name', 'beschreibung', 'typ', 'beispiel', 'gruppe'})
                self.assertTrue(eintrag['name'].startswith(eintrag['gruppe'] + '.'))
                self.assertIn(eintrag['typ'], {'text', 'zahl', 'betrag', 'datum', 'bool', 'liste', 'tabelle'})

    def test_gruppen_je_anlass_nach_tabelle_4_2(self):
        def gruppen(anlass):
            return {e['gruppe'] for e in registry.metadaten(anlass, [{'name': 'a', 'typ': 'text'}])}
        alle = {'empfaenger', 'objekt', 'einheit', 'schreiben', 'verwaltung', 'bank', 'eingabe'}
        self.assertEqual(gruppen('eigentuemer_begruessung'), alle | {'ev', 'hausgeld', 'wechsel'})
        self.assertEqual(gruppen('eigentuemer_verabschiedung'), alle | {'ev', 'wechsel'})
        for stufe in (1, 2, 3):
            self.assertEqual(gruppen(f'mahnung_stufe_{stufe}'), alle | {'ev', 'mahnung'})
        self.assertEqual(gruppen('etv_einladung'), alle | {'ev', 'versammlung'})
        self.assertEqual(gruppen('eigentuemer_allgemein'), alle | {'ev'})
        self.assertEqual(gruppen('vorgang_antwort'), alle | {'vorgang'})

    def test_eingabefelder_erweitern_die_gruppe_eingabe(self):
        namen = registry.dokumentierte_namen(
            'etv_einladung', [{'name': 'versammlung_ort', 'label': 'Ort', 'typ': 'text'}])
        self.assertIn('eingabe.versammlung_ort', namen)
        self.assertNotIn('eingabe.versammlung_ort', registry.dokumentierte_namen('etv_einladung'))

    def test_unbekannter_anlass(self):
        with self.assertRaises(KeyError):
            registry.metadaten('gibt_es_nicht')


class KontextNurDokumentiertTest(APITestCase):
    """Test 6: je Anlass ist der gebaute Kontext exakt die dokumentierte Menge."""

    @classmethod
    def setUpTestData(cls):
        cls.s = fixtures.szenario()

    def test_kontext_enthaelt_je_anlass_nur_dokumentierte_platzhalter(self):
        for anlass in registry.ANLAESSE:
            dokumentiert = registry.dokumentierte_namen(anlass)
            kontext = _kontext(anlass, self.s)
            fremd = _namen(kontext) - dokumentiert
            self.assertEqual(fremd, set(), f'{anlass}: undokumentiert {fremd}')
            self.assertTrue(set(kontext) <= set(registry.gruppen_fuer(anlass)), anlass)

    def test_kontext_ist_bei_vollstaendigen_daten_vollstaendig(self):
        # Mit vollständigen Daten wird jeder dokumentierte Platzhalter des Anlasses befüllt.
        for anlass in registry.ANLAESSE:
            dokumentiert = registry.dokumentierte_namen(anlass) - {'schreiben.ihr_schreiben_vom'}
            fehlt = dokumentiert - _namen(_kontext(anlass, self.s))
            self.assertEqual(fehlt, set(), f'{anlass}: nicht befüllt {fehlt}')

    def test_gruppen_ohne_bezug_fehlen(self):
        kontext = _kontext('mahnung_stufe_1', self.s)
        self.assertNotIn('hausgeld', kontext)
        self.assertNotIn('vorgang', kontext)
        self.assertNotIn('wechsel', kontext)

    def test_kontext_besteht_nur_aus_primitiven(self):
        erlaubt = (str, int, bool, date, Decimal, list, dict)

        def pruefe(wert, pfad):
            self.assertIsInstance(wert, erlaubt, f'{pfad}: {type(wert)}')
            if isinstance(wert, dict):
                [pruefe(v, f'{pfad}.{k}') for k, v in wert.items()]
            if isinstance(wert, list):
                [pruefe(v, f'{pfad}[]') for v in wert]
        for anlass in registry.ANLAESSE:
            pruefe(_kontext(anlass, self.s), anlass)


class KontextWerteTest(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.s = fixtures.szenario()

    def test_unser_zeichen_objektnummer_slash_personenkonto(self):
        k = _kontext('mahnung_stufe_1', self.s)
        self.assertEqual(
            k['schreiben']['unser_zeichen'], f'{self.s.objekt.objektnummer}/{self.s.konto.kontonummer}')

    def test_unser_zeichen_ohne_ev_ueber_person_und_objekt(self):
        s = fixtures.szenario(wechsel=False, mahnung=False, vorgang=False)
        k = kontext_service.baue_kontext(
            'eigentuemer_allgemein', person=s.person, objekt=s.objekt, heute=HEUTE, briefbogen=s.briefbogen)
        self.assertEqual(
            k['schreiben']['unser_zeichen'], f'{s.objekt.objektnummer}/{s.konto.kontonummer}')

    def test_unser_zeichen_fehlt_ohne_eindeutiges_personenkonto(self):
        k = kontext_service.baue_kontext('eigentuemer_allgemein', person=self.s.person, heute=HEUTE)
        self.assertNotIn('unser_zeichen', k['schreiben'])

    def test_objekt_und_einheit(self):
        k = _kontext('eigentuemer_allgemein', self.s)
        self.assertEqual(k['objekt']['anschrift'], 'Musterstraße 1, 60311 Frankfurt am Main')
        self.assertIs(k['objekt']['ist_weg'], True)
        self.assertEqual(k['einheit']['flaechennummer'], '0012')
        self.assertEqual(k['einheit']['typ'], 'Wohnung')

    def test_einheit_und_objekt_werden_aus_der_mahnung_abgeleitet(self):
        k = kontext_service.baue_kontext(
            'mahnung_stufe_1', person=self.s.person, mahnung=self.s.mahnung, briefbogen=self.s.briefbogen, heute=HEUTE)
        self.assertEqual(k['objekt']['objektnummer'], self.s.objekt.objektnummer)
        self.assertEqual(k['einheit']['einheit_nr'], '12')

    def test_empfaenger_und_verwaltung(self):
        k = _kontext('eigentuemer_allgemein', self.s)
        self.assertEqual(k['empfaenger']['anschrift_zeilen'][0], 'Eheleute')
        self.assertEqual(k['empfaenger']['personennummer'], self.s.person.personennummer)
        v = k['verwaltung']
        self.assertEqual(v['firma'], 'Demme Immobilien Verwaltung GmbH')
        self.assertEqual((v['betreuer_name'], v['betreuer_telefon']), ('Anna Beispiel', '069-96 75 20 90'))
        # Ohne expliziten Unterzeichner unterzeichnet der Objektbetreuer.
        self.assertEqual((v['unterzeichner_vorname'], v['unterzeichner_nachname']), ('Anna', 'Beispiel'))

    def test_expliziter_unterzeichner(self):
        k = _kontext('eigentuemer_allgemein', self.s, unterzeichner=self.s.ersteller)
        self.assertNotIn('unterzeichner_vorname', k['verwaltung'])   # Name nicht gepflegt -> fehlt statt leer

    def test_optionale_bezugszeichen(self):
        k = _kontext('eigentuemer_allgemein', self.s)
        self.assertEqual(k['schreiben']['ihr_zeichen'], '')
        self.assertNotIn('ihr_schreiben_vom', k['schreiben'])
        k = _kontext('eigentuemer_allgemein', self.s, ihr_zeichen='X-1', ihr_schreiben_vom=date(2026, 9, 1))
        self.assertEqual(k['schreiben']['ihr_zeichen'], 'X-1')
        self.assertEqual(k['schreiben']['ihr_schreiben_vom'], date(2026, 9, 1))

    def test_bank_nur_bei_weg_mit_genau_einem_zahlungsverkehrskonto(self):
        b = _kontext('eigentuemer_allgemein', self.s)['bank']
        self.assertEqual(b['iban'], fixtures.TEST_IBAN)
        self.assertEqual(b['weg_name'], 'WEG Musterstraße 1')
        self.assertEqual(b['bankname'], 'Frankfurter Volksbank Rhein-Main')
        # Zweites Zahlungsverkehrskonto (am Modell-save vorbei) -> nicht eindeutig -> bank fehlt.
        zweites = Bankkonto.objects.create(
            objekt=self.s.objekt, konto_typ='ruecklage', bezeichnung='Rücklage', iban=fixtures.TEST_IBAN)
        Bankkonto.objects.filter(pk=zweites.pk).update(zahlungsverkehr=True)
        try:
            self.assertNotIn('bank', _kontext('eigentuemer_allgemein', self.s))
        finally:
            zweites.delete()

    def test_bank_fehlt_ohne_zahlungsverkehrskonto(self):
        s = fixtures.szenario(wechsel=False, mahnung=False, vorgang=False)
        Bankkonto.objects.filter(objekt=s.objekt).update(zahlungsverkehr=False)
        k = kontext_service.baue_kontext('eigentuemer_allgemein', person=s.person, objekt=s.objekt, heute=HEUTE)
        self.assertNotIn('bank', k)

    def test_ev_sepa_flags(self):
        ev = _kontext('eigentuemer_allgemein', self.s)['ev']
        self.assertEqual(ev['beginn'], date(2026, 9, 1))
        self.assertEqual((ev['sepa_mandat_vorhanden'], ev['sepa_mandat_fehlt']), (False, True))
        s = fixtures.szenario(wechsel=False, mahnung=False, vorgang=False, mandat=True)
        ev = kontext_service.baue_kontext('eigentuemer_allgemein', person=s.person, objekt=s.objekt, einheit=s.einheit, heute=HEUTE)['ev']
        self.assertEqual((ev['sepa_mandat_vorhanden'], ev['sepa_mandat_fehlt']), (True, False))

    def test_hausgeld(self):
        h = _kontext('eigentuemer_begruessung', self.s)['hausgeld']
        self.assertEqual(h['monatsbetrag'], Decimal('300.00'))
        self.assertEqual(h['gueltig_ab'], date(2026, 9, 1))
        self.assertEqual(h['positionen'], [{'bezeichnung': 'Hausgeld', 'betrag': Decimal('300.00')}])

    def test_wechsel(self):
        w = _kontext('eigentuemer_begruessung', self.s)['wechsel']
        self.assertEqual(w, {'wechsel_datum': date(2026, 9, 1), 'voreigentuemer_name': 'Hans Alt'})

    def test_verabschiedung_ermittelt_das_ev_des_voreigentuemers(self):
        vor = self.s.wechsel.voreigentuemer_ev.person
        k = kontext_service.baue_kontext(
            'eigentuemer_verabschiedung', person=vor, eigentuemerwechsel=self.s.wechsel,
            briefbogen=self.s.briefbogen, heute=HEUTE)
        self.assertEqual(k['ev']['beginn'], date(2010, 1, 1))

    def test_mahnung(self):
        m = _kontext('mahnung_stufe_1', self.s)['mahnung']
        self.assertEqual(m['stufe'], 1)
        self.assertEqual(m['summe_hauptforderung'], Decimal('350.00'))
        self.assertEqual(m['gesamtbetrag'], Decimal('356.20'))
        self.assertEqual(m['frist'], date(2026, 10, 13))            # 29.09. + 14 = Di 13.10.
        self.assertEqual((m['basiszinssatz'], m['zinssatz']), ('3,62 %', '8,62 %'))
        self.assertEqual(m['offene_posten'], [{
            'faellig_ab': date(2026, 8, 1), 'bezeichnung': 'Hausgeld 08/2026',
            'betrag_ursprung': Decimal('350.00'), 'betrag_offen': Decimal('350.00'),
        }])

    def test_mahnfrist_kommt_aus_der_staffel_der_stufe(self):
        """Stufe 1: 14 Tage (29.09. -> Di 13.10.), Stufe 2: 10 Tage (29.09. -> Fr 09.10.); Parameter zählt nicht."""
        m = _kontext('mahnung_stufe_2', self.s, parameter={'frist_tage': 99})['mahnung']
        self.assertEqual(m['frist'], date(2026, 10, 13))
        self.mahnung_stufe_setzen(2)
        m = _kontext('mahnung_stufe_2', self.s, parameter={'frist_tage': 99})['mahnung']
        self.assertEqual(m['frist'], date(2026, 10, 9))

    def mahnung_stufe_setzen(self, stufe):
        self.s.mahnung.mahnstufe = stufe

    def test_mahnfrist_wird_auf_werktag_verschoben(self):
        from apps.korrespondenz.services import fristen_service
        # 04.10.2026 ist ein Sonntag -> Montag 05.10. (Werktagsregel gilt weiter für die Staffelfrist)
        self.assertEqual(fristen_service.berechne_frist(date(2026, 9, 29), 5, 'HE'), date(2026, 10, 5))

    def test_mahnfrist_ersatzweise_aus_parameter_bei_stufe_ausserhalb_der_staffel(self):
        self.mahnung_stufe_setzen(3)
        m = _kontext('mahnung_stufe_3', self.s, parameter={'frist_tage': 5})['mahnung']
        self.assertEqual(m['frist'], date(2026, 10, 5))             # Altbestand: 04.10. ist Sonntag
        self.assertNotIn('frist', _kontext('mahnung_stufe_3', self.s, parameter={})['mahnung'])

    def test_offene_posten_nur_faellige_und_offene(self):
        from apps.buchhaltung.models import Buchung, OffenerPosten
        for datum_, status in ((date(2026, 11, 1), 'offen'), (date(2026, 7, 1), 'verrechnet')):
            b = Buchung.objects.create(
                objekt=self.s.objekt, betrag=Decimal('10'), buchungsdatum=datum_, buchungstext='x')
            OffenerPosten.objects.create(
                buchung=b, personenkonto=self.s.konto, betrag_ursprung=Decimal('10'),
                betrag_offen=Decimal('10'), faellig_ab=datum_, status=status)
        zeilen = _kontext('mahnung_stufe_1', self.s)['mahnung']['offene_posten']
        self.assertEqual([z['bezeichnung'] for z in zeilen], ['Hausgeld 08/2026'])

    def test_vorgang(self):
        v = _kontext('vorgang_antwort', self.s)['vorgang']
        self.assertEqual(v['betreff'], 'Schaden im Treppenhaus')
        self.assertTrue(v['nummer'])

    def test_versammlung_liest_aus_der_ev(self):
        v = _kontext('etv_einladung', self.s)['versammlung']
        self.assertEqual(v['ort'], 'Gemeinschaftsraum')
        self.assertEqual(v['art'], 'ordentliche')
        self.assertEqual(v['tagesordnung'], ['Jahresabrechnung 2025', 'Wirtschaftsplan 2027'])
        self.assertEqual((v['termin'].hour, v['termin'].day), (16, 18))

    def test_versammlung_gruppe_fehlt_ohne_ev(self):
        refs = dict(person=self.s.person, objekt=self.s.objekt, briefbogen=self.s.briefbogen, heute=HEUTE)
        self.assertNotIn('versammlung', kontext_service.baue_kontext('etv_einladung', **refs))

    def test_neutraler_kontext_ohne_person(self):
        k = kontext_service.baue_kontext(
            'etv_einladung', person=None, objekt=self.s.objekt, versammlung=_versammlung(self.s),
            briefbogen=self.s.briefbogen, heute=HEUTE)
        self.assertNotIn('empfaenger', k)
        self.assertNotIn('ev', k)
        self.assertNotIn('unser_zeichen', k.get('schreiben', {}))
        self.assertEqual(k['objekt']['objektnummer'], self.s.objekt.objektnummer)

    def test_eingabe_rohwerte_werden_durchgereicht(self):
        k = _kontext('etv_einladung', self.s, eingabewerte={'versammlung_ort': 'Saal'})
        self.assertEqual(k['eingabe'], {'versammlung_ort': 'Saal'})

    def test_render_mit_echtem_kontext_ende_zu_ende(self):
        version = VorlagenVersion(
            betreff='Zahlungserinnerung {{ objekt.bezeichnung }}',
            inhalt=[
                {'typ': 'text', 'inhalt': '{{ empfaenger.briefanrede }}\n\nBis {{ mahnung.frist | datum }}: {{ mahnung.gesamtbetrag | euro }}'},
                {'typ': 'tabelle', 'quelle': 'mahnung.offene_posten'},
                {'typ': 'text', 'inhalt': 'IBAN {{ bank.iban | iban }} ({{ bank.bankname }}), Zeichen {{ schreiben.unser_zeichen }}'},
            ],
        )
        erg = render_service.render(version, _kontext('mahnung_stufe_1', self.s), {})
        self.assertEqual(erg.fehler, '')
        self.assertIn('Bis 13.10.2026: 356,20 €', erg.html)
        self.assertIn('DE02 5019 0000 6300 2110 10', erg.html)
        self.assertEqual(erg.snapshot['mahnung.frist'], '2026-10-13')

    def test_fehlender_kontextwert_fuehrt_zu_renderfehler(self):
        s = fixtures.szenario(wechsel=False, mahnung=False, vorgang=False)
        Bankkonto.objects.filter(objekt=s.objekt).update(zahlungsverkehr=False)
        kontext = kontext_service.baue_kontext('eigentuemer_allgemein', person=s.person, objekt=s.objekt, heute=HEUTE)
        version = VorlagenVersion(betreff='B', inhalt=[{'typ': 'text', 'inhalt': '{{ bank.iban }}'}])
        erg = render_service.render(version, kontext, {})
        self.assertIn('bank.iban', erg.fehler)
        self.assertEqual(erg.html, '')


class PlatzhalterEndpointTest(APITestCase):
    URL = '/api/v1/korrespondenz/platzhalter/'

    def setUp(self):
        self.user = get_user_model().objects.create_user('api-user', password='x')

    def test_ohne_login_401(self):
        self.assertEqual(self.client.get(self.URL, {'anlass': 'etv_einladung'}).status_code, 401)

    def test_liefert_metadaten_des_anlasses(self):
        self.client.force_authenticate(self.user)
        antwort = self.client.get(self.URL, {'anlass': 'mahnung_stufe_2'})
        self.assertEqual(antwort.status_code, 200)
        self.assertEqual(antwort.json(), registry.metadaten('mahnung_stufe_2'))
        namen = {e['name'] for e in antwort.json()}
        self.assertIn('mahnung.frist', namen)
        self.assertNotIn('hausgeld.monatsbetrag', namen)
        self.assertEqual(
            set(antwort.json()[0]), {'name', 'beschreibung', 'typ', 'beispiel', 'gruppe'})

    def test_unbekannter_oder_fehlender_anlass_400(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get(self.URL, {'anlass': 'quatsch'}).status_code, 400)
        self.assertEqual(self.client.get(self.URL).status_code, 400)
