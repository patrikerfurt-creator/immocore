"""
WKZ OP-Generator — erzeugt periodisch fällige WKZ-OPs + zugehörige KreditorOPs.
"""
import calendar
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction, IntegrityError
from django.utils import timezone

logger = logging.getLogger(__name__)


@dataclass
class Periode:
    periode_von: date
    periode_bis: date
    faellig_am: date


@dataclass
class ErzeugungsErgebnis:
    erzeugt: int = 0
    fehler: list = None

    def __post_init__(self):
        if self.fehler is None:
            self.fehler = []


# ---------------------------------------------------------------------------
# Datums-Arithmetik (kein dateutil nötig)
# ---------------------------------------------------------------------------

def _add_months(d: date, months: int) -> date:
    """Addiert N Monate zu einem Datum; klemmt auf den letzten Monatstag."""
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


# ---------------------------------------------------------------------------
# Wochenend-Regel
# ---------------------------------------------------------------------------

def wende_wochenend_regel_an(d: date, regel: str) -> date:
    """
    Passt ein Datum an, wenn es auf ein Wochenende fällt.
    vor       → Freitag davor
    zurueck   → Montag danach
    unveraendert → keine Änderung
    """
    if regel == 'unveraendert':
        return d
    wd = d.weekday()  # 0=Mo, 5=Sa, 6=So
    if wd < 5:
        return d  # Werktag → unverändert
    if regel == 'vor':
        # Freitag = 4, Samstag = 5 → 1 Tag zurück, Sonntag = 6 → 2 Tage zurück
        return d - timedelta(days=wd - 4)
    else:  # zurueck
        # Samstag → +2 Tage (Montag), Sonntag → +1 Tag (Montag)
        return d + timedelta(days=7 - wd)


# ---------------------------------------------------------------------------
# Fälligkeitsberechnung
# ---------------------------------------------------------------------------

def berechne_fallige_perioden(vorlage, stichtag: date) -> list[Periode]:
    """
    Gibt alle Perioden zurück, deren faellig_am in
    [erste_faelligkeit, stichtag + vorlauf_tage] liegt und für die noch
    kein WKZ-OP existiert.
    """
    from apps.buchhaltung.models import WiederkehrendeBuchungOP

    if vorlage.rhythmus == 'frei':
        return []

    schritt_map = {
        'monatlich': 1, 'zweimonatlich': 2, 'quartalsweise': 3,
        'halbjaehrlich': 6, 'jaehrlich': 12,
    }
    schritt = schritt_map[vorlage.rhythmus]
    grenze = stichtag + timedelta(days=vorlage.vorlauf_tage)

    perioden = []
    anker = vorlage.erste_faelligkeit
    i = 0

    while True:
        periode_von = _add_months(anker, schritt * i)
        periode_bis = _add_months(anker, schritt * (i + 1)) - timedelta(days=1)
        faellig_am = wende_wochenend_regel_an(periode_von, vorlage.bei_wochenende)

        # Außerhalb Geltungszeitraum → Abbruch
        if faellig_am > grenze:
            break
        if faellig_am < vorlage.gueltig_ab:
            i += 1
            continue
        if vorlage.gueltig_bis and faellig_am > vorlage.gueltig_bis:
            break

        # Idempotenz: bereits vorhandenen OP überspringen
        if not WiederkehrendeBuchungOP.objects.filter(
            vorlage=vorlage, periode_von=periode_von, periode_bis=periode_bis,
        ).exists():
            perioden.append(Periode(periode_von, periode_bis, faellig_am))

        i += 1
        if i > 1000:  # Sicherheitsabbruch
            logger.warning("WKZ OP-Generator: Sicherheitsabbruch bei Vorlage %s", vorlage.id)
            break

    return perioden


# ---------------------------------------------------------------------------
# OP-Erzeugung
# ---------------------------------------------------------------------------

def _naechste_op_nummer() -> int:
    from apps.buchhaltung.models import KreditorOP
    last = (
        KreditorOP.objects
        .select_for_update()
        .order_by('-op_nummer')
        .values_list('op_nummer', flat=True)
        .first()
    )
    return (last + 1) if last else 100000


def baue_verwendungszweck(vorlage, periode_von: date, periode_bis: date) -> str:
    return (
        f"{vorlage.bezeichnung} "
        f"{periode_von.strftime('%m/%Y')}–{periode_bis.strftime('%m/%Y')}"
    )


@transaction.atomic
def erzeuge_einzelnen_op(vorlage, periode: Periode) -> 'WiederkehrendeBuchungOP':
    from apps.buchhaltung.models import KreditorOP, WiederkehrendeBuchungOP

    op_nr = _naechste_op_nummer()

    kreditor_op = KreditorOP.objects.create(
        op_nummer=op_nr,
        kreditor=vorlage.kreditor,
        objekt=vorlage.objekt,
        buchung=None,  # WKZ: Buchung entsteht erst bei Bankabgang
        betrag_ursprung=vorlage.betrag_gesamt,
        betrag_offen=vorlage.betrag_gesamt,
        faellig_ab=periode.faellig_am,
        verwendungszweck=baue_verwendungszweck(vorlage, periode.periode_von, periode.periode_bis),
        herkunft='wkz_vorlage',
    )

    wkz_status = 'bescheid_fehlt' if vorlage.bescheid_pflicht else 'erzeugt'
    wkz_op = WiederkehrendeBuchungOP.objects.create(
        vorlage=vorlage,
        kreditor_op=kreditor_op,
        periode_von=periode.periode_von,
        periode_bis=periode.periode_bis,
        faellig_am=periode.faellig_am,
        status=wkz_status,
    )

    if vorlage.bescheid_pflicht:
        logger.warning(
            "WKZ-OP %s: Bescheid fehlt für Vorlage '%s' (Periode %s–%s). "
            "Bitte Bescheid-PDF nachreichen.",
            wkz_op.id, vorlage.bezeichnung, periode.periode_von, periode.periode_bis,
        )

    logger.info(
        "WKZ-OP %s erzeugt: Vorlage '%s', Periode %s–%s, Fälligkeit %s, OP-Nr %s",
        wkz_op.id, vorlage.bezeichnung,
        periode.periode_von, periode.periode_bis, periode.faellig_am, op_nr,
    )
    return wkz_op


# ---------------------------------------------------------------------------
# Hauptlauf
# ---------------------------------------------------------------------------

def erzeuge_faellige_ops(stichtag: date) -> ErzeugungsErgebnis:
    """
    Iteriert über alle aktiven Vorlagen und erzeugt OPs für alle
    Fälligkeiten im Vorlauf-Fenster. Idempotent über Unique-Constraint.
    """
    from apps.buchhaltung.models import WiederkehrendeBuchungVorlage
    from django.db.models import Q

    ergebnis = ErzeugungsErgebnis()
    aktive_vorlagen = WiederkehrendeBuchungVorlage.objects.filter(
        status='aktiv',
        gueltig_ab__lte=stichtag,
    ).filter(
        Q(gueltig_bis__isnull=True) | Q(gueltig_bis__gte=stichtag)
    ).select_related('objekt', 'kreditor')

    for vorlage in aktive_vorlagen:
        try:
            fallige_perioden = berechne_fallige_perioden(vorlage, stichtag)
            for periode in fallige_perioden:
                try:
                    erzeuge_einzelnen_op(vorlage, periode)
                    ergebnis.erzeugt += 1
                except IntegrityError:
                    logger.info(
                        "WKZ-OP für Vorlage %s Periode %s–%s bereits vorhanden (Idempotenz)",
                        vorlage.id, periode.periode_von, periode.periode_bis,
                    )
        except Exception as e:
            ergebnis.fehler.append({'vorlage_id': str(vorlage.id), 'fehler': str(e)})
            logger.exception("WKZ-OP-Erzeugung fehlgeschlagen für Vorlage %s", vorlage.id)

    logger.info(
        "WKZ-OP-Lauf abgeschlossen: %s erzeugt, %s Fehler",
        ergebnis.erzeugt, len(ergebnis.fehler),
    )
    return ergebnis


# ---------------------------------------------------------------------------
# OP verwerfen
# ---------------------------------------------------------------------------

@transaction.atomic
def verwirf_wkz_op(wkz_op_id, grund: str, user) -> 'WiederkehrendeBuchungOP':
    from apps.buchhaltung.models import WiederkehrendeBuchungOP, KreditorOP

    wkz_op = WiederkehrendeBuchungOP.objects.select_for_update().get(pk=wkz_op_id)
    if wkz_op.status in ('bankabgang_erfolgt', 'abweichend_geklaert'):
        raise ValueError("OP mit bereits gebuchtem Bankabgang kann nicht verworfen werden.")

    wkz_op.status = 'verworfen'
    wkz_op.klaerungs_grund = grund
    wkz_op.save(update_fields=['status', 'klaerungs_grund'])

    # Zugehörigen KreditorOP stornieren
    op = wkz_op.kreditor_op
    op.status = 'storniert'
    op.betrag_offen = Decimal('0')
    op.save(update_fields=['status', 'betrag_offen'])

    logger.info(
        "WKZ-OP %s verworfen von %s: %s (KreditorOP %s storniert)",
        wkz_op_id, user, grund, op.op_nummer,
    )
    return wkz_op
