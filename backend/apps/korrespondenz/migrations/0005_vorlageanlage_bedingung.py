from django.db import migrations, models


class Migration(migrations.Migration):
    """Phase 6b: bedingte Vorlagen-Anlage (additiv, kein Datenzugriff)."""

    dependencies = [
        ('korrespondenz', '0004_vorlageanlage_dokument_objekt_kategorie'),
    ]

    operations = [
        migrations.AddField(
            model_name='vorlageanlage',
            name='bedingung',
            field=models.CharField(
                blank=True, max_length=200,
                help_text='Optional: Platzhalter-Bedingung, z. B. ev.sepa_mandat_fehlt. '
                          'Die Anlage wird nur beigefügt, wenn sie erfüllt ist (leer = immer).',
            ),
        ),
    ]
