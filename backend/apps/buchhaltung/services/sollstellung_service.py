"""
Hausgeld-Nebenbuch — Anlegen und Storno einzelner Sollstellungen.

Keine Sachkontenbuchungen bei Sollstellung. Erst Zahlungseingang
(zahlungs_zuordnung_service) löst Buchungen aus.
"""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.buchhaltung.models import (
    Buchungsart,
    HausgeldSollstellungslauf,
    HausgeldSollstellung,
    SollstellungSplit,
)
from apps.buchhaltung.services.opos_nr_service import naechste_opos_nr
from apps.objekte.models import Bankkonto


def _bankkonto_fuer_ba(objekt, ba: Buchungsart):
    """
    Ermittelt das Zielbankkonto für eine BA am Objekt.
    Gibt None zurück wenn kein passendes Konto existiert (kein Crash),
    damit Sollstellungen auch ohne vollständige Bankkonten angelegt werden können.
    """
    bk_typ = ba.bankkonto_typ or 'bewirtschaftung'
    if bk_typ == 'bewirtschaftung':
        return (
            Bankkonto.objects.filter(objekt=objekt, konto_typ='bewirtschaftung', aktiv=True).first()
            or Bankkonto.objects.filter(objekt=objekt, konto_typ='bewirtschaftung').order_by('reihenfolge').first()
        )
    elif bk_typ == 'ruecklage_nach_index':
        try:
            idx = int(ba.nr) - 910  # 911→1, 912→2, ...
        except ValueError:
            idx = 1
        return (
            Bankkonto.objects.filter(objekt=objekt, konto_typ='ruecklage', reihenfolge=idx, aktiv=True).first()
            or Bankkonto.objects.filter(objekt=objekt, konto_typ='ruecklage', reihenfolge=idx).order_by('reihenfolge').first()
            or Bankkonto.objects.filter(objekt=objekt, konto_typ='ruecklage', aktiv=True).order_by('reihenfolge').first()
            or Bankkonto.objects.filter(objekt=objekt, konto_typ='ruecklage').order_by('reihenfolge').first()
        )
    else:
        return (
            Bankkonto.objects.filter(objekt=objekt, aktiv=True).first()
            or Bankkonto.objects.filter(objekt=objekt).order_by('reihenfolge').first()
        )


def _erloeskonto_fuer_ba(ba: Buchungsart, objekt):
    """Löst die Kontonummer aus ba.erloeskonto_default_nr auf."""
    from apps.konten.models import Konto
    from apps.objekte.models import Wirtschaftsjahr
    if not ba.erloeskonto_default_nr:
        return None
    wj = (
        Wirtschaftsjahr.objects.filter(objekt=objekt, status='offen').order_by('-jahr').first()
        or Wirtschaftsjahr.objects.filter(objekt=objekt).order_by('-jahr').first()
    )
    if not wj:
        return None
    return Konto.objects.filter(
        wirtschaftsjahr=wj, kontonummer=ba.erloeskonto_default_nr
    ).first()


@transaction.atomic
def lege_hausgeld_sollstellung_an(
    ev, periode: date, betraege_je_ba: dict, lauf=None, user=None
) -> HausgeldSollstellung:
    """
    Erzeugt eine Hausgeld-Sollstellung mit Splits im Nebenbuch.
    Keine Sachkontenbuchung — erst Zahlungseingang löst Erlösbuchung aus.

    ev: EigentumsVerhaeltnis
    periode: date (Monatserster)
    betraege_je_ba: {Buchungsart: Decimal}
    """
    objekt = ev.einheit.objekt
    soll_summe = sum(betraege_je_ba.values())
    if soll_summe <= 0:
        raise ValidationError("Soll-Summe muss positiv sein.")

    opos_nr = naechste_opos_nr(objekt)

    ss = HausgeldSollstellung.objects.create(
        objekt=objekt,
        eigentumsverhaeltnis=ev,
        sollstellungs_typ='hausgeld',
        ba=None,
        periode=periode,
        faellig_am=periode,
        opos_nr=opos_nr,
        soll_betrag=soll_summe,
        ist_betrag=Decimal('0'),
        status_cached='offen',
        sollstellungslauf=lauf,
        erstellt_von=user,
    )

    for ba_obj, betrag in betraege_je_ba.items():
        if betrag <= 0:
            continue
        bankkonto_ziel = _bankkonto_fuer_ba(objekt, ba_obj)
        erloeskonto    = _erloeskonto_fuer_ba(ba_obj, objekt)
        SollstellungSplit.objects.create(
            sollstellung=ss,
            ba=ba_obj,
            betrag=betrag,
            bankkonto_ziel=bankkonto_ziel,
            erloeskonto=erloeskonto,
        )

    return ss


@transaction.atomic
def lege_sonderumlage_sollstellung_an(
    ev, ba: Buchungsart, betrag: Decimal,
    periode: date, faellig_am: date, lauf=None, user=None
) -> HausgeldSollstellung:
    objekt = ev.einheit.objekt
    opos_nr = naechste_opos_nr(objekt)
    return HausgeldSollstellung.objects.create(
        objekt=objekt,
        eigentumsverhaeltnis=ev,
        sollstellungs_typ='sonderumlage',
        ba=ba,
        periode=periode,
        faellig_am=faellig_am,
        opos_nr=opos_nr,
        soll_betrag=betrag,
        ist_betrag=Decimal('0'),
        status_cached='offen',
        sollstellungslauf=lauf,
        erstellt_von=user,
    )


@transaction.atomic
def lege_abrechnungsergebnis_sollstellung_an(
    ev, betrag: Decimal, wj_ende: date, lauf=None, user=None
) -> HausgeldSollstellung:
    objekt = ev.einheit.objekt
    ba = Buchungsart.objects.filter(nr='950').first()
    opos_nr = naechste_opos_nr(objekt)
    return HausgeldSollstellung.objects.create(
        objekt=objekt,
        eigentumsverhaeltnis=ev,
        sollstellungs_typ='abrechnungsergebnis',
        ba=ba,
        periode=wj_ende,
        faellig_am=wj_ende,
        opos_nr=opos_nr,
        soll_betrag=betrag,
        ist_betrag=Decimal('0'),
        status_cached='offen' if betrag > 0 else 'offen',
        sollstellungslauf=lauf,
        erstellt_von=user,
    )


@transaction.atomic
def storniere_sollstellung(ss: HausgeldSollstellung, grund: str, user) -> None:
    """Storno nur wenn noch keine Zahlungen erfasst wurden (ist_betrag == 0)."""
    if ss.storniert_am is not None:
        raise ValidationError("Sollstellung ist bereits storniert.")
    if ss.ist_betrag != 0:
        raise ValidationError(
            "Sollstellung kann nicht storniert werden — es sind bereits Zahlungen erfasst. "
            "Zahlungszuordnungen zuerst aufheben."
        )
    ss.storniert_am    = timezone.now()
    ss.storniert_von   = user
    ss.storniert_grund = grund
    ss.status_cached   = 'storniert'
    ss.save(update_fields=['storniert_am', 'storniert_von', 'storniert_grund', 'status_cached'])
