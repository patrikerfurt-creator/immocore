"""
Tests für ``auftrag_service.liefer_eingang`` (Lieferadresse der Auftragsmail).

Deckt ab:
  - Vorgang -> Einheit -> Eingang hat Vorrang
  - Fallback: erster Eingang des Objekts (nach bezeichnung)
  - Einheit ohne Eingang -> ebenfalls Fallback auf ersten Objekt-Eingang
  - kein Eingang vorhanden -> None (Aufrufer fällt auf Objektadresse zurück)
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.handwerker.models import Handwerkerauftrag
from apps.handwerker.services import auftrag_service
from apps.objekte.models import Eingang, Einheit, Objekt
from apps.rechnungen.models import Kreditor
from apps.vorgaenge.models import Vorgang, VorgangTyp

User = get_user_model()


class LieferEingangTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="eingang-tester", password="x")
        self.objekt = Objekt.objects.create(
            bezeichnung="Test-WEG Eingang", objektnummer="H910", objekt_typ="weg",
            strasse="Objektstr. 1", plz="10000", ort="Objektstadt",
            verwaltung_seit=date(2020, 1, 1), bundesland="HE",
        )
        self.kreditor = Kreditor.objects.create(
            name="Meister Sanitär GmbH", ist_handwerker=True, email="meister@example.de",
        )

    def _eingang(self, bezeichnung, strasse="Str. 1"):
        return Eingang.objects.create(
            objekt=self.objekt, bezeichnung=bezeichnung, strasse=strasse,
            plz="20000", ort="Eingangsort",
        )

    def _auftrag(self, vorgang=None):
        return Handwerkerauftrag.objects.create(
            objekt=self.objekt, kreditor=self.kreditor, titel="Test",
            erstellt_von=self.user, status="entwurf", vorgang=vorgang,
        )

    def _vorgang(self, einheit=None):
        return Vorgang.objects.create(
            typ=VorgangTyp.objects.get(code="maengelmeldung"), betreff="Mangel",
            erstellt_von=self.user, objekt=self.objekt, einheit=einheit,
        )

    def _einheit(self, eingang=None):
        return Einheit.objects.create(
            objekt=self.objekt, eingang=eingang, einheit_nr="1",
            einheit_typ="Wohnung", lage="EG",
        )

    def test_eingang_der_einheit_des_vorgangs_hat_vorrang(self):
        self._eingang("A erster")
        eingang_b = self._eingang("B zweiter")
        auftrag = self._auftrag(self._vorgang(self._einheit(eingang_b)))

        self.assertEqual(auftrag_service.liefer_eingang(auftrag), eingang_b)

    def test_fallback_erster_objekt_eingang_nach_bezeichnung(self):
        self._eingang("C dritter")
        eingang_a = self._eingang("A erster")
        auftrag = self._auftrag()

        self.assertEqual(auftrag_service.liefer_eingang(auftrag), eingang_a)

    def test_einheit_ohne_eingang_faellt_auf_ersten_objekt_eingang_zurueck(self):
        eingang_a = self._eingang("A erster")
        auftrag = self._auftrag(self._vorgang(self._einheit(eingang=None)))

        self.assertEqual(auftrag_service.liefer_eingang(auftrag), eingang_a)

    def test_vorgang_ohne_einheit_faellt_auf_ersten_objekt_eingang_zurueck(self):
        eingang_a = self._eingang("A erster")
        auftrag = self._auftrag(self._vorgang())

        self.assertEqual(auftrag_service.liefer_eingang(auftrag), eingang_a)

    def test_ohne_eingang_wird_none_geliefert(self):
        self.assertIsNone(auftrag_service.liefer_eingang(self._auftrag()))
