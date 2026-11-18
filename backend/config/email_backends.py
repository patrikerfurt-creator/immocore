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
import logging
import time
from datetime import datetime, timezone
from email.utils import parseaddr, parsedate_to_datetime

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

GRAPH_SENDMAIL_URL = "https://graph.microsoft.com/v1.0/users/{sender}/sendMail"
_TIMEOUT = 30

# Microsoft Graph drosselt app-weit (HTTP 429 ApplicationThrottled, u.a. das
# "IncomingBytes"-Limit, das base64-codierte PDF-Anhänge schnell reißen) und
# liefert bei Überlast zeitweise 503/504. In diesen Fällen soll NICHT hart
# geworfen, sondern – wie von Microsoft vorgesehen – die im ``Retry-After``-
# Header genannte Wartezeit abgewartet und erneut gesendet werden.
#
# Bewusst eng begrenzt: Der ``sofort=true``-Pfad versendet innerhalb eines
# Web-Requests, deshalb darf der Worst Case (``_MAX_RETRIES`` × ``_MAX_RETRY_
# WAIT``) den Gunicorn-Timeout nicht sprengen. Der Massenversand läuft ohnehin
# über Celery (kein Request-Timeout).
_RETRY_STATUS = frozenset({429, 503, 504})
_MAX_RETRIES = 3          # zusätzliche Versuche nach dem ersten
_MAX_RETRY_WAIT = 60      # Sekunden-Obergrenze je Wartepause
_DEFAULT_RETRY_WAIT = 20  # Fallback, falls kein brauchbarer Retry-After kommt


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
        url = GRAPH_SENDMAIL_URL.format(sender=self._postfach())
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        for versuch in range(_MAX_RETRIES + 1):
            resp = requests.post(url, headers=headers, json=payload, timeout=_TIMEOUT)
            if resp.status_code < 400:
                return
            drosselung = resp.status_code in _RETRY_STATUS
            if drosselung and versuch < _MAX_RETRIES:
                wartezeit = self._retry_after_sekunden(resp)
                logger.warning(
                    "Graph sendMail gedrosselt (HTTP %s), Versuch %s/%s — warte "
                    "%.0fs und sende erneut. %s",
                    resp.status_code, versuch + 1, _MAX_RETRIES,
                    wartezeit, resp.text[:200],
                )
                time.sleep(wartezeit)
                continue
            raise GraphVersandError(
                f"Graph sendMail fehlgeschlagen (HTTP {resp.status_code}): {resp.text[:500]}"
            )

    @staticmethod
    def _retry_after_sekunden(resp) -> float:
        """Wartezeit aus dem ``Retry-After``-Header (Sekunden oder HTTP-Datum).

        Fehlt der Header oder ist er unverständlich, greift ``_DEFAULT_RETRY_
        WAIT``. Das Ergebnis ist immer auf ``[0, _MAX_RETRY_WAIT]`` begrenzt,
        damit ein (fehlerhaftes oder bösartiges) Datum weit in der Zukunft den
        Request nicht blockiert.
        """
        kopf = getattr(resp, "headers", None)
        rohwert = kopf.get("Retry-After") if kopf else None
        if rohwert is None:
            return _DEFAULT_RETRY_WAIT
        text = str(rohwert).strip()
        if text.isdigit():
            wartezeit = float(text)
        else:
            try:
                ziel = parsedate_to_datetime(text)
            except (TypeError, ValueError):
                return _DEFAULT_RETRY_WAIT
            if ziel is None:
                return _DEFAULT_RETRY_WAIT
            if ziel.tzinfo is None:
                ziel = ziel.replace(tzinfo=timezone.utc)
            wartezeit = (ziel - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, min(wartezeit, float(_MAX_RETRY_WAIT)))

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
