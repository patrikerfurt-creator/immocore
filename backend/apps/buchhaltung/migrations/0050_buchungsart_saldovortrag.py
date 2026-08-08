from django.db import migrations


def anlegen(apps, schema_editor):
    Buchungsart = apps.get_model('buchhaltung', 'Buchungsart')
    Buchungsart.objects.get_or_create(
        nr='99',
        defaults=dict(
            kuerzel='Vortrag',
            bezeichnung='Saldovortrag',
            einzelabrechnung='nein',
            gesamtabrechnung=False,
            ruecklagen_relevant=True,
            umlage='gesperrt',
            beleg_pflicht=True,
            beschluss_pflicht=False,
            vier_augen_schwelle=None,
            sperre_nach_jahresabschluss=True,
            system_buchungsart=False,
            default_konto_soll_pattern='',
            default_konto_haben_pattern='',
            aktiv=True,
            buchungstyp='personenkonto',
        ),
    )


def entfernen(apps, schema_editor):
    Buchungsart = apps.get_model('buchhaltung', 'Buchungsart')
    Buchungsart.objects.filter(nr='99', system_buchungsart=False).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0049_saldovortrag_negativ'),
    ]

    operations = [
        migrations.RunPython(anlegen, entfernen),
    ]
