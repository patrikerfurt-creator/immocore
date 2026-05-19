from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('massenimport', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='importjob',
            name='typ',
            field=models.CharField(
                choices=[
                    ('weg_objekt',      'WEG-Objekte'),
                    ('personen_import', 'Personen-Import'),
                ],
                default='weg_objekt',
                max_length=20,
            ),
        ),
    ]
