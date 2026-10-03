"""
Tests für ``EVStimmgrundlage`` (Modell + ``stimmgrundlage_service``) und die
Vorbelegung von ``Tagesordnungspunkt.stimmgrundlage`` (Spec v1.1 Kap. 2 und 3).

Deckt ab:
  - erstelle_ev legt automatisch genau eine Standard-Stimmgrundlage an
    (abgeleitet aus stimmprinzip/stimm_verteilerschluessel)
  - CheckConstraint: entweder Verteilerschlüssel ODER echtes Kopfprinzip
  - Unique je EV: höchstens eine Standard-Grundlage, höchstens ein Kopfprinzip
  - Verbrauchsschlüssel sind keine zulässige Stimmgrundlage
  - stimmgrundlage_service.hinzufuegen: Validierung, Sperre nach Versand
  - TOP-Vorbelegung: erster TOP → Standard, weitere TOP → vorheriger TOP
  - Sperre der Stimmgrundlage nach Einladungsversand (wie andere TOP-Felder)
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.versammlung.models import EVStimmgrundlage
from apps.versammlung.services import (
    ev_service, stimmgrundlage_service, tagesordnung_service,
)
from apps.versammlung.tests import factories as f

VERSAMMLUNGEN = '/api/v1/versammlungen/'
TOPS = '/api/v1/tagesordnungspunkte/'


class ErstelleEvAutoStimmgrundlageTest(TestCase):
    def setUp(self):
        self.user = f.user()
        self.objekt = f.objekt()

    def test_kopfprinzip_ist_default(self):
        ev = ev_service.erstelle_ev(objekt=self.objekt, erstellt_von=self.user)
        grundlage = ev.stimmgrundlagen.get()
        self.assertTrue(grundlage.ist_kopfprinzip)
        self.assertTrue(grundlage.ist_standard)
        self.assertEqual(grundlage.bezeichnung_anzeige, 'Kopfprinzip')

    def test_verteilerschluessel_wird_uebernommen(self):
        eh, _ = f.eigentuemer(self.objekt, nr='001')
        vs = f.einheiten_schluessel(self.objekt, [eh])
        ev = ev_service.erstelle_ev(
            objekt=self.objekt, erstellt_von=self.user,
            stimmprinzip='verteilerschluessel', stimm_verteilerschluessel=vs,
            stimm_wirtschaftsjahr=0,
        )
        grundlage = ev.stimmgrundlagen.get(ist_standard=True)
        self.assertFalse(grundlage.ist_kopfprinzip)
        self.assertEqual(grundlage.verteilerschluessel_id, vs.id)
        self.assertEqual(grundlage.bezeichnung_anzeige, '030 Anzahl Einheiten Gesamt')

    def test_kopfprinzip_ist_bei_vs_ev_immer_zusaetzlich_verfuegbar(self):
        # Das echte Kopfprinzip muss als Gewichtungsoption bei JEDER EV
        # vorhanden sein — auch wenn die Standard-Grundlage ein
        # Verteilerschlüssel ist (jeder Eigentümer eine Stimme, § 25 Abs. 2 WEG).
        eh, _ = f.eigentuemer(self.objekt, nr='001')
        vs = f.einheiten_schluessel(self.objekt, [eh])
        ev = ev_service.erstelle_ev(
            objekt=self.objekt, erstellt_von=self.user,
            stimmprinzip='verteilerschluessel', stimm_verteilerschluessel=vs,
            stimm_wirtschaftsjahr=0,
        )
        self.assertEqual(ev.stimmgrundlagen.count(), 2)
        kopf = ev.stimmgrundlagen.get(ist_kopfprinzip=True)
        self.assertFalse(kopf.ist_standard)
        self.assertEqual(kopf.bezeichnung_anzeige, 'Kopfprinzip')


class EVStimmgrundlageConstraintTest(TestCase):
    def setUp(self):
        self.user = f.user()
        self.objekt = f.objekt()
        self.ev = ev_service.erstelle_ev(objekt=self.objekt, erstellt_von=self.user)

    def test_weder_vs_noch_kopf_wird_abgelehnt(self):
        grundlage = EVStimmgrundlage(
            ev=self.ev, verteilerschluessel=None, ist_kopfprinzip=False,
            bezeichnung_anzeige='Ungültig',
        )
        with self.assertRaises(ValidationError):
            grundlage.full_clean()

    def test_beides_wird_abgelehnt(self):
        eh, _ = f.eigentuemer(self.objekt, nr='001')
        vs = f.einheiten_schluessel(self.objekt, [eh])
        grundlage = EVStimmgrundlage(
            ev=self.ev, verteilerschluessel=vs, ist_kopfprinzip=True,
            bezeichnung_anzeige='Ungültig',
        )
        with self.assertRaises(ValidationError):
            grundlage.full_clean()

    def test_verbrauchsschluessel_wird_abgelehnt(self):
        eh, _ = f.eigentuemer(self.objekt, nr='001')
        vs = f.verteilerschluessel(
            self.objekt, {eh: '10'}, schluessel='140', vs_typ='verbrauch',
            bezeichnung='Heizkosten nach Verbrauch',
        )
        grundlage = EVStimmgrundlage(
            ev=self.ev, verteilerschluessel=vs, ist_kopfprinzip=False,
            bezeichnung_anzeige='140 Heizkosten nach Verbrauch',
        )
        with self.assertRaises(ValidationError) as ctx:
            grundlage.full_clean()
        self.assertIn('verteilerschluessel', ctx.exception.message_dict)

    def test_fremdes_objekt_wird_abgelehnt(self):
        fremdes = f.objekt(bezeichnung='Fremde WEG')
        fremde_einheit = f.einheit(fremdes, nr='001')
        fremder_vs = f.einheiten_schluessel(fremdes, [fremde_einheit])
        grundlage = EVStimmgrundlage(
            ev=self.ev, verteilerschluessel=fremder_vs, ist_kopfprinzip=False,
            bezeichnung_anzeige='Fremd',
        )
        with self.assertRaises(ValidationError):
            grundlage.full_clean()

    def test_nur_eine_standard_grundlage_je_ev(self):
        # self.ev hat aus erstelle_ev bereits eine Standard-Grundlage (Kopf).
        eh, _ = f.eigentuemer(self.objekt, nr='001')
        vs = f.einheiten_schluessel(self.objekt, [eh])
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                EVStimmgrundlage.objects.create(
                    ev=self.ev, verteilerschluessel=vs, ist_kopfprinzip=False,
                    ist_standard=True, bezeichnung_anzeige='030 Zweite Standard',
                )

    def test_nur_ein_kopfprinzip_je_ev(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                EVStimmgrundlage.objects.create(
                    ev=self.ev, verteilerschluessel=None, ist_kopfprinzip=True,
                    bezeichnung_anzeige='Kopfprinzip (zweite)',
                )


class StimmgrundlageServiceTest(TestCase):
    def setUp(self):
        self.user = f.user()
        self.objekt = f.objekt()
        self.ev = ev_service.erstelle_ev(objekt=self.objekt, erstellt_von=self.user)

    def test_hinzufuegen_weiterer_verteilerschluessel(self):
        eh, _ = f.eigentuemer(self.objekt, nr='001')
        vs = f.einheiten_schluessel(self.objekt, [eh])
        grundlage = stimmgrundlage_service.hinzufuegen(
            self.ev, verteilerschluessel=vs,
        )
        self.assertEqual(self.ev.stimmgrundlagen.count(), 2)
        self.assertFalse(grundlage.ist_standard)

    def test_hinzufuegen_als_neue_standard_grundlage(self):
        eh, _ = f.eigentuemer(self.objekt, nr='001')
        vs = f.einheiten_schluessel(self.objekt, [eh])
        alte_standard = self.ev.stimmgrundlagen.get(ist_standard=True)

        stimmgrundlage_service.hinzufuegen(
            self.ev, verteilerschluessel=vs, ist_standard=True,
        )

        alte_standard.refresh_from_db()
        self.assertFalse(alte_standard.ist_standard)
        self.assertTrue(self.ev.stimmgrundlagen.get(verteilerschluessel=vs).ist_standard)

    def test_weder_vs_noch_kopf_wird_abgelehnt(self):
        with self.assertRaises(ValidationError):
            stimmgrundlage_service.hinzufuegen(self.ev)

    def test_beides_wird_abgelehnt(self):
        eh, _ = f.eigentuemer(self.objekt, nr='001')
        vs = f.einheiten_schluessel(self.objekt, [eh])
        with self.assertRaises(ValidationError):
            stimmgrundlage_service.hinzufuegen(
                self.ev, verteilerschluessel=vs, ist_kopfprinzip=True,
            )

    def test_gesperrt_nach_einladungsversand(self):
        eh, _ = f.eigentuemer(self.objekt, nr='001')
        vs = f.einheiten_schluessel(self.objekt, [eh])
        ev_service.wechsle_status(self.ev, 'in_bearbeitung', self.user)
        ev_service.wechsle_status(self.ev, 'einladungen_versendet', self.user)
        with self.assertRaises(ValidationError):
            stimmgrundlage_service.hinzufuegen(self.ev, verteilerschluessel=vs)


class TopVorbelegungTest(TestCase):
    def setUp(self):
        self.user = f.user()
        self.objekt = f.objekt()
        self.ev = ev_service.erstelle_ev(objekt=self.objekt, erstellt_von=self.user)
        self.standard = self.ev.stimmgrundlagen.get(ist_standard=True)

    def _top(self, titel, **kwargs):
        return tagesordnung_service.top_anlegen(
            ev=self.ev, titel=titel, erstellt_von=self.user,
            beschlussvorlage='Es wird beschlossen.', **kwargs,
        )

    def test_erster_top_bekommt_standard_grundlage(self):
        top = self._top('Erster')
        self.assertEqual(top.stimmgrundlage_id, self.standard.id)

    def test_weiterer_top_erbt_vom_vorherigen(self):
        eh, _ = f.eigentuemer(self.objekt, nr='001')
        vs = f.einheiten_schluessel(self.objekt, [eh])
        andere_grundlage = stimmgrundlage_service.hinzufuegen(
            self.ev, verteilerschluessel=vs,
        )
        self._top('Erster', stimmgrundlage=andere_grundlage)
        zweiter = self._top('Zweiter')
        self.assertEqual(zweiter.stimmgrundlage_id, andere_grundlage.id)

    def test_explizite_grundlage_ueberschreibt_vorbelegung(self):
        eh, _ = f.eigentuemer(self.objekt, nr='001')
        vs = f.einheiten_schluessel(self.objekt, [eh])
        andere_grundlage = stimmgrundlage_service.hinzufuegen(
            self.ev, verteilerschluessel=vs,
        )
        top = self._top('Erster', stimmgrundlage=andere_grundlage)
        self.assertEqual(top.stimmgrundlage_id, andere_grundlage.id)

    def test_fremde_grundlage_wird_abgelehnt(self):
        andere_ev = ev_service.erstelle_ev(objekt=self.objekt, erstellt_von=self.user)
        fremde_grundlage = andere_ev.stimmgrundlagen.get()
        with self.assertRaises(ValidationError):
            self._top('Erster', stimmgrundlage=fremde_grundlage)

    def test_eingefuegter_top_erbt_von_seinem_vorgaenger(self):
        # "Erster" (Nr. 1) bekommt eine andere Grundlage als der Standard,
        # "Zweiter" (Nr. 2) explizit wieder den Standard — beide UNTER-
        # SCHIEDLICH, damit die Vererbung eindeutig geprüft werden kann.
        eh, _ = f.eigentuemer(self.objekt, nr='001')
        vs = f.einheiten_schluessel(self.objekt, [eh])
        andere_grundlage = stimmgrundlage_service.hinzufuegen(
            self.ev, verteilerschluessel=vs,
        )
        self._top('Erster', stimmgrundlage=andere_grundlage)
        self._top('Zweiter', stimmgrundlage=self.standard)

        # Eingefügt an Position 2 — liegt jetzt direkt HINTER "Erster"
        # (weiterhin Nr. 1) und VOR dem nach Nr. 3 gerückten "Zweiter".
        eingeschoben = self._top('Eingeschoben', nummer=2)
        self.assertEqual(eingeschoben.stimmgrundlage_id, andere_grundlage.id)

    def test_stimmgrundlage_ist_nach_versand_gesperrt(self):
        top = self._top('Erster')
        ev_service.wechsle_status(self.ev, 'in_bearbeitung', self.user)
        ev_service.wechsle_status(self.ev, 'einladungen_versendet', self.user)
        top.refresh_from_db()

        eh, _ = f.eigentuemer(self.objekt, nr='001')
        vs = f.einheiten_schluessel(self.objekt, [eh])
        andere_grundlage = EVStimmgrundlage.objects.create(
            ev=self.ev, verteilerschluessel=vs, ist_kopfprinzip=False,
            bezeichnung_anzeige='030 Anzahl Einheiten Gesamt',
        )
        with self.assertRaises(ValidationError) as ctx:
            tagesordnung_service.top_aktualisieren(
                top, self.user, stimmgrundlage=andere_grundlage,
            )
        self.assertIn('stimmgrundlage', str(ctx.exception))


class StimmgrundlageApiTest(APITestCase):
    def setUp(self):
        self.user = f.user()
        self.client.force_authenticate(self.user)
        self.objekt = f.objekt()
        self.ev = ev_service.erstelle_ev(objekt=self.objekt, erstellt_von=self.user)

    def test_liste_enthaelt_die_automatische_standard_grundlage(self):
        response = self.client.get(
            f'{VERSAMMLUNGEN}{self.ev.id}/stimmgrundlagen/',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['bezeichnung_anzeige'], 'Kopfprinzip')
        self.assertTrue(response.data[0]['ist_standard'])

    def test_hinzufuegen_ueber_api(self):
        eh, _ = f.eigentuemer(self.objekt, nr='001')
        vs = f.einheiten_schluessel(self.objekt, [eh])
        response = self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/stimmgrundlage-hinzufuegen/',
            {'verteilerschluessel': str(vs.id)}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(self.ev.stimmgrundlagen.count(), 2)

    def test_hinzufuegen_ohne_angabe_400(self):
        response = self.client.post(
            f'{VERSAMMLUNGEN}{self.ev.id}/stimmgrundlage-hinzufuegen/', {}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_top_zeigt_stimmgrundlage_verschachtelt(self):
        top = tagesordnung_service.top_anlegen(
            ev=self.ev, titel='TOP 1', erstellt_von=self.user,
            beschlussvorlage='Text.',
        )
        response = self.client.get(f'{TOPS}{top.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['stimmgrundlage']['bezeichnung'], 'Kopfprinzip')
