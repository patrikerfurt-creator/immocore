"""
Tests für den Mail-Posteingang (Service + API).

Kernzusicherung über alle Aktionen hinweg: Der Kontext wird auf den bereits
abgelegten Dokumenten NACHGETRAGEN. Genau dafür gibt es den Posteingang —
die Datei liegt schon im DMS, ihr fehlt nur die Verortung.

Ausserdem geprüft: eine erledigte Mail lässt sich nicht ein zweites Mal
entscheiden, und Verwerfen ohne Begründung wird abgelehnt (die Notiz ist
nach dem Löschen der Dokumente die einzige Spur).
"""
import shutil
import tempfile
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.dokumente.models import Dokument
from apps.objekte.models import Einheit, Objekt
from apps.personen.models import Person
from apps.vorgaenge.models import (
    MailImportProtokoll, Vorgang, VorgangEreignis, VorgangTyp,
)
from apps.vorgaenge.services import mail_import_service as mis
from apps.vorgaenge.services import posteingang_service

from apps.vorgaenge.tests.test_mail_import_service import ki_antwort, schreibe_eml

User = get_user_model()

_MEDIA_TMP = tempfile.mkdtemp(prefix="immocore_test_media_posteingang_")


def tearDownModule():
    shutil.rmtree(_MEDIA_TMP, ignore_errors=True)


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class PosteingangBasis(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='immocore_test_pe_')
        self.addCleanup(shutil.rmtree, self.tmp, True)

        self.user = User.objects.create_user(username='pe-tester', password='x')
        self.objekt = Objekt.objects.create(
            bezeichnung='Test-WEG Posteingang', objektnummer='PE001',
            objekt_typ='weg', ort='Teststadt', verwaltung_seit=date(2020, 1, 1))
        self.einheit = Einheit.objects.create(
            objekt=self.objekt, einheit_nr='W01', einheit_typ='Wohnung', lage='EG')
        self.typ = VorgangTyp.objects.get(code='maengelmeldung')

    @patch.object(mis, 'klassifiziere')
    def _unzugeordnete_mail(self, mock_ki, dateiname='fremd.eml',
                            message_id='<pe@example.org>'):
        """Eine Mail von unbekanntem Absender — landet im Posteingang."""
        mock_ki.return_value = ki_antwort(
            typ_code='anfrage', betreff='Angebot Wartung', konfidenz=0.8)
        pfad = schreibe_eml(
            self.tmp, dateiname, von='unbekannt@example.org',
            betreff='Angebot Wartung 2026', message_id=message_id,
            anhaenge=[('angebot.pdf', b'%PDF-1.4 x', 'application', 'pdf')])
        protokoll = mis.verarbeite_mail(mis.parse_mail(pfad))
        self.assertEqual(protokoll.posteingang_status, 'offen')
        return protokoll


class PosteingangServiceTest(PosteingangBasis):

    def test_import_stellt_unzugeordnete_mail_in_den_posteingang(self):
        protokoll = self._unzugeordnete_mail()
        self.assertIn(protokoll, posteingang_service.offene_mails())
        # Die Dokumente liegen schon da, nur ohne Kontext.
        self.assertEqual(protokoll.dokumente.count(), 2)
        for dokument in protokoll.dokumente.all():
            self.assertIsNone(dokument.objekt_id)

    def test_vorgang_anlegen_traegt_kontext_auf_dokumenten_nach(self):
        protokoll = self._unzugeordnete_mail()

        vorgang = posteingang_service.lege_vorgang_an(
            protokoll, typ=self.typ, benutzer=self.user, objekt=self.objekt,
            betreff='Wartungsangebot prüfen', notiz='gehört zur WEG')

        protokoll.refresh_from_db()
        self.assertEqual(protokoll.posteingang_status, 'zugeordnet')
        self.assertEqual(protokoll.vorgang, vorgang)
        self.assertEqual(protokoll.erledigt_von, self.user)
        self.assertIsNotNone(protokoll.erledigt_am)

        self.assertEqual(vorgang.objekt, self.objekt)
        self.assertEqual(vorgang.quelle, 'mail')
        self.assertEqual(vorgang.betreff, 'Wartungsangebot prüfen')

        for dokument in protokoll.dokumente.all():
            self.assertEqual(dokument.vorgang, vorgang)
            # Die Herkunft bleibt erhalten — sie ändert sich nicht dadurch,
            # dass die Zuordnung gefunden wurde.
            self.assertEqual(dokument.mail_import, protokoll)

    def test_vorgang_zuordnen_haengt_mail_an_bestehenden_vorgang(self):
        protokoll = self._unzugeordnete_mail()
        bestehender = Vorgang.objects.create(
            typ=self.typ, betreff='Laufender Fall', objekt=self.objekt,
            erstellt_von=self.user)

        posteingang_service.ordne_vorgang_zu(
            protokoll, bestehender, benutzer=self.user)

        protokoll.refresh_from_db()
        self.assertEqual(protokoll.posteingang_status, 'zugeordnet')
        self.assertEqual(protokoll.vorgang, bestehender)
        self.assertTrue(VorgangEreignis.objects.filter(
            vorgang=bestehender, typ='mail_eingegangen').exists())
        for dokument in protokoll.dokumente.all():
            self.assertEqual(dokument.vorgang, bestehender)

    def test_nur_ablegen_setzt_kontext_ohne_vorgang(self):
        # Der häufigste Fall: Rechnung, Abrechnung, Wartungsprotokoll — die
        # gehören an ein Objekt, aber niemand muss dazu einen Fall bearbeiten.
        protokoll = self._unzugeordnete_mail()

        posteingang_service.lege_nur_ab(
            protokoll, benutzer=self.user, objekt=self.objekt,
            notiz='Abrechnung, nur zur Ablage')

        protokoll.refresh_from_db()
        self.assertEqual(protokoll.posteingang_status, 'abgelegt')
        self.assertIsNone(protokoll.vorgang_id)
        self.assertEqual(protokoll.objekt, self.objekt)
        self.assertFalse(Vorgang.objects.filter(quelle='mail').exists())
        for dokument in protokoll.dokumente.all():
            self.assertEqual(dokument.objekt, self.objekt)
            self.assertIsNone(dokument.vorgang_id)

    def test_nur_ablegen_verlangt_genau_einen_kontext(self):
        protokoll = self._unzugeordnete_mail()
        with self.assertRaises(ValidationError):
            posteingang_service.lege_nur_ab(protokoll, benutzer=self.user)
        with self.assertRaises(ValidationError):
            posteingang_service.lege_nur_ab(
                protokoll, benutzer=self.user,
                objekt=self.objekt, einheit=self.einheit)

    def test_verwerfen_loescht_dokumente_und_behaelt_die_spur(self):
        protokoll = self._unzugeordnete_mail()
        self.assertEqual(protokoll.dokumente.count(), 2)

        ergebnis = posteingang_service.verwirf(
            protokoll, benutzer=self.user, notiz='Werbung')

        protokoll.refresh_from_db()
        self.assertEqual(ergebnis['geloescht'], 2)
        self.assertEqual(protokoll.posteingang_status, 'verworfen')
        self.assertEqual(protokoll.erledigt_notiz, 'Werbung')
        self.assertEqual(protokoll.dokumente.count(), 0)
        # Die Protokollzeile bleibt: sonst liesse sich später nicht von einer
        # nie eingegangenen Mail unterscheiden.
        self.assertTrue(
            MailImportProtokoll.objects.filter(pk=protokoll.pk).exists())

    def test_verwerfen_ohne_begruendung_wird_abgelehnt(self):
        protokoll = self._unzugeordnete_mail()
        with self.assertRaises(ValidationError):
            posteingang_service.verwirf(protokoll, benutzer=self.user, notiz='')
        protokoll.refresh_from_db()
        self.assertEqual(protokoll.posteingang_status, 'offen')
        self.assertEqual(protokoll.dokumente.count(), 2)

    def test_verwerfen_laesst_revisionssichere_dokumente_stehen(self):
        protokoll = self._unzugeordnete_mail()
        gesperrt = protokoll.dokumente.first()
        gesperrt.revisionssicher = True
        gesperrt.save(update_fields=['revisionssicher'])

        ergebnis = posteingang_service.verwirf(
            protokoll, benutzer=self.user, notiz='Werbung')

        self.assertEqual(ergebnis['gesperrt'], 1)
        self.assertEqual(ergebnis['geloescht'], 1)
        self.assertTrue(Dokument.objects.filter(pk=gesperrt.pk).exists())

    def test_erledigte_mail_kann_nicht_erneut_entschieden_werden(self):
        protokoll = self._unzugeordnete_mail()
        posteingang_service.lege_nur_ab(
            protokoll, benutzer=self.user, objekt=self.objekt)

        with self.assertRaises(ValidationError):
            posteingang_service.lege_vorgang_an(
                protokoll, typ=self.typ, benutzer=self.user, objekt=self.objekt)

    def test_automatisch_zugeordnete_mail_taucht_nicht_im_posteingang_auf(self):
        person = Person.objects.create(
            personennummer='P-PE-1', person_typ='100', vorname='Erika',
            nachname='Melder', email='melder@example.org',
            emails=['melder@example.org'])
        from apps.personen.models import EigentumsVerhaeltnis
        EigentumsVerhaeltnis.objects.create(
            person=person, einheit=self.einheit, beginn=date(2021, 1, 1))

        with patch.object(mis, 'klassifiziere') as mock_ki:
            mock_ki.return_value = ki_antwort(typ_code='maengelmeldung')
            pfad = schreibe_eml(self.tmp, 'bekannt.eml', von='melder@example.org',
                                message_id='<bekannt-pe@example.org>')
            protokoll = mis.verarbeite_mail(mis.parse_mail(pfad))

        self.assertEqual(protokoll.posteingang_status, 'automatisch')
        self.assertNotIn(protokoll, posteingang_service.offene_mails())

    def test_bereits_verorteter_anhang_wird_nicht_umgehaengt(self):
        # Ein Dokument, das anderswo bewusst zugeordnet wurde, bleibt dort —
        # die Owner-Regel erlaubt ohnehin nur einen Kontext.
        protokoll = self._unzugeordnete_mail()
        anhang = protokoll.dokumente.get(dateiname='angebot.pdf')
        anhang.einheit = self.einheit
        anhang.save(update_fields=['einheit'])

        posteingang_service.lege_nur_ab(
            protokoll, benutzer=self.user, objekt=self.objekt)

        anhang.refresh_from_db()
        self.assertEqual(anhang.einheit, self.einheit)
        self.assertIsNone(anhang.objekt_id)


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class PosteingangApiTest(PosteingangBasis):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.basis = '/api/v1/mail-posteingang'

    def test_liste_zeigt_standardmaessig_nur_offene(self):
        offen = self._unzugeordnete_mail()
        MailImportProtokoll.objects.create(
            dateiname='erledigt.eml', status='vorgang_neu',
            posteingang_status='automatisch')

        antwort = self.client.get(f'{self.basis}/')
        self.assertEqual(antwort.status_code, 200)
        ergebnisse = antwort.data['results'] if 'results' in antwort.data else antwort.data
        ids = [zeile['id'] for zeile in ergebnisse]
        self.assertEqual(ids, [str(offen.id)])

    def test_liste_zeigt_den_ki_vorschlag_als_entscheidungshilfe(self):
        self._unzugeordnete_mail()
        antwort = self.client.get(f'{self.basis}/')
        ergebnisse = antwort.data['results'] if 'results' in antwort.data else antwort.data
        zeile = ergebnisse[0]
        self.assertEqual(zeile['ki_typ_code'], 'anfrage')
        self.assertEqual(zeile['ki_betreff'], 'Angebot Wartung')
        self.assertEqual(len(zeile['dokumente']), 2)
        self.assertFalse(zeile['dokumente'][0]['zugeordnet'])

    def test_vorgang_anlegen_ueber_api(self):
        protokoll = self._unzugeordnete_mail()
        antwort = self.client.post(
            f'{self.basis}/{protokoll.id}/vorgang-anlegen/',
            {'typ': str(self.typ.id), 'objekt': str(self.objekt.id),
             'betreff': 'Aus dem Posteingang'}, format='json')

        self.assertEqual(antwort.status_code, 200)
        self.assertEqual(antwort.data['posteingang_status'], 'zugeordnet')
        self.assertIsNotNone(antwort.data['vorgang_nummer'])

    def test_vorgang_anlegen_ohne_bezug_wird_abgelehnt(self):
        protokoll = self._unzugeordnete_mail()
        antwort = self.client.post(
            f'{self.basis}/{protokoll.id}/vorgang-anlegen/',
            {'typ': str(self.typ.id)}, format='json')
        self.assertEqual(antwort.status_code, 400)

    def test_nur_ablegen_ueber_api(self):
        protokoll = self._unzugeordnete_mail()
        antwort = self.client.post(
            f'{self.basis}/{protokoll.id}/nur-ablegen/',
            {'objekt': str(self.objekt.id), 'notiz': 'Abrechnung'}, format='json')

        self.assertEqual(antwort.status_code, 200)
        self.assertEqual(antwort.data['posteingang_status'], 'abgelegt')
        self.assertIsNone(antwort.data['vorgang_nummer'])

    def test_verwerfen_ueber_api_meldet_geloeschte_dokumente(self):
        protokoll = self._unzugeordnete_mail()
        antwort = self.client.post(
            f'{self.basis}/{protokoll.id}/verwerfen/',
            {'notiz': 'Werbung'}, format='json')

        self.assertEqual(antwort.status_code, 200)
        self.assertEqual(antwort.data['geloeschte_dokumente'], 2)

    def test_verwerfen_ohne_notiz_wird_abgelehnt(self):
        protokoll = self._unzugeordnete_mail()
        antwort = self.client.post(
            f'{self.basis}/{protokoll.id}/verwerfen/', {}, format='json')
        self.assertEqual(antwort.status_code, 400)

    def test_zweite_entscheidung_wird_abgelehnt(self):
        protokoll = self._unzugeordnete_mail()
        self.client.post(f'{self.basis}/{protokoll.id}/nur-ablegen/',
                         {'objekt': str(self.objekt.id)}, format='json')
        antwort = self.client.post(
            f'{self.basis}/{protokoll.id}/nur-ablegen/',
            {'objekt': str(self.objekt.id)}, format='json')
        self.assertEqual(antwort.status_code, 400)

    def test_ohne_anmeldung_kein_zugriff(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f'{self.basis}/').status_code, 401)
