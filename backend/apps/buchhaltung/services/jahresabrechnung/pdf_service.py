"""
Jahresabrechnung — PDF-Rendering und Persistierung, Wizard-Schritte 7/8
(HGA-Spec v1.0 Kap. 5/6.1).

Rendering via WeasyPrint (etablierte Bibliothek im Projekt, siehe
wp_pdf_service.py / Phase-0-Verifikation Punkt 2).

- Schritt 7: render_einzelabrechnung_pdf() — nur Vorschau-Bytes, KEIN Dokument.
- Schritt 8: rendere_und_speichere() — finales PDF als Dokument persistiert
  (bestehender Upload-Mechanismus, FileField → Storage/HiDrive).
"""
from datetime import date
from decimal import Decimal

from django.core.files.base import ContentFile
from django.db.models import F, Sum
from django.template.loader import render_to_string
import weasyprint

from apps.buchhaltung.models import EinzelAbrechnung, HausgeldSollstellung, SollstellungZahlung
from apps.dokumente.models import Dokument
from apps.objekte.models import Verteilerschluessel


def _fmt(v) -> str:
    """Decimal/str → deutsches Format '1.234,56'."""
    return f"{Decimal(str(v)):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _d(v) -> Decimal:
    return Decimal(str(v)) if v is not None and v != '' else Decimal('0')


def _pos_row(p: dict, vs_names: dict) -> dict:
    """Baut eine Kostenzeile für die Einzelabrechnung (Muster Seite 2)."""
    return {
        'nr': p['kontonummer'],
        'name': p['kontoname'],
        'gesamt': _fmt(p['gesamtkosten']),
        'vs_name': vs_names.get(p.get('vs_code'), p.get('vs_code') or ''),
        'umlagebasis': _fmt(p['gesamt']) if p.get('gesamt') else '',
        'umlageanteil': _fmt(p['wert']) if p.get('wert') else '',
        'ihr_anteil': _fmt(p['betrag']),
    }


def render_einzelabrechnung_pdf(ea: EinzelAbrechnung, entwurf: bool = True) -> bytes:
    """Rendert das PDF einer EinzelAbrechnung im Muster-Layout (HGA Seite 2)."""
    ja = ea.jahresabrechnung
    wj = ja.wirtschaftsjahr
    objekt = ja.objekt

    vs_names = {v.schluessel: v.bezeichnung for v in Verteilerschluessel.objects.filter(objekt=objekt)}

    # Kostenpositionen nach umlagefähig / nicht umlagefähig gliedern
    gueltig = [p for p in ea.positionen if not p.get('fehler') and p.get('betrag') is not None]
    fehler_positionen = [p for p in ea.positionen if p.get('fehler')]
    uf = [p for p in gueltig if p.get('umlagefaehig')]
    nuf = [p for p in gueltig if not p.get('umlagefaehig')]

    def summe(positions, key):
        return sum((_d(p.get(key)) for p in positions), Decimal('0'))

    # Objektweite Aggregate (für die "Gesamt"-Spalte der Summenzeilen)
    from apps.buchhaltung.services.jahresabrechnung.ruecklagen_service import (
        wirtschaftsplan_ruecklage_gesamt,
    )
    geschwister = EinzelAbrechnung.objects.filter(jahresabrechnung=ja)
    obj_reserve_ist = geschwister.aggregate(s=Sum('ruecklagen_zufuehrung_gesamt'))['s'] or Decimal('0')
    # Objekt-Gesamt der Rücklagenzuführung = fixer Wirtschaftsplan-Wert, sonst Ist.
    plan_reserve = wirtschaftsplan_ruecklage_gesamt(wj)
    obj_reserve = plan_reserve if plan_reserve is not None else obj_reserve_ist
    obj_hg_soll = geschwister.aggregate(s=Sum('hausgeld_soll_gesamt'))['s'] or Decimal('0')
    obj_kosten = summe(uf, 'gesamtkosten') + summe(nuf, 'gesamtkosten')

    # Rücklagen-Zuführung als eigene Position (MEA-Basis für die Anzeige)
    try:
        from apps.buchhaltung.services.jahresabrechnung.verteilerschluessel_service import (
            alle_werte_und_gesamt,
        )
        mea_werte, mea_gesamt = alle_werte_und_gesamt('010', objekt, wj)
        r_basis = _fmt(mea_gesamt)
        r_anteil = _fmt(mea_werte[ea.einheit_id]) if ea.einheit_id in mea_werte else ''
    except Exception:
        r_basis = r_anteil = ''

    # Nachrichtlich: Hausgeldrückstand des Eigentümers zum WJ-Ende
    rueckstand = HausgeldSollstellung.objects.filter(
        eigentumsverhaeltnis=ea.eigentumsverhaeltnis,
        sollstellungs_typ='hausgeld',
        periode__lte=wj.ende_datum,
        storniert_am__isnull=True,
    ).aggregate(s=Sum(F('soll_betrag') - F('ist_betrag')))['s'] or Decimal('0')

    ergebnis = ea.abrechnungsergebnis
    ergebnis_label = 'Nachzahlung' if ergebnis > 0 else ('Guthaben' if ergebnis < 0 else 'ausgeglichen')
    saldo = rueckstand + ergebnis  # Nachzahlung erhöht, Guthaben mindert den Rückstand

    tage = (wj.ende_datum - wj.beginn_datum).days + 1

    # Empfänger-Adressblock
    person = ea.eigentuemer
    empf_name = person.firmenname if person.ist_firma else f"{person.vorname} {person.nachname}".strip()
    personenkonto = getattr(ea.eigentumsverhaeltnis, 'personenkonto', None)
    eigentuemer_nr = (
        f"{objekt.objektnummer}+{personenkonto.kontonummer}" if personenkonto else objekt.objektnummer
    )

    # Erklärung der Umlageschlüssel (distinkt je verwendetem VS)
    vs_erklaerung, seen = [], set()
    for p in gueltig:
        code = p.get('vs_code')
        if not code or code in seen:
            continue
        seen.add(code)
        vs_erklaerung.append({
            'name': vs_names.get(code, code),
            'code': code,
            'umlageanteil': _fmt(p['wert']) if p.get('wert') else '',
            'umlagebasis': _fmt(p['gesamt']) if p.get('gesamt') else '',
        })

    # Kontoauszug der Zahlungen, je Buchungsart (900 Hausgeld, 911/912 Rücklage, 920 …)
    zahlungen = (
        SollstellungZahlung.objects
        .filter(
            sollstellung__eigentumsverhaeltnis=ea.eigentumsverhaeltnis,
            sollstellung__sollstellungs_typ='hausgeld',
            sollstellung__storniert_am__isnull=True,
            buchung__buchungsdatum__gte=wj.beginn_datum,
            buchung__buchungsdatum__lte=wj.ende_datum,
        )
        .exclude(buchung__status='storniert')
        .select_related('split__ba', 'buchung')
        .order_by('split__ba__nr', 'buchung__buchungsdatum')
    )
    ka_gruppen = {}
    for z in zahlungen:
        ba = z.split.ba if z.split else None
        nr = ba.nr if ba else '—'
        g = ka_gruppen.setdefault(nr, {
            'ba_nr': nr,
            'label': ba.bezeichnung if ba else 'Ohne Buchungsart',
            'zeilen': [], 'summe': Decimal('0'),
        })
        g['zeilen'].append({
            'datum': z.buchung.buchungsdatum.strftime('%d.%m.%Y'),
            'bemerkung': z.buchung.buchungstext or 'Zahlungseingang',
            'betrag': _fmt(z.betrag),
        })
        g['summe'] += z.betrag
    kontoauszuege = [
        {**g, 'summe': _fmt(g['summe'])} for g in ka_gruppen.values()
    ]

    context = {
        'ist_entwurf': entwurf,
        'erstellt_am': date.today().strftime('%d.%m.%Y'),
        'kontoauszuege': kontoauszuege,
        'objekt': objekt,
        'objekt_anschrift': f"{objekt.strasse}, {objekt.plz} {objekt.ort}",
        'wj': wj,
        'zeitraum_von': wj.beginn_datum.strftime('%d.%m.%y'),
        'zeitraum_bis': wj.ende_datum.strftime('%d.%m.%y'),
        'zeitraum_lang': f"{wj.beginn_datum.strftime('%d.%m.%Y')} – {wj.ende_datum.strftime('%d.%m.%Y')}",
        'person_name': str(ea.eigentuemer),
        'zeitanteil': f"{tage}/{tage}",
        # Empfänger
        'empf_anrede': person.anrede,
        'empf_name': empf_name,
        'empf_adresse_zeilen': [z for z in (person.adresse or '').splitlines() if z.strip()],
        'eigentuemer_nr': eigentuemer_nr,
        # Einheit
        'einheit_nr': ea.einheit.einheit_nr,
        'einheit_lage': ea.einheit.lage or '',
        # Positionen
        'umlagefaehig': [_pos_row(p, vs_names) for p in uf],
        'nicht_umlagefaehig': [_pos_row(p, vs_names) for p in nuf],
        'summe_uf_gesamt': _fmt(summe(uf, 'gesamtkosten')),
        'summe_uf_anteil': _fmt(summe(uf, 'betrag')),
        'summe_nuf_gesamt': _fmt(summe(nuf, 'gesamtkosten')),
        'summe_nuf_anteil': _fmt(summe(nuf, 'betrag')),
        # Rücklage
        'ruecklage_gesamt': _fmt(obj_reserve),
        'ruecklage_basis': r_basis,
        'ruecklage_anteil': r_anteil,
        'ruecklage_ihr_anteil': _fmt(ea.ruecklagen_zufuehrung_gesamt),
        # Summen
        'abr_summe_gesamt': _fmt(obj_kosten + obj_reserve),
        'abr_summe_anteil': _fmt(ea.kostenanteil_gesamt + ea.ruecklagen_zufuehrung_gesamt),
        'abr_spitze_gesamt': _fmt(obj_kosten + obj_reserve - obj_hg_soll),
        'hg_soll_gesamt': _fmt(obj_hg_soll),
        'hg_soll_anteil': _fmt(ea.hausgeld_soll_gesamt),
        'spitze_label': ergebnis_label,
        'spitze_anteil': _fmt(abs(ergebnis)),
        # Nachrichtlich
        'rueckstand': _fmt(rueckstand),
        'saldo': _fmt(abs(saldo)),
        'saldo_label': 'Rückstand' if saldo > 0 else ('Guthaben' if saldo < 0 else 'ausgeglichen'),
        # Erklärung
        'vs_erklaerung': vs_erklaerung,
        'fehler_positionen': fehler_positionen,
        'hinweis_eigentuemerwechsel': ea.hinweis_eigentuemerwechsel,
    }
    html = render_to_string('jahresabrechnung/einzelabrechnung.html', context)
    return weasyprint.HTML(string=html).write_pdf()


def rendere_und_speichere(ea: EinzelAbrechnung, user=None) -> Dokument:
    """
    Schritt 8: finales PDF rendern und als Dokument persistieren.
    Verknüpfung zur EinzelAbrechnung setzt der Aufrufer (freigabe_service)
    über ea.dokument.
    """
    ja = ea.jahresabrechnung
    pdf_bytes = render_einzelabrechnung_pdf(ea, entwurf=False)
    dateiname = (
        f"JA_{ja.objekt.objektnummer}_{ea.einheit.einheit_nr}_"
        f"{ja.wirtschaftsjahr.jahr}.pdf"
    )
    dokument = Dokument.objects.create(
        datei=ContentFile(pdf_bytes, name=dateiname),
        dateiname=dateiname,
        kategorie='Jahresabrechnung',
        beschreibung=(
            f"Einzelabrechnung {ja.wirtschaftsjahr.jahr} — "
            f"Einheit {ea.einheit.einheit_nr}, {ea.eigentuemer}"
        ),
        verknuepfung_typ='einzelabrechnung',
        objekt=ja.objekt,
        einheit=ea.einheit,
        hochgeladen_von=user or ja.erstellt_von,
    )
    return dokument
