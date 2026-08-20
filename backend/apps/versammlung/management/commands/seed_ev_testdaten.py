"""
Legt eine vollständige Beispiel-EV für ein bestehendes WEG-Objekt an
(Spec v1.1 Phase A, Deliverable "Fixtures").

Bewusst kein Anlegen von Stammdaten: das Kommando setzt ein WEG-Objekt mit
aktiven Eigentumsverhältnissen voraus und arbeitet ausschließlich über die
Services — damit ist der Seed derselbe Pfad, den auch die API später nimmt.

    docker exec immocore_backend python3.11 manage.py seed_ev_testdaten
    docker exec immocore_backend python3.11 manage.py seed_ev_testdaten \
        --objekt 10003 --vs 030
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.objekte.models import Objekt
from apps.versammlung.models import Eigentuemerversammlung
from apps.versammlung.services import ev_service, stimmkraft_service, tagesordnung_service

ARBEITSNAME = 'EV Testdaten (Seed)'

TOPS = [
    {
        'titel': 'Bericht der Verwaltung',
        'erlaeuterung': 'Rückblick auf das abgelaufene Wirtschaftsjahr.',
        'beschlussvorlage': '',
        'abstimmungsmodus': 'kein_beschluss',
    },
    {
        'titel': 'Jahresabrechnung',
        'erlaeuterung': '',
        'beschlussvorlage': (
            'Die Jahresabrechnung wird in der vorgelegten Fassung beschlossen; '
            'die Abrechnungsspitzen werden zum Ersten des Folgemonats fällig.'
        ),
        'abstimmungsmodus': 'einfache_mehrheit',
    },
    {
        'titel': 'Wirtschaftsplan',
        'erlaeuterung': '',
        'beschlussvorlage': (
            'Der Wirtschaftsplan wird beschlossen; die daraus folgenden '
            'Hausgeldvorschüsse gelten ab dem Ersten des Folgemonats.'
        ),
        'abstimmungsmodus': 'einfache_mehrheit',
        'triggert_wirtschaftsplan': True,
    },
    {
        'titel': 'Erneuerung der Hauseingangstür',
        'erlaeuterung': 'Zwei Angebote liegen vor und sind als Anlage beigefügt.',
        'beschlussvorlage': (
            'Die Hauseingangstür wird gemäß Angebot vom 01.02. erneuert; die '
            'Kosten werden der Erhaltungsrücklage entnommen.'
        ),
        'abstimmungsmodus': 'qualifizierte_mehrheit',
        'mehrheit_schwelle': '66.67',
        'triggert_vorgang': True,
    },
]


class Command(BaseCommand):
    help = 'Legt eine Beispiel-Eigentümerversammlung mit Tagesordnung und Teilnehmern an.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--objekt', default=None,
            help='Objektnummer des WEG-Objekts. Ohne Angabe wird das erste '
                 'WEG-Objekt mit aktiven Eigentumsverhältnissen genommen.',
        )
        parser.add_argument(
            '--vs', default=None,
            help='Schlüssel des Stimm-Verteilerschlüssels, z.B. "030" (eine '
                 'Stimme je Einheit) oder "031" (nur Wohnungen). Ohne Angabe '
                 'gilt das Kopfprinzip (§ 25 Abs. 2 WEG).',
        )

    def _objekt_finden(self, objektnummer):
        qs = Objekt.objects.filter(objekt_typ='WEG', status='aktiv')
        if objektnummer:
            objekt = qs.filter(objektnummer=objektnummer).first()
            if objekt is None:
                raise CommandError(
                    f'Kein aktives WEG-Objekt mit Objektnummer "{objektnummer}".'
                )
            return objekt

        objekt = (
            qs.filter(einheiten__eigentumsverhaeltnisse__ende__isnull=True)
            .distinct().order_by('bezeichnung').first()
        )
        if objekt is None:
            raise CommandError(
                'Kein aktives WEG-Objekt mit aktiven Eigentumsverhältnissen '
                'gefunden — bitte zuerst Stammdaten anlegen oder --objekt setzen.'
            )
        return objekt

    @transaction.atomic
    def handle(self, *args, **options):
        user = get_user_model().objects.filter(is_superuser=True).order_by('id').first()
        if user is None:
            raise CommandError('Kein Superuser vorhanden — Seed braucht einen Urheber.')

        objekt = self._objekt_finden(options['objekt'])

        if Eigentuemerversammlung.objects.filter(objekt=objekt, arbeitsname=ARBEITSNAME).exists():
            self.stdout.write(self.style.WARNING(
                f'EV "{ARBEITSNAME}" existiert für {objekt.bezeichnung} bereits — '
                'nichts zu tun.'
            ))
            return

        stimmprinzip, vs = 'kopf', None
        if options['vs']:
            from apps.objekte.models import Verteilerschluessel

            vs = Verteilerschluessel.objects.filter(
                objekt=objekt, schluessel=options['vs'], aktiv=True,
            ).first()
            if vs is None:
                raise CommandError(
                    f'Objekt {objekt.objektnummer} hat keinen aktiven '
                    f'Verteilerschlüssel "{options["vs"]}".'
                )
            stimmprinzip = 'verteilerschluessel'

        ev = ev_service.erstelle_ev(
            objekt=objekt, erstellt_von=user, arbeitsname=ARBEITSNAME,
            stimmprinzip=stimmprinzip, stimm_verteilerschluessel=vs,
        )
        ev_service.aktualisiere_terminierung(
            ev, user,
            termin=timezone.now() + timedelta(days=42),
            ort='Gemeinschaftsraum im Erdgeschoss',
            raum_buchung_notizen='Raum ist reserviert, Bestuhlung für 30 Personen.',
        )

        for daten in TOPS:
            tagesordnung_service.top_anlegen(ev=ev, erstellt_von=user, **daten)

        try:
            stats = stimmkraft_service.ermittle_teilnehmer(ev, user)
        except ValidationError as fehler:
            # Zum Beispiel ein Verteilerschlüssel ohne gepflegte Werte oder
            # Einheiten ohne Eigentümer: der Grund muss sichtbar sein und
            # nicht als "Seed erfolgreich" durchgehen.
            raise CommandError(
                'Teilnehmer konnten nicht ermittelt werden: '
                + '; '.join(fehler.messages)
            )

        ev_service.markiere_task_erledigt(ev, 1, user)
        ev_service.markiere_task_erledigt(ev, 2, user)

        self.stdout.write(self.style.SUCCESS(
            f'EV "{ev.arbeitsname}" für {objekt.bezeichnung} angelegt:\n'
            f'  Termin:            {ev.termin:%d.%m.%Y %H:%M}\n'
            f'  Stimmprinzip:      {ev.get_stimmprinzip_display()}\n'
            f'  Tagesordnung:      {ev.tagesordnung.count()} TOP\n'
            f'  Teilnehmer:        {stats["teilnehmer"]}\n'
            f'  Gesamtstimmkraft:  {stats["gesamt_stimmkraft"]}\n'
            f'  Tasks erledigt:    1 und 2'
        ))
