"""PDF-Erzeugung und Ablage der Schreiben (Spec 5.5).

Ablauf: gerenderter Body (``render_service.render``) + Kontext + Briefbogen ->
HTML (``brief_base.html``) -> WeasyPrint -> PDF -> ``Dokument``.

Das PDF entsteht bei der Freigabe und wird danach NIE neu gerendert:
``erzeuge_schreiben_dokument`` ist idempotent - hat das Schreiben schon ein
Dokument, wird dieses zurückgegeben. Der Freigabe-Trigger selbst (Phase 4)
ruft nur diese Funktion auf.
"""
import hashlib
from dataclasses import dataclass

import weasyprint
from django.core.files.base import ContentFile
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.dokumente.models import Dokument

from . import brief_layout_service
from .render_service import RenderFehler

DOKUMENT_KATEGORIE = 'Korrespondenz'
TEMPLATE = 'korrespondenz/brief_base.html'


@dataclass
class AnlagePdf:
    """Anlage (Spec 3.7): Bezeichnung für den Hinweis am Briefende, optional fertiges PDF zum Anhängen."""
    bezeichnung: str
    pdf: bytes = None


# --------------------------------------------------------------------------
# HTML / PDF
# --------------------------------------------------------------------------

def rendere_brief_html(briefbogen, kontext: dict, render_ergebnis, anlagen=None,
                       nur_firma: bool = False) -> str:
    """Setzt Briefbogen, Kontext und gerenderten Body zum vollständigen HTML zusammen.

    ``nur_firma``: Schluss ohne persönlichen Unterzeichner (nur die Firma).
    """
    if not render_ergebnis.ok:
        raise RenderFehler(f'Schreiben nicht erzeugbar: {render_ergebnis.fehler}')
    layout = brief_layout_service.baue_layout(
        briefbogen, kontext, render_ergebnis.betreff, render_ergebnis.html,
        anlagen_bezeichnungen=[a.bezeichnung for a in anlagen or []],
        nur_firma=nur_firma,
    )
    return render_to_string(TEMPLATE, layout)


def html_zu_pdf(html: str) -> bytes:
    return weasyprint.HTML(string=html).write_pdf()


def haenge_anlagen_an(pdf: bytes, anlagen) -> bytes:
    """Hängt fertige Anlagen-PDFs hinter das Schreiben (ohne PDFs bleibt ``pdf`` unverändert)."""
    zusaetze = [a.pdf for a in anlagen or [] if a.pdf]
    if not zusaetze:
        return pdf
    import pymupdf
    with pymupdf.open(stream=pdf, filetype='pdf') as ziel:
        for zusatz in zusaetze:
            with pymupdf.open(stream=zusatz, filetype='pdf') as quelle:
                ziel.insert_pdf(quelle)
        return ziel.tobytes(deflate=True)


def erzeuge_pdf(version, kontext: dict, briefbogen, render_ergebnis, anlagen=None,
                nur_firma: bool = False) -> bytes:
    """Erzeugt das PDF eines Schreibens.

    ``version``: die gerenderte ``VorlagenVersion`` (Herkunft; das PDF selbst
    entsteht aus ``render_ergebnis``, damit eine spätere Vorlagenänderung
    nichts verändern kann). ``render_ergebnis``: Ergebnis von
    ``render_service.render``. Fehler -> ``RenderFehler`` ("nicht erzeugbar"),
    nie ein Brief mit Lücke.
    """
    html = rendere_brief_html(briefbogen, kontext, render_ergebnis, anlagen, nur_firma)
    return haenge_anlagen_an(html_zu_pdf(html), anlagen)


# --------------------------------------------------------------------------
# Ablage
# --------------------------------------------------------------------------

def _kontext_felder(schreiben) -> dict:
    """Genau EIN Kontext-FK (Owner-Regel B-Hybrid): Vorgang, sonst Person."""
    if schreiben.vorgang_id:
        return {'vorgang_id': schreiben.vorgang_id}
    return {'person_id': schreiben.empfaenger_id}


def _dokument_datum(kontext: dict):
    return (kontext.get('schreiben') or {}).get('datum') or timezone.localdate()


def lege_pdf_ab(pdf: bytes, schreiben, betreff: str, kontext: dict, hochgeladen_von) -> Dokument:
    """Legt das PDF als revisionssicheres ``Dokument`` (Typ ``korrespondenz``) ab."""
    dateiname = f'{schreiben.nummer}.pdf'
    return Dokument.objects.create(
        datei=ContentFile(pdf, name=dateiname),
        dateiname=dateiname,
        titel=f'{schreiben.nummer} {betreff}'[:200],
        kategorie=DOKUMENT_KATEGORIE,
        dokument_typ='korrespondenz',
        beschreibung=betreff,
        dokument_datum=_dokument_datum(kontext),
        hochgeladen_von=hochgeladen_von,
        sha256=hashlib.sha256(pdf).hexdigest(),
        revisionssicher=True,
        revisionssicher_seit=timezone.now(),
        **_kontext_felder(schreiben),
    )


@transaction.atomic
def erzeuge_schreiben_dokument(schreiben, kontext: dict, briefbogen, render_ergebnis,
                               user, anlagen=None) -> Dokument:
    """Erzeugt PDF + Dokument für ein freigegebenes Schreiben - genau einmal.

    Idempotent: hat das Schreiben bereits ein Dokument, wird es unverändert
    zurückgegeben (PDF wird nach der Freigabe nie neu gerendert). Die Zeile
    wird gesperrt, damit zwei parallele Freigaben nicht zwei Dokumente anlegen.
    """
    from apps.korrespondenz.models import Schreiben

    gesperrt = Schreiben.objects.select_for_update().get(pk=schreiben.pk)
    if gesperrt.dokument_id:
        schreiben.dokument = gesperrt.dokument
        return gesperrt.dokument

    pdf = erzeuge_pdf(schreiben.vorlage_version, kontext, briefbogen, render_ergebnis, anlagen)
    dokument = lege_pdf_ab(
        pdf, schreiben, render_ergebnis.betreff, kontext, user or schreiben.freigegeben_von,
    )
    schreiben.dokument = dokument
    schreiben.save(update_fields=['dokument'])
    return dokument
