"""
Jahresabrechnung — Kostenstellen-Übersicht, Wizard-Schritt 3 (HGA-Spec v1.0 Kap. 5).

Ist-Kosten je Sachkonto (Aggregation über Buchung im WJ, Soll auf
Aufwandskonten 50xxx/55xxx) vs. Wirtschaftsplan-Ansatz. Read-only.

Degradation gemäß Spec: Existiert kein beschlossener/aktiver Wirtschaftsplan
für das WJ, werden nur Ist-Kosten ohne Vergleichsspalte geliefert (kein Blocker).
"""
from decimal import Decimal

from django.db.models import Q, Sum

from apps.buchhaltung.models import Buchung
from apps.konten.models import Konto
from apps.objekte.models import Objekt, Wirtschaftsjahr

AUFWANDSKONTO_MIN = 50000
AUFWANDSKONTO_MAX = 55999


def kostenstellen_uebersicht(objekt: Objekt, wj: Wirtschaftsjahr) -> dict:
    """
    Liefert je Aufwandskonto des WJ: Ist-Kosten, Wirtschaftsplan-Ansatz,
    Abweichung (absolut + Prozent).

    Rückgabe:
    {
        'wirtschaftsplan_vorhanden': bool,
        'positionen': [
            {'konto_id', 'kontonummer', 'kontoname', 'vs_code',
             'ist', 'plan', 'abweichung', 'abweichung_prozent'},
            ...
        ],
        'summe_ist': Decimal, 'summe_plan': Decimal | None,
    }
    """
    konten = _aufwandskonten(wj)
    ist_je_konto = _ist_kosten_je_konto(objekt, wj, konten)
    plan_je_konto, wp_vorhanden = _plan_ansaetze_je_konto(wj)

    positionen = []
    summe_ist = Decimal('0')
    summe_plan = Decimal('0') if wp_vorhanden else None
    for konto in konten:
        ist = ist_je_konto.get(konto.id, Decimal('0'))
        plan = plan_je_konto.get(konto.id) if wp_vorhanden else None
        abweichung = (ist - plan) if plan is not None else None
        if plan:
            abweichung_prozent = (abweichung / plan * 100).quantize(Decimal('0.01'))
        else:
            abweichung_prozent = None
        positionen.append({
            'konto_id': str(konto.id),
            'kontonummer': konto.kontonummer,
            'kontoname': konto.kontoname,
            'ist': ist,
            'plan': plan,
            'abweichung': abweichung,
            'abweichung_prozent': abweichung_prozent,
        })
        summe_ist += ist
        if wp_vorhanden and plan is not None:
            summe_plan += plan

    return {
        'wirtschaftsplan_vorhanden': wp_vorhanden,
        'positionen': positionen,
        'summe_ist': summe_ist,
        'summe_plan': summe_plan,
    }


# ---------------------------------------------------------------------------
# intern
# ---------------------------------------------------------------------------

def _aufwandskonten(wj: Wirtschaftsjahr) -> list:
    """Aufwandskonten 50xxx–55xxx des WJ (nur bebuchbare Standard-Konten)."""
    konten = Konto.objects.filter(
        wirtschaftsjahr=wj, kontoart=Konto.Kontoart.STANDARD, aktiv=True,
    ).order_by('kontonummer')
    return [
        k for k in konten
        if k.kontonummer.isdigit()
        and AUFWANDSKONTO_MIN <= int(k.kontonummer) <= AUFWANDSKONTO_MAX
    ]


def buchungen_im_wj(objekt: Objekt, wj: Wirtschaftsjahr):
    """
    Nicht stornierte Buchungen des Objekts im WJ.
    Storno-Paare werden komplett ausgeschlossen (Original hat status='storniert',
    die Storno-Gegenbuchung hat storno_von gesetzt).
    """
    return (
        Buchung.objects
        .filter(objekt=objekt)
        .filter(
            Q(wirtschaftsjahr=wj)
            | Q(
                wirtschaftsjahr__isnull=True,
                buchungsdatum__gte=wj.beginn_datum,
                buchungsdatum__lte=wj.ende_datum,
            )
        )
        .exclude(status='storniert')
        .exclude(storno_von__isnull=False)
    )


def _ist_kosten_je_konto(objekt: Objekt, wj: Wirtschaftsjahr, konten: list) -> dict:
    """Ist-Kosten = Σ Soll-Buchungen − Σ Haben-Buchungen je Aufwandskonto."""
    konto_ids = [k.id for k in konten]
    basis = buchungen_im_wj(objekt, wj)
    soll = dict(
        basis.filter(soll_konto_id__in=konto_ids)
        .values_list('soll_konto_id')
        .annotate(s=Sum('betrag'))
        .values_list('soll_konto_id', 's')
    )
    haben = dict(
        basis.filter(haben_konto_id__in=konto_ids)
        .values_list('haben_konto_id')
        .annotate(s=Sum('betrag'))
        .values_list('haben_konto_id', 's')
    )
    return {
        kid: (soll.get(kid) or Decimal('0')) - (haben.get(kid) or Decimal('0'))
        for kid in konto_ids
    }


def _plan_ansaetze_je_konto(wj: Wirtschaftsjahr) -> tuple:
    """Ansätze aus dem beschlossenen/aktiven Wirtschaftsplan des WJ."""
    from apps.abrechnung_wp.models import Wirtschaftsplan, WirtschaftsplanPosition
    wp = (
        Wirtschaftsplan.objects
        .filter(wirtschaftsjahr=wj, status__in=['beschlossen', 'aktiv'])
        .order_by('-beschlossen_am')
        .first()
    )
    if wp is None:
        return {}, False
    ansaetze = dict(
        WirtschaftsplanPosition.objects
        .filter(wirtschaftsplan=wp)
        .values_list('konto_id', 'betrag')
    )
    return ansaetze, True
