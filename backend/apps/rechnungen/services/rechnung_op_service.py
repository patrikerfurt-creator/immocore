"""
OP-Buchung Phase 1 – Rechnungsfreigabe (§28 WEG).

Normale Rechnung:
  Phase 1 (Freigabe):  Soll 15900 (Schwebende ER) / Haben Kreditorenkonto (70xxx)
                       KreditorOP.betrag_ursprung = +Betrag (WEG schuldet Lieferant)

Gutschrift (ist_gutschrift=True):
  Phase 1 (Freigabe):  Soll Kreditorenkonto (70xxx) / Haben 15900 (Schwebende ER)
                       KreditorOP.betrag_ursprung = -Betrag (Lieferant schuldet WEG)

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
from apps.rechnungen.services.rechnung_buchungstext_service import einzelkosten_suffix


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
    # Erlaubt: direktes_buchen=True (für alle Wege freigegeben)
    #       ODER Aufwandsbereich 50000–55999 (nur System, aber gültiges Aufwandskonto)
    in_aufwandsbereich = KONTO_BEREICH_AUFWAND_VON <= nr <= KONTO_BEREICH_AUFWAND_BIS
    if not (konto.direktes_buchen or in_aufwandsbereich):
        raise ValidationError(
            f"Aufwandskonto {nr} ist weder im Aufwandsbereich "
            f"{KONTO_BEREICH_AUFWAND_VON}–{KONTO_BEREICH_AUFWAND_BIS} "
            f"noch als 'Direktes Buchen' freigegeben."
        )
    if konto.kontoart == "summierung":
        raise ValidationError(
            f"Aufwandskonto {nr} ist ein Summierungskonto und darf nicht direkt bebucht werden."
        )
    konto_objekt_id = konto.wirtschaftsjahr.objekt_id if konto.wirtschaftsjahr_id else None
    if str(konto_objekt_id) != str(objekt_id):
        raise ValidationError("Aufwandskonto gehört nicht zum Objekt der Rechnung.")


@transaction.atomic
def rechnung_freigeben(rechnung, aufwandskonto: Konto, freigegeben_von=None, buchungsdatum: date = None):
    """
    Phase 1: OP-Buchung anlegen und KreditorOP erstellen.

    Buchungssatz: Soll 15900 (Schwebende ER) / Haben Kreditorenkonto (70xxx)
    KreditorOP:   fortlaufende Nummer JJNNNNNN (z.B. 26000001)

    freigegeben_von darf None sein (System-Auto-Buchung via Erkennungs-Pipeline).
    buchungsdatum: Nachbuchung in vergangenes WJ — defaults to today.
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

    hat_splits = rechnung.splits.exists()
    if aufwandskonto is not None:
        _validiere_aufwandskonto(aufwandskonto, rechnung.objekt_id)
    elif not hat_splits:
        raise ValidationError("Kein Aufwandskonto gesetzt und keine Split-Positionen vorhanden – Freigabe nicht möglich.")

    heute = buchungsdatum or date.today()

    konto_15900 = (
        Konto.objects.select_related('wirtschaftsjahr').filter(
            wirtschaftsjahr__objekt_id=rechnung.objekt_id,
            kontonummer=KONTO_SCHWEBENDE_ER,
            wirtschaftsjahr__jahr=heute.year,
        ).first()
        or Konto.objects.select_related('wirtschaftsjahr').filter(
            wirtschaftsjahr__objekt_id=rechnung.objekt_id,
            kontonummer=KONTO_SCHWEBENDE_ER,
        ).order_by('-wirtschaftsjahr__jahr').first()
    )
    if not konto_15900:
        raise ValidationError(
            f"Konto {KONTO_SCHWEBENDE_ER} (Schwebende ER) ist im Objekt nicht angelegt."
        )

    kreditor_konto = get_or_create_kreditor_konto(rechnung.kreditor, rechnung.objekt)

    kreditor_str = rechnung.kreditor.name
    wj = konto_15900.wirtschaftsjahr
    ist_gutschrift = getattr(rechnung, 'ist_gutschrift', False)

    # Buchungsrichtung: bei Gutschrift Soll/Haben invertiert
    if ist_gutschrift:
        # Gutschrift: Lieferant schuldet WEG → Forderung
        # Soll 70xxx (Kreditor) / Haben 15900 (Schwebende ER)
        soll_konto  = kreditor_konto
        haben_konto = konto_15900
        buchungstext_prefix = "GS"   # Gutschrift
    else:
        # Normal: WEG schuldet Lieferant → Verbindlichkeit
        # Soll 15900 (Schwebende ER) / Haben 70xxx (Kreditor)
        soll_konto  = konto_15900
        haben_konto = kreditor_konto
        buchungstext_prefix = "ER"   # Eingangsrechnung

    buchung = Buchung.objects.create(
        objekt=rechnung.objekt,
        soll_konto=soll_konto,
        haben_konto=haben_konto,
        betrag=rechnung.betrag_brutto,
        buchungsdatum=heute,
        buchungstext=(
            f"{buchungstext_prefix} {rechnung.rechnungsnummer or rechnung.dateiname or str(rechnung.id)[:8]}"
            f" / {kreditor_str}"
            f"{einzelkosten_suffix(rechnung)}"
        ),
        belegnr=_naechste_belegnr(heute),
        beleg_referenz=rechnung.rechnungsnummer or str(rechnung.id),
        wirtschaftsjahr=wj,
        wirtschaftsjahr_nr=wj.jahr if wj else heute.year,
        status="entwurf",
        erstellt_von=freigegeben_von,
    )

    # KreditorOP: bei Gutschrift negativer Betrag (Forderung gegen Lieferant)
    op_betrag = -rechnung.betrag_brutto if ist_gutschrift else rechnung.betrag_brutto
    op_nummer = _naechste_op_nummer()
    KreditorOP.objects.create(
        op_nummer=op_nummer,
        rechnung=rechnung,
        kreditor=rechnung.kreditor,
        objekt=rechnung.objekt,
        buchung=buchung,
        betrag_ursprung=op_betrag,
        betrag_offen=op_betrag,
        faellig_ab=rechnung.faelligkeitsdatum or heute,
    )

    if aufwandskonto is not None:
        rechnung.aufwandskonto = aufwandskonto
    elif hat_splits:
        # Bei Splits das erste Split-Konto als Hauptaufwandskonto setzen (für Anzeige)
        erster_split = rechnung.splits.order_by('position').first()
        if erster_split:
            rechnung.aufwandskonto = erster_split.aufwandskonto
    rechnung.op_buchung = buchung
    rechnung.status = "gebucht"
    rechnung.save(update_fields=["aufwandskonto", "op_buchung", "status"])

    return rechnung
