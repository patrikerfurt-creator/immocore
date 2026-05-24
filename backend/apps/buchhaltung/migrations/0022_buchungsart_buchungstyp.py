from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0021_seed_buchungsarten'),
    ]

    operations = [
        migrations.AddField(
            model_name='buchungsart',
            name='buchungstyp',
            field=models.CharField(
                blank=True,
                choices=[
                    ('sachkonto', 'Sachkontenbuchung'),
                    ('personenkonto', 'Personenkontobuchung'),
                    ('kreditor', 'Kreditorenbuchung'),
                ],
                help_text='Buchungstyp für den Dialogbuchhaltung-Filter. Leer = nicht in der Dialogbuchhaltung wählbar.',
                max_length=20,
                null=True,
            ),
        ),
    ]
