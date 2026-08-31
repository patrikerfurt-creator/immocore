"""
Buchungsarten für die kreditorische Zahlung in der Dialogbuchhaltung.

Der Modus "Kreditorenbuchung" füllt sein BA-Dropdown über
/buchungsarten/manuell-waehlbar/?buchungstyp=kreditor. Ohne BA mit
buchungstyp='kreditor' bleibt es leer. Angelegt werden beide Richtungen:
Zahlungsausgang (Zahlung an den Kreditor) und Zahlungseingang (Rückzahlung
oder Erstattung vom Kreditor).

Idempotent über get_or_create — Vorbild: 0050_buchungsart_saldovortrag.
Gleiche Feldbelegung wie 051 AUSG-K im BA-Katalog (seed_buchungsarten).
"""
from django.db import migrations

BUCHUNGSARTEN = [
    ('054', 'ZE-K', 'Zahlungseingang'),
    ('055', 'ZA-K', 'Zahlungsausgang'),
]


def anlegen(apps, schema_editor):
    Buchungsart = apps.get_model('buchhaltung', 'Buchungsart')
    for nr, kuerzel, bezeichnung in BUCHUNGSARTEN:
        Buchungsart.objects.get_or_create(
            nr=nr,
            defaults=dict(
                kuerzel=kuerzel,
                bezeichnung=bezeichnung,
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
            ),
        )


def entfernen(apps, schema_editor):
    Buchungsart = apps.get_model('buchhaltung', 'Buchungsart')
    Buchung = apps.get_model('buchhaltung', 'Buchung')
    for nr, _kuerzel, _bezeichnung in BUCHUNGSARTEN:
        # Bereits bebuchte BAs bleiben stehen — Buchungen dürfen ihre
        # Buchungsart nicht verlieren (PROTECT).
        if Buchung.objects.filter(buchungsart__nr=nr).exists():
            continue
        Buchungsart.objects.filter(nr=nr, buchungstyp='kreditor').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0052_kreditorop_vortrag_am_kreditorop_vortrag_von_and_more'),
    ]

    operations = [
        migrations.RunPython(anlegen, entfernen),
    ]
