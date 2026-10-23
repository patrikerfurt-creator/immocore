"""
Automatische Hausakten-Untergliederung je Eigentuemerversammlung.

Beim Erledigen von Task 1 (Terminierung) entsteht unter Hausakten-Register 16
("Eigentuemerversammlungen") eine objektspezifische Untergliederung 16/A,
16/B … mit dem Arbeitsnamen als Bezeichnung (siehe akten_service und
ev_service._lege_hausakten_register_an).
"""
import shutil
import tempfile
from datetime import timedelta

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.dokumente.models import Aktenregister, Dokument
from apps.dokumente.services import akten_service
from apps.versammlung.services import (
    einladung_service, ev_service, tagesordnung_service,
)
from apps.versammlung.tests import factories as f

_MEDIA_TMP = tempfile.mkdtemp(prefix='immocore_test_media_hausakte_')


def tearDownModule():
    shutil.rmtree(_MEDIA_TMP, ignore_errors=True)


class SuffixZaehlungTest(TestCase):
    """Reine Umrechnung Buchstabenfolge <-> Zahl (A, B, … Z, AA, AB …)."""

    def test_hin_und_rueck(self):
        for zahl, suffix in [(1, 'A'), (2, 'B'), (26, 'Z'),
                             (27, 'AA'), (28, 'AB'), (52, 'AZ'), (53, 'BA')]:
            self.assertEqual(akten_service._zahl_zu_suffix(zahl), suffix)
            self.assertEqual(akten_service._suffix_zu_zahl(suffix), zahl)


class RegisterAnlageTest(TestCase):
    def setUp(self):
        self.user = f.user()
        self.objekt = f.objekt()
        self.ev = ev_service.erstelle_ev(
            objekt=self.objekt, erstellt_von=self.user,
            arbeitsname='ETV 2026 ordentlich',
        )

    def _task1_erledigen(self, ev=None):
        ev = ev or self.ev
        ev_service.aktualisiere_terminierung(
            ev, self.user,
            termin=timezone.now() + timedelta(days=30), ort='Saal',
        )
        return ev_service.markiere_task_erledigt(ev, 1, self.user)

    def test_task1_legt_erstes_unterregister_an(self):
        self._task1_erledigen()
        self.ev.refresh_from_db()
        register = self.ev.hausakte_register
        self.assertIsNotNone(register)
        self.assertEqual(register.code, '16/A')
        self.assertEqual(register.bezeichnung, 'ETV 2026 ordentlich')
        self.assertEqual(register.objekt, self.objekt)
        self.assertEqual(register.aktenart, Aktenregister.AKTENART_HAUS)
        self.assertEqual(register.eltern.code, '16')
        self.assertIsNone(register.eltern.objekt_id)

    def test_task1_erzeugt_audit_ereignis(self):
        self._task1_erledigen()
        ereignis = self.ev.ereignisse.get(typ='register_erzeugt')
        self.assertIn('16/A', ereignis.text)
        self.assertEqual(ereignis.erstellt_von, self.user)

    def test_zweite_ev_am_objekt_bekommt_B(self):
        self._task1_erledigen()
        ev2 = ev_service.erstelle_ev(
            objekt=self.objekt, erstellt_von=self.user, arbeitsname='ETV 2027',
        )
        self._task1_erledigen(ev2)
        ev2.refresh_from_db()
        self.assertEqual(ev2.hausakte_register.code, '16/B')

    def test_register_zaehlung_ist_je_objekt_getrennt(self):
        self._task1_erledigen()
        ev_anderes = ev_service.erstelle_ev(
            objekt=f.objekt(nummer='EV-OBJ-2'), erstellt_von=self.user,
            arbeitsname='ETV anderes Objekt',
        )
        self._task1_erledigen(ev_anderes)
        ev_anderes.refresh_from_db()
        # Eigene Zaehlung je Objekt: beide starten bei A.
        self.assertEqual(ev_anderes.hausakte_register.code, '16/A')

    def test_doppeltes_erledigen_legt_kein_zweites_register_an(self):
        self._task1_erledigen()
        erstes = self.ev.hausakte_register
        # Task 1 kann nicht doppelt "erledigt" werden (Idempotenz in
        # markiere_task_erledigt) — aber selbst ein erneuter sync darf nichts
        # Zweites anlegen.
        akten_service.sync_ev_unterregister(self.ev)
        self.assertEqual(
            Aktenregister.objects.filter(eltern__code='16', objekt=self.objekt).count(),
            1,
        )
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.hausakte_register_id, erstes.id)


class RegisterUmbenennungTest(TestCase):
    """Reset von Task 1 + geaenderter Arbeitsname: gleiches Register, neuer Name."""

    def setUp(self):
        self.user = f.user()
        self.objekt = f.objekt()
        self.ev = ev_service.erstelle_ev(
            objekt=self.objekt, erstellt_von=self.user,
            arbeitsname='ETV 2021-20-10',
        )
        ev_service.aktualisiere_terminierung(
            self.ev, self.user,
            termin=timezone.now() + timedelta(days=30), ort='Saal',
        )
        ev_service.markiere_task_erledigt(self.ev, 1, self.user)
        self.ev.refresh_from_db()
        self.register = self.ev.hausakte_register

    def _abgelegtes_dokument(self):
        dokument = Dokument(
            datei=ContentFile(b'%PDF-1.4 x', name='einladung.pdf'),
            dateiname='einladung.pdf', kategorie='Test',
            objekt=self.objekt, register=self.register,
            hochgeladen_von=self.user,
        )
        dokument.full_clean()
        dokument.save()
        return dokument

    def test_reset_und_umbenennung_behaelt_register_und_zieht_namen_nach(self):
        dokument = self._abgelegtes_dokument()

        ev_service.setze_task_zurueck(self.ev, 1, self.user, 'Termin korrigiert')
        # Arbeitsname korrigieren (wie ueber den Update-Serializer).
        self.ev.arbeitsname = 'ETV 2021-21-10'
        self.ev.save(update_fields=['arbeitsname'])
        ev_service.markiere_task_erledigt(self.ev, 1, self.user)
        self.ev.refresh_from_db()

        # Selbes Register, nur neuer Name.
        self.assertEqual(self.ev.hausakte_register_id, self.register.id)
        self.assertEqual(self.ev.hausakte_register.code, '16/A')
        self.assertEqual(self.ev.hausakte_register.bezeichnung, 'ETV 2021-21-10')
        # Kein zweites Register.
        self.assertEqual(
            Aktenregister.objects.filter(eltern__code='16', objekt=self.objekt).count(),
            1,
        )
        # Abgelegtes Dokument haengt unveraendert am selben Register.
        dokument.refresh_from_db()
        self.assertEqual(dokument.register_id, self.register.id)
        self.assertEqual(dokument.register.bezeichnung, 'ETV 2021-21-10')

    def test_umbenennung_erzeugt_kein_zweites_audit_ereignis(self):
        ev_service.setze_task_zurueck(self.ev, 1, self.user, 'Grund')
        ev_service.markiere_task_erledigt(self.ev, 1, self.user)
        self.assertEqual(
            self.ev.ereignisse.filter(typ='register_erzeugt').count(), 1,
        )


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class EinladungAblageTest(TestCase):
    """Das Einladungs-PDF wird ins 16/x-Register abgelegt, sobald Task 3
    erledigt ist und das Register (aus Task 1) existiert."""

    def setUp(self):
        self.user = f.user()
        self.objekt = f.objekt()
        self.ev = ev_service.erstelle_ev(
            objekt=self.objekt, erstellt_von=self.user, arbeitsname='ETV 2026',
        )

    def _vorbereiten(self):
        ev_service.aktualisiere_terminierung(
            self.ev, self.user,
            termin=timezone.now() + timedelta(days=30), ort='Saal',
        )
        tagesordnung_service.top_anlegen(
            ev=self.ev, titel='Jahresabrechnung', erstellt_von=self.user,
            beschlussvorlage='Die Jahresabrechnung wird beschlossen.',
        )

    def _task1(self):
        ev_service.markiere_task_erledigt(self.ev, 1, self.user)

    def test_task3_legt_einladung_ins_register(self):
        self._vorbereiten()
        self._task1()
        einladung_service.erzeuge_einladungs_pdf(self.ev, self.user)
        ev_service.markiere_task_erledigt(self.ev, 3, self.user)

        self.ev.refresh_from_db()
        self.assertIsNotNone(self.ev.hausakte_register)
        self.assertEqual(
            self.ev.einladungs_pdf.register_id, self.ev.hausakte_register_id,
        )
        self.assertEqual(self.ev.ereignisse.filter(typ='einladung_abgelegt').count(), 1)

    def test_task3_vor_task1_wird_beim_task1_abgelegt(self):
        self._vorbereiten()
        einladung_service.erzeuge_einladungs_pdf(self.ev, self.user)
        # Task 3 zuerst — es gibt noch kein Register, also noch keine Ablage.
        ev_service.markiere_task_erledigt(self.ev, 3, self.user)
        self.ev.refresh_from_db()
        self.assertIsNone(self.ev.einladungs_pdf.register_id)

        # Task 1 legt das Register an und zieht die Ablage nach.
        self._task1()
        self.ev.refresh_from_db()
        self.assertEqual(
            self.ev.einladungs_pdf.register_id, self.ev.hausakte_register_id,
        )

    def test_neuerzeugung_nach_task3_wird_wieder_abgelegt(self):
        self._vorbereiten()
        self._task1()
        einladung_service.erzeuge_einladungs_pdf(self.ev, self.user)
        ev_service.markiere_task_erledigt(self.ev, 3, self.user)

        # Neue Fassung des PDFs — muss sofort wieder im Register landen.
        neues = einladung_service.erzeuge_einladungs_pdf(self.ev, self.user)
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.einladungs_pdf_id, neues.id)
        self.assertEqual(neues.register_id, self.ev.hausakte_register_id)

    def test_ohne_task3_keine_ablage(self):
        self._vorbereiten()
        self._task1()
        dokument = einladung_service.erzeuge_einladungs_pdf(self.ev, self.user)
        # Task 3 nicht erledigt -> Einladung bleibt uneinsortiert.
        self.assertIsNone(dokument.register_id)
        self.assertFalse(self.ev.ereignisse.filter(typ='einladung_abgelegt').exists())


class ArbeitsnamePflichtfeldTest(TestCase):
    def test_erstelle_ev_ohne_arbeitsname_bekommt_ersatznamen(self):
        # Programmatische Anlage ohne Arbeitsname bleibt moeglich, fuellt aber
        # die Invariante (blank=False) mit einem Ersatznamen.
        ev = ev_service.erstelle_ev(
            objekt=f.objekt(nummer='EV-OHNE-NAME'), erstellt_von=f.user(),
        )
        self.assertTrue(ev.arbeitsname.strip())
        self.assertIn('EV-OHNE-NAME', ev.arbeitsname)
