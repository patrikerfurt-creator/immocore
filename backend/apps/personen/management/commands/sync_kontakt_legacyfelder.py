"""Zieht die Legacy-Felder ``Person.email``/``Person.telefon`` nach.

Bis zur Model-Aenderung schrieb das Bearbeitungsformular nur die
JSON-Listen ``emails``/``telefonnummern``; das Legacy-Feld behielt den
Import-Wert. Neue Speichervorgaenge halten beides synchron
(``Person._synchronisiere_legacyfelder``) — dieser Befehl korrigiert den
Bestand einmalig.

Beispiele:
    python manage.py sync_kontakt_legacyfelder --dry-run
    python manage.py sync_kontakt_legacyfelder
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.personen.models import Person, erster_listenwert


class Command(BaseCommand):
    help = 'Synchronisiert Person.email/telefon mit dem ersten Eintrag der JSON-Listen.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Nur anzeigen, was geaendert wuerde — nichts speichern.',
        )

    def handle(self, *args, **optionen):
        trocken = optionen['dry_run']
        geaendert = []

        for person in Person.objects.all().order_by('personennummer'):
            neu_mail = erster_listenwert(person.emails, ('adresse', 'email', 'wert'))
            neu_tel = erster_listenwert(person.telefonnummern, ('nummer', 'telefon', 'wert'))

            felder = []
            if neu_mail and neu_mail.lower() != (person.email or '').strip().lower():
                geaendert.append(
                    (person.personennummer, 'email', person.email, neu_mail)
                )
                felder.append('email')
            if neu_tel and neu_tel != (person.telefon or '').strip():
                geaendert.append(
                    (person.personennummer, 'telefon', person.telefon, neu_tel)
                )
                felder.append('telefon')

            if felder and not trocken:
                # save() spiegelt die Werte selbst; update_fields haelt den
                # Schreibvorgang eng.
                with transaction.atomic():
                    person.save(update_fields=felder)

        for nummer, feld, alt, neu in geaendert:
            self.stdout.write(f'{nummer}: {feld}  {alt!r} -> {neu!r}')

        anzahl = len(geaendert)
        if trocken:
            self.stdout.write(self.style.WARNING(
                f'{anzahl} Feld(er) waeren zu aktualisieren (Probelauf, nichts gespeichert).'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(f'{anzahl} Feld(er) aktualisiert.'))
