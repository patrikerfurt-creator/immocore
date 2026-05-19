import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('personen', '0009_hausgeldhistorie_abrechnungsart'),
        ('buchhaltung', '0017_hausgeld_nebenbuch'),
    ]

    operations = [
        migrations.AddField(
            model_name='hausgeldhistorie',
            name='ba',
            field=models.ForeignKey(
                blank=True,
                help_text='Buchungsart aus dem Hausgeld-Nebenbuch (z.B. 900, 911)',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='hausgeld_historien',
                to='buchhaltung.buchungsart',
            ),
        ),
    ]
