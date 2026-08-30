"""
Berechnet ``name_normalisiert`` für alle bestehenden Kreditoren neu.

Notwendig, weil das Feld bisher auf zwei Arten gefüllt wurde: der
Rechnungsparser entfernte Rechtsformen ("meier"), die manuelle Anlage in
``views.py`` nicht ("meier gmbh"). Die Dubletten-Erkennung vergleicht
exakt auf diesem Feld — dieselbe Firma aus unterschiedlicher Quelle wurde
deshalb nie als Treffer erkannt.

Seit ``Kreditor.save()`` das Feld selbst ableitet, kann es nicht mehr
auseinanderlaufen; hier wird der Bestand einmalig nachgezogen.
"""
from django.db import migrations

from apps.rechnungen.normalisierung import normalisiere_kreditorname


def neu_berechnen(apps, schema_editor):
    Kreditor = apps.get_model('rechnungen', 'Kreditor')

    zu_speichern = []
    for kreditor in Kreditor.objects.all():
        neu = normalisiere_kreditorname(kreditor.name)
        if neu != (kreditor.name_normalisiert or ''):
            kreditor.name_normalisiert = neu
            zu_speichern.append(kreditor)

    Kreditor.objects.bulk_update(zu_speichern, ['name_normalisiert'], batch_size=500)


def zurueck(apps, schema_editor):
    """Kein echtes Zurück: die alten Werte stammten aus zwei verschiedenen
    Verfahren und sind nicht rekonstruierbar. Das Feld ist reine
    Vergleichshilfe und wird bei jedem ``save()`` neu abgeleitet — ein
    No-Op ist hier korrekt und verliert nichts."""


class Migration(migrations.Migration):

    dependencies = [
        ('rechnungen', '0026_kreditorbankverbindung_kreditordublettenpruefung'),
    ]

    operations = [
        migrations.RunPython(neu_berechnen, zurueck),
    ]
