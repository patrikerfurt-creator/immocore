"""
Tests für AuftragsbestaetigungsToken (Phase A, Orchestrator-Vorgabe 9).

Deckt ab:
  - accept_token/reject_token werden automatisch gesetzt und unterscheiden sich
  - ist_gueltig(): True bei frischem Token, False nach verbraucht_am, False
    nach Ablauf von gueltig_bis
  - Gültigkeitsberechnung (berechne_gueltig_bis): hoch=3 / normal=7 /
    niedrig=14 Bankarbeitstage — Startdatum fest (nicht today()), damit
    Wochenenden und ein bekannter deutscher Feiertag (Karfreitag/Ostermontag
    2026, Bundesland HE) nachweislich übersprungen werden.
"""
from datetime import date, datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.handwerker.models import AuftragsbestaetigungsToken, Handwerkerauftrag, berechne_gueltig_bis
from apps.objekte.models import Objekt
from apps.rechnungen.models import Kreditor

User = get_user_model()


def _objekt(nr="H100", bundesland="HE"):
    return Objekt.objects.create(
        bezeichnung="Test-WEG Token", objektnummer=nr, objekt_typ="weg",
        ort="Teststadt", verwaltung_seit=date(2020, 1, 1), bundesland=bundesland,
    )


def _kreditor():
    return Kreditor.objects.create(
        name="Meister Sanitär GmbH", ist_handwerker=True, email="meister@example.de",
    )


def _auftrag(objekt, prioritaet="normal"):
    return Handwerkerauftrag.objects.create(
        objekt=objekt, kreditor=_kreditor(), titel="Wasserhahn undicht",
        prioritaet=prioritaet,
    )


class AuftragsbestaetigungsTokenTest(TestCase):
    def setUp(self):
        self.objekt = _objekt()
        self.auftrag = _auftrag(self.objekt)

    def test_tokens_werden_automatisch_gesetzt_und_unterscheiden_sich(self):
        token = AuftragsbestaetigungsToken.objects.create(auftrag=self.auftrag)
        self.assertTrue(token.accept_token)
        self.assertTrue(token.reject_token)
        self.assertNotEqual(token.accept_token, token.reject_token)

    def test_ist_gueltig_true_bei_frischem_token(self):
        token = AuftragsbestaetigungsToken.objects.create(auftrag=self.auftrag)
        self.assertTrue(token.ist_gueltig())

    def test_ist_gueltig_false_nach_verbrauch(self):
        token = AuftragsbestaetigungsToken.objects.create(auftrag=self.auftrag)
        token.verbraucht_am = timezone.now()
        token.save(update_fields=["verbraucht_am"])
        self.assertFalse(token.ist_gueltig())

    def test_ist_gueltig_false_nach_ablauf(self):
        vergangen = timezone.now() - timedelta(days=1)
        token = AuftragsbestaetigungsToken.objects.create(
            auftrag=self.auftrag, gueltig_bis=vergangen,
        )
        self.assertFalse(token.ist_gueltig())


class BerechneGueltigBisTest(TestCase):
    """Startdatum fest: Montag, 2026-03-30. HE-Feiertage in diesem Fenster:
    Karfreitag (2026-04-03, Fr) und Ostermontag (2026-04-06, Mo) — verifiziert
    per sepa_fristen_service.bd_addieren in der Live-Umgebung."""

    START = date(2026, 3, 30)

    def _erwartetes_ende(self, tag: date) -> datetime:
        return timezone.make_aware(datetime.combine(tag, time.max))

    def setUp(self):
        self.objekt = _objekt(bundesland="HE")

    def test_hoch_3_bankarbeitstage(self):
        auftrag = _auftrag(self.objekt, prioritaet="hoch")
        ergebnis = berechne_gueltig_bis(auftrag, start=self.START)
        self.assertEqual(ergebnis, self._erwartetes_ende(date(2026, 4, 2)))

    def test_normal_7_bankarbeitstage_ueberspringt_wochenende_und_feiertage(self):
        auftrag = _auftrag(self.objekt, prioritaet="normal")
        ergebnis = berechne_gueltig_bis(auftrag, start=self.START)
        # Ohne Feiertags-/Wochenend-Überspringen wäre dies 2026-04-06.
        self.assertEqual(ergebnis, self._erwartetes_ende(date(2026, 4, 10)))

    def test_niedrig_14_bankarbeitstage(self):
        auftrag = _auftrag(self.objekt, prioritaet="niedrig")
        ergebnis = berechne_gueltig_bis(auftrag, start=self.START)
        self.assertEqual(ergebnis, self._erwartetes_ende(date(2026, 4, 21)))

    def test_leeres_bundesland_faellt_auf_he_zurueck_statt_zu_werfen(self):
        objekt_ohne_bundesland = _objekt(nr="H101", bundesland="")
        auftrag = _auftrag(objekt_ohne_bundesland, prioritaet="hoch")
        ergebnis = berechne_gueltig_bis(auftrag, start=self.START)
        self.assertEqual(ergebnis, self._erwartetes_ende(date(2026, 4, 2)))

    def test_save_setzt_gueltig_bis_automatisch_wenn_leer(self):
        auftrag = _auftrag(self.objekt, prioritaet="hoch")
        token = AuftragsbestaetigungsToken(auftrag=auftrag)
        token.save()
        self.assertIsNotNone(token.gueltig_bis)
