"""
Tests für die Mail-Vorschau.

Schwerpunkt ist die Absicherung: Der Mailinhalt stammt von aussen. Würde er
ungefiltert ausgeliefert, könnte eine präparierte Mail Skripte im Kontext
der Anwendung ausführen und die Sitzung des Mitarbeiters übernehmen. Deshalb
prüfen mehrere Tests gezielt, dass Markup aus Betreff, Absendername und Text
als sichtbarer Text ankommt und nicht als HTML.
"""
import shutil
import tempfile
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.objekte.models import Objekt
from apps.vorgaenge.models import VorgangTyp
from apps.vorgaenge.services import mail_import_service as mis
from apps.vorgaenge.services import mail_vorschau_service

from apps.vorgaenge.tests.test_mail_import_service import ki_antwort, schreibe_eml

User = get_user_model()

_MEDIA_TMP = tempfile.mkdtemp(prefix="immocore_test_media_vorschau_")


def tearDownModule():
    shutil.rmtree(_MEDIA_TMP, ignore_errors=True)


class BaueVorschauTest(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='immocore_test_vorschau_')
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_kopf_und_text_erscheinen(self):
        pfad = schreibe_eml(
            self.tmp, 'a.eml', von='melder@example.org', von_name='Jörg Müller',
            betreff='Heizkörper kalt', text='Die Küche bleibt kalt.\nGrüße')

        seite = mail_vorschau_service.baue_vorschau(pfad, 'a.eml')

        self.assertIn('Heizkörper kalt', seite)
        self.assertIn('Jörg Müller', seite)
        self.assertIn('melder@example.org', seite)
        self.assertIn('Die Küche bleibt kalt.', seite)
        self.assertIn('a.eml', seite)

    def test_skript_im_text_wird_escaped(self):
        pfad = schreibe_eml(
            self.tmp, 'xss.eml',
            text='Hallo <script>alert("uebernommen")</script> Ende')

        seite = mail_vorschau_service.baue_vorschau(pfad)

        # Entscheidend: kein ausführbares Tag im Ergebnis.
        self.assertNotIn('<script>', seite)
        self.assertIn('&lt;script&gt;', seite)

    def test_skript_im_betreff_wird_escaped(self):
        pfad = schreibe_eml(
            self.tmp, 'xss2.eml',
            betreff='Rechnung <img src=x onerror=alert(1)>')

        seite = mail_vorschau_service.baue_vorschau(pfad)

        self.assertNotIn('<img src=x', seite)
        self.assertIn('&lt;img', seite)

    def test_skript_im_absendernamen_wird_escaped(self):
        pfad = schreibe_eml(
            self.tmp, 'xss3.eml', von='b@example.org',
            von_name='<script>alert(1)</script>')

        seite = mail_vorschau_service.baue_vorschau(pfad)
        self.assertNotIn('<script>alert(1)</script>', seite)

    def test_html_mail_wird_als_text_dargestellt(self):
        pfad = schreibe_eml(
            self.tmp, 'html.eml',
            html='<html><body><p>Das Tor <b>klemmt</b>.</p>'
                 '<script>alert(1)</script></body></html>')

        seite = mail_vorschau_service.baue_vorschau(pfad)

        self.assertIn('klemmt', seite)
        # Weder das Markup der Mail noch ihr Skript landen im Ergebnis.
        self.assertNotIn('<b>klemmt</b>', seite)
        self.assertNotIn('alert(1)', seite)

    def test_kompakt_laesst_den_kopf_weg(self):
        # Fuer die Einbettung im Posteingang: Betreff und Absender stehen
        # dort schon ueber der Vorschau, doppelt waere nur Ballast.
        pfad = schreibe_eml(self.tmp, 'k.eml', betreff='Heizung kalt',
                            text='Der Heizkoerper bleibt kalt.')

        voll = mail_vorschau_service.baue_vorschau(pfad, 'k.eml')
        kompakt = mail_vorschau_service.baue_vorschau(pfad, 'k.eml', kompakt=True)

        self.assertIn('<h1>', voll)
        self.assertIn('class="kopf"', voll)
        self.assertNotIn('<h1>', kompakt)
        self.assertNotIn('class="kopf"', kompakt)
        # Der Mailtext bleibt in beiden Varianten vollstaendig erhalten.
        self.assertIn('Der Heizkoerper bleibt kalt.', kompakt)

    def test_anhaenge_werden_aufgefuehrt(self):
        pfad = schreibe_eml(
            self.tmp, 'anh.eml',
            anhaenge=[('beleg.pdf', b'%PDF-1.4 x', 'application', 'pdf'),
                      ('logo.png', b'\x89PNG' + b'x' * 100, 'image', 'png')])

        seite = mail_vorschau_service.baue_vorschau(pfad)

        self.assertIn('beleg.pdf', seite)
        self.assertIn('Anhänge (2)', seite)
        # Die kleine Grafik wurde nicht übernommen und wird als Rest gezählt.
        self.assertIn('1 weitere(r) Anhang', seite)

    def test_ist_mail_dokument_erkennt_nur_mails(self):
        class Fake:
            def __init__(self, name):
                self.dateiname = name

        self.assertTrue(mail_vorschau_service.ist_mail_dokument(Fake('a.eml')))
        self.assertTrue(mail_vorschau_service.ist_mail_dokument(Fake('B.MSG')))
        self.assertFalse(mail_vorschau_service.ist_mail_dokument(Fake('beleg.pdf')))


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class MailVorschauApiTest(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='immocore_test_vorschau_api_')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.user = User.objects.create_user(username='vorschau-tester', password='x')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

        objekt = Objekt.objects.create(
            bezeichnung='Test-WEG Vorschau', objektnummer='VS900', objekt_typ='weg',
            ort='Teststadt', verwaltung_seit=date(2020, 1, 1))
        from apps.vorgaenge.models import Vorgang
        self.vorgang = Vorgang.objects.create(
            typ=VorgangTyp.objects.get(code='maengelmeldung'),
            betreff='Vorschau-Test', objekt=objekt, erstellt_von=self.user)

    def _dokumente_der_mail(self, dateiname='post.eml', **kwargs):
        from apps.vorgaenge.services import dokument_service
        pfad = schreibe_eml(self.tmp, dateiname, **kwargs)
        ergebnis = dokument_service.lade_dokument_hoch(
            pfad.read_bytes(), dateiname, self.user, vorgang=self.vorgang,
            kategorie=mis.KATEGORIE_MAIL, dokument_typ='korrespondenz')
        return ergebnis.dokument

    def test_vorschau_liefert_html_mit_schutzheadern(self):
        dokument = self._dokumente_der_mail(betreff='Heizung kalt')

        antwort = self.client.get(f'/api/v1/dokumente/{dokument.id}/mail-vorschau/')

        self.assertEqual(antwort.status_code, 200)
        self.assertIn('text/html', antwort['Content-Type'])
        self.assertIn("script-src 'none'", antwort['Content-Security-Policy'])
        self.assertEqual(antwort['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(antwort['Cache-Control'], 'no-store')
        self.assertIn('Heizung kalt', antwort.content.decode('utf-8'))

    def test_vorschau_fuer_nicht_mail_wird_abgelehnt(self):
        from apps.vorgaenge.services import dokument_service
        ergebnis = dokument_service.lade_dokument_hoch(
            b'%PDF-1.4 x', 'beleg.pdf', self.user, vorgang=self.vorgang,
            kategorie='E-Mail Anhang')

        antwort = self.client.get(
            f'/api/v1/dokumente/{ergebnis.dokument.id}/mail-vorschau/')
        self.assertEqual(antwort.status_code, 400)

    def test_defekte_datei_liefert_klare_meldung_statt_fehler(self):
        from apps.vorgaenge.services import dokument_service
        ergebnis = dokument_service.lade_dokument_hoch(
            b'\x00\x01kaputt', 'kaputt.msg', self.user, vorgang=self.vorgang,
            kategorie=mis.KATEGORIE_MAIL)

        antwort = self.client.get(
            f'/api/v1/dokumente/{ergebnis.dokument.id}/mail-vorschau/')
        self.assertEqual(antwort.status_code, 422)
        self.assertIn('Download', antwort.data['error'])

    def test_ohne_anmeldung_kein_zugriff(self):
        dokument = self._dokumente_der_mail()
        self.client.force_authenticate(None)
        antwort = self.client.get(f'/api/v1/dokumente/{dokument.id}/mail-vorschau/')
        self.assertEqual(antwort.status_code, 401)
