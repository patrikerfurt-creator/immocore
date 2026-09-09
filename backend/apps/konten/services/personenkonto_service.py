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
