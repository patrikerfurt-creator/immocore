"""Kontoauszug des Personenkontos als PDF-Anlage eines Mahnschreibens.

Zwei getrennte Schritte:

* ``baue_daten`` - liest den Auszug aus ``konten.services.personenkonto_service.baue_kontoauszug``
  (dieselbe Logik wie die Kontoauszug-Ansicht: Soll = Sollstellungen, Haben = Zahlungen,
  stornierte Sollstellungen ohne Saldowirkung) und begrenzt ihn auf einen sinnvollen
  Zeitraum. Das Ergebnis ist JSON-sicher und wird zusammen mit dem Schreiben gespeichert,
  damit die Anlage später exakt den Stand des Mahnlaufs zeigt.
* ``rendere_pdf`` - reine Darstellung (WeasyPrint, eigenes schlichtes Template) aus diesen Daten.

Zeitraum: ab dem 1. Januar des Vorjahres bis zum Stichtag. Alles davor wird zu EINER
Zeile "Saldovortrag" verdichtet, der laufende Saldo bleibt dadurch korrekt. Buchungen
nach dem Stichtag (z. B. bereits gestellte künftige Sollstellungen) erscheinen nicht.

Vorzeichen wie im Personenkonto (Eigentümersicht): negativer Saldo = Rückstand.
"""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.template.loader import render_to_string

from apps.konten.services.personenkonto_service import baue_kontoauszug

from . import brief_layout_service, filters, pdf_service

TEMPLATE = 'korrespondenz/kontoauszug_anlage.html'
BEZEICHNUNG = 'Kontoauszug'
NULL = Decimal('0.00')


def _betrag(wert) -> Decimal:
    """Float/None aus ``baue_kontoauszug`` -> Decimal mit 2 Nachkommastellen."""
    if wert is None:
        return NULL
    return Decimal(str(wert)).quantize(NULL, rounding=ROUND_HALF_UP)


def beginn_zeitraum(stichtag: date) -> date:
    return date(stichtag.year - 1, 1, 1)


def _position(p: dict) -> dict:
    soll, haben = p.get('soll'), p.get('haben')
    return {
        'datum': p['buchungsdatum'],
        'beleg': p.get('bu_nr') or '',
        'text': p.get('buchungstext') or '',
        'soll': str(_betrag(soll)) if soll is not None else None,
        'haben': str(_betrag(haben)) if haben is not None else None,
        'saldo': str(_betrag(p['saldo'])),
        'storniert': bool(p.get('storniert')),
    }


def baue_daten(personenkonto, stichtag: date) -> dict:
    """Auszugsdaten (JSON-sicher) des Personenkontos für den Zeitraum bis ``stichtag``."""
    roh = baue_kontoauszug(personenkonto)
    von = beginn_zeitraum(stichtag)
    vortrag = NULL
    saldo = NULL
    positionen = []
    for p in roh['positionen']:
        datum = date.fromisoformat(p['buchungsdatum'])
        if datum > stichtag:
            continue
        saldo = _betrag(p['saldo'])
        if datum < von:
            vortrag = saldo
        else:
            positionen.append(_position(p))
    konto = roh['personenkonto']
    objekt = personenkonto.objekt
    return {
        'stichtag': stichtag.isoformat(),
        'von': von.isoformat(),
        'kopf': {
            'empfaenger': konto['eigentuemer_name'],
            'personenkonto': konto['kontonummer'],
            'einheit_nr': konto['einheit_nr'],
            'objekt': f'{objekt.objektnummer}-{objekt.bezeichnung}'
                      if objekt.objektnummer else objekt.bezeichnung,
        },
        'vortrag': str(vortrag) if vortrag != NULL else None,
        'positionen': positionen,
        'saldo': str(saldo),
    }


# --------------------------------------------------------------------------
# Darstellung
# --------------------------------------------------------------------------

def _euro_oder_leer(wert) -> str:
    return filters.euro(Decimal(wert)) if wert is not None else ''


def _zeile(p: dict) -> dict:
    return {
        'datum': filters.datum(date.fromisoformat(p['datum'])),
        'beleg': p['beleg'],
        'text': p['text'],
        'soll': _euro_oder_leer(p['soll']),
        'haben': _euro_oder_leer(p['haben']),
        'saldo': filters.euro(Decimal(p['saldo'])),
        'storniert': p['storniert'],
    }


def _saldo_hinweis(saldo: Decimal) -> str:
    if saldo < 0:
        return 'Rückstand'
    if saldo > 0:
        return 'Guthaben'
    return 'ausgeglichen'


def baue_template_kontext(daten: dict) -> dict:
    stichtag = date.fromisoformat(daten['stichtag'])
    saldo = Decimal(daten['saldo'])
    return {
        'schrift_regular': brief_layout_service.font_url('LiberationSans-Regular.ttf'),
        'schrift_bold': brief_layout_service.font_url('LiberationSans-Bold.ttf'),
        'kopf': daten['kopf'],
        'stichtag': filters.datum(stichtag),
        'von': filters.datum(date.fromisoformat(daten['von'])),
        'vortrag': filters.euro(Decimal(daten['vortrag'])) if daten['vortrag'] else '',
        'zeilen': [_zeile(p) for p in daten['positionen']],
        'saldo': filters.euro(saldo),
        'saldo_hinweis': _saldo_hinweis(saldo),
    }


def rendere_pdf(daten: dict) -> bytes:
    """Rendert die Auszugsdaten zu einem (ggf. mehrseitigen) PDF."""
    html = render_to_string(TEMPLATE, baue_template_kontext(daten))
    return pdf_service.html_zu_pdf(html)


def erzeuge_anlage(daten: dict) -> pdf_service.AnlagePdf:
    """Anlage für ``pdf_service.haenge_anlagen_an`` / ``erzeuge_pdf(anlagen=...)``."""
    return pdf_service.AnlagePdf(BEZEICHNUNG, rendere_pdf(daten))
