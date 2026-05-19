import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0025_autopilot_user'),
        ('objekte', '0018_objekt_auto_pipeline'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        # lauf_quelle für HausgeldSollstellungslauf
        migrations.AddField(
            model_name='hausgeldsollstellungslauf',
            name='lauf_quelle',
            field=models.CharField(
                choices=[('manuell', 'Manuell'), ('autopilot', 'Autopilot')],
                default='manuell',
                max_length=10,
                verbose_name='Lauf-Quelle',
            ),
        ),
        # UniqueConstraint: pro (Objekt, Periode, Quelle) nur ein commited-Lauf
        migrations.AddConstraint(
            model_name='hausgeldsollstellungslauf',
            constraint=models.UniqueConstraint(
                condition=models.Q(status='commited'),
                fields=['objekt', 'periode', 'lauf_quelle'],
                name='unique_commited_lauf_pro_periode_quelle',
            ),
        ),
        # lauf_quelle für LastschriftLauf
        migrations.AddField(
            model_name='lastschriftlauf',
            name='lauf_quelle',
            field=models.CharField(
                choices=[('manuell', 'Manuell'), ('autopilot', 'Autopilot')],
                default='manuell',
                max_length=10,
                verbose_name='Lauf-Quelle',
            ),
        ),
        # datei_pfad für LastschriftLauf
        migrations.AddField(
            model_name='lastschriftlauf',
            name='datei_pfad',
            field=models.CharField(
                blank=True,
                max_length=500,
                null=True,
                verbose_name='pain.008-Dateipfad',
            ),
        ),
        # Neue Tabelle AutoLaufProtokoll
        migrations.CreateModel(
            name='AutoLaufProtokoll',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('ausgefuehrt_am', models.DateTimeField()),
                ('periode', models.DateField()),
                ('status', models.CharField(
                    choices=[
                        ('erfolg', 'Erfolg'),
                        ('teilweise_erfolg', 'Teilweise Erfolg'),
                        ('fehler', 'Fehler'),
                        ('uebersprungen', 'Übersprungen'),
                    ],
                    max_length=20,
                )),
                ('anzahl_evs_geplant', models.IntegerField(default=0)),
                ('anzahl_evs_erfolgreich', models.IntegerField(default=0)),
                ('anzahl_evs_uebersprungen', models.IntegerField(default=0)),
                ('summe_sollstellungen', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('summe_lastschrift', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('datei_pfad', models.CharField(blank=True, max_length=500, null=True)),
                ('warnungen', models.JSONField(blank=True, default=list)),
                ('fehler', models.TextField(blank=True, null=True)),
                ('objekt', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='auto_lauf_protokolle',
                    to='objekte.objekt',
                )),
                ('sollstellungslauf', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='auto_lauf_protokolle',
                    to='buchhaltung.hausgeldsollstellungslauf',
                )),
                ('lastschriftlauf', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='auto_lauf_protokolle',
                    to='buchhaltung.lastschriftlauf',
                )),
            ],
            options={
                'verbose_name': 'Auto-Lauf-Protokoll',
                'verbose_name_plural': 'Auto-Lauf-Protokolle',
                'ordering': ['-ausgefuehrt_am'],
            },
        ),
    ]
