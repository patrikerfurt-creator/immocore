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


def _vs_bezeichnung(vs_code: str, objekt) -> str:
    vs = Verteilerschluessel.objects.filter(objekt=objekt, schluessel=vs_code, aktiv=True).first()
    return vs.bezeichnung if vs else vs_code


def _bewirtschaftungs_iban(objekt) -> str:
    bk = objekt.bankkonten.filter(konto_typ='bewirtschaftung', aktiv=True).first()
    return bk.iban if bk else ''


def _eigentuemer_name(einheit, stichtag: date) -> str:
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

    positionen_ctx = []
    gesamt = Decimal('0')
    hausgeld = Decimal('0')
    ruecklagen_map: dict[str, Decimal] = {}

    for pos in wp.positionen.filter(betrag__gt=0).order_by('konto__kontonummer'):
        monatlich = (pos.betrag / Decimal('12')).quantize(Decimal('0.01'))
        positionen_ctx.append({
            'konto': pos.konto,
            'vs_code': pos.vs_code,
            'vs_bezeichnung': _vs_bezeichnung(pos.vs_code, objekt),
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
    wp = Wirtschaftsplan.objects.select_related(
        'wirtschaftsjahr__objekt'
    ).prefetch_related(
        'positionen__konto',
        'positionen__anteile__einheit',
    ).get(pk=wp.pk)

    wj = wp.wirtschaftsjahr
    objekt = wj.objekt
    heute = timezone.localdate()
    stichtag = wp.wirkung_ab

    anteile_map = {
        a.position_id: a
        for a in WirtschaftsplanAnteil.objects.filter(
            position__wirtschaftsplan=wp,
            einheit=einheit,
        ).select_related('position__konto')
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
        vs_obj = Verteilerschluessel.objects.filter(
            objekt=objekt, schluessel=pos.vs_code, aktiv=True
        ).first()
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
            ba_bez = '900' if ba == '900' else f'Rücklage {ba}'
            if ba == '900':
                ba_bez = 'Hausgeld lfd. Bewirtschaftung'
            ba_splits[ba] = {'bezeichnung': ba_bez, 'jahresanteil': Decimal('0'), 'monatsbetrag': Decimal('0')}
        ba_splits[ba]['jahresanteil'] += anteil.betrag_anteil
        ba_splits[ba]['monatsbetrag'] += anteil.monatsbetrag_anteil

    monatssoll_gesamt = sum(v['monatsbetrag'] for v in ba_splits.values())

    context = {
        'wp': wp,
        'wj': wj,
        'objekt': objekt,
        'einheit': einheit,
        'eigentuemer_name': _eigentuemer_name(einheit, stichtag),
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


def render_einzel_bulk_zip(wp: Wirtschaftsplan) -> bytes:
    """Erzeugt ein ZIP-Archiv mit einem Einzel-PDF je Einheit."""
    from apps.objekte.models import Einheit

    wp_obj = Wirtschaftsplan.objects.select_related('wirtschaftsjahr__objekt').get(pk=wp.pk)
    objekt = wp_obj.wirtschaftsjahr.objekt
    wj = wp_obj.wirtschaftsjahr

    einheit_ids = WirtschaftsplanAnteil.objects.filter(
        position__wirtschaftsplan=wp
    ).values_list('einheit_id', flat=True).distinct()

    einheiten = Einheit.objects.filter(pk__in=einheit_ids).order_by('einheit_nr')

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for einheit in einheiten:
            pdf_bytes = render_einzel_pdf(wp, einheit)
            filename = f"EWP_{objekt.kurzbezeichnung or objekt.id}_{einheit.einheit_nr}_{wj.jahr}.pdf"
            filename = filename.replace(' ', '_').replace('/', '-')
            zf.writestr(filename, pdf_bytes)

    buf.seek(0)
    return buf.read()


def _html_to_pdf(html: str) -> bytes:
    from weasyprint import HTML, CSS
    return HTML(string=html, base_url=None).write_pdf()
