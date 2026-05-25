import logging

from django.db import transaction
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from .models import Objekt, VerteilerschluesselWert

logger = logging.getLogger(__name__)


_RANGES = {
    'WEG': (10001, 29999),
    'ZH':  (30001, 49999),
    'SEV': (50001, 69999),
}


@receiver(pre_save, sender=Objekt)
def vergib_objektnummer(sender, instance, **kwargs):
    """Vergibt automatisch eine 5-stellige Objektnummer beim ersten Speichern.
    WEG: 10001–29999, ZH: 30001–49999, SEV: 50001–69999
    """
    if instance.objektnummer:
        return

    start, max_nr = _RANGES.get(instance.objekt_typ, (10001, 29999))

    last = (
        Objekt.objects
        .filter(objekt_typ=instance.objekt_typ)
        .exclude(objektnummer='')
        .order_by('-objektnummer')
        .first()
    )
    if last:
        try:
            next_nr = int(last.objektnummer) + 1
        except ValueError:
            next_nr = start
    else:
        next_nr = start

    if next_nr > max_nr:
        raise ValueError(
            f'Nummernkreis für {instance.objekt_typ} erschöpft '
            f'(max. {max_nr})'
        )

    instance.objektnummer = str(next_nr)


def _recompute_wp_positionen_fuer_vs(instance: VerteilerschluesselWert) -> None:
    """Neuberechnung aller Entwurf-WP-Positionen, die vom geänderten VS-Wert abhängen."""
    from apps.abrechnung_wp.models import WirtschaftsplanPosition
    from apps.abrechnung_wp.services.wirtschaftsplan_service import (
        berechne_verteilung,
        _aktualisiere_gesamtsummen,
    )

    vs_code = instance.schluessel.schluessel
    objekt = instance.schluessel.objekt

    qs = WirtschaftsplanPosition.objects.filter(
        vs_code=vs_code,
        wirtschaftsplan__status='entwurf',
        wirtschaftsplan__wirtschaftsjahr__objekt=objekt,
    ).select_related('wirtschaftsplan__wirtschaftsjahr')

    # Bei WJ-spezifischen Werten (wirtschaftsjahr != 0) nur das betroffene WJ neu berechnen
    if instance.wirtschaftsjahr != 0:
        qs = qs.filter(wirtschaftsplan__wirtschaftsjahr__jahr=instance.wirtschaftsjahr)

    positionen = list(qs)
    if not positionen:
        return

    # Positionen nach WP gruppieren, damit _aktualisiere_gesamtsummen nur einmal je WP läuft
    wp_set = {}
    for pos in positionen:
        berechne_verteilung(pos)
        wp_set[pos.wirtschaftsplan_id] = pos.wirtschaftsplan

    for wp in wp_set.values():
        _aktualisiere_gesamtsummen(wp)

    logger.debug(
        'VS-Signal: %d WP-Positionen für VS %s (Objekt %s, WJ=%s) neu berechnet.',
        len(positionen), vs_code, objekt.objektnummer, instance.wirtschaftsjahr or 'zeitlos',
    )


@receiver(post_save, sender=VerteilerschluesselWert)
def vs_wert_geaendert(sender, instance, **kwargs):
    transaction.on_commit(lambda: _recompute_wp_positionen_fuer_vs(instance))


@receiver(post_delete, sender=VerteilerschluesselWert)
def vs_wert_geloescht(sender, instance, **kwargs):
    transaction.on_commit(lambda: _recompute_wp_positionen_fuer_vs(instance))



