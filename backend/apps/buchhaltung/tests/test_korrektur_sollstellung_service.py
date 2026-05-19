"""
Unit-Tests: korrektur_sollstellung_service (Spec v1.2)
"""
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from apps.buchhaltung.models import HausgeldSollstellung, SollstellungSplit
from apps.buchhaltung.services.korrektur_sollstellung_service import (
    get_korrektur_vorgang,
    korrigiere_sollstellung,
    tilge_sollstellung,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _user():
    u, _ = User.objects.get_or_create(
        username='test-korrektur',
        defaults={'is_staff': True},
    )
    return u


def _create_objekt():
    from apps.objekte.models import Objekt
    return Objekt.objects.create(
        objekt_typ='WEG',
        bezeichnung='Korrektur-Test-Objekt',
        kurzbezeichnung='KTO',
        strasse='Teststraße 1',
        plz='60311',
        ort='Frankfurt',
        verwaltung_seit=date(2020, 1, 1),
        glaeubiger_id='DE98ZZZ09999999999',
    )


def _create_ev(objekt, einheit_nr='WE01', nachname='Eigentümer'):
    from apps.objekte.models import Einheit
    from apps.personen.models import Person, EigentumsVerhaeltnis
    einheit = Einheit.objects.create(
        objekt=objekt,
        einheit_nr=einheit_nr,
        einheit_typ='Wohnung',
        lage=f'Lage {einheit_nr}',
    )
    person = Person.objects.create(
        person_typ='100',
        anrede='Herr',
        vorname='Max',
        nachname=nachname,
    )
    return EigentumsVerhaeltnis.objects.create(
        person=person,
        einheit=einheit,
        beginn=date(2020, 1, 1),
    )


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


def _create_sollstellung(objekt, ev, ba, betrag=Decimal('250.00'), user=None):
    """Legt eine Hausgeld-Sollstellung mit einem Split an."""
    from apps.buchhaltung.services.opos_nr_service import naechste_opos_nr
    if user is None:
        user = _user()
    ss = HausgeldSollstellung.objects.create(
        objekt=objekt,
        eigentumsverhaeltnis=ev,
        sollstellungs_typ='hausgeld',
        ba=None,
        periode=date(2026, 4, 1),
        faellig_am=date(2026, 4, 1),
        opos_nr=naechste_opos_nr(objekt),
        soll_betrag=betrag,
        ist_betrag=Decimal('0'),
        status_cached='offen',
        erstellt_von=user,
    )
    SollstellungSplit.objects.create(
        sollstellung=ss,
        ba=ba,
        betrag=betrag,
    )
    return ss


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class KorrigiereCloneTest(TestCase):
    """neue_splits=None: Splits 1:1 geklont (Eigentümerwechsel-Pattern)."""

    def setUp(self):
        self.user = _user()
        self.objekt = _create_objekt()
        self.ba = _get_or_create_ba('900')
        self.ev_alt = _create_ev(self.objekt, 'WE01', 'Alt')
        self.ev_neu = _create_ev(self.objekt, 'WE02', 'Neu')
        self.original = _create_sollstellung(
            self.objekt, self.ev_alt, self.ba, Decimal('300.00'), self.user,
        )
        self.vorgang_id = uuid4()

    def test_gibt_korrektur_und_neuanlage_zurueck(self):
        korrektur, neuanlage = korrigiere_sollstellung(
            original=self.original,
            neue_eigentumsverhaeltnis=self.ev_neu,
            neue_splits=None,
            korrektur_grund='eigentuemerwechsel',
            korrektur_vorgang_id=self.vorgang_id,
            user=self.user,
        )
        self.assertIsInstance(korrektur, HausgeldSollstellung)
        self.assertIsInstance(neuanlage, HausgeldSollstellung)

    def test_korrektur_hat_negierte_splits(self):
        korrektur, _ = korrigiere_sollstellung(
            original=self.original,
            neue_eigentumsverhaeltnis=self.ev_neu,
            neue_splits=None,
            korrektur_grund='eigentuemerwechsel',
            korrektur_vorgang_id=self.vorgang_id,
            user=self.user,
        )
        self.assertEqual(korrektur.sollstellungs_typ, 'korrektur')
        self.assertEqual(korrektur.soll_betrag, -Decimal('300.00'))
        split = korrektur.splits.get()
        self.assertEqual(split.betrag, -Decimal('300.00'))
        self.assertEqual(split.ba, self.ba)

    def test_neuanlage_hat_geklonte_splits(self):
        _, neuanlage = korrigiere_sollstellung(
            original=self.original,
            neue_eigentumsverhaeltnis=self.ev_neu,
            neue_splits=None,
            korrektur_grund='eigentuemerwechsel',
            korrektur_vorgang_id=self.vorgang_id,
            user=self.user,
        )
        self.assertEqual(neuanlage.eigentumsverhaeltnis, self.ev_neu)
        self.assertEqual(neuanlage.soll_betrag, Decimal('300.00'))
        split = neuanlage.splits.get()
        self.assertEqual(split.betrag, Decimal('300.00'))
        self.assertEqual(split.ba, self.ba)

    def test_original_wird_verkettet(self):
        korrektur, _ = korrigiere_sollstellung(
            original=self.original,
            neue_eigentumsverhaeltnis=self.ev_neu,
            neue_splits=None,
            korrektur_grund='eigentuemerwechsel',
            korrektur_vorgang_id=self.vorgang_id,
            user=self.user,
        )
        self.original.refresh_from_db()
        self.assertEqual(self.original.neutralisiert_durch_opos, korrektur)
        self.assertEqual(korrektur.neutralisiert_opos_nr, self.original)

    def test_korrektur_vorgang_felder_gesetzt(self):
        korrektur, neuanlage = korrigiere_sollstellung(
            original=self.original,
            neue_eigentumsverhaeltnis=self.ev_neu,
            neue_splits=None,
            korrektur_grund='eigentuemerwechsel',
            korrektur_vorgang_id=self.vorgang_id,
            user=self.user,
        )
        self.assertEqual(korrektur.korrektur_grund, 'eigentuemerwechsel')
        self.assertEqual(korrektur.korrektur_vorgang_id, self.vorgang_id)
        self.assertEqual(neuanlage.korrektur_grund, 'eigentuemerwechsel')
        self.assertEqual(neuanlage.korrektur_vorgang_id, self.vorgang_id)


class KorrigiereNeueSplitsTest(TestCase):
    """neue_splits=[(ba, betrag)]: Splits aus Liste (Wirtschaftsplan-Pattern)."""

    def setUp(self):
        self.user = _user()
        self.objekt = _create_objekt()
        self.ba = _get_or_create_ba('900')
        self.ev_alt = _create_ev(self.objekt, 'WE01', 'Alt')
        self.ev_neu = _create_ev(self.objekt, 'WE02', 'Neu')
        self.original = _create_sollstellung(
            self.objekt, self.ev_alt, self.ba, Decimal('250.00'), self.user,
        )

    def test_neuanlage_hat_neue_splits(self):
        ba2, _ = __import__('apps.buchhaltung.models', fromlist=['Buchungsart']).Buchungsart.objects.get_or_create(
            nr='910',
            defaults=dict(bezeichnung='BA 910', buchungstyp='einnahme', bankkonto_typ='bewirtschaftung'),
        )
        neue_splits = [(self.ba, Decimal('200.00')), (ba2, Decimal('50.00'))]

        _, neuanlage = korrigiere_sollstellung(
            original=self.original,
            neue_eigentumsverhaeltnis=self.ev_neu,
            neue_splits=neue_splits,
            korrektur_grund='wirtschaftsplan_aenderung',
            korrektur_vorgang_id=uuid4(),
            user=self.user,
        )

        self.assertEqual(neuanlage.soll_betrag, Decimal('250.00'))
        splits = list(neuanlage.splits.order_by('betrag'))
        self.assertEqual(len(splits), 2)
        betraege = {s.ba_id: s.betrag for s in splits}
        self.assertEqual(betraege[self.ba.pk], Decimal('200.00'))
        self.assertEqual(betraege[ba2.pk], Decimal('50.00'))


class IdempotenzTest(TestCase):
    """Original darf nur einmal neutralisiert werden."""

    def setUp(self):
        self.user = _user()
        self.objekt = _create_objekt()
        self.ba = _get_or_create_ba('900')
        self.ev_alt = _create_ev(self.objekt, 'WE01', 'Alt')
        self.ev_neu = _create_ev(self.objekt, 'WE02', 'Neu')
        self.original = _create_sollstellung(
            self.objekt, self.ev_alt, self.ba, Decimal('250.00'), self.user,
        )

    def test_zweite_korrektur_wirft_validation_error(self):
        vorgang_id = uuid4()
        korrigiere_sollstellung(
            original=self.original,
            neue_eigentumsverhaeltnis=self.ev_neu,
            neue_splits=None,
            korrektur_grund='eigentuemerwechsel',
            korrektur_vorgang_id=vorgang_id,
            user=self.user,
        )
        self.original.refresh_from_db()

        with self.assertRaises(ValidationError):
            korrigiere_sollstellung(
                original=self.original,
                neue_eigentumsverhaeltnis=self.ev_neu,
                neue_splits=None,
                korrektur_grund='eigentuemerwechsel',
                korrektur_vorgang_id=uuid4(),
                user=self.user,
            )


class UngueltigerGrundTest(TestCase):
    """Ungültiger korrektur_grund → ValidationError."""

    def setUp(self):
        self.user = _user()
        self.objekt = _create_objekt()
        self.ba = _get_or_create_ba('900')
        self.ev = _create_ev(self.objekt, 'WE01', 'Test')
        self.original = _create_sollstellung(
            self.objekt, self.ev, self.ba, Decimal('200.00'), self.user,
        )

    def test_unbekannter_grund_wirft_validation_error(self):
        with self.assertRaises(ValidationError):
            korrigiere_sollstellung(
                original=self.original,
                neue_eigentumsverhaeltnis=self.ev,
                neue_splits=None,
                korrektur_grund='unbekannt',
                korrektur_vorgang_id=uuid4(),
                user=self.user,
            )


# ---------------------------------------------------------------------------
# Smoke-Test 5 — CheckConstraint negative_betrag_nur_korrektur
# ---------------------------------------------------------------------------

class CheckConstraintNegativBetragTest(TestCase):
    """Smoke-Test 5: soll_betrag < 0 bei typ != 'korrektur' → IntegrityError."""

    def setUp(self):
        self.user = _user()
        self.objekt = _create_objekt()
        self.ba = _get_or_create_ba('900')
        self.ev = _create_ev(self.objekt, 'WE01', 'ConstraintTest')

    def test_negativer_betrag_bei_hausgeld_wirft_integrity_error(self):
        from apps.buchhaltung.services.opos_nr_service import naechste_opos_nr
        with self.assertRaises(IntegrityError):
            HausgeldSollstellung.objects.create(
                objekt=self.objekt,
                eigentumsverhaeltnis=self.ev,
                sollstellungs_typ='hausgeld',
                ba=None,
                periode=date(2026, 4, 1),
                faellig_am=date(2026, 4, 1),
                opos_nr=naechste_opos_nr(self.objekt),
                soll_betrag=Decimal('-100.00'),
                ist_betrag=Decimal('0'),
                status_cached='offen',
                erstellt_von=self.user,
            )


# ---------------------------------------------------------------------------
# Smoke-Test 6 — CheckConstraint korrektur_grund_consistency
# ---------------------------------------------------------------------------

class CheckConstraintKorrekturGrundTest(TestCase):
    """Smoke-Test 6: sollstellungs_typ='korrektur' ohne korrektur_grund → IntegrityError."""

    def setUp(self):
        self.user = _user()
        self.objekt = _create_objekt()
        self.ev = _create_ev(self.objekt, 'WE01', 'ConsistencyTest')

    def test_korrektur_ohne_grund_wirft_integrity_error(self):
        from apps.buchhaltung.services.opos_nr_service import naechste_opos_nr
        with self.assertRaises(IntegrityError):
            HausgeldSollstellung.objects.create(
                objekt=self.objekt,
                eigentumsverhaeltnis=self.ev,
                sollstellungs_typ='korrektur',
                ba=None,
                periode=date(2026, 4, 1),
                faellig_am=date(2026, 4, 1),
                opos_nr=naechste_opos_nr(self.objekt),
                soll_betrag=Decimal('-100.00'),
                ist_betrag=Decimal('0'),
                status_cached='offen',
                korrektur_grund=None,
                korrektur_vorgang_id=None,
                erstellt_von=self.user,
            )


# ---------------------------------------------------------------------------
# Smoke-Test 8 — Tilgungs-Vorzeichen für Korrektur-Sollstellungen
# ---------------------------------------------------------------------------

class TilgungVorzeichenTest(TestCase):
    """Smoke-Test 8: tilge_sollstellung auf Korrektur (soll_betrag < 0) → ist_betrag negativ."""

    def setUp(self):
        self.user = _user()
        self.objekt = _create_objekt()
        self.ba = _get_or_create_ba('900')
        self.ev_alt = _create_ev(self.objekt, 'WE01', 'VorzeichenAlt')
        self.ev_neu = _create_ev(self.objekt, 'WE02', 'VorzeichenNeu')
        self.original = _create_sollstellung(
            self.objekt, self.ev_alt, self.ba, Decimal('720.00'), self.user,
        )

    def test_tilgung_auf_korrektur_setzt_negativen_ist_betrag(self):
        korrektur, _ = korrigiere_sollstellung(
            original=self.original,
            neue_eigentumsverhaeltnis=self.ev_neu,
            neue_splits=None,
            korrektur_grund='eigentuemerwechsel',
            korrektur_vorgang_id=uuid4(),
            user=self.user,
        )
        self.assertEqual(korrektur.soll_betrag, Decimal('-720.00'))
        self.assertEqual(korrektur.ist_betrag, Decimal('0'))

        tilge_sollstellung(korrektur, Decimal('720.00'))
        korrektur.refresh_from_db()

        self.assertEqual(korrektur.ist_betrag, Decimal('-720.00'))

    def test_tilgung_auf_standard_sollstellung_positiv(self):
        ev = _create_ev(self.objekt, 'WE03', 'Standard')
        ss = _create_sollstellung(self.objekt, ev, self.ba, Decimal('300.00'), self.user)
        tilge_sollstellung(ss, Decimal('300.00'))
        ss.refresh_from_db()
        self.assertEqual(ss.ist_betrag, Decimal('300.00'))


# ---------------------------------------------------------------------------
# Smoke-Test 9 — get_korrektur_vorgang mit EigentuemerwechselVorgang
# ---------------------------------------------------------------------------

class GetKorrekturVorgangTest(TestCase):
    """Smoke-Test 9: get_korrektur_vorgang löst EigentuemerwechselVorgang korrekt auf."""

    def setUp(self):
        self.user = _user()
        self.objekt = _create_objekt()
        self.ba = _get_or_create_ba('900')
        self.ev_alt = _create_ev(self.objekt, 'WE01', 'VorgangAlt')
        self.ev_neu = _create_ev(self.objekt, 'WE02', 'VorgangNeu')
        self.original = _create_sollstellung(
            self.objekt, self.ev_alt, self.ba, Decimal('250.00'), self.user,
        )
        self.vorgang_id = uuid4()

    def test_get_korrektur_vorgang_eigentuemerwechsel(self):
        _, neuanlage = korrigiere_sollstellung(
            original=self.original,
            neue_eigentumsverhaeltnis=self.ev_neu,
            neue_splits=None,
            korrektur_grund='eigentuemerwechsel',
            korrektur_vorgang_id=self.vorgang_id,
            user=self.user,
        )
        mock_vorgang = MagicMock()
        mock_manager = MagicMock()
        mock_manager.get.return_value = mock_vorgang

        with patch(
            'apps.buchhaltung.models.EigentuemerwechselVorgang',
            create=True,
            new_callable=lambda: type('M', (), {'objects': mock_manager}),
        ):
            result = get_korrektur_vorgang(neuanlage)

        mock_manager.get.assert_called_once_with(pk=self.vorgang_id)
        self.assertIs(result, mock_vorgang)

    def test_get_korrektur_vorgang_none_wenn_kein_grund(self):
        ev = _create_ev(self.objekt, 'WE03', 'KeinGrund')
        ss = _create_sollstellung(self.objekt, ev, self.ba, Decimal('100.00'), self.user)
        self.assertIsNone(get_korrektur_vorgang(ss))
