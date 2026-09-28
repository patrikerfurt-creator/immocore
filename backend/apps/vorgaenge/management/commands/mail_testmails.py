"""
Erzeugt .eml-Testmails für den Posteingang — aus ECHTEN Stammdaten.

Der Sinn: die Erkennung wird nur dann aussagekräftig getestet, wenn die
Absenderadressen tatsächlich in ``Person.emails`` stehen. Von Hand
zusammengeklickte Mails treffen meist daneben, und man misst dann die
eigene Tipparbeit statt der Erkennung.

    python manage.py mail_testmails --ziel /app/Maileingang
    python manage.py mail_testmails --ziel /app/Maileingang --anzahl 12

Die Mails sind fachlich plausibel, aber frei erfunden. Neben den
Normalfällen entstehen bewusst auch die Fälle, an denen die Erkennung
scheitern SOLL — unbekannter Absender, Antwort auf einen laufenden Vorgang,
Mail ohne brauchbaren Betreff. Ein Testlauf ohne diese Fälle sieht besser
aus, als er ist.
"""
import email.utils
import pathlib
import random
from email.message import EmailMessage

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.personen.models import Person
from apps.vorgaenge.models import Vorgang
from apps.vorgaenge.services.mail_import_service import alle_adressen

# (Betreff, Text, erwarteter Typ) — der erwartete Typ ist nur Dokumentation
# für den, der das Ergebnis später bewertet.
VORLAGEN = [
    ('Heizung im Wohnzimmer wird nicht warm',
     'Sehr geehrte Damen und Herren,\n\n'
     'seit dem Wochenende wird der Heizkörper im Wohnzimmer nicht mehr warm. '
     'Die anderen Räume sind in Ordnung. Entlüftet habe ich bereits, es kam '
     'nur Wasser, keine Luft.\n\n'
     'Können Sie bitte einen Termin mit dem Heizungsbauer veranlassen?\n\n'
     'Mit freundlichen Grüßen\n{name}',
     'maengelmeldung'),
    ('Wasserschaden im Keller - dringend',
     'Guten Morgen,\n\n'
     'im Kellergang steht Wasser, etwa zwei Zentimeter hoch, und es läuft '
     'sichtbar an der Wand zum Heizungsraum herunter. Der Hausmeister ist '
     'nicht erreichbar.\n\n'
     'Bitte umgehend jemanden schicken, bevor die Kellerabteile volllaufen.\n\n'
     'Viele Grüße\n{name}',
     'maengelmeldung'),
    ('Frage zur Jahresabrechnung 2025',
     'Sehr geehrte Damen und Herren,\n\n'
     'ich habe die Jahresabrechnung erhalten und komme bei der Position '
     'Hausmeisterkosten nicht mit. Der Betrag liegt deutlich über dem '
     'Vorjahr.\n\n'
     'Könnten Sie mir die Zusammensetzung erläutern? Eine Aufstellung der '
     'Einzelrechnungen wäre hilfreich.\n\n'
     'Mit freundlichen Grüßen\n{name}',
     'anfrage'),
    ('Ruhestörung durch Nachbarn',
     'Sehr geehrte Damen und Herren,\n\n'
     'seit mehreren Wochen kommt es nachts regelmäßig zu erheblichem Lärm aus '
     'der Wohnung über mir. Ich habe das Gespräch gesucht, ohne Erfolg.\n\n'
     'Ich bitte Sie, die Hausordnung in Erinnerung zu rufen.\n\n'
     'Mit freundlichen Grüßen\n{name}',
     'beschwerde'),
    ('Neue Bankverbindung ab nächstem Monat',
     'Guten Tag,\n\n'
     'ich wechsle die Bank. Bitte ziehen Sie das Hausgeld ab dem kommenden '
     'Monat von meinem neuen Konto ein. Die Unterlagen für das SEPA-Mandat '
     'schicke ich Ihnen unterschrieben per Post.\n\n'
     'Freundliche Grüße\n{name}',
     'anfrage'),
    ('Garagentor schließt nicht mehr vollständig',
     'Hallo,\n\n'
     'das Tor der Tiefgarage bleibt seit gestern etwa 20 cm über dem Boden '
     'stehen und fährt dann wieder hoch. Die Lichtschranke ist sauber, daran '
     'liegt es nicht.\n\n'
     'Bitte kümmern Sie sich darum, die Garage steht derzeit faktisch offen.\n\n'
     'Gruß\n{name}',
     'maengelmeldung'),
    ('Terminanfrage Eigentümerversammlung',
     'Sehr geehrte Damen und Herren,\n\n'
     'wann ist die diesjährige Eigentümerversammlung geplant? Ich muss '
     'Urlaub einplanen und würde gerne teilnehmen.\n\n'
     'Mit freundlichen Grüßen\n{name}',
     'anfrage'),
    ('Treppenhausreinigung mangelhaft',
     'Sehr geehrte Damen und Herren,\n\n'
     'die Reinigung im Treppenhaus wird seit Monaten nur oberflächlich '
     'ausgeführt. Die Fensterbänke im zweiten Obergeschoss wurden erkennbar '
     'seit Wochen nicht angefasst.\n\n'
     'Bitte sprechen Sie die Firma darauf an.\n\n'
     'Mit freundlichen Grüßen\n{name}',
     'beschwerde'),
]

# Mail, deren Absender garantiert in keinen Stammdaten steht.
UNBEKANNT = (
    'werbung@beispiel-dienstleister.de',
    'Angebot Hausmeisterservice 2026',
    'Sehr geehrte Damen und Herren,\n\n'
    'gerne unterbreiten wir Ihnen ein Angebot für die Betreuung Ihrer '
    'Liegenschaften.\n\nMit freundlichen Grüßen\nVertrieb',
)

# Mail ohne brauchbaren Betreff — prüft, ob die KI den Typ trotzdem trifft.
OHNE_BETREFF = (
    '',
    'Hallo,\n\nwie besprochen. Der Rolladen im Schlafzimmer klemmt weiterhin, '
    'er lässt sich nur noch zur Hälfte herunterfahren.\n\nDanke und Gruß\n{name}',
)


class Command(BaseCommand):
    help = 'Erzeugt .eml-Testmails aus echten Stammdaten für den Mail-Posteingang.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--ziel', required=True,
            help='Zielordner für die .eml-Dateien (im Container: /app/...).',
        )
        parser.add_argument(
            '--anzahl', type=int, default=8,
            help='Wie viele Mails von bekannten Absendern (Default 8).',
        )
        parser.add_argument(
            '--empfaenger', default='info@demme-immobilien.de',
            help='To-Adresse der erzeugten Mails.',
        )
        parser.add_argument(
            '--seed', type=int,
            help='Zufallszahl festnageln, damit zwei Läufe dieselben Mails ergeben.',
        )

    def _schreibe(self, ziel: pathlib.Path, dateiname: str, *, von, von_name,
                  an, betreff, text, message_id, in_reply_to=None):
        mail = EmailMessage()
        mail['From'] = email.utils.formataddr((von_name, von)) if von_name else von
        mail['To'] = an
        mail['Subject'] = betreff
        mail['Date'] = email.utils.format_datetime(timezone.localtime())
        mail['Message-ID'] = message_id
        if in_reply_to:
            mail['In-Reply-To'] = in_reply_to
            mail['References'] = in_reply_to
        mail.set_content(text)

        pfad = ziel / dateiname
        pfad.write_bytes(mail.as_bytes())
        return pfad

    def handle(self, *args, **optionen):
        ziel = pathlib.Path(optionen['ziel'])
        try:
            ziel.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise CommandError(f'Zielordner nicht anlegbar: {exc}')

        if optionen['seed'] is not None:
            random.seed(optionen['seed'])

        an = optionen['empfaenger']
        marke = timezone.localtime().strftime('%Y%m%d%H%M%S')

        # Nur Personen, die wirklich eine Mailadresse haben — alles andere
        # waere ein Test der Adressfindung, nicht der Erkennung.
        kandidaten = [
            (p, sorted(alle_adressen(p))[0])
            # nach nachname, nicht nach name — 'name' ist eine Property,
            # kein Datenbankfeld.
            for p in Person.objects.exclude(email='').order_by('nachname')[:200]
            if alle_adressen(p)
        ]
        if not kandidaten:
            raise CommandError(
                'Keine Person mit E-Mail-Adresse in den Stammdaten gefunden. '
                'Ohne echte Absenderadressen ist der Test wertlos — bitte '
                'zuerst Stammdaten laden (local_seed).'
            )

        random.shuffle(kandidaten)
        anzahl = min(optionen['anzahl'], len(kandidaten))
        erzeugt = []

        for i in range(anzahl):
            person, adresse = kandidaten[i]
            betreff, text, erwartet = VORLAGEN[i % len(VORLAGEN)]
            pfad = self._schreibe(
                ziel, f'test_{marke}_{i + 1:02d}.eml',
                von=adresse, von_name=person.name, an=an,
                betreff=betreff, text=text.format(name=person.name),
                message_id=f'<test-{marke}-{i + 1}@beispiel.local>',
            )
            erzeugt.append((pfad.name, adresse, erwartet))

        # Sonderfall 1: unbekannter Absender -> muss 'nicht_zugeordnet' werden
        adresse, betreff, text = UNBEKANNT
        pfad = self._schreibe(
            ziel, f'test_{marke}_90_unbekannt.eml',
            von=adresse, von_name='Vertrieb', an=an,
            betreff=betreff, text=text,
            message_id=f'<test-{marke}-90@beispiel.local>',
        )
        erzeugt.append((pfad.name, adresse, 'nicht_zugeordnet (erwartet)'))

        # Sonderfall 2: Mail ohne Betreff von bekanntem Absender
        person, adresse = kandidaten[0]
        betreff, text = OHNE_BETREFF
        pfad = self._schreibe(
            ziel, f'test_{marke}_91_ohne_betreff.eml',
            von=adresse, von_name=person.name, an=an,
            betreff=betreff, text=text.format(name=person.name),
            message_id=f'<test-{marke}-91@beispiel.local>',
        )
        erzeugt.append((pfad.name, adresse, 'Typ nur aus dem Text'))

        # Sonderfall 3: Antwort auf einen bestehenden Vorgang. Die Nummer im
        # Betreff ist der Weg, den auch echte Antwortmails nehmen werden.
        letzter = Vorgang.objects.order_by('-erstellt_am').first()
        if letzter is not None:
            person = letzter.person
            adresse = sorted(alle_adressen(person))[0] if (
                person and alle_adressen(person)) else kandidaten[0][1]
            name = person.name if person else kandidaten[0][0].name
            pfad = self._schreibe(
                ziel, f'test_{marke}_92_antwort.eml',
                von=adresse, von_name=name, an=an,
                betreff=f'AW: [{letzter.nummer}] {letzter.betreff}',
                text=f'Hallo,\n\nvielen Dank für die Rückmeldung. Gibt es '
                     f'zwischenzeitlich einen Termin?\n\nViele Grüße\n{name}',
                message_id=f'<test-{marke}-92@beispiel.local>',
                in_reply_to=letzter.mail_referenz or None,
            )
            erzeugt.append((pfad.name, adresse,
                            f'Thread-Zuordnung zu {letzter.nummer} (erwartet)'))
        else:
            self.stdout.write(self.style.WARNING(
                'Kein bestehender Vorgang vorhanden — die Antwortmail zum '
                'Testen der Thread-Zuordnung wurde uebersprungen. Nach dem '
                'ersten Scan dieses Kommando einfach erneut aufrufen.'))

        self.stdout.write(self.style.SUCCESS(
            f'\n{len(erzeugt)} Testmail(s) in {ziel} erzeugt:\n'))
        for name, adresse, erwartet in erzeugt:
            self.stdout.write(f'  {name:<34}{adresse:<38}{erwartet}')
        self.stdout.write(
            '\nNaechster Schritt: python manage.py mail_scan --ordner '
            f'{ziel}')
