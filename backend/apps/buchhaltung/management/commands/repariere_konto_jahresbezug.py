"""
Repariert Buchungen, deren Konto-FK auf die Jahres-Instanz eines FREMDEN
Wirtschaftsjahres zeigt.

Konten sind jahresgebunden: dieselbe Kontonummer existiert je WJ als eigener
Datensatz. Buchungen, die einen Verweis aus einem anderen Jahr geerbt haben
(Kontenplan-Auswahl im Frontend, gespeicherte Regeln, Vorjahres-Vorlagen),
landen auf dem Kontoblatt des falschen Jahres und fehlen in jahresbezogenen
Auswertungen — sichtbar z. B. an einem Saldovortrag auf 09911, der im
Rücklagen-Ausweis nicht ankommt.

Maßgeblich ist das Jahr des Buchungsdatums — dieselbe Regel, die
Buchung.save() seit dieser Änderung auf jedem Schreibpfad anwendet. Das
Kommando zieht damit nur den Altbestand nach.

Repariert wird ausschließlich der Fremdschlüssel auf das gleichnamige Konto
im Buchungsjahr. Betrag, Datum, Buchungstext, Status und Buchungsart bleiben
unberührt — der wirtschaftliche Inhalt ändert sich nicht, es wird nur ein
technisch falscher Verweis geradegezogen. Das betrifft auch festgeschriebene
Buchungen: vor einem Lauf auf Live ein Backup ziehen.

    python manage.py repariere_konto_jahresbezug              # Vorschau
    python manage.py repariere_konto_jahresbezug --apply      # schreiben
    python manage.py repariere_konto_jahresbezug --objekt ABC --apply
"""
from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F, Q
from django.db.models.functions import ExtractYear

from apps.buchhaltung.models import Buchung
from apps.konten.services import konto_im_jahr

FELDER = ('soll_konto', 'haben_konto')


class Command(BaseCommand):
    help = 'Hängt Buchungen mit fremdjährigem Konto-FK auf das Konto ihres Buchungsjahres um.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Änderungen schreiben (ohne dieses Flag nur Vorschau).')
        parser.add_argument(
            '--objekt', default=None,
            help='Nur ein Objekt (Kurzbezeichnung).')

    def handle(self, *args, **opts):
        schreiben = opts['apply']
        qs = Buchung.objects.select_related(
            'soll_konto__wirtschaftsjahr', 'haben_konto__wirtschaftsjahr',
        )
        if opts['objekt']:
            qs = qs.filter(objekt__kurzbezeichnung=opts['objekt'])

        qs = qs.annotate(buchungsjahr=ExtractYear('buchungsdatum')).filter(
            Q(soll_konto__isnull=False) & ~Q(soll_konto__wirtschaftsjahr__jahr=F('buchungsjahr'))
            | Q(haben_konto__isnull=False) & ~Q(haben_konto__wirtschaftsjahr__jahr=F('buchungsjahr'))
        ).distinct()

        repariert = Counter()
        ohne_ziel = Counter()
        betroffen = 0

        with transaction.atomic():
            for b in qs:
                jahr = b.buchungsdatum.year
                zu_schreiben = []
                for feld in FELDER:
                    konto = getattr(b, feld)
                    if konto is None or konto.wirtschaftsjahr_id is None:
                        continue
                    if konto.wirtschaftsjahr.jahr == jahr:
                        continue
                    ziel = konto_im_jahr(konto, jahr)
                    marke = '%s: %s → %s' % (
                        konto.kontonummer, konto.wirtschaftsjahr.jahr, jahr)
                    if ziel.id == konto.id:
                        # Im Zieljahr existiert kein gleichnamiges Konto.
                        ohne_ziel[marke] += 1
                        continue
                    setattr(b, feld, ziel)
                    zu_schreiben.append(feld)
                    repariert[marke] += 1
                if zu_schreiben:
                    betroffen += 1
                    if schreiben:
                        # save() löst die Konten ohnehin ins Buchungsjahr auf.
                        b.save(update_fields=zu_schreiben)
            if not schreiben:
                transaction.set_rollback(True)

        for marke, n in sorted(repariert.items()):
            self.stdout.write('  %-32s %4d Buchung(en)' % (marke, n))
        for marke, n in sorted(ohne_ziel.items()):
            self.stdout.write(self.style.WARNING(
                '  %-32s %4d Buchung(en) — kein Konto im Zieljahr, unverändert' % (marke, n)))

        if not repariert and not ohne_ziel:
            self.stdout.write(self.style.SUCCESS(
                'Nichts zu tun — alle Konto-FKs liegen im Jahr ihrer Buchung.'))
            return

        kopf = 'Repariert' if schreiben else 'Vorschau (nichts geschrieben)'
        self.stdout.write(self.style.SUCCESS(
            '%s: %d Buchung(en), %d Verweis(e).' % (kopf, betroffen, sum(repariert.values()))))
        if not schreiben:
            self.stdout.write('Mit --apply ausführen, um zu schreiben.')
