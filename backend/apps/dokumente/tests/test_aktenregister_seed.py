"""
Tests fuer die geseedete Hausakten-Gliederung (Migration 0013).

Die Struktur stammt aus dem Trennblaetterverzeichnis der Demme GmbH. Geprueft
wird, dass die gewohnten Nummern 01-17 unveraendert stehen — verschoebe sich
eine davon, passten Papier- und Digitalakte nicht mehr zusammen.
"""
from django.test import TestCase

from apps.dokumente.models import Aktenregister
from apps.dokumente.services import akten_service

# Die Nummern aus dem Papierverzeichnis, die sich nicht verschieben duerfen.
AUS_DEM_PAPIER = {
    '01': 'Grundbesitzabgaben', '03': 'Schornsteinfeger', '05': 'Wartung',
    '06': 'Versicherung', '11': 'Teilungserkl', '15': 'Beschlusssammlung',
    '17': 'Rechtsangelegenheiten',
}


class AktenregisterSeedTest(TestCase):
    def test_einundzwanzig_register_sind_angelegt(self):
        self.assertEqual(
            Aktenregister.objects.filter(objekt__isnull=True).count(), 21)

    def test_gewohnte_nummern_stehen_unveraendert(self):
        for code, teil in AUS_DEM_PAPIER.items():
            with self.subTest(code=code):
                register = Aktenregister.objects.get(code=code, objekt__isnull=True)
                self.assertIn(teil, register.bezeichnung)

    def test_reihenfolge_entspricht_den_nummern(self):
        codes = list(akten_service.register_einer_akte(
            Aktenregister.AKTENART_HAUS).values_list('code', flat=True))
        self.assertEqual(codes, [f'{n:02d}' for n in range(1, 22)])

    def test_schriftwechsel_gilt_in_allen_akten(self):
        # Als einziges Register aktenart='alle' — Korrespondenz faellt zum
        # Objekt, zur Wohnung und zur Person an.
        self.assertEqual(
            Aktenregister.objects.get(code='21', objekt__isnull=True).aktenart,
            Aktenregister.AKTENART_ALLE)
        for aktenart in (Aktenregister.AKTENART_WOHNUNG,
                         Aktenregister.AKTENART_EIGENTUEMER):
            with self.subTest(aktenart=aktenart):
                codes = [r.code for r in akten_service.register_einer_akte(aktenart)]
                self.assertEqual(codes, ['21'])

    def test_sortierung_laesst_platz_zum_einschieben(self):
        # Zehnerschritte: zwischen zwei Register passt eines, ohne alle
        # folgenden neu zu nummerieren.
        werte = sorted(Aktenregister.objects.filter(objekt__isnull=True)
                       .values_list('sortierung', flat=True))
        self.assertEqual(werte[0], 10)
        self.assertTrue(all(b - a == 10 for a, b in zip(werte, werte[1:])))

    def test_mehrdeutige_register_tragen_einen_hinweis(self):
        # 14/15/16 sind die Stellen, an denen ohne Erlaeuterung falsch
        # abgelegt wird.
        for code in ('05', '14', '15', '16', '17', '19'):
            with self.subTest(code=code):
                register = Aktenregister.objects.get(code=code, objekt__isnull=True)
                self.assertTrue(register.hinweis.strip())

    def test_untergliederung_haengt_sich_unter_ein_geseedetes_register(self):
        from datetime import date
        from apps.objekte.models import Objekt

        objekt = Objekt.objects.create(
            bezeichnung='WEG Seed-Test', objektnummer='SD001', objekt_typ='weg',
            ort='Teststadt', verwaltung_seit=date(2020, 1, 1))
        wartung = Aktenregister.objects.get(code='05', objekt__isnull=True)

        hebeanlage = Aktenregister(
            code='05/A', bezeichnung='Hebeanlage', sortierung=51,
            aktenart=Aktenregister.AKTENART_HAUS, eltern=wartung, objekt=objekt)
        hebeanlage.full_clean()
        hebeanlage.save()

        codes = [r.code for r in akten_service.register_einer_akte(
            Aktenregister.AKTENART_HAUS, objekt=objekt)]
        self.assertIn('05/A', codes)
