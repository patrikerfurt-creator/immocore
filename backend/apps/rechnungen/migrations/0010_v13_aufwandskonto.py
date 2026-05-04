from django.db import migrations


def stufe_2a_2b_zu_2_3(apps, schema_editor):
    Rechnung = apps.get_model('rechnungen', 'Rechnung')
    Rechnung.objects.filter(erkennungs_stufe='2a').update(erkennungs_stufe='2')
    Rechnung.objects.filter(erkennungs_stufe='2b').update(erkennungs_stufe='3')


def konfidenz_konto_zu_aufwandskonto(apps, schema_editor):
    Rechnung = apps.get_model('rechnungen', 'Rechnung')
    for r in Rechnung.objects.filter(erkennungs_konfidenz__has_key='konto'):
        k = dict(r.erkennungs_konfidenz)
        k['aufwandskonto'] = k.pop('konto')
        r.erkennungs_konfidenz = k
        r.save(update_fields=['erkennungs_konfidenz'])


class Migration(migrations.Migration):

    dependencies = [
        ('rechnungen', '0009_kreditor_nummer'),
    ]

    operations = [
        # 1. Buchungskonto-Feld von Rechnung entfernen
        migrations.RemoveField(
            model_name='rechnung',
            name='buchungskonto',
        ),
        # 2. RechnungsMatchRegel.buchungskonto → aufwandskonto umbenennen
        migrations.RenameField(
            model_name='rechnungsmatchregel',
            old_name='buchungskonto',
            new_name='aufwandskonto',
        ),
        # 3. erkennungs_stufe: '2a'→'2', '2b'→'3'
        migrations.RunPython(stufe_2a_2b_zu_2_3, migrations.RunPython.noop),
        # 4. erkennungs_konfidenz JSON key 'konto'→'aufwandskonto'
        migrations.RunPython(konfidenz_konto_zu_aufwandskonto, migrations.RunPython.noop),
    ]
