"""Test 19 + Phase 4: Serienlauf - ein Schreiben je Eigentumsverhältnis, nicht erzeugbare
blockieren nur sich selbst; Empfängerkreis, Vorschau, Freigabe, Verarbeitung."""
from datetime import date
from unittest import mock

from django.core import mail
from django.core.exceptions import ValidationError

from apps.korrespondenz.models import Druckstapel, Schreiben, Serienlauf
from apps.korrespondenz.services import (
    druckstapel_service, postausgang_service, schreiben_service, serienlauf_service,
)

from . import fixtures
from .basis_versand import VersandTestBasis, neue_einheit, neue_person, neues_ev

TEXT_MIT_LAGE = [{'typ': 'text', 'inhalt': 'Ihre Einheit: {{ einheit.lage }}.'}]
TERMIN = [{'name': 'termin', 'label': 'Termin', 'typ': 'text', 'pflicht': True}]


class SerienBasis(VersandTestBasis):
    """Objekt mit fünf aktiven und einem beendeten Eigentumsverhältnis.

    * Mustermann      - Einheit 12 (Wohnung)         [aus dem Szenario]
    * Anna            - Einheiten 2 und 3 (Wohnungen) -> zwei Eigentumsverhältnisse
    * Berta (E-Mail)  - Einheit 4 (Stellplatz)
    * Carl            - Einheit 5 (Wohnung, beendet: kein Empfänger)
    """

    def setUp(self):
        s = self.s
        self.anna = neue_person('Anna')
        self.ev_anna_2 = neues_ev(neue_einheit(s.objekt, '2'), self.anna)
        self.ev_anna_3 = neues_ev(neue_einheit(s.objekt, '3'), self.anna)
        self.berta = self.mail_person('Berta', 'berta@example.org')
        self.ev_berta = neues_ev(neue_einheit(s.objekt, '4', typ='Stellplatz'), self.berta)
        self.ev_carl_alt = neues_ev(
            neue_einheit(s.objekt, '5'), neue_person('Carl'), date(2010, 1, 1), date(2020, 12, 31))
        self.ev_mustermann = s.ev

    def version(self, **kw):
        return self.vorlage(kw.pop('code', 'serie'), kw.pop('anlass', 'eigentuemer_allgemein'), **kw)

    def starte(self, version=None, **kw):
        kw.setdefault('user', self.user)
        return serienlauf_service.starte(version or self.version(), self.s.objekt, **kw)


class EmpfaengerkreisTest(SerienBasis):

    def evs(self, filter_=None):
        return set(serienlauf_service.ermittle_empfaenger(self.s.objekt, filter_))

    def test_alle_aktiven_eigentuemer(self):
        self.assertEqual(self.evs(), {self.ev_mustermann, self.ev_anna_2, self.ev_anna_3, self.ev_berta})

    def test_beendetes_eigentumsverhaeltnis_ist_kein_empfaenger(self):
        self.assertNotIn(self.ev_carl_alt, self.evs())

    def test_filter_einheit_typ(self):
        self.assertEqual(self.evs({'einheit_typ': ['Stellplatz']}), {self.ev_berta})
        self.assertEqual(self.evs({'einheit_typ': 'Stellplatz'}), {self.ev_berta})
        self.assertEqual(
            self.evs({'einheit_typ': ['Wohnung']}), {self.ev_mustermann, self.ev_anna_2, self.ev_anna_3})

    def test_filter_email_zustimmung(self):
        self.assertEqual(self.evs({'email_zustimmung': 'mit'}), {self.ev_berta})
        self.assertEqual(
            self.evs({'email_zustimmung': 'ohne'}), {self.ev_mustermann, self.ev_anna_2, self.ev_anna_3})

    def test_manuelle_abwahl(self):
        self.assertEqual(
            self.evs({'ausschliessen': [str(self.ev_anna_2.pk)]}),
            {self.ev_mustermann, self.ev_anna_3, self.ev_berta})

    def test_manuelle_zuwahl_auch_ausserhalb_der_filter(self):
        self.assertEqual(
            self.evs({'einheit_typ': ['Stellplatz'], 'hinzufuegen': [str(self.ev_carl_alt.pk)]}),
            {self.ev_berta, self.ev_carl_alt})

    def test_abwahl_gewinnt_gegen_zuwahl(self):
        ev = str(self.ev_carl_alt.pk)
        self.assertNotIn(self.ev_carl_alt, self.evs({'hinzufuegen': [ev], 'ausschliessen': [ev]}))

    def test_zuwahl_aus_fremdem_objekt(self):
        fremd = fixtures.szenario(wechsel=False, mahnung=False, vorgang=False)
        with self.assertRaises(ValidationError):
            self.evs({'hinzufuegen': [str(fremd.ev.pk)]})

    def test_ungueltige_filter(self):
        for filter_ in ({'unbekannt': 1}, {'email_zustimmung': 'vielleicht'}, {'ausschliessen': ['x']}):
            with self.subTest(filter=filter_), self.assertRaises(ValidationError):
                self.evs(filter_)


class EinSchreibenJeEigentumsverhaeltnisTest(SerienBasis):
    """Test 19 (Teil 1)."""

    def test_ein_schreiben_je_eigentumsverhaeltnis(self):
        lauf = self.starte(self.version(inhalt=TEXT_MIT_LAGE))
        self.assertEqual(lauf.status, 'zur_pruefung')
        self.assertEqual(lauf.anzahl, 4)
        schreiben = list(lauf.schreiben.all())
        self.assertEqual(len(schreiben), 4)
        self.assertEqual(
            {s.eigentumsverhaeltnis_id for s in schreiben},
            {self.ev_mustermann.pk, self.ev_anna_2.pk, self.ev_anna_3.pk, self.ev_berta.pk})
        self.assertTrue(all(s.status == 'zur_pruefung' for s in schreiben))
        self.assertTrue(all(s.serienlauf_id == lauf.id for s in schreiben))

    def test_mehrere_einheiten_eines_eigentuemers_je_einheit_ein_schreiben(self):
        lauf = self.starte(self.version(inhalt=TEXT_MIT_LAGE))
        annas = lauf.schreiben.filter(empfaenger=self.anna)
        self.assertEqual(annas.count(), 2)
        self.assertEqual({s.einheit.einheit_nr for s in annas}, {'2', '3'})
        self.assertEqual(
            {s.einheit.einheit_nr: 'Wohnung ' + s.einheit.einheit_nr for s in annas},
            {'2': 'Wohnung 2', '3': 'Wohnung 3'})
        for s in annas:                                           # einheitsbezogener Inhalt
            self.assertIn(f'Ihre Einheit: Wohnung {s.einheit.einheit_nr}.', s.html_gerendert)

    def test_jedes_schreiben_hat_eigene_nummer_und_unterzeichner(self):
        lauf = self.starte(self.version(), unterzeichner=self.s.betreuer)
        nummern = list(lauf.schreiben.values_list('nummer', flat=True))
        self.assertEqual(len(set(nummern)), 4)
        self.assertEqual(lauf.unterzeichner, self.s.betreuer)
        self.assertTrue(all(s.unterzeichner == self.s.betreuer for s in lauf.schreiben.all()))

    def test_filter_wirkt_auf_den_lauf(self):
        lauf = self.starte(self.version(), empfaenger_filter={'einheit_typ': ['Stellplatz']})
        self.assertEqual(lauf.anzahl, 1)
        self.assertEqual(lauf.schreiben.get().empfaenger, self.berta)

    def test_leerer_empfaengerkreis_hinterlaesst_keinen_lauf(self):
        with self.assertRaises(ValidationError):
            self.starte(empfaenger_filter={'einheit_typ': ['Gewerbe']})
        self.assertEqual(Serienlauf.objects.count(), 0)
        self.assertEqual(Schreiben.objects.count(), 0)

    def test_vorlage_eines_anderen_objekts(self):
        fremd = fixtures.szenario(wechsel=False, mahnung=False, vorgang=False)
        version = self.version(objekt=fremd.objekt)
        with self.assertRaises(ValidationError):
            self.starte(version)

    def test_nicht_freigegebene_version(self):
        version = self.version()
        version.status = 'entwurf'
        version.save()
        with self.assertRaises(ValidationError):
            self.starte(version)


class NichtErzeugbarBlockiertNurSichSelbstTest(SerienBasis):
    """Test 19 (Teil 2)."""

    def setUp(self):
        super().setUp()
        # Anna hat an Einheit 3 keine Lagebeschreibung -> {{ einheit.lage }} fehlt -> nicht erzeugbar.
        self.ev_anna_3.einheit.__class__.objects.filter(pk=self.ev_anna_3.einheit_id).update(lage='')
        self.lauf = self.starte(self.version(inhalt=TEXT_MIT_LAGE))

    def test_nur_das_betroffene_schreiben_ist_nicht_erzeugbar(self):
        fehlerhaft = self.lauf.schreiben.get(eigentumsverhaeltnis=self.ev_anna_3)
        self.assertEqual(fehlerhaft.status, 'entwurf')
        self.assertIn('einheit.lage', fehlerhaft.fehler)
        self.assertEqual(self.lauf.schreiben.filter(status='zur_pruefung').count(), 3)
        # Annas andere Einheit ist davon unberührt
        self.assertEqual(self.lauf.schreiben.get(eigentumsverhaeltnis=self.ev_anna_2).status, 'zur_pruefung')

    def test_vorschau_listet_nicht_erzeugbare_mit_ursache(self):
        vorschau = serienlauf_service.vorschau(self.lauf)
        self.assertEqual(vorschau.erzeugbar_anzahl, 3)
        self.assertEqual(len(vorschau.zufaellig), 3)
        self.assertEqual([s.eigentumsverhaeltnis_id for s in vorschau.nicht_erzeugbar], [self.ev_anna_3.pk])
        self.assertIn('einheit.lage', vorschau.nicht_erzeugbar[0].fehler)
        self.assertNotIn(vorschau.nicht_erzeugbar[0], vorschau.zufaellig)

    def test_lauf_ist_trotzdem_freigebbar_und_verarbeitet_die_uebrigen(self):
        self.assertEqual(serienlauf_service.freigabe_blocker(self.lauf), [])
        lauf = serienlauf_service.freigeben(self.lauf, self.user)
        self.assertEqual(lauf.status, 'freigegeben')
        lauf = serienlauf_service.verarbeite(lauf, self.user)

        self.assertEqual(lauf.status, 'teilweise_fehler')         # der nicht erzeugbare bleibt offen
        je_status = {}
        for s in lauf.schreiben.all():
            je_status.setdefault(s.status, []).append(s)
        self.assertEqual(len(je_status['entwurf']), 1)
        self.assertEqual(len(je_status['freigegeben']), 3)        # Briefe im Druckstapel
        self.assertTrue(all(s.dokument_id and s.druckstapel_id for s in je_status['freigegeben']))
        self.assertIsNone(je_status['entwurf'][0].dokument_id)    # kein PDF fuer den fehlerhaften

    def test_nicht_erzeugbare_bleiben_im_postausgang_sichtbar(self):
        lauf = serienlauf_service.verarbeite(serienlauf_service.freigeben(self.lauf, self.user), self.user)
        post = postausgang_service.postausgang()
        self.assertEqual([s.eigentumsverhaeltnis_id for s in post], [self.ev_anna_3.pk])
        self.assertEqual(lauf.schreiben.count(), 4)

    def test_alle_nicht_erzeugbar_ist_nicht_freigebbar(self):
        self.lauf.schreiben.filter(status='zur_pruefung').update(status='entwurf', fehler='x')
        blocker = serienlauf_service.freigabe_blocker(self.lauf)
        self.assertIn('Es gibt kein erzeugbares Schreiben.', blocker)
        with self.assertRaises(ValidationError):
            serienlauf_service.freigeben(self.lauf, self.user)


class VorschauTest(SerienBasis):

    def test_drei_zufaellige_empfaenger_stabil_je_lauf(self):
        lauf = self.starte()
        a = [s.pk for s in serienlauf_service.vorschau(lauf).zufaellig]
        b = [s.pk for s in serienlauf_service.vorschau(lauf).zufaellig]
        self.assertEqual(len(a), 3)
        self.assertEqual(a, b)
        self.assertEqual(len(set(a)), 3)

    def test_weniger_als_drei_empfaenger(self):
        lauf = self.starte(empfaenger_filter={'einheit_typ': ['Stellplatz']})
        self.assertEqual(len(serienlauf_service.vorschau(lauf).zufaellig), 1)

    def test_schreiben_im_pruefstatus_stehen_nicht_im_postausgang(self):
        lauf = self.starte()
        self.assertEqual(postausgang_service.postausgang().count(), 0)
        self.assertEqual(postausgang_service.postausgang(serienlauf=lauf).count(), 4)   # gezielt abrufbar


class FreigabeTest(SerienBasis):

    def test_pflicht_eingabefeld_fehlt_lauf_nicht_freigebbar(self):
        version = self.version(
            inhalt=[{'typ': 'text', 'inhalt': 'Termin: {{ eingabe.termin }}'}], eingabefelder=TERMIN)
        lauf = self.starte(version, eingabewerte={'termin': 'Montag'})
        self.assertEqual(serienlauf_service.freigabe_blocker(lauf), [])
        # Werte gehen verloren -> Pflichtfeld fehlt, obwohl Schreiben bereits erzeugt sind
        Serienlauf.objects.filter(pk=lauf.pk).update(eingabewerte={})
        lauf.refresh_from_db()
        blocker = serienlauf_service.freigabe_blocker(lauf)
        self.assertTrue(any('Termin' in b or 'termin' in b for b in blocker), blocker)
        with self.assertRaises(ValidationError):
            serienlauf_service.freigeben(lauf, self.user)
        lauf.refresh_from_db()
        self.assertEqual(lauf.status, 'zur_pruefung')

    def test_ohne_pflichtwert_sind_alle_schreiben_nicht_erzeugbar_und_lauf_gesperrt(self):
        version = self.version(
            inhalt=[{'typ': 'text', 'inhalt': 'Termin: {{ eingabe.termin }}'}], eingabefelder=TERMIN)
        lauf = self.starte(version)
        self.assertEqual(serienlauf_service.vorschau(lauf).erzeugbar_anzahl, 0)
        self.assertEqual(len(serienlauf_service.vorschau(lauf).nicht_erzeugbar), 4)
        with self.assertRaises(ValidationError):
            serienlauf_service.freigeben(lauf, self.user)

    def test_freigabe_setzt_status_und_person(self):
        lauf = serienlauf_service.freigeben(self.starte(), self.user)
        self.assertEqual((lauf.status, lauf.freigegeben_von), ('freigegeben', self.user))
        self.assertIsNotNone(lauf.freigegeben_am)

    def test_erneute_freigabe_ist_idempotent(self):
        lauf = serienlauf_service.freigeben(self.starte(), self.user)
        self.assertEqual(serienlauf_service.freigeben(lauf, self.user).status, 'freigegeben')

    def test_schreiben_erzeugen_nur_einmal(self):
        lauf = self.starte()
        with self.assertRaises(ValidationError):
            serienlauf_service.erzeuge_schreiben(lauf, self.user)
        self.assertEqual(lauf.schreiben.count(), 4)

    def test_verarbeiten_erst_nach_freigabe(self):
        lauf = self.starte()
        with self.assertRaises(ValidationError):
            serienlauf_service.verarbeite(lauf, self.user)


class VerarbeitungTest(SerienBasis):

    def test_mails_raus_und_briefe_in_den_druckstapel(self):
        self.mail_aktiv()
        version = self.version(kanal_standard='email')
        lauf = serienlauf_service.freigeben(self.starte(version), self.user)
        lauf = serienlauf_service.verarbeite(lauf, self.user)

        self.assertEqual(lauf.status, 'versendet')
        # Berta hat E-Mail-Zustimmung -> eine Mail, das Schreiben ist erledigt
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['berta@example.org'])
        berta = lauf.schreiben.get(empfaenger=self.berta)
        self.assertEqual((berta.kanal, berta.status), ('email', 'versendet'))
        # alle anderen erhalten einen Brief -> ein Druckstapel mit Sammel-PDF
        briefe = lauf.schreiben.exclude(empfaenger=self.berta)
        self.assertEqual(briefe.count(), 3)
        self.assertTrue(all(s.kanal == 'brief' and s.status == 'freigegeben' for s in briefe))
        stapel_ids = set(briefe.values_list('druckstapel', flat=True))
        self.assertEqual(len(stapel_ids), 1)
        stapel = Druckstapel.objects.get(pk=stapel_ids.pop())
        self.assertEqual(lauf.druck_dokument_id, stapel.dokument_id)
        self.assertIsNone(berta.druckstapel_id)

        # Bestätigung "gedruckt und kuvertiert" -> alle Briefe versendet
        schreiben_service.bestaetige_druckstapel(stapel, self.user)
        self.assertEqual(lauf.schreiben.filter(status='versendet').count(), 4)

    def test_lauf_ohne_mailversand_meldet_teilweise_fehler_und_briefe_gehen_trotzdem(self):
        version = self.version(kanal_standard='email')            # Objekt ist NICHT freigeschaltet
        lauf = serienlauf_service.verarbeite(
            serienlauf_service.freigeben(self.starte(version), self.user), self.user)
        self.assertEqual(lauf.status, 'teilweise_fehler')
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(lauf.schreiben.get(empfaenger=self.berta).status, 'versand_fehlgeschlagen')
        self.assertIsNotNone(lauf.druck_dokument_id)              # Briefe der anderen sind im Stapel
        # Postausgang zeigt den fehlgeschlagenen Versand
        self.assertEqual([s.empfaenger for s in postausgang_service.postausgang()], [self.berta])

    def test_ein_fehler_bricht_den_lauf_nicht_ab(self):
        lauf = serienlauf_service.freigeben(self.starte(), self.user)
        echt = schreiben_service.freigeben
        def kaputt(schreiben, user):
            if schreiben.eigentumsverhaeltnis_id == self.ev_anna_2.pk:
                raise RuntimeError('boom')
            return echt(schreiben, user)
        with mock.patch.object(schreiben_service, 'freigeben', side_effect=kaputt):
            with self.assertLogs(serienlauf_service.logger, 'ERROR'):
                lauf = serienlauf_service.verarbeite(lauf, self.user)
        self.assertEqual(lauf.status, 'teilweise_fehler')
        self.assertEqual(lauf.schreiben.filter(status='freigegeben').count(), 3)
        self.assertEqual(lauf.schreiben.get(eigentumsverhaeltnis=self.ev_anna_2).status, 'zur_pruefung')

    def test_wiederholung_versendet_nichts_doppelt(self):
        self.mail_aktiv()
        version = self.version(kanal_standard='email')
        lauf = serienlauf_service.freigeben(self.starte(version), self.user)
        # Erster Lauf: Mail-Versand kaputt -> teilweise_fehler
        with mock.patch('django.core.mail.EmailMultiAlternatives.send', side_effect=OSError('down')):
            lauf = serienlauf_service.verarbeite(lauf, self.user)
        self.assertEqual(lauf.status, 'teilweise_fehler')
        self.assertEqual(len(mail.outbox), 0)
        anzahl_dokumente = Schreiben.objects.filter(dokument__isnull=False).count()
        # Zweiter Lauf: Versand geht wieder
        lauf = serienlauf_service.verarbeite(lauf, self.user)
        self.assertEqual(lauf.status, 'versendet')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(Schreiben.objects.filter(dokument__isnull=False).count(), anzahl_dokumente)
        self.assertEqual(Druckstapel.objects.count(), 1)             # der Druckstapel entstand nur einmal

    def test_versendeter_lauf_wird_nicht_erneut_verarbeitet(self):
        lauf = serienlauf_service.verarbeite(
            serienlauf_service.freigeben(self.starte(), self.user), self.user)
        self.assertEqual(lauf.status, 'versendet')
        with self.assertRaises(ValidationError):
            serienlauf_service.verarbeite(lauf, self.user)

    def test_unbekannte_druckbereite_gehoeren_nicht_zum_lauf(self):
        self.vorlage('einzel', 'eigentuemer_allgemein', kanal_standard='brief')
        fremdes = schreiben_service.freigeben(
            schreiben_service.erstellen('einzel', self.anna, objekt=self.s.objekt, user=self.user), self.user)
        lauf = serienlauf_service.verarbeite(
            serienlauf_service.freigeben(self.starte(), self.user), self.user)
        fremdes.refresh_from_db()
        self.assertIsNone(fremdes.druckstapel_id)                   # Einzelbrief bleibt für eigenen Stapel
        self.assertEqual(druckstapel_service.druckbereite_schreiben().get(), fremdes)
        self.assertEqual(lauf.status, 'versendet')
