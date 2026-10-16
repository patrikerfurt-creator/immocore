"""
Tests für den Beauftragungsvermerk und die Handwerker-Meilensteine im
Vorgangs-Verlauf (``VorgangEreignis``), siehe Orchestrator-Auftrag
"interne Kommentare vs. eigentümer-sichtbare Einträge, plus
Beauftragungsvermerk".

Deckt ab:
  - handwerker_beauftragt entsteht beim tatsächlichen Versand
    (``markiere_versendet``), NICHT bei ``erstelle_auftrag``
  - Text enthält Firmenname und Auftragsnummer
  - kein doppelter Vermerk bei erneutem Versand desselben Auftrags
  - kein Vermerk, wenn der Auftrag keinen Vorgang hat
  - handwerker_abgeschlossen entsteht beim Statuswechsel nach 'abgeschlossen'
  - alle diese Ereignisse sind intern=False
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.handwerker.models import Handwerkerauftrag
from apps.handwerker.services import auftrag_service
from apps.objekte.models import Objekt
from apps.rechnungen.models import Kreditor
from apps.vorgaenge.models import Vorgang, VorgangEreignis, VorgangTyp

User = get_user_model()


def _objekt(nr="HV001"):
    return Objekt.objects.create(
        bezeichnung="Test-WEG Vorgang-Ereignisse", objektnummer=nr, objekt_typ="weg",
        ort="Teststadt", verwaltung_seit=date(2020, 1, 1), bundesland="HE",
    )


def _kreditor(name="Müller Sanitär GmbH"):
    return Kreditor.objects.create(name=name, ist_handwerker=True, email="mueller@example.de")


def _user():
    return User.objects.create_user(username="vorgang-ereignis-tester", password="x")


def _vorgang(user, objekt):
    typ = VorgangTyp.objects.get(code="maengelmeldung")
    return Vorgang.objects.create(typ=typ, betreff="Testvorgang", erstellt_von=user, objekt=objekt)


def _auftrag_mit_vorgang(user, objekt, kreditor, status="entwurf", vorgang=None):
    return Handwerkerauftrag.objects.create(
        objekt=objekt, kreditor=kreditor, titel="Heizung defekt",
        erstellt_von=user, status=status, vorgang=vorgang or _vorgang(user, objekt),
    )


class BeauftragungsvermerkTest(TestCase):
    def setUp(self):
        self.user = _user()
        self.objekt = _objekt()
        self.kreditor = _kreditor()

    def test_entsteht_beim_versand_mit_firmenname_und_nummer(self):
        auftrag = _auftrag_mit_vorgang(self.user, self.objekt, self.kreditor, status="entwurf")
        auftrag_service.markiere_versendet(auftrag)

        ereignis = VorgangEreignis.objects.get(
            vorgang=auftrag.vorgang, typ="handwerker_beauftragt",
        )
        self.assertIn(self.kreditor.name, ereignis.text)
        self.assertIn(auftrag.nummer, ereignis.text)
        self.assertFalse(ereignis.intern)
        self.assertIsNone(ereignis.erstellt_von)

    def test_entsteht_nicht_bei_erstelle_auftrag(self):
        """Vor dem tatsächlichen Versand darf 'beauftragt' nicht im Verlauf
        stehen — sonst stünde es dort, obwohl die Mail nie rausging."""
        vorgang = _vorgang(self.user, self.objekt)
        auftrag_service.erstelle_auftrag(
            kreditor=self.kreditor, titel="Heizung defekt", erstellt_von=self.user,
            vorgang=vorgang,
        )
        self.assertFalse(
            VorgangEreignis.objects.filter(vorgang=vorgang, typ="handwerker_beauftragt").exists()
        )

    def test_kein_doppelter_vermerk_bei_erneutem_versand(self):
        auftrag = _auftrag_mit_vorgang(self.user, self.objekt, self.kreditor, status="entwurf")
        auftrag_service.markiere_versendet(auftrag)
        auftrag.refresh_from_db()

        # Erneuter (zweiter) erfolgreicher Versand desselben, bereits
        # versendeten Auftrags (Muster: apps.handwerker.tasks.versende_auftragsmail
        # nach versende_erneut).
        auftrag_service.markiere_versendet(auftrag)

        anzahl = VorgangEreignis.objects.filter(
            vorgang=auftrag.vorgang, typ="handwerker_beauftragt",
        ).count()
        self.assertEqual(anzahl, 1)

    def test_kein_vermerk_ohne_vorgang(self):
        auftrag = Handwerkerauftrag.objects.create(
            objekt=self.objekt, kreditor=self.kreditor, titel="Ohne Vorgang",
            erstellt_von=self.user, status="entwurf",
        )
        auftrag_service.markiere_versendet(auftrag)
        self.assertEqual(VorgangEreignis.objects.count(), 0)


class HandwerkerMeilensteineTest(TestCase):
    def setUp(self):
        self.user = _user()
        self.objekt = _objekt()
        self.kreditor = _kreditor()

    def test_abgeschlossen_erzeugt_vermerk(self):
        auftrag = _auftrag_mit_vorgang(self.user, self.objekt, self.kreditor, status="in_arbeit")
        auftrag_service.wechsle_status(auftrag, "abgeschlossen", erstellt_von=self.user)

        ereignis = VorgangEreignis.objects.get(vorgang=auftrag.vorgang, typ="handwerker_abgeschlossen")
        self.assertIn(self.kreditor.name, ereignis.text)
        self.assertFalse(ereignis.intern)

    def test_kein_vermerk_ohne_vorgang(self):
        auftrag = Handwerkerauftrag.objects.create(
            objekt=self.objekt, kreditor=self.kreditor, titel="Ohne Vorgang",
            erstellt_von=self.user, status="in_arbeit",
        )
        auftrag_service.wechsle_status(auftrag, "abgeschlossen", erstellt_von=self.user)
        self.assertEqual(VorgangEreignis.objects.count(), 0)

    def test_zwischenschritte_ohne_vorgang_ereignis_typ_erzeugen_keinen_vermerk(self):
        """Übergänge ohne eigenen Meilenstein (z.B. 'versendet' -> Vermerk
        läuft separat über markiere_versendet, 'in_arbeit' hat keinen
        Eigentümer-Meilenstein) dürfen kein handwerker_*-Ereignis erzeugen."""
        auftrag = _auftrag_mit_vorgang(self.user, self.objekt, self.kreditor, status="versendet")
        auftrag_service.wechsle_status(auftrag, "in_arbeit", erstellt_von=self.user)
        self.assertEqual(
            VorgangEreignis.objects.filter(vorgang=auftrag.vorgang).count(), 0,
        )
