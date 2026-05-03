from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('personen', '0004_hausgeldhistorie_kontoart'),
    ]

    operations = [
        migrations.AddField(
            model_name='person',
            name='anrede',
            field=models.CharField(
                blank=True,
                choices=[
                    ('Herr', 'Herr'),
                    ('Frau', 'Frau'),
                    ('Eheleute', 'Eheleute'),
                    ('Herren', 'Herren'),
                    ('Damen', 'Damen'),
                    ('Herr und Frau', 'Herr und Frau'),
                    ('Firma', 'Firma'),
                    ('', '–'),
                ],
                default='',
                max_length=20,
            ),
        ),
    ]
