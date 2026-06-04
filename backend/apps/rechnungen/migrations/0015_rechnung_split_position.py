from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('konten', '0002_konto_update'),
        ('rechnungen', '0014_rechnung_ist_gutschrift'),
    ]

    operations = [
        migrations.CreateModel(
            name='RechnungSplitPosition',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('betrag', models.DecimalField(decimal_places=2, max_digits=12)),
                ('position', models.PositiveIntegerField(default=0, help_text='Reihenfolge (0-basiert)')),
                ('aufwandskonto', models.ForeignKey(
                    help_text='Aufwandskonto dieser Split-Position',
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='+',
                    to='konten.konto',
                )),
                ('rechnung', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='splits',
                    to='rechnungen.rechnung',
                )),
            ],
            options={
                'verbose_name': 'Rechnung-Split-Position',
                'verbose_name_plural': 'Rechnung-Split-Positionen',
                'ordering': ['position', 'id'],
            },
        ),
    ]
