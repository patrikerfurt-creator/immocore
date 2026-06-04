"""
OP-Buchung Phase 2 & 3 – Zahlungslauf und Bankabgang/eingang (§28 WEG).

Normale Rechnung:
  Phase 2: Buchung 1: Soll Aufwandskonto (55xxx) / Haben 15900   → Aufwand realisieren
           Buchung 2: Soll Kreditorenkonto (70xxx) / Haben 13600  → Verbindlichkeit ausgleichen
  Phase 3: Buchung:   Soll 13600 / Haben Bank (18xxx)             → Bankabgang

Gutschrift (ist_gutschrift=True):
  Phase 2: Buchung 1: Soll 15900 / Haben Aufwandskonto (55xxx)   → Aufwand reduzieren
           Buchung 2: Soll 13600 / Haben Kreditorenkonto (70xxx)  → Forderung ausgleichen
  Phase 3: Buchung:   Soll Bank (18xxx) / Haben 13600             → Bankeingang
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

    konto_15900 = (
        Konto.objects.select_related('wirtschaftsjahr').filter(
            wirtschaftsjahr__objekt_id=rechnung.objekt_id,
            kontonummer=KONTO_SCHWEBENDE_ER,
            wirtschaftsjahr__jahr=buchungsdatum.year,
        ).first()
        or Konto.objects.select_related('wirtschaftsjahr').filter(
            wirtschaftsjahr__objekt_id=rechnung.objekt_id,
            kontonummer=KONTO_SCHWEBENDE_ER,
        ).order_by('-wirtschaftsjahr__jahr').first()
    )
    if not konto_15900:
        raise ValidationError(f"Konto {KONTO_SCHWEBENDE_ER} nicht im Objekt angelegt.")

    konto_13600 = (
        Konto.objects.select_related('wirtschaftsjahr').filter(
            wirtschaftsjahr__objekt_id=rechnung.objekt_id,
            kontonummer=KONTO_ZAHLUNGSAUSGANG,
            wirtschaftsjahr__jahr=buchungsdatum.year,
        ).first()
        or Konto.objects.filter(
            wirtschaftsjahr__objekt_id=rechnung.objekt_id,
            kontonummer=KONTO_ZAHLUNGSAUSGANG,
        ).order_by('-wirtschaftsjahr__jahr').first()
    )
    if not konto_13600:
        raise ValidationError(f"Konto {KONTO_ZAHLUNGSAUSGANG} (Zahlungsausgang) nicht im Objekt angelegt.")

    wj = konto_15900.wirtschaftsjahr
    ist_gutschrift = getattr(rechnung, 'ist_gutschrift', False)

    # Phase 1 Buchung: normal → haben_konto = Kreditor; Gutschrift → soll_konto = Kreditor
    if ist_gutschrift:
        kreditor_konto = rechnung.op_buchung.soll_konto
    else:
        kreditor_konto = rechnung.op_buchung.haben_konto
    if not kreditor_konto:
        raise ValidationError("Kreditorenkonto aus OP-Buchung nicht lesbar.")

    betrag = rechnung.betrag_brutto
    belegnr = _naechste_belegnr(buchungsdatum)
    ist_gutschrift = getattr(rechnung, 'ist_gutschrift', False)
    text = (
        f"{'Gutschrift' if ist_gutschrift else 'Zahlung'} "
        f"{rechnung.rechnungsnummer or rechnung.dateiname} / "
        f"{rechnung.kreditor.name if rechnung.kreditor else 'Lieferant'}"
    )
    ref = rechnung.rechnungsnummer or str(rechnung.id)

    # ── Split-Buchungen ──────────────────────────────────────────────────────
    splits = list(rechnung.splits.select_related('aufwandskonto').all())
    if splits:
        summe = sum(s.betrag for s in splits)
        if abs(summe - betrag) > Decimal('0.005'):
            raise ValidationError(
                f"Split-Summe {summe} ≠ Rechnungsbetrag {betrag} — bitte Splits korrigieren."
            )
        buchung_aufwand = None
        for split in splits:
            split_text = f"{text} (Split {split.position + 1}/{len(splits)})"
            if ist_gutschrift:
                soll_k  = konto_15900
                haben_k = split.aufwandskonto
            else:
                soll_k  = split.aufwandskonto
                haben_k = konto_15900
            b = Buchung.objects.create(
                objekt=rechnung.objekt,
                soll_konto=soll_k,
                haben_konto=haben_k,
                betrag=split.betrag,
                buchungsdatum=buchungsdatum,
                buchungstext=split_text,
                belegnr=belegnr,
                beleg_referenz=ref,
                wirtschaftsjahr=wj,
                wirtschaftsjahr_nr=wj.jahr if wj else buchungsdatum.year,
                status='festgeschrieben',
                erstellt_von=gebucht_von,
            )
            if buchung_aufwand is None:
                buchung_aufwand = b

        buchung_kreditor = Buchung.objects.create(
            objekt=rechnung.objekt,
            soll_konto=konto_13600 if ist_gutschrift else kreditor_konto,
            haben_konto=kreditor_konto if ist_gutschrift else konto_13600,
            betrag=betrag,
            buchungsdatum=buchungsdatum,
            buchungstext=text,
            belegnr=belegnr,
            beleg_referenz=ref,
            wirtschaftsjahr=wj,
            wirtschaftsjahr_nr=wj.jahr if wj else buchungsdatum.year,
            status='festgeschrieben',
            erstellt_von=gebucht_von,
        )

        try:
            op = rechnung.kreditor_op
            op.zahlung_buchung = buchung_kreditor
            op.betrag_offen    = Decimal('0.00')
            op.status          = 'bezahlt'
            op.save(update_fields=['zahlung_buchung', 'betrag_offen', 'status'])
        except Exception:
            pass

        rechnung.aufwand_buchung = buchung_aufwand
        rechnung.buchung         = buchung_aufwand
        rechnung.status          = 'bezahlt'
        rechnung.save(update_fields=['aufwand_buchung', 'buchung', 'status'])
        return buchung_aufwand, buchung_kreditor

    # ── Keine Splits → bestehende Logik ─────────────────────────────────────
    if ist_gutschrift:
        # Gutschrift Phase 2:
        # Buchung 1: Soll 15900 / Haben Aufwandskonto  → Aufwand reduzieren
        # Buchung 2: Soll 13600 / Haben Kreditorenkonto → Forderung ausgleichen
        buchung_aufwand = Buchung.objects.create(
            objekt=rechnung.objekt,
            soll_konto=konto_15900,
            haben_konto=rechnung.aufwandskonto,
            betrag=betrag,
            buchungsdatum=buchungsdatum,
            buchungstext=text,
            belegnr=belegnr,
            beleg_referenz=ref,
            wirtschaftsjahr=wj,
            wirtschaftsjahr_nr=wj.jahr if wj else buchungsdatum.year,
            status="festgeschrieben",
            erstellt_von=gebucht_von,
        )
        buchung_kreditor = Buchung.objects.create(
            objekt=rechnung.objekt,
            soll_konto=konto_13600,
            haben_konto=kreditor_konto,
            betrag=betrag,
            buchungsdatum=buchungsdatum,
            buchungstext=text,
            belegnr=belegnr,
            beleg_referenz=ref,
            wirtschaftsjahr=wj,
            wirtschaftsjahr_nr=wj.jahr if wj else buchungsdatum.year,
            status="festgeschrieben",
            erstellt_von=gebucht_von,
        )
    else:
        # Normale Rechnung Phase 2:
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
            wirtschaftsjahr=wj,
            wirtschaftsjahr_nr=wj.jahr if wj else buchungsdatum.year,
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
            wirtschaftsjahr=wj,
            wirtschaftsjahr_nr=wj.jahr if wj else buchungsdatum.year,
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

    konto_13600 = (
        Konto.objects.select_related('wirtschaftsjahr').filter(
            wirtschaftsjahr__objekt_id=rechnung.objekt_id,
            kontonummer=KONTO_ZAHLUNGSAUSGANG,
            wirtschaftsjahr__jahr=buchungsdatum.year,
        ).first()
        or Konto.objects.select_related('wirtschaftsjahr').filter(
            wirtschaftsjahr__objekt_id=rechnung.objekt_id,
            kontonummer=KONTO_ZAHLUNGSAUSGANG,
        ).order_by('-wirtschaftsjahr__jahr').first()
    )
    if not konto_13600:
        raise ValidationError(f"Konto {KONTO_ZAHLUNGSAUSGANG} nicht im Objekt angelegt.")

    wj = konto_13600.wirtschaftsjahr
    ist_gutschrift = getattr(rechnung, 'ist_gutschrift', False)

    if ist_gutschrift:
        # Gutschrift Phase 3: Bankeingang
        # Soll Bank (18xxx) / Haben 13600
        text = (
            f"Bankeingang Gutschrift {rechnung.rechnungsnummer or rechnung.dateiname} / "
            f"{rechnung.kreditor.name if rechnung.kreditor else 'Lieferant'}"
        )
        buchung = Buchung.objects.create(
            objekt=rechnung.objekt,
            soll_konto=bankkonto,
            haben_konto=konto_13600,
            betrag=rechnung.betrag_brutto,
            buchungsdatum=buchungsdatum,
            buchungstext=text,
            belegnr=_naechste_belegnr(buchungsdatum),
            beleg_referenz=rechnung.rechnungsnummer or str(rechnung.id),
            wirtschaftsjahr=wj,
            wirtschaftsjahr_nr=wj.jahr if wj else buchungsdatum.year,
            status="festgeschrieben",
            erstellt_von=gebucht_von,
        )
    else:
        # Normale Rechnung Phase 3: Bankabgang
        # Soll 13600 / Haben Bank (18xxx)
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
            wirtschaftsjahr=wj,
            wirtschaftsjahr_nr=wj.jahr if wj else buchungsdatum.year,
            status="festgeschrieben",
            erstellt_von=gebucht_von,
        )
    return buchung
