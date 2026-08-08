from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0047_wirtschaftsplanruecklage'),
    ]

    operations = [
        migrations.AlterField(
            model_name='hausgeldsollstellung',
            name='sollstellungs_typ',
            field=models.CharField(
                choices=[
                    ('hausgeld', 'Hausgeld'),
                    ('sonderumlage', 'Sonderumlage'),
                    ('abrechnungsergebnis', 'Abrechnungsergebnis'),
                    ('korrektur', 'Korrektur'),
                    ('saldovortrag', 'Saldovortrag'),
                ],
                max_length=20,
            ),
        ),
    ]
