import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0018_hausgeld_lauf_freigabe'),
    ]

    operations = [
        migrations.AddField(
            model_name='lastschriftlauf',
            name='hausgeld_sollstellungslauf',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='lastschrift_laeufe',
                to='buchhaltung.hausgeldsollstellungslauf',
            ),
        ),
    ]
