"""
Management-Command: rechnungen_purge

Löscht Rechnungen samt ihrer kompletten buchhalterischen Spur — in
FK-sicherer Reihenfolge, atomar. Gedacht für das Bereinigen von Test-/
Probedaten VOR dem echten Go-Live (umgeht bewusst die GoBD-Löschsperre
auf Beleg-Ebene; auf einem real im Betrieb befindlichen System NICHT
verwenden).

Entfernt:
  - KreditorOP der betroffenen Rechnungen   (PROTECT-Blocker Richtung Rechnung)
  - die Rechnungen selbst                    (+ Splits, Freigaben, Dubletten-
                                              Prüfungen via CASCADE; WKZ-Vorlagen
                                              werden per SET_NULL entkoppelt)
  - die zugehörigen Buchungen                (op_buchung, aufwand_buchung,
                                              buchung, KreditorOP.buchung,
                                              KreditorOP.zahlung_buchung),
                                              sofern danach verwaist
  - optional (--mit-belegen): die Beleg-Dokumente + die physischen Dateien

Bleibt unberührt:
  - Stammdaten (Objekte, Personen, Einheiten, Verträge, Konten, Kreditoren)
  - Hausgeld-Sollstellungen und deren Zahlungen
  - Bank-/CAMT-Daten, Wirtschaftsjahre, Buchungsarten

Aufruf:
    python manage.py rechnungen_purge --dry-run
    python manage.py rechnungen_purge                 # fragt nach
    python manage.py rechnungen_purge --force
    python manage.py rechnungen_purge --force --mit-belegen
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.rechnungen.models import Rechnung
from apps.buchhaltung.models import Buchung, KreditorOP


class Command(BaseCommand):
    help = (
        'Löscht alle Rechnungen samt zugehöriger Buchungen/KreditorOPs '
        '(Test-Daten-Bereinigung). Stammdaten und Hausgeld bleiben erhalten.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--force', '-f', action='store_true',
            help='Ohne Bestätigungsabfrage ausführen',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Nur anzeigen, was gelöscht würde — kein DB-Commit',
        )
        parser.add_argument(
            '--mit-belegen', action='store_true',
            help='Auch die Beleg-Dokumente und ihre physischen Dateien löschen',
        )

    def handle(self, *args, **options):
        force       = options['force']
        dry_run     = options['dry_run']
        mit_belegen = options['mit_belegen']

        rechnungen   = Rechnung.objects.all()
        rechnung_ids = list(rechnungen.values_list('pk', flat=True))

        if not rechnung_ids:
            self.stdout.write(self.style.SUCCESS('  Keine Rechnungen vorhanden — nichts zu tun.\n'))
            return

        # Buchungs-IDs einsammeln, die zu diesen Rechnungen gehören.
        buchung_ids = set()
        for feld in ('op_buchung_id', 'aufwand_buchung_id', 'buchung_id'):
            buchung_ids.update(
                rechnungen.exclude(**{feld: None}).values_list(feld, flat=True)
            )

        kreditor_ops = KreditorOP.objects.filter(rechnung_id__in=rechnung_ids)
        for feld in ('buchung_id', 'zahlung_buchung_id'):
            buchung_ids.update(
                kreditor_ops.exclude(**{feld: None}).values_list(feld, flat=True)
            )
        buchung_ids.discard(None)

        beleg_dok_ids = list(
            rechnungen.exclude(beleg_dokument_id=None)
            .values_list('beleg_dokument_id', flat=True)
        )

        # --- Übersicht ---
        self.stdout.write('\n' + '-' * 62)
        self.stdout.write(self.style.WARNING('  IMMOCORE — Rechnungen purgen'))
        self.stdout.write('-' * 62)
        self.stdout.write(f'\n  Rechnungen:        {len(rechnung_ids)}')
        self.stdout.write(f'  KreditorOPs:       {kreditor_ops.count()}')
        self.stdout.write(f'  Buchungen:         {len(buchung_ids)}')
        self.stdout.write(
            f'  Beleg-Dokumente:   {len(beleg_dok_ids)}'
            + ('  (werden gelöscht)' if mit_belegen else '  (bleiben erhalten — ohne --mit-belegen)')
        )
        self.stdout.write('\n  Stammdaten, Hausgeld-Sollstellungen und Bank-/CAMT-Daten bleiben unberührt.')
        self.stdout.write('-' * 62 + '\n')

        if dry_run:
            self.stdout.write(self.style.SUCCESS('  --dry-run aktiv — keine Änderungen.\n'))
            return

        if not force:
            antwort = input(
                '  Wirklich ALLE Rechnungen samt Buchungen unwiderruflich löschen? [ja/NEIN]: '
            ).strip().lower()
            if antwort != 'ja':
                self.stdout.write(self.style.NOTICE('  Abgebrochen — keine Änderungen.\n'))
                return

        # Beleg-Pfade VOR dem Löschen auflösen (Dateien erst nach Commit entfernen).
        datei_pfade = []
        if mit_belegen and beleg_dok_ids:
            from apps.dokumente.models import Dokument
            from apps.dokumente.services import beleg_service
            for dok in Dokument.objects.filter(pk__in=beleg_dok_ids):
                try:
                    datei_pfade.append(beleg_service.dokument_pfad(dok))
                except Exception as exc:  # Pfad nicht auflösbar — Datei überspringen
                    self.stderr.write(f'    ! Pfad für Dokument {dok.pk} nicht auflösbar: {exc}')

        with transaction.atomic():
            self.stdout.write('  Lösche KreditorOPs...')
            n_kop, _ = kreditor_ops.delete()

            self.stdout.write('  Lösche Rechnungen (inkl. Splits/Freigaben/Dubletten)...')
            n_r, _ = Rechnung.objects.filter(pk__in=rechnung_ids).delete()

            self.stdout.write('  Lösche zugehörige Buchungen...')
            n_b, _ = Buchung.objects.filter(pk__in=buchung_ids).delete()

            n_d = 0
            if mit_belegen and beleg_dok_ids:
                from apps.dokumente.models import Dokument
                self.stdout.write('  Lösche Beleg-Dokumente...')
                n_d, _ = Dokument.objects.filter(pk__in=beleg_dok_ids).delete()

        # Physische Dateien erst nach erfolgreichem Commit entfernen.
        n_files = 0
        for pfad in datei_pfade:
            try:
                if pfad.exists():
                    pfad.unlink()
                    n_files += 1
            except Exception as exc:
                self.stderr.write(f'    ! Datei {pfad} nicht löschbar: {exc}')

        self.stdout.write(self.style.SUCCESS(
            f'\n  OK: {n_r} Rechnungs-bezogene Zeilen, {n_kop} KreditorOP-Zeilen, '
            f'{n_b} Buchungs-Zeilen gelöscht'
            + (f', {n_d} Beleg-Zeilen, {n_files} Dateien entfernt' if mit_belegen else '')
            + '.\n'
        ))
