"""Tests für den Graph-Mailabruf (apps.vorgaenge.services.graph_mail_abruf_service).

Token-Beschaffung und alle Graph-HTTP-Aufrufe sind gemockt; die Verarbeitung
selbst (``mail_import_service.verarbeite_datei``) wird gemockt, weil sie an
anderer Stelle getestet ist — hier geht es um die Abruflogik: Schalter,
Konfig-Gate, Zustand-Fortschreibung und das Herunterladen der MIME.
"""
import tempfile
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.vorgaenge.models import GraphMailAbruf
from apps.vorgaenge.services import graph_mail_abruf_service as svc

GRAPH_SETTINGS = dict(
    MS_GRAPH_TENANT_ID='tenant',
    MS_GRAPH_CLIENT_ID='client',
    MS_GRAPH_CLIENT_SECRET='geheim',
    MS_GRAPH_SENDER='info@demme-immobilien.de',
)


@override_settings(**GRAPH_SETTINGS)
class GraphMailAbrufTest(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._ordner_override = override_settings(MAIL_GRAPH_EINGANG=self._tmp.name)
        self._ordner_override.enable()
        self.addCleanup(self._ordner_override.disable)

    def _aktiv(self):
        z = GraphMailAbruf.load()
        z.aktiv = True
        z.save()
        return z

    def test_inaktiv_ruft_graph_nicht(self):
        # Default aktiv=False
        with patch.object(svc.requests, 'get') as get:
            ergebnis = svc.abrufen()
        self.assertEqual(ergebnis['status'], 'inaktiv')
        get.assert_not_called()

    @override_settings(MS_GRAPH_TENANT_ID='')
    def test_ohne_credentials_nicht_konfiguriert(self):
        self._aktiv()
        with patch.object(svc.requests, 'get') as get:
            ergebnis = svc.abrufen()
        self.assertEqual(ergebnis['status'], 'nicht_konfiguriert')
        get.assert_not_called()

    def test_holt_mime_und_verarbeitet_und_schreibt_zustand_fort(self):
        self._aktiv()
        liste = MagicMock(status_code=200)
        liste.json.return_value = {
            'value': [{'id': 'AAMkAAA=', 'receivedDateTime': '2026-09-28T10:00:00Z'}]
        }
        mime = MagicMock(status_code=200, content=b'From: kunde@example.de\r\nSubject: Test\r\n\r\nHallo')

        with patch.object(svc, 'hole_app_token', return_value='TOK'), \
                patch.object(svc.requests, 'get', side_effect=[liste, mime]) as get, \
                patch.object(svc.mail_import_service, 'verarbeite_datei') as verarbeite:
            ergebnis = svc.abrufen()

        self.assertEqual(ergebnis['status'], 'ok')
        self.assertEqual(ergebnis['geholt'], 1)
        # Erst die Liste, dann die MIME.
        self.assertEqual(get.call_count, 2)
        self.assertIn('/messages', get.call_args_list[0].args[0])
        self.assertTrue(get.call_args_list[1].args[0].endswith('/$value'))
        verarbeite.assert_called_once()
        # Zustand fortgeschrieben.
        z = GraphMailAbruf.load()
        self.assertIsNotNone(z.letzter_abruf)
        self.assertIsNotNone(z.zuletzt_gelaufen)
        self.assertIn('1 Mail', z.letzte_meldung)

    def test_filter_ab_letztem_abruf_wird_gesetzt(self):
        from django.utils import timezone
        z = self._aktiv()
        z.letzter_abruf = timezone.now()
        z.save()
        liste = MagicMock(status_code=200)
        liste.json.return_value = {'value': []}

        with patch.object(svc, 'hole_app_token', return_value='TOK'), \
                patch.object(svc.requests, 'get', return_value=liste) as get:
            svc.abrufen()

        params = get.call_args.kwargs['params']
        self.assertIn('$filter', params)
        self.assertIn('receivedDateTime ge', params['$filter'])
