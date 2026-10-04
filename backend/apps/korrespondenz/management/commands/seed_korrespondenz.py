"""Seed: Standard-Briefbogen (mit Logo) und Mustervorlagen als Entwurf.

Idempotent und rein additiv - siehe ``services/seed_service.py``. Aufruf::

    python manage.py seed_korrespondenz [--user <username>]

Das Logo-``Dokument`` braucht einen Uploader (``hochgeladen_von`` ist Pflicht); Vorgabe ist
der erste aktive Superuser.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.korrespondenz.services import seed_service


def _finde_user(username):
    User = get_user_model()
    if username:
        user = User.objects.filter(**{User.USERNAME_FIELD: username}).first()
        if user is None:
            raise CommandError(f'Benutzer "{username}" nicht gefunden.')
        return user
    user = User.objects.filter(is_superuser=True, is_active=True).order_by('date_joined', 'pk').first()
    if user is None:
        raise CommandError('Kein aktiver Superuser vorhanden - bitte --user angeben.')
    return user


class Command(BaseCommand):
    help = 'Legt Standard-Briefbogen und Mustervorlagen (Status entwurf) idempotent an.'

    def add_arguments(self, parser):
        parser.add_argument('--user', help='Benutzername des Uploaders für das Logo-Dokument.')

    def handle(self, *args, **options):
        ergebnis = seed_service.seede(_finde_user(options['user']))
        if ergebnis.briefbogen_angelegt:
            self.stdout.write('Briefbogen: angelegt (Standard, mit Logo).')
        else:
            self.stdout.write(f'Briefbogen: vorhanden ("{ergebnis.briefbogen_vorhanden}"), unverändert.')
        for code in ergebnis.vorlagen_angelegt:
            self.stdout.write(f'Vorlage {code}: angelegt (Version 1, entwurf).')
        for code in ergebnis.vorlagen_vorhanden:
            self.stdout.write(f'Vorlage {code}: vorhanden, unverändert.')
