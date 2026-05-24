"""
Migration 0016 — Objekt Pipeline-Felder

Fügt bundesland, auto_pipeline_aktiv und auto_verbuchen_aktiv hinzu.
Alle drei Spalten existieren bereits in der DB (von einem anderen Branch) —
die DDL-Operationen sind daher idempotent (EXCEPTION WHEN duplicate_column).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('objekte', '0015_objekt_kurzbezeichnung'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='objekt',
                    name='bundesland',
                    field=models.CharField(
                        blank=True, default='', max_length=50,
                        verbose_name='Bundesland',
                        help_text='Bundesland für Feiertags-Berechnung (Auto-Pipeline)',
                    ),
                ),
                migrations.AddField(
                    model_name='objekt',
                    name='auto_pipeline_aktiv',
                    field=models.BooleanField(
                        default=False,
                        verbose_name='Auto-Pipeline aktiv',
                        help_text='Automatische monatliche Hausgeld-Sollstellung + SEPA-Lastschrift',
                    ),
                ),
                migrations.AddField(
                    model_name='objekt',
                    name='auto_verbuchen_aktiv',
                    field=models.BooleanField(
                        default=False,
                        verbose_name='Auto-Verbuchen aktiv',
                        help_text='Bankabgänge automatisch verbuchen wenn eindeutiger WKZ-Match',
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        DO $$
                        BEGIN
                            ALTER TABLE objekte_objekt
                                ADD COLUMN bundesland VARCHAR(50) NOT NULL DEFAULT '';
                        EXCEPTION WHEN duplicate_column THEN
                            ALTER TABLE objekte_objekt
                                ALTER COLUMN bundesland SET DEFAULT '';
                        END $$;

                        DO $$
                        BEGIN
                            ALTER TABLE objekte_objekt
                                ADD COLUMN auto_pipeline_aktiv BOOLEAN NOT NULL DEFAULT FALSE;
                        EXCEPTION WHEN duplicate_column THEN
                            ALTER TABLE objekte_objekt
                                ALTER COLUMN auto_pipeline_aktiv SET DEFAULT FALSE;
                        END $$;

                        DO $$
                        BEGIN
                            ALTER TABLE objekte_objekt
                                ADD COLUMN auto_verbuchen_aktiv BOOLEAN NOT NULL DEFAULT FALSE;
                        EXCEPTION WHEN duplicate_column THEN
                            ALTER TABLE objekte_objekt
                                ALTER COLUMN auto_verbuchen_aktiv SET DEFAULT FALSE;
                        END $$;
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
    ]
