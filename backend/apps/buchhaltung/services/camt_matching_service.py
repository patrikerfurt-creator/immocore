"""
CAMT.053 Buchungs-Matching: KreditorOP-Erkennung und Buchung (Fall 2 + 8).

Fall 2: DBIT/Einzelüberweisung → KreditorOP schließen (Phase-2/3-Buchung)
Fall 8: DBIT → Eigentümer-Erstattung (DBIT gegen Person.ibans)
"""
import logging
import re
from decimal import Decimal

from django.db import transaction

logger = logging.getLogger(__name__)


def matche_kreditor_op(umsatz):
    """
    Sucht einen offenen oder offenstehenden KreditorOP zum DBIT-Kontoumsatz.

    Matching-Stufen (absteigend nach Verlässlichkeit):
      1. Betrag + Kreditor-IBAN (exakt)
      2. Betrag + Rechnungsnummer aus Verwendungszweck

    Returns: KreditorOP oder None
    """
    from apps.buchhaltung.models import KreditorOP

    if umsatz.betrag >= 0:
        return None

    betrag = abs(umsatz.betrag)
    cdtr_iban = (umsatz.auftraggeber_iban or '').strip().replace(' ', '')

    # Stufe 1: Betrag + IBAN
    if cdtr_iban:
        ops = KreditorOP.objects.filter(
            objekt=umsatz.objekt,
            betrag_offen=betrag,
            kreditor__iban=cdtr_iban,
            status__in=('offen', 'teilbezahlt'),
        )
        if ops.count() == 1:
            return ops.first()

    # Stufe 2: Rechnungsnummer aus Verwendungszweck
    verwendungszweck = umsatz.verwendungszweck or ''
    match = re.search(r'RE[.\-]?\s*(\d+)', verwendungszweck, re.IGNORECASE)
    if match:
        re_nr = match.group(1)
        ops = KreditorOP.objects.filter(
            objekt=umsatz.objekt,
            betrag_offen=betrag,
            rechnung__rechnungsnummer__icontains=re_nr,
            status__in=('offen', 'teilbezahlt'),
        )
        if ops.count() == 1:
            return ops.first()

    return None


def matche_eigentuemer_erstattung(umsatz):
    """
    Fall 8: DBIT → Eigentümer-Erstattung (Creditor-IBAN in Person.ibans).

    Returns: (Person, EigentumsVerhaeltnis) oder None
    """
    from apps.personen.models import Person, EigentumsVerhaeltnis

    if umsatz.betrag >= 0:
        return None

    cdtr_iban = (umsatz.auftraggeber_iban or '').strip().replace(' ', '')
    if not cdtr_iban:
        return None

    for person in Person.objects.filter(person_typ='100'):
        ibans = [i.strip().replace(' ', '') for i in (person.ibans or [])]
        if cdtr_iban in ibans:
            ev = EigentumsVerhaeltnis.objects.filter(
                person=person,
                einheit__objekt=umsatz.objekt,
                ende__isnull=True,
            ).first()
            if ev:
                return person, ev

    return None


@transaction.atomic
def buche_camt_dbit_kreditor(umsatz, user) -> dict:
    """
    Fall 2: Bucht einen DBIT-Kontoumsatz gegen einen gematchten KreditorOP.

    Ablauf:
    - status='offen': rechnung_bezahlen() + bank_abgang_buchen()
    - status='bezahlt' (Zahlungslauf schon erfolgt): nur bank_abgang_buchen()

    Setzt Kontoumsatz.buchung und Kontoumsatz.status='gebucht'.

    Returns: dict mit 'rechnung_status', 'buchungen', 'op_status'
    """
    from apps.buchhaltung.models import KreditorOP
    from apps.konten.models import Konto
    from apps.rechnungen.services.rechnung_zahlung_service import (
        rechnung_bezahlen,
        bank_abgang_buchen,
    )

    kreditor_op = matche_kreditor_op(umsatz)
    if not kreditor_op:
        return {'matched': False}

    rechnung = kreditor_op.rechnung
    buchungen = []

    bank_sachkonto = _ermittle_bank_sachkonto(umsatz)
    if not bank_sachkonto:
        logger.warning(
            "camt_matching: Kein Bank-Sachkonto für Objekt %s gefunden — Buchung übersprungen",
            umsatz.objekt_id,
        )
        return {'matched': True, 'gebucht': False, 'grund': 'kein_bank_sachkonto'}

    if rechnung and kreditor_op.status in ('offen', 'teilbezahlt'):
        if rechnung.status == 'gebucht':
            buchung_aufwand, buchung_kreditor = rechnung_bezahlen(
                rechnung=rechnung,
                buchungsdatum=umsatz.buchungsdatum,
                gebucht_von=user,
            )
            buchungen.extend([buchung_aufwand, buchung_kreditor])

        if rechnung.status == 'bezahlt':
            bank_buchung = bank_abgang_buchen(
                rechnung=rechnung,
                bankkonto=bank_sachkonto,
                buchungsdatum=umsatz.buchungsdatum,
                gebucht_von=user,
            )
            buchungen.append(bank_buchung)
            umsatz.buchung = bank_buchung

    elif rechnung and kreditor_op.status == 'bezahlt':
        bank_buchung = bank_abgang_buchen(
            rechnung=rechnung,
            bankkonto=bank_sachkonto,
            buchungsdatum=umsatz.buchungsdatum,
            gebucht_von=user,
        )
        buchungen.append(bank_buchung)
        umsatz.buchung = bank_buchung

    umsatz.status = 'gebucht'
    umsatz.save(update_fields=['buchung', 'status'])

    kreditor_op.refresh_from_db()
    return {
        'matched': True,
        'gebucht': True,
        'rechnung_status': rechnung.status if rechnung else None,
        'op_status': kreditor_op.status,
        'buchungen': [str(b.id) for b in buchungen],
    }


def erkenne_dbit(umsatz) -> dict | None:
    """
    Erkennt DBIT-Transaktionen und gibt einen ki_vorschlag zurück.

    Reihenfolge:
    1. Fall 2: KreditorOP-Match
    2. Fall 8: Eigentümer-Erstattung
    """
    if umsatz.betrag >= 0:
        return None

    # Fall 2: KreditorOP-Match
    op = matche_kreditor_op(umsatz)
    if op:
        rechnung = op.rechnung
        return {
            'typ': 'kreditor_op',
            'stufe': 1,
            'konfidenz': 'hoch',
            'kreditor_op_id': str(op.id),
            'rechnung_id': str(rechnung.id) if rechnung else None,
            'kreditor_name': op.kreditor.name if op.kreditor else '',
            'betrag': str(abs(umsatz.betrag)),
            'begruendung': (
                f"IBAN {umsatz.auftraggeber_iban} → KreditorOP #{op.op_nummer} "
                f"({op.kreditor.name if op.kreditor else '?'}), {op.betrag_offen} € offen"
            ),
        }

    # Fall 8: Eigentümer-Erstattung
    ergebnis = matche_eigentuemer_erstattung(umsatz)
    if ergebnis:
        person, ev = ergebnis
        return {
            'typ': 'eigentuemer_erstattung',
            'stufe': 1,
            'konfidenz': 'hoch',
            'person_id': str(person.id),
            'ev_id': str(ev.id),
            'begruendung': (
                f"IBAN {umsatz.auftraggeber_iban} → Eigentümer {person.name} "
                f"(EV {ev.einheit.einheit_nr if ev.einheit_id else '?'})"
            ),
        }

    return None


def _ermittle_bank_sachkonto(umsatz):
    """Ermittelt das passende Sachkonto (18xxx) für den Bankabgang."""
    from apps.konten.models import Konto

    if umsatz.objekt is None:
        return None

    bankkonto_obj = umsatz.bankkonto
    if bankkonto_obj and bankkonto_obj.konto_typ == 'ruecklage':
        kontonummern = ['18911', '18000']
    else:
        kontonummern = ['18000', '18911']

    for knr in kontonummern:
        konto = Konto.objects.filter(
            wirtschaftsjahr__objekt=umsatz.objekt,
            kontonummer=knr,
            aktiv=True,
        ).order_by('-wirtschaftsjahr__jahr').first()
        if konto:
            return konto

    return None
