"""
Tests: wirtschaftsplan_beschluss_service (Wirtschaftsplan-Spec v1.2, Phase B)
UC-1 bis UC-4, Validierungs-Tests, CheckConstraint-Tests
"""
import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase, override_settings

from apps.buchhaltung.models import (
    FrontofficeAufgabe,
    HausgeldSollstellung,
    HausgeldSollstellungslauf,
    SollstellungSplit,
    WirtschaftsplanBeschluss,
    WirtschaftsplanKorrekturPaar,
    WirtschaftsplanPosition,
)
from apps.buchhaltung.services.hausgeld_historie_service import setze_neue_saetze
from apps.buchhaltung.services.opos_nr_service import naechste_opos_nr
from apps.buchhaltung.services.wirtschaftsplan_beschluss_service import (
    beschluss_buchen,
    beschluss_erfassen,
    beschluss_stornieren,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _user(username='wp-user'):
    u, _ = User.objects.get_or_create(username=username, defaults={'is_staff': True})
    return u


def _create_objekt(kuerzel='WP1'):
    from apps.objekte.models import Objekt
    return Objekt.objects.create(
        objekt_typ='WEG',
        bezeichnung=f'WP-Test-Objekt {kuerzel}',
        kurzbezeichnung=kuerzel,
        strasse='Teststraße 1',
        plz='60311',
        ort='Frankfurt',
        verwaltung_seit=date(2020, 1, 1),
        glaeubiger_id='DE98ZZZ09999999999',
    )


def _create_einheit(objekt, nr='WE01'):
    from apps.objekte.models import Einheit
    return Einheit.objects.create(
        objekt=objekt,
        einheit_nr=nr,
        einheit_typ='Wohnung',
        lage=f'Lage {nr}',
    )


def _create_ev(einheit, nachname='Eigentuemer'):
    from apps.personen.models import Person, EigentumsVerhaeltnis
    person = Person.objects.create(
        person_typ='100', anrede='Herr', vorname='Test', nachname=nachname,
    )
    return EigentumsVerhaeltnis.objects.create(
        einheit=einheit, person=person, beginn=date(2020, 1, 1), ende=None,
    )


def _get_or_create_ba(nr='900'):
    from apps.buchhaltung.models import Buchungsart
    ba, _ = Buchungsart.objects.get_or_create(
        nr=nr,
        defaults=dict(bezeichnung=f'BA {nr}', buchungstyp='einnahme', bankkonto_typ='bewirtschaftung'),
    )
    return ba


def _create_hausgeld_historie(ev, ba, betrag=Decimal('300.00'), gueltig_ab=date(2025, 1, 1)):
    from apps.personen.models import HausgeldHistorie
    return HausgeldHistorie.objects.create(
        eigentumsverhaeltnis=ev,
        ba=ba,
        betrag=betrag,
        gueltig_ab=gueltig_ab,
        quelle='import',
        import_referenz='test-data',
        erstellt_von=_user(),
    )


def _create_committed_lauf(objekt, periode):
    return HausgeldSollstellungslauf.objects.create(
        objekt=objekt,
        typ='hausgeld_monat',
        periode=periode,
        status='commited',
        erstellt_von=_user(),
    )


def _create_sollstellung(objekt, ev, ba, lauf, periode, soll_betrag):
    ss = HausgeldSollstellung.objects.create(
        objekt=objekt,
        eigentumsverhaeltnis=ev,
        sollstellungs_typ='hausgeld',
        ba=None,
        periode=periode,
        faellig_am=periode,
        opos_nr=naechste_opos_nr(objekt),
        soll_betrag=soll_betrag,
        ist_betrag=Decimal('0'),
        status_cached='offen',
        sollstellungslauf=lauf,
        erstellt_von=_user(),
    )
    SollstellungSplit.objects.create(sollstellung=ss, ba=ba, betrag=soll_betrag)
    return ss


def _build_position(ev, ba, betrag):
    return {'eigentumsverhaeltnis': ev, 'buchungsart': ba, 'betrag': betrag}


# ---------------------------------------------------------------------------
# UC-1: Vorausschauender Beschluss
# ---------------------------------------------------------------------------

class UC1VorausschauendTest(TestCase):
    """UC-1: Beschluss für zukünftigen Monat — keine Korrektur-Paare, HausgeldHistorie neu."""

    def setUp(self):
        self.user = _user()
        self.objekt = _create_objekt('UC1')
        self.einheit = _create_einheit(self.objekt)
        self.ev = _create_ev(self.einheit)
        self.ba = _get_or_create_ba()
        _create_hausgeld_historie(self.ev, self.ba, betrag=Decimal('300.00'))

    def test_vorausschauender_beschluss(self):
        beschluss = beschluss_erfassen(
            objekt=self.objekt,
            beschluss_typ='wirtschaftsplan',
            beschluss_datum=date(2026, 12, 1),
            wirtschaftsplan_beginn=date(2027, 1, 1),
            gesamt_volumen=Decimal('4200.00'),
            positionen_data=[_build_position(self.ev, self.ba, Decimal('350.00'))],
            user=self.user,
        )
        self.assertEqual(beschluss.status, 'erfasst')

        stats = beschluss_buchen(beschluss, self.user)

        beschluss.refresh_from_db()
        self.assertEqual(beschluss.status, 'gebucht')
        self.assertEqual(stats['evs_aktualisiert'], 1)
        self.assertEqual(stats['sollstellungen_korrigiert'], 0)
        self.assertEqual(stats['saldenmitteilungen_erzeugt'], 0)

        from apps.personen.models import HausgeldHistorie
        neuer_eintrag = HausgeldHistorie.objects.get(
            eigentumsverhaeltnis=self.ev,
            ba=self.ba,
            gueltig_ab=date(2027, 1, 1),
        )
        self.assertEqual(neuer_eintrag.betrag, Decimal('350.00'))
        self.assertEqual(neuer_eintrag.quelle, 'beschluss')
        self.assertEqual(neuer_eintrag.beschluss, beschluss)

        alter_eintrag = HausgeldHistorie.objects.get(
            eigentumsverhaeltnis=self.ev,
            ba=self.ba,
            gueltig_ab=date(2025, 1, 1),
        )
        self.assertEqual(alter_eintrag.gueltig_bis, date(2026, 12, 31))

        self.assertEqual(WirtschaftsplanKorrekturPaar.objects.count(), 0)
        self.assertEqual(FrontofficeAufgabe.objects.filter(aufgabe_typ='saldenmitteilung_wirtschaftsplan').count(), 0)


# ---------------------------------------------------------------------------
# UC-2: Rückwirkender Beschluss
# ---------------------------------------------------------------------------

class UC2RueckwirkendTest(TestCase):
    """UC-2: Beschluss für vergangenen Monat — Korrektur-Paare, Saldenmitteilung."""

    BEGINN = date(2026, 1, 1)
    BETRAG_ALT = Decimal('300.00')
    BETRAG_NEU = Decimal('350.00')
    PERIODEN = [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1), date(2026, 4, 1)]

    def setUp(self):
        self.user = _user()
        self.objekt = _create_objekt('UC2')
        self.einheit = _create_einheit(self.objekt)
        self.ev = _create_ev(self.einheit)
        self.ba = _get_or_create_ba()
        _create_hausgeld_historie(self.ev, self.ba, betrag=self.BETRAG_ALT, gueltig_ab=self.BEGINN)

        for periode in self.PERIODEN:
            lauf = _create_committed_lauf(self.objekt, periode)
            _create_sollstellung(self.objekt, self.ev, self.ba, lauf, periode, self.BETRAG_ALT)

    def test_rueckwirkender_beschluss(self):
        beschluss = beschluss_erfassen(
            objekt=self.objekt,
            beschluss_typ='wirtschaftsplan',
            beschluss_datum=date(2026, 4, 18),
            wirtschaftsplan_beginn=self.BEGINN,
            gesamt_volumen=Decimal('4200.00'),
            positionen_data=[_build_position(self.ev, self.ba, self.BETRAG_NEU)],
            user=self.user,
        )
        stats = beschluss_buchen(beschluss, self.user)

        self.assertEqual(stats['sollstellungen_korrigiert'], 4)
        self.assertEqual(WirtschaftsplanKorrekturPaar.objects.filter(beschluss=beschluss).count(), 4)

        differenz_je_periode = self.BETRAG_NEU - self.BETRAG_ALT
        erwartete_differenz = differenz_je_periode * 4
        self.assertEqual(stats['gesamtdifferenz'], erwartete_differenz)
        self.assertEqual(stats['saldenmitteilungen_erzeugt'], 1)

        aufgabe = FrontofficeAufgabe.objects.get(
            objekt=self.objekt, aufgabe_typ='saldenmitteilung_wirtschaftsplan'
        )
        self.assertIn('+200.00', aufgabe.beschreibung)
        self.assertIn('2026-01-01', aufgabe.beschreibung)

    def test_originale_sind_neutralisiert(self):
        beschluss = beschluss_erfassen(
            objekt=self.objekt,
            beschluss_typ='wirtschaftsplan',
            beschluss_datum=date(2026, 4, 18),
            wirtschaftsplan_beginn=self.BEGINN,
            gesamt_volumen=Decimal('4200.00'),
            positionen_data=[_build_position(self.ev, self.ba, self.BETRAG_NEU)],
            user=self.user,
        )
        beschluss_buchen(beschluss, self.user)

        for periode in self.PERIODEN:
            original = HausgeldSollstellung.objects.get(
                eigentumsverhaeltnis=self.ev,
                periode=periode,
                sollstellungs_typ='hausgeld',
                soll_betrag=self.BETRAG_ALT,
            )
            self.assertIsNotNone(original.neutralisiert_durch_opos_id)

    def test_keine_doppelkorrektur(self):
        """idempotency: zweiter Buchungsversuch soll 0 neue Paare erzeugen."""
        beschluss = beschluss_erfassen(
            objekt=self.objekt,
            beschluss_typ='wirtschaftsplan',
            beschluss_datum=date(2026, 4, 18),
            wirtschaftsplan_beginn=self.BEGINN,
            gesamt_volumen=Decimal('4200.00'),
            positionen_data=[_build_position(self.ev, self.ba, self.BETRAG_NEU)],
            user=self.user,
        )
        beschluss_buchen(beschluss, self.user)

        beschluss2 = beschluss_erfassen(
            objekt=self.objekt,
            beschluss_typ='wirtschaftsplan',
            beschluss_datum=date(2026, 5, 1),
            wirtschaftsplan_beginn=self.BEGINN,
            gesamt_volumen=Decimal('4200.00'),
            positionen_data=[_build_position(self.ev, self.ba, self.BETRAG_NEU)],
            user=self.user,
        )
        stats2 = beschluss_buchen(beschluss2, self.user)
        self.assertEqual(stats2['sollstellungen_korrigiert'], 0)


# ---------------------------------------------------------------------------
# UC-3: Folge-Beschluss schließt alten ab
# ---------------------------------------------------------------------------

class UC3FolgeBeschlussTest(TestCase):
    """UC-3: Folge-Beschluss setzt gueltig_bis des alten Eintrags."""

    def setUp(self):
        self.user = _user()
        self.objekt = _create_objekt('UC3')
        self.einheit = _create_einheit(self.objekt)
        self.ev = _create_ev(self.einheit)
        self.ba = _get_or_create_ba()
        _create_hausgeld_historie(self.ev, self.ba, betrag=Decimal('300.00'), gueltig_ab=date(2026, 1, 1))

    def test_folge_beschluss_schliesst_vorherigen(self):
        b1 = beschluss_erfassen(
            objekt=self.objekt,
            beschluss_typ='wirtschaftsplan',
            beschluss_datum=date(2026, 12, 1),
            wirtschaftsplan_beginn=date(2027, 1, 1),
            gesamt_volumen=Decimal('4200.00'),
            positionen_data=[_build_position(self.ev, self.ba, Decimal('350.00'))],
            user=self.user,
        )
        beschluss_buchen(b1, self.user)

        b2 = beschluss_erfassen(
            objekt=self.objekt,
            beschluss_typ='wirtschaftsplan',
            beschluss_datum=date(2027, 11, 1),
            wirtschaftsplan_beginn=date(2028, 1, 1),
            gesamt_volumen=Decimal('4800.00'),
            positionen_data=[_build_position(self.ev, self.ba, Decimal('400.00'))],
            user=self.user,
        )
        beschluss_buchen(b2, self.user)

        from apps.personen.models import HausgeldHistorie
        eintrag_2027 = HausgeldHistorie.objects.get(
            eigentumsverhaeltnis=self.ev, ba=self.ba, gueltig_ab=date(2027, 1, 1)
        )
        self.assertEqual(eintrag_2027.gueltig_bis, date(2027, 12, 31))

        eintrag_2028 = HausgeldHistorie.objects.get(
            eigentumsverhaeltnis=self.ev, ba=self.ba, gueltig_ab=date(2028, 1, 1)
        )
        self.assertIsNone(eintrag_2028.gueltig_bis)
        self.assertEqual(eintrag_2028.betrag, Decimal('400.00'))


# ---------------------------------------------------------------------------
# UC-4: Umlaufbeschluss-Stundung
# ---------------------------------------------------------------------------

class UC4StundungTest(TestCase):
    """UC-4: Umlaufbeschluss-Stundung → FrontofficeAufgabe stundung_laeuft_ab."""

    def setUp(self):
        self.user = _user()
        self.objekt = _create_objekt('UC4')
        self.einheit = _create_einheit(self.objekt)
        self.ev = _create_ev(self.einheit)
        self.ba = _get_or_create_ba()
        _create_hausgeld_historie(self.ev, self.ba, betrag=Decimal('300.00'))

    def test_stundung_aufgabe_wird_erzeugt(self):
        beschluss = beschluss_erfassen(
            objekt=self.objekt,
            beschluss_typ='umlaufbeschluss_stundung',
            beschluss_datum=date(2027, 3, 1),
            wirtschaftsplan_beginn=date(2027, 4, 1),
            wirtschaftsplan_ende=date(2027, 8, 31),
            positionen_data=[_build_position(self.ev, self.ba, Decimal('150.00'))],
            user=self.user,
        )
        beschluss_buchen(beschluss, self.user)

        aufgabe = FrontofficeAufgabe.objects.get(
            objekt=self.objekt, aufgabe_typ='stundung_laeuft_ab'
        )
        self.assertIn('2027-08-31', aufgabe.beschreibung)

    def test_stundung_ohne_ende_keine_aufgabe(self):
        """Stundung ohne wirtschaftsplan_ende → keine stundung_laeuft_ab-Aufgabe."""
        beschluss = beschluss_erfassen(
            objekt=self.objekt,
            beschluss_typ='umlaufbeschluss_sonstig',
            beschluss_datum=date(2027, 3, 1),
            wirtschaftsplan_beginn=date(2027, 4, 1),
            positionen_data=[_build_position(self.ev, self.ba, Decimal('150.00'))],
            user=self.user,
        )
        beschluss_buchen(beschluss, self.user)

        self.assertEqual(
            FrontofficeAufgabe.objects.filter(aufgabe_typ='stundung_laeuft_ab').count(), 0
        )


# ---------------------------------------------------------------------------
# Validierungs-Tests
# ---------------------------------------------------------------------------

class ValidierungsTest(TestCase):

    def setUp(self):
        self.user = _user()
        self.objekt = _create_objekt('VAL')
        self.einheit = _create_einheit(self.objekt)
        self.ev = _create_ev(self.einheit)
        self.ba = _get_or_create_ba()

    def test_beginn_nicht_monatserster_fehler(self):
        with self.assertRaises(ValidationError):
            beschluss_erfassen(
                objekt=self.objekt,
                beschluss_typ='wirtschaftsplan',
                beschluss_datum=date(2026, 12, 1),
                wirtschaftsplan_beginn=date(2027, 1, 15),
                gesamt_volumen=Decimal('4200.00'),
                positionen_data=[_build_position(self.ev, self.ba, Decimal('350.00'))],
                user=self.user,
            )

    def test_ende_nicht_monatsletzter_fehler(self):
        with self.assertRaises(ValidationError):
            beschluss_erfassen(
                objekt=self.objekt,
                beschluss_typ='umlaufbeschluss_stundung',
                beschluss_datum=date(2026, 12, 1),
                wirtschaftsplan_beginn=date(2027, 1, 1),
                wirtschaftsplan_ende=date(2027, 8, 15),
                positionen_data=[_build_position(self.ev, self.ba, Decimal('150.00'))],
                user=self.user,
            )

    def test_wirtschaftsplan_ohne_gesamt_volumen_fehler(self):
        with self.assertRaises(ValidationError):
            beschluss_erfassen(
                objekt=self.objekt,
                beschluss_typ='wirtschaftsplan',
                beschluss_datum=date(2026, 12, 1),
                wirtschaftsplan_beginn=date(2027, 1, 1),
                gesamt_volumen=None,
                positionen_data=[_build_position(self.ev, self.ba, Decimal('350.00'))],
                user=self.user,
            )

    def test_stundung_ohne_ende_fehler(self):
        with self.assertRaises(ValidationError):
            beschluss_erfassen(
                objekt=self.objekt,
                beschluss_typ='umlaufbeschluss_stundung',
                beschluss_datum=date(2026, 12, 1),
                wirtschaftsplan_beginn=date(2027, 1, 1),
                wirtschaftsplan_ende=None,
                positionen_data=[_build_position(self.ev, self.ba, Decimal('150.00'))],
                user=self.user,
            )

    def test_gesamtvolumen_abweichung_fehler(self):
        with self.assertRaises(ValidationError):
            beschluss_erfassen(
                objekt=self.objekt,
                beschluss_typ='wirtschaftsplan',
                beschluss_datum=date(2026, 12, 1),
                wirtschaftsplan_beginn=date(2027, 1, 1),
                gesamt_volumen=Decimal('9999.00'),
                positionen_data=[_build_position(self.ev, self.ba, Decimal('350.00'))],
                user=self.user,
            )

    def test_buchen_status_nicht_erfasst_fehler(self):
        beschluss = beschluss_erfassen(
            objekt=self.objekt,
            beschluss_typ='wirtschaftsplan',
            beschluss_datum=date(2026, 12, 1),
            wirtschaftsplan_beginn=date(2027, 1, 1),
            gesamt_volumen=Decimal('4200.00'),
            positionen_data=[_build_position(self.ev, self.ba, Decimal('350.00'))],
            user=self.user,
        )
        beschluss_buchen(beschluss, self.user)

        with self.assertRaises(ValidationError):
            beschluss_buchen(beschluss, self.user)

    def test_gobd_storno_nach_buchung_fehler(self):
        beschluss = beschluss_erfassen(
            objekt=self.objekt,
            beschluss_typ='wirtschaftsplan',
            beschluss_datum=date(2026, 12, 1),
            wirtschaftsplan_beginn=date(2027, 1, 1),
            gesamt_volumen=Decimal('4200.00'),
            positionen_data=[_build_position(self.ev, self.ba, Decimal('350.00'))],
            user=self.user,
        )
        beschluss_buchen(beschluss, self.user)

        with self.assertRaises(ValidationError):
            beschluss_stornieren(beschluss, self.user, 'Test-Grund')

    def test_stornieren_aus_erfasst_ok(self):
        beschluss = beschluss_erfassen(
            objekt=self.objekt,
            beschluss_typ='wirtschaftsplan',
            beschluss_datum=date(2026, 12, 1),
            wirtschaftsplan_beginn=date(2027, 1, 1),
            gesamt_volumen=Decimal('4200.00'),
            positionen_data=[_build_position(self.ev, self.ba, Decimal('350.00'))],
            user=self.user,
        )
        beschluss_stornieren(beschluss, self.user, 'Fehleingabe')
        beschluss.refresh_from_db()
        self.assertEqual(beschluss.status, 'storniert')


# ---------------------------------------------------------------------------
# CheckConstraint-Tests
# ---------------------------------------------------------------------------

class CheckConstraintQuelleTest(TestCase):

    def setUp(self):
        self.user = _user()
        self.objekt = _create_objekt('CC1')
        self.einheit = _create_einheit(self.objekt)
        self.ev = _create_ev(self.einheit)
        self.ba = _get_or_create_ba()

    def test_quelle_beschluss_ohne_beschluss_fk_fehler(self):
        from apps.personen.models import HausgeldHistorie
        with self.assertRaises(IntegrityError):
            HausgeldHistorie.objects.create(
                eigentumsverhaeltnis=self.ev,
                ba=self.ba,
                betrag=Decimal('300.00'),
                gueltig_ab=date(2027, 1, 1),
                quelle='beschluss',
                beschluss=None,
                import_referenz=None,
                erstellt_von=self.user,
            )

    def test_quelle_import_ohne_referenz_fehler(self):
        from apps.personen.models import HausgeldHistorie
        with self.assertRaises(IntegrityError):
            HausgeldHistorie.objects.create(
                eigentumsverhaeltnis=self.ev,
                ba=self.ba,
                betrag=Decimal('300.00'),
                gueltig_ab=date(2027, 1, 1),
                quelle='import',
                beschluss=None,
                import_referenz=None,
                erstellt_von=self.user,
            )


# ---------------------------------------------------------------------------
# Feature-Flag-Tests
# ---------------------------------------------------------------------------

class FeatureFlagTest(TestCase):

    def setUp(self):
        self.user = _user()
        self.objekt = _create_objekt('FF1')
        self.einheit = _create_einheit(self.objekt)
        self.ev = _create_ev(self.einheit)
        self.ba = _get_or_create_ba()

    @override_settings(HAUSGELD_IMPORT_QUELLE_ERLAUBT=True)
    def test_flag_aktiv_erlaubt_import(self):
        ergebnisse = setze_neue_saetze(
            ev=self.ev,
            gueltig_ab=date(2026, 1, 1),
            saetze_je_ba=[(self.ba, Decimal('300.00'))],
            quelle='import',
            beschluss=None,
            import_referenz='test-import',
            user=self.user,
        )
        self.assertEqual(len(ergebnisse), 1)
        self.assertEqual(ergebnisse[0].quelle, 'import')

    @override_settings(HAUSGELD_IMPORT_QUELLE_ERLAUBT=False)
    def test_flag_inaktiv_wirft_validationerror(self):
        with self.assertRaises(ValidationError):
            setze_neue_saetze(
                ev=self.ev,
                gueltig_ab=date(2026, 1, 1),
                saetze_je_ba=[(self.ba, Decimal('300.00'))],
                quelle='import',
                beschluss=None,
                import_referenz='test-import',
                user=self.user,
            )
