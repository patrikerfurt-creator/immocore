"""
Tests für ``apps.versammlung.models`` (Spec v1.1 Kap. 4).

Deckt ab:
  - EV nur für WEG-Objekte (clean)
  - Tagesordnungspunkt: Beschlussvorlage-Pflicht, Schwelle nur bei
    qualifizierter Mehrheit, Unique (ev, nummer)
  - EVTeilnehmer: Selbstvertretung, Unique (ev, person)
  - EVStimme: TOP und Teilnehmer aus derselben EV, Unique (top, teilnehmer)
  - Beschluss: fortlaufende Nummer je Objekt, Konsistenz TOP/EV/Objekt
  - EVVersandprotokoll: Wiederholversand ist protokollierbar
"""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.versammlung.models import (
    Beschluss, BeschlussNummerZaehler, EVStimme, EVTeilnehmer,
    EVVersandprotokoll, Eigentuemerversammlung, Tagesordnungspunkt,
)
from apps.versammlung.tests import factories as f


class EigentuemerversammlungModelTest(TestCase):
    def setUp(self):
        self.user = f.user()

    def test_weg_objekt_ist_zulaessig(self):
        ev = Eigentuemerversammlung(objekt=f.objekt(), erstellt_von=self.user)
        ev.full_clean()  # darf nicht werfen

    def test_sev_objekt_wird_abgelehnt(self):
        ev = Eigentuemerversammlung(objekt=f.objekt(typ='SEV'), erstellt_von=self.user)
        with self.assertRaises(ValidationError) as ctx:
            ev.full_clean()
        self.assertIn('WEG-Objekte', str(ctx.exception))

    def test_kleingeschriebenes_weg_wird_akzeptiert(self):
        # Ältere Testdaten enthalten 'weg' statt 'WEG' — fachlich dasselbe.
        ev = Eigentuemerversammlung(objekt=f.objekt(typ='weg'), erstellt_von=self.user)
        ev.full_clean()

    def test_str_ohne_termin(self):
        ev = Eigentuemerversammlung.objects.create(
            objekt=f.objekt(bezeichnung='WEG Rottplatz'), erstellt_von=self.user,
            arbeitsname='EV 2026',
        )
        self.assertIn('ohne Termin', str(ev))
        self.assertIn('WEG Rottplatz', str(ev))


class TagesordnungspunktModelTest(TestCase):
    def setUp(self):
        self.ev = Eigentuemerversammlung.objects.create(
            objekt=f.objekt(), erstellt_von=f.user(),
        )

    def _top(self, **kwargs):
        daten = {'ev': self.ev, 'nummer': 1, 'titel': 'TOP',
                 'beschlussvorlage': 'Es wird beschlossen.'}
        daten.update(kwargs)
        return Tagesordnungspunkt(**daten)

    def test_beschlussvorlage_pflicht_bei_abstimmung(self):
        with self.assertRaises(ValidationError) as ctx:
            self._top(beschlussvorlage='   ').full_clean()
        self.assertIn('beschlussvorlage', ctx.exception.message_dict)

    def test_kein_beschluss_braucht_keine_vorlage(self):
        self._top(beschlussvorlage='', abstimmungsmodus='kein_beschluss').full_clean()

    def test_qualifizierte_mehrheit_braucht_schwelle(self):
        with self.assertRaises(ValidationError) as ctx:
            self._top(abstimmungsmodus='qualifizierte_mehrheit').full_clean()
        self.assertIn('mehrheit_schwelle', ctx.exception.message_dict)

    def test_schwelle_nur_bei_qualifizierter_mehrheit(self):
        with self.assertRaises(ValidationError) as ctx:
            self._top(abstimmungsmodus='einfache_mehrheit',
                      mehrheit_schwelle=Decimal('66.67')).full_clean()
        self.assertIn('mehrheit_schwelle', ctx.exception.message_dict)

    def test_nummer_je_ev_eindeutig(self):
        self._top().save()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._top(titel='Zweiter mit Nummer 1').save()


class EVTeilnehmerModelTest(TestCase):
    def setUp(self):
        self.ev = Eigentuemerversammlung.objects.create(
            objekt=f.objekt(), erstellt_von=f.user(),
        )
        self.person = f.person()

    def test_selbstvertretung_wird_abgelehnt(self):
        teilnehmer = EVTeilnehmer(ev=self.ev, person=self.person,
                                  vertreten_durch=self.person)
        with self.assertRaises(ValidationError) as ctx:
            teilnehmer.full_clean()
        self.assertIn('vertreten_durch', ctx.exception.message_dict)

    def test_person_je_ev_nur_einmal(self):
        EVTeilnehmer.objects.create(ev=self.ev, person=self.person)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                EVTeilnehmer.objects.create(ev=self.ev, person=self.person)

    def test_anwesenheit_ist_dreiwertig(self):
        teilnehmer = EVTeilnehmer.objects.create(ev=self.ev, person=self.person)
        self.assertIsNone(teilnehmer.ist_anwesend)
        teilnehmer.ist_anwesend = False
        teilnehmer.full_clean()
        teilnehmer.save()
        self.assertIs(EVTeilnehmer.objects.get(pk=teilnehmer.pk).ist_anwesend, False)


class EVStimmeModelTest(TestCase):
    def setUp(self):
        self.user = f.user()
        self.objekt = f.objekt()
        self.ev = Eigentuemerversammlung.objects.create(
            objekt=self.objekt, erstellt_von=self.user,
        )
        self.top = Tagesordnungspunkt.objects.create(
            ev=self.ev, nummer=1, titel='TOP 1', beschlussvorlage='Beschluss.',
        )
        self.teilnehmer = EVTeilnehmer.objects.create(
            ev=self.ev, person=f.person(), stimmkraft=Decimal('1'),
        )

    def test_stimme_wird_gespeichert(self):
        stimme = EVStimme(top=self.top, teilnehmer=self.teilnehmer, votum='ja',
                          stimmkraft=Decimal('1'), erfasst_von=self.user)
        stimme.full_clean()
        stimme.save()
        self.assertEqual(self.top.stimmen.count(), 1)

    def test_teilnehmer_fremder_ev_wird_abgelehnt(self):
        fremde_ev = Eigentuemerversammlung.objects.create(
            objekt=self.objekt, erstellt_von=self.user, arbeitsname='Andere EV',
        )
        fremder = EVTeilnehmer.objects.create(ev=fremde_ev, person=f.person())
        stimme = EVStimme(top=self.top, teilnehmer=fremder, votum='ja',
                          stimmkraft=Decimal('1'), erfasst_von=self.user)
        with self.assertRaises(ValidationError):
            stimme.full_clean()

    def test_ein_votum_je_top_und_teilnehmer(self):
        EVStimme.objects.create(top=self.top, teilnehmer=self.teilnehmer,
                                votum='ja', stimmkraft=Decimal('1'),
                                erfasst_von=self.user)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                EVStimme.objects.create(top=self.top, teilnehmer=self.teilnehmer,
                                        votum='nein', stimmkraft=Decimal('1'),
                                        erfasst_von=self.user)


class BeschlussModelTest(TestCase):
    def setUp(self):
        self.user = f.user()
        self.objekt = f.objekt()
        self.ev = Eigentuemerversammlung.objects.create(
            objekt=self.objekt, erstellt_von=self.user,
        )

    def _beschluss(self, **kwargs):
        daten = {
            'objekt': self.objekt, 'ev': self.ev,
            'beschluss_datum': date(2026, 3, 15),
            'wortlaut': 'Der Wirtschaftsplan wird beschlossen.',
            'erstellt_von': self.user,
        }
        daten.update(kwargs)
        return Beschluss.objects.create(**daten)

    def test_nummer_laeuft_je_objekt_fortlaufend(self):
        self.assertEqual(self._beschluss().nummer, 1)
        self.assertEqual(self._beschluss().nummer, 2)
        self.assertEqual(self._beschluss().nummer, 3)
        self.assertEqual(
            BeschlussNummerZaehler.objects.get(objekt=self.objekt).letzter_zaehler, 3,
        )

    def test_nummernkreise_sind_je_objekt_getrennt(self):
        self._beschluss()
        anderes_objekt = f.objekt(bezeichnung='Zweite WEG')
        andere_ev = Eigentuemerversammlung.objects.create(
            objekt=anderes_objekt, erstellt_von=self.user,
        )
        zweiter = self._beschluss(objekt=anderes_objekt, ev=andere_ev)
        self.assertEqual(zweiter.nummer, 1)

    def test_top_muss_zur_ev_gehoeren(self):
        fremde_ev = Eigentuemerversammlung.objects.create(
            objekt=self.objekt, erstellt_von=self.user, arbeitsname='Andere EV',
        )
        fremder_top = Tagesordnungspunkt.objects.create(
            ev=fremde_ev, nummer=1, titel='TOP', beschlussvorlage='Text.',
        )
        beschluss = Beschluss(
            objekt=self.objekt, ev=self.ev, top=fremder_top,
            beschluss_datum=date(2026, 3, 15), wortlaut='Text.',
            erstellt_von=self.user,
        )
        with self.assertRaises(ValidationError):
            beschluss.full_clean()

    def test_ev_muss_zum_objekt_gehoeren(self):
        beschluss = Beschluss(
            objekt=f.objekt(bezeichnung='Fremdes Objekt'), ev=self.ev,
            beschluss_datum=date(2026, 3, 15), wortlaut='Text.',
            erstellt_von=self.user,
        )
        with self.assertRaises(ValidationError):
            beschluss.full_clean()

    def test_umlaufbeschluss_ohne_ev_ist_moeglich(self):
        beschluss = self._beschluss(ev=None, top=None)
        self.assertIsNone(beschluss.ev_id)
        self.assertEqual(beschluss.nummer, 1)


class EVVersandprotokollModelTest(TestCase):
    def test_wiederholversand_ist_protokollierbar(self):
        user = f.user()
        ev = Eigentuemerversammlung.objects.create(
            objekt=f.objekt(), erstellt_von=user,
        )
        person = f.person()
        EVVersandprotokoll.objects.create(
            ev=ev, person=person, kanal='email', status='fehlgeschlagen',
            empfaenger='alt@example.org', fehlertext='Mailbox unbekannt',
            versendet_von=user,
        )
        EVVersandprotokoll.objects.create(
            ev=ev, person=person, kanal='email', status='erfolgreich',
            empfaenger='neu@example.org', versendet_von=user,
        )
        self.assertEqual(
            EVVersandprotokoll.objects.filter(ev=ev, person=person).count(), 2,
        )
