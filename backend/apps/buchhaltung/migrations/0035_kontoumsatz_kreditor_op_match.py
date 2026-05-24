import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0034_wp_quelle'),
    ]

    operations = [
        # Neues Erkennungsquellen-Feld kreditor_op_match wird über choices-Änderung abgedeckt
        # (kein DB-Schema-Änderung, nur Python-Ebene)
        migrations.AlterField(
            model_name='kontoumsatz',
            name='erkennungs_quelle',
            field=models.CharField(
                blank=True,
                choices=[
                    ('e2e_id',            'EndToEndId-Match (Nebenbuch)'),
                    ('iban_ev',           'IBAN-Match auf EigentumsVerhältnis'),
                    ('bank_match_regel',  'BankMatchRegel'),
                    ('iban_kreditor',     'IBAN-Match auf Kreditor'),
                    ('kreditor_op_match', 'Kreditor-Lastschrift OP-Abgleich'),
                    ('ki',                'KI-Vorschlag'),
                    ('keine',             'Keine Erkennung'),
                ],
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='kontoumsatz',
            name='erkannt_kreditor_op',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='kontoumsaetze_erkannt',
                to='buchhaltung.kreditorop',
            ),
        ),
    ]
