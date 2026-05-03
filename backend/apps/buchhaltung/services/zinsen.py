"""
Verzugszinsen gem. § 288 BGB — taggenau berechnet.
Basiszinssatz aus DB-Tabelle; Verbraucher +5 %, Unternehmer +9 %.
"""
from decimal import Decimal, ROUND_HALF_UP
from datetime import date


def get_basiszinssatz(stichtag: date) -> Decimal:
    from apps.buchhaltung.models import Basiszinssatz
    eintrag = (
        Basiszinssatz.objects
        .filter(gueltig_ab__lte=stichtag)
        .order_by('-gueltig_ab')
        .first()
    )
    if eintrag:
        return eintrag.satz
    return Decimal('3.62')  # letzter bekannter Wert bei Seed-Fehlen


def berechne_verzugszinsen(
    betrag: Decimal,
    faellig_ab: date,
    bis_datum: date,
    schuldner_typ: str = 'verbraucher',
) -> Decimal:
    """
    Berechnet Verzugszinsen taggenau für einen Betrag.

    schuldner_typ: 'verbraucher' (+5 %) oder 'unternehmer' (+9 %)
    """
    if bis_datum <= faellig_ab:
        return Decimal('0.00')

    aufschlag = Decimal('9') if schuldner_typ == 'unternehmer' else Decimal('5')
    tage = (bis_datum - faellig_ab).days
    basiszins = get_basiszinssatz(faellig_ab)
    gesamtzins = basiszins + aufschlag
    zinsen = betrag * gesamtzins / Decimal('100') / Decimal('365') * tage
    return zinsen.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
