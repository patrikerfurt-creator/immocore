"""Datenmigration: Buchungen dem ersten Wirtschaftsjahr ihres Objekts zuordnen."""
from django.db import migrations
from django.utils import timezone


def _buchungen_wj_zuordnen(apps, schema_editor):
    Wirtschaftsjahr = apps.get_model('objekte',     'Wirtschaftsjahr')
    Buchung         = apps.get_model('buchhaltung', 'Buchung')
    Objekt          = apps.get_model('objekte',     'Objekt')

    # Je Objekt das erste (älteste) WJ holen und alle WJ-losen Buchungen zuordnen
    for objekt in Objekt.objects.all():
        wj = (
            Wirtschaftsjahr.objects
            .filter(objekt=objekt)
            .order_by('jahr')
            .first()
        )
        if wj:
            Buchung.objects.filter(
                objekt=objekt,
                wirtschaftsjahr__isnull=True,
            ).update(wirtschaftsjahr=wj)


def _buchungen_wj_rueckgaengig(apps, schema_editor):
    Buchung = apps.get_model('buchhaltung', 'Buchung')
    Buchung.objects.all().update(wirtschaftsjahr=None)


class Migration(migrations.Migration):

    dependencies = [
        ('konten',      '0004_konto_wirtschaftsjahr_kvs'),
        ('buchhaltung', '0016_buchung_wirtschaftsjahr_fk'),
        ('objekte',     '0015_wirtschaftsjahr_einheitverbrauch'),
    ]

    operations = [
        migrations.RunPython(_buchungen_wj_zuordnen, _buchungen_wj_rueckgaengig),
    ]
