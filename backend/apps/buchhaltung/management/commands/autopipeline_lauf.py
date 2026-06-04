"""
Management Command: autopipeline_lauf

Führt die Hausgeld-Sollstellungs- und SEPA-Lastschrift-Pipeline
für einen bestimmten Monat manuell aus — identisch zur Nacht-Automatik,
aber mit frei wählbarem Datum (z.B. für Nachläufe vergangener Monate).

Aufruf:
    python manage.py autopipeline_lauf --monat 2025-01
    python manage.py autopipeline_lauf --monat 2025-01 --objekt 10001
    python manage.py autopipeline_lauf --monat 2025-01 --dry-run
    python manage.py autopipeline_lauf --monat 2025-01 --force
"""
import traceback
from datetime import date
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = 'Autopipeline (Sollstellungen + Lastschriften) manuell für einen Monat ausführen'

    def add_arguments(self, parser):
        parser.add_argument(
            '--monat', required=True, type=str,
            help='Periode im Format YYYY-MM (z.B. 2025-01)',
        )
        parser.add_argument(
            '--objekt', type=str, default=None,
            help='Nur dieses Objekt verarbeiten (Objektnummer, z.B. 10001)',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Nur zeigen, welche Objekte verarbeitet würden — nichts buchen.',
        )
        parser.add_argument(
            '--stichtag', type=str, default=None,
            help='Stichtag für SEPA-Fristberechnung (Format: YYYY-MM-DD). '
                 'Default bei Nachläufen: erster Tag der Periode (historisch korrekt).',
        )
        parser.add_argument(
            '--force', action='store_true',
            help='Auch Objekte verarbeiten, deren Idempotenz-Sperre bereits greift '
                 '(bestehende committete Läufe werden NICHT überschrieben — '
                 'der Service loggt sie nur als übersprungen).',
        )

    def handle(self, *args, **options):
        from apps.objekte.models import Objekt
        from apps.buchhaltung.services.auto_pipeline_service import run_objekt

        monat_str = options['monat']
        try:
            jahr, mon = int(monat_str.split('-')[0]), int(monat_str.split('-')[1])
            periode = date(jahr, mon, 1)
        except (ValueError, IndexError):
            self.stderr.write(f'Ungültiges Monatsformat: {monat_str} — erwartet YYYY-MM')
            return

        dry_run     = options['dry_run']
        objekt_nr   = options.get('objekt')

        stichtag_str = options.get('stichtag')
        if stichtag_str:
            try:
                stichtag = date.fromisoformat(stichtag_str)
            except ValueError:
                self.stderr.write(f'Ungültiges Stichtag-Format: {stichtag_str} — erwartet YYYY-MM-DD')
                return
        else:
            # Für Nachläufe historischer Monate: Periode selbst als Stichtag verwenden,
            # damit SEPA-Fristberechnung korrekte (historische) Fälligkeiten liefert.
            stichtag = periode

        User = get_user_model()
        try:
            user = User.objects.get(username='immocore-autopilot')
        except User.DoesNotExist:
            # Fallback: ersten Superuser verwenden
            user = User.objects.filter(is_superuser=True).first()
            if not user:
                self.stderr.write('Kein System-User gefunden. Bitte "immocore-autopilot" anlegen.')
                return
            self.stdout.write(self.style.WARNING(
                f'  System-User "immocore-autopilot" nicht gefunden — verwende "{user.username}"'
            ))

        qs = Objekt.objects.filter(auto_pipeline_aktiv=True, status='aktiv')
        if objekt_nr:
            qs = qs.filter(objektnummer=objekt_nr)

        objekte = list(qs)

        self.stdout.write('\n' + '=' * 70)
        self.stdout.write('  IMMOCORE — Autopipeline Manuell-Lauf')
        self.stdout.write('=' * 70)
        self.stdout.write(f'  Periode  : {periode.strftime("%B %Y")} ({periode})')
        self.stdout.write(f'  Stichtag : {stichtag}')
        self.stdout.write(f'  Objekte  : {len(objekte)}')
        self.stdout.write(f'  User     : {user.username}')
        if dry_run:
            self.stdout.write(self.style.WARNING('  --dry-run: keine Buchungen\n'))

        if not objekte:
            self.stdout.write(self.style.WARNING('\n  Keine passenden Objekte gefunden.'))
            if objekt_nr:
                self.stdout.write(f'  (Objektnummer "{objekt_nr}" mit auto_pipeline_aktiv=True und status=aktiv gesucht)')
            return

        self.stdout.write('-' * 70)
        for obj in objekte:
            self.stdout.write(f'  {obj.objektnummer}  {obj.bezeichnung}')
        self.stdout.write('-' * 70 + '\n')

        if dry_run:
            self.stdout.write(self.style.SUCCESS('  Dry-run abgeschlossen — keine Änderungen.'))
            return

        erfolg = fehler = uebersprungen = 0

        for objekt in objekte:
            self.stdout.write(f'  → {objekt.objektnummer} {objekt.bezeichnung} … ', ending='')
            try:
                protokoll = run_objekt(objekt=objekt, periode=periode, user=user, stichtag=stichtag)
                if protokoll.status == 'uebersprungen':
                    self.stdout.write(self.style.WARNING('übersprungen (committet bereits vorhanden)'))
                    uebersprungen += 1
                elif protokoll.status == 'fehler':
                    self.stdout.write(self.style.ERROR(f'FEHLER: {protokoll.fehler[:120]}'))
                    fehler += 1
                else:
                    info = (
                        f'OK [{protokoll.status}] '
                        f'— {protokoll.anzahl_evs_erfolgreich}/{protokoll.anzahl_evs_geplant} EVs'
                        f', Summe {protokoll.summe_sollstellungen} €'
                    )
                    self.stdout.write(self.style.SUCCESS(info))
                    erfolg += 1
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f'FEHLER: {exc}'))
                self.stderr.write(traceback.format_exc())
                fehler += 1

        self.stdout.write('\n' + '=' * 70)
        self.stdout.write(self.style.SUCCESS(
            f'  Fertig: {erfolg} erfolgreich, {uebersprungen} übersprungen, {fehler} Fehler'
        ))
        self.stdout.write('=' * 70 + '\n')
