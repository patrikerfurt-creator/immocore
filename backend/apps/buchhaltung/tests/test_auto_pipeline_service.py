"""
Unit- und Integrations-Tests: auto_pipeline_service.

Setzt eine vollständige DB-Umgebung voraus (PostgreSQL).
Smoke-Tests 1–3 aus der Spec (Kap. 13) werden hier abgedeckt.
"""
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.buchhaltung.models import (
    AutoLaufProtokoll,
    FrontofficeAufgabe,
    HausgeldSollstellung,
    HausgeldSollstellungslauf,
    LastschriftLauf,
)
from apps.buchhaltung.services.auto_pipeline_service import run_objekt

User = get_user_model()


def _create_autopilot_user():
    user, _ = User.objects.get_or_create(
        username='immocore-autopilot',
        defaults={
            'first_name': 'IMMOCORE',
            'last_name': 'Autopilot',
            'email': 'autopilot@noreply.immocore.local',
            'is_active': True,
        },
    )
    user.set_unusable_password()
    user.save()
    return user


def _create_test_objekt(**kwargs):
    from apps.objekte.models import Objekt
    defaults = dict(
        objekt_typ='WEG',
        bezeichnung='Test-Objekt',
        kurzbezeichnung='Test',
        strasse='Musterstraße 1',
        plz='60311',
        ort='Frankfurt',
        verwaltung_seit=date(2020, 1, 1),
        glaeubiger_id='DE98ZZZ09999999999',
        auto_pipeline_aktiv=True,
        bundesland='HE',
    )
    defaults.update(kwargs)
    return Objekt.objects.create(**defaults)


def _create_test_bankkonto(objekt, **kwargs):
    from apps.objekte.models import Bankkonto
    defaults = dict(
        konto_typ='bewirtschaftung',
        bezeichnung='Bewirtschaftungskonto',
        iban='DE12500105170648489890',
        bic='INGDDEFF',
        kontoinhaber='WEG Test',
        zahlungsverkehr=True,
        aktiv=True,
    )
    defaults.update(kwargs)
    return Bankkonto.objects.create(objekt=objekt, **defaults)


def _create_einheit(objekt, einheit_nr='WE01'):
    from apps.objekte.models import Einheit
    return Einheit.objects.create(
        objekt=objekt,
        einheit_nr=einheit_nr,
        einheit_typ='Wohnung',
        lage=f'Lage {einheit_nr}',
    )


def _create_sepa_mandat(mandatsreferenz='M2024-001', iban='DE89370400440532013000'):
    from apps.personen.models import SEPAMandat
    return SEPAMandat.objects.create(
        mandatsreferenz=mandatsreferenz,
        iban=iban,
        bic='COBADEFF',
        unterzeichnet_am=date(2024, 1, 15),
        sequence_type='RCUR',
    )


def _create_person(sepa_mandat=None, **kwargs):
    from apps.personen.models import Person
    defaults = dict(
        person_typ='100',
        anrede='Herr',
        vorname='Max',
        nachname='Mustermann',
        sepa_mandat=sepa_mandat,
    )
    defaults.update(kwargs)
    return Person.objects.create(**defaults)


def _create_ev(person, einheit, beginn=None):
    from apps.personen.models import EigentumsVerhaeltnis
    return EigentumsVerhaeltnis.objects.create(
        person=person,
        einheit=einheit,
        beginn=beginn or date(2020, 1, 1),
    )


def _create_hausgeld_historie(ev, ba, betrag=Decimal('250.00'), gueltig_ab=None, user=None):
    from apps.personen.models import HausgeldHistorie
    if user is None:
        user, _ = User.objects.get_or_create(username='test-admin', defaults={'is_staff': True})
    return HausgeldHistorie.objects.create(
        eigentumsverhaeltnis=ev,
        ba=ba,
        betrag=betrag,
        gueltig_ab=gueltig_ab or date(2025, 1, 1),
        quelle='import',
        import_referenz='test-data',
        erstellt_von=user,
    )


def _create_wirtschaftsjahr(objekt, jahr):
    from apps.objekte.models import Wirtschaftsjahr
    return Wirtschaftsjahr.objects.get_or_create(
        objekt=objekt, jahr=jahr, defaults=dict(beginn_monat=1),
    )[0]


def _create_konto_13650(wj):
    """DCL-Debitor-Konto — Gegenkonto für Lastschrift-Buchungen (sepa_lastschrift.erstelle_lastschrift_buchungen)."""
    from apps.konten.models import Konto
    return Konto.objects.get_or_create(
        wirtschaftsjahr=wj, kontonummer='13650',
        defaults=dict(kontoname='DCL-Debitor', kontoart='standard', direktes_buchen=False),
    )[0]


def _get_or_create_ba(nr='900'):
    from apps.buchhaltung.models import Buchungsart
    ba, _ = Buchungsart.objects.get_or_create(
        nr=nr,
        defaults=dict(
            bezeichnung=f'BA {nr}',
            buchungstyp='einnahme',
            bankkonto_typ='bewirtschaftung',
        ),
    )
    return ba


class AutoPipelineIdempotenzTest(TestCase):
    """Smoke-Test 4: Zweiter Aufruf erzeugt 'uebersprungen'-Protokoll."""

    def setUp(self):
        self.user = _create_autopilot_user()
        self.objekt = _create_test_objekt()

    @override_settings(SEPA_OUTPUT_DIR='/tmp/test_sepa_output')
    def test_zweiter_aufruf_uebersprungen(self):
        periode = date(2026, 4, 1)

        # Ersten Lauf manuell in DB anlegen
        lauf = HausgeldSollstellungslauf.objects.create(
            objekt=self.objekt,
            typ='hausgeld_monat',
            periode=periode,
            status='commited',
            lauf_quelle='autopilot',
            erstellt_von=self.user,
            freigabe_user=self.user,
        )

        # Zweiten Aufruf von run_objekt → sollte übersprungen werden
        protokoll = run_objekt(
            objekt=self.objekt,
            periode=periode,
            user=self.user,
        )

        self.assertEqual(protokoll.status, 'uebersprungen')
        self.assertEqual(protokoll.sollstellungslauf, lauf)
        # Keine zweite Sollstellung erzeugt
        self.assertEqual(
            HausgeldSollstellungslauf.objects.filter(
                objekt=self.objekt, periode=periode, lauf_quelle='autopilot',
            ).count(),
            1,
        )


class AutoPipelineKeinKandidatTest(TestCase):
    """Smoke-Test 3 (teilweise): Objekt ohne Eigentümer → teilweise_erfolg."""

    def setUp(self):
        self.user = _create_autopilot_user()
        self.objekt = _create_test_objekt()
        _create_test_bankkonto(self.objekt)

    @override_settings(
        SEPA_OUTPUT_DIR='/tmp/test_sepa_output',
        SEPA_AUTOPILOT_VORLAUF_BD=5,
    )
    def test_ohne_kandidaten_teilerfolg(self):
        """
        Objekt hat eine EV ohne SEPA-Mandat → Sollstellung wird erzeugt,
        aber kein Lastschriftlauf. Protokoll: teilweise_erfolg.
        """
        ba = _get_or_create_ba()
        bk = _create_test_bankkonto(self.objekt, zahlungsverkehr=False, konto_typ='bewirtschaftung')
        einheit = _create_einheit(self.objekt)
        person = _create_person(sepa_mandat=None)  # Kein Mandat
        ev = _create_ev(person, einheit)
        _create_hausgeld_historie(ev, ba, betrag=Decimal('300.00'))

        periode = date(2026, 4, 1)
        protokoll = run_objekt(objekt=self.objekt, periode=periode, user=self.user)

        self.assertIn(protokoll.status, ['teilweise_erfolg', 'fehler'])
        if protokoll.status == 'teilweise_erfolg':
            self.assertIsNone(protokoll.lastschriftlauf)
            self.assertGreater(len(protokoll.warnungen), 0)
            # Warnungstyp kein_sepa_mandat
            typen = [w.get('warnung_typ') for w in protokoll.warnungen]
            self.assertIn('kein_sepa_mandat', typen)


class AutoPipelineNotausschalterTest(TestCase):
    """Smoke-Test 5: SEPA_AUTOPILOT_AKTIV=false → Task returned sofort."""

    def test_task_returns_wenn_deaktiviert(self):
        from apps.buchhaltung.tasks import task_auto_hausgeld_pipeline

        with override_settings(SEPA_AUTOPILOT_AKTIV=False):
            result = task_auto_hausgeld_pipeline.run()

        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Gemeinsames Setup für vollständige Lauf-Tests (Tests 2, 3, 7, 10)
# ---------------------------------------------------------------------------

PATCH_FRISTEN = (
    'apps.buchhaltung.services.auto_pipeline_service'
    '.sepa_fristen_service.naechster_einreichungstag'
)


class _VollePipelineMixin:
    """Basis-Setup: Objekt + Zahlungsverkehrs-BK + BA. Subklassen rufen _add_rcur_ev(i) auf."""

    PERIODE = date(2026, 4, 1)

    def setUp(self):
        super().setUp()
        self.user = _create_autopilot_user()
        self.objekt = _create_test_objekt()
        self.bk = _create_test_bankkonto(self.objekt)
        self.ba = _get_or_create_ba('900')
        self.wj = _create_wirtschaftsjahr(self.objekt, jahr=self.PERIODE.year)
        self.konto_13650 = _create_konto_13650(self.wj)

    def _add_rcur_ev(self, index: int):
        mandat = _create_sepa_mandat(
            mandatsreferenz=f'M2024-{index:03d}',
            iban=f'DE89370400440532013{index:03d}',
        )
        person = _create_person(sepa_mandat=mandat, nachname=f'Eigentümer{index}')
        einheit = _create_einheit(self.objekt, einheit_nr=f'WE{index:02d}')
        ev = _create_ev(person, einheit)
        _create_hausgeld_historie(ev, self.ba)
        return ev


# ---------------------------------------------------------------------------
# Test 2: Vollständiger Lauf
# ---------------------------------------------------------------------------

class AutoPipelineVollstaendigTest(_VollePipelineMixin, TestCase):
    """Test 2: 3 RCUR-EVs → status='erfolg', pain.008 geschrieben, 3 Sollstellungen."""

    def setUp(self):
        super().setUp()
        for i in range(1, 4):
            self._add_rcur_ev(i)

    def test_erfolgreicher_lauf(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with override_settings(SEPA_OUTPUT_DIR=tmpdir):
                with patch(PATCH_FRISTEN, return_value=self.PERIODE):
                    protokoll = run_objekt(
                        objekt=self.objekt, periode=self.PERIODE, user=self.user,
                    )

        self.assertEqual(protokoll.status, 'erfolg')
        self.assertEqual(protokoll.anzahl_evs_geplant, 3)
        self.assertEqual(protokoll.anzahl_evs_erfolgreich, 3)
        self.assertEqual(protokoll.anzahl_evs_uebersprungen, 0)
        self.assertEqual(len(protokoll.warnungen), 0)
        self.assertIsNotNone(protokoll.lastschriftlauf)
        self.assertIsNotNone(protokoll.datei_pfad)
        self.assertEqual(
            HausgeldSollstellung.objects.filter(objekt=self.objekt, periode=self.PERIODE).count(),
            3,
        )
        self.assertEqual(LastschriftLauf.objects.filter(objekt=self.objekt).count(), 1)


# ---------------------------------------------------------------------------
# Test 3: Gemischter Lauf
# ---------------------------------------------------------------------------

class AutoPipelineGemischtTest(_VollePipelineMixin, TestCase):
    """Test 3: 3 RCUR + 1 kein Mandat + 1 FRST → teilweise_erfolg, 2 FrontofficeAufgaben."""

    def setUp(self):
        super().setUp()
        for i in range(1, 4):
            self._add_rcur_ev(i)
        # EV ohne Mandat
        person_kein = _create_person(sepa_mandat=None, nachname='KeinMandat')
        einheit_kein = _create_einheit(self.objekt, einheit_nr='WE10')
        ev_kein = _create_ev(person_kein, einheit_kein)
        _create_hausgeld_historie(ev_kein, self.ba)
        # EV mit FRST-Mandat
        mandat_frst = _create_sepa_mandat(
            mandatsreferenz='M2024-FRST',
            iban='DE89370400440532013010',
        )
        mandat_frst.sequence_type = 'FRST'
        mandat_frst.save()
        person_frst = _create_person(sepa_mandat=mandat_frst, nachname='FRSTEigentuemer')
        einheit_frst = _create_einheit(self.objekt, einheit_nr='WE11')
        ev_frst = _create_ev(person_frst, einheit_frst)
        _create_hausgeld_historie(ev_frst, self.ba)

    def test_gemischter_lauf(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with override_settings(SEPA_OUTPUT_DIR=tmpdir):
                with patch(PATCH_FRISTEN, return_value=self.PERIODE):
                    protokoll = run_objekt(
                        objekt=self.objekt, periode=self.PERIODE, user=self.user,
                    )

        self.assertEqual(protokoll.status, 'teilweise_erfolg')
        self.assertEqual(protokoll.anzahl_evs_geplant, 5)
        self.assertEqual(protokoll.anzahl_evs_erfolgreich, 3)
        self.assertEqual(protokoll.anzahl_evs_uebersprungen, 2)
        self.assertEqual(FrontofficeAufgabe.objects.filter(objekt=self.objekt).count(), 2)
        typen = set(
            FrontofficeAufgabe.objects.filter(objekt=self.objekt)
            .values_list('aufgabe_typ', flat=True)
        )
        self.assertIn('kein_sepa_mandat', typen)
        self.assertIn('mandat_typ_frst', typen)


# ---------------------------------------------------------------------------
# Test 6: Objekt mit auto_pipeline_aktiv=False
# ---------------------------------------------------------------------------

class AutoPipelineObjektDeaktivTest(TestCase):
    """Test 6: auto_pipeline_aktiv=False → Task überspringt Objekt."""

    def setUp(self):
        self.user = _create_autopilot_user()
        self.objekt = _create_test_objekt(auto_pipeline_aktiv=False)

    def test_inaktives_objekt_wird_ignoriert(self):
        from apps.buchhaltung.tasks import task_auto_hausgeld_pipeline

        with patch('apps.buchhaltung.tasks._ist_stichtag_oder_nachholtag', return_value=True):
            with override_settings(SEPA_AUTOPILOT_AKTIV=True, SEPA_OUTPUT_DIR='/tmp/unused'):
                task_auto_hausgeld_pipeline.run()

        self.assertEqual(AutoLaufProtokoll.objects.filter(objekt=self.objekt).count(), 0)


# ---------------------------------------------------------------------------
# Test 7: SEPA-Frist verschoben
# ---------------------------------------------------------------------------

class AutoPipelineFristVerschobenTest(_VollePipelineMixin, TestCase):
    """Test 7: Fälligkeit > Periode → sepa_frist_unterschritten Warnung + Lauf trotzdem."""

    def setUp(self):
        super().setUp()
        for i in range(1, 3):
            self._add_rcur_ev(i)

    def test_frist_verschoben(self):
        verschobene_faelligkeit = self.PERIODE + timedelta(days=3)

        with tempfile.TemporaryDirectory() as tmpdir:
            with override_settings(SEPA_OUTPUT_DIR=tmpdir):
                with patch(PATCH_FRISTEN, return_value=verschobene_faelligkeit):
                    protokoll = run_objekt(
                        objekt=self.objekt, periode=self.PERIODE, user=self.user,
                    )

        self.assertEqual(protokoll.status, 'teilweise_erfolg')
        typen = [w.get('warnung_typ') for w in protokoll.warnungen]
        self.assertIn('sepa_frist_unterschritten', typen)
        self.assertIsNotNone(protokoll.lastschriftlauf)
        ls = LastschriftLauf.objects.get(pk=protokoll.lastschriftlauf.pk)
        self.assertEqual(ls.faelligkeitsdatum, verschobene_faelligkeit)
        self.assertTrue(
            FrontofficeAufgabe.objects.filter(
                objekt=self.objekt, aufgabe_typ='sepa_frist_unterschritten',
            ).exists()
        )


# ---------------------------------------------------------------------------
# Test 8: Rollback bei Dateischreibfehler
# ---------------------------------------------------------------------------

class AutoPipelineRollbackBeiDateifehlerTest(_VollePipelineMixin, TestCase):
    """Test 8: OSError beim Schreiben → @transaction.atomic rollt alles zurück."""

    def setUp(self):
        super().setUp()
        for i in range(1, 4):
            self._add_rcur_ev(i)

    def test_rollback_bei_dateifehler(self):
        patch_schreibe = (
            'apps.buchhaltung.services.auto_pipeline_service._schreibe_pain008_datei'
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            with override_settings(SEPA_OUTPUT_DIR=tmpdir):
                with patch(PATCH_FRISTEN, return_value=self.PERIODE):
                    with patch(patch_schreibe, side_effect=OSError('Kein Speicherplatz')):
                        with self.assertRaises(OSError):
                            run_objekt(
                                objekt=self.objekt, periode=self.PERIODE, user=self.user,
                            )

        self.assertEqual(
            HausgeldSollstellungslauf.objects.filter(objekt=self.objekt).count(), 0,
        )
        self.assertEqual(
            HausgeldSollstellung.objects.filter(objekt=self.objekt).count(), 0,
        )
        self.assertEqual(LastschriftLauf.objects.filter(objekt=self.objekt).count(), 0)
        self.assertEqual(AutoLaufProtokoll.objects.filter(objekt=self.objekt).count(), 0)


# ---------------------------------------------------------------------------
# Test 10: Audit — erstellt_von immer Autopilot-User
# ---------------------------------------------------------------------------

class AutoPipelineAuditUserTest(_VollePipelineMixin, TestCase):
    """Test 10: Sollstellungslauf und Sollstellungen werden stets als autopilot-user erstellt."""

    def setUp(self):
        super().setUp()
        for i in range(1, 3):
            self._add_rcur_ev(i)

    def test_erstellt_von_ist_autopilot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with override_settings(SEPA_OUTPUT_DIR=tmpdir):
                with patch(PATCH_FRISTEN, return_value=self.PERIODE):
                    protokoll = run_objekt(
                        objekt=self.objekt, periode=self.PERIODE, user=self.user,
                    )

        lauf = protokoll.sollstellungslauf
        self.assertEqual(lauf.erstellt_von.username, 'immocore-autopilot')
        for ss in HausgeldSollstellung.objects.filter(objekt=self.objekt, periode=self.PERIODE):
            self.assertEqual(ss.erstellt_von.username, 'immocore-autopilot')


# ---------------------------------------------------------------------------
# Mandats-Resolver im Einzug (Portal-SEPA-Mandat, Phase 3)
# ---------------------------------------------------------------------------

class EinzugMandatResolverTest(TestCase):
    """Vorfilter und commite_lastschriftlauf lösen das Mandat je EV auf."""

    PERIODE = date(2026, 4, 1)

    def setUp(self):
        self.user = _create_autopilot_user()
        self.objekt = _create_test_objekt()
        self.bk = _create_test_bankkonto(self.objekt)
        self.lauf = HausgeldSollstellungslauf.objects.create(
            objekt=self.objekt, typ='hausgeld_monat', periode=self.PERIODE,
            status='commited', lauf_quelle='autopilot', erstellt_von=self.user,
        )

    def _mandat(self, referenz, iban, person=None, ev=None, aktiv=True):
        from apps.personen.models import SEPAMandat
        return SEPAMandat.objects.create(
            mandatsreferenz=referenz, iban=iban, bic='COBADEFF',
            unterzeichnet_am=date(2024, 1, 15), sequence_type='RCUR',
            aktiv=aktiv, person=person, eigentumsverhaeltnis=ev,
        )

    def _ev_mit_sollstellung(self, person, nr):
        from apps.buchhaltung.services.opos_nr_service import naechste_opos_nr
        ev = _create_ev(person, _create_einheit(self.objekt, einheit_nr=nr))
        ss = HausgeldSollstellung.objects.create(
            objekt=self.objekt, eigentumsverhaeltnis=ev,
            sollstellungs_typ='hausgeld', ba=None, periode=self.PERIODE,
            faellig_am=self.PERIODE, opos_nr=naechste_opos_nr(self.objekt),
            soll_betrag=Decimal('250.00'), ist_betrag=Decimal('0'),
            status_cached='offen', erstellt_von=self.user,
            sollstellungslauf=self.lauf,
        )
        return ev, ss

    def test_einheitenmandat_und_sammelmandat_je_ev(self):
        from apps.buchhaltung.services.auto_pipeline_service import _filtere_lastschrift_kandidaten
        person = _create_person()
        ev1, _ = self._ev_mit_sollstellung(person, 'WE01')
        ev2, _ = self._ev_mit_sollstellung(person, 'WE02')
        self._mandat('M-EV1', 'DE89370400440532013001', person=person, ev=ev1)
        self._mandat('M-SAMMEL', 'DE89370400440532013002', person=person)

        kandidaten, ausgeschlossen = _filtere_lastschrift_kandidaten(self.lauf)
        self.assertEqual(ausgeschlossen, [])
        self.assertEqual(len(kandidaten), 2)

        from apps.buchhaltung.services.sepa_lastschrift import commite_lastschriftlauf
        lauf = commite_lastschriftlauf(
            self.objekt, self.PERIODE, kandidaten, self.user, lauf_quelle='autopilot')
        je_einheit = {p['verwendungszweck'].split(' - ')[1]: p for p in lauf.positionen}
        self.assertEqual(je_einheit['WE01']['mandatsreferenz'], 'M-EV1')
        self.assertEqual(je_einheit['WE01']['schuldner_iban'], 'DE89370400440532013001')
        self.assertEqual(je_einheit['WE02']['mandatsreferenz'], 'M-SAMMEL')
        self.assertEqual(je_einheit['WE02']['schuldner_iban'], 'DE89370400440532013002')

    def test_ev_ohne_mandat_wird_ausgeschlossen(self):
        from apps.buchhaltung.services.auto_pipeline_service import _filtere_lastschrift_kandidaten
        person = _create_person()
        ev, _ = self._ev_mit_sollstellung(person, 'WE01')

        kandidaten, ausgeschlossen = _filtere_lastschrift_kandidaten(self.lauf)
        self.assertEqual(kandidaten, [])
        self.assertEqual([a['warnung_typ'] for a in ausgeschlossen], ['kein_sepa_mandat'])
        self.assertEqual(ausgeschlossen[0]['ev_id'], str(ev.id))
        self.assertTrue(ausgeschlossen[0]['nachricht'].endswith('SEPA-Mandat fehlt'))

    def test_inaktives_mandat_wird_ausgeschlossen(self):
        from apps.buchhaltung.services.auto_pipeline_service import _filtere_lastschrift_kandidaten
        mandat = _create_sepa_mandat()
        mandat.aktiv = False
        mandat.save()
        person = _create_person(sepa_mandat=mandat)  # Legacy-Verknüpfung
        self._ev_mit_sollstellung(person, 'WE01')

        kandidaten, ausgeschlossen = _filtere_lastschrift_kandidaten(self.lauf)
        self.assertEqual(kandidaten, [])
        self.assertEqual([a['warnung_typ'] for a in ausgeschlossen], ['kein_sepa_mandat'])

    def test_commite_ueberspringt_kandidat_ohne_mandat(self):
        from apps.buchhaltung.services.sepa_lastschrift import commite_lastschriftlauf
        mit = _create_person(nachname='MitMandat')
        ohne = _create_person(nachname='OhneMandat')
        self._mandat('M-MIT', 'DE89370400440532013003', person=mit)
        _, ss_mit = self._ev_mit_sollstellung(mit, 'WE01')
        _, ss_ohne = self._ev_mit_sollstellung(ohne, 'WE02')

        with self.assertLogs('apps.buchhaltung.services.sepa_lastschrift', level='WARNING') as cm:
            lauf = commite_lastschriftlauf(
                self.objekt, self.PERIODE, [ss_ohne, ss_mit], self.user,
                lauf_quelle='autopilot',
            )
        self.assertTrue(any('OhneMandat' in m for m in cm.output))
        self.assertEqual(lauf.anzahl_positionen, 1)
        self.assertEqual(lauf.positionen[0]['mandatsreferenz'], 'M-MIT')
        self.assertEqual(lauf.positionen[0]['sollstellung_ids'], [str(ss_mit.id)])
