"""
Tests: Kontierung der Kreditor-Seite bei Buchungen aus der
Dialogbuchhaltung. Die Kreditor-Seite muss im Hauptbuch als Sachkonto
70xxx ankommen, im Wirtschaftsjahr der Gegenseite.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.buchhaltung.models import Buchung, Buchungsart
from apps.konten.models import Konto, Personenkonto
from apps.objekte.models import Objekt, Wirtschaftsjahr
from apps.rechnungen.models import Kreditor

User = get_user_model()
BASE = '/api/v1/buchungen/'


class KreditorBuchungKontierungTest(TestCase):

    client_class = APIClient

    def setUp(self):
        self.user = User.objects.create_user('kb-tester', password='x', is_staff=True)
        self.client.force_authenticate(self.user)
        self.objekt = Objekt.objects.create(
            objektnummer='KB-1', objekt_typ='WEG', bezeichnung='Kreditor Testobjekt',
            strasse='Teststr. 1', plz='12345', ort='Teststadt',
            verwaltung_seit=date(2020, 1, 1),
        )
        self.wj2025 = Wirtschaftsjahr.objects.create(
            objekt=self.objekt, jahr=2025, beginn_monat=1, status='offen')
        self.wj2026 = Wirtschaftsjahr.objects.create(
            objekt=self.objekt, jahr=2026, beginn_monat=1,
            vorjahr=self.wj2025, status='offen')
        self.bank2025 = Konto.objects.create(
            wirtschaftsjahr=self.wj2025, kontonummer='18000', kontoname='Bank 1')
        self.bank2026 = Konto.objects.create(
            wirtschaftsjahr=self.wj2026, kontonummer='18000', kontoname='Bank 1')
        self.kreditor = Kreditor.objects.create(name='Zahlungs Handwerk GmbH')
        # 054/055 kommen aus Migration 0053
        self.ba_ausgang = Buchungsart.objects.get(nr='055')
        self.ba_eingang = Buchungsart.objects.get(nr='054')

    def _post(self, **extra):
        daten = {
            'objekt': str(self.objekt.id),
            'betrag': '250.00',
            'buchungsdatum': '2025-06-15',
            'buchungstext': 'Test',
            'wirtschaftsjahr': str(self.wj2025.id),
        }
        daten.update(extra)
        return self.client.post(BASE, daten, format='json')

    @property
    def kreditor_nr(self):
        return self.kreditor.kreditorennummer

    # -- Kernfälle -----------------------------------------------------------

    def test_zahlungsausgang_kontiert_kreditor_ins_soll(self):
        resp = self._post(
            buchungsart=str(self.ba_ausgang.id),
            haben_konto=str(self.bank2025.id),
            kreditor=str(self.kreditor.id),
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        b = Buchung.objects.get(pk=resp.data['id'])
        self.assertIsNotNone(b.soll_konto, 'Kreditor-Bein fehlt im Soll')
        self.assertEqual(b.soll_konto.kontonummer, self.kreditor_nr)
        self.assertEqual(b.haben_konto, self.bank2025)
        self.assertEqual(b.kreditor, self.kreditor)

    def test_zahlungseingang_kontiert_kreditor_ins_haben(self):
        resp = self._post(
            buchungsart=str(self.ba_eingang.id),
            soll_konto=str(self.bank2025.id),
            kreditor=str(self.kreditor.id),
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        b = Buchung.objects.get(pk=resp.data['id'])
        self.assertEqual(b.soll_konto, self.bank2025)
        self.assertIsNotNone(b.haben_konto, 'Kreditor-Bein fehlt im Haben')
        self.assertEqual(b.haben_konto.kontonummer, self.kreditor_nr)

    def test_kreditorkonto_wird_angelegt_und_wiederverwendet(self):
        self.assertFalse(Konto.objects.filter(kontonummer=self.kreditor_nr).exists())
        self._post(haben_konto=str(self.bank2025.id), kreditor=str(self.kreditor.id))
        self._post(haben_konto=str(self.bank2025.id), kreditor=str(self.kreditor.id))
        konten = Konto.objects.filter(
            kontonummer=self.kreditor_nr, wirtschaftsjahr=self.wj2025)
        self.assertEqual(konten.count(), 1, 'Kreditorkonto wurde doppelt angelegt')
        self.assertEqual(konten.first().kontoname, f'Kreditor {self.kreditor.name}')

    def test_kreditorkonto_folgt_dem_jahr_der_gegenseite(self):
        """
        Die Bank kommt aus 2026 — dann muss auch das Kreditorkonto aus 2026
        stammen, sonst zerfällt die Buchung auf zwei Kontenrahmen.
        """
        resp = self._post(
            buchungsdatum='2026-03-01',
            wirtschaftsjahr=str(self.wj2025.id),   # bewusst abweichend
            haben_konto=str(self.bank2026.id),
            kreditor=str(self.kreditor.id),
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        b = Buchung.objects.get(pk=resp.data['id'])
        self.assertEqual(b.soll_konto.wirtschaftsjahr.jahr, 2026)
        self.assertEqual(b.haben_konto.wirtschaftsjahr.jahr, 2026)

    def test_buchung_erscheint_auf_dem_kreditorkonto(self):
        """Genau das war der Bruch: die Buchung war im Hauptbuch unsichtbar."""
        self._post(haben_konto=str(self.bank2025.id), kreditor=str(self.kreditor.id))
        kk = Konto.objects.get(kontonummer=self.kreditor_nr, wirtschaftsjahr=self.wj2025)
        treffer = Buchung.objects.filter(soll_konto=kk) | Buchung.objects.filter(haben_konto=kk)
        self.assertEqual(treffer.count(), 1)
        self.assertEqual(treffer.first().betrag, Decimal('250.00'))

    # -- Abgrenzungen --------------------------------------------------------

    def test_ohne_kreditor_bleibt_alles_unveraendert(self):
        aufwand = Konto.objects.create(
            wirtschaftsjahr=self.wj2025, kontonummer='50100', kontoname='Hausmeister')
        resp = self._post(
            soll_konto=str(aufwand.id), haben_konto=str(self.bank2025.id))
        self.assertEqual(resp.status_code, 201, resp.content)
        b = Buchung.objects.get(pk=resp.data['id'])
        self.assertEqual(b.soll_konto, aufwand)
        self.assertEqual(b.haben_konto, self.bank2025)
        self.assertFalse(Konto.objects.filter(kontonummer=self.kreditor_nr).exists())

    def test_beide_konten_gesetzt_werden_nicht_ueberschrieben(self):
        """Rechnungslogik/E-Banking kontieren selbst — nicht anfassen."""
        schwebe = Konto.objects.create(
            wirtschaftsjahr=self.wj2025, kontonummer='15900',
            kontoname='Schwebende Eingangsrechnungen')
        kk = Konto.objects.create(
            wirtschaftsjahr=self.wj2025, kontonummer=self.kreditor_nr,
            kontoname='Kreditor alt')
        resp = self._post(
            soll_konto=str(schwebe.id), haben_konto=str(kk.id),
            kreditor=str(self.kreditor.id))
        self.assertEqual(resp.status_code, 201, resp.content)
        b = Buchung.objects.get(pk=resp.data['id'])
        self.assertEqual(b.soll_konto, schwebe)
        self.assertEqual(b.haben_konto, kk)

    def test_personenkontobuchung_bleibt_unberuehrt(self):
        """Bei Personenkonten ist der Kreditor nur ein Vermerk."""
        from apps.personen.models import Person, EigentumsVerhaeltnis
        from apps.objekte.models import Einheit
        person = Person.objects.create(
            person_typ='100', vorname='Test', nachname='Eigentuemer')
        einheit = Einheit.objects.create(
            objekt=self.objekt, einheit_nr='1', einheit_typ='Wohnung', lage='EG links')
        ev = EigentumsVerhaeltnis.objects.create(
            einheit=einheit, person=person, beginn=date(2020, 1, 1))
        # Personenkonto entsteht per post_save-Signal auf EigentumsVerhaeltnis
        pk = Personenkonto.objects.get(vertrag=ev)
        resp = self._post(
            soll_konto=str(self.bank2025.id),
            personenkonto=str(pk.id),
            kreditor=str(self.kreditor.id),
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        b = Buchung.objects.get(pk=resp.data['id'])
        self.assertIsNone(b.haben_konto, 'Personenkonto-Bein wurde ueberschrieben')
        self.assertEqual(b.personenkonto_id, pk.id)

    def test_ohne_jedes_sachkonto_wird_nichts_geraten(self):
        resp = self._post(kreditor=str(self.kreditor.id))
        self.assertEqual(resp.status_code, 201, resp.content)
        b = Buchung.objects.get(pk=resp.data['id'])
        self.assertIsNone(b.soll_konto)
        self.assertIsNone(b.haben_konto)

    def test_kreditor_ohne_nummer_liefert_400(self):
        """
        Kreditor.save() vergibt eine fehlende Nummer selbst nach — ein
        nummernloser Kreditor kann nur per UPDATE entstehen (z.B. Altimport).
        Dann muss die Buchung mit 400 abgelehnt werden, nicht mit 500.
        """
        Kreditor.objects.filter(pk=self.kreditor.pk).update(kreditorennummer='')
        resp = self._post(
            haben_konto=str(self.bank2025.id), kreditor=str(self.kreditor.id))
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn('kreditor', resp.data)

    # -- Aktualisieren eines Entwurfs ----------------------------------------

    def test_patch_kontiert_die_kreditorseite_nach(self):
        resp = self._post(
            haben_konto=str(self.bank2025.id), kreditor=str(self.kreditor.id))
        buchung_id = resp.data['id']
        # Betrag korrigieren — die Kontierung muss erhalten bleiben
        resp = self.client.patch(
            f'{BASE}{buchung_id}/', {'betrag': '300.00'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        b = Buchung.objects.get(pk=buchung_id)
        self.assertEqual(b.betrag, Decimal('300.00'))
        self.assertEqual(b.soll_konto.kontonummer, self.kreditor_nr)

    def test_patch_dreht_die_seite_mit(self):
        """Aus Zahlungsausgang wird Zahlungseingang — Kreditor wechselt die Seite."""
        resp = self._post(
            haben_konto=str(self.bank2025.id), kreditor=str(self.kreditor.id))
        buchung_id = resp.data['id']
        resp = self.client.patch(f'{BASE}{buchung_id}/', {
            'soll_konto': str(self.bank2025.id),
            'haben_konto': None,
        }, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        b = Buchung.objects.get(pk=buchung_id)
        self.assertEqual(b.soll_konto, self.bank2025)
        self.assertEqual(b.haben_konto.kontonummer, self.kreditor_nr)
