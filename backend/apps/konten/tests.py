"""
Tests der Konten-App.

Schwerpunkt: Zuordnung von SollstellungZahlungen zu Teilbuchungen für die
Spalte „tilgt OP" im Buchungsdetail (Debitoren/Personenkonto).
"""
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from datetime import date

from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIRequestFactory

from apps.konten.services import ordne_zahlungen_teilbuchungen_zu


def _teil(betrag, ba_id):
    return SimpleNamespace(id=uuid4(), betrag=Decimal(betrag), buchungsart_id=ba_id)


def _zahlung(betrag, ba_id, opos):
    split = SimpleNamespace(ba_id=ba_id)
    return SimpleNamespace(
        id=uuid4(), betrag=Decimal(betrag), split=split, split_id=uuid4(),
        sollstellung=SimpleNamespace(opos_nr=opos),
    )


class OpZuordnungTest(SimpleTestCase):

    def test_zwei_teilbuchungen_gleiche_ba_werden_korrekt_getrennt(self):
        """
        Der Fall, der die Zuordnung nötig macht: laufender Monat + Nachtilgung
        eines Vormonats gehen beide auf dasselbe Erlöskonto (gleiche BA).
        """
        laufend = _teil('320.25', ba_id=900)
        nachtilgung = _teil('3.60', ba_id=900)
        ruecklage = _teil('76.15', ba_id=911)
        zahlungen = [
            _zahlung('3.60', 900, 'OPOS-MAI'),
            _zahlung('320.25', 900, 'OPOS-JUNI'),
            _zahlung('76.15', 911, 'OPOS-JUNI'),
        ]
        z = ordne_zahlungen_teilbuchungen_zu([laufend, nachtilgung, ruecklage], zahlungen)
        self.assertEqual(z[laufend.id].sollstellung.opos_nr, 'OPOS-JUNI')
        self.assertEqual(z[nachtilgung.id].sollstellung.opos_nr, 'OPOS-MAI')
        self.assertEqual(z[ruecklage.id].sollstellung.opos_nr, 'OPOS-JUNI')

    def test_jede_zahlung_wird_nur_einmal_vergeben(self):
        """Gleiche Beträge dürfen nicht doppelt derselben Zahlung zugeordnet werden."""
        a = _teil('50.00', ba_id=900)
        b = _teil('50.00', ba_id=900)
        zahlungen = [_zahlung('50.00', 900, 'OPOS-A'), _zahlung('50.00', 900, 'OPOS-B')]
        z = ordne_zahlungen_teilbuchungen_zu([a, b], zahlungen)
        self.assertEqual(len({z[a.id].id, z[b.id].id}), 2)

    def test_fallback_nur_betrag_wenn_ba_abweicht(self):
        t = _teil('99.00', ba_id=900)
        zahlungen = [_zahlung('99.00', 911, 'OPOS-X')]
        z = ordne_zahlungen_teilbuchungen_zu([t], zahlungen)
        self.assertEqual(z[t.id].sollstellung.opos_nr, 'OPOS-X')

    def test_ohne_passende_zahlung_kein_eintrag(self):
        t = _teil('12.34', ba_id=900)
        z = ordne_zahlungen_teilbuchungen_zu([t], [_zahlung('99.99', 900, 'OPOS-Y')])
        self.assertNotIn(t.id, z)

    def test_ohne_zahlungen_leeres_ergebnis(self):
        t = _teil('10.00', ba_id=900)
        self.assertEqual(ordne_zahlungen_teilbuchungen_zu([t], []), {})


class KontenJahresFilterTest(TestCase):
    """
    Konten sind jahresgebunden. Der Listen-Endpunkt muss die Konten des
    angefragten Jahres liefern — sonst zeigt ein Belegformular die Konten des
    laufenden Wirtschaftsjahres, während die Vorkontierung auf das Konto des
    Belegjahres zeigt. Die Auswahl wirkt dann leer, obwohl ein Konto gesetzt ist.
    """

    def setUp(self):
        from apps.objekte.models import Objekt, Wirtschaftsjahr
        from apps.konten.models import Konto
        from django.contrib.auth import get_user_model

        self.objekt = Objekt.objects.create(
            bezeichnung='Test-WEG-Jahr', objektnummer='JF001', objekt_typ='WEG',
            strasse='Teststr. 1', plz='60000', ort='Teststadt',
            verwaltung_seit=date(2020, 1, 1),
        )
        self.wj2025 = Wirtschaftsjahr.objects.create(objekt=self.objekt, jahr=2025, beginn_monat=1)
        self.wj2026 = Wirtschaftsjahr.objects.create(objekt=self.objekt, jahr=2026, beginn_monat=1)
        self.konto2025 = Konto.objects.create(
            wirtschaftsjahr=self.wj2025, kontonummer='55100', kontoname='Verwaltergebühr',
            kontoart='standard',
        )
        self.konto2026 = Konto.objects.create(
            wirtschaftsjahr=self.wj2026, kontonummer='55100', kontoname='Verwaltergebühr',
            kontoart='standard',
        )
        self.user = get_user_model().objects.create_user(username='kf_test', password='x')

    def _ids_fuer(self, params):
        from apps.konten.views import KontoViewSet
        req = APIRequestFactory().get('/', params)
        req.user = self.user
        resp = KontoViewSet.as_view({'get': 'list'})(req)
        daten = resp.data if isinstance(resp.data, list) else resp.data.get('results', [])
        return {str(k['id']) for k in daten if k.get('kontonummer') == '55100'}

    def test_jahr_liefert_konto_des_angefragten_jahres(self):
        ids = self._ids_fuer({'objekt': str(self.objekt.id), 'jahr': '2025'})
        self.assertIn(str(self.konto2025.id), ids)
        self.assertNotIn(str(self.konto2026.id), ids)

    def test_ohne_jahr_weiterhin_aktuelles_wirtschaftsjahr(self):
        ids = self._ids_fuer({'objekt': str(self.objekt.id)})
        self.assertIn(str(self.konto2026.id), ids)

    def test_unbekanntes_jahr_faellt_auf_aktuelles_zurueck(self):
        """Kein Wirtschaftsjahr 2019 → Liste bleibt nutzbar statt leer."""
        ids = self._ids_fuer({'objekt': str(self.objekt.id), 'jahr': '2019'})
        self.assertEqual(ids, {str(self.konto2026.id)})
