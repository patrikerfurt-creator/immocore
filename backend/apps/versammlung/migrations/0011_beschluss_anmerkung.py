# Generated for Beschluss-Anmerkung (Verwaltungsnotiz aus dem Abstimmtool)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('versammlung', '0010_tagesordnungspunkt_abstimmung_ja_2_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='beschluss',
            name='anmerkung',
            field=models.TextField(blank=True, default='', help_text='Freitext-Anmerkung der Verwaltung zum Beschluss — wird aus der im Abstimmtool erfassten Bemerkung (top.ergebnis_bemerkung) übernommen. KEIN Bestandteil des unveränderlichen Wortlauts (§ 24 Abs. 7 WEG), sondern eine erläuternde Notiz; erscheint im Beschlussprotokoll und in der Sammlung.', verbose_name='Anmerkung der Verwaltung'),
        ),
    ]
