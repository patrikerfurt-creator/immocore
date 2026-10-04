"""Phase 4: Druckstapel - Sammel-PDF (sortiert), Bestätigung "gedruckt und kuvertiert"."""
from unittest import mock

import pymupdf
from django.core.exceptions import ValidationError

from apps.dokumente.models import Dokument
from apps.korrespondenz.models import Druckstapel, Schreiben
from apps.korrespondenz.services import druckstapel_service, schreiben_service
from apps.personen.models import Person

from . import fixtures
from .basis_versand import VersandTestBasis, neue_einheit, neue_person, neues_ev


def seiten(dokument) -> list:
    with dokument.datei.open('rb') as f, pymupdf.open(stream=f.read(), filetype='pdf') as doc:
        return [seite.get_text() for seite in doc]


class DruckstapelBasis(VersandTestBasis):

    def setUp(self):
        self.vorlage('brief', 'eigentuemer_allgemein', kanal_standard='brief')

    def brief(self, person=None, objekt=None, einheit=None, freigeben=True):
        s = schreiben_service.erstellen(
            'brief', person or self.s.person, objekt=objekt or self.s.objekt, einheit=einheit,
            user=self.user)
        self.assertEqual(s.status, 'zur_pruefung', s.fehler)
        return schreiben_service.freigeben(s, self.user) if freigeben else s


class SammelPdfTest(DruckstapelBasis):

    def test_sortiert_nach_objekt_dann_empfaenger(self):
        b = fixtures.szenario(wechsel=False, mahnung=False, vorgang=False)   # spätere Objektnummer
        Person.objects.filter(pk=self.s.person.pk).update(nachname='Zorn')
        Person.objects.filter(pk=b.person.pk).update(nachname='Adam')
        self.assertLess(self.s.objekt.objektnummer, b.objekt.objektnummer)

        # Erstellungsreihenfolge bewusst gegen die Sortierung: Objekt B zuerst.
        s_b = self.brief(b.person, b.objekt)
        s_a1 = self.brief(self.s.person, self.s.objekt)
        anna = neue_person('Anna')
        e2 = neue_einheit(self.s.objekt, '2')
        neues_ev(e2, anna)
        s_a2 = self.brief(anna, self.s.objekt, e2)

        stapel = druckstapel_service.erzeuge(self.user)
        texte = seiten(stapel.dokument)
        self.assertEqual(len(texte), 3)
        # Objekt A vor Objekt B; innerhalb A alphabetisch (Anna vor Zorn); dann Objekt B (Adam)
        self.assertIn('Anna', texte[0])
        self.assertIn('Zorn', texte[1])
        self.assertIn('Adam', texte[2])
        self.assertEqual({s_a1.pk, s_a2.pk, s_b.pk}, set(stapel.schreiben.values_list('pk', flat=True)))

    def test_sortierschluessel_ohne_objekt_kommt_zuletzt(self):
        mit = self.brief()
        ohne = self.brief()
        ohne.objekt = None
        self.assertLess(druckstapel_service.sortierschluessel(mit), druckstapel_service.sortierschluessel(ohne))

    def test_sammel_dokument_ist_druckhilfe_und_nicht_revisionssicher(self):
        s = self.brief()
        stapel = druckstapel_service.erzeuge(self.user)
        dok = stapel.dokument
        self.assertFalse(dok.revisionssicher)
        self.assertEqual(dok.objekt_id, self.s.objekt.id)           # ein gemeinsames Objekt
        self.assertEqual(dok.dokument_typ, 'korrespondenz')
        self.assertEqual(dok.hochgeladen_von, self.user)
        # Das revisionssichere Original je Schreiben bleibt unberührt
        s.refresh_from_db()
        self.assertTrue(s.dokument.revisionssicher)
        self.assertNotEqual(s.dokument_id, dok.id)

    def test_mehrere_objekte_ohne_gemeinsamen_kontext(self):
        b = fixtures.szenario(wechsel=False, mahnung=False, vorgang=False)
        self.brief()
        self.brief(b.person, b.objekt)
        stapel = druckstapel_service.erzeuge(self.user)
        self.assertIsNone(stapel.dokument.objekt_id)

    def test_status_und_zuordnung_nach_erzeugen(self):
        s = self.brief()
        stapel = druckstapel_service.erzeuge(self.user)
        self.assertEqual(stapel.status, 'offen')
        self.assertEqual(stapel.erstellt_von, self.user)
        s.refresh_from_db()
        self.assertEqual(s.druckstapel_id, stapel.id)
        self.assertEqual(s.status, 'freigegeben')                    # noch nicht versendet
        self.assertIsNone(s.versendet_am)


class AuswahlTest(DruckstapelBasis):

    def test_ohne_druckbereite_briefe(self):
        with self.assertRaises(ValidationError):
            druckstapel_service.erzeuge(self.user)
        self.assertEqual(Druckstapel.objects.count(), 0)

    def test_schreiben_in_pruefung_sind_nicht_druckbereit(self):
        self.brief(freigeben=False)
        self.assertEqual(druckstapel_service.druckbereite_schreiben().count(), 0)

    def test_nur_briefe_werden_gebuendelt(self):
        self.vorlage('mail', 'eigentuemer_allgemein', kanal_standard='email')
        person = self.mail_person()
        mail = schreiben_service.freigeben(
            schreiben_service.erstellen('mail', person, objekt=self.s.objekt, user=self.user), self.user)
        self.brief()
        self.assertEqual(druckstapel_service.druckbereite_schreiben().count(), 1)
        with self.assertRaises(ValidationError) as ctx:
            druckstapel_service.erzeuge(self.user, schreiben_ids=[mail.pk])
        self.assertIn('nicht als Brief', str(ctx.exception))

    def test_schreiben_wird_nur_einmal_gestapelt(self):
        s = self.brief()
        druckstapel_service.erzeuge(self.user)
        self.assertEqual(druckstapel_service.druckbereite_schreiben().count(), 0)
        with self.assertRaises(ValidationError):
            druckstapel_service.erzeuge(self.user, schreiben_ids=[s.pk])
        self.assertEqual(Druckstapel.objects.count(), 1)

    def test_explizite_auswahl(self):
        a, b = self.brief(), self.brief()
        stapel = druckstapel_service.erzeuge(self.user, schreiben_ids=[a.pk])
        self.assertEqual(list(stapel.schreiben.all()), [a])
        self.assertEqual(list(druckstapel_service.druckbereite_schreiben()), [b])

    def test_unbekannte_id(self):
        import uuid
        with self.assertRaises(ValidationError):
            druckstapel_service.erzeuge(self.user, schreiben_ids=[uuid.uuid4()])

    def test_filter_auf_objekt(self):
        b = fixtures.szenario(wechsel=False, mahnung=False, vorgang=False)
        self.brief()
        s_b = self.brief(b.person, b.objekt)
        stapel = druckstapel_service.erzeuge(self.user, objekt=b.objekt)
        self.assertEqual(list(stapel.schreiben.all()), [s_b])

    def test_fehler_beim_sammel_pdf_laesst_keinen_halben_stapel_zurueck(self):
        a = self.brief()
        with mock.patch.object(druckstapel_service, 'baue_sammel_pdf', side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                druckstapel_service.erzeuge(self.user)
        self.assertEqual(Druckstapel.objects.count(), 0)
        self.assertEqual(Dokument.objects.filter(titel__startswith='Druckstapel').count(), 0)
        a.refresh_from_db()
        self.assertIsNone(a.druckstapel_id)


class BestaetigenTest(DruckstapelBasis):

    def test_versendet_am_erst_nach_bestaetigung(self):
        a, b = self.brief(), self.brief()
        stapel = druckstapel_service.erzeuge(self.user)
        for s in (a, b):
            s.refresh_from_db()
            self.assertEqual(s.status, 'freigegeben')
            self.assertIsNone(s.versendet_am)

        stapel = schreiben_service.bestaetige_druckstapel(stapel, self.user)
        self.assertEqual(stapel.status, 'bestaetigt')
        self.assertEqual(stapel.bestaetigt_von, self.user)
        self.assertIsNotNone(stapel.bestaetigt_am)
        for s in (a, b):
            s.refresh_from_db()
            self.assertEqual(s.status, 'versendet')
            self.assertIsNotNone(s.versendet_am)
            self.assertEqual(s.fehler, '')

    def test_doppelte_bestaetigung(self):
        self.brief()
        stapel = druckstapel_service.erzeuge(self.user)
        schreiben_service.bestaetige_druckstapel(stapel, self.user)
        with self.assertRaises(ValidationError):
            schreiben_service.bestaetige_druckstapel(stapel, self.user)

    def test_versenden_eines_briefs_setzt_nicht_versendet_am(self):
        s = self.brief()
        erg = schreiben_service.versenden(s, self.user)
        self.assertEqual(erg.ergebnis, 'druckstapel')
        s.refresh_from_db()
        self.assertEqual((s.status, s.kanal), ('freigegeben', 'brief'))
        self.assertIsNone(s.versendet_am)

    def test_versendet_ist_endzustand(self):
        s = self.brief()
        stapel = druckstapel_service.erzeuge(self.user)
        schreiben_service.bestaetige_druckstapel(stapel, self.user)
        s.refresh_from_db()
        for aktion in (schreiben_service.versenden, schreiben_service.verwerfen, schreiben_service.freigeben):
            with self.subTest(aktion=aktion.__name__), self.assertRaises(ValidationError):
                aktion(s, self.user)

    def test_bestaetigung_erzeugt_kein_neues_dokument(self):
        self.brief()
        stapel = druckstapel_service.erzeuge(self.user)
        vorher = Dokument.objects.count()
        schreiben_service.bestaetige_druckstapel(stapel, self.user)
        self.assertEqual(Dokument.objects.count(), vorher)
        self.assertEqual(Schreiben.objects.filter(status='versendet').count(), 1)
