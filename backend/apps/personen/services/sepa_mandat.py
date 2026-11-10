"""
Resolver: welches SEPA-Mandat gilt für ein Eigentumsverhältnis (EV)?

Rangfolge (R2), ausschliesslich in ``_waehle`` implementiert:

1. aktives Mandat mit ``eigentumsverhaeltnis_id == ev.id`` (Einheitenmandat)
2. aktives Mandat mit ``person_id == ev.person_id`` und
   ``eigentumsverhaeltnis_id IS NULL`` (Sammelmandat)
3. Legacy-Rückfall: ``ev.person.sepa_mandat``, sofern aktiv,
   ``eigentumsverhaeltnis_id IS NULL`` und ``person_id in (None, ev.person_id)``
4. ``None``

"Aktiv" bedeutet ausschliesslich ``SEPAMandat.aktiv=True``. Die Aktivität des
EV (beginn/ende) prüft der Resolver nicht — die Fälligkeit entscheidet der
Sollstellungslauf.

Keine Importe aus buchhaltung/portal (Zyklusvermeidung).
"""
from __future__ import annotations

from typing import Iterable, Optional
from uuid import UUID

from django.db.models import Q

from apps.personen.models import EigentumsVerhaeltnis, Person, SEPAMandat


def _waehle(
    spezifisch: Optional[SEPAMandat],
    sammel: Optional[SEPAMandat],
    legacy: Optional[SEPAMandat],
    person_id: Optional[UUID],
) -> Optional[SEPAMandat]:
    """
    Wendet die Rangfolge R2 an.

    spezifisch: aktives Einheitenmandat des EV (oder None)
    sammel:     aktives Sammelmandat der Person (oder None)
    legacy:     Mandat aus ``Person.sepa_mandat`` (oder None)
    person_id:  ID der Person, für die aufgelöst wird (Legacy-Besitzprüfung)
    """
    if spezifisch is not None and spezifisch.aktiv:
        return spezifisch
    if sammel is not None and sammel.aktiv:
        return sammel
    if (
        legacy is not None
        and legacy.aktiv
        and legacy.eigentumsverhaeltnis_id is None
        and legacy.person_id in (None, person_id)
    ):
        return legacy
    return None


def mandate_fuer_evs(
    evs: Iterable[EigentumsVerhaeltnis],
) -> dict[UUID, Optional[SEPAMandat]]:
    """
    Löst für alle übergebenen EVs das geltende Mandat auf (eine DB-Abfrage).

    Rangfolge: Einheitenmandat > Sammelmandat der Person > Legacy-Rückfall
    über ``Person.sepa_mandat`` > None (siehe Modul-Docstring).

    Aufrufer müssen ``ev.person`` per ``select_related`` geladen haben, sonst
    entsteht je EV ein zusätzlicher Query (für ``person.sepa_mandat_id``).

    Returns: {ev.id: SEPAMandat | None} — jede übergebene EV-ID ist enthalten.
    """
    ev_liste = list(evs)
    if not ev_liste:
        return {}

    ev_ids = {ev.id for ev in ev_liste}
    person_ids = {ev.person_id for ev in ev_liste}
    legacy_ids = {
        ev.person.sepa_mandat_id for ev in ev_liste
        if ev.person.sepa_mandat_id is not None
    }

    treffer = SEPAMandat.objects.filter(aktiv=True).filter(
        Q(eigentumsverhaeltnis_id__in=ev_ids)
        | Q(person_id__in=person_ids, eigentumsverhaeltnis__isnull=True)
        | Q(id__in=legacy_ids)
    )

    je_ev: dict[UUID, SEPAMandat] = {}
    je_person: dict[UUID, SEPAMandat] = {}
    je_id: dict[UUID, SEPAMandat] = {}
    for mandat in treffer:
        je_id[mandat.id] = mandat
        if mandat.eigentumsverhaeltnis_id is not None:
            je_ev[mandat.eigentumsverhaeltnis_id] = mandat
        elif mandat.person_id is not None:
            je_person[mandat.person_id] = mandat

    return {
        ev.id: _waehle(
            je_ev.get(ev.id),
            je_person.get(ev.person_id),
            je_id.get(ev.person.sepa_mandat_id),
            ev.person_id,
        )
        for ev in ev_liste
    }


def mandat_fuer_ev(ev: EigentumsVerhaeltnis) -> Optional[SEPAMandat]:
    """Geltendes Mandat für ein einzelnes EV (siehe ``mandate_fuer_evs``)."""
    return mandate_fuer_evs([ev])[ev.id]


def sammelmandat_fuer_person(person: Person) -> Optional[SEPAMandat]:
    """
    Aktives Sammelmandat der Person (Schritte 2 und 3 der Rangfolge):
    aktives Mandat mit ``person_id`` und ohne EV, sonst der Legacy-Rückfall
    ``person.sepa_mandat`` (aktiv, EV NULL, ``person_id in (None, person.id)``).
    Einheitenmandate werden nie geliefert.
    """
    sammel = SEPAMandat.objects.filter(
        person_id=person.id, eigentumsverhaeltnis__isnull=True, aktiv=True,
    ).first()
    legacy = person.sepa_mandat if person.sepa_mandat_id is not None else None
    return _waehle(None, sammel, legacy, person.id)
