from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('personen', '0010_hausgeldhistorie_ba'),
    ]

    operations = [
        migrations.AddField(
            model_name='sepamandat',
            name='sequence_type',
            field=models.CharField(
                choices=[('RCUR', 'Wiederkehrend (RCUR)'), ('FRST', 'Erstlastschrift (FRST)')],
                default='RCUR',
                max_length=4,
                verbose_name='Sequenz-Typ',
            ),
        ),
    ]
