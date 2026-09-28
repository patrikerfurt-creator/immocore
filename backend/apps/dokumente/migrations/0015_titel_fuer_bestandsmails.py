"""
Traegt den Titel fuer bereits importierte Mails nach.

Der KI-Kurzbetreff liegt seit dem Import im ``MailImportProtokoll``, wurde
bisher aber nur fuer den Vorgangsbetreff genutzt. Am Dokument macht er die
Mail in der Akte lesbar: statt

    "Bestätigung Mülltonnenreinigung (Wingertstraße 29-31, 60316 Frankfurt
     am Main).msg"

steht dort

    "Bestätigung Mülltonnenreinigung Wingertstraße 29-31"

Der DATEINAME bleibt unveraendert — er ist die Bruecke zur Datei im
Archivordner.

Anhaenge bekommen bewusst KEINEN Titel aus dem Mailbetreff: Eine Rechnung
im Anhang einer Mail heisst nicht wie die Mail, und ein falscher Titel ist
schlechter als gar keiner. Fuer Rechnungsbelege leitet
``Dokument.anzeigename`` den Namen ohnehin aus der Rechnung ab.
"""
from django.db import migrations


def titel_nachtragen(apps, schema_editor):
    Dokument = apps.get_model('dokumente', 'Dokument')

    # Nur die Mail selbst (Kategorie "E-Mail Posteingang"), nicht die
    # Anhaenge, und nur wo noch kein Titel steht.
    betroffen = Dokument.objects.filter(
        mail_import__isnull=False,
        kategorie='E-Mail Posteingang',
        titel='',
    ).select_related('mail_import')

    for dokument in betroffen:
        protokoll = dokument.mail_import
        titel = (protokoll.ki_betreff or protokoll.betreff or '').strip()
        if titel:
            dokument.titel = titel[:200]
            dokument.save(update_fields=['titel'])


def zurueck(apps, schema_editor):
    Dokument = apps.get_model('dokumente', 'Dokument')
    Dokument.objects.filter(
        mail_import__isnull=False, kategorie='E-Mail Posteingang',
    ).update(titel='')


class Migration(migrations.Migration):

    dependencies = [
        ('dokumente', '0014_dokument_titel'),
        # Das Protokoll mit ki_betreff muss existieren.
        ('vorgaenge', '0013_seed_vorgangtyp_fallakten'),
    ]

    operations = [
        migrations.RunPython(titel_nachtragen, zurueck),
    ]
