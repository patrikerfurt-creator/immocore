from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from .models import Person, EigentumsVerhaeltnis


@receiver(pre_save, sender=Person)
def vergib_personennummer(sender, instance, **kwargs):
    if instance.personennummer:
        return
    last = Person.objects.exclude(personennummer='').order_by('-personennummer').first()
    if last:
        try:
            next_nr = int(last.personennummer) + 1
        except ValueError:
            next_nr = 100001
    else:
        next_nr = 100001
    instance.personennummer = str(next_nr)


@receiver(post_save, sender=EigentumsVerhaeltnis)
def create_personenkonto(sender, instance, created, **kwargs):
    """Erstellt automatisch Personenkonto + Unterkonten für jede Abrechnungsart."""
    if not created:
        return

    from apps.konten.models import Personenkonto, Unterkonto, Abrechnungsart

    objekt = instance.einheit.objekt

    last = Personenkonto.objects.filter(objekt=objekt).order_by('-kontonummer').first()
    if last:
        next_nr = str(int(last.kontonummer) + 1).zfill(4)
    else:
        next_nr = "0001"

    pk = Personenkonto.objects.create(
        objekt=objekt,
        eigentuemer=instance.person,
        vertrag=instance,
        kontonummer=next_nr,
        status='aktiv'
    )

    for abr in Abrechnungsart.objects.filter(objekt=objekt, aktiv=True).order_by('code'):
        Unterkonto.objects.create(
            personenkonto=pk,
            suffix=f'.{abr.code}',
            bezeichnung=abr.bezeichnung,
        )
