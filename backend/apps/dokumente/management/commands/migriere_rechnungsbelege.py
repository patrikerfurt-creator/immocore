"""
Management-Command: Migriert Rechnungs-Altbelege (Rechnung.pfad) in das
DMS-Dokument-Model (Rechnung.beleg_dokument) — Phase C der Spec
Beleg↔Dokument-Kopplung (E1-Beschluss, Option c).

Modi (genau einer, Default = Neuanlage):
  (Default)          Legt je unverknüpfter Rechnung mit Alt-Pfad genau ein
                      Dokument an, verknüpft es (beleg_dokument) und vergibt
                      die Belegnummer über den bestehenden BelegnummerZaehler.
  --sperren           Setzt die GoBD-Sperre (revisionssicher) nachträglich auf
                      migrierte Dokumente bereits gebuchter Rechnungen —
                      rückdatiert auf den OP-Buchungszeitpunkt.
  --rueckabwicklung   Entfernt ungesperrte migrierte Dokumente + Kopplung
                      wieder (z. B. nach fehlgeschlagenem Testlauf).

Vor jedem Modus läuft ein rein lesender Pre-Flight-Check, der bei
Inkonsistenzen hart mit CommandError abbricht (siehe _preflight()).

Beispiele:
    python manage.py migriere_rechnungsbelege --dry-run
    python manage.py migriere_rechnungsbelege --limit 50
    python manage.py migriere_rechnungsbelege
    python manage.py migriere_rechnungsbelege --sperren
    python manage.py migriere_rechnungsbelege --sperren --dry-run
    python manage.py migriere_rechnungsbelege --rueckabwicklung --dry-run
"""
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count, Max
from django.db.models.functions import Length

from apps.dokumente.models import BelegnummerZaehler, Dokument
from apps.dokumente.services.beleg_service import koppel_rechnungsbeleg, rechnungen_root
from apps.rechnungen.models import Rechnung, Verarbeitungslog

User = get_user_model()


class Command(BaseCommand):
    help = "Migriert Rechnung.pfad-Altbelege in Dokument (Phase C, Beleg↔Dokument-Kopplung)."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Nur Vorschau, keine Änderungen.')
        parser.add_argument('--limit', type=int, default=None,
                             help='Nur die ersten N Rechnungen bearbeiten (Neuanlage-Modus).')
        parser.add_argument('--sperren', action='store_true',
                             help='Statt Neuanlage: GoBD-Sperre rückwirkend auf bereits gekoppelte Belege setzen.')
        parser.add_argument('--rueckabwicklung', action='store_true',
                             help='Statt Neuanlage: ungesperrte migrierte Dokumente + Kopplung wieder entfernen.')
        parser.add_argument('--erlaube-fehlende', action='store_true',
                             help='Dokument auch anlegen, wenn die physische Datei nicht existiert.')
        parser.add_argument('--user', default=None,
                             help='Username des Systemnutzers für hochgeladen_von (Neuanlage-Modus).')
        parser.add_argument('--erlaube-vorhandenen-zaehlerstand', action='store_true',
                             help='Pre-Flight-Abbruch bei BelegnummerZaehler.letzter_zaehler != 0 übergehen.')

    def handle(self, *args, **opts):
        if opts['sperren'] and opts['rueckabwicklung']:
            raise CommandError("--sperren und --rueckabwicklung schließen sich gegenseitig aus.")

        neuanlage_modus = not (opts['sperren'] or opts['rueckabwicklung'])
        root = rechnungen_root()
        sys_user = self._preflight(opts, root, neuanlage_modus)

        if opts['rueckabwicklung']:
            self._rueckabwicklung(opts)
        elif opts['sperren']:
            self._sperren(opts)
        else:
            self._neuanlage(opts, root, sys_user)

    # ── Pre-Flight ───────────────────────────────────────────────────────
    def _preflight(self, opts, root: Path, neuanlage_modus: bool):
        """Rein lesende Konsistenzprüfungen. Bricht bei Verstößen mit CommandError ab."""
        # 1) Doppelte pfad-Werte
        dupes = list(
            Rechnung.objects.exclude(pfad='')
            .values('pfad').annotate(n=Count('id')).filter(n__gt=1)
            .values_list('pfad', flat=True)
        )
        if dupes:
            raise CommandError(
                "Pre-Flight: doppelte Rechnung.pfad-Werte gefunden:\n" + "\n".join(dupes)
            )

        # 2) pfad länger als FileField.max_length (1000)
        max_len = Rechnung.objects.exclude(pfad='').aggregate(m=Max(Length('pfad')))['m']
        if max_len and max_len > 1000:
            raise CommandError(
                f"Pre-Flight: mindestens ein Rechnung.pfad ist länger als 1000 Zeichen (max={max_len})."
            )

        # 3) Rechnungen mit Pfad außerhalb der Rechnungen-Wurzel
        root_posix = root.as_posix().rstrip('/') + '/'
        fremde = [
            r.pfad for r in Rechnung.objects.exclude(pfad='').only('id', 'pfad')
            if not r.pfad.replace('\\', '/').startswith(root_posix)
        ]
        if fremde:
            raise CommandError(
                f"Pre-Flight: Rechnungen mit Pfad außerhalb der Wurzel '{root}' gefunden:\n"
                + "\n".join(fremde)
            )

        # 4) Zählerstand
        zaehler = BelegnummerZaehler.objects.filter(pk=1).first()
        letzter = zaehler.letzter_zaehler if zaehler else 0
        self.stdout.write(f"BelegnummerZaehler.letzter_zaehler = {letzter}")
        if letzter != 0 and neuanlage_modus and not opts['erlaube_vorhandenen_zaehlerstand']:
            raise CommandError(
                f"Pre-Flight: BelegnummerZaehler.letzter_zaehler ist bereits {letzter} (≠ 0). "
                "Neuanlage-Modus erwartet einen jungfräulichen Zähler — "
                "mit --erlaube-vorhandenen-zaehlerstand übergehen."
            )

        # 5) User-Auflösung (nur Neuanlage-Modus)
        if not neuanlage_modus:
            return None
        return self._resolve_user(opts)

    def _resolve_user(self, opts):
        if opts['user']:
            try:
                return User.objects.get(username=opts['user'])
            except User.DoesNotExist:
                raise CommandError(f"Pre-Flight: Benutzer '{opts['user']}' existiert nicht.")
        user = User.objects.filter(username='immocore-autopilot').first()
        if user:
            return user
        user = User.objects.filter(is_superuser=True).order_by('pk').first()
        if user:
            return user
        raise CommandError(
            "Pre-Flight: kein Systembenutzer gefunden (weder 'immocore-autopilot' noch ein Superuser). "
            "Bitte --user USERNAME angeben."
        )

    # ── Neuanlage ────────────────────────────────────────────────────────
    def _neuanlage(self, opts, root: Path, sys_user):
        qs = Rechnung.objects.filter(beleg_dokument__isnull=True).exclude(pfad='').order_by('erstellt_am', 'id')
        if opts['limit']:
            qs = qs[:opts['limit']]

        angelegt = 0
        ohne_objekt = 0
        skips = {}

        for r in qs:
            try:
                rel = Path(r.pfad).relative_to(root).as_posix()
            except ValueError:
                # Defensiv — Pre-Flight (Schritt 3) fängt fremde Wurzeln eigentlich schon ab.
                skips['wurzel'] = skips.get('wurzel', 0) + 1
                continue

            existiert = (root / rel).exists()
            if not existiert and not opts['erlaube_fehlende']:
                skips['datei_fehlt'] = skips.get('datei_fehlt', 0) + 1
                continue

            if opts['dry_run']:
                angelegt += 1
                if not r.objekt_id:
                    ohne_objekt += 1
                continue

            with transaction.atomic():
                # Anlage + Kopplung: gemeinsame Logik mit der Pipeline (Phase A)
                dok = koppel_rechnungsbeleg(r, hochgeladen_von=sys_user)
                # auto_now_add rückdatieren: Ablage soll den historischen Zeitpunkt tragen
                Dokument.objects.filter(pk=dok.pk).update(
                    abgelegt_am=r.erstellt_am, hochgeladen_am=r.erstellt_am,
                )
                Verarbeitungslog.objects.create(
                    rechnung=r, aktion='Beleg-Dokument migriert',
                    status=r.status, details=dok.beleg_nummer,
                )

            angelegt += 1
            if not r.objekt_id:
                ohne_objekt += 1

        naechster_zaehlerstand = (BelegnummerZaehler.objects.filter(pk=1).first() or BelegnummerZaehler()).letzter_zaehler + 1

        praefix = '[DRY-RUN] ' if opts['dry_run'] else ''
        self.stdout.write(self.style.SUCCESS(
            f"\n{praefix}{angelegt} Dokument(e) {'wären angelegt worden' if opts['dry_run'] else 'angelegt'}."
        ))
        for grund, n in sorted(skips.items()):
            self.stdout.write(f"  übersprungen ({grund}): {n}")
        self.stdout.write(f"  davon ohne Objekt: {ohne_objekt}")
        self.stdout.write(f"  nächster Zählerstand: {naechster_zaehlerstand}")

    # ── Sperren ──────────────────────────────────────────────────────────
    def _sperren(self, opts):
        qs = Rechnung.objects.filter(
            beleg_dokument__isnull=False,
            status__in=['freigegeben', 'teilbezahlt', 'bezahlt'],
        ).select_related('beleg_dokument', 'op_buchung')

        gesperrt = 0
        for r in qs:
            if r.beleg_dokument.revisionssicher:
                continue
            ts = (r.op_buchung.erstellt_am if r.op_buchung_id else None) or r.erstellt_am
            if opts['dry_run']:
                gesperrt += 1
                continue
            # BEWUSST .update() statt sperre_beleg_revisionssicher(): wir setzen den
            # historischen OP-Buchungszeitpunkt, nicht timezone.now(). Der Service
            # bleibt der einzige Weg für den Laufzeitpfad (rechnung_freigeben()).
            Dokument.objects.filter(pk=r.beleg_dokument_id).update(
                revisionssicher=True, revisionssicher_seit=ts,
            )
            gesperrt += 1

        praefix = '[DRY-RUN] ' if opts['dry_run'] else ''
        self.stdout.write(self.style.SUCCESS(
            f"\n{praefix}{gesperrt} Beleg(e) {'wären gesperrt worden' if opts['dry_run'] else 'gesperrt'}."
        ))

    # ── Rückabwicklung ───────────────────────────────────────────────────
    def _rueckabwicklung(self, opts):
        ids = list(
            Dokument.objects.filter(
                dokument_typ='beleg', ablage_wurzel='rechnungen',
                revisionssicher=False, rechnung__isnull=False,
            ).values_list('pk', flat=True)
        )
        gesperrt_unangetastet = Dokument.objects.filter(
            dokument_typ='beleg', ablage_wurzel='rechnungen', revisionssicher=True,
        ).count()

        praefix = '[DRY-RUN] ' if opts['dry_run'] else ''
        if opts['dry_run']:
            self.stdout.write(self.style.WARNING(
                f"\n{praefix}{len(ids)} Dokument(e) würden entfernt (Kopplung + Datensatz)."
            ))
            self.stdout.write(f"  revisionssicher (unangetastet): {gesperrt_unangetastet}")
            return

        with transaction.atomic():
            Rechnung.objects.filter(beleg_dokument_id__in=ids).update(beleg_dokument=None)
            # Zähler wird NICHT zurückgedreht — der Nummernkreis darf Lücken haben,
            # darf aber nie eine Nummer doppelt vergeben.
            Dokument.objects.filter(pk__in=ids).delete()

        self.stdout.write(self.style.SUCCESS(f"\n{len(ids)} Dokument(e) entfernt."))
        self.stdout.write(f"  revisionssicher (unangetastet): {gesperrt_unangetastet}")
