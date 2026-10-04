"""Test 16 (Teil 2): Versand - E-Mail mit PDF-Anhang, Brief -> Druckstapel, "Stufe 3 auch Brief",
ohne SMTP -> ``versand_fehlgeschlagen``."""
from unittest import mock

from django.core import mail
from django.core.exceptions import ValidationError
from django.test import override_settings

from apps.korrespondenz.models import Schreiben
from apps.korrespondenz.services import druckstapel_service, schreiben_service
from apps.objekte.models import Objekt
from apps.personen.models import Person
from apps.vorgaenge.models import Vorgang, VorgangEreignis, VorgangTyp

from .basis_versand import VersandTestBasis, neue_person

KONSOLE = 'django.core.mail.backends.console.EmailBackend'


class VersandTestMixin:
    """Hilfen: freigegebenes Schreiben an einen E-Mail-Empfänger."""

    def freigegeben(self, *, anlass='eigentuemer_allgemein', kanal_standard='email', person=None,
                    begleittext='', vorgang=None, mahnung=None):
        code = f'v_{anlass}_{kanal_standard}'
        self.vorlage(code, anlass, kanal_standard=kanal_standard, begleittext=begleittext)
        schreiben = schreiben_service.erstellen(
            code, person or self.person, objekt=self.s.objekt, vorgang=vorgang, mahnung=mahnung,
            user=self.user,
        )
        return schreiben_service.freigeben(schreiben, self.user)

    def druck_bestaetigen(self):
        stapel = druckstapel_service.erzeuge(self.user)
        return schreiben_service.bestaetige_druckstapel(stapel, self.user)


class EmailVersandTest(VersandTestMixin, VersandTestBasis):

    def setUp(self):
        self.mail_aktiv()
        self.person = self.mail_person()

    def test_email_mit_pdf_anhang(self):
        s = self.freigegeben(begleittext='Guten Tag,\nanbei unser Schreiben.')
        self.assertEqual(s.kanal, 'email')
        erg = schreiben_service.versenden(s, self.user)

        self.assertEqual(erg.ergebnis, 'versendet')
        self.assertEqual(len(mail.outbox), 1)
        nachricht = mail.outbox[0]
        self.assertEqual(nachricht.to, ['mailer@example.org'])
        self.assertEqual(nachricht.subject, 'Information zum Objekt')
        self.assertEqual(nachricht.body, 'Guten Tag,\nanbei unser Schreiben.')
        self.assertEqual(nachricht.from_email, 'info@demme-immobilien.de')
        html, typ = nachricht.alternatives[0]
        self.assertEqual(typ, 'text/html')
        self.assertIn('anbei unser Schreiben', html)
        dateiname, inhalt, mimetyp = nachricht.attachments[0]
        self.assertEqual((dateiname, mimetyp), (f'{s.nummer}.pdf', 'application/pdf'))
        self.assertTrue(inhalt.startswith(b'%PDF'))

        s.refresh_from_db()
        self.assertEqual(s.status, 'versendet')
        self.assertIsNotNone(s.versendet_am)
        self.assertEqual(s.mail_message_id, nachricht.extra_headers['Message-ID'])
        self.assertEqual(s.fehler, '')

    def test_standardtext_ohne_begleittext(self):
        s = self.freigegeben()
        schreiben_service.versenden(s, self.user)
        body = mail.outbox[0].body
        self.assertIn('Sehr geehrte Damen und Herren', body)
        self.assertIn(s.nummer, body)
        self.assertIn('Demme Immobilien Verwaltung GmbH', body)

    def test_mail_wird_nie_doppelt_gesendet(self):
        s = self.freigegeben()
        schreiben_service.versenden(s, self.user)
        with self.assertRaises(ValidationError):
            schreiben_service.versenden(s, self.user)
        self.assertEqual(len(mail.outbox), 1)

    def test_versand_vor_freigabe_nicht_moeglich(self):
        self.vorlage('vv', 'eigentuemer_allgemein', kanal_standard='email')
        s = schreiben_service.erstellen('vv', self.person, objekt=self.s.objekt, user=self.user)
        with self.assertRaises(ValidationError):
            schreiben_service.versenden(s, self.user)
        self.assertEqual(len(mail.outbox), 0)

    def test_kanalwechsel_nur_auf_brief(self):
        s = self.freigegeben()
        with self.assertRaises(ValidationError):
            schreiben_service.versenden(s, self.user, kanal='email')

    def test_ohne_zustimmung_wird_es_ein_brief(self):
        person = neue_person('Ohnezustimmung', email='x@example.org', zustimmung=False)
        s = self.freigegeben(person=person)
        self.assertEqual(s.kanal, 'brief')
        erg = schreiben_service.versenden(s, self.user)
        self.assertEqual(erg.ergebnis, 'druckstapel')
        self.assertEqual(len(mail.outbox), 0)
        s.refresh_from_db()
        self.assertEqual(s.status, 'freigegeben')
        self.assertIsNone(s.versendet_am)              # erst nach Bestätigung "gedruckt und kuvertiert"

    def test_zustimmung_nach_dem_erstellen_widerrufen_ergibt_brief(self):
        s = self.freigegeben()
        Person.objects.filter(pk=self.person.pk).update(zustellweg_zustimmung_am=None)
        erg = schreiben_service.versenden(s, self.user)
        self.assertEqual(erg.ergebnis, 'druckstapel')
        self.assertEqual(len(mail.outbox), 0)
        s.refresh_from_db()
        self.assertEqual(s.kanal, 'brief')

    def test_versendet_erzeugt_vorgangsereignis_extern(self):
        typ, _ = VorgangTyp.objects.get_or_create(code='test', defaults={'bezeichnung': 'Test'})
        vorgang = Vorgang.objects.create(
            typ=typ, objekt=self.s.objekt, person=self.person, betreff='Anfrage',
            erstellt_von=self.s.ersteller)
        s = self.freigegeben(vorgang=vorgang)
        schreiben_service.versenden(s, self.user)
        ereignis = VorgangEreignis.objects.get(vorgang=vorgang, typ='schreiben_versendet')
        self.assertFalse(ereignis.intern)
        self.assertEqual(ereignis.neuer_wert, s.nummer)
        self.assertEqual(ereignis.erstellt_von, self.user)


class OhneSmtpTest(VersandTestMixin, VersandTestBasis):
    """Ohne funktionierenden Mailversand: nichts wird gesendet, Status ``versand_fehlgeschlagen``."""

    def setUp(self):
        self.mail_aktiv()
        self.person = self.mail_person()

    def _pruefe_fehlgeschlagen(self, s, erwartet='nicht konfiguriert'):
        erg = schreiben_service.versenden(s, self.user)
        self.assertEqual(erg.ergebnis, 'fehlgeschlagen')
        self.assertIn(erwartet, erg.hinweis)
        self.assertIn('Brief bleibt möglich', erg.hinweis)
        s.refresh_from_db()
        self.assertEqual(s.status, 'versand_fehlgeschlagen')
        self.assertIn(erwartet, s.fehler)
        self.assertIsNone(s.versendet_am)
        self.assertEqual(s.mail_message_id, '')
        self.assertEqual(len(mail.outbox), 0)
        return s

    @override_settings(EMAIL_BACKEND=KONSOLE)
    def test_konsolen_backend(self):
        self._pruefe_fehlgeschlagen(self.freigegeben())

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend', EMAIL_HOST='')
    def test_smtp_ohne_host(self):
        self._pruefe_fehlgeschlagen(self.freigegeben())

    @override_settings(EMAIL_BACKEND='config.email_backends.GraphEmailBackend',
                       MS_GRAPH_TENANT_ID='', MS_GRAPH_CLIENT_ID='', MS_GRAPH_CLIENT_SECRET='')
    def test_graph_ohne_zugangsdaten(self):
        self._pruefe_fehlgeschlagen(self.freigegeben())

    def test_transportfehler(self):
        s = self.freigegeben()
        with mock.patch('django.core.mail.EmailMultiAlternatives.send', side_effect=OSError('Verbindung')):
            self._pruefe_fehlgeschlagen(s, 'Verbindung')

    def test_objekt_nicht_fuer_mailversand_freigeschaltet(self):
        self.mail_aktiv(aktiv=False)
        s = self.freigegeben()
        self._pruefe_fehlgeschlagen(s, 'mailversand_aktiv')

    def test_schreiben_ohne_objekt_wird_nicht_durch_mailversand_aktiv_blockiert(self):
        """Entscheidung B: die Sperre gilt nur bei gesetztem Objekt (bei gesetztem Objekt s. o.)."""
        self.mail_aktiv(aktiv=False)                    # bliebe für ein Schreiben MIT Objekt gesperrt
        self.vorlage('ohne_objekt', 'eigentuemer_allgemein', kanal_standard='email')
        s = schreiben_service.erstellen('ohne_objekt', self.person, user=self.user)
        self.assertIsNone(s.objekt_id)
        self.assertEqual(s.status, 'zur_pruefung', s.fehler)
        s = schreiben_service.freigeben(s, self.user)

        erg = schreiben_service.versenden(s, self.user)

        self.assertEqual(erg.ergebnis, 'versendet', erg.hinweis)
        s.refresh_from_db()
        self.assertEqual((s.status, s.fehler), ('versendet', ''))
        self.assertTrue(s.mail_message_id)
        self.assertEqual(len(mail.outbox), 1)

    def test_brief_bleibt_moeglich(self):
        with override_settings(EMAIL_BACKEND=KONSOLE):
            s = self._pruefe_fehlgeschlagen(self.freigegeben())
        erg = schreiben_service.versenden(s, self.user, kanal='brief')
        self.assertEqual(erg.ergebnis, 'druckstapel')
        s.refresh_from_db()
        self.assertEqual((s.status, s.kanal, s.fehler), ('freigegeben', 'brief', ''))
        self.assertIn(s, druckstapel_service.druckbereite_schreiben())
        self.druck_bestaetigen()
        s.refresh_from_db()
        self.assertEqual(s.status, 'versendet')
        self.assertIsNotNone(s.versendet_am)

    def test_erneuter_versuch_nach_konfiguration(self):
        with override_settings(EMAIL_BACKEND=KONSOLE):
            s = self._pruefe_fehlgeschlagen(self.freigegeben())
        erg = schreiben_service.versenden(s, self.user)     # locmem = versandfähig
        self.assertEqual(erg.ergebnis, 'versendet')
        self.assertEqual(len(mail.outbox), 1)
        s.refresh_from_db()
        self.assertEqual((s.status, s.fehler), ('versendet', ''))


class MahnstufeDreiVersandTest(VersandTestMixin, VersandTestBasis):
    """Stufe 3 geht immer auch als Brief - die E-Mail allein macht das Schreiben nicht ``versendet``."""

    def setUp(self):
        self.mail_aktiv()
        self.person = self.mail_person()

    def test_stufe_3_mail_und_brief(self):
        s = self.freigegeben(anlass='mahnung_stufe_3')
        self.assertEqual(s.kanal, 'email')
        erg = schreiben_service.versenden(s, self.user)

        self.assertEqual(erg.ergebnis, 'druckstapel')
        self.assertEqual(len(mail.outbox), 1)                  # E-Mail ist raus ...
        s.refresh_from_db()
        self.assertEqual(s.status, 'freigegeben')              # ... aber der Brief fehlt noch
        self.assertIsNone(s.versendet_am)
        self.assertNotEqual(s.mail_message_id, '')
        self.assertIn(s, druckstapel_service.druckbereite_schreiben())

        self.druck_bestaetigen()
        s.refresh_from_db()
        self.assertEqual(s.status, 'versendet')
        self.assertIsNotNone(s.versendet_am)
        self.assertEqual(len(mail.outbox), 1)                  # Bestätigung sendet nichts erneut

    def test_stufe_2_nur_email(self):
        s = self.freigegeben(anlass='mahnung_stufe_2')
        erg = schreiben_service.versenden(s, self.user)
        self.assertEqual(erg.ergebnis, 'versendet')
        self.assertNotIn(s, druckstapel_service.druckbereite_schreiben())

    def test_beides_mail_und_brief(self):
        s = self.freigegeben(kanal_standard='beides')
        erg = schreiben_service.versenden(s, self.user)
        self.assertEqual(erg.ergebnis, 'druckstapel')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(s, druckstapel_service.druckbereite_schreiben())

    def test_stufe_3_ueber_verknuepfte_mahnung(self):
        from apps.korrespondenz.tests import fixtures
        ns = fixtures.szenario(wechsel=False, mahnung=True, vorgang=False)
        ns.mahnung.mahnstufe = 3
        ns.mahnung.save()
        Objekt.objects.filter(pk=ns.objekt.pk).update(mailversand_aktiv=True)
        person = ns.person
        Person.objects.filter(pk=person.pk).update(
            zustellweg='email', zustellweg_zustimmung_am='2026-01-01T00:00:00Z',
            emails=[{'adresse': 'mahn@example.org'}])
        person.refresh_from_db()
        self.vorlage('m2', 'mahnung_stufe_2', kanal_standard='email')
        s = schreiben_service.erstellen(
            'm2', person, objekt=ns.objekt, eigentumsverhaeltnis=ns.ev, mahnung=ns.mahnung,
            user=self.user)
        self.assertEqual(s.status, 'zur_pruefung', s.fehler)
        s = schreiben_service.freigeben(s, self.user)
        self.assertEqual(schreiben_service.versenden(s, self.user).ergebnis, 'druckstapel')
        self.assertEqual(len(mail.outbox), 1)

    def test_stufe_3_mail_fehlgeschlagen_brief_bleibt_pflicht(self):
        with override_settings(EMAIL_BACKEND=KONSOLE):
            s = self.freigegeben(anlass='mahnung_stufe_3')
            erg = schreiben_service.versenden(s, self.user)
        self.assertEqual(erg.ergebnis, 'fehlgeschlagen')
        self.assertIn(Schreiben.objects.get(pk=s.pk), druckstapel_service.druckbereite_schreiben())

        self.druck_bestaetigen()
        s.refresh_from_db()
        self.assertEqual(s.status, 'versand_fehlgeschlagen')   # Brief gedruckt, Mail fehlt noch

        erg = schreiben_service.versenden(s, self.user)         # jetzt versandfähig
        self.assertEqual(erg.ergebnis, 'versendet')
        s.refresh_from_db()
        self.assertEqual(s.status, 'versendet')
        self.assertEqual(len(mail.outbox), 1)
