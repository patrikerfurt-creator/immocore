"""
Management Command: rechnung_watch
Überwacht C:\\Projekte\\immocore\\Rechnungen auf neue PDF/Bild-Dateien
und importiert sie automatisch mit OCR + KI-Parsing.

Verwendung:
    python manage.py rechnung_watch
    python manage.py rechnung_watch --ordner /anderer/pfad --intervall 30
"""
import time
from pathlib import Path

from django.core.management.base import BaseCommand

WATCH_ORDNER = Path(r'C:\Projekte\immocore\Rechnungen')
ERLAUBTE_ENDUNGEN = {'.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.tif'}


class Command(BaseCommand):
    help = 'Überwacht Rechnungseingangsordner und importiert neue Dateien mit OCR + KI'

    def add_arguments(self, parser):
        parser.add_argument('--ordner', default=str(WATCH_ORDNER),
                            help='Zu überwachender Ordner')
        parser.add_argument('--intervall', type=int, default=60,
                            help='Prüfintervall in Sekunden (Standard: 60)')

    def handle(self, *args, **options):
        from apps.rechnungen.services.verarbeitung import verarbeite_datei

        ordner = Path(options['ordner'])
        intervall = options['intervall']
        archiv = ordner / 'archiv'
        archiv.mkdir(exist_ok=True)

        self.stdout.write(self.style.SUCCESS(
            f'rechnung_watch gestartet\n'
            f'  Ordner:    {ordner}\n'
            f'  Intervall: {intervall}s\n'
            f'  Archiv:    {archiv}\n'
        ))

        self.stdout.write('Prüfe vorhandene Dateien beim Start…')
        self._verarbeite_ordner(ordner, archiv, verarbeite_datei)

        self.stdout.write(f'Warte auf neue Dateien (alle {intervall}s)…')
        while True:
            time.sleep(intervall)
            self._verarbeite_ordner(ordner, archiv, verarbeite_datei)

    def _verarbeite_ordner(self, ordner: Path, archiv: Path, verarbeite_fn):
        seen: set[str] = set()
        dateien = []
        for ext in ERLAUBTE_ENDUNGEN:
            for p in ordner.glob(f'*{ext}'):
                if p.name.lower() not in seen:
                    seen.add(p.name.lower())
                    dateien.append(p)
            for p in ordner.glob(f'*{ext.upper()}'):
                if p.name.lower() not in seen:
                    seen.add(p.name.lower())
                    dateien.append(p)

        if not dateien:
            return

        self.stdout.write(f'  {len(dateien)} Datei(en) gefunden…')
        for datei in sorted(dateien):
            try:
                result = verarbeite_fn(str(datei), archiv)
                status = result['status']
                notiz = result['notiz']
                kreditor = result.get('kreditor') or '?'

                farbe = {
                    'importiert':     self.style.SUCCESS,
                    'erkannt':        self.style.SUCCESS,
                    'pruefung_match': self.style.WARNING,
                    'nicht_erkannt':  self.style.WARNING,
                    'prueffall':      self.style.WARNING,
                    'duplikat':       self.style.WARNING,
                    'fehler':         self.style.ERROR,
                }.get(status, self.style.SUCCESS)

                self.stdout.write(farbe(
                    f'    {status.upper()} {datei.name}: {notiz} | Kreditor: {kreditor}'
                ))
            except Exception as exc:
                self.stderr.write(self.style.ERROR(
                    f'    FEHLER {datei.name}: {exc}'
                ))
