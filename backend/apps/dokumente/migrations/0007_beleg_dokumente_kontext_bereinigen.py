"""
Datenmigration (Owner-Regel B-Hybrid, Spec Vorgang & DMS Kap. 1.6):
Dokumente, die bereits über Rechnung.beleg_dokument an eine Rechnung gekoppelt
sind, dürfen künftig KEINEN der vier Kontext-FKs (objekt/einheit/vorgang/person)
mehr gesetzt haben — die Rechnung selbst ist der Owner. Muss vor der
nachfolgenden AddConstraint-Migration laufen, sonst würde die DB-Constraint
(<= 1 Kontext-FK) hier nichts verletzen, aber die künftige clean()-Regel
(0 Kontext-FKs NUR bei Rechnungskopplung) wäre für Bestandsdaten falsch befüllt.

Bewusst reversibel als No-Op (kein Zurücksetzen auf alte objekt/einheit-Werte
möglich, da diese beim Vorwärtslauf verworfen werden) — siehe reverse_code.
"""
from django.db import migrations


def bereinige_beleg_dokumente(apps, schema_editor):
    Dokument = apps.get_model('dokumente', 'Dokument')
    Dokument.objects.filter(rechnung__isnull=False).update(objekt=None, einheit=None)


def noop_reverse(apps, schema_editor):
    # Irreversibel im eigentlichen Sinn (die ursprünglichen objekt/einheit-Werte
    # sind nach dem Vorwärtslauf nicht mehr rekonstruierbar) — bewusster No-Op,
    # damit ein migrate zurück nicht hart abbricht.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('dokumente', '0006_dokument_person_dokument_version_and_more'),
        ('rechnungen', '0023_rechnung_status_wkz_beleg'),
    ]

    operations = [
        migrations.RunPython(bereinige_beleg_dokumente, noop_reverse),
    ]
