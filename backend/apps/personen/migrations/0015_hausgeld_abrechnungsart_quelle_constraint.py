"""
Migration 0015: Hausgeld-Historie Abrechnungsart-Backfill + Constraint-Umstellung

Import-Einträge hatten bisher abrechnungsart=NULL (nur ba gesetzt).
Dadurch konnten Import- und WP-Beschluss-Einträge für dasselbe gueltig_ab
nicht sauber koexistieren. Diese Migration:

1. Entfernt den alten Unique-Constraint auf (ev, abr, gueltig_ab)
2. Befüllt abrechnungsart bei bestehenden Import-Einträgen per ba.nr-Lookup
3. Setzt neuen Unique-Constraint auf (ev, abr, quelle, gueltig_ab)
   → Import und WP-Beschluss für dasselbe Datum sind jetzt separate Einträge
"""
from django.db import migrations, models


def backfill_abrechnungsart(apps, schema_editor):
    HausgeldHistorie = apps.get_model('personen', 'HausgeldHistorie')
    Abrechnungsart = apps.get_model('konten', 'Abrechnungsart')

    eintraege = (
        HausgeldHistorie.objects
        .filter(abrechnungsart__isnull=True, ba__isnull=False)
        .select_related('eigentumsverhaeltnis__einheit__objekt', 'ba')
    )
    for hist in eintraege:
        try:
            abr = Abrechnungsart.objects.filter(
                objekt=hist.eigentumsverhaeltnis.einheit.objekt,
                code=hist.ba.nr,
            ).first()
            if abr:
                hist.abrechnungsart = abr
                hist.save(update_fields=['abrechnungsart'])
        except Exception:
            pass


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('personen', '0014_wp_quelle'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='hausgeldhistorie',
            name='uniq_historie_je_vertrag_abrart_datum',
        ),
        migrations.RunPython(backfill_abrechnungsart, noop),
        migrations.AddConstraint(
            model_name='hausgeldhistorie',
            constraint=models.UniqueConstraint(
                fields=['eigentumsverhaeltnis', 'abrechnungsart', 'quelle', 'gueltig_ab'],
                name='uniq_historie_je_vertrag_abrart_quelle_datum',
            ),
        ),
    ]
