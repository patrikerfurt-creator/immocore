"""Phase 6b: Anbindung Eigentümerwechsel (Spec 9.2, Test 18) und Vorgang (Spec 9.3).

Die Wechsel-Freigabe (``vorschau_committen``) bucht unverändert; die Schreiben entstehen per
``transaction.on_commit``. Im ``TestCase`` läuft on_commit nie von selbst, daher
``captureOnCommitCallbacks(execute=True)`` (bzw. ``execute=False`` als Beweis, dass NICHTS
innerhalb der Freigabe-Transaktion passiert).
PDFs entstehen echt (WeasyPrint/PyMuPDF) in einem temporären ``MEDIA_ROOT``.
"""
from datetime import timedelta
from unittest import mock

import pymupdf
from django.core.files.base import ContentFile
from rest_framework.test import APIClient

from apps.buchhaltung.models import FrontofficeAufgabe
from apps.buchhaltung.services import eigentuemerwechsel_korrektur_service as wechsel_service
from apps.dokumente.models import Dokument
from apps.korrespondenz.models import Schreiben, Vorlage, VorlageAnlage
from apps.korrespondenz.services import (
    anlagen_service, eigentuemerwechsel_anbindung_service, schreiben_service, vorlage_service,
)
from apps.korrespondenz.services.render_service import RenderFehler
from apps.personen.models import EigentumsVerhaeltnis

from . import fixtures
from .basis_versand import VersandTestBasis

BEGRUESSUNG = 'eigentuemer_begruessung'
VERABSCHIEDUNG = 'eigentuemer_verabschiedung'
SEPA_HINWEIS = 'Bitte senden Sie uns das beigefügte SEPA-Lastschriftmandat zurück.'
BEGRUESSUNG_TEXT = [
    {'typ': 'text', 'inhalt': (
        'wir begrüßen Sie in {{ objekt.bezeichnung }} ab dem {{ wechsel.wechsel_datum | datum }}. '
        'Ihr Hausgeld beträgt {{ hausgeld.monatsbetrag | euro }}.'
    )},
    {'typ': 'bedingt', 'bedingung': 'ev.sepa_mandat_fehlt', 'inhalt': SEPA_HINWEIS},
]
VERABSCHIEDUNG_TEXT = [
    {'typ': 'text', 'inhalt': 'wir danken Ihnen für die Zusammenarbeit bis zum {{ wechsel.wechsel_datum | datum }}.'},
]


def pdf_mit_text(text: str) -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), text)
    return doc.tobytes()


class WechselTestBasis(VersandTestBasis):
    """Szenario MIT Eigentümerwechsel (Neueigentümer ``s.person``, Voreigentümer Hans Alt)."""

    mandat = False

    def setUp(self):
        self.s = fixtures.szenario(wechsel=True, mahnung=False, vorgang=False, mandat=self.mandat)
        self.wechsel = self.s.wechsel
        self.freigeber = fixtures.User.objects.create_user('freigeber', password='x')

    # --- Hilfen ---
    def vorlage_begruessung(self, inhalt=None):
        return self.vorlage(BEGRUESSUNG, inhalt=BEGRUESSUNG_TEXT if inhalt is None else inhalt)

    def dokument(self, text, dateiname, kategorie='Sonstiges', objekt=None, **felder):
        pdf = pdf_mit_text(text)
        return Dokument.objects.create(
            datei=ContentFile(pdf, name=dateiname), dateiname=dateiname, kategorie=kategorie,
            objekt=objekt, hochgeladen_von=self.freigeber, **felder,
        )

    def anlage(self, vorlage, **felder):
        felder.setdefault('reihenfolge', 0)
        return VorlageAnlage.objects.create(vorlage=vorlage, **felder)

    def sepa_und_hausordnung(self, version, *, hausordnung=True):
        """SEPA-Formular (bedingte Pflichtanlage, fest hinterlegt) + Hausordnung (Objekt-Kategorie)."""
        sepa = self.dokument('SEPA-FORMULAR-SEITE', 'sepa.pdf')
        self.anlage(version.vorlage, art='dokument', bezeichnung='SEPA-Formular', pflicht=True,
                    dokument=sepa, bedingung='ev.sepa_mandat_fehlt', reihenfolge=1)
        self.anlage(version.vorlage, art='objekt_kategorie', bezeichnung='Hausordnung', pflicht=True,
                    objekt_kategorie='Hausordnung', reihenfolge=2)
        if hausordnung:
            self.dokument('HAUSORDNUNG-SEITE', 'hausordnung.pdf', 'Hausordnung', self.s.objekt)
        return sepa

    def freigeben(self, **kw):
        """Wechsel-Freigabe; die on_commit-Callbacks laufen wie nach einem echten Commit."""
        with self.captureOnCommitCallbacks(execute=True):
            return wechsel_service.vorschau_committen(self.wechsel, self.freigeber, 'DE02501900006300211010', **kw)

    def schreiben_liste(self):
        return list(Schreiben.objects.filter(eigentuemerwechsel=self.wechsel).order_by('erstellt_am'))

    def aufgaben(self):
        return FrontofficeAufgabe.objects.filter(aufgabe_typ='schreiben_nicht_erzeugbar')


class BegruessungTest(WechselTestBasis):

    def test_begruessung_zur_pruefung_an_den_neueigentuemer(self):
        self.vorlage_begruessung()
        self.freigeben()
        (schreiben,) = self.schreiben_liste()
        self.assertEqual(schreiben.status, 'zur_pruefung')          # NICHT automatisch freigegeben
        self.assertIsNone(schreiben.dokument_id)
        self.assertEqual(schreiben.empfaenger_id, self.s.person.pk)
        self.assertEqual(schreiben.eigentumsverhaeltnis_id, self.wechsel.neueigentuemer_ev_id)
        self.assertEqual(schreiben.unterzeichner_id, self.s.betreuer.pk)  # Automatik = Objektbetreuer
        self.assertIn('WEG Musterstraße 1', schreiben.html_gerendert)
        self.assertIn('300,00', schreiben.html_gerendert)
        self.assertFalse(self.aufgaben().exists())
        self.wechsel.refresh_from_db()
        self.assertEqual(self.wechsel.status, 'freigegeben')

    def test_nichts_innerhalb_der_freigabe_transaktion(self):
        """Die Schreiben entstehen erst per on_commit - die Freigabe selbst legt keines an."""
        self.vorlage_begruessung()
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            wechsel_service.vorschau_committen(self.wechsel, self.freigeber, 'DE02501900006300211010')
        self.assertEqual(len(callbacks), 1)
        self.assertEqual(Schreiben.objects.count(), 0)
        callbacks[0]()
        self.assertEqual(Schreiben.objects.filter(eigentuemerwechsel=self.wechsel).count(), 1)

    def test_verabschiedung_nur_mit_aktiver_vorlage(self):
        self.vorlage_begruessung()
        self.freigeben()
        self.assertEqual(len(self.schreiben_liste()), 1)            # ohne Vorlage: nichts, keine Aufgabe
        self.assertFalse(self.aufgaben().exists())

    def test_verabschiedung_an_den_voreigentuemer(self):
        self.vorlage_begruessung()
        self.vorlage(VERABSCHIEDUNG, inhalt=VERABSCHIEDUNG_TEXT)
        self.freigeben()
        schreiben = {s.vorlage_version.vorlage.code: s for s in self.schreiben_liste()}
        self.assertEqual(set(schreiben), {BEGRUESSUNG, VERABSCHIEDUNG})
        alt = schreiben[VERABSCHIEDUNG]
        self.assertEqual(alt.status, 'zur_pruefung')
        self.assertEqual(alt.empfaenger_id, self.wechsel.voreigentuemer_ev.person_id)
        self.assertEqual(alt.eigentumsverhaeltnis_id, self.wechsel.voreigentuemer_ev_id)

    def test_inaktive_verabschiedung_wird_ignoriert(self):
        self.vorlage_begruessung()
        self.vorlage(VERABSCHIEDUNG, inhalt=VERABSCHIEDUNG_TEXT)
        Vorlage.objects.filter(code=VERABSCHIEDUNG).update(aktiv=False)
        self.freigeben()
        self.assertEqual([s.vorlage_version.vorlage.code for s in self.schreiben_liste()], [BEGRUESSUNG])

    def test_fehlerhafte_verabschiedung_blockiert_begruessung_nicht(self):
        self.vorlage_begruessung()
        self.vorlage(VERABSCHIEDUNG, inhalt=[{'typ': 'text', 'inhalt': '{{ wechsel.gibt_es_nicht }}'}])
        self.freigeben()
        stati = {s.vorlage_version.vorlage.code: s.status for s in self.schreiben_liste()}
        self.assertEqual(stati, {BEGRUESSUNG: 'zur_pruefung', VERABSCHIEDUNG: 'entwurf'})
        self.assertEqual(self.aufgaben().count(), 1)


class FehlerverhaltenTest(WechselTestBasis):
    """Test 18: ein Fehler bei der Schreiben-Erzeugung rollt die Freigabe NICHT zurück."""

    def pruefe_freigabe_besteht(self):
        self.wechsel.refresh_from_db()
        self.assertEqual(self.wechsel.status, 'freigegeben')
        self.assertEqual(self.wechsel.freigegeben_von_id, self.freigeber.pk)
        self.assertIsNone(self.wechsel.neueigentuemer_ev.ende)
        self.assertEqual(self.wechsel.voreigentuemer_ev.ende, self.wechsel.wechsel_datum - timedelta(days=1))
        self.assertTrue(FrontofficeAufgabe.objects.filter(aufgabe_typ='eigentuemerwechsel_forderung').exists())

    def test_fehlende_begruessungs_vorlage_nur_aufgabe(self):
        self.freigeben()
        self.pruefe_freigabe_besteht()
        self.assertEqual(self.schreiben_liste(), [])
        (aufgabe,) = self.aufgaben()
        self.assertEqual(aufgabe.objekt_id, self.s.objekt.pk)
        self.assertEqual(aufgabe.ev_id, self.wechsel.neueigentuemer_ev_id)
        self.assertIn('Vorlage fehlt', aufgabe.beschreibung)
        self.assertEqual(aufgabe.erstellt_von_id, self.freigeber.pk)

    def test_vorlage_ohne_freigegebene_version_nur_aufgabe(self):
        vorlage = self.vorlage_begruessung().vorlage
        Vorlage.objects.filter(pk=vorlage.pk).update(aktive_version=None)
        self.freigeben()
        self.pruefe_freigabe_besteht()
        self.assertEqual(self.aufgaben().count(), 1)

    def test_unerwarteter_fehler_rollt_freigabe_nicht_zurueck(self):
        self.vorlage_begruessung()
        with mock.patch.object(schreiben_service, 'erstelle_aus_version', side_effect=RuntimeError('kaputt')):
            self.freigeben()                                         # wirft nicht
        self.pruefe_freigabe_besteht()
        self.assertEqual(self.schreiben_liste(), [])
        (aufgabe,) = self.aufgaben()
        self.assertIn('kaputt', aufgabe.beschreibung)

    def test_fehler_beim_laden_nach_dem_commit_erreicht_den_aufrufer_nicht(self):
        self.vorlage_begruessung()
        with mock.patch.object(eigentuemerwechsel_anbindung_service, 'erzeuge_schreiben',
                               side_effect=RuntimeError('boom')):
            self.freigeben()
        self.pruefe_freigabe_besteht()

    def test_nicht_erzeugbar_bleibt_entwurf_mit_fehler_und_aufgabe(self):
        self.vorlage_begruessung(inhalt=[{'typ': 'text', 'inhalt': '{{ eingabe.fehlt }}'}])
        self.freigeben()
        self.pruefe_freigabe_besteht()
        (schreiben,) = self.schreiben_liste()
        self.assertEqual(schreiben.status, 'entwurf')
        self.assertTrue(schreiben.fehler)
        (aufgabe,) = self.aufgaben()
        self.assertIn(schreiben.nummer, aufgabe.beschreibung)

    def test_wechselfehler_loest_keine_schreiben_aus(self):
        """Scheitert die Freigabe selbst, wird nichts registriert."""
        self.vorlage_begruessung()
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            with self.assertRaises(Exception):
                wechsel_service.vorschau_committen(self.wechsel, self.s.ersteller, 'DE02501900006300211010')
        self.assertEqual(callbacks, [])
        self.assertEqual(self.schreiben_liste(), [])


class SepaUndAnlagenTest(WechselTestBasis):
    """Bedingte Blöcke/Anlagen: SEPA-Mandat fehlt -> Hinweis + Pflichtanlage; Hausordnung je Objekt."""

    def test_sepa_fehlt_hinweisblock_und_pflichtanlage(self):
        version = self.vorlage_begruessung()
        self.sepa_und_hausordnung(version)
        self.freigeben()
        (schreiben,) = self.schreiben_liste()
        self.assertEqual(schreiben.status, 'zur_pruefung')
        self.assertIn(SEPA_HINWEIS, schreiben.html_gerendert)
        refs = schreiben.kontext_snapshot[schreiben_service.SNAPSHOT_ANLAGEN]
        self.assertEqual([r['bezeichnung'] for r in refs], ['SEPA-Formular', 'Hausordnung'])

        schreiben_service.freigeben(schreiben, self.freigeber)
        with pymupdf.open(stream=schreiben.dokument.datei.read(), filetype='pdf') as pdf:
            texte = [seite.get_text() for seite in pdf]
        self.assertEqual(len(texte), 3)                              # Brief + SEPA + Hausordnung
        self.assertIn('SEPA-FORMULAR-SEITE', texte[1])
        self.assertIn('HAUSORDNUNG-SEITE', texte[2])

    def test_sepa_fehlt_aber_formular_nicht_hinterlegt_nicht_erzeugbar(self):
        version = self.vorlage_begruessung()
        self.anlage(version.vorlage, art='dokument', bezeichnung='SEPA-Formular', pflicht=True,
                    bedingung='ev.sepa_mandat_fehlt')
        self.freigeben()
        (schreiben,) = self.schreiben_liste()
        self.assertEqual(schreiben.status, 'entwurf')
        self.assertIn('SEPA-Formular', schreiben.fehler)
        self.assertEqual(self.aufgaben().count(), 1)

    def test_fehlende_hausordnung_pflicht_nicht_erzeugbar(self):
        version = self.vorlage_begruessung()
        self.sepa_und_hausordnung(version, hausordnung=False)
        self.freigeben()
        (schreiben,) = self.schreiben_liste()
        self.assertEqual(schreiben.status, 'entwurf')
        self.assertIn('Hausordnung', schreiben.fehler)
        self.assertNotIn('SEPA-Formular', schreiben.fehler)          # SEPA ist vorhanden
        self.assertEqual(self.aufgaben().count(), 1)
        self.wechsel.refresh_from_db()
        self.assertEqual(self.wechsel.status, 'freigegeben')

    def test_vorschau_zeigt_die_anlagen(self):
        version = self.vorlage_begruessung()
        self.sepa_und_hausordnung(version)
        self.freigeben()
        (schreiben,) = self.schreiben_liste()
        with pymupdf.open(stream=schreiben_service.pdf_bytes(schreiben), filetype='pdf') as pdf:
            self.assertEqual(pdf.page_count, 3)

    def test_anlagenauswahl_ist_eingefroren(self):
        """Ein später ersetztes Dokument ändert ein bereits geprüftes Schreiben nicht."""
        version = self.vorlage_begruessung()
        self.sepa_und_hausordnung(version)
        self.freigeben()
        (schreiben,) = self.schreiben_liste()
        self.dokument('NEUE-HAUSORDNUNG', 'neu.pdf', 'Hausordnung', self.s.objekt)
        schreiben_service.freigeben(schreiben, self.freigeber)
        with pymupdf.open(stream=schreiben.dokument.datei.read(), filetype='pdf') as pdf:
            self.assertIn('HAUSORDNUNG-SEITE', pdf[2].get_text())
            self.assertNotIn('NEUE-HAUSORDNUNG', pdf[2].get_text())


class SepaVorhandenTest(WechselTestBasis):
    mandat = True

    def test_sepa_vorhanden_kein_hinweis_keine_sepa_anlage(self):
        version = self.vorlage_begruessung()
        self.sepa_und_hausordnung(version)
        self.freigeben()
        (schreiben,) = self.schreiben_liste()
        self.assertEqual(schreiben.status, 'zur_pruefung')
        self.assertNotIn(SEPA_HINWEIS, schreiben.html_gerendert)
        refs = schreiben.kontext_snapshot[schreiben_service.SNAPSHOT_ANLAGEN]
        self.assertEqual([r['bezeichnung'] for r in refs], ['Hausordnung'])

    def test_bedingte_pflichtanlage_ohne_dokument_stoert_nicht(self):
        version = self.vorlage_begruessung()
        self.anlage(version.vorlage, art='dokument', bezeichnung='SEPA-Formular', pflicht=True,
                    bedingung='ev.sepa_mandat_fehlt')
        self.freigeben()
        (schreiben,) = self.schreiben_liste()
        self.assertEqual(schreiben.status, 'zur_pruefung')


class AnlagenAufloesungTest(WechselTestBasis):
    """``anlagen_service.loese_auf``: art=dokument / art=objekt_kategorie, Reihenfolge, Pflicht."""

    def setUp(self):
        super().setUp()
        self.version = self.vorlage_begruessung()
        self.vorlage_obj = self.version.vorlage
        self.kontext = {'ev': {'sepa_mandat_fehlt': True}}

    def loese(self, kontext=None):
        return anlagen_service.loese_auf(self.vorlage_obj, self.s.objekt, kontext or self.kontext)

    def test_dokument_und_objekt_kategorie_in_reihenfolge(self):
        fest = self.dokument('FEST', 'fest.pdf')
        haus = self.dokument('HAUS', 'haus.pdf', 'Hausordnung', self.s.objekt)
        self.anlage(self.vorlage_obj, art='objekt_kategorie', bezeichnung='Hausordnung',
                    objekt_kategorie='Hausordnung', reihenfolge=2)
        self.anlage(self.vorlage_obj, art='dokument', bezeichnung='Festes', dokument=fest, reihenfolge=1)
        ergebnis = self.loese()
        self.assertEqual([(a.bezeichnung, a.dokument.pk) for a in ergebnis],
                         [('Festes', fest.pk), ('Hausordnung', haus.pk)])

    def test_pdf_bytes_werden_geladen(self):
        fest = self.dokument('FEST-INHALT', 'fest.pdf')
        self.anlage(self.vorlage_obj, art='dokument', bezeichnung='Festes', dokument=fest)
        refs = anlagen_service.als_refs(self.loese())
        (anlage,) = anlagen_service.lade_pdfs(refs)
        self.assertEqual(anlage.bezeichnung, 'Festes')
        with pymupdf.open(stream=anlage.pdf, filetype='pdf') as pdf:
            self.assertIn('FEST-INHALT', pdf[0].get_text())

    def test_objekt_kategorie_nimmt_aktuellstes_nicht_abgeloestes_pdf_des_richtigen_objekts(self):
        alt = self.dokument('ALT', 'alt.pdf', 'Hausordnung', self.s.objekt, dokument_datum='2020-01-01')
        neu = self.dokument('NEU', 'neu.pdf', 'hausordnung', self.s.objekt, dokument_datum='2024-01-01')
        self.dokument('ANDERES-OBJEKT', 'x.pdf', 'Hausordnung', fixtures.szenario(
            wechsel=False, mahnung=False, vorgang=False).objekt, dokument_datum='2030-01-01')
        self.dokument('KEIN-PDF', 'x.docx', 'Hausordnung', self.s.objekt, dokument_datum='2031-01-01')
        self.anlage(self.vorlage_obj, art='objekt_kategorie', bezeichnung='Hausordnung',
                    objekt_kategorie='Hausordnung')
        self.assertEqual(self.loese()[0].dokument.pk, neu.pk)        # Kategorie ohne Groß-/Kleinschreibung
        Dokument.objects.filter(pk=alt.pk).update(vorgaenger_version=None)
        Dokument.objects.filter(pk=neu.pk).update(vorgaenger_version=alt)  # neu ersetzt alt
        self.assertEqual(self.loese()[0].dokument.pk, neu.pk)

    def test_optionale_fehlende_anlage_entfaellt(self):
        self.anlage(self.vorlage_obj, art='objekt_kategorie', bezeichnung='Hausordnung',
                    objekt_kategorie='Hausordnung', pflicht=False)
        self.anlage(self.vorlage_obj, art='dokument', bezeichnung='Ohne Dokument', pflicht=False)
        self.assertEqual(self.loese(), [])

    def test_fehlende_pflichtanlagen_werden_alle_gemeldet(self):
        self.anlage(self.vorlage_obj, art='objekt_kategorie', bezeichnung='Hausordnung',
                    objekt_kategorie='Hausordnung', pflicht=True)
        self.anlage(self.vorlage_obj, art='dokument', bezeichnung='SEPA-Formular', pflicht=True)
        with self.assertRaises(RenderFehler) as ctx:
            self.loese()
        self.assertIn('Hausordnung', str(ctx.exception))
        self.assertIn('SEPA-Formular', str(ctx.exception))

    def test_bedingung_nicht_erfuellt_entfaellt_auch_pflicht(self):
        self.anlage(self.vorlage_obj, art='dokument', bezeichnung='SEPA-Formular', pflicht=True,
                    bedingung='ev.sepa_mandat_fehlt')
        self.assertEqual(self.loese({'ev': {'sepa_mandat_fehlt': False}}), [])

    def test_datei_fehlt_auf_platte_pflicht_nicht_erzeugbar(self):
        fest = self.dokument('FEST', 'fest.pdf')
        self.anlage(self.vorlage_obj, art='dokument', bezeichnung='Festes', dokument=fest, pflicht=True)
        fest.datei.storage.delete(fest.datei.name)
        with self.assertRaises(RenderFehler):
            self.loese()

    def test_ohne_anlagen_bleibt_alles_wie_bisher(self):
        self.assertEqual(self.loese(), [])
        self.freigeben()
        (schreiben,) = self.schreiben_liste()
        self.assertEqual(schreiben.kontext_snapshot[schreiben_service.SNAPSHOT_ANLAGEN], [])
        schreiben_service.freigeben(schreiben, self.freigeber)
        with pymupdf.open(stream=schreiben.dokument.datei.read(), filetype='pdf') as pdf:
            self.assertEqual(pdf.page_count, 1)


class VorgangAnbindungTest(VersandTestBasis):
    """Spec 9.3: "Schreiben erstellen" im Vorgang setzt ``vorgang``; ``vorgang_antwort`` ist bearbeitbar."""

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.s = fixtures.szenario(wechsel=False, mahnung=False, vorgang=True)

    def test_api_schreiben_erstellen_setzt_vorgang(self):
        self.vorlage('antwort', 'vorgang_antwort', einzeln_bearbeitbar=True)
        antwort = self.client.post('/api/v1/korrespondenz/schreiben/', {
            'vorlage_code': 'antwort', 'empfaenger': str(self.s.person.pk),
            'vorgang': str(self.s.vorgang.pk),
        }, format='json')
        self.assertEqual(antwort.status_code, 201, antwort.content)
        schreiben = Schreiben.objects.get(pk=antwort.json()['id'])
        self.assertEqual(schreiben.vorgang_id, self.s.vorgang.pk)
        self.assertEqual(schreiben.objekt_id, self.s.objekt.pk)
        self.assertTrue(antwort.json()['einzeln_bearbeitbar'])

    def test_vorgang_antwort_ist_immer_einzeln_bearbeitbar(self):
        vorlage = vorlage_service.lege_vorlage_an(
            code='va', bezeichnung='Antwort', anlass='vorgang_antwort', einzeln_bearbeitbar=False)
        self.assertTrue(vorlage.einzeln_bearbeitbar)
        andere = vorlage_service.lege_vorlage_an(
            code='allg', bezeichnung='Allgemein', anlass='eigentuemer_allgemein', einzeln_bearbeitbar=False)
        self.assertFalse(andere.einzeln_bearbeitbar)

    def test_patch_kann_einzeln_bearbeitbar_bei_vorgang_antwort_nicht_abschalten(self):
        vorlage = vorlage_service.lege_vorlage_an(code='va', bezeichnung='A', anlass='vorgang_antwort')
        antwort = self.client.patch(
            f'/api/v1/korrespondenz/vorlagen/{vorlage.pk}/', {'einzeln_bearbeitbar': False}, format='json')
        self.assertEqual(antwort.status_code, 200, antwort.content)
        vorlage.refresh_from_db()
        self.assertTrue(vorlage.einzeln_bearbeitbar)
