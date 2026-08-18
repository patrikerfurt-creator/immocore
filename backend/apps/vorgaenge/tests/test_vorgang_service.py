"""
Tests für ``apps.vorgaenge.services.vorgang_service`` (Phase B, Spec Vorgang &
DMS Kap. 1.3 / 4).

Deckt ab:
  - erstelle_vorgang: quelle-Default, prioritaet-Vorbelegung aus typ, kein
    VorgangEreignis bei Anlage
  - wechsle_status: ALLE erlaubten Übergänge (Status korrekt, VorgangEreignis
    erzeugt, geschlossen_am/-_von-Handling)
  - wechsle_status: mind. drei unerlaubte Übergänge -> Exception, kein
    DB-Zustand geändert
  - Kommentar-Historie bleibt bei Statuswechsel erhalten
  - Sonderfälle: Wiedervorlage ohne wiedervorlage_am, Verlassen von
    wiedervorlage nullt das Feld, Wiedereröffnung setzt geschlossen_am zurück,
    erstellt_von=None nur bei system_wiedervorlage_faellig
  - weise_zu / kommentiere
"""
import shutil
import tempfile
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from apps.objekte.models import Objekt
from apps.vorgaenge.models import Vorgang, VorgangEreignis, VorgangTyp
from apps.vorgaenge.services import vorgang_service

User = get_user_model()

_MEDIA_TMP = tempfile.mkdtemp(prefix="immocore_test_media_vorgaenge_service_")


def tearDownModule():
    shutil.rmtree(_MEDIA_TMP, ignore_errors=True)


def _objekt(nr="VS001"):
    return Objekt.objects.create(
        bezeichnung="Test-WEG Vorgang-Service", objektnummer=nr, objekt_typ="weg",
        ort="Teststadt", verwaltung_seit=date(2020, 1, 1),
    )


def _user(username="vorgang-service-tester"):
    return User.objects.create_user(username=username, password="x")


def _typ(code="maengelmeldung"):
    return VorgangTyp.objects.get(code=code)


class ErstelleVorgangTest(TestCase):
    def setUp(self):
        self.objekt = _objekt()
        self.user = _user()

    def test_quelle_default_manuell(self):
        vorgang = vorgang_service.erstelle_vorgang(
            typ=_typ(), betreff="Test", erstellt_von=self.user, objekt=self.objekt,
        )
        self.assertEqual(vorgang.quelle, "manuell")
        self.assertEqual(vorgang.status, "offen")

    def test_prioritaet_vorbelegung_aus_typ(self):
        typ = _typ("beschwerde")
        typ.standard_prioritaet = "hoch"
        typ.save(update_fields=["standard_prioritaet"])
        vorgang = vorgang_service.erstelle_vorgang(
            typ=typ, betreff="Test", erstellt_von=self.user, objekt=self.objekt,
        )
        self.assertEqual(vorgang.prioritaet, "hoch")

    def test_prioritaet_explizit_ueberschreibt_vorbelegung(self):
        vorgang = vorgang_service.erstelle_vorgang(
            typ=_typ(), betreff="Test", erstellt_von=self.user, objekt=self.objekt,
            prioritaet="niedrig",
        )
        self.assertEqual(vorgang.prioritaet, "niedrig")

    def test_anlage_erzeugt_kein_ereignis(self):
        vorgang = vorgang_service.erstelle_vorgang(
            typ=_typ(), betreff="Test", erstellt_von=self.user, objekt=self.objekt,
        )
        self.assertEqual(VorgangEreignis.objects.filter(vorgang=vorgang).count(), 0)

    def test_ohne_kontext_wirft_fehler(self):
        with self.assertRaises(ValidationError):
            vorgang_service.erstelle_vorgang(
                typ=_typ(), betreff="Test", erstellt_von=self.user,
            )


class WechsleStatusErlaubteUebergaengeTest(TestCase):
    def setUp(self):
        self.objekt = _objekt("VS010")
        self.user = _user("erlaubt-tester")

    def _vorgang(self, status="offen"):
        vorgang = vorgang_service.erstelle_vorgang(
            typ=_typ(), betreff="Test", erstellt_von=self.user, objekt=self.objekt,
        )
        if status != "offen":
            # Direktes Setzen für den Testaufbau (umgeht bewusst den Service) —
            # der eigentliche Übergang wird unten über wechsle_status geprüft.
            vorgang.status = status
            vorgang.save(update_fields=["status"])
        return vorgang

    def _pruefe_erfolgreichen_wechsel(self, vorgang, neuer_status, **kwargs):
        anzahl_vorher = VorgangEreignis.objects.filter(vorgang=vorgang).count()
        ergebnis = vorgang_service.wechsle_status(
            vorgang, neuer_status, erstellt_von=self.user, **kwargs
        )
        self.assertEqual(ergebnis.status, neuer_status)
        vorgang.refresh_from_db()
        self.assertEqual(vorgang.status, neuer_status)
        ereignisse = VorgangEreignis.objects.filter(vorgang=vorgang).order_by("erstellt_am")
        self.assertEqual(ereignisse.count(), anzahl_vorher + 1)
        letztes = ereignisse.last()
        self.assertEqual(letztes.typ, kwargs.get("ereignis_typ", "statuswechsel"))
        self.assertEqual(letztes.neuer_wert, neuer_status)
        return vorgang

    def test_offen_zu_in_bearbeitung(self):
        vorgang = self._vorgang("offen")
        self._pruefe_erfolgreichen_wechsel(vorgang, "in_bearbeitung")

    def test_statuswechsel_ist_eigentuemer_sichtbar(self):
        """Patrik-Entscheidung: ein regulärer Statuswechsel (ereignis_typ
        'statuswechsel') ist für den Eigentümer sichtbar."""
        vorgang = self._vorgang("offen")
        vorgang_service.wechsle_status(vorgang, "in_bearbeitung", erstellt_von=self.user)
        ereignis = VorgangEreignis.objects.get(vorgang=vorgang, typ="statuswechsel")
        self.assertFalse(ereignis.intern)

    def test_offen_zu_storniert(self):
        vorgang = self._vorgang("offen")
        self._pruefe_erfolgreichen_wechsel(vorgang, "storniert")
        vorgang.refresh_from_db()
        self.assertIsNotNone(vorgang.geschlossen_am)
        self.assertEqual(vorgang.geschlossen_von, self.user)

    def test_in_bearbeitung_zu_wartet_extern(self):
        vorgang = self._vorgang("in_bearbeitung")
        self._pruefe_erfolgreichen_wechsel(vorgang, "wartet_extern")

    def test_in_bearbeitung_zu_wiedervorlage(self):
        vorgang = self._vorgang("in_bearbeitung")
        morgen = date.today() + timedelta(days=1)
        self._pruefe_erfolgreichen_wechsel(vorgang, "wiedervorlage", wiedervorlage_am=morgen)
        vorgang.refresh_from_db()
        self.assertEqual(vorgang.wiedervorlage_am, morgen)

    def test_in_bearbeitung_zu_erledigt(self):
        vorgang = self._vorgang("in_bearbeitung")
        self._pruefe_erfolgreichen_wechsel(vorgang, "erledigt")
        vorgang.refresh_from_db()
        self.assertIsNotNone(vorgang.geschlossen_am)
        self.assertEqual(vorgang.geschlossen_von, self.user)

    def test_in_bearbeitung_zu_storniert(self):
        vorgang = self._vorgang("in_bearbeitung")
        self._pruefe_erfolgreichen_wechsel(vorgang, "storniert")

    def test_wartet_extern_zu_in_bearbeitung(self):
        vorgang = self._vorgang("wartet_extern")
        self._pruefe_erfolgreichen_wechsel(vorgang, "in_bearbeitung")

    def test_wartet_extern_zu_erledigt(self):
        vorgang = self._vorgang("wartet_extern")
        self._pruefe_erfolgreichen_wechsel(vorgang, "erledigt")

    def test_wartet_extern_zu_storniert(self):
        vorgang = self._vorgang("wartet_extern")
        self._pruefe_erfolgreichen_wechsel(vorgang, "storniert")

    def test_wiedervorlage_zu_in_bearbeitung(self):
        gestern = date.today() - timedelta(days=1)
        vorgang = self._vorgang("wiedervorlage")
        vorgang.wiedervorlage_am = gestern
        vorgang.save(update_fields=["wiedervorlage_am"])
        self._pruefe_erfolgreichen_wechsel(vorgang, "in_bearbeitung")
        vorgang.refresh_from_db()
        self.assertIsNone(vorgang.wiedervorlage_am)

    def test_wiedervorlage_zu_storniert(self):
        gestern = date.today() - timedelta(days=1)
        vorgang = self._vorgang("wiedervorlage")
        vorgang.wiedervorlage_am = gestern
        vorgang.save(update_fields=["wiedervorlage_am"])
        self._pruefe_erfolgreichen_wechsel(vorgang, "storniert")
        vorgang.refresh_from_db()
        self.assertIsNone(vorgang.wiedervorlage_am)

    def test_erledigt_zu_in_bearbeitung_wiedereroeffnung(self):
        vorgang = self._vorgang("in_bearbeitung")
        vorgang_service.wechsle_status(vorgang, "erledigt", erstellt_von=self.user)
        vorgang.refresh_from_db()
        self.assertIsNotNone(vorgang.geschlossen_am)
        self.assertIsNotNone(vorgang.geschlossen_von)

        self._pruefe_erfolgreichen_wechsel(vorgang, "in_bearbeitung")
        vorgang.refresh_from_db()
        self.assertIsNone(vorgang.geschlossen_am)
        self.assertIsNone(vorgang.geschlossen_von)


class WechsleStatusUnerlaubteUebergaengeTest(TestCase):
    def setUp(self):
        self.objekt = _objekt("VS020")
        self.user = _user("unerlaubt-tester")

    def _vorgang(self, status):
        vorgang = vorgang_service.erstelle_vorgang(
            typ=_typ(), betreff="Test", erstellt_von=self.user, objekt=self.objekt,
        )
        if status != "offen":
            vorgang.status = status
            vorgang.save(update_fields=["status"])
        return vorgang

    def _pruefe_abgewiesen(self, vorgang, neuer_status):
        alter_status = vorgang.status
        anzahl_vorher = VorgangEreignis.objects.filter(vorgang=vorgang).count()
        with self.assertRaises(ValidationError):
            vorgang_service.wechsle_status(vorgang, neuer_status, erstellt_von=self.user)
        vorgang.refresh_from_db()
        self.assertEqual(vorgang.status, alter_status)
        self.assertEqual(VorgangEreignis.objects.filter(vorgang=vorgang).count(), anzahl_vorher)

    def test_storniert_zu_in_bearbeitung_wird_abgewiesen(self):
        vorgang = self._vorgang("storniert")
        self._pruefe_abgewiesen(vorgang, "in_bearbeitung")

    def test_offen_zu_erledigt_wird_abgewiesen(self):
        vorgang = self._vorgang("offen")
        self._pruefe_abgewiesen(vorgang, "erledigt")

    def test_erledigt_zu_wartet_extern_wird_abgewiesen(self):
        vorgang = self._vorgang("erledigt")
        self._pruefe_abgewiesen(vorgang, "wartet_extern")


class WechsleStatusSonderfaelleTest(TestCase):
    def setUp(self):
        self.objekt = _objekt("VS030")
        self.user = _user("sonderfall-tester")

    def _vorgang(self, status="offen"):
        vorgang = vorgang_service.erstelle_vorgang(
            typ=_typ(), betreff="Test", erstellt_von=self.user, objekt=self.objekt,
        )
        if status != "offen":
            vorgang.status = status
            vorgang.save(update_fields=["status"])
        return vorgang

    def test_wechsel_nach_wiedervorlage_ohne_datum_wirft_fehler(self):
        vorgang = self._vorgang("in_bearbeitung")
        with self.assertRaises(ValidationError):
            vorgang_service.wechsle_status(vorgang, "wiedervorlage", erstellt_von=self.user)
        vorgang.refresh_from_db()
        self.assertEqual(vorgang.status, "in_bearbeitung")

    def test_erstellt_von_none_bei_normalem_typ_wirft_fehler(self):
        vorgang = self._vorgang("offen")
        with self.assertRaises(ValidationError):
            vorgang_service.wechsle_status(vorgang, "in_bearbeitung", erstellt_von=None)

    def test_erstellt_von_none_bei_system_wiedervorlage_faellig_ist_ok(self):
        gestern = date.today() - timedelta(days=1)
        vorgang = self._vorgang("wiedervorlage")
        vorgang.wiedervorlage_am = gestern
        vorgang.save(update_fields=["wiedervorlage_am"])

        vorgang_service.wechsle_status(
            vorgang, "in_bearbeitung", erstellt_von=None,
            ereignis_typ="system_wiedervorlage_faellig",
        )
        vorgang.refresh_from_db()
        self.assertEqual(vorgang.status, "in_bearbeitung")
        ereignis = VorgangEreignis.objects.get(vorgang=vorgang, typ="system_wiedervorlage_faellig")
        self.assertIsNone(ereignis.erstellt_von)
        self.assertTrue(ereignis.intern)


class KommentarHistorieTest(TestCase):
    def setUp(self):
        self.objekt = _objekt("VS040")
        self.user = _user("kommentar-historie-tester")
        self.vorgang = vorgang_service.erstelle_vorgang(
            typ=_typ(), betreff="Test", erstellt_von=self.user, objekt=self.objekt,
        )

    def test_kommentar_bleibt_bei_statuswechsel_erhalten(self):
        kommentar = vorgang_service.kommentiere(self.vorgang, "Erster Kommentar", self.user)
        vorgang_service.wechsle_status(self.vorgang, "in_bearbeitung", erstellt_von=self.user)

        ereignisse = list(VorgangEreignis.objects.filter(vorgang=self.vorgang).order_by("erstellt_am"))
        self.assertEqual(len(ereignisse), 2)
        self.assertEqual(ereignisse[0].typ, "kommentar")
        self.assertEqual(ereignisse[0].text, "Erster Kommentar")
        self.assertEqual(ereignisse[1].typ, "statuswechsel")

        kommentar.refresh_from_db()
        self.assertEqual(kommentar.text, "Erster Kommentar")


class KommentiereTest(TestCase):
    def setUp(self):
        self.objekt = _objekt("VS050")
        self.user = _user("kommentiere-tester")
        self.vorgang = vorgang_service.erstelle_vorgang(
            typ=_typ(), betreff="Test", erstellt_von=self.user, objekt=self.objekt,
        )

    def test_kommentar_wird_angelegt(self):
        ereignis = vorgang_service.kommentiere(self.vorgang, "Hallo", self.user)
        self.assertEqual(ereignis.typ, "kommentar")
        self.assertEqual(ereignis.text, "Hallo")
        self.assertEqual(ereignis.erstellt_von, self.user)

    def test_leerer_text_wirft_fehler(self):
        with self.assertRaises(ValidationError):
            vorgang_service.kommentiere(self.vorgang, "", self.user)

    def test_nur_whitespace_wirft_fehler(self):
        with self.assertRaises(ValidationError):
            vorgang_service.kommentiere(self.vorgang, "   ", self.user)

    def test_ohne_angabe_ist_intern(self):
        """Patrik-Entscheidung: Kommentare sind ohne explizites Anhaken
        standardmäßig intern."""
        ereignis = vorgang_service.kommentiere(self.vorgang, "Interner Hinweis", self.user)
        self.assertTrue(ereignis.intern)

    def test_explizit_intern_true(self):
        ereignis = vorgang_service.kommentiere(
            self.vorgang, "Interner Hinweis", self.user, intern=True,
        )
        self.assertTrue(ereignis.intern)

    def test_explizit_sichtbar_setzt_intern_false(self):
        ereignis = vorgang_service.kommentiere(
            self.vorgang, "Für den Eigentümer", self.user, intern=False,
        )
        self.assertFalse(ereignis.intern)


class WeiseZuTest(TestCase):
    def setUp(self):
        self.objekt = _objekt("VS060")
        self.user = _user("weise-zu-tester")
        self.anderer_user = _user("weise-zu-ziel")
        self.vorgang = vorgang_service.erstelle_vorgang(
            typ=_typ(), betreff="Test", erstellt_von=self.user, objekt=self.objekt,
        )

    def test_zuweisung_setzt_feld_und_erzeugt_ereignis(self):
        vorgang_service.weise_zu(self.vorgang, self.anderer_user, self.user)
        self.vorgang.refresh_from_db()
        self.assertEqual(self.vorgang.zugewiesen_an, self.anderer_user)

        ereignis = VorgangEreignis.objects.get(vorgang=self.vorgang, typ="zuweisung_geaendert")
        self.assertIsNone(ereignis.alter_wert)
        self.assertEqual(ereignis.neuer_wert, self.anderer_user.get_username())
        self.assertTrue(ereignis.intern)

    def test_zuweisung_entfernen_setzt_neuer_wert_none(self):
        vorgang_service.weise_zu(self.vorgang, self.anderer_user, self.user)
        vorgang_service.weise_zu(self.vorgang, None, self.user)
        self.vorgang.refresh_from_db()
        self.assertIsNone(self.vorgang.zugewiesen_an)

        ereignisse = VorgangEreignis.objects.filter(
            vorgang=self.vorgang, typ="zuweisung_geaendert",
        ).order_by("erstellt_am")
        self.assertEqual(ereignisse.last().alter_wert, self.anderer_user.get_username())
        self.assertIsNone(ereignisse.last().neuer_wert)


class SetzePortalSichtbarTest(TestCase):
    def setUp(self):
        self.objekt = _objekt("VS070")
        self.user = _user("portal-sichtbar-tester")
        self.vorgang = vorgang_service.erstelle_vorgang(
            typ=_typ(), betreff="Test", erstellt_von=self.user, objekt=self.objekt,
        )

    def test_default_ist_false(self):
        self.assertFalse(self.vorgang.portal_sichtbar)

    def test_setzen_auf_true(self):
        vorgang_service.setze_portal_sichtbar(self.vorgang, True)
        self.vorgang.refresh_from_db()
        self.assertTrue(self.vorgang.portal_sichtbar)

    def test_erzeugt_kein_vorgangereignis(self):
        vorgang_service.setze_portal_sichtbar(self.vorgang, True)
        self.assertEqual(VorgangEreignis.objects.filter(vorgang=self.vorgang).count(), 0)


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class PortalAnsichtTest(TestCase):
    """Deckt ``vorgang_service.portal_ansicht`` ab — den Lesepfad für die
    Eigentümer-Sicht (Mitarbeiter-Vorschau, kein öffentlicher Endpunkt)."""

    def setUp(self):
        self.objekt = _objekt("VS080")
        self.user = _user("portal-ansicht-tester")
        self.anderer_user = _user("portal-ansicht-zuweisung-ziel")
        self.vorgang = vorgang_service.erstelle_vorgang(
            typ=_typ(), betreff="Wasserschaden Keller",
            beschreibung="Rohrbruch im Keller, Wasser tritt aus.",
            erstellt_von=self.user, objekt=self.objekt,
        )

    def test_ohne_portal_sichtbar_liefert_nichts_inhaltliches(self):
        self.assertFalse(self.vorgang.portal_sichtbar)
        ergebnis = vorgang_service.portal_ansicht(self.vorgang)
        self.assertEqual(ergebnis, {'sichtbar': False})

    def test_mit_portal_sichtbar_liefert_vorgangsdaten(self):
        vorgang_service.setze_portal_sichtbar(self.vorgang, True)
        ergebnis = vorgang_service.portal_ansicht(self.vorgang)
        self.assertTrue(ergebnis['sichtbar'])
        self.assertEqual(ergebnis['nummer'], self.vorgang.nummer)
        self.assertEqual(ergebnis['betreff'], "Wasserschaden Keller")
        self.assertEqual(ergebnis['status'], 'offen')
        self.assertEqual(ergebnis['objekt_bezeichnung'], self.objekt.bezeichnung)

    def test_enthaelt_freigegebene_ereignisse_nicht_interne(self):
        vorgang_service.setze_portal_sichtbar(self.vorgang, True)
        vorgang_service.kommentiere(self.vorgang, "Interner Vermerk", self.user, intern=True)
        vorgang_service.kommentiere(self.vorgang, "Wir kümmern uns darum.", self.user, intern=False)
        vorgang_service.wechsle_status(self.vorgang, "in_bearbeitung", erstellt_von=self.user)
        vorgang_service.weise_zu(self.vorgang, self.anderer_user, self.user)

        ergebnis = vorgang_service.portal_ansicht(self.vorgang)
        typen = [e['typ'] for e in ergebnis['ereignisse']]

        self.assertIn('kommentar', typen)
        self.assertIn('statuswechsel', typen)
        self.assertNotIn('zuweisung_geaendert', typen)

        texte = [e['text'] for e in ergebnis['ereignisse']]
        self.assertIn("Wir kümmern uns darum.", texte)
        self.assertNotIn("Interner Vermerk", texte)

    def test_enthaelt_keine_dokument_id_keinen_link_kein_zugewiesen_an(self):
        """🔒 Absicherung gegen versehentliche Offenlegung: weder Dokument-ID/
        -Link noch der Name des zugewiesenen Mitarbeiters dürfen in der
        serialisierten Portal-Ansicht (als String) auftauchen."""
        from apps.vorgaenge.services import dokument_service

        vorgang_service.setze_portal_sichtbar(self.vorgang, True)
        vorgang_service.weise_zu(self.vorgang, self.anderer_user, self.user)
        ergebnis_upload = dokument_service.lade_dokument_hoch(
            b"Inhalt", "gutachten.pdf", self.user, vorgang=self.vorgang,
        )

        ergebnis = vorgang_service.portal_ansicht(self.vorgang)
        ergebnis_text = repr(ergebnis)

        self.assertNotIn(str(ergebnis_upload.dokument.id), ergebnis_text)
        self.assertNotIn(self.anderer_user.get_username(), ergebnis_text)
        self.assertIn("gutachten.pdf", ergebnis_text)

    def test_kommentar_ohne_sichtbarkeit_wird_nicht_ausgeliefert(self):
        vorgang_service.setze_portal_sichtbar(self.vorgang, True)
        vorgang_service.kommentiere(self.vorgang, "Nur intern", self.user)
        ergebnis = vorgang_service.portal_ansicht(self.vorgang)
        self.assertEqual(ergebnis['ereignisse'], [])
