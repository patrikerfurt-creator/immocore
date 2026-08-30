"""
WKZ-Freigabe (Stufe 2) — Zuständigkeit und Ablehnung.

Bei einer WKZ-Vorlage, die aus einer Eingangsrechnung angelegt wurde, läuft die
Zahlung über die wiederkehrende Zahlung statt über die einzelne Rechnung (die
Rechnung wird beim Abschluss ihrer Erfassung auf status='wkz_beleg' gesetzt,
siehe route_zur_freigabe). Damit die Zahlung trotzdem durch eine Freigabe läuft,
erscheint die eingereichte Vorlage als eigener Posten unter „Rechnungsfreigabe"
und wird dort freigegeben (Status 'eingereicht' → 'aktiv').

Zuständigkeit identisch zur Rechnungsfreigabe (Spec v1.1 Kap. 5.2):
objektbasierte `Objekt.zahlungsfreigabe_grenzen`, bewertet mit dem
Jahresbetrag der Vorlage. GF sieht und darf alles.
"""
import logging

from django.db import transaction

from apps.rechnungen.services.rechnung_freigabe_service import (
    _ist_geschaeftsfuehrer,
    _ist_objekt_freigeber,
)

from .vorlage_service import _bestimme_freigabestufe

logger = logging.getLogger(__name__)


def freigabe_betrag(vorlage):
    """Bewertungsgrundlage der Freigabestufe: der Jahresbetrag. Bei Rhythmus
    'frei' ist kein Jahresbetrag berechenbar → Einzelbetrag."""
    return vorlage.jahresbetrag if vorlage.jahresbetrag is not None else vorlage.betrag_gesamt


def freigabestufe_fuer(vorlage) -> dict:
    """Zuständige Freigabestufe der Vorlage laut zahlungsfreigabe_grenzen."""
    return _bestimme_freigabestufe(vorlage.objekt, freigabe_betrag(vorlage))


def darf_wkz_vorlage_freigeben(vorlage, user) -> bool:
    """Objektbasierte Stufe-2-Berechtigung für eine WKZ-Vorlage."""
    if _ist_geschaeftsfuehrer(user):
        return True
    rolle = freigabestufe_fuer(vorlage).get('rolle', '')
    if rolle == 'auto':
        return True
    if rolle in ('sachbearbeiter', 'objektmanager'):
        return _ist_objekt_freigeber(user, vorlage.objekt)
    return False   # 'geschaeftsfuehrer'-Stufe: oben bereits behandelt


@transaction.atomic
def lehne_vorlage_ab(vorlage, grund: str, user):
    """Freigabe verweigern — die Vorlage geht zurück in den Entwurf und kann
    von der Buchhaltung korrigiert und erneut eingereicht werden. Es werden
    keine WKZ-OPs erzeugt, weil die Vorlage nie aktiv war."""
    if vorlage.status != 'eingereicht':
        raise ValueError("Nur eingereichte Vorlagen können abgelehnt werden.")
    vorlage.status = 'entwurf'
    vorlage.save(update_fields=['status', 'geaendert_am'])
    logger.info(
        "WKZ Vorlage %s Freigabe abgelehnt von %s (zurück in Entwurf): %s",
        vorlage.id, user, grund,
    )
    return vorlage
