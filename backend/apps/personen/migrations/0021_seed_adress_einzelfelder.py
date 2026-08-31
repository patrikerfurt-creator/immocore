"""
Übernimmt die bestehenden Adress-Textblöcke in die neuen Einzelfelder.

Der Bestand ist dafür sehr gleichförmig: von 593 gefüllten Adressen haben
591 exakt den zweizeiligen Aufbau ``Straße Hausnummer`` / ``PLZ Ort``.

``adresse`` wird bewusst NICHT verändert — die Migration ist damit rein
additiv und im Zweifel gefahrlos wiederholbar. Was der Parser nicht
eindeutig zerlegen kann, landet vollständig in ``strasse``; verloren geht
nichts, und die Verwaltung kann solche Fälle in der Personenmaske
nachziehen.
"""
from django.db import migrations

# Reine String-Funktionen ohne Model-Bezug — deshalb ist der Import hier
# unbedenklich (kein historisches Modell nötig).
from apps.personen.adresse import zerlege_adresse


def uebernehmen(apps, schema_editor):
    Person = apps.get_model('personen', 'Person')

    zu_speichern = []
    for person in Person.objects.exclude(adresse='').exclude(adresse__isnull=True):
        # Bereits gefüllte Einzelfelder nicht überschreiben.
        if any([person.strasse, person.hausnummer, person.plz, person.ort]):
            continue

        teile = zerlege_adresse(person.adresse)
        person.strasse = teile['strasse'][:255]
        person.hausnummer = teile['hausnummer'][:20]
        person.plz = teile['plz'][:10]
        person.ort = teile['ort'][:100]
        zu_speichern.append(person)

    Person.objects.bulk_update(
        zu_speichern, ['strasse', 'hausnummer', 'plz', 'ort'], batch_size=500,
    )


def zuruecknehmen(apps, schema_editor):
    """Leert die Einzelfelder wieder. ``adresse`` war nie verändert worden,
    der Adressbestand bleibt also in jedem Fall vollständig."""
    Person = apps.get_model('personen', 'Person')
    Person.objects.update(strasse='', hausnummer='', plz='', ort='')


class Migration(migrations.Migration):

    dependencies = [
        ('personen', '0020_person_hausnummer_person_ort_person_plz_and_more'),
    ]

    operations = [
        migrations.RunPython(uebernehmen, zuruecknehmen),
    ]
