"""
Tests für die Beleg-Dokument-Kopplung in der Rechnungs-Intake-Pipeline
(verarbeite_datei) — v1_1 Phase A.

Deckt ab:
  - Erfolgsfall: Rechnung bekommt automatisch ein Beleg-Dokument + Log
  - Negativfall: Kopplung schlägt fehl (kein Systembenutzer) → Rechnung wird
    trotzdem angelegt, Fehler wird geloggt, Pipeline bricht nicht ab.
"""
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.buchhaltung.models import ImportOrdnerEinstellung
from apps.dokumente.models import Dokument
from apps.rechnungen.models import Rechnung, Verarbeitungslog
from apps.rechnungen.services.verarbeitung import verarbeite_datei

User = get_user_model()

# Parsed-Dict ohne Rechnungsnummer -> Pflichtfeld fehlt -> status 'prueffall'.
# Damit bleibt der Test unabhängig von der (KI-gestützten) Erkennungspipeline,
# die nur bei status == 'importiert' anschließend läuft.
_PARSED_UNVOLLSTAENDIG = {
    'text': 'Testrechnung',
    'invoice_number': None,
    'invoice_number_normalized': '',
    'invoice_date': None,
    'due_date': None,
    'gross_amount': None,
    'net_amount': None,
    'vat_rate': None,
    'currency': 'EUR',
    'supplier': None,
    'supplier_normalized': '',
    'iban': None,
    'description': None,
    'property_address': None,
    'customer_number': '',
    'is_credit_note': False,
}


class BelegKopplungPipelineTest(TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="immocore_test_pipeline_")
        self.addCleanup(shutil.rmtree, self._tmp, ignore_errors=True)

        self.archiv_root = Path(self._tmp) / "archiv"
        self.archiv_root.mkdir(parents=True, exist_ok=True)
        ImportOrdnerEinstellung.objects.create(
            bereich="rechnungen", archiv_ordner=str(self.archiv_root),
        )

        eingang = Path(self._tmp) / "eingang"
        eingang.mkdir(parents=True, exist_ok=True)
        self.quelldatei = eingang / "test-rechnung.pdf"
        self.quelldatei.write_bytes(b"%PDF-1.4 Testinhalt Rechnung")

    def _verarbeite(self):
        with patch(
            "apps.rechnungen.services.verarbeitung.extract_invoice_data",
            return_value=dict(_PARSED_UNVOLLSTAENDIG),
        ):
            return verarbeite_datei(str(self.quelldatei), self.archiv_root)

    def test_beleg_dokument_wird_automatisch_angelegt(self):
        # 'immocore-autopilot' existiert immer (Datenmigration
        # buchhaltung/0025_autopilot_user.py) — kein eigenes Anlegen nötig.
        self._verarbeite()

        rechnung = Rechnung.objects.get()
        self.assertIsNotNone(rechnung.beleg_dokument_id)
        dok = rechnung.beleg_dokument
        self.assertIsInstance(dok, Dokument)
        self.assertEqual(dok.ablage_wurzel, "rechnungen")
        self.assertEqual(dok.dokument_typ, "beleg")
        self.assertEqual(dok.kategorie, "Beleg")
        self.assertEqual(dok.hochgeladen_von.username, "immocore-autopilot")

        log = Verarbeitungslog.objects.filter(
            rechnung=rechnung, aktion="Beleg-Dokument angelegt",
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.details, dok.beleg_nummer)

    def test_fehlgeschlagene_kopplung_blockiert_rechnungseingang_nicht(self):
        # Kein Systembenutzer vorhanden -> _system_user() liefert None ->
        # Kopplung schlägt kontrolliert fehl, Rechnung wird aber trotzdem angelegt.
        User.objects.filter(username="immocore-autopilot").delete()
        self.assertFalse(User.objects.filter(is_superuser=True).exists())

        ergebnis = self._verarbeite()

        rechnung = Rechnung.objects.get()
        self.assertEqual(ergebnis["rechnung_id"], str(rechnung.id))
        self.assertIsNone(rechnung.beleg_dokument_id)

        log = Verarbeitungslog.objects.filter(
            rechnung=rechnung, aktion="Beleg-Kopplung fehlgeschlagen",
        ).first()
        self.assertIsNotNone(log)
        self.assertIn("Systembenutzer", log.details)

        # Der eigentliche Rechnungseingang-Log-Eintrag muss trotzdem existieren.
        self.assertTrue(
            Verarbeitungslog.objects.filter(rechnung=rechnung, aktion="Datei verarbeitet").exists()
        )
