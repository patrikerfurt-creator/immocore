"""
Manueller Anstoss des Mail-Posteingangs plus Auswertung der Erkennungsgüte.

Der Celery-Beat-Task ``vorgaenge.mail_ordner_scan`` macht dasselbe im
Hintergrund — dieses Kommando ist für den Testlauf gedacht, bei dem man das
Ergebnis sofort sehen will (Muster: ``rechnungen.rechnung_watch``).

    python manage.py mail_scan                  # Ordner aus der Einstellung
    python manage.py mail_scan --ordner /app/Maileingang
    python manage.py mail_scan --trocken        # erkennt, legt nichts an
    python manage.py mail_scan --auswertung     # nur Statistik, kein Scan
"""
import pathlib

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from apps.vorgaenge.models import MailImportProtokoll

TRENNER = '-' * 78


def _kuerze(text, laenge):
    text = (text or '').replace('\n', ' ').strip()
    if len(text) <= laenge:
        return text.ljust(laenge)
    return text[:laenge - 1] + '…'


class Command(BaseCommand):
    help = ('Verarbeitet .eml-Dateien aus dem Mail-Posteingang und zeigt, was '
            'die Erkennung daraus gemacht hat.')

    def add_arguments(self, parser):
        parser.add_argument(
            '--ordner',
            help='Posteingangs-Ordner. Ohne Angabe wird die '
                 'ImportOrdnerEinstellung mit bereich="mails" verwendet.',
        )
        parser.add_argument('--archiv', help='Zielordner für verarbeitete Mails.')
        parser.add_argument(
            '--fehler',
            help='Zielordner für nicht zugeordnete und fehlerhafte Mails.',
        )
        parser.add_argument(
            '--trocken', action='store_true',
            help='Erkennung vollständig ausführen, aber KEINE Vorgänge anlegen.',
        )
        parser.add_argument(
            '--auswertung', action='store_true',
            help='Nur die Statistik über die bisherigen Protokolle ausgeben, '
                 'nichts verarbeiten.',
        )
        parser.add_argument(
            '--limit', type=int, default=40,
            help='Wie viele Protokollzeilen im Detail gezeigt werden (Default 40).',
        )

    # -- Ordner -----------------------------------------------------------

    def _ordner_ermitteln(self, optionen):
        if optionen['ordner']:
            return optionen['ordner'], optionen['archiv'], optionen['fehler']

        from apps.buchhaltung.models import ImportOrdnerEinstellung
        einst = ImportOrdnerEinstellung.objects.filter(bereich='mails').first()
        if einst is None or not einst.import_ordner:
            raise CommandError(
                'Kein Posteingang konfiguriert. Entweder --ordner angeben oder '
                'eine ImportOrdnerEinstellung mit bereich="mails" anlegen '
                '(Pfad im Container-Format, z.B. /app/Maileingang).'
            )
        if not einst.aktiv:
            self.stdout.write(self.style.WARNING(
                'Hinweis: Die Einstellung ist auf aktiv=False — der Beat-Task '
                'ueberspringt sie, dieser manuelle Lauf nicht.'))
        return einst.import_ordner, einst.archiv_ordner, einst.fehler_ordner

    # -- Ausgabe ----------------------------------------------------------

    def _zeige_detail(self, protokolle):
        if not protokolle:
            return
        self.stdout.write('')
        self.stdout.write(TRENNER)
        self.stdout.write(
            f"{'DATEI':<26}{'STATUS':<18}{'PERSON':<22}{'EINHEIT':<12}TYP")
        self.stdout.write(TRENNER)

        for p in protokolle:
            einheit = p.einheit.einheit_nr if p.einheit_id else (
                p.objekt.bezeichnung if p.objekt_id else '-')
            typ = p.ki_typ_code or '-'
            if p.ki_konfidenz is not None:
                typ = f"{typ} ({p.ki_konfidenz:.2f})"
            zeile = (f"{_kuerze(p.dateiname, 26)}"
                     f"{_kuerze(p.get_status_display(), 18)}"
                     f"{_kuerze(p.person.name if p.person_id else '-', 22)}"
                     f"{_kuerze(einheit, 12)}{typ}")

            if p.status == 'vorgang_neu':
                self.stdout.write(self.style.SUCCESS(zeile))
            elif p.status in ('nicht_zugeordnet', 'fehler'):
                self.stdout.write(self.style.ERROR(zeile))
            else:
                self.stdout.write(zeile)

            hinweise = []
            if p.mehrdeutig:
                hinweise.append('mehrdeutig: Einheit nicht eindeutig bestimmbar')
            if p.ki_fehler:
                hinweise.append(f'KI: {p.ki_fehler}')
            if p.fehler:
                hinweise.append(f'Fehler: {p.fehler}')
            if p.vorgang_id:
                hinweise.append(f'-> {p.vorgang.nummer}')
            for hinweis in hinweise:
                self.stdout.write(f"    {hinweis}")

    def _zeige_statistik(self):
        gesamt = MailImportProtokoll.objects.count()
        if not gesamt:
            self.stdout.write('Noch keine Mails verarbeitet.')
            return

        self.stdout.write('')
        self.stdout.write(TRENNER)
        self.stdout.write(f'AUSWERTUNG ueber {gesamt} verarbeitete Mail(s)')
        self.stdout.write(TRENNER)

        self.stdout.write('\nErgebnis:')
        anzeige = dict(MailImportProtokoll.STATUS_CHOICES)
        for zeile in (MailImportProtokoll.objects
                      .values('status').annotate(n=Count('id')).order_by('-n')):
            anteil = zeile['n'] / gesamt * 100
            self.stdout.write(
                f"  {anzeige.get(zeile['status'], zeile['status']):<34}"
                f"{zeile['n']:>4}  ({anteil:5.1f} %)")

        # Die Kernzahl: bei wie vielen Mails hat Stufe 1 den Absender
        # ueberhaupt einer Person zuordnen koennen. Alles Weitere haengt daran.
        mit_person = MailImportProtokoll.objects.filter(person__isnull=False).count()
        mit_einheit = MailImportProtokoll.objects.filter(einheit__isnull=False).count()
        mehrdeutig = MailImportProtokoll.objects.filter(mehrdeutig=True).count()
        self.stdout.write('\nStufe 1 (regelbasiert):')
        self.stdout.write(f"  Person erkannt                    {mit_person:>4}  "
                          f"({mit_person / gesamt * 100:5.1f} %)")
        self.stdout.write(f"  Einheit eindeutig                 {mit_einheit:>4}  "
                          f"({mit_einheit / gesamt * 100:5.1f} %)")
        self.stdout.write(f"  davon mehrdeutig markiert         {mehrdeutig:>4}")

        mit_ki = MailImportProtokoll.objects.exclude(ki_typ_code='')
        anzahl_ki = mit_ki.count()
        self.stdout.write('\nStufe 2 (KI-Klassifikation):')
        self.stdout.write(f"  Typ vorgeschlagen                 {anzahl_ki:>4}  "
                          f"({anzahl_ki / gesamt * 100:5.1f} %)")
        ki_fehler = MailImportProtokoll.objects.exclude(ki_fehler='').count()
        if ki_fehler:
            self.stdout.write(self.style.WARNING(
                f"  KI-Fehler                         {ki_fehler:>4}"))
        for zeile in (mit_ki.values('ki_typ_code')
                      .annotate(n=Count('id')).order_by('-n')):
            self.stdout.write(f"    {zeile['ki_typ_code']:<30}{zeile['n']:>4}")

        konfidenzen = [float(k) for k in mit_ki.exclude(ki_konfidenz__isnull=True)
                       .values_list('ki_konfidenz', flat=True)]
        if konfidenzen:
            schnitt = sum(konfidenzen) / len(konfidenzen)
            niedrig = sum(1 for k in konfidenzen if k < 0.7)
            self.stdout.write(f"    Konfidenz im Schnitt          {schnitt:>7.2f}")
            self.stdout.write(f"    davon unter 0.70              {niedrig:>4}")

        # Manuelle Bewertung — der eigentliche Guetemassstab. Sie entsteht
        # erst, wenn jemand die Zeilen durchsieht (Django-Admin: Mail-Import-
        # Protokoll, Feld "bewertung").
        bewertet = MailImportProtokoll.objects.exclude(bewertung='offen')
        anzahl_bewertet = bewertet.count()
        self.stdout.write('\nManuelle Bewertung:')
        if not anzahl_bewertet:
            self.stdout.write(
                '  noch keine Zeile bewertet — im Django-Admin unter '
                '"Mail-Import-Protokolle" das Feld "bewertung" setzen,\n'
                '  danach zeigt diese Auswertung die echte Trefferquote.')
        else:
            for zeile in (bewertet.values('bewertung')
                          .annotate(n=Count('id')).order_by('-n')):
                anteil = zeile['n'] / anzahl_bewertet * 100
                self.stdout.write(f"  {zeile['bewertung']:<34}{zeile['n']:>4}  "
                                  f"({anteil:5.1f} %)")
            richtig = bewertet.filter(bewertung='richtig').count()
            self.stdout.write(self.style.SUCCESS(
                f"\n  Trefferquote: {richtig}/{anzahl_bewertet} "
                f"= {richtig / anzahl_bewertet * 100:.1f} % "
                f"(von {gesamt} verarbeiteten Mails bewertet: {anzahl_bewertet})"))

    # -- Ablauf -----------------------------------------------------------

    def handle(self, *args, **optionen):
        from apps.vorgaenge.services import mail_import_service

        if optionen['auswertung']:
            self._zeige_statistik()
            return

        ordner, archiv, fehler = self._ordner_ermitteln(optionen)
        if not pathlib.Path(ordner).is_dir():
            raise CommandError(
                f'Ordner nicht gefunden: {ordner}\n'
                'Laeuft das Backend im Container, muss der Pfad der Pfad IM '
                'Container sein (/app/...), nicht der Windows-Pfad.'
            )

        vorher = MailImportProtokoll.objects.count()
        modus = 'TROCKENLAUF (keine Anlage)' if optionen['trocken'] else 'Anlage aktiv'
        self.stdout.write(f'Posteingang: {ordner}   [{modus}]')

        ergebnis = mail_import_service.scan_ordner(
            ordner, archiv, fehler, anlegen=not optionen['trocken'],
        )

        if not ergebnis['dateien']:
            self.stdout.write(self.style.WARNING(
                'Keine .eml-Dateien im Ordner gefunden.'))
            return

        neue = MailImportProtokoll.objects.order_by('verarbeitet_am')[vorher:]
        self._zeige_detail(list(neue[:optionen['limit']]))

        self.stdout.write('')
        self.stdout.write(TRENNER)
        self.stdout.write(
            f"{ergebnis['dateien']} Datei(en): "
            f"{ergebnis['vorgang_neu']} neue Vorgaenge, "
            f"{ergebnis['thread_zuordnung']} Thread-Zuordnungen, "
            f"{ergebnis['duplikat']} Duplikate, "
            f"{ergebnis['nicht_zugeordnet']} nicht zugeordnet, "
            f"{ergebnis['fehler']} Fehler")
        if ergebnis.get('uebersprungen'):
            self.stdout.write(self.style.WARNING(
                f"{ergebnis['uebersprungen']} Datei(en) uebersprungen — sie "
                f"wurden zeitgleich von einem anderen Lauf (Celery-Beat) "
                f"verarbeitet."))
        self.stdout.write(
            'Auswertung ueber alle Laeufe: python manage.py mail_scan --auswertung')
