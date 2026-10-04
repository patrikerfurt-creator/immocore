"""
Management Command: repariere_wkz_fehlbelege

Korrigiert Rechnungen, die faelschlich als WKZ-Beleg aus dem Zahlweg
genommen wurden (Status 'wkz_beleg', Kreditor-OP geloescht), obwohl sie als
eigenstaendige Rechnung verbucht/bezahlt werden muessen.

Hintergrund
-----------
Eine Energiehaus-PDF (und aehnliche) traegt zwei getrennte Forderungen:
die Schlussrechnung (normale Rechnung) UND die kuenftigen Abschlaege (WKZ).
Beim Anlegen einer WKZ aus der Rechnung wurde die Rechnung bisher auf
'wkz_beleg' gesetzt und ihr Kreditor-OP geloescht (Kopplung in
route_zur_freigabe -> _rechnung_als_wkz_beleg_markieren). Dadurch liess sich
die Schlussrechnung nicht mehr normal verbuchen/bezahlen.

Dieser Befehl holt betroffene Rechnungen zurueck auf den normalen Weg und
erzeugt den Kreditor-OP ueber den regulaeren Freigabe-Service neu. Die ggf.
aus der Rechnung abgeleitete WKZ-Vorlage bleibt unveraendert bestehen
(nur der PDF-/DMS-Bezug).

Aufruf
------
    python manage.py repariere_wkz_fehlbelege --rechnung EHDE-ARV-2025-10485 --dry-run
    python manage.py repariere_wkz_fehlbelege --rechnung EHDE-ARV-2025-10485 --commit
    python manage.py repariere_wkz_fehlbelege --alle --dry-run

Standard ist Dry-Run: ohne --commit wird NICHTS veraendert.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = "Faelschlich als WKZ-Beleg behandelte Rechnungen auf den normalen Zahlweg zurueckholen"

    def add_arguments(self, parser):
        parser.add_argument(
            '--rechnung', type=str, default=None,
            help='Rechnungsnummer oder (Teil der) UUID der zu reparierenden Rechnung.',
        )
        parser.add_argument(
            '--alle', action='store_true',
            help="Alle Rechnungen mit Status 'wkz_beleg' ohne OP-Buchung reparieren.",
        )
        parser.add_argument(
            '--commit', action='store_true',
            help='Aenderungen tatsaechlich schreiben (ohne: Dry-Run, nur Anzeige).',
        )
        parser.add_argument(
            '--buchungsdatum', type=str, default=None,
            help='Buchungsdatum fuer die OP-Buchung (YYYY-MM-DD). '
                 'Default: Rechnungsdatum der jeweiligen Rechnung.',
        )

    def handle(self, *args, **options):
        from datetime import date
        from apps.rechnungen.models import Rechnung, Verarbeitungslog
        from apps.rechnungen.services.rechnung_op_service import (
            rechnung_freigeben as op_freigeben,
        )

        nummer = options.get('rechnung')
        alle = options['alle']
        commit = options['commit']

        buchungsdatum = None
        if options.get('buchungsdatum'):
            try:
                buchungsdatum = date.fromisoformat(options['buchungsdatum'])
            except ValueError:
                self.stderr.write(f"Ungueltiges Buchungsdatum: {options['buchungsdatum']}")
                return

        if not nummer and not alle:
            self.stderr.write('Bitte --rechnung <nummer|id> oder --alle angeben.')
            return

        qs = Rechnung.objects.filter(status='wkz_beleg', op_buchung__isnull=True)
        if nummer:
            treffer = qs.filter(rechnungsnummer=nummer)
            if not treffer.exists():
                treffer = qs.filter(rechnungsnummer__icontains=nummer)
            if not treffer.exists():
                treffer = qs.filter(id__icontains=nummer)
            qs = treffer

        rechnungen = list(qs)

        User = get_user_model()
        user = (User.objects.filter(username='immocore-autopilot').first()
                or User.objects.filter(is_superuser=True).first())
        if not user:
            self.stderr.write('Kein System-/Superuser gefunden — Abbruch.')
            return

        self.stdout.write('\n' + '=' * 70)
        self.stdout.write('  WKZ-Fehlbelege reparieren  ' + ('(COMMIT)' if commit else '(DRY-RUN)'))
        self.stdout.write('=' * 70)
        self.stdout.write(f'  Betroffene Rechnungen: {len(rechnungen)}  | User: {user.username}')
        self.stdout.write('-' * 70)

        if not rechnungen:
            self.stdout.write(self.style.WARNING(
                '  Keine passenden Rechnungen (Status wkz_beleg, ohne OP) gefunden.'
            ))
            return

        erfolg = uebersprungen = fehler = 0
        for r in rechnungen:
            kennung = r.rechnungsnummer or str(r.id)[:8]
            hat_konto = bool(r.aufwandskonto_id) or r.splits.exists()
            if not hat_konto:
                self.stdout.write(self.style.WARNING(
                    f'  ÜBERSPRUNGEN {kennung}: kein Aufwandskonto und keine Splits — '
                    f'erst im Rechnungseingang kontieren.'
                ))
                uebersprungen += 1
                continue

            self.stdout.write(
                f'  {kennung}  {r.betrag_brutto} €  Objekt {getattr(r.objekt, "objektnummer", "?")}  '
                f'-> zurueck auf normalen Weg, OP neu erzeugen'
            )
            if not commit:
                continue

            try:
                # Status aus 'wkz_beleg' zurueck in einen freigabefaehigen Zustand,
                # dann regulaere OP-Buchung ueber den Freigabe-Service.
                r.status = 'in_buchhaltung'
                r.save(update_fields=['status'])
                op_freigeben(
                    r, r.aufwandskonto, user,
                    buchungsdatum=buchungsdatum or r.rechnungsdatum,
                )
                Verarbeitungslog.objects.create(
                    rechnung=r,
                    aktion='WKZ-Fehlbeleg korrigiert',
                    status=r.status,
                    details=('Rechnung war faelschlich als WKZ-Beleg aus dem Zahlweg genommen; '
                             'zurueck auf den normalen Weg geholt und Kreditor-OP neu erzeugt.'),
                )
                self.stdout.write(self.style.SUCCESS(f'    OK — Status jetzt: {r.status}'))
                erfolg += 1
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f'    FEHLER: {exc}'))
                fehler += 1

        self.stdout.write('-' * 70)
        if commit:
            self.stdout.write(self.style.SUCCESS(
                f'  Fertig: {erfolg} repariert, {uebersprungen} uebersprungen, {fehler} Fehler'
            ))
        else:
            self.stdout.write(self.style.WARNING(
                '  Dry-Run — nichts geaendert. Mit --commit ausfuehren.'
            ))
        self.stdout.write('=' * 70 + '\n')
