"""
Tests zur Datenmigration 0028_reparatur_leistungstext_hash.

Die Migration zieht gespeicherte ``leistungstext_hash``-Werte auf die
aktuelle Formel nach, nachdem ``normalisiere_leistungstext`` um den
Monatsnamen-Filter erweitert wurde. Getestet wird gegen die echten Modelle —
die Migrationsfunktionen nehmen das Modell als Parameter, damit sie sowohl
mit dem historischen als auch mit dem aktuellen Modell laufen.
"""
import hashlib
import importlib
import re
from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.rechnungen.models import Rechnung, RechnungsMatchRegel
from apps.rechnungen.recognition import DE_STOPWORDS, leistungstext_hash

from .test_recognition import make_kreditor, make_konto, make_objekt, make_user

migration = importlib.import_module(
    'apps.rechnungen.migrations.0028_reparatur_leistungstext_hash'
)


def hash_alte_formel(text: str) -> str:
    """Reproduziert die Hash-Formel VOR dem Monatsnamen-Fix, um den
    Ausgangszustand echter Bestandsdaten herzustellen."""
    t = text.lower()
    t = re.sub(r'\d{1,2}[./]\d{1,2}[./]\d{2,4}', '', t)
    t = re.sub(r'\b(q[1-4]|kw\s?\d{1,2})\b', '', t)
    t = re.sub(r'(rg|re|rechnung|beleg)[-.\s]?\d+', '', t)
    t = re.sub(r'\b\d{4,}\b', '', t)
    t = re.sub(r'[^a-z0-9äöüß ]+', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    t = ' '.join(w for w in t.split() if w not in DE_STOPWORDS)
    return hashlib.sha256(t.encode('utf-8')).hexdigest()


class RegelHashReparaturTest(TestCase):

    def setUp(self):
        self.user     = make_user('migration')
        self.objekt   = make_objekt()
        self.kreditor = make_kreditor(name='Demme Immobilien Verwaltung GmbH')
        self.konto_wohnung    = make_konto(
            self.objekt, kontonummer='55100', kontoname='Verwaltergebühr Wohnung')
        self.konto_stellplatz = make_konto(
            self.objekt, kontonummer='55110', kontoname='Verwaltergebühr Stellplätze')

    def _regel(self, konto, sample, hash_wert=None, trefferzahl=1, status='aktiv',
               letzte_anwendung=None):
        return RechnungsMatchRegel.objects.create(
            kreditor=self.kreditor, objekt=self.objekt, aufwandskonto=konto,
            leistungstext_hash=(
                hash_wert if hash_wert is not None else leistungstext_hash(sample)
            ),
            leistungstext_sample=sample, status=status, trefferzahl=trefferzahl,
            letzte_anwendung=letzte_anwendung,
            erstellt_durch=self.user, erstellt_aus='pruefung',
        )

    def _reparieren(self):
        migration._regeln_reparieren(RechnungsMatchRegel)

    # -- Kern: gebrochener Hash ------------------------------------------

    def test_gebrochener_hash_wird_nachgezogen(self):
        sample = 'WEG Verwaltung für 11 Wohneinheiten für den Monat August 2026.'
        regel = self._regel(self.konto_wohnung, sample, hash_wert=hash_alte_formel(sample))
        self.assertNotEqual(regel.leistungstext_hash, leistungstext_hash(sample))

        self._reparieren()

        regel.refresh_from_db()
        self.assertEqual(regel.leistungstext_hash, leistungstext_hash(sample))
        self.assertEqual(regel.status, 'aktiv')

    def test_intakter_hash_bleibt_unveraendert(self):
        sample = 'WEG Verwaltung Stellplätze im Zeitraum 01.09. bis 30.09.'
        regel = self._regel(self.konto_stellplatz, sample)
        vorher = regel.leistungstext_hash

        self._reparieren()

        regel.refresh_from_db()
        self.assertEqual(regel.leistungstext_hash, vorher)

    def test_regel_ohne_sample_bleibt_unangetastet(self):
        regel = self._regel(self.konto_wohnung, '', hash_wert='a' * 64)

        self._reparieren()

        regel.refresh_from_db()
        self.assertEqual(regel.leistungstext_hash, 'a' * 64)
        self.assertEqual(regel.status, 'aktiv')

    # -- Zusammenfall mehrerer Regeln ------------------------------------

    def test_monatsregeln_werden_zusammengefuehrt(self):
        """Genau der Effekt, den der Monatsnamen-Fix bezweckt: aus den
        monatlich entstandenen Einzelregeln wird eine."""
        juli   = 'Hausmeistertätigkeit für Juli gemäß Leistungsverzeichnis'
        august = 'Hausmeistertätigkeit für August gemäß Leistungsverzeichnis'
        self.assertEqual(leistungstext_hash(juli), leistungstext_hash(august))

        schwach = self._regel(self.konto_wohnung, juli,
                              hash_wert=hash_alte_formel(juli), trefferzahl=2)
        stark   = self._regel(self.konto_wohnung, august,
                              hash_wert=hash_alte_formel(august), trefferzahl=5)

        self._reparieren()

        schwach.refresh_from_db()
        stark.refresh_from_db()
        self.assertEqual(stark.status, 'aktiv')
        self.assertEqual(schwach.status, 'veraltet')
        self.assertEqual(stark.leistungstext_hash, leistungstext_hash(august))
        self.assertEqual(stark.trefferzahl, 7)

    def test_zusammenfall_mit_verschiedenen_konten_veraltet_alle(self):
        """Nicht mehr entscheidbar — dann lieber Prüffall als ein womöglich
        falsch gesetztes Konto."""
        juli   = 'Gartenpflege Monat Juli'
        august = 'Gartenpflege Monat August'
        a = self._regel(self.konto_wohnung, juli, hash_wert=hash_alte_formel(juli))
        b = self._regel(self.konto_stellplatz, august, hash_wert=hash_alte_formel(august))

        self._reparieren()

        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(a.status, 'veraltet')
        self.assertEqual(b.status, 'veraltet')

    def test_zielhash_der_einen_ist_altwert_der_anderen(self):
        """Ringtausch: ohne die Platzhalter-Phase würde die Unique-Constraint
        unique_aktive_matchregel schon vorübergehend verletzt."""
        text_a = 'Verwaltung für den Monat August'
        text_b = 'Sonderleistung Treppenhaus'

        a = self._regel(self.konto_wohnung, text_a, hash_wert=hash_alte_formel(text_a))
        b = self._regel(self.konto_stellplatz, text_b,
                        hash_wert=leistungstext_hash(text_a))

        self._reparieren()   # darf nicht mit IntegrityError brechen

        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(a.leistungstext_hash, leistungstext_hash(text_a))
        self.assertEqual(b.leistungstext_hash, leistungstext_hash(text_b))
        self.assertEqual(a.status, 'aktiv')
        self.assertEqual(b.status, 'aktiv')

    def test_veraltete_regeln_werden_nicht_angefasst(self):
        sample = 'Verwaltung für den Monat Mai'
        regel = self._regel(self.konto_wohnung, sample,
                            hash_wert=hash_alte_formel(sample), status='veraltet')

        self._reparieren()

        regel.refresh_from_db()
        self.assertEqual(regel.leistungstext_hash, hash_alte_formel(sample))

    def test_laeuft_ohne_regeln_durch(self):
        self._reparieren()
        self.assertEqual(RechnungsMatchRegel.objects.count(), 0)


class RechnungHashReparaturTest(TestCase):

    def setUp(self):
        self.objekt   = make_objekt()
        self.kreditor = make_kreditor()

    def _rechnung(self, leistungstext, hash_wert, beschreibung=''):
        return Rechnung.objects.create(
            objekt=self.objekt, kreditor=self.kreditor, betrag_brutto=Decimal('100.00'),
            status='in_buchhaltung', leistungstext=leistungstext,
            leistungsbeschreibung=beschreibung, leistungstext_hash=hash_wert,
        )

    def test_gebrochener_hash_wird_nachgezogen(self):
        text = 'WEG Verwaltung für den Monat August 2026'
        r = self._rechnung(text, hash_alte_formel(text))

        migration._rechnungen_reparieren(Rechnung)

        r.refresh_from_db()
        self.assertEqual(r.leistungstext_hash, leistungstext_hash(text))

    def test_leerer_hash_bleibt_leer(self):
        r = self._rechnung('Verwaltung für den Monat August', '')

        migration._rechnungen_reparieren(Rechnung)

        r.refresh_from_db()
        self.assertEqual(r.leistungstext_hash, '')

    def test_faellt_auf_leistungsbeschreibung_zurueck(self):
        text = 'Hausmeister für den Monat Juli'
        r = self._rechnung('', hash_alte_formel(text), beschreibung=text)

        migration._rechnungen_reparieren(Rechnung)

        r.refresh_from_db()
        self.assertEqual(r.leistungstext_hash, leistungstext_hash(text))

    def test_rechnung_ohne_leistungstext_bleibt_unangetastet(self):
        r = self._rechnung('', 'b' * 64)

        migration._rechnungen_reparieren(Rechnung)

        r.refresh_from_db()
        self.assertEqual(r.leistungstext_hash, 'b' * 64)


class ErkennungNachReparaturTest(TestCase):
    """Der Zweck der Migration, am realen Fall nachgebaut (Demme an der WEG
    Bischof-Kaller-Straße): für dasselbe Kreditor/Objekt-Paar sind zwei Konten
    gelernt — Wohnung und Stellplätze. ``match_konto_eindeutig`` greift daher
    bewusst nicht, allein der Leistungstext-Hash kann entscheiden. Ist dessen
    Wert gebrochen, bleibt die Rechnung Prüffall."""

    def setUp(self):
        self.user     = make_user('e2e')
        self.objekt   = make_objekt()
        self.kreditor = make_kreditor(name='Demme Immobilien Verwaltung GmbH')
        self.konto    = make_konto(
            self.objekt, kontonummer='55100', kontoname='Verwaltergebühr Wohnung')
        self.konto_stellplatz = make_konto(
            self.objekt, kontonummer='55110', kontoname='Verwaltergebühr Stellplätze')
        self.sample   = 'WEG Verwaltung für 11 Wohneinheiten für den Monat August 2026.'

        # Gebrochen: Hash nach alter Formel, weil der Text "Monat August" nennt.
        self.regel = RechnungsMatchRegel.objects.create(
            kreditor=self.kreditor, objekt=self.objekt, aufwandskonto=self.konto,
            leistungstext_hash=hash_alte_formel(self.sample),
            leistungstext_sample=self.sample, status='aktiv',
            erstellt_durch=self.user, erstellt_aus='pruefung',
        )
        # Intakt: der Stellplatz-Text nennt nur Datumsangaben, keinen Monatsnamen.
        stellplatz_text = 'WEG Verwaltung Stellplätze im Zeitraum 01.08. bis 31.08.'
        RechnungsMatchRegel.objects.create(
            kreditor=self.kreditor, objekt=self.objekt,
            aufwandskonto=self.konto_stellplatz,
            leistungstext_hash=leistungstext_hash(stellplatz_text),
            leistungstext_sample=stellplatz_text, status='aktiv',
            erstellt_durch=self.user, erstellt_aus='pruefung',
        )

    def _rechnung(self):
        return Rechnung.objects.create(
            objekt=self.objekt, kreditor=self.kreditor,
            lieferant_name=self.kreditor.name,
            lieferant_normalisiert=self.kreditor.name_normalisiert,
            betrag_brutto=Decimal('418.88'), status='in_buchhaltung',
            rechnungsdatum=date(date.today().year, 8, 1),
            leistungstext=self.sample,
        )

    def test_vor_reparatur_bleibt_pruefall(self):
        from apps.rechnungen.recognition import fuehre_erkennung_aus
        rechnung = fuehre_erkennung_aus(self._rechnung())
        self.assertIsNone(rechnung.aufwandskonto)
        self.assertEqual(rechnung.erkennungs_stufe, '2')

    def test_nach_reparatur_wird_kontiert(self):
        from apps.rechnungen.recognition import fuehre_erkennung_aus
        migration._regeln_reparieren(RechnungsMatchRegel)

        rechnung = fuehre_erkennung_aus(self._rechnung())
        self.assertEqual(rechnung.aufwandskonto.kontonummer, '55100')
        self.assertEqual(rechnung.erkennungs_stufe, '1')
        self.assertEqual(rechnung.match_regel_id, self.regel.id)
