from django.db import migrations


# Sinnvolle Vorbelegung (in der Admin-UI änderbar): bei Anfrage/Beschwerde ist
# eine Antwort an einen Eigentümer/Mieter typisch, bei Mängelmeldung/Interner
# Aufgabe/Sonstiges eher nicht (interne Bearbeitung bzw. kein direkter
# Antwort-Kontext).
AKTIV = ['anfrage', 'beschwerde']
INAKTIV = ['maengelmeldung', 'intern', 'sonstiges']


def setze_antwort_vorschlag_aktiv(apps, schema_editor):
    VorgangTyp = apps.get_model('vorgaenge', 'VorgangTyp')
    VorgangTyp.objects.filter(code__in=AKTIV).update(antwort_vorschlag_aktiv=True)
    VorgangTyp.objects.filter(code__in=INAKTIV).update(antwort_vorschlag_aktiv=False)


def rueckgaengig(apps, schema_editor):
    VorgangTyp = apps.get_model('vorgaenge', 'VorgangTyp')
    VorgangTyp.objects.filter(code__in=AKTIV + INAKTIV).update(antwort_vorschlag_aktiv=False)


class Migration(migrations.Migration):

    dependencies = [
        ('vorgaenge', '0003_vorgangtyp_antwort_vorschlag_aktiv_and_more'),
    ]

    operations = [
        migrations.RunPython(setze_antwort_vorschlag_aktiv, rueckgaengig),
    ]
