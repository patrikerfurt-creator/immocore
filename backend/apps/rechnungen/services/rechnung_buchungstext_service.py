"""
Buchungstext der OP-Buchung inkl. Debitornummer des Kostenverursachers
(Spec Kap. 6.2, Umbau v1.0).

Debitornummer = Personenkonto.kontonummer (V4), 4-stellig, führende Nullen.
Zugriffspfad (V4/V5): Einheit → aktives EigentumsVerhaeltnis → personenkonto.
Kein Property `aktuelles_eigentumsverhaeltnis` vorhanden → expliziter Filter.
"""
from django.db.models import Q


def _aktives_ev(einheit, stichtag=None):
    """Aktives EigentumsVerhaeltnis der Einheit.
    stichtag=None → heute aktiv (ende IS NULL);
    sonst der zum Stichtag laufende Vertrag (beginn <= stichtag <= ende|open)."""
    qs = einheit.eigentumsverhaeltnisse.all()
    if stichtag is None:
        return qs.filter(ende__isnull=True).first()
    return (
        qs.filter(beginn__lte=stichtag)
        .filter(Q(ende__isnull=True) | Q(ende__gte=stichtag))
        .order_by("-beginn")
        .first()
    )


def ermittle_debitor_nr(einheit, stichtag=None):
    """Debitornummer = Personenkonto.kontonummer (V4). Kann None sein, wenn
    kein aktives EV oder kein Personenkonto existiert (kein harter Fehler)."""
    ev = _aktives_ev(einheit, stichtag)
    pk = getattr(ev, "personenkonto", None) if ev else None
    return pk.kontonummer if pk else None


def einzelkosten_suffix(rechnung) -> str:
    """Zusatz ' | Einzelkosten PKto NNNN <einheit_nr> <Name>' für den
    Buchungstext, wenn ein Kostenverursacher gesetzt ist — sonst ''.
    Eigentümer/Debitor zum RECHNUNGSDATUM (Bestätigungspunkt B2)."""
    einheit = rechnung.kostenverursacher
    if not einheit:
        return ""
    stichtag = rechnung.rechnungsdatum  # B2: Eigentümer zum Rechnungsdatum
    ev = _aktives_ev(einheit, stichtag)
    debitor_nr = ermittle_debitor_nr(einheit, stichtag)
    name = ev.person.name if ev and ev.person_id and ev.person.name else "?"
    deb = f"PKto {debitor_nr} " if debitor_nr else ""
    return f" | Einzelkosten {deb}{einheit.einheit_nr} {name}"


def baue_buchungstext(rechnung) -> str:
    """Vollständiger OP-Buchungstext inkl. Debitor-Info (Spec 6.2)."""
    kreditor_name = rechnung.kreditor.name if rechnung.kreditor_id else "?"
    basis = f"OP Rechnung {rechnung.rechnungsnummer} – {kreditor_name}"
    return basis + einzelkosten_suffix(rechnung)
