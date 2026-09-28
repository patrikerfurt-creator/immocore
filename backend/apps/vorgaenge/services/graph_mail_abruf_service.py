"""Abruf des info@-Postfachs über Microsoft Graph (read-only, app-only).

Holt alle Mails seit dem letzten Abruf (``receivedDateTime``) als MIME
herunter, legt sie als ``.eml`` in einen eigenen Ordner und lässt die
bestehende Posteingang-Pipeline (``mail_import_service.verarbeite_datei``)
sie verarbeiten — inklusive KI-Klassifikation, automatischer Vorgangsanlage
und DMS-Ablage.

Das Postfach bleibt unangetastet: Es wird ausschließlich ``Mail.Read``
genutzt, nichts wird als gelesen markiert oder verschoben. Idempotenz kommt
aus zwei Quellen:

1. ``letzter_abruf`` (minus kleinem Sicherheitsfenster) grenzt die Menge ein,
2. die Message-ID-Deduplizierung in ``verarbeite_mail`` verhindert, dass eine
   im Überlappungsfenster erneut geholte Mail einen zweiten Vorgang erzeugt.

Weil das Postfach die Quelle bleibt und ``letzter_abruf`` erst nach einem Lauf
fortgeschrieben wird, ist der Abruf auch gegen Container-Abstürze robust: beim
nächsten Lauf wird schlicht ab demselben Zeitpunkt erneut geholt.
"""
import logging
import pathlib
from datetime import timedelta, timezone as dt_timezone
from urllib.parse import quote

import requests
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.vorgaenge.models import GraphMailAbruf
from apps.vorgaenge.services import mail_import_service
from config.graph_auth import hole_app_token

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_TIMEOUT = 30
_UEBERLAPP = timedelta(minutes=5)   # Sicherheitsfenster gegen verpasste Mails
_SEITE = 50


def graph_konfiguriert() -> bool:
    return bool(
        settings.MS_GRAPH_TENANT_ID and settings.MS_GRAPH_CLIENT_ID
        and settings.MS_GRAPH_CLIENT_SECRET and settings.MS_GRAPH_SENDER
    )


def _eingang_ordner() -> pathlib.Path:
    ordner = pathlib.Path(settings.MAIL_GRAPH_EINGANG)
    ordner.mkdir(parents=True, exist_ok=True)
    return ordner


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _hole_nachrichtenliste(token: str, seit) -> list:
    """Listet ``{id, receivedDateTime}`` seit ``seit`` (aufsteigend, paginiert)."""
    sender = quote(settings.MS_GRAPH_SENDER, safe="@")
    url = f"{GRAPH_BASE}/users/{sender}/messages"
    params = {
        "$select": "id,receivedDateTime",
        "$orderby": "receivedDateTime asc",
        "$top": str(_SEITE),
    }
    if seit is not None:
        ts = seit.astimezone(dt_timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        params["$filter"] = f"receivedDateTime ge {ts}"
    nachrichten = []
    while url:
        resp = requests.get(url, headers=_headers(token), params=params, timeout=_TIMEOUT)
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Graph messages-Liste HTTP {resp.status_code}: {resp.text[:300]}"
            )
        data = resp.json()
        nachrichten.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
        params = None  # der nextLink trägt die Query bereits
    return nachrichten


def _lade_mime(token: str, message_id: str) -> bytes:
    sender = quote(settings.MS_GRAPH_SENDER, safe="@")
    url = f"{GRAPH_BASE}/users/{sender}/messages/{quote(message_id, safe='')}/$value"
    resp = requests.get(url, headers=_headers(token), timeout=_TIMEOUT)
    if resp.status_code >= 400:
        raise RuntimeError(
            f"Graph MIME-Abruf HTTP {resp.status_code}: {resp.text[:200]}"
        )
    return resp.content


def _dateiname(message_id: str) -> str:
    kern = "".join(c for c in message_id if c.isalnum())[-60:] or "mail"
    return f"graph_{kern}.eml"


def abrufen() -> dict:
    """Führt einen Abruf-Lauf durch und schreibt den Zustand fort.

    Rückgabe: ``{'status', 'geholt', 'meldung'}``.
    """
    zustand = GraphMailAbruf.load()
    if not zustand.aktiv:
        return {'status': 'inaktiv', 'geholt': 0, 'meldung': 'Abruf ist deaktiviert.'}
    if not graph_konfiguriert():
        return {'status': 'nicht_konfiguriert', 'geholt': 0,
                'meldung': 'MS_GRAPH_-Werte fehlen.'}

    token = hole_app_token(
        settings.MS_GRAPH_TENANT_ID,
        settings.MS_GRAPH_CLIENT_ID,
        settings.MS_GRAPH_CLIENT_SECRET,
    )

    seit = (zustand.letzter_abruf - _UEBERLAPP) if zustand.letzter_abruf else None
    nachrichten = _hole_nachrichtenliste(token, seit)

    ordner = _eingang_ordner()
    archiv = ordner / 'archiv'
    fehler = ordner / 'fehler'

    geholt = 0
    max_received = zustand.letzter_abruf
    for eintrag in nachrichten:
        mid = eintrag.get('id')
        if not mid:
            continue
        received = parse_datetime(eintrag.get('receivedDateTime') or '')
        try:
            mime = _lade_mime(token, mid)
        except Exception:
            logger.exception("Graph-Abruf: MIME für Nachricht %s nicht ladbar.", mid[:20])
            continue
        pfad = ordner / _dateiname(mid)
        try:
            pfad.write_bytes(mime)
            mail_import_service.verarbeite_datei(pfad, archiv, fehler)
        except Exception:
            logger.exception("Graph-Abruf: Verarbeitung von %s fehlgeschlagen.", pfad.name)
            continue
        geholt += 1
        if received and (max_received is None or received > max_received):
            max_received = received

    zustand.zuletzt_gelaufen = timezone.now()
    # Fortschreiben: jüngstes Empfangsdatum, sonst (keine neuen Mails) jetzt.
    zustand.letzter_abruf = max_received or timezone.now()
    zustand.letzte_meldung = f"{geholt} Mail(s) verarbeitet."
    zustand.save()
    logger.info("Graph-Mailabruf: %s Mail(s) verarbeitet.", geholt)
    return {'status': 'ok', 'geholt': geholt, 'meldung': zustand.letzte_meldung}
