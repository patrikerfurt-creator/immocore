"""
Kontextvorschlag: Zu welchem Owner gehoert ein frisch hochgeladenes Dokument?

Owner-Regel (siehe ``Dokument.clean``): genau EINER von Objekt / Einheit /
Person. Dieser Dienst schlaegt genau einen als bevorzugten Owner vor und nennt
zusaetzlich die weiteren aufgeloesten Treffer als Alternativen — vorschlagen,
nicht setzen, wie beim Registervorschlag.

Zwei Stufen, die teure zuletzt:

  Stufe 1 — deterministisch ueber den Dateinamen
    Steht die Objektnummer als eigenes Token im Dateinamen, ist der Fall
    klar: kein KI-Aufruf.

  Stufe 2 — Claude ueber den Dateiinhalt
    Die KI liest den extrahierten Text und nennt die identifizierenden
    MERKMALE (Objektnummer, Objektadresse, Personenname, Einheit). Diese
    Merkmale werden anschliessend DETERMINISTISCH gegen die Stammdaten
    aufgeloest — die KI waehlt keine ID, sie liefert nur Suchbegriffe. So
    kann sie keinen Datensatz erfinden; ein halluzinierter Name findet
    schlicht nichts.

LEITLINIE: vorschlagen, nicht setzen. Unter ``MINDESTKONFIDENZ`` wird kein
bevorzugter Owner gesetzt (``owner`` bleibt leer) — die aufgeloesten Treffer
werden dann nur als unverbindlicher Hinweis zurueckgemeldet.
"""
import json
import logging
import re

from django.db.models import Q

logger = logging.getLogger(__name__)

# Unterhalb dieser Selbsteinschaetzung wird kein bevorzugter Owner gesetzt.
# Bewusst niedriger als beim Register (0.8): ein Kontextvorschlag ist leichter
# zu pruefen (Objekt/Person sind dem Sachbearbeiter vertraut) und die
# deterministische Aufloesung gegen die Stammdaten faengt Halluzinationen
# bereits ab — die KI-Konfidenz ist hier nur die zweite Schranke.
MINDESTKONFIDENZ = 0.6

KI_TEXT_LAENGE = 6000

# Owner-Rangfolge, wenn die KI mehrere Merkmale aufloesen konnte: die
# spezifischste Einheit zuerst, dann das Objekt (der haeufige Normalfall einer
# Hausakte), die Person zuletzt — eine Person wird nur dann bevorzugt, wenn
# weder Einheit noch Objekt getroffen wurden. Die jeweils anderen Treffer
# bleiben als Alternative sichtbar, sodass der Nutzer mit einem Klick
# umstellen kann.
_OWNER_RANG = ['einheit', 'objekt', 'person']

_SYSTEM_PROMPT = """Du hilfst einer WEG-Hausverwaltung, ein Dokument dem \
richtigen Stammsatz zuzuordnen.

Du bekommst Dateiname und Textauszug eines Dokuments. Nenne die \
identifizierenden Merkmale, die TATSAECHLICH im Dokument stehen — rate nichts \
hinzu. Fehlt ein Merkmal, gib null zurueck.

Felder:
- objektnummer: Objekt-, Liegenschafts- oder Kundennummer der Verwaltung, \
falls genannt, sonst null
- objektadresse: Strasse und Hausnummer der betroffenen Liegenschaft, falls \
genannt, sonst null
- person_name: Name des betroffenen Eigentuemers oder Empfaengers, NUR wenn es \
um eine einzelne Person geht, sonst null
- einheit: Wohnungs- oder Einheitsbezeichnung (z.B. "WE 7", "Whg. 3. OG \
links"), sonst null
- konfidenz: 0.0 bis 1.0, wie eindeutig die Zuordnung aus dem Text ist
- begruendung: ein knapper Satz, woran du es festmachst

Antworte AUSSCHLIESSLICH mit einem JSON-Objekt mit genau diesen Schluesseln. \
Kein Markdown, keine Code-Fences."""


def _leeres_ergebnis() -> dict:
    return {
        'owner': None,            # 'objekt' | 'einheit' | 'person' | None
        'objekt': None, 'einheit': None, 'person': None,
        'quelle': 'keine', 'konfidenz': None, 'begruendung': '', 'fehler': '',
    }


def _entpacke_json(text: str) -> dict:
    text = (text or '').strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, ende = text.find('{'), text.rfind('}')
        if start >= 0 and ende > start:
            return json.loads(text[start:ende + 1])
        raise


def _bestimme_owner(ergebnis: dict) -> dict:
    """Setzt ``owner`` auf den spezifischsten aufgeloesten Treffer."""
    for feld in _OWNER_RANG:
        if ergebnis.get(feld) is not None:
            ergebnis['owner'] = feld
            break
    return ergebnis


# ── Stufe 1: Dateiname ───────────────────────────────────────────────────────

def _ueber_dateiname(dateiname: str) -> dict | None:
    from apps.objekte.models import Objekt

    tokens = set(re.findall(r'[0-9A-Za-zÄÖÜäöüß]+', dateiname or ''))
    if not tokens:
        return None
    treffer = (Objekt.objects.exclude(objektnummer='')
               .filter(objektnummer__in=tokens).first())
    if treffer is None:
        return None
    ergebnis = _leeres_ergebnis()
    ergebnis.update({
        'objekt': treffer, 'quelle': 'dateiname', 'konfidenz': 0.95,
        'begruendung': f'Objektnummer "{treffer.objektnummer}" im Dateinamen erkannt.',
    })
    return _bestimme_owner(ergebnis)


# ── Deterministische Aufloesung der KI-Merkmale gegen die Stammdaten ─────────

def _finde_objekt(objektnummer, objektadresse):
    from apps.objekte.models import Objekt

    if objektnummer:
        objekt = Objekt.objects.filter(
            objektnummer__iexact=str(objektnummer).strip()).first()
        if objekt is not None:
            return objekt
    if objektadresse:
        adresse = str(objektadresse).strip()
        # Erst die volle Strasse, dann ersatzweise nur der Strassenname (ohne
        # Hausnummer) — aber nur, wenn er genau EIN Objekt trifft, sonst waere
        # der Vorschlag geraten.
        objekt = Objekt.objects.filter(strasse__icontains=adresse).first()
        if objekt is not None:
            return objekt
        strassenname = re.split(r'\s*\d', adresse, maxsplit=1)[0].strip()
        if len(strassenname) >= 4:
            qs = Objekt.objects.filter(strasse__icontains=strassenname)
            if qs.count() == 1:
                return qs.first()
    return None


def _finde_person(person_name):
    from apps.personen.models import Person

    if not person_name:
        return None
    teile = [t for t in re.split(r'[\s,]+', str(person_name).strip()) if len(t) >= 2]
    if not teile:
        return None
    # Firma: der ganze Name als Teilstring des Firmennamens.
    firma = Person.objects.filter(firmenname__icontains=str(person_name).strip())
    if firma.count() == 1:
        return firma.first()
    # Natuerliche Person: Vor- UND Nachname muessen passen (in beliebiger
    # Reihenfolge), damit ein haeufiger Nachname allein nicht genuegt.
    if len(teile) >= 2:
        erster, letzter = teile[0], teile[-1]
        genau = Person.objects.filter(
            (Q(vorname__iexact=erster) & Q(nachname__iexact=letzter))
            | (Q(vorname__iexact=letzter) & Q(nachname__iexact=erster))
        )
        if genau.count() == 1:
            return genau.first()
    return None


def _finde_einheit(objekt, einheit_hint):
    from apps.objekte.models import Einheit

    if objekt is None or not einheit_hint:
        return None
    hint = str(einheit_hint).strip()
    basis = Einheit.objects.filter(objekt=objekt)
    tokens = re.findall(r'[0-9A-Za-zÄÖÜäöüß]+', hint)
    if tokens:
        treffer = basis.filter(einheit_nr__in=tokens)
        if treffer.count() == 1:
            return treffer.first()
    treffer = basis.filter(lage__icontains=hint)
    if treffer.count() == 1:
        return treffer.first()
    return None


# ── Stufe 2: KI ueber den Inhalt ─────────────────────────────────────────────

def _ueber_ki(dateiname: str, beschreibung: str, inhalt_text: str,
              ergebnis: dict) -> dict:
    """Stufe 2 — wirft nie; ein Fehler landet als Text in ``fehler``."""
    from django.conf import settings

    api_key = getattr(settings, 'ANTHROPIC_API_KEY', None)
    if not api_key:
        ergebnis['begruendung'] = (
            'Keine automatische Zuordnung über den Inhalt (KI nicht konfiguriert).')
        return ergebnis
    if not (inhalt_text or '').strip():
        ergebnis['begruendung'] = (
            'Kein lesbarer Textinhalt für eine inhaltliche Zuordnung gefunden.')
        return ergebnis

    try:
        import anthropic

        modell = getattr(settings, 'ANTHROPIC_MODEL', 'claude-sonnet-4-5')
        teile = [f'Dateiname: {dateiname}']
        if beschreibung:
            teile.append(f'Beschreibung: {beschreibung[:500]}')
        teile.append(f'Textauszug:\n{inhalt_text[:KI_TEXT_LAENGE]}')

        client = anthropic.Anthropic(api_key=api_key)
        antwort = client.messages.create(
            model=modell,
            max_tokens=500,
            system=_SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': '\n'.join(teile)}],
        )
        roh = next((b.text for b in antwort.content
                    if getattr(b, 'type', None) == 'text'), '')
        daten = _entpacke_json(roh)
    except Exception as exc:
        logger.warning('Kontextvorschlag für %s fehlgeschlagen: %s', dateiname, exc)
        ergebnis['fehler'] = f'{type(exc).__name__}: {exc}'
        return ergebnis

    konfidenz = daten.get('konfidenz')
    try:
        konfidenz = round(float(konfidenz), 3) if konfidenz is not None else None
    except (TypeError, ValueError):
        konfidenz = None

    ergebnis.update({
        'quelle': 'ki',
        'konfidenz': konfidenz,
        'begruendung': str(daten.get('begruendung') or '').strip(),
    })

    objekt = _finde_objekt(daten.get('objektnummer'), daten.get('objektadresse'))
    person = _finde_person(daten.get('person_name'))
    einheit = _finde_einheit(objekt, daten.get('einheit'))

    ergebnis['objekt'] = objekt
    ergebnis['einheit'] = einheit
    ergebnis['person'] = person

    if objekt is None and einheit is None and person is None:
        ergebnis['begruendung'] = (
            ergebnis['begruendung']
            or 'Die genannten Merkmale passen zu keinem Stammsatz.')
        return ergebnis

    # Owner nur setzen, wenn die KI sich sicher genug ist — sonst bleiben die
    # Treffer als unverbindlicher Hinweis stehen (owner=None).
    if konfidenz is None or konfidenz >= MINDESTKONFIDENZ:
        _bestimme_owner(ergebnis)
    else:
        ergebnis['begruendung'] = (
            f'{ergebnis["begruendung"]} (Konfidenz {konfidenz:.2f} unter '
            f'{MINDESTKONFIDENZ} — nur als Hinweis)').strip()
    return ergebnis


def schlage_kontext_vor(dateiname: str, beschreibung: str = '',
                        inhalt_text: str = '') -> dict:
    """Ermittelt einen Owner-Vorschlag (Objekt/Einheit/Person) für ein Dokument.

    Rückgabe immer vollständig:
    ``{owner, objekt, einheit, person, quelle, konfidenz, begruendung, fehler}``.
    ``owner`` nennt das bevorzugte Feld (oder ``None``); die drei Felder
    enthalten die aufgelösten Modell-Instanzen (oder ``None``).
    """
    treffer = _ueber_dateiname(dateiname)
    if treffer is not None:
        return treffer
    return _ueber_ki(dateiname, beschreibung, inhalt_text, _leeres_ergebnis())
