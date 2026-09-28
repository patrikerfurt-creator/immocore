"""E-Mail-Versand über die Microsoft-Graph-API (app-only / Client Credentials).

Hintergrund: Microsoft 365 hat die klassische SMTP-Anmeldung mit
Benutzer + Passwort (Basic Auth) weitgehend abgeschaltet und verlangt
OAuth2. Djangos eingebautes SMTP-Backend kann kein OAuth2. Dieses Backend
holt sich per MSAL ein App-Token (Client-Credentials-Flow, kein Benutzer
nötig) und verschickt die Mail über ``POST /users/{sender}/sendMail``.

Weil es das normale ``BaseEmailBackend``-Interface implementiert, läuft der
gesamte bestehende Versandcode (Handwerkeraufträge, EV-Einladungen inkl.
PDF-Anhängen, alle ``send_mail``/``EmailMessage``-Aufrufe) unverändert –
es genügt, ``EMAIL_BACKEND`` in ``.env.prod`` auf diese Klasse zu stellen.

Aktivierung (erst wenn die Azure-App bereitsteht):
    EMAIL_BACKEND=config.email_backends.GraphEmailBackend
    MS_GRAPH_TENANT_ID=...
    MS_GRAPH_CLIENT_ID=...
    MS_GRAPH_CLIENT_SECRET=...
    MS_GRAPH_SENDER=info@demme-immobilien.de   # optional, Default = DEFAULT_FROM_EMAIL

Solange diese Werte fehlen, bleibt das Backend inaktiv: Ein aktiviertes
Backend ohne Credentials wirft (außer bei ``fail_silently``) einen klaren
Fehler statt still zu scheitern – dieselbe Schutzlogik wie
``handwerker.tasks._versand_konfiguriert``.
"""
from __future__ import annotations

import base64
from email.utils import parseaddr

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend

GRAPH_SENDMAIL_URL = "https://graph.microsoft.com/v1.0/users/{sender}/sendMail"
_TIMEOUT = 30


class GraphVersandError(Exception):
    """Fehler beim Token-Abruf oder beim sendMail-Aufruf gegen Graph."""


class GraphEmailBackend(BaseEmailBackend):
    """Versendet Django-``EmailMessage``-Objekte über Microsoft Graph."""

    def __init__(self, fail_silently: bool = False, **kwargs):
        super().__init__(fail_silently=fail_silently)
        self.tenant_id = getattr(settings, "MS_GRAPH_TENANT_ID", "") or ""
        self.client_id = getattr(settings, "MS_GRAPH_CLIENT_ID", "") or ""
        self.client_secret = getattr(settings, "MS_GRAPH_CLIENT_SECRET", "") or ""
        self.sender = (
            getattr(settings, "MS_GRAPH_SENDER", "")
            or getattr(settings, "DEFAULT_FROM_EMAIL", "")
            or ""
        )

    # -- Konfiguration ----------------------------------------------------
    def konfiguriert(self) -> bool:
        """True, wenn alle vier Pflichtwerte gesetzt sind."""
        return all([self.tenant_id, self.client_id, self.client_secret, self.sender])

    # -- Token ------------------------------------------------------------
    def _hole_token(self) -> str:
        from config.graph_auth import hole_app_token
        return hole_app_token(self.tenant_id, self.client_id, self.client_secret)

    # -- Versand ----------------------------------------------------------
    def send_messages(self, email_messages) -> int:
        if not email_messages:
            return 0
        if not self.konfiguriert():
            if self.fail_silently:
                return 0
            raise ImproperlyConfigured(
                "GraphEmailBackend ist als EMAIL_BACKEND gesetzt, aber "
                "MS_GRAPH_TENANT_ID / MS_GRAPH_CLIENT_ID / MS_GRAPH_CLIENT_SECRET "
                "fehlen. Kein Versand möglich."
            )
        try:
            token = self._hole_token()
        except Exception:
            if self.fail_silently:
                return 0
            raise
        gesendet = 0
        for message in email_messages:
            try:
                self._sende_eine(message, token)
            except Exception:
                if not self.fail_silently:
                    raise
                continue
            gesendet += 1
        return gesendet

    def _sende_eine(self, message, token: str) -> None:
        payload = self._baue_payload(message)
        resp = requests.post(
            GRAPH_SENDMAIL_URL.format(sender=self._postfach()),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=_TIMEOUT,
        )
        if resp.status_code >= 400:
            raise GraphVersandError(
                f"Graph sendMail fehlgeschlagen (HTTP {resp.status_code}): {resp.text[:500]}"
            )

    # -- Payload-Aufbau ---------------------------------------------------
    def _postfach(self) -> str:
        """Das Postfach, aus dem gesendet wird (immer das konfigurierte)."""
        return self.sender

    @staticmethod
    def _adresse(wert: str) -> str:
        """Reine E-Mail-Adresse aus ``"Name <a@b.de>"`` extrahieren."""
        return parseaddr(wert)[1] or wert

    @classmethod
    def _empfaenger(cls, adressen) -> list:
        return [
            {"emailAddress": {"address": cls._adresse(a)}}
            for a in (adressen or [])
            if a
        ]

    def _baue_payload(self, message) -> dict:
        # Body: HTML bevorzugen, wenn vorhanden – sonst Text.
        html = None
        if getattr(message, "content_subtype", "plain") == "html":
            html = message.body
        for inhalt, mimetype in getattr(message, "alternatives", []) or []:
            if mimetype == "text/html":
                html = inhalt
                break
        if html is not None:
            body = {"contentType": "HTML", "content": html}
        else:
            body = {"contentType": "Text", "content": message.body}

        msg = {
            "subject": message.subject or "",
            "body": body,
            "toRecipients": self._empfaenger(message.to),
        }
        if message.cc:
            msg["ccRecipients"] = self._empfaenger(message.cc)
        if message.bcc:
            msg["bccRecipients"] = self._empfaenger(message.bcc)
        if getattr(message, "reply_to", None):
            msg["replyTo"] = self._empfaenger(message.reply_to)

        anhaenge = self._anhaenge(message)
        if anhaenge:
            msg["attachments"] = anhaenge

        return {"message": msg, "saveToSentItems": True}

    @staticmethod
    def _anhaenge(message) -> list:
        result = []
        for anhang in getattr(message, "attachments", []) or []:
            if isinstance(anhang, tuple):
                filename, content, mimetype = anhang
            else:  # MIMEBase-Objekt
                filename = anhang.get_filename() or "anhang"
                content = anhang.get_payload(decode=True)
                mimetype = anhang.get_content_type()
            if isinstance(content, str):
                content = content.encode("utf-8")
            result.append(
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": filename,
                    "contentType": mimetype or "application/octet-stream",
                    "contentBytes": base64.b64encode(content).decode("ascii"),
                }
            )
        return result
