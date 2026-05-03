import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0002_buchungsmodul'),
        ('konten', '0003_abrechnungsart'),
    ]

    operations = [
        migrations.AddField(
            model_name='buchung',
            name='personenkonto',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='hauptbuchungen',
                to='konten.personenkonto',
            ),
        ),
    ]
