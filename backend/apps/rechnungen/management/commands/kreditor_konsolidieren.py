"""
Management-Command: kreditor_konsolidieren

Führt mehrere versehentlich doppelt angelegte Kreditoren zu einem
kanonischen Kreditor zusammen.

Problem: Die automatische Kreditor-Erkennung (services.kreditor_matching)
matcht über IBAN, exakten normalisierten Namen und Fuzzy-Name (Schwelle
0,75). Fehlt die IBAN und weichen die Namensvarianten stark ab
(„Gartenbau Scherer" / „Gartenbau Scherer und Team" / „Scherer, Uwe"),
legt die Verarbeitung denselben Lieferanten mehrfach neu an.

Lösung:
  - Ziel-Kreditor (kanonisch) behalten.
  - Alle FK-Referenzen der Quell-Kreditoren automatisch auf das Ziel
    umhängen (Rechnung, KreditorOP, Buchung, RechnungsMatchRegel,
    KreditorRegel, Bankverbindungen, WKZ-Vorlagen, Handwerker-FKs …).
  - Unique-Kollisionen vorab auflösen (RechnungsMatchRegel, KreditorRegel,
    ObjektHandwerker, IBANs).
  - IBANs der Quellen als Zweit-Bankverbindung ans Ziel übernehmen, damit
    künftige Rechnungen von dieser IBAN sicher gematcht werden.
  - Quell-Kreditoren deaktivieren (Standard) oder löschen (--loeschen).

Aufruf:
  python manage.py kreditor_konsolidieren --ziel 70073 --quelle 70043 70101 --dry-run
  python manage.py kreditor_konsolidieren --ziel 70073 --quelle 70043 70101
  python manage.py kreditor_konsolidieren --ziel 70073 --quelle 70043 70101 --loeschen
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


def _get_kreditor_fk_felder():
    """Alle (Model, FK-Feldname), die direkt auf rechnungen.Kreditor zeigen.

    Reverse-Relations und FKs auf gleichnamige Felder anderer Modelle
    (z. B. BankMatchRegel.kreditor → personen.Person) werden korrekt
    ausgefiltert, weil remote_field.model streng auf Kreditor geprüft wird.
    """
    from django.apps import apps
    from apps.rechnungen.models import Kreditor
    felder = []
    for model in apps.get_models():
        for field in model._meta.get_fields():
            if (
                hasattr(field, 'column')
                and not field.many_to_many  # M2M nicht per .update() umhängbar;
                                            # die through-Tabelle (ObjektHandwerker)
                                            # ist als eigener FK ohnehin abgedeckt.
                and hasattr(field, 'remote_field')
                and field.remote_field is not None
                and getattr(field.remote_field, 'model', None) is Kreditor
            ):
                felder.append((model, field.name))
    return felder


class Command(BaseCommand):
    help = 'Führt doppelt angelegte Kreditoren zu einem kanonischen Kreditor zusammen'

    def add_arguments(self, parser):
        parser.add_argument('--ziel', required=True,
                            help='Kreditorennummer des kanonischen Ziels, z. B. 70073')
        parser.add_argument('--quelle', required=True, nargs='+',
                            help='Eine oder mehrere Quell-Kreditorennummern, z. B. 70043 70101')
        parser.add_argument('--dry-run', action='store_true',
                            help='Nur anzeigen, nichts ändern')
        parser.add_argument('--loeschen', action='store_true',
                            help='Quell-Kreditoren löschen statt nur deaktivieren')

    def handle(self, *args, **options):
        from apps.rechnungen.models import Kreditor, KreditorBankverbindung

        ziel_nr = options['ziel']
        quell_nrs = options['quelle']
        dry_run = options['dry_run']
        loeschen = options['loeschen']

        if ziel_nr in quell_nrs:
            raise CommandError('Ziel darf nicht gleichzeitig Quelle sein.')

        try:
            ziel = Kreditor.objects.get(kreditorennummer=ziel_nr)
        except Kreditor.DoesNotExist:
            raise CommandError(f'Ziel-Kreditor {ziel_nr!r} nicht gefunden.')

        quellen = []
        for nr in quell_nrs:
            try:
                quellen.append(Kreditor.objects.get(kreditorennummer=nr))
            except Kreditor.DoesNotExist:
                raise CommandError(f'Quell-Kreditor {nr!r} nicht gefunden.')

        self.stdout.write(f'Ziel : {ziel.kreditorennummer}  {ziel.name!r}  iban={ziel.iban!r}')
        for q in quellen:
            self.stdout.write(f'Quelle: {q.kreditorennummer}  {q.name!r}  iban={q.iban!r}')
        self.stdout.write('')

        fk_felder = _get_kreditor_fk_felder()
        self.stdout.write(f'FK-Felder auf Kreditor: {len(fk_felder)}')
        for model, feld in fk_felder:
            self.stdout.write(f'  {model.__name__}.{feld}')
        self.stdout.write('')

        with transaction.atomic():
            umgehaengt = 0
            kollisionen = 0
            ibans_uebernommen = 0

            for q in quellen:
                self.stdout.write(f'--- Quelle {q.kreditorennummer} {q.name!r} ---')

                # 1) Unique-Kollisionen VOR dem generischen Umhängen auflösen.
                kollisionen += self._loese_matchregel_kollisionen(q, ziel, dry_run)
                kollisionen += self._loese_kreditorregel_kollisionen(q, ziel, dry_run)
                kollisionen += self._loese_handwerker_kollisionen(q, ziel, dry_run)

                # 2) Haupt-IBAN der Quelle als Bankverbindung ans Ziel übernehmen.
                if q.iban:
                    ibans_uebernommen += self._uebernehme_iban(
                        q, ziel, KreditorBankverbindung, dry_run)

                # 3) Quell-Bankverbindungen, deren IBAN das Ziel schon kennt, entfernen
                #    (iban ist unique → generisches Umhängen würde sonst scheitern).
                kollisionen += self._loese_bankverbindung_kollisionen(q, ziel, dry_run)

                # 4) Generisch alle verbliebenen FK-Referenzen umhängen.
                for model, feld in fk_felder:
                    qs = model.objects.filter(**{feld: q.id})
                    n = qs.count()
                    if not n:
                        continue
                    if not dry_run:
                        qs.update(**{feld: ziel})
                    umgehaengt += n
                    self.stdout.write(
                        f'  {model.__name__}.{feld}: {n} Zeile(n) → {ziel.kreditorennummer}')

                # 5) Quelle deaktivieren oder löschen.
                if dry_run:
                    aktion = 'LÖSCHEN' if loeschen else 'DEAKTIVIEREN'
                    self.stdout.write(f'  würde Quelle {q.kreditorennummer} {aktion}')
                elif loeschen:
                    q.delete()
                    self.stdout.write(f'  Quelle {q.kreditorennummer} gelöscht')
                else:
                    q.aktiv = False
                    q.save(update_fields=['aktiv'])
                    self.stdout.write(f'  Quelle {q.kreditorennummer} deaktiviert')
                self.stdout.write('')

            if dry_run:
                self.stdout.write(self.style.WARNING(
                    f'DRY-RUN: nichts geändert. Würde {umgehaengt} FK-Referenzen umhängen, '
                    f'{kollisionen} Kollision(en) auflösen, {ibans_uebernommen} IBAN(s) übernehmen.'))
                transaction.set_rollback(True)
            else:
                self.stdout.write(self.style.SUCCESS(
                    f'Fertig: {umgehaengt} FK-Referenzen umgehängt, '
                    f'{kollisionen} Kollision(en) aufgelöst, {ibans_uebernommen} IBAN(s) übernommen, '
                    f'{len(quellen)} Quell-Kreditor(en) {"gelöscht" if loeschen else "deaktiviert"}.'))

    # ------------------------------------------------------------------ Helfer

    def _loese_matchregel_kollisionen(self, quelle, ziel, dry_run):
        """Aktive Quell-Match-Regeln, die mit einer aktiven Ziel-Regel auf
        (objekt, leistungstext_hash) kollidieren, auf 'veraltet' setzen.
        Der UniqueConstraint greift nur für status='aktiv'."""
        from apps.rechnungen.models import RechnungsMatchRegel
        n = 0
        ziel_keys = set(
            RechnungsMatchRegel.objects
            .filter(kreditor=ziel, status='aktiv')
            .values_list('objekt_id', 'leistungstext_hash')
        )
        for regel in RechnungsMatchRegel.objects.filter(kreditor=quelle, status='aktiv'):
            if (regel.objekt_id, regel.leistungstext_hash) in ziel_keys:
                n += 1
                self.stdout.write(
                    f'  Kollision RechnungsMatchRegel {regel.id} → status=veraltet')
                if not dry_run:
                    regel.status = 'veraltet'
                    regel.save(update_fields=['status'])
        return n

    def _loese_kreditorregel_kollisionen(self, quelle, ziel, dry_run):
        """KreditorRegel: unique (kreditor, kundennummer). Kollidierende
        Quell-Regeln löschen (Treffer gehen dabei verloren — selten)."""
        from apps.rechnungen.models import KreditorRegel
        n = 0
        ziel_kundennrn = set(
            KreditorRegel.objects.filter(kreditor=ziel)
            .values_list('kundennummer', flat=True)
        )
        for regel in KreditorRegel.objects.filter(kreditor=quelle):
            if regel.kundennummer in ziel_kundennrn:
                n += 1
                self.stdout.write(
                    f'  Kollision KreditorRegel (kundennr={regel.kundennummer!r}) → gelöscht')
                if not dry_run:
                    regel.delete()
        return n

    def _loese_handwerker_kollisionen(self, quelle, ziel, dry_run):
        """ObjektHandwerker: unique (objekt, kreditor). Kollidierende
        Quell-Zuordnungen löschen."""
        try:
            from apps.handwerker.models import ObjektHandwerker
        except Exception:
            return 0
        n = 0
        ziel_objekte = set(
            ObjektHandwerker.objects.filter(kreditor=ziel)
            .values_list('objekt_id', flat=True)
        )
        for oh in ObjektHandwerker.objects.filter(kreditor=quelle):
            if oh.objekt_id in ziel_objekte:
                n += 1
                self.stdout.write(
                    f'  Kollision ObjektHandwerker (objekt={oh.objekt_id}) → gelöscht')
                if not dry_run:
                    oh.delete()
        return n

    def _loese_bankverbindung_kollisionen(self, quelle, ziel, dry_run):
        """KreditorBankverbindung.iban ist unique. Quell-Bankverbindungen,
        deren IBAN das Ziel (Haupt-IBAN oder Zweitkonto) schon kennt, löschen."""
        from apps.rechnungen.models import KreditorBankverbindung
        n = 0
        bekannt = set(ziel.bankverbindungen.values_list('iban', flat=True))
        if ziel.iban:
            bekannt.add(ziel.iban)
        for bv in KreditorBankverbindung.objects.filter(kreditor=quelle):
            if bv.iban in bekannt:
                n += 1
                self.stdout.write(
                    f'  Kollision Bankverbindung {bv.iban} (Ziel kennt sie) → gelöscht')
                if not dry_run:
                    bv.delete()
        return n

    def _uebernehme_iban(self, quelle, ziel, KreditorBankverbindung, dry_run):
        """Haupt-IBAN der Quelle beim Ziel sichern, damit künftige Rechnungen
        von dieser IBAN gematcht werden. Wird Haupt-IBAN, falls das Ziel noch
        keine hat, sonst Zweit-Bankverbindung."""
        iban = quelle.iban
        bekannt = set(ziel.bankverbindungen.values_list('iban', flat=True))
        if ziel.iban:
            bekannt.add(ziel.iban)
        if iban in bekannt:
            return 0
        if not ziel.iban:
            self.stdout.write(f'  IBAN {iban} → Ziel.Haupt-IBAN')
            if not dry_run:
                # Quell-IBAN freiräumen, damit der unique-Constraint nicht bricht.
                quelle.iban = None
                quelle.save(update_fields=['iban'])
                ziel.iban = iban
                ziel.bic = ziel.bic or quelle.bic
                ziel.save(update_fields=['iban', 'bic'])
        else:
            self.stdout.write(f'  IBAN {iban} → Ziel.Zweit-Bankverbindung')
            if not dry_run:
                quelle.iban = None
                quelle.save(update_fields=['iban'])
                KreditorBankverbindung.objects.create(
                    kreditor=ziel, iban=iban, bic=quelle.bic or '',
                    bemerkung=f'Übernommen aus zusammengeführtem Kreditor {quelle.kreditorennummer}',
                )
        return 1
