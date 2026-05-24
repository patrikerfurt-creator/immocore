"""
Migration 0017 — Buchung.wirtschaftsjahr → db_column='wirtschaftsjahr_nr'

Der WJ-Branch hat die Spalte 'wirtschaftsjahr' in 'wirtschaftsjahr_nr' umbenannt
und eine neue FK-Spalte 'wirtschaftsjahr_id' hinzugefügt.

Der WKZ-Branch verwendet das Feld weiterhin unter dem Python-Namen 'wirtschaftsjahr',
mappt es jetzt aber via db_column auf die tatsächlich vorhandene Spalte 'wirtschaftsjahr_nr'.

Keine DB-Änderung nötig — die Spalte existiert bereits.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0016_wj_buchungsart_felder_kreditor'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name='buchung',
                    name='wirtschaftsjahr',
                    field=models.IntegerField(
                        null=True, blank=True,
                        db_column='wirtschaftsjahr_nr',
                    ),
                ),
            ],
            database_operations=[
                # Spalte existiert bereits als wirtschaftsjahr_nr — nichts zu tun
            ],
        ),
    ]
