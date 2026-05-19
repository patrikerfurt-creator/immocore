"""
Wirtschaftsplan-Service — Verteilungsberechnung, Beschluss-Commit, Korrekturbeschluss.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.abrechnung_wp.models import Wirtschaftsplan, WirtschaftsplanPosition, WirtschaftsplanAnteil
from apps.objekte.models import Verteilerschluessel, VerteilerschluesselWert, EinheitVerbrauch
from apps.personen.models import EigentumsVerhaeltnis, HausgeldHistorie
from apps.buchhaltung.models import Buchungsart
from apps.konten.models import Abrechnungsart


# ---------------------------------------------------------------------------
# VS-Basis ermitteln
# ---------------------------------------------------------------------------

def _ermittle_vs_basis(vs_code: str, objekt, wirtschaftsjahr) -> dict:
    """
    Gibt {'gesamt': Decimal, 'per_einheit': {einheit_id: Decimal}} zurück.
    Nutzt VerteilerschluesselWert (wirtschaftsjahr=0 für zeitlose VS).
    """
    vs_obj = Verteilerschluessel.objects.filter(objekt=objekt, schluessel=vs_code, aktiv=True).first()
    if not vs_obj:
        return {'gesamt': Decimal('0'), 'per_einheit': {}}

    werte = VerteilerschluesselWert.objects.filter(
        schluessel=vs_obj,
        beteiligt=True,
    ).filter(
        Q(wirtschaftsjahr=0) | Q(wirtschaftsjahr=wirtschaftsjahr.jahr)
    ).select_related('einheit')

    per_einheit = {}
    gesamt = Decimal('0')
    for w in werte:
        val = w.wert or Decimal('0')
        per_einheit[w.einheit_id] = val
        gesamt += val

    return {'gesamt': gesamt, 'per_einheit': per_einheit}


def _ba_aus_abrechnungsart(abrechnungsart_code: str) -> str:
    """Gibt den BA-Code zurück (z.B. '900', '911'). None wenn unbekannt."""
    return abrechnungsart_code if abrechnungsart_code else None


# ---------------------------------------------------------------------------
# Verteilungsberechnung
# ---------------------------------------------------------------------------

@transaction.atomic
def berechne_verteilung(position: WirtschaftsplanPosition) -> None:
    """
    Errechnet WirtschaftsplanAnteil-Datensätze für alle aktiven Einheiten
    und persistiert sie. Bestehende Anteile werden vorab gelöscht.
    """
    wp = position.wirtschaftsplan
    objekt = wp.wirtschaftsjahr.objekt

    vs_basis = _ermittle_vs_basis(position.vs_code, objekt, wp.wirtschaftsjahr)
    vs_gesamt = vs_basis['gesamt']

    if vs_gesamt == 0:
        WirtschaftsplanAnteil.objects.filter(position=position).delete()
        position.verteilung_validiert = False
        position.save(update_fields=['verteilung_validiert'])
        return

    WirtschaftsplanAnteil.objects.filter(position=position).delete()
    anteile_neu = []
    summe_geprueft = Decimal('0.00')

    for einheit_id, anteil_einheit in vs_basis['per_einheit'].items():
        if anteil_einheit == 0:
            continue
        betrag_anteil = (position.betrag * anteil_einheit / vs_gesamt).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        monatsbetrag = (betrag_anteil / Decimal('12')).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        summe_geprueft += betrag_anteil
        anteile_neu.append(WirtschaftsplanAnteil(
            position=position,
            einheit_id=einheit_id,
            vs_anteil_einheit=anteil_einheit,
            vs_anteil_gesamt=vs_gesamt,
            betrag_anteil=betrag_anteil,
            monatsbetrag_anteil=monatsbetrag,
        ))

    WirtschaftsplanAnteil.objects.bulk_create(anteile_neu)

    differenz = abs(position.betrag - summe_geprueft)
    position.verteilung_validiert = differenz <= Decimal('0.10')
    position.save(update_fields=['verteilung_validiert'])


# ---------------------------------------------------------------------------
# BA-Aggregation je EV
# ---------------------------------------------------------------------------

def _aktives_ev_an_stichtag(einheit, stichtag: date):
    return EigentumsVerhaeltnis.objects.filter(
        einheit=einheit,
        beginn__lte=stichtag,
    ).filter(
        Q(ende__isnull=True) | Q(ende__gte=stichtag)
    ).first()


def aggregiere_ba_je_ev(wp: Wirtschaftsplan) -> dict:
    """
    Aggregiert monatliche Anteile pro EigentumsVerhaeltnis pro BA-Code.
    Gibt {(ev_id, ba_code): Decimal} zurück.
    """
    ergebnis = defaultdict(lambda: Decimal('0.00'))
    for position in wp.positionen.select_related('konto').prefetch_related('anteile__einheit').all():
        ba_code = _ba_aus_abrechnungsart(position.konto.abrechnungsart)
        if not ba_code:
            continue
        for anteil in position.anteile.all():
            ev = _aktives_ev_an_stichtag(anteil.einheit, wp.wirkung_ab)
            if ev is None:
                continue
            ergebnis[(ev.id, ba_code)] += anteil.monatsbetrag_anteil
    return dict(ergebnis)


def _aktualisiere_gesamtsummen(wp: Wirtschaftsplan) -> None:
    """Aktualisiert die Cache-Felder gesamtsumme / gesamtsumme_hausgeld / gesamtsumme_ruecklage."""
    positionen = wp.positionen.select_related('konto').all()
    gesamt = Decimal('0')
    hausgeld = Decimal('0')
    ruecklage = defaultdict(lambda: Decimal('0'))
    for pos in positionen:
        gesamt += pos.betrag
        knum = pos.konto.kontonummer
        abr = pos.konto.abrechnungsart or ''
        if knum[:3] in ('500', '501', '502', '503', '504', '505', '506', '507', '508', '509',
                        '510', '511', '512', '513', '514', '515', '516', '517', '518', '519',
                        '520', '521', '522', '523', '524', '525', '526', '527', '528', '529',
                        '530', '531', '532', '533', '534', '535', '536', '537', '538', '539',
                        '540', '541', '542', '543', '544', '545', '546', '547', '548', '549',
                        '550', '551', '552', '553', '554', '555', '556', '557', '558', '559'):
            hausgeld += pos.betrag
        elif knum.startswith('579'):
            ruecklage[abr] += pos.betrag
    wp.gesamtsumme = gesamt
    wp.gesamtsumme_hausgeld = hausgeld
    wp.gesamtsumme_ruecklage = {k: str(v) for k, v in ruecklage.items()}
    wp.save(update_fields=['gesamtsumme', 'gesamtsumme_hausgeld', 'gesamtsumme_ruecklage'])


# ---------------------------------------------------------------------------
# Beschluss-Commit
# ---------------------------------------------------------------------------

@transaction.atomic
def commite_beschluss(wp: Wirtschaftsplan, beschluss_data: dict, user) -> dict:
    """
    Führt den Beschluss atomar aus:
    1. WP-Status → beschlossen
    2. Ggf. aufhebt_wp → aufgehoben
    3. HausgeldHistorie fortschreiben
    4. Bei rückwirkendem Beschluss: Differenz-Mechanik
    5. WP → aktiv wenn wirkung_ab <= heute

    beschluss_data: {'beschluss_datum': date, 'top': str, 'bemerkung': str}
    """
    from apps.abrechnung_wp.services.wp_differenz_service import (
        ermittle_differenz_perioden, erzeuge_nachhol_sollstellungen,
        erzeuge_gutschrift_auszahlungslauf,
    )

    wp = Wirtschaftsplan.objects.select_for_update().get(pk=wp.pk)

    if wp.status != 'entwurf':
        from django.core.exceptions import ValidationError
        raise ValidationError(f"WP hat Status '{wp.status}' — nur Entwürfe können beschlossen werden.")

    if wp.wirtschaftsjahr.status == 'abgeschlossen':
        from django.core.exceptions import ValidationError
        raise ValidationError("Wirtschaftsjahr ist abgeschlossen.")

    # Alle Positionen müssen validiert oder freigegeben sein
    unvalidiert = wp.positionen.filter(
        verteilung_validiert=False,
        verteilung_freigegeben_trotz_diff=False,
    )
    if unvalidiert.exists():
        from django.core.exceptions import ValidationError
        raise ValidationError(
            f"{unvalidiert.count()} Position(en) haben ungültige Verteilung."
        )

    now = timezone.now()
    heute = timezone.localdate()

    # 1) WP aktualisieren
    wp.status = 'beschlossen'
    wp.beschluss_datum = beschluss_data.get('beschluss_datum')
    wp.beschluss_tagesordnungspunkt = beschluss_data.get('top', '')
    wp.bemerkung = beschluss_data.get('bemerkung', '')
    wp.beschlossen_am = now
    wp.beschlossen_von = user
    if wp.wirkung_ab <= heute:
        wp.status = 'aktiv'
    wp.save()

    # 2) Vorgänger-WP aufheben
    if wp.aufhebt_wp_id:
        alt_wp = Wirtschaftsplan.objects.select_for_update().get(pk=wp.aufhebt_wp_id)
        alt_wp.status = 'aufgehoben'
        alt_wp.save(update_fields=['status'])

    # 3) HausgeldHistorie fortschreiben
    ba_je_ev = aggregiere_ba_je_ev(wp)
    for (ev_id, ba_code), monatsbetrag in ba_je_ev.items():
        ba_obj = Buchungsart.objects.filter(nr=ba_code).first()
        abr_obj = None
        try:
            ev = EigentumsVerhaeltnis.objects.select_related('einheit__objekt').get(pk=ev_id)
            abr_obj = Abrechnungsart.objects.filter(
                objekt=ev.einheit.objekt, code=ba_code
            ).first()
        except EigentumsVerhaeltnis.DoesNotExist:
            continue

        HausgeldHistorie.objects.update_or_create(
            eigentumsverhaeltnis_id=ev_id,
            abrechnungsart=abr_obj,
            gueltig_ab=wp.wirkung_ab,
            defaults={
                'ba': ba_obj,
                'betrag': monatsbetrag,
                'quelle': 'wirtschaftsplan',
                'quelle_wp': wp,
                'import_referenz': None,
                'beschluss': None,
                'erstellt_von': user,
            },
        )

    # 4) Rückwirkende Differenz-Mechanik
    nachhol_ids = []
    gutschrift_lauf = None
    if wp.wirkung_ab < heute:
        diffs = ermittle_differenz_perioden(wp, ba_je_ev)
        if diffs['erhoehungen']:
            nachhol_ids = erzeuge_nachhol_sollstellungen(wp, diffs['erhoehungen'], user)
        if diffs['absenkungen']:
            gutschrift_lauf = erzeuge_gutschrift_auszahlungslauf(wp, diffs['absenkungen'], user)

    _aktualisiere_gesamtsummen(wp)

    return {
        'wechsel_id': str(wp.id),
        'status': wp.status,
        'nachhol_sollstellungs_ids': nachhol_ids,
        'gutschrift_lauf_id': str(gutschrift_lauf.id) if gutschrift_lauf else None,
    }


# ---------------------------------------------------------------------------
# Korrekturbeschluss
# ---------------------------------------------------------------------------

@transaction.atomic
def korrekturbeschluss_anlegen(alt_wp: Wirtschaftsplan, user) -> Wirtschaftsplan:
    """
    Legt einen neuen WP-Entwurf mit aufhebt_wp=alt_wp an und kopiert
    alle Positionen und Anteile des Vorgängers.
    """
    neu = Wirtschaftsplan.objects.create(
        wirtschaftsjahr=alt_wp.wirtschaftsjahr,
        status='entwurf',
        wirkung_ab=alt_wp.wirkung_ab,
        aufhebt_wp=alt_wp,
        erstellt_von=user,
    )

    for pos in alt_wp.positionen.prefetch_related('anteile').all():
        neue_pos = WirtschaftsplanPosition.objects.create(
            wirtschaftsplan=neu,
            konto=pos.konto,
            vs_code=pos.vs_code,
            betrag=pos.betrag,
            bemerkung=pos.bemerkung,
        )
        # Anteile neu berechnen (nicht 1:1 kopieren — Stammdaten könnten sich geändert haben)
        berechne_verteilung(neue_pos)

    return neu
