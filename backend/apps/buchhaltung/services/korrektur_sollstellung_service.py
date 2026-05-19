"""
Generischer Korrektur-Service für Hausgeld-Sollstellungen (Spec v1.2).
"""
from decimal import Decimal
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.buchhaltung.models import HausgeldSollstellung, SollstellungSplit
from apps.buchhaltung.services.opos_nr_service import naechste_opos_nr

_ERLAUBTE_KORREKTUR_GRUENDE = ('eigentuemerwechsel', 'wirtschaftsplan_aenderung')


@transaction.atomic
def korrigiere_sollstellung(
    original: HausgeldSollstellung,
    neue_eigentumsverhaeltnis,
    neue_splits: list | None,
    korrektur_grund: str,
    korrektur_vorgang_id: UUID,
    user,
) -> tuple[HausgeldSollstellung, HausgeldSollstellung]:
    """
    Erzeugt für eine Original-Sollstellung:
      (a) Korrektur-Sollstellung auf original.eigentumsverhaeltnis mit negierten Splits
      (b) Neuanlage-Sollstellung auf neue_eigentumsverhaeltnis

    Splits-Verhalten:
      - neue_splits=None  → 1:1 Klon aus Original (Eigentümerwechsel)
      - neue_splits=[(ba, betrag), ...] → aus Liste gebildet (Wirtschaftsplan)

    Raises:
      ValidationError wenn original bereits neutralisiert oder korrektur_grund ungültig
    """
    if korrektur_grund not in _ERLAUBTE_KORREKTUR_GRUENDE:
        raise ValidationError(
            f"Ungültiger korrektur_grund '{korrektur_grund}'. "
            f"Erlaubt: {_ERLAUBTE_KORREKTUR_GRUENDE}"
        )

    if original.neutralisiert_durch_opos_id is not None:
        raise ValidationError(
            f"Sollstellung {original.opos_nr} wurde bereits neutralisiert "
            f"(durch OPOS {original.neutralisiert_durch_opos_id})."
        )

    objekt = original.objekt

    # (a) Korrektur-Sollstellung (negativ, gleiche EV wie Original)
    korrektur = HausgeldSollstellung.objects.create(
        objekt=objekt,
        eigentumsverhaeltnis=original.eigentumsverhaeltnis,
        sollstellungs_typ='korrektur',
        ba=original.ba,
        periode=original.periode,
        faellig_am=original.faellig_am,
        opos_nr=naechste_opos_nr(objekt),
        soll_betrag=-original.soll_betrag,
        ist_betrag=Decimal('0'),
        status_cached='offen',
        korrektur_grund=korrektur_grund,
        korrektur_vorgang_id=korrektur_vorgang_id,
        neutralisiert_opos_nr=original,
        erstellt_von=user,
    )
    _negiere_splits(original, korrektur)

    # Rückverkettung am Original
    original.neutralisiert_durch_opos = korrektur
    original.save(update_fields=['neutralisiert_durch_opos'])

    # (b) Neuanlage-Sollstellung auf neue EV
    if neue_splits is None:
        neuanlage_betrag = original.soll_betrag
    else:
        neuanlage_betrag = sum(betrag for _, betrag in neue_splits)

    neuanlage = HausgeldSollstellung.objects.create(
        objekt=objekt,
        eigentumsverhaeltnis=neue_eigentumsverhaeltnis,
        sollstellungs_typ='hausgeld',
        ba=original.ba,
        periode=original.periode,
        faellig_am=original.faellig_am,
        opos_nr=naechste_opos_nr(objekt),
        soll_betrag=neuanlage_betrag,
        ist_betrag=Decimal('0'),
        status_cached='offen',
        korrektur_grund=korrektur_grund,
        korrektur_vorgang_id=korrektur_vorgang_id,
        erstellt_von=user,
    )

    if neue_splits is None:
        _klone_splits(original, neuanlage)
    else:
        _setze_splits(neuanlage, neue_splits)

    return korrektur, neuanlage


def _negiere_splits(
    original: HausgeldSollstellung,
    korrektur: HausgeldSollstellung,
) -> None:
    for split in original.splits.select_related('ba', 'bankkonto_ziel', 'erloeskonto'):
        SollstellungSplit.objects.create(
            sollstellung=korrektur,
            ba=split.ba,
            betrag=-split.betrag,
            bankkonto_ziel=split.bankkonto_ziel,
            erloeskonto=split.erloeskonto,
        )


def _klone_splits(
    original: HausgeldSollstellung,
    neuanlage: HausgeldSollstellung,
) -> None:
    for split in original.splits.select_related('ba', 'bankkonto_ziel', 'erloeskonto'):
        SollstellungSplit.objects.create(
            sollstellung=neuanlage,
            ba=split.ba,
            betrag=split.betrag,
            bankkonto_ziel=split.bankkonto_ziel,
            erloeskonto=split.erloeskonto,
        )


def _setze_splits(
    sollstellung: HausgeldSollstellung,
    splits: list,
) -> None:
    for ba, betrag in splits:
        SollstellungSplit.objects.create(
            sollstellung=sollstellung,
            ba=ba,
            betrag=betrag,
        )


def get_korrektur_vorgang(sollstellung: HausgeldSollstellung):
    """
    Lädt den auslösenden Vorgang anhand korrektur_grund + korrektur_vorgang_id.
    Gibt None zurück wenn korrektur_vorgang_id nicht gesetzt.
    """
    if sollstellung.korrektur_vorgang_id is None:
        return None
    if sollstellung.korrektur_grund == 'eigentuemerwechsel':
        from apps.buchhaltung.models import EigentuemerwechselVorgang
        return EigentuemerwechselVorgang.objects.get(pk=sollstellung.korrektur_vorgang_id)
    if sollstellung.korrektur_grund == 'wirtschaftsplan_aenderung':
        from apps.buchhaltung.models import WirtschaftsplanBeschluss
        return WirtschaftsplanBeschluss.objects.get(pk=sollstellung.korrektur_vorgang_id)
    return None


def tilge_sollstellung(sollstellung: HausgeldSollstellung, betrag_eingang: Decimal) -> None:
    """
    betrag_eingang ist immer positiv (echter Geldfluss).

    Standard-Sollstellung (soll_betrag > 0): ist_betrag wächst gegen soll_betrag.
    Korrektur-Sollstellung (soll_betrag < 0): Auszahlung — ist_betrag wird negativer.
    """
    if sollstellung.soll_betrag < 0:
        sollstellung.ist_betrag -= betrag_eingang
    else:
        sollstellung.ist_betrag += betrag_eingang
    sollstellung.save(update_fields=['ist_betrag'])
