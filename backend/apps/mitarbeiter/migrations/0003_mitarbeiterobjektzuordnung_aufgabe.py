from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mitarbeiter', '0002_mitarbeiter_objekt_zuordnung'),
    ]

    operations = [
        migrations.AddField(
            model_name='mitarbeiterobjektzuordnung',
            name='aufgabe',
            field=models.CharField(
                blank=True,
                choices=[
                    ('objektmanagement', 'Objektmanagement'),
                    ('buchhaltung',      'Buchhaltung'),
                    ('frontoffice',      'Frontoffice'),
                    ('backoffice',       'Backoffice'),
                    ('fm_management',    'FM-Management'),
                    ('geschaeftsfuehrer','Geschäftsführer'),
                    ('prokurist',        'Prokurist'),
                    ('auszubildender',   'Auszubildender'),
                ],
                default='',
                max_length=50,
                verbose_name='Aufgabe im Objekt',
            ),
        ),
    ]
