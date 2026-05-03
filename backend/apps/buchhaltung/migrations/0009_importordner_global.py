from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0008_import_ordner_einstellung'),
        ('objekte', '0001_initial'),
    ]

    operations = [
        # Unique-Together entfernen
        migrations.AlterUniqueTogether(
            name='importordnereinstellung',
            unique_together=set(),
        ),
        # Objekt-FK entfernen
        migrations.RemoveField(
            model_name='importordnereinstellung',
            name='objekt',
        ),
        # Bereich als global unique markieren
        migrations.AlterField(
            model_name='importordnereinstellung',
            name='bereich',
            field=models.CharField(
                choices=[('rechnungen', 'Rechnungen'), ('dokumente', 'Dokumente')],
                max_length=50,
                unique=True,
            ),
        ),
    ]
