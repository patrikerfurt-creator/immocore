"""Tests 1 und 2 (Spec 11): Vorlagen-Auflösung und Versions-Immutabilität."""
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.test import TestCase

from apps.korrespondenz.models import Textbaustein, Vorlage, VorlagenVersion
from apps.korrespondenz.services import vorlage_service
from apps.objekte.models import Objekt

User = get_user_model()


def _objekt(nr):
    return Objekt.objects.create(
        objektnummer=nr, objekt_typ='WEG', bezeichnung=f'WEG {nr}', strasse='Str 1',
        plz='12345', ort='Ort', verwaltung_seit=date(2020, 1, 1),
    )


def _vorlage(code='mahnung_stufe_1', objekt=None, aktiv=True):
    return Vorlage.objects.create(
        code=code, bezeichnung=f'{code} {objekt}', anlass='mahnung_stufe_1',
        objekt=objekt, aktiv=aktiv,
    )


def _freigeber():
    user = User.objects.create_user('freigeber', password='x')
    user.user_permissions.add(Permission.objects.get(codename='vorlage_freigeben'))
    return User.objects.get(pk=user.pk)  # Permission-Cache leeren


class AufloesenTest(TestCase):
    """Test 1: objektspezifisch vor global; inaktive werden ignoriert."""

    def setUp(self):
        self.objekt = _objekt('A1')
        self.anderes = _objekt('A2')
        self.global_ = _vorlage()

    def test_objektspezifisch_vor_global(self):
        spezifisch = _vorlage(objekt=self.objekt)
        self.assertEqual(vorlage_service.aufloesen('mahnung_stufe_1', self.objekt), spezifisch)

    def test_global_fuer_objekt_ohne_eigene_vorlage(self):
        _vorlage(objekt=self.objekt)
        self.assertEqual(vorlage_service.aufloesen('mahnung_stufe_1', self.anderes), self.global_)

    def test_ohne_objekt_nur_global(self):
        _vorlage(objekt=self.objekt)
        self.assertEqual(vorlage_service.aufloesen('mahnung_stufe_1', None), self.global_)

    def test_inaktive_objektvorlage_wird_ignoriert(self):
        _vorlage(objekt=self.objekt, aktiv=False)
        self.assertEqual(vorlage_service.aufloesen('mahnung_stufe_1', self.objekt), self.global_)

    def test_inaktive_globale_vorlage_wird_ignoriert(self):
        self.global_.aktiv = False
        self.global_.save()
        with self.assertRaises(vorlage_service.VorlageNichtGefunden):
            vorlage_service.aufloesen('mahnung_stufe_1', self.objekt)

    def test_unbekannter_code(self):
        with self.assertRaises(vorlage_service.VorlageNichtGefunden):
            vorlage_service.aufloesen('gibt_es_nicht', None)


class VersionImmutabilitaetTest(TestCase):
    """Test 2: freigegebene Version unveränderlich; Bearbeiten erzeugt neue Version."""

    def setUp(self):
        self.vorlage = _vorlage()
        self.version = VorlagenVersion.objects.create(
            vorlage=self.vorlage, version=1, betreff='Alt', inhalt=[{'typ': 'text', 'inhalt': 'a'}],
        )
        self.user = _freigeber()
        vorlage_service.freigeben(self.version, self.user)
        self.version.refresh_from_db()

    def test_freigabe_setzt_status_und_aktive_version(self):
        self.vorlage.refresh_from_db()
        self.assertEqual(self.version.status, 'freigegeben')
        self.assertEqual(self.vorlage.aktive_version_id, self.version.pk)
        self.assertEqual(self.version.freigegeben_von, self.user)
        self.assertIsNotNone(self.version.freigegeben_am)

    def test_freigegebene_version_kann_nicht_aktualisiert_werden(self):
        with self.assertRaises(vorlage_service.VersionGesperrt):
            vorlage_service.aktualisiere_entwurf(self.version, {'betreff': 'Neu'})
        self.version.refresh_from_db()
        self.assertEqual(self.version.betreff, 'Alt')

    def test_bearbeiten_erzeugt_neue_version_und_laesst_alte_unberuehrt(self):
        neu = vorlage_service.bearbeiten(self.version, {'betreff': 'Neu'}, user=self.user)
        self.assertNotEqual(neu.pk, self.version.pk)
        self.assertEqual((neu.version, neu.status, neu.betreff), (2, 'entwurf', 'Neu'))
        self.assertEqual(neu.inhalt, self.version.inhalt)
        self.version.refresh_from_db()
        self.assertEqual((self.version.status, self.version.betreff), ('freigegeben', 'Alt'))

    def test_neue_version_ist_tiefe_kopie(self):
        neu = vorlage_service.bearbeiten(self.version, {}, user=self.user)
        neu.inhalt[0]['inhalt'] = 'geändert'
        self.assertEqual(self.version.inhalt[0]['inhalt'], 'a')

    def test_entwurf_wird_in_place_bearbeitet(self):
        entwurf = vorlage_service.bearbeiten(self.version, {}, user=self.user)
        gleich = vorlage_service.bearbeiten(entwurf, {'betreff': 'Entwurf 2'}, user=self.user)
        self.assertEqual(gleich.pk, entwurf.pk)
        self.assertEqual(VorlagenVersion.objects.filter(vorlage=self.vorlage).count(), 2)

    def test_freigabe_loest_vorgaenger_ab(self):
        neu = vorlage_service.bearbeiten(self.version, {'betreff': 'Neu'}, user=self.user)
        vorlage_service.freigeben(neu, self.user)
        self.version.refresh_from_db()
        self.vorlage.refresh_from_db()
        self.assertEqual(self.version.status, 'abgeloest')
        self.assertEqual(self.vorlage.aktive_version_id, neu.pk)
        with self.assertRaises(vorlage_service.VersionGesperrt):
            vorlage_service.aktualisiere_entwurf(self.version, {'betreff': 'x'})

    def test_unbekanntes_feld_wird_abgelehnt(self):
        with self.assertRaises(ValueError):
            vorlage_service.bearbeiten(self.version, {'status': 'entwurf'}, user=self.user)

    def test_freigabe_ohne_permission(self):
        entwurf = vorlage_service.bearbeiten(self.version, {}, user=self.user)
        ohne = User.objects.create_user('ohne', password='x')
        with self.assertRaises(PermissionDenied):
            vorlage_service.freigeben(entwurf, ohne)

    def test_freigegebene_version_nicht_erneut_freigebbar(self):
        with self.assertRaises(vorlage_service.VersionGesperrt):
            vorlage_service.freigeben(self.version, self.user)


class BausteineTest(TestCase):
    def test_objektbaustein_hat_vorrang(self):
        objekt = _objekt('B1')
        Textbaustein.objects.create(code='gruss', bezeichnung='g', inhalt='global')
        Textbaustein.objects.create(code='gruss', bezeichnung='g', inhalt='objekt', objekt=objekt)
        bloecke = [{'typ': 'baustein', 'code': 'gruss'}, {'typ': 'text', 'inhalt': 'x'}]
        self.assertEqual(vorlage_service.lade_bausteine(bloecke, objekt), {'gruss': 'objekt'})
        self.assertEqual(vorlage_service.lade_bausteine(bloecke, None), {'gruss': 'global'})
