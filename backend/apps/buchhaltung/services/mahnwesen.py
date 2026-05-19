"""
Mahnwesen-Service
- simuliere_mahnlauf(): Vorschau (ohne Schreiben)
- fuehre_mahnlauf_aus(): Erzeugt Mahngebühr + Zinsen-Buchungen
"""
import logging
from decimal import Decimal
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from .zinsen import berechne_verzugszinsen

logger = logging.getLogger(__name__)

# Konfigurierbare Defaults (später per Objekt überschreibbar)
MAHNSTUFEN = [
    {'stufe': 0, 'verzug_tage': 14,  'gebuehr': Decimal('0.00'),  'bezeichnung': 'Zahlungserinnerung'},
    {'stufe': 1, 'verzug_tage': 28,  'gebuehr': Decimal('5.00'),  'bezeichnung': '1. Mahnung'},
    {'stufe': 2, 'verzug_tage': 42,  'gebuehr': Decimal('10.00'), 'bezeichnung': '2. Mahnung'},
    {'stufe': 3, 'verzug_tage': 56,  'gebuehr': Decimal('15.00'), 'bezeichnung': 'Letzte Mahnung'},
]


def _get_ba(kuerzel: str):
    from apps.buchhaltung.models import Buchungsart
    return Buchungsart.objects.filter(kuerzel=kuerzel, aktiv=True).first()


def simuliere_mahnlauf(objekt_id: str, stichtag: date | None = None) -> dict:
    """Gibt Vorschau der zu mahnenden Personenkonten zurück."""
    from apps.buchhaltung.models import OffenerPosten
    from apps.konten.models import Personenkonto

    if stichtag is None:
        stichtag = date.today()

    mahnungen = []
    gesamt_gebuehren = Decimal('0.00')
    gesamt_zinsen = Decimal('0.00')

    pks = Personenkonto.objects.filter(
        objekt_id=objekt_id, status='aktiv'
    ).prefetch_related('offene_posten', 'mahnsperren')

    for pk in pks:
        aktive_sperre = pk.mahnsperren.filter(
            gesperrt_bis__gte=stichtag,
            aufgehoben_am__isnull=True,
        ).first()
        if aktive_sperre:
            continue

        ops_faellig = pk.offene_posten.filter(
            status__in=['offen', 'teilverrechnet'],
            faellig_ab__lte=stichtag,
        ).order_by('faellig_ab')

        if not ops_faellig.exists():
            continue

        max_stufe = ops_faellig.values_list('mahnstufe', flat=True)
        aktuelle_stufe = max(max_stufe) if max_stufe else 0
        naechste_stufe = min(aktuelle_stufe + 1, 3)
        stufen_config = MAHNSTUFEN[naechste_stufe]

        aelteste_op = ops_faellig.first()
        verzug_tage = (stichtag - aelteste_op.faellig_ab).days

        if verzug_tage < stufen_config['verzug_tage']:
            continue

        op_summe = sum(op.betrag_offen for op in ops_faellig)
        gebuehr = stufen_config['gebuehr']
        zinsen = Decimal('0.00')

        if naechste_stufe >= 1:
            for op in ops_faellig:
                zinsen += berechne_verzugszinsen(
                    op.betrag_offen, op.faellig_ab, stichtag
                )
            zinsen = zinsen.quantize(Decimal('0.01'))

        gesamt_gebuehren += gebuehr
        gesamt_zinsen += zinsen

        mahnungen.append({
            'personenkonto_id': str(pk.id),
            'eigentuemer': pk.eigentuemer.name,
            'mahnstufe': naechste_stufe,
            'op_summe': float(op_summe),
            'gebuehr': float(gebuehr),
            'zinsen': float(zinsen),
            'eskaliert_zu_forderungsfall': naechste_stufe == 3,
        })

    return {
        'stichtag': str(stichtag),
        'anzahl': len(mahnungen),
        'gesamt_gebuehren': float(gesamt_gebuehren),
        'gesamt_zinsen': float(gesamt_zinsen),
        'mahnungen': mahnungen,
    }


@transaction.atomic
def fuehre_mahnlauf_aus(lauf_id: str, user) -> dict:
    """Schreibt Mahngebühr + Zinsen-Buchungen, hebt Mahnstufen an."""
    from apps.buchhaltung.models import (
        Mahnlauf, Mahnung, Buchung, OffenerPosten
    )
    from apps.konten.models import Personenkonto

    lauf = Mahnlauf.objects.select_for_update().get(pk=lauf_id)
    if lauf.status not in ('simulation', 'freigegeben'):
        raise ValueError(f'Mahnlauf hat Status {lauf.status}')

    ba_mahng = _get_ba('MAHNG')
    ba_verzz = _get_ba('VERZZ')
    stichtag = lauf.erstellt_am.date()
    vorschau = simuliere_mahnlauf(str(lauf.objekt_id), stichtag)

    ok = 0
    for m in vorschau['mahnungen']:
        try:
            pk = Personenkonto.objects.get(pk=m['personenkonto_id'])

            b_gebuehr = None
            if ba_mahng and Decimal(str(m['gebuehr'])) > 0:
                konto = _fallback_konto(lauf.objekt)
                b_gebuehr = Buchung.objects.create(
                    objekt=lauf.objekt,
                    buchungsart=ba_mahng,
                    betrag=Decimal(str(m['gebuehr'])),
                    soll_konto=konto,
                    haben_konto=konto,
                    buchungsdatum=stichtag,
                    buchungstext=f"Mahngebühr Stufe {m['mahnstufe']}",
                    status='festgeschrieben',
                    erstellt_von=user,
                )

            b_zinsen = None
            if ba_verzz and Decimal(str(m['zinsen'])) > 0:
                konto = _fallback_konto(lauf.objekt)
                b_zinsen = Buchung.objects.create(
                    objekt=lauf.objekt,
                    buchungsart=ba_verzz,
                    betrag=Decimal(str(m['zinsen'])),
                    soll_konto=konto,
                    haben_konto=konto,
                    buchungsdatum=stichtag,
                    buchungstext=f"Verzugszinsen § 288 BGB Stufe {m['mahnstufe']}",
                    status='festgeschrieben',
                    erstellt_von=user,
                )

            Mahnung.objects.create(
                lauf=lauf,
                personenkonto=pk,
                mahnstufe=m['mahnstufe'],
                offene_posten_summe=Decimal(str(m['op_summe'])),
                gebuehr=Decimal(str(m['gebuehr'])),
                zinsen=Decimal(str(m['zinsen'])),
                buchung_gebuehr=b_gebuehr,
                buchung_zinsen=b_zinsen,
            )

            pk.offene_posten.filter(
                status__in=['offen', 'teilverrechnet']
            ).update(mahnstufe=m['mahnstufe'])

            if m['eskaliert_zu_forderungsfall']:
                pk.offene_posten.filter(
                    status__in=['offen', 'teilverrechnet']
                ).update(status='forderungsfall')

            ok += 1

        except Exception as exc:
            logger.exception('Mahnfehler für %s', m)

    lauf.status = 'ausgefuehrt'
    lauf.anzahl_mahnungen = ok
    lauf.gesamt_gebuehren = Decimal(str(vorschau['gesamt_gebuehren']))
    lauf.gesamt_zinsen = Decimal(str(vorschau['gesamt_zinsen']))
    lauf.save(update_fields=[
        'status', 'anzahl_mahnungen', 'gesamt_gebuehren', 'gesamt_zinsen'
    ])

    return {'ok': ok}


def _fallback_konto(objekt):
    from apps.konten.models import Konto
    return (
        Konto.objects.filter(wirtschaftsjahr__objekt=objekt, aktiv=True)
        .order_by('kontonummer')
        .first()
    )
