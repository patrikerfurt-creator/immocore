"""
Tests für die Mail-Import-Kommandos.

Sie sind Testwerkzeug, kein Produktivpfad — geprüft wird deshalb nur, was
im entscheidenden Moment scheitern würde: das Zurücksetzen muss auch dann
durchlaufen, wenn an den Vorgängen bereits Dokumente hängen
(``Dokument.vorgang`` ist PROTECT).
"""
import shutil
import tempfile
from datetime import date
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.dokumente.models import Dokument
from apps.objekte.models import Einheit, Objekt
from apps.personen.models import EigentumsVerhaeltnis, Person
from apps.vorgaenge.models import MailImportProtokoll, Vorgang
from apps.vorgaenge.services import mail_import_service as mis

from apps.vorgaenge.tests.test_mail_import_service import (
    ki_antwort, schreibe_eml,
)

User = get_user_model()

_MEDIA_TMP = tempfile.mkdtemp(prefix="immocore_test_media_mailkommandos_")


def tearDownModule():
    shutil.rmtree(_MEDIA_TMP, ignore_errors=True)


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class MailTestdatenZuruecksetzenTest(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='immocore_test_kommando_')
        self.addCleanup(shutil.rmtree, self.tmp, True)

        objekt = Objekt.objects.create(
            bezeichnung='Test-WEG Kommando', objektnummer='KD001',
            objekt_typ='weg', ort='Teststadt', verwaltung_seit=date(2020, 1, 1))
        einheit = Einheit.objects.create(
            objekt=objekt, einheit_nr='W01', einheit_typ='Wohnung', lage='EG')
        person = Person.objects.create(
            personennummer='P-KD-1', person_typ='100', vorname='Erika',
            nachname='Melder', email='melder@example.org',
            emails=['melder@example.org'])
        EigentumsVerhaeltnis.objects.create(
            person=person, einheit=einheit, beginn=date(2021, 1, 1))

    @patch.object(mis, 'klassifiziere')
    def _importiere_eine_mail(self, mock_ki):
        mock_ki.return_value = ki_antwort(typ_code='maengelmeldung')
        pfad = schreibe_eml(
            self.tmp, 'kommando.eml', von='melder@example.org',
            message_id='<kommando@example.org>',
            anhaenge=[('beleg.pdf', b'%PDF-1.4 x', 'application', 'pdf')])
        return mis.verarbeite_mail(mis.parse_mail(pfad))

    def test_zuruecksetzen_raeumt_auch_die_dokumente_weg(self):
        protokoll = self._importiere_eine_mail()
        self.assertEqual(protokoll.dokumente.count(), 2)
        self.assertEqual(Vorgang.objects.filter(quelle='mail').count(), 1)

        # Ohne vorheriges Löschen der Dokumente scheitert das Löschen des
        # Vorgangs an PROTECT — genau das darf nicht passieren.
        call_command('mail_testdaten_zuruecksetzen', '--ja',
                     '--ordner', self.tmp, stdout=StringIO())

        self.assertEqual(MailImportProtokoll.objects.count(), 0)
        self.assertEqual(Vorgang.objects.filter(quelle='mail').count(), 0)
        self.assertEqual(Dokument.objects.filter(mail_import__isnull=False).count(), 0)

    def test_ohne_ja_wird_nichts_geloescht(self):
        self._importiere_eine_mail()
        ausgabe = StringIO()
        call_command('mail_testdaten_zuruecksetzen', '--ordner', self.tmp,
                     stdout=ausgabe)

        self.assertEqual(MailImportProtokoll.objects.count(), 1)
        self.assertEqual(Vorgang.objects.filter(quelle='mail').count(), 1)
        self.assertIn('Nichts geloescht', ausgabe.getvalue())

    def test_revisionssicheres_dokument_bleibt_erhalten(self):
        protokoll = self._importiere_eine_mail()
        dokument = protokoll.dokumente.first()
        dokument.revisionssicher = True
        dokument.save(update_fields=['revisionssicher'])

        ausgabe = StringIO()
        # Der Vorgang lässt sich dann nicht löschen (PROTECT) — das Kommando
        # darf daran scheitern, aber es muss vorher sagen, warum.
        with self.assertRaises(Exception):
            call_command('mail_testdaten_zuruecksetzen', '--ja',
                         '--ordner', self.tmp, stdout=ausgabe)
        self.assertIn('revisionssicher', ausgabe.getvalue())
        self.assertTrue(Dokument.objects.filter(pk=dokument.pk).exists())


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class MailDmsNachtragenTest(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='immocore_test_nachtrag_')
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_meldet_wenn_nichts_nachzutragen_ist(self):
        ausgabe = StringIO()
        call_command('mail_dms_nachtragen', '--ordner', self.tmp, stdout=ausgabe)
        self.assertIn('Nichts nachzutragen', ausgabe.getvalue())

    def test_traegt_fehlende_ablage_nach(self):
        # Protokollzeile ohne Dokument, Datei liegt im Archiv — der Zustand
        # aller Mails, die vor Einführung der DMS-Ablage eingelesen wurden.
        import pathlib
        archiv = pathlib.Path(self.tmp) / 'archiv'
        archiv.mkdir()
        schreibe_eml(archiv, 'alt.eml', von='alt@example.org',
                     message_id='<alt@example.org>')
        protokoll = MailImportProtokoll.objects.create(
            dateiname='alt.eml', message_id='<alt@example.org>',
            absender='alt@example.org', status='nicht_zugeordnet')

        call_command('mail_dms_nachtragen', '--ja', '--ordner', self.tmp,
                     stdout=StringIO())

        dokument = protokoll.dokumente.get()
        self.assertEqual(dokument.dateiname, 'alt.eml')
        self.assertEqual(dokument.dokument_typ, 'korrespondenz')
        self.assertIsNone(dokument.vorgang_id)
