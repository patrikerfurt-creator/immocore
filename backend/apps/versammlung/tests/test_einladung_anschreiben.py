"""
EV-Einladung mit vorangestelltem Anschreiben (Spec 9.4, Phase 6d).

Stapel je Eigentümer: Anschreiben (Demme-Briefbogen) + Vollmacht-Seite -> Einladung
(altes ``einladung.html``, unverändert) -> frei angehängte Anlagen. Die PDFs entstehen
echt mit WeasyPrint/PyMuPDF; geprüft wird über die Textschicht. Logos entstehen als
``Dokument`` in einem temporären ``MEDIA_ROOT``.
"""
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest import mock

import pymupdf
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.dokumente.models import Dokument
from apps.korrespondenz.tests import fixtures_brief
from apps.objekte.models import Bankkonto
from apps.personen.models import Person
from apps.versammlung.models import EVVersandprotokoll
from apps.versammlung.services import (
    einladung_anschreiben_service, einladung_service, ev_service, stimmkraft_service,
    tagesordnung_service,
)
from apps.versammlung.tests import factories as f

User = get_user_model()

_MEDIA_TMP = tempfile.mkdtemp(prefix='immocore_test_media_ev_anschreiben_')
TEST_IBAN = 'DE02501900006300211010'

# Nur im Anschreiben bzw. nur in der alten Einladung vorkommende Marker.
MARKER_ANSCHREIBEN = 'Unser Zeichen:'
MARKER_ALTE_EINLADUNG = 'Objekt-Nr.'
MARKER_ANLAGE = 'FREMDANLAGE-INHALT'


def tearDownModule():
    shutil.rmtree(_MEDIA_TMP, ignore_errors=True)


def seitentexte(pdf: bytes) -> list:
    with pymupdf.open(stream=pdf, filetype='pdf') as doc:
        return [seite.get_text() for seite in doc]


def kompakt(text: str) -> str:
    return ''.join(text.split())


def erste_seite_mit(seiten: list, marker: str) -> int:
    for nr, text in enumerate(seiten):
        if marker in text:
            return nr
    raise AssertionError(f'Marker {marker!r} auf keiner Seite gefunden.')


class AnschreibenTestBasis(TestCase):
    """WEG mit Zahlungsverkehrskonto, Briefbogen, Eheleute-Eigentümer, EV mit 4 TOPs."""

    @classmethod
    def setUpClass(cls):
        cls._override = override_settings(MEDIA_ROOT=_MEDIA_TMP)
        cls._override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._override.disable()

    def setUp(self):
        self.user = User.objects.create_user(
            'ev-anschreiben', password='x', first_name='Anna', last_name='Beispiel',
        )
        self.objekt = f.objekt(bezeichnung='WEG Musterstraße 1', nummer='EV0053')
        self.objekt.betreuer = self.user
        self.objekt.save(update_fields=['betreuer'])
        Bankkonto.objects.create(
            objekt=self.objekt, konto_typ='bewirtschaftung', bezeichnung='Bewirtschaftung',
            iban=TEST_IBAN, bic='FFVBDEFFXXX', kontoinhaber='WEG Musterstraße 1',
            zahlungsverkehr=True,
        )
        self.briefbogen = fixtures_brief.demme_briefbogen(self.user)

        self.person = Person.objects.create(
            personennummer='PEAN01', person_typ='100', anrede='Eheleute', titel='Dr.',
            vorname='Max', nachname='Mustermann', vorname2='Erika',
            strasse='Musterweg', hausnummer='5', plz='60311', ort='Frankfurt am Main',
            adresse='Musterweg 5\n60311 Frankfurt am Main',
        )
        f.eigentuemer(self.objekt, self.person, nr='012')

        self.ev = ev_service.erstelle_ev(objekt=self.objekt, erstellt_von=self.user)
        ev_service.aktualisiere_terminierung(
            self.ev, self.user, termin=timezone.now() + timedelta(days=30),
            ort='Gemeinschaftsraum, Musterstraße 1',
        )
        for titel in ('Jahresabrechnung 2025', 'Wirtschaftsplan 2027', 'Bestellung des Verwalters',
                      'Leerrohre für die Stellplätze'):
            tagesordnung_service.top_anlegen(
                ev=self.ev, titel=titel, erstellt_von=self.user,
                beschlussvorlage=f'Es wird beschlossen: {titel}.',
            )
        stimmkraft_service.ermittle_teilnehmer(self.ev, self.user)
        self.teilnehmer = self.ev.teilnehmer.get(person=self.person)

    def anschreiben(self, teilnehmer=None, anlagen=None) -> list:
        return seitentexte(einladung_anschreiben_service.rendere_anschreiben_pdf(
            self.ev, self.briefbogen, teilnehmer=teilnehmer, anlagen=anlagen,
        ))

    def fremd_anlage(self) -> Dokument:
        with pymupdf.open() as doc:
            doc.new_page().insert_text((72, 72), MARKER_ANLAGE)
            inhalt = doc.tobytes()
        return Dokument.objects.create(
            datei=ContentFile(inhalt, name='Hausordnung.pdf'), dateiname='Hausordnung.pdf',
            beschreibung='Hausordnung 2026', dokument_typ='sonstiges', objekt=self.objekt,
            hochgeladen_von=self.user,
        )


class StapelTest(AnschreibenTestBasis):

    def test_reihenfolge_anschreiben_vollmacht_einladung_anlagen(self):
        anlage = self.fremd_anlage()
        seiten = seitentexte(einladung_service.rendere_einladung(
            self.ev, empfaenger=self.teilnehmer,
        ))
        i_brief = erste_seite_mit(seiten, MARKER_ANSCHREIBEN)
        i_vollmacht = erste_seite_mit(seiten, 'Vertretungsvollmacht')
        i_einladung = erste_seite_mit(seiten, MARKER_ALTE_EINLADUNG)
        self.assertEqual(i_brief, 0)
        self.assertLess(i_brief, i_vollmacht)
        self.assertLess(i_vollmacht, i_einladung)
        self.assertNotIn(MARKER_ANSCHREIBEN, seiten[i_einladung])   # Einladung ohne Briefbogen-Kopf

        dokument = einladung_service.erzeuge_einladungs_pdf(
            self.ev, self.user, anlagen_ids=[str(anlage.id)],
        )
        with dokument.datei.open('rb') as datei:
            gesamt = seitentexte(datei.read())
        self.assertEqual(erste_seite_mit(gesamt, MARKER_ANSCHREIBEN), 0)
        self.assertLess(erste_seite_mit(gesamt, 'Vertretungsvollmacht'),
                        erste_seite_mit(gesamt, MARKER_ALTE_EINLADUNG))
        self.assertLess(erste_seite_mit(gesamt, MARKER_ALTE_EINLADUNG),
                        erste_seite_mit(gesamt, MARKER_ANLAGE))
        self.assertIn(MARKER_ANLAGE, gesamt[-1])                     # Anlage ganz hinten
        self.assertEqual(dokument.objekt_id, self.objekt.id)

    def test_alte_einladung_wird_unveraendert_mit_dem_alten_template_gerendert(self):
        with mock.patch.object(
            einladung_service, 'render_to_string', wraps=einladung_service.render_to_string,
        ) as spy:
            einladung_service.rendere_einladung(self.ev, empfaenger=self.teilnehmer)
        self.assertIn('versammlung/einladung.html', [c.args[0] for c in spy.call_args_list])

        seiten = seitentexte(einladung_service.rendere_einladung(self.ev))
        text = '\n'.join(seiten[erste_seite_mit(seiten, MARKER_ALTE_EINLADUNG):])
        self.assertIn('Einladung zur Ordentliche Versammlung', text)   # Überschrift des alten Templates
        for nr, titel in enumerate(('Jahresabrechnung 2025', 'Wirtschaftsplan 2027',
                                    'Bestellung des Verwalters', 'Leerrohre für die Stellplätze'), 1):
            self.assertIn(f'TOP {nr}: {titel}', text)
        self.assertIn('Gemeinschaftsraum, Musterstraße 1', text)

    def test_einladung_selbst_traegt_keine_briefbogen_elemente(self):
        # Kein Briefbogen-Element (Bezugszeichen) in der Einladung selbst.
        seiten = seitentexte(einladung_service.rendere_einladung(self.ev))
        for text in seiten[erste_seite_mit(seiten, MARKER_ALTE_EINLADUNG):]:
            self.assertNotIn(MARKER_ANSCHREIBEN, text)

    def test_anlagenverzeichnis_des_anschreibens(self):
        seite1 = self.anschreiben(self.teilnehmer, anlagen=[self.fremd_anlage()])[0]
        nach = seite1.split('Anlagen:')[1]
        self.assertIn('Einladung zur Eigentümerversammlung mit Tagesordnung', nach)
        self.assertIn('Vollmacht', nach)
        self.assertIn('Hausordnung.pdf', nach)


class AnschreibenPersonalisiertTest(AnschreibenTestBasis):

    def test_anschrift_aus_den_einzelfeldern(self):
        seite1 = self.anschreiben(self.teilnehmer)[0]
        for zeile in ('Eheleute', 'Dr. Max Mustermann', 'Erika Mustermann', 'Musterweg 5',
                      '60311 Frankfurt am Main'):
            self.assertIn(zeile, seite1)

    def test_legacy_adresse_wird_nicht_verwendet(self):
        Person.objects.filter(pk=self.person.pk).update(adresse='ALTLAST-ADRESSE 99\n11111 Altstadt')
        self.assertNotIn('ALTLAST', '\n'.join(self.anschreiben(self.teilnehmer)))

    def test_persoenliche_briefanrede(self):
        seite1 = self.anschreiben(self.teilnehmer)[0]
        self.assertIn('Sehr geehrte Frau Dr. Mustermann,', seite1)
        self.assertIn('sehr geehrter Herr Mustermann,', seite1)
        self.assertNotIn('Sehr geehrte Damen und Herren', seite1)

    def test_betreff_termin_ort_und_bezugszeichen(self):
        seite1 = self.anschreiben(self.teilnehmer)[0]
        termin = timezone.localtime(self.ev.termin)
        self.assertIn(f'Einladung zur ordentlichen Eigentümerversammlung am {termin:%d.%m.%Y}', seite1)
        self.assertIn('Objekt: EV0053-WEG Musterstraße 1', seite1)
        self.assertIn('Gemeinschaftsraum, Musterstraße 1', seite1)
        self.assertIn(f'{termin.hour}.{termin.minute:02d} Uhr', seite1)
        self.assertIn('eine ordentliche Eigentümerversammlung', ' '.join(seite1.split()))
        self.assertIn('EV0053/', seite1)                              # Unser Zeichen

    def test_firma_unterzeichnet_ohne_persoenliches_gez(self):
        text = '\n'.join(self.anschreiben(self.teilnehmer))
        schluss = text.split('Mit freundlichen Grüßen')[1]
        self.assertIn('Demme Immobilien Verwaltung GmbH', schluss)
        self.assertNotIn('gez.', text)
        self.assertNotIn('Anna Beispiel', text)                       # Objektbetreuer unterzeichnet nicht

    def test_anschreiben_braucht_keinen_unterzeichner(self):
        self.objekt.betreuer = None
        self.objekt.save(update_fields=['betreuer'])
        self.ev.erstellt_von = User.objects.create_user('ohne-namen', password='x')
        self.ev.save(update_fields=['erstellt_von'])
        self.assertIn('Mit freundlichen Grüßen', self.anschreiben(self.teilnehmer)[0])

    def test_vollmacht_ist_seite_des_anschreibens_ohne_briefkopf_mit_fusszeile(self):
        seiten = self.anschreiben(self.teilnehmer)
        self.assertEqual(len(seiten), 2)                              # Brief + Vollmacht
        vollmacht = seiten[-1]
        self.assertIn('Vertretungsvollmacht', vollmacht)
        self.assertIn('Hiermit bevollmächtige ich', vollmacht)
        self.assertIn('die Verwalterin, Demme Immobilien Verwaltung GmbH', vollmacht)
        self.assertNotIn('Ihr Zeichen:', vollmacht)                   # Anlage-Seite ohne Briefkopf
        self.assertNotIn('Sehr geehrte', vollmacht)
        for nr, text in enumerate(seiten, 1):
            self.assertIn('BIC: FFVBDEFFXXX', text, f'Fußzeile fehlt auf Seite {nr}')
            self.assertIn(TEST_IBAN, kompakt(text), f'IBAN fehlt auf Seite {nr}')
        self.assertIn('Seite 2 von 2', vollmacht)

    def test_vollmacht_nennt_vollmachtgeber_und_einheit(self):
        vollmacht = self.anschreiben(self.teilnehmer)[-1]
        for text in ('Dr. Max Mustermann', 'Musterweg 5', '60311 Frankfurt am Main', 'Einheit 012'):
            self.assertIn(text, vollmacht)


class AnschreibenNeutralTest(AnschreibenTestBasis):

    def test_neutrale_anschrift_und_anrede(self):
        seite1 = self.anschreiben()[0]
        self.assertIn('An die Wohnungseigentümer', seite1)
        self.assertIn('Sehr geehrte Damen und Herren,', seite1)
        self.assertIn('Einladung zur ordentlichen Eigentümerversammlung am', seite1)

    def test_vollmacht_mit_schreiblinien(self):
        vollmacht = self.anschreiben()[-1]
        self.assertIn('Vertretungsvollmacht', vollmacht)
        self.assertIn('______________________________', vollmacht)
        self.assertNotIn('Mustermann', vollmacht)
        self.assertIn('BIC: FFVBDEFFXXX', vollmacht)

    def test_dms_dokument_ist_die_neutrale_fassung(self):
        dokument = einladung_service.erzeuge_einladungs_pdf(self.ev, self.user)
        with dokument.datei.open('rb') as datei:
            seiten = seitentexte(datei.read())
        self.assertIn('An die Wohnungseigentümer', seiten[0])
        self.assertNotIn('Mustermann', seiten[0])


class RueckfallOhneBriefbogenTest(TestCase):
    """Ohne Standard-Briefbogen (Seed folgt in Phase 7) geht nur die alte Einladung raus."""

    @override_settings(MEDIA_ROOT=_MEDIA_TMP)
    def test_nur_alte_einladung_mit_log_warnung(self):
        user = f.user()
        ev = ev_service.erstelle_ev(objekt=f.objekt(), erstellt_von=user)
        ev_service.aktualisiere_terminierung(
            ev, user, termin=timezone.now() + timedelta(days=30), ort='Saal',
        )
        tagesordnung_service.top_anlegen(
            ev=ev, titel='Jahresabrechnung', erstellt_von=user, beschlussvorlage='Beschluss.',
        )
        with self.assertLogs('apps.versammlung.services.einladung_service', level='WARNING') as log:
            pdf = einladung_service.rendere_einladung(ev)
        self.assertIn('ohne Anschreiben', log.output[0])
        seiten = seitentexte(pdf)
        text = '\n'.join(seiten)
        self.assertIn('Hausverwaltung', text)
        self.assertIn(MARKER_ALTE_EINLADUNG, seiten[0])
        self.assertNotIn(MARKER_ANSCHREIBEN, text)
        self.assertNotIn('Vertretungsvollmacht', text)


class NichtErzeugbarTest(AnschreibenTestBasis):

    def test_weg_ohne_zahlungsverkehrskonto_ist_nicht_erzeugbar(self):
        Bankkonto.objects.filter(objekt=self.objekt).update(zahlungsverkehr=False)
        with self.assertRaises(ValidationError) as ctx:
            einladung_service.rendere_einladung(self.ev)
        self.assertIn('Anschreiben nicht erzeugbar', str(ctx.exception))
        self.assertIn('Fußzeilen-Bankkonto', str(ctx.exception))

    def test_person_ohne_anschrift_in_den_einzelfeldern_ist_nicht_erzeugbar(self):
        Person.objects.filter(pk=self.person.pk).update(
            strasse='', hausnummer='', plz='', ort='', adresse='Nur Legacy 1\n12345 Stadt',
        )
        self.teilnehmer.refresh_from_db()
        with self.assertRaises(ValidationError) as ctx:
            einladung_service.rendere_einladung(self.ev, empfaenger=self.teilnehmer)
        self.assertIn('keine Anschrift', str(ctx.exception))


class EPostWegTest(AnschreibenTestBasis):
    """Der Postversand schreibt je Eigentümer den vollständigen personalisierten Stapel."""

    def test_epost_pdf_hat_anschreiben_vollmacht_und_einladung(self):
        einladung_service.erzeuge_einladungs_pdf(self.ev, self.user)
        einladung_service.versende_einladungen(self.ev, self.user)
        protokoll = EVVersandprotokoll.objects.get(ev=self.ev, person=self.person)
        self.assertEqual((protokoll.kanal, protokoll.status), ('epost', 'erfolgreich'))
        seiten = seitentexte(Path(protokoll.epost_pfad).read_bytes())
        self.assertIn('Sehr geehrte Frau Dr. Mustermann,', seiten[0])
        i_vollmacht = erste_seite_mit(seiten, 'Vertretungsvollmacht')
        i_einladung = erste_seite_mit(seiten, MARKER_ALTE_EINLADUNG)
        self.assertLess(i_vollmacht, i_einladung)
        self.assertIn('Einheit 012', seiten[i_vollmacht])

    def test_epost_ohne_einzelfeld_anschrift_wird_protokolliert_statt_leer_gedruckt(self):
        einladung_service.erzeuge_einladungs_pdf(self.ev, self.user)
        Person.objects.filter(pk=self.person.pk).update(
            strasse='', hausnummer='', plz='', ort='', adresse='Nur Legacy 1\n12345 Stadt',
        )
        einladung_service.versende_einladungen(self.ev, self.user)
        protokoll = EVVersandprotokoll.objects.get(ev=self.ev, person=self.person)
        self.assertEqual((protokoll.kanal, protokoll.status), ('epost', 'fehlgeschlagen'))
        self.assertIn('Anschrift', protokoll.fehlertext)
