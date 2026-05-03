import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0003_buchung_personenkonto'),
        ('konten', '0003_abrechnungsart'),
    ]

    operations = [
        # haben_konto nullable machen (Gesamtbuchung hat kein direktes Haben-Konto)
        migrations.AlterField(
            model_name='buchung',
            name='haben_konto',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='haben_buchungen',
                to='konten.konto',
            ),
        ),
        # parent_buchung für Sammelbuchung-Struktur
        migrations.AddField(
            model_name='buchung',
            name='parent_buchung',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='teilbuchungen',
                to='buchhaltung.buchung',
            ),
        ),
    ]
