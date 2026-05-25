import io
import zipfile
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Q
from django.template.loader import render_to_string
import weasyprint

from apps.abrechnung_wp.models import Wirtschaftsplan, WirtschaftsplanAnteil
from apps.objekte.models import Bankkonto, Einheit, Verteilerschluessel
from apps.personen.models import EigentumsVerhaeltnis


def _fmt(v) -> str:
    """Decimal/float → deutsches Format '1.234,56'."""
    return f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt3(v) -> str:
    """Decimal/float → deutsches Format '1.000,000' (3 Nachkommastellen)."""
    return f"{float(v):,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")


_VS_UNIT = {
    'mea':      'MEA',
    'flaeche':  'm²',
}


def _build_vs_lookup(objekt) -> dict:
    """Gibt {vs_code: {'bezeichnung': str, 'unit': str}} für alle aktiven VS im Objekt zurück."""
    result = {}
    for vs in Verteilerschluessel.objects.filter(objekt=objekt, aktiv=True):
        unit = _VS_UNIT.get(vs.vs_typ or '', 'Einh.')
        result[vs.schluessel] = {'bezeichnung': vs.bezeichnung, 'unit': unit}
    return result


def render_gesamt_pdf(wp: Wirtschaftsplan) -> bytes:
    objekt = wp.wirtschaftsjahr.objekt
    vs_lookup = _build_vs_lookup(objekt)

    positionen_raw = (
        wp.positionen
        .filter(betrag__gt=0)
        .select_related('konto')
        .order_by('konto__kontonummer')
    )

    positionen = []
    for pos in positionen_raw:
        vs_info = vs_lookup.get(pos.vs_code, {})
        positionen.append({
            'kontonummer': pos.konto.kontonummer,
            'kontoname':   pos.konto.kontoname,
            'vs_code':     pos.vs_code,
            'vs_bezeichnung': vs_info.get('bezeichnung', pos.vs_code),
            'betrag':      _fmt(pos.betrag),
        })

    gesamtsumme = Decimal(str(wp.gesamtsumme))
    summe_hausgeld = Decimal(str(wp.gesamtsumme_hausgeld))
    summe_ruecklage = gesamtsumme - summe_hausgeld
    monatssoll = (gesamtsumme / Decimal('12')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    context = {
        'wp':              wp,
        'objekt':          objekt,
        'wj':              wp.wirtschaftsjahr,
        'positionen':      positionen,
        'gesamtsumme':     _fmt(gesamtsumme),
        'summe_hausgeld':  _fmt(summe_hausgeld),
        'summe_ruecklage': _fmt(summe_ruecklage),
        'monatssoll':      _fmt(monatssoll),
        'erstellt_am':     date.today().strftime('%d.%m.%Y'),
        'ist_entwurf':     wp.status == 'entwurf',
        'beschluss_datum': wp.beschluss_datum.strftime('%d.%m.%Y') if wp.beschluss_datum else '—',
        'wirkung_ab':      wp.wirkung_ab.strftime('%d.%m.%Y'),
    }

    html = render_to_string('wirtschaftsplan/gesamt.html', context)
    return weasyprint.HTML(string=html).write_pdf()


def render_einzel_pdf(wp: Wirtschaftsplan, einheit: Einheit) -> bytes:
    objekt = wp.wirtschaftsjahr.objekt
    vs_lookup = _build_vs_lookup(objekt)

    ev = (
        EigentumsVerhaeltnis.objects
        .filter(einheit=einheit, beginn__lte=wp.wirkung_ab)
        .filter(Q(ende__isnull=True) | Q(ende__gte=wp.wirkung_ab))
        .select_related('person')
        .first()
    )

    anteile_list = list(
        WirtschaftsplanAnteil.objects
        .filter(position__wirtschaftsplan=wp, einheit=einheit, position__betrag__gt=0)
        .select_related('position', 'position__konto')
        .order_by('position__konto__kontonummer')
    )

    positionen = []
    jahresanteil_by_ba: dict[str, Decimal] = {}
    monatssoll_by_ba:   dict[str, Decimal] = {}
    mea_anteil = mea_gesamt = None

    for anteil in anteile_list:
        pos = anteil.position
        ba = pos.konto.abrechnungsart or '900'
        vs_info = vs_lookup.get(pos.vs_code, {})
        unit = vs_info.get('unit', 'Einh.')

        if pos.vs_code == '010' and mea_anteil is None:
            mea_anteil = _fmt3(anteil.vs_anteil_einheit)
            mea_gesamt = _fmt3(anteil.vs_anteil_gesamt)

        positionen.append({
            'kontonummer':    pos.konto.kontonummer,
            'kontoname':      pos.konto.kontoname,
            'vs_gesamt':      _fmt3(anteil.vs_anteil_gesamt),
            'vs_gesamt_unit': unit,
            'vs_anteil':      _fmt3(anteil.vs_anteil_einheit),
            'vs_anteil_unit': unit,
            'betrag':         _fmt(pos.betrag),
            'betrag_anteil':  _fmt(anteil.betrag_anteil),
        })

        jahresanteil_by_ba[ba] = jahresanteil_by_ba.get(ba, Decimal('0')) + anteil.betrag_anteil

    jahresanteil_gesamt = sum(jahresanteil_by_ba.values(), Decimal('0'))
    monatssoll_by_ba = {
        ba: (v / Decimal('12')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        for ba, v in jahresanteil_by_ba.items()
    }
    monatssoll_gesamt = sum(monatssoll_by_ba.values(), Decimal('0'))

    bankkonto = (
        Bankkonto.objects
        .filter(objekt=objekt, konto_typ='bewirtschaftung', aktiv=True)
        .order_by('reihenfolge')
        .first()
    )

    context = {
        'wp':              wp,
        'objekt':          objekt,
        'wj':              wp.wirtschaftsjahr,
        'einheit':         einheit,
        'person_name':     ev.person.name if ev else '—',
        'mea_anteil':      mea_anteil,
        'mea_gesamt':      mea_gesamt,
        'positionen':      positionen,
        'jahresanteil_by_ba': {k: _fmt(v) for k, v in sorted(jahresanteil_by_ba.items())},
        'monatssoll_by_ba':   {k: _fmt(v) for k, v in sorted(monatssoll_by_ba.items())},
        'jahresanteil_gesamt': _fmt(jahresanteil_gesamt),
        'monatssoll_gesamt':   _fmt(monatssoll_gesamt),
        'bewirtschaftung_iban': bankkonto.iban if bankkonto else '—',
        'erstellt_am':     date.today().strftime('%d.%m.%Y'),
        'ist_entwurf':     wp.status == 'entwurf',
        'beschluss_datum': wp.beschluss_datum.strftime('%d.%m.%Y') if wp.beschluss_datum else '—',
        'wirkung_ab':      wp.wirkung_ab.strftime('%d.%m.%Y'),
    }

    html = render_to_string('wirtschaftsplan/einzeln.html', context)
    return weasyprint.HTML(string=html).write_pdf()


def render_einzel_bulk_zip(wp: Wirtschaftsplan) -> bytes:
    objekt = wp.wirtschaftsjahr.objekt
    einheiten = Einheit.objects.filter(objekt=objekt).order_by('einheit_nr')

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for einheit in einheiten:
            pdf = render_einzel_pdf(wp, einheit)
            fname = f"EWP_{objekt.objektnummer}_{einheit.einheit_nr}_{wp.wirtschaftsjahr.jahr}.pdf"
            zf.writestr(fname, pdf)
    return buf.getvalue()
