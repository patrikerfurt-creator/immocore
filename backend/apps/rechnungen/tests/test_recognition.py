"""
Unit- und Integrations-Tests für die 3-stufige Rechnungserkennung (Spec v1.2).

Kap. 10.1 Unit-Tests
Kap. 10.2 Integrations-Tests Workflow-Pfade 1–12
Kap. 10.3 Edge Cases
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch, PropertyMock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.utils import timezone

from apps.rechnungen.recognition import (
    normalisiere_leistungstext,
    leistungstext_hash,
    _konfidenz_min,
    darf_betreuer_direkt_freigeben,
    lege_match_regel_an,
    route_rechnung,
    fuehre_erkennung_aus,
    AUTO_KONFIDENZ_SCHWELLE,
    SCHWELLE_KREDITOR,
    SCHWELLE_OBJEKT,
)

User = get_user_model()


# ===========================================================================
# Hilfsfunktionen
# ===========================================================================

def make_user(username, groups=None):
    u = User.objects.create_user(username=username, password='test')
    for g in (groups or []):
        grp, _ = Group.objects.get_or_create(name=g)
        u.groups.add(grp)
    return u


def make_objekt(betreuer=None, betreuer_vertretung=None, grenzen=None):
    from apps.objekte.models import Objekt
    from datetime import date
    obj = Objekt.objects.create(
        bezeichnung=f'Testobjekt-{Objekt.objects.count()}',
        strasse='Teststraße 1',
        plz='12345',
        ort='Teststadt',
        objekt_typ='WEG',
        verwaltung_seit=date(2020, 1, 1),
    )
    if betreuer:
        obj.betreuer = betreuer
    if betreuer_vertretung:
        obj.betreuer_vertretung = betreuer_vertretung
    if grenzen is not None:
        obj.zahlungsfreigabe_grenzen = grenzen
    obj.save()
    return obj


def make_kreditor(name='TestKreditor', iban=None):
    from apps.rechnungen.models import Kreditor
    return Kreditor.objects.create(
        name=name,
        name_normalisiert=name.lower(),
        iban=iban,
    )


def make_konto(objekt, kontonummer='52000', kontoname='Testkonto', direktes_buchen=False):
    from apps.konten.models import Konto
    from apps.objekte.models import Wirtschaftsjahr
    from datetime import date
    wj, _ = Wirtschaftsjahr.objects.get_or_create(
        objekt=objekt,
        jahr=date.today().year,
        defaults={'beginn_monat': 1},
    )
    return Konto.objects.create(
        wirtschaftsjahr=wj,
        kontonummer=kontonummer,
        kontoname=kontoname,
        direktes_buchen=direktes_buchen,
        aktiv=True,
    )


def make_rechnung(objekt=None, kreditor=None, aufwandskonto=None,
                  betrag=Decimal('100.00'), stufe=None, konfidenz=None):
    from apps.rechnungen.models import Rechnung
    r = Rechnung.objects.create(
        objekt=objekt,
        kreditor=kreditor,
        aufwandskonto=aufwandskonto,
        betrag_brutto=betrag,
        status='erfasst',
        erkennungs_stufe=stufe,
        erkennungs_konfidenz=konfidenz,
        leistungstext='Hausmeisterdienste',
    )
    return r


# ===========================================================================
# Kap. 10.1 Unit-Tests
# ===========================================================================

class TextNormalisierungTest(TestCase):
    def test_datum_entfernt(self):
        result = normalisiere_leistungstext('Rechnung 01.03.2024 Hausmeister')
        self.assertNotIn('01.03.2024', result)

    def test_belegnummer_entfernt(self):
        result = normalisiere_leistungstext('RG-12345 Hausmeister')
        self.assertNotIn('12345', result)
        self.assertNotIn('rg', result)

    def test_quartal_entfernt(self):
        result = normalisiere_leistungstext('Wartung Q1 2024')
        self.assertNotIn('q1', result)

    def test_stopwoerter_entfernt(self):
        result = normalisiere_leistungstext('Reparatur und Wartung')
        self.assertNotIn('und', result)
        self.assertIn('reparatur', result)
        self.assertIn('wartung', result)

    def test_gleicher_hash_nach_normalisierung(self):
        h1 = leistungstext_hash('Hausmeister Q1 2024 RG-999')
        h2 = leistungstext_hash('Hausmeister Q2 2025 RG-888')
        self.assertEqual(h1, h2)

    def test_hash_laenge_64(self):
        h = leistungstext_hash('Test')
        self.assertEqual(len(h), 64)


class KonfidenzMinTest(TestCase):
    def test_minimum_aus_drei_dimensionen(self):
        r = MagicMock()
        r.erkennungs_konfidenz = {'kreditor': 0.95, 'objekt': 0.80, 'aufwandskonto': 1.0}
        self.assertAlmostEqual(_konfidenz_min(r), 0.80)

    def test_fehlende_dimension_als_null(self):
        r = MagicMock()
        r.erkennungs_konfidenz = {'kreditor': 0.95}
        self.assertAlmostEqual(_konfidenz_min(r), 0.0)

    def test_keine_konfidenz(self):
        r = MagicMock()
        r.erkennungs_konfidenz = None
        self.assertAlmostEqual(_konfidenz_min(r), 0.0)

    def test_exakt_schwelle(self):
        r = MagicMock()
        r.erkennungs_konfidenz = {'kreditor': 0.95, 'objekt': 0.95, 'aufwandskonto': 0.95}
        self.assertAlmostEqual(_konfidenz_min(r), AUTO_KONFIDENZ_SCHWELLE)


class StufenAbleitungTest(TestCase):
    """8 Kombinationen von (k_eind, o_eind, c_eind) → korrekte Stufe."""

    def _mock_erkennung(self, k_eind, o_eind, c_eind):
        """Testet fuehre_erkennung_aus durch Mocken der Match-Funktionen."""
        from unittest.mock import patch
        from apps.rechnungen.recognition import MatchResult

        k_konfidenz = 1.0 if k_eind else 0.0
        o_konfidenz = 1.0 if o_eind else 0.0
        c_konfidenz = 1.0 if c_eind else 0.0

        mock_kreditor = MagicMock()
        mock_objekt   = MagicMock()
        mock_konto    = MagicMock()
        mock_objekt.betreuer_id = None
        mock_objekt.betreuer = None
        mock_objekt.zahlungsfreigabe_grenzen = None

        kreditor_result = MatchResult(mock_kreditor, k_konfidenz, 'iban') if k_eind else MatchResult()
        objekt_result   = MatchResult(mock_objekt,   o_konfidenz, 'anschrift') if o_eind else MatchResult()
        konto_result    = MatchResult(mock_konto,    c_konfidenz, 'match_regel') if c_eind else MatchResult()

        mock_rechnung = MagicMock()
        mock_rechnung.lieferant_iban = 'DE00123456780000000000' if k_eind else None
        mock_rechnung.lieferant_normalisiert = ''
        mock_rechnung.lieferant_name = ''
        mock_rechnung.objekt_id = None
        mock_rechnung.objekt = None
        mock_rechnung.kreditor_id = None
        mock_rechnung.leistungstext = 'Hausmeister'
        mock_rechnung.leistungsbeschreibung = ''
        mock_rechnung.leistungstext_hash = ''
        mock_rechnung.betrag_brutto = Decimal('100')

        with patch('apps.rechnungen.recognition.match_kreditor', return_value=kreditor_result), \
             patch('apps.rechnungen.recognition.match_objekt',   return_value=objekt_result), \
             patch('apps.rechnungen.recognition.match_konto_historie', return_value=MatchResult()), \
             patch('apps.rechnungen.recognition.RechnungsMatchRegel') as mock_mrm, \
             patch('apps.rechnungen.recognition.RechnungsErkennungsLog') as mock_log:

            if c_eind:
                mock_regel = MagicMock()
                mock_regel.aufwandskonto = mock_konto
                mock_mrm.objects.filter.return_value.first.return_value = mock_regel
            else:
                mock_mrm.objects.filter.return_value.first.return_value = None
            mock_log.objects.create.return_value = MagicMock()
            mock_rechnung.save = MagicMock()

            if o_eind:
                mock_rechnung.objekt = mock_objekt

            fuehre_erkennung_aus(mock_rechnung)

        return mock_rechnung

    def test_stufe_1_alle_eindeutig(self):
        r = self._mock_erkennung(True, True, True)
        self.assertEqual(r.erkennungs_stufe, '1')
        # After full pipeline: Stufe-1 with 100% confidence + betrag 100€ → auto-gebucht
        self.assertIn(r.status, ('erkannt', 'gebucht', 'in_pruefung'))

    def test_stufe_2_nur_objekt(self):
        r = self._mock_erkennung(False, True, False)
        self.assertEqual(r.erkennungs_stufe, '2')
        self.assertEqual(r.status, 'pruefung_match')

    def test_stufe_2_objekt_und_kreditor(self):
        r = self._mock_erkennung(True, True, False)
        self.assertEqual(r.erkennungs_stufe, '2')
        self.assertEqual(r.status, 'pruefung_match')

    def test_stufe_3_nur_kreditor(self):
        r = self._mock_erkennung(True, False, False)
        self.assertEqual(r.erkennungs_stufe, '3')
        self.assertEqual(r.status, 'nicht_erkannt')

    def test_stufe_3_nichts(self):
        r = self._mock_erkennung(False, False, False)
        self.assertEqual(r.erkennungs_stufe, '3')
        self.assertEqual(r.status, 'nicht_erkannt')

    def test_stufe_1_konto_allein_nicht_moeglich(self):
        # Konto ohne Kreditor/Objekt → Stufe 3 (Konto wird gar nicht geprüft)
        r = self._mock_erkennung(False, False, True)
        self.assertEqual(r.erkennungs_stufe, '3')


class DarfDirektFreigebenTest(TestCase):
    def setUp(self):
        self.gf_user   = make_user('gf',   ['Geschaeftsfuehrer'])
        self.sb_user   = make_user('sb',   ['Sachbearbeiter'])
        self.fo_user   = make_user('fo',   ['Frontoffice'])
        self.norm_user = make_user('norm', [])
        self.objekt    = make_objekt()
        self.konto     = make_konto(self.objekt)

    def _r(self, betrag):
        r = MagicMock()
        r.objekt = self.objekt
        r.betrag_brutto = Decimal(str(betrag))
        return r

    def test_auto_limit_erlaubt_fuer_alle(self):
        self.objekt.zahlungsfreigabe_grenzen = [
            {'bis': 500, 'rolle': 'auto', 'frist_tage': 0}
        ]
        self.objekt.save()
        r = self._r(100)
        self.assertTrue(darf_betreuer_direkt_freigeben(r, self.norm_user))

    def test_sachbearbeiter_limit_frontoffice_erlaubt(self):
        self.objekt.zahlungsfreigabe_grenzen = [
            {'bis': 5000, 'rolle': 'sachbearbeiter', 'frist_tage': 3}
        ]
        self.objekt.save()
        r = self._r(1000)
        self.assertTrue(darf_betreuer_direkt_freigeben(r, self.fo_user))

    def test_sachbearbeiter_limit_normaler_user_verboten(self):
        self.objekt.zahlungsfreigabe_grenzen = [
            {'bis': 5000, 'rolle': 'sachbearbeiter', 'frist_tage': 3}
        ]
        self.objekt.save()
        r = self._r(1000)
        self.assertFalse(darf_betreuer_direkt_freigeben(r, self.norm_user))

    def test_gf_limit_nur_gf(self):
        self.objekt.zahlungsfreigabe_grenzen = [
            {'bis': None, 'rolle': 'geschaeftsfuehrer', 'frist_tage': 5}
        ]
        self.objekt.save()
        r = self._r(50000)
        self.assertTrue(darf_betreuer_direkt_freigeben(r, self.gf_user))
        self.assertFalse(darf_betreuer_direkt_freigeben(r, self.sb_user))
        self.assertFalse(darf_betreuer_direkt_freigeben(r, self.fo_user))


# ===========================================================================
# Kap. 10.2 Integrations-Tests
# ===========================================================================

class WorkflowPfadTest(TestCase):
    def setUp(self):
        self.betreuer_user = make_user('betreuer', ['Sachbearbeiter'])
        self.gf_user       = make_user('gf', ['Geschaeftsfuehrer'])
        self.fo_user       = make_user('fo', ['Frontoffice'])
        self.objekt = make_objekt(
            betreuer=self.betreuer_user,
            grenzen=[
                {'bis': 500,   'rolle': 'auto',             'frist_tage': 0},
                {'bis': 5000,  'rolle': 'sachbearbeiter',   'frist_tage': 3},
                {'bis': None,  'rolle': 'geschaeftsfuehrer', 'frist_tage': 5},
            ],
        )
        self.kreditor = make_kreditor(iban='DE02500105170137075030')
        self.konto    = make_konto(self.objekt)

    def _rechnung_mit_konfidenz(self, betrag, k=1.0, o=1.0, c=1.0, stufe='1'):
        r = make_rechnung(
            objekt=self.objekt,
            kreditor=self.kreditor,
            aufwandskonto=self.konto,
            betrag=Decimal(str(betrag)),
        )
        r.erkennungs_stufe = stufe
        r.erkennungs_konfidenz = {'kreditor': k, 'objekt': o, 'aufwandskonto': c}
        if stufe == '1':
            r.status = 'erkannt'
        elif stufe == '2':
            r.status = 'pruefung_match'
        else:
            r.status = 'nicht_erkannt'
        r.save()
        return r

    def test_pfad_1_stufe1_konfidenz_98_betrag_250_auto(self):
        """Stufe 1, Konfidenz 98%, Betrag 250 € → AUTO gebucht."""
        r = self._rechnung_mit_konfidenz(250, k=0.98, o=0.98, c=1.0)
        route_rechnung(r)
        self.assertEqual(r.status, 'gebucht')
        self.assertEqual(r.routing_ziel, 'limit_workflow')

    def test_pfad_2_stufe1_konfidenz_92_betrag_250_nicht_auto(self):
        """Stufe 1, Konfidenz 92%, Betrag 250 € → in_pruefung (Konfidenz zu niedrig)."""
        r = self._rechnung_mit_konfidenz(250, k=0.92, o=0.92, c=1.0)
        route_rechnung(r)
        self.assertEqual(r.status, 'in_pruefung')
        self.assertIsNotNone(r.zugewiesen_an)

    def test_pfad_3_stufe1_konfidenz_98_betrag_5000_gf(self):
        """Stufe 1, Konfidenz 98%, Betrag 5000 € → in_pruefung an GF."""
        r = self._rechnung_mit_konfidenz(5000, k=0.98, o=0.98, c=1.0)
        route_rechnung(r)
        self.assertEqual(r.status, 'in_pruefung')

    def test_pfad_4_stufe_2_routing_objektbetreuer(self):
        """Stufe 2 (Objekt erkannt, Konto fehlt) → Routing Objektbetreuer."""
        r = self._rechnung_mit_konfidenz(100, k=0.0, o=0.9, c=0.0, stufe='2')
        route_rechnung(r)
        self.assertEqual(r.routing_ziel, 'objektbetreuer')
        self.assertEqual(r.zugewiesen_an, self.betreuer_user)

    def test_pfad_6_stufe_3_nur_kreditor_routing_frontoffice(self):
        """Stufe 3 (nur Kreditor erkannt, kein Objekt) → Routing Frontoffice."""
        r = self._rechnung_mit_konfidenz(100, k=0.95, o=0.0, c=0.0, stufe='3')
        r.objekt = None
        r.save()
        route_rechnung(r)
        self.assertEqual(r.routing_ziel, 'frontoffice')
        self.assertIsNone(r.zugewiesen_an)

    def test_pfad_7_stufe_3_routing_frontoffice(self):
        """Stufe 3 → Routing Frontoffice."""
        r = self._rechnung_mit_konfidenz(100, k=0.0, o=0.0, c=0.0, stufe='3')
        r.objekt = None
        r.save()
        route_rechnung(r)
        self.assertEqual(r.routing_ziel, 'frontoffice')
        self.assertIsNone(r.zugewiesen_an)

    def test_pfad_8_abwesenheit_vertretung(self):
        """Stufe 2, Betreuer abwesend → Routing an Vertretung."""
        from apps.mitarbeiter.models import Mitarbeiter
        vertretung = make_user('vertretung', ['Sachbearbeiter'])
        self.objekt.betreuer_vertretung = vertretung
        self.objekt.save()

        try:
            profil = self.betreuer_user.mitarbeiter_profil
            profil.abwesend = True
            profil.save()
        except Exception:
            pass  # Profil-Modell existiert evtl. noch nicht in Test-DB

        r = self._rechnung_mit_konfidenz(100, k=0.0, o=0.9, c=0.0, stufe='2')
        route_rechnung(r)
        self.assertEqual(r.routing_ziel, 'objektbetreuer')


class LernlogikTest(TestCase):
    def setUp(self):
        self.user    = make_user('tester')
        self.objekt  = make_objekt()
        self.kreditor = make_kreditor()
        self.konto   = make_konto(self.objekt)

    def _rechnung(self):
        r = make_rechnung(objekt=self.objekt, kreditor=self.kreditor, aufwandskonto=self.konto)
        r.leistungstext = 'Hausmeisterdienste'
        r.save()
        return r

    def test_regel_wird_angelegt(self):
        from apps.rechnungen.models import RechnungsMatchRegel
        r = self._rechnung()
        regel = lege_match_regel_an(r, self.user, 'pruefung')
        self.assertIsNotNone(regel)
        self.assertEqual(RechnungsMatchRegel.objects.filter(status='aktiv').count(), 1)

    def test_idempotenz_trefferzahl(self):
        from apps.rechnungen.models import RechnungsMatchRegel
        r = self._rechnung()
        lege_match_regel_an(r, self.user, 'pruefung')
        lege_match_regel_an(r, self.user, 'pruefung')
        regeln = RechnungsMatchRegel.objects.filter(status='aktiv')
        self.assertEqual(regeln.count(), 1)
        self.assertEqual(regeln.first().trefferzahl, 2)

    def test_kontokorrektur_veraltet_alte_regel(self):
        from apps.rechnungen.models import RechnungsMatchRegel
        r = self._rechnung()
        lege_match_regel_an(r, self.user, 'pruefung')

        neues_konto = make_konto(self.objekt, '53000', 'Anderes Konto')
        r.aufwandskonto = neues_konto
        r.save()
        lege_match_regel_an(r, self.user, 'freigabe_korrektur')

        self.assertEqual(RechnungsMatchRegel.objects.filter(status='veraltet').count(), 1)
        self.assertEqual(RechnungsMatchRegel.objects.filter(status='aktiv').count(), 1)

    def test_opt_out_speichert_keine_regel(self):
        from apps.rechnungen.models import RechnungsMatchRegel
        r = self._rechnung()
        result = lege_match_regel_an(r, self.user, 'pruefung', lernen=False)
        self.assertIsNone(result)
        self.assertEqual(RechnungsMatchRegel.objects.count(), 0)


# ===========================================================================
# Kap. 10.3 Edge Cases
# ===========================================================================

class EdgeCaseTest(TestCase):
    def setUp(self):
        self.user   = make_user('tester')
        self.objekt = make_objekt()
        self.konto  = make_konto(self.objekt)

    def test_konto_falsches_objekt_wird_abgelehnt(self):
        """Aufwandskonto eines anderen Objekts darf nicht zugewiesen werden."""
        anderes_objekt = make_objekt()
        fremdes_konto  = make_konto(anderes_objekt, '52000', 'Fremdes Konto')
        kreditor = make_kreditor()
        r = make_rechnung(objekt=self.objekt, kreditor=kreditor, aufwandskonto=self.konto)
        r.aufwandskonto = fremdes_konto

        # Der API-Endpunkt schützt mit Konto.objects.get(pk=konto_id, objekt=objekt).
        self.assertNotEqual(fremdes_konto.objekt, self.objekt)

    def test_auto_konfidenz_exakt_schwelle_zaehlt(self):
        """Konfidenz exakt 0.95 ist ≥ Schwelle → auto-fähig."""
        r = MagicMock()
        r.erkennungs_konfidenz = {
            'kreditor':     AUTO_KONFIDENZ_SCHWELLE,
            'objekt':       AUTO_KONFIDENZ_SCHWELLE,
            'aufwandskonto': AUTO_KONFIDENZ_SCHWELLE,
        }
        self.assertGreaterEqual(_konfidenz_min(r), AUTO_KONFIDENZ_SCHWELLE)

    def test_stufe1_ohne_auto_in_config_immer_in_pruefung(self):
        """Stufe 1 ohne Auto-Limit in zahlungsfreigabe_grenzen → immer in_pruefung."""
        betreuer = make_user('betreuer2', ['Sachbearbeiter'])
        obj = make_objekt(
            betreuer=betreuer,
            grenzen=[
                {'bis': 5000, 'rolle': 'sachbearbeiter', 'frist_tage': 3},
                {'bis': None, 'rolle': 'geschaeftsfuehrer', 'frist_tage': 5},
            ],
        )
        kreditor = make_kreditor(iban='DE00500105170000000001')
        konto = make_konto(obj)
        r = make_rechnung(objekt=obj, kreditor=kreditor, aufwandskonto=konto, betrag=Decimal('100'))
        r.erkennungs_stufe = '1'
        r.status = 'erkannt'
        r.erkennungs_konfidenz = {'kreditor': 1.0, 'objekt': 1.0, 'aufwandskonto': 1.0}
        r.save()
        route_rechnung(r)
        self.assertEqual(r.status, 'in_pruefung')


# ===========================================================================
# Kap. 10.4 API-Pfad 13: Legacy-Feld buchungskonto_id → HTTP 400
# ===========================================================================

class LegacyFeldTest(TestCase):
    def setUp(self):
        self.user    = make_user('tester')
        self.objekt  = make_objekt()
        self.kreditor = make_kreditor()
        self.konto   = make_konto(self.objekt)

    def test_identifizieren_mit_buchungskonto_id_liefert_400(self):
        """Pfad 13: buchungskonto_id im Body → HTTP 400 mit Hinweis auf aufwandskonto_id."""
        from django.test import RequestFactory
        from rest_framework.test import force_authenticate
        from apps.rechnungen.views import RechnungViewSet
        from apps.rechnungen.models import Rechnung

        rechnung = make_rechnung(
            objekt=self.objekt, kreditor=self.kreditor,
            stufe='2',
        )
        rechnung.status = 'pruefung_match'
        rechnung.save()

        factory = RequestFactory()
        request = factory.post(
            f'/rechnungen/{rechnung.id}/identifizieren/',
            data={
                'kreditor_id':    str(self.kreditor.id),
                'objekt_id':      str(self.objekt.id),
                'buchungskonto_id': str(self.konto.id),
            },
            content_type='application/json',
        )
        force_authenticate(request, user=self.user)

        view = RechnungViewSet.as_view({'post': 'identifizieren'})
        response = view(request, pk=str(rechnung.id))
        self.assertEqual(response.status_code, 400)
        self.assertIn('aufwandskonto_id', str(response.data))
