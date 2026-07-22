"""
Jahresabrechnung — Verteilerschlüssel-Auflösung je Konto (HGA-Spec v1.0 Kap. 4.3).

Read-only; wirft VerteilerschluesselFehler bei fehlenden Werten —
kein automatischer Fallback auf einen anderen Schlüssel (Spec Kap. 4.3 Fehlerfall).

Abweichungen zur Spec (siehe docs/HGA_PHASE0_VERIFIKATION.md, Punkt 2):
- KontoVerteilerSchluessel hat keinen wirtschaftsjahr-FK. Der aktive VS-Code
  wird über konto (hängt am WJ) + gueltig_ab aufgelöst; Fallback ist das
  Feld Konto.verteilerschluessel.
- Stammdaten-Werte (Fläche/MEA/Kopf) liegen nicht als Felder an der Einheit,
  sondern in VerteilerschluesselWert (wirtschaftsjahr=0 = zeitlos, ein
  jahresspezifischer Datensatz überschreibt den zeitlosen).
"""
from decimal import Decimal

from django.core.exceptions import ValidationError

from apps.konten.models import Konto, KontoVerteilerSchluessel
from apps.objekte.models import (
    Einheit,
    EinheitVerbrauch,
    Verteilerschluessel,
    VerteilerschluesselWert,
    Wirtschaftsjahr,
)

VERBRAUCH_VS_CODES = ('140', '141', '142', '143', '144', '145')


class VerteilerschluesselFehler(ValidationError):
    """Fehlender/unvollständiger Verteilerschlüssel — blockiert Schritt 6."""

    def __init__(self, konto: 'Konto | None', einheit: 'Einheit | None', vs_code: 'str | None', grund: str):
        self.konto = konto
        self.einheit = einheit
        self.vs_code = vs_code
        konto_str = f" für Konto {konto.kontonummer}" if konto else ''
        einheit_str = f" / Einheit {einheit.einheit_nr}" if einheit else ''
        super().__init__(
            f"Verteilerschlüssel {vs_code or '?'}{konto_str}{einheit_str}: {grund}"
        )


def aktiver_vs_code(konto: Konto, stichtag=None) -> str:
    """
    Aktiver VS-Code eines Kontos: jüngster KontoVerteilerSchluessel-Eintrag
    mit gueltig_ab <= stichtag (Default: WJ-Ende des Kontos), sonst
    Fallback auf Konto.verteilerschluessel.
    """
    if stichtag is None:
        stichtag = konto.wirtschaftsjahr.ende_datum
    zuordnung = (
        KontoVerteilerSchluessel.objects
        .filter(konto=konto, gueltig_ab__lte=stichtag)
        .order_by('-gueltig_ab')
        .first()
    )
    if zuordnung:
        return zuordnung.vs_code
    if konto.verteilerschluessel:
        return konto.verteilerschluessel
    raise VerteilerschluesselFehler(
        konto, None, None,
        "Kein Verteilerschlüssel zugeordnet (weder KontoVerteilerSchluessel noch Konto-Stammdaten).",
    )


def anteil_einheit(konto: Konto, einheit: Einheit, wj: Wirtschaftsjahr) -> Decimal:
    """
    Anteil der Einheit an den Kosten des Kontos (Spec Kap. 4.3):
    Anteil = Wert(Einheit) / Gesamtwert(Objekt) für den aktiven VS des Kontos.
    """
    vs_code = aktiver_vs_code(konto, stichtag=wj.ende_datum)
    try:
        return anteil_einheit_fuer_vs_code(vs_code, einheit, wj)
    except VerteilerschluesselFehler as exc:
        # Konto-Kontext ergänzen (anteil_einheit_fuer_vs_code kennt das Konto nicht)
        raise VerteilerschluesselFehler(konto, einheit, vs_code, exc.messages[0]) from exc


def anteil_einheit_fuer_vs_code(vs_code: str, einheit: Einheit, wj: Wirtschaftsjahr) -> Decimal:
    """
    Anteil der Einheit für einen konkreten VS-Code, unabhängig vom Konto.
    Wird auch vom ruecklagen_service genutzt (Anteil = Endbestand × MEA, Kap. 4.5).
    """
    if vs_code in VERBRAUCH_VS_CODES:
        wert, gesamt = _verbrauch_wert_und_gesamt(vs_code, einheit, wj)
    else:
        wert, gesamt = _stammdaten_wert_und_gesamt(vs_code, einheit, wj)
    if not gesamt:
        raise VerteilerschluesselFehler(
            None, einheit, vs_code,
            "Gesamtwert des Objekts ist 0 oder nicht ermittelbar.",
        )
    return Decimal(wert) / Decimal(gesamt)


def mea_anteil(einheit: Einheit, wj: Wirtschaftsjahr) -> Decimal:
    """MEA-Anteil der Einheit (VS 010) — für Rücklagen-Ausweis (Kap. 4.5)."""
    return anteil_einheit_fuer_vs_code('010', einheit, wj)


# ---------------------------------------------------------------------------
# intern
# ---------------------------------------------------------------------------

def _verbrauch_wert_und_gesamt(vs_code: str, einheit: Einheit, wj: Wirtschaftsjahr):
    """Verbrauchs-VS (140–145) aus EinheitVerbrauch. Fehlender Wert blockiert."""
    rows = EinheitVerbrauch.objects.filter(
        wirtschaftsjahr=wj, einheit__objekt=einheit.objekt, vs_code=vs_code,
    )
    werte = {r.einheit_id: r.wert for r in rows}
    if einheit.id not in werte or werte[einheit.id] is None:
        raise VerteilerschluesselFehler(
            None, einheit, vs_code,
            "Verbrauchswert fehlt — bitte VS-Import nachholen oder manuell erfassen.",
        )
    fehlende = [eid for eid, w in werte.items() if w is None]
    if fehlende:
        raise VerteilerschluesselFehler(
            None, einheit, vs_code,
            f"Verbrauchswerte unvollständig ({len(fehlende)} Einheit(en) ohne Wert).",
        )
    gesamt = sum(werte.values(), Decimal('0'))
    return werte[einheit.id], gesamt


def _stammdaten_wert_und_gesamt(vs_code: str, einheit: Einheit, wj: Wirtschaftsjahr):
    """
    Stammdaten-VS (Fläche/MEA/Kopf/Direkt) aus VerteilerschluesselWert.
    wirtschaftsjahr=0 gilt zeitlos; ein Datensatz mit wirtschaftsjahr=wj.jahr
    überschreibt den zeitlosen Wert.
    """
    vs_config = Verteilerschluessel.objects.filter(
        objekt=einheit.objekt, schluessel=vs_code, aktiv=True,
    ).first()
    if vs_config is None:
        raise VerteilerschluesselFehler(
            None, einheit, vs_code,
            "Verteilerschlüssel ist am Objekt nicht konfiguriert.",
        )
    rows = VerteilerschluesselWert.objects.filter(
        schluessel=vs_config, beteiligt=True,
        wirtschaftsjahr__in=(0, wj.jahr),
    ).order_by('einheit_id', 'wirtschaftsjahr')
    werte = {}
    for r in rows:  # jahresspezifisch (wj.jahr > 0) überschreibt zeitlos
        werte[r.einheit_id] = r.wert
    if einheit.id not in werte or werte[einheit.id] is None:
        raise VerteilerschluesselFehler(
            None, einheit, vs_code,
            "Kein Verteilerschlüssel-Wert für die Einheit hinterlegt.",
        )
    fehlende = [eid for eid, w in werte.items() if w is None]
    if fehlende:
        raise VerteilerschluesselFehler(
            None, einheit, vs_code,
            f"Verteilerschlüssel-Werte unvollständig ({len(fehlende)} Einheit(en) ohne Wert).",
        )
    gesamt = sum(werte.values(), Decimal('0'))
    return werte[einheit.id], gesamt
