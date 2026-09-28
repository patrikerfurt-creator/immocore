"""
Traegt die DMS-Ablage fuer bereits verarbeitete Mails nach.

Mails, die vor der Einfuehrung der DMS-Ablage eingelesen wurden, haben eine
Protokollzeile, aber kein Dokument. Die Originaldateien liegen noch im
Archiv- bzw. Fehlerordner — dieses Kommando liest sie erneut und legt Mail
und Anhaenge ab, ohne die Erkennung noch einmal laufen zu lassen (keine
KI-Aufrufe, keine neuen Vorgaenge, keine geaenderten Zuordnungen).

    python manage.py mail_dms_nachtragen            # zeigt nur, was fehlt
    python manage.py mail_dms_nachtragen --ja       # legt ab

Zeilen mit Status 'duplikat' werden uebersprungen: deren Mail liegt bereits
ueber die urspruengliche Protokollzeile im DMS.
"""
import pathlib

from django.core.management.base import BaseCommand, CommandError

from apps.vorgaenge.models import MailImportProtokoll
from apps.vorgaenge.services import mail_import_service as mis


class Command(BaseCommand):
    help = 'Legt Mail und Anhaenge fuer bereits verarbeitete Mails im DMS ab.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--ja', action='store_true',
            help='Pflicht — ohne dieses Flag wird nur angezeigt, was fehlt.',
        )
        parser.add_argument(
            '--ordner',
            help='Posteingang. Ohne Angabe aus der ImportOrdnerEinstellung '
                 'mit bereich="mails".',
        )

    def _ordner(self, optionen) -> pathlib.Path:
        if optionen['ordner']:
            return pathlib.Path(optionen['ordner'])
        from apps.buchhaltung.models import ImportOrdnerEinstellung
        einst = ImportOrdnerEinstellung.objects.filter(bereich='mails').first()
        if einst is None or not einst.import_ordner:
            raise CommandError('Kein Posteingang konfiguriert — --ordner angeben.')
        return pathlib.Path(einst.import_ordner)

    def _finde_datei(self, eingang: pathlib.Path, dateiname: str) -> pathlib.Path | None:
        """Sucht die Originaldatei in Archiv, Fehlerordner und Eingang."""
        for unterordner in ('archiv', 'fehler', ''):
            kandidat = (eingang / unterordner / dateiname) if unterordner else (eingang / dateiname)
            if kandidat.is_file():
                return kandidat
        return None

    def handle(self, *args, **optionen):
        eingang = self._ordner(optionen)
        benutzer = mis.mail_system_user()

        offen = (MailImportProtokoll.objects
                 .filter(dokumente__isnull=True)
                 .exclude(status__in=('duplikat', 'fehler'))
                 .order_by('gesendet_am'))

        gesamt = offen.count()
        if not gesamt:
            self.stdout.write(self.style.SUCCESS(
                'Nichts nachzutragen — jede verarbeitete Mail liegt im DMS.'))
            return

        self.stdout.write(f'{gesamt} Mail(s) ohne DMS-Ablage.\n')

        fehlend = []
        for protokoll in offen:
            datei = self._finde_datei(eingang, protokoll.dateiname)
            if datei is None:
                fehlend.append(protokoll)
                continue
            if not optionen['ja']:
                self.stdout.write(f'  wuerde ablegen: {protokoll.dateiname[:72]}')
                continue
            try:
                parsed = mis.parse_mail(datei)
            except Exception as exc:
                self.stdout.write(self.style.ERROR(
                    f'  nicht lesbar: {protokoll.dateiname[:60]} — {exc}'))
                continue
            anzahl = mis._lege_im_dms_ab(
                protokoll, parsed, benutzer, vorgang=protokoll.vorgang)
            self.stdout.write(self.style.SUCCESS(
                f'  {anzahl} Dokument(e): {protokoll.dateiname[:66]}'))

        if fehlend:
            self.stdout.write(self.style.WARNING(
                f'\n{len(fehlend)} Datei(en) nicht auffindbar — die Mail wurde '
                f'verarbeitet, die Originaldatei liegt aber nicht mehr in '
                f'{eingang} (archiv/, fehler/ oder direkt darin):'))
            for protokoll in fehlend[:20]:
                self.stdout.write(f'  {protokoll.dateiname[:72]}')

        if not optionen['ja']:
            self.stdout.write(self.style.WARNING(
                '\nNichts abgelegt — zum Ausfuehren --ja anhaengen.'))
