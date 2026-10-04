"""Auflösung der Vorlagen-Anlagen zu konkreten PDF-Anlagen (Spec 3.7, 9.2).

``VorlageAnlage`` beschreibt, WAS hinter ein Schreiben gehört; dieser Service macht
daraus die konkreten Dokumente:

* ``art='dokument'``          das an der Anlage hinterlegte Dokument (festes PDF, z. B. SEPA-Formular)
* ``art='objekt_kategorie'``  das aktuelle Dokument des Objekts in dieser Kategorie (z. B. Hausordnung)

Reihenfolge = ``VorlageAnlage.reihenfolge``. ``bedingung`` (z. B. ``ev.sepa_mandat_fehlt``) wird
gegen den Kontext des Schreibens ausgewertet - trifft sie nicht zu, entfällt die Anlage.
Fehlt eine ``pflicht``-Anlage (kein Dokument, Datei fehlt, kein PDF), ist das Schreiben
"nicht erzeugbar" (``RenderFehler``); eine fehlende optionale Anlage entfällt mit Log-Warnung.

Die Auflösung passiert EINMAL beim Erzeugen des Schreibens (``schreiben_service._rendere``) und
wird als Liste von Dokument-Ids im ``kontext_snapshot`` eingefroren (``SNAPSHOT_ANLAGEN``).
Vorschau und Freigabe laden genau diese Dokumente (``lade_pdfs``) - so passt die Anlage
immer zum geprüften Text (z. B. Hinweisblock "SEPA-Mandat beigefügt").
"""
import logging
from dataclasses import dataclass

from django.db.models import F

from apps.dokumente.models import Dokument
from apps.dokumente.services import beleg_service

from . import render_service
from .pdf_service import AnlagePdf
from .render_service import RenderFehler

logger = logging.getLogger(__name__)


@dataclass
class AufgeloesteAnlage:
    bezeichnung: str
    dokument: Dokument


def _als_pdf_lesbar(dokument: Dokument) -> bool:
    """Ist das Dokument ein PDF und die Datei vorhanden?"""
    name = (dokument.dateiname or dokument.datei.name or '').lower()
    if not name.endswith('.pdf'):
        return False
    return beleg_service.dokument_pfad(dokument).is_file()


def _objekt_dokument(objekt, kategorie: str):
    """Aktuellstes (nicht abgelöstes) PDF des Objekts in der Kategorie; ``None`` wenn keines."""
    if objekt is None or not kategorie:
        return None
    kandidaten = Dokument.objects.filter(
        objekt=objekt, kategorie__iexact=kategorie, nachfolger_versionen__isnull=True,
    ).order_by(F('dokument_datum').desc(nulls_last=True), '-hochgeladen_am')
    for dokument in kandidaten:
        if _als_pdf_lesbar(dokument):
            return dokument
    return None


def _finde_dokument(anlage, objekt):
    if anlage.art == 'dokument':
        dokument = anlage.dokument
        return dokument if dokument is not None and _als_pdf_lesbar(dokument) else None
    if anlage.art == 'objekt_kategorie':
        return _objekt_dokument(objekt, anlage.objekt_kategorie)
    return None


def _fehlt_text(anlage) -> str:
    if anlage.art == 'dokument':
        grund = 'kein PDF-Dokument hinterlegt oder Datei nicht vorhanden'
    else:
        grund = f'kein PDF des Objekts in der Kategorie "{anlage.objekt_kategorie}"'
    return f'Pflichtanlage "{anlage.bezeichnung}": {grund}.'


def loese_auf(vorlage, objekt, kontext: dict) -> list:
    """Löst die Anlagen der Vorlage zu ``AufgeloesteAnlage`` auf (Reihenfolge, Bedingung, Pflicht).

    Wirft ``RenderFehler`` mit ALLEN fehlenden Pflichtanlagen.
    """
    ergebnis, fehler = [], []
    for anlage in vorlage.anlagen.order_by('reihenfolge', 'bezeichnung'):
        if anlage.bedingung and not render_service.bedingung_erfuellt(anlage.bedingung, kontext):
            continue
        dokument = _finde_dokument(anlage, objekt)
        if dokument is not None:
            ergebnis.append(AufgeloesteAnlage(anlage.bezeichnung, dokument))
        elif anlage.pflicht:
            fehler.append(_fehlt_text(anlage))
        else:
            logger.warning('Anlage "%s" (%s) nicht auffindbar - entfällt.', anlage.bezeichnung, vorlage.code)
    if fehler:
        raise RenderFehler(' '.join(fehler))
    return ergebnis


def als_refs(anlagen) -> list:
    """JSON-sichere Form für ``kontext_snapshot``: ``[{'bezeichnung', 'dokument_id'}]`` in Reihenfolge."""
    return [{'bezeichnung': a.bezeichnung, 'dokument_id': str(a.dokument.pk)} for a in anlagen]


def lade_pdfs(refs) -> list:
    """Lädt die eingefrorenen Anlagen als ``AnlagePdf`` (mit PDF-Bytes) für Vorschau/Freigabe.

    Wirft ``RenderFehler``, wenn ein Dokument inzwischen fehlt oder nicht lesbar ist.
    """
    ergebnis = []
    for ref in refs or []:
        dokument = Dokument.objects.filter(pk=ref['dokument_id']).first()
        if dokument is None or not _als_pdf_lesbar(dokument):
            raise RenderFehler(f'Anlage "{ref["bezeichnung"]}" ist nicht mehr verfügbar.')
        ergebnis.append(AnlagePdf(
            bezeichnung=ref['bezeichnung'],
            pdf=beleg_service.dokument_pfad(dokument).read_bytes(),
        ))
    return ergebnis
