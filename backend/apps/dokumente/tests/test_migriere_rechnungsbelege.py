"""
Tests für den Management-Command migriere_rechnungsbelege (Phase C,
Spec Beleg↔Dokument-Kopplung).

Deckt ab:
  - Pre-Flight (doppelter pfad, fremde Wurzel, Zählerstand != 0)
  - Neuanlage: dry-run, Vollauf, Idempotenz bei Re-Run, fehlende Datei
  - --sperren: rückdatierte GoBD-Sperre, idempotent
  - --rueckabwicklung: entfernt nur ungesperrte migrierte Dokumente
  - beleg_service.dokument_pfad(): Auflösung media/rechnungen
"""
import shutil
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.buchhaltung.models import Buchung, ImportOrdnerEinstellung
from apps.dokumente.models import BelegnummerZaehler, Dokument
from apps.dokumente.services.beleg_service import dokument_pfad, rechnungen_root
from apps.objekte.models import Objekt
from apps.rechnungen.models import Rechnung, Verarbeitungslog

User = get_user_model()


def _objekt(nr="B900"):
    return Objekt.objects.create(
        bezeichnung="Test-WEG Migration", objektnummer=nr, objekt_typ="weg",
        ort="Teststadt", verwaltung_seit=date(2020, 1, 1),
    )


def _user(username="migrations-tester"):
    return User.objects.create_user(username=username, password="x")


def _superuser(username="admin-fallback"):
    return User.objects.create_superuser(username=username, email="admin@example.com", password="x")


def _pdf(pfad: Path, inhalt: bytes = b"%PDF-1.4 Testinhalt"):
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(inhalt)


def _rechnung(objekt, pfad="", dateiname="", sha256="", status="freigegeben", betrag="100.00"):
    return Rechnung.objects.create(
        objekt=objekt, pfad=pfad, dateiname=dateiname or (Path(pfad).name if pfad else ""),
        sha256_hash=sha256, status=status, betrag_brutto=Decimal(betrag),
    )


def _setze_erstellt_am(instanz, zeitpunkt):
    """Rückdatiert auto_now_add-Feld erstellt_am (nur per .update() möglich)."""
    type(instanz).objects.filter(pk=instanz.pk).update(erstellt_am=zeitpunkt)
    instanz.refresh_from_db()


class _RechnungenWurzelMixin:
    """Legt eine temporäre Rechnungen-Wurzel + ImportOrdnerEinstellung an."""

    def _setup_wurzel(self):
        self._tmp = tempfile.mkdtemp(prefix="immocore_test_rechnungen_")
        self.addCleanup(shutil.rmtree, self._tmp, ignore_errors=True)
        self.archiv_dir = Path(self._tmp) / "archiv"
        self.archiv_dir.mkdir(parents=True, exist_ok=True)
        ImportOrdnerEinstellung.objects.create(
            bereich="rechnungen",
            archiv_ordner=str(self.archiv_dir),
        )
        self.root = rechnungen_root()
        self.assertEqual(self.root, Path(self._tmp))


class PreflightTest(_RechnungenWurzelMixin, TestCase):
    def setUp(self):
        self._setup_wurzel()
        self.objekt = _objekt()

    def test_doppelter_pfad_bricht_ab(self):
        pfad = str(self.archiv_dir / "2026" / "08" / "doppelt.pdf")
        _pdf(Path(pfad))
        _rechnung(self.objekt, pfad=pfad)
        _rechnung(self.objekt, pfad=pfad)
        with self.assertRaises(CommandError):
            call_command("migriere_rechnungsbelege", dry_run=True)

    def test_fremde_wurzel_bricht_ab(self):
        _rechnung(self.objekt, pfad="/anderswo/rechnung.pdf")
        with self.assertRaises(CommandError):
            call_command("migriere_rechnungsbelege", dry_run=True)

    def test_zaehlerstand_ungleich_null_bricht_neuanlage_ab(self):
        BelegnummerZaehler.objects.create(pk=1, letzter_zaehler=5)
        with self.assertRaises(CommandError):
            call_command("migriere_rechnungsbelege", dry_run=True)

    def test_zaehlerstand_override_erlaubt_lauf(self):
        BelegnummerZaehler.objects.create(pk=1, letzter_zaehler=5)
        # Darf nicht abbrechen; keine Kandidaten vorhanden -> lauft einfach durch.
        call_command("migriere_rechnungsbelege", dry_run=True, erlaube_vorhandenen_zaehlerstand=True)

    def test_pfad_zu_lang_bricht_ab(self):
        # Rechnung.pfad ist selbst varchar(1000) — ein zu langer Wert lässt sich
        # über die ORM gar nicht erst einfügen. Simuliert historische Altdaten
        # (z. B. vor einer Spaltenverkürzung) über eine temporäre Spaltenweitung,
        # die mit dem Test-Rollback wieder verschwindet.
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE rechnungen_rechnung ALTER COLUMN pfad TYPE varchar(2000)")
        zu_lang = "/" + ("x" * 1200) + ".pdf"
        _rechnung(self.objekt, pfad=zu_lang, dateiname="lang.pdf")
        with self.assertRaises(CommandError):
            call_command("migriere_rechnungsbelege", dry_run=True)


class NeuanlageTest(_RechnungenWurzelMixin, TestCase):
    def setUp(self):
        self._setup_wurzel()
        self.objekt = _objekt()
        self.user = _user()

    def _rechnung_mit_datei(self, name, **kwargs):
        pfad = self.archiv_dir / "2026" / "08" / name
        _pdf(pfad)
        return _rechnung(self.objekt, pfad=str(pfad), **kwargs)

    def test_dry_run_legt_nichts_an(self):
        self._rechnung_mit_datei("re1.pdf")
        self._rechnung_mit_datei("re2.pdf")
        import io
        out = io.StringIO()
        call_command("migriere_rechnungsbelege", dry_run=True, user=self.user.username, stdout=out)
        self.assertEqual(Dokument.objects.count(), 0)
        self.assertIn("2 Dokument(e)", out.getvalue())

    def test_vollauf_legt_dokumente_an_und_koppelt(self):
        basis = timezone.now() - timedelta(days=3)
        r1 = self._rechnung_mit_datei("re1.pdf", sha256="a" * 64)
        _setze_erstellt_am(r1, basis)
        r2 = self._rechnung_mit_datei("re2.pdf")
        _setze_erstellt_am(r2, basis + timedelta(hours=1))
        r3 = self._rechnung_mit_datei("re3.pdf")
        _setze_erstellt_am(r3, basis + timedelta(hours=2))

        call_command("migriere_rechnungsbelege", user=self.user.username)

        r1.refresh_from_db(); r2.refresh_from_db(); r3.refresh_from_db()
        self.assertIsNotNone(r1.beleg_dokument_id)
        self.assertIsNotNone(r2.beleg_dokument_id)
        self.assertIsNotNone(r3.beleg_dokument_id)

        dok1 = r1.beleg_dokument
        self.assertEqual(dok1.ablage_wurzel, "rechnungen")
        self.assertTrue(dok1.datei.name.startswith("archiv/"))
        self.assertFalse(dok1.datei.name.startswith("/"))
        self.assertEqual(dok1.sha256, "a" * 64)
        self.assertEqual(dok1.abgelegt_am, r1.erstellt_am)
        self.assertEqual(dok1.hochgeladen_von_id, self.user.id)

        # Belegnummern fortlaufend in erstellt_am-Reihenfolge
        self.assertEqual(r1.beleg_dokument.beleg_nummer, "AA00000001")
        self.assertEqual(r2.beleg_dokument.beleg_nummer, "AA00000002")
        self.assertEqual(r3.beleg_dokument.beleg_nummer, "AA00000003")

        # Verarbeitungslog — status = Rechnungsstatus zum Migrationszeitpunkt (forensisch, D3-Mapping)
        log = Verarbeitungslog.objects.filter(rechnung=r1, aktion="Beleg-Dokument migriert").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.details, dok1.beleg_nummer)
        self.assertEqual(log.status, r1.status)

    def test_rerun_ist_idempotent(self):
        self._rechnung_mit_datei("re1.pdf")
        call_command("migriere_rechnungsbelege", user=self.user.username)
        self.assertEqual(Dokument.objects.count(), 1)
        # Zweiter Lauf: Zähler ist jetzt != 0 — Pre-Flight verlangt bewusst den
        # Override, damit ein Neuanlage-Lauf nicht versehentlich zweimal gegen
        # eine echte DB läuft.
        call_command(
            "migriere_rechnungsbelege", user=self.user.username,
            erlaube_vorhandenen_zaehlerstand=True,
        )
        self.assertEqual(Dokument.objects.count(), 1)

    def test_fehlende_datei_wird_uebersprungen(self):
        pfad = self.archiv_dir / "2026" / "08" / "fehlt.pdf"
        r = _rechnung(self.objekt, pfad=str(pfad))
        call_command("migriere_rechnungsbelege", user=self.user.username)
        r.refresh_from_db()
        self.assertIsNone(r.beleg_dokument_id)

    def test_fehlende_datei_mit_override_wird_angelegt(self):
        pfad = self.archiv_dir / "2026" / "08" / "fehlt.pdf"
        r = _rechnung(self.objekt, pfad=str(pfad))
        call_command("migriere_rechnungsbelege", user=self.user.username, erlaube_fehlende=True)
        r.refresh_from_db()
        self.assertIsNotNone(r.beleg_dokument_id)

    def test_kein_user_angegeben_faellt_auf_autopilot_zurueck(self):
        # 'immocore-autopilot' existiert immer (Datenmigration
        # buchhaltung/0025_autopilot_user.py) und hat Vorrang vor Superusern.
        self._rechnung_mit_datei("re1.pdf")
        call_command("migriere_rechnungsbelege")
        dok = Dokument.objects.first()
        self.assertEqual(dok.hochgeladen_von.username, "immocore-autopilot")

    def test_kein_user_und_kein_autopilot_faellt_auf_superuser_zurueck(self):
        User.objects.filter(username="immocore-autopilot").delete()
        superuser = _superuser()
        self._rechnung_mit_datei("re1.pdf")
        call_command("migriere_rechnungsbelege")
        dok = Dokument.objects.first()
        self.assertEqual(dok.hochgeladen_von_id, superuser.id)

    def test_limit_begrenzt_anzahl(self):
        self._rechnung_mit_datei("re1.pdf")
        self._rechnung_mit_datei("re2.pdf")
        call_command("migriere_rechnungsbelege", user=self.user.username, limit=1)
        self.assertEqual(Dokument.objects.count(), 1)


class SperrenTest(_RechnungenWurzelMixin, TestCase):
    def setUp(self):
        self._setup_wurzel()
        self.objekt = _objekt()
        self.user = _user()

    def _dok(self):
        return Dokument.objects.create(
            datei="archiv/2026/08/re.pdf", ablage_wurzel="rechnungen",
            dateiname="re.pdf", kategorie="Beleg", dokument_typ="beleg",
            verknuepfung_typ="Rechnung", objekt=self.objekt,
            hochgeladen_von=self.user, revisionssicher=False,
        )

    def _buchung(self, erstellt_am):
        b = Buchung.objects.create(
            objekt=self.objekt, betrag=Decimal("50.00"), buchungsdatum=date(2026, 1, 10),
        )
        Buchung.objects.filter(pk=b.pk).update(erstellt_am=erstellt_am)
        b.refresh_from_db()
        return b

    def test_sperrt_nur_qualifizierte_status(self):
        op_ts = timezone.now() - timedelta(days=10)
        buchung = self._buchung(op_ts)

        r_freigegeben = _rechnung(self.objekt, status="freigegeben")
        r_freigegeben.beleg_dokument = self._dok()
        r_freigegeben.op_buchung = buchung
        r_freigegeben.save(update_fields=["beleg_dokument", "op_buchung"])

        r_teilbezahlt = _rechnung(self.objekt, status="teilbezahlt")
        r_teilbezahlt.beleg_dokument = self._dok()
        r_teilbezahlt.save(update_fields=["beleg_dokument"])
        _setze_erstellt_am(r_teilbezahlt, timezone.now() - timedelta(days=5))

        r_in_pruefung = _rechnung(self.objekt, status="in_pruefung")
        r_in_pruefung.beleg_dokument = self._dok()
        r_in_pruefung.save(update_fields=["beleg_dokument"])

        call_command("migriere_rechnungsbelege", sperren=True)

        r_freigegeben.refresh_from_db()
        r_teilbezahlt.refresh_from_db()
        r_in_pruefung.refresh_from_db()

        self.assertTrue(r_freigegeben.beleg_dokument.revisionssicher)
        self.assertEqual(r_freigegeben.beleg_dokument.revisionssicher_seit, op_ts)

        self.assertTrue(r_teilbezahlt.beleg_dokument.revisionssicher)
        self.assertEqual(r_teilbezahlt.beleg_dokument.revisionssicher_seit, r_teilbezahlt.erstellt_am)

        self.assertFalse(r_in_pruefung.beleg_dokument.revisionssicher)

    def test_zweiter_lauf_sperrt_nichts_mehr(self):
        r = _rechnung(self.objekt, status="bezahlt")
        r.beleg_dokument = self._dok()
        r.save(update_fields=["beleg_dokument"])

        call_command("migriere_rechnungsbelege", sperren=True)
        import io
        out = io.StringIO()
        call_command("migriere_rechnungsbelege", sperren=True, stdout=out)
        self.assertIn("0 Beleg(e)", out.getvalue())


class RueckabwicklungTest(_RechnungenWurzelMixin, TestCase):
    def setUp(self):
        self._setup_wurzel()
        self.objekt = _objekt()
        self.user = _user()

    def _dok(self, revisionssicher=False):
        return Dokument.objects.create(
            datei="archiv/2026/08/re.pdf", ablage_wurzel="rechnungen",
            dateiname="re.pdf", kategorie="Beleg", dokument_typ="beleg",
            verknuepfung_typ="Rechnung", objekt=self.objekt,
            hochgeladen_von=self.user, revisionssicher=revisionssicher,
        )

    def test_entfernt_nur_ungesperrte_dokumente(self):
        BelegnummerZaehler.objects.create(pk=1, letzter_zaehler=3)

        dok_offen = self._dok(revisionssicher=False)
        r_offen = _rechnung(self.objekt, status="freigegeben")
        r_offen.beleg_dokument = dok_offen
        r_offen.save(update_fields=["beleg_dokument"])

        dok_gesperrt = self._dok(revisionssicher=True)
        r_gesperrt = _rechnung(self.objekt, status="bezahlt")
        r_gesperrt.beleg_dokument = dok_gesperrt
        r_gesperrt.save(update_fields=["beleg_dokument"])

        call_command("migriere_rechnungsbelege", rueckabwicklung=True)

        self.assertFalse(Dokument.objects.filter(pk=dok_offen.pk).exists())
        r_offen.refresh_from_db()
        self.assertIsNone(r_offen.beleg_dokument_id)

        self.assertTrue(Dokument.objects.filter(pk=dok_gesperrt.pk).exists())
        r_gesperrt.refresh_from_db()
        self.assertEqual(r_gesperrt.beleg_dokument_id, dok_gesperrt.id)

        self.assertEqual(BelegnummerZaehler.objects.get(pk=1).letzter_zaehler, 3)

    def test_dry_run_entfernt_nichts(self):
        dok_offen = self._dok(revisionssicher=False)
        r_offen = _rechnung(self.objekt, status="freigegeben")
        r_offen.beleg_dokument = dok_offen
        r_offen.save(update_fields=["beleg_dokument"])

        call_command("migriere_rechnungsbelege", rueckabwicklung=True, dry_run=True)
        self.assertTrue(Dokument.objects.filter(pk=dok_offen.pk).exists())


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="immocore_test_media_"))
class DokumentPfadTest(_RechnungenWurzelMixin, TestCase):
    def setUp(self):
        self._setup_wurzel()
        self.objekt = _objekt()
        self.user = _user()

    def test_media_wurzel(self):
        from django.conf import settings
        dok = Dokument.objects.create(
            datei="sub/testfile.pdf", ablage_wurzel="media",
            dateiname="testfile.pdf", kategorie="Beleg", dokument_typ="beleg",
            verknuepfung_typ="Rechnung", objekt=self.objekt, hochgeladen_von=self.user,
        )
        self.assertEqual(dokument_pfad(dok), Path(settings.MEDIA_ROOT) / "sub/testfile.pdf")

    def test_rechnungen_wurzel(self):
        dok = Dokument.objects.create(
            datei="archiv/2026/08/testfile.pdf", ablage_wurzel="rechnungen",
            dateiname="testfile.pdf", kategorie="Beleg", dokument_typ="beleg",
            verknuepfung_typ="Rechnung", objekt=self.objekt, hochgeladen_von=self.user,
        )
        self.assertEqual(dokument_pfad(dok), self.root / "archiv/2026/08/testfile.pdf")
