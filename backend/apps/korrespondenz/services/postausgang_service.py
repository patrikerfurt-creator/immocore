"""Postausgang: Abfrage der Schreiben, die Aufmerksamkeit brauchen (Spec 7.2).

Standardansicht: ``zur_pruefung``, "nicht erzeugbar" (``entwurf`` mit ``fehler``)
und ``versand_fehlgeschlagen``. Schreiben eines Serienlaufs, der noch in
Vorschau/Prüfung ist, werden über den Serienlauf geprüft und tauchen hier
nicht auf (außer gezielt über ``serienlauf``).
"""
from django.db.models import Q

from apps.korrespondenz.models import Schreiben

from . import druckstapel_service

NICHT_ERZEUGBAR = 'nicht_erzeugbar'
ALLE = 'alle'
_ECHTE_STATUS = {s for s, _ in Schreiben.STATUS_CHOICES}


def _nicht_erzeugbar() -> Q:
    return Q(status='entwurf') & ~Q(fehler='')


def _status_filter(status: str) -> Q:
    """``status``: kommagetrennte Statuswerte, ``nicht_erzeugbar`` oder ``alle``; leer = Postausgang."""
    werte = [w.strip() for w in (status or '').split(',') if w.strip()]
    if not werte:
        return Q(status__in=('zur_pruefung', 'versand_fehlgeschlagen')) | _nicht_erzeugbar()
    if ALLE in werte:
        return Q()
    bedingung = Q()
    for wert in werte:
        if wert == NICHT_ERZEUGBAR:
            bedingung |= _nicht_erzeugbar()
        elif wert in _ECHTE_STATUS:
            bedingung |= Q(status=wert)
        else:
            raise ValueError(f'Unbekannter Status: {wert}')
    return bedingung


def postausgang(*, status: str = '', objekt=None, anlass: str = '', betreuer=None,
                serienlauf=None, druckbereit: bool = False):
    """Queryset der Schreiben im Postausgang, gefiltert nach Status, Objekt, Anlass, Betreuer.

    ``betreuer``: Objektbetreuer (User-Id) des Objekts. ``druckbereit``: nur
    Briefe, die auf den Druckstapel warten. Raises ``ValueError`` bei unbekanntem Status.
    """
    qs = Schreiben.objects.select_related(
        'vorlage_version__vorlage', 'empfaenger', 'objekt', 'einheit', 'dokument',
    )
    if druckbereit:
        qs = qs.filter(pk__in=druckstapel_service.druckbereite_schreiben().values('pk'))
    else:
        qs = qs.filter(_status_filter(status))
    if serienlauf is not None:
        qs = qs.filter(serienlauf=serienlauf)
    else:
        qs = qs.exclude(serienlauf__status__in=('vorschau', 'zur_pruefung'))
    if objekt is not None:
        qs = qs.filter(objekt=objekt)
    if anlass:
        qs = qs.filter(vorlage_version__vorlage__anlass=anlass)
    if betreuer is not None:
        qs = qs.filter(objekt__betreuer=betreuer)
    return qs.order_by('-erstellt_am')
