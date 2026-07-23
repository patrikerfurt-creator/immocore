"""
Jahresabrechnung — Rücklagen-Ausweis, Wizard-Schritt 5 (HGA-Spec v1.0 Kap. 4.5).

Je Rücklage (= Bankkonto mit konto_typ='ruecklage', Index über reihenfolge,
BA-Zuordnung 911/912/… analog sollstellung_service._bankkonto_fuer_ba):

    Anfangsbestand   Bankkonto-Saldo zum WJ-Beginn (Σ Kontoumsätze davor —
                     das System führt keinen separaten Anfangssaldo)
    + Zuführungen    Σ SollstellungZahlung auf Splits mit der Rücklagen-BA
                     im WJ (Nebenbuch — NICHT Sachkontenbuchungen, Kap. 4.5)
    − Entnahmen      Buchungen mit Rücklagen-Sachkonto (abrechnungsart=BA)
                     als Gegenkonto (Haben) im WJ
    = Endbestand     rechnerisch; Soll = Bankauszug zum WJ-Ende.
                     |Abweichung| > 0,01 € → Klärungsfall, blockiert Schritt 5.

Anteil Eigentümer = Endbestand × MEA der Einheit (via verteilerschluessel_service).
Read-only.
"""
from decimal import Decimal

from django.db.models import Q, Sum

from apps.buchhaltung.models import (
    Buchung,
    Kontoumsatz,
    SollstellungZahlung,
    WirtschaftsplanRuecklage,
)
from apps.konten.models import Konto
from apps.objekte.models import Bankkonto, Einheit, Objekt, Wirtschaftsjahr

from .kostenstellen_service import buchungen_im_wj
from .verteilerschluessel_service import mea_anteil

ABWEICHUNGS_TOLERANZ = Decimal('0.01')


def ruecklagen_uebersicht(objekt: Objekt, wj: Wirtschaftsjahr) -> list:
    """
    Tabelle gemäß Kap. 4.5, ein Eintrag je Rücklagen-Bankkonto:

    {'bankkonto_id', 'bezeichnung', 'ba_nr',
     'anfangsbestand', 'zufuehrungen', 'entnahmen',
     'endbestand_berechnet', 'endbestand_bank',
     'abweichung', 'klaerungsfall'}
    """
    rows = []
    ruecklagen_konten = Bankkonto.objects.filter(
        objekt=objekt, konto_typ='ruecklage',
    ).order_by('reihenfolge')
    for bk in ruecklagen_konten:
        ba_nr = str(910 + bk.reihenfolge)  # reihenfolge 1 → BA 911, 2 → 912, …
        anfangsbestand = _anfangsbestand(bk, objekt, wj, ba_nr)
        zufuehrungen = _zufuehrungen_nebenbuch(objekt, wj, ba_nr)
        entnahmen = _entnahmen(objekt, wj, ba_nr)
        endbestand_berechnet = anfangsbestand + zufuehrungen - entnahmen
        endbestand_bank = _bank_saldo(bk, bis=wj.ende_datum, exklusiv=False)
        abweichung = endbestand_berechnet - endbestand_bank
        plan = WirtschaftsplanRuecklage.objects.filter(
            wirtschaftsjahr=wj, ba_nr=ba_nr,
        ).first()
        rows.append({
            'bankkonto_id': str(bk.id),
            'bezeichnung': bk.bezeichnung,
            'ba_nr': ba_nr,
            'anfangsbestand': anfangsbestand,
            'zufuehrungen': zufuehrungen,
            'entnahmen': entnahmen,
            'endbestand_berechnet': endbestand_berechnet,
            'endbestand_bank': endbestand_bank,
            'abweichung': abweichung,
            'klaerungsfall': abs(abweichung) > ABWEICHUNGS_TOLERANZ,
            # Fixer Planwert lt. Wirtschaftsplan (Objekt-Gesamt); None = nicht erfasst
            'zufuehrung_plan': plan.betrag if plan else None,
        })
    return rows


def wirtschaftsplan_ruecklage_gesamt(wj: Wirtschaftsjahr):
    """Summe der geplanten Rücklagen-Zuführung (alle Rücklagen-BAs) für das WJ.
    None, wenn kein Planwert erfasst ist → Aufrufer fällt auf Ist-Werte zurück."""
    plaene = WirtschaftsplanRuecklage.objects.filter(wirtschaftsjahr=wj)
    if not plaene.exists():
        return None
    return plaene.aggregate(s=Sum('betrag'))['s'] or Decimal('0')


def pruefe_schritt5_blocker(objekt: Objekt, wj: Wirtschaftsjahr) -> list:
    """Klärungsfälle (Abweichung berechneter Endbestand vs. Bankauszug).

    NUR informativ (Hinweis im Wizard-Schritt 5). Schritt 5 sperrt NICHT mehr,
    und die Freigabe wird dadurch nicht blockiert.
    """
    return [r for r in ruecklagen_uebersicht(objekt, wj) if r['klaerungsfall']]


def anteil_eigentuemer(endbestand: Decimal, einheit: Einheit, wj: Wirtschaftsjahr) -> Decimal:
    """Anteil der Einheit am Rücklagen-Endbestand: Endbestand × MEA (Kap. 4.5)."""
    return endbestand * mea_anteil(einheit, wj)


# ---------------------------------------------------------------------------
# intern
# ---------------------------------------------------------------------------

def _anfangsbestand(bankkonto: Bankkonto, objekt: Objekt, wj: Wirtschaftsjahr, ba_nr: str) -> Decimal:
    """
    Anfangsbestand der Rücklage: primär der Saldovortrag (BA 99) auf dem
    Rücklagen-Bestandskonto 09<ba_nr> (z. B. 09911). Fällt zurück auf die
    Summe der Bank-Kontoumsätze vor WJ-Beginn, wenn kein Bestandskonto oder
    kein Saldovortrag gebucht ist (Alt-Logik / CAMT-Historie).
    """
    vortrag = _saldovortrag_bestandskonto(objekt, wj, ba_nr)
    if vortrag is not None:
        return vortrag
    return _bank_saldo(bankkonto, bis=wj.beginn_datum, exklusiv=True)


def _saldovortrag_bestandskonto(objekt: Objekt, wj: Wirtschaftsjahr, ba_nr: str):
    """Saldovortrag (BA 99, Haben − Soll) auf dem Bestandskonto 09<ba_nr>.
    Gibt None zurück, wenn Konto oder Saldovortrags-Buchung fehlen."""
    konto = Konto.objects.filter(wirtschaftsjahr=wj, kontonummer=f"09{ba_nr}").first()
    if konto is None:
        return None
    vortrag = Buchung.objects.filter(
        wirtschaftsjahr=wj, buchungsart__nr='99',
    ).filter(Q(haben_konto=konto) | Q(soll_konto=konto))
    if not vortrag.exists():
        return None
    haben = vortrag.filter(haben_konto=konto).aggregate(s=Sum('betrag'))['s'] or Decimal('0')
    soll = vortrag.filter(soll_konto=konto).aggregate(s=Sum('betrag'))['s'] or Decimal('0')
    return haben - soll


def _bank_saldo(bankkonto: Bankkonto, bis, exklusiv: bool) -> Decimal:
    """
    Saldo als Summe aller nicht stornierten Kontoumsätze bis zum Stichtag.
    Es existiert kein Anfangssaldo-Feld — Voraussetzung ist eine lückenlose
    Umsatzhistorie seit Kontoanlage (CAMT-Import).
    """
    qs = Kontoumsatz.objects.filter(bankkonto=bankkonto).exclude(status='storniert')
    if exklusiv:
        qs = qs.filter(buchungsdatum__lt=bis)
    else:
        qs = qs.filter(buchungsdatum__lte=bis)
    return qs.aggregate(s=Sum('betrag'))['s'] or Decimal('0')


def _zufuehrungen_nebenbuch(objekt: Objekt, wj: Wirtschaftsjahr, ba_nr: str) -> Decimal:
    """
    Zuführungen aus dem Nebenbuch: gezahlte Beträge auf Sollstellungs-Splits
    mit der Rücklagen-BA im WJ (Kap. 4.5 — nicht mehr aus Unterkonto-Buchungen).
    """
    summe = (
        SollstellungZahlung.objects
        .filter(
            sollstellung__objekt=objekt,
            split__ba__nr=ba_nr,
            buchung__buchungsdatum__gte=wj.beginn_datum,
            buchung__buchungsdatum__lte=wj.ende_datum,
        )
        .exclude(buchung__status='storniert')
        .exclude(sollstellung__storniert_am__isnull=False)
        .aggregate(s=Sum('betrag'))['s']
    )
    return summe or Decimal('0')


def _entnahmen(objekt: Objekt, wj: Wirtschaftsjahr, ba_nr: str) -> Decimal:
    """
    Entnahmen: Buchungen im WJ mit einem Rücklagen-Sachkonto
    (Konto.abrechnungsart == BA-Nr) auf der Haben-Seite (Gegenkonto).

    Erlöskonten (41xxx) werden ausgeschlossen: Sie tragen zwar dieselbe
    abrechnungsart wie das Rücklagen-Sachkonto, repräsentieren aber die
    Hausgeld-Rücklagenzuführung (Einnahme, bereits in _zufuehrungen_nebenbuch
    erfasst) — keine Entnahme. Ohne den Ausschluss würde jede Rücklagen-Zahlung
    fälschlich zugleich als Entnahme gezählt.
    """
    summe = (
        buchungen_im_wj(objekt, wj)
        .filter(haben_konto__abrechnungsart=ba_nr)
        .exclude(haben_konto__kontonummer__startswith='41')
        .aggregate(s=Sum('betrag'))['s']
    )
    return summe or Decimal('0')
