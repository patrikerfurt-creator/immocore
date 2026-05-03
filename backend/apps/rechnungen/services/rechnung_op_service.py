"""
OP-Buchung Phase 1 – Rechnungsfreigabe (Kassenprinzip §28 WEG).

Bei Freigabe wird das Aufwandskonto validiert und an der Rechnung gespeichert.
Eine OP-Buchung (Soll 15900 / Haben 70xxx) setzt ein Kreditor-Subledger (70xxx)
voraus, das im aktuellen System noch nicht implementiert ist. Das Konto 15900
ist bereits für alle Objekte angelegt und steht bereit.
"""
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.konten.models import Konto
from apps.rechnungen.konstanten import (
    KONTO_BEREICH_AUFWAND_VON,
    KONTO_BEREICH_AUFWAND_BIS,
)


def _validiere_aufwandskonto(konto: Konto, objekt_id) -> None:
    nr = konto.kontonummer
    if not (KONTO_BEREICH_AUFWAND_VON <= nr <= KONTO_BEREICH_AUFWAND_BIS):
        raise ValidationError(
            f"Aufwandskonto {nr} liegt außerhalb {KONTO_BEREICH_AUFWAND_VON}–{KONTO_BEREICH_AUFWAND_BIS}."
        )
    if konto.kontoart != "standard":
        raise ValidationError(
            f"Aufwandskonto {nr} ist kein Standardkonto (ist: {konto.kontoart})."
        )
    if konto.direktes_buchen:
        raise ValidationError(
            f"Aufwandskonto {nr} ist als 'Direktes Buchen' markiert und nicht für den OP-Workflow zulässig."
        )
    if str(konto.objekt_id) != str(objekt_id):
        raise ValidationError("Aufwandskonto gehört nicht zum Objekt der Rechnung.")


@transaction.atomic
def rechnung_freigeben(rechnung, aufwandskonto: Konto, freigegeben_von):
    """
    Validiert das Aufwandskonto und speichert es an der Rechnung.
    Status → freigegeben.

    Die eigentliche OP-Buchung (Soll 15900 / Haben 70xxx) ist für eine
    spätere Erweiterung mit Kreditor-Subledger vorgesehen.
    """
    if rechnung.op_buchung_id:
        raise ValidationError("OP-Buchung existiert bereits.")
    if rechnung.status not in (
        "importiert", "erfasst", "erkannt",
        "pruefung_match", "nicht_erkannt", "in_pruefung",
    ):
        raise ValidationError(
            f"Rechnung im Status '{rechnung.status}' kann nicht freigegeben werden."
        )
    if not rechnung.objekt_id:
        raise ValidationError("Rechnung hat kein Objekt – Freigabe nicht möglich.")

    _validiere_aufwandskonto(aufwandskonto, rechnung.objekt_id)

    rechnung.aufwandskonto = aufwandskonto
    rechnung.status = "freigegeben"
    rechnung.save(update_fields=["aufwandskonto", "status"])
    return rechnung
