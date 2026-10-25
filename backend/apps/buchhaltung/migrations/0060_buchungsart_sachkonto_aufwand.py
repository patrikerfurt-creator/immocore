"""
Buchungsart 040 SACH-A — Sachkontenbuchung Aufwand (Bewirtschaftung).

Abrechnungsrelevante Sachkontobuchung: Aufwand, der in die Gesamt- und
Einzelabrechnung einfließt und per Verteilerschlüssel auf die Eigentümer
umgelegt wird. Erscheint in der Dialogbuchhaltung im Sachkonto-Modus.
Bewusst OHNE `richtung` — Soll/Haben wählt der Bearbeiter frei.

Idempotent über get_or_create — Vorbild: 0056_buchungsart_ausbuchung_opos.
"""
from django.db import migrations

NR = '040'


def anlegen(apps, schema_editor):
    Buchungsart = apps.get_model('buchhaltung', 'Buchungsart')
    Buchungsart.objects.get_or_create(
        nr=NR,
        defaults=dict(
            kuerzel='SACH-A',
            bezeichnung='Sachkontenbuchung Aufwand (Bewirtschaftung)',
            einzelabrechnung='ja',
            gesamtabrechnung=True,
            ruecklagen_relevant=False,
            umlage='pflicht',
            beleg_pflicht=True,
            beschluss_pflicht=False,
            vier_augen_schwelle=10000,
            sperre_nach_jahresabschluss=True,
            system_buchungsart=False,
            default_konto_soll_pattern='',
            default_konto_haben_pattern='',
            aktiv=True,
            buchungstyp='sachkonto',
            richtung=None,
        ),
    )


def entfernen(apps, schema_editor):
    Buchungsart = apps.get_model('buchhaltung', 'Buchungsart')
    Buchung = apps.get_model('buchhaltung', 'Buchung')
    # Bereits bebuchte BA bleibt stehen — Buchungen zeigen per PROTECT darauf.
    if Buchung.objects.filter(buchungsart__nr=NR).exists():
        return
    Buchungsart.objects.filter(nr=NR, buchungstyp='sachkonto').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0059_mahneinstellung'),
    ]

    operations = [
        migrations.RunPython(anlegen, entfernen),
    ]
