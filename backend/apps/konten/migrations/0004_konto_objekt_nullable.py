"""
Migration 0004 — Konto.objekt nullable + objekt_id Spalte

Die konten_konto-Tabelle wurde auf dem Wirtschaftsjahr-Branch von objekt_id
auf wirtschaftsjahr_id umgestellt. Auf diesem Branch brauchen wir objekt_id
zurück (für kontenrahmen_anlegen und alle import-Services).

Idempotent: ADD COLUMN IF NOT EXISTS. Spalte ist nullable, da bestehende
Zeilen aus dem WJ-Branch keinen objekt_id-Wert haben.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('konten', '0003_abrechnungsart'),
        ('objekte', '0017_bankkonto_zahlungsverkehr'),
    ]

    operations = [
        # State: Konto.objekt wird nullable
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name='konto',
                    name='objekt',
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='konten',
                        to='objekte.objekt',
                    ),
                ),
            ],
            database_operations=[
                # objekt_id-Spalte idempotent hinzufügen (nullable FK)
                migrations.RunSQL(
                    sql="""
                        DO $$
                        BEGIN
                            ALTER TABLE konten_konto
                                ADD COLUMN objekt_id UUID NULL
                                REFERENCES objekte_objekt(id)
                                ON DELETE CASCADE
                                DEFERRABLE INITIALLY DEFERRED;
                        EXCEPTION WHEN duplicate_column THEN
                            NULL; -- Spalte existiert bereits, nichts tun
                        END $$;
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
    ]
