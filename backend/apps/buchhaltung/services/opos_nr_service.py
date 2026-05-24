from django.db import transaction

from apps.buchhaltung.models import OposSequenz


def luhn_pruefziffer(basis: str) -> int:
    """Standard-Luhn-Algorithmus (Mod-10) über alle Ziffern."""
    summe = 0
    for i, ziffer in enumerate(reversed(basis)):
        n = int(ziffer)
        if i % 2 == 0:
            n *= 2
            if n > 9:
                n -= 9
        summe += n
    return (10 - summe % 10) % 10


def validiere_opos_nr(opos_nr: str) -> bool:
    if len(opos_nr) != 15 or not opos_nr.isdigit():
        return False
    return luhn_pruefziffer(opos_nr[:14]) == int(opos_nr[14])


@transaction.atomic
def naechste_opos_nr(objekt) -> str:
    """Race-sichre OPOS-Nummern-Vergabe via SELECT FOR UPDATE."""
    seq, _ = OposSequenz.objects.get_or_create(objekt=objekt)
    seq = OposSequenz.objects.select_for_update().get(objekt=objekt)
    lfd = seq.naechste_lfd_nr
    seq.naechste_lfd_nr = lfd + 1
    seq.save(update_fields=['naechste_lfd_nr'])

    objekt_nr = str(objekt.objektnummer).zfill(6)
    lfd_str   = str(lfd).zfill(8)
    basis     = objekt_nr + lfd_str
    pruefz    = luhn_pruefziffer(basis)
    return basis + str(pruefz)
