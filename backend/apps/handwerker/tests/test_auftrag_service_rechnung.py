"""
Tests für ``auftrag_service.ordne_rechnung_zu`` /
``auftrag_service.loese_rechnung_zuordnung`` (Phase B, Orchestrator-Vorgabe
Schritt 2/5).

Deckt ab:
  - erfolgreiche Zuordnung schreibt ein 'rechnung_zugeordnet'-Ereignis
  - fremder Kreditor wird abgewiesen
  - bereits einem anderen Auftrag zugeordnete Rechnung wird abgewiesen
  - Lösen der Zuordnung funktioniert und schreibt ein Ereignis
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.handwerker.models import Handwerkerauftrag
from apps.handwerker.services import auftrag_service
from apps.objekte.models import Objekt
from apps.rechnungen.models import Kreditor, Rechnung

User = get_user_model()


def _objekt(nr="H800"):
    return Objekt.objects.create(
        bezeichnung="Test-WEG Rechnung", objektnummer=nr, objekt_typ="weg",
        ort="Teststadt", verwaltung_seit=date(2020, 1, 1), bundesland="HE",
    )


def _kreditor(name="Meister Sanitär GmbH", email="meister@example.de"):
    return Kreditor.objects.create(name=name, ist_handwerker=True, email=email)


def _user():
    return User.objects.create_user(username="rechnung-tester", password="x")


def _rechnung(objekt, kreditor, **kwargs):
    defaults = dict(objekt=objekt, kreditor=kreditor, status="importiert",
                     betrag_brutto=Decimal("100.00"), rechnungsnummer="RE-1")
    defaults.update(kwargs)
    return Rechnung.objects.create(**defaults)


class OrdneRechnungZuTest(TestCase):
    def setUp(self):
        self.user = _user()
        self.objekt = _objekt()
        self.kreditor = _kreditor()
        self.auftrag = Handwerkerauftrag.objects.create(
            objekt=self.objekt, kreditor=self.kreditor, titel="Testauftrag",
            erstellt_von=self.user,
        )

    def test_erfolgreiche_zuordnung_schreibt_ereignis(self):
        rechnung = _rechnung(self.objekt, self.kreditor)
        auftrag_service.ordne_rechnung_zu(self.auftrag, rechnung, erstellt_von=self.user)

        rechnung.refresh_from_db()
        self.assertEqual(rechnung.handwerkerauftrag_id, self.auftrag.id)
        ereignisse = self.auftrag.ereignisse.filter(typ="rechnung_zugeordnet")
        self.assertEqual(ereignisse.count(), 1)
        self.assertIn("RE-1", ereignisse.first().text)

    def test_fremder_kreditor_wird_abgewiesen(self):
        anderer_kreditor = _kreditor(name="Anderer Handwerker", email="anderer@example.de")
        rechnung = _rechnung(self.objekt, anderer_kreditor)
        with self.assertRaises(ValidationError):
            auftrag_service.ordne_rechnung_zu(self.auftrag, rechnung, erstellt_von=self.user)
        rechnung.refresh_from_db()
        self.assertIsNone(rechnung.handwerkerauftrag_id)

    def test_bereits_anderem_auftrag_zugeordnete_rechnung_wird_abgewiesen(self):
        anderer_auftrag = Handwerkerauftrag.objects.create(
            objekt=self.objekt, kreditor=self.kreditor, titel="Anderer Auftrag",
            erstellt_von=self.user,
        )
        rechnung = _rechnung(self.objekt, self.kreditor, handwerkerauftrag=anderer_auftrag)
        with self.assertRaises(ValidationError):
            auftrag_service.ordne_rechnung_zu(self.auftrag, rechnung, erstellt_von=self.user)
        rechnung.refresh_from_db()
        self.assertEqual(rechnung.handwerkerauftrag_id, anderer_auftrag.id)

    def test_erneute_zuordnung_zum_gleichen_auftrag_ist_unproblematisch(self):
        rechnung = _rechnung(self.objekt, self.kreditor, handwerkerauftrag=self.auftrag)
        auftrag_service.ordne_rechnung_zu(self.auftrag, rechnung, erstellt_von=self.user)
        rechnung.refresh_from_db()
        self.assertEqual(rechnung.handwerkerauftrag_id, self.auftrag.id)

    def test_loesen_der_zuordnung_funktioniert(self):
        rechnung = _rechnung(self.objekt, self.kreditor, handwerkerauftrag=self.auftrag)
        auftrag_service.loese_rechnung_zuordnung(rechnung, erstellt_von=self.user)
        rechnung.refresh_from_db()
        self.assertIsNone(rechnung.handwerkerauftrag_id)
        self.assertEqual(self.auftrag.ereignisse.filter(typ="rechnung_zugeordnet").count(), 1)

    def test_loesen_ohne_zuordnung_wird_abgewiesen(self):
        rechnung = _rechnung(self.objekt, self.kreditor)
        with self.assertRaises(ValidationError):
            auftrag_service.loese_rechnung_zuordnung(rechnung, erstellt_von=self.user)


class KommentiereTest(TestCase):
    def setUp(self):
        self.user = _user()
        self.objekt = _objekt()
        self.kreditor = _kreditor()
        self.auftrag = Handwerkerauftrag.objects.create(
            objekt=self.objekt, kreditor=self.kreditor, titel="Testauftrag",
            erstellt_von=self.user,
        )

    def test_kommentar_wird_angelegt(self):
        ereignis = auftrag_service.kommentiere(self.auftrag, "Termin mit Mieter abgestimmt.", self.user)
        self.assertEqual(ereignis.typ, "kommentar")
        self.assertEqual(ereignis.erstellt_von, self.user)

    def test_leerer_kommentar_wird_abgewiesen(self):
        with self.assertRaises(ValidationError):
            auftrag_service.kommentiere(self.auftrag, "   ", self.user)
