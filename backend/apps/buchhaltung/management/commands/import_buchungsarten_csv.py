"""
Import-Command: Liest buchungsarten.csv und legt Buchungsarten an / aktualisiert sie.
Idempotent — bestehende Einträge werden per update_or_create aktualisiert.

Aufruf:
    python manage.py import_buchungsarten_csv
    python manage.py import_buchungsarten_csv --csv /pfad/zur/datei.csv
    python manage.py import_buchungsarten_csv --dry-run
"""
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.buchhaltung.models import Buchungsart

DEFAULT_CSV = Path(__file__).resolve().parents[5] / 'buchungsarten.csv'

BOOL_MAP = {'true': True, 'false': False, '1': True, '0': False, 'ja': True, 'nein': False}
EINZELABR_VALUES = {'ja', 'nein', 'anteilig'}
UMLAGE_VALUES = {'pflicht', 'optional', 'gesperrt'}
BANKKONTO_TYP_VALUES = {'bewirtschaftung', 'ruecklage_nach_index', 'frei', ''}
BUCHUNGSTYP_VALUES   = {'sachkonto', 'personenkonto', 'kreditor', ''}


def _bool(val: str) -> bool:
    return BOOL_MAP.get(val.strip().lower(), False)


def _decimal_or_none(val: str):
    val = val.strip()
    if not val:
        return None
    try:
        return Decimal(val)
    except InvalidOperation:
        raise ValueError(f"Ungültiger Dezimalwert: {val!r}")


def _int_or_none(val: str):
    val = val.strip()
    if not val:
        return None
    try:
        return int(val)
    except ValueError:
        raise ValueError(f"Ungültiger Ganzzahlwert: {val!r}")


class Command(BaseCommand):
    help = 'Importiert Buchungsarten aus buchungsarten.csv (Semikolon-getrennt)'

    def add_arguments(self, parser):
        parser.add_argument('--csv', type=str, default=str(DEFAULT_CSV),
                            help='Pfad zur CSV-Datei (Standard: buchungsarten.csv im Projektstamm)')
        parser.add_argument('--dry-run', action='store_true',
                            help='Nur prüfen, keine Datenbankänderungen vornehmen')

    def handle(self, *args, **options):
        csv_path = Path(options['csv'])
        dry_run = options['dry_run']

        if not csv_path.exists():
            raise CommandError(f'CSV-Datei nicht gefunden: {csv_path}')

        self.stdout.write(f'Lese: {csv_path}')
        if dry_run:
            self.stdout.write(self.style.WARNING('  → DRY-RUN: keine Datenbankänderungen'))

        created = updated = fehler = 0

        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter=';')
            for i, row in enumerate(reader, start=2):
                nr = row.get('nr', '').strip()
                if not nr:
                    self.stdout.write(self.style.WARNING(f'  Zeile {i}: nr fehlt, übersprungen'))
                    continue

                einzelabr = row.get('einzelabrechnung', 'nein').strip().lower()
                if einzelabr not in EINZELABR_VALUES:
                    self.stdout.write(self.style.ERROR(
                        f'  Zeile {i} ({nr}): einzelabrechnung "{einzelabr}" ungültig — erwartet: ja/nein/anteilig'))
                    fehler += 1
                    continue

                umlage = row.get('umlage', 'gesperrt').strip().lower()
                if umlage not in UMLAGE_VALUES:
                    self.stdout.write(self.style.ERROR(
                        f'  Zeile {i} ({nr}): umlage "{umlage}" ungültig — erwartet: pflicht/optional/gesperrt'))
                    fehler += 1
                    continue

                bankkonto_typ = row.get('bankkonto_typ', '').strip().lower() or None
                if bankkonto_typ and bankkonto_typ not in BANKKONTO_TYP_VALUES:
                    self.stdout.write(self.style.ERROR(
                        f'  Zeile {i} ({nr}): bankkonto_typ "{bankkonto_typ}" ungültig'))
                    fehler += 1
                    continue

                buchungstyp = row.get('buchungstyp', '').strip().lower() or None
                if buchungstyp and buchungstyp not in BUCHUNGSTYP_VALUES:
                    self.stdout.write(self.style.ERROR(
                        f'  Zeile {i} ({nr}): buchungstyp "{buchungstyp}" ungültig — erwartet: sachkonto/personenkonto/kreditor'))
                    fehler += 1
                    continue

                try:
                    defaults = dict(
                        kuerzel=row.get('kuerzel', '').strip(),
                        bezeichnung=row.get('bezeichnung', '').strip(),
                        einzelabrechnung=einzelabr,
                        gesamtabrechnung=_bool(row.get('gesamtabrechnung', 'False')),
                        ruecklagen_relevant=_bool(row.get('ruecklagen_relevant', 'False')),
                        umlage=umlage,
                        beleg_pflicht=_bool(row.get('beleg_pflicht', 'False')),
                        beschluss_pflicht=_bool(row.get('beschluss_pflicht', 'False')),
                        vier_augen_schwelle=_decimal_or_none(row.get('vier_augen_schwelle', '')),
                        sperre_nach_jahresabschluss=_bool(row.get('sperre_nach_jahresabschluss', 'True')),
                        system_buchungsart=_bool(row.get('system_buchungsart', 'False')),
                        default_konto_soll_pattern=row.get('default_konto_soll_pattern', '').strip(),
                        default_konto_haben_pattern=row.get('default_konto_haben_pattern', '').strip(),
                        aktiv=_bool(row.get('aktiv', 'True')),
                        tilgungs_prioritaet=_int_or_none(row.get('tilgungs_prioritaet', '')),
                        erloeskonto_default_nr=row.get('erloeskonto_default_nr', '').strip(),
                        bankkonto_typ=bankkonto_typ,
                        buchungstyp=buchungstyp,
                    )
                except ValueError as e:
                    self.stdout.write(self.style.ERROR(f'  Zeile {i} ({nr}): {e}'))
                    fehler += 1
                    continue

                if dry_run:
                    self.stdout.write(f'  [DRY] {nr} {defaults["kuerzel"]} — {defaults["bezeichnung"]}')
                    continue

                _, was_created = Buchungsart.objects.update_or_create(nr=nr, defaults=defaults)
                if was_created:
                    created += 1
                    self.stdout.write(f'  + {nr} {defaults["kuerzel"]}')
                else:
                    updated += 1
                    self.stdout.write(f'  ~ {nr} {defaults["kuerzel"]}')

        if not dry_run:
            self.stdout.write(self.style.SUCCESS(
                f'\nFertig: {created} angelegt, {updated} aktualisiert, {fehler} Fehler.'
            ))
        else:
            self.stdout.write(self.style.WARNING(f'\nDRY-RUN abgeschlossen. {fehler} Fehler gefunden.'))
