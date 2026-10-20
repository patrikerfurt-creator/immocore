"""
Tests für die doppelt qualifizierte Mehrheit (§ 21 Abs. 2 Nr. 1 WEG).

Fachlogik (Patrik/Anwalt-Entscheidung 2026-10-19):
  * 1. Achse — Köpfe: Ja-Anteil der abgegebenen Stimmen MUSS die Schwelle
    ÜBERSCHREITEN (strikt >, "mehr als" 2/3). Immer nach Kopfprinzip, unabhängig
    vom sonstigen Stimmprinzip der Gemeinschaft.
  * 2. Achse — MEA: Ja-Anteil an der GESAMTEN MEA der Gemeinschaft (auch
    Abwesende) muss die Schwelle ERREICHEN (>=, "die Hälfte").
  * Angenommen nur, wenn beide Achsen erfüllt sind.

Setup: 4 Eigentümer, je 1 Kopf; MEA 600/200/120/80 (Summe 1000).
"""
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.versammlung.serializers import (
    TagesordnungspunktCreateSerializer, TagesordnungspunktSerializer,
)
from apps.versammlung.services import (
    durchfuehrung_service, ev_service, stimmgrundlage_service,
    stimmkraft_service, tagesordnung_service,
)
from apps.versammlung.tests import factories as f


class _DoppeltBasis(TestCase):
    MEA = {'Gross': '600', 'Zwei': '200', 'Drei': '120', 'Vier': '80'}  # Summe 1000

    def setUp(self):
        self.user = f.user()
        self.objekt = f.objekt()
        self.einheiten = {}
        for index, name in enumerate(self.MEA, start=1):
            einheit, _ = f.eigentuemer(
                self.objekt, f.person(nachname=name), nr=f'{index:03d}',
            )
            self.einheiten[name] = einheit
        self.mea = f.mea_schluessel(
            self.objekt, {self.einheiten[n]: wert for n, wert in self.MEA.items()},
        )
        # EV nach Kopfprinzip (Standard-Grundlage = Kopf); MEA-Grundlage ergänzen.
        self.ev = ev_service.erstelle_ev(
            objekt=self.objekt, erstellt_von=self.user, stimmprinzip='kopf',
        )
        ev_service.aktualisiere_terminierung(
            self.ev, self.user,
            termin=timezone.now() - timedelta(hours=1), ort='Gemeinschaftsraum',
        )
        stimmgrundlage_service.hinzufuegen(self.ev, verteilerschluessel=self.mea)
        stimmkraft_service.ermittle_teilnehmer(self.ev, self.user)
        self.teilnehmer = {
            t.person.nachname: t
            for t in self.ev.teilnehmer.select_related('person')
        }

    def _top(self, s1='66.67', s2='50.00'):
        return tagesordnung_service.top_anlegen(
            ev=self.ev, titel='Bauliche Veränderung', erstellt_von=self.user,
            beschlussvorlage='Es wird beschlossen.',
            abstimmungsmodus='doppelt_qualifiziert',
            mehrheit_schwelle=Decimal(s1), mehrheit_schwelle_2=Decimal(s2),
        )

    def _anwesend(self, *namen):
        for name, teilnehmer in self.teilnehmer.items():
            durchfuehrung_service.erfasse_anwesenheit(
                teilnehmer, self.user, ist_anwesend=name in namen,
            )

    def _voten(self, top, mapping):
        voten = {str(self.teilnehmer[n].id): v for n, v in mapping.items()}
        return durchfuehrung_service.erfasse_einzelstimmen(top, self.user, voten)


class DoppeltQualifiziertBewertungTest(_DoppeltBasis):

    def test_angenommen_wenn_beide_achsen_erfuellt(self):
        # 3 von 4 Köpfen (75 % > 66,67 %), MEA 920/1000 (92 % >= 50 %).
        self._anwesend('Gross', 'Zwei', 'Drei', 'Vier')
        top = self._top()
        self._voten(top, {'Gross': 'ja', 'Zwei': 'ja', 'Drei': 'ja', 'Vier': 'nein'})
        top.refresh_from_db()
        self.assertEqual(top.abstimmungsergebnis, 'angenommen')
        self.assertEqual(top.abstimmung_ja, Decimal('3.0000'))        # Köpfe
        self.assertEqual(top.abstimmung_nein, Decimal('1.0000'))
        self.assertEqual(top.abstimmung_ja_2, Decimal('920.0000'))    # MEA
        self.assertEqual(top.abstimmung_nein_2, Decimal('80.0000'))

    def test_abgelehnt_wenn_kopf_achse_scheitert(self):
        # 2 von 4 Köpfen (50 %, nicht > 66,67 %) — obwohl MEA 800/1000 (80 %) ok.
        self._anwesend('Gross', 'Zwei', 'Drei', 'Vier')
        top = self._top()
        self._voten(top, {'Gross': 'ja', 'Zwei': 'ja', 'Drei': 'nein', 'Vier': 'nein'})
        top.refresh_from_db()
        self.assertEqual(top.abstimmungsergebnis, 'abgelehnt')

    def test_abgelehnt_wenn_mea_achse_scheitert(self):
        # Köpfe ok (3 von 4 = 75 %), aber die kleinen Eigentümer tragen nur
        # 400/1000 MEA (40 % < 50 %) — der Großeigentümer stimmt dagegen.
        self._anwesend('Gross', 'Zwei', 'Drei', 'Vier')
        top = self._top()
        self._voten(top, {'Zwei': 'ja', 'Drei': 'ja', 'Vier': 'ja', 'Gross': 'nein'})
        top.refresh_from_db()
        self.assertEqual(top.abstimmungsergebnis, 'abgelehnt')
        self.assertEqual(top.abstimmung_ja_2, Decimal('400.0000'))

    def test_mea_achse_misst_gegen_gesamt_nicht_gegen_abgegebene(self):
        # Nur zwei kleine Eigentümer anwesend, beide Ja: Köpfe 2/2 = 100 %,
        # aber MEA 320/1000 (32 %) < 50 % — Abwesende zählen gegen den Antrag.
        self._anwesend('Zwei', 'Drei')
        top = self._top()
        self._voten(top, {'Zwei': 'ja', 'Drei': 'ja'})
        top.refresh_from_db()
        self.assertEqual(top.abstimmungsergebnis, 'abgelehnt')
        self.assertEqual(top.abstimmung_ja, Decimal('2.0000'))      # Köpfe
        self.assertEqual(top.abstimmung_ja_2, Decimal('320.0000'))  # MEA

    def test_kopf_schwelle_ist_strikt_groesser(self):
        # Schwelle 50 %, genau 2 von 4 Köpfen (50 %) — "mehr als" ist NICHT
        # erfüllt (strikt >), also abgelehnt, obwohl MEA klar über 50 % liegt.
        self._anwesend('Gross', 'Zwei', 'Drei', 'Vier')
        top = self._top(s1='50.00', s2='50.00')
        self._voten(top, {'Gross': 'ja', 'Zwei': 'ja', 'Drei': 'nein', 'Vier': 'nein'})
        top.refresh_from_db()
        self.assertEqual(top.abstimmungsergebnis, 'abgelehnt')

    def test_enthaltung_zaehlt_bei_kopf_achse_nicht_in_den_nenner(self):
        # 2 Ja, 1 Enthaltung, 1 Nein: abgegeben (Ja+Nein) = 3 Köpfe, Ja-Anteil
        # 2/3 = 66,66 % — nicht > 66,67 % -> abgelehnt (Enthaltung zählt nicht).
        self._anwesend('Gross', 'Zwei', 'Drei', 'Vier')
        top = self._top()
        self._voten(top, {'Gross': 'ja', 'Zwei': 'ja', 'Drei': 'enthaltung', 'Vier': 'nein'})
        top.refresh_from_db()
        self.assertEqual(top.abstimmungsergebnis, 'abgelehnt')


class DoppeltQualifiziertValidierungTest(_DoppeltBasis):

    def test_summenpfad_verweigert_doppelt(self):
        # Eine einachsige Summenbewertung darf die doppelt qualifizierte Mehrheit
        # nicht beurteilen.
        top = self._top()
        with self.assertRaises(ValidationError):
            durchfuehrung_service.bewerte_ergebnis(
                top, Decimal('3'), Decimal('1'), Decimal('0'), Decimal('4'),
            )

    def test_erfasse_abstimmung_verweigert_doppelt(self):
        self._anwesend('Gross', 'Zwei', 'Drei', 'Vier')
        top = self._top()
        with self.assertRaises(ValidationError):
            durchfuehrung_service.erfasse_abstimmung(
                top, self.user, ja=3, nein=1, enthaltung=0,
            )


class DoppeltQualifiziertGrundlagenPflichtTest(TestCase):
    """Ohne MEA-Stimmgrundlage darf kein doppelt qualifizierter TOP entstehen."""

    def setUp(self):
        self.user = f.user()
        self.objekt = f.objekt()
        for index in range(1, 4):
            f.eigentuemer(self.objekt, f.person(nachname=f'P{index}'), nr=f'{index:03d}')
        # EV nur mit Kopfprinzip — KEINE MEA-Stimmgrundlage ergänzt.
        self.ev = ev_service.erstelle_ev(
            objekt=self.objekt, erstellt_von=self.user, stimmprinzip='kopf',
        )

    def test_doppelt_ohne_mea_grundlage_abgelehnt(self):
        with self.assertRaises(ValidationError):
            tagesordnung_service.top_anlegen(
                ev=self.ev, titel='TOP', erstellt_von=self.user,
                beschlussvorlage='Es wird beschlossen.',
                abstimmungsmodus='doppelt_qualifiziert',
                mehrheit_schwelle=Decimal('66.67'),
                mehrheit_schwelle_2=Decimal('50.00'),
            )

    def test_doppelt_ohne_zweite_schwelle_abgelehnt(self):
        with self.assertRaises(ValidationError):
            tagesordnung_service.top_anlegen(
                ev=self.ev, titel='TOP', erstellt_von=self.user,
                beschlussvorlage='Es wird beschlossen.',
                abstimmungsmodus='doppelt_qualifiziert',
                mehrheit_schwelle=Decimal('66.67'),
            )


class DoppeltQualifiziertSerializerTest(_DoppeltBasis):
    """API-Vertrag v1.5: Serializer-Felder und doppelt_achsen."""

    def test_read_serializer_liefert_doppelt_achsen(self):
        top = self._top()
        data = TagesordnungspunktSerializer(top).data
        self.assertEqual(data['mehrheit_schwelle'], '66.67')
        self.assertEqual(data['mehrheit_schwelle_2'], '50.00')
        self.assertIn('abstimmung_ja_2', data)
        self.assertIn('abstimmung_nein_2', data)

        kopf_g = self.ev.stimmgrundlagen.get(ist_kopfprinzip=True)
        mea_g = self.ev.stimmgrundlagen.get(verteilerschluessel__vs_typ='mea')
        achsen = data['doppelt_achsen']
        self.assertEqual(achsen['koepfe']['stimmgrundlage_id'], str(kopf_g.id))
        self.assertEqual(achsen['koepfe']['schwelle'], '66.67')
        self.assertEqual(achsen['koepfe']['vergleich'], 'groesser')
        self.assertEqual(achsen['mea']['stimmgrundlage_id'], str(mea_g.id))
        self.assertEqual(achsen['mea']['schwelle'], '50.00')
        self.assertEqual(achsen['mea']['vergleich'], 'groesser_gleich')

    def test_doppelt_achsen_null_bei_anderem_modus(self):
        top = tagesordnung_service.top_anlegen(
            ev=self.ev, titel='Normaler TOP', erstellt_von=self.user,
            beschlussvorlage='Es wird beschlossen.',
            abstimmungsmodus='einfache_mehrheit',
        )
        data = TagesordnungspunktSerializer(top).data
        self.assertIsNone(data['doppelt_achsen'])

    def test_create_serializer_akzeptiert_zweite_schwelle(self):
        serializer = TagesordnungspunktCreateSerializer(data={
            'ev': str(self.ev.id), 'titel': 'Bauliche Veränderung',
            'beschlussvorlage': 'Es wird beschlossen.',
            'abstimmungsmodus': 'doppelt_qualifiziert',
            'mehrheit_schwelle': '66.67', 'mehrheit_schwelle_2': '50.00',
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data['mehrheit_schwelle_2'], Decimal('50.00'))


class DoppeltQualifiziertToolErgebnisTest(_DoppeltBasis):
    """API-Vertrag v1.5: der ergebnis-Block trägt die 2. Achse (ja_2/nein_2),
    und immocore übernimmt die Entscheidung des Tools 1:1."""

    def test_tool_ergebnis_mit_zweiter_achse_wird_uebernommen(self):
        self._anwesend('Gross', 'Zwei', 'Drei', 'Vier')
        top = self._top()
        voten = {
            str(self.teilnehmer[n].id): v for n, v in
            {'Gross': 'ja', 'Zwei': 'ja', 'Drei': 'ja', 'Vier': 'nein'}.items()
        }
        # Das Tool meldet bewusst 'abgelehnt', obwohl die Stimmen rechnerisch
        # angenommen ergäben — immocore übernimmt 1:1 und bewertet NICHT neu.
        durchfuehrung_service.erfasse_einzelstimmen(
            top, self.user, voten,
            ergebnis={
                'ja': '3.0000', 'nein': '1.0000', 'enthaltung': '0.0000',
                'ja_2': '920.0000', 'nein_2': '80.0000', 'ergebnis': 'abgelehnt',
            },
        )
        top.refresh_from_db()
        self.assertEqual(top.abstimmungsergebnis, 'abgelehnt')      # 1:1 übernommen
        self.assertEqual(top.abstimmung_ja, Decimal('3.0000'))     # Köpfe
        self.assertEqual(top.abstimmung_nein, Decimal('1.0000'))
        self.assertEqual(top.abstimmung_ja_2, Decimal('920.0000'))  # MEA
        self.assertEqual(top.abstimmung_nein_2, Decimal('80.0000'))
