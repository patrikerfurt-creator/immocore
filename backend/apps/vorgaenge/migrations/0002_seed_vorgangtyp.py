import uuid

from django.db import migrations


SEED = [
    ('maengelmeldung', 'Mängelmeldung',            10),
    ('anfrage',        'Anfrage',                  20),
    ('beschwerde',     'Beschwerde',                30),
    ('intern',         'Interne Aufgabe',           40),
    ('sonstiges',      'Sonstiges',                 50),
]


def seed_vorgangtyp(apps, schema_editor):
    VorgangTyp = apps.get_model('vorgaenge', 'VorgangTyp')
    for code, bezeichnung, sortierung in SEED:
        VorgangTyp.objects.get_or_create(
            code=code,
            defaults={
                'id': uuid.uuid4(),
                'bezeichnung': bezeichnung,
                'sortierung': sortierung,
                'aktiv': True,
            },
        )


def unseed_vorgangtyp(apps, schema_editor):
    VorgangTyp = apps.get_model('vorgaenge', 'VorgangTyp')
    VorgangTyp.objects.filter(code__in=[code for code, _, _ in SEED]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('vorgaenge', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_vorgangtyp, unseed_vorgangtyp),
    ]
