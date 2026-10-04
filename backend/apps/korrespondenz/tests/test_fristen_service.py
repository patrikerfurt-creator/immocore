"""Test 20 (Spec 11): Frist verschiebt Wochenende/Feiertag auf den nächsten Werktag."""
from datetime import date

from django.test import SimpleTestCase

from apps.korrespondenz.services.fristen_service import berechne_frist, naechster_werktag


class FristTest(SimpleTestCase):

    def test_werktag_bleibt(self):
        # 29.09.2026 (Di) + 14 = 13.10.2026 (Di)
        self.assertEqual(berechne_frist(date(2026, 9, 29), 14, 'HE'), date(2026, 10, 13))

    def test_sonntag_wird_montag(self):
        # 29.09. + 5 = So 04.10.; Sa 03.10. wäre Feiertag, ist aber ohnehin Wochenende
        self.assertEqual(berechne_frist(date(2026, 9, 29), 5, 'HE'), date(2026, 10, 5))

    def test_samstag_wird_montag(self):
        self.assertEqual(berechne_frist(date(2026, 9, 29), 4, 'HE'), date(2026, 10, 5))

    def test_feiertag_unter_der_woche_wird_naechster_tag(self):
        # 14.05.2026 (Do) = Christi Himmelfahrt -> Fr 15.05.
        self.assertEqual(berechne_frist(date(2026, 5, 1), 13, 'HE'), date(2026, 5, 15))

    def test_feiertag_vor_wochenende_springt_ueber_das_wochenende(self):
        # 01.05.2026 (Fr) = Tag der Arbeit -> Mo 04.05.
        self.assertEqual(berechne_frist(date(2026, 4, 17), 14, 'HE'), date(2026, 5, 4))

    def test_karfreitag_bis_ostermontag(self):
        # Fr 03.04. Karfreitag, Sa, So, Mo 06.04. Ostermontag -> Di 07.04.
        self.assertEqual(berechne_frist(date(2026, 3, 20), 14, 'HE'), date(2026, 4, 7))

    def test_feiertag_haengt_vom_bundesland_ab(self):
        # Fronleichnam 04.06.2026 (Do): Feiertag in Hessen, nicht in Berlin.
        self.assertEqual(berechne_frist(date(2026, 5, 21), 14, 'HE'), date(2026, 6, 5))
        self.assertEqual(berechne_frist(date(2026, 5, 21), 14, 'BE'), date(2026, 6, 4))

    def test_weihnachten(self):
        # Fr 25.12. Feiertag, Sa 26.12. (Feiertag+WE), So 27.12. -> Mo 28.12.
        self.assertEqual(berechne_frist(date(2026, 12, 11), 14, 'HE'), date(2026, 12, 28))

    def test_naechster_werktag_direkt(self):
        self.assertEqual(naechster_werktag(date(2026, 10, 3), 'HE'), date(2026, 10, 5))
        self.assertEqual(naechster_werktag(date(2026, 10, 5), 'HE'), date(2026, 10, 5))

    def test_frist_null_tage(self):
        self.assertEqual(berechne_frist(date(2026, 9, 26), 0, 'HE'), date(2026, 9, 28))  # Sa -> Mo
