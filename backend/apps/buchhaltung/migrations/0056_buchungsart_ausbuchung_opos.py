"""
Buchungsart 056 AUSB-K — Ausbuchung offener Kreditor-Posten.

Für Posten, bei denen zum Jahresende nicht mehr mit einem Ausgleich zu
rechnen ist. Bewusst OHNE `richtung`: die Buchungsseite hängt nicht an der
Buchungsart, sondern je Posten daran, ob er eine Verbindlichkeit oder eine
Forderung ist (siehe kreditor_ausbuchung_service).

Idempotent über get_or_create — Vorbild: 0053_buchungsarten_kreditorische_zahlung.
"""
from django.db import migrations

NR = '056'


def anlegen(apps, schema_editor):
    Buchungsart = apps.get_model('buchhaltung', 'Buchungsart')
    Buchungsart.objects.get_or_create(
        nr=NR,
        defaults=dict(
            kuerzel='AUSB-K',
            bezeichnung='Ausbuchung offener Posten',
            einzelabrechnung='nein',
            gesamtabrechnung=False,
            ruecklagen_relevant=False,
            umlage='gesperrt',
            beleg_pflicht=False,
            beschluss_pflicht=False,
            vier_augen_schwelle=None,
            sperre_nach_jahresabschluss=True,
            system_buchungsart=False,
            default_konto_soll_pattern='',
            default_konto_haben_pattern='',
            aktiv=True,
            buchungstyp='kreditor',
            richtung=None,
        ),
    )


def entfernen(apps, schema_editor):
    Buchungsart = apps.get_model('buchhaltung', 'Buchungsart')
    Buchung = apps.get_model('buchhaltung', 'Buchung')
    # Bereits bebuchte BA bleibt stehen — Buchungen zeigen per PROTECT darauf.
    if Buchung.objects.filter(buchungsart__nr=NR).exists():
        return
    Buchungsart.objects.filter(nr=NR, buchungstyp='kreditor').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0055_kreditorop_ausgebucht_am_kreditorop_ausgebucht_von_and_more'),
    ]

    operations = [
        migrations.RunPython(anlegen, entfernen),
    ]
