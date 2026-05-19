"""Umbenennen wirtschaftsjahr (IntegerField) → wirtschaftsjahr_nr,
neues wirtschaftsjahr-FK (UUID) → Wirtschaftsjahr hinzufügen.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0015_buchung_erstellt_von_nullable'),
        ('objekte',     '0015_wirtschaftsjahr_einheitverbrauch'),
    ]

    operations = [
        migrations.RenameField(
            model_name='buchung',
            old_name='wirtschaftsjahr',
            new_name='wirtschaftsjahr_nr',
        ),
        migrations.AddField(
            model_name='buchung',
            name='wirtschaftsjahr',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='buchungen_wj',
                to='objekte.wirtschaftsjahr',
            ),
        ),
    ]
