"""Tests für den getrennten Portal-Versandweg (SMTP, Absender noreply@immospace.cloud).

Portal-Einladungen laufen bewusst NICHT über das globale Backend (info@/Graph),
sondern über einen eigenen SMTP-Weg aus den EMAIL_*-Variablen.
"""
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings

from apps.portal.services import mail_service


class PortalAbsenderTest(TestCase):
    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        EMAIL_HOST='',
        PORTAL_FROM_EMAIL='noreply@immospace.cloud',
    )
    def test_absender_ist_portal_from_email(self):
        mail.outbox = []
        with patch.object(mail_service, 'render_to_string', return_value='Body'):
            mail_service._sende('Betreff', 'portal_magic_link', 'kunde@example.de', {})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, 'noreply@immospace.cloud')
        self.assertEqual(mail.outbox[0].to, ['kunde@example.de'])


class PortalConnectionTest(TestCase):
    @override_settings(
        EMAIL_HOST='smtp.example.de', EMAIL_PORT=2525,
        EMAIL_HOST_USER='noreply@immospace.cloud', EMAIL_HOST_PASSWORD='pw',
        EMAIL_USE_TLS=True,
    )
    def test_mit_host_baut_eigene_smtp_verbindung(self):
        conn = mail_service._portal_connection()
        self.assertEqual(conn.host, 'smtp.example.de')
        self.assertEqual(conn.port, 2525)
        self.assertEqual(conn.username, 'noreply@immospace.cloud')
        self.assertTrue(conn.use_tls)

    @override_settings(EMAIL_HOST='')
    def test_ohne_host_faellt_auf_globales_backend_zurueck(self):
        self.assertIsNone(mail_service._portal_connection())

    @override_settings(EMAIL_HOST='smtp.example.de')
    def test_versand_konfiguriert_bei_gesetztem_host(self):
        self.assertTrue(mail_service.versand_konfiguriert())

    @override_settings(EMAIL_HOST='',
                       EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend')
    def test_console_backend_ohne_host_gilt_als_nicht_versandfaehig(self):
        self.assertFalse(mail_service.versand_konfiguriert())
