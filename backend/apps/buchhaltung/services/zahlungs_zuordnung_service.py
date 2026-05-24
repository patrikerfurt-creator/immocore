"""
Manuelle Zahlungszuordnung: Zahlungseingang gegen Nebenbuch (HausgeldSollstellung).

Buchungssatz: Soll 18xxx (Bank) / Haben 41xxx (Erlös je Split)
Nebenbuch:    ist_betrag auf Sollstellung + SollstellungZahlung anlegen

Tilgungsreihenfolge: älteste Sollstellung zuerst (§ 366 Abs. 2 BGB),
innerhalb einer Sollstellung Rücklage vor Hausgeld (tilgungs_prioritaet).
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction


def _split_sort_key(split):
    ba = split.ba
    if ba is None:
        return (99, '')
    if ba.tilgungs_prioritaet is not None:
        return (ba.tilgungs_prioritaet, ba.nr)
    # Fallback: 91x (Rücklage) vor 900 (Hausgeld) vor Rest
    nr = ba.nr or ''
    if nr.startswith('91'):
        return (20, nr)
    if nr == '900':
        return (90, nr)
    return (99, nr)


@transaction.atomic
def verrechne_eingang_manuell(
    personenkonto,
    bank_sachkonto,
    betrag: Decimal,
    buchungsdatum,
    buchungstext: str,
    wirtschaftsjahr,
    user,
):
    """
    Bucht einen manuellen Zahlungseingang gegen offene Sollstellungen.

    personenkonto: Personenkonto-Instanz
    bank_sachkonto: Konto-Instanz (18xxx Sachkonto)
    betrag: Gesamtbetrag des Zahlungseingangs
    buchungsdatum: date
    buchungstext: str
    wirtschaftsjahr: Wirtschaftsjahr-Instanz
    user: User-Instanz
    Gibt parent Buchung zurück.
    """
    from apps.buchhaltung.models import Buchung, HausgeldSollstellung, SollstellungZahlung

    ev = personenkonto.vertrag

    offene_ss = list(
        HausgeldSollstellung.objects
        .filter(eigentumsverhaeltnis=ev, storniert_am__isnull=True)
        .exclude(status_cached__in=['ausgeglichen', 'storniert'])
        .order_by('periode', 'erstellt_am')
        .prefetch_related('splits__ba')
    )

    if not offene_ss:
        raise ValidationError("Keine offenen Sollstellungen für dieses Personenkonto.")

    verbleibend = betrag

    parent_buchung = Buchung.objects.create(
        objekt=personenkonto.objekt,
        buchungsart=None,
        betrag=betrag,
        soll_konto=bank_sachkonto,
        haben_konto=None,
        personenkonto=personenkonto,
        buchungsdatum=buchungsdatum,
        belegdatum=buchungsdatum,
        buchungstext=buchungstext or 'Zahlungseingang',
        wirtschaftsjahr=wirtschaftsjahr,
        status='festgeschrieben',
        erstellt_von=user,
    )

    for ss in offene_ss:
        if verbleibend <= 0:
            break

        rest_ss = ss.soll_betrag - ss.ist_betrag
        if rest_ss <= 0:
            continue

        splits = sorted(ss.splits.all(), key=_split_sort_key)

        if splits:
            for split in splits:
                if verbleibend <= 0:
                    break
                rest_split = split.betrag - split.ist_betrag_split
                if rest_split <= 0:
                    continue

                teil = min(verbleibend, rest_split)

                Buchung.objects.create(
                    objekt=personenkonto.objekt,
                    buchungsart=split.ba,
                    betrag=teil,
                    soll_konto=None,
                    haben_konto=split.erloeskonto,
                    personenkonto=personenkonto,
                    parent_buchung=parent_buchung,
                    buchungsdatum=buchungsdatum,
                    belegdatum=buchungsdatum,
                    buchungstext=f"{split.ba.bezeichnung if split.ba else ''} {ss.periode.strftime('%m/%Y')}",
                    wirtschaftsjahr=wirtschaftsjahr,
                    status='festgeschrieben',
                    erstellt_von=user,
                )

                SollstellungZahlung.objects.create(
                    sollstellung=ss,
                    split=split,
                    buchung=parent_buchung,
                    betrag=teil,
                    tilgungsstufe='hauptforderung',
                    erstellt_von=user,
                )

                split.ist_betrag_split = split.ist_betrag_split + teil
                split.save(update_fields=['ist_betrag_split'])

                ss.ist_betrag = ss.ist_betrag + teil
                verbleibend -= teil
        else:
            # Sonderumlage / Abrechnungsergebnis — kein Split
            from apps.konten.models import Konto
            teil = min(verbleibend, rest_ss)
            ba = ss.ba
            erloeskonto = None
            if ba and ba.erloeskonto_default_nr:
                erloeskonto = Konto.objects.filter(
                    wirtschaftsjahr=wirtschaftsjahr,
                    kontonummer=ba.erloeskonto_default_nr,
                ).first()

            Buchung.objects.create(
                objekt=personenkonto.objekt,
                buchungsart=ba,
                betrag=teil,
                soll_konto=None,
                haben_konto=erloeskonto,
                personenkonto=personenkonto,
                parent_buchung=parent_buchung,
                buchungsdatum=buchungsdatum,
                belegdatum=buchungsdatum,
                buchungstext=f"{ba.bezeichnung if ba else 'Zahlung'} {ss.periode.strftime('%m/%Y')}",
                wirtschaftsjahr=wirtschaftsjahr,
                status='festgeschrieben',
                erstellt_von=user,
            )

            SollstellungZahlung.objects.create(
                sollstellung=ss,
                split=None,
                buchung=parent_buchung,
                betrag=teil,
                tilgungsstufe='hauptforderung',
                erstellt_von=user,
            )

            ss.ist_betrag = ss.ist_betrag + teil
            verbleibend -= teil

        ss.status_cached = ss.status
        ss.save(update_fields=['ist_betrag', 'status_cached'])

    return parent_buchung
