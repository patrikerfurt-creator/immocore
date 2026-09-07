"""
Management Command: kreditor_dubletten_neubewerten

Bewertet OFFENE Kreditor-Dublettenprüfungen mit dem aktuellen Datenstand neu
und schließt die ab, die inzwischen ein eindeutiger Treffer sind.

Hintergrund: der Abgleich unterschied nicht zwischen "der Kreditor hat eine
ANDERE IBAN" und "der Kreditor hat noch GAR KEINE IBAN". Letzteres wurde als
Betrugsmuster gemeldet, obwohl es nichts gab, wovon die Beleg-IBAN abweichen
konnte. Auf Live hingen dadurch 92 Belege desselben Kreditors in der
Prüfliste. Der Bugfix in ``services.kreditor_matching`` verhindert neue
Fälle, räumt die bestehenden aber nicht auf — das macht dieser Command.

Er entscheidet NICHTS, was der Abgleich nicht selbst als ``sicher``
einstuft. Bleibt ein Verdacht bestehen, bleibt der Fall offen und wird nur
berichtet.

Aufruf:
    python manage.py kreditor_dubletten_neubewerten --dry-run
    python manage.py kreditor_dubletten_neubewerten
    python manage.py kreditor_dubletten_neubewerten --iban-uebernehmen
    python manage.py kreditor_dubletten_neubewerten --benutzer p.maurer
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

AKTION = 'Kreditor-Dublettenprüfung neu bewertet'

# Nur aus diesem Zustand wird eine Rechnung zurück in die Pipeline geschickt.
# Ist sie inzwischen weitergelaufen (jemand hat den Kreditor anders gesetzt),
# wird ausschließlich der Prüffall geschlossen — ein Status-Rücksprung von
# 'zur_freigabe' nach 'in_buchhaltung' wäre ein Datenverlust.
STATUS_ANGEHALTEN = 'prueffall'
DUPLIKAT_TYP_ANGEHALTEN = 'kreditor_dublette'


class Command(BaseCommand):
    help = 'Offene Kreditor-Dublettenprüfungen neu bewerten und eindeutige abschließen'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Nur berichten, nichts speichern.',
        )
        parser.add_argument(
            '--iban-uebernehmen', action='store_true',
            help=(
                'Erkannte Beleg-IBAN beim Kreditor ergänzen, wenn dort noch keine '
                'steht. Standard ist AUS: Bankverbindungen sollen nicht in einem '
                'Massenlauf aus Belegen entstehen.'
            ),
        )
        parser.add_argument(
            '--benutzer', type=str, default=None,
            help='Benutzername für das Audit-Feld (default: Systembenutzer).',
        )

    def handle(self, *args, **options):
        from django.contrib.auth import get_user_model

        from apps.rechnungen.models import KreditorDublettenPruefung, Verarbeitungslog
        from apps.rechnungen.recognition import fuehre_erkennung_aus
        from apps.rechnungen.services import kreditor_dubletten
        from apps.rechnungen.services.kreditor_matching import gleiche_kreditoren
        from apps.rechnungen.services.verarbeitung import _system_user

        dry_run = options['dry_run']
        iban_uebernehmen = options['iban_uebernehmen']

        if options['benutzer']:
            benutzer = get_user_model().objects.filter(username=options['benutzer']).first()
            if benutzer is None:
                raise CommandError(f'Benutzer "{options["benutzer"]}" existiert nicht.')
        else:
            benutzer = _system_user()
            if benutzer is None:
                raise CommandError(
                    'Kein Systembenutzer gefunden — bitte --benutzer angeben. Ohne '
                    'Benutzer bliebe nicht nachvollziehbar, wer entschieden hat.'
                )

        offen = list(
            KreditorDublettenPruefung.objects
            .filter(status=KreditorDublettenPruefung.STATUS_OFFEN)
            .select_related('rechnung')
            .order_by('erstellt_am')
        )

        self.stdout.write('\n' + '-' * 70)
        self.stdout.write('  IMMOCORE — Kreditor-Dublettenprüfungen neu bewerten')
        self.stdout.write('-' * 70)
        self.stdout.write(f'  Offene Prüffälle : {len(offen)}')
        self.stdout.write(f'  Entscheider      : {benutzer.username}')
        self.stdout.write(f'  IBAN übernehmen  : {"ja" if iban_uebernehmen else "nein"}')
        if dry_run:
            self.stdout.write(self.style.WARNING('  --dry-run: keine Änderungen'))
        self.stdout.write('-' * 70 + '\n')

        abgeschlossen = 0
        weiterhin_offen = 0
        fehler = 0
        ohne_bankverbindung = []

        for pruefung in offen:
            rechnung = pruefung.rechnung
            kennung = rechnung.dateiname or str(rechnung.pk)

            ergebnis = gleiche_kreditoren(pruefung.erkannter_name, pruefung.erkannte_iban)

            if not ergebnis.sicher:
                weiterhin_offen += 1
                zustand = ergebnis.anlass if ergebnis.verdacht else 'kein Kandidat'
                self.stdout.write(
                    f'  OFFEN   {kennung[:45]:<45} | bleibt Prüffall ({zustand})'
                )
                continue

            kreditor = ergebnis.kreditor
            # Weitergelaufene Rechnungen werden nicht zurückgesetzt — dort wird
            # nur der Prüffall geschlossen.
            zurueck_in_pipeline = (
                rechnung.status == STATUS_ANGEHALTEN
                and rechnung.duplikat_typ == DUPLIKAT_TYP_ANGEHALTEN
            )
            hinweis = (
                'zurück in die Pipeline' if zurueck_in_pipeline
                else f'nur Prüffall geschlossen (Rechnung steht auf {rechnung.status})'
            )
            self.stdout.write(
                f'  KLAR    {kennung[:45]:<45} | {kreditor.name[:30]} '
                f'[{kreditor.kreditorennummer or "ohne Nummer"}] | {hinweis}'
            )

            if dry_run:
                abgeschlossen += 1
                if not (kreditor.iban or '').strip():
                    ohne_bankverbindung.append(
                        f'{kreditor.name} [{kreditor.kreditorennummer or "ohne Nummer"}]'
                    )
                continue

            try:
                with transaction.atomic():
                    kreditor_dubletten.zuordnen(
                        pruefung, kreditor.pk, benutzer,
                        iban_uebernehmen=iban_uebernehmen,
                        notiz=(
                            'Automatische Neubewertung: der Kreditor kannte zum '
                            'Prüfzeitpunkt keine Bankverbindung, es lag also keine '
                            'IBAN-Abweichung vor.'
                        ),
                    )

                    if zurueck_in_pipeline:
                        # Erst die Sperre wegnehmen, dann die Erkennung — sonst
                        # bliebe die Rechnung als 'kreditor_dublette' markiert in
                        # der Duplikat-Ansicht stehen.
                        rechnung.duplikat_typ = ''
                        rechnung.verarbeitungsnotiz = (
                            'Kreditor-Dublettenverdacht aufgelöst — kein '
                            'IBAN-Konflikt, Kreditor zugeordnet.'
                        )
                        rechnung.save(update_fields=['duplikat_typ', 'verarbeitungsnotiz'])
                        rechnung = fuehre_erkennung_aus(rechnung)

                    Verarbeitungslog.objects.create(
                        rechnung=rechnung,
                        aktion=AKTION,
                        status=rechnung.status,
                        details=(
                            f'Kreditor {kreditor.name} '
                            f'[{kreditor.kreditorennummer or "ohne Nummer"}] zugeordnet '
                            f'(Neubewertung durch {benutzer.username}).'
                        ),
                    )
                abgeschlossen += 1

                kreditor.refresh_from_db()
                if not (kreditor.iban or '').strip():
                    ohne_bankverbindung.append(
                        f'{kreditor.name} [{kreditor.kreditorennummer or "ohne Nummer"}]'
                    )

            except Exception as exc:
                fehler += 1
                self.stderr.write(f'  FEHLER  {kennung}: {exc}')

        self.stdout.write('\n' + '-' * 70)
        stil = self.style.WARNING if dry_run else self.style.SUCCESS
        verb = 'wären abgeschlossen' if dry_run else 'abgeschlossen'
        self.stdout.write(stil(
            f'  {abgeschlossen} {verb}, {weiterhin_offen} bleiben offen, {fehler} Fehler'
        ))
        if ohne_bankverbindung:
            self.stdout.write(
                '\n  Hinweis: diese Kreditoren haben weiterhin keine IBAN und sind '
                'damit nicht zahlbar:'
            )
            for name in sorted(set(ohne_bankverbindung)):
                self.stdout.write(f'    - {name}')
            if not iban_uebernehmen:
                self.stdout.write(
                    '  (Von Hand nachtragen oder Lauf mit --iban-uebernehmen.)'
                )
        self.stdout.write('-' * 70 + '\n')
