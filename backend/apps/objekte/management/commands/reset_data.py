"""
Management-Command: reset_data
Löscht alle Geschäftsdaten und setzt Sequenzen zurück.
Auth-Tabellen (User, Groups, Permissions) bleiben erhalten.

Aufruf:
    python manage.py reset_data           # Bestätigung erforderlich
    python manage.py reset_data --force   # Ohne Rückfrage
    python manage.py reset_data --dry-run # Nur anzeigen, nichts löschen
"""

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand
from django.db import connection


APP_LABELS = [
    'objekte',
    'personen',
    'konten',
    'buchhaltung',
    'rechnungen',
    'prozesse',
    'dokumente',
    'tickets',
    'massenimport',
]


def _tabellen():
    """Gibt alle DB-Tabellennamen der Geschäftsdaten-Apps zurück."""
    tabellen = []
    for label in APP_LABELS:
        try:
            app = django_apps.get_app_config(label)
        except LookupError:
            continue
        for model in app.get_models():
            tabellen.append(model._meta.db_table)
    return tabellen


class Command(BaseCommand):
    help = 'Löscht alle Geschäftsdaten (ohne User/Auth) — für Neu-Import'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force', '-f',
            action='store_true',
            help='Ohne Bestätigungsabfrage ausführen',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Nur anzeigen, was gelöscht würde — kein DB-Commit',
        )

    def handle(self, *args, **options):
        force   = options['force']
        dry_run = options['dry_run']

        tabellen = _tabellen()

        self.stdout.write('\n' + '-' * 60)
        self.stdout.write(self.style.WARNING('  IMMOCORE - Datentabellen zuruecksetzen'))
        self.stdout.write('-' * 60)
        self.stdout.write(f'\n  Folgende {len(tabellen)} Tabellen werden geleert:\n')

        for t in sorted(tabellen):
            self.stdout.write(f'    - {t}')

        self.stdout.write(
            '\n  Auth-Tabellen (User, Groups, Permissions) bleiben erhalten.\n'
        )
        self.stdout.write('-' * 60 + '\n')

        if dry_run:
            self.stdout.write(self.style.SUCCESS('  --dry-run aktiv - keine Aenderungen vorgenommen.\n'))
            return

        if not force:
            antwort = input(
                '  Wirklich ALLE Geschäftsdaten unwiderruflich löschen? [ja/NEIN]: '
            ).strip().lower()
            if antwort != 'ja':
                self.stdout.write(self.style.NOTICE('  Abgebrochen - keine Aenderungen.\n'))
                return

        self.stdout.write('  Loesche Daten ...')

        tabellen_sql = ', '.join(f'"{t}"' for t in tabellen)
        with connection.cursor() as cursor:
            cursor.execute(
                f'TRUNCATE {tabellen_sql} RESTART IDENTITY CASCADE;'
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'\n  OK: {len(tabellen)} Tabellen geleert - Datenbank bereit fuer Neu-Import.\n'
            )
        )
