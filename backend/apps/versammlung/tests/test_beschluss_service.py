"""
Tests für ``apps.versammlung.services.beschluss_service``
(Spec v1.1 Kap. 9, Phase D).

Deckt ab:
  - uebernimm_in_sammlung: nur angenommene TOPs, fortlaufende Nummer je Objekt,
    revisionssicheres PDF, Status- und Taskwechsel, Idempotenz
  - Vorbedingungen: Status und Termin
  - Trigger: Folge-Vorgang und WP-Aufgabe (Typ, Zuweisung, Beschlussbezug)
  - Protokoll-PDF: Anlage, Verknüpfung, Neuerzeugung behält die alte Fassung
  - vermerke_anfechtung: Status, Pflichtdatum bei Aufhebung, Wortlaut bleibt
  - anwesenheitsliste als Protokollgrundlage
"""
import shutil
import tempfile
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.dokumente.models import Dokument
from apps.versammlung.models import Beschluss
from apps.versammlung.services import (
    beschluss_service, durchfuehrung_service, ev_service, stimmkraft_service,
    tagesordnung_service,
)
from apps.versammlung.tests import factories as f

_MEDIA_TMP = tempfile.mkdtemp(prefix='immocore_test_media_ev_beschluss_')


def tearDownModule():
    shutil.rmtree(_MEDIA_TMP, ignore_errors=True)


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class _Basis(TestCase):
    """Durchgeführte EV mit drei Eigentümern und zwei abgestimmten TOPs."""

    def setUp(self):
        self.user = f.user()
        self.betreuer = f.user(username='objektbetreuer')
        self.objekt = f.objekt()
        self.objekt.betreuer = self.betreuer
        self.objekt.save(update_fields=['betreuer'])

        einheiten = [
            f.eigentuemer(self.objekt, nr=f'{index:03d}')[0]
            for index in range(1, 4)
        ]
        vs = f.einheiten_schluessel(self.objekt, einheiten)
        self.ev = ev_service.erstelle_ev(
            objekt=self.objekt, erstellt_von=self.user,
            stimmprinzip='verteilerschluessel', stimm_verteilerschluessel=vs,
        )
        ev_service.aktualisiere_terminierung(
            self.ev, self.user,
            termin=timezone.now() - timedelta(hours=3), ort='Gemeinschaftsraum',
        )
        stimmkraft_service.ermittle_teilnehmer(self.ev, self.user)
        for teilnehmer in self.ev.teilnehmer.all():
            durchfuehrung_service.erfasse_anwesenheit(
                teilnehmer, self.user, ist_anwesend=True,
            )

    def _top(self, titel, **extra):
        return tagesordnung_service.top_anlegen(
            ev=self.ev, titel=titel, erstellt_von=self.user,
            beschlussvorlage=f'Beschlusswortlaut zu {titel}.', **extra,
        )

    def _abstimmen(self, top, ja=3, nein=0, enthaltung=0):
        return durchfuehrung_service.erfasse_abstimmung(
            top, self.user, ja=ja, nein=nein, enthaltung=enthaltung,
        )

    def _durchfuehren(self):
        durchfuehrung_service.schliesse_durchfuehrung_ab(self.ev, self.user)
        self.ev.refresh_from_db()


class UebernahmeTest(_Basis):
    def test_nur_angenommene_tops_werden_beschluss(self):
        angenommen = self._top('Jahresabrechnung')
        abgelehnt = self._top('Sonderumlage')
        self._abstimmen(angenommen, ja=3, nein=0)
        self._abstimmen(abgelehnt, ja=1, nein=2)
        self._durchfuehren()

        ergebnis = beschluss_service.uebernimm_in_sammlung(self.ev, self.user)

        self.assertEqual(ergebnis['beschluesse'], 1)
        self.assertEqual(Beschluss.objects.filter(ev=self.ev).count(), 1)
        beschluss = Beschluss.objects.get(ev=self.ev)
        self.assertEqual(beschluss.top_id, angenommen.id)
        self.assertEqual(beschluss.wortlaut, angenommen.beschlussvorlage)
        self.assertEqual(beschluss.ergebnis_ja, Decimal('3'))
        self.assertEqual(beschluss.ort, self.ev.ort)

    def test_nummern_laufen_je_objekt_fortlaufend(self):
        for titel in ('TOP A', 'TOP B'):
            self._abstimmen(self._top(titel))
        self._durchfuehren()

        ergebnis = beschluss_service.uebernimm_in_sammlung(self.ev, self.user)
        self.assertEqual(ergebnis['nummern'], [1, 2])

    def test_beschluss_pdf_ist_revisionssicher(self):
        self._abstimmen(self._top('Jahresabrechnung'))
        self._durchfuehren()
        beschluss_service.uebernimm_in_sammlung(self.ev, self.user)

        beschluss = Beschluss.objects.get(ev=self.ev)
        dokument = beschluss.dokument
        self.assertIsNotNone(dokument)
        self.assertEqual(dokument.dokument_typ, 'beschluss')
        self.assertTrue(dokument.revisionssicher)
        self.assertEqual(dokument.objekt_id, self.objekt.id)
        self.assertIsNone(dokument.person_id)
        with self.assertRaises(ValidationError):
            dokument.delete()

    def test_status_und_task_nach_uebernahme(self):
        self._abstimmen(self._top('Jahresabrechnung'))
        self._durchfuehren()
        beschluss_service.uebernimm_in_sammlung(self.ev, self.user)

        self.ev.refresh_from_db()
        self.assertEqual(self.ev.status, 'beschluesse_verarbeitet')
        self.assertTrue(self.ev.task5_beschlussfassung_erledigt)
        self.assertIsNotNone(self.ev.protokoll_pdf_id)

    def test_zweiter_aufruf_verdoppelt_nicht(self):
        self._abstimmen(self._top('Jahresabrechnung'))
        self._durchfuehren()
        beschluss_service.uebernimm_in_sammlung(self.ev, self.user)
        zweites = beschluss_service.uebernimm_in_sammlung(self.ev, self.user)

        self.assertEqual(zweites['beschluesse'], 0)
        self.assertEqual(zweites['uebersprungen'], 1)
        self.assertEqual(Beschluss.objects.filter(ev=self.ev).count(), 1)

    def test_vor_durchfuehrung_nicht_moeglich(self):
        self._abstimmen(self._top('Jahresabrechnung'))
        with self.assertRaises(ValidationError) as ctx:
            beschluss_service.uebernimm_in_sammlung(self.ev, self.user)
        self.assertIn('nach der Durchführung', str(ctx.exception))

    def test_ohne_termin_nicht_moeglich(self):
        self._abstimmen(self._top('Jahresabrechnung'))
        self._durchfuehren()
        self.ev.termin = None
        self.ev.save(update_fields=['termin'])
        with self.assertRaises(ValidationError) as ctx:
            beschluss_service.uebernimm_in_sammlung(self.ev, self.user)
        self.assertIn('§ 24 Abs. 7 WEG', str(ctx.exception))

    def test_ereignis_je_beschluss(self):
        self._abstimmen(self._top('Jahresabrechnung'))
        self._durchfuehren()
        beschluss_service.uebernimm_in_sammlung(self.ev, self.user)
        self.assertEqual(
            self.ev.ereignisse.filter(typ='beschluss_erzeugt').count(), 1,
        )


class TriggerTest(_Basis):
    def test_folge_vorgang(self):
        top = self._top('Erneuerung Hauseingangstür', triggert_vorgang=True)
        self._abstimmen(top)
        self._durchfuehren()

        ergebnis = beschluss_service.uebernimm_in_sammlung(self.ev, self.user)

        self.assertEqual(ergebnis['vorgaenge'], 1)
        self.assertEqual(ergebnis['mit_vorgang_trigger'], 1)
        beschluss = Beschluss.objects.get(ev=self.ev)
        vorgang = beschluss.vorgang
        self.assertIsNotNone(vorgang)
        self.assertEqual(vorgang.typ.code, 'ev-beschluss')
        self.assertEqual(vorgang.quelle, 'beschluss')
        self.assertEqual(vorgang.objekt_id, self.objekt.id)
        self.assertEqual(vorgang.zugewiesen_an, self.betreuer)
        self.assertIn(beschluss.wortlaut, vorgang.beschreibung)
        # Kein Handwerkerauftrag ohne Kreditorauswahl.
        self.assertIn('nicht automatisch', vorgang.beschreibung)

    def test_wirtschaftsplan_aufgabe(self):
        top = self._top('Wirtschaftsplan 2026', triggert_wirtschaftsplan=True)
        self._abstimmen(top)
        self._durchfuehren()

        ergebnis = beschluss_service.uebernimm_in_sammlung(self.ev, self.user)

        self.assertEqual(ergebnis['mit_wp_trigger'], 1)
        beschluss = Beschluss.objects.get(ev=self.ev)
        self.assertIn('wirtschaftsplan_beschluss_service', beschluss.vorgang.beschreibung)

    def test_beide_trigger_erzeugen_zwei_vorgaenge(self):
        top = self._top(
            'Sanierung mit Umlage',
            triggert_vorgang=True, triggert_wirtschaftsplan=True,
        )
        self._abstimmen(top)
        self._durchfuehren()

        ergebnis = beschluss_service.uebernimm_in_sammlung(self.ev, self.user)

        self.assertEqual(ergebnis['vorgaenge'], 2)
        self.assertEqual(
            self.ev.ereignisse.filter(typ='vorgang_erzeugt').count(), 2,
        )
        # Beschluss.vorgang zeigt auf den ersten (Umsetzungs-)Vorgang.
        beschluss = Beschluss.objects.get(ev=self.ev)
        self.assertIn('umsetzen', beschluss.vorgang.betreff)

    def test_ohne_trigger_kein_vorgang(self):
        self._abstimmen(self._top('Jahresabrechnung'))
        self._durchfuehren()
        ergebnis = beschluss_service.uebernimm_in_sammlung(self.ev, self.user)
        self.assertEqual(ergebnis['vorgaenge'], 0)
        self.assertIsNone(Beschluss.objects.get(ev=self.ev).vorgang_id)

    def test_abgelehnter_top_loest_nichts_aus(self):
        top = self._top('Sanierung', triggert_vorgang=True)
        self._abstimmen(top, ja=0, nein=3)
        self._durchfuehren()
        ergebnis = beschluss_service.uebernimm_in_sammlung(self.ev, self.user)
        self.assertEqual(ergebnis['beschluesse'], 0)
        self.assertEqual(ergebnis['vorgaenge'], 0)


class ProtokollTest(_Basis):
    def test_protokoll_wird_am_objekt_abgelegt(self):
        self._abstimmen(self._top('Jahresabrechnung'))
        self._durchfuehren()
        dokument = beschluss_service.erzeuge_protokoll_pdf(self.ev, self.user)

        self.assertEqual(dokument.kategorie, 'EV-Protokoll')
        self.assertEqual(dokument.objekt_id, self.objekt.id)
        self.assertIsNone(dokument.person_id)
        dokument.datei.open('rb')
        try:
            self.assertTrue(dokument.datei.read(5).startswith(b'%PDF'))
        finally:
            dokument.datei.close()
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.protokoll_pdf_id, dokument.id)

    def test_neuerzeugung_behaelt_alte_fassung(self):
        self._abstimmen(self._top('Jahresabrechnung'))
        self._durchfuehren()
        erstes = beschluss_service.erzeuge_protokoll_pdf(self.ev, self.user)
        zweites = beschluss_service.erzeuge_protokoll_pdf(self.ev, self.user)

        self.assertNotEqual(erstes.id, zweites.id)
        self.assertTrue(Dokument.objects.filter(pk=erstes.pk).exists())
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.protokoll_pdf_id, zweites.id)

    def test_protokoll_erzeugt_ereignis(self):
        self._abstimmen(self._top('Jahresabrechnung'))
        self._durchfuehren()
        beschluss_service.erzeuge_protokoll_pdf(self.ev, self.user)
        self.assertTrue(self.ev.ereignisse.filter(typ='protokoll_erzeugt').exists())

    def test_anwesenheitsliste_enthaelt_vertretung(self):
        teilnehmer = self.ev.teilnehmer.first()
        vertreter = f.person(nachname='Bevollmaechtigt')
        durchfuehrung_service.erfasse_anwesenheit(
            teilnehmer, self.user, ist_anwesend=True, vertreten_durch=vertreter,
        )
        liste = beschluss_service.anwesenheitsliste(self.ev)

        self.assertEqual(len(liste), 3)
        zeile = next(z for z in liste if z['name'] == teilnehmer.person.name)
        self.assertEqual(zeile['vertretung'], vertreter.name)
        self.assertTrue(zeile['anwesend'])
        self.assertEqual(zeile['stimmkraft'], Decimal('1'))


class AnfechtungTest(_Basis):
    def setUp(self):
        super().setUp()
        self._abstimmen(self._top('Jahresabrechnung'))
        self._durchfuehren()
        beschluss_service.uebernimm_in_sammlung(self.ev, self.user)
        self.beschluss = Beschluss.objects.get(ev=self.ev)

    def test_anhaengige_klage_vermerken(self):
        beschluss_service.vermerke_anfechtung(
            self.beschluss, self.user,
            anfechtung_status='anhaengig', notiz='AG Frankfurt, 2 C 123/26',
        )
        self.beschluss.refresh_from_db()
        self.assertEqual(self.beschluss.anfechtung_status, 'anhaengig')
        self.assertIn('2 C 123/26', self.beschluss.anfechtung_notiz)

    def test_aufhebung_braucht_datum(self):
        with self.assertRaises(ValidationError) as ctx:
            beschluss_service.vermerke_anfechtung(
                self.beschluss, self.user, anfechtung_status='aufgehoben',
            )
        self.assertIn('Datum', str(ctx.exception))

    def test_aufhebung_mit_datum(self):
        beschluss_service.vermerke_anfechtung(
            self.beschluss, self.user, anfechtung_status='aufgehoben',
            aufgehoben_am=date(2026, 9, 1),
            gerichtlicher_hinweis='Urteil vom 01.09.2026',
        )
        self.beschluss.refresh_from_db()
        self.assertEqual(self.beschluss.aufgehoben_am, date(2026, 9, 1))

    def test_wortlaut_bleibt_unveraendert(self):
        wortlaut = self.beschluss.wortlaut
        beschluss_service.vermerke_anfechtung(
            self.beschluss, self.user, anfechtung_status='aufgehoben',
            aufgehoben_am=date(2026, 9, 1),
        )
        self.beschluss.refresh_from_db()
        self.assertEqual(self.beschluss.wortlaut, wortlaut)
        self.assertTrue(Beschluss.objects.filter(pk=self.beschluss.pk).exists())

    def test_unbekannter_status(self):
        with self.assertRaises(ValidationError):
            beschluss_service.vermerke_anfechtung(
                self.beschluss, self.user, anfechtung_status='vielleicht',
            )

    def test_zuruecknahme_setzt_aufhebungsdatum_zurueck(self):
        beschluss_service.vermerke_anfechtung(
            self.beschluss, self.user, anfechtung_status='aufgehoben',
            aufgehoben_am=date(2026, 9, 1),
        )
        beschluss_service.vermerke_anfechtung(
            self.beschluss, self.user, anfechtung_status='abgewiesen',
            notiz='Klage abgewiesen, Beschluss bleibt wirksam.',
        )
        self.beschluss.refresh_from_db()
        self.assertIsNone(self.beschluss.aufgehoben_am)
