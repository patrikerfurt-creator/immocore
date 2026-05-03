"""
Sollstellungslauf-Service

Buchungsstruktur (Sammelbuchung pro Eigentümer/Monat):
  Gesamt-Buchung  → Personenkonto 0001, Gesamtbetrag, eine BU-Nr.
                    soll_konto=None, haben_konto=None (Sammelbuchung)
  Teilbuchungen   → gleiche BU-Nr., je Abrechnungsart:
                    soll_unterkonto=0001.9xx / haben_konto=41XXX
                    z.B. Soll 0001.900 an Haben 41900 (HGV)
                         Soll 0001.911 an Haben 41911 (RLZ)

Im Kontoauszug erscheint nur die Gesamt-Buchung.
Drill-down zeigt die Teilbuchungen mit Unterkonto / Erlöskonto.
"""
import logging
from decimal import Decimal
from datetime import date
from itertools import groupby

from django.db import transaction

logger = logging.getLogger(__name__)

ERLOSKONTO_PRAEFIX = '41'  # 41 + Abrechnungsart-Code → z.B. 41900, 41911


def _get_ba(kuerzel: str):
    from apps.buchhaltung.models import Buchungsart
    return Buchungsart.objects.filter(kuerzel=kuerzel, aktiv=True).first()


def _get_konto(objekt_id, kontonummer: str):
    from apps.konten.models import Konto
    return Konto.objects.filter(
        objekt_id=objekt_id, kontonummer=kontonummer, aktiv=True
    ).first()


def _get_erloskonto(objekt_id, kontoart_suffix: str):
    """'.900' → Konto '41900', '.911' → Konto '41911'"""
    code = kontoart_suffix.lstrip('.')
    return _get_konto(objekt_id, f'{ERLOSKONTO_PRAEFIX}{code}')


def _get_hausgeld_betraege(ev, jahr: int, monat: int) -> dict:
    """Gibt {'.900': Decimal, '.911': ...} für alle konfigurierten Kontoarten zurück."""
    from apps.personen.models import HausgeldHistorie
    stichtag = date(jahr, monat, 1)

    alle_kontoarten = (
        HausgeldHistorie.objects
        .filter(eigentumsverhaeltnis=ev)
        .values_list('kontoart', flat=True)
        .distinct()
    )

    betraege = {}
    for kontoart in alle_kontoarten:
        if not kontoart:
            continue
        eintrag = (
            HausgeldHistorie.objects
            .filter(
                eigentumsverhaeltnis=ev,
                kontoart=kontoart,
                gueltig_ab__lte=stichtag,
            )
            .order_by('-gueltig_ab')
            .first()
        )
        if eintrag and eintrag.betrag > 0:
            betraege[kontoart] = eintrag.betrag
    return betraege


def _get_unterkonto(personenkonto, suffix: str):
    return personenkonto.unterkonten.filter(suffix=suffix).first()


def _ba_kuerzel_fuer_kontoart(kontoart_suffix: str) -> str:
    code = kontoart_suffix.lstrip('.')
    return {'900': 'HGV', '911': 'RLZ'}.get(code, f'BA{code}')


def _belegnr(personenkonto, jahr: int, monat: int) -> str:
    return f'SS-{jahr:04d}{monat:02d}-{personenkonto.kontonummer}'


def simuliere_lauf(objekt_id: str, periode_von: date, periode_bis: date,
                   ba_filter: list | None = None) -> dict:
    """Vorschau ohne DB-Änderungen."""
    from apps.objekte.models import Objekt
    from apps.personen.models import EigentumsVerhaeltnis

    objekt = Objekt.objects.get(pk=objekt_id)
    positionen = []
    fehler = []
    gesamt = Decimal('0.00')

    aktive_evs = EigentumsVerhaeltnis.objects.filter(
        einheit__objekt=objekt,
        ende__isnull=True,
    ).select_related('person', 'einheit', 'personenkonto')

    for jahr, m in _monate_im_zeitraum(periode_von, periode_bis):
        for ev in aktive_evs:
            try:
                pk = ev.personenkonto
            except Exception:
                fehler.append({
                    'person': str(ev.person),
                    'einheit': str(ev.einheit),
                    'grund': 'Kein Personenkonto angelegt',
                })
                continue

            betraege = _get_hausgeld_betraege(ev, jahr, m)
            if not betraege:
                continue

            gesamt_betrag = sum(betraege.values())
            positionen.append({
                'personenkonto_id': str(pk.id),
                'person': pk.eigentuemer.name,
                'einheit': ev.einheit.einheit_nr,
                'monat': m,
                'jahr': jahr,
                'gesamt': float(gesamt_betrag),
                'positionen': [
                    {
                        'kontoart': ka,
                        'ba': _ba_kuerzel_fuer_kontoart(ka),
                        'betrag': float(b),
                    }
                    for ka, b in betraege.items()
                    if not ba_filter or _ba_kuerzel_fuer_kontoart(ka) in ba_filter
                ],
            })
            gesamt += gesamt_betrag

    return {
        'objekt': str(objekt.id),
        'periode_von': str(periode_von),
        'periode_bis': str(periode_bis),
        'anzahl_positionen': len(positionen),
        'gesamt_summe': float(gesamt),
        'positionen': positionen,
        'fehler': fehler,
    }


@transaction.atomic
def fuehre_lauf_aus(lauf_id: str, user) -> dict:
    """
    Erzeugt pro Eigentümer/Monat:
      1 Gesamt-Buchung  (Personenkonto = Soll, Gesamtbetrag)
      N Teilbuchungen   (gleiche BU-Nr., Soll=13650, Haben=41XXX je BA)
      1 OffenerPosten   (auf Gesamt-Buchung)
      1 Sollstellung    (auf Gesamt-Buchung)
    """
    from apps.buchhaltung.models import (
        SollstellungsLauf, Sollstellung, Buchung, OffenerPosten, Buchungsart
    )
    from apps.konten.models import Personenkonto

    lauf = SollstellungsLauf.objects.select_for_update().get(pk=lauf_id)
    if lauf.status not in ('simulation', 'freigegeben'):
        raise ValueError(f'Lauf hat Status "{lauf.status}" — kann nicht ausgeführt werden.')

    ba_default = Buchungsart.objects.filter(aktiv=True, system_buchungsart=True).first()

    fehler_log = []
    vorschau = simuliere_lauf(str(lauf.objekt_id), lauf.periode_von, lauf.periode_bis)
    ok = 0

    for pos in vorschau['positionen']:
        if not pos['positionen']:
            continue
        try:
            pk = Personenkonto.objects.get(pk=pos['personenkonto_id'])
            jahr, monat = pos['jahr'], pos['monat']
            gesamt_betrag = Decimal(str(pos['gesamt']))
            bu_nr = _belegnr(pk, jahr, monat)
            datum = date(jahr, monat, 1)

            # Doppelsollstellungs-Sperre
            if Sollstellung.objects.filter(
                personenkonto=pk,
                periode_monat=monat,
                periode_jahr=jahr,
                status__in=['vorschau', 'gebucht'],
            ).exists():
                fehler_log.append({'position': pos, 'grund': 'Doppelsollstellung'})
                continue

            # ── Gesamt-Buchung ──────────────────────────────────────────────
            # Repräsentiert das Personenkonto 0001 als Ganzes (Gesamtbetrag).
            # Kein Sachkonto auf Soll/Haben — die Aufschlüsselung erfolgt
            # in den Teilbuchungen (0001.9xx an 41XXX).
            gesamt_buchung = Buchung.objects.create(
                objekt=lauf.objekt,
                buchungsart=ba_default,
                betrag=gesamt_betrag,
                soll_konto=None,
                haben_konto=None,
                soll_unterkonto=None,
                personenkonto=pk,               # Personenkonto 0001 (Nebenbuch)
                unterkonto=None,
                parent_buchung=None,
                belegnr=bu_nr,
                buchungsdatum=datum,
                belegdatum=datum,
                buchungstext=f'Sollstellung {monat:02d}/{jahr} — {pk.eigentuemer.name}',
                wirtschaftsjahr=jahr,
                status='festgeschrieben',
                erstellt_von=user,
            )

            # ── Teilbuchungen je Abrechnungsart ────────────────────────────
            # Soll: Unterkonto 0001.9xx  /  Haben: Erlöskonto 41XXX
            # Beispiel HGV:  Soll 0001.900  an  Haben 41900
            #         RLZ:   Soll 0001.911  an  Haben 41911
            for teil in pos['positionen']:
                kontoart = teil['kontoart']     # z.B. '.900'
                betrag = Decimal(str(teil['betrag']))
                ba_kuerzel = teil['ba']

                erloskonto = _get_erloskonto(str(lauf.objekt_id), kontoart)
                if not erloskonto:
                    fehler_log.append({
                        'position': pos,
                        'grund': f'Erlöskonto {ERLOSKONTO_PRAEFIX}{kontoart.lstrip(".")} nicht gefunden',
                    })
                    continue

                ba = _get_ba(ba_kuerzel) or ba_default
                unterkonto = _get_unterkonto(pk, kontoart)  # 0001.9xx

                Buchung.objects.create(
                    objekt=lauf.objekt,
                    buchungsart=ba,
                    betrag=betrag,
                    soll_konto=None,
                    soll_unterkonto=unterkonto,  # Soll: 0001.9xx
                    haben_konto=erloskonto,       # Haben: 41XXX
                    personenkonto=pk,
                    unterkonto=unterkonto,
                    parent_buchung=gesamt_buchung,
                    belegnr=bu_nr,
                    buchungsdatum=datum,
                    belegdatum=datum,
                    buchungstext=f'Sollstellung {ba_kuerzel} {monat:02d}/{jahr} — {pk.eigentuemer.name}',
                    wirtschaftsjahr=jahr,
                    status='festgeschrieben',
                    erstellt_von=user,
                )

            # ── Offener Posten auf Gesamt-Buchung ──────────────────────────
            OffenerPosten.objects.create(
                buchung=gesamt_buchung,
                personenkonto=pk,
                betrag_ursprung=gesamt_betrag,
                betrag_offen=gesamt_betrag,
                faellig_ab=datum,
            )

            # ── Sollstellung auf Gesamt-Buchung ────────────────────────────
            Sollstellung.objects.create(
                lauf=lauf,
                personenkonto=pk,
                buchungsart=ba_default,
                buchung=gesamt_buchung,
                betrag=gesamt_betrag,
                periode_monat=monat,
                periode_jahr=jahr,
                status='gebucht',
            )
            ok += 1

        except Exception as exc:
            logger.exception('Sollstellungsfehler für %s', pos)
            fehler_log.append({'position': pos, 'grund': str(exc)})

    lauf.status = 'ausgefuehrt'
    lauf.anzahl_buchungen = ok
    lauf.gesamt_summe = Decimal(str(vorschau['gesamt_summe']))
    lauf.fehler_log = fehler_log
    lauf.save(update_fields=[
        'status', 'anzahl_buchungen', 'gesamt_summe', 'fehler_log'
    ])

    return {
        'gebucht': ok,
        'fehler': len(fehler_log),
        'fehler_log': fehler_log,
    }


def _monate_im_zeitraum(von: date, bis: date):
    monate = []
    aktuell = date(von.year, von.month, 1)
    ende = date(bis.year, bis.month, 1)
    while aktuell <= ende:
        monate.append((aktuell.year, aktuell.month))
        if aktuell.month == 12:
            aktuell = date(aktuell.year + 1, 1, 1)
        else:
            aktuell = date(aktuell.year, aktuell.month + 1, 1)
    return monate
