from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0050_buchungsart_saldovortrag'),
    ]

    operations = [
        migrations.AddField(
            model_name='wiederkehrendebuchungvorlage',
            name='zahlweg',
            field=models.CharField(
                choices=[
                    ('lastschrift', 'Lastschrift (Kreditor zieht ein)'),
                    ('ueberweisung', 'Überweisung (manuell zahlen)'),
                ],
                default='lastschrift',
                help_text=(
                    'lastschrift: Kreditor zieht ein (Match über camt). '
                    'ueberweisung: Zahlung wird manuell über den Zahlungsverkehr veranlasst.'
                ),
                max_length=12,
            ),
        ),
        migrations.AlterField(
            model_name='wiederkehrendebuchungop',
            name='status',
            field=models.CharField(
                choices=[
                    ('erzeugt', 'Erzeugt'),
                    ('bescheid_fehlt', 'Bescheid fehlt'),
                    ('ueberweisung_veranlasst', 'Überweisung veranlasst'),
                    ('bankabgang_erfolgt', 'Bankabgang erfolgt'),
                    ('abweichend_geklaert', 'Abweichend (geklärt)'),
                    ('verworfen', 'Verworfen'),
                ],
                default='erzeugt',
                max_length=25,
            ),
        ),
    ]
