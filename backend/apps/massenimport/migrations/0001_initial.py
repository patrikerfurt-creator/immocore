import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ImportJob',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('typ', models.CharField(
                    choices=[('weg_objekt', 'WEG-Objekte')],
                    default='weg_objekt',
                    max_length=20,
                )),
                ('datei_pfad',      models.CharField(blank=True, max_length=500)),
                ('status', models.CharField(
                    choices=[
                        ('pending',   'Ausstehend'),
                        ('parsed',    'Vorschau bereit'),
                        ('committed', 'Übernommen'),
                        ('failed',    'Fehlgeschlagen'),
                        ('partial',   'Teilweise übernommen'),
                    ],
                    default='pending',
                    max_length=20,
                )),
                ('preview_token',  models.UUIDField(blank=True, null=True, unique=True)),
                ('zeilen_gesamt',  models.PositiveIntegerField(default=0)),
                ('zeilen_ok',      models.PositiveIntegerField(default=0)),
                ('zeilen_warnung', models.PositiveIntegerField(default=0)),
                ('zeilen_fehler',  models.PositiveIntegerField(default=0)),
                ('ergebnis',       models.JSONField(default=dict)),
                ('erstellt_am',    models.DateTimeField(auto_now_add=True)),
                ('aktualisiert_am', models.DateTimeField(auto_now=True)),
                ('erstellt_von', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='import_jobs',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Import-Job',
                'verbose_name_plural': 'Import-Jobs',
                'ordering': ['-erstellt_am'],
            },
        ),
    ]
