"""
Management Command: ampel_neu_berechnen

Rechnet die Verifikations-Ampel bestehender Rechnungen mit der aktuellen
Bewertungslogik neu.

Hintergrund: ``erkennung_ampel`` / ``erkennung_gesamt_konfidenz`` /
``erkennung_details`` sind ein GECACHTER Snapshot. Er entsteht beim Import
und bei jeder Feldänderung — danach nie wieder. Eine Korrektur in
``erkennung_ampel_service`` wirkt deshalb nur auf neue Belege; die bereits
bewerteten tragen ihre alte Einschätzung weiter, auch wenn sie falsch war.

Konkret behoben wird damit die verdrehte Kreditor-Bewertung: bei fehlender
IBAN wurde ersatzweise der Lieferantenname in die IBAN-Prüfziffernprüfung
geschoben. Ergebnis war "IBAN ungültig (Format/Prüfziffer)" → rot bei 0 %
für einen korrekt erkannten Kreditor, während eine Rechnung OHNE jeden
Kreditor gelb bei 100 % erhielt. Auf Live betraf das 19 von 20 roten
Rechnungen.

Der Command schreibt AUSSCHLIESSLICH die drei ``erkennung_*``-Felder. Er
ändert keinen Status, keine Buchung, keine Zuordnung — die Ampel ist reine
Anzeige (Spec Kap. 5.2).

Standardmäßig werden nur Rechnungen angefasst, die schon eine Ampel haben.
Unbewertete (``erkennung_ampel IS NULL``) bleiben außen vor: ihnen zum
ersten Mal eine Bewertung zu geben, ist eine fachliche Entscheidung und
kein Bugfix — dafür gibt es ``--auch-unbewertete``.

Aufruf:
    python manage.py ampel_neu_berechnen --dry-run
    python manage.py ampel_neu_berechnen
    python manage.py ampel_neu_berechnen --auch-unbewertete
    python manage.py ampel_neu_berechnen --status in_buchhaltung zur_freigabe
"""
from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction

FELDER = ['erkennung_ampel', 'erkennung_gesamt_konfidenz', 'erkennung_details']


class Command(BaseCommand):
    help = 'Verifikations-Ampel bestehender Rechnungen mit aktueller Logik neu berechnen'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Nur berichten, nichts speichern.',
        )
        parser.add_argument(
            '--auch-unbewertete', action='store_true',
            help=(
                'Auch Rechnungen ohne bisherige Ampel bewerten. Standard ist AUS — '
                'das ist eine fachliche Ausweitung, kein Bugfix.'
            ),
        )
        parser.add_argument(
            '--status', nargs='+', default=None,
            help='Nur diese Rechnungsstatus (z.B. in_buchhaltung zur_freigabe).',
        )

    def handle(self, *args, **options):
        from apps.rechnungen.models import Rechnung
        from apps.rechnungen.services.erkennung_ampel_service import (
            berechne_und_speichere_ampel,
        )

        dry_run = options['dry_run']
        qs = Rechnung.objects.select_related('kreditor').order_by('erstellt_am')
        if not options['auch_unbewertete']:
            qs = qs.exclude(erkennung_ampel__isnull=True)
        if options['status']:
            qs = qs.filter(status__in=options['status'])

        uebergaenge = Counter()
        fehler = 0
        geaendert = []

        for rechnung in qs:
            alt = (
                rechnung.erkennung_ampel,
                rechnung.erkennung_gesamt_konfidenz,
                (rechnung.erkennung_details or {}).get('kreditor', {}).get('hinweis', ''),
            )
            try:
                berechne_und_speichere_ampel(rechnung)
            except Exception as exc:
                fehler += 1
                self.stderr.write(self.style.WARNING(
                    f'  Fehler bei {rechnung.rechnungsnummer or rechnung.id}: {exc}'
                ))
                continue

            neu = (
                rechnung.erkennung_ampel,
                rechnung.erkennung_gesamt_konfidenz,
                (rechnung.erkennung_details or {}).get('kreditor', {}).get('hinweis', ''),
            )
            if alt[:2] == neu[:2] and alt[2] == neu[2]:
                uebergaenge['unveraendert'] += 1
                continue

            uebergaenge[f'{alt[0] or "—"} → {neu[0] or "—"}'] += 1
            geaendert.append((rechnung, alt, neu))
            if not dry_run:
                with transaction.atomic():
                    rechnung.save(update_fields=FELDER)

        self.stdout.write('')
        self.stdout.write(f'Geprüft:    {qs.count()}')
        self.stdout.write(f'Geändert:   {len(geaendert)}')
        if fehler:
            self.stdout.write(self.style.WARNING(f'Fehler:     {fehler}'))
        self.stdout.write('')
        for uebergang, anzahl in uebergaenge.most_common():
            self.stdout.write(f'  {anzahl:5d}  {uebergang}')

        if geaendert:
            self.stdout.write('')
            self.stdout.write('Details (max. 30):')
            for rechnung, alt, neu in geaendert[:30]:
                kred = rechnung.kreditor.name if rechnung.kreditor_id else '(kein Kreditor)'
                self.stdout.write(
                    f'  {rechnung.rechnungsnummer or "?":18s} {kred[:32]:34s} '
                    f'{alt[0] or "—"} {alt[1] or 0} → {neu[0] or "—"} {neu[1] or 0}'
                )
                if alt[2] != neu[2]:
                    self.stdout.write(f'{"":20s}{alt[2] or "—"}  →  {neu[2] or "—"}')

        self.stdout.write('')
        if dry_run:
            self.stdout.write(self.style.WARNING(
                'DRY-RUN — nichts gespeichert. Ohne --dry-run erneut aufrufen.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS('Ampeln aktualisiert.'))
