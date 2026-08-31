"""
Einheiten-Ansicht des Portals (Spec 1a, Kap. 6.1).

Liefert die WEGs und Einheiten des eingeloggten Eigentümers — bewusst NUR
Stammdaten je Einheit. Kein Saldo, keine Buchungen: das ist ausdrücklich
Spec 1 (vollständig) vorbehalten.
"""
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from apps.objekte.models import Verteilerschluessel, VerteilerschluesselWert
from apps.personen.models import EigentumsVerhaeltnis, Person


def _mea_werte(objekt_ids: list) -> dict:
    """MEA je Einheit über alle beteiligten Objekte.

    Der Miteigentumsanteil ist im realen Datenmodell kein Feld auf
    ``Einheit``, sondern der Wert im Verteilerschlüssel mit
    ``vs_typ='mea'`` (gleiche Ermittlung wie im Stimmkraft-Service der
    Eigentümerversammlung).

    ``wirtschaftsjahr=0`` bedeutet "zeitlos" und ist der Regelfall für MEA.
    Existiert kein zeitloser Wert, wird der jüngste jahresbezogene Wert
    genommen, damit die Einheit nicht ohne MEA dasteht.
    """
    schluessel_ids = list(
        Verteilerschluessel.objects
        .filter(objekt_id__in=objekt_ids, vs_typ='mea', aktiv=True)
        .order_by('objekt_id', 'schluessel')
        .values_list('id', flat=True)
    )
    if not schluessel_ids:
        return {}

    ergebnis: dict = {}
    beste_jahre: dict = {}
    for einheit_id, jahr, wert in (
        VerteilerschluesselWert.objects
        .filter(schluessel_id__in=schluessel_ids, beteiligt=True, wert__isnull=False)
        .values_list('einheit_id', 'wirtschaftsjahr', 'wert')
    ):
        # Zeitloser Wert (Jahr 0) schlägt jeden jahresbezogenen Wert.
        vorrang = 10**9 if jahr == 0 else jahr
        if einheit_id not in beste_jahre or vorrang > beste_jahre[einheit_id]:
            beste_jahre[einheit_id] = vorrang
            ergebnis[einheit_id] = Decimal(wert)
    return ergebnis


def meine_einheiten(person: Person) -> list[dict]:
    """WEG-Karten mit ihren Einheiten (Mockup-Struktur, Spec Kap. 6.1).

    Nur AKTUELLE Eigentumsverhältnisse: ``ende`` leer oder in der Zukunft.
    Ein Voreigentümer soll nach dem Verkauf keine Einheitsdaten mehr sehen.
    """
    heute = timezone.localdate()
    verhaeltnisse = (
        EigentumsVerhaeltnis.objects
        .filter(person=person, beginn__lte=heute)
        .filter(Q(ende__isnull=True) | Q(ende__gte=heute))
        .select_related('einheit', 'einheit__objekt')
        .order_by('einheit__objekt__bezeichnung', 'einheit__einheit_nr')
    )

    objekt_ids = {ev.einheit.objekt_id for ev in verhaeltnisse}
    mea = _mea_werte(list(objekt_ids))

    karten: dict = {}
    for ev in verhaeltnisse:
        einheit = ev.einheit
        objekt = einheit.objekt
        karte = karten.setdefault(objekt.id, {
            'objekt_id': str(objekt.id),
            'objektnummer': objekt.objektnummer,
            'bezeichnung': objekt.bezeichnung,
            'strasse': objekt.strasse,
            'plz': objekt.plz,
            'ort': objekt.ort,
            'einheiten': [],
        })
        karte['einheiten'].append({
            'einheit_id': str(einheit.id),
            'einheit_nr': einheit.einheit_nr,
            'lage': einheit.lage,
            'nutzungsart': einheit.einheit_typ,
            'miteigentumsanteil': mea.get(einheit.id),
            'eigentum_seit': ev.beginn,
            'eigentum_bis': ev.ende,
        })

    return list(karten.values())
