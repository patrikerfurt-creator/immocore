"""
WKZ Bank-Match — Zuordnung eingehender Kontoumsätze zu offenen WKZ-OPs.

Rein lesender Service (schreibt nichts in die DB);
ordne_auto_zu schreibt nur ki_vorschlag auf den Kontoumsatz.
"""
import logging
import re
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _extrahiere_mandats_id(verwendungszweck: str) -> Optional[str]:
    """
    Versucht eine SEPA-Mandats-ID aus dem Verwendungszweck zu lesen.
    SEPA-Structured: MREF/ oder MNDTID/
    """
    if not verwendungszweck:
        return None
    for pattern in (
        r'MREF/([A-Za-z0-9+?:().,\- ]{1,35})(?:/|$)',
        r'MNDTID/([A-Za-z0-9+?:().,\- ]{1,35})(?:/|$)',
    ):
        m = re.search(pattern, verwendungszweck)
        if m:
            return m.group(1).strip()
    return None


def identifiziere_kreditor_aus_eingang(kontoumsatz) -> Optional['Kreditor']:
    """
    Versucht zuerst Mandats-ID-Match (aus Verwendungszweck),
    dann IBAN-Match gegen Kreditor.iban.

    kontoumsatz: Kontoumsatz-Instanz
    """
    from apps.rechnungen.models import Kreditor
    from apps.buchhaltung.models import WiederkehrendeBuchungVorlage

    # 1. Mandats-ID aus Verwendungszweck
    mandat_id = _extrahiere_mandats_id(kontoumsatz.verwendungszweck)
    if mandat_id:
        vorlage = WiederkehrendeBuchungVorlage.objects.filter(
            sepa_mandat_id=mandat_id,
            status__in=('aktiv', 'pausiert'),
        ).select_related('kreditor').first()
        if vorlage:
            logger.debug(
                "WKZ Bank-Match: Kreditor %s via MandatID %s gefunden",
                vorlage.kreditor, mandat_id
            )
            return vorlage.kreditor

    # 2. IBAN-Match: auftraggeber_iban und empfaenger_iban prüfen
    for iban_field in ('auftraggeber_iban', 'empfaenger_iban'):
        iban = getattr(kontoumsatz, iban_field, '').strip()
        if iban:
            kreditor = Kreditor.objects.filter(iban=iban, aktiv=True).first()
            if kreditor:
                logger.debug(
                    "WKZ Bank-Match: Kreditor %s via IBAN %s (%s) gefunden",
                    kreditor, iban, iban_field
                )
                return kreditor

    return None


# ---------------------------------------------------------------------------
# Kandidaten finden
# ---------------------------------------------------------------------------

def finde_kandidaten(kontoumsatz) -> list:
    """
    Gibt alle offenen WiederkehrendeBuchungOPs zurück, die zum Kontoumsatz
    passen (Kreditor + Objekt + Betragsfenster + Zeitfenster).

    Gibt [] zurück, wenn kein Kreditor identifizierbar.
    """
    from apps.buchhaltung.models import WiederkehrendeBuchungOP

    kreditor = identifiziere_kreditor_aus_eingang(kontoumsatz)
    if not kreditor:
        return []

    bank_betrag = abs(kontoumsatz.betrag)
    bank_datum = kontoumsatz.buchungsdatum

    # Basis-Filterprimär über Objekt + Kreditor + Status
    qs = WiederkehrendeBuchungOP.objects.filter(
        vorlage__kreditor=kreditor,
        status__in=('erzeugt', 'bescheid_fehlt'),
    ).select_related('vorlage', 'kreditor_op')

    # Objekt einschränken über bankkonto
    if kontoumsatz.bankkonto_id:
        qs = qs.filter(vorlage__objekt__bankkonten=kontoumsatz.bankkonto)

    # Python-seitig Fenster prüfen (Toleranzen sind pro Vorlage unterschiedlich)
    kandidaten = []
    for op in qs:
        tol_betrag = op.vorlage.toleranz_betrag
        tol_tage = op.vorlage.toleranz_tage

        betrag_ok = abs(op.kreditor_op.betrag_ursprung - bank_betrag) <= tol_betrag
        datum_diff = abs((op.faellig_am - bank_datum).days)
        datum_ok = datum_diff <= tol_tage

        if betrag_ok and datum_ok:
            kandidaten.append(op)

    logger.debug(
        "WKZ Bank-Match: %s Kandidat(en) für Kontoumsatz %s (Kreditor %s)",
        len(kandidaten), kontoumsatz.pk, kreditor
    )
    return kandidaten


# ---------------------------------------------------------------------------
# Match-Entscheidung
# ---------------------------------------------------------------------------

def ist_eindeutiger_auto_match(kandidat, kontoumsatz) -> bool:
    """
    Prüft, ob der Betrag innerhalb der 1%-Schwelle liegt
    (konservative Auto-Verbucher-Grenze laut Spec Kap. 6.3).
    """
    bank_betrag = abs(kontoumsatz.betrag)
    erwarteter_betrag = kandidat.kreditor_op.betrag_ursprung

    if erwarteter_betrag == Decimal('0'):
        return False

    abweichung_relativ = abs(bank_betrag - erwarteter_betrag) / erwarteter_betrag
    return abweichung_relativ <= Decimal('0.01')


def ordne_auto_zu(kontoumsatz, wkz_op) -> None:
    """
    Setzt ki_vorschlag auf dem Kontoumsatz für eine automatische
    WKZ-Zuordnung. Ändert noch nichts an den Buchungen.
    """
    kontoumsatz.ki_vorschlag = {
        'typ': 'wkz',
        'stufe': 0,
        'wkz_op_id': str(wkz_op.id),
        'vorlage_id': str(wkz_op.vorlage_id),
        'kreditor': str(wkz_op.vorlage.kreditor),
        'periode_von': str(wkz_op.periode_von),
        'periode_bis': str(wkz_op.periode_bis),
        'erwarteter_betrag': str(wkz_op.kreditor_op.betrag_ursprung),
        'konfidenz': 'hoch',
    }
    kontoumsatz.status = 'erkannt'
    kontoumsatz.save(update_fields=['ki_vorschlag', 'status'])
    logger.info(
        "WKZ Bank-Match: Kontoumsatz %s auto-zugeordnet zu WKZ-OP %s",
        kontoumsatz.pk, wkz_op.id
    )


def baue_vorschlag(kontoumsatz, kandidaten: list) -> dict:
    """
    Erzeugt den ki_vorschlag-Dict für mehrdeutige Matches
    (Frontoffice-Darstellung).
    """
    return {
        'typ': 'wkz',
        'stufe': 0,
        'konfidenz': 'mittel',
        'kandidaten': [
            {
                'wkz_op_id': str(op.id),
                'vorlage_id': str(op.vorlage_id),
                'bezeichnung': op.vorlage.bezeichnung,
                'kreditor': str(op.vorlage.kreditor),
                'periode_von': str(op.periode_von),
                'periode_bis': str(op.periode_bis),
                'faellig_am': str(op.faellig_am),
                'erwarteter_betrag': str(op.kreditor_op.betrag_ursprung),
                'status': op.status,
            }
            for op in kandidaten
        ],
    }
