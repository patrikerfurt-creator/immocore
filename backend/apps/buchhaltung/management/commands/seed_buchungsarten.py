"""
Seed-Command: Legt die 27 Buchungsarten (BA-Katalog) gemäß MODUL_BUCHHALTUNG.md an.
Idempotent — vorhandene BAs werden übersprungen.
"""
from django.core.management.base import BaseCommand
from apps.buchhaltung.models import Buchungsart


BA_KATALOG = [
    # nr, kuerzel, bezeichnung, einzelabr, gesamt, ruecklage, umlage, beleg, beschluss, system, soll_pat, haben_pat
    ('001', 'SAVO-S', 'Saldenvortrag Sachkonten',                   'nein', False, False, 'gesperrt', False, False, True,  '', ''),
    ('002', 'SAVO-P', 'Saldenvortrag Personenkonten',               'nein', False, False, 'gesperrt', False, False, True,  '', ''),
    ('003', 'SAVO-K', 'Saldenvortrag Kreditoren',                   'nein', False, False, 'gesperrt', False, False, True,  '', ''),
    ('004', 'SAVO-B', 'Saldenvortrag Bankkonten',                   'nein', False, False, 'gesperrt', False, False, True,  '', ''),
    ('010', 'HGV',    'Sollstellung Hausgeldvorauszahlung',          'ja',   True,  False, 'gesperrt', False, False, True,  '', ''),
    ('011', 'RLZ',    'Sollstellung Rücklagenzuführung',             'nein', False, True,  'gesperrt', False, False, True,  '.911', ''),
    ('012', 'SU',     'Sonderumlage',                                'ja',   True,  False, 'pflicht',  True,  True,  True,  '', ''),
    ('013', 'NZJA',   'Nachzahlung aus Jahresabrechnung',            'nein', False, False, 'gesperrt', False, False, True,  '', ''),
    ('014', 'GJA',    'Guthaben aus Jahresabrechnung',               'nein', False, False, 'gesperrt', False, False, True,  '', ''),
    ('015', 'MIETE',  'Miete (ZH/SEV)',                              'nein', False, False, 'gesperrt', False, False, True,  '', ''),
    ('016', 'NKVZ',   'Nebenkostenvorauszahlung (ZH/SEV)',           'nein', False, False, 'gesperrt', False, False, True,  '', ''),
    ('020', 'EING-P', 'Eingang Personenkonto (Zahlung)',             'nein', False, False, 'gesperrt', False, False, False, '', ''),
    ('021', 'AUSG-P', 'Ausgang Personenkonto (Erstattung)',          'nein', False, False, 'gesperrt', False, False, False, '', ''),
    ('022', 'UMB-P',  'Umbuchung Personenkonto',                     'nein', False, False, 'gesperrt', False, False, False, '', ''),
    ('023', 'MAHNG',  'Mahngebühr',                                  'nein', False, False, 'gesperrt', False, False, True,  '', ''),
    ('024', 'VERZZ',  'Verzugszinsen (§ 288 BGB)',                   'nein', False, False, 'gesperrt', False, False, True,  '', ''),
    ('040', 'SACH-A', 'Sachkontenbuchung Aufwand (Bewirtschaftung)', 'ja',   True,  False, 'pflicht',  True,  False, False, '', ''),
    ('041', 'SACH-AR','Sachkontenbuchung Aufwand (Rücklage)',        'nein', False, True,  'gesperrt', True,  True,  False, '', '.911'),
    ('042', 'SACH-E', 'Sachkontenbuchung Ertrag (Bewirtschaftung)', 'ja',   True,  False, 'optional', True,  False, False, '', ''),
    ('043', 'SACH-ER','Sachkontenbuchung Ertrag (Rücklage, Zinsen)','nein', False, True,  'gesperrt', True,  False, False, '', '.911'),
    ('044', 'SACH-U', 'Sachkonten-Umbuchung (nicht abr.-relevant)', 'nein', False, False, 'gesperrt', False, False, False, '', ''),
    ('050', 'EING-K', 'Eingang Kreditor (Rechnungseingang)',         'ja',   True,  False, 'optional', True,  False, False, '', ''),
    ('051', 'AUSG-K', 'Ausgang Kreditor (Zahlung)',                  'nein', False, False, 'gesperrt', False, False, False, '', ''),
    ('052', 'GS-K',   'Kreditoren-Gutschrift',                       'nein', False, False, 'gesperrt', True,  False, False, '', ''),
    ('053', 'SKT-K',  'Skonto / Rabatt Kreditor',                    'nein', False, False, 'gesperrt', False, False, False, '', ''),
    ('080', 'ARAP-B', 'ARAP-Bildung',                                'nein', False, False, 'gesperrt', True,  False, False, '', ''),
    ('081', 'ARAP-A', 'ARAP-Auflösung',                              'ja',   True,  False, 'optional', False, False, False, '', ''),
    ('082', 'PRAP-B', 'PRAP-Bildung',                                'nein', False, False, 'gesperrt', True,  False, False, '', ''),
    ('083', 'PRAP-A', 'PRAP-Auflösung',                              'ja',   True,  False, 'optional', False, False, False, '', ''),
    ('090', 'JA-ABS', 'Jahresabschluss-Buchung',                     'nein', False, False, 'gesperrt', True,  False, True,  '', ''),
    ('091', 'RL-ENT', 'Rücklagenentwicklung (Jahresbuchung)',        'nein', False, True,  'gesperrt', True,  False, True,  '', '.911'),
    ('098', 'STO',    'Storno (spiegelt Original-BA)',                'nein', False, False, 'gesperrt', True,  False, False, '', ''),
    ('099', 'KOR',    'Korrekturbuchung (spiegelt Original-BA)',      'nein', False, False, 'gesperrt', True,  False, False, '', ''),
]

VIER_AUGEN_SCHWELLEN = {
    '012': 5000,
    '040': 10000,
    '041': 5000,
}


class Command(BaseCommand):
    help = 'Legt die Standard-Buchungsarten (BA-Katalog) an (idempotent)'

    def handle(self, *args, **options):
        created = 0
        skipped = 0

        for row in BA_KATALOG:
            (nr, kuerzel, bezeichnung, einzelabr, gesamt, ruecklage,
             umlage, beleg, beschluss, system, soll_pat, haben_pat) = row

            obj, was_created = Buchungsart.objects.update_or_create(
                nr=nr,
                defaults=dict(
                    kuerzel=kuerzel,
                    bezeichnung=bezeichnung,
                    einzelabrechnung=einzelabr,
                    gesamtabrechnung=gesamt,
                    ruecklagen_relevant=ruecklage,
                    umlage=umlage,
                    beleg_pflicht=beleg,
                    beschluss_pflicht=beschluss,
                    system_buchungsart=system,
                    default_konto_soll_pattern=soll_pat,
                    default_konto_haben_pattern=haben_pat,
                    vier_augen_schwelle=VIER_AUGEN_SCHWELLEN.get(nr),
                    aktiv=True,
                ),
            )

            if was_created:
                created += 1
                self.stdout.write(f'  + {nr} {kuerzel}')
            else:
                skipped += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'\nFertig: {created} angelegt, {skipped} bereits vorhanden.'
            )
        )
