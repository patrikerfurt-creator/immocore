"""Phase 3 - Briefbogen & PDF: Tests 9-13 und 15 (Spec 11) plus Absicherung der Bausteine.

Die PDFs werden echt mit WeasyPrint erzeugt; geprüft wird über die Textschicht
und Positionen (PyMuPDF). Logos entstehen als ``Dokument`` in einem temporären
``MEDIA_ROOT``.
"""
import hashlib
import shutil
import tempfile
from datetime import date

import pymupdf
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings

from apps.dokumente.models import Dokument
from apps.korrespondenz.models import Schreiben
from apps.korrespondenz.services import brief_layout_service, kontext_service, pdf_service, render_service
from apps.korrespondenz.services.render_service import RenderFehler
from apps.objekte.models import Bankkonto, Objekt

from . import fixtures, fixtures_brief

User = get_user_model()

PT_JE_MM = 72 / 25.4


def seitentexte(pdf: bytes) -> list:
    with pymupdf.open(stream=pdf, filetype='pdf') as doc:
        return [seite.get_text() for seite in doc]


def kompakt(text: str) -> str:
    """Whitespace-frei, für IBAN-Vergleiche."""
    return ''.join(text.split())


def woerter(pdf: bytes, seite: int) -> list:
    """``[(x0, y0, x1, y1, wort)]`` in mm."""
    with pymupdf.open(stream=pdf, filetype='pdf') as doc:
        return [
            (w[0] / PT_JE_MM, w[1] / PT_JE_MM, w[2] / PT_JE_MM, w[3] / PT_JE_MM, w[4])
            for w in doc[seite].get_text('words')
        ]


def _kurze_version():
    """Einseitiger Brief plus Vollmacht-Anlage, ohne Eingabefelder und ohne ``schreiben.unser_zeichen``."""
    version = fixtures_brief.etv_version()
    version.eingabefelder = []
    version.inhalt = [
        {'typ': 'text', 'inhalt': 'wir informieren Sie über den Stand.'},
        {'typ': 'anlage_seite', 'titel': 'Vertretungsvollmacht', 'inhalt': 'Hiermit bevollmächtige ich'},
    ]
    return version


class PdfTestBasis(TestCase):
    """Gemeinsame Daten: Szenario (WEG mit Zahlungsverkehrskonto), Briefbogen, Vorlage A.1."""

    @classmethod
    def setUpClass(cls):
        cls._media = tempfile.mkdtemp(prefix='korr_test_media_')
        cls._override = override_settings(MEDIA_ROOT=cls._media)
        cls._override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._override.disable()
        shutil.rmtree(cls._media, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        cls.s = fixtures.szenario(wechsel=False, mahnung=False, vorgang=False)
        cls.unterzeichner = User.objects.create_user(
            'unterzeichner', first_name='Patrik', last_name='Maurer')
        cls.briefbogen = fixtures_brief.demme_briefbogen(cls.s.ersteller)

    # --- Hilfen ---
    def kontext(self, **kw):
        return kontext_service.baue_kontext(
            'etv_einladung', person=kw.pop('person', self.s.person),
            objekt=kw.pop('objekt', self.s.objekt), einheit=kw.pop('einheit', self.s.einheit),
            briefbogen=self.briefbogen, unterzeichner=self.unterzeichner,
            schreiben_nummer='KS-2026-000001', heute=date(2026, 9, 29), **kw,
        )

    def rendere(self, kontext, version=None, eingabe=None):
        erg = render_service.render(
            version or fixtures_brief.etv_version(), kontext, eingabe or fixtures_brief.EINGABEWERTE,
        )
        self.assertTrue(erg.ok, erg.fehler)
        return erg

    def pdf(self, kontext=None, version=None, eingabe=None, briefbogen=None, anlagen=None):
        version = version or fixtures_brief.etv_version()
        kontext = kontext or self.kontext()
        erg = self.rendere(kontext, version, eingabe)
        return pdf_service.erzeuge_pdf(version, kontext, briefbogen or self.briefbogen, erg, anlagen)


class FusszeileWegTest(PdfTestBasis):
    """Test 9: WEG-Fußzeile aus Objektbezeichnung und Zahlungsverkehrskonto."""

    def test_objektbezeichnung_iban_bic_bank_erscheinen(self):
        kontext = self.kontext()
        bankname = kontext['bank']['bankname']
        self.assertTrue(bankname, 'schwifty muss für die Test-IBAN einen Banknamen liefern')
        seite1 = seitentexte(self.pdf(kontext))[0]
        self.assertIn(self.s.objekt.bezeichnung, seite1)
        self.assertIn('IBAN: ' + fixtures.TEST_IBAN[:4] + ' ' + fixtures.TEST_IBAN[4:8], seite1)
        self.assertIn(fixtures.TEST_IBAN, kompakt(seite1))
        self.assertIn('BIC: FFVBDEFFXXX', seite1)
        self.assertIn(bankname, seite1)

    def test_pflichtangaben_default_an_und_abschaltbar(self):
        self.assertTrue(self.briefbogen.pflichtangaben_anzeigen)
        pflicht = 'Amtsgericht Königstein im Taunus HRB 7182'
        self.assertIn(pflicht, seitentexte(self.pdf())[0])

        self.briefbogen.pflichtangaben_anzeigen = False
        try:
            self.assertNotIn(pflicht, seitentexte(self.pdf())[0])
        finally:
            self.briefbogen.pflichtangaben_anzeigen = True

    def test_weg_fusszeile_ohne_verbandslogo_und_firmenzeilen(self):
        seite1 = seitentexte(self.pdf())[0]
        self.assertNotIn('Frankfurt - Königstein/Taunus - Erfurt', seite1)


class FusszeileWegNichtErzeugbarTest(PdfTestBasis):
    """Test 10: kein bzw. zwei passende Bankkonten -> Render-Fehler, kein PDF."""

    def _versuche_pdf(self, objekt, person):
        kontext = self.kontext(objekt=objekt, person=person)
        self.assertNotIn('bank', kontext)          # Phase-2-Kontext lässt die Gruppe weg
        erg = self.rendere(kontext)
        with self.assertRaises(RenderFehler) as ctx:
            pdf_service.erzeuge_pdf(fixtures_brief.etv_version(), kontext, self.briefbogen, erg)
        self.assertIn('nicht eindeutig', str(ctx.exception))
        self.assertIn('nicht erzeugbar', str(ctx.exception))

    def test_kein_zahlungsverkehrskonto(self):
        Bankkonto.objects.filter(objekt=self.s.objekt).update(zahlungsverkehr=False)
        self._versuche_pdf(self.s.objekt, self.s.person)

    def test_inaktives_konto_zaehlt_nicht(self):
        Bankkonto.objects.filter(objekt=self.s.objekt).update(aktiv=False)
        self._versuche_pdf(self.s.objekt, self.s.person)

    def test_zwei_zahlungsverkehrskonten(self):
        # Bankkonto.save() erzwingt genau EIN zahlungsverkehr-Konto je Objekt. Den Zustand
        # "zwei" gibt es nur über Altdaten/Direktzugriff: deshalb per queryset.update(),
        # das save() (und damit die Exklusivität) umgeht.
        Bankkonto.objects.create(
            objekt=self.s.objekt, konto_typ='ruecklage', bezeichnung='Rücklage',
            iban='DE89370400440532013000', bic='COBADEFFXXX', kontoinhaber='WEG',
        )
        Bankkonto.objects.filter(objekt=self.s.objekt).update(zahlungsverkehr=True)
        self.assertEqual(Bankkonto.objects.filter(objekt=self.s.objekt, zahlungsverkehr=True).count(), 2)
        self._versuche_pdf(self.s.objekt, self.s.person)

    def test_unvollstaendiger_bank_kontext_wird_abgelehnt(self):
        kontext = self.kontext()
        kontext['bank'].pop('bic')
        erg = self.rendere(kontext)
        with self.assertRaises(RenderFehler):
            pdf_service.erzeuge_pdf(fixtures_brief.etv_version(), kontext, self.briefbogen, erg)


class FusszeileFirmaTest(PdfTestBasis):
    """Test 11: Nicht-WEG-Objekte und Schreiben ohne Objekt -> Firmenfußzeile des Briefbogens."""

    def _pruefe_firmenfusszeile(self, pdf):
        seite1 = seitentexte(pdf)[0]
        b = self.briefbogen
        for zeile in (b.fuss_firma_zeile1, b.fuss_firma_zeile2, b.fuss_firma_zeile3):
            self.assertIn(zeile, seite1)
        self.assertNotIn(b.pflichtangaben, seite1)      # Pflichtangaben nur in der WEG-Fußzeile
        return pdf

    def test_nicht_weg_objekt(self):
        Objekt.objects.filter(pk=self.s.objekt.pk).update(objekt_typ='ZH')
        objekt = Objekt.objects.get(pk=self.s.objekt.pk)
        pdf = self.pdf(self.kontext(objekt=objekt))
        self._pruefe_firmenfusszeile(pdf)

    def test_kein_verbandslogo_in_fusszeile(self):
        Objekt.objects.filter(pk=self.s.objekt.pk).update(objekt_typ='ZH')
        objekt = Objekt.objects.get(pk=self.s.objekt.pk)
        with pymupdf.open(stream=self.pdf(self.kontext(objekt=objekt)), filetype='pdf') as doc:
            bilder = doc[0].get_image_info()
        # Der Test-Briefbogen hat ein fuss_logo (Fixture), es wird aber nicht mehr gerendert:
        # nur das Demme-Logo im Briefkopf, kein Bild in der Fußzeile.
        self.assertIsNotNone(self.briefbogen.fuss_logo_id)
        self.assertEqual(len(bilder), 1)

    def test_schreiben_ohne_objekt(self):
        kontext = kontext_service.baue_kontext(
            'eigentuemer_allgemein', person=self.s.person, briefbogen=self.briefbogen,
            unterzeichner=self.unterzeichner, schreiben_nummer='KS-2026-000002',
            heute=date(2026, 9, 29),
        )
        self.assertNotIn('objekt', kontext)
        pdf = self.pdf(kontext, _kurze_version(), eingabe={})
        self._pruefe_firmenfusszeile(pdf)
        seite1 = seitentexte(pdf)[0]
        self.assertNotIn('Objekt:', seite1)             # Objekt-/Flächenzeile entfällt
        self.assertNotIn('Fläche:', seite1)

    def test_flaechenzeile_entfaellt_ohne_einheit(self):
        kontext = self.kontext()
        kontext.pop('einheit')
        seite1 = seitentexte(self.pdf(kontext))[0]
        self.assertIn('Objekt: ', seite1)
        self.assertNotIn('Fläche:', seite1)


class FusszeileJedeSeiteTest(PdfTestBasis):
    """Test 12: Fußzeile auf jeder Seite, auch auf Anlage-Seiten."""

    def _langer_brief(self):
        version = fixtures_brief.etv_version()
        absatz = ('Dies ist ein längerer Absatz, der den Brieftext über mehrere Seiten laufen lässt. ' * 8)
        version.inhalt = [{'typ': 'text', 'inhalt': absatz}] * 9 + [
            {'typ': 'anlage_seite', 'titel': 'Anlage A', 'inhalt': 'Erste Anlage.'},
            {'typ': 'anlage_seite', 'titel': 'Anlage B', 'inhalt': 'Zweite Anlage.'},
        ]
        return version

    def test_mehrseitig_mit_anlagen(self):
        version = self._langer_brief()
        seiten = seitentexte(self.pdf(version=version))
        self.assertGreaterEqual(len(seiten), 4)     # >= 2 Brief- + 2 Anlage-Seiten
        for nr, text in enumerate(seiten, 1):
            self.assertIn('WEG Musterstraße 1', text, f'Fußzeile fehlt auf Seite {nr}')
            self.assertIn('BIC: FFVBDEFFXXX', text, f'Fußzeile fehlt auf Seite {nr}')
            self.assertIn(fixtures.TEST_IBAN, kompakt(text), f'IBAN fehlt auf Seite {nr}')
        self.assertIn('Anlage A', seiten[-2])
        self.assertIn('Anlage B', seiten[-1])

    def test_folgeseiten_ohne_briefkopf_mit_seitenzahl(self):
        version = self._langer_brief()
        pdf = self.pdf(version=version)
        seiten = seitentexte(pdf)
        n = len(seiten)
        self.assertNotIn('Seite 1 von', seiten[0])          # Seite 1 ohne Seitenzahl
        for nr in range(2, n + 1):
            text = seiten[nr - 1]
            self.assertIn(f'Seite {nr} von {n}', text)
            for nur_seite_1 in ('Sprechzeiten', 'Ihr Zeichen', 'Porto!Demme'):
                self.assertNotIn(nur_seite_1, text)
        with pymupdf.open(stream=pdf, filetype='pdf') as doc:
            self.assertEqual(len(doc[1].get_image_info()), 0)   # kein Logo auf Folgeseiten

    def test_schluss_steht_vor_den_anlagen(self):
        seiten = seitentexte(self.pdf())
        self.assertIn('Mit freundlichen Grüßen', seiten[0])
        self.assertNotIn('Mit freundlichen Grüßen', seiten[1])
        self.assertIn('gez. Patrik Maurer', seiten[0])


class VisuellerAbgleichTest(PdfTestBasis):
    """Test 13: Testschreiben Anhang B - Grobprüfung (Seitenzahl, Kernelemente, Positionen).

    Der exakte +-2-mm-Abgleich mit dem Referenz-Rendering erfolgt visuell (Abnahme);
    hier nur Kernelemente und grobe Positionen mit Toleranz.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.kontext_b = fixtures_brief.anhang_b_kontext(cls.s, cls.briefbogen, cls.unterzeichner)

    def setUp(self):
        self.pdf_b = self.pdf(self.kontext_b)

    def test_zwei_seiten_und_kernelemente(self):
        seiten = seitentexte(self.pdf_b)
        self.assertEqual(len(seiten), 2)
        s1, s2 = seiten
        for erwartet in (
            'Objekt: 53-WEG Musterstraße 1', 'Fläche: 0012-Wohnung 2. OG links',
            'Einberufung der Eigentümerversammlung', 'Eheleute', 'Dr. Max Mustermann',
            'Erika Mustermann', 'Musterweg 5', '60311 Frankfurt am Main',
            'Ihr Zeichen:', 'Ihr Schreiben vom:', 'Unser Zeichen:', 'Datum:', '29. September 2026',
            'Donnerstag, den 18. Dezember 2025 um 16.00 Uhr', 'Tagesordnung:',
            'Beschlussfassung über die Jahresabrechnung 2024', 'Mit freundlichen Grüßen',
            'gez. Patrik Maurer', 'Sprechzeiten:', 'MO, MI, FR', 'Fon 069-96 75 20 90',
            'info@demme-immobilien.de', 'Bürotermine nur nach vorheriger telefonischer',
            'Coventrystraße 32 · 65934 Frankfurt am Main', 'Porto!Demme',
        ):
            self.assertIn(erwartet, s1)
        self.assertIn(kompakt(fixtures_brief.ANHANG_B_IBAN), kompakt(s1))
        self.assertIn('BIC: TESTDEFFXXX', s1)
        self.assertIn('Vertretungsvollmacht', s2)
        self.assertIn('Seite 2 von 2', s2)

    def test_positionen_seite_1(self):
        w = {}
        for x0, y0, x1, y1, wort in woerter(self.pdf_b, 0):
            w.setdefault(wort, (x0, y0, x1, y1))
        # Anschriftfeld: x 25, beginnt bei y 62,7 (Toleranz für Glyph-Box +-3 mm)
        self.assertAlmostEqual(w['Eheleute'][0], 25, delta=2)
        self.assertAlmostEqual(w['Eheleute'][1], 62.7, delta=3)
        # Absenderzeile x 25, y ~ 42-46
        self.assertAlmostEqual(w['Coventrystraße'][0], 25, delta=2)
        # Infoblock ab x 140 (das erste 'Coventrystraße' ist die Absenderzeile bei x 25)
        infoblock_x = [x0 for x0, y0, x1, y1, wort in woerter(self.pdf_b, 0) if wort == 'Sprechzeiten:']
        self.assertAlmostEqual(infoblock_x[0], 140, delta=2)
        # Bezugszeichenzeile y ~ 96, Betreffblock ab y ~ 110
        self.assertAlmostEqual(w['Ihr'][1], 96, delta=3)
        self.assertAlmostEqual(w['Objekt:'][1], 110, delta=3)

    def test_logo_position_und_groesse(self):
        with pymupdf.open(stream=self.pdf_b, filetype='pdf') as doc:
            logo = doc[0].get_image_info()[0]['bbox']
        x0, y0, x1, y1 = (v / PT_JE_MM for v in logo)
        self.assertAlmostEqual(x0, 136, delta=2)
        self.assertAlmostEqual(y0, 5, delta=2)
        self.assertAlmostEqual(x1 - x0, 61, delta=2)
        self.assertAlmostEqual(y1 - y0, 41, delta=2)

    def test_falz_und_lochmarken_auf_jeder_seite(self):
        with pymupdf.open(stream=self.pdf_b, filetype='pdf') as doc:
            for seite in doc:
                ys = sorted(
                    round(d['rect'].y0 / PT_JE_MM)
                    for d in seite.get_drawings() if d['rect'].x0 / PT_JE_MM < 12
                )
                self.assertEqual(len(ys), 3, ys)                   # Falz, Loch, Falz
                self.assertTrue(all(abs(a - b) <= 1 for a, b in zip(ys, [105, 148, 210])), ys)

    def test_steuerzeichen_ist_weiss_und_eins_zu_eins(self):
        with pymupdf.open(stream=self.pdf_b, filetype='pdf') as doc:
            spans = [
                sp for block in doc[0].get_text('dict')['blocks'] if block.get('type') == 0
                for line in block['lines'] for sp in line['spans'] if 'Porto' in sp['text']
            ]
        self.assertEqual([sp['text'] for sp in spans], ['Porto!Demme'])
        self.assertEqual(spans[0]['color'], 0xFFFFFF)

    def test_alle_texte_seite_1_in_der_gebuendelten_arial_schrift(self):
        # "Brief-Arial" = gebündelte, zu Arial metrikkompatible Liberation Sans (assets/fonts);
        # unabhängig davon, ob das Betriebssystem Arial hat.
        with pymupdf.open(stream=self.pdf_b, filetype='pdf') as doc:
            spans = [
                sp for block in doc[0].get_text('dict')['blocks'] if block.get('type') == 0
                for line in block['lines'] for sp in line['spans'] if sp['text'].strip()
            ]
        fremd = {sp['font'] for sp in spans if 'Brief-Arial' not in sp['font']}
        self.assertEqual(fremd, set())


class FreigabeDokumentTest(PdfTestBasis):
    """Test 15: genau ein revisionssicheres Dokument mit korrektem Einzelkontext."""

    def _schreiben(self, vorgang=None, nummer='KS-2026-000901'):
        version = fixtures_brief.etv_version(speichern=True)
        return Schreiben.objects.create(
            nummer=nummer, vorlage_version=version, empfaenger=self.s.person,
            objekt=self.s.objekt, einheit=self.s.einheit, vorgang=vorgang,
            freigegeben_von=self.unterzeichner, status='freigegeben',
        )

    def _freigabe(self, schreiben):
        kontext = self.kontext()
        erg = self.rendere(kontext)
        return pdf_service.erzeuge_schreiben_dokument(
            schreiben, kontext, self.briefbogen, erg, self.unterzeichner,
        ), kontext, erg

    def test_ohne_vorgang_kontext_person(self):
        schreiben = self._schreiben()
        dok, _, _ = self._freigabe(schreiben)
        self.assertEqual(Dokument.objects.filter(dokument_typ='korrespondenz').count(), 1)
        self.assertEqual(dok.person_id, self.s.person.id)
        self.assertIsNone(dok.vorgang_id)
        self.assertIsNone(dok.objekt_id)
        self.assertIsNone(dok.einheit_id)
        schreiben.refresh_from_db()
        self.assertEqual(schreiben.dokument_id, dok.id)

    def test_mit_vorgang_kontext_vorgang(self):
        s = fixtures.szenario(wechsel=False, mahnung=False, vorgang=True)
        version = fixtures_brief.etv_version(speichern=True)
        schreiben = Schreiben.objects.create(
            nummer='KS-2026-000902', vorlage_version=version, empfaenger=s.person,
            objekt=s.objekt, einheit=s.einheit, vorgang=s.vorgang,
            freigegeben_von=self.unterzeichner, status='freigegeben',
        )
        kontext = kontext_service.baue_kontext(
            'etv_einladung', person=s.person, objekt=s.objekt, einheit=s.einheit,
            briefbogen=self.briefbogen, unterzeichner=self.unterzeichner, heute=date(2026, 9, 29),
        )
        erg = self.rendere(kontext)
        dok = pdf_service.erzeuge_schreiben_dokument(
            schreiben, kontext, self.briefbogen, erg, self.unterzeichner)
        self.assertEqual(dok.vorgang_id, s.vorgang.id)
        self.assertIsNone(dok.person_id)

    def test_revisionssicher_sha256_und_dateiinhalt(self):
        dok, _, _ = self._freigabe(self._schreiben())
        self.assertEqual(dok.dokument_typ, 'korrespondenz')
        self.assertTrue(dok.revisionssicher)
        self.assertIsNotNone(dok.revisionssicher_seit)
        with dok.datei.open('rb') as f:
            inhalt = f.read()
        self.assertTrue(inhalt.startswith(b'%PDF'))
        self.assertEqual(dok.sha256, hashlib.sha256(inhalt).hexdigest())
        self.assertEqual(dok.dateiname, 'KS-2026-000901.pdf')
        with self.assertRaises(ValidationError):
            dok.delete()                                  # GoBD-Sperre greift

    def test_zweite_freigabe_erzeugt_kein_zweites_dokument_und_rendert_nicht_neu(self):
        schreiben = self._schreiben()
        dok1, kontext, erg = self._freigabe(schreiben)
        sha = dok1.sha256
        # Zweiter Aufruf mit anderem Inhalt: darf nichts ändern
        erg2 = render_service.RenderErgebnis(html='<p>ANDERS</p>', betreff='Anders')
        dok2 = pdf_service.erzeuge_schreiben_dokument(
            Schreiben.objects.get(pk=schreiben.pk), kontext, self.briefbogen, erg2, self.unterzeichner)
        self.assertEqual(dok1.id, dok2.id)
        self.assertEqual(Dokument.objects.filter(dokument_typ='korrespondenz').count(), 1)
        dok2.refresh_from_db()
        self.assertEqual(dok2.sha256, sha)

    def test_render_fehler_legt_kein_dokument_an(self):
        schreiben = self._schreiben()
        fehler = render_service.RenderErgebnis(fehler='Platzhalter fehlt')
        with self.assertRaises(RenderFehler):
            pdf_service.erzeuge_schreiben_dokument(
                schreiben, self.kontext(), self.briefbogen, fehler, self.unterzeichner)
        self.assertEqual(Dokument.objects.filter(dokument_typ='korrespondenz').count(), 0)
        schreiben.refresh_from_db()
        self.assertIsNone(schreiben.dokument_id)


class AnlagenUndSchlussTest(PdfTestBasis):
    """Anlagen-Hinweis, angehängte Anlagen-PDFs und Pflichtangaben des Schlusses."""

    def _fremd_pdf(self):
        with pymupdf.open() as doc:
            doc.new_page().insert_text((72, 72), 'Hausordnung Inhalt')
            return doc.tobytes()

    def test_hinweis_und_angehaengte_pdf(self):
        anlagen = [pdf_service.AnlagePdf('Hausordnung', self._fremd_pdf()),
                   pdf_service.AnlagePdf('SEPA-Mandat')]
        seiten = seitentexte(self.pdf(version=_kurze_version(), anlagen=anlagen))
        self.assertEqual(len(seiten), 3)                     # Brief + Vollmacht + Hausordnung
        self.assertIn('Anlagen:', seiten[0])
        self.assertIn('Hausordnung', seiten[0])
        self.assertIn('SEPA-Mandat', seiten[0])
        self.assertIn('Hausordnung Inhalt', seiten[2])

    def test_ohne_anlagen_kein_hinweis(self):
        self.assertNotIn('Anlagen:', seitentexte(self.pdf(version=_kurze_version()))[0])

    def test_unterzeichner_fehlt_ist_render_fehler(self):
        kontext = self.kontext()
        kontext['verwaltung'].pop('unterzeichner_nachname')
        kontext['verwaltung'].pop('unterzeichner_vorname')
        erg = self.rendere(kontext)
        with self.assertRaises(RenderFehler):
            pdf_service.erzeuge_pdf(fixtures_brief.etv_version(), kontext, self.briefbogen, erg)


class NurFirmaSchlussTest(PdfTestBasis):
    """Option ``nur_firma``: die Firma unterzeichnet, kein persönliches „gez. Name“."""

    def test_nur_firma_ohne_gez_zeile(self):
        version = _kurze_version()
        kontext = self.kontext()
        erg = self.rendere(kontext, version)
        pdf = pdf_service.erzeuge_pdf(version, kontext, self.briefbogen, erg, nur_firma=True)
        seite1 = seitentexte(pdf)[0]
        self.assertIn('Mit freundlichen Grüßen', seite1)
        self.assertNotIn('gez.', seite1)
        self.assertIn('Demme Immobilien Verwaltung GmbH', seite1.split('Mit freundlichen Grüßen')[1])

    def test_nur_firma_braucht_keinen_unterzeichner(self):
        kontext = self.kontext()
        kontext['verwaltung'].pop('unterzeichner_nachname')
        kontext['verwaltung'].pop('unterzeichner_vorname')
        schluss = brief_layout_service.baue_schluss(kontext, nur_firma=True)
        self.assertEqual(schluss, {'firma': 'Demme Immobilien Verwaltung GmbH', 'unterzeichner': ''})

    def test_nur_firma_ohne_firma_ist_render_fehler(self):
        with self.assertRaises(RenderFehler):
            brief_layout_service.baue_schluss({'verwaltung': {}}, nur_firma=True)

    def test_standard_bleibt_mit_gez_zeile(self):
        seite1 = seitentexte(self.pdf(version=_kurze_version()))[0]
        self.assertIn('gez. Patrik Maurer', seite1)


class LayoutServiceTest(SimpleTestCase):
    """Reine Funktionen des Layout-Service."""

    def test_teile_body_trennt_vor_der_ersten_anlage(self):
        html = ('<p>Text</p>\n<div class="seitenumbruch" style="x"></div>\n'
                '<section class="anlage-seite" style="y"><p>A</p></section>')
        brief, anlagen = brief_layout_service.teile_body(html)
        self.assertEqual(brief.strip(), '<p>Text</p>')
        self.assertTrue(anlagen.startswith('<section class="anlage-seite"'))

    def test_teile_body_ohne_anlage(self):
        brief, anlagen = brief_layout_service.teile_body('<p>Text</p>')
        self.assertEqual((brief, anlagen), ('<p>Text</p>', ''))

    def test_firma_wird_auf_zwei_zeilen_verteilt(self):
        f = brief_layout_service._firma_zeilen
        self.assertEqual(f('Demme Immobilien Verwaltung GmbH'), ['Demme Immobilien', 'Verwaltung GmbH'])
        self.assertEqual(f('Demme GmbH'), ['Demme GmbH'])

    def test_rand_unten_mindestens_20_mm(self):
        self.assertEqual(brief_layout_service.rand_unten_mm({'hoehe_mm': 7.2}), 20.0)
        self.assertGreater(brief_layout_service.rand_unten_mm({'hoehe_mm': 12.6}), 20.0)
