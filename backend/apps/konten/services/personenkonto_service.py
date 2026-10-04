"""
Saldo-Berechnung je Personenkonto (Debitorensicht).

Einzige Stelle, an der Soll (Nebenbuch: `HausgeldSollstellung`) und Haben
(Sachbuch: `Buchung`) für die Debitorenansicht zusammengeführt werden.
Sowohl die interne Ansicht (`PersonenkontoViewSet.mit_saldo`) als auch die
Portal-Endpunkte (`apps.portal.views_konto`) rufen ausschließlich diese
Funktion auf — eine zweite, eigene Rechnung würde früher oder später von
hier abweichen, und ein Eigentümer, der zwei unterschiedliche Salden sieht,
ruft an.

Extrahiert aus `PersonenkontoViewSet.mit_saldo` (reines Refactoring, keine
Verhaltensänderung): Filter und Gruppierung sind identisch geblieben, nur
`soll_je_typ` ist neu dazugekommen — dieselbe Query, zusätzlich nach
`sollstellungs_typ` gruppiert, damit eine Aufschlüsselung (Portal) exakt
dieselben Zahlen benutzt wie der Gesamtsaldo.
"""
from decimal import Decimal
from uuid import UUID

from django.db.models import Sum


def saldi_je_personenkonto(personenkonten, *, wirtschaftsjahr_id: str | None = None) -> dict[UUID, dict]:
    """
    Berechnet Soll, Haben und Saldo je Personenkonto.

    Soll  = Nebenbuch: Summe `HausgeldSollstellung.soll_betrag` je
            zugehörigem Eigentumsverhältnis, nicht stornierte Sollstellungen,
            optional auf ein Wirtschaftsjahr (über `periode__year`) eingegrenzt.
    Haben = Sachbuch: Summe `Buchung.betrag` je Personenkonto, nur
            Kopfbuchungen mit gesetztem `soll_konto` (Zahlungseingänge),
            ohne stornierte Buchungen, optional auf ein Wirtschaftsjahr
            eingegrenzt.

    Vorzeichen aus Eigentümersicht (wie ein Bankkonto):
    saldo < 0 = Rückstand (weniger gezahlt als gefordert),
    saldo > 0 = Guthaben.

    Gibt `{personenkonto_id: {'soll', 'haben', 'saldo', 'soll_je_typ'}}` zurück.
    `soll_je_typ` ist `{sollstellungs_typ: Decimal}` — dieselbe Soll-Query,
    zusätzlich nach Typ gruppiert.
    """
    from apps.buchhaltung.models import Buchung, HausgeldSollstellung

    personenkonten = list(personenkonten)
    ev_ids = [pk.vertrag_id for pk in personenkonten if pk.vertrag_id]
    pk_ids = [pk.id for pk in personenkonten]

    # Soll aus Nebenbuch: Summe der nicht-stornierten Sollstellungen je EV
    ss_qs = (
        HausgeldSollstellung.objects
        .filter(eigentumsverhaeltnis_id__in=ev_ids, storniert_am__isnull=True)
    )
    if wirtschaftsjahr_id:
        from apps.objekte.models import Wirtschaftsjahr
        try:
            wj = Wirtschaftsjahr.objects.get(pk=wirtschaftsjahr_id)
            ss_qs = ss_qs.filter(periode__year=wj.jahr)
        except Wirtschaftsjahr.DoesNotExist:
            pass

    soll_per_ev = dict(
        ss_qs.values('eigentumsverhaeltnis_id')
        .annotate(s=Sum('soll_betrag'))
        .values_list('eigentumsverhaeltnis_id', 's')
    )

    soll_je_typ_per_ev: dict = {}
    for zeile in (
        ss_qs.values('eigentumsverhaeltnis_id', 'sollstellungs_typ')
        .annotate(s=Sum('soll_betrag'))
    ):
        soll_je_typ_per_ev.setdefault(zeile['eigentumsverhaeltnis_id'], {})[
            zeile['sollstellungs_typ']
        ] = zeile['s']

    # Haben aus Buchungen (Zahlungseingänge)
    haben_qs = (
        Buchung.objects
        .filter(personenkonto_id__in=pk_ids, soll_konto__isnull=False, parent_buchung__isnull=True)
        .exclude(status='storniert')
    )
    if wirtschaftsjahr_id:
        haben_qs = haben_qs.filter(wirtschaftsjahr_id=wirtschaftsjahr_id)
    haben_per_pk = dict(
        haben_qs.values('personenkonto_id').annotate(s=Sum('betrag')).values_list('personenkonto_id', 's')
    )

    ergebnis: dict[UUID, dict] = {}
    for pk in personenkonten:
        soll  = soll_per_ev.get(pk.vertrag_id) or Decimal('0')
        haben = haben_per_pk.get(pk.id) or Decimal('0')
        ergebnis[pk.id] = {
            'soll': soll,
            'haben': haben,
            'saldo': haben - soll,
            'soll_je_typ': soll_je_typ_per_ev.get(pk.vertrag_id, {}),
        }
    return ergebnis


def baue_kontoauszug(pk_obj, *, wirtschaftsjahr_id: str | None = None) -> dict:
    """
    Kontoauszug eines Personenkontos (Debitorensicht).
    Soll  = Forderungen aus dem Nebenbuch (HausgeldSollstellung).
    Haben = Zahlungseingänge (Buchung, verknüpft via Personenkonto oder SollstellungZahlung).
    Beide Listen werden nach Datum gemischt und chronologisch sortiert.

    Stornierte Sollstellungen werden mit ausgeliefert (storniert=True) —
    ohne Saldowirkung, aber nachvollziehbar (z.B. Storni aus einem
    Eigentümerwechsel). Der Saldo bleibt dadurch unverändert.

    Vorzeichen aus Eigentümersicht: negativer Saldo = Rückstand,
    positiver Saldo = Guthaben.

    Extrahiert aus `PersonenkontoViewSet.kontoauszug` (reines Refactoring, keine
    Verhaltensänderung): die Ansicht liefert exakt dieses Dict, und der
    Mahnschreiben-Kontoauszug (`apps.korrespondenz`) nutzt dieselben Daten
    statt einer zweiten Saldo-Rechnung.
    """
    from apps.buchhaltung.models import Buchung, HausgeldSollstellung

    ev = pk_obj.vertrag
    wj_id = wirtschaftsjahr_id

    # --- Soll-Seite: Sollstellungen aus Nebenbuch (inkl. Storni) ---
    ss_qs = (
        HausgeldSollstellung.objects
        .filter(eigentumsverhaeltnis=ev)
        .select_related('sollstellungslauf')
        .order_by('periode', 'erstellt_am')
    )
    if wj_id:
        from apps.objekte.models import Wirtschaftsjahr
        try:
            wj = Wirtschaftsjahr.objects.get(pk=wj_id)
            ss_qs = ss_qs.filter(periode__year=wj.jahr)
        except Wirtschaftsjahr.DoesNotExist:
            pass

    # --- Haben-Seite: Zahlungseingänge (Buchungen) ---
    haben_qs = (
        Buchung.objects
        .filter(personenkonto=pk_obj, soll_konto__isnull=False, parent_buchung__isnull=True)
        .exclude(status='storniert')
    )
    if wj_id:
        haben_qs = haben_qs.filter(wirtschaftsjahr_id=wj_id)
    haben_qs = haben_qs.order_by('buchungsdatum', 'erstellt_am')

    # Einträge zusammenführen und chronologisch sortieren
    eintraege = []
    for ss in ss_qs:
        typ_label = {'hausgeld': 'Hausgeld', 'sonderumlage': 'Sonderumlage', 'abrechnungsergebnis': 'Abrechnung'}.get(ss.sollstellungs_typ, ss.sollstellungs_typ)
        ist_storniert = ss.storniert_am is not None
        eintraege.append({
            '_datum': ss.periode,
            '_sort2': ss.erstellt_am,
            'id': str(ss.id),
            'typ': 'sollstellung',
            'opos_nr': ss.opos_nr,
            'bu_nr': ss.opos_nr,
            'buchungsdatum': str(ss.periode),
            'buchungstext': f"{typ_label} {ss.periode.strftime('%m/%Y')}",
            'soll': float(ss.soll_betrag) if ss.soll_betrag > 0 else None,
            'haben': float(abs(ss.soll_betrag)) if ss.soll_betrag < 0 else None,
            'hat_detail': False,
            'status': 'storniert' if ist_storniert else ss.status_cached,
            'ist_betrag': float(ss.ist_betrag),
            'storniert': ist_storniert,
            'storniert_am': ss.storniert_am.date().isoformat() if ist_storniert else None,
            'storniert_grund': ss.storniert_grund or None,
        })
    for b in haben_qs:
        eintraege.append({
            '_datum': b.buchungsdatum,
            '_sort2': b.erstellt_am,
            'id': str(b.id),
            'typ': 'buchung',
            'opos_nr': None,
            'bu_nr': b.belegnr or f'BU-{str(b.id)[:8].upper()}',
            'buchungsdatum': str(b.buchungsdatum),
            'buchungstext': b.buchungstext,
            'soll': None,
            'haben': float(b.betrag),
            'hat_detail': b.teilbuchungen.exists(),
            'status': None,
            'ist_betrag': None,
            'storniert': False,
            'storniert_am': None,
            'storniert_grund': None,
        })

    eintraege.sort(key=lambda x: (x['_datum'], x['_sort2'] or ''))

    saldo = Decimal('0.00')
    positionen = []
    for e in eintraege:
        # Stornierte Positionen werden angezeigt, wirken aber nicht auf den Saldo.
        if e['storniert']:
            soll_val = haben_val = Decimal('0')
        else:
            soll_val  = Decimal(str(e['soll']))  if e['soll']  is not None else Decimal('0')
            haben_val = Decimal(str(e['haben'])) if e['haben'] is not None else Decimal('0')
        saldo += haben_val - soll_val
        e['saldo'] = float(saldo)
        e.pop('_datum')
        e.pop('_sort2')
        positionen.append(e)

    einheit_nr = ''
    try:
        einheit_nr = pk_obj.vertrag.einheit.einheit_nr
    except Exception:
        pass

    return {
        'personenkonto': {
            'id': str(pk_obj.id),
            'kontonummer': pk_obj.kontonummer,
            'eigentuemer_name': pk_obj.eigentuemer.name,
            'einheit_nr': einheit_nr,
            'status': pk_obj.status,
        },
        'saldo_gesamt': float(saldo),
        'positionen': positionen,
    }
