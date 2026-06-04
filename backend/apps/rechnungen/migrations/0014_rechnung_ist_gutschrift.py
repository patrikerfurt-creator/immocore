from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rechnungen', '0013_merge_0011_wkz_models_0012_rechnung_sepa_lastschrift'),
    ]

    operations = [
        migrations.AddField(
            model_name='rechnung',
            name='ist_gutschrift',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'Gutschrift / Guthaben: Lieferant schuldet der WEG Geld. '
                    'betrag_brutto bleibt positiv — Buchungslogik wird invertiert: '
                    'Phase 1 Soll 70xxx / Haben 15900, Phase 2 Soll 15900 / Haben 55xxx + Soll 13600 / Haben 70xxx.'
                ),
            ),
        ),
    ]
