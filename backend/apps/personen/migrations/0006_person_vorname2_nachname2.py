from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('personen', '0005_person_anrede'),
    ]

    operations = [
        migrations.AddField(
            model_name='person',
            name='vorname2',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='person',
            name='nachname2',
            field=models.CharField(blank=True, max_length=100),
        ),
    ]
