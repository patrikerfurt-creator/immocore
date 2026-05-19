"""
Phase A Backfill: Kontoumsatz-Status-Normalisierung.
- Datensätze mit buchung != NULL → status = 'verbucht'
- Datensätze mit buchung IS NULL und status in ('gebucht', 'manuell') → status = 'unklar'
"""
from django.db import migrations


def backfill_kontoumsatz_status(apps, schema_editor):
    Kontoumsatz = apps.get_model('buchhaltung', 'Kontoumsatz')
    # Bereits verbucht (buchung FK gesetzt) → 'verbucht'
    Kontoumsatz.objects.filter(buchung__isnull=False).exclude(status='verbucht').update(status='verbucht')
    # Inkonsistent: 'gebucht' oder 'manuell' ohne buchung → 'unklar'
    Kontoumsatz.objects.filter(buchung__isnull=True, status__in=('gebucht', 'manuell')).update(status='unklar')


def reverse_backfill(apps, schema_editor):
    # Reverse: 'verbucht' → 'gebucht'
    Kontoumsatz = apps.get_model('buchhaltung', 'Kontoumsatz')
    Kontoumsatz.objects.filter(status='verbucht').update(status='gebucht')


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0032_ebanking_phase_a'),
    ]

    operations = [
        migrations.RunPython(backfill_kontoumsatz_status, reverse_backfill),
    ]
