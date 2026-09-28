"""
Ordnet noch nicht einsortierte Dokumente einem Aktenregister zu.

    python manage.py register_zuordnen                  # zeigt nur Vorschlaege
    python manage.py register_zuordnen --ja             # setzt sie
    python manage.py register_zuordnen --nur-mails --ja

Ohne ``--ja`` wird nichts geaendert — der Lauf zeigt, was passieren wuerde.
Das ist hier wichtiger als sonst: Ein falsch abgelegtes Dokument findet
niemand wieder, ein unsortiertes steht unter "Ohne Register" und faellt auf.

Nur Dokumente OHNE Register werden betrachtet. Eine bestehende Zuordnung
wird nie ueberschrieben — wer von Hand einsortiert hat, hat recht.
"""
from django.core.management.base import BaseCommand

from apps.dokumente.models import Aktenregister, Dokument
from apps.dokumente.services import akten_service, register_vorschlag_service

TRENNER = '-' * 78


def _kuerze(text, laenge):
    text = (text or '').replace('\n', ' ').strip()
    return text if len(text) <= laenge else text[:laenge - 1] + '…'


class Command(BaseCommand):
    help = 'Schlaegt fuer nicht einsortierte Dokumente ein Aktenregister vor.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--ja', action='store_true',
            help='Vorschlaege tatsaechlich setzen. Ohne dieses Flag wird nur '
                 'angezeigt, was passieren wuerde.',
        )
        parser.add_argument(
            '--nur-mails', action='store_true',
            help='Nur Dokumente aus dem Mail-Import.',
        )
        parser.add_argument(
            '--objekt', help='Auf ein Objekt beschraenken (UUID).',
        )
        parser.add_argument(
            '--limit', type=int,
            help='Hoechstens so viele Dokumente verarbeiten (spart '
                 'API-Aufrufe beim Ausprobieren).',
        )

    def _objekt_von(self, dokument):
        """Das Objekt, in dessen Akte das Dokument haengt.

        Ein Dokument hat genau einen Kontext-FK; das Objekt steckt je nach
        Fall direkt darin oder eine Ebene tiefer.
        """
        if dokument.objekt_id:
            return dokument.objekt
        if dokument.einheit_id:
            return dokument.einheit.objekt
        if dokument.vorgang_id:
            vorgang = dokument.vorgang
            if vorgang.objekt_id:
                return vorgang.objekt
            if vorgang.einheit_id:
                return vorgang.einheit.objekt
        return None

    def handle(self, *args, **optionen):
        qs = (Dokument.objects
              .filter(register__isnull=True)
              .select_related('objekt', 'einheit', 'vorgang', 'vorgang__objekt',
                              'vorgang__einheit', 'mail_import')
              .order_by('hochgeladen_am'))
        if optionen['nur_mails']:
            qs = qs.filter(mail_import__isnull=False)
        # --objekt wird weiter unten je Dokument geprueft (ueber
        # _objekt_von), weil das Objekt je nach Kontext-FK eine Ebene tiefer
        # steckt und sich nicht in einem Queryset-Filter ausdruecken laesst.
        if optionen['limit']:
            qs = qs[:optionen['limit']]

        dokumente = list(qs)
        if not dokumente:
            self.stdout.write('Nichts zuzuordnen — alle Dokumente haben ein Register.')
            return

        modus = 'SETZEN' if optionen['ja'] else 'TROCKENLAUF (nichts wird geaendert)'
        self.stdout.write(f'{len(dokumente)} Dokument(e) ohne Register  [{modus}]')
        self.stdout.write(TRENNER)

        # Registerliste je Objekt nur einmal holen.
        register_cache: dict = {}
        zaehler = {'gesetzt': 0, 'unsicher': 0, 'kein_objekt': 0, 'fehler': 0}

        for dokument in dokumente:
            objekt = self._objekt_von(dokument)
            if optionen['objekt'] and (objekt is None
                                       or str(objekt.id) != optionen['objekt']):
                continue
            if objekt is None:
                # Ohne Objekt ist nicht bestimmbar, welche Register gelten —
                # etwa bei einer noch nicht zugeordneten Posteingangs-Mail.
                zaehler['kein_objekt'] += 1
                self.stdout.write(self.style.WARNING(
                    f'  {_kuerze(dokument.anzeigename, 58):<58} kein Objekt — '
                    f'zuerst im Posteingang zuordnen'))
                continue

            if objekt.id not in register_cache:
                register_cache[objekt.id] = list(akten_service.register_einer_akte(
                    Aktenregister.AKTENART_HAUS, objekt=objekt))

            vorschlag = register_vorschlag_service.schlage_register_vor(
                dokument, register_cache[objekt.id])

            konfidenz = (f"{vorschlag['konfidenz']:.2f}"
                         if vorschlag['konfidenz'] is not None else '—')
            name = _kuerze(dokument.anzeigename, 52)

            if vorschlag['fehler']:
                zaehler['fehler'] += 1
                self.stdout.write(self.style.ERROR(
                    f'  {name:<52} FEHLER  {vorschlag["fehler"][:60]}'))
                continue

            if vorschlag['register'] is None:
                zaehler['unsicher'] += 1
                self.stdout.write(
                    f'  {name:<52} offen   {konfidenz:>5}  '
                    f'{_kuerze(vorschlag["begruendung"], 40)}')
                continue

            register = vorschlag['register']
            zaehler['gesetzt'] += 1
            if optionen['ja']:
                dokument.register = register
                dokument.save(update_fields=['register'])
            self.stdout.write(self.style.SUCCESS(
                f'  {name:<52} {register.code:<6} {konfidenz:>5}  '
                f'{_kuerze(vorschlag["begruendung"], 40)}'))

        self.stdout.write(TRENNER)
        self.stdout.write(
            f'{zaehler["gesetzt"]} zugeordnet, {zaehler["unsicher"]} offen '
            f'(zu unsicher), {zaehler["kein_objekt"]} ohne Objekt, '
            f'{zaehler["fehler"]} Fehler')
        if not optionen['ja'] and zaehler['gesetzt']:
            self.stdout.write(self.style.WARNING(
                'Nichts geaendert — zum Setzen --ja anhaengen.'))
