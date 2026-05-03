"""
v1.2: erkennungs_stufe CharField (1/2a/2b/3), routing_ziel,
      RechnungsBearbeitungsLock, Frontoffice-Gruppe,
      log-Felder routing_ziel + auto_gebucht.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('rechnungen', '0006_kreditor_add_bic'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── 1. erkennungs_stufe: IntegerField → CharField ──────────────────
        migrations.RemoveField(model_name='rechnung', name='erkennungs_stufe'),
        migrations.AddField(
            model_name='rechnung',
            name='erkennungs_stufe',
            field=models.CharField(
                blank=True, max_length=3, null=True,
                choices=[
                    ('1',  'Stufe 1 — Erkannt'),
                    ('2a', 'Stufe 2a — Prüffall (Objekt erkannt → Objektbetreuer)'),
                    ('2b', 'Stufe 2b — Prüffall (nur Kreditor → Frontoffice)'),
                    ('3',  'Stufe 3 — Nicht erkannt (Frontoffice)'),
                ],
            ),
        ),
        # ── 2. routing_ziel auf Rechnung ────────────────────────────────────
        migrations.AddField(
            model_name='rechnung',
            name='routing_ziel',
            field=models.CharField(
                blank=True, max_length=20,
                choices=[
                    ('limit_workflow', 'Limit-Workflow'),
                    ('objektbetreuer', 'Objektbetreuer'),
                    ('frontoffice',    'Frontoffice-Inbox'),
                ],
                help_text='Ergebnis Phase B',
            ),
        ),
        # ── 3. RechnungsErkennungsLog: stufe CharField, neue Felder ─────────
        migrations.RemoveField(model_name='rechnungserkennungslog', name='stufe'),
        migrations.AddField(
            model_name='rechnungserkennungslog',
            name='stufe',
            field=models.CharField(blank=True, max_length=3, null=True),
        ),
        migrations.AddField(
            model_name='rechnungserkennungslog',
            name='routing_ziel',
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name='rechnungserkennungslog',
            name='auto_gebucht',
            field=models.BooleanField(default=False),
        ),
        # ── 4. RechnungsBearbeitungsLock ─────────────────────────────────────
        migrations.CreateModel(
            name='RechnungsBearbeitungsLock',
            fields=[
                ('rechnung', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    primary_key=True, serialize=False,
                    related_name='bearbeitungslock',
                    to='rechnungen.rechnung',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='rechnungs_locks',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('gueltig_bis', models.DateTimeField()),
                ('erstellt_am', models.DateTimeField(auto_now_add=True)),
            ],
            options={'verbose_name': 'Bearbeitungs-Lock'},
        ),
        # ── 5. Frontoffice-Gruppe (Daten-Migration) ──────────────────────────
        migrations.RunPython(
            code=lambda apps, schema_editor: apps.get_model('auth', 'Group').objects.get_or_create(name='Frontoffice'),
            reverse_code=migrations.RunPython.noop,
        ),
    ]
