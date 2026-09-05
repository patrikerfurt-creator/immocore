"""Bestandsdaten: Erstaktivierung fuer bereits eingeloggte Zugaenge nachziehen.

Bis einschliesslich Spec-1a-Stand setzte ``melde_an`` ``erstaktivierung_am``
nur beim Einloesen eines EINLADUNGS-Tokens. Wer den 72-Stunden-Link
verfallen liess und sich danach per Magic Link anmeldete, blieb in der
Verwaltungsansicht dauerhaft auf "Eingeladen — noch nicht aktiviert"
stehen, obwohl das Portal nachweislich genutzt wurde.

Als Aktivierungszeitpunkt wird ``letzter_login`` uebernommen: der exakte
erste Login ist rueckwirkend nicht rekonstruierbar (Sessions werden beim
Abmelden geloescht), und ``letzter_login`` ist der einzige belastbare
Nachweis, dass der Zugang tatsaechlich benutzt wurde.
"""
from django.db import migrations
from django.db.models import F


def nachziehen(apps, schema_editor):
    PortalZugang = apps.get_model('portal', 'PortalZugang')
    (
        PortalZugang.objects
        .filter(erstaktivierung_am__isnull=True, letzter_login__isnull=False)
        .update(erstaktivierung_am=F('letzter_login'))
    )


def zurueck(apps, schema_editor):
    """Nicht umkehrbar ohne Datenverlust — bewusst ein No-Op.

    Ein Rueckwaertslauf duerfte nur die hier gesetzten Werte entfernen,
    nicht die zwischenzeitlich echt erfassten; unterscheiden lassen sie
    sich nicht.
    """


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(nachziehen, zurueck),
    ]
