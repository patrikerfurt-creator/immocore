"""
Ausbuchung offener Kreditor-Posten (Buchungsart 056 AUSB-K).

Zweck: Posten, bei denen zum Jahresende nicht mehr mit einem Ausgleich zu
rechnen ist, werden gegen ein frei gewähltes Gegenkonto aufgelöst. Die
Buchungsseite ergibt sich je Posten aus seiner Art:

  Verbindlichkeit (betrag_ursprung > 0, wir schulden dem Kreditor)
      Kreditorkonto 70xxx  Soll  /  Gegenkonto  Haben
      → die Schuld entfällt, das Gegenkonto trägt den Ertrag

  Forderung (betrag_ursprung < 0, z.B. offene Gutschrift zu unseren Gunsten)
      Gegenkonto  Soll  /  Kreditorkonto 70xxx  Haben
      → die Forderung ist wertlos, das Gegenkonto trägt den Aufwand

`betrag_offen` wird immer ohne Vorzeichen geführt; die Richtung steckt im
Vorzeichen von `betrag_ursprung` (siehe KreditorOP.ist_forderung) und deckt
sich mit den Seiten der Ursprungsbuchung.

Danach ist der Posten `ausgebucht` und `betrag_offen` = 0 — analog zum
Ausgleich im E-Banking. Der ausgebuchte Betrag bleibt über die Buchung und
`betrag_ursprung` nachvollziehbar. Ein ausgebuchter Posten blockiert
Schritt 2 der Jahresabrechnung nicht mehr.
"""
from datetime import date, datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.buchhaltung.models import Buchung, Buchungsart, KreditorOP

BA_AUSBUCHUNG = '056'
BELEG_REFERENZ_PREFIX = 'KREDITOR-OP-AUSBUCHUNG'


def _als_date(wert):
    if isinstance(wert, date):
        return wert
    return datetime.strptime(str(wert), '%Y-%m-%d').date()


def _belegnr(buchungsdatum: date) -> str:
    """Fortlaufende Belegnummer im Schema AB-<Jahr>-<lfd>."""
    prefix = f'AB-{buchungsdatum.year}-'
    last = (
        Buchung.objects.filter(belegnr__startswith=prefix)
        .order_by('-belegnr')
        .values_list('belegnr', flat=True)
        .first()
    )
    try:
        lfd = int(last.rsplit('-', 1)[-1]) + 1 if last else 1
    except (ValueError, AttributeError):
        lfd = 1
    return f'{prefix}{lfd:05d}'


def _pruefe_gegenkonto(gegenkonto, objekt):
    if gegenkonto is None:
        raise ValidationError('Kein Gegenkonto gewählt.')
    if not gegenkonto.aktiv:
        raise ValidationError(
            f'Gegenkonto {gegenkonto.kontonummer} ist nicht aktiv.')
    if gegenkonto.kontoart == 'summierung':
        raise ValidationError(
            f'Auf das Summierungskonto {gegenkonto.kontonummer} kann nicht gebucht werden.')
    wj = gegenkonto.wirtschaftsjahr
    if wj is None:
        raise ValidationError(
            f'Gegenkonto {gegenkonto.kontonummer} ist keinem Wirtschaftsjahr zugeordnet.')
    if wj.objekt_id != objekt.id:
        raise ValidationError(
            f'Gegenkonto {gegenkonto.kontonummer} gehört zu einem anderen Objekt.')
    if wj.status != 'offen':
        raise ValidationError(
            f'Wirtschaftsjahr {wj.jahr} ist nicht offen — Ausbuchung nicht möglich.')
    return wj


@transaction.atomic
def ausbuchen(objekt, op_nummern: list, gegenkonto, buchungsdatum, user,
              buchungstext: str = '') -> dict:
    """
    Bucht die gewählten offenen Kreditor-Posten gegen `gegenkonto` aus.

    objekt        : Objekt
    op_nummern    : Liste von KreditorOP.op_nummer
    gegenkonto    : Konto (Ertrags-/Aufwandskonto, jahresgebunden)
    buchungsdatum : date | 'YYYY-MM-DD' — muss im WJ des Gegenkontos liegen
    user          : ausführender Benutzer

    Gibt eine Zusammenfassung je Posten zurück.
    """
    from apps.rechnungen.services.rechnung_op_service import (
        get_or_create_kreditor_konto,
    )

    if not op_nummern:
        raise ValidationError('Keine offenen Posten ausgewählt.')

    wj = _pruefe_gegenkonto(gegenkonto, objekt)
    buchungsdatum = _als_date(buchungsdatum)
    if not (wj.beginn_datum <= buchungsdatum <= wj.ende_datum):
        raise ValidationError(
            f'Buchungsdatum {buchungsdatum:%d.%m.%Y} liegt außerhalb des '
            f'Wirtschaftsjahres {wj.jahr} des Gegenkontos '
            f'({wj.beginn_datum:%d.%m.%Y}–{wj.ende_datum:%d.%m.%Y}).'
        )

    try:
        nummern = [int(n) for n in op_nummern]
    except (TypeError, ValueError):
        raise ValidationError('Ungültige OP-Nummer übergeben.')

    ops = list(
        KreditorOP.objects
        .select_related('kreditor')
        .filter(objekt=objekt, op_nummer__in=nummern)
        .order_by('op_nummer')
    )
    if fehlend := set(nummern) - {op.op_nummer for op in ops}:
        raise ValidationError(
            'Kreditor-OP nicht gefunden (oder gehört zu einem anderen Objekt): '
            + ', '.join(f'OP-{n}' for n in sorted(fehlend))
        )

    for op in ops:
        if op.status not in ('offen', 'teilbezahlt'):
            raise ValidationError(
                f'OP-{op.op_nummer} hat den Status "{op.get_status_display()}" '
                f'und kann nicht ausgebucht werden.'
            )
        if op.betrag_offen <= 0:
            raise ValidationError(
                f'OP-{op.op_nummer} hat keinen offenen Betrag ({op.betrag_offen} €).')
        if op.betrag_ursprung == 0:
            raise ValidationError(
                f'OP-{op.op_nummer} hat den Ursprungsbetrag 0,00 € — '
                f'die Buchungsseite ist nicht bestimmbar.'
            )

    ba = Buchungsart.objects.filter(nr=BA_AUSBUCHUNG).first()
    jetzt = timezone.now()
    ergebnisse = []
    summe_forderungen = Decimal('0.00')
    summe_verbindlichkeiten = Decimal('0.00')

    for op in ops:
        betrag = op.betrag_offen
        kreditorkonto = get_or_create_kreditor_konto(op.kreditor, objekt, jahr=wj.jahr)
        forderung = op.ist_forderung

        if forderung:
            soll_konto, haben_konto = gegenkonto, kreditorkonto
            summe_forderungen += betrag
        else:
            soll_konto, haben_konto = kreditorkonto, gegenkonto
            summe_verbindlichkeiten += betrag

        text = buchungstext or (
            f'Ausbuchung OP-{op.op_nummer} {op.kreditor.name} — '
            f'{"Forderung" if forderung else "Verbindlichkeit"} '
            f'nicht mehr ausgleichbar'
        )
        buchung = Buchung.objects.create(
            objekt=objekt,
            buchungsart=ba,
            betrag=betrag,
            soll_konto=soll_konto,
            haben_konto=haben_konto,
            kreditor=op.kreditor,
            buchungsdatum=buchungsdatum,
            belegnr=_belegnr(buchungsdatum),
            buchungstext=text,
            beleg_referenz=f'{BELEG_REFERENZ_PREFIX}-{op.op_nummer}',
            wirtschaftsjahr=wj,
            wirtschaftsjahr_nr=wj.jahr,
            status='festgeschrieben',
            erstellt_von=user,
        )

        op.status = 'ausgebucht'
        op.betrag_offen = Decimal('0.00')
        op.ausgebucht_am = jetzt
        op.ausgebucht_von = user
        op.save(update_fields=[
            'status', 'betrag_offen', 'ausgebucht_am', 'ausgebucht_von'])

        ergebnisse.append({
            'op_nummer': op.op_nummer,
            'kreditor': op.kreditor.name,
            'betrag': str(betrag),
            'art': 'forderung' if forderung else 'verbindlichkeit',
            'soll_konto': soll_konto.kontonummer,
            'haben_konto': haben_konto.kontonummer,
            'belegnr': buchung.belegnr,
        })

    return {
        'anzahl': len(ergebnisse),
        'wirtschaftsjahr': wj.jahr,
        'gegenkonto': f'{gegenkonto.kontonummer} — {gegenkonto.kontoname}',
        'summe': str(summe_verbindlichkeiten + summe_forderungen),
        'summe_verbindlichkeiten': str(summe_verbindlichkeiten),
        'summe_forderungen': str(summe_forderungen),
        'ops': ergebnisse,
    }
