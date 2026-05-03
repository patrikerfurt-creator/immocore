"""
Datenmigration: Bestehende Objekte erhalten betreuer = erster Superuser.
Banner-Hinweis zur Nachpflege wird über das Feld selbst (null=True) signalisiert.
"""
from django.db import migrations


def setze_default_betreuer(apps, schema_editor):
    Objekt = apps.get_model('objekte', 'Objekt')
    User = apps.get_model('auth', 'User')

    betreuer = User.objects.filter(is_superuser=True).order_by('id').first()
    if betreuer is None:
        betreuer = User.objects.order_by('id').first()
    if betreuer is None:
        return

    Objekt.objects.filter(betreuer__isnull=True).update(betreuer=betreuer)


class Migration(migrations.Migration):

    dependencies = [
        ('objekte', '0013_add_betreuer'),
    ]

    operations = [
        migrations.RunPython(setze_default_betreuer, migrations.RunPython.noop),
    ]
