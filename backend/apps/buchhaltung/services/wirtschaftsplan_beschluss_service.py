"""
Service: Wirtschaftsplan-Beschluss erfassen, buchen, stornieren (Spec v1.2, Kap. 6.2 + 8).
"""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.buchhaltung.models import (
    FrontofficeAufgabe,
    HausgeldSollstellung,
    WirtschaftsplanBeschluss,
    WirtschaftsplanKorrekturPaar,
    WirtschaftsplanPosition,
)
from apps.buchhaltung.services import hausgeld_historie_service
from apps.buchhaltung.services.korrektur_sollstellung_service import korrigiere_sollstellung


@transaction.atomic
def beschluss_erfassen(
    objekt,
    beschluss_typ: str,
    beschluss_datum: date,
    wirtschaftsplan_beginn: date,
    positionen_data: list,
    user,
    protokoll_position: str = None,
    wirtschaftsplan_ende: date = None,
    gesamt_volumen: Decimal = None,
    protokoll_dokument=None,
    notiz: str = None,
) -> WirtschaftsplanBeschluss:
    """
    Legt WirtschaftsplanBeschluss + WirtschaftsplanPosition an. Status='erfasst'.

    positionen_data: list of {'eigentumsverhaeltnis': EigentumsVerhaeltnis,
                               'buchungsart': Buchungsart, 'betrag': Decimal}
    """
    _validiere_beschluss(
        beschluss_typ=beschluss_typ,
        wirtschaftsplan_beginn=wirtschaftsplan_beginn,
        wirtschaftsplan_ende=wirtschaftsplan_ende,
        gesamt_volumen=gesamt_volumen,
        positionen_data=positionen_data,
    )

    beschluss = WirtschaftsplanBeschluss.objects.create(
        objekt=objekt,
        beschluss_typ=beschluss_typ,
        beschluss_datum=beschluss_datum,
        protokoll_position=protokoll_position,
        wirtschaftsplan_beginn=wirtschaftsplan_beginn,
        wirtschaftsplan_ende=wirtschaftsplan_ende,
        gesamt_volumen=gesamt_volumen,
        protokoll_dokument=protokoll_dokument,
        notiz=notiz,
        status='erfasst',
        erstellt_von=user,
    )

    for pos in positionen_data:
        WirtschaftsplanPosition.objects.create(
            beschluss=beschluss,
            eigentumsverhaeltnis=pos['eigentumsverhaeltnis'],
            buchungsart=pos['buchungsart'],
            betrag=pos['betrag'],
        )

    return beschluss


@transaction.atomic
def beschluss_buchen(beschluss: WirtschaftsplanBeschluss, user) -> dict:
    if beschluss.status != 'erfasst':
        raise ValidationError(f"Status '{beschluss.status}' ist nicht buchbar.")

    heute = timezone.localdate()
    ist_rueckwirkend = beschluss.wirtschaftsplan_beginn < heute

    stats = {
        'evs_aktualisiert': 0,
        'sollstellungen_korrigiert': 0,
        'saldenmitteilungen_erzeugt': 0,
        'gesamtdifferenz': Decimal('0.00'),
    }

    positionen_nach_ev = {}
    for position in beschluss.positionen.select_related('eigentumsverhaeltnis', 'buchungsart'):
        ev_id = position.eigentumsverhaeltnis_id
        positionen_nach_ev.setdefault(ev_id, []).append(position)

    for ev_id, positionen in positionen_nach_ev.items():
        ev = positionen[0].eigentumsverhaeltnis

        saetze_je_ba = [(p.buchungsart, p.betrag) for p in positionen]
        hausgeld_historie_service.setze_neue_saetze(
            ev=ev,
            gueltig_ab=beschluss.wirtschaftsplan_beginn,
            saetze_je_ba=saetze_je_ba,
            quelle='beschluss',
            beschluss=beschluss,
            import_referenz=None,
            user=user,
        )
        stats['evs_aktualisiert'] += 1

        if ist_rueckwirkend:
            ev_differenz = _korrigiere_rueckwirkende_sollstellungen(
                beschluss=beschluss,
                ev=ev,
                positionen=positionen,
                user=user,
                stats=stats,
            )
            stats['gesamtdifferenz'] += ev_differenz

            if ev_differenz != Decimal('0.00'):
                _erzeuge_saldenmitteilung_aufgabe(beschluss, ev, ev_differenz, user)
                stats['saldenmitteilungen_erzeugt'] += 1

    if beschluss.beschluss_typ == 'umlaufbeschluss_stundung' and beschluss.wirtschaftsplan_ende:
        _erzeuge_stundung_ablauf_aufgabe(beschluss, user)

    beschluss.status = 'gebucht'
    beschluss.gebucht_am = timezone.now()
    beschluss.save(update_fields=['status', 'gebucht_am'])

    return stats


@transaction.atomic
def beschluss_stornieren(beschluss: WirtschaftsplanBeschluss, user, grund: str) -> WirtschaftsplanBeschluss:
    if beschluss.status != 'erfasst':
        raise ValidationError(
            f"Storno nur aus Status 'erfasst' erlaubt. Aktueller Status: '{beschluss.status}'."
        )

    beschluss.status = 'storniert'
    beschluss.notiz = (
        f"{beschluss.notiz or ''}\n[Storno durch {user}: {grund}]".strip()
    )
    beschluss.save(update_fields=['status', 'notiz'])

    return beschluss


# ---------------------------------------------------------------------------
# Interne Helpers
# ---------------------------------------------------------------------------

def _validiere_beschluss(beschluss_typ, wirtschaftsplan_beginn, wirtschaftsplan_ende, gesamt_volumen, positionen_data):
    if wirtschaftsplan_beginn.day != 1:
        raise ValidationError("wirtschaftsplan_beginn muss Monatserster sein.")

    if wirtschaftsplan_ende is not None:
        import calendar
        letzter_tag = calendar.monthrange(wirtschaftsplan_ende.year, wirtschaftsplan_ende.month)[1]
        if wirtschaftsplan_ende.day != letzter_tag:
            raise ValidationError("wirtschaftsplan_ende muss Monatsletzter sein.")
        if wirtschaftsplan_ende <= wirtschaftsplan_beginn:
            raise ValidationError("wirtschaftsplan_ende muss nach wirtschaftsplan_beginn liegen.")

    if beschluss_typ == 'wirtschaftsplan':
        if gesamt_volumen is None:
            raise ValidationError("gesamt_volumen ist Pflicht bei beschluss_typ='wirtschaftsplan'.")
        if positionen_data:
            summe = sum(p['betrag'] for p in positionen_data) * 12
            if abs(summe - gesamt_volumen) > Decimal('0.01'):
                raise ValidationError(
                    f"Summe der Positionen × 12 ({summe:.2f} €) weicht vom gesamt_volumen "
                    f"({gesamt_volumen:.2f} €) um mehr als 0,01 € ab."
                )

    if beschluss_typ == 'umlaufbeschluss_stundung' and wirtschaftsplan_ende is None:
        raise ValidationError("wirtschaftsplan_ende ist Pflicht bei beschluss_typ='umlaufbeschluss_stundung'.")


def _korrigiere_rueckwirkende_sollstellungen(beschluss, ev, positionen, user, stats) -> Decimal:
    differenz_summe = Decimal('0.00')

    periode_filter = Q(periode__gte=beschluss.wirtschaftsplan_beginn)
    if beschluss.wirtschaftsplan_ende:
        periode_filter &= Q(periode__lte=beschluss.wirtschaftsplan_ende)

    betroffene_originals = HausgeldSollstellung.objects.filter(
        periode_filter,
        eigentumsverhaeltnis=ev,
        sollstellungs_typ='hausgeld',
        storniert_am__isnull=True,
        neutralisiert_durch_opos__isnull=True,
        sollstellungslauf__status='commited',
    ).order_by('periode')

    neue_splits = [(p.buchungsart, p.betrag) for p in positionen]
    neuer_gesamtbetrag = sum(b for _, b in neue_splits)

    for original in betroffene_originals:
        korrektur, neuanlage = korrigiere_sollstellung(
            original=original,
            neue_eigentumsverhaeltnis=ev,
            neue_splits=neue_splits,
            korrektur_grund='wirtschaftsplan_aenderung',
            korrektur_vorgang_id=beschluss.id,
            user=user,
        )

        differenz = neuer_gesamtbetrag - original.soll_betrag
        differenz_summe += differenz

        WirtschaftsplanKorrekturPaar.objects.create(
            beschluss=beschluss,
            eigentumsverhaeltnis=ev,
            periode=original.periode,
            original_sollstellung=original,
            korrektur_sollstellung=korrektur,
            neuanlage_sollstellung=neuanlage,
            differenz_betrag=differenz,
        )
        stats['sollstellungen_korrigiert'] += 1

    return differenz_summe


def _erzeuge_saldenmitteilung_aufgabe(beschluss, ev, differenz, user):
    person = ev.person
    FrontofficeAufgabe.objects.create(
        objekt=beschluss.objekt,
        aufgabe_typ='saldenmitteilung_wirtschaftsplan',
        beschreibung=(
            f"Saldenmitteilung versenden: {person.name} hat eine Differenz von "
            f"{differenz:+.2f} € durch Wirtschaftsplan-Beschluss vom "
            f"{beschluss.beschluss_datum} (ab {beschluss.wirtschaftsplan_beginn})."
        ),
        ev_id=ev.id,
        einheit_nr=ev.einheit.einheit_nr if ev.einheit_id else '',
        erstellt_von=user,
    )


def _erzeuge_stundung_ablauf_aufgabe(beschluss, user):
    FrontofficeAufgabe.objects.create(
        objekt=beschluss.objekt,
        aufgabe_typ='stundung_laeuft_ab',
        beschreibung=(
            f"Umlaufbeschluss-Stundung läuft am {beschluss.wirtschaftsplan_ende} ab "
            f"(Beschluss vom {beschluss.beschluss_datum})."
        ),
        erstellt_von=user,
    )
