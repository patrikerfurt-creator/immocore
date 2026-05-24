from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('objekte', '0015_wirtschaftsjahr_einheitverbrauch'),
    ]

    operations = [
        migrations.AddField(
            model_name='bankkonto',
            name='zahlungsverkehr',
            field=models.BooleanField(
                default=False,
                help_text='Standardkonto für Überweisungen – pro Objekt nur eines.',
                verbose_name='Für Zahlungsverkehr',
            ),
        ),
    ]
