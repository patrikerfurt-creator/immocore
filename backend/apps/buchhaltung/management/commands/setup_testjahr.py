"""
Management-Command: Testjahr für ein Objekt aufsetzen.

Legt für ein Objekt ein Wirtschaftsjahr an (inkl. kopiertem Kontenrahmen),
spiegelt die Hausgeld-Beträge eines Referenzjahres auf das Zieljahr, erzeugt
für jeden Monat einen committeten Sollstellungslauf und bucht optional zu
jedem Fälligkeitsdatum die volle Zahlung, sodass alle Personenkonten
ausgeglichen sind.

Gedacht als Test-/Demo-Werkzeug (z. B. um die Jahresabrechnung zu testen),
NICHT für den Produktivbetrieb.

Beispiel:
    python manage.py setup_testjahr --objekt 10001 --jahr 2025
    python manage.py setup_testjahr --objekt 10001 --jahr 2025 --dry-run
    python manage.py setup_testjahr --objekt 10001 --jahr 2025 --keine-zahlungen

Idempotent: Bereits vorhandene Bestandteile (WJ, Konten, Historie, committete
Läufe, ausgeglichene Sollstellungen) werden übersprungen.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.objekte.models import Objekt, Wirtschaftsjahr
from apps.konten.models import Konto
from apps.personen.models import EigentumsVerhaeltnis, HausgeldHistorie
from apps.buchhaltung.models import HausgeldSollstellung, HausgeldSollstellungslauf
from apps.buchhaltung.services import wirtschaftsjahr as wj_service
from apps.buchhaltung.services.sollstellungslauf_service import (
    erstelle_lauf_aus_vorschau,
    freigeben_lauf,
    commiten_lauf,
    pruefe_duplikat_lauf,
    _aktuelle_betraege,
)
from apps.buchhaltung.services.zahlungs_zuordnung_service import (
    verrechne_eingang_manuell,
)

User = get_user_model()


class Command(BaseCommand):
    help = "Legt für ein Objekt ein Testjahr mit Sollstellungen und Zahlungen an."

    def add_arguments(self, parser):
        parser.add_argument('--objekt', required=True, help='Objektnummer, z. B. 10001')
        parser.add_argument('--jahr', required=True, type=int, help='Zieljahr, z. B. 2025')
        parser.add_argument(
            '--referenzjahr', type=int, default=None,
            help='Jahr, dessen Hausgeld-Beträge/Konten gespiegelt werden '
                 '(Standard: nächstes vorhandenes WJ nach dem Zieljahr, sonst frühestes WJ).',
        )
        parser.add_argument('--dry-run', action='store_true', help='Nur Vorschau, keine Änderungen.')
        parser.add_argument('--keine-zahlungen', action='store_true',
                            help='Sollstellungen erzeugen, aber keine Zahlungen buchen.')
        parser.add_argument('--vertraege-nicht-aktivieren', action='store_true',
                            help='Vertragsbeginn NICHT ins Testjahr zurückdatieren '
                                 '(Standard: zurückdatieren, damit die Verträge im Testjahr aktiv sind).')

    # ------------------------------------------------------------------ #

    def handle(self, *args, **opts):
        objektnummer = opts['objekt']
        jahr = opts['jahr']
        dry_run = opts['dry_run']
        keine_zahlungen = opts['keine_zahlungen']
        vertraege_aktivieren = not opts['vertraege_nicht_aktivieren']

        try:
            objekt = Objekt.objects.get(objektnummer=objektnummer)
        except Objekt.DoesNotExist:
            raise CommandError(f"Objekt {objektnummer} nicht gefunden.")

        # Referenz-WJ bestimmen (Quelle für Konten + Hausgeld-Beträge)
        template = None
        if opts['referenzjahr']:
            template = Wirtschaftsjahr.objects.filter(objekt=objekt, jahr=opts['referenzjahr']).first()
            if template is None:
                raise CommandError(f"Referenzjahr {opts['referenzjahr']} für {objektnummer} nicht gefunden.")
        else:
            template = (
                Wirtschaftsjahr.objects.filter(objekt=objekt, jahr__gt=jahr).order_by('jahr').first()
                or Wirtschaftsjahr.objects.filter(objekt=objekt).order_by('jahr').first()
            )
        if template is None:
            raise CommandError(
                f"Für {objektnummer} existiert kein Wirtschaftsjahr als Vorlage. "
                f"Bitte zuerst ein WJ anlegen."
            )
        if template.jahr == jahr:
            raise CommandError("Referenzjahr und Zieljahr dürfen nicht identisch sein.")

        ersteller = User.objects.filter(is_superuser=True).order_by('pk').first() or User.objects.order_by('pk').first()
        if ersteller is None:
            raise CommandError("Kein Benutzer in der Datenbank — mindestens einer wird benötigt.")
        freigeber = User.objects.exclude(pk=ersteller.pk).filter(is_active=True).order_by('pk').first()

        evs = list(
            EigentumsVerhaeltnis.objects
            .filter(einheit__objekt=objekt)
            .select_related('einheit', 'person')
        )

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\nTestjahr {jahr} für Objekt {objektnummer} ({objekt.bezeichnung})"
        ))
        self.stdout.write(f"  Referenzjahr (Vorlage) : {template.jahr}")
        self.stdout.write(f"  Verträge               : {len(evs)}")
        self.stdout.write(f"  Ersteller / Freigeber  : {ersteller} / {freigeber or '(kein zweiter — Vier-Augen wird umgangen)'}")
        self.stdout.write(f"  Zahlungen buchen       : {'nein' if keine_zahlungen else 'ja (volle Tilgung zum Fälligkeitsdatum)'}")

        if dry_run:
            ref_stichtag = date(template.jahr, template.beginn_monat, 1)
            mit_betrag = sum(1 for ev in evs if _aktuelle_betraege(ev, ref_stichtag))
            self.stdout.write(self.style.WARNING(
                f"\n[DRY-RUN] Es würden angelegt werden:\n"
                f"  • WJ {jahr} (Status offen) + Kopie des Kontenrahmens {template.jahr}\n"
                f"  • Hausgeld-Historie {jahr} für {mit_betrag} von {len(evs)} Verträgen\n"
                f"  • bis zu 12 Sollstellungsläufe (Jan–Dez {jahr})\n"
                f"  • Zahlungen: {'keine' if keine_zahlungen else 'je Sollstellung eine volle Zahlung'}\n"
                f"Keine Änderungen geschrieben."
            ))
            return

        with transaction.atomic():
            wj_neu = self._wj_anlegen(objekt, jahr, template, ersteller)
            if vertraege_aktivieren:
                self._vertraege_aktivieren(evs, jahr)
            hist_neu = self._historie_spiegeln(evs, template, jahr, ersteller)
            laeufe, ss_gesamt = self._sollstellungslaeufe(objekt, jahr, wj_neu, ersteller, freigeber)
            self._splits_auf_wj_umhaengen(objekt, jahr, wj_neu)
            zahlungen = 0
            if not keine_zahlungen:
                zahlungen = self._zahlungen_buchen(objekt, jahr, wj_neu, ersteller)

        self._zusammenfassung(objekt, jahr, wj_neu, hist_neu, laeufe, ss_gesamt, zahlungen)

    # ------------------------------------------------------------------ #

    def _wj_anlegen(self, objekt, jahr, template, user):
        wj_neu, created = Wirtschaftsjahr.objects.get_or_create(
            objekt=objekt, jahr=jahr,
            defaults=dict(beginn_monat=template.beginn_monat, status='offen', eroeffnet_von=user),
        )
        k = wj_service._kopiere_konten(template, wj_neu)
        vs = wj_service._kopiere_vs_zuordnungen(template, wj_neu)
        vb = wj_service._kopiere_einheit_verbrauch(template, wj_neu)
        self.stdout.write(
            f"  WJ {jahr}: {'angelegt' if created else 'bereits vorhanden'} "
            f"(Konten kopiert: {k}, VS: {vs}, Verbrauch: {vb})"
        )
        return wj_neu

    def _vertraege_aktivieren(self, evs, jahr):
        """Datiert den Vertragsbeginn auf <jahr>-01-01 zurück, wo er später liegt.

        Der Sollstellungslauf berücksichtigt nur Verträge mit beginn <= Periode.
        Für ein Testjahr in der Vergangenheit müssen die Verträge also im Testjahr
        bereits aktiv sein. Test-/Demo-Eingriff in Stammdaten — per Seed-Reset
        wiederherstellbar.
        """
        jan1 = date(jahr, 1, 1)
        geaendert = 0
        for ev in evs:
            if ev.beginn and ev.beginn > jan1:
                ev.beginn = jan1
                ev.save(update_fields=['beginn'])
                geaendert += 1
        if geaendert:
            self.stdout.write(self.style.WARNING(
                f"  Vertragsbeginn auf {jan1} zurückdatiert: {geaendert} Verträge (Test-Eingriff in Stammdaten)"
            ))
        return geaendert

    def _historie_spiegeln(self, evs, template, jahr, user):
        """Spiegelt die zum Referenz-Stichtag gültigen Beträge auf gueltig_ab=<jahr>-01-01."""
        ref_stichtag = date(template.jahr, template.beginn_monat, 1)
        jan1 = date(jahr, 1, 1)
        dez31 = date(jahr, 12, 31)
        angelegt = 0

        for ev in evs:
            # Neueste Quell-Einträge je (ba, abrechnungsart) ermitteln
            quelle = (
                HausgeldHistorie.objects
                .filter(eigentumsverhaeltnis=ev, gueltig_ab__lte=ref_stichtag)
                .order_by('ba_id', 'abrechnungsart_id', '-gueltig_ab')
                .select_related('ba', 'abrechnungsart')
            )
            seen = set()
            for h in quelle:
                key = (h.ba_id, h.abrechnungsart_id)
                if key in seen:
                    continue
                seen.add(key)
                if not h.betrag or h.betrag <= 0:
                    continue
                # Idempotenz: existiert für dieses Jahr schon ein Eintrag?
                if HausgeldHistorie.objects.filter(
                    eigentumsverhaeltnis=ev, ba_id=h.ba_id,
                    abrechnungsart_id=h.abrechnungsart_id, gueltig_ab=jan1,
                ).exists():
                    continue
                HausgeldHistorie.objects.create(
                    eigentumsverhaeltnis=ev,
                    abrechnungsart_id=h.abrechnungsart_id,
                    ba_id=h.ba_id,
                    betrag=h.betrag,
                    gueltig_ab=jan1,
                    gueltig_bis=dez31,
                    wirtschaftsplan_jahr=jahr,
                    quelle='import',
                    beschluss=None,
                    quelle_wp=None,
                    import_referenz=f'TEST-{jahr}',
                    bemerkung=f'Testjahr {jahr} — gespiegelt aus {template.jahr}',
                    erstellt_von=user,
                )
                angelegt += 1

        self.stdout.write(f"  Hausgeld-Historie {jahr}: {angelegt} Einträge angelegt")
        return angelegt

    def _sollstellungslaeufe(self, objekt, jahr, wj_neu, ersteller, freigeber):
        laeufe = 0
        ss_gesamt = 0
        for monat in range(1, 13):
            periode = date(jahr, monat, 1)
            # Leere Läufe aus früheren Versuchen entfernen, damit Wiederholung greift
            HausgeldSollstellungslauf.objects.filter(
                objekt=objekt, periode=periode, anzahl_sollstellungen=0,
            ).delete()
            if pruefe_duplikat_lauf(objekt, periode):
                continue  # bereits committet (mit Sollstellungen)
            try:
                lauf = erstelle_lauf_aus_vorschau(objekt, periode, ersteller, wirtschaftsjahr=wj_neu)
            except ValidationError:
                continue

            # Freigabe (Vier-Augen) — mit zweitem User, sonst umgehen
            if freigeber and freigeber.pk != ersteller.pk:
                freigeben_lauf(lauf, freigeber)
            else:
                lauf.status = 'freigegeben'
                lauf.freigabe_user = ersteller
                lauf.freigegeben_am = timezone.now()
                lauf.save(update_fields=['status', 'freigabe_user', 'freigegeben_am'])

            commiten_lauf(lauf, ersteller)
            laeufe += 1
            ss_gesamt += lauf.anzahl_sollstellungen

        self.stdout.write(f"  Sollstellungsläufe: {laeufe} committet, {ss_gesamt} Sollstellungen erzeugt")
        return laeufe, ss_gesamt

    def _splits_auf_wj_umhaengen(self, objekt, jahr, wj_neu):
        """Erlöskonten der Splits auf das Ziel-WJ umhängen.

        _erloeskonto_fuer_ba() wählt das neueste OFFENE WJ — bei einem Testjahr
        in der Vergangenheit zeigt es sonst auf ein späteres WJ. Wir korrigieren
        das, damit die Zahlungsbuchungen im Ziel-WJ landen.
        """
        konten_ziel = {k.kontonummer: k for k in Konto.objects.filter(wirtschaftsjahr=wj_neu)}
        korrigiert = 0
        ss_qs = (
            HausgeldSollstellung.objects
            .filter(objekt=objekt, periode__year=jahr)
            .prefetch_related('splits__erloeskonto')
        )
        for ss in ss_qs:
            for sp in ss.splits.all():
                if sp.erloeskonto is None:
                    continue
                ziel = konten_ziel.get(sp.erloeskonto.kontonummer)
                if ziel is not None and sp.erloeskonto_id != ziel.id:
                    sp.erloeskonto = ziel
                    sp.save(update_fields=['erloeskonto'])
                    korrigiert += 1
        if korrigiert:
            self.stdout.write(f"  Erlöskonten auf WJ {jahr} umgehängt: {korrigiert} Splits")

    def _zahlungen_buchen(self, objekt, jahr, wj_neu, user):
        bank_bew = Konto.objects.filter(wirtschaftsjahr=wj_neu, kontonummer='18000', aktiv=True).first()
        if bank_bew is None:
            self.stdout.write(self.style.WARNING(
                "  Kein Bank-Sachkonto 18000 im Ziel-WJ — Zahlungen werden übersprungen."
            ))
            return 0

        gebucht = 0
        ss_qs = (
            HausgeldSollstellung.objects
            .filter(objekt=objekt, periode__year=jahr, storniert_am__isnull=True)
            .exclude(status_cached='ausgeglichen')
            .select_related('eigentumsverhaeltnis')
            .order_by('periode', 'erstellt_am')
        )
        for ss in ss_qs:
            rest = ss.soll_betrag - ss.ist_betrag
            if rest <= 0:
                continue
            personenkonto = getattr(ss.eigentumsverhaeltnis, 'personenkonto', None)
            if personenkonto is None:
                self.stdout.write(self.style.WARNING(
                    f"  Kein Personenkonto für {ss.eigentumsverhaeltnis} — Sollstellung {ss.opos_nr} übersprungen."
                ))
                continue
            verrechne_eingang_manuell(
                personenkonto=personenkonto,
                bank_sachkonto=bank_bew,
                betrag=rest,
                buchungsdatum=ss.faellig_am,
                buchungstext=f"Testzahlung Hausgeld {ss.periode.strftime('%m/%Y')}",
                wirtschaftsjahr=wj_neu,
                user=user,
                sollstellungs_ids=[str(ss.id)],
            )
            gebucht += 1

        self.stdout.write(f"  Zahlungen gebucht: {gebucht}")
        return gebucht

    def _zusammenfassung(self, objekt, jahr, wj_neu, hist_neu, laeufe, ss_gesamt, zahlungen):
        agg = HausgeldSollstellung.objects.filter(
            objekt=objekt, periode__year=jahr, storniert_am__isnull=True,
        )
        anzahl = agg.count()
        offen = agg.exclude(status_cached='ausgeglichen').count()
        soll = sum((s.soll_betrag for s in agg), Decimal('0'))
        ist = sum((s.ist_betrag for s in agg), Decimal('0'))

        self.stdout.write(self.style.SUCCESS(
            f"\n✓ Testjahr {jahr} für {objekt.objektnummer} fertig:\n"
            f"    Sollstellungen : {anzahl} (offen: {offen})\n"
            f"    Soll gesamt    : {soll} €\n"
            f"    Ist gesamt     : {ist} €\n"
            f"    Differenz      : {soll - ist} €  {'→ alle Personenkonten ausgeglichen' if soll == ist else '→ NICHT vollständig ausgeglichen'}\n"
            f"    Zahlungen      : {zahlungen} gebucht"
        ))
