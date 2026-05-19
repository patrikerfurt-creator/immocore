"""
OP-Buchung Phase 1 – Rechnungsfreigabe (§28 WEG).

Phase 1 (Freigabe):  Soll 15900 (Schwebende ER) / Haben Kreditorenkonto (70xxx)
                     + KreditorOP mit Nummer JJNNNNNN (z.B. 26000001)

Phase 2 (Zahlung):   → rechnung_zahlung_service
"""
from datetime import date
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.buchhaltung.models import Buchung, KreditorOP
from apps.konten.models import Konto
from apps.rechnungen.konstanten import (
    KONTO_BEREICH_AUFWAND_VON,
    KONTO_BEREICH_AUFWAND_BIS,
    KONTO_SCHWEBENDE_ER,
)


def _naechste_belegnr(buchungsdatum: date) -> str:
    prefix = f"ER-{buchungsdatum.year}-"
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


def _naechste_op_nummer() -> int:
    jahr_kurz = date.today().year % 100          # 26 für 2026
    basis     = jahr_kurz * 1_000_000            # 26_000_000
    last = (
        KreditorOP.objects
        .select_for_update()
        .filter(op_nummer__gte=basis, op_nummer__lt=basis + 1_000_000)
        .order_by("-op_nummer")
        .values_list("op_nummer", flat=True)
        .first()
    )
    return (last + 1) if last else (basis + 1)


def get_or_create_kreditor_konto(kreditor, objekt) -> Konto:
    """Liefert das Sachkonto (70xxx) für diesen Kreditor im Objekt, legt es bei Bedarf an."""
    if not kreditor.kreditorennummer:
        raise ValidationError(f"Kreditor '{kreditor.name}' hat noch keine Kreditorennummer.")
    from apps.objekte.models import Wirtschaftsjahr
    wj = (
        Wirtschaftsjahr.objects.filter(objekt=objekt, status='offen').order_by('-jahr').first()
        or Wirtschaftsjahr.objects.filter(objekt=objekt).order_by('-jahr').first()
    )
    if wj is None:
        raise ValidationError(f"Kein Wirtschaftsjahr für Objekt '{objekt}' vorhanden.")
    konto, _ = Konto.objects.get_or_create(
        wirtschaftsjahr=wj,
        kontonummer=kreditor.kreditorennummer,
        defaults={
            "kontoname": f"Kreditor {kreditor.name}",
            "kontoart": "standard",
            "direktes_buchen": False,
            "aktiv": True,
        },
    )
    return konto


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
    konto_objekt_id = konto.wirtschaftsjahr.objekt_id if konto.wirtschaftsjahr_id else None
    if str(konto_objekt_id) != str(objekt_id):
        raise ValidationError("Aufwandskonto gehört nicht zum Objekt der Rechnung.")


@transaction.atomic
def rechnung_freigeben(rechnung, aufwandskonto: Konto, freigegeben_von=None):
    """
    Phase 1: OP-Buchung anlegen und KreditorOP erstellen.

    Buchungssatz: Soll 15900 (Schwebende ER) / Haben Kreditorenkonto (70xxx)
    KreditorOP:   fortlaufende Nummer JJNNNNNN (z.B. 26000001)

    freigegeben_von darf None sein (System-Auto-Buchung via Erkennungs-Pipeline).
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
    if not rechnung.betrag_brutto:
        raise ValidationError("Kein Betrag vorhanden – Freigabe nicht möglich.")
    if not rechnung.kreditor_id:
        raise ValidationError("Kein Kreditor zugeordnet – Freigabe nicht möglich.")

    _validiere_aufwandskonto(aufwandskonto, rechnung.objekt_id)

    konto_15900 = Konto.objects.select_related('wirtschaftsjahr').filter(
        wirtschaftsjahr__objekt_id=rechnung.objekt_id, kontonummer=KONTO_SCHWEBENDE_ER
    ).first()
    if not konto_15900:
        raise ValidationError(
            f"Konto {KONTO_SCHWEBENDE_ER} (Schwebende ER) ist im Objekt nicht angelegt."
        )

    kreditor_konto = get_or_create_kreditor_konto(rechnung.kreditor, rechnung.objekt)

    kreditor_str = rechnung.kreditor.name
    heute = date.today()
    wj = konto_15900.wirtschaftsjahr

    buchung = Buchung.objects.create(
        objekt=rechnung.objekt,
        soll_konto=konto_15900,
        haben_konto=kreditor_konto,
        betrag=rechnung.betrag_brutto,
        buchungsdatum=heute,
        buchungstext=(
            f"ER {rechnung.rechnungsnummer or rechnung.dateiname or str(rechnung.id)[:8]}"
            f" / {kreditor_str}"
        ),
        belegnr=_naechste_belegnr(heute),
        beleg_referenz=rechnung.rechnungsnummer or str(rechnung.id),
        wirtschaftsjahr=wj,
        wirtschaftsjahr_nr=wj.jahr if wj else heute.year,
        status="entwurf",
        erstellt_von=freigegeben_von,
    )

    op_nummer = _naechste_op_nummer()
    KreditorOP.objects.create(
        op_nummer=op_nummer,
        rechnung=rechnung,
        kreditor=rechnung.kreditor,
        objekt=rechnung.objekt,
        buchung=buchung,
        betrag_ursprung=rechnung.betrag_brutto,
        betrag_offen=rechnung.betrag_brutto,
        faellig_ab=rechnung.faelligkeitsdatum or heute,
    )

    rechnung.aufwandskonto = aufwandskonto
    rechnung.op_buchung = buchung
    rechnung.status = "gebucht"
    rechnung.save(update_fields=["aufwandskonto", "op_buchung", "status"])

    return rechnung
