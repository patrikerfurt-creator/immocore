"""
Smoke-Tests: eigentuemerwechsel_korrektur_service (Wechsel-Spec v1.1, Tests 1-9)
"""
from datetime import date
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.buchhaltung.models import (
    EigentuemerwechselVorgang,
    FrontofficeAufgabe,
    HausgeldSollstellung,
    HausgeldSollstellungslauf,
    SollstellungSplit,
    WechselKorrekturPaar,
)
from apps.buchhaltung.services.eigentuemerwechsel_korrektur_service import (
    vorschau_committen,
    vorschau_erstellen,
)
from apps.buchhaltung.services.korrektur_sollstellung_service import tilge_sollstellung
from apps.buchhaltung.services.opos_nr_service import naechste_opos_nr

User = get_user_model()


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _user(username='wechsel-ersteller'):
    u, _ = User.objects.get_or_create(username=username, defaults={'is_staff': True})
    return u


def _freigabe_user():
    return _user('wechsel-freigeber')


def _create_objekt(kuerzel='WO1'):
    from apps.objekte.models import Objekt
    return Objekt.objects.create(
        objekt_typ='WEG',
        bezeichnung=f'Wechsel-Test-Objekt {kuerzel}',
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


def _create_voreigentuemer_ev(einheit, nachname='Voreigentuemer'):
    from apps.personen.models import Person, EigentumsVerhaeltnis
    person = Person.objects.create(
        person_typ='100', anrede='Herr', vorname='Alt', nachname=nachname,
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


def _create_committed_lauf(objekt, periode, user):
    return HausgeldSollstellungslauf.objects.create(
        objekt=objekt,
        typ='hausgeld_monat',
        periode=periode,
        status='commited',
        erstellt_von=user,
    )


def _create_sollstellung(objekt, ev, ba, lauf, periode, soll_betrag, ist_betrag=Decimal('0')):
    ss = HausgeldSollstellung.objects.create(
        objekt=objekt,
        eigentumsverhaeltnis=ev,
        sollstellungs_typ='hausgeld',
        ba=None,
        periode=periode,
        faellig_am=periode,
        opos_nr=naechste_opos_nr(objekt),
        soll_betrag=soll_betrag,
        ist_betrag=ist_betrag,
        status_cached='ausgeglichen' if ist_betrag == soll_betrag else 'offen',
        sollstellungslauf=lauf,
        erstellt_von=_user(),
    )
    SollstellungSplit.objects.create(sollstellung=ss, ba=ba, betrag=soll_betrag)
    return ss


NEUEIGENTUEMER_DATA = {
    'anrede': 'Frau',
    'vorname': 'Neu',
    'nachname': 'Eigentuemer',
    'email': 'neu@test.example',
}

WECHSEL_DATUM = date(2026, 4, 1)
PERIODEN = [date(2026, 4, 1), date(2026, 5, 1), date(2026, 6, 1)]
BETRAG = Decimal('360.00')


# ---------------------------------------------------------------------------
# Test 1 — Standardfall: 3 Monate, alle gezahlt
# ---------------------------------------------------------------------------

class StandardfallTest(TestCase):
    def setUp(self):
        self.user = _user()
        self.freigabe = _freigabe_user()
        self.objekt = _create_objekt('ST1')
        self.einheit = _create_einheit(self.objekt)
        self.ev = _create_voreigentuemer_ev(self.einheit)
        self.ba = _get_or_create_ba('900')
        self.laeufe = [_create_committed_lauf(self.objekt, p, self.user) for p in PERIODEN]
        self.sollstellungen = [
            _create_sollstellung(self.objekt, self.ev, self.ba, self.laeufe[i], PERIODEN[i], BETRAG, BETRAG)
            for i in range(3)
        ]

    def test_vorschau_erstellt_drei_paare(self):
        vorgang = vorschau_erstellen(self.objekt, self.einheit, WECHSEL_DATUM, NEUEIGENTUEMER_DATA, self.user)
        self.assertEqual(vorgang.status, 'vorschau')
        self.assertEqual(vorgang.korrektur_paare.count(), 3)
        self.assertEqual(vorgang.auszahlungsbetrag, BETRAG * 3)

    def test_commit_erzeugt_korrekturen_und_neuanlagen(self):
        vorgang = vorschau_erstellen(self.objekt, self.einheit, WECHSEL_DATUM, NEUEIGENTUEMER_DATA, self.user)
        vorschau_committen(vorgang, self.freigabe, 'DE89370400440532013000')

        vorgang.refresh_from_db()
        self.assertEqual(vorgang.status, 'freigegeben')

        paare = list(vorgang.korrektur_paare.select_related(
            'korrektur_sollstellung', 'neuanlage_sollstellung'
        ).order_by('periode'))
        self.assertEqual(len(paare), 3)
        for paar in paare:
            self.assertIsNotNone(paar.korrektur_sollstellung)
            self.assertIsNotNone(paar.neuanlage_sollstellung)
            self.assertEqual(paar.korrektur_sollstellung.soll_betrag, -BETRAG)
            self.assertEqual(paar.neuanlage_sollstellung.soll_betrag, BETRAG)

    def test_frontoffice_aufgabe_angelegt(self):
        vorgang = vorschau_erstellen(self.objekt, self.einheit, WECHSEL_DATUM, NEUEIGENTUEMER_DATA, self.user)
        vorschau_committen(vorgang, self.freigabe, 'DE89370400440532013000')
        aufgaben = FrontofficeAufgabe.objects.filter(
            objekt=self.objekt, aufgabe_typ='eigentuemerwechsel_forderung'
        )
        self.assertEqual(aufgaben.count(), 1)


# ---------------------------------------------------------------------------
# Test 2 — Vier-Augen-Constraint
# ---------------------------------------------------------------------------

class VierAugenTest(TestCase):
    def setUp(self):
        self.user = _user()
        self.objekt = _create_objekt('VA1')
        self.einheit = _create_einheit(self.objekt)
        self.ev = _create_voreigentuemer_ev(self.einheit)
        self.ba = _get_or_create_ba('900')
        lauf = _create_committed_lauf(self.objekt, WECHSEL_DATUM, self.user)
        _create_sollstellung(self.objekt, self.ev, self.ba, lauf, WECHSEL_DATUM, BETRAG, BETRAG)
        self.vorgang = vorschau_erstellen(self.objekt, self.einheit, WECHSEL_DATUM, NEUEIGENTUEMER_DATA, self.user)

    def test_gleicher_user_wirft_validation_error(self):
        with self.assertRaises(ValidationError):
            vorschau_committen(self.vorgang, self.user, 'DE89370400440532013000')


# ---------------------------------------------------------------------------
# Test 3 — Teilzahlung: 2 von 3 Monaten bezahlt
# ---------------------------------------------------------------------------

class TeilzahlungTest(TestCase):
    def setUp(self):
        self.user = _user()
        self.freigabe = _freigabe_user()
        self.objekt = _create_objekt('TZ1')
        self.einheit = _create_einheit(self.objekt)
        self.ev = _create_voreigentuemer_ev(self.einheit)
        self.ba = _get_or_create_ba('900')
        perioden = PERIODEN
        ist_betraege = [BETRAG, BETRAG, Decimal('0')]
        self.laeufe = [_create_committed_lauf(self.objekt, p, self.user) for p in perioden]
        self.sollstellungen = [
            _create_sollstellung(self.objekt, self.ev, self.ba, self.laeufe[i], perioden[i], BETRAG, ist_betraege[i])
            for i in range(3)
        ]

    def test_auszahlungsbetrag_nur_gezahlte(self):
        vorgang = vorschau_erstellen(self.objekt, self.einheit, WECHSEL_DATUM, NEUEIGENTUEMER_DATA, self.user)
        self.assertEqual(vorgang.auszahlungsbetrag, BETRAG * 2)

    def test_dritter_monat_nach_commit_offen_und_neutralisiert(self):
        vorgang = vorschau_erstellen(self.objekt, self.einheit, WECHSEL_DATUM, NEUEIGENTUEMER_DATA, self.user)
        vorschau_committen(vorgang, self.freigabe, 'DE89370400440532013000')

        original_juni = self.sollstellungen[2]
        original_juni.refresh_from_db()
        self.assertIsNotNone(original_juni.neutralisiert_durch_opos)

        korrektur_juni = original_juni.neutralisiert_durch_opos
        self.assertEqual(korrektur_juni.sollstellungs_typ, 'korrektur')
        self.assertEqual(korrektur_juni.ist_betrag, Decimal('0'))

        # Beide vom Mahnwesen ausgenommen
        from apps.buchhaltung.models import HausgeldSollstellung
        from django.db.models import F
        mahnbare = HausgeldSollstellung.objects.filter(
            soll_betrag__gt=F('ist_betrag'),
            neutralisiert_durch_opos__isnull=True,
        ).exclude(sollstellungs_typ='korrektur')
        pks = list(mahnbare.values_list('pk', flat=True))
        self.assertNotIn(original_juni.pk, pks)
        self.assertNotIn(korrektur_juni.pk, pks)


# ---------------------------------------------------------------------------
# Test 4 — Wechsel nicht am Monatsersten
# ---------------------------------------------------------------------------

class WechselNichtMonatsersterTest(TestCase):
    def setUp(self):
        self.user = _user()
        self.objekt = _create_objekt('WM1')
        self.einheit = _create_einheit(self.objekt)
        _create_voreigentuemer_ev(self.einheit)

    def test_validierung_fehlschlag(self):
        with self.assertRaises(ValidationError):
            vorschau_erstellen(
                self.objekt, self.einheit, date(2026, 4, 15), NEUEIGENTUEMER_DATA, self.user,
            )


# ---------------------------------------------------------------------------
# Test 5 — Auszahlung unterdrückt
# ---------------------------------------------------------------------------

class AuszahlungUnterdruecktTest(TestCase):
    def setUp(self):
        self.user = _user()
        self.freigabe = _freigabe_user()
        self.objekt = _create_objekt('AU1')
        self.einheit = _create_einheit(self.objekt)
        self.ev = _create_voreigentuemer_ev(self.einheit)
        self.ba = _get_or_create_ba('900')
        lauf = _create_committed_lauf(self.objekt, WECHSEL_DATUM, self.user)
        _create_sollstellung(self.objekt, self.ev, self.ba, lauf, WECHSEL_DATUM, BETRAG, BETRAG)

    def test_commit_mit_unterdrueckung_kein_fehler(self):
        vorgang = vorschau_erstellen(self.objekt, self.einheit, WECHSEL_DATUM, NEUEIGENTUEMER_DATA, self.user)
        vorschau_committen(vorgang, self.freigabe, 'DE89370400440532013000', auszahlung_unterdruecken=True)
        vorgang.refresh_from_db()
        self.assertEqual(vorgang.status, 'freigegeben')
        self.assertTrue(vorgang.auszahlung_unterdruecken)

    def test_frontoffice_aufgabe_neueigentuemer_immer_angelegt(self):
        vorgang = vorschau_erstellen(self.objekt, self.einheit, WECHSEL_DATUM, NEUEIGENTUEMER_DATA, self.user)
        vorschau_committen(vorgang, self.freigabe, 'DE89370400440532013000', auszahlung_unterdruecken=True)
        self.assertEqual(
            FrontofficeAufgabe.objects.filter(
                objekt=self.objekt, aufgabe_typ='eigentuemerwechsel_forderung',
            ).count(),
            1,
        )


# ---------------------------------------------------------------------------
# Test 6 — Wechsel in abgerechneter Periode: Abrechnungsergebnis nicht angefasst
# ---------------------------------------------------------------------------

class AbgerechnetePeriodesTest(TestCase):
    def setUp(self):
        self.user = _user()
        self.freigabe = _freigabe_user()
        self.objekt = _create_objekt('AP1')
        self.einheit = _create_einheit(self.objekt)
        self.ev = _create_voreigentuemer_ev(self.einheit)
        self.ba = _get_or_create_ba('900')
        lauf = _create_committed_lauf(self.objekt, WECHSEL_DATUM, self.user)
        _create_sollstellung(self.objekt, self.ev, self.ba, lauf, WECHSEL_DATUM, BETRAG, BETRAG)

        # Abrechnungsergebnis-Sollstellung für gleiche Periode (andere BA)
        ba_abr = _get_or_create_ba('500')
        self.abrechnung_ss = HausgeldSollstellung.objects.create(
            objekt=self.objekt,
            eigentumsverhaeltnis=self.ev,
            sollstellungs_typ='abrechnungsergebnis',
            ba=ba_abr,
            periode=WECHSEL_DATUM,
            faellig_am=WECHSEL_DATUM,
            opos_nr=naechste_opos_nr(self.objekt),
            soll_betrag=Decimal('150.00'),
            ist_betrag=Decimal('0'),
            status_cached='offen',
            erstellt_von=self.user,
        )

    def test_abrechnungsergebnis_nicht_in_paaren(self):
        vorgang = vorschau_erstellen(self.objekt, self.einheit, WECHSEL_DATUM, NEUEIGENTUEMER_DATA, self.user)
        original_pks = list(
            vorgang.korrektur_paare.values_list('original_sollstellung_id', flat=True)
        )
        self.assertNotIn(self.abrechnung_ss.pk, original_pks)

    def test_abrechnungsergebnis_nach_commit_unveraendert(self):
        vorgang = vorschau_erstellen(self.objekt, self.einheit, WECHSEL_DATUM, NEUEIGENTUEMER_DATA, self.user)
        vorschau_committen(vorgang, self.freigabe, 'DE89370400440532013000')
        self.abrechnung_ss.refresh_from_db()
        self.assertIsNone(self.abrechnung_ss.neutralisiert_durch_opos)


# ---------------------------------------------------------------------------
# Test 7 — Auto-Pipeline-Folge: EV-Lifecycle nach Commit
# ---------------------------------------------------------------------------

class AutoPipelineEVLifecycleTest(TestCase):
    def setUp(self):
        self.user = _user()
        self.freigabe = _freigabe_user()
        self.objekt = _create_objekt('EV1')
        self.einheit = _create_einheit(self.objekt)
        self.voreigentuemer_ev = _create_voreigentuemer_ev(self.einheit)
        self.ba = _get_or_create_ba('900')
        lauf = _create_committed_lauf(self.objekt, WECHSEL_DATUM, self.user)
        _create_sollstellung(self.objekt, self.voreigentuemer_ev, self.ba, lauf, WECHSEL_DATUM, BETRAG, BETRAG)

    def test_ev_lifecycle_nach_commit(self):
        vorgang = vorschau_erstellen(self.objekt, self.einheit, WECHSEL_DATUM, NEUEIGENTUEMER_DATA, self.user)
        vorschau_committen(vorgang, self.freigabe, 'DE89370400440532013000')

        self.voreigentuemer_ev.refresh_from_db()
        neueigentuemer_ev = vorgang.neueigentuemer_ev
        neueigentuemer_ev.refresh_from_db()

        self.assertIsNotNone(self.voreigentuemer_ev.ende)
        self.assertEqual(self.voreigentuemer_ev.ende, WECHSEL_DATUM - __import__('datetime').timedelta(days=1))
        self.assertIsNone(neueigentuemer_ev.ende)

    def test_auto_pipeline_sieht_nur_neueigentuemer(self):
        from apps.personen.models import EigentumsVerhaeltnis
        vorgang = vorschau_erstellen(self.objekt, self.einheit, WECHSEL_DATUM, NEUEIGENTUEMER_DATA, self.user)
        vorschau_committen(vorgang, self.freigabe, 'DE89370400440532013000')

        aktive_evs = EigentumsVerhaeltnis.objects.filter(
            einheit=self.einheit, ende__isnull=True,
        )
        self.assertEqual(aktive_evs.count(), 1)
        self.assertEqual(aktive_evs.first().pk, vorgang.neueigentuemer_ev.pk)


# ---------------------------------------------------------------------------
# Test 8 — Tilgungs-Vorzeichen für Korrektur-Sollstellungen
# ---------------------------------------------------------------------------

class TilgungsVorzeichenTest(TestCase):
    def setUp(self):
        self.user = _user()
        self.freigabe = _freigabe_user()
        self.objekt = _create_objekt('TV1')
        self.einheit = _create_einheit(self.objekt)
        self.ev = _create_voreigentuemer_ev(self.einheit)
        self.ba = _get_or_create_ba('900')
        lauf = _create_committed_lauf(self.objekt, WECHSEL_DATUM, self.user)
        _create_sollstellung(self.objekt, self.ev, self.ba, lauf, WECHSEL_DATUM, BETRAG, BETRAG)

    def test_tilgung_auf_korrektur_negativ(self):
        vorgang = vorschau_erstellen(self.objekt, self.einheit, WECHSEL_DATUM, NEUEIGENTUEMER_DATA, self.user)
        vorschau_committen(vorgang, self.freigabe, 'DE89370400440532013000')

        paar = vorgang.korrektur_paare.select_related('korrektur_sollstellung').first()
        korrektur = paar.korrektur_sollstellung
        self.assertEqual(korrektur.soll_betrag, -BETRAG)

        tilge_sollstellung(korrektur, BETRAG)
        korrektur.refresh_from_db()
        self.assertEqual(korrektur.ist_betrag, -BETRAG)


# ---------------------------------------------------------------------------
# Test 9 — EV-Lifecycle und UniqueConstraint
# ---------------------------------------------------------------------------

class EVLifecycleConstraintTest(TestCase):
    def setUp(self):
        self.user = _user()
        self.freigabe = _freigabe_user()
        self.objekt = _create_objekt('LC1')
        self.einheit = _create_einheit(self.objekt)
        self.voreigentuemer_ev = _create_voreigentuemer_ev(self.einheit)
        self.ba = _get_or_create_ba('900')
        lauf = _create_committed_lauf(self.objekt, WECHSEL_DATUM, self.user)
        _create_sollstellung(self.objekt, self.voreigentuemer_ev, self.ba, lauf, WECHSEL_DATUM, BETRAG, BETRAG)

    def test_unique_constraint_nicht_verletzt(self):
        from apps.personen.models import EigentumsVerhaeltnis
        # Vorher: 1 aktive EV
        self.assertEqual(EigentumsVerhaeltnis.objects.filter(einheit=self.einheit, ende__isnull=True).count(), 1)

        vorgang = vorschau_erstellen(self.objekt, self.einheit, WECHSEL_DATUM, NEUEIGENTUEMER_DATA, self.user)
        # Während Vorschau: Neueigentümer EV hat ende=wechsel_datum, noch immer 1 aktive
        self.assertEqual(EigentumsVerhaeltnis.objects.filter(einheit=self.einheit, ende__isnull=True).count(), 1)

        vorschau_committen(vorgang, self.freigabe, 'DE89370400440532013000')
        # Nach Commit: wieder genau 1 aktive EV (Neueigentümer)
        self.assertEqual(EigentumsVerhaeltnis.objects.filter(einheit=self.einheit, ende__isnull=True).count(), 1)

    def test_audit_alle_paare_vollstaendig(self):
        vorgang = vorschau_erstellen(self.objekt, self.einheit, WECHSEL_DATUM, NEUEIGENTUEMER_DATA, self.user)
        vorschau_committen(vorgang, self.freigabe, 'DE89370400440532013000')

        paare = list(vorgang.korrektur_paare.all())
        for paar in paare:
            self.assertIsNotNone(paar.original_sollstellung_id)
            self.assertIsNotNone(paar.korrektur_sollstellung_id)
            self.assertIsNotNone(paar.neuanlage_sollstellung_id)
