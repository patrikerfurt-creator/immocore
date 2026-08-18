"""
Tests für die n:1-Rechnungsverknüpfung Rechnung.handwerkerauftrag
(Phase A, Orchestrator-Vorgabe 8).

Deckt ab:
  - Rechnung.handwerkerauftrag ist setzbar
  - mehrere Rechnungen können demselben Auftrag zugeordnet werden
  - auftrag.rechnungen (related_name) liefert sie
  - Regressionstest: Rechnung.beleg_dokument bleibt von der
    Handwerkerauftrag-Verknüpfung unberührt (Owner-Regel B-Hybrid)
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase

from apps.dokumente.models import Dokument
from apps.handwerker.models import Handwerkerauftrag
from apps.objekte.models import Objekt
from apps.rechnungen.models import Kreditor, Rechnung

User = get_user_model()


def _objekt(nr="H300"):
    return Objekt.objects.create(
        bezeichnung="Test-WEG Rechnungsverknüpfung", objektnummer=nr, objekt_typ="weg",
        ort="Teststadt", verwaltung_seit=date(2020, 1, 1),
    )


def _kreditor():
    return Kreditor.objects.create(
        name="Meister Sanitär GmbH", ist_handwerker=True, email="meister@example.de",
    )


def _auftrag(objekt):
    return Handwerkerauftrag.objects.create(
        objekt=objekt, kreditor=_kreditor(), titel="Wasserhahn undicht",
    )


def _rechnung(objekt, **kwargs):
    defaults = dict(objekt=objekt, status="importiert", betrag_brutto=Decimal("100.00"))
    defaults.update(kwargs)
    return Rechnung.objects.create(**defaults)


class RechnungHandwerkerauftragTest(TestCase):
    def setUp(self):
        self.objekt = _objekt()
        self.auftrag = _auftrag(self.objekt)

    def test_handwerkerauftrag_ist_setzbar(self):
        rechnung = _rechnung(self.objekt, handwerkerauftrag=self.auftrag)
        rechnung.refresh_from_db()
        self.assertEqual(rechnung.handwerkerauftrag_id, self.auftrag.id)

    def test_mehrere_rechnungen_an_einem_auftrag_moeglich(self):
        r1 = _rechnung(self.objekt, handwerkerauftrag=self.auftrag)
        r2 = _rechnung(self.objekt, handwerkerauftrag=self.auftrag)
        rechnungen = list(self.auftrag.rechnungen.all())
        self.assertCountEqual(rechnungen, [r1, r2])

    def test_rechnung_ohne_auftrag_bleibt_moeglich(self):
        rechnung = _rechnung(self.objekt)
        self.assertIsNone(rechnung.handwerkerauftrag_id)


class RechnungBelegDokumentRegressionTest(TestCase):
    """Stellt sicher, dass die neue Handwerkerauftrag-FK die bestehende
    Beleg-Dokument-Kopplung (GoBD, B-Hybrid) nicht beeinflusst."""

    def setUp(self):
        self.objekt = _objekt("H301")
        self.auftrag = _auftrag(self.objekt)
        self.user = User.objects.create_user(username="beleg-tester", password="x")

    def test_beleg_dokument_bleibt_unberuehrt_von_handwerkerauftrag(self):
        dok = Dokument.objects.create(
            datei=ContentFile(b"%PDF-1.4 Beleg", name="beleg.pdf"),
            dateiname="beleg.pdf", kategorie="Beleg", dokument_typ="beleg",
            objekt=self.objekt, hochgeladen_von=self.user, ablage_wurzel="media",
        )
        rechnung = _rechnung(self.objekt, beleg_dokument=dok, handwerkerauftrag=self.auftrag)
        rechnung.refresh_from_db()
        self.assertEqual(rechnung.beleg_dokument_id, dok.id)
        self.assertEqual(rechnung.handwerkerauftrag_id, self.auftrag.id)
