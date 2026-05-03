from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rechnungen', '0003_rechnung_kundennummer_rechnung_vorgeschlagenes_konto_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='FreigabelimitDefault',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('grenzen', models.JSONField(default=list, verbose_name='Freigabe-Grenzen')),
            ],
            options={
                'verbose_name': 'Freigabelimit-Standard',
            },
        ),
    ]
