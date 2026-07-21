"""
Tests: jahresabrechnung/einzelabrechnung_service (HGA-Spec v1.0 Kap. 4, Phase C)

Formel-Korrektheit (Kap. 4.1), Hausgeld-Soll aus Nebenbuch (Kap. 4.2,
inkl. Plan-Änderung im Jahr = unterschiedliche Monatsbeträge),
Eigentümerwechsel (Kap. 4.4: kein Split, Fußnote), VS-Fehler-Logging,
Invariante abrechnungsergebnis == kostenanteil - hausgeld_soll.
"""
from datetime import date
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.buchhaltung.models import (
    Buchung,
    EinzelAbrechnung,
    HausgeldSollstellung,
    Jahresabrechnung,
)
from apps.buchhaltung.services.jahresabrechnung.einzelabrechnung_service import (
    berechne_alle_einzelabrechnungen,
    berechne_einzelabrechnung,
    berechne_hausgeld_soll,
    hat_eigentuemerwechsel_im_wj,
)
from apps.konten.models import Konto
from apps.objekte.models import (
    Bankkonto,
    Einheit,
    Objekt,
    Verteilerschluessel,
    VerteilerschluesselWert,
    Wirtschaftsjahr,
)
from apps.personen.models import EigentumsVerhaeltnis, Person
from apps.prozesse.models import Prozess

User = get_user_model()


def _user(username='ea-user'):
    u, _ = User.objects.get_or_create(username=username, defaults={'is_staff': True})
    return u


def _create_objekt(kuerzel='EA1'):
    return Objekt.objects.create(
        objekt_typ='WEG',
        bezeichnung=f'EA-Test-Objekt {kuerzel}',
        kurzbezeichnung=kuerzel,
        strasse='Teststraße 1',
        plz='60311',
        ort='Frankfurt',
        verwaltung_seit=date(2020, 1, 1),
        glaeubiger_id='DE98ZZZ09999999999',
    )


class EinzelAbrechnungServiceTestBase(TestCase):
    def setUp(self):
        self.user = _user()
        self.objekt = _create_objekt()
        self.wj = Wirtschaftsjahr.objects.create(
            objekt=self.objekt, jahr=2025, beginn_monat=1)
        self.e1 = Einheit.objects.create(
            objekt=self.objekt, einheit_nr='WE01', einheit_typ='Wohnung', lage='EG')
        self.e2 = Einheit.objects.create(
            objekt=self.objekt, einheit_nr='WE02', einheit_typ='Wohnung', lage='OG')
        self.p1 = Person.objects.create(
            person_typ='100', anrede='Herr', vorname='Anton', nachname='Alt')
        self.p2 = Person.objects.create(
            person_typ='100', anrede='Frau', vorname='Berta', nachname='Besitzer')
        self.ev1 = EigentumsVerhaeltnis.objects.create(
            einheit=self.e1, person=self.p1, beginn=date(2020, 1, 1))
        self.ev2 = EigentumsVerhaeltnis.objects.create(
            einheit=self.e2, person=self.p2, beginn=date(2020, 1, 1))
        # MEA 300/700
        vs = Verteilerschluessel.objects.create(
            objekt=self.objekt, schluessel='010', bezeichnung='MEA', vs_typ='mea')
        VerteilerschluesselWert.objects.create(
            schluessel=vs, einheit=self.e1, wirtschaftsjahr=0, wert=Decimal('300'))
        VerteilerschluesselWert.objects.create(
            schluessel=vs, einheit=self.e2, wirtschaftsjahr=0, wert=Decimal('700'))
        self.prozess = Prozess.objects.create(
            prozess_typ='jahresabrechnung', objekt=self.objekt, gestartet_von=self.user)
        self.ja = Jahresabrechnung.objects.create(
            objekt=self.objekt, wirtschaftsjahr=self.wj,
            prozess=self.prozess, erstellt_von=self.user)

    def _create_kosten(self, betrag='1000.00', kontonummer='50100', vs='010'):
        konto = Konto.objects.create(
            wirtschaftsjahr=self.wj, kontonummer=kontonummer,
            kontoname=f'Aufwand {kontonummer}', verteilerschluessel=vs)
        Buchung.objects.create(
            objekt=self.objekt, betrag=Decimal(betrag),
            buchungsdatum=date(2025, 5, 10), status='festgeschrieben',
            soll_konto=konto,
        )
        return konto

    def _create_soll(self, ev, betrag, periode, typ='hausgeld', storniert=False):
        from django.utils import timezone
        return HausgeldSollstellung.objects.create(
            objekt=self.objekt, eigentumsverhaeltnis=ev,
            sollstellungs_typ=typ, periode=periode, faellig_am=periode,
            opos_nr=f'OP-{uuid4().hex[:10]}', soll_betrag=Decimal(betrag),
            erstellt_von=self.user,
            storniert_am=timezone.now() if storniert else None,
        )


class HausgeldSollTest(EinzelAbrechnungServiceTestBase):
    def test_summe_ueber_wj(self):
        self._create_soll(self.ev1, '100.00', date(2025, 1, 1))
        self._create_soll(self.ev1, '100.00', date(2025, 2, 1))
        self.assertEqual(
            berechne_hausgeld_soll(self.ev1, self.wj), Decimal('200.00'))

    def test_plan_aenderung_im_jahr_anteilige_monate(self):
        """Kap. 4.1: 6 Monate alter Plan + 6 Monate neuer Plan."""
        for monat in range(1, 7):
            self._create_soll(self.ev1, '100.00', date(2025, monat, 1))
        for monat in range(7, 13):
            self._create_soll(self.ev1, '120.00', date(2025, monat, 1))
        self.assertEqual(
            berechne_hausgeld_soll(self.ev1, self.wj), Decimal('1320.00'))

    def test_stornierte_und_fremde_typen_zaehlen_nicht(self):
        self._create_soll(self.ev1, '100.00', date(2025, 1, 1))
        self._create_soll(self.ev1, '999.00', date(2025, 2, 1), storniert=True)
        self._create_soll(self.ev1, '500.00', date(2025, 3, 1), typ='sonderumlage')
        self._create_soll(self.ev1, '100.00', date(2024, 12, 1))  # Vorjahr
        self.assertEqual(
            berechne_hausgeld_soll(self.ev1, self.wj), Decimal('100.00'))


class FormelTest(EinzelAbrechnungServiceTestBase):
    def test_abrechnungsergebnis_formel(self):
        """Kap. 4.1: Ergebnis = Σ(Kosten × Anteil) − Hausgeld-Soll."""
        self._create_kosten('1000.00')
        self._create_soll(self.ev1, '100.00', date(2025, 1, 1))
        self._create_soll(self.ev1, '100.00', date(2025, 2, 1))
        ea = berechne_einzelabrechnung(self.ja, self.e1)
        self.assertEqual(ea.kostenanteil_gesamt, Decimal('300.00'))   # 1000 × 0,3
        self.assertEqual(ea.hausgeld_soll_gesamt, Decimal('200.00'))
        self.assertEqual(ea.abrechnungsergebnis, Decimal('100.00'))   # Nachzahlung
        self.assertEqual(ea.eigentuemer, self.p1)
        self.assertEqual(ea.eigentumsverhaeltnis, self.ev1)

    def test_invariante(self):
        self._create_kosten('847.33')
        self._create_soll(self.ev1, '412.50', date(2025, 1, 1))
        ea = berechne_einzelabrechnung(self.ja, self.e1)
        self.assertEqual(
            ea.abrechnungsergebnis,
            ea.kostenanteil_gesamt - ea.hausgeld_soll_gesamt,
        )

    def test_guthaben_bei_hohem_soll(self):
        self._create_kosten('1000.00')
        self._create_soll(self.ev1, '500.00', date(2025, 1, 1))
        ea = berechne_einzelabrechnung(self.ja, self.e1)
        self.assertEqual(ea.abrechnungsergebnis, Decimal('-200.00'))  # Guthaben

    def test_positionen_json_befuellt(self):
        self._create_kosten('1000.00')
        ea = berechne_einzelabrechnung(self.ja, self.e1)
        self.assertEqual(len(ea.positionen), 1)
        pos = ea.positionen[0]
        self.assertEqual(pos['kontonummer'], '50100')
        self.assertEqual(pos['vs_code'], '010')
        self.assertEqual(pos['gesamtkosten'], '1000.00')
        self.assertEqual(pos['betrag'], '300.00')
        self.assertFalse(ea.positionen_hat_fehler())

    def test_upsert_kein_duplikat(self):
        self._create_kosten('1000.00')
        berechne_einzelabrechnung(self.ja, self.e1)
        self._create_soll(self.ev1, '100.00', date(2025, 1, 1))
        ea2 = berechne_einzelabrechnung(self.ja, self.e1)
        self.assertEqual(
            EinzelAbrechnung.objects.filter(
                jahresabrechnung=self.ja, einheit=self.e1).count(), 1)
        self.assertEqual(ea2.hausgeld_soll_gesamt, Decimal('100.00'))

    def test_nur_entwurf_berechenbar(self):
        self.ja.status = 'gesperrt'
        self.ja.save(update_fields=['status'])
        with self.assertRaises(ValidationError):
            berechne_einzelabrechnung(self.ja, self.e1)

    def test_objekt_ohne_einheiten_wirft_klaren_fehler(self):
        """Statt stillem No-Op (leere Liste) eine verständliche Meldung."""
        objekt2 = _create_objekt('EA2')
        wj2 = Wirtschaftsjahr.objects.create(objekt=objekt2, jahr=2025, beginn_monat=1)
        prozess2 = Prozess.objects.create(
            prozess_typ='jahresabrechnung', objekt=objekt2, gestartet_von=self.user)
        ja2 = Jahresabrechnung.objects.create(
            objekt=objekt2, wirtschaftsjahr=wj2, prozess=prozess2, erstellt_von=self.user)
        with self.assertRaisesMessage(ValidationError, 'keine Einheiten'):
            berechne_alle_einzelabrechnungen(ja2)

    def test_berechne_alle(self):
        self._create_kosten('1000.00')
        ergebnisse = berechne_alle_einzelabrechnungen(self.ja)
        self.assertEqual(len(ergebnisse), 2)
        self.assertEqual(
            {ea.einheit_id for ea in ergebnisse}, {self.e1.id, self.e2.id})
        # Anteile summieren sich auf die Gesamtkosten
        self.assertEqual(
            sum(ea.kostenanteil_gesamt for ea in ergebnisse), Decimal('1000.00'))


class VsFehlerTest(EinzelAbrechnungServiceTestBase):
    def test_vs_fehler_wird_geloggt_statt_abbruch(self):
        """Kap. 7: VerteilerschluesselFehler landet in positionen, kein Crash."""
        self._create_kosten('1000.00', kontonummer='50100', vs='010')
        self._create_kosten('500.00', kontonummer='50200', vs='140')  # keine Verbräuche
        ea = berechne_einzelabrechnung(self.ja, self.e1)
        fehler_pos = [p for p in ea.positionen if p.get('fehler')]
        ok_pos = [p for p in ea.positionen if not p.get('fehler')]
        self.assertEqual(len(fehler_pos), 1)
        self.assertEqual(fehler_pos[0]['kontonummer'], '50200')
        self.assertEqual(len(ok_pos), 1)
        self.assertTrue(ea.positionen_hat_fehler())
        # Kostenanteil enthält nur die berechenbaren Positionen
        self.assertEqual(ea.kostenanteil_gesamt, Decimal('300.00'))


class EigentuemerwechselTest(EinzelAbrechnungServiceTestBase):
    def setUp(self):
        super().setUp()
        # Wechsel WE01: Alt bis 30.06.2025, Käuferin ab 01.07.2025
        self.ev1.ende = date(2025, 6, 30)
        self.ev1.save(update_fields=['ende'])
        self.kaeuferin = Person.objects.create(
            person_typ='100', anrede='Frau', vorname='Clara', nachname='Kauf')
        self.ev_neu = EigentumsVerhaeltnis.objects.create(
            einheit=self.e1, person=self.kaeuferin, beginn=date(2025, 7, 1))

    def test_wechsel_erkannt(self):
        self.assertTrue(hat_eigentuemerwechsel_im_wj(self.e1, self.wj))
        self.assertFalse(hat_eigentuemerwechsel_im_wj(self.e2, self.wj))

    def test_abrechnung_auf_kaeufer_mit_fussnote(self):
        """Kap. 4.4: Kein Split — voller Jahresbetrag beim aktuellen Eigentümer."""
        self._create_kosten('1000.00')
        # Nachhol-Sollstellungen: Käuferin ist rückwirkend Schuldnerin des
        # vollen Jahres-Solls (Eigentümerwechsel-Modul, Kap. 4.4)
        for monat in range(1, 13):
            self._create_soll(self.ev_neu, '50.00', date(2025, monat, 1))
        ea = berechne_einzelabrechnung(self.ja, self.e1)
        self.assertEqual(ea.eigentuemer, self.kaeuferin)
        self.assertEqual(ea.eigentumsverhaeltnis, self.ev_neu)
        self.assertEqual(ea.hausgeld_soll_gesamt, Decimal('600.00'))
        self.assertTrue(ea.hinweis_eigentuemerwechsel)

    def test_soll_des_verkaeufers_zaehlt_nicht_beim_kaeufer(self):
        self._create_soll(self.ev1, '300.00', date(2025, 1, 1))     # Alt-EV
        self._create_soll(self.ev_neu, '50.00', date(2025, 7, 1))
        ea = berechne_einzelabrechnung(self.ja, self.e1)
        self.assertEqual(ea.hausgeld_soll_gesamt, Decimal('50.00'))

    def test_einheit_ohne_aktives_ev_wirft_fehler(self):
        self.ev_neu.delete()
        self.ev1.ende = date(2025, 6, 30)
        self.ev1.save(update_fields=['ende'])
        with self.assertRaises(ValidationError):
            berechne_einzelabrechnung(self.ja, self.e1)


class PdfServiceTest(EinzelAbrechnungServiceTestBase):
    """Smoke-Tests pdf_service (Phase C): Rendering + Dokument-Persistierung."""

    def _ea(self):
        self._create_kosten('1000.00')
        self._create_soll(self.ev1, '100.00', date(2025, 1, 1))
        return berechne_einzelabrechnung(self.ja, self.e1)

    def test_render_vorschau_liefert_pdf(self):
        from apps.buchhaltung.services.jahresabrechnung.pdf_service import (
            render_einzelabrechnung_pdf,
        )
        pdf = render_einzelabrechnung_pdf(self._ea())
        self.assertTrue(pdf.startswith(b'%PDF'))

    def test_rendere_und_speichere_erzeugt_dokument(self):
        from apps.buchhaltung.services.jahresabrechnung.pdf_service import (
            rendere_und_speichere,
        )
        ea = self._ea()
        dokument = rendere_und_speichere(ea, user=self.user)
        self.assertEqual(dokument.verknuepfung_typ, 'einzelabrechnung')
        self.assertEqual(dokument.objekt, self.objekt)
        self.assertEqual(dokument.einheit, self.e1)
        self.assertIn('WE01', dokument.dateiname)
        self.assertIn('2025', dokument.dateiname)
        with dokument.datei.open('rb') as f:
            self.assertTrue(f.read(4).startswith(b'%PDF'))


class RuecklagenJsonTest(EinzelAbrechnungServiceTestBase):
    def test_ruecklagen_json_mit_anteil(self):
        from apps.buchhaltung.models import Kontoumsatz
        bk = Bankkonto.objects.create(
            objekt=self.objekt, konto_typ='ruecklage',
            bezeichnung='Rücklage 1', reihenfolge=1)
        Kontoumsatz.objects.create(
            objekt=self.objekt, bankkonto=bk,
            sha256_hash=uuid4().hex + uuid4().hex[:32],
            betrag=Decimal('10000.00'), buchungsdatum=date(2024, 6, 1),
            status='verbucht')
        ea = berechne_einzelabrechnung(self.ja, self.e1)
        self.assertEqual(len(ea.ruecklagen), 1)
        r = ea.ruecklagen[0]
        self.assertEqual(r['endbestand'], '10000.00')
        self.assertEqual(r['anteil_eigentuemer'], '3000.00')  # × MEA 0,3
