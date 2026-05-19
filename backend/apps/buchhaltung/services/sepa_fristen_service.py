"""
SEPA-Fristen-Service — Bankarbeitstags-Logik für RCUR-Lastschriften.
Nutzt die `holidays`-Bibliothek für bundeslandspezifische Feiertage.
"""
import functools
import logging
from datetime import date, timedelta

from django.conf import settings

logger = logging.getLogger(__name__)


def naechster_einreichungstag(
    stichtag: date,
    soll_faelligkeit: date,
    bundesland: str,
) -> date:
    """
    Gibt den frühestmöglichen Fälligkeitstag zurück, an dem eine
    pain.008-Einreichung mit RCUR-Mandaten gültig ist.

    SEPA-Regel RCUR: Einreichung mindestens 2 Bankarbeitstage vor Fälligkeit.
    Wir nehmen Vorlauf SEPA_AUTOPILOT_VORLAUF_BD (default 5).

    Wenn soll_faelligkeit erreichbar ist: gibt soll_faelligkeit zurück.
    Wenn nicht: gibt den nächstmöglichen Bankarbeitstag zurück.
    """
    benoetigt_bd = getattr(settings, 'SEPA_AUTOPILOT_VORLAUF_BD', 5)
    frueheste_faelligkeit = bd_addieren(stichtag, benoetigt_bd, bundesland)

    if frueheste_faelligkeit <= soll_faelligkeit:
        return soll_faelligkeit
    return frueheste_faelligkeit


def bd_addieren(start: date, anzahl_bd: int, bundesland: str) -> date:
    """Addiert N Bankarbeitstage auf start."""
    kalender = _bankarbeitstag_kalender(bundesland)
    current = start
    addiert = 0
    while addiert < anzahl_bd:
        current += timedelta(days=1)
        if current.weekday() < 5 and current not in kalender:
            addiert += 1
    return current


def ist_bankarbeitstag(datum: date, bundesland: str) -> bool:
    """True wenn datum ein Bankarbeitstag ist (kein Wochenende, kein Feiertag)."""
    if datum.weekday() >= 5:
        return False
    return datum not in _bankarbeitstag_kalender(bundesland)


@functools.lru_cache(maxsize=64)
def _bankarbeitstag_kalender(bundesland: str):
    """
    Cache pro Bundesland. Gibt ein holidays-Objekt zurück, das die Feiertage
    für die nächsten Jahre enthält.
    """
    try:
        import holidays
        current_year = date.today().year
        return holidays.Germany(
            state=bundesland,
            years=range(current_year - 1, current_year + 3),
        )
    except Exception:
        logger.warning(
            "Unbekanntes Bundesland '%s' für Bankfeiertage-Berechnung — fallback auf HE.",
            bundesland,
        )
        import holidays
        current_year = date.today().year
        return holidays.Germany(
            state='HE',
            years=range(current_year - 1, current_year + 3),
        )
