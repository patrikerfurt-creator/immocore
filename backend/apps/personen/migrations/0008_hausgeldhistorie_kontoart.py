"""
Migration 0008 — HausgeldHistorie.kontoart + CHECK-Constraint entfernen

Die Tabelle personen_hausgeldhistorie wurde im Wirtschaftsjahr-Branch
grundlegend umgebaut:
  - kontoart (VARCHAR) wurde entfernt und durch abrechnungsart_id FK ersetzt
  - wirtschaftsplan_jahr, ba_id, beschluss_id, import_referenz usw. wurden ergänzt
  - ein strikter CHECK-Constraint (hausgeld_historie_quelle_consistency) erzwingt
    WJ-spezifische Geschäftslogik (z.B. quelle='import' → import_referenz NOT NULL)

Der WKZ-Branch benötigt:
  1. kontoart als VARCHAR zurück (z.B. '.900', '.911')
  2. Den CHECK-Constraint entfernt, damit normale Imports funktionieren
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('personen', '0007_wj_branch_felder'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='hausgeldhistorie',
                    name='kontoart',
                    field=models.CharField(
                        blank=True, default='', max_length=10,
                        help_text='z.B. .900, .911, .912, .940',
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        -- 1. kontoart idempotent hinzufügen
                        DO $$
                        BEGIN
                            ALTER TABLE personen_hausgeldhistorie
                                ADD COLUMN kontoart VARCHAR(10) NOT NULL DEFAULT '';
                        EXCEPTION WHEN duplicate_column THEN
                            ALTER TABLE personen_hausgeldhistorie
                                ALTER COLUMN kontoart SET DEFAULT '';
                        END $$;

                        -- 2. WJ-spezifischen CHECK-Constraint entfernen (falls vorhanden)
                        DO $$
                        BEGIN
                            ALTER TABLE personen_hausgeldhistorie
                                DROP CONSTRAINT hausgeld_historie_quelle_consistency;
                        EXCEPTION WHEN undefined_object THEN
                            NULL;  -- Constraint existiert nicht, nichts tun
                        END $$;
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
    ]
