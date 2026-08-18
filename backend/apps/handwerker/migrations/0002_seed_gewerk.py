import uuid

from django.db import migrations


SEED = [
    ('sanitaer',                 'Sanitär',                   10),
    ('heizung',                  'Heizung',                   20),
    ('elektrik',                 'Elektrik',                  30),
    ('dachdeckerei',             'Dachdeckerei',              40),
    ('mauerwerk',                'Mauerwerk',                 50),
    ('tischlerei',               'Tischlerei',                60),
    ('schlosser',                'Schlosser',                 70),
    ('maler',                    'Maler',                     80),
    ('bodenleger',               'Bodenleger',                90),
    ('aufzug',                   'Aufzug',                   100),
    ('garten',                   'Garten- und Landschaftsbau',110),
    ('reinigung',                'Reinigung',                120),
    ('schaedlingsbekaempfung',   'Schädlingsbekämpfung',     130),
    ('sonstige',                 'Sonstige',                 140),
]


def seed_gewerk(apps, schema_editor):
    Gewerk = apps.get_model('handwerker', 'Gewerk')
    for code, bezeichnung, sortierung in SEED:
        Gewerk.objects.get_or_create(
            code=code,
            defaults={
                'id': uuid.uuid4(),
                'bezeichnung': bezeichnung,
                'sortierung': sortierung,
                'aktiv': True,
            },
        )


def unseed_gewerk(apps, schema_editor):
    Gewerk = apps.get_model('handwerker', 'Gewerk')
    Gewerk.objects.filter(code__in=[code for code, _, _ in SEED]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('handwerker', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_gewerk, unseed_gewerk),
    ]
