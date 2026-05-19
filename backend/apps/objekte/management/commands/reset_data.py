"""
Management-Command: reset_data
Löscht alle Geschäftsdaten und setzt Sequenzen zurück.

Erhalten bleiben:
- Auth-Tabellen (User, Groups, Permissions)
- ImportOrdnerEinstellung + CamtImportEinstellung  (Ordner-Konfiguration)

Aufruf:
    python manage.py reset_data           # Bestätigung erforderlich
    python manage.py reset_data --force   # Ohne Rückfrage
    python manage.py reset_data --dry-run # Nur anzeigen, nichts löschen
"""

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand
from django.db import connection, transaction


APP_LABELS = [
    'personen',
    'objekte',
    'konten',
    'buchhaltung',
    'rechnungen',
    'prozesse',
    'dokumente',
    'tickets',
    'massenimport',
]

# Tabellen, deren Inhalt vor dem TRUNCATE gesichert und danach wiederhergestellt wird
TABELLEN_ERHALTEN = frozenset({
    'buchhaltung_importordnereinstellung',
    'buchhaltung_camtimporteinstellung',
    'buchhaltung_buchungsart',   # System-Seed aus Migration — darf nicht gelöscht werden
})

# Spalten in gesicherten Tabellen, die auf gelöschte Tabellen zeigen → beim Restore auf NULL setzen
FK_NULLIFY = {
    'buchhaltung_camtimporteinstellung': ['objekt_id'],
}


def _tabellen():
    tabellen = []
    for label in APP_LABELS:
        try:
            app = django_apps.get_app_config(label)
        except LookupError:
            continue
        for model in app.get_models():
            tabellen.append(model._meta.db_table)
    return tabellen


def _backup_table(table_name, cursor):
    cursor.execute(f'SELECT * FROM "{table_name}"')
    if not cursor.description:
        return []
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _restore_table(table_name, data_list, cursor):
    if not data_list:
        return 0
    columns = list(data_list[0].keys())
    columns_sql = ', '.join(f'"{c}"' for c in columns)
    placeholders = ', '.join(['%s'] * len(columns))
    sql = f'INSERT INTO "{table_name}" ({columns_sql}) VALUES ({placeholders})'
    for row in data_list:
        cursor.execute(sql, list(row.values()))
    return len(data_list)


class Command(BaseCommand):
    help = (
        'Löscht alle Geschäftsdaten für Neu-Import. '
        'Importordner-Einstellungen (CAMT + Rechnungen) bleiben erhalten.'
    )

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
        loeschen = sorted(t for t in tabellen if t not in TABELLEN_ERHALTEN)
        erhalten = sorted(t for t in tabellen if t in TABELLEN_ERHALTEN)

        self.stdout.write('\n' + '-' * 62)
        self.stdout.write(self.style.WARNING('  IMMOCORE — Datentabellen zurücksetzen'))
        self.stdout.write('-' * 62)

        self.stdout.write(f'\n  GELÖSCHT ({len(loeschen)} Tabellen):\n')
        for t in loeschen:
            self.stdout.write(f'    - {t}')

        self.stdout.write(f'\n  ERHALTEN (Backup + Restore, {len(erhalten)} Tabellen):\n')
        for t in erhalten:
            self.stdout.write(f'    + {t}')

        self.stdout.write(
            '\n\n  Auth-Tabellen (User, Groups, Permissions) werden nicht berührt.\n'
        )
        self.stdout.write('-' * 62 + '\n')

        if dry_run:
            self.stdout.write(self.style.SUCCESS('  --dry-run aktiv — keine Änderungen.\n'))
            return

        if not force:
            antwort = input(
                '  Wirklich ALLE Geschäftsdaten unwiderruflich löschen? [ja/NEIN]: '
            ).strip().lower()
            if antwort != 'ja':
                self.stdout.write(self.style.NOTICE('  Abgebrochen — keine Änderungen.\n'))
                return

        with transaction.atomic():
            with connection.cursor() as cursor:

                # 1. Importordner-Einstellungen sichern (kein FK auf gelöschte Tabellen)
                self.stdout.write('  Sichere Importordner-Einstellungen...')
                backups = {}
                for t in erhalten:
                    backups[t] = _backup_table(t, cursor)
                    self.stdout.write(f'    • {t}: {len(backups[t])} Zeile(n)')

                # 2. Alles löschen
                self.stdout.write('\n  Lösche alle Geschäftsdaten...')
                alle_sql = ', '.join(f'"{t}"' for t in tabellen)
                cursor.execute(f'TRUNCATE {alle_sql} RESTART IDENTITY CASCADE;')
                self.stdout.write('    ✓ TRUNCATE abgeschlossen')

                # 3. Importordner-Einstellungen wiederherstellen
                self.stdout.write('\n  Stelle Importordner-Einstellungen wieder her...')
                for t in erhalten:
                    daten = backups[t]
                    if t in FK_NULLIFY:
                        felder = FK_NULLIFY[t]
                        daten = [{**row, **{f: None for f in felder}} for row in daten]
                    n = _restore_table(t, daten, cursor)
                    self.stdout.write(f'    + {t}: {n} Zeile(n)')

        self.stdout.write(self.style.SUCCESS(
            '\n  OK: Datenbank zurückgesetzt — bereit für Neu-Import.\n'
        ))
