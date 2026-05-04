from django.db import migrations, models
import django.db.models.deletion


def add_konto_13600(apps, schema_editor):
    Konto = apps.get_model("konten", "Konto")
    Objekt = apps.get_model("objekte", "Objekt")
    for objekt in Objekt.objects.all():
        Konto.objects.get_or_create(
            objekt=objekt,
            kontonummer="13600",
            defaults={
                "kontoname": "Schwebender Zahlungsausgang",
                "abrechnungsart": None,
                "direktes_buchen": False,
                "verteilerschluessel": None,
                "kontoart": "standard",
                "arge_konto": False,
                "arge_kostenart": None,
                "aktiv": True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0013_lastschriftlauf_buchungen_erstellt'),
        ('rechnungen', '0010_v13_aufwandskonto'),
        ('objekte', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='KreditorOP',
            fields=[
                ('op_nummer', models.IntegerField(unique=True, db_index=True)),
                ('betrag_ursprung', models.DecimalField(decimal_places=2, max_digits=12)),
                ('betrag_offen', models.DecimalField(decimal_places=2, max_digits=12)),
                ('faellig_ab', models.DateField()),
                ('status', models.CharField(
                    choices=[
                        ('offen', 'Offen'),
                        ('bezahlt', 'Bezahlt'),
                        ('teilbezahlt', 'Teilbezahlt'),
                        ('storniert', 'Storniert'),
                    ],
                    default='offen',
                    max_length=20,
                )),
                ('erstellt_am', models.DateTimeField(auto_now_add=True)),
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('buchung', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='kreditor_op_erstellung',
                    to='buchhaltung.buchung',
                )),
                ('zahlung_buchung', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='kreditor_op_zahlung',
                    to='buchhaltung.buchung',
                )),
                ('kreditor', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='offene_posten',
                    to='rechnungen.kreditor',
                )),
                ('objekt', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='kreditor_ops',
                    to='objekte.objekt',
                )),
                ('rechnung', models.OneToOneField(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='kreditor_op',
                    to='rechnungen.rechnung',
                )),
            ],
            options={
                'verbose_name': 'Kreditor-OP',
                'verbose_name_plural': 'Kreditor-OPs',
                'ordering': ['-op_nummer'],
            },
        ),
        migrations.RunPython(add_konto_13600, migrations.RunPython.noop),
    ]
