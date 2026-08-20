"""
Tests für ``apps.versammlung.services.stimmkraft_service`` (Spec v1.1 Kap. 5).

Deckt ab:
  - Teilnehmerkreis aus aktiven Eigentumsverhältnissen (beendete zählen nicht)
  - Kopfprinzip: eine Stimme je Eigentümer, auch bei mehreren Einheiten
  - Verteilerschlüssel als Stimmgrundlage: VS 030 (je Einheit), VS 010 (MEA),
    VS 031 (nur Wohnungen — Stellplatzeigentümer ohne Stimmrecht)
  - Vollständigkeitsprüfungen: fehlende Werte, leerer Schlüssel, inaktiver
    Schlüssel und Einheiten OHNE aktiven Eigentümer führen zum Abbruch
  - Idempotenz und Neuermittlung nach Eigentümerwechsel
  - berechne_quorum: informativ, kein Gate
"""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.personen.models import EigentumsVerhaeltnis
from apps.versammlung.services import ev_service, stimmkraft_service
from apps.versammlung.tests import factories as f


class TeilnehmerkreisTest(TestCase):
    def setUp(self):
        self.user = f.user()
        self.objekt = f.objekt()
        self.ev = ev_service.erstelle_ev(objekt=self.objekt, erstellt_von=self.user)

    def test_je_eigentuemer_ein_teilnehmer(self):
        f.eigentuemer(self.objekt)
        f.eigentuemer(self.objekt)
        stats = stimmkraft_service.ermittle_teilnehmer(self.ev, self.user)
        self.assertEqual(stats['teilnehmer'], 2)
        self.assertEqual(self.ev.teilnehmer.count(), 2)

    def test_beendete_verhaeltnisse_zaehlen_nicht(self):
        _, verhaeltnis = f.eigentuemer(self.objekt)
        verhaeltnis.ende = date(2025, 12, 31)
        verhaeltnis.save(update_fields=['ende'])
        f.eigentuemer(self.objekt)
        stats = stimmkraft_service.ermittle_teilnehmer(self.ev, self.user)
        self.assertEqual(stats['teilnehmer'], 1)

    def test_objekt_ohne_eigentuemer_wird_abgelehnt(self):
        with self.assertRaises(ValidationError) as ctx:
            stimmkraft_service.ermittle_teilnehmer(self.ev, self.user)
        self.assertIn('keine aktiven Eigentumsverhältnisse', str(ctx.exception))

    def test_anteile_werden_je_einheit_angelegt(self):
        person = f.person(nachname='Vielhaber')
        f.eigentuemer(self.objekt, person, nr='001')
        f.eigentuemer(self.objekt, person, nr='002')
        stimmkraft_service.ermittle_teilnehmer(self.ev, self.user)
        teilnehmer = self.ev.teilnehmer.get()
        self.assertEqual(teilnehmer.anteile.count(), 2)
        self.assertEqual(
            sorted(teilnehmer.anteile.values_list('einheit_nr_snapshot', flat=True)),
            ['001', '002'],
        )

    def test_ermittlung_erzeugt_ereignis(self):
        f.eigentuemer(self.objekt)
        stimmkraft_service.ermittle_teilnehmer(self.ev, self.user)
        ereignis = self.ev.ereignisse.get(typ='stimmkraft_ermittelt')
        self.assertIn('Kopfprinzip', ereignis.text)


class KopfprinzipTest(TestCase):
    def setUp(self):
        self.user = f.user()
        self.objekt = f.objekt()

    def test_eine_stimme_je_person(self):
        vielhaber = f.person(nachname='Vielhaber')
        f.eigentuemer(self.objekt, vielhaber, nr='001')
        f.eigentuemer(self.objekt, vielhaber, nr='002')
        f.eigentuemer(self.objekt, vielhaber, nr='003')
        f.eigentuemer(self.objekt, f.person(nachname='Einzel'), nr='004')

        ev = ev_service.erstelle_ev(objekt=self.objekt, erstellt_von=self.user)
        stats = stimmkraft_service.ermittle_teilnehmer(ev, self.user)

        self.assertEqual(stats['teilnehmer'], 2)
        self.assertEqual(stats['gesamt_stimmkraft'], Decimal('2'))
        self.assertEqual(stats['grundlage'], 'Kopfprinzip')
        self.assertEqual(ev.teilnehmer.get(person=vielhaber).stimmkraft, Decimal('1'))

    def test_einheiten_ohne_eigentuemer_stoeren_nicht(self):
        # Beim Kopfprinzip geht keine Stimme verloren, wenn eine Einheit keinen
        # Eigentümer hat — es zählen Personen, nicht Einheiten.
        f.eigentuemer(self.objekt, nr='001')
        f.einheit(self.objekt, nr='002')

        ev = ev_service.erstelle_ev(objekt=self.objekt, erstellt_von=self.user)
        stats = stimmkraft_service.ermittle_teilnehmer(ev, self.user)
        self.assertEqual(stats['gesamt_stimmkraft'], Decimal('1'))

    def test_mea_snapshot_wird_trotzdem_gefuellt(self):
        eh, _ = f.eigentuemer(self.objekt, nr='001')
        f.mea_schluessel(self.objekt, {eh: '500'})

        ev = ev_service.erstelle_ev(objekt=self.objekt, erstellt_von=self.user)
        stimmkraft_service.ermittle_teilnehmer(ev, self.user)
        self.assertEqual(
            ev.teilnehmer.get().anteile.get().mea_wert_snapshot, Decimal('500'),
        )

    def test_verteilerschluessel_ohne_prinzip_wird_abgelehnt(self):
        eh, _ = f.eigentuemer(self.objekt, nr='001')
        vs = f.einheiten_schluessel(self.objekt, [eh])
        with self.assertRaises(ValidationError) as ctx:
            ev_service.erstelle_ev(
                objekt=self.objekt, erstellt_von=self.user,
                stimmprinzip='kopf', stimm_verteilerschluessel=vs,
            )
        self.assertIn('stimm_verteilerschluessel', ctx.exception.message_dict)


class VerteilerschluesselPrinzipTest(TestCase):
    def setUp(self):
        self.user = f.user()
        self.objekt = f.objekt()

    def _ev(self, vs, **extra):
        return ev_service.erstelle_ev(
            objekt=self.objekt, erstellt_von=self.user,
            stimmprinzip='verteilerschluessel', stimm_verteilerschluessel=vs,
            **extra,
        )

    def test_prinzip_ohne_schluessel_wird_abgelehnt(self):
        f.eigentuemer(self.objekt, nr='001')
        with self.assertRaises(ValidationError) as ctx:
            ev_service.erstelle_ev(
                objekt=self.objekt, erstellt_von=self.user,
                stimmprinzip='verteilerschluessel',
            )
        self.assertIn('stimm_verteilerschluessel', ctx.exception.message_dict)

    def test_schluessel_fremden_objekts_wird_abgelehnt(self):
        eh, _ = f.eigentuemer(self.objekt, nr='001')
        fremdes = f.objekt(bezeichnung='Fremde WEG')
        fremde_einheit = f.einheit(fremdes, nr='001')
        fremder_vs = f.einheiten_schluessel(fremdes, [fremde_einheit])
        with self.assertRaises(ValidationError):
            self._ev(fremder_vs)

    def test_vs_030_gibt_eine_stimme_je_einheit(self):
        vielhaber = f.person(nachname='Vielhaber')
        eh1, _ = f.eigentuemer(self.objekt, vielhaber, nr='001')
        eh2, _ = f.eigentuemer(self.objekt, vielhaber, nr='002')
        eh3, _ = f.eigentuemer(self.objekt, f.person(nachname='Einzel'), nr='003')
        vs = f.einheiten_schluessel(self.objekt, [eh1, eh2, eh3])

        ev = self._ev(vs)
        stats = stimmkraft_service.ermittle_teilnehmer(ev, self.user)

        self.assertEqual(stats['gesamt_stimmkraft'], Decimal('3'))
        self.assertEqual(stats['grundlage'], '030 Anzahl Einheiten Gesamt')
        self.assertEqual(ev.teilnehmer.get(person=vielhaber).stimmkraft, Decimal('2'))

    def test_mea_schluessel_summiert_anteile(self):
        vielhaber = f.person(nachname='Vielhaber')
        eh1, _ = f.eigentuemer(self.objekt, vielhaber, nr='001')
        eh2, _ = f.eigentuemer(self.objekt, vielhaber, nr='002')
        eh3, _ = f.eigentuemer(self.objekt, f.person(nachname='Einzel'), nr='003')
        vs = f.mea_schluessel(self.objekt, {eh1: '250.5', eh2: '300', eh3: '449.5'})

        ev = self._ev(vs)
        stats = stimmkraft_service.ermittle_teilnehmer(ev, self.user)

        self.assertEqual(stats['gesamt_stimmkraft'], Decimal('1000.0'))
        self.assertEqual(ev.teilnehmer.get(person=vielhaber).stimmkraft, Decimal('550.5'))

    def test_nur_wohnungen_stimmen_mit(self):
        # VS 031: Stellplätze sind am Schlüssel nicht beteiligt — ihr Eigentümer
        # wird geladen, hat aber kein Stimmrecht.
        wohnung, _ = f.eigentuemer(self.objekt, f.person(nachname='Wohnend'), nr='001')
        stellplatz, _ = f.eigentuemer(
            self.objekt, f.person(nachname='Stellplatz'), nr='002',
        )
        vs = f.verteilerschluessel(
            self.objekt, {wohnung: '1'},
            schluessel='031', bezeichnung='Anzahl Wohnungen',
        )

        ev = self._ev(vs)
        stats = stimmkraft_service.ermittle_teilnehmer(ev, self.user)

        self.assertEqual(stats['teilnehmer'], 2)
        self.assertEqual(stats['gesamt_stimmkraft'], Decimal('1'))
        self.assertEqual(stats['ohne_stimmrecht'], ['Max Stellplatz'])
        ereignis = ev.ereignisse.get(typ='stimmkraft_ermittelt')
        self.assertIn('Ohne Stimmrecht', ereignis.text)

    def test_fehlender_wert_bricht_ab(self):
        eh1, _ = f.eigentuemer(self.objekt, nr='001')
        eh2, _ = f.eigentuemer(self.objekt, nr='002')
        vs = f.verteilerschluessel(self.objekt, {eh1: '1', eh2: None})

        ev = self._ev(vs)
        with self.assertRaises(ValidationError) as ctx:
            stimmkraft_service.ermittle_teilnehmer(ev, self.user)
        self.assertIn('fehlen Werte', str(ctx.exception))
        self.assertIn('002', str(ctx.exception))

    def test_leerer_schluessel_bricht_ab(self):
        f.eigentuemer(self.objekt, nr='001')
        vs = f.verteilerschluessel(self.objekt, {})

        ev = self._ev(vs)
        with self.assertRaises(ValidationError) as ctx:
            stimmkraft_service.ermittle_teilnehmer(ev, self.user)
        self.assertIn('keine beteiligten', str(ctx.exception))

    def test_inaktiver_schluessel_bricht_ab(self):
        eh, _ = f.eigentuemer(self.objekt, nr='001')
        vs = f.einheiten_schluessel(self.objekt, [eh])
        ev = self._ev(vs)
        vs.aktiv = False
        vs.save(update_fields=['aktiv'])

        with self.assertRaises(ValidationError) as ctx:
            stimmkraft_service.ermittle_teilnehmer(ev, self.user)
        self.assertIn('nicht aktiv', str(ctx.exception))

    def test_einheit_ohne_eigentuemer_bricht_ab(self):
        # Der Fall von Objekt 10031: Einheiten mit Stimmkraft, aber ohne
        # aktives Eigentumsverhältnis. Ohne Abbruch würde die Versammlung mit
        # zu kleiner Stimmkraft rechnen.
        eh1, _ = f.eigentuemer(self.objekt, nr='001')
        verwaist_a = f.einheit(self.objekt, nr='002')
        verwaist_b = f.einheit(self.objekt, nr='003')
        vs = f.einheiten_schluessel(self.objekt, [eh1, verwaist_a, verwaist_b])

        ev = self._ev(vs)
        with self.assertRaises(ValidationError) as ctx:
            stimmkraft_service.ermittle_teilnehmer(ev, self.user)
        meldung = str(ctx.exception)
        self.assertIn('keinen aktiven Eigentümer', meldung)
        self.assertIn('002', meldung)
        self.assertIn('003', meldung)
        self.assertEqual(ev.teilnehmer.count(), 0)

    def test_lange_fehlerliste_wird_gekuerzt(self):
        eh, _ = f.eigentuemer(self.objekt, nr='001')
        verwaiste = [f.einheit(self.objekt, nr=f'{i:03d}') for i in range(10, 30)]
        vs = f.einheiten_schluessel(self.objekt, [eh] + verwaiste)

        ev = self._ev(vs)
        with self.assertRaises(ValidationError) as ctx:
            stimmkraft_service.ermittle_teilnehmer(ev, self.user)
        self.assertIn('und 10 weitere', str(ctx.exception))


class NeuermittlungTest(TestCase):
    def setUp(self):
        self.user = f.user()
        self.objekt = f.objekt()
        self.einheit, self.verhaeltnis = f.eigentuemer(self.objekt, nr='001')
        self.vs = f.einheiten_schluessel(self.objekt, [self.einheit])
        self.ev = ev_service.erstelle_ev(
            objekt=self.objekt, erstellt_von=self.user,
            stimmprinzip='verteilerschluessel', stimm_verteilerschluessel=self.vs,
        )
        stimmkraft_service.ermittle_teilnehmer(self.ev, self.user)

    def test_zweiter_lauf_ist_idempotent(self):
        stats = stimmkraft_service.ermittle_teilnehmer(self.ev, self.user)
        self.assertEqual(stats['neu'], 0)
        self.assertEqual(self.ev.teilnehmer.count(), 1)
        self.assertEqual(self.ev.teilnehmer.get().anteile.count(), 1)

    def test_eigentuemerwechsel_setzt_alte_stimmkraft_auf_null(self):
        alter_eigentuemer = self.verhaeltnis.person
        self.verhaeltnis.ende = date(2026, 2, 28)
        self.verhaeltnis.save(update_fields=['ende'])
        neuer = f.person(nachname='Neueigentuemer')
        EigentumsVerhaeltnis.objects.create(
            einheit=self.einheit, person=neuer, beginn=date(2026, 3, 1),
        )

        stats = stimmkraft_service.stimmkraft_neu_ermitteln(self.ev, self.user)

        self.assertEqual(stats['neu'], 1)
        self.assertEqual(stats['entfallen'], 1)
        self.assertEqual(stats['gesamt_stimmkraft'], Decimal('1'))
        alt = self.ev.teilnehmer.get(person=alter_eigentuemer)
        self.assertEqual(alt.stimmkraft, Decimal('0'))
        self.assertEqual(self.ev.teilnehmer.get(person=neuer).stimmkraft, Decimal('1'))

    def test_verkaufte_einheit_verliert_ihren_anteil(self):
        person = self.verhaeltnis.person
        zweite_einheit, zweites_verhaeltnis = f.eigentuemer(
            self.objekt, person, nr='002',
        )
        f.vs_wert(self.vs, zweite_einheit, '1')
        stimmkraft_service.ermittle_teilnehmer(self.ev, self.user)
        self.assertEqual(self.ev.teilnehmer.get(person=person).anteile.count(), 2)
        self.assertEqual(self.ev.teilnehmer.get(person=person).stimmkraft, Decimal('2'))

        # Einheit verkauft: das Verhältnis endet, der Käufer ist noch nicht
        # erfasst → die Stimme ist nicht zuordenbar, das muss auffallen.
        zweites_verhaeltnis.ende = date(2026, 2, 28)
        zweites_verhaeltnis.save(update_fields=['ende'])
        with self.assertRaises(ValidationError):
            stimmkraft_service.stimmkraft_neu_ermitteln(self.ev, self.user)

        # Mit erfasstem Käufer läuft die Neuermittlung durch.
        EigentumsVerhaeltnis.objects.create(
            einheit=zweite_einheit, person=f.person(nachname='Kaeufer'),
            beginn=date(2026, 3, 1),
        )
        stats = stimmkraft_service.stimmkraft_neu_ermitteln(self.ev, self.user)
        self.assertEqual(stats['gesamt_stimmkraft'], Decimal('2'))
        self.assertEqual(self.ev.teilnehmer.get(person=person).anteile.count(), 1)


class QuorumTest(TestCase):
    def setUp(self):
        self.user = f.user()
        self.objekt = f.objekt()
        self.a = f.person(nachname='Anwesend')
        self.b = f.person(nachname='Abwesend')
        eh1, _ = f.eigentuemer(self.objekt, self.a, nr='001')
        eh2, _ = f.eigentuemer(self.objekt, self.a, nr='002')
        eh3, _ = f.eigentuemer(self.objekt, self.b, nr='003')
        vs = f.einheiten_schluessel(self.objekt, [eh1, eh2, eh3])
        self.ev = ev_service.erstelle_ev(
            objekt=self.objekt, erstellt_von=self.user,
            stimmprinzip='verteilerschluessel', stimm_verteilerschluessel=vs,
        )
        stimmkraft_service.ermittle_teilnehmer(self.ev, self.user)

    def test_ohne_anwesenheit_null_prozent(self):
        quorum = stimmkraft_service.berechne_quorum(self.ev)
        self.assertEqual(quorum['gesamt_stimmkraft'], Decimal('3'))
        self.assertEqual(quorum['anwesende_stimmkraft'], Decimal('0'))
        self.assertEqual(quorum['anwesend_prozent'], Decimal('0.00'))
        self.assertEqual(quorum['anzahl_anwesenheit_offen'], 2)

    def test_anwesende_stimmkraft_wird_summiert(self):
        teilnehmer = self.ev.teilnehmer.get(person=self.a)
        teilnehmer.ist_anwesend = True
        teilnehmer.save(update_fields=['ist_anwesend'])
        abwesend = self.ev.teilnehmer.get(person=self.b)
        abwesend.ist_anwesend = False
        abwesend.save(update_fields=['ist_anwesend'])

        quorum = stimmkraft_service.berechne_quorum(self.ev)
        self.assertEqual(quorum['anwesende_stimmkraft'], Decimal('2'))
        self.assertEqual(quorum['anwesend_prozent'], Decimal('66.67'))
        self.assertEqual(quorum['anzahl_anwesend'], 1)
        self.assertEqual(quorum['anzahl_anwesenheit_offen'], 0)

    def test_kein_quorum_gate_im_ergebnis(self):
        quorum = stimmkraft_service.berechne_quorum(self.ev)
        self.assertNotIn('quorum_erreicht', quorum)
        self.assertIn('beschlussfähig', quorum['hinweis'])

    def test_ev_ohne_teilnehmer_liefert_null(self):
        leere_ev = ev_service.erstelle_ev(objekt=self.objekt, erstellt_von=self.user)
        quorum = stimmkraft_service.berechne_quorum(leere_ev)
        self.assertEqual(quorum['gesamt_stimmkraft'], Decimal('0'))
        self.assertEqual(quorum['anwesend_prozent'], Decimal('0.00'))
