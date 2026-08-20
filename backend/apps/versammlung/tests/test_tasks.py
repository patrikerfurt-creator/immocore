"""
Tests für ``apps.versammlung.tasks`` (Spec v1.1 Kap. 6).

Kernanforderung: der Task darf NIE durchwerfen. Geprüft werden der Erfolgsfall
und alle drei Abbruchpfade (EV weg, User weg, Service wirft).
"""
import shutil
import tempfile
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.versammlung.services import einladung_service, ev_service, stimmkraft_service, tagesordnung_service
from apps.versammlung.tasks import versende_ev_einladungen
from apps.versammlung.tests import factories as f

_MEDIA_TMP = tempfile.mkdtemp(prefix='immocore_test_media_ev_tasks_')


def tearDownModule():
    shutil.rmtree(_MEDIA_TMP, ignore_errors=True)


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class VersendeEvEinladungenTaskTest(TestCase):
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
        person = f.person(nachname='Mailempfaenger')
        person.emails = ['mail@example.org']
        person.save(update_fields=['emails'])
        f.eigentuemer(self.objekt, person, nr='001')
        stimmkraft_service.ermittle_teilnehmer(self.ev, self.user)
        einladung_service.erzeuge_einladungs_pdf(self.ev, self.user)
        mail.outbox = []

    def test_erfolgsfall(self):
        ergebnis = versende_ev_einladungen(str(self.ev.id), self.user.id)
        self.assertEqual(ergebnis['erfolgreich'], 1)
        self.assertEqual(len(mail.outbox), 1)
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.status, 'einladungen_versendet')

    def test_unbekannte_ev_wirft_nicht(self):
        self.assertIsNone(versende_ev_einladungen(str(uuid4()), self.user.id))

    def test_unbekannter_user_wirft_nicht(self):
        self.assertIsNone(versende_ev_einladungen(str(self.ev.id), 999999))
        self.assertEqual(len(mail.outbox), 0)

    def test_servicefehler_wird_als_ereignis_vermerkt(self):
        with patch(
            'apps.versammlung.services.einladung_service.versende_einladungen',
            side_effect=RuntimeError('Simulierter Fehler'),
        ):
            self.assertIsNone(versende_ev_einladungen(str(self.ev.id), self.user.id))
        ereignis = self.ev.ereignisse.filter(typ='versand_fehler').last()
        self.assertIsNotNone(ereignis)
        self.assertIn('Simulierter Fehler', ereignis.text)
