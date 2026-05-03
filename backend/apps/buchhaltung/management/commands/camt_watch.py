"""
Management Command: camt_watch
Überwacht einen Ordner auf neue camt.053 XML-Dateien und importiert sie automatisch.

Verwendung:
    python manage.py camt_watch
    python manage.py camt_watch --ordner /pfad/zum/ordner --intervall 60
    python manage.py camt_watch --objekt <UUID>  (falls mehrere Objekte)

Beim Start werden vorhandene Dateien sofort importiert.
Danach wird der Ordner alle --intervall Sekunden geprüft.
Importierte Dateien werden nach archiv/ verschoben, fehlerhafte nach fehler/.
"""
import logging
import shutil
import time
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

logger = logging.getLogger(__name__)

WATCH_ORDNER = Path(r'C:\Projekte\immocore\CamtDAT')


class Command(BaseCommand):
    help = 'Überwacht CamtDAT-Ordner und importiert neue camt.053 XML-Dateien'

    def add_arguments(self, parser):
        parser.add_argument(
            '--ordner',
            default=str(WATCH_ORDNER),
            help='Zu überwachender Ordner (Standard: C:\\Projekte\\immocore\\CamtDAT)',
        )
        parser.add_argument(
            '--intervall',
            type=int,
            default=60,
            help='Prüfintervall in Sekunden (Standard: 60)',
        )
        parser.add_argument(
            '--objekt',
            default=None,
            help='Objekt-UUID (Standard: erstes Objekt in der Datenbank)',
        )

    def handle(self, *args, **options):
        ordner = Path(options['ordner'])
        intervall = options['intervall']
        objekt_id = options['objekt']

        archiv = ordner / 'archiv'
        fehler = ordner / 'fehler'
        archiv.mkdir(exist_ok=True)
        fehler.mkdir(exist_ok=True)

        # Objekt ermitteln
        from apps.objekte.models import Objekt
        if objekt_id:
            try:
                objekt = Objekt.objects.get(pk=objekt_id)
            except Objekt.DoesNotExist:
                self.stderr.write(self.style.ERROR(f'Objekt {objekt_id} nicht gefunden.'))
                return
        else:
            objekt = Objekt.objects.first()
            if not objekt:
                self.stderr.write(self.style.ERROR('Kein Objekt in der Datenbank gefunden.'))
                return

        self.stdout.write(self.style.SUCCESS(
            f'camt_watch gestartet\n'
            f'  Ordner:    {ordner}\n'
            f'  Objekt:    {objekt.bezeichnung}\n'
            f'  Intervall: {intervall}s\n'
            f'  Archiv:    {archiv}\n'
        ))

        # Beim Start: vorhandene Dateien sofort verarbeiten
        self.stdout.write('Prüfe vorhandene Dateien beim Start…')
        self._verarbeite_ordner(ordner, archiv, fehler, objekt)

        # Überwachungs-Loop
        self.stdout.write(f'Warte auf neue Dateien (alle {intervall}s)…')
        while True:
            time.sleep(intervall)
            self._verarbeite_ordner(ordner, archiv, fehler, objekt)

    def _verarbeite_ordner(self, ordner: Path, archiv: Path, fehler: Path, objekt):
        """Importiert alle XML-Dateien im Ordner (keine Unterordner)."""
        seen: set[str] = set()
        dateien = []
        for p in sorted(ordner.glob('*.xml')) + sorted(ordner.glob('*.XML')):
            if p.name.lower() not in seen:
                seen.add(p.name.lower())
                dateien.append(p)
        if not dateien:
            return

        self.stdout.write(f'  {len(dateien)} Datei(en) gefunden…')
        for datei in dateien:
            self._importiere_datei(datei, archiv, fehler, objekt)

    def _importiere_datei(self, datei: Path, archiv: Path, fehler: Path, objekt):
        """Parst eine camt.053-Datei und speichert neue Kontoumsätze."""
        from apps.buchhaltung.models import Kontoumsatz
        from apps.buchhaltung.services.camt053 import parse_camt053
        from apps.buchhaltung.services.buchungserkennung import erkenne_buchung
        from apps.objekte.models import Bankkonto

        try:
            xml_bytes = datei.read_bytes()
            transaktionen = parse_camt053(xml_bytes)
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f'    FEHLER Parsen {datei.name}: {exc}'))
            ziel = fehler / datei.name
            shutil.move(str(datei), str(ziel))
            return

        importiert = 0
        duplikate = 0

        try:
            with transaction.atomic():
                for txn in transaktionen:
                    if Kontoumsatz.objects.filter(sha256_hash=txn['sha256_hash']).exists():
                        duplikate += 1
                        continue

                    empfaenger_iban = txn.get('empfaenger_iban', '')
                    bankkonto = None
                    # Bankkonto per IBAN aus der Datei oder Auftraggeber-IBAN suchen
                    for iban_kandidat in [empfaenger_iban, txn.get('auftraggeber_iban', '')]:
                        if iban_kandidat:
                            bankkonto = Bankkonto.objects.filter(
                                objekt=objekt, iban=iban_kandidat
                            ).first()
                            if bankkonto:
                                break

                    ku = Kontoumsatz.objects.create(
                        objekt=objekt,
                        bankkonto=bankkonto,
                        sha256_hash=txn['sha256_hash'],
                        betrag=txn['betrag'],
                        buchungsdatum=txn['buchungsdatum'],
                        wertstellungsdatum=txn.get('wertstellungsdatum'),
                        auftraggeber_name=txn.get('auftraggeber_name', ''),
                        auftraggeber_iban=txn.get('auftraggeber_iban', ''),
                        empfaenger_iban=empfaenger_iban,
                        verwendungszweck=txn.get('verwendungszweck', ''),
                        import_datei=datei.name,
                    )

                    # KI-Buchungserkennung
                    try:
                        vorschlag = erkenne_buchung(ku)
                        if vorschlag:
                            ku.ki_vorschlag = vorschlag
                            ku.status = 'erkannt'
                            ku.save(update_fields=['ki_vorschlag', 'status'])
                    except Exception:
                        pass  # Erkennung ist optional

                    importiert += 1

        except Exception as exc:
            self.stderr.write(self.style.ERROR(f'    FEHLER Import {datei.name}: {exc}'))
            ziel = fehler / datei.name
            shutil.move(str(datei), str(ziel))
            return

        # Datei ins Archiv verschieben
        ziel = archiv / datei.name
        # Bei Namenskonflikt im Archiv: Suffix anhängen
        if ziel.exists():
            ziel = archiv / f'{datei.stem}_{int(time.time())}{datei.suffix}'
        shutil.move(str(datei), str(ziel))

        self.stdout.write(self.style.SUCCESS(
            f'    OK {datei.name}: '
            f'{importiert} importiert, {duplikate} Duplikate → archiv/'
        ))
