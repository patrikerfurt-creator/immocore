"""
Tests für ``apps.versammlung.services.ev_service`` (Spec v1.1 Kap. 6).

Deckt ab:
  - erstelle_ev: Status/Flags, Einladungstext-Vorlage, Ereignis 'erstellt'
  - aktualisiere_terminierung: Teiländerung, Ereignis nur bei Termin/Ort
  - markiere_task_erledigt: Voraussetzungen je Task, Idempotenz, erster Task
    hebt 'entwurf' auf 'in_bearbeitung', beliebige Reihenfolge erlaubt
  - setze_task_zurueck: Grund ist Pflicht
  - wechsle_status: alle erlaubten Übergänge, unerlaubte werfen, Zeitstempel
"""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.versammlung.models import EVEreignis, Eigentuemerversammlung
from apps.versammlung.services import ev_service, tagesordnung_service
from apps.versammlung.tests import factories as f


class ErstelleEvTest(TestCase):
    def setUp(self):
        self.user = f.user()
        self.objekt = f.objekt()

    def test_anlage_setzt_status_und_flags(self):
        ev = ev_service.erstelle_ev(
            objekt=self.objekt, erstellt_von=self.user, arbeitsname='EV 2026',
        )
        self.assertEqual(ev.status, 'entwurf')
        self.assertEqual(ev.stimmprinzip, 'kopf')
        status = ev_service.task_status(ev)
        self.assertEqual(status['anzahl_erledigt'], 0)
        self.assertFalse(status['task1']['erledigt'])

    def test_einladungstext_wird_vorbelegt(self):
        ev = ev_service.erstelle_ev(objekt=self.objekt, erstellt_von=self.user)
        self.assertEqual(ev.einladungstext, ev_service.EINLADUNGSTEXT_VORLAGE)

    def test_eigener_einladungstext_bleibt_erhalten(self):
        ev = ev_service.erstelle_ev(
            objekt=self.objekt, erstellt_von=self.user, einladungstext='Kurz.',
        )
        self.assertEqual(ev.einladungstext, 'Kurz.')

    def test_anlage_erzeugt_ereignis(self):
        ev = ev_service.erstelle_ev(objekt=self.objekt, erstellt_von=self.user)
        ereignis = ev.ereignisse.get()
        self.assertEqual(ereignis.typ, 'erstellt')
        self.assertEqual(ereignis.erstellt_von, self.user)

    def test_sev_objekt_wird_abgelehnt(self):
        with self.assertRaises(ValidationError):
            ev_service.erstelle_ev(
                objekt=f.objekt(typ='ZH'), erstellt_von=self.user,
            )
        self.assertEqual(Eigentuemerversammlung.objects.count(), 0)


class TerminierungTest(TestCase):
    def setUp(self):
        self.user = f.user()
        self.ev = ev_service.erstelle_ev(objekt=f.objekt(), erstellt_von=self.user)
        self.termin = timezone.now() + timedelta(days=30)

    def test_termin_und_ort_werden_gesetzt(self):
        ev_service.aktualisiere_terminierung(
            self.ev, self.user, termin=self.termin, ort='Gemeinschaftsraum',
        )
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.termin, self.termin)
        self.assertEqual(self.ev.ort, 'Gemeinschaftsraum')

    def test_nicht_uebergebene_felder_bleiben_unveraendert(self):
        ev_service.aktualisiere_terminierung(
            self.ev, self.user, termin=self.termin, ort='Saal A',
        )
        ev_service.aktualisiere_terminierung(
            self.ev, self.user, raum_buchung_notizen='Bestuhlung 30 Plätze',
        )
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.ort, 'Saal A')
        self.assertEqual(self.ev.raum_buchung_notizen, 'Bestuhlung 30 Plätze')

    def test_terminaenderung_wird_protokolliert(self):
        ev_service.aktualisiere_terminierung(self.ev, self.user, termin=self.termin)
        self.assertEqual(
            self.ev.ereignisse.filter(typ='termin_geaendert').count(), 1,
        )

    def test_nur_notiz_erzeugt_kein_terminereignis(self):
        ev_service.aktualisiere_terminierung(
            self.ev, self.user, raum_buchung_notizen='nur eine Notiz',
        )
        self.assertFalse(self.ev.ereignisse.filter(typ='termin_geaendert').exists())

    def test_terminvorschlaege_werden_gespeichert(self):
        vorschlaege = [{'termin': '2026-03-15T19:00', 'notiz': 'Beirat bevorzugt'}]
        ev_service.aktualisiere_terminierung(
            self.ev, self.user, terminvorschlaege=vorschlaege,
        )
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.terminvorschlaege, vorschlaege)


class TaskFortschrittTest(TestCase):
    def setUp(self):
        self.user = f.user()
        self.ev = ev_service.erstelle_ev(objekt=f.objekt(), erstellt_von=self.user)

    def _termin_setzen(self):
        ev_service.aktualisiere_terminierung(
            self.ev, self.user,
            termin=timezone.now() + timedelta(days=30), ort='Saal',
        )

    def test_task1_ohne_termin_wird_abgelehnt(self):
        with self.assertRaises(ValidationError) as ctx:
            ev_service.markiere_task_erledigt(self.ev, 1, self.user)
        self.assertIn('Termin', str(ctx.exception))
        self.ev.refresh_from_db()
        self.assertFalse(self.ev.task1_terminierung_erledigt)

    def test_task1_mit_termin_und_ort(self):
        self._termin_setzen()
        ev_service.markiere_task_erledigt(self.ev, 1, self.user)
        self.ev.refresh_from_db()
        self.assertTrue(self.ev.task1_terminierung_erledigt)
        self.assertEqual(self.ev.status, 'in_bearbeitung')

    def test_task2_ohne_tagesordnung_wird_abgelehnt(self):
        with self.assertRaises(ValidationError) as ctx:
            ev_service.markiere_task_erledigt(self.ev, 2, self.user)
        self.assertIn('keinen Punkt', str(ctx.exception))

    def test_task2_mit_tagesordnung(self):
        tagesordnung_service.top_anlegen(
            ev=self.ev, titel='Jahresabrechnung', erstellt_von=self.user,
            beschlussvorlage='Die Jahresabrechnung wird beschlossen.',
        )
        ev_service.markiere_task_erledigt(self.ev, 2, self.user)
        self.ev.refresh_from_db()
        self.assertTrue(self.ev.task2_tagesordnung_erledigt)

    def test_reihenfolge_ist_frei(self):
        # Task 3 vor Task 1 und 2 — laut Spec ausdrücklich erlaubt.
        ev_service.markiere_task_erledigt(self.ev, 3, self.user)
        self.ev.refresh_from_db()
        self.assertTrue(self.ev.task3_einladung_erledigt)
        self.assertFalse(self.ev.task1_terminierung_erledigt)

    def test_doppeltes_markieren_erzeugt_kein_zweites_ereignis(self):
        ev_service.markiere_task_erledigt(self.ev, 4, self.user)
        ev_service.markiere_task_erledigt(self.ev, 4, self.user)
        self.assertEqual(
            self.ev.ereignisse.filter(typ='task_erledigt').count(), 1,
        )

    def test_unbekannte_tasknummer(self):
        with self.assertRaises(ValidationError):
            ev_service.markiere_task_erledigt(self.ev, 6, self.user)

    def test_zuruecksetzen_braucht_grund(self):
        ev_service.markiere_task_erledigt(self.ev, 3, self.user)
        with self.assertRaises(ValidationError):
            ev_service.setze_task_zurueck(self.ev, 3, self.user, '  ')
        self.ev.refresh_from_db()
        self.assertTrue(self.ev.task3_einladung_erledigt)

    def test_zuruecksetzen_mit_grund(self):
        ev_service.markiere_task_erledigt(self.ev, 3, self.user)
        ev_service.setze_task_zurueck(
            self.ev, 3, self.user, 'Anlage fehlte im PDF',
        )
        self.ev.refresh_from_db()
        self.assertFalse(self.ev.task3_einladung_erledigt)
        ereignis = self.ev.ereignisse.get(typ='task_zurueckgesetzt')
        self.assertIn('Anlage fehlte', ereignis.text)

    def test_task_status_zaehlt_erledigte(self):
        ev_service.markiere_task_erledigt(self.ev, 3, self.user)
        ev_service.markiere_task_erledigt(self.ev, 5, self.user)
        status = ev_service.task_status(self.ev)
        self.assertEqual(status['anzahl_erledigt'], 2)
        self.assertTrue(status['task5']['erledigt'])
        self.assertEqual(status['task4']['bezeichnung'], 'Durchführung')


class StatuswechselTest(TestCase):
    def setUp(self):
        self.user = f.user()
        self.ev = ev_service.erstelle_ev(objekt=f.objekt(), erstellt_von=self.user)

    def test_vollstaendiger_ablauf(self):
        for ziel in ('in_bearbeitung', 'einladungen_versendet', 'durchgefuehrt',
                     'beschluesse_verarbeitet', 'archiviert'):
            ev_service.wechsle_status(self.ev, ziel, self.user)
            self.ev.refresh_from_db()
            self.assertEqual(self.ev.status, ziel)
        self.assertEqual(
            self.ev.ereignisse.filter(typ='statuswechsel').count(), 5,
        )

    def test_sprung_ueber_stationen_wird_abgelehnt(self):
        with self.assertRaises(ValidationError):
            ev_service.wechsle_status(self.ev, 'durchgefuehrt', self.user)
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.status, 'entwurf')

    def test_archiviert_ist_terminal(self):
        ev_service.wechsle_status(self.ev, 'archiviert', self.user)
        with self.assertRaises(ValidationError):
            ev_service.wechsle_status(self.ev, 'in_bearbeitung', self.user)

    def test_unbekannter_status(self):
        with self.assertRaises(ValidationError):
            ev_service.wechsle_status(self.ev, 'erledigt', self.user)

    def test_gleicher_status_ist_wirkungslos(self):
        ev_service.wechsle_status(self.ev, 'entwurf', self.user)
        self.assertFalse(self.ev.ereignisse.filter(typ='statuswechsel').exists())

    def test_zeitstempel_werden_gesetzt(self):
        ev_service.wechsle_status(self.ev, 'in_bearbeitung', self.user)
        ev_service.wechsle_status(self.ev, 'einladungen_versendet', self.user)
        ev_service.wechsle_status(self.ev, 'durchgefuehrt', self.user)
        self.ev.refresh_from_db()
        self.assertIsNotNone(self.ev.einladung_versendet_am)
        self.assertIsNotNone(self.ev.durchgefuehrt_am)

    def test_systemereignis_ohne_user(self):
        ev_service.vermerke_ereignis(self.ev, 'kommentar', None, text='Systemhinweis')
        ereignis = EVEreignis.objects.get(ev=self.ev, typ='kommentar')
        self.assertIsNone(ereignis.erstellt_von)
