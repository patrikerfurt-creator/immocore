"""
Unit- und Integrations-Tests für die 3-stufige Rechnungserkennung (Spec v1.2).

Kap. 10.1 Unit-Tests
Kap. 10.2 Integrations-Tests Workflow-Pfade 1–12
Kap. 10.3 Edge Cases
"""
from datetime import date
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

    def test_monatsnamen_entfernt(self):
        """
        Dauerleistungen tragen den Monat im Leistungstext. Bliebe er im Hash,
        bekäme jede Monatsrechnung einen neuen Hash — die gelernte Regel griffe
        nie wieder und es entstünde jeden Monat eine neue.
        """
        result = normalisiere_leistungstext('Verwaltergebühr Juli 2025')
        self.assertNotIn('juli', result)
        self.assertIn('verwaltergebühr', result)

    def test_gleicher_hash_ueber_monate(self):
        h_juni = leistungstext_hash('WEG-Verwaltung Wohnungen, Verwaltergebühr Juni 2025')
        h_juli = leistungstext_hash('WEG-Verwaltung Wohnungen, Verwaltergebühr Juli 2025')
        self.assertEqual(h_juni, h_juli)

    def test_abgekuerzte_monate_entfernt(self):
        self.assertEqual(
            leistungstext_hash('Wartung Jan'), leistungstext_hash('Wartung Dez'))

    def test_verschiedene_leistungen_bleiben_verschieden(self):
        """Die Monatsbereinigung darf inhaltlich Verschiedenes nicht zusammenwerfen."""
        self.assertNotEqual(
            leistungstext_hash('Gerätemiete Heizkostenverteiler Juni'),
            leistungstext_hash('Abrechnungsservice Heizkosten Juni'))


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
             patch('apps.rechnungen.recognition.match_konto_historie', return_value=MatchResult()),              patch('apps.rechnungen.recognition.match_konto_eindeutig', return_value=MatchResult()), \
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

    # v1.1: Die Erkennungs-Stufe (1/2/3) bleibt als Kontext erhalten;
    # der Lifecycle-Status ist nach der Pipeline IMMER 'in_buchhaltung'
    # (Stufe 1 Buchhaltung, keine Auto-Buchung — Spec Kap. 4).

    def test_stufe_1_alle_eindeutig(self):
        r = self._mock_erkennung(True, True, True)
        self.assertEqual(r.erkennungs_stufe, '1')
        self.assertEqual(r.status, 'in_buchhaltung')

    def test_stufe_2_nur_objekt(self):
        r = self._mock_erkennung(False, True, False)
        self.assertEqual(r.erkennungs_stufe, '2')
        self.assertEqual(r.status, 'in_buchhaltung')

    def test_stufe_2_objekt_und_kreditor(self):
        r = self._mock_erkennung(True, True, False)
        self.assertEqual(r.erkennungs_stufe, '2')
        self.assertEqual(r.status, 'in_buchhaltung')

    def test_stufe_3_nur_kreditor(self):
        r = self._mock_erkennung(True, False, False)
        self.assertEqual(r.erkennungs_stufe, '3')
        self.assertEqual(r.status, 'in_buchhaltung')

    def test_stufe_3_nichts(self):
        r = self._mock_erkennung(False, False, False)
        self.assertEqual(r.erkennungs_stufe, '3')
        self.assertEqual(r.status, 'in_buchhaltung')

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

    # v1.1 (Spec Kap. 4 / 11.1): route_rechnung bucht NIE mehr automatisch —
    # jede Rechnung landet in Stufe 1 (in_buchhaltung). routing_ziel bleibt
    # als Erkennungs-Kontext erhalten; zugewiesen_an wird erst in Stufe 2 gesetzt.

    def test_pfad_1_stufe1_konfidenz_98_betrag_250_nicht_auto(self):
        """v1.1: Stufe 1, Konfidenz 98%, Betrag 250 € → KEINE Auto-Buchung, in_buchhaltung."""
        from apps.buchhaltung.models import Buchung
        anzahl_vorher = Buchung.objects.count()
        r = self._rechnung_mit_konfidenz(250, k=0.98, o=0.98, c=1.0)
        auto_gebucht = route_rechnung(r)
        self.assertFalse(auto_gebucht)
        self.assertEqual(r.status, 'in_buchhaltung')
        self.assertEqual(r.routing_ziel, 'limit_workflow')
        self.assertEqual(Buchung.objects.count(), anzahl_vorher)

    def test_pfad_2_stufe1_konfidenz_92_betrag_250(self):
        """v1.1: Stufe 1, Konfidenz 92% → in_buchhaltung (Stufe 1, keine Zuweisung)."""
        r = self._rechnung_mit_konfidenz(250, k=0.92, o=0.92, c=1.0)
        route_rechnung(r)
        self.assertEqual(r.status, 'in_buchhaltung')
        self.assertIsNone(r.zugewiesen_an)

    def test_pfad_3_stufe1_konfidenz_98_betrag_5000(self):
        """v1.1: auch hohe Beträge → in_buchhaltung (Freigabe-Stufe erst in Stufe 2)."""
        r = self._rechnung_mit_konfidenz(5000, k=0.98, o=0.98, c=1.0)
        route_rechnung(r)
        self.assertEqual(r.status, 'in_buchhaltung')

    def test_pfad_4_stufe_2_kontext_objektbetreuer(self):
        """Stufe 2 (Objekt erkannt, Konto fehlt) → routing_ziel-Kontext, in_buchhaltung."""
        r = self._rechnung_mit_konfidenz(100, k=0.0, o=0.9, c=0.0, stufe='2')
        route_rechnung(r)
        self.assertEqual(r.routing_ziel, 'objektbetreuer')
        self.assertEqual(r.status, 'in_buchhaltung')
        self.assertIsNone(r.zugewiesen_an)

    def test_pfad_6_stufe_3_nur_kreditor_kontext_frontoffice(self):
        """Stufe 3 (kein Objekt) → routing_ziel-Kontext frontoffice, in_buchhaltung."""
        r = self._rechnung_mit_konfidenz(100, k=0.95, o=0.0, c=0.0, stufe='3')
        r.objekt = None
        r.save()
        route_rechnung(r)
        self.assertEqual(r.routing_ziel, 'frontoffice')
        self.assertIsNone(r.zugewiesen_an)
        self.assertEqual(r.status, 'in_buchhaltung')

    def test_pfad_7_stufe_3_kontext_frontoffice(self):
        """Stufe 3 → routing_ziel-Kontext frontoffice, in_buchhaltung."""
        r = self._rechnung_mit_konfidenz(100, k=0.0, o=0.0, c=0.0, stufe='3')
        r.objekt = None
        r.save()
        route_rechnung(r)
        self.assertEqual(r.routing_ziel, 'frontoffice')
        self.assertIsNone(r.zugewiesen_an)
        self.assertEqual(r.status, 'in_buchhaltung')


class KontoEindeutigTest(TestCase):
    """
    Eindeutigkeits-Fallback: Verwendet ein Kreditor in einem Objekt
    nachweislich nur ein Aufwandskonto, wird es auch ohne Übereinstimmung im
    Leistungstext gesetzt. Nötig, weil die OCR den Leistungstext jedes Mal
    anders formuliert und die gelernte Regel sonst nie greift.
    """

    def setUp(self):
        self.user     = make_user('eindeutig')
        self.objekt   = make_objekt()
        self.kreditor = make_kreditor()
        self.konto_a  = make_konto(self.objekt, kontonummer='55100', kontoname='Verwaltergebühr')
        self.konto_b  = make_konto(self.objekt, kontonummer='39000', kontoname='RAP')

    def _regel(self, konto, text):
        from apps.rechnungen.models import RechnungsMatchRegel
        from apps.rechnungen.recognition import leistungstext_hash
        return RechnungsMatchRegel.objects.create(
            kreditor=self.kreditor, objekt=self.objekt, aufwandskonto=konto,
            leistungstext_hash=leistungstext_hash(text), leistungstext_sample=text,
            status='aktiv', erstellt_durch=self.user, erstellt_aus='pruefung',
        )

    def test_ein_konto_ergibt_treffer(self):
        from apps.rechnungen.recognition import match_konto_eindeutig
        self._regel(self.konto_a, 'Verwaltergebühr Wohnungen')
        self._regel(self.konto_a, 'WEG-Verwaltung Objektbetreuung')
        res = match_konto_eindeutig(self.kreditor, self.objekt)
        self.assertEqual(res.kandidat.id, self.konto_a.id)
        self.assertEqual(res.konfidenz, 1.0)
        self.assertEqual(res.match_typ, 'kreditor_eindeutig')

    def test_gleiche_kontonummer_in_zwei_jahren_ist_eindeutig(self):
        """
        Konten sind jahresgebunden: dieselbe Nummer existiert je Wirtschaftsjahr
        einmal. Regeln aus verschiedenen Jahren zeigen deshalb auf verschiedene
        Konto-Objekte — fachlich ist die Kontierung trotzdem eindeutig.
        """
        from apps.rechnungen.recognition import match_konto_eindeutig
        from apps.konten.models import Konto
        from apps.objekte.models import Wirtschaftsjahr
        wj_vorjahr = Wirtschaftsjahr.objects.create(
            objekt=self.objekt, jahr=date.today().year - 1, beginn_monat=1)
        konto_vorjahr = Konto.objects.create(
            wirtschaftsjahr=wj_vorjahr, kontonummer=self.konto_a.kontonummer,
            kontoname=self.konto_a.kontoname, kontoart='standard',
        )
        self._regel(self.konto_a, 'Verwaltergebühr laufendes Jahr')
        self._regel(konto_vorjahr, 'Verwaltergebühr Vorjahr')
        res = match_konto_eindeutig(self.kreditor, self.objekt)
        self.assertIsNotNone(res.kandidat)
        self.assertEqual(res.kandidat.kontonummer, self.konto_a.kontonummer)
        self.assertEqual(res.konfidenz, 1.0)

    def test_mehrere_konten_ergeben_keinen_treffer(self):
        """
        Der Techem-Fall: Gerätemiete und Vorjahresabgrenzung gehen auf
        verschiedene Konten — hier muss der Leistungstext entscheiden.
        """
        from apps.rechnungen.recognition import match_konto_eindeutig
        self._regel(self.konto_a, 'Gerätemiete Heizkostenverteiler')
        self._regel(self.konto_b, 'Abrechnungsservice Vorjahr')
        res = match_konto_eindeutig(self.kreditor, self.objekt)
        self.assertIsNone(res.kandidat)

    def test_veraltete_regeln_zaehlen_nicht(self):
        from apps.rechnungen.recognition import match_konto_eindeutig
        self._regel(self.konto_a, 'Verwaltergebühr')
        alt = self._regel(self.konto_b, 'Frühere Kontierung')
        alt.status = 'veraltet'
        alt.save(update_fields=['status'])
        res = match_konto_eindeutig(self.kreditor, self.objekt)
        self.assertEqual(res.kandidat.id, self.konto_a.id)

    def test_ohne_regeln_kein_treffer(self):
        from apps.rechnungen.recognition import match_konto_eindeutig
        self.assertIsNone(match_konto_eindeutig(self.kreditor, self.objekt).kandidat)

    def test_ohne_kreditor_kein_treffer(self):
        from apps.rechnungen.recognition import match_konto_eindeutig
        self.assertIsNone(match_konto_eindeutig(None, self.objekt).kandidat)


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

    def test_stufe1_ohne_auto_in_config_in_buchhaltung(self):
        """v1.1: auch ohne Auto-Limit in den Grenzen → Stufe 1 (in_buchhaltung)."""
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
        self.assertEqual(r.status, 'in_buchhaltung')


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


class PruefgrundTextTest(TestCase):
    """
    Die Begründung, warum eine Rechnung zurückgehalten wurde, muss für einen
    Bearbeiter lesbar sein — nicht nur als technischer Code wie
    'ocr_unvollstaendig'.
    """

    def setUp(self):
        self.objekt = make_objekt()
        self.kreditor = make_kreditor()

    def _rechnung(self, status='prueffall', typ='', notiz='', quelle=None):
        r = make_rechnung(objekt=self.objekt, kreditor=self.kreditor)
        r.status = status
        r.duplikat_typ = typ
        r.verarbeitungsnotiz = notiz
        r.duplikat_von = quelle
        r.save()
        return r

    def test_unauffaellige_rechnung_ohne_grund(self):
        from apps.rechnungen.serializers import pruefgrund_text
        self.assertEqual(pruefgrund_text(self._rechnung(status='in_buchhaltung')), '')

    def test_ocr_unvollstaendig_nennt_die_felder(self):
        from apps.rechnungen.serializers import pruefgrund_text
        r = self._rechnung(typ='ocr_unvollstaendig',
                           notiz='OCR unvollständig: Rechnungsnummer, Bruttobetrag')
        text = pruefgrund_text(r)
        self.assertIn('Rechnungsnummer, Bruttobetrag', text)
        self.assertNotIn('ocr_unvollstaendig', text)

    def test_ocr_unvollstaendig_ohne_notiz_bleibt_verstaendlich(self):
        from apps.rechnungen.serializers import pruefgrund_text
        text = pruefgrund_text(self._rechnung(typ='ocr_unvollstaendig'))
        self.assertIn('Texterkennung', text)

    def test_hash_duplikat_nennt_die_quelle(self):
        from apps.rechnungen.serializers import pruefgrund_text
        original = make_rechnung(objekt=self.objekt, kreditor=self.kreditor)
        original.dateiname = 'original.pdf'
        original.save()
        text = pruefgrund_text(self._rechnung(status='duplikat', typ='hash', quelle=original))
        self.assertIn('original.pdf', text)
        self.assertNotIn('hash', text.lower().replace('rechnung', ''))

    def test_kein_doppelter_dateiname(self):
        """Die Quelle darf nicht zweimal im Text stehen (Text + Notiz)."""
        from apps.rechnungen.serializers import pruefgrund_text
        original = make_rechnung(objekt=self.objekt, kreditor=self.kreditor)
        original.dateiname = 'doppelt.pdf'
        original.save()
        r = self._rechnung(status='duplikat', typ='hash',
                           notiz='Exaktes Duplikat: doppelt.pdf', quelle=original)
        self.assertEqual(pruefgrund_text(r).count('doppelt.pdf'), 1)

    def test_unbekannter_typ_faellt_auf_notiz_zurueck(self):
        from apps.rechnungen.serializers import pruefgrund_text
        text = pruefgrund_text(self._rechnung(typ='irgendwas_neues', notiz='Sonderfall XY'))
        self.assertIn('Sonderfall XY', text)


class RouteZurFreigabeStatusTest(TestCase):
    """
    Der Stufe-1-Abschluss darf eine bereits freigegebene Rechnung nicht zurück
    nach 'zur_freigabe' werfen: ihr offener Posten bliebe bestehen, der Zustand
    wäre widersprüchlich, und jeder Durchlauf zählt die Lernstatistik hoch.
    """

    def setUp(self):
        self.user = make_user('freigabe_status')
        self.objekt = make_objekt()
        self.kreditor = make_kreditor()
        self.konto = make_konto(self.objekt)

    def _rechnung(self, status):
        r = make_rechnung(objekt=self.objekt, kreditor=self.kreditor, aufwandskonto=self.konto)
        r.status = status
        r.leistungstext = 'Hausmeisterdienste'
        r.save()
        return r

    def test_aus_stufe_1_erlaubt(self):
        from apps.rechnungen.services.rechnung_freigabe_service import route_zur_freigabe
        r = self._rechnung('in_buchhaltung')
        route_zur_freigabe(r, geprueft_von=self.user)
        r.refresh_from_db()
        self.assertEqual(r.status, 'zur_freigabe')

    def test_bereits_freigegeben_wird_abgelehnt(self):
        from django.core.exceptions import ValidationError
        from apps.rechnungen.services.rechnung_freigabe_service import route_zur_freigabe
        r = self._rechnung('freigegeben')
        with self.assertRaises(ValidationError):
            route_zur_freigabe(r, geprueft_von=self.user)
        r.refresh_from_db()
        self.assertEqual(r.status, 'freigegeben')   # unveraendert

    def test_bezahlt_wird_abgelehnt(self):
        from django.core.exceptions import ValidationError
        from apps.rechnungen.services.rechnung_freigabe_service import route_zur_freigabe
        r = self._rechnung('bezahlt')
        with self.assertRaises(ValidationError):
            route_zur_freigabe(r, geprueft_von=self.user)

    def test_vorhandene_op_buchung_wird_abgelehnt(self):
        """Auch aus einem Stufe-1-Status: existiert die OP-Buchung, ist Schluss."""
        from django.core.exceptions import ValidationError
        from apps.buchhaltung.models import Buchung
        from apps.rechnungen.services.rechnung_freigabe_service import route_zur_freigabe
        r = self._rechnung('in_buchhaltung')
        r.op_buchung = Buchung.objects.create(
            objekt=self.objekt, betrag=Decimal('10.00'), buchungsdatum=date(2026, 1, 1))
        r.save(update_fields=['op_buchung'])
        with self.assertRaises(ValidationError):
            route_zur_freigabe(r, geprueft_von=self.user)

    def test_lernstatistik_wird_nicht_hochgezaehlt(self):
        """Der abgelehnte Durchlauf darf keine Match-Regel anlegen."""
        from django.core.exceptions import ValidationError
        from apps.rechnungen.models import RechnungsMatchRegel
        from apps.rechnungen.services.rechnung_freigabe_service import route_zur_freigabe
        r = self._rechnung('freigegeben')
        vorher = RechnungsMatchRegel.objects.count()
        with self.assertRaises(ValidationError):
            route_zur_freigabe(r, geprueft_von=self.user)
        self.assertEqual(RechnungsMatchRegel.objects.count(), vorher)


class KreditorKontoauszugStornoTest(TestCase):
    """
    Der Buchungssaldo im Kreditor-Kontoauszug muss Storno-Paare BEIDSEITIG
    ausschliessen. Wird nur das stornierte Original gefiltert, bleibt die
    Gegenbuchung allein stehen und verfälscht den Saldo um ihren Betrag.
    """

    def setUp(self):
        from django.contrib.auth import get_user_model
        self.user = get_user_model().objects.create_user(username='kkauszug', password='x')
        self.objekt = make_objekt()
        self.kreditor = make_kreditor()
        self.kreditor.kreditorennummer = '70099'
        self.kreditor.save(update_fields=['kreditorennummer'])
        self.konto_kred = make_konto(self.objekt, kontonummer='70099', kontoname='Kreditor Test')
        self.konto_bank = make_konto(self.objekt, kontonummer='18000', kontoname='Bank')

    def _saldo(self):
        from apps.rechnungen.views import KreditorViewSet
        from rest_framework.test import APIRequestFactory
        req = APIRequestFactory().get('/')
        req.user = self.user
        resp = KreditorViewSet.as_view({'get': 'kontoauszug'})(req, pk=str(self.kreditor.id))
        return resp.data.get('buchungen_saldo')

    def test_stornopaar_beeinflusst_saldo_nicht(self):
        from apps.buchhaltung.models import Buchung
        original = Buchung.objects.create(
            objekt=self.objekt, betrag=Decimal('100.00'), buchungsdatum=date(2026, 3, 1),
            soll_konto=self.konto_kred, haben_konto=self.konto_bank,
            status='storniert', erstellt_von=self.user,
        )
        Buchung.objects.create(   # Gegenbuchung
            objekt=self.objekt, betrag=Decimal('100.00'), buchungsdatum=date(2026, 3, 1),
            soll_konto=self.konto_bank, haben_konto=self.konto_kred,
            status='festgeschrieben', storno_von=original, erstellt_von=self.user,
        )
        self.assertEqual(Decimal(str(self.saldo_oder_null())), Decimal('0'))

    def saldo_oder_null(self):
        s = self._saldo()
        return s if s is not None else 0

    def test_offene_buchung_zaehlt_weiterhin(self):
        """Gegenprobe: eine normale Buchung muss im Saldo erscheinen."""
        from apps.buchhaltung.models import Buchung
        Buchung.objects.create(
            objekt=self.objekt, betrag=Decimal('250.00'), buchungsdatum=date(2026, 3, 2),
            soll_konto=self.konto_kred, haben_konto=self.konto_bank,
            status='festgeschrieben', erstellt_von=self.user,
        )
        self.assertEqual(Decimal(str(self.saldo_oder_null())), Decimal('250'))
