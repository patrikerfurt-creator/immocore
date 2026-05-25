"""
Service: Wirtschaftsplan erstellen, Verteilung berechnen, Beschluss durchführen.
Spec: CLAUDE_CODE_ANLEITUNG_WIRTSCHAFTSPLAN_v1_0.md Kap. 12.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.abrechnung_wp.models import Wirtschaftsplan, WirtschaftsplanPosition, WirtschaftsplanAnteil
from apps.objekte.models import Verteilerschluessel, VerteilerschluesselWert, EinheitVerbrauch, Wirtschaftsjahr


@transaction.atomic
def erstelle_wirtschaftsplan(wirtschaftsjahr: Wirtschaftsjahr, wirkung_ab: date, user) -> Wirtschaftsplan:
    """Legt neuen WP-Entwurf an."""
    return Wirtschaftsplan.objects.create(
        wirtschaftsjahr=wirtschaftsjahr,
        wirkung_ab=wirkung_ab,
        status='entwurf',
        erstellt_von=user,
    )


@transaction.atomic
def setze_position_betrag(wp: Wirtschaftsplan, konto, betrag: Decimal, user) -> WirtschaftsplanPosition:
    """
    Legt Position an oder aktualisiert Betrag, berechnet danach die Verteilung.
    """
    if wp.status != 'entwurf':
        raise ValidationError("Nur Entwurf-WPs können bearbeitet werden.")

    vs_code = _aktiver_vs_code(konto)
    if vs_code is None:
        raise ValidationError(f"Konto {konto.kontonummer} hat keinen aktiven Verteilerschlüssel.")

    _validiere_konto_whitelist(konto)

    position, _ = WirtschaftsplanPosition.objects.update_or_create(
        wirtschaftsplan=wp,
        konto=konto,
        defaults={'betrag': betrag, 'vs_code': vs_code},
    )
    berechne_verteilung(position)
    _aktualisiere_gesamtsummen(wp)
    return position


@transaction.atomic
def loesche_position(wp: Wirtschaftsplan, position: WirtschaftsplanPosition) -> None:
    if wp.status != 'entwurf':
        raise ValidationError("Nur Entwurf-WPs können bearbeitet werden.")
    position.delete()
    _aktualisiere_gesamtsummen(wp)


@transaction.atomic
def berechne_verteilung(position: WirtschaftsplanPosition) -> None:
    """
    Errechnet WirtschaftsplanAnteil-Datensätze und persistiert sie.
    Spec Kap. 6.2.
    """
    objekt = position.wirtschaftsplan.wirtschaftsjahr.objekt
    wj = position.wirtschaftsplan.wirtschaftsjahr

    vs_basis = _ermittle_vs_basis(position.vs_code, objekt, wj)
    vs_gesamt = vs_basis['gesamt']

    if vs_gesamt == 0 or vs_gesamt is None:
        position.verteilung_validiert = False
        position.save(update_fields=['verteilung_validiert'])
        return

    WirtschaftsplanAnteil.objects.filter(position=position).delete()

    from apps.objekte.models import Einheit
    einheiten = Einheit.objects.filter(objekt=objekt)
    anteile_neu = []
    summe_geprueft = Decimal('0.00')

    for einheit in einheiten:
        anteil_einheit = vs_basis['per_einheit'].get(str(einheit.id), Decimal('0'))
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
            einheit=einheit,
            vs_anteil_einheit=anteil_einheit,
            vs_anteil_gesamt=vs_gesamt,
            betrag_anteil=betrag_anteil,
            monatsbetrag_anteil=monatsbetrag,
        ))

    WirtschaftsplanAnteil.objects.bulk_create(anteile_neu)
    differenz = (position.betrag - summe_geprueft).copy_abs()
    position.verteilung_validiert = differenz <= Decimal('0.10')
    position.save(update_fields=['verteilung_validiert'])


def aggregiere_ba_je_ev(wp: Wirtschaftsplan) -> dict:
    """
    Aggregiert monatliche Anteile pro EV pro BA-Code.
    Spec Kap. 6.3.
    Returns: {(ev_id, ba_code): Decimal}
    """
    ergebnis = defaultdict(lambda: Decimal('0.00'))
    stichtag = wp.wirkung_ab

    for position in wp.positionen.select_related('konto').prefetch_related('anteile__einheit'):
        ba_code = _ba_aus_konto(position.konto)
        for anteil in position.anteile.all():
            ev = _aktives_ev_an_stichtag(anteil.einheit, stichtag)
            if ev is None:
                continue
            ergebnis[(str(ev.id), ba_code)] += anteil.monatsbetrag_anteil

    return dict(ergebnis)


@transaction.atomic
def commite_beschluss(wp: Wirtschaftsplan, beschluss_datum: date, top: str, bemerkung: str, user) -> dict:
    """
    Führt den WP-Beschluss durch. Spec Kap. 7.
    Nur für nicht-rückwirkende Beschlüsse (wirkung_ab >= heute).
    Rückwirkende Beschlüsse werden in wp_differenz_service behandelt.
    """
    heute = timezone.localdate()

    # Vorbedingungen prüfen
    if wp.status != 'entwurf':
        raise ValidationError(f"WP hat Status '{wp.status}' — nur Entwurf kann beschlossen werden.")

    wj = wp.wirtschaftsjahr
    if wj.status != 'offen':
        raise ValidationError("Wirtschaftsjahr ist abgeschlossen.")

    positionen = list(wp.positionen.all())
    for pos in positionen:
        if not (pos.verteilung_validiert or pos.verteilung_freigegeben_trotz_diff):
            raise ValidationError(
                f"Position {pos.konto.kontonummer} hat ungültige Verteilung. "
                "Bitte prüfen oder manuell freigeben."
            )

    # Vorgänger-WP aufheben falls Korrekturbeschluss
    if wp.aufhebt_wp_id:
        vorgaenger = Wirtschaftsplan.objects.select_for_update().get(id=wp.aufhebt_wp_id)
        if vorgaenger.status not in ('beschlossen', 'aktiv'):
            raise ValidationError("Vorgänger-WP ist nicht aktiv/beschlossen.")
        vorgaenger.status = 'aufgehoben'
        vorgaenger.save(update_fields=['status'])

    # WP beschließen
    wp.status = 'beschlossen' if wp.wirkung_ab > heute else 'aktiv'
    wp.beschluss_datum = beschluss_datum
    wp.beschluss_tagesordnungspunkt = top
    wp.bemerkung = bemerkung or wp.bemerkung
    wp.beschlossen_am = timezone.now()
    wp.beschlossen_von = user
    wp.save(update_fields=['status', 'beschluss_datum', 'beschluss_tagesordnungspunkt',
                           'bemerkung', 'beschlossen_am', 'beschlossen_von'])

    # HausgeldHistorie fortschreiben
    ev_ba_map = aggregiere_ba_je_ev(wp)
    _schreibe_hausgeld_historien(wp, ev_ba_map, user)

    ist_rueckwirkend = wp.wirkung_ab < heute
    stats = {
        'evs_aktualisiert': len(set(ev_id for ev_id, _ in ev_ba_map.keys())),
        'ist_rueckwirkend': ist_rueckwirkend,
        'nachhol_sollstellungen': 0,
        'gutschrift_positionen': 0,
    }

    if ist_rueckwirkend:
        from apps.abrechnung_wp.services.wp_differenz_service import verarbeite_rueckwirkenden_beschluss
        diff_stats = verarbeite_rueckwirkenden_beschluss(wp, ev_ba_map, user)
        stats.update(diff_stats)

    return stats


@transaction.atomic
def korrekturbeschluss_anlegen(alt_wp: Wirtschaftsplan, user) -> Wirtschaftsplan:
    """Legt neuen WP-Entwurf als Korrekturbeschluss für alt_wp an."""
    if alt_wp.status not in ('beschlossen', 'aktiv'):
        raise ValidationError("Korrekturbeschluss nur für beschlossene/aktive WPs möglich.")

    neu = Wirtschaftsplan.objects.create(
        wirtschaftsjahr=alt_wp.wirtschaftsjahr,
        wirkung_ab=alt_wp.wirkung_ab,
        status='entwurf',
        aufhebt_wp=alt_wp,
        erstellt_von=user,
    )

    # Beträge des alten WP als Vorbelegung übernehmen
    for pos in alt_wp.positionen.all():
        WirtschaftsplanPosition.objects.create(
            wirtschaftsplan=neu,
            konto=pos.konto,
            vs_code=pos.vs_code,
            betrag=pos.betrag,
        )
    # Verteilung neu berechnen
    for pos in neu.positionen.all():
        berechne_verteilung(pos)
    _aktualisiere_gesamtsummen(neu)
    return neu


def freigabe_trotz_diff(position: WirtschaftsplanPosition) -> None:
    position.verteilung_freigegeben_trotz_diff = True
    position.save(update_fields=['verteilung_freigegeben_trotz_diff'])


def vorschau_hausgeld(wp: Wirtschaftsplan) -> list[dict]:
    """
    Read-Only-Vorschau der Hausgeld-Sollanteile je EV.
    Gibt Liste von {einheit_nr, lage, person_name, ba_betraege, summe, delta} zurück.
    """
    from apps.personen.models import HausgeldHistorie
    from apps.buchhaltung.models import Buchungsart

    ev_ba_map = aggregiere_ba_je_ev(wp)
    evs_ids = set(ev_id for ev_id, _ in ev_ba_map.keys())

    from apps.personen.models import EigentumsVerhaeltnis
    evs = {
        str(ev.id): ev
        for ev in EigentumsVerhaeltnis.objects.filter(id__in=evs_ids).select_related('person', 'einheit')
    }

    ergebnis = {}
    for (ev_id, ba_code), betrag in ev_ba_map.items():
        if ev_id not in ergebnis:
            ev = evs.get(ev_id)
            ergebnis[ev_id] = {
                'ev_id': ev_id,
                'einheit_nr': ev.einheit.einheit_nr if ev and ev.einheit_id else '',
                'lage': ev.einheit.lage if ev and ev.einheit_id else '',
                'person_name': ev.person.name if ev else '',
                'ba_betraege': {},
                'summe': Decimal('0.00'),
                'delta': Decimal('0.00'),
            }
        ergebnis[ev_id]['ba_betraege'][ba_code] = betrag
        ergebnis[ev_id]['summe'] += betrag

    # Delta zum aktuellen Soll
    for ev_id, zeile in ergebnis.items():
        aktuell = _aktuelles_monatssoll(ev_id, wp.wirkung_ab)
        zeile['delta'] = zeile['summe'] - aktuell

    return sorted(ergebnis.values(), key=lambda x: x['einheit_nr'])


# ---------------------------------------------------------------------------
# Interne Helpers
# ---------------------------------------------------------------------------

def _validiere_konto_whitelist(konto) -> None:
    try:
        nr = int(konto.kontonummer)
    except ValueError:
        raise ValidationError(f"Kontonummer '{konto.kontonummer}' ist keine Zahl.")

    # Aufwand 50000–55999 oder Rücklage 57xxx
    if not ((50000 <= nr <= 55999) or (57000 <= nr <= 57999)):
        raise ValidationError(
            f"Konto {konto.kontonummer} liegt nicht im erlaubten Bereich 50000–55999 oder 57xxx."
        )

    if konto.kontoart not in ('standard', 'summierung'):
        raise ValidationError(
            f"Konto {konto.kontonummer} muss Standard- oder Summierungskonto sein."
        )


def _aktiver_vs_code(konto) -> str | None:
    """Gibt den aktuell gültigen VS-Code des Kontos zurück (aus KontoVerteilerSchluessel)."""
    from apps.konten.models import KontoVerteilerSchluessel
    kvs = KontoVerteilerSchluessel.objects.filter(konto=konto).order_by('-gueltig_ab').first()
    if kvs:
        return kvs.vs_code
    # Fallback: direkt am Konto gespeicherter VS
    return konto.verteilerschluessel or None


def _ermittle_vs_basis(vs_code: str, objekt, wj) -> dict:
    """
    Ermittelt VS-Basis für die Verteilungsberechnung.
    Returns: {'gesamt': Decimal, 'per_einheit': {str(einheit_id): Decimal}}
    Spec Kap. 6.1.
    """
    per_einheit = {}
    gesamt = Decimal('0')

    vs = Verteilerschluessel.objects.filter(objekt=objekt, schluessel=vs_code, aktiv=True).first()
    if vs is None:
        # Versuche Verbrauchswerte direkt
        verbraeuche = EinheitVerbrauch.objects.filter(
            wirtschaftsjahr=wj, vs_code=vs_code
        )
        if verbraeuche.exists():
            for v in verbraeuche:
                if v.wert:
                    per_einheit[str(v.einheit_id)] = v.wert
                    gesamt += v.wert
        return {'gesamt': gesamt, 'per_einheit': per_einheit}

    # Lade zeitlose UND WJ-spezifische Werte; WJ-spezifisch hat Vorrang pro Einheit.
    alle_werte = VerteilerschluesselWert.objects.filter(
        schluessel=vs, beteiligt=True
    ).filter(
        Q(wirtschaftsjahr=0) | Q(wirtschaftsjahr=wj.jahr)
    )
    wert_per_einheit: dict = {}
    for w in alle_werte:
        eid = str(w.einheit_id)
        existing = wert_per_einheit.get(eid)
        if existing is None or w.wirtschaftsjahr != 0:
            wert_per_einheit[eid] = w

    for w in wert_per_einheit.values():
        if w.wert:
            per_einheit[str(w.einheit_id)] = w.wert
            gesamt += w.wert

    return {'gesamt': gesamt, 'per_einheit': per_einheit}


def _ba_aus_konto(konto) -> str:
    """
    Leitet BA-Code aus Konto.abrechnungsart ab (z.B. '900', '911', '912').
    Fallback auf '900' für Aufwandskonten.
    """
    if konto.abrechnungsart:
        return konto.abrechnungsart
    try:
        nr = int(konto.kontonummer)
    except (ValueError, TypeError):
        return '900'
    if 50000 <= nr <= 55999:
        return '900'
    return '900'


def _aktives_ev_an_stichtag(einheit, stichtag: date):
    """Gibt das EigentumsVerhaeltnis der Einheit am Stichtag zurück."""
    from apps.personen.models import EigentumsVerhaeltnis
    return EigentumsVerhaeltnis.objects.filter(
        einheit=einheit,
        beginn__lte=stichtag,
    ).filter(
        Q(ende__isnull=True) | Q(ende__gte=stichtag)
    ).select_related('person', 'einheit').first()


def _schreibe_hausgeld_historien(wp: Wirtschaftsplan, ev_ba_map: dict, user) -> None:
    """Schließt laufende HausgeldHistorie-Einträge und schreibt neue."""
    from datetime import timedelta
    from apps.personen.models import HausgeldHistorie
    from apps.buchhaltung.models import Buchungsart

    vortag = wp.wirkung_ab - timedelta(days=1)
    ev_ids = list({ev_id for ev_id, _ in ev_ba_map.keys()})

    # Alle offenen Historien der betroffenen EVs schließen
    HausgeldHistorie.objects.filter(
        eigentumsverhaeltnis_id__in=ev_ids,
        gueltig_bis__isnull=True,
        gueltig_ab__lt=wp.wirkung_ab,
    ).update(gueltig_bis=vortag)

    for (ev_id, ba_code), monatsbetrag in ev_ba_map.items():
        ba = Buchungsart.objects.filter(code=ba_code).first()
        if ba is None:
            continue
        HausgeldHistorie.objects.create(
            eigentumsverhaeltnis_id=ev_id,
            ba=ba,
            betrag=monatsbetrag,
            gueltig_ab=wp.wirkung_ab,
            quelle='beschluss',
            quelle_wp=wp,
            wirtschaftsplan_jahr=wp.wirtschaftsjahr.jahr,
            erstellt_von=user,
        )


def _aktualisiere_gesamtsummen(wp: Wirtschaftsplan) -> None:
    """Berechnet gesamtsumme, gesamtsumme_hausgeld, gesamtsumme_ruecklage neu."""
    gesamt = Decimal('0')
    hausgeld = Decimal('0')
    ruecklage = {}

    for pos in wp.positionen.filter(betrag__gt=0):
        gesamt += pos.betrag
        ba_code = _ba_aus_konto(pos.konto)
        if ba_code == '900':
            hausgeld += pos.betrag
        else:
            ruecklage[ba_code] = ruecklage.get(ba_code, Decimal('0')) + pos.betrag

    wp.gesamtsumme = gesamt
    wp.gesamtsumme_hausgeld = hausgeld
    wp.gesamtsumme_ruecklage = {k: float(v) for k, v in ruecklage.items()}
    wp.save(update_fields=['gesamtsumme', 'gesamtsumme_hausgeld', 'gesamtsumme_ruecklage'])


def _aktuelles_monatssoll(ev_id: str, stichtag: date) -> Decimal:
    """Gibt die Summe der aktuell gültigen HausgeldHistorie-Beträge vor dem Stichtag zurück."""
    from apps.personen.models import HausgeldHistorie
    from django.db.models import Max

    historien = HausgeldHistorie.objects.filter(
        eigentumsverhaeltnis_id=ev_id,
        gueltig_ab__lt=stichtag,
    ).values('ba_id').annotate(max_gueltig_ab=Max('gueltig_ab'))

    total = Decimal('0')
    for h in historien:
        neueste = HausgeldHistorie.objects.filter(
            eigentumsverhaeltnis_id=ev_id,
            ba_id=h['ba_id'],
            gueltig_ab=h['max_gueltig_ab'],
        ).first()
        if neueste:
            total += neueste.betrag
    return total
