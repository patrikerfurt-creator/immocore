"""
Management Command: erkennung_bestand

Führt die 3-stufige Erkennungs-Pipeline auf Bestandsrechnungen aus.

Aufruf:
    python manage.py erkennung_bestand
    python manage.py erkennung_bestand --status importiert,nicht_erkannt
    python manage.py erkennung_bestand --status prueffall --verbose
    python manage.py erkennung_bestand --dry-run
"""
from django.core.management.base import BaseCommand
from django.db import transaction

STANDARD_STATUSE = ['importiert', 'erfasst', 'nicht_erkannt', 'prueffall', 'pruefung_match']


class Command(BaseCommand):
    help = 'Erkennungs-Pipeline auf Bestandsrechnungen ausführen'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Nur zählen, nichts speichern.',
        )
        parser.add_argument(
            '--status',
            default=','.join(STANDARD_STATUSE),
            help=f'Kommagetrennte Status-Liste (default: {",".join(STANDARD_STATUSE)}).',
        )
        parser.add_argument(
            '--verbose', '-v2', action='store_true',
            help='Zeigt pro Rechnung Kreditor/Objekt/Konto-Ergebnis.',
        )
        parser.add_argument(
            '--batch-size', type=int, default=100,
        )

    def handle(self, *args, **options):
        from apps.rechnungen.models import Rechnung
        from apps.rechnungen.recognition import fuehre_erkennung_aus

        dry_run    = options['dry_run']
        verbose    = options['verbose']
        batch_size = options['batch_size']
        statuse    = [s.strip() for s in options['status'].split(',') if s.strip()]

        qs = Rechnung.objects.filter(status__in=statuse).order_by('erstellt_am')
        gesamt = qs.count()

        self.stdout.write('\n' + '-' * 70)
        self.stdout.write('  IMMOCORE — Erkennungs-Pipeline Bestandslauf')
        self.stdout.write('-' * 70)
        self.stdout.write(f'  Status-Filter : {", ".join(statuse)}')
        self.stdout.write(f'  Gefunden      : {gesamt} Rechnungen')
        if dry_run:
            self.stdout.write(self.style.WARNING('  --dry-run: keine Änderungen\n'))
            return
        self.stdout.write('-' * 70 + '\n')

        verarbeitet = 0
        fehler      = 0
        stufen      = {'1': 0, '2': 0, '3': 0}
        routing     = {}

        for offset in range(0, gesamt, batch_size):
            batch = list(qs[offset:offset + batch_size])
            for rechnung in batch:
                alt_status = rechnung.status
                try:
                    with transaction.atomic():
                        rechnung = fuehre_erkennung_aus(rechnung)

                    stufe = rechnung.erkennungs_stufe or '3'
                    stufen[stufe] = stufen.get(stufe, 0) + 1
                    routing[rechnung.routing_ziel or '?'] = routing.get(rechnung.routing_ziel or '?', 0) + 1
                    verarbeitet += 1

                    if verbose:
                        k  = rechnung.erkennungs_konfidenz or {}
                        kr = f"{rechnung.kreditor.name[:25]:<25} [{k.get('kreditor', 0):.0%}]" if rechnung.kreditor else f"{'—':<25} [  0%]"
                        ob = f"{rechnung.objekt.bezeichnung[:25]:<25} [{k.get('objekt', 0):.0%}]" if rechnung.objekt else f"{'—':<25} [  0%]"
                        ko = f"{rechnung.aufwandskonto.kontonummer if rechnung.aufwandskonto else '—':<8} [{k.get('aufwandskonto', 0):.0%}]"
                        self.stdout.write(
                            f"  Stufe {stufe} | {rechnung.dateiname[:35]:<35} | "
                            f"Kreditor: {kr} | Objekt: {ob} | Konto: {ko} | → {rechnung.routing_ziel}"
                        )

                except Exception as exc:
                    fehler += 1
                    self.stderr.write(f'  FEHLER [{rechnung.id}] {rechnung.dateiname}: {exc}')

        self.stdout.write('\n' + '-' * 70)
        self.stdout.write(self.style.SUCCESS(
            f'  Fertig: {verarbeitet} verarbeitet, {fehler} Fehler\n'
            f'\n  Erkennungs-Stufen:\n'
            f'    Stufe 1 (erkannt)       : {stufen.get("1", 0):>4}\n'
            f'    Stufe 2 (Objekt-Match)  : {stufen.get("2", 0):>4}\n'
            f'    Stufe 3 (nicht erkannt) : {stufen.get("3", 0):>4}\n'
        ))
        if routing:
            self.stdout.write('  Routing-Ziele:')
            for ziel, anzahl in sorted(routing.items(), key=lambda x: -x[1]):
                self.stdout.write(f'    {ziel:<25} : {anzahl:>4}')
        self.stdout.write('-' * 70 + '\n')
