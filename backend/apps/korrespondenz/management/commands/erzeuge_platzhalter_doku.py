"""Schreibt die Platzhalter-Doku (Markdown) aus der Registry.

    python manage.py erzeuge_platzhalter_doku [--ziel <datei>]

Vorgabe für ``--ziel``: ``docs/korrespondenz_platzhalter.md`` im Repo (relativ zu BASE_DIR).
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.korrespondenz.services import platzhalter_doku_service


def _standardziel() -> Path:
    return Path(settings.BASE_DIR).parent / 'docs' / 'korrespondenz_platzhalter.md'


class Command(BaseCommand):
    help = 'Erzeugt docs/korrespondenz_platzhalter.md aus der Platzhalter-Registry.'

    def add_arguments(self, parser):
        parser.add_argument('--ziel', help='Zieldatei (Vorgabe: docs/korrespondenz_platzhalter.md).')

    def handle(self, *args, **options):
        ziel = Path(options['ziel']) if options['ziel'] else _standardziel()
        if not ziel.parent.is_dir():
            # Im Container ist nur backend/ nach /app gemountet - dort --ziel angeben.
            raise CommandError(f'Zielverzeichnis {ziel.parent} existiert nicht - bitte --ziel angeben.')
        ziel.write_text(platzhalter_doku_service.erzeuge_markdown(), encoding='utf-8', newline='\n')
        self.stdout.write(f'Geschrieben: {ziel}')
