"""
Migration 0016 — WJ-Branch Felder in buchhaltung_buchungsart + kreditor FK in Buchung

Die Tabelle buchhaltung_buchungsart hat im Wirtschaftsjahr-Branch folgende
NOT-NULL-Spalte dazubekommen:
  - erloeskonto_default_nr VARCHAR(10) NOT NULL (bereits vorhanden, SET DEFAULT '')
  - tilgungs_prioritaet INTEGER NULL         (bereits vorhanden, nullable)
  - bankkonto_typ VARCHAR(25) NULL           (bereits vorhanden, nullable)
  - buchungstyp VARCHAR(20) NULL             (bereits vorhanden, nullable)

Buchung bekommt einen neuen nullable FK auf rechnungen_kreditor:
  - kreditor_id UUID NULL → rechnungen_kreditor(id)
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0015_wkz_models'),
        ('rechnungen', '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                # WJ-Felder in Buchungsart
                migrations.AddField(
                    model_name='buchungsart',
                    name='erloeskonto_default_nr',
                    field=models.CharField(blank=True, default='', max_length=10),
                ),
                migrations.AddField(
                    model_name='buchungsart',
                    name='tilgungs_prioritaet',
                    field=models.IntegerField(blank=True, null=True),
                ),
                migrations.AddField(
                    model_name='buchungsart',
                    name='bankkonto_typ',
                    field=models.CharField(blank=True, max_length=25, null=True),
                ),
                migrations.AddField(
                    model_name='buchungsart',
                    name='buchungstyp',
                    field=models.CharField(blank=True, max_length=20, null=True),
                ),
                # Kreditor FK an Buchung
                migrations.AddField(
                    model_name='buchung',
                    name='kreditor',
                    field=models.ForeignKey(
                        blank=True, null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='buchungen',
                        to='rechnungen.Kreditor',
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        -- erloeskonto_default_nr: existiert als NOT NULL → DB-Default setzen
                        DO $$
                        BEGIN
                            ALTER TABLE buchhaltung_buchungsart
                                ALTER COLUMN erloeskonto_default_nr SET DEFAULT '';
                        EXCEPTION WHEN undefined_column THEN
                            ALTER TABLE buchhaltung_buchungsart
                                ADD COLUMN erloeskonto_default_nr VARCHAR(10) NOT NULL DEFAULT '';
                        END $$;

                        -- tilgungs_prioritaet: nullable, existiert bereits (noop falls vorhanden)
                        DO $$
                        BEGIN
                            ALTER TABLE buchhaltung_buchungsart
                                ADD COLUMN tilgungs_prioritaet INTEGER NULL;
                        EXCEPTION WHEN duplicate_column THEN
                            NULL;
                        END $$;

                        -- bankkonto_typ: nullable, existiert bereits
                        DO $$
                        BEGIN
                            ALTER TABLE buchhaltung_buchungsart
                                ADD COLUMN bankkonto_typ VARCHAR(25) NULL;
                        EXCEPTION WHEN duplicate_column THEN
                            NULL;
                        END $$;

                        -- buchungstyp: nullable, existiert bereits
                        DO $$
                        BEGIN
                            ALTER TABLE buchhaltung_buchungsart
                                ADD COLUMN buchungstyp VARCHAR(20) NULL;
                        EXCEPTION WHEN duplicate_column THEN
                            NULL;
                        END $$;

                        -- kreditor_id: NEU → idempotent hinzufügen
                        DO $$
                        BEGIN
                            ALTER TABLE buchhaltung_buchung
                                ADD COLUMN kreditor_id UUID NULL
                                REFERENCES rechnungen_kreditor(id)
                                ON DELETE SET NULL
                                DEFERRABLE INITIALLY DEFERRED;
                        EXCEPTION WHEN duplicate_column THEN
                            NULL;
                        END $$;
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
    ]
