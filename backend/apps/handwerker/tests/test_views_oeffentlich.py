"""
API-Tests für die ÖFFENTLICHEN Auftragsbestätigungs-Endpunkte (Phase C,
Orchestrator-Vorgabe Schritt 6) — die ERSTEN öffentlichen Endpunkte des
Projekts, entsprechend hohe Sorgfalt bei den Tests.

``cache.clear()`` in jedem ``setUp()``: ``ScopedRateThrottle`` nutzt den
Django-Cache (hier echtes Redis, siehe ``config.settings.CACHES``) als
Zähler-Backend — der wird NICHT durch die Test-Transaktion zurückgerollt.
Ohne das Zurücksetzen würden wiederholte Testläufe innerhalb derselben
Stunde irgendwann am 30/hour-Limit scheitern.

Pflicht-Tests (🔒):
  - GET ändert nachweislich NICHTS (Status, verbraucht_am, Ereignisanzahl
    vor/nach GET identisch) — der wichtigste Test dieser Phase.
  - accept_token/reject_token tauchen in KEINER Antwort auf.
"""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.handwerker.models import AuftragsbestaetigungsToken, Handwerkerauftrag
from apps.objekte.models import Objekt
from apps.rechnungen.models import Kreditor

User = get_user_model()


def _objekt(nr='HWKOEF001'):
    return Objekt.objects.create(
        bezeichnung='Test-WEG Öffentliche API', objektnummer=nr, objekt_typ='weg',
        strasse='Handwerkerstraße 5', plz='54321', ort='Musterstadt',
        verwaltung_seit=date(2020, 1, 1), bundesland='HE',
    )


def _kreditor():
    return Kreditor.objects.create(
        name='Meister Sanitär GmbH', ist_handwerker=True, email='meister@example.de',
    )


class OeffentlicherAuftragGetTest(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='oeff-get-tester')
        self.objekt = _objekt()
        self.kreditor = _kreditor()
        self.auftrag = Handwerkerauftrag.objects.create(
            objekt=self.objekt, kreditor=self.kreditor, titel='Wasserschaden Keller',
            erstellt_von=self.user, status='versendet',
        )
        self.token = AuftragsbestaetigungsToken.objects.create(auftrag=self.auftrag)

    def _url(self, token):
        return f'/api/v1/oeffentlich/auftrag/{token}/'

    def test_ohne_login_erreichbar(self):
        response = self.client.get(self._url(self.token.accept_token))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_liefert_erwartete_felder_und_aktion_annehmen(self):
        response = self.client.get(self._url(self.token.accept_token))
        self.assertEqual(response.data['nummer'], self.auftrag.nummer)
        self.assertEqual(response.data['aktion'], 'annehmen')
        self.assertEqual(response.data['status'], 'versendet')
        self.assertFalse(response.data['bereits_verwendet'])
        self.assertFalse(response.data['abgelaufen'])
        self.assertEqual(response.data['objekt_bezeichnung'], self.objekt.bezeichnung)
        self.assertIn('Handwerkerstraße', response.data['objekt_adresse'])
        self.assertEqual(response.data['kreditor_name'], self.kreditor.name)

    def test_reject_token_liefert_aktion_ablehnen(self):
        response = self.client.get(self._url(self.token.reject_token))
        self.assertEqual(response.data['aktion'], 'ablehnen')

    def test_unbekannter_token_404(self):
        response = self.client.get(self._url('unbekannter-token-xyz'))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_abgelaufener_token_wird_im_get_als_abgelaufen_markiert_nicht_als_fehler(self):
        self.token.gueltig_bis = timezone.now() - timedelta(days=1)
        self.token.save(update_fields=['gueltig_bis'])
        response = self.client.get(self._url(self.token.accept_token))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['abgelaufen'])

    def test_get_ist_nebenwirkungsfrei(self):
        """🔒 Wichtigster Test dieser Phase: GET darf niemals etwas ändern —
        Mail-Scanner/Linkvorschauen rufen GET automatisch ab."""
        vor_status = self.auftrag.status
        vor_ereignisanzahl = self.auftrag.ereignisse.count()
        vor_verbraucht = self.token.verbraucht_am

        self.client.get(self._url(self.token.accept_token))
        self.client.get(self._url(self.token.accept_token))
        self.client.get(self._url(self.token.reject_token))

        self.auftrag.refresh_from_db()
        self.token.refresh_from_db()

        self.assertEqual(self.auftrag.status, vor_status)
        self.assertEqual(self.auftrag.ereignisse.count(), vor_ereignisanzahl)
        self.assertEqual(self.token.verbraucht_am, vor_verbraucht)

    def test_token_leak(self):
        """🔒 Pflicht-Test: weder accept_token noch reject_token dürfen im
        GET erscheinen."""
        response = self.client.get(self._url(self.token.accept_token))
        inhalt = str(response.content)
        self.assertNotIn(self.token.accept_token, inhalt)
        self.assertNotIn(self.token.reject_token, inhalt)


class OeffentlicherAuftragBestaetigenTest(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='oeff-post-tester')
        self.objekt = _objekt()
        self.kreditor = _kreditor()

    def _auftrag(self, auftrag_status='versendet'):
        auftrag = Handwerkerauftrag.objects.create(
            objekt=self.objekt, kreditor=self.kreditor, titel='Testauftrag',
            erstellt_von=self.user, status=auftrag_status,
        )
        token = AuftragsbestaetigungsToken.objects.create(auftrag=auftrag)
        return auftrag, token

    def _url(self, token):
        return f'/api/v1/oeffentlich/auftrag/{token}/bestaetigen/'

    def test_ohne_login_erreichbar(self):
        auftrag, token = self._auftrag()
        response = self.client.post(self._url(token.accept_token))
        self.assertNotIn(response.status_code, (401, 403))

    def test_annahme_erfolgreich(self):
        auftrag, token = self._auftrag()
        response = self.client.post(self._url(token.accept_token))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        auftrag.refresh_from_db()
        self.assertEqual(auftrag.status, 'angenommen')
        self.assertEqual(auftrag.ereignisse.count(), 1)
        self.assertEqual(response.data['nummer'], auftrag.nummer)
        self.assertEqual(response.data['aktion'], 'annehmen')

    def test_ablehnung_mit_grund_speichert_grund_und_schreibt_ereignis(self):
        auftrag, token = self._auftrag()
        response = self.client.post(self._url(token.reject_token), {'grund': 'Keine Zeit diese Woche.'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        auftrag.refresh_from_db()
        self.assertEqual(auftrag.status, 'abgelehnt')
        self.assertEqual(auftrag.ablehnung_grund, 'Keine Zeit diese Woche.')
        self.assertEqual(auftrag.ereignisse.count(), 1)

    def test_zweiter_post_gibt_409_mit_aktuellem_status(self):
        auftrag, token = self._auftrag()
        erste_antwort = self.client.post(self._url(token.accept_token))
        self.assertEqual(erste_antwort.status_code, status.HTTP_200_OK)

        zweite_antwort = self.client.post(self._url(token.accept_token))
        self.assertEqual(zweite_antwort.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(zweite_antwort.data['status'], 'angenommen')

    def test_abgelaufener_token_410(self):
        auftrag, token = self._auftrag()
        token.gueltig_bis = timezone.now() - timedelta(days=1)
        token.save(update_fields=['gueltig_bis'])
        response = self.client.post(self._url(token.accept_token))
        self.assertEqual(response.status_code, status.HTTP_410_GONE)
        auftrag.refresh_from_db()
        self.assertEqual(auftrag.status, 'versendet')

    def test_unbekannter_token_404(self):
        response = self.client.post(self._url('unbekannter-token-xyz'))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_ungueltiger_statusuebergang_409(self):
        # 'abgeschlossen' ist terminal — kein Übergang mehr erlaubt, auch
        # nicht per (an sich noch gültigem) Token.
        auftrag, token = self._auftrag(auftrag_status='abgeschlossen')
        response = self.client.post(self._url(token.accept_token))
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_antwort_enthaelt_auftragsnummer_nicht_uuid(self):
        auftrag, token = self._auftrag()
        response = self.client.post(self._url(token.accept_token))
        self.assertEqual(response.data['nummer'], auftrag.nummer)
        self.assertNotIn(str(auftrag.id), str(response.content))

    def test_antwort_enthaelt_niemals_den_anderen_token(self):
        auftrag, token = self._auftrag()
        response = self.client.post(self._url(token.accept_token))
        inhalt = str(response.content)
        self.assertNotIn(token.reject_token, inhalt)
        self.assertNotIn(token.accept_token, inhalt)
