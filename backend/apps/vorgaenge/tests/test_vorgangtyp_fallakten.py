"""
Tests fuer die Fallakten-Vorgangstypen (Migration 0013).

Geprueft wird vor allem, was still schiefgehen wuerde: ein automatischer
KI-Antwortentwurf bei einem Rechtsfall waere eine Rechtsauskunft, und eine
im Portal anlegbare Hausgeldklage waere widersinnig — beides faellt sonst
erst im Betrieb auf.
"""
from django.test import TestCase

from apps.vorgaenge.models import VorgangTyp

FALLAKTEN = ['anfechtung', 'hausgeldklage', 'versicherungsschaden', 'sanierung']


class FallaktenTypenTest(TestCase):
    def test_alle_vier_typen_sind_angelegt(self):
        vorhanden = set(VorgangTyp.objects.filter(code__in=FALLAKTEN)
                        .values_list('code', flat=True))
        self.assertEqual(vorhanden, set(FALLAKTEN))

    def test_kein_automatischer_ki_entwurf(self):
        # Ein versandfertiger Entwurf zu einer Anfechtung waere eine
        # Rechtsauskunft — er darf gar nicht erst entstehen.
        for typ in VorgangTyp.objects.filter(code__in=FALLAKTEN):
            with self.subTest(code=typ.code):
                self.assertFalse(typ.antwort_vorschlag_aktiv)

    def test_nicht_im_portal_erstellbar(self):
        # Am deutlichsten bei der Hausgeldklage: sie richtet sich gegen den
        # Eigentuemer, der sie sonst selbst anlegen koennte.
        for typ in VorgangTyp.objects.filter(code__in=FALLAKTEN):
            with self.subTest(code=typ.code):
                self.assertFalse(typ.portal_erstellbar)

    def test_fristgebundene_faelle_starten_mit_hoher_prioritaet(self):
        # § 45 WEG (Anfechtung) und die Anzeigefristen der Versicherer sind
        # Ausschlussfristen — versaeumt heisst verloren.
        for code in ('anfechtung', 'hausgeldklage', 'versicherungsschaden'):
            with self.subTest(code=code):
                self.assertEqual(
                    VorgangTyp.objects.get(code=code).standard_prioritaet, 'hoch')

    def test_sanierung_ist_normal_priorisiert(self):
        self.assertEqual(
            VorgangTyp.objects.get(code='sanierung').standard_prioritaet, 'normal')

    def test_stehen_hinter_den_bestehenden_typen(self):
        neueste_alte = VorgangTyp.objects.exclude(
            code__in=FALLAKTEN).order_by('-sortierung').first()
        aelteste_neue = VorgangTyp.objects.filter(
            code__in=FALLAKTEN).order_by('sortierung').first()
        self.assertGreater(aelteste_neue.sortierung, neueste_alte.sortierung)

    def test_prioritaet_wird_beim_anlegen_uebernommen(self):
        from datetime import date
        from django.contrib.auth import get_user_model
        from apps.objekte.models import Objekt
        from apps.vorgaenge.services import vorgang_service

        objekt = Objekt.objects.create(
            bezeichnung='Test-WEG Fallakte', objektnummer='FA001',
            objekt_typ='weg', ort='Teststadt', verwaltung_seit=date(2020, 1, 1))
        user = get_user_model().objects.create_user(username='fa-tester', password='x')

        vorgang = vorgang_service.erstelle_vorgang(
            typ=VorgangTyp.objects.get(code='anfechtung'),
            betreff='Anfechtung TOP 5', erstellt_von=user, objekt=objekt)

        self.assertEqual(vorgang.prioritaet, 'hoch')
        # Kein Entwurf angestossen: der Typ hat das Flag nicht.
        self.assertEqual(vorgang.antwort_vorschlaege.count(), 0)
