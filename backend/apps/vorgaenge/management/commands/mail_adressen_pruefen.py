"""
Prueft, wie gut sich Absenderadressen ueberhaupt zuordnen lassen — vor dem
ersten Mail-Import und nach jeder Stammdatenpflege.

Die Kennzahl "Einheit eindeutig" aus ``mail_scan --auswertung`` haengt fast
vollstaendig an der Qualitaet der Mailadressen in den Stammdaten. Dieses
Kommando zeigt, woran es liegt, statt es raten zu lassen:

    python manage.py mail_adressen_pruefen
    python manage.py mail_adressen_pruefen --alle

Geteilte Adressen haben zwei Ursachen, die man an den Daten nicht sauber
trennen kann: Ehepaare mit getrennten Personensaetzen — und echte Dubletten
(derselbe Name zweimal, oder einmal "Hermann" und einmal "Herrmann"). Beide
tauchen hier auf; der Verdacht auf Dublette wird markiert, entschieden wird
er von einem Menschen.
"""
from collections import defaultdict

from django.core.management.base import BaseCommand

from apps.personen.models import EigentumsVerhaeltnis, Person
from apps.vorgaenge.services.mail_import_service import alle_adressen


def _namenskern(person) -> str:
    """Grobe Normalform des Namens fuer den Dublettenverdacht.

    Bewusst simpel — Doppelbuchstaben und Leerzeichen raus, kleingeschrieben.
    Damit fallen "Hermann"/"Herrmann" und "Mueller"/"Müller" zusammen. Das
    ist eine HEURISTIK fuer einen Hinweis, keine Entscheidung.
    """
    name = (person.name or '').lower()
    for alt, neu in (('ä', 'a'), ('ö', 'o'), ('ü', 'u'), ('ß', 's')):
        name = name.replace(alt, neu)
    name = ''.join(z for z in name if z.isalnum())
    entdoppelt = []
    for zeichen in name:
        if not entdoppelt or entdoppelt[-1] != zeichen:
            entdoppelt.append(zeichen)
    return ''.join(entdoppelt)


class Command(BaseCommand):
    help = ('Zeigt, wie eindeutig sich Absenderadressen auf Personen und '
            'Einheiten abbilden lassen.')

    def add_arguments(self, parser):
        parser.add_argument(
            '--alle', action='store_true',
            help='Auch die Adressen auflisten, die sauber eindeutig sind.',
        )

    def handle(self, *args, **optionen):
        nach_adresse = defaultdict(list)
        ohne_adresse = 0
        for person in Person.objects.all():
            adressen = alle_adressen(person)
            if not adressen:
                ohne_adresse += 1
            for adresse in adressen:
                nach_adresse[adresse].append(person)

        personen_gesamt = Person.objects.count()
        geteilt = {a: ps for a, ps in nach_adresse.items() if len(ps) > 1}

        self.stdout.write(f'Personen gesamt:              {personen_gesamt}')
        self.stdout.write(f'  davon ohne Mailadresse:     {ohne_adresse}  '
                          f'(deren Mails sind nicht zuordenbar)')
        self.stdout.write(f'Verschiedene Adressen:        {len(nach_adresse)}')
        self.stdout.write(f'  von mehreren Personen:      {len(geteilt)}')

        if not geteilt:
            self.stdout.write(self.style.SUCCESS(
                '\nKeine geteilten Adressen — jede Mail ist eindeutig '
                'einer Person zuzuordnen.'))
            return

        self.stdout.write('')
        self.stdout.write('-' * 78)
        self.stdout.write('GETEILTE ADRESSEN')
        self.stdout.write('-' * 78)

        zaehler = {'einheit': 0, 'objekt': 0, 'verstreut': 0, 'ohne_ev': 0}
        dublettenverdacht = []

        for adresse, personen in sorted(geteilt.items()):
            evs = list(
                EigentumsVerhaeltnis.objects
                .filter(person__in=personen, ende__isnull=True)
                .select_related('einheit', 'einheit__objekt')
            )
            einheiten = {ev.einheit_id for ev in evs}
            objekte = {ev.einheit.objekt_id for ev in evs}
            mit_ev = {ev.person_id for ev in evs}

            if not evs:
                zaehler['ohne_ev'] += 1
                befund, stil = 'kein aktives EV — keine Zuordnung', self.style.ERROR
            elif len(einheiten) == 1:
                zaehler['einheit'] += 1
                befund, stil = 'EINE Einheit — voll zuordenbar', self.style.SUCCESS
            elif len(objekte) == 1:
                zaehler['objekt'] += 1
                befund = f'ein Objekt, {len(einheiten)} Einheiten — nur Objekt'
                stil = self.style.WARNING
            else:
                zaehler['verstreut'] += 1
                befund = f'{len(objekte)} Objekte — keine Zuordnung'
                stil = self.style.ERROR

            # Nur ein Satz mit Vertrag + gleicher Namenskern = sehr
            # wahrscheinlich dieselbe Person doppelt erfasst.
            kerne = {_namenskern(p) for p in personen}
            verdacht = len(kerne) == 1 and len(mit_ev) <= 1
            if verdacht:
                dublettenverdacht.append((adresse, personen))

            self.stdout.write(stil(f'  {adresse}'))
            self.stdout.write(f'      {befund}')
            for person in personen:
                hat_ev = 'Vertrag' if person.id in mit_ev else 'ohne Vertrag'
                self.stdout.write(
                    f'      - {person.name[:52]:<54}{person.personennummer or "-":<14}{hat_ev}')
            if verdacht:
                self.stdout.write(self.style.WARNING(
                    '      ^ Dublettenverdacht: gleicher Name, nur ein Vertrag'))

        self.stdout.write('')
        self.stdout.write('-' * 78)
        self.stdout.write('Auswirkung auf die Erkennung:')
        self.stdout.write(f'  voll zuordenbar (eine Einheit)      {zaehler["einheit"]:>4}')
        self.stdout.write(f'  nur Objekt bestimmbar               {zaehler["objekt"]:>4}')
        self.stdout.write(f'  gar nicht zuordenbar                '
                          f'{zaehler["verstreut"] + zaehler["ohne_ev"]:>4}')
        if dublettenverdacht:
            self.stdout.write(self.style.WARNING(
                f'\n{len(dublettenverdacht)} Adresse(n) mit Dublettenverdacht — '
                f'werden die Personensaetze zusammengefuehrt,\nwird aus jedem '
                f'dieser Faelle eine eindeutige Zuordnung.'))
