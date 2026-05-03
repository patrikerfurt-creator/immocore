from django.db import migrations, models
import django.db.models.deletion


def add_konto_15900(apps, schema_editor):
    Konto = apps.get_model("konten", "Konto")
    Objekt = apps.get_model("objekte", "Objekt")
    for objekt in Objekt.objects.all():
        Konto.objects.get_or_create(
            objekt=objekt,
            kontonummer="15900",
            defaults={
                "kontoname": "Schwebende Eingangsrechnungen",
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
        ('buchhaltung', '0001_initial'),
        ('rechnungen', '0007_v12_routing'),
    ]

    operations = [
        migrations.AddField(
            model_name='rechnung',
            name='aufwandskonto',
            field=models.ForeignKey(
                blank=True, null=True,
                help_text='Aufwandskonto (50000–55999), wird bei Zahlung gebucht',
                on_delete=django.db.models.deletion.PROTECT,
                related_name='rechnungen_als_aufwand',
                to='konten.konto',
            ),
        ),
        migrations.AddField(
            model_name='rechnung',
            name='op_buchung',
            field=models.OneToOneField(
                blank=True, null=True,
                help_text='Phase-1-Buchung bei Freigabe (reserviert für Kreditor-Subledger)',
                on_delete=django.db.models.deletion.PROTECT,
                related_name='rechnung_op',
                to='buchhaltung.buchung',
            ),
        ),
        migrations.AddField(
            model_name='rechnung',
            name='aufwand_buchung',
            field=models.OneToOneField(
                blank=True, null=True,
                help_text='Phase-2-Buchung: Aufwand / Bank bei Zahlung',
                on_delete=django.db.models.deletion.PROTECT,
                related_name='rechnung_aufwand',
                to='buchhaltung.buchung',
            ),
        ),
        migrations.RunPython(add_konto_15900, migrations.RunPython.noop),
    ]
