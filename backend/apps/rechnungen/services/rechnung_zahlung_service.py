"""
OP-Buchung Phase 2 & 3 – Zahlungslauf und Bankabgang (§28 WEG).

Phase 2 (Zahlungslauf):
  Buchung 1: Soll Aufwandskonto (50xxx) / Haben 15900  → löscht Schwebende ER
  Buchung 2: Soll Kreditorenkonto (70xxx) / Haben 13600 → stellt Zahlungsausgang, schließt OP

Phase 3 (Bank):
  Buchung:   Soll 13600 / Haben Bank (18xxx)            → Bankabgang
"""
from decimal import Decimal
from datetime import date
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.buchhaltung.models import Buchung, KreditorOP
from apps.konten.models import Konto
from apps.rechnungen.konstanten import (
    KONTO_SCHWEBENDE_ER,
    KONTO_ZAHLUNGSAUSGANG,
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
def rechnung_bezahlen(rechnung, buchungsdatum: date, gebucht_von):
    """
    Phase 2 – Zahlungslauf.

    Buchung 1: Soll Aufwandskonto (50xxx) / Haben 15900
    Buchung 2: Soll Kreditorenkonto (70xxx) / Haben 13600
    Schließt KreditorOP (status='bezahlt', betrag_offen=0).
    """
    if rechnung.status == "bezahlt":
        raise ValidationError("Rechnung ist bereits bezahlt.")
    if rechnung.status != "gebucht":
        raise ValidationError(
            f"Rechnung im Status '{rechnung.status}' kann nicht bezahlt werden – "
            "bitte zuerst freigeben (Status 'gebucht' erforderlich)."
        )
    if not rechnung.op_buchung_id:
        raise ValidationError("Keine OP-Buchung vorhanden – bitte zuerst freigeben.")
    if not rechnung.aufwandskonto_id:
        raise ValidationError("Kein Aufwandskonto gesetzt – bitte zuerst freigeben.")

    konto_15900 = Konto.objects.filter(
        objekt_id=rechnung.objekt_id, kontonummer=KONTO_SCHWEBENDE_ER
    ).first()
    if not konto_15900:
        raise ValidationError(f"Konto {KONTO_SCHWEBENDE_ER} nicht im Objekt angelegt.")

    konto_13600 = Konto.objects.filter(
        objekt_id=rechnung.objekt_id, kontonummer=KONTO_ZAHLUNGSAUSGANG
    ).first()
    if not konto_13600:
        raise ValidationError(f"Konto {KONTO_ZAHLUNGSAUSGANG} (Zahlungsausgang) nicht im Objekt angelegt.")

    kreditor_konto = rechnung.op_buchung.haben_konto
    if not kreditor_konto:
        raise ValidationError("Kreditorenkonto aus OP-Buchung nicht lesbar.")

    betrag = rechnung.betrag_brutto
    belegnr = _naechste_belegnr(buchungsdatum)
    text = (
        f"Zahlung {rechnung.rechnungsnummer or rechnung.dateiname} / "
        f"{rechnung.kreditor.name if rechnung.kreditor else 'Lieferant'}"
    )
    ref = rechnung.rechnungsnummer or str(rechnung.id)

    # Buchung 1: Soll Aufwandskonto / Haben 15900
    buchung_aufwand = Buchung.objects.create(
        objekt=rechnung.objekt,
        soll_konto=rechnung.aufwandskonto,
        haben_konto=konto_15900,
        betrag=betrag,
        buchungsdatum=buchungsdatum,
        buchungstext=text,
        belegnr=belegnr,
        beleg_referenz=ref,
        wirtschaftsjahr=buchungsdatum.year,
        status="festgeschrieben",
        erstellt_von=gebucht_von,
    )

    # Buchung 2: Soll Kreditorenkonto / Haben 13600
    buchung_kreditor = Buchung.objects.create(
        objekt=rechnung.objekt,
        soll_konto=kreditor_konto,
        haben_konto=konto_13600,
        betrag=betrag,
        buchungsdatum=buchungsdatum,
        buchungstext=text,
        belegnr=belegnr,
        beleg_referenz=ref,
        wirtschaftsjahr=buchungsdatum.year,
        status="festgeschrieben",
        erstellt_von=gebucht_von,
    )

    # KreditorOP schließen
    try:
        op = rechnung.kreditor_op
        op.zahlung_buchung = buchung_kreditor
        op.betrag_offen = Decimal("0.00")
        op.status = "bezahlt"
        op.save(update_fields=["zahlung_buchung", "betrag_offen", "status"])
    except KreditorOP.DoesNotExist:
        pass

    rechnung.aufwand_buchung = buchung_aufwand
    rechnung.buchung = buchung_aufwand
    rechnung.status = "bezahlt"
    rechnung.save(update_fields=["aufwand_buchung", "buchung", "status"])

    return buchung_aufwand, buchung_kreditor


@transaction.atomic
def bank_abgang_buchen(rechnung, bankkonto: Konto, buchungsdatum: date, gebucht_von) -> Buchung:
    """
    Phase 3 – Bankabgang.

    Buchung: Soll 13600 (Schwebender Zahlungsausgang) / Haben Bankkonto (18xxx)
    """
    if rechnung.status != "bezahlt":
        raise ValidationError(
            f"Bank-Abgang nur für bezahlte Rechnungen möglich (Status: '{rechnung.status}')."
        )

    konto_13600 = Konto.objects.filter(
        objekt_id=rechnung.objekt_id, kontonummer=KONTO_ZAHLUNGSAUSGANG
    ).first()
    if not konto_13600:
        raise ValidationError(f"Konto {KONTO_ZAHLUNGSAUSGANG} nicht im Objekt angelegt.")

    text = (
        f"Bankabgang {rechnung.rechnungsnummer or rechnung.dateiname} / "
        f"{rechnung.kreditor.name if rechnung.kreditor else 'Lieferant'}"
    )

    buchung = Buchung.objects.create(
        objekt=rechnung.objekt,
        soll_konto=konto_13600,
        haben_konto=bankkonto,
        betrag=rechnung.betrag_brutto,
        buchungsdatum=buchungsdatum,
        buchungstext=text,
        belegnr=_naechste_belegnr(buchungsdatum),
        beleg_referenz=rechnung.rechnungsnummer or str(rechnung.id),
        wirtschaftsjahr=buchungsdatum.year,
        status="festgeschrieben",
        erstellt_von=gebucht_von,
    )
    return buchung
