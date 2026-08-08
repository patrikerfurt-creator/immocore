from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rechnungen', '0022_remove_rechnung_pdf_upload'),
    ]

    operations = [
        migrations.AlterField(
            model_name='rechnung',
            name='status',
            field=models.CharField(
                choices=[
                    ('importiert', 'Importiert'),
                    ('duplikat', 'Duplikat'),
                    ('prueffall', 'Prüffall (alt)'),
                    ('erfasst', 'Erfasst'),
                    ('erkannt', 'Erkannt (Stufe 1)'),
                    ('pruefung_match', 'Prüffall (Stufe 2)'),
                    ('nicht_erkannt', 'Nicht erkannt (Stufe 3)'),
                    ('in_pruefung', 'In Prüfung'),
                    ('in_buchhaltung', 'In Buchhaltung (Stufe 1)'),
                    ('zur_freigabe', 'Zur Freigabe (Stufe 2)'),
                    ('freigegeben', 'Freigegeben (OP gebucht)'),
                    ('teilbezahlt', 'Teilbezahlt'),
                    ('bezahlt', 'Bezahlt'),
                    ('wkz_beleg', 'WKZ-Beleg (über WKZ abgewickelt)'),
                    ('abgelehnt', 'Abgelehnt'),
                    ('storniert', 'Storniert'),
                    ('fehler', 'Fehler'),
                ],
                default='importiert',
                max_length=20,
            ),
        ),
    ]
