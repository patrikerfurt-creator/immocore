"""
Hausgeld-Nebenbuch — Massenlauf-Service.

Idempotent: Wiederholte Ausführung für dieselbe Periode ändert nichts
(UniqueConstraint auf ev+periode+typ+ba schützt gegen Duplikate).
"""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.buchhaltung.models import (
    Buchungsart,
    HausgeldSollstellungslauf,
    HausgeldSollstellung,
)
from apps.buchhaltung.services.sollstellung_service import (
    lege_hausgeld_sollstellung_an,
    storniere_sollstellung,
)
from apps.personen.models import EigentumsVerhaeltnis


def simuliere_hausgeld_monat(objekt, periode: date) -> dict:
    """
    Vorschau für einen Hausgeld-Massenlauf ohne DB-Commit.
    Gibt Positions-Liste mit erwarteten Splits und Gesamtsumme zurück.
    """
    aktive_evs = EigentumsVerhaeltnis.objects.filter(
        einheit__objekt=objekt,
        beginn__lte=periode,
    ).exclude(ende__lt=periode).select_related('einheit', 'person')

    positionen = []
    warnungen = []
    gesamtsumme = Decimal('0')

    for ev in aktive_evs:
        betraege = _aktuelle_betraege(ev, periode)
        if not betraege:
            warnungen.append(
                f"{ev.person.name} / {ev.einheit.einheit_nr}: keine Hausgeld-Beträge in der Historie"
            )
            continue

        splits = [
            {'ba_code': str(ba.nr), 'betrag': str(betrag)}
            for ba, betrag in betraege.items()
        ]
        summe = sum(betraege.values(), Decimal('0'))
        gesamtsumme += summe

        positionen.append({
            'eigentumsverhaeltnis_id': str(ev.id),
            'eigentuemer_name': ev.person.name,
            'einheit_nr': ev.einheit.einheit_nr,
            'splits': splits,
            'summe': str(summe),
            'opos_nr_neu': '(wird bei Commit reserviert)',
        })

    return {
        'objekt_id': str(objekt.pk),
        'periode': periode.strftime('%Y-%m'),
        'anzahl_evs': len(positionen),
        'gesamtsumme': str(gesamtsumme),
        'positionen': positionen,
        'warnungen': warnungen,
    }


@transaction.atomic
def erstelle_lauf_aus_vorschau(objekt, periode: date, user, wirtschaftsjahr=None) -> HausgeldSollstellungslauf:
    """Legt Lauf-Datensatz mit Status='vorschau' an, ohne Sollstellungen zu erzeugen."""
    vorschau = simuliere_hausgeld_monat(objekt, periode)
    lauf = HausgeldSollstellungslauf.objects.create(
        objekt=objekt,
        wirtschaftsjahr=wirtschaftsjahr,
        typ='hausgeld_monat',
        periode=periode,
        status='vorschau',
        erstellt_von=user,
        anzahl_sollstellungen=vorschau['anzahl_evs'],
        summe=Decimal(vorschau['gesamtsumme']),
    )
    return lauf


@transaction.atomic
def freigeben_lauf(lauf: HausgeldSollstellungslauf, user) -> HausgeldSollstellungslauf:
    """vorschau → freigegeben. Validiert Vier-Augen (freigabe_user != erstellt_von).

    Kann via settings.HAUSGELD_VIER_AUGEN_PFLICHT = False deaktiviert werden
    (z.B. für Einzelbenutzer-Umgebungen / Demo).
    """
    from django.conf import settings
    if lauf.status != 'vorschau':
        raise ValidationError(f"Lauf hat Status '{lauf.status}' — nur 'vorschau' kann freigegeben werden.")
    vier_augen = getattr(settings, 'HAUSGELD_VIER_AUGEN_PFLICHT', True)
    if vier_augen and lauf.erstellt_von_id == user.pk:
        raise ValidationError("Vier-Augen-Prinzip: Freigabe durch denselben Benutzer wie Erstellung nicht erlaubt.")
    lauf.status = 'freigegeben'
    lauf.freigabe_user = user
    lauf.freigegeben_am = timezone.now()
    lauf.save(update_fields=['status', 'freigabe_user', 'freigegeben_am'])
    return lauf


@transaction.atomic
def commiten_lauf(lauf: HausgeldSollstellungslauf, user) -> HausgeldSollstellungslauf:
    """freigegeben → commited. Erzeugt alle Sollstellungen."""
    if lauf.status != 'freigegeben':
        raise ValidationError(f"Lauf hat Status '{lauf.status}' — nur 'freigegeben' kann commited werden.")
    return _fuehre_lauf_aus(lauf, user)


def _fuehre_lauf_aus(lauf: HausgeldSollstellungslauf, user) -> HausgeldSollstellungslauf:
    """Erzeugt Sollstellungen für einen bestehenden Lauf und setzt Status auf 'commited'."""
    objekt  = lauf.objekt
    periode = lauf.periode

    aktive_evs = EigentumsVerhaeltnis.objects.filter(
        einheit__objekt=objekt,
        beginn__lte=periode,
    ).exclude(ende__lt=periode).select_related('einheit__objekt', 'person', 'einheit')

    summe         = Decimal('0')
    anzahl        = 0
    fehler_details = []
    warnungen      = []

    for ev in aktive_evs:
        betraege  = _aktuelle_betraege(ev, periode)
        soll_summe = sum(betraege.values(), Decimal('0'))
        if soll_summe <= 0:
            warnungen.append({
                'ev_id': str(ev.pk),
                'person': str(ev.person),
                'einheit': str(ev.einheit),
                'meldung': 'Keine Hausgeld-Beträge in der Historie — übersprungen.',
            })
            continue
        try:
            ss = lege_hausgeld_sollstellung_an(ev, periode, betraege, lauf=lauf, user=user)
            # Warnung wenn Bankkonto-Platzhalter oder kein Bankkonto gesetzt
            fehlende_bk = [
                str(sp.ba.nr) for sp in ss.splits.select_related('ba', 'bankkonto_ziel')
                if sp.bankkonto_ziel is None or not sp.bankkonto_ziel.aktiv
            ]
            if fehlende_bk:
                warnungen.append({
                    'ev_id': str(ev.pk),
                    'person': str(ev.person),
                    'einheit': str(ev.einheit),
                    'meldung': f"Kein aktives Bankkonto für BA {', '.join(fehlende_bk)} — bitte IBAN pflegen.",
                })
            summe  += soll_summe
            anzahl += 1
        except (IntegrityError, ValidationError) as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Sollstellung übersprungen für EV %s / Periode %s: %s",
                ev.pk, periode, exc,
            )
            fehler_details.append({
                'ev_id': str(ev.pk),
                'person': str(ev.person) if hasattr(ev, 'person') else '?',
                'einheit': str(ev.einheit) if hasattr(ev, 'einheit') else '?',
                'meldung': str(exc),
            })

    lauf.anzahl_sollstellungen = anzahl
    lauf.summe         = summe
    lauf.fehler_details = fehler_details + warnungen
    lauf.status        = 'commited'
    lauf.commited_am   = timezone.now()
    lauf.commited_von  = user
    lauf.save(update_fields=[
        'anzahl_sollstellungen', 'summe', 'fehler_details',
        'status', 'commited_am', 'commited_von',
    ])
    return lauf


def _aktuelle_betraege(ev, periode: date) -> dict:
    """
    Gibt {Buchungsart: Decimal} zurück für alle BAs mit positivem Betrag.
    Liest aus HausgeldHistorie (ba-Feld) für den Stichtag der Periode.
    Fallback auf abrechnungsart wenn ba nicht gesetzt.
    """
    from apps.personen.models import HausgeldHistorie
    result = {}

    # Alle Historieneinträge für dieses EV, deren gueltig_ab <= periode
    historien = (
        HausgeldHistorie.objects.filter(
            eigentumsverhaeltnis=ev,
            gueltig_ab__lte=periode,
        )
        .order_by('ba_id', 'abrechnungsart_id', '-gueltig_ab')
        .select_related('ba', 'abrechnungsart')
    )

    seen = set()
    for h in historien:
        # Nimm ba FK wenn gesetzt, sonst abrechnungsart als Fallback-Mapping
        ba_obj = h.ba
        if ba_obj is None and h.abrechnungsart:
            ba_obj = Buchungsart.objects.filter(nr=h.abrechnungsart.code).first()
        if ba_obj is None:
            continue
        if ba_obj.pk in seen:
            continue  # älterer Eintrag — neuester wurde schon verarbeitet
        seen.add(ba_obj.pk)
        if h.betrag and h.betrag > 0:
            result[ba_obj] = h.betrag

    return result


@transaction.atomic
def run_hausgeld_monat(
    objekt,
    periode: date,
    user,
    skip_freigabe: bool = False,
    lauf_quelle: str = 'manuell',
) -> HausgeldSollstellungslauf:
    """
    Direkter Einschritt-Commit (für Tests / Migrationen / Management-Commands
    und den Auto-Pipeline-Service).

    skip_freigabe=True überspringt den Vier-Augen-Check (nur für Autopilot).
    lauf_quelle='autopilot' kennzeichnet maschinell erzeugte Läufe.

    Produktiv-Weg für manuellen Betrieb:
      erstelle_lauf_aus_vorschau → freigeben_lauf → commiten_lauf.
    """
    lauf = HausgeldSollstellungslauf.objects.create(
        objekt=objekt,
        typ='hausgeld_monat',
        periode=periode,
        status='freigegeben',
        erstellt_von=user,
        freigabe_user=user,
        freigegeben_am=timezone.now(),
        lauf_quelle=lauf_quelle,
    )
    return _fuehre_lauf_aus(lauf, user)


@transaction.atomic
def storniere_lauf(lauf: HausgeldSollstellungslauf, grund: str, user) -> None:
    """
    Storniert einen kompletten Lauf. Nur möglich wenn keine Sollstellung
    bereits getilgt ist.
    """
    if lauf.status == 'storniert':
        raise ValidationError("Lauf ist bereits storniert.")

    fehler = []
    for ss in lauf.sollstellungen.all():
        if ss.ist_betrag != 0:
            fehler.append(f"OPOS-Nr {ss.opos_nr}: bereits {ss.ist_betrag} € getilgt")

    if fehler:
        raise ValidationError(
            "Massen-Storno nicht möglich — folgende Sollstellungen haben bereits Tilgungen:\n"
            + "\n".join(fehler)
        )

    for ss in lauf.sollstellungen.filter(storniert_am__isnull=True):
        storniere_sollstellung(ss, grund=grund, user=user)

    lauf.status         = 'storniert'
    lauf.storniert_am   = timezone.now()
    lauf.storniert_von  = user
    lauf.storniert_grund = grund
    lauf.save(update_fields=['status', 'storniert_am', 'storniert_von', 'storniert_grund'])
