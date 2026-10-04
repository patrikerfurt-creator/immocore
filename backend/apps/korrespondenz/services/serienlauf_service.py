"""Serienlauf: Serienbrief an die Eigentümer eines Objekts (Spec 7.4, 3.9).

Ablauf::

    anlegen (vorschau) -> erzeuge_schreiben (zur_pruefung) -> freigeben (freigegeben)
        -> verarbeite (versendet | teilweise_fehler)

    ``abbrechen`` (vor dem Versand): vorschau | zur_pruefung | freigegeben -> abgebrochen.

* Ein Schreiben je Eigentumsverhältnis (bei mehreren Einheiten eines
  Eigentümers je Einheit eines - Flächenzeile und Vollmacht sind einheitsbezogen).
* Nicht erzeugbare Schreiben (``entwurf`` mit ``fehler``) blockieren nur sich
  selbst: sie stehen in der Vorschau mit Ursache, der Lauf geht ohne sie weiter.
* ``verarbeite`` (Celery-Task ``korrespondenz.serienlauf_verarbeiten``) gibt
  jedes Schreiben frei, versendet die E-Mails und bündelt die Briefe in einem
  Druckstapel (Sammel-PDF = ``Serienlauf.druck_dokument``). Ein Fehler bei einem
  Schreiben bricht die übrigen nicht ab.

Empfängerfilter (``Serienlauf.empfaenger_filter``)::

    {"einheit_typ": ["Wohnung", ...],        # optional; String oder Liste
     "email_zustimmung": "mit" | "ohne",     # optional; sonst alle
     "ausschliessen": [<EV-Id>, ...],        # manuelle Abwahl
     "hinzufuegen": [<EV-Id>, ...]}          # manuelle Zuwahl (EV desselben Objekts)
"""
import logging
import random
from dataclasses import dataclass, field
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.korrespondenz.models import Schreiben, Serienlauf
from apps.personen.models import EigentumsVerhaeltnis

from . import druckstapel_service, eingabefelder_service, schreiben_service

logger = logging.getLogger(__name__)

VORSCHAU_ANZAHL = 3
FILTER_SCHLUESSEL = ('einheit_typ', 'email_zustimmung', 'ausschliessen', 'hinzufuegen')


@dataclass
class SerienVorschau:
    """Vorschau (7.4 Punkt 4): zufällige Beispiele plus alle nicht erzeugbaren Schreiben."""
    zufaellig: list = field(default_factory=list)
    nicht_erzeugbar: list = field(default_factory=list)
    erzeugbar_anzahl: int = 0


# --------------------------------------------------------------------------
# Empfängerkreis
# --------------------------------------------------------------------------

def _ids(werte, name: str) -> set:
    try:
        return {UUID(str(w)) for w in werte or []}
    except ValueError as exc:
        raise ValidationError(f'Empfängerfilter "{name}": ungültige ID ({exc}).') from exc


def normalisiere_filter(empfaenger_filter) -> dict:
    """Prüft den Empfängerfilter und liefert die normalisierte Form."""
    filter_ = dict(empfaenger_filter or {})
    unbekannt = set(filter_) - set(FILTER_SCHLUESSEL)
    if unbekannt:
        raise ValidationError('Unbekannte Filter: ' + ', '.join(sorted(unbekannt)))
    typen = filter_.get('einheit_typ') or []
    if isinstance(typen, str):
        typen = [typen]
    zustimmung = filter_.get('email_zustimmung') or ''
    if zustimmung not in ('', 'mit', 'ohne'):
        raise ValidationError('Filter "email_zustimmung" muss "mit" oder "ohne" sein.')
    return {
        'einheit_typ': [str(t) for t in typen],
        'email_zustimmung': zustimmung,
        'ausschliessen': sorted(str(i) for i in _ids(filter_.get('ausschliessen'), 'ausschliessen')),
        'hinzufuegen': sorted(str(i) for i in _ids(filter_.get('hinzufuegen'), 'hinzufuegen')),
    }


def ermittle_empfaenger(objekt, empfaenger_filter, stichtag=None) -> list:
    """Eigentumsverhältnisse, die einen Brief bekommen (aktive Eigentümer des Objekts + Filter)."""
    filter_ = normalisiere_filter(empfaenger_filter)
    stichtag = stichtag or timezone.localdate()
    im_objekt = EigentumsVerhaeltnis.objects.filter(einheit__objekt=objekt)

    aktiv = Q(beginn__lte=stichtag) & (Q(ende__isnull=True) | Q(ende__gte=stichtag))
    auswahl = im_objekt.filter(aktiv)
    if filter_['einheit_typ']:
        auswahl = auswahl.filter(einheit__einheit_typ__in=filter_['einheit_typ'])
    # Email-Zustimmung richtet sich nach dem tatsächlichen Zusteller: ist ein
    # Zustellungsbevollmächtigter hinterlegt, zählt dessen Zustellweg/Zustimmung,
    # sonst der des Eigentümers selbst.
    zugestimmt_ohne_zb = Q(
        person__zustellungsbevollmaechtigter__isnull=True,
        person__zustellweg='email',
        person__zustellweg_zustimmung_am__isnull=False,
    )
    zugestimmt_mit_zb = Q(
        person__zustellungsbevollmaechtigter__isnull=False,
        person__zustellungsbevollmaechtigter__zustellweg='email',
        person__zustellungsbevollmaechtigter__zustellweg_zustimmung_am__isnull=False,
    )
    zugestimmt = zugestimmt_ohne_zb | zugestimmt_mit_zb
    if filter_['email_zustimmung'] == 'mit':
        auswahl = auswahl.filter(zugestimmt)
    elif filter_['email_zustimmung'] == 'ohne':
        auswahl = auswahl.exclude(zugestimmt)

    ids = set(auswahl.values_list('pk', flat=True))
    zusaetzlich = _ids(filter_['hinzufuegen'], 'hinzufuegen')
    gefunden = set(im_objekt.filter(pk__in=zusaetzlich).values_list('pk', flat=True))
    if gefunden != zusaetzlich:
        raise ValidationError('Zuwahl: Eigentumsverhältnis gehört nicht zu diesem Objekt.')
    ids = (ids | gefunden) - _ids(filter_['ausschliessen'], 'ausschliessen')
    return list(
        im_objekt.filter(pk__in=ids).select_related('person', 'einheit')
        .order_by('einheit__einheit_nr', 'person__nachname', 'person__vorname')
    )


# --------------------------------------------------------------------------
# Anlegen, Schreiben erzeugen, Vorschau
# --------------------------------------------------------------------------

@transaction.atomic
def anlegen(version, objekt, *, empfaenger_filter=None, eingabewerte=None,
            unterzeichner=None, user=None) -> Serienlauf:
    """Legt einen Serienlauf im Status ``vorschau`` an (noch ohne Schreiben)."""
    if version.status != 'freigegeben':
        raise ValidationError(f'{version} ist nicht freigegeben.')
    if version.vorlage.objekt_id not in (None, objekt.pk):
        raise ValidationError('Die Vorlage gehört zu einem anderen Objekt.')
    return Serienlauf.objects.create(
        vorlage_version=version, objekt=objekt,
        empfaenger_filter=normalisiere_filter(empfaenger_filter),
        eingabewerte=eingabewerte or {}, unterzeichner=unterzeichner or user,
        status='vorschau', erstellt_von=user,
    )


@transaction.atomic
def erzeuge_schreiben(lauf: Serienlauf, user) -> Serienlauf:
    """``vorschau`` -> ``zur_pruefung``: ein Schreiben je Eigentumsverhältnis erzeugen und rendern."""
    lauf = Serienlauf.objects.select_for_update().get(pk=lauf.pk)
    if lauf.status != 'vorschau':
        raise ValidationError('Die Schreiben dieses Serienlaufs wurden bereits erzeugt.')
    empfaenger = ermittle_empfaenger(lauf.objekt, lauf.empfaenger_filter)
    if not empfaenger:
        raise ValidationError('Der Empfängerkreis ist leer.')
    for ev in empfaenger:
        schreiben_service.erstelle_aus_version(
            lauf.vorlage_version, ev.person, objekt=lauf.objekt, einheit=ev.einheit,
            eigentumsverhaeltnis=ev, serienlauf=lauf, eingabewerte=lauf.eingabewerte,
            unterzeichner=lauf.unterzeichner, user=user,
        )
    lauf.anzahl = len(empfaenger)
    lauf.status = 'zur_pruefung'
    lauf.save(update_fields=['anzahl', 'status'])
    return lauf


@transaction.atomic
def starte(version, objekt, *, empfaenger_filter=None, eingabewerte=None,
           unterzeichner=None, user=None) -> Serienlauf:
    """Legt den Serienlauf an und erzeugt sofort alle Schreiben (Vorschau liegt danach vor).

    Alles oder nichts: bei leerem Empfängerkreis bleibt kein leerer Lauf zurück.
    """
    lauf = anlegen(
        version, objekt, empfaenger_filter=empfaenger_filter, eingabewerte=eingabewerte,
        unterzeichner=unterzeichner, user=user,
    )
    return erzeuge_schreiben(lauf, user)


def erzeugbare_schreiben(lauf: Serienlauf):
    return lauf.schreiben.filter(status='zur_pruefung').select_related('empfaenger', 'einheit')


def nicht_erzeugbare_schreiben(lauf: Serienlauf):
    return lauf.schreiben.filter(status='entwurf').exclude(fehler='').select_related('empfaenger', 'einheit')


def vorschau(lauf: Serienlauf) -> SerienVorschau:
    """3 zufällige erzeugbare Schreiben (stabil je Lauf) + alle nicht erzeugbaren mit Ursache."""
    erzeugbar = list(erzeugbare_schreiben(lauf).order_by('nummer'))
    ziehung = random.Random(str(lauf.pk)).sample(erzeugbar, min(VORSCHAU_ANZAHL, len(erzeugbar)))
    return SerienVorschau(
        zufaellig=sorted(ziehung, key=lambda s: s.nummer),
        nicht_erzeugbar=list(nicht_erzeugbare_schreiben(lauf).order_by('nummer')),
        erzeugbar_anzahl=len(erzeugbar),
    )


# --------------------------------------------------------------------------
# Freigabe und Verarbeitung
# --------------------------------------------------------------------------

def freigabe_blocker(lauf: Serienlauf) -> list:
    """Gründe, warum der Lauf nicht freigegeben werden kann (leer = freigebbar)."""
    if lauf.status != 'zur_pruefung':
        return [f'Der Serienlauf ist nicht in Prüfung ({lauf.get_status_display()}).']
    pruefung = eingabefelder_service.validiere(lauf.vorlage_version.eingabefelder, lauf.eingabewerte)
    blocker = list(pruefung.fehler)
    if not erzeugbare_schreiben(lauf).exists():
        blocker.append('Es gibt kein erzeugbares Schreiben.')
    return blocker


@transaction.atomic
def freigeben(lauf: Serienlauf, user) -> Serienlauf:
    """``zur_pruefung`` -> ``freigegeben``. Die Verarbeitung folgt über ``verarbeite`` (Celery)."""
    lauf = Serienlauf.objects.select_for_update().get(pk=lauf.pk)
    if lauf.status == 'freigegeben':
        return lauf          # idempotent: erneutes Anstoßen der Verarbeitung ist erlaubt
    blocker = freigabe_blocker(lauf)
    if blocker:
        raise ValidationError(blocker)
    lauf.status = 'freigegeben'
    lauf.freigegeben_am = timezone.now()
    lauf.freigegeben_von = user
    lauf.save(update_fields=['status', 'freigegeben_am', 'freigegeben_von'])
    return lauf


ABBRECHBAR = ('vorschau', 'zur_pruefung', 'freigegeben')
# Schreiben, die im bereits freigegebenen Lauf zeigen, dass die Verarbeitung angelaufen ist.
IN_VERARBEITUNG = ('freigegeben', 'versendet', 'versand_fehlgeschlagen')


@transaction.atomic
def abbrechen(lauf: Serienlauf, user=None) -> Serienlauf:
    """``vorschau``/``zur_pruefung``/``freigegeben`` -> ``abgebrochen``; offene Schreiben -> ``verworfen``.

    * Verworfen werden die Schreiben in ``entwurf``/``zur_pruefung`` (über
      ``schreiben_service.verwerfen``). Versendete sowie bereits freigegebene
      Schreiben (revisionssicheres PDF) bleiben unangetastet.
    * Ein bereits freigegebener Lauf ist nur abbrechbar, solange die Verarbeitung
      noch nicht angelaufen ist (kein Schreiben ``freigegeben``/``versendet``/
      ``versand_fehlgeschlagen``); sonst ``ValidationError``.
    * Abgebrochene Läufe sind endgültig: nicht erneut freigebbar oder verarbeitbar.
    """
    lauf = Serienlauf.objects.select_for_update().get(pk=lauf.pk)
    if lauf.status not in ABBRECHBAR:
        raise ValidationError(
            f'Der Serienlauf kann nicht abgebrochen werden ({lauf.get_status_display()}).')
    if lauf.status == 'freigegeben' and lauf.schreiben.filter(status__in=IN_VERARBEITUNG).exists():
        raise ValidationError(
            'Die Verarbeitung des Serienlaufs ist bereits angelaufen und kann nicht mehr abgebrochen werden.')
    for schreiben in lauf.schreiben.filter(status__in=('entwurf', 'zur_pruefung')).order_by('nummer'):
        schreiben_service.verwerfen(schreiben, user)
    lauf.status = 'abgebrochen'
    lauf.save(update_fields=['status'])
    return lauf


def _verarbeite_schreiben(schreiben: Schreiben, user) -> bool:
    """Gibt ein Schreiben frei und versendet es. ``True`` = kein Fehler."""
    try:
        if schreiben.status == 'zur_pruefung':
            schreiben_service.freigeben(schreiben, user)
        if schreiben.status in ('freigegeben', 'versand_fehlgeschlagen'):
            return schreiben_service.versenden(schreiben, user).ergebnis != 'fehlgeschlagen'
        return True
    except Exception:  # noqa: BLE001 - ein Schreiben darf den Lauf nicht abbrechen
        logger.exception('Serienlauf: Schreiben %s konnte nicht verarbeitet werden.', schreiben.nummer)
        return False


def _erzeuge_druckstapel(lauf: Serienlauf, user) -> bool:
    """Bündelt die druckbereiten Briefe des Laufs; ``True`` = kein Fehler (auch wenn nichts zu drucken ist)."""
    ids = list(druckstapel_service.druckbereite_schreiben().filter(serienlauf=lauf)
               .values_list('pk', flat=True))
    if not ids:
        return True
    try:
        stapel = druckstapel_service.erzeuge(user, schreiben_ids=ids)
    except Exception:  # noqa: BLE001
        logger.exception('Serienlauf %s: Druckstapel konnte nicht erzeugt werden.', lauf.pk)
        return False
    lauf.druck_dokument = stapel.dokument
    lauf.save(update_fields=['druck_dokument'])
    return True


def verarbeite(lauf: Serienlauf, user) -> Serienlauf:
    """``freigegeben`` -> ``versendet``/``teilweise_fehler``: Mails raus, Briefe in den Druckstapel.

    Erneut aufrufbar (``teilweise_fehler``): bereits erledigte Schreiben werden
    nicht doppelt versendet.
    """
    lauf = Serienlauf.objects.get(pk=lauf.pk)
    if lauf.status not in ('freigegeben', 'teilweise_fehler'):
        raise ValidationError(f'Serienlauf kann in Status "{lauf.status}" nicht verarbeitet werden.')
    ohne_fehler = True
    for schreiben in lauf.schreiben.exclude(status__in=('entwurf', 'verworfen', 'versendet')).order_by('nummer'):
        ohne_fehler &= _verarbeite_schreiben(schreiben, user)
    ohne_fehler &= _erzeuge_druckstapel(lauf, user)

    offen = lauf.schreiben.filter(
        status__in=('entwurf', 'zur_pruefung', 'versand_fehlgeschlagen')
    ).exists()
    lauf.status = 'versendet' if ohne_fehler and not offen else 'teilweise_fehler'
    lauf.save(update_fields=['status'])
    return lauf
