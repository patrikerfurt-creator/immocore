"""
Tests für ``apps.versammlung.services.einladung_service`` (Spec v1.1 Kap. 7–8).

Deckt ab:
  - pruefe_ladungsfrist: eingehalten / unterschritten / ohne Termin
  - erzeuge_einladungs_pdf: Vorbedingungen, DMS-Ablage (Owner-Regel B-Hybrid),
    Ereignis, Neuerzeugung ersetzt die Verknüpfung ohne das alte Dokument zu löschen
  - Anlagen: Nicht-PDF wird abgelehnt, unbekannte ID wird abgelehnt
  - versandplan: E-Mail aus emails-JSON und Legacy-Feld, EPost ohne E-Mail,
    Portal nie vorgeschlagen, Hinweis bei fehlender Anschrift
  - versende_einladungen: Mailversand, EPost-Ordner samt CSV, Protokollzeilen,
    Statuswechsel, nicht konfiguriertes Mailbackend, Plan-Override
"""
import shutil
import sys
import tempfile
import types
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.dokumente.models import Dokument
from apps.versammlung.models import EVVersandprotokoll
from apps.versammlung.services import (
    einladung_service, ev_service, stimmkraft_service, tagesordnung_service,
)
from apps.versammlung.tests import factories as f

_MEDIA_TMP = tempfile.mkdtemp(prefix='immocore_test_media_ev_einladung_')


def tearDownModule():
    shutil.rmtree(_MEDIA_TMP, ignore_errors=True)


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class LadungsfristTest(TestCase):
    def setUp(self):
        self.user = f.user()
        self.ev = ev_service.erstelle_ev(objekt=f.objekt(), erstellt_von=self.user)

    def test_ohne_termin(self):
        ergebnis = einladung_service.pruefe_ladungsfrist(self.ev)
        self.assertFalse(ergebnis['eingehalten'])
        self.assertIn('Kein Termin', ergebnis['warnung'])

    def test_frist_eingehalten(self):
        ev_service.aktualisiere_terminierung(
            self.ev, self.user, termin=timezone.now() + timedelta(days=30), ort='Saal',
        )
        ergebnis = einladung_service.pruefe_ladungsfrist(self.ev)
        self.assertTrue(ergebnis['eingehalten'])
        self.assertEqual(ergebnis['warnung'], '')

    def test_frist_unterschritten_warnt_ohne_zu_sperren(self):
        ev_service.aktualisiere_terminierung(
            self.ev, self.user, termin=timezone.now() + timedelta(days=5), ort='Saal',
        )
        ergebnis = einladung_service.pruefe_ladungsfrist(self.ev)
        self.assertFalse(ergebnis['eingehalten'])
        self.assertIn('§ 24 Abs. 4 WEG', ergebnis['warnung'])
        self.assertIn('anfechtbar', ergebnis['warnung'])


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class EinladungsPdfTest(TestCase):
    def setUp(self):
        self.user = f.user()
        self.objekt = f.objekt()
        self.ev = ev_service.erstelle_ev(objekt=self.objekt, erstellt_von=self.user)

    def _vorbereiten(self):
        ev_service.aktualisiere_terminierung(
            self.ev, self.user,
            termin=timezone.now() + timedelta(days=30),
            ort='Gemeinschaftsraum',
        )
        tagesordnung_service.top_anlegen(
            ev=self.ev, titel='Jahresabrechnung', erstellt_von=self.user,
            beschlussvorlage='Die Jahresabrechnung wird beschlossen.',
        )
        tagesordnung_service.top_anlegen(
            ev=self.ev, titel='Sanierung Dach', erstellt_von=self.user,
            beschlussvorlage='Das Dach wird saniert.',
            abstimmungsmodus='qualifizierte_mehrheit', mehrheit_schwelle='66.67',
        )

    def test_ohne_termin_kein_pdf(self):
        tagesordnung_service.top_anlegen(
            ev=self.ev, titel='TOP', erstellt_von=self.user, beschlussvorlage='Text.',
        )
        with self.assertRaises(ValidationError) as ctx:
            einladung_service.erzeuge_einladungs_pdf(self.ev, self.user)
        self.assertIn('Termin und Ort', str(ctx.exception))

    def test_ohne_tagesordnung_kein_pdf(self):
        ev_service.aktualisiere_terminierung(
            self.ev, self.user, termin=timezone.now() + timedelta(days=30), ort='Saal',
        )
        with self.assertRaises(ValidationError) as ctx:
            einladung_service.erzeuge_einladungs_pdf(self.ev, self.user)
        self.assertIn('Tagesordnung', str(ctx.exception))

    def test_pdf_wird_am_objekt_abgelegt(self):
        self._vorbereiten()
        dokument = einladung_service.erzeuge_einladungs_pdf(self.ev, self.user)

        self.assertEqual(dokument.objekt_id, self.objekt.id)
        # Owner-Regel B-Hybrid: genau ein Kontext-FK.
        self.assertIsNone(dokument.einheit_id)
        self.assertIsNone(dokument.person_id)
        self.assertIsNone(dokument.vorgang_id)
        self.assertEqual(dokument.kategorie, 'EV-Einladung')
        self.assertEqual(dokument.dokument_typ, 'korrespondenz')
        self.assertTrue(dokument.dateiname.endswith('.pdf'))

        self.ev.refresh_from_db()
        self.assertEqual(self.ev.einladungs_pdf_id, dokument.id)

    def test_pdf_ist_ein_pdf(self):
        self._vorbereiten()
        dokument = einladung_service.erzeuge_einladungs_pdf(self.ev, self.user)
        dokument.datei.open('rb')
        try:
            self.assertTrue(dokument.datei.read(5).startswith(b'%PDF'))
        finally:
            dokument.datei.close()

    def test_erzeugung_wird_protokolliert(self):
        self._vorbereiten()
        einladung_service.erzeuge_einladungs_pdf(self.ev, self.user)
        ereignis = self.ev.ereignisse.get(typ='einladung_erzeugt')
        self.assertIn('2 TOP', ereignis.text)

    def test_neuerzeugung_behaelt_das_alte_dokument(self):
        self._vorbereiten()
        erstes = einladung_service.erzeuge_einladungs_pdf(self.ev, self.user)
        zweites = einladung_service.erzeuge_einladungs_pdf(self.ev, self.user)

        self.assertNotEqual(erstes.id, zweites.id)
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.einladungs_pdf_id, zweites.id)
        # GoBD: die erste Fassung bleibt im DMS.
        self.assertTrue(Dokument.objects.filter(pk=erstes.pk).exists())

    def test_nicht_pdf_anlage_wird_abgelehnt(self):
        self._vorbereiten()
        anlage = Dokument.objects.create(
            datei=ContentFile(b'Text', name='notiz.txt'), dateiname='notiz.txt',
            kategorie='Sonstiges', objekt=self.objekt, hochgeladen_von=self.user,
        )
        with self.assertRaises(ValidationError) as ctx:
            einladung_service.erzeuge_einladungs_pdf(
                self.ev, self.user, anlagen_ids=[str(anlage.id)],
            )
        self.assertIn('notiz.txt', str(ctx.exception))
        self.ev.refresh_from_db()
        self.assertIsNone(self.ev.einladungs_pdf_id)

    def test_unbekannte_anlage_wird_abgelehnt(self):
        self._vorbereiten()
        with self.assertRaises(ValidationError) as ctx:
            einladung_service.erzeuge_einladungs_pdf(
                self.ev, self.user,
                anlagen_ids=['11111111-1111-1111-1111-111111111111'],
            )
        self.assertIn('nicht gefunden', str(ctx.exception))

    def test_pdf_anlage_wird_angehaengt(self):
        self._vorbereiten()
        # Als Anlage dient ein zuvor erzeugtes Einladungs-PDF — ein garantiert
        # gültiges PDF, ohne Testfixture-Datei im Repo.
        anlage = einladung_service.erzeuge_einladungs_pdf(self.ev, self.user)
        try:
            dokument = einladung_service.erzeuge_einladungs_pdf(
                self.ev, self.user, anlagen_ids=[str(anlage.id)],
            )
        except ValidationError as fehler:
            # Ohne PyMuPDF im Image ist der Abbruch das gewünschte Verhalten.
            self.assertIn('PyMuPDF', str(fehler))
            return
        self.assertGreater(dokument.datei.size, anlage.datei.size)


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class VersandplanTest(TestCase):
    def setUp(self):
        self.user = f.user()
        self.objekt = f.objekt()
        self.ev = ev_service.erstelle_ev(objekt=self.objekt, erstellt_von=self.user)

    def _teilnehmer(self, person):
        f.eigentuemer(self.objekt, person)
        stimmkraft_service.ermittle_teilnehmer(self.ev, self.user)

    def test_email_aus_json_feld(self):
        person = f.person(nachname='Jsonmail')
        person.emails = ['neu@example.org']
        person.save(update_fields=['emails'])
        self._teilnehmer(person)

        eintrag = einladung_service.versandplan(self.ev)['eintraege'][0]
        self.assertEqual(eintrag['kanal'], 'email')
        self.assertEqual(eintrag['empfaenger'], 'neu@example.org')

    def test_email_aus_dict_eintrag(self):
        person = f.person(nachname='Dictmail')
        person.emails = [{'adresse': 'dict@example.org', 'typ': 'privat'}]
        person.save(update_fields=['emails'])
        self._teilnehmer(person)

        eintrag = einladung_service.versandplan(self.ev)['eintraege'][0]
        self.assertEqual(eintrag['empfaenger'], 'dict@example.org')

    def test_email_aus_legacy_feld(self):
        person = f.person(nachname='Legacy')
        person.email = 'legacy@example.org'
        person.save(update_fields=['email'])
        self._teilnehmer(person)

        eintrag = einladung_service.versandplan(self.ev)['eintraege'][0]
        self.assertEqual(eintrag['kanal'], 'email')
        self.assertEqual(eintrag['empfaenger'], 'legacy@example.org')

    def test_ohne_email_wird_epost(self):
        person = f.person(nachname='Papier')
        person.adresse = 'Musterweg 1\n12345 Teststadt'
        person.save(update_fields=['adresse'])
        self._teilnehmer(person)

        eintrag = einladung_service.versandplan(self.ev)['eintraege'][0]
        self.assertEqual(eintrag['kanal'], 'epost')
        self.assertIn('Musterweg 1', eintrag['empfaenger'])

    def test_ohne_email_und_ohne_anschrift_mit_hinweis(self):
        self._teilnehmer(f.person(nachname='Unerreichbar'))
        eintrag = einladung_service.versandplan(self.ev)['eintraege'][0]
        self.assertEqual(eintrag['kanal'], 'epost')
        self.assertIn('nicht zugestellt', eintrag['hinweis'])

    def test_portal_wird_nie_vorgeschlagen(self):
        person = f.person(nachname='Portalnutzer')
        person.emails = ['portal@example.org']
        person.save(update_fields=['emails'])
        self._teilnehmer(person)

        plan = einladung_service.versandplan(self.ev)
        self.assertEqual(plan['zusammenfassung']['portal'], 0)
        self.assertFalse(plan['portal_verfuegbar'])
        self.assertIn('Eigentümer-Portal', plan['portal_hinweis'])

    def test_zusammenfassung_zaehlt_kanaele(self):
        mit_mail = f.person(nachname='Mailer')
        mit_mail.emails = ['a@example.org']
        mit_mail.save(update_fields=['emails'])
        ohne_mail = f.person(nachname='Poster')
        ohne_mail.adresse = 'Weg 2\n12345 Stadt'
        ohne_mail.save(update_fields=['adresse'])
        f.eigentuemer(self.objekt, mit_mail)
        f.eigentuemer(self.objekt, ohne_mail)
        stimmkraft_service.ermittle_teilnehmer(self.ev, self.user)

        plan = einladung_service.versandplan(self.ev)
        self.assertEqual(plan['anzahl'], 2)
        self.assertEqual(plan['zusammenfassung']['email'], 1)
        self.assertEqual(plan['zusammenfassung']['epost'], 1)


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class VersandTest(TestCase):
    def setUp(self):
        self.user = f.user()
        self.objekt = f.objekt()
        self.ev = ev_service.erstelle_ev(objekt=self.objekt, erstellt_von=self.user)
        ev_service.aktualisiere_terminierung(
            self.ev, self.user,
            termin=timezone.now() + timedelta(days=30), ort='Gemeinschaftsraum',
        )
        tagesordnung_service.top_anlegen(
            ev=self.ev, titel='Jahresabrechnung', erstellt_von=self.user,
            beschlussvorlage='Die Jahresabrechnung wird beschlossen.',
        )

        self.mailer = f.person(nachname='Mailempfaenger')
        self.mailer.emails = ['mail@example.org']
        self.mailer.save(update_fields=['emails'])
        self.poster = f.person(nachname='Postempfaenger')
        self.poster.adresse = 'Musterweg 1\n12345 Teststadt'
        self.poster.save(update_fields=['adresse'])
        f.eigentuemer(self.objekt, self.mailer, nr='001')
        f.eigentuemer(self.objekt, self.poster, nr='002')
        stimmkraft_service.ermittle_teilnehmer(self.ev, self.user)
        mail.outbox = []

    def _pdf(self):
        return einladung_service.erzeuge_einladungs_pdf(self.ev, self.user)

    def test_ohne_pdf_kein_versand(self):
        with self.assertRaises(ValidationError) as ctx:
            einladung_service.versende_einladungen(self.ev, self.user)
        self.assertIn('Einladungs-PDF', str(ctx.exception))

    def test_versand_ueber_beide_kanaele(self):
        self._pdf()
        ergebnis = einladung_service.versende_einladungen(self.ev, self.user)

        self.assertEqual(ergebnis['gesamt'], 2)
        self.assertEqual(ergebnis['erfolgreich'], 2)
        self.assertEqual(ergebnis['kanaele']['email'], 1)
        self.assertEqual(ergebnis['kanaele']['epost'], 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['mail@example.org'])
        self.assertEqual(len(mail.outbox[0].attachments), 1)
        self.assertTrue(mail.outbox[0].attachments[0][0].endswith('.pdf'))

    def test_epost_ordner_enthaelt_pdf_und_csv(self):
        self._pdf()
        ergebnis = einladung_service.versende_einladungen(self.ev, self.user)

        ordner = einladung_service.epost_verzeichnis(self.ev)
        self.assertEqual(ergebnis['epost_ordner'], str(ordner))
        self.assertTrue(ordner.is_dir())
        pdfs = sorted(p.name for p in ordner.glob('*.pdf'))
        self.assertEqual(len(pdfs), 1)
        self.assertIn('postempfaenger', pdfs[0].lower())

        csv_datei = ordner / 'versand.csv'
        self.assertTrue(csv_datei.exists())
        inhalt = csv_datei.read_text(encoding='utf-8-sig')
        self.assertIn('Name;Anschrift;Einheiten;PDF-Datei', inhalt)
        self.assertIn('Musterweg 1', inhalt)
        self.assertIn('002', inhalt)

    def test_protokollzeilen_je_person(self):
        self._pdf()
        einladung_service.versende_einladungen(self.ev, self.user)

        protokolle = {p.person_id: p for p in EVVersandprotokoll.objects.filter(ev=self.ev)}
        self.assertEqual(len(protokolle), 2)
        self.assertEqual(protokolle[self.mailer.id].kanal, 'email')
        self.assertEqual(protokolle[self.mailer.id].status, 'erfolgreich')
        self.assertEqual(protokolle[self.poster.id].kanal, 'epost')
        self.assertTrue(protokolle[self.poster.id].epost_pfad.endswith('.pdf'))

    def test_status_wechselt_auf_einladungen_versendet(self):
        self._pdf()
        einladung_service.versende_einladungen(self.ev, self.user)
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.status, 'einladungen_versendet')
        self.assertIsNotNone(self.ev.einladung_versendet_am)

    def test_plan_override_erzwingt_epost(self):
        self._pdf()
        plan = einladung_service.versandplan(self.ev)
        mailer_eintrag = next(
            e for e in plan['eintraege'] if e['person_id'] == str(self.mailer.id)
        )
        # Der Eigentümer hat eine Mailadresse, soll aber Post bekommen.
        self.mailer.adresse = 'Postweg 9\n12345 Teststadt'
        self.mailer.save(update_fields=['adresse'])

        ergebnis = einladung_service.versende_einladungen(
            self.ev, self.user, plan={mailer_eintrag['teilnehmer_id']: 'epost'},
        )
        self.assertEqual(ergebnis['kanaele']['epost'], 2)
        self.assertEqual(ergebnis['kanaele']['email'], 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_unbekannter_kanal_wird_abgelehnt(self):
        self._pdf()
        with self.assertRaises(ValidationError) as ctx:
            einladung_service.versende_einladungen(
                self.ev, self.user, plan={'irgendeine-id': 'brieftaube'},
            )
        self.assertIn('brieftaube', str(ctx.exception))

    def test_portal_kanal_wird_uebersprungen(self):
        self._pdf()
        plan = einladung_service.versandplan(self.ev)
        eintrag = next(
            e for e in plan['eintraege'] if e['person_id'] == str(self.mailer.id)
        )
        ergebnis = einladung_service.versende_einladungen(
            self.ev, self.user, plan={eintrag['teilnehmer_id']: 'portal'},
        )
        self.assertEqual(ergebnis['uebersprungen'], 1)
        protokoll = EVVersandprotokoll.objects.get(ev=self.ev, person=self.mailer)
        self.assertEqual(protokoll.status, 'uebersprungen')
        self.assertIn('Portal', protokoll.fehlertext)

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend',
        MEDIA_ROOT=_MEDIA_TMP,
    )
    def test_konsolen_backend_gilt_als_fehlgeschlagen(self):
        self._pdf()
        ergebnis = einladung_service.versende_einladungen(self.ev, self.user)

        self.assertEqual(ergebnis['fehlgeschlagen'], 1)
        protokoll = EVVersandprotokoll.objects.get(
            ev=self.ev, person=self.mailer, kanal='email',
        )
        self.assertEqual(protokoll.status, 'fehlgeschlagen')
        self.assertIn('nicht konfiguriert', protokoll.fehlertext)
        # Der EPost-Empfänger ist erfolgreich — der Status wechselt trotzdem.
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.status, 'einladungen_versendet')

    def test_fehler_werden_als_ereignis_vermerkt(self):
        self._pdf()
        plan = einladung_service.versandplan(self.ev)
        eintrag = next(
            e for e in plan['eintraege'] if e['person_id'] == str(self.mailer.id)
        )
        einladung_service.versende_einladungen(
            self.ev, self.user, plan={eintrag['teilnehmer_id']: 'portal'},
        )
        self.assertTrue(self.ev.ereignisse.filter(typ='versand_fehler').exists())

    def test_ohne_erfolg_kein_statuswechsel(self):
        self._pdf()
        plan = einladung_service.versandplan(self.ev)
        alle_portal = {e['teilnehmer_id']: 'portal' for e in plan['eintraege']}
        ergebnis = einladung_service.versende_einladungen(
            self.ev, self.user, plan=alle_portal,
        )
        self.assertEqual(ergebnis['erfolgreich'], 0)
        self.ev.refresh_from_db()
        self.assertNotEqual(self.ev.status, 'einladungen_versendet')

    def test_wiederholversand_erzeugt_zweite_protokollzeile(self):
        self._pdf()
        einladung_service.versende_einladungen(self.ev, self.user)
        einladung_service.versende_einladungen(self.ev, self.user)
        self.assertEqual(
            EVVersandprotokoll.objects.filter(ev=self.ev, person=self.mailer).count(), 2,
        )


class PyMuPdfLadenTest(TestCase):
    """Ladepfad für PyMuPDF (Prod-Prüfung 2026-08-20).

    Der Alias ``fitz`` ist seit PyMuPDF 1.24 deprecated; ``requirements.txt``
    pinnt nur ``>=1.24``. Fällt der Alias in einer künftigen Version weg, darf
    das nicht als "nicht installiert" gemeldet werden.
    """

    def test_bevorzugt_aktuellen_modulnamen(self):
        self.assertEqual(einladung_service._pymupdf().__name__, 'pymupdf')

    def test_faellt_auf_fitz_zurueck(self):
        # ``fitz`` ist bei aktuellem PyMuPDF selbst nur ein Shim, der intern
        # ``pymupdf`` importiert — ein blockierter pymupdf-Import würde also
        # auch den Fallback treffen. Deshalb liegt hier eine Attrappe in
        # sys.modules, die ``import fitz`` ohne echten Ladevorgang findet.
        attrappe = types.ModuleType('fitz')
        echtes_import = __import__

        def ohne_pymupdf(name, *args, **kwargs):
            if name == 'pymupdf':
                raise ImportError('simuliert: altes PyMuPDF ohne Modulnamen pymupdf')
            return echtes_import(name, *args, **kwargs)

        with patch.dict(sys.modules, {'fitz': attrappe}):
            with patch('builtins.__import__', side_effect=ohne_pymupdf):
                modul = einladung_service._pymupdf()
        self.assertIs(modul, attrappe)

    def test_klare_meldung_wenn_gar_nicht_installiert(self):
        echtes_import = __import__

        def ohne_pymupdf(name, *args, **kwargs):
            if name in ('pymupdf', 'fitz'):
                raise ImportError(f'simuliert: {name} fehlt')
            return echtes_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=ohne_pymupdf):
            with self.assertRaises(ValidationError) as ctx:
                einladung_service._pymupdf()
        self.assertIn('PyMuPDF', str(ctx.exception))
        self.assertIn('nicht installiert', str(ctx.exception))
