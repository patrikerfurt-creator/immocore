"""Phase 4: schreiben_service - Erstellen, Statusübergänge, Textanpassung, Vorgangsverlauf."""
from unittest import mock

import pymupdf
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.dokumente.models import Dokument
from apps.korrespondenz.models import Briefbogen, Schreiben, SchreibenNummerZaehler
from apps.korrespondenz.services import postausgang_service, schreiben_service
from apps.korrespondenz.services.vorlage_service import VorlageNichtGefunden
from apps.objekte.models import Bankkonto
from apps.vorgaenge.models import Vorgang, VorgangEreignis, VorgangTyp

from .basis_versand import VersandTestBasis


def seitentext(pdf: bytes) -> str:
    with pymupdf.open(stream=pdf, filetype='pdf') as doc:
        return '\n'.join(seite.get_text() for seite in doc)


class NummerTest(VersandTestBasis):

    def test_format_und_fortlaufend(self):
        n1 = schreiben_service.naechste_nummer(2026)
        n2 = schreiben_service.naechste_nummer(2026)
        self.assertEqual(n1, 'KS-2026-000001')
        self.assertEqual(n2, 'KS-2026-000002')

    def test_zaehler_je_jahr(self):
        schreiben_service.naechste_nummer(2026)
        self.assertEqual(schreiben_service.naechste_nummer(2027), 'KS-2027-000001')
        self.assertEqual(SchreibenNummerZaehler.objects.get(jahr=2026).letzter_zaehler, 1)

    def test_nummer_passt_in_feld(self):
        self.assertLessEqual(len(schreiben_service.naechste_nummer(2026)), 20)


class ErstellenTest(VersandTestBasis):

    def erstelle(self, **kw):
        return schreiben_service.erstellen(
            'eigentuemer_allgemein', self.s.person, objekt=self.s.objekt, einheit=self.s.einheit,
            user=self.user, **kw,
        )

    def test_erfolg_zur_pruefung(self):
        self.vorlage()
        s = self.erstelle()
        self.assertEqual(s.status, 'zur_pruefung')
        self.assertRegex(s.nummer, r'^KS-\d{4}-\d{6}$')
        self.assertEqual(s.fehler, '')
        self.assertIn('wir informieren Sie', s.html_gerendert)
        self.assertEqual(s.kontext_snapshot[schreiben_service.SNAPSHOT_BETREFF], 'Information zum Objekt')
        self.assertEqual(s.objekt_id, self.s.objekt.id)
        self.assertEqual(s.erstellt_von, self.user)
        self.assertEqual(s.unterzeichner, self.user)       # Default = erstellender Mitarbeiter
        self.assertEqual(s.kanal, 'brief')
        self.assertIsNone(s.dokument_id)                   # PDF entsteht erst bei der Freigabe
        self.assertEqual(Dokument.objects.filter(dokument_typ='korrespondenz').count(), 0)

    def test_explizit_gewaehlter_unterzeichner(self):
        self.vorlage()
        s = self.erstelle(unterzeichner=self.s.betreuer)
        self.assertEqual(s.unterzeichner, self.s.betreuer)

    def test_objekt_wird_aus_einheit_abgeleitet(self):
        self.vorlage()
        s = schreiben_service.erstellen(
            'eigentuemer_allgemein', self.s.person, einheit=self.s.einheit, user=self.user)
        self.assertEqual(s.objekt_id, self.s.objekt.id)

    def test_objektspezifische_vorlage_hat_vorrang(self):
        self.vorlage()
        spezifisch = self.vorlage(
            objekt=self.s.objekt, inhalt=[{'typ': 'text', 'inhalt': 'Objektspezifischer Text.'}])
        s = self.erstelle()
        self.assertEqual(s.vorlage_version_id, spezifisch.id)
        self.assertIn('Objektspezifischer Text', s.html_gerendert)

    def test_keine_vorlage(self):
        with self.assertRaises(VorlageNichtGefunden):
            self.erstelle()

    def test_vorlage_ohne_freigegebene_version(self):
        version = self.vorlage()
        version.status = 'abgeloest'
        version.save()
        with self.assertRaises(VorlageNichtGefunden):
            self.erstelle()

    def test_pflicht_eingabefeld_fehlt_bleibt_entwurf_mit_fehler(self):
        self.vorlage(
            inhalt=[{'typ': 'text', 'inhalt': 'Termin: {{ eingabe.termin }}'}],
            eingabefelder=[{'name': 'termin', 'label': 'Termin', 'typ': 'text', 'pflicht': True}],
        )
        s = self.erstelle()
        self.assertEqual(s.status, 'entwurf')
        self.assertIn('termin', s.fehler.lower())
        self.assertEqual(s.html_gerendert, '')
        self.assertEqual(Dokument.objects.filter(dokument_typ='korrespondenz').count(), 0)
        # erscheint im Postausgang als "nicht erzeugbar"
        self.assertIn(s, postausgang_service.postausgang(status='nicht_erzeugbar'))
        self.assertIn(s, postausgang_service.postausgang())

    def test_eingabewerte_werden_gerendert(self):
        self.vorlage(
            inhalt=[{'typ': 'text', 'inhalt': 'Termin: {{ eingabe.termin }}'}],
            eingabefelder=[{'name': 'termin', 'label': 'Termin', 'typ': 'text', 'pflicht': True}],
        )
        s = self.erstelle(eingabewerte={'termin': 'Montag'})
        self.assertEqual(s.status, 'zur_pruefung')
        self.assertIn('Termin: Montag', s.html_gerendert)
        self.assertEqual(s.eingabewerte, {'termin': 'Montag'})

    def test_fehlendes_fusszeilen_bankkonto_ist_nicht_erzeugbar(self):
        self.vorlage()
        Bankkonto.objects.filter(objekt=self.s.objekt).update(zahlungsverkehr=False)
        s = self.erstelle()
        self.assertEqual(s.status, 'entwurf')
        self.assertIn('nicht erzeugbar', s.fehler)

    def test_kein_briefbogen_ist_nicht_erzeugbar(self):
        self.vorlage()
        Briefbogen.objects.update(ist_standard=False)
        s = self.erstelle()
        self.assertEqual(s.status, 'entwurf')
        self.assertIn('Briefbogen', s.fehler)

    def test_unerwarteter_fehler_wird_zu_nicht_erzeugbar(self):
        self.vorlage()
        with mock.patch.object(schreiben_service.kontext_service, 'baue_kontext', side_effect=RuntimeError('boom')):
            with self.assertLogs(schreiben_service.logger, 'ERROR'):
                s = self.erstelle()
        self.assertEqual(s.status, 'entwurf')
        self.assertIn('boom', s.fehler)

    def test_erneut_erzeugen_nach_korrektur(self):
        self.vorlage()
        Bankkonto.objects.filter(objekt=self.s.objekt).update(zahlungsverkehr=False)
        s = self.erstelle()
        self.assertEqual(s.status, 'entwurf')
        Bankkonto.objects.filter(objekt=self.s.objekt).update(zahlungsverkehr=True)
        s = schreiben_service.erneut_erzeugen(s)
        self.assertEqual(s.status, 'zur_pruefung')
        self.assertEqual(s.fehler, '')

    def test_erneut_erzeugen_nur_im_entwurf(self):
        self.vorlage()
        s = self.erstelle()
        with self.assertRaises(ValidationError):
            schreiben_service.erneut_erzeugen(s)

    def test_nummer_ist_eindeutig(self):
        self.vorlage()
        a, b = self.erstelle(), self.erstelle()
        self.assertNotEqual(a.nummer, b.nummer)
        with self.assertRaises(IntegrityError):
            Schreiben.objects.filter(pk=b.pk).update(nummer=a.nummer)


class FreigabeTest(VersandTestBasis):

    def setUp(self):
        self.version = self.vorlage()
        self.s1 = schreiben_service.erstellen(
            'eigentuemer_allgemein', self.s.person, objekt=self.s.objekt, einheit=self.s.einheit,
            user=self.user)

    def test_freigabe_erzeugt_genau_ein_revisionssicheres_dokument(self):
        s = schreiben_service.freigeben(self.s1, self.user)
        self.assertEqual(s.status, 'freigegeben')
        self.assertEqual(s.freigegeben_von, self.user)
        self.assertIsNotNone(s.freigegeben_am)
        self.assertTrue(s.dokument.revisionssicher)
        self.assertEqual(Dokument.objects.filter(dokument_typ='korrespondenz').count(), 1)
        self.assertEqual(s.dokument.dateiname, f'{s.nummer}.pdf')

    def test_pdf_zeigt_den_geprueften_text_und_wird_nicht_neu_gerendert(self):
        # Die Vorlage ändert sich nach dem Erstellen (hier hart in der DB): das PDF
        # muss trotzdem den geprüften Endtext enthalten.
        self.version.__class__.objects.filter(pk=self.version.pk).update(
            inhalt=[{'typ': 'text', 'inhalt': 'GEAENDERTER TEXT'}], betreff='Anderer Betreff')
        s = schreiben_service.freigeben(self.s1, self.user)
        text = seitentext(schreiben_service.pdf_bytes(s))
        self.assertIn('wir informieren Sie', text)
        self.assertNotIn('GEAENDERTER TEXT', text)
        self.assertIn('Information zum Objekt', text)

    def test_zweite_freigabe_ist_nicht_erlaubt_und_erzeugt_kein_zweites_dokument(self):
        schreiben_service.freigeben(self.s1, self.user)
        with self.assertRaises(ValidationError):
            schreiben_service.freigeben(self.s1, self.user)
        self.assertEqual(Dokument.objects.filter(dokument_typ='korrespondenz').count(), 1)

    def test_freigabe_nicht_erzeugbar_bleibt_zur_pruefung_mit_fehler(self):
        Bankkonto.objects.filter(objekt=self.s.objekt).update(zahlungsverkehr=False)
        with self.assertRaises(ValidationError) as ctx:
            schreiben_service.freigeben(self.s1, self.user)
        self.assertIn('nicht erzeugbar', str(ctx.exception))
        s = Schreiben.objects.get(pk=self.s1.pk)
        self.assertEqual(s.status, 'zur_pruefung')
        self.assertIn('nicht erzeugbar', s.fehler)
        self.assertIsNone(s.dokument_id)
        self.assertEqual(Dokument.objects.filter(dokument_typ='korrespondenz').count(), 0)

    def test_entwurf_kann_nicht_freigegeben_werden(self):
        Bankkonto.objects.filter(objekt=self.s.objekt).update(zahlungsverkehr=False)
        s = schreiben_service.erstellen(
            'eigentuemer_allgemein', self.s.person, objekt=self.s.objekt, user=self.user)
        self.assertEqual(s.status, 'entwurf')
        with self.assertRaises(ValidationError):
            schreiben_service.freigeben(s, self.user)

    def test_vorschau_vor_freigabe_legt_kein_dokument_an(self):
        pdf = schreiben_service.pdf_bytes(self.s1)
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertIn('wir informieren Sie', seitentext(pdf))
        self.assertEqual(Dokument.objects.filter(dokument_typ='korrespondenz').count(), 0)
        self.assertEqual(Schreiben.objects.get(pk=self.s1.pk).status, 'zur_pruefung')

    def test_pdf_nach_freigabe_ist_das_abgelegte_dokument(self):
        s = schreiben_service.freigeben(self.s1, self.user)
        with Dokument.objects.get(pk=s.dokument_id).datei.open('rb') as f:
            abgelegt = f.read()
        self.assertEqual(schreiben_service.pdf_bytes(s), abgelegt)

    def test_kein_pdf_fuer_verworfenes_schreiben(self):
        s = schreiben_service.verwerfen(self.s1, self.user)
        with self.assertRaises(ValidationError):
            schreiben_service.pdf_bytes(s)


class VerwerfenTest(VersandTestBasis):

    def setUp(self):
        self.vorlage()

    def erstelle(self):
        return schreiben_service.erstellen(
            'eigentuemer_allgemein', self.s.person, objekt=self.s.objekt, einheit=self.s.einheit,
            user=self.user)

    def test_zur_pruefung_wird_verworfen(self):
        s = schreiben_service.verwerfen(self.erstelle(), self.user)
        self.assertEqual(s.status, 'verworfen')
        self.assertNotIn(s, postausgang_service.postausgang())

    def test_nicht_erzeugbarer_entwurf_wird_verworfen(self):
        Bankkonto.objects.filter(objekt=self.s.objekt).update(zahlungsverkehr=False)
        s = self.erstelle()
        self.assertEqual(s.status, 'entwurf')
        self.assertEqual(schreiben_service.verwerfen(s, self.user).status, 'verworfen')

    def test_freigegebenes_wird_nicht_verworfen(self):
        s = schreiben_service.freigeben(self.erstelle(), self.user)
        with self.assertRaises(ValidationError):
            schreiben_service.verwerfen(s, self.user)
        self.assertEqual(Schreiben.objects.get(pk=s.pk).status, 'freigegeben')

    def test_verworfenes_ist_endzustand(self):
        s = schreiben_service.verwerfen(self.erstelle(), self.user)
        for aktion in (schreiben_service.freigeben, schreiben_service.verwerfen, schreiben_service.versenden):
            with self.subTest(aktion=aktion.__name__), self.assertRaises(ValidationError):
                aktion(s, self.user)

    def test_unerlaubter_uebergang_wird_abgelehnt(self):
        s = self.erstelle()
        with self.assertRaises(ValidationError):
            schreiben_service._uebergang(s, 'versendet')
        with self.assertRaises(ValidationError):
            schreiben_service.versenden(s, self.user)        # zur_pruefung ist nicht versendbar


class TextanpassungTest(VersandTestBasis):

    NEU = [{'typ': 'text', 'inhalt': 'Individuell angepasster Text.'}]

    def erstelle(self, bearbeitbar=True):
        self.vorlage(einzeln_bearbeitbar=bearbeitbar)
        return schreiben_service.erstellen(
            'eigentuemer_allgemein', self.s.person, objekt=self.s.objekt, einheit=self.s.einheit,
            user=self.user)

    def test_anpassung_rendert_neu_und_landet_im_pdf(self):
        s = schreiben_service.passe_an(self.erstelle(), self.NEU)
        self.assertEqual(s.inhalt_angepasst, self.NEU)
        self.assertIn('Individuell angepasster Text', s.html_gerendert)
        s = schreiben_service.freigeben(s, self.user)
        text = seitentext(schreiben_service.pdf_bytes(s))
        self.assertIn('Individuell angepasster Text', text)
        self.assertNotIn('wir informieren Sie', text)

    def test_nicht_bearbeitbare_vorlage(self):
        s = self.erstelle(bearbeitbar=False)
        with self.assertRaises(ValidationError):
            schreiben_service.passe_an(s, self.NEU)
        self.assertIsNone(Schreiben.objects.get(pk=s.pk).inhalt_angepasst)

    def test_nur_im_status_zur_pruefung(self):
        s = schreiben_service.freigeben(self.erstelle(), self.user)
        with self.assertRaises(ValidationError):
            schreiben_service.passe_an(s, self.NEU)

    def test_nicht_renderbarer_inhalt_laesst_schreiben_unveraendert(self):
        s = self.erstelle()
        vorher = s.html_gerendert
        with self.assertRaises(ValidationError):
            schreiben_service.passe_an(s, [{'typ': 'text', 'inhalt': '{{ eingabe.gibt_es_nicht }}'}])
        s.refresh_from_db()
        self.assertEqual(s.html_gerendert, vorher)
        self.assertIsNone(s.inhalt_angepasst)

    def test_ungueltiges_format(self):
        s = self.erstelle()
        for inhalt in ('Text', [1, 2], {'typ': 'text'}):
            with self.subTest(inhalt=inhalt), self.assertRaises(ValidationError):
                schreiben_service.passe_an(s, inhalt)


class VorgangsverlaufTest(VersandTestBasis):

    def setUp(self):
        self.vorlage()
        typ, _ = VorgangTyp.objects.get_or_create(code='test', defaults={'bezeichnung': 'Test'})
        self.vorgang = Vorgang.objects.create(
            typ=typ, objekt=self.s.objekt, einheit=self.s.einheit, person=self.s.person,
            betreff='Schaden', erstellt_von=self.s.ersteller)

    def test_erstellt_und_versendet_im_verlauf(self):
        s = schreiben_service.erstellen(
            'eigentuemer_allgemein', self.s.person, vorgang=self.vorgang, user=self.user)
        self.assertEqual(s.vorgang_id, self.vorgang.id)
        self.assertEqual(s.objekt_id, self.s.objekt.id)            # aus dem Vorgang abgeleitet
        erstellt = VorgangEreignis.objects.get(vorgang=self.vorgang, typ='schreiben_erstellt')
        self.assertTrue(erstellt.intern)
        self.assertEqual(erstellt.neuer_wert, s.nummer)

        s = schreiben_service.freigeben(s, self.user)
        # Vorgang => Dokument hängt am Vorgang (Owner-Regel B-Hybrid)
        self.assertEqual(s.dokument.vorgang_id, self.vorgang.id)
        self.assertEqual(VorgangEreignis.objects.filter(typ='schreiben_versendet').count(), 0)

    def test_ohne_vorgang_kein_ereignis(self):
        schreiben_service.erstellen('eigentuemer_allgemein', self.s.person, objekt=self.s.objekt, user=self.user)
        self.assertEqual(VorgangEreignis.objects.count(), 0)
