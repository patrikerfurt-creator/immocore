from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0041_sollstellungslauf_unique_constraint_fix'),
        ('rechnungen', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='wiederkehrendebuchungvorlage',
            name='rechnung',
            field=models.ForeignKey(
                blank=True,
                help_text='Rechnung, aus der diese WKZ-Vorlage abgeleitet wurde (optional, für DMS-Bezug).',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='wkz_vorlagen',
                to='rechnungen.rechnung',
            ),
        ),
    ]
