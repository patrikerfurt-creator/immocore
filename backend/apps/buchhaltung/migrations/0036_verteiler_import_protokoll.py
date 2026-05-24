from uuid import uuid4
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0035_kontoumsatz_kreditor_op_match'),
        ('objekte', '0019_ebanking_phase_a'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='VerteilerImportProtokoll',
            fields=[
                ('id', models.UUIDField(default=uuid4, editable=False, primary_key=True, serialize=False)),
                ('vs_code', models.CharField(max_length=3)),
                ('dateiname', models.CharField(max_length=255)),
                ('anzahl_aktualisiert', models.IntegerField()),
                ('importiert_am', models.DateTimeField(auto_now_add=True)),
                ('objekt', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='verteiler_importe',
                    to='objekte.objekt',
                )),
                ('wirtschaftsjahr', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='verteiler_importe',
                    to='objekte.wirtschaftsjahr',
                )),
                ('importiert_von', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='verteiler_importe',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Verteiler-Import-Protokoll',
                'verbose_name_plural': 'Verteiler-Import-Protokolle',
                'ordering': ['-importiert_am'],
            },
        ),
    ]
