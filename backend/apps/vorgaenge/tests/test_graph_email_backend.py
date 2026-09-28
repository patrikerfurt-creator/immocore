"""Tests für das Microsoft-Graph-E-Mail-Backend (config.email_backends).

Sämtliche Graph-/MSAL-Aufrufe sind gemockt – in den Tests geht nie eine
echte Mail raus und es wird kein Token bei Microsoft geholt.
"""
import base64
from unittest.mock import MagicMock, patch

from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.test import TestCase, override_settings

from config.email_backends import GraphEmailBackend, GraphVersandError

GRAPH_SETTINGS = dict(
    MS_GRAPH_TENANT_ID='tenant-123',
    MS_GRAPH_CLIENT_ID='client-123',
    MS_GRAPH_CLIENT_SECRET='geheim',
    MS_GRAPH_SENDER='info@demme-immobilien.de',
    EMAIL_BACKEND='config.email_backends.GraphEmailBackend',
)


def _mock_msal():
    """Patch-Objekt für msal.ConfidentialClientApplication mit Fake-Token."""
    app = MagicMock()
    app.acquire_token_for_client.return_value = {'access_token': 'TOKEN-XYZ'}
    return app


@override_settings(**GRAPH_SETTINGS)
class GraphEmailBackendVersandTest(TestCase):
    def test_html_mail_mit_anhang_wird_korrekt_gesendet(self):
        msg = EmailMultiAlternatives(
            'Ihr Vorgang', 'Text-Variante', 'info@demme-immobilien.de',
            ['kunde@example.de'], cc=['kollege@demme-immobilien.de'],
        )
        msg.attach_alternative('<p>Guten Tag</p>', 'text/html')
        msg.attach('protokoll.pdf', b'%PDF-1.7 inhalt', 'application/pdf')

        with patch('msal.ConfidentialClientApplication', return_value=_mock_msal()), \
                patch('config.email_backends.requests.post') as post:
            post.return_value = MagicMock(status_code=202, text='')
            gesendet = GraphEmailBackend().send_messages([msg])

        self.assertEqual(gesendet, 1)
        (url,), kwargs = post.call_args
        self.assertIn('/users/info@demme-immobilien.de/sendMail', url)
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer TOKEN-XYZ')

        message = kwargs['json']['message']
        self.assertEqual(message['subject'], 'Ihr Vorgang')
        self.assertEqual(message['body']['contentType'], 'HTML')
        self.assertEqual(message['body']['content'], '<p>Guten Tag</p>')
        self.assertEqual(message['toRecipients'],
                         [{'emailAddress': {'address': 'kunde@example.de'}}])
        self.assertEqual(message['ccRecipients'],
                         [{'emailAddress': {'address': 'kollege@demme-immobilien.de'}}])
        anhang = message['attachments'][0]
        self.assertEqual(anhang['name'], 'protokoll.pdf')
        self.assertEqual(anhang['contentType'], 'application/pdf')
        self.assertEqual(base64.b64decode(anhang['contentBytes']), b'%PDF-1.7 inhalt')
        self.assertTrue(kwargs['json']['saveToSentItems'])

    def test_reine_textmail_nutzt_contenttype_text(self):
        msg = EmailMessage('Betreff', 'Nur Text', 'info@demme-immobilien.de',
                           ['kunde@example.de'])
        with patch('msal.ConfidentialClientApplication', return_value=_mock_msal()), \
                patch('config.email_backends.requests.post') as post:
            post.return_value = MagicMock(status_code=202, text='')
            GraphEmailBackend().send_messages([msg])

        message = post.call_args.kwargs['json']['message']
        self.assertEqual(message['body']['contentType'], 'Text')
        self.assertEqual(message['body']['content'], 'Nur Text')
        self.assertNotIn('ccRecipients', message)
        self.assertNotIn('attachments', message)

    def test_name_in_absenderadresse_wird_auf_reine_adresse_reduziert(self):
        msg = EmailMessage('S', 'B', 'info@demme-immobilien.de',
                           ['Max Muster <max@example.de>'])
        with patch('msal.ConfidentialClientApplication', return_value=_mock_msal()), \
                patch('config.email_backends.requests.post') as post:
            post.return_value = MagicMock(status_code=202, text='')
            GraphEmailBackend().send_messages([msg])

        message = post.call_args.kwargs['json']['message']
        self.assertEqual(message['toRecipients'],
                         [{'emailAddress': {'address': 'max@example.de'}}])

    def test_http_fehler_wirft_bei_fail_silently_false(self):
        msg = EmailMessage('S', 'B', 'info@demme-immobilien.de', ['k@example.de'])
        with patch('msal.ConfidentialClientApplication', return_value=_mock_msal()), \
                patch('config.email_backends.requests.post') as post:
            post.return_value = MagicMock(status_code=403, text='Forbidden')
            with self.assertRaises(GraphVersandError):
                GraphEmailBackend(fail_silently=False).send_messages([msg])

    def test_http_fehler_wird_bei_fail_silently_true_geschluckt(self):
        msg = EmailMessage('S', 'B', 'info@demme-immobilien.de', ['k@example.de'])
        with patch('msal.ConfidentialClientApplication', return_value=_mock_msal()), \
                patch('config.email_backends.requests.post') as post:
            post.return_value = MagicMock(status_code=500, text='Boom')
            gesendet = GraphEmailBackend(fail_silently=True).send_messages([msg])
        self.assertEqual(gesendet, 0)


class GraphEmailBackendKonfigTest(TestCase):
    @override_settings(MS_GRAPH_TENANT_ID='', MS_GRAPH_CLIENT_ID='',
                       MS_GRAPH_CLIENT_SECRET='', MS_GRAPH_SENDER='')
    def test_ohne_credentials_wirft_improperly_configured(self):
        msg = EmailMessage('S', 'B', 'info@demme-immobilien.de', ['k@example.de'])
        with self.assertRaises(ImproperlyConfigured):
            GraphEmailBackend(fail_silently=False).send_messages([msg])

    @override_settings(MS_GRAPH_TENANT_ID='', MS_GRAPH_CLIENT_ID='',
                       MS_GRAPH_CLIENT_SECRET='', MS_GRAPH_SENDER='')
    def test_ohne_credentials_und_fail_silently_gibt_null(self):
        msg = EmailMessage('S', 'B', 'info@demme-immobilien.de', ['k@example.de'])
        self.assertEqual(
            GraphEmailBackend(fail_silently=True).send_messages([msg]), 0)

    @override_settings(**GRAPH_SETTINGS)
    def test_leere_nachrichtenliste_ruft_graph_nicht(self):
        with patch('config.email_backends.requests.post') as post:
            self.assertEqual(GraphEmailBackend().send_messages([]), 0)
            post.assert_not_called()
