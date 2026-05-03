import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0004_buchung_sammelbuchung'),
        ('konten', '0003_abrechnungsart'),
    ]

    operations = [
        # soll_konto nullable machen (Gesamt-Buchung hat kein Sachkonto auf Soll-Seite)
        migrations.AlterField(
            model_name='buchung',
            name='soll_konto',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='soll_buchungen',
                to='konten.konto',
            ),
        ),
        # Unterkonto auf Soll-Seite (für Teilbuchungen: 0001.900 an 41900)
        migrations.AddField(
            model_name='buchung',
            name='soll_unterkonto',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='soll_buchungen',
                to='konten.unterkonto',
            ),
        ),
    ]
