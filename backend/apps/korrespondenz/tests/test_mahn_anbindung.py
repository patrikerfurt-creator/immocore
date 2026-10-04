"""Phase 6a: Anbindung Mahnwesen inkl. Kontoauszug-Anlage (Spec 9.1, Test 17).

Der Mahnlauf selbst (``fuehre_mahnlauf_aus``) läuft gegen echte Testdaten; die
Anbindung hängt am Schalter ``KORRESPONDENZ_MAHNWESEN_AKTIV``. PDFs entstehen echt
(WeasyPrint) in einem temporären ``MEDIA_ROOT``; der Versand-Task wird abgefangen.
"""
from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

import pymupdf
from django.test import override_settings
from django.utils import timezone

from apps.buchhaltung.models import (
    Basiszinssatz, Buchung, FrontofficeAufgabe, HausgeldSollstellung, MahnEinstellung, Mahnlauf,
    Mahnung, OffenerPosten,
)
from apps.buchhaltung.services import mahnwesen
from apps.konten.models import Konto
from apps.korrespondenz.models import Schreiben, Vorlage
from apps.korrespondenz.services import (
    kontext_service, kontoauszug_anlage_service, mahn_anbindung_service, schreiben_service,
)
from apps.korrespondenz.services.mahn_anbindung_service import MahnBlockade
from apps.objekte.models import Bankkonto, Wirtschaftsjahr

from .basis_versand import VersandTestBasis

MAHN_TEXT = [
    {'typ': 'text', 'inhalt': 'trotz unserer Zahlungserinnerung konnten wir keinen Zahlungseingang feststellen:'},
    {'typ': 'tabelle', 'quelle': 'mahnung.offene_posten'},
    {'typ': 'text', 'inhalt': (
        'Hauptforderung {{ mahnung.summe_hauptforderung | euro }} - Mahngebühr {{ mahnung.gebuehr | euro }} - '
        'Verzugszinsen {{ mahnung.zinsen | euro }} - Gesamt {{ mahnung.gesamtbetrag | euro }}, '
        'zahlbar bis {{ mahnung.frist | datum }}.'
    )},
]
VERSAND_TASK = 'apps.korrespondenz.tasks.versende_schreiben.delay'


class MahnTestBasis(VersandTestBasis):
    """WEG mit Zahlungsverkehrskonto, ein Personenkonto mit überfälligen Posten und Kontoauszug-Daten."""

    def setUp(self):
        Basiszinssatz.objects.get_or_create(gueltig_ab=date(2020, 1, 1), defaults={'satz': Decimal('3.62')})
        self.heute = timezone.localdate()
        self.konto = self.s.konto
        self.objekt = self.s.objekt
        # Pflicht-Konfiguration je Objekt (ohne sie wird nicht gemahnt).
        MahnEinstellung.objects.create(
            objekt=self.objekt, mahngebuehr=Decimal('5.00'), anzahl_mahnstufen=2, zinsen_erheben=True,
        )

    # --- Daten ---
    def op(self, tage_ueberfaellig, betrag='350.00', text='Hausgeld', mahnstufe=0):
        faellig = self.heute - timedelta(days=tage_ueberfaellig)
        buchung = Buchung.objects.create(
            objekt=self.objekt, betrag=Decimal(betrag), buchungsdatum=faellig,
            buchungstext=f'{text} {faellig:%m/%Y}',
        )
        return OffenerPosten.objects.create(
            buchung=buchung, personenkonto=self.konto, betrag_ursprung=Decimal(betrag),
            betrag_offen=Decimal(betrag), faellig_ab=faellig, mahnstufe=mahnstufe,
        )

    def sollstellungen(self, anzahl, ab=date(2025, 1, 1)):
        """``anzahl`` monatliche Hausgeld-Sollstellungen ab ``ab``; die erste Hälfte ist bezahlt."""
        wj, _ = Wirtschaftsjahr.objects.get_or_create(objekt=self.objekt, jahr=ab.year, defaults={'beginn_monat': 1})
        bank, _ = Konto.objects.get_or_create(
            wirtschaftsjahr=wj, kontonummer='18000', defaults={'kontoname': 'Bank', 'kontoart': 'standard'},
        )
        for i in range(anzahl):
            monat = date(ab.year + (ab.month - 1 + i) // 12, (ab.month - 1 + i) % 12 + 1, 1)
            HausgeldSollstellung.objects.create(
                objekt=self.objekt, eigentumsverhaeltnis=self.s.ev, sollstellungs_typ='hausgeld',
                erstellt_von=self.s.ersteller, periode=monat, faellig_am=monat,
                opos_nr=f'T-{self.konto.kontonummer}-{i:03d}', soll_betrag=Decimal('300.00'),
                status_cached='offen',
            )
            if i < anzahl // 2:
                Buchung.objects.create(
                    objekt=self.objekt, betrag=Decimal('300.00'), buchungsdatum=monat + timedelta(days=3),
                    buchungstext=f'Zahlung Hausgeld {monat:%m/%Y}', personenkonto=self.konto,
                    soll_konto=bank, wirtschaftsjahr=wj,
                )

    def mahn_vorlagen(self, *stufen):
        for stufe in stufen:
            version = self.vorlage(
                code=f'mahnung_stufe_{stufe}', anlass=f'mahnung_stufe_{stufe}', inhalt=MAHN_TEXT,
                kanal_standard='brief',
            )
            version.parameter = {'frist_tage': 10}
            version.save(update_fields=['parameter'])

    def neuer_lauf(self):
        return Mahnlauf.objects.create(objekt=self.objekt, ausgefuehrt_von=self.s.ersteller)

    def fuehre_aus(self, lauf=None):
        lauf = lauf or self.neuer_lauf()
        with mock.patch(VERSAND_TASK) as versand, self.captureOnCommitCallbacks(execute=True):
            ergebnis = mahnwesen.fuehre_mahnlauf_aus(str(lauf.pk), self.user)
        return lauf, ergebnis, versand


class StufenMappingTest(MahnTestBasis):

    def test_staffel_der_realen_mahnstufen(self):
        real = {s['stufe']: s['bezeichnung'] for s in mahnwesen.MAHNSTUFEN}
        self.assertEqual(real, {1: '1. Mahnung', 2: '2. Mahnung'})

    def test_relatives_mapping_bei_zwei_stufen(self):
        """Letzte Stufe -> mahnung_stufe_3, frühere -> mahnung_stufe_2 (mahnung_stufe_1 ungenutzt)."""
        self.assertEqual(mahn_anbindung_service.vorlage_code(1, 2), 'mahnung_stufe_2')
        self.assertEqual(mahn_anbindung_service.vorlage_code(2, 2), 'mahnung_stufe_3')

    def test_relatives_mapping_bei_einer_stufe(self):
        self.assertEqual(mahn_anbindung_service.vorlage_code(1, 1), 'mahnung_stufe_3')

    def test_unbekannte_stufe_blockiert(self):
        for stufe, anzahl in ((0, 2), (3, 2), (2, 1), (None, 2)):
            with self.subTest(stufe=stufe, anzahl=anzahl), self.assertRaises(MahnBlockade):
                mahn_anbindung_service.vorlage_code(stufe, anzahl)

    def test_blockade_ist_value_error_fuer_die_bestehende_ansicht(self):
        self.assertTrue(issubclass(MahnBlockade, ValueError))

    def test_lauf_erzeugt_nie_stufe_0(self):
        """Begründung des Mappings: die erste Mahnung des Laufs ist bereits Stufe 1."""
        self.op(60)
        vorschau = mahnwesen.simuliere_mahnlauf(str(self.objekt.pk), self.heute)
        self.assertEqual([m['mahnstufe'] for m in vorschau['mahnungen']], [1])


class SchalterAusTest(MahnTestBasis):
    """Schalter aus (Default): der Mahnlauf verhält sich exakt wie bisher."""

    def test_default_ist_aus(self):
        from django.conf import settings
        self.assertFalse(settings.KORRESPONDENZ_MAHNWESEN_AKTIV)

    def test_kein_schreiben_kein_pdf_altes_verhalten(self):
        self.op(60)
        lauf, ergebnis, versand = self.fuehre_aus()
        self.assertEqual(ergebnis, {'ok': 1})
        lauf.refresh_from_db()
        self.assertEqual(lauf.status, 'ausgefuehrt')
        mahnung = Mahnung.objects.get()
        self.assertEqual(mahnung.mahnstufe, 1)
        self.assertEqual(mahnung.pdf_pfad, '')
        self.assertEqual(Schreiben.objects.count(), 0)
        self.assertEqual(OffenerPosten.objects.get().mahnstufe, 1)
        versand.assert_not_called()

    def test_fehlende_vorlage_blockiert_bei_schalter_aus_nicht(self):
        self.op(60)
        self.assertFalse(Vorlage.objects.exists())
        _, ergebnis, _ = self.fuehre_aus()
        self.assertEqual(ergebnis, {'ok': 1})


@override_settings(KORRESPONDENZ_MAHNWESEN_AKTIV=True)
class MahnlaufFreigabeTest(MahnTestBasis):
    """Test 17: Mahnlauf-Ausführung erzeugt je Mahnung ein freigegebenes Schreiben."""

    def test_freigegebenes_schreiben_mit_pdf_und_kontoauszug(self):
        self.mahn_vorlagen(2)
        self.sollstellungen(30)          # 2025/01 .. 2027/06 -> Auszug reicht über eine Seite
        self.op(60)
        lauf, ergebnis, versand = self.fuehre_aus()

        self.assertEqual(ergebnis, {'ok': 1})
        mahnung = Mahnung.objects.get()
        schreiben = Schreiben.objects.get()
        self.assertEqual(schreiben.mahnung, mahnung)
        self.assertEqual(schreiben.status, 'freigegeben')
        self.assertIsNotNone(schreiben.dokument_id)
        self.assertEqual(schreiben.vorlage_version.vorlage.code, 'mahnung_stufe_2')
        self.assertEqual(schreiben.unterzeichner, self.objekt.betreuer)
        self.assertEqual(schreiben.freigegeben_von, self.user)
        mahnung.refresh_from_db()
        self.assertEqual(mahnung.pdf_pfad, schreiben.dokument.datei.name)
        self.assertTrue(mahnung.pdf_pfad.endswith(f'{schreiben.nummer}.pdf'))
        versand.assert_called_once_with(str(schreiben.pk), self.user.pk)

        with schreiben.dokument.datei.open('rb') as f, pymupdf.open(stream=f.read(), filetype='pdf') as pdf:
            self.assertGreaterEqual(pdf.page_count, 2)
            erste = pdf[0].get_text()
            letzte = pdf[pdf.page_count - 1].get_text()
        self.assertIn('Anlagen', erste)
        self.assertIn('Kontoauszug', erste)
        self.assertIn('Kontoauszug', letzte)
        self.assertIn('Saldo zum', letzte)

    def test_kontoauszug_ist_mehrseitig(self):
        self.sollstellungen(20, ab=date(2025, 1, 1))
        daten = kontoauszug_anlage_service.baue_daten(self.konto, date(2026, 12, 31))
        daten['positionen'] = daten['positionen'] * 6
        pdf = kontoauszug_anlage_service.rendere_pdf(daten)
        with pymupdf.open(stream=pdf, filetype='pdf') as doc:
            self.assertGreaterEqual(doc.page_count, 3)
            self.assertIn('Kontoauszug', doc[0].get_text())
            self.assertIn('Seite 2 von', doc[1].get_text())

    def test_mahnung_entspricht_mahnlauf_summen(self):
        self.mahn_vorlagen(2)
        self.op(60, '350.00')
        self.fuehre_aus()
        mahnung = Mahnung.objects.get()
        html = Schreiben.objects.get().html_gerendert
        self.assertIn('350,00', html)
        self.assertEqual(mahnung.offene_posten_summe, Decimal('350.00'))
        self.assertEqual(mahnung.gebuehr, Decimal('5.00'))

    def test_letzte_stufe_nutzt_stufe_3_vorlage_und_forderungsfall(self):
        self.mahn_vorlagen(3)
        self.op(90, mahnstufe=1)
        self.fuehre_aus()
        schreiben = Schreiben.objects.get()
        self.assertEqual(Mahnung.objects.get().mahnstufe, 2)
        self.assertEqual(schreiben.vorlage_version.vorlage.code, 'mahnung_stufe_3')
        self.assertEqual(schreiben.status, 'freigegeben')

    def test_objektspezifische_vorlage_hat_vorrang(self):
        self.mahn_vorlagen(2)
        spezifisch = self.vorlage(
            code='mahnung_stufe_2', anlass='mahnung_stufe_2', inhalt=MAHN_TEXT, objekt=self.objekt,
        )
        spezifisch.parameter = {'frist_tage': 5}
        spezifisch.save(update_fields=['parameter'])
        self.op(60)
        self.fuehre_aus()
        self.assertEqual(Schreiben.objects.get().vorlage_version, spezifisch)


@override_settings(KORRESPONDENZ_MAHNWESEN_AKTIV=True)
class OffenePostenKonsistenzTest(MahnTestBasis):

    def test_tabelle_zeigt_posten_zum_mahnlauf_zeitpunkt(self):
        """Die letzte Stufe setzt die Posten auf ``forderungsfall``; das Schreiben zeigt sie trotzdem."""
        self.mahn_vorlagen(3)
        posten = self.op(90, '410.00', text='Sonderumlage', mahnstufe=1)
        self.fuehre_aus()
        posten.refresh_from_db()
        self.assertEqual(posten.status, 'forderungsfall')
        schreiben = Schreiben.objects.get()

        live = kontext_service._offene_posten_zeilen(self.konto, self.heute)
        self.assertEqual(live, [], 'Live-Abfrage sieht die Posten nicht mehr')
        self.assertIn('Sonderumlage', schreiben.html_gerendert)
        self.assertIn('410,00', schreiben.html_gerendert)

        # Auch ein späteres Neu-Rendern (Kontext aus dem Schreiben) bleibt beim Mahnlauf-Stand.
        kontext = schreiben_service._baue_kontext(schreiben, None, self.heute)
        zeilen = kontext['mahnung']['offene_posten']
        self.assertEqual([z['betrag_offen'] for z in zeilen], [Decimal('410.00')])
        self.assertEqual(zeilen[0]['faellig_ab'], posten.faellig_ab)

    def test_spaetere_zahlung_aendert_das_schreiben_nicht(self):
        self.mahn_vorlagen(2)
        posten = self.op(60, '350.00')
        self.fuehre_aus()
        OffenerPosten.objects.filter(pk=posten.pk).update(betrag_offen=Decimal('0.00'), status='verrechnet')
        schreiben = Schreiben.objects.get()
        kontext = schreiben_service._baue_kontext(schreiben, None, self.heute)
        self.assertEqual([z['betrag_offen'] for z in kontext['mahnung']['offene_posten']], [Decimal('350.00')])

    def test_ohne_snapshot_gilt_der_live_stand(self):
        """Bestehendes Verhalten (z. B. Vorschau) bleibt: ohne Snapshot wird live gelesen."""
        self.op(60, '350.00')
        lauf = self.neuer_lauf()
        mahnung = Mahnung.objects.create(
            lauf=lauf, personenkonto=self.konto, mahnstufe=1,
            offene_posten_summe=Decimal('350.00'), gebuehr=Decimal('5.00'), zinsen=Decimal('0.00'),
        )
        kontext = kontext_service.baue_kontext(
            'mahnung_stufe_2', person=self.s.person, mahnung=mahnung, heute=self.heute,
            parameter={'frist_tage': 10},
        )
        self.assertEqual(len(kontext['mahnung']['offene_posten']), 1)


@override_settings(KORRESPONDENZ_MAHNWESEN_AKTIV=True)
class BlockadeTest(MahnTestBasis):

    def assertLaufUnveraendert(self, lauf, posten):
        lauf.refresh_from_db()
        posten.refresh_from_db()
        self.assertEqual(lauf.status, 'simulation')
        self.assertEqual(Mahnung.objects.count(), 0)
        self.assertEqual(Schreiben.objects.count(), 0)
        self.assertEqual(posten.mahnstufe, 0)
        self.assertEqual(posten.status, 'offen')

    def test_fehlende_vorlage_blockiert(self):
        posten = self.op(60)
        lauf = self.neuer_lauf()
        with self.assertRaises(MahnBlockade) as ctx:
            self.fuehre_aus(lauf)
        self.assertIn('mahnung_stufe_2', str(ctx.exception))
        self.assertLaufUnveraendert(lauf, posten)

    def test_inaktive_vorlage_zaehlt_als_fehlend(self):
        self.mahn_vorlagen(2)
        Vorlage.objects.filter(code='mahnung_stufe_2').update(aktiv=False)
        posten = self.op(60)
        lauf = self.neuer_lauf()
        with self.assertRaises(MahnBlockade):
            self.fuehre_aus(lauf)
        self.assertLaufUnveraendert(lauf, posten)

    def test_nur_vorkommende_stufen_werden_geprueft(self):
        """Vorlage 3 fehlt, im Lauf kommt aber nur Stufe 1 (-> Vorlage 2) vor: kein Problem."""
        self.mahn_vorlagen(2)
        self.op(60)
        _, ergebnis, _ = self.fuehre_aus()
        self.assertEqual(ergebnis, {'ok': 1})

    def test_schreiben_nicht_erzeugbar_blockiert_und_rollt_alles_zurueck(self):
        """WEG ohne eindeutiges Zahlungsverkehr-Konto: kein halber Lauf, auch keine Buchungen."""
        self.mahn_vorlagen(2)
        Bankkonto.objects.filter(objekt=self.objekt).update(zahlungsverkehr=False)
        posten = self.op(60)
        buchungen_vorher = Buchung.objects.count()
        lauf = self.neuer_lauf()
        with self.assertRaises(MahnBlockade) as ctx:
            self.fuehre_aus(lauf)
        self.assertIn('nicht erzeugbar', str(ctx.exception))
        self.assertIn(self.konto.kontonummer, str(ctx.exception))
        self.assertLaufUnveraendert(lauf, posten)
        self.assertEqual(Buchung.objects.count(), buchungen_vorher)


@override_settings(KORRESPONDENZ_MAHNWESEN_AKTIV=True)
class NachCommitFehlerTest(MahnTestBasis):

    def test_fehler_beim_pdf_rollt_den_lauf_nicht_zurueck(self):
        self.mahn_vorlagen(2)
        self.op(60)
        with mock.patch.object(
            kontoauszug_anlage_service, 'rendere_pdf', side_effect=RuntimeError('WeasyPrint kaputt'),
        ):
            lauf, ergebnis, versand = self.fuehre_aus()
        lauf.refresh_from_db()
        self.assertEqual(lauf.status, 'ausgefuehrt')
        self.assertEqual(ergebnis, {'ok': 1})
        schreiben = Schreiben.objects.get()
        self.assertEqual(schreiben.status, 'zur_pruefung')
        self.assertIsNone(schreiben.dokument_id)
        self.assertEqual(Mahnung.objects.get().pdf_pfad, '')
        aufgabe = FrontofficeAufgabe.objects.get()
        self.assertEqual(aufgabe.aufgabe_typ, 'schreiben_nicht_erzeugbar')
        self.assertIn(schreiben.nummer, aufgabe.beschreibung)
        versand.assert_not_called()

    def test_broker_ausfall_laesst_das_schreiben_freigegeben(self):
        self.mahn_vorlagen(2)
        self.op(60)
        lauf = self.neuer_lauf()
        with mock.patch(VERSAND_TASK, side_effect=ConnectionError('Redis weg')), \
                self.captureOnCommitCallbacks(execute=True):
            mahnwesen.fuehre_mahnlauf_aus(str(lauf.pk), self.user)
        schreiben = Schreiben.objects.get()
        self.assertEqual(schreiben.status, 'freigegeben')
        self.assertNotEqual(Mahnung.objects.get().pdf_pfad, '')
        self.assertFalse(FrontofficeAufgabe.objects.exists())


class KontoauszugAnlageTest(MahnTestBasis):

    def test_daten_saldo_und_vortrag(self):
        self.sollstellungen(6, ab=date(2024, 10, 1))    # Okt 2024 - Mär 2025, alles im Zeitraum
        daten = kontoauszug_anlage_service.baue_daten(self.konto, date(2025, 6, 30))
        # 6 Sollstellungen (Okt 24 - Mär 25) je 300, davon 3 bezahlt -> Saldo -900
        self.assertEqual(daten['saldo'], '-900.00')
        self.assertEqual(daten['von'], '2024-01-01')
        self.assertEqual(daten['stichtag'], '2025-06-30')
        self.assertEqual(daten['kopf']['personenkonto'], self.konto.kontonummer)
        self.assertEqual(daten['positionen'][-1]['saldo'], '-900.00')

    def test_vortrag_verdichtet_fruehere_jahre(self):
        self.sollstellungen(4, ab=date(2022, 1, 1))     # alles weit vor dem Zeitraum
        daten = kontoauszug_anlage_service.baue_daten(self.konto, date(2025, 6, 30))
        self.assertEqual(daten['positionen'], [])
        self.assertEqual(daten['vortrag'], daten['saldo'])
        self.assertEqual(daten['saldo'], '-600.00')

    def test_nach_dem_stichtag_bleibt_aussen_vor(self):
        self.sollstellungen(6, ab=date(2025, 1, 1))
        daten = kontoauszug_anlage_service.baue_daten(self.konto, date(2025, 2, 28))
        self.assertEqual([p['datum'] for p in daten['positionen'] if p['soll']], ['2025-01-01', '2025-02-01'])

    def test_stornierte_sollstellung_ohne_saldowirkung(self):
        self.sollstellungen(2, ab=date(2025, 1, 1))
        HausgeldSollstellung.objects.filter(periode=date(2025, 2, 1)).update(storniert_am=timezone.now())
        daten = kontoauszug_anlage_service.baue_daten(self.konto, date(2025, 3, 1))
        storno = [p for p in daten['positionen'] if p['storniert']]
        self.assertEqual(len(storno), 1)
        self.assertEqual(daten['saldo'], '0.00')     # Jan 300 Soll, 300 bezahlt; Feb storniert

    def test_daten_sind_json_sicher(self):
        import json
        self.sollstellungen(3)
        json.dumps(kontoauszug_anlage_service.baue_daten(self.konto, date(2026, 1, 1)))
