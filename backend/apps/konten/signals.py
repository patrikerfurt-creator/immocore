from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Abrechnungsart


@receiver(post_save, sender=Abrechnungsart)
def sync_unterkonten_bei_neuer_abrechnungsart(sender, instance, created, **kwargs):
    """Neue Abrechnungsart → Unterkonto für alle aktiven Personenkonten des Objekts."""
    if not created:
        return
    from .models import Unterkonto
    suffix = f'.{instance.code}'
    for pk in instance.objekt.personenkonten.filter(status='aktiv'):
        Unterkonto.objects.get_or_create(
            personenkonto=pk,
            suffix=suffix,
            defaults={'bezeichnung': instance.bezeichnung}
        )
