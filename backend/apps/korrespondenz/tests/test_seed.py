"""Phase 7: Seed (Briefbogen + Mustervorlagen) und Platzhalter-Doku."""
import tempfile
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.dokumente.models import Dokument
from apps.korrespondenz.models import Briefbogen, Vorlage, VorlageAnlage, VorlagenVersion
from apps.korrespondenz.services import platzhalter_doku_service, registry, render_service, seed_daten, seed_service

User = get_user_model()

_EINGABEWERTE = {
    'etv_einladung': {
        'versammlung_datum': '2026-12-18', 'versammlung_uhrzeit': '16:00',
        'versammlung_ort': 'Achat Hotel Offenbach', 'tagesordnung': ['Jahresabrechnung', 'Wirtschaftsplan'],
    },
    'eigentuemer_allgemein': {'betreff': 'Information', 'inhalt': 'Zeile 1\nZeile 2'},
}


def _kontext_aus_registry(anlass: str) -> dict:
    """Kontext aus den Registry-Beispielen (Beträge als Decimal wie im echten Kontext)."""
    kontext = {}
    for p in registry.metadaten(anlass):
        wert = Decimal(p['beispiel']) if p['typ'] == 'betrag' else p['beispiel']
        kontext.setdefault(p['gruppe'], {})[p['name'].split('.', 1)[1]] = wert
    return kontext


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='korr_seed_'))
class SeedTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user('seeder', password='x', is_superuser=True)

    def test_seed_legt_briefbogen_mit_logo_an(self):
        ergebnis = seed_service.seede(self.user)
        self.assertTrue(ergebnis.briefbogen_angelegt)
        standard = Briefbogen.objects.filter(ist_standard=True)
        self.assertEqual(standard.count(), 1)
        bogen = standard.get()
        self.assertEqual(bogen.firma_name, 'Demme Immobilien Verwaltung GmbH')
        self.assertEqual(bogen.steuerzeichen_unsichtbar, 'Porto!Demme')
        self.assertTrue(bogen.pflichtangaben_anzeigen)
        self.assertIsNone(bogen.fuss_logo)
        self.assertEqual(bogen.logo.dateiname, 'demme_logo.jpeg')
        self.assertTrue(bogen.logo.datei.storage.exists(bogen.logo.datei.name))

    def test_alle_vorlagen_nur_als_entwurf(self):
        seed_service.seede(self.user)
        codes = set(Vorlage.objects.values_list('code', flat=True))
        self.assertEqual(codes, {
            'eigentuemer_begruessung', 'eigentuemer_verabschiedung', 'mahnung_stufe_2',
            'mahnung_stufe_3', 'etv_einladung', 'eigentuemer_allgemein',
        })
        self.assertNotIn('mahnung_stufe_1', codes)
        for vorlage in Vorlage.objects.all():
            self.assertIsNone(vorlage.objekt_id)
            self.assertIsNone(vorlage.aktive_version_id)
            versionen = list(vorlage.versionen.all())
            self.assertEqual([(v.version, v.status) for v in versionen], [(1, 'entwurf')])
            self.assertIsNone(versionen[0].freigegeben_am)

    def test_begruessung_anlagen(self):
        seed_service.seede(self.user)
        anlagen = list(VorlageAnlage.objects.filter(vorlage__code='eigentuemer_begruessung'))
        self.assertEqual([a.art for a in anlagen], ['dokument', 'objekt_kategorie'])
        sepa, hausordnung = anlagen
        self.assertEqual(sepa.bedingung, 'ev.sepa_mandat_fehlt')
        self.assertTrue(sepa.pflicht)
        self.assertIsNone(sepa.dokument_id)
        self.assertEqual(hausordnung.objekt_kategorie, 'Hausordnung')

    def test_mahnung_stufe_2_ohne_zahlungserinnerung(self):
        seed_service.seede(self.user)
        inhalt = VorlagenVersion.objects.get(vorlage__code='mahnung_stufe_2').inhalt
        self.assertNotIn('Zahlungserinnerung', str(inhalt))
        klage = VorlagenVersion.objects.get(vorlage__code='mahnung_stufe_3').inhalt
        self.assertIn('gerichtlich geltend machen', str(klage))

    def test_idempotenz_keine_duplikate(self):
        seed_service.seede(self.user)
        zaehler = (Briefbogen.objects.count(), Dokument.objects.count(), Vorlage.objects.count(),
                   VorlagenVersion.objects.count(), VorlageAnlage.objects.count())
        zweiter = seed_service.seede(self.user)
        self.assertFalse(zweiter.briefbogen_angelegt)
        self.assertEqual(zweiter.vorlagen_angelegt, [])
        self.assertEqual(len(zweiter.vorlagen_vorhanden), len(seed_daten.VORLAGEN))
        self.assertEqual(zaehler, (Briefbogen.objects.count(), Dokument.objects.count(),
                                   Vorlage.objects.count(), VorlagenVersion.objects.count(),
                                   VorlageAnlage.objects.count()))

    def test_bestehender_standard_briefbogen_bleibt_unberuehrt(self):
        logo = Dokument.objects.create(
            datei='dokumente/x.jpeg', dateiname='x.jpeg', kategorie='Briefbogen', hochgeladen_von=self.user,
        )
        vorher = Briefbogen.objects.create(
            bezeichnung='Bestand', firma_name='Andere GmbH', logo=logo, ist_standard=True,
        )
        seed_service.seede(self.user)
        self.assertEqual(Briefbogen.objects.count(), 1)
        vorher.refresh_from_db()
        self.assertEqual(vorher.firma_name, 'Andere GmbH')
        self.assertEqual(Dokument.objects.count(), 1)

    def test_bestehende_vorlage_bleibt_unberuehrt(self):
        vorhanden = Vorlage.objects.create(
            code='mahnung_stufe_2', bezeichnung='Eigene Mahnung', anlass='mahnung_stufe_2',
        )
        seed_service.seede(self.user)
        vorhanden.refresh_from_db()
        self.assertEqual(vorhanden.bezeichnung, 'Eigene Mahnung')
        self.assertEqual(vorhanden.versionen.count(), 0)

    def test_command_ist_idempotent(self):
        for _ in range(2):
            call_command('seed_korrespondenz', stdout=StringIO())
        self.assertEqual(Briefbogen.objects.filter(ist_standard=True).count(), 1)
        self.assertEqual(Vorlage.objects.count(), len(seed_daten.VORLAGEN))


class SeedVorlagenInhaltTest(TestCase):
    """Jede Seed-Vorlage ist strukturell gültig, nutzt nur dokumentierte Platzhalter und rendert."""

    def test_struktur_gueltig(self):
        for daten in seed_daten.VORLAGEN:
            with self.subTest(code=daten['code']):
                self.assertEqual(seed_service.pruefe_vorlagen_daten(daten), [])

    def test_platzhalter_dokumentiert_und_renderbar(self):
        for daten in seed_daten.VORLAGEN:
            with self.subTest(code=daten['code']):
                version = VorlagenVersion(
                    betreff=daten['betreff'], inhalt=daten['inhalt'],
                    eingabefelder=daten.get('eingabefelder', []),
                    pflicht_platzhalter=daten.get('pflicht_platzhalter', []),
                )
                anlass = daten['anlass']
                unbekannt = render_service.verwendete_platzhalter(version) - registry.dokumentierte_namen(
                    anlass, version.eingabefelder)
                self.assertEqual(unbekannt, set())
                ergebnis = render_service.render(
                    version, _kontext_aus_registry(anlass), _EINGABEWERTE.get(daten['code'], {}))
                self.assertTrue(ergebnis.ok, ergebnis.fehler)
                self.assertTrue(ergebnis.betreff)


class PlatzhalterDokuTest(TestCase):

    def test_markdown_enthaelt_alle_anlaesse_und_platzhalter(self):
        text = platzhalter_doku_service.erzeuge_markdown()
        for anlass in registry.ANLAESSE:
            self.assertIn(f'## Anlass `{anlass}`', text)
            for p in registry.metadaten(anlass):
                self.assertIn(f"`{p['name']}`", text)

    def test_markdown_ist_deterministisch(self):
        self.assertEqual(platzhalter_doku_service.erzeuge_markdown(),
                         platzhalter_doku_service.erzeuge_markdown())
