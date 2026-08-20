"""
Seed des Vorgangs-Typs für Folgeaufgaben aus EV-Beschlüssen
(Spec v1.1 Kap. 9, Phase D).

Muster: ``vorgaenge/0002_seed_vorgangtyp.py``. Der Typ liegt in ``vorgaenge``,
gehört fachlich aber zum EV-Modul — daher der Seed hier, mit Abhängigkeit auf
die Ziel-App.
"""
import uuid

from django.db import migrations

CODE = 'ev-beschluss'
BEZEICHNUNG = 'Beschluss-Umsetzung (EV)'


def seed(apps, schema_editor):
    VorgangTyp = apps.get_model('vorgaenge', 'VorgangTyp')
    VorgangTyp.objects.get_or_create(
        code=CODE,
        defaults={
            'id': uuid.uuid4(),
            'bezeichnung': BEZEICHNUNG,
            'standard_prioritaet': 'normal',
            'sortierung': 60,
            'aktiv': True,
        },
    )


def unseed(apps, schema_editor):
    # Nur löschen, wenn noch kein Vorgang daran hängt — sonst würde ein
    # Rückwärtslauf an PROTECT scheitern und die Migration unbrauchbar machen.
    VorgangTyp = apps.get_model('vorgaenge', 'VorgangTyp')
    typ = VorgangTyp.objects.filter(code=CODE).first()
    if typ and not typ.vorgaenge.exists():
        typ.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('versammlung', '0001_initial'),
        ('vorgaenge', '0002_seed_vorgangtyp'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
