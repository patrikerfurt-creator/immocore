"""
WP-Differenz-Service — Rückwirkende Beschlüsse: Nachhol-Sollstellungen und Gutschrift-Auszahlungsläufe.
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from apps.abrechnung_wp.models import Wirtschaftsplan
from apps.buchhaltung.models import Buchungsart, HausgeldSollstellung
from apps.personen.models import EigentumsVerhaeltnis, HausgeldHistorie


def _monatsersten_zwischen(von: date, bis_exkl: date):
    """Gibt alle Monatsersten [von, bis_exkl) zurück."""
    result = []
    p = date(von.year, von.month, 1)
    bis_erster = date(bis_exkl.year, bis_exkl.month, 1)
    while p < bis_erster:
        result.append(p)
        if p.month == 12:
            p = date(p.year + 1, 1, 1)
        else:
            p = date(p.year, p.month + 1, 1)
    return result


def _altes_monatssoll(ev_id: str, ba_code: str, vor_datum: date) -> Decimal:
    """
    Gibt den zuletzt gültigen HausgeldHistorie-Betrag für (ev, ba) VOR dem WP-Wirkungsdatum zurück.
    """
    hist = HausgeldHistorie.objects.filter(
        eigentumsverhaeltnis_id=ev_id,
        ba__nr=ba_code,
        gueltig_ab__lt=vor_datum,
    ).order_by('-gueltig_ab').first()
    return hist.betrag if hist else Decimal('0')


def _ev_fuer_periode(einheit_id, periode: date):
    """Gibt den aktiven EV für eine Einheit in einer Periode zurück."""
    erster = date(periode.year, periode.month, 1)
    return EigentumsVerhaeltnis.objects.filter(
        einheit_id=einheit_id,
        beginn__lte=erster,
    ).filter(
        Q(ende__isnull=True) | Q(ende__gte=erster)
    ).first()


def ermittle_differenz_perioden(wp: Wirtschaftsplan, ba_je_ev: dict) -> dict:
    """
    Ermittelt pro (ev, periode, ba_code) die Differenz zwischen neuem und altem Soll.

    Gibt {
      'erhoehungen': [(ev, periode, {ba_code: diff}), ...],
      'absenkungen': [(ev, gesamt_diff, {ba_code: diff}), ...],
    } zurück.
    """
    heute = timezone.localdate()
    perioden = _monatsersten_zwischen(wp.wirkung_ab, heute)
    if not perioden:
        return {'erhoehungen': [], 'absenkungen': []}

    # Aggregiere neues Soll je EV je BA
    neues_soll = defaultdict(lambda: defaultdict(lambda: Decimal('0')))
    for (ev_id, ba_code), betrag in ba_je_ev.items():
        neues_soll[ev_id][ba_code] = betrag

    # Pro Periode: finde den aktiven EV
    # Gruppen: {(ev_id, ba_code): diff_je_periode_liste}
    erhoehungen_map = defaultdict(list)  # (ev_id, periode) → {ba_code: diff}
    absenkungen_map = defaultdict(lambda: defaultdict(lambda: Decimal('0')))  # ev_id → {ba_code: sum_diff}

    # Hole alle betroffenen Einheiten aus den WP-Anteilen
    from apps.abrechnung_wp.models import WirtschaftsplanAnteil
    einheit_ids = (
        WirtschaftsplanAnteil.objects
        .filter(position__wirtschaftsplan=wp)
        .values_list('einheit_id', flat=True)
        .distinct()
    )

    for einheit_id in einheit_ids:
        for periode in perioden:
            ev = _ev_fuer_periode(einheit_id, periode)
            if not ev:
                continue
            ev_id = str(ev.id)
            diff_je_ba = {}
            for ba_code, neuer_betrag in neues_soll[ev_id].items():
                alter_betrag = _altes_monatssoll(ev_id, ba_code, wp.wirkung_ab)
                diff = neuer_betrag - alter_betrag
                if diff != 0:
                    diff_je_ba[ba_code] = diff

            for ba_code, diff in diff_je_ba.items():
                if diff > 0:
                    if ev_id not in [e[0] for e in erhoehungen_map.get((ev_id, periode), [])]:
                        erhoehungen_map[(ev_id, str(einheit_id), periode)] = diff_je_ba
                elif diff < 0:
                    absenkungen_map[ev_id][ba_code] += diff

    # Format für Service-Consumer
    erhoehungen = []
    gesehen = set()
    for (ev_id, einheit_id, periode), diff_je_ba in erhoehungen_map.items():
        erh_diffs = {ba: d for ba, d in diff_je_ba.items() if d > 0}
        if erh_diffs and (ev_id, periode) not in gesehen:
            try:
                ev_obj = EigentumsVerhaeltnis.objects.get(pk=ev_id)
                erhoehungen.append((ev_obj, periode, erh_diffs))
                gesehen.add((ev_id, periode))
            except EigentumsVerhaeltnis.DoesNotExist:
                pass

    absenkungen = []
    for ev_id, ba_diffs in absenkungen_map.items():
        neg_diffs = {ba: d for ba, d in ba_diffs.items() if d < 0}
        if neg_diffs:
            try:
                ev_obj = EigentumsVerhaeltnis.objects.get(pk=ev_id)
                gesamt = sum(neg_diffs.values())
                absenkungen.append((ev_obj, gesamt, neg_diffs))
            except EigentumsVerhaeltnis.DoesNotExist:
                pass

    return {'erhoehungen': erhoehungen, 'absenkungen': absenkungen}


def erzeuge_nachhol_sollstellungen(wp: Wirtschaftsplan, erhoehungen: list, user) -> list:
    """
    Legt Nachhol-Sollstellungen für Erhöhungs-Fälle an.
    erhoehungen: [(ev, periode, {ba_code: diff}), ...]
    """
    from apps.buchhaltung.services.sollstellung_service import lege_hausgeld_sollstellung_an

    heute = timezone.localdate()
    nachhol_ids = []

    for ev, periode, diff_je_ba in erhoehungen:
        betraege_je_ba = {}
        for ba_code, diff in diff_je_ba.items():
            if diff <= 0:
                continue
            ba_obj = Buchungsart.objects.filter(nr=ba_code).first()
            if ba_obj:
                betraege_je_ba[ba_obj] = diff

        if not betraege_je_ba:
            continue

        ss = lege_hausgeld_sollstellung_an(
            ev=ev,
            periode=periode,
            betraege_je_ba=betraege_je_ba,
            lauf=None,
            user=user,
        )
        # WP-Referenz setzen
        HausgeldSollstellung.objects.filter(pk=ss.pk).update(
            nachhol_aus_wp_beschluss=wp,
        )
        nachhol_ids.append(str(ss.id))

    return nachhol_ids


def erzeuge_gutschrift_auszahlungslauf(wp: Wirtschaftsplan, absenkungen: list, user):
    """
    Erzeugt einen wp_gutschrift-Auszahlungslauf für Absenkungs-Fälle.
    absenkungen: [(ev, gesamt_betrag, {ba_code: diff}), ...]
    """
    from apps.buchhaltung.models import Auszahlungslauf
    from django.utils import timezone

    if not absenkungen:
        return None

    objekt = wp.wirtschaftsjahr.objekt
    heute = timezone.localdate()
    positionen = []
    gesamt = Decimal('0')

    for ev, gesamt_diff, ba_diffs in absenkungen:
        auszahlungsbetrag = abs(gesamt_diff)
        person = ev.person
        iban = ''
        if hasattr(person, 'ibans') and person.ibans:
            iban = person.ibans[0]

        wp_id_kurz = str(wp.id)[:8]
        ev_id_kurz = str(ev.id)[:8]

        positionen.append({
            'ev_id': str(ev.id),
            'einheit_nr': ev.einheit.einheit_nr,
            'person_name': ev.person_name if hasattr(ev, 'person_name') else str(person),
            'iban': iban,
            'betrag': str(auszahlungsbetrag),
            'end_to_end_id': f'WP-GS-{wp_id_kurz}-{ev_id_kurz}',
            'verwendungszweck': f'Gutschrift WP-Beschluss {wp.beschluss_datum} für Einheit {ev.einheit.einheit_nr}',
            'status': 'offen' if iban else 'blockiert_iban_fehlt',
            'ba_aufteilung': {ba: str(abs(d)) for ba, d in ba_diffs.items()},
        })
        gesamt += auszahlungsbetrag

    lauf = Auszahlungslauf.objects.create(
        objekt=objekt,
        typ='wp_gutschrift',
        bezeichnung=f'WP-Gutschrift {wp.wirtschaftsjahr.jahr} Beschluss {wp.beschluss_datum}',
        faelligkeitsdatum=heute,
        status='erstellt',
        wirtschaftsplan=wp,
        erstellt_von=user,
        anzahl_positionen=len(positionen),
        gesamt_summe=gesamt,
        positionen=positionen,
    )
    return lauf
