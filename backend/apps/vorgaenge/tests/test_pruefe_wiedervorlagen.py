"""
Tests für ``apps.vorgaenge.tasks.pruefe_wiedervorlagen`` (Phase C, Spec
Vorgang & DMS Kap. 3).

Deckt ab:
  - wiedervorlage_am = gestern -> Rückführung nach in_bearbeitung,
    VorgangEreignis 'system_wiedervorlage_faellig', wiedervorlage_am genullt
  - wiedervorlage_am = heute -> ebenfalls Rückführung (Spec: "<= heute")
  - wiedervorlage_am = morgen -> bleibt unverändert, kein Ereignis
  - Vorgänge in anderen Stati mit gesetztem Datum werden nicht angefasst
  - Fehler bei einem Vorgang bricht die Verarbeitung der übrigen nicht ab
"""
from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.objekte.models import Objekt
from apps.vorgaenge.models import Vorgang, VorgangEreignis, VorgangTyp
from apps.vorgaenge.services import vorgang_service
from apps.vorgaenge.tasks import pruefe_wiedervorlagen

User = get_user_model()


def _objekt(nr):
    return Objekt.objects.create(
        bezeichnung="Test-WEG Wiedervorlage-Task", objektnummer=nr, objekt_typ="weg",
        ort="Teststadt", verwaltung_seit=date(2020, 1, 1),
    )


def _user(username):
    return User.objects.create_user(username=username, password="x")


def _typ(code="maengelmeldung"):
    return VorgangTyp.objects.get(code=code)


class PruefeWiedervorlagenTest(TestCase):
    def setUp(self):
        self.user = _user("wiedervorlage-task-tester")

    def _vorgang_in_wiedervorlage(self, nr, wiedervorlage_am):
        """Legt einen Vorgang an und versetzt ihn (über den Service) in den
        Status 'wiedervorlage' mit dem gewünschten Datum.
        """
        vorgang = vorgang_service.erstelle_vorgang(
            typ=_typ(), betreff=f"Test {nr}", erstellt_von=self.user, objekt=_objekt(nr),
        )
        vorgang_service.wechsle_status(
            vorgang, "in_bearbeitung", erstellt_von=self.user,
        )
        vorgang_service.wechsle_status(
            vorgang, "wiedervorlage", erstellt_von=self.user,
            wiedervorlage_am=wiedervorlage_am,
        )
        vorgang.refresh_from_db()
        return vorgang

    def test_wiedervorlage_am_gestern_wird_zurueckgefuehrt(self):
        gestern = date.today() - timedelta(days=1)
        vorgang = self._vorgang_in_wiedervorlage("PW001", gestern)

        pruefe_wiedervorlagen()

        vorgang.refresh_from_db()
        self.assertEqual(vorgang.status, "in_bearbeitung")
        self.assertIsNone(vorgang.wiedervorlage_am)
        ereignis = VorgangEreignis.objects.get(
            vorgang=vorgang, typ="system_wiedervorlage_faellig",
        )
        self.assertIsNone(ereignis.erstellt_von)

    def test_wiedervorlage_am_heute_wird_zurueckgefuehrt(self):
        heute = date.today()
        vorgang = self._vorgang_in_wiedervorlage("PW002", heute)

        pruefe_wiedervorlagen()

        vorgang.refresh_from_db()
        self.assertEqual(vorgang.status, "in_bearbeitung")
        self.assertIsNone(vorgang.wiedervorlage_am)
        self.assertTrue(
            VorgangEreignis.objects.filter(
                vorgang=vorgang, typ="system_wiedervorlage_faellig",
            ).exists()
        )

    def test_wiedervorlage_am_morgen_bleibt_unveraendert(self):
        morgen = date.today() + timedelta(days=1)
        vorgang = self._vorgang_in_wiedervorlage("PW003", morgen)

        pruefe_wiedervorlagen()

        vorgang.refresh_from_db()
        self.assertEqual(vorgang.status, "wiedervorlage")
        self.assertEqual(vorgang.wiedervorlage_am, morgen)
        self.assertFalse(
            VorgangEreignis.objects.filter(
                vorgang=vorgang, typ="system_wiedervorlage_faellig",
            ).exists()
        )

    def test_andere_stati_werden_nicht_angefasst(self):
        # Vorgang in 'in_bearbeitung' hat regulär gar kein wiedervorlage_am
        # gesetzt (clean()-Regel) -- der Task darf ihn trotzdem nicht anfassen,
        # selbst wenn er (rein hypothetisch, am Model vorbei) ein Datum trüge.
        vorgang = vorgang_service.erstelle_vorgang(
            typ=_typ(), betreff="Test PW004", erstellt_von=self.user, objekt=_objekt("PW004"),
        )
        vorgang_service.wechsle_status(vorgang, "in_bearbeitung", erstellt_von=self.user)
        Vorgang.objects.filter(pk=vorgang.pk).update(
            wiedervorlage_am=date.today() - timedelta(days=1)
        )

        pruefe_wiedervorlagen()

        vorgang.refresh_from_db()
        self.assertEqual(vorgang.status, "in_bearbeitung")
        self.assertFalse(
            VorgangEreignis.objects.filter(
                vorgang=vorgang, typ="system_wiedervorlage_faellig",
            ).exists()
        )

    def test_fehler_bei_einem_vorgang_bricht_andere_nicht_ab(self):
        gestern = date.today() - timedelta(days=1)
        fehlerhafter_vorgang = self._vorgang_in_wiedervorlage("PW005", gestern)
        intakter_vorgang = self._vorgang_in_wiedervorlage("PW006", gestern)

        original = vorgang_service.wechsle_status

        def _wechsle_status_mit_fehler(vorgang, *args, **kwargs):
            if vorgang.pk == fehlerhafter_vorgang.pk:
                raise RuntimeError("Simulierter Fehler für Test")
            return original(vorgang, *args, **kwargs)

        with patch(
            "apps.vorgaenge.services.vorgang_service.wechsle_status",
            side_effect=_wechsle_status_mit_fehler,
        ):
            ergebnis = pruefe_wiedervorlagen()

        fehlerhafter_vorgang.refresh_from_db()
        intakter_vorgang.refresh_from_db()

        # Der fehlerhafte Vorgang bleibt unverändert in 'wiedervorlage'...
        self.assertEqual(fehlerhafter_vorgang.status, "wiedervorlage")
        # ...der intakte Vorgang wird trotzdem korrekt zurückgeführt.
        self.assertEqual(intakter_vorgang.status, "in_bearbeitung")
        self.assertTrue(
            VorgangEreignis.objects.filter(
                vorgang=intakter_vorgang, typ="system_wiedervorlage_faellig",
            ).exists()
        )
        self.assertEqual(ergebnis, {'verarbeitet': 1, 'fehler': 1})
