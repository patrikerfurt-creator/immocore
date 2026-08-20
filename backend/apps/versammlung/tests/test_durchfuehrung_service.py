"""
Tests für ``apps.versammlung.services.durchfuehrung_service``
(Spec v1.1 Kap. 3 und 6.1, Phase D).

Deckt ab:
  - erfasse_anwesenheit: an/ab/offen, Vertretung, Selbstvertretung, Ereignis
  - erfasse_zusage: manuell und Portal-Quelle
  - bewerte_ergebnis: alle vier Modi inkl. Grenzfälle (Ja=Nein, alles
    Enthaltung, 0 Anwesende, Allstimmigkeit gegen Gesamtstimmkraft)
  - Enthaltungen zählen NICHT in den Nenner
  - Plausibilität: Stimmen > anwesende Stimmkraft, negative Stimmen
  - kein Quorum-Gate: Abstimmung auch unter 50 % Anwesenheit möglich
  - erfasse_einzelstimmen: Summen abgeleitet, Abwesende abgewiesen, Ersetzen
  - schliesse_durchfuehrung_ab: offene TOPs blockieren, kein_beschluss nicht
  - Sperre nach Beschlussverarbeitung
"""
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.versammlung.models import EVStimme
from apps.versammlung.services import (
    durchfuehrung_service, ev_service, stimmkraft_service, tagesordnung_service,
)
from apps.versammlung.tests import factories as f


class _Basis(TestCase):
    """EV mit drei Eigentümern, Stimmkraft nach VS 030 → je 1 Stimme."""

    def setUp(self):
        self.user = f.user()
        self.objekt = f.objekt()
        self.personen = [
            f.person(nachname=name) for name in ('Alpha', 'Beta', 'Gamma')
        ]
        self.einheiten = []
        for index, person in enumerate(self.personen, start=1):
            einheit, _ = f.eigentuemer(self.objekt, person, nr=f'{index:03d}')
            self.einheiten.append(einheit)
        self.vs = f.einheiten_schluessel(self.objekt, self.einheiten)

        self.ev = ev_service.erstelle_ev(
            objekt=self.objekt, erstellt_von=self.user,
            stimmprinzip='verteilerschluessel', stimm_verteilerschluessel=self.vs,
        )
        ev_service.aktualisiere_terminierung(
            self.ev, self.user,
            termin=timezone.now() - timedelta(hours=2), ort='Gemeinschaftsraum',
        )
        stimmkraft_service.ermittle_teilnehmer(self.ev, self.user)
        self.teilnehmer = {
            t.person.nachname: t
            for t in self.ev.teilnehmer.select_related('person')
        }

    def _top(self, modus='einfache_mehrheit', schwelle=None, titel='TOP'):
        return tagesordnung_service.top_anlegen(
            ev=self.ev, titel=titel, erstellt_von=self.user,
            beschlussvorlage='Es wird beschlossen.',
            abstimmungsmodus=modus, mehrheit_schwelle=schwelle,
        )

    def _anwesend(self, *nachnamen):
        for nachname, teilnehmer in self.teilnehmer.items():
            durchfuehrung_service.erfasse_anwesenheit(
                teilnehmer, self.user, ist_anwesend=nachname in nachnamen,
            )


class AnwesenheitTest(_Basis):
    def test_anwesenheit_setzen(self):
        teilnehmer = self.teilnehmer['Alpha']
        durchfuehrung_service.erfasse_anwesenheit(
            teilnehmer, self.user, ist_anwesend=True,
        )
        teilnehmer.refresh_from_db()
        self.assertTrue(teilnehmer.ist_anwesend)
        self.assertIsNotNone(teilnehmer.anwesenheit_erfasst_am)

    def test_zuruecksetzen_auf_offen(self):
        teilnehmer = self.teilnehmer['Alpha']
        durchfuehrung_service.erfasse_anwesenheit(
            teilnehmer, self.user, ist_anwesend=True,
        )
        durchfuehrung_service.erfasse_anwesenheit(
            teilnehmer, self.user, ist_anwesend=None,
        )
        teilnehmer.refresh_from_db()
        self.assertIsNone(teilnehmer.ist_anwesend)
        self.assertIsNone(teilnehmer.anwesenheit_erfasst_am)

    def test_ungueltiger_wert(self):
        with self.assertRaises(ValidationError):
            durchfuehrung_service.erfasse_anwesenheit(
                self.teilnehmer['Alpha'], self.user, ist_anwesend='vielleicht',
            )

    def test_vertretung_durch_person(self):
        vertreten = self.teilnehmer['Beta']
        durchfuehrung_service.erfasse_anwesenheit(
            vertreten, self.user, ist_anwesend=True,
            vertreten_durch=self.personen[0],
        )
        vertreten.refresh_from_db()
        self.assertEqual(vertreten.vertreten_durch_id, self.personen[0].id)
        # Die Stimmkraft bleibt beim Vertretenen, der Vertreter behält seine.
        self.assertEqual(vertreten.stimmkraft, Decimal('1'))
        self.assertEqual(self.teilnehmer['Alpha'].stimmkraft, Decimal('1'))

    def test_vertretung_als_freitext(self):
        teilnehmer = self.teilnehmer['Beta']
        durchfuehrung_service.erfasse_anwesenheit(
            teilnehmer, self.user, ist_anwesend=True,
            vertreter_name='RA Schmitt',
        )
        teilnehmer.refresh_from_db()
        self.assertEqual(teilnehmer.vertreter_name, 'RA Schmitt')

    def test_selbstvertretung_wird_abgelehnt(self):
        teilnehmer = self.teilnehmer['Alpha']
        with self.assertRaises(ValidationError):
            durchfuehrung_service.erfasse_anwesenheit(
                teilnehmer, self.user, ist_anwesend=True,
                vertreten_durch=teilnehmer.person,
            )

    def test_ereignis_nennt_person_und_vertretung(self):
        durchfuehrung_service.erfasse_anwesenheit(
            self.teilnehmer['Beta'], self.user, ist_anwesend=True,
            vertreten_durch=self.personen[0],
        )
        ereignis = self.ev.ereignisse.filter(typ='anwesenheit_erfasst').last()
        self.assertIn('Beta', ereignis.text)
        self.assertIn('vertreten durch', ereignis.text)


class ZusageTest(_Basis):
    def test_zusage_manuell(self):
        teilnehmer = self.teilnehmer['Alpha']
        durchfuehrung_service.erfasse_zusage(
            teilnehmer, self.user, zusage_status='zugesagt',
        )
        teilnehmer.refresh_from_db()
        self.assertEqual(teilnehmer.zusage_status, 'zugesagt')
        self.assertEqual(teilnehmer.zusage_quelle, 'manuell')
        self.assertIsNotNone(teilnehmer.zusage_am)

    def test_absage_und_zuruecksetzen(self):
        teilnehmer = self.teilnehmer['Alpha']
        durchfuehrung_service.erfasse_zusage(
            teilnehmer, self.user, zusage_status='abgesagt', quelle='portal',
        )
        teilnehmer.refresh_from_db()
        self.assertEqual(teilnehmer.zusage_quelle, 'portal')

        durchfuehrung_service.erfasse_zusage(
            teilnehmer, self.user, zusage_status='offen',
        )
        teilnehmer.refresh_from_db()
        self.assertIsNone(teilnehmer.zusage_am)
        self.assertEqual(teilnehmer.zusage_quelle, '')

    def test_unbekannter_status(self):
        with self.assertRaises(ValidationError):
            durchfuehrung_service.erfasse_zusage(
                self.teilnehmer['Alpha'], self.user, zusage_status='vielleicht',
            )

    def test_unbekannte_quelle(self):
        with self.assertRaises(ValidationError):
            durchfuehrung_service.erfasse_zusage(
                self.teilnehmer['Alpha'], self.user,
                zusage_status='zugesagt', quelle='brieftaube',
            )


class BewertungTest(_Basis):
    """Reine Bewertungslogik — Spec v1.1 Kap. 6.1."""

    def _bewerte(self, modus, ja, nein, enthaltung=0, gesamt=3, schwelle=None):
        top = self._top(modus=modus, schwelle=schwelle, titel=f'TOP {modus} {ja}/{nein}')
        return durchfuehrung_service.bewerte_ergebnis(
            top, Decimal(str(ja)), Decimal(str(nein)), Decimal(str(enthaltung)),
            Decimal(str(gesamt)),
        )

    def test_einfache_mehrheit_angenommen(self):
        self.assertEqual(self._bewerte('einfache_mehrheit', 2, 1), 'angenommen')

    def test_einfache_mehrheit_stimmengleichheit_abgelehnt(self):
        # Ja = Nein ist keine Mehrheit.
        self.assertEqual(self._bewerte('einfache_mehrheit', 1, 1), 'abgelehnt')

    def test_einfache_mehrheit_enthaltungen_zaehlen_nicht(self):
        # 1 Ja, 0 Nein, 2 Enthaltungen → angenommen, obwohl Ja < Hälfte aller.
        self.assertEqual(self._bewerte('einfache_mehrheit', 1, 0, 2), 'angenommen')

    def test_einfache_mehrheit_nur_enthaltungen(self):
        self.assertEqual(self._bewerte('einfache_mehrheit', 0, 0, 3), 'abgelehnt')

    def test_qualifizierte_mehrheit_genau_auf_der_schwelle(self):
        # 2 von 3 abgegebenen = 66,67 % → erreicht die Schwelle 66.67.
        self.assertEqual(
            self._bewerte('qualifizierte_mehrheit', 2, 1, schwelle=Decimal('66.67')),
            'angenommen',
        )

    def test_qualifizierte_mehrheit_knapp_darunter(self):
        # 3 von 5 abgegebenen = 60 %.
        self.assertEqual(
            self._bewerte('qualifizierte_mehrheit', 3, 2, gesamt=5,
                          schwelle=Decimal('66.67')),
            'abgelehnt',
        )

    def test_qualifizierte_mehrheit_ohne_abgegebene_stimmen(self):
        self.assertEqual(
            self._bewerte('qualifizierte_mehrheit', 0, 0, 3, schwelle=Decimal('66.67')),
            'abgelehnt',
        )

    def test_einstimmigkeit_mit_enthaltung(self):
        # Keine Nein-Stimme → angenommen, Enthaltung schadet nicht.
        self.assertEqual(self._bewerte('einstimmigkeit', 2, 0, 1), 'angenommen')

    def test_einstimmigkeit_mit_nein(self):
        self.assertEqual(self._bewerte('einstimmigkeit', 2, 1), 'abgelehnt')

    def test_einstimmigkeit_ohne_ja(self):
        self.assertEqual(self._bewerte('einstimmigkeit', 0, 0, 3), 'abgelehnt')

    def test_allstimmigkeit_braucht_alle_stimmen(self):
        # Alle drei Stimmen Ja → angenommen.
        self.assertEqual(self._bewerte('allstimmigkeit', 3, 0, gesamt=3), 'angenommen')

    def test_allstimmigkeit_scheitert_an_abwesenden(self):
        # Einstimmig unter den zwei Anwesenden, aber ein Eigentümer fehlt.
        self.assertEqual(self._bewerte('allstimmigkeit', 2, 0, gesamt=3), 'abgelehnt')

    def test_kein_beschluss_hat_kein_ergebnis(self):
        with self.assertRaises(ValidationError):
            self._bewerte('kein_beschluss', 1, 0)


class AbstimmungErfassenTest(_Basis):
    def test_erfassung_setzt_ergebnis(self):
        self._anwesend('Alpha', 'Beta', 'Gamma')
        top = self._top()
        durchfuehrung_service.erfasse_abstimmung(top, self.user, ja=2, nein=1)
        top.refresh_from_db()
        self.assertEqual(top.abstimmungsergebnis, 'angenommen')
        self.assertEqual(top.abstimmung_ja, Decimal('2'))
        self.assertTrue(self.ev.ereignisse.filter(typ='abstimmung_erfasst').exists())

    def test_kein_quorum_gate(self):
        # Nur einer von drei anwesend — Abstimmung ist trotzdem möglich
        # (§ 25 Abs. 3 WEG a.F. ist aufgehoben).
        self._anwesend('Alpha')
        quorum = stimmkraft_service.berechne_quorum(self.ev)
        self.assertEqual(quorum['anwesend_prozent'], Decimal('33.33'))

        top = self._top()
        durchfuehrung_service.erfasse_abstimmung(top, self.user, ja=1, nein=0)
        top.refresh_from_db()
        self.assertEqual(top.abstimmungsergebnis, 'angenommen')

    def test_summe_ueber_anwesender_stimmkraft(self):
        self._anwesend('Alpha')
        top = self._top()
        with self.assertRaises(ValidationError) as ctx:
            durchfuehrung_service.erfasse_abstimmung(top, self.user, ja=2, nein=1)
        self.assertIn('übersteigen', str(ctx.exception))
        top.refresh_from_db()
        self.assertEqual(top.abstimmungsergebnis, 'offen')

    def test_negative_stimmen(self):
        self._anwesend('Alpha', 'Beta', 'Gamma')
        top = self._top()
        with self.assertRaises(ValidationError):
            durchfuehrung_service.erfasse_abstimmung(top, self.user, ja=-1, nein=0)

    def test_korrektur_wird_als_solche_protokolliert(self):
        self._anwesend('Alpha', 'Beta', 'Gamma')
        top = self._top()
        durchfuehrung_service.erfasse_abstimmung(top, self.user, ja=2, nein=1)
        durchfuehrung_service.erfasse_abstimmung(top, self.user, ja=1, nein=2)
        top.refresh_from_db()
        self.assertEqual(top.abstimmungsergebnis, 'abgelehnt')
        korrektur = self.ev.ereignisse.get(typ='abstimmung_korrigiert')
        self.assertIn('2', korrektur.alter_wert)

    def test_bemerkung_wird_gespeichert(self):
        self._anwesend('Alpha', 'Beta', 'Gamma')
        top = self._top()
        durchfuehrung_service.erfasse_abstimmung(
            top, self.user, ja=3, nein=0, bemerkung='Einstimmig ohne Diskussion.',
        )
        top.refresh_from_db()
        self.assertEqual(top.ergebnis_bemerkung, 'Einstimmig ohne Diskussion.')

    def test_vertagen_und_entfallen(self):
        top = self._top()
        durchfuehrung_service.setze_ergebnis_status(
            top, self.user, 'vertagt', 'Unterlagen fehlten.',
        )
        top.refresh_from_db()
        self.assertEqual(top.abstimmungsergebnis, 'vertagt')
        self.assertEqual(top.abstimmung_ja, Decimal('0'))

        with self.assertRaises(ValidationError):
            durchfuehrung_service.setze_ergebnis_status(top, self.user, 'angenommen')


class EinzelstimmenTest(_Basis):
    def test_summen_werden_abgeleitet(self):
        self._anwesend('Alpha', 'Beta', 'Gamma')
        top = self._top()
        durchfuehrung_service.erfasse_einzelstimmen(top, self.user, {
            str(self.teilnehmer['Alpha'].id): 'ja',
            str(self.teilnehmer['Beta'].id): 'ja',
            str(self.teilnehmer['Gamma'].id): 'nein',
        })
        top.refresh_from_db()
        self.assertEqual(top.abstimmung_ja, Decimal('2'))
        self.assertEqual(top.abstimmung_nein, Decimal('1'))
        self.assertEqual(top.abstimmungsergebnis, 'angenommen')
        self.assertEqual(top.stimmen.count(), 3)

    def test_abwesende_werden_abgewiesen(self):
        self._anwesend('Alpha')
        top = self._top()
        with self.assertRaises(ValidationError) as ctx:
            durchfuehrung_service.erfasse_einzelstimmen(top, self.user, {
                str(self.teilnehmer['Alpha'].id): 'ja',
                str(self.teilnehmer['Beta'].id): 'ja',
            })
        self.assertIn('Beta', str(ctx.exception))
        top.refresh_from_db()
        self.assertEqual(top.abstimmungsergebnis, 'offen')
        self.assertEqual(EVStimme.objects.filter(top=top).count(), 0)

    def test_unbekannter_teilnehmer(self):
        self._anwesend('Alpha')
        top = self._top()
        with self.assertRaises(ValidationError):
            durchfuehrung_service.erfasse_einzelstimmen(
                top, self.user, {'11111111-1111-1111-1111-111111111111': 'ja'},
            )

    def test_unbekanntes_votum(self):
        self._anwesend('Alpha')
        top = self._top()
        with self.assertRaises(ValidationError):
            durchfuehrung_service.erfasse_einzelstimmen(
                top, self.user, {str(self.teilnehmer['Alpha'].id): 'enthalten'},
            )

    def test_erneute_erfassung_ersetzt(self):
        self._anwesend('Alpha', 'Beta', 'Gamma')
        top = self._top()
        durchfuehrung_service.erfasse_einzelstimmen(top, self.user, {
            str(self.teilnehmer['Alpha'].id): 'ja',
        })
        durchfuehrung_service.erfasse_einzelstimmen(top, self.user, {
            str(self.teilnehmer['Alpha'].id): 'nein',
            str(self.teilnehmer['Beta'].id): 'nein',
        })
        top.refresh_from_db()
        self.assertEqual(top.stimmen.count(), 2)
        self.assertEqual(top.abstimmung_nein, Decimal('2'))
        self.assertEqual(top.abstimmung_ja, Decimal('0'))

    def test_stimmkraft_wird_je_stimme_gespeichert(self):
        # Alpha bekommt eine zweite Einheit → 2 Stimmen nach VS 030.
        vierte, _ = f.eigentuemer(self.objekt, self.personen[0], nr='004')
        f.vs_wert(self.vs, vierte, '1')
        stimmkraft_service.stimmkraft_neu_ermitteln(self.ev, self.user)
        teilnehmer = self.ev.teilnehmer.get(person=self.personen[0])
        durchfuehrung_service.erfasse_anwesenheit(
            teilnehmer, self.user, ist_anwesend=True,
        )
        top = self._top()
        durchfuehrung_service.erfasse_einzelstimmen(
            top, self.user, {str(teilnehmer.id): 'ja'},
        )
        stimme = top.stimmen.get()
        self.assertEqual(stimme.stimmkraft, Decimal('2'))
        top.refresh_from_db()
        self.assertEqual(top.abstimmung_ja, Decimal('2'))


class DurchfuehrungAbschliessenTest(_Basis):
    def test_offene_tops_blockieren(self):
        self._top(titel='Mit Beschluss')
        with self.assertRaises(ValidationError) as ctx:
            durchfuehrung_service.schliesse_durchfuehrung_ab(self.ev, self.user)
        self.assertIn('TOP 1', str(ctx.exception))

    def test_kein_beschluss_blockiert_nicht(self):
        tagesordnung_service.top_anlegen(
            ev=self.ev, titel='Bericht', erstellt_von=self.user,
            beschlussvorlage='', abstimmungsmodus='kein_beschluss',
        )
        durchfuehrung_service.schliesse_durchfuehrung_ab(self.ev, self.user)
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.status, 'durchgefuehrt')
        self.assertTrue(self.ev.task4_durchfuehrung_erledigt)

    def test_vertagter_top_blockiert_nicht(self):
        top = self._top()
        durchfuehrung_service.setze_ergebnis_status(top, self.user, 'vertagt')
        durchfuehrung_service.schliesse_durchfuehrung_ab(self.ev, self.user)
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.status, 'durchgefuehrt')

    def test_abschluss_ohne_versand_moeglich(self):
        # Status ist 'in_bearbeitung' (nie versendet) — der Statusgraph darf
        # die Durchführung nicht blockieren.
        self._anwesend('Alpha', 'Beta', 'Gamma')
        top = self._top()
        durchfuehrung_service.erfasse_abstimmung(top, self.user, ja=3, nein=0)
        durchfuehrung_service.schliesse_durchfuehrung_ab(self.ev, self.user)
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.status, 'durchgefuehrt')
        self.assertIsNotNone(self.ev.durchgefuehrt_am)

    def test_sperre_nach_beschlussverarbeitung(self):
        self._anwesend('Alpha', 'Beta', 'Gamma')
        top = self._top()
        durchfuehrung_service.erfasse_abstimmung(top, self.user, ja=3, nein=0)
        durchfuehrung_service.schliesse_durchfuehrung_ab(self.ev, self.user)
        ev_service.wechsle_status(self.ev, 'beschluesse_verarbeitet', self.user)

        with self.assertRaises(ValidationError) as ctx:
            durchfuehrung_service.erfasse_abstimmung(top, self.user, ja=0, nein=3)
        self.assertIn('nicht mehr änderbar', str(ctx.exception))
