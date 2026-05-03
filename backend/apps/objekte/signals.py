from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import Objekt


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



