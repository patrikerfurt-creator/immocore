from django.db import migrations, models


def assign_kreditorennummern(apps, schema_editor):
    """Vergib Kreditorennummern ab 70000 an alle bestehenden Kreditoren (nach Anlagedatum)."""
    Kreditor = apps.get_model('rechnungen', 'Kreditor')
    kreditoren = list(Kreditor.objects.filter(
        kreditorennummer__isnull=True,
    ).order_by('erstellt_am', 'name'))
    for i, k in enumerate(kreditoren):
        k.kreditorennummer = str(70000 + i)
        k.save(update_fields=['kreditorennummer'])


class Migration(migrations.Migration):

    dependencies = [
        ('rechnungen', '0008_op_buchung'),
    ]

    operations = [
        migrations.AddField(
            model_name='kreditor',
            name='kreditorennummer',
            field=models.CharField(
                blank=True,
                help_text='Automatisch vergeben ab 70000',
                max_length=10,
                null=True,
                unique=True,
            ),
        ),
        migrations.RunPython(assign_kreditorennummern, migrations.RunPython.noop),
    ]
