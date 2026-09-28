"""
Leitet ``posteingang_status`` fuer bereits verarbeitete Mails aus dem
Import-Ergebnis ab.

Ohne diesen Schritt bekaeme jede Bestandszeile den Feld-Default 'offen' —
auch die Mails, die der Import laengst zugeordnet hat. Die Posteingangsliste
waere damit beim ersten Aufruf voll mit erledigten Faellen.
"""
from django.db import migrations


# Nur wirklich unzugeordnete Mails gehoeren in den Posteingang. Alles andere
# (angelegt, Thread-Treffer, Duplikat, Fehler) ist entschieden.
OFFEN_AB_STATUS = ['nicht_zugeordnet']


def leite_ab(apps, schema_editor):
    MailImportProtokoll = apps.get_model('vorgaenge', 'MailImportProtokoll')
    MailImportProtokoll.objects.exclude(status__in=OFFEN_AB_STATUS).update(
        posteingang_status='automatisch')
    MailImportProtokoll.objects.filter(status__in=OFFEN_AB_STATUS).update(
        posteingang_status='offen')


def zurueck(apps, schema_editor):
    # Der Feld-Default reicht als Rueckfallebene — die Ableitung ist
    # jederzeit reproduzierbar.
    MailImportProtokoll = apps.get_model('vorgaenge', 'MailImportProtokoll')
    MailImportProtokoll.objects.update(posteingang_status='offen')


class Migration(migrations.Migration):

    dependencies = [
        ('vorgaenge', '0011_mailimportprotokoll_erledigt_am_and_more'),
    ]

    operations = [
        migrations.RunPython(leite_ab, zurueck),
    ]
