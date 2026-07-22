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
from django.template.loader import render_to_string
import weasyprint

from apps.buchhaltung.models import EinzelAbrechnung
from apps.dokumente.models import Dokument


def _fmt(v) -> str:
    """Decimal/str → deutsches Format '1.234,56'."""
    return f"{float(Decimal(str(v))):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def render_einzelabrechnung_pdf(ea: EinzelAbrechnung, entwurf: bool = True) -> bytes:
    """Rendert das PDF einer EinzelAbrechnung (Schritt 7: entwurf=True)."""
    ja = ea.jahresabrechnung
    wj = ja.wirtschaftsjahr
    objekt = ja.objekt

    positionen = []
    for p in ea.positionen:
        if p.get('fehler'):
            # Fehler-Positionen erscheinen nicht im PDF — Freigabe ist ohnehin
            # blockiert (positionen_hat_fehler), Vorschau zeigt den Rest.
            continue
        positionen.append({
            'kontonummer': p['kontonummer'],
            'kontoname': p['kontoname'],
            'vs_code': p.get('vs_code'),
            'gesamtkosten': _fmt(p['gesamtkosten']),
            'anteil': p.get('anteil', '—'),
            'betrag': _fmt(p['betrag']),
        })

    ruecklagen = []
    for r in ea.ruecklagen:
        ruecklagen.append({
            'bezeichnung': r['bezeichnung'],
            'anfangsbestand': _fmt(r['anfangsbestand']),
            'zufuehrungen': _fmt(r['zufuehrungen']),
            'entnahmen': _fmt(r['entnahmen']),
            'endbestand': _fmt(r['endbestand']),
            'anteil_eigentuemer': (
                _fmt(r['anteil_eigentuemer']) if r.get('anteil_eigentuemer') else None
            ),
        })

    ergebnis = ea.abrechnungsergebnis
    if ergebnis > 0:
        ergebnis_label = 'Nachzahlung'
    elif ergebnis < 0:
        ergebnis_label = 'Guthaben'
    else:
        ergebnis_label = 'Abrechnungsergebnis'

    context = {
        'objekt': objekt,
        'wj': wj,
        'einheit': ea.einheit,
        'person_name': str(ea.eigentuemer),
        'zeitraum_von': wj.beginn_datum.strftime('%d.%m.%Y'),
        'zeitraum_bis': wj.ende_datum.strftime('%d.%m.%Y'),
        'positionen': positionen,
        'ruecklagen': ruecklagen,
        'kostenanteil_gesamt': _fmt(ea.kostenanteil_gesamt),
        'hausgeld_soll_gesamt': _fmt(ea.hausgeld_soll_gesamt),
        'abrechnungsergebnis': _fmt(abs(ergebnis)),
        'ergebnis_label': ergebnis_label,
        'hinweis_eigentuemerwechsel': ea.hinweis_eigentuemerwechsel,
        'erstellt_am': date.today().strftime('%d.%m.%Y'),
        'ist_entwurf': entwurf,
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
