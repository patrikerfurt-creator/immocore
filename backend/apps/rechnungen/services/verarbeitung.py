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

from apps.dokumente.services.beleg_service import koppel_rechnungsbeleg
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
# Systembenutzer für automatische Beleg-Kopplung (v1_1 Phase A)
# ---------------------------------------------------------------------------

def _system_user():
    """Löst den Systembenutzer für die automatische Beleg-Kopplung auf.

    Reihenfolge wie migriere_rechnungsbelege._resolve_user / autopipeline_lauf:
    'immocore-autopilot' > erster Superuser > None (Aufrufer muss die
    Kopplung dann überspringen).
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = User.objects.filter(username='immocore-autopilot').first()
    if user:
        return user
    return User.objects.filter(is_superuser=True).order_by('pk').first()


# ---------------------------------------------------------------------------
# Kreditor-Abgleich
# ---------------------------------------------------------------------------

def gleiche_kreditor_ab(supplier: str, iban: str):
    """Abgleich OHNE Nebenwirkung — legt nichts an.

    Liefert ein ``AbgleichErgebnis`` mit genau einem von drei Zuständen
    (sicher / verdacht / neu). Der Aufrufer entscheidet, was daraus folgt:
    verwenden, anhalten oder anlegen.
    """
    from .kreditor_matching import AbgleichErgebnis, gleiche_kreditoren

    if not supplier:
        return AbgleichErgebnis()
    return gleiche_kreditoren(supplier, iban or '')


def finde_oder_erstelle_kreditor(supplier: str, supplier_normalized: str, iban: str) -> Kreditor | None:
    """Sicheren Treffer liefern oder neu anlegen — OHNE Dubletten-Sperre.

    Bleibt für Aufrufer erhalten, die keinen Prüffall erzeugen können
    (z.B. die manuelle Erfassung, wo direkt am Bildschirm entschieden
    wird). Der automatische Import nutzt stattdessen
    ``gleiche_kreditor_ab`` und hält Verdachtsfälle an — sonst entstünden
    weiter unbemerkt Doppelungen.

    ``supplier_normalized`` wird nicht mehr ausgewertet:
    ``name_normalisiert`` entsteht seit der Vereinheitlichung
    ausschließlich in ``Kreditor.save()``.
    """
    ergebnis = gleiche_kreditor_ab(supplier, iban)
    if ergebnis.sicher:
        return ergebnis.kreditor
    if not supplier:
        return None

    # Verdachtsfälle landen hier nur, wenn der Aufrufer sie bewusst nicht
    # anhält: dann ist der beste aktive Kandidat immer noch besser als
    # eine stille Neuanlage.
    for kandidat in ergebnis.kandidaten:
        if kandidat.kreditor.aktiv and kandidat.match_typ in ('iban', 'iban_zweitkonto', 'name_exakt'):
            return kandidat.kreditor

    kwargs = {'name': supplier}
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


def _finde_duplikat_iban(iban: str, betrag: Decimal, datum, nr_norm: str = '') -> Rechnung | None:
    if not iban:
        return None
    qs = Rechnung.objects.filter(lieferant_iban=iban).exclude(status='duplikat')
    # Wenn Rechnungsnummer erkannt: nur Treffer mit gleicher Nummer zulassen
    if nr_norm:
        qs = qs.filter(rechnungsnummer_normalisiert=nr_norm)
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
    from django.db.models import Q
    konten = list(Konto.objects.filter(
        wirtschaftsjahr__objekt=objekt,
        aktiv=True,
    ).exclude(
        kontoart='summierung',
    ).filter(
        Q(direktes_buchen=True) | Q(kontonummer__gte='50000', kontonummer__lte='55999')
    )[:80])
    if not konten:
        return None
    konten_text = "\n".join(f"{k.kontonummer}: {k.kontoname}" for k in konten)
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=getattr(settings, 'ANTHROPIC_API_KEY', ''))
        response = client.messages.create(
            model=getattr(settings, 'ANTHROPIC_MODEL', 'claude-sonnet-4-6'),
            max_tokens=1500,  # claude-sonnet-5 denkt zuerst — Budget für Thinking + kurze Antwort
            messages=[{'role': 'user', 'content':
                f"Welches Buchungskonto (nur Kontonummer) passt zur Leistung: "
                f"'{leistungsbeschreibung[:400]}'\n\nKontenplan:\n{konten_text[:2000]}\n\n"
                f"Antworte NUR mit der Kontonummer, sonst nichts."
            }]
        )
        nr = next((b.text for b in response.content if getattr(b, 'type', None) == 'text'), '').strip()
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

        # Kreditor — Verdachtsfälle werden angehalten statt still angelegt.
        kundennummer = parsed.get('customer_number') or ''
        abgleich = gleiche_kreditor_ab(parsed.get('supplier'), parsed.get('iban'))
        if abgleich.sicher:
            kreditor = abgleich.kreditor
        elif abgleich.verdacht:
            # Kein Kreditor: die Rechnung bleibt ohne und damit nicht buchbar,
            # bis jemand entschieden hat (Prüffall wird nach dem Anlegen der
            # Rechnung erzeugt — er braucht deren ID).
            kreditor = None
        elif parsed.get('supplier'):
            kwargs = {'name': parsed['supplier']}
            if parsed.get('iban'):
                kwargs['iban'] = parsed['iban']
            kreditor = Kreditor.objects.create(**kwargs)
        else:
            kreditor = None

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
        elif abgleich.verdacht:
            # Vor der Duplikat-Erkennung: ein ungeklärter Kreditor macht
            # jede weitere Zuordnung (Objekt, Konto, Buchung) wertlos.
            status = 'prueffall'
            duplikat_typ = 'kreditor_dublette'
            bester = abgleich.kandidaten[0]
            notiz = (
                f'Kreditor-Dublettenverdacht ({abgleich.anlass}): '
                f'ähnelt "{bester.kreditor.name}" '
                f'[{bester.kreditor.kreditorennummer or "ohne Nummer"}]'
            )
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
            # Stufe 3: IBAN + Betrag + Datum (+ Rechnungsnummer wenn vorhanden)
            if status == 'importiert' and parsed.get('iban') and parsed.get('gross_amount'):
                dup = _finde_duplikat_iban(
                    parsed['iban'],
                    parsed['gross_amount'],
                    parsed.get('invoice_date'),
                    parsed.get('invoice_number_normalized', ''),
                )
                if dup:
                    status, duplikat_typ, duplikat_von = 'duplikat', 'iban_betrag_datum', dup
                    notiz = f'IBAN+Betrag+Datum Duplikat: {dup.dateiname}'
            # Stufe 4: Fuzzy — nur wenn keine Rechnungsnummer erkannt (erkannte Nr. ist stärkerer Beweis)
            if status == 'importiert' and not parsed.get('invoice_number_normalized') and parsed.get('gross_amount') and parsed.get('supplier_normalized'):
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

        ist_gutschrift = parsed.get('is_credit_note', False)
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
            betrag_brutto=parsed.get('gross_amount'),   # immer positiv (abs-Wert)
            betrag_netto=parsed.get('net_amount'),       # immer positiv (abs-Wert)
            mwst_satz=parsed.get('vat_rate'),
            waehrung=parsed.get('currency') or 'EUR',
            leistungsbeschreibung=parsed.get('description') or '',
            leistungstext=parsed.get('description') or '',
            textauszug=(parsed.get('text') or '')[:5000],
            verarbeitungsnotiz=notiz,
            kundennummer=kundennummer,
            vorgeschlagenes_konto=vorgeschlagenes_konto,
            ist_gutschrift=ist_gutschrift,
        )

        # Dublettenprüfung anlegen — braucht die Rechnungs-ID, deshalb erst
        # hier. Die Rechnung hat in diesem Fall bewusst keinen Kreditor.
        if abgleich.verdacht:
            from .kreditor_dubletten import lege_pruefung_an
            lege_pruefung_an(
                rechnung, abgleich,
                parsed.get('supplier') or '', parsed.get('iban') or '',
            )

        # Beleg-Dokument koppeln (v1_1 Phase A) — darf den Rechnungseingang nie
        # blockieren, daher eigener Savepoint (die äußere Transaktion bleibt
        # sonst nach einer Exception "kaputt" und der Log-Eintrag/Commit unten
        # würde ebenfalls scheitern).
        try:
            with transaction.atomic():
                sys_user = _system_user()
                if sys_user is None:
                    raise ValueError("Kein Systembenutzer für Beleg-Kopplung gefunden.")
                dok = koppel_rechnungsbeleg(rechnung, hochgeladen_von=sys_user)
                Verarbeitungslog.objects.create(rechnung=rechnung, aktion='Beleg-Dokument angelegt',
                                                status=rechnung.status, details=dok.beleg_nummer)
        except Exception as exc:
            logger.warning('Beleg-Kopplung fehlgeschlagen für Rechnung %s: %s', rechnung.id, exc)
            Verarbeitungslog.objects.create(rechnung=rechnung, aktion='Beleg-Kopplung fehlgeschlagen',
                                            status=rechnung.status, details=str(exc)[:500])

        Verarbeitungslog.objects.create(
            rechnung=rechnung,
            aktion='Datei verarbeitet',
            status=status,
            details=notiz,
        )

    # Nach dem Commit: 3-stufige Erkennungspipeline für neue (nicht-Duplikat)
    # Rechnungen. v1.1 Phase D: der Auto-Buchungs-Zweig (op_freigeben ohne
    # Nutzer bei status 'gebucht') wurde entfernt — route_rechnung endet
    # immer in Stufe 1 (in_buchhaltung), gebucht wird erst in Stufe 2.
    if rechnung.status == 'importiert':
        try:
            from apps.rechnungen.recognition import fuehre_erkennung_aus
            fuehre_erkennung_aus(rechnung)
            status = rechnung.status
            notiz = rechnung.verarbeitungsnotiz or notiz
        except Exception as exc:
            logger.warning('Erkennungs-Pipeline Fehler bei %s: %s', dateiname, exc)

        # Erkennungs-Ampel direkt mitberechnen. Sie wird sonst erst beim
        # Speichern über die API gesetzt — importierte Rechnungen erscheinen
        # in der Oberfläche bis dahin als „Noch nicht bewertet", obwohl alle
        # Felder erkannt sind.
        try:
            from apps.rechnungen.services.erkennung_ampel_service import (
                berechne_und_speichere_ampel,
            )
            berechne_und_speichere_ampel(rechnung)
            rechnung.save(update_fields=[
                'erkennung_ampel', 'erkennung_gesamt_konfidenz', 'erkennung_details',
            ])
        except Exception as exc:
            logger.warning('Ampel-Berechnung fehlgeschlagen bei %s: %s', dateiname, exc)

    return {
        'status': status,
        'dateiname': dateiname,
        'notiz': notiz,
        'rechnung_id': str(rechnung.id),
        'kreditor': kreditor.name if kreditor else None,
        'objekt': objekt.bezeichnung if objekt else None,
    }


@transaction.atomic
def ocr_erneut_ausfuehren(rechnung: Rechnung) -> Rechnung:
    """
    Führt OCR + Erkennungs-Pipeline erneut für eine bereits importierte Rechnung aus.
    Gedacht für Rechnungen die beim Import kein Internet hatten (ocr_unvollstaendig).
    """
    from apps.rechnungen.recognition import fuehre_erkennung_aus

    parsed = extract_invoice_data(rechnung.pfad)
    fehlende = [label for key, label in PFLICHTFELDER.items() if not parsed.get(key)]

    kundennummer = parsed.get('customer_number') or ''
    # Auch der Wiederholungslauf hält Verdachtsfälle an — sonst wäre er ein
    # Schlupfloch, durch das genau die Doppelungen entstehen, die der
    # Erstimport verhindert.
    abgleich = gleiche_kreditor_ab(parsed.get('supplier'), parsed.get('iban'))
    if abgleich.sicher:
        kreditor = abgleich.kreditor
    elif abgleich.verdacht:
        kreditor = None
        from .kreditor_dubletten import lege_pruefung_an
        lege_pruefung_an(
            rechnung, abgleich,
            parsed.get('supplier') or '', parsed.get('iban') or '',
        )
    elif parsed.get('supplier'):
        kwargs = {'name': parsed['supplier']}
        if parsed.get('iban'):
            kwargs['iban'] = parsed['iban']
        kreditor = Kreditor.objects.create(**kwargs)
    else:
        kreditor = None

    objekt, vorgeschlagenes_konto = _wende_kreditor_regel_an(kreditor, kundennummer)
    if not objekt:
        objekt = finde_objekt_fuer_adresse(parsed.get('property_address') or '')
    if not vorgeschlagenes_konto and objekt:
        vorgeschlagenes_konto = _vorschlage_konto_ki(parsed.get('description') or '', objekt)

    rechnung.lieferant_name          = parsed.get('supplier') or ''
    rechnung.lieferant_normalisiert  = parsed.get('supplier_normalized') or ''
    rechnung.lieferant_iban          = parsed.get('iban') or ''
    rechnung.rechnungsnummer         = parsed.get('invoice_number') or ''
    rechnung.rechnungsnummer_normalisiert = parsed.get('invoice_number_normalized') or ''
    rechnung.rechnungsdatum          = parsed.get('invoice_date')
    rechnung.faelligkeitsdatum       = parsed.get('due_date')
    rechnung.betrag_brutto           = parsed.get('gross_amount')   # immer positiv (abs-Wert)
    rechnung.betrag_netto            = parsed.get('net_amount')      # immer positiv (abs-Wert)
    rechnung.mwst_satz               = parsed.get('vat_rate')
    rechnung.leistungsbeschreibung   = parsed.get('description') or ''
    rechnung.leistungstext           = parsed.get('description') or ''
    rechnung.textauszug              = (parsed.get('text') or '')[:5000]
    rechnung.kreditor                = kreditor
    rechnung.kundennummer            = kundennummer
    rechnung.ist_gutschrift          = parsed.get('is_credit_note', False)

    if fehlende:
        rechnung.verarbeitungsnotiz = f'OCR wiederholt – noch unvollständig: {", ".join(fehlende)}'
        rechnung.save()
    elif abgleich.verdacht:
        # Nicht in die Erkennungs-Pipeline schicken: ohne geklärten
        # Kreditor greifen weder Kreditor-Regel noch Kontovorschlag.
        rechnung.status = 'prueffall'
        rechnung.duplikat_typ = 'kreditor_dublette'
        bester = abgleich.kandidaten[0]
        rechnung.verarbeitungsnotiz = (
            f'Kreditor-Dublettenverdacht ({abgleich.anlass}): '
            f'ähnelt "{bester.kreditor.name}" '
            f'[{bester.kreditor.kreditorennummer or "ohne Nummer"}]'
        )
        rechnung.save()
    else:
        rechnung.status      = 'importiert'
        rechnung.duplikat_typ = ''
        rechnung.verarbeitungsnotiz = 'OCR erfolgreich wiederholt'
        if objekt and not rechnung.objekt_id:
            rechnung.objekt = objekt
        if vorgeschlagenes_konto and not rechnung.vorgeschlagenes_konto_id:
            rechnung.vorgeschlagenes_konto = vorgeschlagenes_konto
        rechnung.save()
        rechnung = fuehre_erkennung_aus(rechnung)

    Verarbeitungslog.objects.create(
        rechnung=rechnung,
        aktion='OCR wiederholt',
        status=rechnung.status,
        details=rechnung.verarbeitungsnotiz,
    )
    return rechnung
