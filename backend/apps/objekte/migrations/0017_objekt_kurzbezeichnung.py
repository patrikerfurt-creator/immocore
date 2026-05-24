from django.db import migrations, models


def fill_kurzbezeichnung(apps, schema_editor):
    Objekt = apps.get_model('objekte', 'Objekt')
    for o in Objekt.objects.filter(kurzbezeichnung=''):
        o.kurzbezeichnung = (o.strasse or o.bezeichnung)[:40]
        o.save(update_fields=['kurzbezeichnung'])


class Migration(migrations.Migration):

    dependencies = [
        ('objekte', '0016_bankkonto_zahlungsverkehr'),
    ]

    operations = [
        migrations.AddField(
            model_name='objekt',
            name='kurzbezeichnung',
            field=models.CharField(
                blank=True,
                help_text='Kurzbeschreibung für SEPA-Verwendungszweck (z.B. „Coventrystr. 32")',
                max_length=40,
            ),
        ),
        migrations.RunPython(fill_kurzbezeichnung, migrations.RunPython.noop),
    ]
