"""PDF-Vorschau einer Vorlagenversion im Editor (Spec 8: ``POST /versionen/{id}/vorschau/``).

Läuft dieselbe Kette wie ein echtes Schreiben (Kontext -> Render -> Briefbogen ->
PDF), legt aber NICHTS an: kein ``Schreiben``, kein ``Dokument``, keine
Nummer aus dem Nummernkreis. Vorschau ist für jeden Status der Version erlaubt
(auch ``entwurf``).

Die Vorschau ist eine LAYOUT-Vorschau mit Beispieldaten: was sich aus Person/Einheit/Objekt
nicht auflösen lässt oder leer ist (``wechsel``, ``mahnung``, ``vorgang``, Betreuer,
Bankkonto, Pflicht-Eingabefelder ...), wird aus den Registry-Beispielen aufgefüllt
(``beispiel_kontext_service``; reale Werte haben Vorrang). Das PDF trägt deshalb auf jeder
Seite den Hinweis ``VORSCHAU_HINWEIS`` und ein dezentes Wasserzeichen. Fehler bleiben nur
noch, wo der Vorlagentext selbst fehlerhaft ist (Syntax, unbekannter Platzhalter,
Pflicht-Platzhalter fehlt im Text, ungültiger Eingabewert, kein Briefbogen).

Das echte Erzeugen eines Schreibens (``schreiben_service``) ist davon unberührt und bleibt
streng: dort gibt es keine Beispielwerte.
"""
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.korrespondenz.models import Briefbogen

from django.template.loader import render_to_string

from . import (
    beispiel_kontext_service, brief_layout_service, kontext_service, pdf_service, render_service,
    vorlage_service,
)
from .render_service import RenderFehler

VORSCHAU_NUMMER = 'VORSCHAU'
VORSCHAU_HINWEIS = 'VORSCHAU – Beispieldaten, kein echtes Schreiben'


def _briefbogen_fuer(vorlage):
    """Briefbogen der Vorlage, sonst der aktive Standard-Briefbogen."""
    if vorlage.briefbogen_id:
        return vorlage.briefbogen
    return Briefbogen.objects.filter(ist_standard=True, aktiv=True).first()


def _baue_vorschau_kontext(version, person, objekt, einheit, eingabewerte, briefbogen, user, heute):
    """(kontext, eingabewerte): echter Kontext + Beispiele; Eingaben des Aufrufers haben Vorrang."""
    vorlage = version.vorlage
    eingabewerte = beispiel_kontext_service.fuelle_eingabewerte(
        version.eingabefelder, eingabewerte, heute)
    echt = kontext_service.baue_kontext(
        vorlage.anlass, person=person, objekt=objekt, einheit=einheit,
        eingabewerte=eingabewerte, parameter=version.parameter, unterzeichner=user,
        briefbogen=briefbogen, schreiben_nummer=VORSCHAU_NUMMER, heute=heute,
    )
    kontext = beispiel_kontext_service.fuelle_kontext_mit_beispielen(vorlage.anlass, echt, heute)
    return kontext, eingabewerte


def _vorschau_pdf(briefbogen, kontext, ergebnis) -> bytes:
    """Wie ``pdf_service.erzeuge_pdf`` (ohne Anlagen), aber mit Vorschau-Hinweis im Layout."""
    layout = brief_layout_service.baue_layout(briefbogen, kontext, ergebnis.betreff, ergebnis.html)
    layout['vorschau_hinweis'] = VORSCHAU_HINWEIS
    return pdf_service.html_zu_pdf(render_to_string(pdf_service.TEMPLATE, layout))


def erzeuge_vorschau_pdf(version, person, *, einheit=None, eingabewerte=None, user=None) -> bytes:
    """PDF der ``version`` gegen den frei gewählten Beispiel-Empfänger ``person`` (ohne Persistierung)."""
    vorlage = version.vorlage
    briefbogen = _briefbogen_fuer(vorlage)
    if briefbogen is None:
        raise ValidationError('Kein Briefbogen vorhanden (weder an der Vorlage noch als Standard).')
    objekt = einheit.objekt if einheit is not None else vorlage.objekt
    try:
        kontext, eingabewerte = _baue_vorschau_kontext(
            version, person, objekt, einheit, eingabewerte, briefbogen, user, timezone.localdate())
        ergebnis = render_service.render(
            version, kontext, eingabewerte,
            bausteine=vorlage_service.lade_bausteine(version.inhalt, objekt),
        )
        if not ergebnis.ok:
            raise RenderFehler(ergebnis.fehler)
        return _vorschau_pdf(briefbogen, kontext, ergebnis)
    except RenderFehler as exc:
        raise ValidationError(f'Vorschau nicht erzeugbar: {exc}') from exc
