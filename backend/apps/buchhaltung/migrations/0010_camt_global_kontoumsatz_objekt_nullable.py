from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0009_importordner_global'),
    ]

    operations = [
        # CamtImportEinstellung: objekt-FK entfernen (global statt je Objekt)
        migrations.RemoveField(
            model_name='camtimporteinstellung',
            name='objekt',
        ),
        # Kontoumsatz: objekt nullable (IBAN-Zuordnung statt Import-Einstellung)
        migrations.AlterField(
            model_name='kontoumsatz',
            name='objekt',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name='kontoumsaetze',
                to='objekte.objekt',
            ),
        ),
    ]
