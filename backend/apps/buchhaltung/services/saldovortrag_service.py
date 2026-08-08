"""
Saldovortrag für ein Personenkonto (Debitoren-Anfangssaldo).

Erzeugt zweierlei in einer Transaktion:
  1) Offener Posten  — HausgeldSollstellung(typ='saldovortrag', ba=BA 99)
     mit je Abrechnungsart einem SollstellungSplit (erloeskonto = 90080).
  2) Sachkontenbuchung je Abrechnungsart — Personenkonto ↔ 90080, wobei die
     Buchungsart der Abrechnungsart die Seite (Unterkonto) bestimmt.

richtung:
  'soll'  → Eigentümer schuldet (Nachforderung). PK im Soll / 90080 im Haben.
            soll_betrag der Sollstellung positiv.
  'haben' → Guthaben des Eigentümers. PK im Haben / 90080 im Soll.
            soll_betrag der Sollstellung negativ (wie 'abrechnungsergebnis').
"""
from datetime import date, datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

BA_SALDOVORTRAG = '99'
KONTO_SALDENVORTRAG_DEBITOREN = '90080'


def _als_date(wert):
    if isinstance(wert, date):
        return wert
    return datetime.strptime(str(wert), '%Y-%m-%d').date()


@transaction.atomic
def buche_saldovortrag(personenkonto, stichtag, richtung, zeilen, user, wirtschaftsjahr=None,
                       buchungstext: str = ''):
    """
    personenkonto : Personenkonto-Instanz
    stichtag      : date | 'YYYY-MM-DD' (Periode/Fälligkeit/Buchungsdatum)
    richtung      : 'soll' | 'haben'  (Seite des Personenkontos)
    zeilen        : list[dict] mit {'ba_nr': '900', 'betrag': Decimal|str} — Beträge positiv
    user          : User-Instanz
    wirtschaftsjahr : optional Wirtschaftsjahr; sonst aus stichtag.year abgeleitet
    Gibt dict mit Zusammenfassung zurück.
    """
    from apps.buchhaltung.models import Buchung, Buchungsart, HausgeldSollstellung, SollstellungSplit
    from apps.buchhaltung.services.opos_nr_service import naechste_opos_nr
    from apps.konten.models import Konto
    from apps.objekte.models import Wirtschaftsjahr

    if richtung not in ('soll', 'haben'):
        raise ValidationError("richtung muss 'soll' oder 'haben' sein.")

    stichtag = _als_date(stichtag)
    ev = personenkonto.vertrag
    if ev is None:
        raise ValidationError('Personenkonto hat kein Eigentumsverhältnis.')
    objekt = personenkonto.objekt

    # Zeilen normalisieren
    norm = []
    for z in zeilen:
        ba_nr = str(z.get('ba_nr') or z.get('ba') or '').strip()
        try:
            betrag = Decimal(str(z.get('betrag')))
        except Exception:
            raise ValidationError(f'Ungültiger Betrag in Zeile {z!r}.')
        if not ba_nr:
            raise ValidationError('Abrechnungsart (ba_nr) fehlt in einer Zeile.')
        if betrag <= 0:
            raise ValidationError('Beträge müssen positiv sein (Richtung steuert Soll/Haben).')
        norm.append((ba_nr, betrag))
    if not norm:
        raise ValidationError('Mindestens eine Abrechnungsart-Zeile erforderlich.')

    # Wirtschaftsjahr — strikt aus dem Stichtag. Ein Saldovortrag gehört ins Jahr
    # des Stichtags, nie ins aktuell im UI gewählte WJ (der übergebene Parameter
    # wird bewusst nur akzeptiert, wenn er zum Stichtagsjahr passt).
    wj = Wirtschaftsjahr.objects.filter(objekt=objekt, jahr=stichtag.year).first()
    if not wj:
        raise ValidationError(
            f'Kein Wirtschaftsjahr {stichtag.year} am Objekt — Saldovortrag zum {stichtag} '
            f'kann nicht in ein anderes WJ gebucht werden.'
        )

    # Gegenkonto 90080 (WJ des Stichtags, sonst neuestes)
    gegen = (Konto.objects.filter(wirtschaftsjahr=wj, kontonummer=KONTO_SALDENVORTRAG_DEBITOREN).first()
             or Konto.objects.filter(wirtschaftsjahr__objekt=objekt, kontonummer=KONTO_SALDENVORTRAG_DEBITOREN
                                      ).order_by('-wirtschaftsjahr__jahr').first())
    if not gegen:
        raise ValidationError(f'Konto {KONTO_SALDENVORTRAG_DEBITOREN} (Saldenvorträge Debitoren) fehlt.')

    ba_savo = Buchungsart.objects.filter(nr=BA_SALDOVORTRAG).first()
    if not ba_savo:
        raise ValidationError(f'Buchungsart {BA_SALDOVORTRAG} (Saldovortrag) fehlt.')

    split_bas = {}
    for ba_nr, _ in norm:
        if ba_nr in split_bas:
            continue
        ba = Buchungsart.objects.filter(nr=ba_nr).first()
        if not ba:
            raise ValidationError(f'Abrechnungsart {ba_nr} nicht gefunden.')
        split_bas[ba_nr] = ba

    vorzeichen = Decimal('1') if richtung == 'soll' else Decimal('-1')
    summe = sum(b for _, b in norm)

    # 1) Offener Posten
    ss = HausgeldSollstellung.objects.create(
        objekt=objekt,
        eigentumsverhaeltnis=ev,
        sollstellungs_typ='saldovortrag',
        ba=ba_savo,
        periode=stichtag,
        faellig_am=stichtag,
        opos_nr=naechste_opos_nr(objekt),
        soll_betrag=vorzeichen * summe,
        ist_betrag=Decimal('0'),
        status_cached='offen',
        erstellt_von=user,
    )
    for ba_nr, betrag in norm:
        SollstellungSplit.objects.create(
            sollstellung=ss,
            ba=split_bas[ba_nr],
            betrag=vorzeichen * betrag,
            bankkonto_ziel=None,
            erloeskonto=gegen,
        )

    # 2) Sachkontenbuchung je Abrechnungsart (PK ↔ 90080)
    text = buchungstext or f'Saldovortrag {stichtag.year}'
    buchungen = []
    for ba_nr, betrag in norm:
        if richtung == 'soll':      # PK Soll / 90080 Haben
            soll_konto, haben_konto = None, gegen
        else:                       # PK Haben / 90080 Soll
            soll_konto, haben_konto = gegen, None
        b = Buchung.objects.create(
            objekt=objekt,
            buchungsart=split_bas[ba_nr],
            betrag=betrag,
            soll_konto=soll_konto,
            haben_konto=haben_konto,
            personenkonto=personenkonto,
            buchungsdatum=stichtag,
            belegdatum=stichtag,
            buchungstext=f'{text} — {ba_nr}',
            wirtschaftsjahr=wj,
            status='festgeschrieben',
            erstellt_von=user,
        )
        buchungen.append(b)

    return {
        'sollstellung_id': str(ss.id),
        'opos_nr': ss.opos_nr,
        'soll_betrag': ss.soll_betrag,
        'richtung': richtung,
        'anzahl_buchungen': len(buchungen),
        'buchung_ids': [str(b.id) for b in buchungen],
        'gegenkonto': gegen.kontonummer,
    }
