"""
Service: Rückwirkender WP-Beschluss — Differenz-Sollstellungen und Gutschrift-Auszahlungen.
Spec: CLAUDE_CODE_ANLEITUNG_WIRTSCHAFTSPLAN_v1_0.md Kap. 8.
Hinweis: Vollimplementierung folgt in Phase 2. Aktuell: Logging + No-Op.
"""
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


def verarbeite_rueckwirkenden_beschluss(wp, ev_ba_map: dict, user) -> dict:
    """
    Verarbeitet rückwirkende Differenzen nach WP-Beschluss.
    Aktuell nur Logging — keine Nachhol-Sollstellungen oder Gutschriften.
    """
    logger.info(
        "Rückwirkender WP-Beschluss %s: wirkung_ab=%s — "
        "Differenz-Verarbeitung noch nicht implementiert.",
        wp.id, wp.wirkung_ab,
    )
    return {'nachhol_sollstellungen': 0, 'gutschrift_positionen': 0}
