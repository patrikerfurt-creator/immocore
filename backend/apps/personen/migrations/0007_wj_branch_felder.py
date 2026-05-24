"""
Migration 0007 — Felder aus Wirtschaftsjahr-Branch nachgetragen

Folgende Felder existieren in der DB (Wirtschaftsjahr-Branch) aber nicht im
aktuellen Model (feature/WKZ-Branch). Alle DDL-Operationen sind idempotent.

Felder:
- personen_person.briefanrede        VARCHAR NOT NULL DEFAULT ''
- personen_person.briefanrede2       VARCHAR NOT NULL DEFAULT ''
- personen_sepamandat.sequence_type  VARCHAR NOT NULL DEFAULT 'RCUR'
- personen_hausgeldhistorie.quelle   VARCHAR NOT NULL DEFAULT 'import'
- personen_hausgeldhistorie.bemerkung VARCHAR NOT NULL DEFAULT ''
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('personen', '0006_person_vorname2_nachname2'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='person',
                    name='briefanrede',
                    field=models.CharField(blank=True, default='', max_length=255,
                                           verbose_name='Briefanrede'),
                ),
                migrations.AddField(
                    model_name='person',
                    name='briefanrede2',
                    field=models.CharField(blank=True, default='', max_length=255,
                                           verbose_name='Briefanrede 2. Person'),
                ),
                migrations.AddField(
                    model_name='sepamandat',
                    name='sequence_type',
                    field=models.CharField(blank=True, default='RCUR', max_length=4,
                                           verbose_name='Sequenztyp'),
                ),
                migrations.AddField(
                    model_name='hausgeldhistorie',
                    name='quelle',
                    field=models.CharField(blank=True, default='import', max_length=20,
                                           verbose_name='Quelle'),
                ),
                migrations.AddField(
                    model_name='hausgeldhistorie',
                    name='bemerkung',
                    field=models.CharField(blank=True, default='', max_length=255,
                                           verbose_name='Bemerkung'),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        DO $$
                        BEGIN
                            ALTER TABLE personen_person
                                ADD COLUMN briefanrede VARCHAR(255) NOT NULL DEFAULT '';
                        EXCEPTION WHEN duplicate_column THEN
                            ALTER TABLE personen_person
                                ALTER COLUMN briefanrede SET DEFAULT '';
                        END $$;

                        DO $$
                        BEGIN
                            ALTER TABLE personen_person
                                ADD COLUMN briefanrede2 VARCHAR(255) NOT NULL DEFAULT '';
                        EXCEPTION WHEN duplicate_column THEN
                            ALTER TABLE personen_person
                                ALTER COLUMN briefanrede2 SET DEFAULT '';
                        END $$;

                        DO $$
                        BEGIN
                            ALTER TABLE personen_sepamandat
                                ADD COLUMN sequence_type VARCHAR(4) NOT NULL DEFAULT 'RCUR';
                        EXCEPTION WHEN duplicate_column THEN
                            ALTER TABLE personen_sepamandat
                                ALTER COLUMN sequence_type SET DEFAULT 'RCUR';
                        END $$;

                        DO $$
                        BEGIN
                            ALTER TABLE personen_hausgeldhistorie
                                ADD COLUMN quelle VARCHAR(20) NOT NULL DEFAULT 'import';
                        EXCEPTION WHEN duplicate_column THEN
                            ALTER TABLE personen_hausgeldhistorie
                                ALTER COLUMN quelle SET DEFAULT 'import';
                        END $$;

                        DO $$
                        BEGIN
                            ALTER TABLE personen_hausgeldhistorie
                                ADD COLUMN bemerkung VARCHAR(255) NOT NULL DEFAULT '';
                        EXCEPTION WHEN duplicate_column THEN
                            ALTER TABLE personen_hausgeldhistorie
                                ALTER COLUMN bemerkung SET DEFAULT '';
                        END $$;
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
    ]
