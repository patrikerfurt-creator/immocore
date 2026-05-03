from django.db import migrations, models
import django.db.models.deletion
from uuid import uuid4


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0010_camt_global_kontoumsatz_objekt_nullable'),
    ]

    operations = [
        migrations.CreateModel(
            name='CamtImportLog',
            fields=[
                ('id', models.UUIDField(default=uuid4, editable=False, primary_key=True, serialize=False)),
                ('zeitpunkt', models.DateTimeField(auto_now_add=True)),
                ('import_ordner', models.CharField(blank=True, max_length=500)),
                ('anzahl_dateien', models.IntegerField(default=0)),
                ('anzahl_importiert', models.IntegerField(default=0)),
                ('anzahl_duplikate', models.IntegerField(default=0)),
                ('anzahl_erkannt', models.IntegerField(default=0)),
                ('anzahl_fehler', models.IntegerField(default=0)),
                ('fehler_details', models.JSONField(blank=True, default=list)),
                ('einstellung', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='logs',
                    to='buchhaltung.camtimporteinstellung',
                )),
            ],
            options={
                'verbose_name': 'CAMT-Import-Log',
                'verbose_name_plural': 'CAMT-Import-Logs',
                'ordering': ['-zeitpunkt'],
            },
        ),
    ]
