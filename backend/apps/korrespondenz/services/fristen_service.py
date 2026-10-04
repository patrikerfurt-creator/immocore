"""Fristberechnung für Schreiben (Spec 4.2, ``mahnung.frist``; Test 20).

Werktag/Feiertag wird NICHT neu implementiert: ``ist_bankarbeitstag`` aus
``apps.buchhaltung.services.sepa_fristen_service`` (Feiertage je Bundesland
über die ``holidays``-Bibliothek, bereits Projekt-Dependency) ist die
einzige Quelle. Ein Bankarbeitstag ist dort "kein Wochenende, kein Feiertag".
"""
from datetime import date, timedelta

from apps.buchhaltung.services.sepa_fristen_service import ist_bankarbeitstag


def naechster_werktag(datum: date, bundesland: str) -> date:
    """``datum`` selbst, falls Werktag, sonst der nächste Werktag danach."""
    while not ist_bankarbeitstag(datum, bundesland):
        datum += timedelta(days=1)
    return datum


def berechne_frist(heute: date, frist_tage: int, bundesland: str) -> date:
    """``heute`` + ``frist_tage`` Kalendertage, auf den nächsten Werktag verschoben."""
    return naechster_werktag(heute + timedelta(days=int(frist_tage)), bundesland)
