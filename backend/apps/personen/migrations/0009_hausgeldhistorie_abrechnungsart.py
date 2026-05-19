from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('personen', '0008_briefanrede2'),
        ('konten', '0005_data_migration_wj'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Neues FK-Feld abrechnungsart (nullable, wird durch Import gesetzt)
        migrations.AddField(
            model_name='hausgeldhistorie',
            name='abrechnungsart',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='hausgeld_eintraege',
                to='konten.abrechnungsart',
                help_text='z.B. 900 (Hausgeld), 911 (Rücklage I)',
            ),
        ),

        # 2. Neue Felder
        migrations.AddField(
            model_name='hausgeldhistorie',
            name='wirtschaftsplan_jahr',
            field=models.PositiveIntegerField(
                blank=True, null=True,
                help_text='Wirtschaftsplan-Jahr, das diese Änderung ausgelöst hat.',
            ),
        ),
        migrations.AddField(
            model_name='hausgeldhistorie',
            name='quelle',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('wizard',             'Wizard'),
                    ('csv_import',         'CSV-Import'),
                    ('massenimport',       'Massenimport'),
                    ('manuell',            'Manuelle Pflege'),
                    ('eigentuemerwechsel', 'Eigentümerwechsel'),
                ],
                default='manuell',
            ),
        ),
        migrations.AddField(
            model_name='hausgeldhistorie',
            name='bemerkung',
            field=models.CharField(max_length=200, blank=True, default=''),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='hausgeldhistorie',
            name='erstellt_am',
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),

        # 3. related_name von hausgeld_historie → hausgeld_eintraege
        migrations.AlterField(
            model_name='hausgeldhistorie',
            name='eigentumsverhaeltnis',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='hausgeld_eintraege',
                to='personen.eigentumsverhaeltnis',
            ),
        ),

        # 4. kontoart entfernen
        migrations.RemoveField(
            model_name='hausgeldhistorie',
            name='kontoart',
        ),

        # 5. Ordering + Index aktualisieren
        migrations.AlterModelOptions(
            name='hausgeldhistorie',
            options={
                'verbose_name': 'Hausgeld-Historie',
                'verbose_name_plural': 'Hausgeld-Historien',
                'ordering': ['eigentumsverhaeltnis', 'abrechnungsart', '-gueltig_ab'],
            },
        ),

        # 6. Index hinzufügen
        migrations.AddIndex(
            model_name='hausgeldhistorie',
            index=models.Index(
                fields=['eigentumsverhaeltnis', 'abrechnungsart', '-gueltig_ab'],
                name='idx_hausgeld_ev_abr_datum',
            ),
        ),

        # 7. UniqueConstraint (eigentumsverhaeltnis, abrechnungsart, gueltig_ab)
        migrations.AddConstraint(
            model_name='hausgeldhistorie',
            constraint=models.UniqueConstraint(
                fields=['eigentumsverhaeltnis', 'abrechnungsart', 'gueltig_ab'],
                name='uniq_historie_je_vertrag_abrart_datum',
            ),
        ),

        # 8. UniqueConstraint auf EigentumsVerhaeltnis (ein aktiver Vertrag je Einheit)
        migrations.AddConstraint(
            model_name='eigentumsverhaeltnis',
            constraint=models.UniqueConstraint(
                fields=['einheit'],
                condition=models.Q(ende__isnull=True),
                name='uniq_aktiver_vertrag_je_einheit',
            ),
        ),
    ]
