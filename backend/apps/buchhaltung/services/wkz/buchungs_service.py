"""
WKZ Buchungs-Service — Kassenprinzip-Aufwandsbuchung bei Bankabgang.

Buchungslogik gemäß §28 WEG: Aufwand entsteht erst beim Bankabgang,
niemals vorher.
"""
import logging
from decimal import Decimal
from datetime import date

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Ausnahmen
# ---------------------------------------------------------------------------

class KontoNichtImWJException(Exception):
    """
    Wird geworfen, wenn ein Split-Konto nicht im aktuellen WJ / Objekt
    gefunden werden kann. Buchung wird abgebrochen, OP bleibt offen.
    """
    pass


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def bestimme_aktives_wj(objekt, datum: date) -> int:
    """
    Gibt das 'aktive' Wirtschaftsjahr als Integer zurück.
    Da wirtschaftsjahr ein IntegerField ist (Jahrezahl), ist das
    einfach das Jahr des Buchungsdatums.
    """
    return datum.year


def _finde_konto(objekt, kontonummer: str):
    """
    Sucht das Konto mit der gegebenen Kontonummer im Objekt.
    Raises KontoNichtImWJException wenn nicht gefunden.
    """
    from apps.konten.models import Konto
    konto = Konto.objects.filter(
        objekt=objekt,
        kontonummer=kontonummer,
        aktiv=True,
    ).first()
    if not konto:
        raise KontoNichtImWJException(
            f"Konto {kontonummer} im Objekt '{objekt.bezeichnung}' nicht gefunden "
            f"oder inaktiv. Bitte Kontenplan prüfen."
        )
    return konto


def _bestimme_bank_sachkonto(kontoumsatz, objekt):
    """
    Ermittelt das Buchungs-Sachkonto für das Bankkonto des Umsatzes.
    Bewirtschaftungskonto → 18000, Rücklagenkonto → 18911.
    Sucht zuerst nach dem Standard-Kontonummer, dann nach beliebigem
    Konto im 18xxx-Bereich das zum Bankkonto gehört.
    """
    from apps.konten.models import Konto

    bankkonto = kontoumsatz.bankkonto
    if bankkonto:
        ziel_nr = '18000' if bankkonto.konto_typ == 'bewirtschaftung' else '18911'
        konto = Konto.objects.filter(
            objekt=objekt,
            kontonummer=ziel_nr,
            aktiv=True,
        ).first()
        if konto:
            return konto

    # Fallback: erstes Bank-Konto im Objekt (18000–18999)
    konto = Konto.objects.filter(
        objekt=objekt,
        aktiv=True,
    ).filter(
        kontonummer__gte='18000',
        kontonummer__lte='18999',
    ).first()

    if not konto:
        raise KontoNichtImWJException(
            f"Kein Bank-Sachkonto (18xxx) im Objekt '{objekt.bezeichnung}' gefunden."
        )
    return konto


def _naechste_belegnr_wkz(objekt, datum: date) -> str:
    """Erzeugt eine fortlaufende WKZ-Belegnummer im Schema WKZ-JJJJ-NNNNN."""
    from apps.buchhaltung.models import Buchung
    prefix = f"WKZ-{datum.year}-"
    last = (
        Buchung.objects
        .filter(belegnr__startswith=prefix, objekt=objekt)
        .order_by('-belegnr')
        .values_list('belegnr', flat=True)
        .first()
    )
    try:
        lfd = int(last.rsplit('-', 1)[-1]) + 1 if last else 1
    except (ValueError, AttributeError):
        lfd = 1
    return f"{prefix}{lfd:05d}"


def _erzeuge_sammelbuchung(objekt, datum, belegnr, verwendungszweck, wj, erstellt_von,
                           betrag=None, haben_konto=None):
    """Erzeugt die Parent-Buchung (Sammelbuchung)."""
    from apps.buchhaltung.models import Buchung
    return Buchung.objects.create(
        objekt=objekt,
        buchungsdatum=datum,
        belegdatum=datum,
        belegnr=belegnr,
        buchungstext=verwendungszweck,
        verwendungszweck=verwendungszweck,
        wirtschaftsjahr=wj,
        status='entwurf',
        erstellt_von=erstellt_von,
        betrag=betrag,
        haben_konto=haben_konto,
    )


def _erzeuge_teilbuchung(parent, soll_konto, haben_konto, betrag, text, erstellt_von):
    """Erzeugt eine Teilbuchung zur Sammelbuchung."""
    from apps.buchhaltung.models import Buchung
    return Buchung.objects.create(
        objekt=parent.objekt,
        parent_buchung=parent,
        soll_konto=soll_konto,
        haben_konto=haben_konto,
        betrag=betrag,
        buchungsdatum=parent.buchungsdatum,
        belegdatum=parent.belegdatum,
        belegnr=parent.belegnr,
        buchungstext=text or parent.buchungstext,
        wirtschaftsjahr=parent.wirtschaftsjahr,
        status='entwurf',
        erstellt_von=erstellt_von,
    )


# ---------------------------------------------------------------------------
# Hauptfunktionen
# ---------------------------------------------------------------------------

@transaction.atomic
def verbuche_bankabgang(wkz_op, kontoumsatz, user=None) -> 'Buchung':
    """
    Erzeugt die Kassenprinzip-Aufwandsbuchung beim Bankabgang.
    Splits werden gegen das aktive WJ (= buchungsjahr) über kontonummer aufgelöst.

    Buchungsbeispiel (Stadtwerke Q2 2026, 850 €):
        Soll  50100  Wasser              450,00
        Soll  50200  Müllabfuhr          280,00
        Haben 18000  Bank Bewirtschaftung 850,00

    Returns: die erzeugte Parent-Buchung
    """
    vorlage = wkz_op.vorlage
    objekt = vorlage.objekt
    bank_datum = kontoumsatz.buchungsdatum
    bank_betrag = abs(kontoumsatz.betrag)

    wj = bestimme_aktives_wj(objekt, bank_datum)
    bank_konto = _bestimme_bank_sachkonto(kontoumsatz, objekt)

    # Splits auflösen
    splits = list(vorlage.splits.all().order_by('reihenfolge'))
    if not splits:
        raise ValueError(f"Vorlage {vorlage.id} hat keine Splits — Verbuchung nicht möglich.")

    split_konten = []
    for split in splits:
        konto = _finde_konto(objekt, split.kontonummer)
        split_konten.append((split, konto))

    verwendungszweck = (
        f"{vorlage.bezeichnung} "
        f"{wkz_op.periode_von.strftime('%m/%Y')}–{wkz_op.periode_bis.strftime('%m/%Y')}"
    )
    belegnr = _naechste_belegnr_wkz(objekt, bank_datum)
    erstellt_von = user or _system_user()

    # Sammelbuchung anlegen
    parent = _erzeuge_sammelbuchung(
        objekt, bank_datum, belegnr, verwendungszweck, wj, erstellt_von,
        betrag=bank_betrag, haben_konto=bank_konto,
    )

    # Teilbuchungen je Split
    for split, soll_konto in split_konten:
        _erzeuge_teilbuchung(
            parent=parent,
            soll_konto=soll_konto,
            haben_konto=None,
            betrag=split.betrag,
            text=split.bezeichnung,
            erstellt_von=erstellt_von,
        )

    # WKZ-OP abschließen
    wkz_op.status = 'bankabgang_erfolgt'
    wkz_op.bank_match_buchung = parent
    wkz_op.save(update_fields=['status', 'bank_match_buchung'])

    # KreditorOP ausgleichen
    op = wkz_op.kreditor_op
    op.betrag_offen = Decimal('0')
    op.status = 'bezahlt'
    op.zahlung_buchung = parent
    op.save(update_fields=['betrag_offen', 'status', 'zahlung_buchung'])

    logger.info(
        "WKZ Bankabgang verbucht: WKZ-OP %s, Buchung %s, Betrag %s, WJ %s",
        wkz_op.id, parent.id, bank_betrag, wj
    )
    return parent


@transaction.atomic
def verbuche_mit_anpassung(
    wkz_op, kontoumsatz, splits_override: dict, user
) -> 'Buchung':
    """
    Verbuchung mit abweichendem Bankbetrag — Buchhalter gibt angepasste
    Splitbeträge vor.

    splits_override: {kontonummer: Decimal-Betrag, ...}
    SUM(splits_override) muss == abs(kontoumsatz.betrag) sein.
    """
    bank_betrag = abs(kontoumsatz.betrag)
    summe = sum(Decimal(str(v)) for v in splits_override.values())
    if abs(summe - bank_betrag) > Decimal('0.01'):
        raise ValueError(
            f"Splits-Summe {summe} stimmt nicht mit Bankabgang {bank_betrag} überein."
        )

    vorlage = wkz_op.vorlage
    objekt = vorlage.objekt
    bank_datum = kontoumsatz.buchungsdatum

    wj = bestimme_aktives_wj(objekt, bank_datum)
    bank_konto = _bestimme_bank_sachkonto(kontoumsatz, objekt)

    # Split-Konten auflösen
    split_konten = []
    for kontonummer, betrag in splits_override.items():
        konto = _finde_konto(objekt, str(kontonummer))
        split_konten.append((konto, Decimal(str(betrag))))

    verwendungszweck = (
        f"{vorlage.bezeichnung} "
        f"{wkz_op.periode_von.strftime('%m/%Y')}–{wkz_op.periode_bis.strftime('%m/%Y')}"
    )
    belegnr = _naechste_belegnr_wkz(objekt, bank_datum)

    parent = _erzeuge_sammelbuchung(
        objekt, bank_datum, belegnr, verwendungszweck, wj, user,
        betrag=bank_betrag, haben_konto=bank_konto,
    )

    for konto, betrag in split_konten:
        _erzeuge_teilbuchung(
            parent=parent,
            soll_konto=konto,
            haben_konto=None,
            betrag=betrag,
            text=konto.kontoname if hasattr(konto, 'kontoname') else '',
            erstellt_von=user,
        )

    abweichung = bank_betrag - vorlage.betrag_gesamt
    wkz_op.status = 'abweichend_geklaert'
    wkz_op.bank_match_buchung = parent
    wkz_op.abweichung_betrag = abweichung
    wkz_op.klaerungs_grund = f"Anpassung beim Bank-Match durch {user}"
    wkz_op.save(update_fields=[
        'status', 'bank_match_buchung', 'abweichung_betrag', 'klaerungs_grund'
    ])

    op = wkz_op.kreditor_op
    op.betrag_offen = Decimal('0')
    op.status = 'bezahlt'
    op.zahlung_buchung = parent
    op.save(update_fields=['betrag_offen', 'status', 'zahlung_buchung'])

    logger.info(
        "WKZ Bankabgang mit Anpassung verbucht: WKZ-OP %s, Abweichung %s, durch %s",
        wkz_op.id, abweichung, user
    )
    return parent


def _system_user():
    """Gibt den ersten Superuser zurück (für automatische System-Buchungen)."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.filter(is_superuser=True).first()
