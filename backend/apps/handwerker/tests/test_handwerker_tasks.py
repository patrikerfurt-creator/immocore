"""
Tests für ``apps.handwerker.tasks`` (Phase B, Orchestrator-Vorgabe Schritt 3/5).

E-Mail-Versand IMMER über das ``locmem``-Backend — niemals echter SMTP-Versand.

Deckt ab:
  - versende_auftragsmail: genau eine Mail, Empfänger = Kreditor-E-Mail,
    Betreff enthält die Auftragsnummer, Body enthält "im Auftrag der
    {Objekt}", die Lieferadresse (Eingang bzw. Objektadresse), die Bitte um
    Eingangsbestätigung, den Rechnungsrücklauf inkl. Lohnkostenanteil und KEINE
    Annehmen-/Ablehnen-Links; Status wechselt auf 'versendet' und
    versendet_am ist gesetzt
  - Versandfehler (gemockt): Ereignis 'versand_fehlgeschlagen', Status bleibt
    'entwurf', Task wirft nicht durch
  - Ladefehler (z.B. ProgrammingError nach Migration, Worker noch nicht neu
    gestartet — siehe Modul-Docstring in tasks.py): Task wirft nicht durch,
    Ereignis 'versand_fehlgeschlagen' wird per Zweitversuch (ohne
    select_related) protokolliert; scheitert auch der Zweitversuch, wird nur
    geloggt
"""
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.db.utils import ProgrammingError
from django.test import TestCase, override_settings

from apps.handwerker.models import Handwerkerauftrag
from apps.handwerker.tasks import versende_auftragsmail
from apps.objekte.models import Eingang, Einheit, Objekt
from apps.rechnungen.models import Kreditor

User = get_user_model()


def _objekt(nr="H900"):
    return Objekt.objects.create(
        bezeichnung="Test-WEG Task", objektnummer=nr, objekt_typ="weg",
        strasse="Teststraße 1", plz="12345", ort="Teststadt",
        verwaltung_seit=date(2020, 1, 1), bundesland="HE",
        # Für Versand-Tests freigeschaltet; das Objekt-Gate (Default False)
        # wird gezielt in VersendeAuftragsmailObjektGateTest geprüft.
        mailversand_aktiv=True,
    )


def _kreditor():
    return Kreditor.objects.create(
        name="Meister Sanitär GmbH", ist_handwerker=True, email="meister@example.de",
    )


def _user():
    return User.objects.create_user(username="task-tester", password="x")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
                    FRONTEND_BASE_URL="http://testserver.local")
class VersendeAuftragsmailTest(TestCase):
    def setUp(self):
        self.user = _user()
        self.objekt = _objekt()
        self.kreditor = _kreditor()
        self.auftrag = Handwerkerauftrag.objects.create(
            objekt=self.objekt, kreditor=self.kreditor, titel="Wasserhahn undicht",
            erstellt_von=self.user, status="entwurf",
        )

    def test_versendet_genau_eine_mail_an_kreditor(self):
        versende_auftragsmail(str(self.auftrag.id))

        self.assertEqual(len(mail.outbox), 1)
        gesendete_mail = mail.outbox[0]
        self.assertEqual(gesendete_mail.to, [self.kreditor.email])
        self.assertIn(self.auftrag.nummer, gesendete_mail.subject)

    def test_body_enthaelt_neue_formulierungen_und_keine_bestaetigungslinks(self):
        versende_auftragsmail(str(self.auftrag.id))

        gesendete_mail = mail.outbox[0]
        text_body = gesendete_mail.body
        html_body = gesendete_mail.alternatives[0][0]

        self.assertIn(f"im Auftrag der {self.objekt.bezeichnung} übersenden", text_body)
        self.assertIn(f"im Auftrag der <strong>{self.objekt.bezeichnung}</strong>", html_body)
        for body in (text_body, html_body):
            self.assertIn("im Auftrag der", body)
            self.assertNotIn("Demme Immobilien Verwaltung GmbH</strong>", body)
            self.assertNotIn("Handwerkerauftrag", body)
            self.assertIn("den Eingang der Mail", body)
            self.assertIn("ob Sie den", body)
            self.assertIn("Lohnkostenanteil (brutto)", body)
            self.assertIn(self.auftrag.nummer, body)
            # Annehmen/Ablehnen-Flow ist entfernt.
            self.assertNotIn("annehmen", body.lower())
            self.assertNotIn("ablehnen", body.lower())
            self.assertNotIn("auftrag-bestaetigung", body)
            self.assertNotIn("verbindliche Auftragsannahme", body)

    def test_adresse_ist_objektadresse_wenn_kein_eingang_existiert(self):
        versende_auftragsmail(str(self.auftrag.id))

        text_body = mail.outbox[0].body
        self.assertIn("Adresse: Teststraße 1, 12345 Teststadt", text_body)

    def test_adresse_ist_eingang_wenn_vorhanden(self):
        Eingang.objects.create(
            objekt=self.objekt, bezeichnung="Haus A", strasse="Eingangsweg 7",
            plz="54321", ort="Eingangsstadt",
        )

        versende_auftragsmail(str(self.auftrag.id))

        text_body = mail.outbox[0].body
        html_body = mail.outbox[0].alternatives[0][0]
        self.assertIn("Adresse: Eingangsweg 7, 54321 Eingangsstadt", text_body)
        self.assertIn("Eingangsweg 7, 54321 Eingangsstadt", html_body)
        self.assertNotIn("Teststraße 1", text_body)

    def test_adresse_ist_eingang_der_einheit_des_vorgangs(self):
        from apps.vorgaenge.models import Vorgang, VorgangTyp

        Eingang.objects.create(
            objekt=self.objekt, bezeichnung="A erster", strasse="Erste Str. 1",
            plz="11111", ort="Erstort",
        )
        eingang_b = Eingang.objects.create(
            objekt=self.objekt, bezeichnung="B zweiter", strasse="Zweite Str. 2",
            plz="22222", ort="Zweitort",
        )
        einheit = Einheit.objects.create(
            objekt=self.objekt, eingang=eingang_b, einheit_nr="1", einheit_typ="Wohnung",
            lage="EG links",
        )
        vorgang = Vorgang.objects.create(
            typ=VorgangTyp.objects.get(code="maengelmeldung"), betreff="Mangel",
            erstellt_von=self.user, objekt=self.objekt, einheit=einheit,
        )
        self.auftrag.vorgang = vorgang
        self.auftrag.save(update_fields=["vorgang"])

        versende_auftragsmail(str(self.auftrag.id))

        self.assertIn("Adresse: Zweite Str. 2, 22222 Zweitort", mail.outbox[0].body)

    def test_status_wechselt_auf_versendet(self):
        versende_auftragsmail(str(self.auftrag.id))

        self.auftrag.refresh_from_db()
        self.assertEqual(self.auftrag.status, "versendet")
        self.assertIsNotNone(self.auftrag.versendet_am)

    @patch("django.core.mail.EmailMultiAlternatives.send", side_effect=RuntimeError("SMTP down"))
    def test_versandfehler_protokolliert_ereignis_status_bleibt_entwurf(self, mock_send):
        versende_auftragsmail(str(self.auftrag.id))  # darf nicht durchwerfen

        self.auftrag.refresh_from_db()
        self.assertEqual(self.auftrag.status, "entwurf")
        self.assertEqual(len(mail.outbox), 0)

        fehler_ereignisse = self.auftrag.ereignisse.filter(typ="versand_fehlgeschlagen")
        self.assertEqual(fehler_ereignisse.count(), 1)
        self.assertIn("SMTP down", fehler_ereignisse.first().text)

    def test_unbekannter_auftrag_wirft_nicht(self):
        versende_auftragsmail("00000000-0000-0000-0000-000000000000")  # darf nicht werfen
        self.assertEqual(len(mail.outbox), 0)

    def test_versand_wird_verweigert_wenn_kreditor_nachtraeglich_ungueltig_wird(self):
        """(c) Korrektur aus der Phase-B-Abnahme (Orchestrator, Schritt 0):
        defensive Prüfung unmittelbar vor dem Versand."""
        self.kreditor.ist_handwerker = False
        self.kreditor.email = ""
        self.kreditor.save(update_fields=["ist_handwerker", "email"])

        versende_auftragsmail(str(self.auftrag.id))  # darf nicht werfen

        self.assertEqual(len(mail.outbox), 0)
        self.auftrag.refresh_from_db()
        self.assertEqual(self.auftrag.status, "entwurf")
        fehler_ereignisse = self.auftrag.ereignisse.filter(typ="versand_fehlgeschlagen")
        self.assertEqual(fehler_ereignisse.count(), 1)

    @patch(
        "apps.handwerker.tasks.render_to_string",
        side_effect=RuntimeError("Template kaputt"),
    )
    def test_renderfehler_protokolliert_ereignis_status_bleibt_entwurf(self, mock_render):
        """Bestätigt: derselbe try/except-Block wie beim Versandfehler-Test
        fängt auch Fehler beim RENDERN des Templates ab (kein doppelter Pfad,
        aber ein eigener Auslöser: render_to_string statt mail.send)."""
        versende_auftragsmail(str(self.auftrag.id))  # darf nicht durchwerfen

        self.auftrag.refresh_from_db()
        self.assertEqual(self.auftrag.status, "entwurf")
        self.assertEqual(len(mail.outbox), 0)

        fehler_ereignisse = self.auftrag.ereignisse.filter(typ="versand_fehlgeschlagen")
        self.assertEqual(fehler_ereignisse.count(), 1)
        self.assertIn("Template kaputt", fehler_ereignisse.first().text)

    @patch.object(
        Handwerkerauftrag.objects, "select_related",
        side_effect=ProgrammingError("column rechnungen_kreditor.gewerk_id does not exist"),
    )
    def test_ladefehler_beim_select_related_protokolliert_ereignis_ueber_zweitversuch(self, mock_select_related):
        """Realer Vorfall: select_related() greift nach einer Migration auf
        eine nicht mehr existierende Spalte zu (Worker mit veraltetem
        Schema-Wissen). Der Task darf nicht durchwerfen, und da der
        Zweitversuch OHNE select_related den Auftrag trotzdem laden kann,
        muss ein 'versand_fehlgeschlagen'-Ereignis geschrieben werden."""
        versende_auftragsmail(str(self.auftrag.id))  # darf nicht durchwerfen

        self.assertEqual(len(mail.outbox), 0)
        self.auftrag.refresh_from_db()
        self.assertEqual(self.auftrag.status, "entwurf")

        fehler_ereignisse = self.auftrag.ereignisse.filter(typ="versand_fehlgeschlagen")
        self.assertEqual(fehler_ereignisse.count(), 1)
        self.assertIn("geladen werden", fehler_ereignisse.first().text)

    @patch.object(
        Handwerkerauftrag.objects, "select_related",
        side_effect=ProgrammingError("column rechnungen_kreditor.gewerk_id does not exist"),
    )
    def test_ladefehler_ohne_zweitversuchs_erfolg_wird_nur_geloggt(self, mock_select_related):
        """Schlägt auch der Zweitversuch (kein select_related) fehl — hier
        simuliert durch einen nicht existierenden Auftrag —, gibt es kein
        Objekt, an dem ein Ereignis hängen könnte: Task darf trotzdem nicht
        durchwerfen, es wird nur geloggt."""
        unbekannte_id = "00000000-0000-0000-0000-000000000000"

        versende_auftragsmail(unbekannte_id)  # darf nicht durchwerfen

        self.assertEqual(len(mail.outbox), 0)


@override_settings(FRONTEND_BASE_URL="http://testserver.local")
class VersendeAuftragsmailProduktionsSperreTest(TestCase):
    """Deckt die Produktions-Sperre gegen die stille Konsolen-Backend-Falle ab
    (siehe ``apps.handwerker.tasks._versand_konfiguriert``): auf einem
    Live-Server ohne SMTP-Konfiguration darf ``versende_auftragsmail`` weder
    tatsächlich versenden noch den Auftrag auf ``versendet`` setzen."""

    def setUp(self):
        self.user = _user()
        self.objekt = _objekt()
        self.kreditor = _kreditor()
        self.auftrag = Handwerkerauftrag.objects.create(
            objekt=self.objekt, kreditor=self.kreditor, titel="Wasserhahn undicht",
            erstellt_von=self.user, status="entwurf",
        )

    @override_settings(DEBUG=False, EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
    def test_konsolen_backend_in_produktion_versendet_nicht(self):
        versende_auftragsmail(str(self.auftrag.id))  # darf nicht durchwerfen

        self.assertEqual(len(mail.outbox), 0)
        self.auftrag.refresh_from_db()
        self.assertEqual(self.auftrag.status, "entwurf")

        fehler_ereignisse = self.auftrag.ereignisse.filter(typ="versand_fehlgeschlagen")
        self.assertEqual(fehler_ereignisse.count(), 1)
        self.assertIn("nicht konfiguriert", fehler_ereignisse.first().text)

    @override_settings(
        DEBUG=False, EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend", EMAIL_HOST="",
    )
    def test_smtp_backend_ohne_email_host_in_produktion_versendet_nicht(self):
        versende_auftragsmail(str(self.auftrag.id))  # darf nicht durchwerfen

        self.assertEqual(len(mail.outbox), 0)
        self.auftrag.refresh_from_db()
        self.assertEqual(self.auftrag.status, "entwurf")

        fehler_ereignisse = self.auftrag.ereignisse.filter(typ="versand_fehlgeschlagen")
        self.assertEqual(fehler_ereignisse.count(), 1)
        self.assertIn("nicht konfiguriert", fehler_ereignisse.first().text)

    @override_settings(
        DEBUG=False, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_HOST="mail.example.com",
    )
    def test_locmem_in_produktion_gilt_als_versandfaehig(self):
        """locmem muss weiterhin als versandfähig gelten, sonst würden alle
        bestehenden Tests, die den Versand über locmem prüfen, brechen."""
        versende_auftragsmail(str(self.auftrag.id))

        self.assertEqual(len(mail.outbox), 1)
        self.auftrag.refresh_from_db()
        self.assertEqual(self.auftrag.status, "versendet")

    @override_settings(
        DEBUG=False, EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST="mail.example.com",
    )
    @patch("django.core.mail.EmailMultiAlternatives.send")
    def test_smtp_backend_mit_email_host_in_produktion_versucht_versand(self, mock_send):
        versende_auftragsmail(str(self.auftrag.id))

        mock_send.assert_called_once()
        self.auftrag.refresh_from_db()
        self.assertEqual(self.auftrag.status, "versendet")

    @override_settings(DEBUG=True, EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
    def test_konsolen_backend_bei_debug_true_versendet_wie_bisher(self):
        """Lokale Entwicklung (DEBUG=True) bleibt unverändert: das
        Konsolen-Backend meldet Erfolg, der Auftrag wird 'versendet'."""
        versende_auftragsmail(str(self.auftrag.id))  # darf nicht durchwerfen

        self.auftrag.refresh_from_db()
        self.assertEqual(self.auftrag.status, "versendet")
        fehler_ereignisse = self.auftrag.ereignisse.filter(typ="versand_fehlgeschlagen")
        self.assertEqual(fehler_ereignisse.count(), 0)


class VersendeAuftragsmailObjektGateTest(TestCase):
    """Objekt-Gate (Objekt.mailversand_aktiv, Default False): ohne Freischaltung
    geht KEINE Auftragsmail raus – bewusst auch bei DEBUG/Konsolen-Backend."""

    def setUp(self):
        self.user = _user()
        self.kreditor = _kreditor()

    def _auftrag(self, *, freigeschaltet):
        objekt = _objekt()
        objekt.mailversand_aktiv = freigeschaltet
        objekt.save(update_fields=["mailversand_aktiv"])
        auftrag = Handwerkerauftrag.objects.create(
            objekt=objekt, kreditor=self.kreditor, titel="Test",
            erstellt_von=self.user, status="entwurf",
        )
        return auftrag

    def test_gesperrtes_objekt_versendet_nicht(self):
        auftrag = self._auftrag(freigeschaltet=False)
        versende_auftragsmail(str(auftrag.id))

        self.assertEqual(len(mail.outbox), 0)
        auftrag.refresh_from_db()
        self.assertEqual(auftrag.status, "entwurf")
        ereignisse = auftrag.ereignisse.filter(typ="versand_fehlgeschlagen")
        self.assertEqual(ereignisse.count(), 1)
        self.assertIn("freigeschaltet", ereignisse.first().text)

    def test_freigeschaltetes_objekt_versendet(self):
        auftrag = self._auftrag(freigeschaltet=True)
        versende_auftragsmail(str(auftrag.id))

        self.assertEqual(len(mail.outbox), 1)
        auftrag.refresh_from_db()
        self.assertEqual(auftrag.status, "versendet")
