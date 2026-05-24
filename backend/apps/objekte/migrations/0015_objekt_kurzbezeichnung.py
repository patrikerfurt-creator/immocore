"""
Migration 0015 — Objekt.kurzbezeichnung

Fügt das Feld kurzbezeichnung hinzu (für SEPA-Verwendungszweck, z. B. "WEG-MusterStr1").
Die DDL-Operation ist idempotent: Falls die Spalte bereits existiert (z. B. von einem
anderen Branch), wird der ADD COLUMN-Fehler still ignoriert.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('objekte', '0014_datenmigration_betreuer'),
    ]

    operations = [
        # State-Update: Django-ORM kennt das Feld
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='objekt',
                    name='kurzbezeichnung',
                    field=models.CharField(
                        blank=True,
                        default='',
                        help_text='Kurzkürzel für SEPA-Verwendungszweck, z. B. "WEG-RottPlatz14"',
                        max_length=50,
                        verbose_name='Kurzbezeichnung',
                    ),
                ),
            ],
            database_operations=[
                # Idempotent: ADD COLUMN IF NOT EXISTS + DEFAULT sichern
                migrations.RunSQL(
                    sql="""
                        DO $$
                        BEGIN
                            ALTER TABLE objekte_objekt
                                ADD COLUMN kurzbezeichnung VARCHAR(50) NOT NULL DEFAULT '';
                        EXCEPTION WHEN duplicate_column THEN
                            -- Spalte existiert bereits — sicherstellen dass DEFAULT gesetzt ist
                            ALTER TABLE objekte_objekt
                                ALTER COLUMN kurzbezeichnung SET DEFAULT '';
                        END
                        $$;
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
    ]
