from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0011_camtimportlog'),
        ('objekte', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='LastschriftLauf',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('bezeichnung', models.CharField(blank=True, max_length=255)),
                ('faelligkeitsdatum', models.DateField()),
                ('status', models.CharField(
                    choices=[
                        ('erstellt', 'Erstellt'),
                        ('exportiert', 'Exportiert (XML heruntergeladen)'),
                        ('eingereicht', 'Eingereicht'),
                    ],
                    default='erstellt',
                    max_length=20,
                )),
                ('erstellt_am', models.DateTimeField(auto_now_add=True)),
                ('anzahl_positionen', models.IntegerField(default=0)),
                ('gesamt_summe', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('positionen', models.JSONField(default=list)),
                ('ohne_mandat', models.JSONField(default=list)),
                ('objekt', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='lastschrift_laeufe',
                    to='objekte.objekt',
                )),
                ('sollstellungs_lauf', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='lastschrift_laeufe',
                    to='buchhaltung.sollstellungslauf',
                )),
                ('erstellt_von', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='lastschrift_laeufe',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Lastschrift-Lauf',
                'verbose_name_plural': 'Lastschrift-Läufe',
                'ordering': ['-erstellt_am'],
            },
        ),
    ]
