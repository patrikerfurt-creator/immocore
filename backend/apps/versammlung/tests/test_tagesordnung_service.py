"""
Tests für ``apps.versammlung.services.tagesordnung_service`` (Spec v1.1 Kap. 6).

Deckt ab:
  - top_anlegen: automatische Nummer, Einfügen mit Nachrücken, Ereignis
  - top_aktualisieren: nur pflegbare Felder, Ereignis mit alt/neu
  - top_loeschen: Nummernlücke wird geschlossen
  - Sperre nach Einladungsversand (§ 23 Abs. 2 WEG) inkl. erlaubter Ausnahmen
  - pruefe_vollstaendigkeit: leere TO, Lücke, fehlende Vorlage/Schwelle
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.versammlung.services import ev_service, tagesordnung_service
from apps.versammlung.tests import factories as f


class TopAnlegenTest(TestCase):
    def setUp(self):
        self.user = f.user()
        self.ev = ev_service.erstelle_ev(objekt=f.objekt(), erstellt_von=self.user)

    def _top(self, titel, **kwargs):
        return tagesordnung_service.top_anlegen(
            ev=self.ev, titel=titel, erstellt_von=self.user,
            beschlussvorlage=kwargs.pop('beschlussvorlage', 'Es wird beschlossen.'),
            **kwargs,
        )

    def test_nummern_werden_fortlaufend_vergeben(self):
        self.assertEqual(self._top('Erster').nummer, 1)
        self.assertEqual(self._top('Zweiter').nummer, 2)
        self.assertEqual(self._top('Dritter').nummer, 3)

    def test_einfuegen_laesst_folgepunkte_aufrueecken(self):
        self._top('Erster')
        self._top('Zweiter')
        self._top('Dritter')
        neu = self._top('Eingeschoben', nummer=2)
        self.assertEqual(neu.nummer, 2)
        titel = list(self.ev.tagesordnung.order_by('nummer').values_list('titel', flat=True))
        self.assertEqual(titel, ['Erster', 'Eingeschoben', 'Zweiter', 'Dritter'])

    def test_nummer_null_wird_abgelehnt(self):
        with self.assertRaises(ValidationError):
            self._top('Ungültig', nummer=0)

    def test_anlage_erzeugt_ereignis(self):
        top = self._top('Jahresabrechnung')
        ereignis = self.ev.ereignisse.get(typ='top_angelegt')
        self.assertEqual(ereignis.top_id, top.id)
        self.assertIn('Jahresabrechnung', ereignis.text)

    def test_kein_beschluss_ohne_vorlage(self):
        top = self._top('Bericht', beschlussvorlage='', abstimmungsmodus='kein_beschluss')
        self.assertEqual(top.abstimmungsmodus, 'kein_beschluss')

    def test_qualifizierte_mehrheit_mit_schwelle(self):
        top = self._top('Sanierung', abstimmungsmodus='qualifizierte_mehrheit',
                        mehrheit_schwelle=Decimal('66.67'))
        self.assertEqual(top.mehrheit_schwelle, Decimal('66.67'))


class TopAendernTest(TestCase):
    def setUp(self):
        self.user = f.user()
        self.ev = ev_service.erstelle_ev(objekt=f.objekt(), erstellt_von=self.user)
        self.top = tagesordnung_service.top_anlegen(
            ev=self.ev, titel='Alter Titel', erstellt_von=self.user,
            beschlussvorlage='Alter Wortlaut.',
        )

    def test_titel_wird_geaendert_und_protokolliert(self):
        tagesordnung_service.top_aktualisieren(
            self.top, self.user, titel='Neuer Titel',
        )
        self.top.refresh_from_db()
        self.assertEqual(self.top.titel, 'Neuer Titel')
        ereignis = self.ev.ereignisse.get(typ='top_geaendert')
        self.assertIn('Alter Titel', ereignis.text)
        self.assertIn('Neuer Titel', ereignis.text)

    def test_unveraenderte_werte_erzeugen_kein_ereignis(self):
        tagesordnung_service.top_aktualisieren(
            self.top, self.user, titel='Alter Titel',
        )
        self.assertFalse(self.ev.ereignisse.filter(typ='top_geaendert').exists())

    def test_unbekanntes_feld_wird_abgelehnt(self):
        with self.assertRaises(ValidationError) as ctx:
            tagesordnung_service.top_aktualisieren(
                self.top, self.user, abstimmung_ja=Decimal('5'),
            )
        self.assertIn('abstimmung_ja', str(ctx.exception))

    def test_ungueltige_kombination_wird_abgelehnt(self):
        with self.assertRaises(ValidationError):
            tagesordnung_service.top_aktualisieren(
                self.top, self.user, abstimmungsmodus='qualifizierte_mehrheit',
            )
        self.top.refresh_from_db()
        self.assertEqual(self.top.abstimmungsmodus, 'einfache_mehrheit')


class SperreNachVersandTest(TestCase):
    def setUp(self):
        self.user = f.user()
        self.ev = ev_service.erstelle_ev(objekt=f.objekt(), erstellt_von=self.user)
        self.top = tagesordnung_service.top_anlegen(
            ev=self.ev, titel='TOP 1', erstellt_von=self.user,
            beschlussvorlage='Wortlaut.',
        )
        ev_service.wechsle_status(self.ev, 'in_bearbeitung', self.user)
        ev_service.wechsle_status(self.ev, 'einladungen_versendet', self.user)
        self.top.refresh_from_db()

    def test_anlegen_nach_versand_wird_abgelehnt(self):
        with self.assertRaises(ValidationError) as ctx:
            tagesordnung_service.top_anlegen(
                ev=self.ev, titel='Nachträglich', erstellt_von=self.user,
                beschlussvorlage='Text.',
            )
        self.assertIn('§ 23 Abs. 2 WEG', str(ctx.exception))
        self.assertEqual(self.ev.tagesordnung.count(), 1)

    def test_loeschen_nach_versand_wird_abgelehnt(self):
        with self.assertRaises(ValidationError):
            tagesordnung_service.top_loeschen(self.top, self.user)
        self.assertEqual(self.ev.tagesordnung.count(), 1)

    def test_beschlussvorlage_nach_versand_gesperrt(self):
        with self.assertRaises(ValidationError) as ctx:
            tagesordnung_service.top_aktualisieren(
                self.top, self.user, beschlussvorlage='Anderer Wortlaut.',
            )
        self.assertIn('beschlussvorlage', str(ctx.exception))

    def test_erlaeuterung_nach_versand_erlaubt(self):
        tagesordnung_service.top_aktualisieren(
            self.top, self.user, erlaeuterung='Zusatzinfo zur Sitzung',
        )
        self.top.refresh_from_db()
        self.assertEqual(self.top.erlaeuterung, 'Zusatzinfo zur Sitzung')


class TopLoeschenTest(TestCase):
    def setUp(self):
        self.user = f.user()
        self.ev = ev_service.erstelle_ev(objekt=f.objekt(), erstellt_von=self.user)
        self.tops = [
            tagesordnung_service.top_anlegen(
                ev=self.ev, titel=f'TOP {i}', erstellt_von=self.user,
                beschlussvorlage='Wortlaut.',
            )
            for i in range(1, 5)
        ]

    def test_luecke_wird_geschlossen(self):
        tagesordnung_service.top_loeschen(self.tops[1], self.user)
        nummern = list(
            self.ev.tagesordnung.order_by('nummer').values_list('nummer', flat=True)
        )
        self.assertEqual(nummern, [1, 2, 3])
        titel = list(
            self.ev.tagesordnung.order_by('nummer').values_list('titel', flat=True)
        )
        self.assertEqual(titel, ['TOP 1', 'TOP 3', 'TOP 4'])

    def test_loeschen_erzeugt_ereignis(self):
        tagesordnung_service.top_loeschen(self.tops[0], self.user)
        ereignis = self.ev.ereignisse.get(typ='top_geloescht')
        self.assertIn('TOP 1', ereignis.text)

    def test_neu_nummerieren_ist_idempotent(self):
        anzahl = tagesordnung_service.neu_nummerieren(self.ev)
        self.assertEqual(anzahl, 4)
        nummern = list(
            self.ev.tagesordnung.order_by('nummer').values_list('nummer', flat=True)
        )
        self.assertEqual(nummern, [1, 2, 3, 4])


class UnterpunkteTest(TestCase):
    """TOP-Hierarchie: Unterpunkte (3.1, 3.2) und Gliederungspunkte."""

    def setUp(self):
        self.user = f.user()
        self.ev = ev_service.erstelle_ev(objekt=f.objekt(), erstellt_von=self.user)

    def _top(self, titel, **kwargs):
        return tagesordnung_service.top_anlegen(
            ev=self.ev, titel=titel, erstellt_von=self.user,
            beschlussvorlage=kwargs.pop('beschlussvorlage', 'Es wird beschlossen.'),
            **kwargs,
        )

    def test_unterpunkt_bekommt_eigene_nummer_und_anzeige(self):
        self._top('TOP 1')
        drei = self._top('Sanierungen')
        u1 = self._top('Dach', eltern=drei)
        u2 = self._top('Fassade', eltern=drei)
        self.assertEqual((u1.nummer, u1.nummer_anzeige), (1, '2.1'))
        self.assertEqual((u2.nummer, u2.nummer_anzeige), (2, '2.2'))

    def test_eltern_wird_zum_gliederungspunkt(self):
        drei = self._top('Sanierungen')
        self.assertEqual(drei.abstimmungsmodus, 'einfache_mehrheit')
        self._top('Dach', eltern=drei)
        drei.refresh_from_db()
        self.assertEqual(drei.abstimmungsmodus, 'kein_beschluss')
        self.assertTrue(drei.hat_unterpunkte)

    def test_gliederungspunkt_kann_nicht_abstimmen(self):
        drei = self._top('Sanierungen')
        self._top('Dach', eltern=drei)
        drei.refresh_from_db()
        with self.assertRaises(ValidationError):
            tagesordnung_service.top_aktualisieren(
                drei, self.user, abstimmungsmodus='einfache_mehrheit',
            )

    def test_nur_eine_ebene(self):
        drei = self._top('Sanierungen')
        unter = self._top('Dach', eltern=drei)
        with self.assertRaises(ValidationError):
            self._top('Dachziegel', eltern=unter)

    def test_eltern_mit_ergebnis_kann_keine_unterpunkte_bekommen(self):
        drei = self._top('Sanierungen')
        drei.abstimmungsergebnis = 'angenommen'
        drei.save(update_fields=['abstimmungsergebnis'])
        with self.assertRaises(ValidationError):
            self._top('Dach', eltern=drei)

    def test_neu_nummerieren_je_ebene(self):
        eins = self._top('TOP 1')
        drei = self._top('Sanierungen')
        self._top('Dach', eltern=drei)
        u2 = self._top('Fassade', eltern=drei)
        self._top('Keller', eltern=drei)
        # Mittleren Unterpunkt löschen → Unterpunkt-Ebene schließt die Lücke,
        # Haupt-Ebene bleibt unberührt.
        tagesordnung_service.top_loeschen(u2, self.user)
        unter = list(drei.unterpunkte.order_by('nummer').values_list('nummer', 'titel'))
        self.assertEqual(unter, [(1, 'Dach'), (2, 'Keller')])
        haupt = list(self.ev.tagesordnung.filter(eltern__isnull=True)
                     .order_by('nummer').values_list('nummer', flat=True))
        self.assertEqual(haupt, [1, 2])
        self.assertEqual(eins.titel, 'TOP 1')

    def test_geordnete_tagesordnung_ist_baum(self):
        self._top('TOP 1')
        drei = self._top('Sanierungen')
        self._top('Dach', eltern=drei)
        self._top('Fassade', eltern=drei)
        self._top('TOP 3')
        reihenfolge = [
            t.nummer_anzeige
            for t in tagesordnung_service.geordnete_tagesordnung(self.ev)
        ]
        self.assertEqual(reihenfolge, ['1', '2', '2.1', '2.2', '3'])

    def test_loeschen_gliederungspunkt_entfernt_unterpunkte(self):
        drei = self._top('Sanierungen')
        self._top('Dach', eltern=drei)
        self._top('Fassade', eltern=drei)
        tagesordnung_service.top_loeschen(drei, self.user)
        self.assertEqual(self.ev.tagesordnung.count(), 0)

    def test_vollstaendigkeit_prueft_unterpunkt_ebene(self):
        drei = self._top('Sanierungen')
        self._top('Dach', eltern=drei)
        u2 = self._top('Fassade', eltern=drei)
        # Lücke in der Unterpunkt-Ebene erzwingen.
        u2.nummer = 4
        u2.save(update_fields=['nummer'])
        probleme = tagesordnung_service.pruefe_vollstaendigkeit(self.ev)
        self.assertTrue(any('Unterpunkt-Nummerierung' in p for p in probleme))


class VollstaendigkeitTest(TestCase):
    def setUp(self):
        self.user = f.user()
        self.ev = ev_service.erstelle_ev(objekt=f.objekt(), erstellt_von=self.user)

    def test_leere_tagesordnung(self):
        probleme = tagesordnung_service.pruefe_vollstaendigkeit(self.ev)
        self.assertEqual(len(probleme), 1)
        self.assertIn('keinen Punkt', probleme[0])

    def test_vollstaendige_tagesordnung(self):
        tagesordnung_service.top_anlegen(
            ev=self.ev, titel='TOP 1', erstellt_von=self.user,
            beschlussvorlage='Wortlaut.',
        )
        tagesordnung_service.top_anlegen(
            ev=self.ev, titel='TOP 2', erstellt_von=self.user,
            beschlussvorlage='', abstimmungsmodus='kein_beschluss',
        )
        self.assertEqual(tagesordnung_service.pruefe_vollstaendigkeit(self.ev), [])

    def test_luecke_in_der_nummerierung_wird_erkannt(self):
        top = tagesordnung_service.top_anlegen(
            ev=self.ev, titel='TOP 1', erstellt_von=self.user,
            beschlussvorlage='Wortlaut.',
        )
        # Direkte Manipulation, um den Prüfpfad zu treffen (über den Service
        # kann diese Lücke nicht entstehen).
        top.nummer = 3
        top.save(update_fields=['nummer'])
        probleme = tagesordnung_service.pruefe_vollstaendigkeit(self.ev)
        self.assertTrue(any('lückenlos' in p for p in probleme))
