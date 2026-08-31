"""
Buchungsrichtung der kreditorischen Zahlungs-BAs setzen.

`richtung` steuert in der Dialogbuchhaltung, auf welcher Seite das Gegenkonto
steht. Beim Zahlungsausgang wird die Verbindlichkeit abgebaut — das
Kreditorkonto gehört ins Soll, die Bank ins Haben. Beim Zahlungseingang
(Rückzahlung/Erstattung vom Kreditor) umgekehrt.

Das Feld galt bisher nur für Personenkonten; die Choice-Labels werden
entsprechend allgemein formuliert (Gegenkonto statt Personenkonto).
"""
from django.db import migrations, models

RICHTUNGEN = {
    '054': 'eingang',   # Zahlungseingang
    '055': 'abgang',    # Zahlungsausgang
}


def richtung_setzen(apps, schema_editor):
    Buchungsart = apps.get_model('buchhaltung', 'Buchungsart')
    for nr, richtung in RICHTUNGEN.items():
        Buchungsart.objects.filter(nr=nr, buchungstyp='kreditor').update(richtung=richtung)


def richtung_zuruecksetzen(apps, schema_editor):
    Buchungsart = apps.get_model('buchhaltung', 'Buchungsart')
    Buchungsart.objects.filter(
        nr__in=list(RICHTUNGEN), buchungstyp='kreditor').update(richtung=None)


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0053_buchungsarten_kreditorische_zahlung'),
    ]

    operations = [
        migrations.AlterField(
            model_name='buchungsart',
            name='richtung',
            field=models.CharField(blank=True, choices=[('eingang', 'Eingang (Bank → Gegenkonto)'), ('abgang', 'Abgang (Gegenkonto → Bank)')], help_text='Bestimmt die Buchungsrichtung in der Dialogbuchhaltung automatisch. Gegenkonto ist je Buchungstyp das Personenkonto bzw. das Kreditorkonto. "abgang" = Gegenkonto im Soll, Bank im Haben.', max_length=10, null=True),
        ),
        migrations.RunPython(richtung_setzen, richtung_zuruecksetzen),
    ]
