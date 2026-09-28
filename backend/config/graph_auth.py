"""Gemeinsame App-Token-Beschaffung für Microsoft Graph (Client-Credentials).

Genutzt sowohl vom Versand (``config.email_backends.GraphEmailBackend``) als
auch vom Empfang (``apps.vorgaenge.services.graph_mail_abruf_service``). Beide
authentifizieren app-only (kein Benutzer) mit derselben Azure-App.
"""
from __future__ import annotations

GRAPH_SCOPE = "https://graph.microsoft.com/.default"
AUTHORITY = "https://login.microsoftonline.com/{tenant}"


class GraphAuthError(Exception):
    """Token-Abruf bei Microsoft fehlgeschlagen."""


def hole_app_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    """Holt ein App-Token (Client-Credentials-Flow) für Microsoft Graph."""
    import msal  # lokaler Import: nur nötig, wenn wirklich zugegriffen wird

    app = msal.ConfidentialClientApplication(
        client_id=client_id,
        authority=AUTHORITY.format(tenant=tenant_id),
        client_credential=client_secret,
    )
    result = app.acquire_token_for_client(scopes=[GRAPH_SCOPE])
    if "access_token" not in result:
        raise GraphAuthError(
            result.get("error_description")
            or result.get("error")
            or "Token-Abruf bei Microsoft fehlgeschlagen."
        )
    return result["access_token"]
