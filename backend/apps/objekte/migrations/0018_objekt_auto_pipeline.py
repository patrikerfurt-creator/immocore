from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('objekte', '0017_objekt_kurzbezeichnung'),
    ]

    operations = [
        migrations.AddField(
            model_name='objekt',
            name='auto_pipeline_aktiv',
            field=models.BooleanField(
                default=True,
                help_text='Deaktivieren um dieses Objekt aus der monatlichen Auto-Pipeline auszuschließen.',
                verbose_name='Auto-Pipeline aktiv',
            ),
        ),
        migrations.AddField(
            model_name='objekt',
            name='bundesland',
            field=models.CharField(
                default='HE',
                help_text='ISO-3166-2 Bundesland-Kürzel für Bankfeiertage (z.B. HE, BY, NW).',
                max_length=2,
                verbose_name='Bundesland (ISO)',
            ),
        ),
    ]
