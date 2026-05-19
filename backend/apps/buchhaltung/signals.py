from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='objekte.Bankkonto')
def bankkonto_iban_verknuepfen(sender, instance, **kwargs):
    """
    Verknüpft bereits importierte Kontoumsätze rückwirkend mit dem Bankkonto,
    wenn das Konto erst nach dem CAMT-Import angelegt wurde.
    Betroffen sind Umsätze, bei denen die empfaenger_iban übereinstimmt,
    aber bankkonto noch NULL ist.
    """
    from apps.buchhaltung.models import Kontoumsatz

    iban = (instance.iban or '').strip()
    if not iban:
        return

    qs = Kontoumsatz.objects.filter(empfaenger_iban=iban, bankkonto__isnull=True)
    if not qs.exists():
        return

    # Status 'unbekannt' → 'importiert' sobald Bankkonto + Objekt bekannt
    from django.db.models import Case, F, Value, When
    qs.update(
        bankkonto=instance,
        objekt=instance.objekt,
        status=Case(
            When(status='unbekannt', then=Value('importiert')),
            default=F('status'),
        ),
    )
