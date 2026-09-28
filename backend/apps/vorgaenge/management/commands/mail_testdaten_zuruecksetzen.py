"""
Setzt einen Mail-Import-Testlauf zurueck.

Beim Erproben der Erkennung will man dieselben Mails mehrfach durchlaufen
lassen — mit anderem Prompt, anderem Modell, geaenderten Regeln. Dafuer
muessen Protokoll und die daraus entstandenen Vorgaenge weg, sonst greift
die Duplikatpruefung und man misst nichts mehr.

    python manage.py mail_testdaten_zuruecksetzen --ja
    python manage.py mail_testdaten_zuruecksetzen --ja --mails-zurueck

Geloescht wird ausschliesslich, was der Mail-Import erzeugt hat: die
Protokollzeilen, die Vorgaenge mit ``quelle='mail'`` samt abhaengigen Zeilen
und die ``mail_eingegangen``-Ereignisse an vorbestehenden Vorgaengen.
Vorgaenge anderer Herkunft (manuell, Portal, Beschluss) bleiben unberuehrt.
"""
import pathlib

from django.core.management.base import BaseCommand, CommandError

from apps.vorgaenge.models import (
    MailImportProtokoll, Vorgang, VorgangEreignis,
)
from apps.vorgaenge.services.mail_import_service import ERLAUBTE_ENDUNGEN


class Command(BaseCommand):
    help = ('Loescht Protokoll und Vorgaenge eines Mail-Import-Testlaufs '
            '(nur quelle="mail").')

    def add_arguments(self, parser):
        parser.add_argument(
            '--ja', action='store_true',
            help='Pflicht — bestaetigt das Loeschen. Ohne dieses Flag wird '
                 'nur angezeigt, was geloescht wuerde.',
        )
        parser.add_argument(
            '--mails-zurueck', action='store_true',
            help='Verschiebt die Mails aus archiv/ und fehler/ zurueck in den '
                 'Posteingang, damit derselbe Satz erneut laufen kann.',
        )
        parser.add_argument(
            '--ordner',
            help='Posteingang fuer --mails-zurueck. Ohne Angabe aus der '
                 'ImportOrdnerEinstellung mit bereich="mails".',
        )

    def _ordner(self, optionen):
        if optionen['ordner']:
            return pathlib.Path(optionen['ordner'])
        from apps.buchhaltung.models import ImportOrdnerEinstellung
        einst = ImportOrdnerEinstellung.objects.filter(bereich='mails').first()
        if einst is None or not einst.import_ordner:
            raise CommandError(
                'Kein Posteingang konfiguriert — --ordner angeben.')
        return pathlib.Path(einst.import_ordner)

    def handle(self, *args, **optionen):
        protokolle = MailImportProtokoll.objects.count()
        mail_vorgaenge = Vorgang.objects.filter(quelle='mail')
        nummern = sorted(mail_vorgaenge.values_list('nummer', flat=True))
        ereignisse = VorgangEreignis.objects.filter(typ='mail_eingegangen')

        self.stdout.write(f'Protokollzeilen:           {protokolle}')
        self.stdout.write(f'Vorgaenge mit quelle=mail: {len(nummern)}')
        if nummern:
            self.stdout.write(f'  {", ".join(nummern)}')
        self.stdout.write(f'Mail-Ereignisse:           {ereignisse.count()}')

        if not optionen['ja']:
            self.stdout.write(self.style.WARNING(
                '\nNichts geloescht — zum Ausfuehren --ja anhaengen.'))
            return

        # Zuerst die Dokumente: ``Dokument.vorgang`` ist PROTECT, ein Vorgang
        # mit abgelegter Mail liesse sich sonst nicht loeschen. Betroffen sind
        # ausschliesslich Dokumente aus dem Mail-Import (mail_import gesetzt) —
        # alles andere im DMS bleibt unangetastet.
        from apps.dokumente.models import Dokument
        mail_dokumente = Dokument.objects.filter(mail_import__isnull=False)
        gesperrt = mail_dokumente.filter(revisionssicher=True)
        if gesperrt.exists():
            self.stdout.write(self.style.WARNING(
                f'{gesperrt.count()} Dokument(e) sind revisionssicher und '
                f'bleiben erhalten (GoBD).'))
        anzahl_dokumente = mail_dokumente.filter(revisionssicher=False).count()
        for dokument in mail_dokumente.filter(revisionssicher=False):
            dokument.delete()
        self.stdout.write(f'{anzahl_dokumente} Mail-Dokument(e) geloescht.')

        ereignisse.delete()
        MailImportProtokoll.objects.all().delete()
        geloescht, _ = mail_vorgaenge.delete()
        self.stdout.write(self.style.SUCCESS(
            f'\nGeloescht: {geloescht} Datensaetze. '
            f'Verbleibende Vorgaenge gesamt: {Vorgang.objects.count()}'))

        if not optionen['mails_zurueck']:
            return

        eingang = self._ordner(optionen)
        zurueck = 0
        for unterordner in ('archiv', 'fehler'):
            quelle = eingang / unterordner
            if not quelle.is_dir():
                continue
            for datei in quelle.iterdir():
                if datei.is_file() and datei.suffix.lower() in ERLAUBTE_ENDUNGEN:
                    ziel = eingang / datei.name
                    if ziel.exists():
                        continue
                    datei.rename(ziel)
                    zurueck += 1
        self.stdout.write(self.style.SUCCESS(
            f'{zurueck} Mail(s) zurueck in den Posteingang gelegt: {eingang}'))
