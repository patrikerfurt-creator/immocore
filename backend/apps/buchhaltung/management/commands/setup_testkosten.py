"""
Management-Command: Testkosten (Aufwandsbuchungen) für ein Objekt/WJ anlegen.

Bucht auf zufällig gewählte Sachkonten in einem Kontonummern-Bereich einen
Aufwand gegen die Bank (Soll Kostenkonto / Haben 18000). Damit bekommt die
Jahresabrechnung eine Kostenseite zum Testen.

Nur Test-/Demo-Werkzeug, nicht für den Produktivbetrieb.

Beispiel:
    python manage.py setup_testkosten --objekt 10001 --jahr 2025
    python manage.py setup_testkosten --objekt 10001 --jahr 2025 --anzahl 10 --min 1000 --max 5000
    python manage.py setup_testkosten --objekt 10001 --jahr 2025 --dry-run

Idempotent: Buchungen werden mit Beleg-Nr. 'TESTK-<jahr>-<konto>' markiert und
bei erneutem Lauf übersprungen (bzw. mit --force neu gebucht).
"""
import random
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.objekte.models import Objekt, Wirtschaftsjahr
from apps.konten.models import Konto
from apps.buchhaltung.models import Buchung

User = get_user_model()


class Command(BaseCommand):
    help = "Bucht Testkosten (Aufwand an Bank) auf Sachkonten eines Bereichs."

    def add_arguments(self, parser):
        parser.add_argument('--objekt', required=True, help='Objektnummer, z. B. 10001')
        parser.add_argument('--jahr', required=True, type=int, help='Wirtschaftsjahr, z. B. 2025')
        parser.add_argument('--anzahl', type=int, default=10, help='Anzahl zu bebuchender Konten (Standard: 10)')
        parser.add_argument('--von', type=int, default=50100, help='Kontonummer von (Standard: 50100)')
        parser.add_argument('--bis', type=int, default=55500, help='Kontonummer bis (Standard: 55500)')
        parser.add_argument('--min', type=int, default=1000, help='Mindestbetrag in € (Standard: 1000)')
        parser.add_argument('--max', type=int, default=5000, help='Höchstbetrag in € (Standard: 5000)')
        parser.add_argument('--dry-run', action='store_true', help='Nur Vorschau, keine Änderungen.')
        parser.add_argument('--force', action='store_true', help='Vorhandene Testkosten löschen und neu buchen.')

    def handle(self, *args, **opts):
        objektnummer = opts['objekt']
        jahr = opts['jahr']
        anzahl = opts['anzahl']
        knr_von, knr_bis = opts['von'], opts['bis']
        betrag_min, betrag_max = opts['min'], opts['max']

        if betrag_min > betrag_max:
            raise CommandError("--min darf nicht größer als --max sein.")

        try:
            objekt = Objekt.objects.get(objektnummer=objektnummer)
        except Objekt.DoesNotExist:
            raise CommandError(f"Objekt {objektnummer} nicht gefunden.")

        wj = Wirtschaftsjahr.objects.filter(objekt=objekt, jahr=jahr).first()
        if wj is None:
            raise CommandError(
                f"Kein Wirtschaftsjahr {jahr} für {objektnummer}. "
                f"Bitte zuerst 'setup_testjahr' ausführen."
            )

        bank = Konto.objects.filter(wirtschaftsjahr=wj, kontonummer='18000', aktiv=True).first()
        if bank is None:
            raise CommandError(f"Kein Bank-Sachkonto 18000 im WJ {jahr}.")

        user = User.objects.filter(is_superuser=True).order_by('pk').first() or User.objects.order_by('pk').first()
        if user is None:
            raise CommandError("Kein Benutzer in der Datenbank.")

        # Kandidaten: direkt bebuchbare Standard-Sachkonten im Bereich
        kandidaten = [
            k for k in Konto.objects.filter(
                wirtschaftsjahr=wj, aktiv=True, kontoart='standard',
            )
            if k.kontonummer.isdigit() and knr_von <= int(k.kontonummer) <= knr_bis
        ]
        kandidaten.sort(key=lambda k: k.kontonummer)

        if not kandidaten:
            raise CommandError(f"Keine bebuchbaren Standard-Konten im Bereich {knr_von}–{knr_bis}.")

        rng = random.Random(f"{objektnummer}-{jahr}-kosten")
        auswahl = kandidaten if anzahl >= len(kandidaten) else rng.sample(kandidaten, anzahl)
        auswahl.sort(key=lambda k: k.kontonummer)

        if anzahl > len(kandidaten):
            self.stdout.write(self.style.WARNING(
                f"Nur {len(kandidaten)} Konten im Bereich vorhanden — alle werden bebucht."
            ))

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\nTestkosten {jahr} für Objekt {objektnummer} ({objekt.bezeichnung})"
        ))
        self.stdout.write(f"  Bereich {knr_von}–{knr_bis}, {len(auswahl)} Konten, Beträge {betrag_min}–{betrag_max} €")

        # Beträge + Datum je Konto festlegen (reproduzierbar via Seed)
        plan = []
        for i, konto in enumerate(auswahl):
            euro = Decimal(rng.uniform(betrag_min, betrag_max)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            monat = (i % 12) + 1
            plan.append((konto, euro, date(jahr, monat, 15)))

        if opts['dry_run']:
            self.stdout.write(self.style.WARNING("\n[DRY-RUN] Es würde gebucht:"))
            for konto, euro, datum in plan:
                self.stdout.write(f"    {konto.kontonummer} {konto.kontoname:<40} {euro:>10} €  ({datum})")
            self.stdout.write(f"  Summe: {sum(e for _, e, _ in plan)} €  — keine Änderungen geschrieben.")
            return

        gebucht = 0
        uebersprungen = 0
        summe = Decimal('0')
        with transaction.atomic():
            for konto, euro, datum in plan:
                belegnr = f'TESTK-{jahr}-{konto.kontonummer}'
                vorhanden = Buchung.objects.filter(objekt=objekt, belegnr=belegnr)
                if vorhanden.exists():
                    if opts['force']:
                        vorhanden.delete()
                    else:
                        uebersprungen += 1
                        continue
                Buchung.objects.create(
                    objekt=objekt,
                    buchungsart=None,
                    betrag=euro,
                    soll_konto=konto,
                    haben_konto=bank,
                    buchungsdatum=datum,
                    belegdatum=datum,
                    belegnr=belegnr,
                    buchungstext=f'Testkosten {konto.kontoname}',
                    wirtschaftsjahr=wj,
                    status='festgeschrieben',
                    erstellt_von=user,
                )
                gebucht += 1
                summe += euro

        self.stdout.write(self.style.SUCCESS(
            f"\n✓ {gebucht} Kostenbuchungen angelegt"
            f"{f', {uebersprungen} übersprungen (bereits vorhanden)' if uebersprungen else ''}.\n"
            f"    Summe neu gebucht: {summe} €"
        ))
