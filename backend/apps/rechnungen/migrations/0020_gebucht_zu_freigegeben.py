"""
Umbau v1.1 Phase D (Spec Kap. 10): Statuswert 'gebucht' entfällt —
Bestandsdaten nach 'freigegeben' migrieren ("Freigabe erteilt, OP gebucht").
'auto_freigabe' existierte in diesem Codebestand nie (V3).
"""
from django.db import migrations


def vorwaerts(apps, schema_editor):
    Rechnung = apps.get_model('rechnungen', 'Rechnung')
    Rechnung.objects.filter(status='gebucht').update(status='freigegeben')


def rueckwaerts(apps, schema_editor):
    Rechnung = apps.get_model('rechnungen', 'Rechnung')
    Rechnung.objects.filter(status='freigegeben').update(status='gebucht')


class Migration(migrations.Migration):

    dependencies = [
        ('rechnungen', '0019_alter_rechnung_status'),
    ]

    operations = [
        migrations.RunPython(vorwaerts, rueckwaerts),
    ]
