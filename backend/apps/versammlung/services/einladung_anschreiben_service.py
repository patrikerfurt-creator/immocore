"""
Anschreiben zur EV-Einladung auf dem Korrespondenz-Briefbogen (Spec 9.4, Phase 6d).

Die Einladung selbst (``versammlung/einladung.html`` mit Tagesordnung) bleibt
unverändert. Beim Versand wird ihr ein kurzes ANSCHREIBEN auf dem Demme-Briefbogen
vorangestellt: Anschrift, Bezugszeichen, Betreff, Anrede, ein Text mit Termin,
Uhrzeit und Ort, Grußformel (nur die Firma unterzeichnet), Anlagenverzeichnis -
und als weitere Seite des Anschreibens die Vollmacht (``anlage_seite`` ohne
Briefkopf, Fußzeile bleibt).

Dieses Modul baut nur das Anschreiben-PDF; das Zusammenfügen zum Stapel
(Anschreiben -> Einladung -> Anlagen) steht in ``einladung_service``.

Das Versammlungsmodul bleibt Eigentümer von Termin, Ort, Tagesordnung, Versandplan
und ``EVVersandprotokoll``: Termin und Ort kommen über die Platzhalter-Gruppe
``versammlung`` direkt aus der EV. Anschrift und Anrede stammen aus den führenden
Einzelfeldern der Person (``anschrift_zeilen``), nicht aus dem Legacy-Feld
``Person.adresse``.

Grundsatz wie im Korrespondenz-Modul: kein Brief mit Lücke. Fehlt dem Briefbogen
eine Pflichtangabe (Anschrift, Bankkonto der WEG), endet der Aufbau mit
``RenderFehler``.
"""
from types import SimpleNamespace

from django.template.loader import render_to_string
from django.utils import timezone

from apps.korrespondenz.models import Briefbogen
from apps.korrespondenz.services import kontext_service, pdf_service, render_service
from apps.korrespondenz.services.render_service import RenderFehler

ANLASS = 'etv_einladung'
VOLLMACHT_TEMPLATE = 'versammlung/anschreiben_vollmacht.html'

ANLAGE_EINLADUNG = 'Einladung zur Eigentümerversammlung mit Tagesordnung'
ANLAGE_VOLLMACHT = 'Vollmacht'

# Art -> Dativ-Adjektiv für den Betreff („Einladung zur … Eigentümerversammlung“).
_ART_DATIV = {
    'ordentlich': 'ordentlichen',
    'ausserordentl': 'außerordentlichen',
    'wiederholung': 'wiederholten',
}

# Brieftext ab der Anrede (Blocksprache der Render-Engine; Termin/Ort/Art aus der EV).
_BLOECKE = [
    {'typ': 'text', 'inhalt': (
        '<p>hiermit berufen wir eine {{ versammlung.art }} Eigentümerversammlung der '
        'Wohnungseigentümergemeinschaft {{ objekt.bezeichnung }} ein.</p>'
    )},
    {'typ': 'text', 'inhalt': (
        '<p><strong>Termin:</strong> {{ versammlung.termin | datum_lang }}, '
        '{{ versammlung.termin | uhrzeit }}<br>'
        '<strong>Ort:</strong> {{ versammlung.ort }}</p>'
    )},
    {'typ': 'text', 'inhalt': (
        'Die Einladung mit der Tagesordnung finden Sie in der Anlage. Sollten Sie nicht '
        'persönlich teilnehmen können, können Sie sich mit der ebenfalls beigefügten '
        'Vollmacht vertreten lassen.\n\n'
        'Für Rückfragen stehen wir Ihnen gerne zur Verfügung.'
    )},
]


def standard_briefbogen():
    """Aktiver Standard-Briefbogen, ``None`` solange keiner angelegt ist (Seed = Phase 7)."""
    return Briefbogen.objects.filter(ist_standard=True, aktiv=True).first()


# --------------------------------------------------------------------------
# Empfänger
# --------------------------------------------------------------------------

def _neutraler_empfaenger(ev) -> dict:
    """Anschriftfeld/Anrede der neutralen Fassung (DMS-Ablage, Portal/Mail) ohne Person."""
    objekt = ev.objekt
    return {
        'anschrift_zeilen': [
            zeile for zeile in (
                'An die Wohnungseigentümer', objekt.bezeichnung, objekt.strasse,
                f'{objekt.plz} {objekt.ort}'.strip(),
            ) if zeile
        ],
        'briefanrede': 'Sehr geehrte Damen und Herren,',
        'briefanrede2': '',
    }


def _pruefe_anschrift(person) -> None:
    """Postversand braucht eine Anschrift in den Einzelfeldern (Legacy ``adresse`` zählt nicht)."""
    if not any((getattr(person, feld) or '').strip() for feld in ('strasse', 'plz', 'ort')):
        raise RenderFehler(
            f'Für {person.name} ist in den Personenstammdaten keine Anschrift '
            '(Straße/PLZ/Ort) hinterlegt - Anschreiben nicht erzeugbar.'
        )


def _einziges_eigentumsverhaeltnis(teilnehmer):
    """Eigentumsverhältnis des Empfängers, wenn er genau eine Einheit vertritt (sonst ``None``)."""
    if teilnehmer is None:
        return None
    anteile = list(teilnehmer.anteile.select_related('eigentumsverhaeltnis')[:2])
    return anteile[0].eigentumsverhaeltnis if len(anteile) == 1 else None


def _einheiten(teilnehmer) -> list:
    if teilnehmer is None:
        return []
    return [
        nr for nr in teilnehmer.anteile.values_list('einheit_nr_snapshot', flat=True) if nr
    ]


# --------------------------------------------------------------------------
# Kontext, Betreff, Body
# --------------------------------------------------------------------------

def baue_kontext(ev, briefbogen, teilnehmer=None) -> dict:
    """Kontext für Briefbogen und Body (Anlass ``etv_einladung``, Gruppe ``versammlung`` aus der EV).

    Ohne Teilnehmer entsteht die neutrale Fassung. Es wird bewusst KEIN Unterzeichner
    übergeben: das Anschreiben ergeht im Namen der Firma (``nur_firma``).
    """
    person = teilnehmer.person if teilnehmer is not None else None
    if person is not None:
        _pruefe_anschrift(person)
    kontext = kontext_service.baue_kontext(
        ANLASS, person=person, objekt=ev.objekt, versammlung=ev,
        eigentumsverhaeltnis=_einziges_eigentumsverhaeltnis(teilnehmer),
        briefbogen=briefbogen, heute=timezone.localdate(),
    )
    if person is None:
        kontext['empfaenger'] = _neutraler_empfaenger(ev)
    return kontext


def baue_betreff(ev) -> str:
    art = _ART_DATIV.get(ev.art, '')
    titel = f'Einladung zur {art} Eigentümerversammlung' if art else 'Einladung zur Eigentümerversammlung'
    return f'{titel} am {timezone.localtime(ev.termin):%d.%m.%Y}'


def rendere_brieftext(kontext: dict) -> str:
    """Brieftext ab der Anrede über die Render-Engine; ``RenderFehler`` bei fehlenden Werten."""
    baustein = SimpleNamespace(betreff='-', inhalt=_BLOECKE, eingabefelder=[], pflicht_platzhalter=[])
    ergebnis = render_service.render(baustein, kontext, {})
    if not ergebnis.ok:
        raise RenderFehler(f'Anschreiben nicht erzeugbar: {ergebnis.fehler}')
    return ergebnis.html


def rendere_vollmacht(ev, kontext: dict, teilnehmer=None) -> str:
    """Vollmacht als ``anlage_seite``: Vollmachtgeber = Empfänger, neutral mit Schreiblinien."""
    return render_to_string(VOLLMACHT_TEMPLATE, {
        'objekt': ev.objekt,
        'anschrift_zeilen': (kontext.get('empfaenger') or {}).get('anschrift_zeilen') if teilnehmer else None,
        'einheiten': _einheiten(teilnehmer),
        'firma': (kontext.get('verwaltung') or {}).get('firma', ''),
        'unser_zeichen': (kontext.get('schreiben') or {}).get('unser_zeichen', ''),
    })


def anlagen_verzeichnis(anlagen=None) -> list:
    """Anlagenblock unter der Grußformel: Einladung, Vollmacht, dann frei angehängte Dokumente."""
    eintraege = [ANLAGE_EINLADUNG, ANLAGE_VOLLMACHT]
    for dokument in anlagen or []:
        text = dokument.dateiname
        if dokument.beschreibung:
            text = f'{text} — {dokument.beschreibung}'
        eintraege.append(text)
    return [pdf_service.AnlagePdf(bezeichnung=e) for e in eintraege]


# --------------------------------------------------------------------------
# Öffentlich
# --------------------------------------------------------------------------

def rendere_anschreiben_pdf(ev, briefbogen, *, teilnehmer=None, anlagen=None) -> bytes:
    """PDF des Anschreibens (Brief + Vollmacht-Seite) auf dem Briefbogen.

    ``teilnehmer`` (``EVTeilnehmer``): personalisierte Fassung für den Postversand.
    Ohne Teilnehmer entsteht die neutrale Fassung (DMS, Mail).
    ``anlagen`` (Dokumente) erscheinen nur im Anlagenverzeichnis; angehängt werden sie
    im ``einladung_service``.

    ``RenderFehler`` bei fehlenden Pflichtangaben des Briefbogens.
    """
    kontext = baue_kontext(ev, briefbogen, teilnehmer)
    ergebnis = render_service.RenderErgebnis(
        html=rendere_brieftext(kontext) + '\n' + rendere_vollmacht(ev, kontext, teilnehmer),
        betreff=baue_betreff(ev),
    )
    return pdf_service.erzeuge_pdf(
        None, kontext, briefbogen, ergebnis, anlagen_verzeichnis(anlagen), nur_firma=True,
    )
