"""
Umbau v1.1 (zweistufig): Der v1.0-Status 'in_freigabe' heißt in v1.1
'zur_freigabe' (Stufe 2 offen). Bestandsdaten dieses Branches umziehen.
Rein additive Korrektur — kein v1.2-Apparat betroffen.
"""
from django.db import migrations


def vorwaerts(apps, schema_editor):
    Rechnung = apps.get_model('rechnungen', 'Rechnung')
    Rechnung.objects.filter(status='in_freigabe').update(status='zur_freigabe')


def rueckwaerts(apps, schema_editor):
    Rechnung = apps.get_model('rechnungen', 'Rechnung')
    Rechnung.objects.filter(status='zur_freigabe').update(status='in_freigabe')


class Migration(migrations.Migration):

    dependencies = [
        ('rechnungen', '0017_alter_rechnung_status'),
    ]

    operations = [
        migrations.RunPython(vorwaerts, rueckwaerts),
    ]
