"""
Service: Hausgeld-Historie verwalten (Wirtschaftsplan-Spec v1.2, Kap. 6.1).
"""
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction


@transaction.atomic
def setze_neue_saetze(
    ev,
    gueltig_ab: date,
    saetze_je_ba: list,
    quelle: str,
    beschluss,
    import_referenz,
    user,
) -> list:
    """
    Schließt bestehende offene Einträge pro BA (gueltig_bis = gueltig_ab - 1 Tag).
    Legt pro BA einen neuen HausgeldHistorie-Eintrag an.

    saetze_je_ba: list of (Buchungsart, Decimal)
    Returns: Liste der neu angelegten HausgeldHistorie-Einträge.
    """
    from apps.personen.models import HausgeldHistorie

    if quelle == 'import' and not settings.HAUSGELD_IMPORT_QUELLE_ERLAUBT:
        raise ValidationError(
            "Import-Quelle nicht erlaubt — Initialimport bereits abgeschlossen."
        )
    if quelle == 'beschluss' and beschluss is None:
        raise ValidationError("quelle='beschluss' erfordert beschluss-FK")
    if quelle == 'import' and not import_referenz:
        raise ValidationError("quelle='import' erfordert import_referenz")

    neue_eintraege = []
    vortag = gueltig_ab - timedelta(days=1)

    for ba, betrag in saetze_je_ba:
        HausgeldHistorie.objects.filter(
            eigentumsverhaeltnis=ev,
            ba=ba,
            gueltig_bis__isnull=True,
        ).update(gueltig_bis=vortag)

        HausgeldHistorie.objects.filter(
            eigentumsverhaeltnis=ev,
            ba=ba,
            gueltig_bis__gte=gueltig_ab,
        ).update(gueltig_bis=vortag)

        neuer_eintrag = HausgeldHistorie.objects.create(
            eigentumsverhaeltnis=ev,
            ba=ba,
            gueltig_ab=gueltig_ab,
            gueltig_bis=None,
            betrag=betrag,
            quelle=quelle,
            beschluss=beschluss,
            import_referenz=import_referenz,
            erstellt_von=user,
        )
        neue_eintraege.append(neuer_eintrag)

    return neue_eintraege
