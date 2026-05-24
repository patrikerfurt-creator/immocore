"""
Migration 0017 — Bankkonto.zahlungsverkehr

Flag für Standard-Zahlungsverkehrskonto (SEPA pain.001).
Idempotent: ADD COLUMN IF NOT EXISTS via PL/pgSQL EXCEPTION-Block.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('objekte', '0016_objekt_pipeline_felder'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='bankkonto',
                    name='zahlungsverkehr',
                    field=models.BooleanField(
                        default=False,
                        verbose_name='Zahlungsverkehrskonto',
                        help_text='Standardkonto für ausgehende Zahlungen (SEPA pain.001)',
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        DO $$
                        BEGIN
                            ALTER TABLE objekte_bankkonto
                                ADD COLUMN zahlungsverkehr BOOLEAN NOT NULL DEFAULT FALSE;
                        EXCEPTION WHEN duplicate_column THEN
                            ALTER TABLE objekte_bankkonto
                                ALTER COLUMN zahlungsverkehr SET DEFAULT FALSE;
                        END $$;
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
    ]
