from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0022_buchungsart_buchungstyp'),
        ('objekte', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='camtimporteinstellung',
            name='objekt',
            field=models.ForeignKey(
                blank=True,
                help_text='Fallback-Objekt wenn die Empfänger-IBAN keinem Bankkonto zugeordnet werden kann.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='camt_einstellungen',
                to='objekte.objekt',
            ),
        ),
    ]
