"""
Tests für ``apps.vorgaenge.services.mail_import_service``.

Deckt ab:
  - Parsing: RFC-2047-Umlaute in Betreff/Absender, HTML-only-Mails,
    Anhangsfilter (Signaturgrafik vs. Beleg), Antwortpräfixe
  - Stufe 1: Adressfindung über ``email`` und über die JSON-Liste ``emails``
    (String- und Dict-Einträge), Mehrdeutigkeit bei mehreren Personen
  - Kontext: ein aktives EV, mehrere EVs im selben/in verschiedenen Objekten,
    nur beendetes EV
  - Thread: Zuordnung über References und über die Vorgangsnummer im Betreff
  - Verarbeitung: Duplikat, unbekannter Absender legt KEINEN Vorgang an,
    Anlage mit KI-Typ, Ausfall der KI führt auf ``sonstiges``

Die KI (Stufe 2) wird durchgehend gepatcht — die Tests dürfen weder eine
API-Verbindung noch einen API-Key voraussetzen.
"""
import email.utils
import pathlib
import shutil
import tempfile
from datetime import date
from email.message import EmailMessage
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.objekte.models import Einheit, Objekt
from apps.personen.models import EigentumsVerhaeltnis, Person
from apps.vorgaenge.models import (
    MailImportProtokoll, Vorgang, VorgangEreignis, VorgangTyp,
)
from apps.vorgaenge.services import mail_import_service as mis

User = get_user_model()

_MEDIA_TMP = tempfile.mkdtemp(prefix="immocore_test_media_mailimport_")


def tearDownModule():
    shutil.rmtree(_MEDIA_TMP, ignore_errors=True)


KI_LEER = {
    'typ_code': '', 'prioritaet': '', 'betreff': '', 'zusammenfassung': '',
    'konfidenz': None, 'begruendung': '', 'modell': '', 'fehler': '',
}


def ki_antwort(**felder):
    """Rückgabewert für den gepatchten ``klassifiziere``-Aufruf."""
    return {**KI_LEER, **felder}


def schreibe_eml(ordner, dateiname, *, von='absender@example.org', von_name='Test',
                 betreff='Testbetreff', text='Testtext', message_id='<m1@example.org>',
                 in_reply_to=None, references=None, html=None, anhaenge=(),
                 datum='Mon, 5 Jan 2026 10:00:00 +0100'):
    """Erzeugt eine echte ``.eml``-Datei — die Tests gehen bewusst durch den
    Parser statt ein ``ParsedMail`` von Hand zu bauen.

    ``datum=''`` erzeugt eine Mail ohne ``Date``-Header.
    """
    mail = EmailMessage()
    mail['From'] = email.utils.formataddr((von_name, von))
    mail['To'] = 'info@example.org'
    mail['Subject'] = betreff
    if datum:
        mail['Date'] = email.utils.format_datetime(
            email.utils.parsedate_to_datetime(datum))
    if message_id:
        mail['Message-ID'] = message_id
    if in_reply_to:
        mail['In-Reply-To'] = in_reply_to
    if references:
        mail['References'] = ' '.join(references)

    if html is not None:
        mail.set_content(html, subtype='html')
    else:
        mail.set_content(text)

    for name, inhalt, maintype, subtype in anhaenge:
        mail.add_attachment(inhalt, maintype=maintype, subtype=subtype, filename=name)

    pfad = pathlib.Path(ordner) / dateiname
    pfad.write_bytes(mail.as_bytes())
    return pfad


def _objekt(nr='MI001', bezeichnung='Test-WEG Mailimport'):
    return Objekt.objects.create(
        bezeichnung=bezeichnung, objektnummer=nr, objekt_typ='weg',
        ort='Teststadt', verwaltung_seit=date(2020, 1, 1),
    )


def _einheit(objekt, nr='W01'):
    return Einheit.objects.create(
        objekt=objekt, einheit_nr=nr, einheit_typ='Wohnung', lage='EG links',
    )


def _person(nachname='Melder', email_adresse='melder@example.org', emails=None,
            personennummer=None):
    return Person.objects.create(
        personennummer=personennummer or f'P-MI-{nachname}',
        person_typ='100', vorname='Erika', nachname=nachname,
        email=email_adresse or '',
        emails=emails if emails is not None else ([email_adresse] if email_adresse else []),
    )


class ParseEmlTest(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='immocore_test_eml_')
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_umlaute_in_betreff_und_absender(self):
        pfad = schreibe_eml(
            self.tmp, 'umlaut.eml', von='mueller@example.org',
            von_name='Jörg Müller', betreff='Heizkörper wird nicht warm — dringend',
            text='Die Küche bleibt kalt. Grüße')
        parsed = mis.parse_eml(pfad)

        self.assertEqual(parsed.absender_email, 'mueller@example.org')
        self.assertEqual(parsed.absender_name, 'Jörg Müller')
        self.assertEqual(parsed.betreff, 'Heizkörper wird nicht warm — dringend')
        self.assertIn('Küche', parsed.body)

    def test_dekodiere_header_loest_rfc2047_auf(self):
        # Betrifft den .msg-Pfad: extract-msg liefert die Header mit der
        # alten compat32-Policy, also unverändert. Ohne die Auflösung stünde
        # in der Vorschau "=?UTF-8?Q?Stra=C3=9Fe?=" statt "Straße".
        roh = '=?UTF-8?Q?Patrik_Maurer_WEG_Schwalbacher_Stra=C3=9Fe_47=2D49?='
        self.assertEqual(
            mis.dekodiere_header(roh), 'Patrik Maurer WEG Schwalbacher Straße 47-49')

    def test_dekodiere_header_laesst_klartext_unveraendert(self):
        self.assertEqual(mis.dekodiere_header('Max Mustermann'), 'Max Mustermann')
        self.assertEqual(mis.dekodiere_header(''), '')

    def test_dekodiere_header_faellt_auf_rohwert_zurueck(self):
        # Defekter Header: lesbar genug, um den Fall zu erkennen — und nie
        # ein Grund, die ganze Mail scheitern zu lassen.
        kaputt = '=?NICHTEXISTENT?Q?abc?='
        self.assertIsInstance(mis.dekodiere_header(kaputt), str)

    def test_absender_wird_kleingeschrieben(self):
        pfad = schreibe_eml(self.tmp, 'gross.eml', von='Melder@Example.ORG')
        self.assertEqual(mis.parse_eml(pfad).absender_email, 'melder@example.org')

    def test_antwortpraefix_wird_entfernt(self):
        for roh, erwartet in (
            ('AW: Heizung kalt', 'Heizung kalt'),
            ('Re: Re: Heizung kalt', 'Heizung kalt'),
            ('WG: AW: Heizung kalt', 'Heizung kalt'),
            ('Heizung kalt', 'Heizung kalt'),
        ):
            with self.subTest(roh=roh):
                self.assertEqual(mis.bereinige_betreff(roh), erwartet)

    def test_html_mail_wird_zu_text(self):
        pfad = schreibe_eml(
            self.tmp, 'html.eml',
            html='<html><body><p>Das Tor <b>klemmt</b>.</p>'
                 '<p>Gr&uuml;&szlig;e</p><style>p{color:red}</style></body></html>')
        body = mis.parse_eml(pfad).body

        self.assertIn('klemmt', body)
        self.assertIn('Grüße', body)
        self.assertNotIn('<b>', body)
        self.assertNotIn('color:red', body)

    def test_anhaenge_pdf_wird_uebernommen_kleine_grafik_nicht(self):
        pfad = schreibe_eml(
            self.tmp, 'anhang.eml',
            anhaenge=[
                ('beleg.pdf', b'%PDF-1.4 xxx', 'application', 'pdf'),
                ('signatur.png', b'\x89PNG' + b'x' * 100, 'image', 'png'),
                ('schaden.jpg', b'\xff\xd8' + b'y' * (30 * 1024), 'image', 'jpeg'),
            ])
        parsed = mis.parse_eml(pfad)

        namen = [name for name, _ in parsed.anhaenge]
        self.assertIn('beleg.pdf', namen)
        self.assertIn('schaden.jpg', namen)
        # Kleine Grafik = mit hoher Wahrscheinlichkeit Signaturlogo.
        self.assertNotIn('signatur.png', namen)
        # Gezählt werden trotzdem alle drei.
        self.assertEqual(parsed.anhaenge_gesamt, 3)

    def test_nul_bytes_im_text_werden_entfernt(self):
        # Mails mit defektem Encoding enthalten gelegentlich NUL-Bytes.
        # PostgreSQL lehnt die in Textspalten ab — bleiben sie stehen,
        # scheitert das Speichern und die Mail ist nur noch als Fehler
        # sichtbar statt als Vorgang.
        pfad = schreibe_eml(
            self.tmp, 'nul.eml', betreff='Defekt\x00er Betreff',
            text='Text mit \x00 mittendrin.')
        parsed = mis.parse_eml(pfad)

        self.assertNotIn('\x00', parsed.betreff)
        self.assertNotIn('\x00', parsed.betreff_bereinigt)
        self.assertNotIn('\x00', parsed.body)
        self.assertIn('Text mit', parsed.body)

    def test_references_werden_gelesen(self):
        pfad = schreibe_eml(
            self.tmp, 'thread.eml', in_reply_to='<a@example.org>',
            references=['<a@example.org>', '<b@example.org>'])
        parsed = mis.parse_eml(pfad)

        self.assertEqual(parsed.in_reply_to, '<a@example.org>')
        self.assertEqual(parsed.references, ['<a@example.org>', '<b@example.org>'])


class FindePersonenTest(TestCase):
    def test_treffer_ueber_email_feld(self):
        person = _person(email_adresse='treffer@example.org')
        self.assertEqual(mis.finde_personen('treffer@example.org'), [person])

    def test_treffer_ist_case_insensitiv(self):
        person = _person(email_adresse='treffer@example.org')
        self.assertEqual(mis.finde_personen('Treffer@Example.ORG'), [person])

    def test_treffer_ueber_emails_liste_mit_dict(self):
        # emails-Einträge sind historisch mal String, mal Dict — beide müssen
        # gefunden werden, sonst hängt die Zuordnung vom Importweg ab.
        person = _person(
            nachname='DictMail', email_adresse='erste@example.org',
            emails=[{'adresse': 'erste@example.org'},
                    {'adresse': 'zweite@example.org'}])
        self.assertEqual(mis.finde_personen('zweite@example.org'), [person])

    def test_kein_treffer_bei_unbekannter_adresse(self):
        _person(email_adresse='bekannt@example.org')
        self.assertEqual(mis.finde_personen('fremd@example.org'), [])

    def test_leere_adresse_liefert_nichts(self):
        self.assertEqual(mis.finde_personen(''), [])

    def test_mehrere_personen_unter_gleicher_adresse(self):
        _person(nachname='EheA', email_adresse='paar@example.org',
                personennummer='P-MI-A')
        _person(nachname='EheB', email_adresse='paar@example.org',
                personennummer='P-MI-B')
        self.assertEqual(len(mis.finde_personen('paar@example.org')), 2)


class FindeKontextTest(TestCase):
    def setUp(self):
        self.objekt = _objekt()
        self.person = _person()

    def test_ein_aktives_ev_liefert_einheit_und_objekt(self):
        einheit = _einheit(self.objekt)
        EigentumsVerhaeltnis.objects.create(
            person=self.person, einheit=einheit, beginn=date(2021, 1, 1))

        kontext = mis.finde_kontext(self.person)
        self.assertEqual(kontext['einheit'], einheit)
        self.assertEqual(kontext['objekt'], self.objekt)
        self.assertFalse(kontext['mehrdeutig'])

    def test_mehrere_evs_im_selben_objekt_liefern_nur_objekt(self):
        for nr in ('W01', 'W02'):
            EigentumsVerhaeltnis.objects.create(
                person=self.person, einheit=_einheit(self.objekt, nr),
                beginn=date(2021, 1, 1))

        kontext = mis.finde_kontext(self.person)
        self.assertIsNone(kontext['einheit'])
        self.assertEqual(kontext['objekt'], self.objekt)
        self.assertTrue(kontext['mehrdeutig'])

    def test_evs_in_verschiedenen_objekten_liefern_nichts(self):
        zweites = _objekt(nr='MI002', bezeichnung='Zweite WEG')
        EigentumsVerhaeltnis.objects.create(
            person=self.person, einheit=_einheit(self.objekt), beginn=date(2021, 1, 1))
        EigentumsVerhaeltnis.objects.create(
            person=self.person, einheit=_einheit(zweites), beginn=date(2021, 1, 1))

        kontext = mis.finde_kontext(self.person)
        self.assertIsNone(kontext['einheit'])
        self.assertIsNone(kontext['objekt'])
        self.assertTrue(kontext['mehrdeutig'])

    def test_nur_beendetes_ev_gilt_als_mehrdeutig(self):
        einheit = _einheit(self.objekt)
        EigentumsVerhaeltnis.objects.create(
            person=self.person, einheit=einheit,
            beginn=date(2019, 1, 1), ende=date(2023, 6, 30))

        kontext = mis.finde_kontext(self.person)
        self.assertEqual(kontext['einheit'], einheit)
        self.assertTrue(kontext['mehrdeutig'])

    def test_ohne_ev_bleibt_alles_leer(self):
        kontext = mis.finde_kontext(self.person)
        self.assertIsNone(kontext['einheit'])
        self.assertIsNone(kontext['objekt'])


class FindeKontextGeteiltTest(TestCase):
    """Adresse, die mehrere Personensätze führen — Ehepaar mit zwei Sätzen
    oder Dublette. Die Fälle stecken real in den Stammdaten (21 von 533
    Adressen); vorher fiel jeder davon durch die Erkennung."""

    def setUp(self):
        self.objekt = _objekt()
        self.a = _person(nachname='Hahling', email_adresse='paar@example.org',
                         personennummer='P-MI-GA')
        self.b = _person(nachname='Hahling2', email_adresse='paar@example.org',
                         personennummer='P-MI-GB')

    def test_nur_ein_satz_mit_vertrag_loest_vollstaendig_auf(self):
        # Der Dublettenfall: derselbe Eigentümer zweimal erfasst, nur ein
        # Satz hat das Eigentumsverhältnis.
        einheit = _einheit(self.objekt)
        EigentumsVerhaeltnis.objects.create(
            person=self.a, einheit=einheit, beginn=date(2021, 1, 1))

        kontext = mis.finde_kontext_geteilt([self.a, self.b])

        self.assertEqual(kontext['person'], self.a)
        self.assertEqual(kontext['einheit'], einheit)
        self.assertEqual(kontext['objekt'], self.objekt)
        self.assertFalse(kontext['mehrdeutig'])

    def test_zwei_vertraege_im_selben_objekt_liefern_nur_objekt(self):
        for person, nr in ((self.a, 'W01'), (self.b, 'W02')):
            EigentumsVerhaeltnis.objects.create(
                person=person, einheit=_einheit(self.objekt, nr),
                beginn=date(2021, 1, 1))

        kontext = mis.finde_kontext_geteilt([self.a, self.b])

        self.assertIsNone(kontext['person'])
        self.assertIsNone(kontext['einheit'])
        self.assertEqual(kontext['objekt'], self.objekt)
        self.assertTrue(kontext['mehrdeutig'])

    def test_vertraege_in_verschiedenen_objekten_liefern_nichts(self):
        zweites = _objekt(nr='MI002', bezeichnung='Zweite WEG')
        EigentumsVerhaeltnis.objects.create(
            person=self.a, einheit=_einheit(self.objekt), beginn=date(2021, 1, 1))
        EigentumsVerhaeltnis.objects.create(
            person=self.b, einheit=_einheit(zweites), beginn=date(2021, 1, 1))

        kontext = mis.finde_kontext_geteilt([self.a, self.b])

        self.assertIsNone(kontext['person'])
        self.assertIsNone(kontext['einheit'])
        self.assertIsNone(kontext['objekt'])
        self.assertTrue(kontext['mehrdeutig'])

    def test_ohne_aktive_vertraege_bleibt_alles_leer(self):
        einheit = _einheit(self.objekt)
        EigentumsVerhaeltnis.objects.create(
            person=self.a, einheit=einheit,
            beginn=date(2019, 1, 1), ende=date(2023, 6, 30))

        kontext = mis.finde_kontext_geteilt([self.a, self.b])

        self.assertIsNone(kontext['person'])
        self.assertIsNone(kontext['einheit'])
        self.assertTrue(kontext['mehrdeutig'])


class FindeThreadVorgangTest(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='immocore_test_eml_thread_')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.objekt = _objekt()
        self.user = User.objects.create_user(username='mi-thread', password='x')
        self.vorgang = Vorgang.objects.create(
            typ=VorgangTyp.objects.get(code='maengelmeldung'),
            betreff='Heizung kalt', objekt=self.objekt,
            erstellt_von=self.user, mail_referenz='<ursprung@example.org>',
        )

    def test_zuordnung_ueber_in_reply_to(self):
        pfad = schreibe_eml(self.tmp, 'a.eml', betreff='AW: Heizung kalt',
                            in_reply_to='<ursprung@example.org>')
        self.assertEqual(mis.finde_thread_vorgang(mis.parse_eml(pfad)), self.vorgang)

    def test_zuordnung_ueber_references(self):
        pfad = schreibe_eml(self.tmp, 'b.eml', betreff='AW: Heizung kalt',
                            references=['<fremd@example.org>', '<ursprung@example.org>'])
        self.assertEqual(mis.finde_thread_vorgang(mis.parse_eml(pfad)), self.vorgang)

    def test_zuordnung_ueber_vorgangsnummer_im_betreff(self):
        # Der Weg, der auch dann trägt, wenn ein Mailprogramm die Header
        # beim Antworten verliert.
        pfad = schreibe_eml(
            self.tmp, 'c.eml', betreff=f'AW: [{self.vorgang.nummer}] Heizung kalt')
        self.assertEqual(mis.finde_thread_vorgang(mis.parse_eml(pfad)), self.vorgang)

    def test_keine_zuordnung_ohne_hinweis(self):
        pfad = schreibe_eml(self.tmp, 'd.eml', betreff='Ganz neues Thema')
        self.assertIsNone(mis.finde_thread_vorgang(mis.parse_eml(pfad)))


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class VerarbeiteMailTest(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='immocore_test_eml_verarbeitung_')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.objekt = _objekt()
        self.einheit = _einheit(self.objekt)
        self.person = _person(email_adresse='melder@example.org')
        EigentumsVerhaeltnis.objects.create(
            person=self.person, einheit=self.einheit, beginn=date(2021, 1, 1))

    # -- Anlage --------------------------------------------------------

    @patch.object(mis, 'klassifiziere')
    def test_bekannter_absender_erzeugt_vorgang(self, mock_ki):
        mock_ki.return_value = ki_antwort(
            typ_code='maengelmeldung', prioritaet='hoch',
            betreff='Heizkörper bleibt kalt', zusammenfassung='Heizung defekt.',
            konfidenz=0.92, modell='test-modell')
        pfad = schreibe_eml(self.tmp, 'a.eml', von='melder@example.org',
                            betreff='Heizung', text='Wird nicht warm.')

        protokoll = mis.verarbeite_mail(mis.parse_eml(pfad))

        self.assertEqual(protokoll.status, 'vorgang_neu')
        self.assertEqual(protokoll.person, self.person)
        self.assertEqual(protokoll.einheit, self.einheit)
        self.assertEqual(protokoll.objekt, self.objekt)
        self.assertEqual(protokoll.zuordnung_quelle, 'email_exakt')

        vorgang = protokoll.vorgang
        self.assertIsNotNone(vorgang)
        self.assertEqual(vorgang.quelle, 'mail')
        self.assertEqual(vorgang.typ.code, 'maengelmeldung')
        self.assertEqual(vorgang.prioritaet, 'hoch')
        self.assertEqual(vorgang.betreff, 'Heizkörper bleibt kalt')
        self.assertEqual(vorgang.mail_referenz, '<m1@example.org>')
        # Der Originaltext muss im Vorgang lesbar bleiben.
        self.assertIn('Wird nicht warm.', vorgang.beschreibung)

    @patch.object(mis, 'klassifiziere')
    def test_ki_ausfall_fuehrt_auf_sonstiges_statt_zu_scheitern(self, mock_ki):
        mock_ki.return_value = ki_antwort(fehler='RuntimeError: API nicht erreichbar')
        pfad = schreibe_eml(self.tmp, 'b.eml', von='melder@example.org',
                            betreff='Irgendwas ist kaputt')

        protokoll = mis.verarbeite_mail(mis.parse_eml(pfad))

        self.assertEqual(protokoll.status, 'vorgang_neu')
        self.assertEqual(protokoll.vorgang.typ.code, 'sonstiges')
        # Der Betreff fällt auf den bereinigten Mailbetreff zurück.
        self.assertEqual(protokoll.vorgang.betreff, 'Irgendwas ist kaputt')
        self.assertIn('API nicht erreichbar', protokoll.ki_fehler)

    @patch.object(mis, 'klassifiziere')
    def test_halluzinierter_typ_code_wird_verworfen(self, mock_ki):
        mock_ki.return_value = ki_antwort(typ_code='gibtesnicht')
        pfad = schreibe_eml(self.tmp, 'c.eml', von='melder@example.org')

        protokoll = mis.verarbeite_mail(mis.parse_eml(pfad))
        self.assertEqual(protokoll.vorgang.typ.code, 'sonstiges')

    @patch.object(mis, 'klassifiziere')
    def test_mail_und_anhang_landen_als_dokumente_am_vorgang(self, mock_ki):
        mock_ki.return_value = ki_antwort(typ_code='maengelmeldung')
        pfad = schreibe_eml(
            self.tmp, 'd.eml', von='melder@example.org',
            anhaenge=[('beleg.pdf', b'%PDF-1.4 test', 'application', 'pdf')])

        protokoll = mis.verarbeite_mail(mis.parse_mail(pfad))

        dokumente = {d.dateiname: d for d in protokoll.vorgang.dokumente.all()}
        # Die Mail selbst UND der Anhang — der Anhang einzeln, weil eine
        # eingebettete Rechnung über die Dokumentensuche nicht auffindbar ist.
        self.assertEqual(set(dokumente), {'d.eml', 'beleg.pdf'})

        mail_dokument = dokumente['d.eml']
        self.assertEqual(mail_dokument.dokument_typ, 'korrespondenz')
        self.assertEqual(mail_dokument.kategorie, mis.KATEGORIE_MAIL)
        self.assertEqual(mail_dokument.mail_import, protokoll)
        # Im DMS liegt die unveränderte Originaldatei, nicht der Fließtext.
        self.assertEqual(mail_dokument.datei.read(), pathlib.Path(pfad).read_bytes())
        self.assertEqual(dokumente['beleg.pdf'].mail_import, protokoll)

    @patch.object(mis, 'klassifiziere')
    def test_nicht_zugeordnete_mail_wird_trotzdem_abgelegt(self, mock_ki):
        # Kern der Trennung von Aufbewahrung und Zuordnung: Die Mail muss im
        # DMS liegen, auch wenn niemand weiß, wohin sie gehört — sonst hinge
        # die Aufbewahrungspflicht daran, dass jemand eine Maske anklickt.
        mock_ki.return_value = ki_antwort(typ_code='sonstiges')
        pfad = schreibe_eml(
            self.tmp, 'fremd.eml', von='unbekannt@example.org',
            message_id='<fremd-dms@example.org>',
            anhaenge=[('rechnung.pdf', b'%PDF-1.4 rechnung', 'application', 'pdf')])

        protokoll = mis.verarbeite_mail(mis.parse_mail(pfad))

        self.assertEqual(protokoll.status, 'nicht_zugeordnet')
        self.assertIsNone(protokoll.vorgang)

        dokumente = {d.dateiname: d for d in protokoll.dokumente.all()}
        self.assertEqual(set(dokumente), {'fremd.eml', 'rechnung.pdf'})
        for dokument in dokumente.values():
            # Kontextlos — die Zuordnung trägt später ein Mensch nach.
            self.assertIsNone(dokument.vorgang_id)
            self.assertIsNone(dokument.objekt_id)
            self.assertIsNone(dokument.einheit_id)
            self.assertIsNone(dokument.person_id)
            self.assertEqual(dokument.mail_import, protokoll)

    @patch.object(mis, 'klassifiziere')
    def test_trockenlauf_legt_nichts_im_dms_ab(self, mock_ki):
        mock_ki.return_value = ki_antwort(typ_code='maengelmeldung')
        pfad = schreibe_eml(self.tmp, 'trocken.eml', von='melder@example.org',
                            message_id='<trocken-dms@example.org>')

        protokoll = mis.verarbeite_mail(mis.parse_mail(pfad), anlegen=False)
        self.assertEqual(protokoll.dokumente.count(), 0)

    @patch.object(mis, 'klassifiziere')
    def test_antwortmail_wird_am_bestehenden_vorgang_abgelegt(self, mock_ki):
        mock_ki.return_value = ki_antwort(typ_code='maengelmeldung')
        erste = schreibe_eml(self.tmp, 'erst.eml', von='melder@example.org',
                             message_id='<t1@example.org>')
        vorgang = mis.verarbeite_mail(mis.parse_mail(erste)).vorgang

        antwort = schreibe_eml(self.tmp, 'antw.eml', von='melder@example.org',
                               betreff='AW: Rueckfrage', message_id='<t2@example.org>',
                               in_reply_to='<t1@example.org>')
        protokoll = mis.verarbeite_mail(mis.parse_mail(antwort))

        self.assertEqual(protokoll.status, 'thread_zuordnung')
        dokument = protokoll.dokumente.get()
        self.assertEqual(dokument.dateiname, 'antw.eml')
        self.assertEqual(dokument.vorgang, vorgang)

    # -- Nicht-Anlage --------------------------------------------------

    @patch.object(mis, 'klassifiziere')
    def test_unbekannter_absender_legt_keinen_vorgang_an(self, mock_ki):
        mock_ki.return_value = ki_antwort(typ_code='anfrage')
        pfad = schreibe_eml(self.tmp, 'e.eml', von='fremd@example.org')

        protokoll = mis.verarbeite_mail(mis.parse_eml(pfad))

        self.assertEqual(protokoll.status, 'nicht_zugeordnet')
        self.assertIsNone(protokoll.vorgang)
        self.assertEqual(protokoll.zuordnung_quelle, 'keine')
        self.assertFalse(Vorgang.objects.filter(quelle='mail').exists())
        # Die Klassifikation wird trotzdem protokolliert — sonst sieht man im
        # Testlauf nicht, ob wenigstens der Typ gestimmt hätte.
        self.assertEqual(protokoll.ki_typ_code, 'anfrage')

    @patch.object(mis, 'klassifiziere')
    def test_geteilte_adresse_erzeugt_jetzt_einen_vorgang(self, mock_ki):
        # Vorher fiel dieser Fall komplett durch ('nicht_zugeordnet'), obwohl
        # die Einheit über den einzigen aktiven Vertrag feststeht.
        mock_ki.return_value = ki_antwort(typ_code='maengelmeldung')
        zwilling = _person(nachname='MelderDublette',
                           email_adresse='melder@example.org',
                           personennummer='P-MI-DUB')
        self.assertEqual(len(mis.finde_personen('melder@example.org')), 2)

        pfad = schreibe_eml(self.tmp, 'geteilt.eml', von='melder@example.org',
                            message_id='<geteilt@example.org>')
        protokoll = mis.verarbeite_mail(mis.parse_eml(pfad))

        self.assertEqual(protokoll.status, 'vorgang_neu')
        self.assertEqual(protokoll.zuordnung_quelle, 'email_geteilt')
        self.assertEqual(protokoll.personen_treffer, 2)
        # Nur self.person hat ein Eigentumsverhältnis -> vollständig aufgelöst.
        self.assertEqual(protokoll.person, self.person)
        self.assertEqual(protokoll.einheit, self.einheit)
        self.assertFalse(protokoll.mehrdeutig)
        self.assertIsNotNone(protokoll.vorgang)
        self.assertNotEqual(protokoll.person, zwilling)

    @patch.object(mis, 'klassifiziere')
    def test_personen_treffer_wird_auch_ohne_treffer_protokolliert(self, mock_ki):
        mock_ki.return_value = ki_antwort(typ_code='anfrage')
        pfad = schreibe_eml(self.tmp, 'niemand.eml', von='fremd@example.org',
                            message_id='<niemand@example.org>')

        protokoll = mis.verarbeite_mail(mis.parse_eml(pfad))
        self.assertEqual(protokoll.personen_treffer, 0)
        self.assertEqual(protokoll.zuordnung_quelle, 'keine')

    @patch.object(mis, 'klassifiziere')
    def test_zweite_mail_mit_gleicher_message_id_ist_duplikat(self, mock_ki):
        mock_ki.return_value = ki_antwort(typ_code='maengelmeldung')
        pfad = schreibe_eml(self.tmp, 'f.eml', von='melder@example.org',
                            message_id='<doppelt@example.org>')
        mis.verarbeite_mail(mis.parse_eml(pfad))

        pfad2 = schreibe_eml(self.tmp, 'f2.eml', von='melder@example.org',
                             message_id='<doppelt@example.org>')
        protokoll = mis.verarbeite_mail(mis.parse_eml(pfad2))

        self.assertEqual(protokoll.status, 'duplikat')
        self.assertEqual(Vorgang.objects.filter(quelle='mail').count(), 1)

    @patch.object(mis, 'klassifiziere')
    def test_trockenlauf_erkennt_aber_legt_nichts_an(self, mock_ki):
        mock_ki.return_value = ki_antwort(typ_code='maengelmeldung', konfidenz=0.8)
        pfad = schreibe_eml(self.tmp, 'g.eml', von='melder@example.org')

        protokoll = mis.verarbeite_mail(mis.parse_eml(pfad), anlegen=False)

        self.assertEqual(protokoll.status, 'vorgang_neu')
        self.assertEqual(protokoll.person, self.person)
        self.assertEqual(protokoll.ki_typ_code, 'maengelmeldung')
        self.assertIsNone(protokoll.vorgang)
        self.assertFalse(Vorgang.objects.filter(quelle='mail').exists())

    # -- Thread --------------------------------------------------------

    @patch.object(mis, 'klassifiziere')
    def test_antwort_landet_als_ereignis_am_bestehenden_vorgang(self, mock_ki):
        mock_ki.return_value = ki_antwort(typ_code='maengelmeldung')
        erste = schreibe_eml(self.tmp, 'h.eml', von='melder@example.org',
                             message_id='<erste@example.org>')
        vorgang = mis.verarbeite_mail(mis.parse_eml(erste)).vorgang

        antwort = schreibe_eml(
            self.tmp, 'h2.eml', von='melder@example.org',
            betreff='AW: Rueckfrage', message_id='<zweite@example.org>',
            in_reply_to='<erste@example.org>', text='Gibt es schon einen Termin?')
        protokoll = mis.verarbeite_mail(mis.parse_eml(antwort))

        self.assertEqual(protokoll.status, 'thread_zuordnung')
        self.assertEqual(protokoll.vorgang, vorgang)
        # Kein zweiter Vorgang.
        self.assertEqual(Vorgang.objects.filter(quelle='mail').count(), 1)

        ereignis = VorgangEreignis.objects.filter(
            vorgang=vorgang, typ='mail_eingegangen').first()
        self.assertIsNotNone(ereignis)
        self.assertIn('Gibt es schon einen Termin?', ereignis.text)
        # Fremdtext ist im Portal nicht sichtbar, solange ihn niemand freigibt.
        self.assertTrue(ereignis.intern)


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class ScanOrdnerTest(TestCase):
    def setUp(self):
        self.eingang = tempfile.mkdtemp(prefix='immocore_test_eingang_')
        self.addCleanup(shutil.rmtree, self.eingang, True)
        self.archiv = pathlib.Path(self.eingang) / 'archiv'
        self.fehler = pathlib.Path(self.eingang) / 'fehler'

        objekt = _objekt()
        einheit = _einheit(objekt)
        person = _person(email_adresse='melder@example.org')
        EigentumsVerhaeltnis.objects.create(
            person=person, einheit=einheit, beginn=date(2021, 1, 1))

    @patch.object(mis, 'klassifiziere')
    def test_dateien_werden_je_ergebnis_einsortiert(self, mock_ki):
        mock_ki.return_value = ki_antwort(typ_code='maengelmeldung')
        schreibe_eml(self.eingang, 'gut.eml', von='melder@example.org',
                     message_id='<gut@example.org>')
        schreibe_eml(self.eingang, 'fremd.eml', von='fremd@example.org',
                     message_id='<fremd@example.org>')

        ergebnis = mis.scan_ordner(self.eingang, self.archiv, self.fehler)

        self.assertEqual(ergebnis['dateien'], 2)
        self.assertEqual(ergebnis['vorgang_neu'], 1)
        self.assertEqual(ergebnis['nicht_zugeordnet'], 1)
        # Der Eingang muss leer sein, sonst läuft der nächste Scan doppelt.
        self.assertEqual(
            list(pathlib.Path(self.eingang).glob('*.eml')), [])
        self.assertTrue((self.archiv / 'gut.eml').exists())
        self.assertTrue((self.fehler / 'fremd.eml').exists())

    @patch.object(mis, 'klassifiziere')
    def test_defekte_datei_bricht_den_lauf_nicht_ab(self, mock_ki):
        mock_ki.return_value = ki_antwort(typ_code='maengelmeldung')
        (pathlib.Path(self.eingang) / 'kaputt.eml').write_bytes(b'\x00\x01nonsense')
        schreibe_eml(self.eingang, 'gut.eml', von='melder@example.org',
                     message_id='<gut2@example.org>')

        ergebnis = mis.scan_ordner(self.eingang, self.archiv, self.fehler)

        self.assertEqual(ergebnis['dateien'], 2)
        self.assertEqual(ergebnis['vorgang_neu'], 1)
        self.assertEqual(
            MailImportProtokoll.objects.filter(dateiname='kaputt.eml').count(), 1)

    def test_fehlender_ordner_ist_kein_absturz(self):
        ergebnis = mis.scan_ordner('/gibt/es/nicht')
        self.assertEqual(ergebnis['dateien'], 0)

    @patch.object(mis, 'klassifiziere')
    def test_datei_wird_vor_verarbeitung_reserviert(self, mock_ki):
        # Kern des Parallelschutzes: Wer das Rename in .arbeit gewinnt,
        # verarbeitet die Datei. Hier wird das Rename simuliert vorweggenommen
        # — der Scan muss die Datei dann kommentarlos überspringen statt sie
        # ein zweites Mal zu verarbeiten (sonst entstehen doppelte Vorgänge,
        # wie beim ersten Lauf gegen den mitlaufenden Celery-Beat-Task).
        mock_ki.return_value = ki_antwort(typ_code='maengelmeldung')
        schreibe_eml(self.eingang, 'gleichzeitig.eml', von='melder@example.org',
                     message_id='<par@example.org>')

        echtes_rename = pathlib.Path.rename

        def rename_vom_anderen_lauf(selbst, ziel):
            if selbst.name == 'gleichzeitig.eml' and '.arbeit' in str(ziel):
                raise FileNotFoundError(2, 'No such file or directory', str(selbst))
            return echtes_rename(selbst, ziel)

        with patch.object(pathlib.Path, 'rename', rename_vom_anderen_lauf):
            ergebnis = mis.scan_ordner(self.eingang, self.archiv, self.fehler)

        self.assertEqual(ergebnis['uebersprungen'], 1)
        self.assertEqual(ergebnis['vorgang_neu'], 0)
        self.assertFalse(Vorgang.objects.filter(quelle='mail').exists())

    @patch.object(mis, 'klassifiziere')
    def test_nachfassmail_wird_unabhaengig_von_der_dateireihenfolge_zugeordnet(self, mock_ki):
        # Der Fall aus dem Echtbetrieb: eine Nachfassmail verweist per
        # In-Reply-To auf die Ursprungsmail. Legt jemand einen ganzen
        # Posteingang auf einmal ab, ist die Dateireihenfolge beliebig.
        # Wird die Nachfassmail zuerst verarbeitet, existiert der bezogene
        # Vorgang noch nicht — und es entstehen zwei Vorgänge statt einem.
        # Deshalb wird nach Sendezeitpunkt sortiert, nicht nach Dateizeit.
        mock_ki.return_value = ki_antwort(typ_code='maengelmeldung')

        # Dateinamen bewusst so, dass die Nachfassmail alphabetisch zuerst
        # käme — die Sortierung darf sich davon nicht beirren lassen.
        schreibe_eml(
            self.eingang, 'a_nachfass.eml', von='melder@example.org',
            betreff='DRINGEND - Nachfassen zu meiner Mail',
            message_id='<zweite@example.org>',
            in_reply_to='<erste@example.org>',
            datum='Sun, 13 Sep 2026 12:06:23 +0200')
        schreibe_eml(
            self.eingang, 'z_ursprung.eml', von='melder@example.org',
            betreff='Aufzuege nicht nutzbar',
            message_id='<erste@example.org>',
            datum='Fri, 11 Sep 2026 20:07:47 +0200')

        ergebnis = mis.scan_ordner(self.eingang, self.archiv, self.fehler)

        self.assertEqual(ergebnis['vorgang_neu'], 1)
        self.assertEqual(ergebnis['thread_zuordnung'], 1)
        self.assertEqual(Vorgang.objects.filter(quelle='mail').count(), 1)

        vorgang = Vorgang.objects.get(quelle='mail')
        # Der Vorgang gehört zur ÄLTEREN Mail, die Nachfassmail hängt daran.
        self.assertEqual(vorgang.mail_referenz, '<erste@example.org>')
        self.assertTrue(VorgangEreignis.objects.filter(
            vorgang=vorgang, typ='mail_eingegangen').exists())

    @patch.object(mis, 'klassifiziere')
    def test_mail_ohne_datum_haelt_die_reihenfolge_nicht_auf(self, mock_ki):
        mock_ki.return_value = ki_antwort(typ_code='maengelmeldung')
        schreibe_eml(self.eingang, 'ohne_datum.eml', von='melder@example.org',
                     message_id='<ohnedatum@example.org>', datum='')
        schreibe_eml(self.eingang, 'mit_datum.eml', von='fremd@example.org',
                     message_id='<mitdatum@example.org>',
                     datum='Fri, 11 Sep 2026 20:07:47 +0200')

        ergebnis = mis.scan_ordner(self.eingang, self.archiv, self.fehler)

        self.assertEqual(ergebnis['dateien'], 2)
        self.assertEqual(ergebnis['fehler'], 0)

    @patch.object(mis, 'klassifiziere')
    def test_arbeitsordner_wird_nicht_mitgescannt(self, mock_ki):
        mock_ki.return_value = ki_antwort(typ_code='maengelmeldung')
        arbeit = pathlib.Path(self.eingang) / '.arbeit'
        arbeit.mkdir()
        schreibe_eml(arbeit, 'liegengeblieben.eml', von='melder@example.org',
                     message_id='<rest@example.org>')

        ergebnis = mis.scan_ordner(self.eingang, self.archiv, self.fehler)

        # Ein Rest aus einem abgestürzten Lauf darf nicht stillschweigend
        # eingesammelt werden — er könnte gerade in Arbeit sein.
        self.assertEqual(ergebnis['dateien'], 0)
        self.assertTrue((arbeit / 'liegengeblieben.eml').exists())


class FormatDispatcherTest(TestCase):
    """``parse_mail`` ist der einzige Einstieg — er wählt den Parser nach
    Dateiendung und ergänzt eine Ersatzkennung, wo die Message-ID fehlt."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='immocore_test_dispatch_')
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_eml_wird_an_parse_eml_gegeben(self):
        pfad = schreibe_eml(self.tmp, 'a.eml', betreff='Direkt gelesen')
        self.assertEqual(mis.parse_mail(pfad).betreff, 'Direkt gelesen')

    def test_msg_wird_an_parse_msg_gegeben(self):
        # Eine echte .msg lässt sich hier nicht erzeugen (extract-msg liest
        # nur); geprüft wird deshalb die Weiche, nicht der Outlook-Parser.
        pfad = pathlib.Path(self.tmp) / 'b.msg'
        pfad.write_bytes(b'egal')
        with patch.object(mis, 'parse_msg') as mock_msg:
            mock_msg.return_value = mis.ParsedMail(
                dateiname='b.msg', absender_email='a@b.de',
                betreff='Aus Outlook', message_id='<x@y>')
            parsed = mis.parse_mail(pfad)

        mock_msg.assert_called_once()
        self.assertEqual(parsed.betreff, 'Aus Outlook')

    def test_unbekanntes_format_wird_abgelehnt(self):
        pfad = pathlib.Path(self.tmp) / 'c.pdf'
        pfad.write_bytes(b'%PDF')
        with self.assertRaises(ValueError):
            mis.parse_mail(pfad)

    def test_fehlende_message_id_bekommt_stabile_ersatzkennung(self):
        # Ohne Kennung greift die Duplikatprüfung nicht. Outlook-.msg liefert
        # die Message-ID nur bei empfangenen Mails mit.
        pfad = schreibe_eml(self.tmp, 'd.eml', betreff='Ohne ID', message_id='')
        erste = mis.parse_mail(pfad)

        pfad2 = schreibe_eml(self.tmp, 'anders_benannt.eml', betreff='Ohne ID',
                             message_id='')
        zweite = mis.parse_mail(pfad2)

        self.assertTrue(erste.message_id.startswith('<ersatz-'))
        # Dieselbe Mail unter anderem Dateinamen -> dieselbe Kennung.
        self.assertEqual(erste.message_id, zweite.message_id)

    def test_verschiedene_mails_bekommen_verschiedene_ersatzkennungen(self):
        a = mis.parse_mail(schreibe_eml(self.tmp, 'e.eml', betreff='Heizung',
                                        message_id=''))
        b = mis.parse_mail(schreibe_eml(self.tmp, 'f.eml', betreff='Garage',
                                        message_id=''))
        self.assertNotEqual(a.message_id, b.message_id)
