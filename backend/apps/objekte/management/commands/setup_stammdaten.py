"""
Management-Command: setup_stammdaten
Legt Kontenrahmen, Abrechnungsarten und Verteilerschlüssel für alle Objekte nach
(oder ein einzelnes Objekt via --objektnummer). Idempotent — bereits vorhandene
Datensätze werden nicht doppelt angelegt.

Aufruf:
    python manage.py setup_stammdaten                       # alle Objekte
    python manage.py setup_stammdaten --objektnummer 10001  # ein Objekt
    python manage.py setup_stammdaten --dry-run             # nur anzeigen
"""

from django.core.management.base import BaseCommand

from apps.objekte.models import Objekt
from apps.konten.services import (
    kontenrahmen_anlegen,
    abrechnungsarten_anlegen,
    verteilerschluessel_anlegen,
)
from apps.konten.models import Konto, Abrechnungsart
from apps.objekte.models import Verteilerschluessel
from apps.massenimport.services import _ruecklage_konten_defs


class Command(BaseCommand):
    help = 'Legt Kontenrahmen, Abrechnungsarten und Verteilerschluessel fuer Objekte an (Nachholimport)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--objektnummer',
            type=str,
            default=None,
            help='Nur dieses Objekt bearbeiten (Objektnummer, z.B. 10001)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Nur anzeigen, was angelegt werden wuerde — kein DB-Commit',
        )

    def handle(self, *args, **options):
        dry_run       = options['dry_run']
        objektnummer  = options['objektnummer']

        qs = Objekt.objects.prefetch_related('bankkonten', 'einheiten')
        if objektnummer:
            qs = qs.filter(objektnummer=objektnummer)
            if not qs.exists():
                self.stderr.write(f'Objekt "{objektnummer}" nicht gefunden.')
                return

        objekte = list(qs.order_by('objektnummer'))

        self.stdout.write('\n' + '-' * 60)
        self.stdout.write('  IMMOCORE - Stammdaten nachholgen')
        self.stdout.write('-' * 60)
        self.stdout.write(f'  {len(objekte)} Objekt(e) werden bearbeitet')
        if dry_run:
            self.stdout.write('  --dry-run: keine Aenderungen\n')
        self.stdout.write('-' * 60 + '\n')

        gesamt_konten      = 0
        gesamt_abr         = 0
        gesamt_vs          = 0

        for objekt in objekte:
            anz_rl = objekt.bankkonten.filter(konto_typ='ruecklage').count()
            anz_einheiten = objekt.einheiten.count()

            fehlend_konten = 0
            fehlend_abr    = 0
            fehlend_vs     = 0

            if dry_run:
                hat_konten = Konto.objects.filter(objekt=objekt).exists()
                hat_abr    = Abrechnungsart.objects.filter(objekt=objekt).exists()
                hat_vs     = Verteilerschluessel.objects.filter(objekt=objekt).exists()
                self.stdout.write(
                    f'  [{objekt.objektnummer}] {objekt.bezeichnung} '
                    f'(Typ={objekt.objekt_typ}, RL={anz_rl}, Einheiten={anz_einheiten})'
                )
                self.stdout.write(
                    f'    Kontenrahmen: {"vorhanden" if hat_konten else "FEHLT"} | '
                    f'Abrechnungsarten: {"vorhanden" if hat_abr else "FEHLT"} | '
                    f'Verteilerschluessel: {"vorhanden" if hat_vs else "FEHLT"}'
                )
                continue

            self.stdout.write(
                f'  [{objekt.objektnummer}] {objekt.bezeichnung} '
                f'(Typ={objekt.objekt_typ}, RL={anz_rl}, Einheiten={anz_einheiten}) ...',
                ending='',
            )

            # 1. Kontenrahmen (nur WEG)
            if objekt.objekt_typ == 'WEG':
                r = kontenrahmen_anlegen(str(objekt.id))
                fehlend_konten += r.get('angelegt', 0)

                # Rucklage II+ Konten
                for n in range(1, anz_rl + 1):
                    from apps.konten.models import Konto as _Konto
                    for kd in _ruecklage_konten_defs(n):
                        _, created = _Konto.objects.get_or_create(
                            objekt=objekt,
                            kontonummer=kd['kontonummer'],
                            defaults={**kd, 'arge_kostenart': None, 'aktiv': True},
                        )
                        if created:
                            fehlend_konten += 1

            # 2. Abrechnungsarten
            ruecklagen_list = [
                {'reihenfolge': i}
                for i in range(1, anz_rl + 1)
            ]
            n_abr = abrechnungsarten_anlegen(str(objekt.id), ruecklagen_list)
            fehlend_abr += n_abr

            # Zusatz-Abrechnungsarten fuer Rucklage II+ (komplementar zu abrechnungsarten_anlegen)
            from apps.konten.models import Abrechnungsart as _Abr
            from apps.massenimport.services import _roman
            for n in range(2, anz_rl + 1):
                _, created = _Abr.objects.get_or_create(
                    objekt=objekt,
                    code=str(910 + n),
                    defaults={'bezeichnung': f'Ruecklage {_roman(n)}', 'aktiv': True},
                )
                if created:
                    fehlend_abr += 1

            # 3. Verteilerschluessel + VSBeteiligung
            n_vs = verteilerschluessel_anlegen(str(objekt.id))
            fehlend_vs += n_vs

            gesamt_konten += fehlend_konten
            gesamt_abr    += fehlend_abr
            gesamt_vs     += fehlend_vs

            self.stdout.write(
                f' Konten+{fehlend_konten} Abr+{fehlend_abr} VS+{fehlend_vs}'
            )

        self.stdout.write('\n' + '-' * 60)
        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f'  Fertig: +{gesamt_konten} Konten, '
                    f'+{gesamt_abr} Abrechnungsarten, '
                    f'+{gesamt_vs} Verteilerschluessel angelegt.\n'
                )
            )
        else:
            self.stdout.write(self.style.WARNING('  --dry-run: keine Aenderungen vorgenommen.\n'))
