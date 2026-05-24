"""
WP-PDF-Service — Gesamtwirtschaftsplan-PDF und Einzelwirtschaftsplan-PDF via WeasyPrint.
"""
import io
import zipfile
from decimal import Decimal
from datetime import date

from django.template.loader import render_to_string
from django.utils import timezone

from apps.abrechnung_wp.models import Wirtschaftsplan, WirtschaftsplanAnteil
from apps.objekte.models import Verteilerschluessel
from apps.personen.models import EigentumsVerhaeltnis
from django.db.models import Q


# ---------------------------------------------------------------------------
# Interne Helfer
# ---------------------------------------------------------------------------

def _build_vs_cache(objekt) -> dict:
    """Lädt alle aktiven VS für das Objekt in einen {schluessel: vs_obj}-Cache (1 Query)."""
    return {
        vs.schluessel: vs
        for vs in Verteilerschluessel.objects.filter(objekt=objekt, aktiv=True)
    }


def _build_ev_name_map(einheit_ids: list, stichtag: date) -> dict:
    """Gibt {einheit_id: eigentümer_name} zurück — 2 Queries statt N×2."""
    evs = (
        EigentumsVerhaeltnis.objects
        .filter(einheit_id__in=einheit_ids, beginn__lte=stichtag)
        .filter(Q(ende__isnull=True) | Q(ende__gte=stichtag))
        .select_related('person')
        .order_by('einheit_id', '-beginn')
    )
    result: dict = {}
    for ev in evs:
        if ev.einheit_id not in result:
            result[ev.einheit_id] = ev.person.name

    # Fallback für Einheiten ohne aktives EV → neuestes EV
    missing = [eid for eid in einheit_ids if eid not in result]
    if missing:
        for ev in (
            EigentumsVerhaeltnis.objects
            .filter(einheit_id__in=missing)
            .select_related('person')
            .order_by('einheit_id', '-beginn')
        ):
            if ev.einheit_id not in result:
                result[ev.einheit_id] = ev.person.name

    return result


def _vs_bezeichnung(vs_code: str, objekt) -> str:
    """Einzelabfrage — nur noch für standalone-Nutzung außerhalb der Bulk-Funktionen."""
    vs = Verteilerschluessel.objects.filter(objekt=objekt, schluessel=vs_code, aktiv=True).first()
    return vs.bezeichnung if vs else vs_code


def _bewirtschaftungs_iban(objekt) -> str:
    bk = objekt.bankkonten.filter(konto_typ='bewirtschaftung', aktiv=True).first()
    return bk.iban if bk else ''


def _eigentuemer_name(einheit, stichtag: date) -> str:
    """Einzelabfrage — für standalone-Nutzung oder Fallback."""
    ev = EigentumsVerhaeltnis.objects.filter(
        einheit=einheit,
        beginn__lte=stichtag,
    ).filter(
        Q(ende__isnull=True) | Q(ende__gte=stichtag)
    ).select_related('person').first()
    if ev:
        return ev.person.name
    ev_latest = EigentumsVerhaeltnis.objects.filter(
        einheit=einheit
    ).select_related('person').order_by('-beginn').first()
    return ev_latest.person.name if ev_latest else '—'


# ---------------------------------------------------------------------------
# Öffentliche Render-Funktionen
# ---------------------------------------------------------------------------

def render_gesamt_pdf(wp: Wirtschaftsplan) -> bytes:
    """Rendert den Gesamtwirtschaftsplan als PDF-Bytes."""
    wp = Wirtschaftsplan.objects.select_related(
        'wirtschaftsjahr__objekt'
    ).prefetch_related(
        'positionen__konto',
        'positionen__anteile',
    ).get(pk=wp.pk)

    wj = wp.wirtschaftsjahr
    objekt = wj.objekt
    heute = timezone.localdate()

    # VS-Bezeichnungen in einem Query laden (statt N einzelne Abfragen pro Position)
    vs_cache = _build_vs_cache(objekt)

    positionen_ctx = []
    gesamt = Decimal('0')
    hausgeld = Decimal('0')
    ruecklagen_map: dict[str, Decimal] = {}

    for pos in wp.positionen.filter(betrag__gt=0).order_by('konto__kontonummer'):
        monatlich = (pos.betrag / Decimal('12')).quantize(Decimal('0.01'))
        vs_obj = vs_cache.get(pos.vs_code)
        positionen_ctx.append({
            'konto': pos.konto,
            'vs_code': pos.vs_code,
            'vs_bezeichnung': vs_obj.bezeichnung if vs_obj else pos.vs_code,
            'betrag': pos.betrag,
            'monatlich': monatlich,
        })
        gesamt += pos.betrag
        ba = pos.konto.abrechnungsart or ''
        nr = pos.konto.kontonummer
        if ba == '900' or ('50000' <= nr <= '55999'):
            hausgeld += pos.betrag
        elif nr.startswith('57') and ba:
            ruecklagen_map[ba] = ruecklagen_map.get(ba, Decimal('0')) + pos.betrag

    ruecklagen_ctx = [
        {
            'ba_code': ba_code,
            'jahresbetrag': betrag,
            'monatsbetrag': (betrag / Decimal('12')).quantize(Decimal('0.01')),
        }
        for ba_code, betrag in sorted(ruecklagen_map.items())
    ]

    context = {
        'wp': wp,
        'wj': wj,
        'objekt': objekt,
        'positionen': positionen_ctx,
        'gesamt': gesamt,
        'gesamt_monatlich': (gesamt / Decimal('12')).quantize(Decimal('0.01')),
        'hausgeld': hausgeld,
        'hausgeld_monatlich': (hausgeld / Decimal('12')).quantize(Decimal('0.01')),
        'ruecklagen': ruecklagen_ctx,
        'entwurf': wp.status == 'entwurf',
        'heute': heute.strftime('%d.%m.%Y'),
    }

    html = render_to_string('wirtschaftsplan/gesamt.html', context)
    return _html_to_pdf(html)


def render_einzel_pdf(wp: Wirtschaftsplan, einheit) -> bytes:
    """Rendert den Einzelwirtschaftsplan für eine Einheit als PDF-Bytes."""
    wp_loaded = Wirtschaftsplan.objects.select_related(
        'wirtschaftsjahr__objekt'
    ).prefetch_related(
        'positionen__konto',
        'positionen__anteile__einheit',
    ).get(pk=wp.pk)

    objekt = wp_loaded.wirtschaftsjahr.objekt
    stichtag = wp_loaded.beschluss_datum or timezone.localdate()
    vs_cache = _build_vs_cache(objekt)
    ev_map = _build_ev_name_map([einheit.id], stichtag)

    return _render_einzel_pdf_intern(wp_loaded, einheit, vs_cache, ev_map)


def render_einzel_bulk_zip(wp: Wirtschaftsplan) -> bytes:
    """
    Erzeugt ein ZIP-Archiv mit einem Einzel-PDF je Einheit.

    Optimiert: WP wird einmal aus der DB geladen; VS-Cache und Eigentümer-Map
    werden einmalig aufgebaut und an alle Render-Aufrufe weitergereicht.
    Damit entfallen ~(50 × 3) redundante DB-Roundtrips und ~500 VS-Abfragen.
    """
    from apps.objekte.models import Einheit

    # WP einmal laden — nicht N-mal in render_einzel_pdf()
    wp_loaded = Wirtschaftsplan.objects.select_related(
        'wirtschaftsjahr__objekt'
    ).prefetch_related(
        'positionen__konto',
        'positionen__anteile__einheit',
    ).get(pk=wp.pk)

    objekt = wp_loaded.wirtschaftsjahr.objekt
    wj = wp_loaded.wirtschaftsjahr
    stichtag = wp_loaded.beschluss_datum or timezone.localdate()

    einheit_ids = list(
        WirtschaftsplanAnteil.objects.filter(
            position__wirtschaftsplan=wp
        ).values_list('einheit_id', flat=True).distinct()
    )
    einheiten = list(Einheit.objects.filter(pk__in=einheit_ids).order_by('einheit_nr'))

    # Caches einmal aufbauen — kein DB-Hit mehr im Render-Loop
    vs_cache = _build_vs_cache(objekt)
    ev_map = _build_ev_name_map([e.id for e in einheiten], stichtag)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for einheit in einheiten:
            pdf_bytes = _render_einzel_pdf_intern(wp_loaded, einheit, vs_cache, ev_map)
            filename = f"EWP_{objekt.kurzbezeichnung or objekt.id}_{einheit.einheit_nr}_{wj.jahr}.pdf"
            filename = filename.replace(' ', '_').replace('/', '-')
            zf.writestr(filename, pdf_bytes)

    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------------------
# Interne Render-Funktion (Kern-Logik, cache-basiert)
# ---------------------------------------------------------------------------

def _render_einzel_pdf_intern(
    wp: Wirtschaftsplan,
    einheit,
    vs_cache: dict,
    ev_map: dict,
) -> bytes:
    """
    Innere Render-Funktion. Erwartet einen bereits geladenen WP (mit Prefetch)
    sowie vorberechnete vs_cache und ev_map — kein zusätzlicher DB-Roundtrip
    für VS-Bezeichnungen oder Eigentümer-Namen.
    """
    wj = wp.wirtschaftsjahr
    objekt = wj.objekt
    heute = timezone.localdate()

    anteile_map = {
        a.position_id: a
        for a in WirtschaftsplanAnteil.objects.filter(
            position__wirtschaftsplan=wp,
            einheit=einheit,
        )
    }

    positionen_ctx = []
    gesamt_jahresbetrag = Decimal('0')
    gesamt_anteil = Decimal('0')
    ba_splits: dict[str, dict] = {}

    for pos in wp.positionen.filter(betrag__gt=0).order_by('konto__kontonummer'):
        anteil = anteile_map.get(pos.id)
        if anteil is None:
            continue

        vs_gesamt = anteil.vs_anteil_gesamt
        vs_einheit = anteil.vs_anteil_einheit
        vs_obj = vs_cache.get(pos.vs_code)
        einheit_label = vs_obj.einheit if (vs_obj and vs_obj.einheit) else ''

        if vs_obj and vs_obj.vs_typ in ('kopf', 'direkt'):
            vs_gesamt_text = f"{int(vs_gesamt):,} Einh.".replace(',', '.')
            vs_anteil_text = f"{int(vs_einheit)} Einh."
        else:
            vs_gesamt_text = f"{vs_gesamt:,.3f} {einheit_label}".replace(',', 'X').replace('.', ',').replace('X', '.')
            vs_anteil_text = f"{vs_einheit:,.3f}".replace(',', 'X').replace('.', ',').replace('X', '.')

        positionen_ctx.append({
            'konto': pos.konto,
            'vs_gesamt_text': vs_gesamt_text,
            'vs_anteil_text': vs_anteil_text,
            'betrag': pos.betrag,
            'betrag_anteil': anteil.betrag_anteil,
        })

        gesamt_jahresbetrag += pos.betrag
        gesamt_anteil += anteil.betrag_anteil

        ba = pos.konto.abrechnungsart or '900'
        if ba not in ba_splits:
            ba_bez = 'Hausgeld lfd. Bewirtschaftung' if ba == '900' else f'Rücklage {ba}'
            ba_splits[ba] = {'bezeichnung': ba_bez, 'jahresanteil': Decimal('0'), 'monatsbetrag': Decimal('0')}
        ba_splits[ba]['jahresanteil'] += anteil.betrag_anteil
        ba_splits[ba]['monatsbetrag'] += anteil.monatsbetrag_anteil

    monatssoll_gesamt = sum(v['monatsbetrag'] for v in ba_splits.values())

    context = {
        'wp': wp,
        'wj': wj,
        'objekt': objekt,
        'einheit': einheit,
        'eigentuemer_name': ev_map.get(einheit.id, '—'),
        'positionen': positionen_ctx,
        'gesamt_jahresbetrag': gesamt_jahresbetrag,
        'gesamt_anteil': gesamt_anteil,
        'ba_splits': ba_splits,
        'monatssoll_gesamt': monatssoll_gesamt,
        'bewirtschaftung_iban': _bewirtschaftungs_iban(objekt),
        'entwurf': wp.status == 'entwurf',
        'heute': heute.strftime('%d.%m.%Y'),
    }

    html = render_to_string('wirtschaftsplan/einzeln.html', context)
    return _html_to_pdf(html)


def _html_to_pdf(html: str) -> bytes:
    from weasyprint import HTML
    return HTML(string=html, base_url=None).write_pdf()
