"""
Mahnwesen-Service
- konfig_fuer(): objektspezifische Pflicht-Konfiguration (MahnEinstellung)
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

# Globale Fristen-Staffel (Verzugstage + Zahlungsfrist je Stufe). Die Mahngebühr steht
# NICHT hier, sondern je Objekt in ``MahnEinstellung.mahngebuehr`` (fest, bei jeder Stufe
# gleich). Aktuell ist nur die 2-stufige Staffel definiert (3. Stufe folgt auf Ansage).
MAHNSTUFEN = [
    {'stufe': 1, 'verzug_tage': 15, 'frist': 14, 'bezeichnung': '1. Mahnung'},
    {'stufe': 2, 'verzug_tage': 30, 'frist': 10, 'bezeichnung': '2. Mahnung'},
]

_STAFFEL_JE_STUFE = {s['stufe']: s for s in MAHNSTUFEN}


class MahnKonfigFehlt(ValueError):
    """Für das Objekt ist keine ``MahnEinstellung`` hinterlegt (Mahnen blockiert).

    ``ValueError``, damit die Views die Meldung als HTTP 400 ausliefern. Ein Batch
    (Mahnlauf über mehrere Objekte) fängt genau diese Klasse je Objekt ab und macht
    mit dem nächsten Objekt weiter.
    """


def konfig_fuer(objekt):
    """Die ``MahnEinstellung`` des Objekts (Instanz oder Id); ohne sie ``MahnKonfigFehlt``."""
    from apps.buchhaltung.models import MahnEinstellung

    konfig = MahnEinstellung.objects.filter(objekt=objekt).first()
    if konfig is None:
        raise MahnKonfigFehlt(
            'Für dieses Objekt ist keine Mahn-Konfiguration hinterlegt '
            '(Mahngebühr/Stufenzahl). Bitte zuerst konfigurieren.'
        )
    return konfig


def staffel_fuer_stufe(stufe: int) -> dict | None:
    """Staffel-Eintrag (Verzugstage, Frist, Bezeichnung) einer Mahnstufe; ``None`` wenn unbekannt."""
    return _STAFFEL_JE_STUFE.get(stufe)


def zahlungsfrist_tage(stufe) -> int | None:
    """Zahlungsfrist in Kalendertagen der Stufe (aus der Staffel); ``None`` wenn die Stufe unbekannt ist."""
    eintrag = _STAFFEL_JE_STUFE.get(stufe)
    return eintrag['frist'] if eintrag else None


def _get_ba(kuerzel: str):
    from apps.buchhaltung.models import Buchungsart
    return Buchungsart.objects.filter(kuerzel=kuerzel, aktiv=True).first()


def simuliere_mahnlauf(objekt_id: str, stichtag: date | None = None) -> dict:
    """Gibt Vorschau der zu mahnenden Personenkonten zurück.

    Wirft ``MahnKonfigFehlt`` (ValueError), wenn das Objekt keine ``MahnEinstellung`` hat.
    """
    from apps.buchhaltung.models import OffenerPosten
    from apps.konten.models import Personenkonto

    konfig = konfig_fuer(objekt_id)
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
        if aktuelle_stufe >= konfig.anzahl_mahnstufen:
            # Letzte Stufe bereits erreicht: kein weiterer Lauf, kein Rückschritt.
            continue
        naechste_stufe = min(aktuelle_stufe + 1, konfig.anzahl_mahnstufen)
        stufen_config = _STAFFEL_JE_STUFE[naechste_stufe]

        aelteste_op = ops_faellig.first()
        verzug_tage = (stichtag - aelteste_op.faellig_ab).days

        if verzug_tage < stufen_config['verzug_tage']:
            continue

        op_summe = sum(op.betrag_offen for op in ops_faellig)
        gebuehr = konfig.mahngebuehr
        zinsen = Decimal('0.00')

        if konfig.zinsen_erheben:
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
            'zahlungsfrist_tage': stufen_config['frist'],
            'eskaliert_zu_forderungsfall': naechste_stufe == konfig.anzahl_mahnstufen,
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

    konfig = konfig_fuer(lauf.objekt_id)
    ba_mahng = _get_ba('MAHNG')
    ba_verzz = _get_ba('VERZZ')
    stichtag = lauf.erstellt_am.date()
    vorschau = simuliere_mahnlauf(str(lauf.objekt_id), stichtag)

    # Modul Vorlagen & Korrespondenz (Spec 9.1): NUR hinter dem Schalter. Ohne ihn
    # bleibt dieser Lauf unverändert (kein Import, keine Prüfung, keine Schreiben).
    anbindung, snapshots = None, {}
    if _korrespondenz_aktiv():
        from apps.korrespondenz.services import mahn_anbindung_service as anbindung
        anbindung.pruefe_vorlagen(
            {m['mahnstufe'] for m in vorschau['mahnungen']}, lauf.objekt, konfig.anzahl_mahnstufen,
        )
        snapshots = anbindung.erfasse_snapshots(vorschau['mahnungen'], stichtag)

    ok = 0
    angelegt = []
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

            mahnung = Mahnung.objects.create(
                lauf=lauf,
                personenkonto=pk,
                mahnstufe=m['mahnstufe'],
                offene_posten_summe=Decimal(str(m['op_summe'])),
                gebuehr=Decimal(str(m['gebuehr'])),
                zinsen=Decimal(str(m['zinsen'])),
                buchung_gebuehr=b_gebuehr,
                buchung_zinsen=b_zinsen,
            )
            angelegt.append(mahnung)

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

    if anbindung is not None:
        # Blockade (MahnBlockade) rollt den gesamten Lauf zurück; die Freigabe der
        # Schreiben (PDF, Kontoauszug, Versand) folgt erst nach dem Commit.
        schreiben_ids = anbindung.erstelle_schreiben(
            lauf, angelegt, snapshots, user, konfig.anzahl_mahnstufen,
        )
        anbindung.plane_freigabe(schreiben_ids, user)

    lauf.status = 'ausgefuehrt'
    lauf.anzahl_mahnungen = ok
    lauf.gesamt_gebuehren = Decimal(str(vorschau['gesamt_gebuehren']))
    lauf.gesamt_zinsen = Decimal(str(vorschau['gesamt_zinsen']))
    lauf.save(update_fields=[
        'status', 'anzahl_mahnungen', 'gesamt_gebuehren', 'gesamt_zinsen'
    ])

    return {'ok': ok}


def _korrespondenz_aktiv() -> bool:
    """Schalter KORRESPONDENZ_MAHNWESEN_AKTIV (Default False, nur per Umgebung)."""
    from django.conf import settings
    return bool(getattr(settings, 'KORRESPONDENZ_MAHNWESEN_AKTIV', False))


def _fallback_konto(objekt):
    from apps.konten.models import Konto
    return (
        Konto.objects.filter(wirtschaftsjahr__objekt=objekt, aktiv=True)
        .order_by('kontonummer')
        .first()
    )
