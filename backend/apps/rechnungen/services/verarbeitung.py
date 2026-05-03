"""
Rechnungsverarbeitung: Duplikat-Erkennung, Kreditor-Abgleich, DB-Speicherung.
Portiert aus DOPRE/db.py + service.py, nutzt Django ORM statt pg8000.
"""
import logging
import shutil
import time
from decimal import Decimal
from pathlib import Path

from django.db import transaction

import re

logger = logging.getLogger(__name__)

from apps.rechnungen.models import Kreditor, KreditorRegel, Rechnung, Verarbeitungslog
from apps.rechnungen.services.invoice_parser import (
    extract_invoice_data, get_file_hash,
)

ERLAUBTE_ENDUNGEN = {'.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.tif'}
PFLICHTFELDER = {
    'invoice_number': 'Rechnungsnummer',
    'gross_amount': 'Bruttobetrag',
}


# ---------------------------------------------------------------------------
# Kreditor-Abgleich
# ---------------------------------------------------------------------------

def finde_oder_erstelle_kreditor(supplier: str, supplier_normalized: str, iban: str) -> Kreditor | None:
    if not supplier:
        return None

    if iban:
        k = Kreditor.objects.filter(iban=iban, aktiv=True).first()
        if k:
            return k

    if supplier_normalized:
        k = Kreditor.objects.filter(name_normalisiert=supplier_normalized, aktiv=True).first()
        if k:
            return k

    # Neu anlegen
    kwargs = {
        'name': supplier,
        'name_normalisiert': supplier_normalized or '',
    }
    if iban:
        kwargs['iban'] = iban
    return Kreditor.objects.create(**kwargs)


# ---------------------------------------------------------------------------
# Objekt-Erkennung anhand Liegenschaftsadresse
# ---------------------------------------------------------------------------

def _normalisiere_strasse(s: str) -> str:
    if not s:
        return ''
    s = s.lower().strip()
    s = re.sub(r'str\.\s*', 'straße ', s)
    s = re.sub(r'\s+', ' ', s)
    return s


def finde_objekt_fuer_adresse(address: str):
    """Versucht anhand einer Adresse das passende Objekt zu finden."""
    if not address:
        return None
    from apps.objekte.models import Eingang
    addr_norm = _normalisiere_strasse(address)
    treffer = []
    for eingang in Eingang.objects.select_related('objekt').filter(objekt__status='aktiv'):
        strasse_norm = _normalisiere_strasse(eingang.strasse)
        if not strasse_norm:
            continue
        strasse_ohne_nr = re.sub(r'\s*\d+.*$', '', strasse_norm).strip()
        if not strasse_ohne_nr or strasse_ohne_nr not in addr_norm:
            continue
        # Straße passt — PLZ als Bonus-Punkt, aber kein Pflichtkriterium
        score = 1
        if eingang.plz and eingang.plz in address:
            score += 1
        if eingang.ort and eingang.ort.lower() in address.lower():
            score += 1
        treffer.append((score, eingang.objekt))
    if treffer:
        treffer.sort(key=lambda x: x[0], reverse=True)
        return treffer[0][1]
    return None


# ---------------------------------------------------------------------------
# Duplikat-Erkennung (5-stufig wie DOPRE)
# ---------------------------------------------------------------------------

def _finde_duplikat_hash(sha256: str) -> Rechnung | None:
    return Rechnung.objects.filter(
        sha256_hash=sha256
    ).exclude(status='duplikat').first()


def _finde_duplikat_rechnungsnummer(nr_norm: str) -> Rechnung | None:
    if not nr_norm:
        return None
    return Rechnung.objects.filter(
        rechnungsnummer_normalisiert=nr_norm
    ).exclude(status='duplikat').first()


def _finde_duplikat_iban(iban: str, betrag: Decimal, datum) -> Rechnung | None:
    if not iban:
        return None
    qs = Rechnung.objects.filter(lieferant_iban=iban).exclude(status='duplikat')
    if betrag and datum:
        r = qs.filter(betrag_brutto=betrag, rechnungsdatum=datum).first()
        if r:
            return r
    if betrag:
        return qs.filter(betrag_brutto=betrag).first()
    return None


def _finde_prueffall(betrag: Decimal, lieferant_norm: str, datum) -> Rechnung | None:
    if betrag is None:
        return None
    qs = Rechnung.objects.filter(betrag_brutto=betrag).exclude(status='duplikat')
    if lieferant_norm and datum:
        r = qs.filter(lieferant_normalisiert=lieferant_norm, rechnungsdatum=datum).first()
        if r:
            return r
    if datum:
        r = qs.filter(rechnungsdatum=datum).first()
        if r:
            return r
    if lieferant_norm:
        return qs.filter(lieferant_normalisiert=lieferant_norm).first()
    return None


# ---------------------------------------------------------------------------
# Kreditor-Regel: Objekt + Konto aus gelernten Zuordnungen
# ---------------------------------------------------------------------------

def _wende_kreditor_regel_an(kreditor, kundennummer: str):
    """Sucht eine gelernte Regel (Kreditor + Kundennummer) und gibt (objekt, konto) zurück."""
    if not kreditor:
        return None, None
    if kundennummer:
        regel = KreditorRegel.objects.filter(kreditor=kreditor, kundennummer=kundennummer).first()
        if regel:
            return regel.objekt, regel.konto
    # Fallback: allgemeine Regel ohne Kundennummer
    regel = KreditorRegel.objects.filter(kreditor=kreditor, kundennummer='').first()
    if regel:
        return regel.objekt, regel.konto
    return None, None


def _vorschlage_konto_ki(leistungsbeschreibung: str, objekt):
    """KI-Vorschlag: passendes Aufwandskonto anhand der Leistungsbeschreibung."""
    from apps.konten.models import Konto
    from django.conf import settings

    if not leistungsbeschreibung or not objekt:
        return None
    konten = list(Konto.objects.filter(objekt=objekt, direktes_buchen=True, aktiv=True)[:80])
    if not konten:
        return None
    konten_text = "\n".join(f"{k.kontonummer}: {k.kontoname}" for k in konten)
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=getattr(settings, 'ANTHROPIC_API_KEY', ''))
        response = client.messages.create(
            model=getattr(settings, 'ANTHROPIC_MODEL', 'claude-sonnet-4-6'),
            max_tokens=20,
            messages=[{'role': 'user', 'content':
                f"Welches Buchungskonto (nur Kontonummer) passt zur Leistung: "
                f"'{leistungsbeschreibung[:400]}'\n\nKontenplan:\n{konten_text[:2000]}\n\n"
                f"Antworte NUR mit der Kontonummer, sonst nichts."
            }]
        )
        nr = response.content[0].text.strip()
        return next((k for k in konten if k.kontonummer == nr), None)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Haupt-Verarbeitungsfunktion
# ---------------------------------------------------------------------------

def verarbeite_datei(datei_pfad: str, archiv_root: Path) -> dict:
    """
    Verarbeitet eine Rechnungsdatei:
    - OCR + KI-Parsing
    - Duplikat-Erkennung
    - Kreditor-Abgleich / Neuanlage
    - DB-Speicherung
    - Datei ins Archiv verschieben

    Gibt Status-Dict zurück.
    """
    pfad = Path(datei_pfad)
    dateiname = pfad.name
    ext = pfad.suffix.lower()

    if ext not in ERLAUBTE_ENDUNGEN:
        return {'status': 'ignoriert', 'dateiname': dateiname, 'notiz': f'Dateityp nicht unterstützt: {ext}'}

    sha256 = get_file_hash(datei_pfad)
    parsed = extract_invoice_data(datei_pfad)

    # Pflichtfeld-Prüfung
    fehlende = [label for key, label in PFLICHTFELDER.items() if not parsed.get(key)]

    with transaction.atomic():
        status = 'importiert'
        duplikat_typ = ''
        duplikat_von = None
        notiz = 'Neue Rechnung verarbeitet'

        # Kreditor
        kundennummer = parsed.get('customer_number') or ''
        kreditor = finde_oder_erstelle_kreditor(
            parsed.get('supplier'),
            parsed.get('supplier_normalized'),
            parsed.get('iban'),
        )

        # Objekt + Konto: erst Regel, dann Adress-Erkennung
        objekt, vorgeschlagenes_konto = _wende_kreditor_regel_an(kreditor, kundennummer)
        if not objekt:
            objekt = finde_objekt_fuer_adresse(parsed.get('property_address') or '')
        if not vorgeschlagenes_konto and objekt:
            vorgeschlagenes_konto = _vorschlage_konto_ki(
                parsed.get('description') or '', objekt
            )

        if fehlende:
            status = 'prueffall'
            duplikat_typ = 'ocr_unvollstaendig'
            notiz = f'OCR unvollständig: {", ".join(fehlende)}'
        else:
            # Stufe 1: Hash
            dup = _finde_duplikat_hash(sha256)
            if dup:
                status, duplikat_typ, duplikat_von = 'duplikat', 'hash', dup
                notiz = f'Exaktes Duplikat: {dup.dateiname}'
            # Stufe 2: Rechnungsnummer
            elif parsed.get('invoice_number_normalized'):
                dup = _finde_duplikat_rechnungsnummer(parsed['invoice_number_normalized'])
                if dup:
                    status, duplikat_typ, duplikat_von = 'duplikat', 'rechnungsnummer', dup
                    notiz = f'Gleiche Rechnungsnummer: {dup.dateiname}'
            # Stufe 3: IBAN + Betrag + Datum
            if status == 'importiert' and parsed.get('iban') and parsed.get('gross_amount'):
                dup = _finde_duplikat_iban(parsed['iban'], parsed['gross_amount'], parsed.get('invoice_date'))
                if dup:
                    status, duplikat_typ, duplikat_von = 'duplikat', 'iban_betrag_datum', dup
                    notiz = f'IBAN+Betrag+Datum Duplikat: {dup.dateiname}'
            # Stufe 4: Fuzzy
            if status == 'importiert' and parsed.get('gross_amount') and parsed.get('supplier_normalized'):
                dup = _finde_prueffall(parsed['gross_amount'], parsed['supplier_normalized'], parsed.get('invoice_date'))
                if dup:
                    status, duplikat_typ, duplikat_von = 'prueffall', 'unscharf', dup
                    notiz = f'Mögliches Duplikat (unscharf): {dup.dateiname}'

        # Zielordner bestimmen
        if status == 'duplikat':
            ziel_ordner = archiv_root / 'duplikate'
        elif status == 'prueffall':
            ziel_ordner = archiv_root / 'prueffaelle'
        else:
            from datetime import date
            heute = date.today()
            ziel_ordner = archiv_root / str(heute.year) / f'{heute.month:02d}'

        ziel_ordner.mkdir(parents=True, exist_ok=True)
        ziel_pfad = ziel_ordner / dateiname
        if ziel_pfad.exists():
            ziel_pfad = ziel_ordner / f'{pfad.stem}_{int(time.time())}{pfad.suffix}'
        shutil.move(str(pfad), str(ziel_pfad))

        rechnung = Rechnung.objects.create(
            dateiname=dateiname,
            pfad=str(ziel_pfad),
            objekt=objekt,
            sha256_hash=sha256,
            status=status,
            duplikat_typ=duplikat_typ,
            duplikat_von=duplikat_von,
            kreditor=kreditor,
            lieferant_name=parsed.get('supplier') or '',
            lieferant_normalisiert=parsed.get('supplier_normalized') or '',
            lieferant_iban=parsed.get('iban') or '',
            rechnungsnummer=parsed.get('invoice_number') or '',
            rechnungsnummer_normalisiert=parsed.get('invoice_number_normalized') or '',
            rechnungsdatum=parsed.get('invoice_date'),
            faelligkeitsdatum=parsed.get('due_date'),
            betrag_brutto=parsed.get('gross_amount'),
            betrag_netto=parsed.get('net_amount'),
            mwst_satz=parsed.get('vat_rate'),
            waehrung=parsed.get('currency') or 'EUR',
            leistungsbeschreibung=parsed.get('description') or '',
            leistungstext=parsed.get('description') or '',
            textauszug=(parsed.get('text') or '')[:5000],
            verarbeitungsnotiz=notiz,
            kundennummer=kundennummer,
            vorgeschlagenes_konto=vorgeschlagenes_konto,
        )

        Verarbeitungslog.objects.create(
            rechnung=rechnung,
            aktion='Datei verarbeitet',
            status=status,
            details=notiz,
        )

    # Nach dem Commit: 3-stufige Erkennungspipeline für neue (nicht-Duplikat) Rechnungen
    if rechnung.status == 'importiert':
        try:
            from apps.rechnungen.recognition import fuehre_erkennung_aus
            fuehre_erkennung_aus(rechnung)
            status = rechnung.status
            notiz = rechnung.verarbeitungsnotiz or notiz
        except Exception as exc:
            logger.warning('Erkennungs-Pipeline Fehler bei %s: %s', dateiname, exc)

    return {
        'status': status,
        'dateiname': dateiname,
        'notiz': notiz,
        'rechnung_id': str(rechnung.id),
        'kreditor': kreditor.name if kreditor else None,
        'objekt': objekt.bezeichnung if objekt else None,
    }
