"""
Tests für HandwerkerauftragNummerZaehler.naechste_nummer() — 1:1 nach dem
Muster von apps.vorgaenge.tests.test_vorgang_nummer (Phase A, Vorgabe 5).

Deckt ab:
  - Format HWA-{JJ}-{LFD5}
  - fortlaufend pro Kalenderjahr, getrennte Zähler je Jahr
  - Race-Condition: parallele Vergabe (Threads) erzeugt keine Duplikate
    (SELECT FOR UPDATE-Schutz statt reinem COUNT()+1)
"""
import threading

from django.db import connection
from django.test import TestCase, TransactionTestCase

from apps.handwerker.models import HandwerkerauftragNummerZaehler


class HandwerkerauftragNummerFormatTest(TestCase):
    def test_format_und_fortlaufend(self):
        n1 = HandwerkerauftragNummerZaehler.naechste_nummer(2026)
        n2 = HandwerkerauftragNummerZaehler.naechste_nummer(2026)
        n3 = HandwerkerauftragNummerZaehler.naechste_nummer(2026)
        self.assertEqual(n1, "HWA-26-00001")
        self.assertEqual(n2, "HWA-26-00002")
        self.assertEqual(n3, "HWA-26-00003")

    def test_getrennte_zaehler_je_jahr(self):
        HandwerkerauftragNummerZaehler.naechste_nummer(2025)
        n_2025 = HandwerkerauftragNummerZaehler.naechste_nummer(2025)
        n_2026 = HandwerkerauftragNummerZaehler.naechste_nummer(2026)
        self.assertEqual(n_2025, "HWA-25-00002")
        self.assertEqual(n_2026, "HWA-26-00001")

    def test_default_jahr_ist_laufendes_jahr(self):
        from django.utils import timezone
        nummer = HandwerkerauftragNummerZaehler.naechste_nummer()
        jj = f"{timezone.now().year % 100:02d}"
        self.assertTrue(nummer.startswith(f"HWA-{jj}-"))


class HandwerkerauftragNummerRaceConditionTest(TransactionTestCase):
    """Echte Nebenläufigkeit erfordert TransactionTestCase (separate
    Connections je Thread, echte Commits)."""

    def test_parallele_vergabe_erzeugt_keine_duplikate(self):
        ergebnisse = []
        fehler = []
        lock = threading.Lock()

        def worker():
            try:
                nummer = HandwerkerauftragNummerZaehler.naechste_nummer(2026)
                with lock:
                    ergebnisse.append(nummer)
            except Exception as exc:  # pragma: no cover - Diagnose bei Fehlschlag
                with lock:
                    fehler.append(exc)
            finally:
                connection.close()

        anzahl_threads = 20
        threads = [threading.Thread(target=worker) for _ in range(anzahl_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(fehler, [])
        self.assertEqual(len(ergebnisse), anzahl_threads)
        self.assertEqual(len(set(ergebnisse)), anzahl_threads, "Doppelte Handwerkerauftragsnummer vergeben!")
