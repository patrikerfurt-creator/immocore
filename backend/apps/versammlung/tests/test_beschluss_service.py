"""
Tests für ``apps.versammlung.services.beschluss_service``
(Spec v1.1 Kap. 9, Phase D).

Deckt ab:
  - uebernimm_in_sammlung: nur angenommene TOPs, fortlaufende Nummer je Objekt,
    revisionssicheres PDF, Idempotenz
  - Vorbedingungen: Status (Checkout) und Termin
  - Trigger: Folge-Vorgang und WP-Aufgabe (Typ, Zuweisung, Beschlussbezug)
  - vermerke_anfechtung: Status, Pflichtdatum bei Aufhebung, Wortlaut bleibt

Nacharbeits-Auftrag (2026-09-27): der frühere Testaufbau über
``self.ev.status = 'durchgefuehrt'`` (alter Task4/5-Ablauf) ist entfallen —
``uebernimm_in_sammlung`` akzeptiert seither nur noch den Status
``ausgecheckt`` (siehe dessen Docstring). Die Tests erreichen diesen Status
jetzt über ``checkout_service.checkout``, wie der echte Ablauf es tut. Die
Tests für Protokoll-PDF und ``anwesenheitsliste`` sind entfallen — beide
Funktionen gehörten zum entfernten ``durchgefuehrt``-Zweig und wurden mit
diesem aus ``beschluss_service`` entfernt (das Protokoll liefert seither
ausschließlich das externe Abstimmtool über
``checkout_service.protokoll_upload``, siehe test_checkout_service.py).
"""
import shutil
import tempfile
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.versammlung.models import Beschluss
from apps.versammlung.services import (
    beschluss_service, checkout_service, durchfuehrung_service, ev_service,
    stimmkraft_service, tagesordnung_service,
)
from apps.versammlung.tests import factories as f

_MEDIA_TMP = tempfile.mkdtemp(prefix='immocore_test_media_ev_beschluss_')


def tearDownModule():
    shutil.rmtree(_MEDIA_TMP, ignore_errors=True)


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class _Basis(TestCase):
    """EV mit drei Eigentümern, ausgecheckt mit abgestimmten TOPs."""

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

    def _checkout(self):
        # Der einzige Weg zu einer abgeschlossenen Abstimmung ist der echte
        # Checkout — TOPs müssen also VOR diesem Aufruf angelegt sein
        # (Tagesordnung ist danach gesperrt, siehe tagesordnung_service).
        checkout_service.checkout(self.ev, self.user)
        self.ev.refresh_from_db()


class UebernahmeTest(_Basis):
    def test_angenommene_und_abgelehnte_werden_beschluss(self):
        # Auch abgelehnte Anträge (Negativbeschlüsse) kommen in die Sammlung,
        # mit festgeschriebenem Ergebnis. 'kein_beschluss'/'offen' nicht.
        angenommen = self._top('Jahresabrechnung')
        abgelehnt = self._top('Sonderumlage')
        self._checkout()
        self._abstimmen(angenommen, ja=3, nein=0)
        self._abstimmen(abgelehnt, ja=1, nein=2)

        ergebnis = beschluss_service.uebernimm_in_sammlung(self.ev, self.user)

        self.assertEqual(ergebnis['beschluesse'], 2)
        self.assertEqual(Beschluss.objects.filter(ev=self.ev).count(), 2)

        b_ja = Beschluss.objects.get(top=angenommen)
        self.assertEqual(b_ja.ergebnis, 'angenommen')
        self.assertEqual(b_ja.ergebnis_ja, Decimal('3'))
        self.assertEqual(b_ja.ort, self.ev.ort)

        b_nein = Beschluss.objects.get(top=abgelehnt)
        self.assertEqual(b_nein.ergebnis, 'abgelehnt')
        self.assertEqual(b_nein.ergebnis_ja, Decimal('1'))
        self.assertEqual(b_nein.ergebnis_nein, Decimal('2'))
        # Fortlaufende Nummern auch über abgelehnte hinweg.
        self.assertNotEqual(b_ja.nummer, b_nein.nummer)

    def test_nummern_laufen_je_objekt_fortlaufend(self):
        tops = [self._top(titel) for titel in ('TOP A', 'TOP B')]
        self._checkout()
        for top in tops:
            self._abstimmen(top)

        ergebnis = beschluss_service.uebernimm_in_sammlung(self.ev, self.user)
        self.assertEqual(ergebnis['nummern'], [1, 2])

    def test_beschluss_pdf_ist_revisionssicher(self):
        top = self._top('Jahresabrechnung')
        self._checkout()
        self._abstimmen(top)
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

    def test_kein_protokoll_und_kein_statuswechsel(self):
        # Kein eigenes Protokoll, kein Statuswechsel — das übernimmt erst
        # checkout_service.protokoll_upload (Schritt 2 von 2, Spec v1.1 Kap. 4D).
        top = self._top('Jahresabrechnung')
        self._checkout()
        self._abstimmen(top)
        beschluss_service.uebernimm_in_sammlung(self.ev, self.user)

        self.ev.refresh_from_db()
        self.assertEqual(self.ev.status, 'ausgecheckt')
        self.assertIsNotNone(self.ev.abschluss_erledigt_am)
        self.assertIsNone(self.ev.protokoll_pdf_id)

    def test_zweiter_aufruf_verdoppelt_nicht(self):
        top = self._top('Jahresabrechnung')
        self._checkout()
        self._abstimmen(top)
        beschluss_service.uebernimm_in_sammlung(self.ev, self.user)
        zweites = beschluss_service.uebernimm_in_sammlung(self.ev, self.user)

        self.assertEqual(zweites['beschluesse'], 0)
        self.assertEqual(zweites['uebersprungen'], 1)
        self.assertEqual(Beschluss.objects.filter(ev=self.ev).count(), 1)

    def test_ohne_checkout_nicht_moeglich(self):
        top = self._top('Jahresabrechnung')
        self._abstimmen(top)
        with self.assertRaises(ValidationError) as ctx:
            beschluss_service.uebernimm_in_sammlung(self.ev, self.user)
        self.assertIn('Checkout', str(ctx.exception))

    def test_ohne_termin_nicht_moeglich(self):
        top = self._top('Jahresabrechnung')
        self._checkout()
        self._abstimmen(top)
        self.ev.termin = None
        self.ev.save(update_fields=['termin'])
        with self.assertRaises(ValidationError) as ctx:
            beschluss_service.uebernimm_in_sammlung(self.ev, self.user)
        self.assertIn('§ 24 Abs. 7 WEG', str(ctx.exception))

    def test_ereignis_je_beschluss(self):
        top = self._top('Jahresabrechnung')
        self._checkout()
        self._abstimmen(top)
        beschluss_service.uebernimm_in_sammlung(self.ev, self.user)
        self.assertEqual(
            self.ev.ereignisse.filter(typ='beschluss_erzeugt').count(), 1,
        )


class TriggerTest(_Basis):
    def test_folge_vorgang(self):
        top = self._top('Erneuerung Hauseingangstür', triggert_vorgang=True)
        self._checkout()
        self._abstimmen(top)

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
        self._checkout()
        self._abstimmen(top)

        ergebnis = beschluss_service.uebernimm_in_sammlung(self.ev, self.user)

        self.assertEqual(ergebnis['mit_wp_trigger'], 1)
        beschluss = Beschluss.objects.get(ev=self.ev)
        self.assertIn('wirtschaftsplan_beschluss_service', beschluss.vorgang.beschreibung)

    def test_beide_trigger_erzeugen_zwei_vorgaenge(self):
        top = self._top(
            'Sanierung mit Umlage',
            triggert_vorgang=True, triggert_wirtschaftsplan=True,
        )
        self._checkout()
        self._abstimmen(top)

        ergebnis = beschluss_service.uebernimm_in_sammlung(self.ev, self.user)

        self.assertEqual(ergebnis['vorgaenge'], 2)
        self.assertEqual(
            self.ev.ereignisse.filter(typ='vorgang_erzeugt').count(), 2,
        )
        # Beschluss.vorgang zeigt auf den ersten (Umsetzungs-)Vorgang.
        beschluss = Beschluss.objects.get(ev=self.ev)
        self.assertIn('umsetzen', beschluss.vorgang.betreff)

    def test_ohne_trigger_kein_vorgang(self):
        top = self._top('Jahresabrechnung')
        self._checkout()
        self._abstimmen(top)
        ergebnis = beschluss_service.uebernimm_in_sammlung(self.ev, self.user)
        self.assertEqual(ergebnis['vorgaenge'], 0)
        self.assertIsNone(Beschluss.objects.get(ev=self.ev).vorgang_id)

    def test_abgelehnter_top_wird_beschluss_aber_loest_keine_vorgaenge_aus(self):
        # Negativbeschluss: kommt in die Sammlung, triggert aber keine
        # Automationen, auch wenn triggert_vorgang gesetzt ist.
        top = self._top('Sanierung', triggert_vorgang=True)
        self._checkout()
        self._abstimmen(top, ja=0, nein=3)
        ergebnis = beschluss_service.uebernimm_in_sammlung(self.ev, self.user)
        self.assertEqual(ergebnis['beschluesse'], 1)
        self.assertEqual(ergebnis['vorgaenge'], 0)
        self.assertEqual(ergebnis['mit_vorgang_trigger'], 0)
        beschluss = Beschluss.objects.get(top=top)
        self.assertEqual(beschluss.ergebnis, 'abgelehnt')
        self.assertIsNone(beschluss.vorgang_id)


class AnfechtungTest(_Basis):
    def setUp(self):
        super().setUp()
        top = self._top('Jahresabrechnung')
        self._checkout()
        self._abstimmen(top)
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
