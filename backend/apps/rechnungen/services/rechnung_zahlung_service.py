"""
OP-Buchung Phase 2 – Zahlung (Kassenprinzip §28 WEG).

Buchung: Soll Aufwandskonto (50xxx/55xxx) / Haben Bankkonto (18xxx)
Aufwand wird erst bei Zahlung gebucht, nicht bei Rechnungseingang.
"""
from decimal import Decimal
from datetime import date
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.buchhaltung.models import Buchung
from apps.konten.models import Konto
from apps.rechnungen.konstanten import (
    KONTO_BEREICH_AUFWAND_VON,
    KONTO_BEREICH_AUFWAND_BIS,
)


def _naechste_belegnr(buchungsdatum: date) -> str:
    prefix = f"KR-{buchungsdatum.year}-"
    last = (
        Buchung.objects.filter(belegnr__startswith=prefix)
        .order_by("-belegnr")
        .values_list("belegnr", flat=True)
        .first()
    )
    try:
        lfd = int(last.rsplit("-", 1)[-1]) + 1 if last else 1
    except (ValueError, AttributeError):
        lfd = 1
    return f"{prefix}{lfd:05d}"


@transaction.atomic
def rechnung_bezahlen(rechnung, bankkonto: Konto, betrag: Decimal,
                      buchungsdatum: date, gebucht_von) -> Buchung:
    """
    Erzeugt die Aufwandsbuchung bei Zahlung (Phase 2, Kassenprinzip).
        Soll Aufwandskonto (50xxx/55xxx)
        Haben Bankkonto (18xxx)

    Setzt rechnung.aufwand_buchung, rechnung.buchung und rechnung.status='bezahlt'.
    """
    if rechnung.status == "bezahlt":
        raise ValidationError("Rechnung ist bereits bezahlt.")

    # Aufwandskonto ermitteln: zuerst aufwandskonto, Fallback kostenstelle
    konto_aufwand = rechnung.aufwandskonto or rechnung.kostenstelle
    if not konto_aufwand:
        raise ValidationError(
            "Kein Aufwandskonto erfasst – bitte zuerst Sachkonto zuweisen."
        )
    if not rechnung.betrag_brutto:
        raise ValidationError("Kein Betrag vorhanden.")
    if not rechnung.objekt_id:
        raise ValidationError("Rechnung hat kein Objekt.")

    # Aufwandskonto validieren (nur wenn aufwandskonto gesetzt, nicht bei Fallback)
    if rechnung.aufwandskonto:
        nr = konto_aufwand.kontonummer
        if not (KONTO_BEREICH_AUFWAND_VON <= nr <= KONTO_BEREICH_AUFWAND_BIS):
            raise ValidationError(
                f"Aufwandskonto {nr} außerhalb {KONTO_BEREICH_AUFWAND_VON}–{KONTO_BEREICH_AUFWAND_BIS}."
            )

    if betrag <= 0:
        raise ValidationError(f"Zahlbetrag {betrag} muss positiv sein.")

    text = (
        f"Zahlung {rechnung.rechnungsnummer or rechnung.dateiname} / "
        f"{rechnung.kreditor or rechnung.lieferant_name or 'Lieferant'}"
    )

    buchung = Buchung.objects.create(
        objekt=rechnung.objekt,
        soll_konto=konto_aufwand,
        haben_konto=bankkonto,
        betrag=betrag,
        buchungsdatum=buchungsdatum,
        buchungstext=text,
        belegnr=_naechste_belegnr(buchungsdatum),
        beleg_referenz=rechnung.rechnungsnummer or str(rechnung.id),
        wirtschaftsjahr=buchungsdatum.year,
        status="festgeschrieben",
        erstellt_von=gebucht_von,
    )

    rechnung.aufwand_buchung = buchung
    rechnung.buchung = buchung
    rechnung.status = "bezahlt"
    rechnung.save(update_fields=["aufwand_buchung", "buchung", "status"])
    return buchung
