"""
Freigabe-Berechtigung Rechnungseingang (Spec Kap. 4.2, Umbau v1.0).

WER freigeben darf, ergibt sich ausschließlich aus dem persönlichen
Euro-Limit (Mitarbeiter.freigabe_limit) — NICHT mehr aus der Rolle.
Die Betragsschwellen (Bagatellgrenze) bleiben am Objekt.

V9-Auflösung: AUTH_USER_MODEL ist Standard-`auth.User`; das Limit liegt auf
dem Profil-Model `Mitarbeiter` (OneToOne, related_name='mitarbeiter_profil').
"""
from decimal import Decimal


def freigabe_limit(user) -> Decimal | None:
    """Persönliches Freigabelimit des Users oder None (keine Berechtigung).
    Zugriff über das Mitarbeiter-Profil (V9)."""
    profil = getattr(user, "mitarbeiter_profil", None)
    if profil is None:
        return None
    return profil.freigabe_limit


def darf_freigeben(rechnung, user) -> bool:
    """Persönliches Limit entscheidet — nicht die Rolle (Spec 4.2).
    NULL-Limit → keine Berechtigung. Betrag == Limit → erlaubt."""
    limit = freigabe_limit(user)
    if limit is None or rechnung.betrag_brutto is None:
        return False
    return rechnung.betrag_brutto <= limit


def _lade_grenzen(rechnung) -> list:
    """Freigabe-Stufen aus dem Objekt oder globalem Default (als Liste)."""
    from ..models import FreigabelimitDefault
    if rechnung.objekt_id and rechnung.objekt.zahlungsfreigabe_grenzen:
        grenzen = rechnung.objekt.zahlungsfreigabe_grenzen
        if isinstance(grenzen, list) and grenzen:
            return grenzen
    return FreigabelimitDefault.lade().grenzen


def _bagatellgrenze(grenzen: list) -> Decimal:
    """Obergrenze der untersten 'auto'-Stufe. Ohne auto-Stufe → 0
    (dann braucht jede Rechnung eine Freigabe)."""
    auto_grenzen = [
        s.get("bis") for s in (grenzen or [])
        if s.get("rolle") == "auto" and s.get("bis") is not None
    ]
    if not auto_grenzen:
        return Decimal("0")
    return Decimal(str(max(auto_grenzen)))


def braucht_freigabe(rechnung) -> bool:
    """Bagatellgrenze aus Objekt-Konfig (unterste 'auto'-Stufe).
    Unterhalb: der Erfasser bucht direkt, sofern er ein freigabe_limit > 0
    besitzt (Vier-Augen-Detail: Bestätigungspunkt B1 — eine Freigabe genügt)."""
    bagatell = _bagatellgrenze(_lade_grenzen(rechnung))
    betrag = rechnung.betrag_brutto or Decimal("0")
    return betrag > bagatell
