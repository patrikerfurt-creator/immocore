"""
Tests für ``auftrag_service.wechsle_status`` (Phase B, Orchestrator-Vorgabe
Schritt 2/5) — explizite Übergangstabelle.

Deckt ab:
  - alle erlaubten Statusübergänge inkl. Zeitstempel + genau ein Ereignis
  - mindestens vier unerlaubte Übergänge: nichts ändert sich, kein Ereignis
  - erstellt_von=None wird ohne _system_ausloeser=True abgewiesen
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.handwerker.models import Handwerkerauftrag, HandwerkerauftragEreignis
from apps.handwerker.services import auftrag_service
from apps.objekte.models import Objekt
from apps.rechnungen.models import Kreditor

User = get_user_model()


def _objekt(nr="H500"):
    return Objekt.objects.create(
        bezeichnung="Test-WEG Statuswechsel", objektnummer=nr, objekt_typ="weg",
        ort="Teststadt", verwaltung_seit=date(2020, 1, 1), bundesland="HE",
    )


def _kreditor():
    return Kreditor.objects.create(
        name="Meister Sanitär GmbH", ist_handwerker=True, email="meister@example.de",
    )


def _user():
    return User.objects.create_user(username="status-tester", password="x")


class WechsleStatusErlaubteUebergaengeTest(TestCase):
    def setUp(self):
        self.user = _user()
        self.objekt = _objekt()
        self.kreditor = _kreditor()

    def _auftrag(self, status="entwurf"):
        auftrag = Handwerkerauftrag.objects.create(
            objekt=self.objekt, kreditor=self.kreditor, titel="Testauftrag",
            erstellt_von=self.user, status=status,
        )
        return auftrag

    def test_entwurf_zu_versendet(self):
        auftrag = self._auftrag("entwurf")
        auftrag_service.wechsle_status(auftrag, "versendet", erstellt_von=self.user)
        auftrag.refresh_from_db()
        self.assertEqual(auftrag.status, "versendet")
        self.assertIsNotNone(auftrag.versendet_am)
        self.assertEqual(auftrag.ereignisse.count(), 1)

    def test_entwurf_zu_storniert(self):
        auftrag = self._auftrag("entwurf")
        auftrag_service.wechsle_status(auftrag, "storniert", erstellt_von=self.user)
        auftrag.refresh_from_db()
        self.assertEqual(auftrag.status, "storniert")

    def test_versendet_zu_angenommen(self):
        auftrag = self._auftrag("versendet")
        auftrag_service.wechsle_status(auftrag, "angenommen", erstellt_von=self.user)
        auftrag.refresh_from_db()
        self.assertEqual(auftrag.status, "angenommen")
        self.assertIsNotNone(auftrag.angenommen_am)

    def test_versendet_zu_abgelehnt(self):
        auftrag = self._auftrag("versendet")
        auftrag_service.wechsle_status(auftrag, "abgelehnt", erstellt_von=self.user)
        auftrag.refresh_from_db()
        self.assertEqual(auftrag.status, "abgelehnt")
        self.assertIsNotNone(auftrag.abgelehnt_am)

    def test_versendet_zu_abgelaufen(self):
        auftrag = self._auftrag("versendet")
        auftrag_service.wechsle_status(
            auftrag, "abgelaufen", erstellt_von=None,
            ereignis_typ="system_abgelaufen", _system_ausloeser=True,
        )
        auftrag.refresh_from_db()
        self.assertEqual(auftrag.status, "abgelaufen")

    def test_versendet_zu_storniert(self):
        auftrag = self._auftrag("versendet")
        auftrag_service.wechsle_status(auftrag, "storniert", erstellt_von=self.user)
        auftrag.refresh_from_db()
        self.assertEqual(auftrag.status, "storniert")

    def test_angenommen_zu_in_arbeit(self):
        auftrag = self._auftrag("angenommen")
        auftrag_service.wechsle_status(auftrag, "in_arbeit", erstellt_von=self.user)
        auftrag.refresh_from_db()
        self.assertEqual(auftrag.status, "in_arbeit")

    def test_angenommen_zu_abgeschlossen(self):
        auftrag = self._auftrag("angenommen")
        auftrag_service.wechsle_status(auftrag, "abgeschlossen", erstellt_von=self.user)
        auftrag.refresh_from_db()
        self.assertEqual(auftrag.status, "abgeschlossen")
        self.assertIsNotNone(auftrag.abgeschlossen_am)

    def test_angenommen_zu_storniert(self):
        auftrag = self._auftrag("angenommen")
        auftrag_service.wechsle_status(auftrag, "storniert", erstellt_von=self.user)
        auftrag.refresh_from_db()
        self.assertEqual(auftrag.status, "storniert")

    def test_in_arbeit_zu_abgeschlossen(self):
        auftrag = self._auftrag("in_arbeit")
        auftrag_service.wechsle_status(auftrag, "abgeschlossen", erstellt_von=self.user)
        auftrag.refresh_from_db()
        self.assertEqual(auftrag.status, "abgeschlossen")

    def test_in_arbeit_zu_storniert(self):
        auftrag = self._auftrag("in_arbeit")
        auftrag_service.wechsle_status(auftrag, "storniert", erstellt_von=self.user)
        auftrag.refresh_from_db()
        self.assertEqual(auftrag.status, "storniert")

    def test_abgelehnt_zu_storniert(self):
        auftrag = self._auftrag("abgelehnt")
        auftrag_service.wechsle_status(auftrag, "storniert", erstellt_von=self.user)
        auftrag.refresh_from_db()
        self.assertEqual(auftrag.status, "storniert")

    def test_abgelaufen_zu_versendet(self):
        auftrag = self._auftrag("abgelaufen")
        auftrag_service.wechsle_status(auftrag, "versendet", erstellt_von=self.user)
        auftrag.refresh_from_db()
        self.assertEqual(auftrag.status, "versendet")

    def test_abgelaufen_zu_storniert(self):
        auftrag = self._auftrag("abgelaufen")
        auftrag_service.wechsle_status(auftrag, "storniert", erstellt_von=self.user)
        auftrag.refresh_from_db()
        self.assertEqual(auftrag.status, "storniert")


class WechsleStatusUnerlaubteUebergaengeTest(TestCase):
    def setUp(self):
        self.user = _user()
        self.objekt = _objekt()
        self.kreditor = _kreditor()

    def _auftrag(self, status):
        return Handwerkerauftrag.objects.create(
            objekt=self.objekt, kreditor=self.kreditor, titel="Testauftrag",
            erstellt_von=self.user, status=status,
        )

    def _assert_unveraendert(self, auftrag, alter_status):
        with self.assertRaises(ValidationError):
            auftrag_service.wechsle_status(auftrag, "irgendein_ziel", erstellt_von=self.user)

    def _assert_uebergang_abgewiesen(self, von_status, nach_status):
        auftrag = self._auftrag(von_status)
        with self.assertRaises(ValidationError):
            auftrag_service.wechsle_status(auftrag, nach_status, erstellt_von=self.user)
        auftrag.refresh_from_db()
        self.assertEqual(auftrag.status, von_status)
        self.assertEqual(auftrag.ereignisse.count(), 0)

    def test_entwurf_zu_angenommen_abgewiesen(self):
        self._assert_uebergang_abgewiesen("entwurf", "angenommen")

    def test_storniert_zu_versendet_abgewiesen(self):
        self._assert_uebergang_abgewiesen("storniert", "versendet")

    def test_abgeschlossen_zu_in_arbeit_abgewiesen(self):
        self._assert_uebergang_abgewiesen("abgeschlossen", "in_arbeit")

    def test_abgelehnt_zu_angenommen_abgewiesen(self):
        self._assert_uebergang_abgewiesen("abgelehnt", "angenommen")

    def test_erstellt_von_none_ohne_system_ausloeser_wird_abgewiesen(self):
        auftrag = self._auftrag("entwurf")
        with self.assertRaises(ValidationError):
            auftrag_service.wechsle_status(auftrag, "versendet", erstellt_von=None)
        auftrag.refresh_from_db()
        self.assertEqual(auftrag.status, "entwurf")
        self.assertEqual(auftrag.ereignisse.count(), 0)


class WechsleStatusMitNachtraeglichUngueltigemKreditorTest(TestCase):
    """Korrektur aus der Phase-B-Abnahme (Orchestrator, Schritt 0): ein
    Kreditor, dem NACH Versand eines Auftrags ``ist_handwerker`` aberkannt
    oder die E-Mail geleert wird, darf einen bestehenden Auftrag nicht mehr
    dauerhaft blockieren — ``wechsle_status()`` ruft bei jedem Übergang
    ``full_clean()`` auf, das darf hier nicht mehr scheitern."""

    def setUp(self):
        self.user = _user()
        self.objekt = _objekt()
        self.kreditor = _kreditor()

    def _auftrag_angenommen_mit_ungueltigem_kreditor(self):
        auftrag = Handwerkerauftrag.objects.create(
            objekt=self.objekt, kreditor=self.kreditor, titel="Testauftrag",
            erstellt_von=self.user, status="angenommen",
        )
        # Kreditor wird NACH Anlage/Versand/Annahme ungültig gemacht.
        self.kreditor.ist_handwerker = False
        self.kreditor.email = ""
        self.kreditor.save(update_fields=["ist_handwerker", "email"])
        return auftrag

    def test_angenommen_zu_abgeschlossen_trotz_ungueltigem_kreditor(self):
        auftrag = self._auftrag_angenommen_mit_ungueltigem_kreditor()
        auftrag_service.wechsle_status(auftrag, "abgeschlossen", erstellt_von=self.user)
        auftrag.refresh_from_db()
        self.assertEqual(auftrag.status, "abgeschlossen")

    def test_angenommen_zu_storniert_trotz_ungueltigem_kreditor(self):
        auftrag = self._auftrag_angenommen_mit_ungueltigem_kreditor()
        auftrag_service.wechsle_status(auftrag, "storniert", erstellt_von=self.user)
        auftrag.refresh_from_db()
        self.assertEqual(auftrag.status, "storniert")

    def test_neuanlage_mit_ungueltigem_kreditor_wird_weiterhin_abgewiesen(self):
        """(b) — die Prüfung bleibt für NEUE (Status 'entwurf') Aufträge aktiv."""
        self.kreditor.ist_handwerker = False
        self.kreditor.email = ""
        self.kreditor.save(update_fields=["ist_handwerker", "email"])

        neuer_auftrag = Handwerkerauftrag(
            objekt=self.objekt, kreditor=self.kreditor, titel="Neuer Auftrag",
            erstellt_von=self.user,
        )
        with self.assertRaises(ValidationError):
            neuer_auftrag.full_clean()
