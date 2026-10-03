"""
Tests für das Management-Command `kreditor_konsolidieren`.

Deckt die kritischen Pfade ab:
  - generisches Umhängen aller FK-Referenzen (Rechnung) auf das Ziel
  - Auflösung der RechnungsMatchRegel-Kollision (unique aktive Regel)
  - Übernahme der Quell-IBAN ans Ziel (damit künftig gematcht wird)
  - Deaktivieren (Standard) vs. Löschen (--loeschen)
  - --dry-run ändert nichts
"""
from datetime import date
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.konten.models import Konto
from apps.objekte.models import Objekt, Wirtschaftsjahr
from apps.rechnungen.models import (
    Kreditor,
    RechnungsMatchRegel,
    Rechnung,
)

User = get_user_model()

IBAN_Q = 'DE89370400440532013000'


def _welt():
    objekt = Objekt.objects.create(
        bezeichnung='Test-WEG', objektnummer='T001', objekt_typ='weg',
        ort='Teststadt', verwaltung_seit=date(2020, 1, 1),
    )
    wj = Wirtschaftsjahr.objects.create(objekt=objekt, jahr=2025, beginn_monat=1)
    aufwand = Konto.objects.create(
        wirtschaftsjahr=wj, kontonummer='50100', kontoname='Hauswart',
        kontoart='standard', direktes_buchen=False,
    )
    user = User.objects.create_user(username='tester', password='x')
    return objekt, aufwand, user


def _rechnung(objekt, kreditor, nr):
    return Rechnung.objects.create(
        objekt=objekt, kreditor=kreditor,
        betrag_brutto=Decimal('100.00'), rechnungsnummer=nr, status='in_pruefung',
    )


class KreditorKonsolidierenTest(TestCase):
    def setUp(self):
        self.objekt, self.aufwand, self.user = _welt()
        self.ziel = Kreditor.objects.create(name='Gartenbau Scherer', kreditorennummer='70073')
        self.q1 = Kreditor.objects.create(name='Gartenbau Scherer und Team', kreditorennummer='70043')
        self.q2 = Kreditor.objects.create(name='Scherer, Uwe', kreditorennummer='70101')

    def _run(self, *extra):
        out = StringIO()
        call_command('kreditor_konsolidieren',
                     '--ziel', '70073', '--quelle', '70043', '70101',
                     *extra, stdout=out, stderr=out)
        return out.getvalue()

    def test_rechnungen_werden_umgehaengt_und_quellen_deaktiviert(self):
        _rechnung(self.objekt, self.ziel, 'RE-A')
        _rechnung(self.objekt, self.q1, 'RE-B')
        _rechnung(self.objekt, self.q1, 'RE-C')
        _rechnung(self.objekt, self.q2, 'RE-D')

        self._run()

        self.assertEqual(Rechnung.objects.filter(kreditor=self.ziel).count(), 4)
        self.assertEqual(Rechnung.objects.filter(kreditor=self.q1).count(), 0)
        self.assertEqual(Rechnung.objects.filter(kreditor=self.q2).count(), 0)

        self.ziel.refresh_from_db(); self.q1.refresh_from_db(); self.q2.refresh_from_db()
        self.assertTrue(self.ziel.aktiv)
        self.assertFalse(self.q1.aktiv)
        self.assertFalse(self.q2.aktiv)
        # Deaktivieren (Standard) löscht nicht:
        self.assertTrue(Kreditor.objects.filter(kreditorennummer='70043').exists())

    def test_loeschen_entfernt_quellen(self):
        _rechnung(self.objekt, self.q1, 'RE-B')
        self._run('--loeschen')
        self.assertFalse(Kreditor.objects.filter(kreditorennummer='70043').exists())
        self.assertFalse(Kreditor.objects.filter(kreditorennummer='70101').exists())
        self.assertEqual(Rechnung.objects.filter(kreditor=self.ziel).count(), 1)

    def test_matchregel_kollision_wird_veraltet(self):
        # Ziel und Quelle haben je eine AKTIVE Regel mit gleichem (objekt, hash):
        RechnungsMatchRegel.objects.create(
            kreditor=self.ziel, objekt=self.objekt, leistungstext_hash='HASH1',
            aufwandskonto=self.aufwand, erstellt_durch=self.user, erstellt_aus='manuell',
        )
        kollidierend = RechnungsMatchRegel.objects.create(
            kreditor=self.q1, objekt=self.objekt, leistungstext_hash='HASH1',
            aufwandskonto=self.aufwand, erstellt_durch=self.user, erstellt_aus='manuell',
        )
        # Nicht kollidierende Quell-Regel (anderer Hash):
        frei = RechnungsMatchRegel.objects.create(
            kreditor=self.q1, objekt=self.objekt, leistungstext_hash='HASH2',
            aufwandskonto=self.aufwand, erstellt_durch=self.user, erstellt_aus='manuell',
        )

        self._run()

        kollidierend.refresh_from_db(); frei.refresh_from_db()
        # Kollidierende Quell-Regel ist jetzt veraltet und am Ziel:
        self.assertEqual(kollidierend.status, 'veraltet')
        self.assertEqual(kollidierend.kreditor_id, self.ziel.id)
        # Freie Quell-Regel wurde umgehängt und bleibt aktiv:
        self.assertEqual(frei.status, 'aktiv')
        self.assertEqual(frei.kreditor_id, self.ziel.id)
        # Ziel hat weiter genau eine aktive Regel für (objekt, HASH1):
        self.assertEqual(
            RechnungsMatchRegel.objects.filter(
                kreditor=self.ziel, objekt=self.objekt,
                leistungstext_hash='HASH1', status='aktiv').count(),
            1,
        )

    def test_iban_wird_uebernommen(self):
        self.q2.iban = IBAN_Q
        self.q2.save(update_fields=['iban'])

        self._run()

        self.ziel.refresh_from_db(); self.q2.refresh_from_db()
        self.assertEqual(self.ziel.iban, IBAN_Q)   # Ziel hatte keine → wird Haupt-IBAN
        self.assertIsNone(self.q2.iban)            # Quelle freigeräumt

    def test_dry_run_aendert_nichts(self):
        _rechnung(self.objekt, self.q1, 'RE-B')
        self._run('--dry-run')
        self.q1.refresh_from_db()
        self.assertTrue(self.q1.aktiv)
        self.assertEqual(Rechnung.objects.filter(kreditor=self.q1).count(), 1)
        self.assertEqual(Rechnung.objects.filter(kreditor=self.ziel).count(), 0)
