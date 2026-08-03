import hashlib

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.dokumente.models import BelegnummerZaehler, Dokument


@transaction.atomic
def lege_rechnungsbeleg_ab(rechnung, datei_bytes: bytes, dateiname: str,
                           objekt, hochgeladen_von) -> Dokument:
    """Legt das Rechnungs-PDF genau einmal als Dokument ab und koppelt es an die Rechnung.

    Vergibt dabei die globale Belegnummer. Doppelte Ablage auf derselben
    Rechnung ist gesperrt (Idempotenzschutz über beleg_dokument).
    """
    if rechnung.beleg_dokument_id:
        raise ValidationError("Rechnung hat bereits einen Beleg.")

    dok = Dokument.objects.create(
        datei=ContentFile(datei_bytes, name=dateiname),
        dateiname=dateiname,
        kategorie='Beleg',
        dokument_typ='beleg',
        sha256=hashlib.sha256(datei_bytes).hexdigest(),
        revisionssicher=False,   # Sperre erst bei Freigabe (OP-Buchung)
        verknuepfung_typ='Rechnung',
        objekt=objekt,
        hochgeladen_von=hochgeladen_von,
        beleg_nummer=BelegnummerZaehler.naechste_nummer(),
    )
    rechnung.beleg_dokument = dok
    rechnung.save(update_fields=['beleg_dokument'])
    return dok


def sperre_beleg_revisionssicher(dokument: Dokument) -> Dokument:
    """Setzt die GoBD-Sperre (Löschen/Datei-Austausch) auf einem Beleg-Dokument. Idempotent."""
    if dokument.revisionssicher:
        return dokument
    dokument.revisionssicher = True
    dokument.revisionssicher_seit = timezone.now()
    dokument.save(update_fields=['revisionssicher', 'revisionssicher_seit'])
    return dokument
