"""
Data-Migration: Legt Standard-Buchungsarten für das Hausgeld-Nebenbuch an
und verknüpft bestehende HausgeldHistorie-Einträge mit der passenden BA.
"""
from django.db import migrations

BUCHUNGSARTEN = [
    {'nr': '900', 'kuerzel': 'HG',   'bezeichnung': 'Hausgeld',                    'bankkonto_typ': 'bewirtschaftung',      'erloeskonto_default_nr': '41900'},
    {'nr': '911', 'kuerzel': 'RL1',  'bezeichnung': 'Rücklage I',                  'bankkonto_typ': 'ruecklage_nach_index', 'erloeskonto_default_nr': '41911'},
    {'nr': '912', 'kuerzel': 'RL2',  'bezeichnung': 'Rücklage II',                 'bankkonto_typ': 'ruecklage_nach_index', 'erloeskonto_default_nr': '41912'},
    {'nr': '913', 'kuerzel': 'RL3',  'bezeichnung': 'Rücklage III',                'bankkonto_typ': 'ruecklage_nach_index', 'erloeskonto_default_nr': '41913'},
    {'nr': '914', 'kuerzel': 'RL4',  'bezeichnung': 'Rücklage IV',                 'bankkonto_typ': 'ruecklage_nach_index', 'erloeskonto_default_nr': '41914'},
    {'nr': '915', 'kuerzel': 'RL5',  'bezeichnung': 'Rücklage V',                  'bankkonto_typ': 'ruecklage_nach_index', 'erloeskonto_default_nr': '41915'},
    {'nr': '916', 'kuerzel': 'RL6',  'bezeichnung': 'Rücklage VI',                 'bankkonto_typ': 'ruecklage_nach_index', 'erloeskonto_default_nr': '41916'},
    {'nr': '917', 'kuerzel': 'RL7',  'bezeichnung': 'Rücklage VII',                'bankkonto_typ': 'ruecklage_nach_index', 'erloeskonto_default_nr': '41917'},
    {'nr': '918', 'kuerzel': 'RL8',  'bezeichnung': 'Rücklage VIII',               'bankkonto_typ': 'ruecklage_nach_index', 'erloeskonto_default_nr': '41918'},
    {'nr': '930', 'kuerzel': 'SU',   'bezeichnung': 'Sonderumlage',                'bankkonto_typ': 'bewirtschaftung',      'erloeskonto_default_nr': '41930'},
    {'nr': '940', 'kuerzel': 'MAH',  'bezeichnung': 'Mahngebühren',                'bankkonto_typ': 'bewirtschaftung',      'erloeskonto_default_nr': '41940'},
    {'nr': '941', 'kuerzel': 'RLG',  'bezeichnung': 'Rücklastschriftgebühren',     'bankkonto_typ': 'bewirtschaftung',      'erloeskonto_default_nr': '41941'},
    {'nr': '950', 'kuerzel': 'ABR',  'bezeichnung': 'Abrechnung Vorjahr',          'bankkonto_typ': 'bewirtschaftung',      'erloeskonto_default_nr': '41950'},
]


def seed_buchungsarten(apps, schema_editor):
    Buchungsart = apps.get_model('buchhaltung', 'Buchungsart')
    HausgeldHistorie = apps.get_model('personen', 'HausgeldHistorie')

    ba_by_nr = {}
    for bd in BUCHUNGSARTEN:
        ba, _ = Buchungsart.objects.get_or_create(
            nr=bd['nr'],
            defaults={
                'kuerzel':                bd['kuerzel'],
                'bezeichnung':            bd['bezeichnung'],
                'einzelabrechnung':       'nein',
                'gesamtabrechnung':       False,
                'ruecklagen_relevant':    bd['nr'].startswith('91'),
                'umlage':                 'pflicht',
                'beleg_pflicht':          False,
                'beschluss_pflicht':      False,
                'sperre_nach_jahresabschluss': False,
                'system_buchungsart':     False,
                'aktiv':                  True,
                'bankkonto_typ':          bd['bankkonto_typ'],
                'erloeskonto_default_nr': bd['erloeskonto_default_nr'],
            },
        )
        ba_by_nr[bd['nr']] = ba

    # Rückwirkend ba setzen für alle Historien die nur abrechnungsart haben
    for h in HausgeldHistorie.objects.filter(ba__isnull=True, abrechnungsart__isnull=False).select_related('abrechnungsart'):
        code = h.abrechnungsart.code
        ba = ba_by_nr.get(code)
        if ba:
            h.ba = ba
            h.save(update_fields=['ba'])


def remove_buchungsarten(apps, schema_editor):
    Buchungsart = apps.get_model('buchhaltung', 'Buchungsart')
    nrs = [bd['nr'] for bd in BUCHUNGSARTEN]
    Buchungsart.objects.filter(nr__in=nrs, system_buchungsart=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0020_drop_alte_sollstellung_welt'),
        ('personen', '0010_hausgeldhistorie_ba'),
    ]

    operations = [
        migrations.RunPython(seed_buchungsarten, remove_buchungsarten),
    ]
