"""SEPAMandat: Check- und partielle Unique-Constraints (Phase 2, Portal-SEPA-Mandat).

Bewusst getrennt von 0024 (Felder) und 0025 (Bestands-Datenmigration):
Reihenfolge Felder -> RunPython -> Constraints. Die Constraints greifen erst,
nachdem die Datenmigration ``person`` befuellt hat.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('personen', '0025_sepamandat_bestand_zu_sammelmandat'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='sepamandat',
            constraint=models.CheckConstraint(condition=models.Q(('eigentumsverhaeltnis__isnull', True), ('person__isnull', False), _connector='OR'), name='ck_mandat_ev_braucht_person'),
        ),
        migrations.AddConstraint(
            model_name='sepamandat',
            constraint=models.UniqueConstraint(condition=models.Q(('aktiv', True), ('eigentumsverhaeltnis__isnull', False)), fields=('eigentumsverhaeltnis',), name='uniq_aktives_mandat_je_ev'),
        ),
        migrations.AddConstraint(
            model_name='sepamandat',
            constraint=models.UniqueConstraint(condition=models.Q(('aktiv', True), ('eigentumsverhaeltnis__isnull', True)), fields=('person',), name='uniq_aktives_sammelmandat_je_person'),
        ),
    ]
