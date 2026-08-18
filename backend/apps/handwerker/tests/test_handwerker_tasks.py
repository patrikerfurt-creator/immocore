"""
Tests für ``apps.handwerker.tasks`` (Phase B, Orchestrator-Vorgabe Schritt 3/5).

E-Mail-Versand IMMER über das ``locmem``-Backend — niemals echter SMTP-Versand.

Deckt ab:
  - versende_auftragsmail: genau eine Mail, Empfänger = Kreditor-E-Mail,
    Betreff enthält die Auftragsnummer, Body enthält beide Token-Links mit
    FRONTEND_BASE_URL und den Verbindlichkeitshinweis; Status wechselt auf
    'versendet' und versendet_am ist gesetzt
  - Versandfehler (gemockt): Ereignis 'versand_fehlgeschlagen', Status bleibt
    'entwurf', Task wirft nicht durch
  - Ladefehler (z.B. ProgrammingError nach Migration, Worker noch nicht neu
    gestartet — siehe Modul-Docstring in tasks.py): Task wirft nicht durch,
    Ereignis 'versand_fehlgeschlagen' wird per Zweitversuch (ohne
    select_related) protokolliert; scheitert auch der Zweitversuch, wird nur
    geloggt
  - benachrichtige_intern: Ladefehler wirft nicht durch
  - pruefe_abgelaufene_auftraege: abgelaufener (unverbrauchter) Token ->
    'abgelaufen' + Systemereignis; gültiger Token bleibt unverändert;
    verbrauchter Token führt NICHT zu 'abgelaufen'
"""
from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.db.utils import ProgrammingError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.handwerker.models import AuftragsbestaetigungsToken, Handwerkerauftrag
from apps.handwerker.tasks import (
    benachrichtige_intern,
    pruefe_abgelaufene_auftraege,
    versende_auftragsmail,
)
from apps.objekte.models import Objekt
from apps.rechnungen.models import Kreditor

User = get_user_model()


def _objekt(nr="H900"):
    return Objekt.objects.create(
        bezeichnung="Test-WEG Task", objektnummer=nr, objekt_typ="weg",
        strasse="Teststraße 1", plz="12345", ort="Teststadt",
        verwaltung_seit=date(2020, 1, 1), bundesland="HE",
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
        self.token = AuftragsbestaetigungsToken.objects.create(auftrag=self.auftrag)

    def test_versendet_genau_eine_mail_an_kreditor(self):
        versende_auftragsmail(str(self.auftrag.id))

        self.assertEqual(len(mail.outbox), 1)
        gesendete_mail = mail.outbox[0]
        self.assertEqual(gesendete_mail.to, [self.kreditor.email])
        self.assertIn(self.auftrag.nummer, gesendete_mail.subject)

    def test_body_enthaelt_beide_token_links_und_verbindlichkeitshinweis(self):
        versende_auftragsmail(str(self.auftrag.id))

        gesendete_mail = mail.outbox[0]
        text_body = gesendete_mail.body
        html_body = gesendete_mail.alternatives[0][0]

        erwarteter_accept_link = f"http://testserver.local/auftrag-bestaetigung/{self.token.accept_token}/"
        erwarteter_reject_link = f"http://testserver.local/auftrag-bestaetigung/{self.token.reject_token}/"

        self.assertIn(erwarteter_accept_link, text_body)
        self.assertIn(erwarteter_reject_link, text_body)
        self.assertIn(erwarteter_accept_link, html_body)
        self.assertIn(erwarteter_reject_link, html_body)
        self.assertIn("verbindliche Auftragsannahme", text_body)
        self.assertIn("verbindliche Auftragsannahme", html_body)

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


class BenachrichtigeInternTest(TestCase):
    def setUp(self):
        self.user = _user()
        self.objekt = _objekt()
        self.kreditor = _kreditor()
        self.auftrag = Handwerkerauftrag.objects.create(
            objekt=self.objekt, kreditor=self.kreditor, titel="Wasserhahn undicht",
            erstellt_von=self.user, status="entwurf",
        )

    @patch.object(
        Handwerkerauftrag.objects, "select_related",
        side_effect=ProgrammingError("column rechnungen_kreditor.gewerk_id does not exist"),
    )
    def test_ladefehler_wirft_nicht_durch(self, mock_select_related):
        benachrichtige_intern(str(self.auftrag.id), "angenommen")  # darf nicht durchwerfen
        self.assertEqual(len(mail.outbox), 0)

    def test_unbekannter_auftrag_wirft_nicht(self):
        benachrichtige_intern(
            "00000000-0000-0000-0000-000000000000", "angenommen",
        )  # darf nicht durchwerfen
        self.assertEqual(len(mail.outbox), 0)


class PruefeAbgelaufeneAuftraegeTest(TestCase):
    def setUp(self):
        self.user = _user()
        self.objekt = _objekt()
        self.kreditor = _kreditor()

    def _auftrag_versendet(self, nr):
        return Handwerkerauftrag.objects.create(
            objekt=self.objekt, kreditor=self.kreditor, titel=f"Auftrag {nr}",
            erstellt_von=self.user, status="versendet",
        )

    def test_abgelaufener_unverbrauchter_token_fuehrt_zu_abgelaufen(self):
        auftrag = self._auftrag_versendet(1)
        token = AuftragsbestaetigungsToken.objects.create(auftrag=auftrag)
        token.gueltig_bis = timezone.now() - timedelta(days=1)
        token.save(update_fields=["gueltig_bis"])

        pruefe_abgelaufene_auftraege()

        auftrag.refresh_from_db()
        self.assertEqual(auftrag.status, "abgelaufen")
        self.assertEqual(auftrag.ereignisse.filter(typ="system_abgelaufen").count(), 1)

    def test_gueltiger_token_bleibt_unveraendert(self):
        auftrag = self._auftrag_versendet(2)
        AuftragsbestaetigungsToken.objects.create(auftrag=auftrag)  # gueltig_bis in der Zukunft

        pruefe_abgelaufene_auftraege()

        auftrag.refresh_from_db()
        self.assertEqual(auftrag.status, "versendet")

    def test_verbrauchter_token_fuehrt_nicht_zu_abgelaufen(self):
        auftrag = self._auftrag_versendet(3)
        token = AuftragsbestaetigungsToken.objects.create(auftrag=auftrag)
        token.gueltig_bis = timezone.now() - timedelta(days=1)
        token.verbraucht_am = timezone.now() - timedelta(hours=1)
        token.save(update_fields=["gueltig_bis", "verbraucht_am"])

        pruefe_abgelaufene_auftraege()

        auftrag.refresh_from_db()
        self.assertEqual(auftrag.status, "versendet")
