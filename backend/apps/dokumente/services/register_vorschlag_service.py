"""
Registervorschlag: In welches Aktenregister gehört ein Dokument?

Dreistufig, wie überall im Projekt — die teure Stufe kommt zuletzt:

  Stufe 0 — deterministisch über den Kreditor
    Ein Wartungsvertrag der Süwag gehört in "01 Versorger", jedes Mal. Wenn
    am Kreditor ein Standardregister hinterlegt ist, endet die Suche hier:
    kein API-Aufruf, kein Zweifelsfall, keine Konfidenz.

  Stufe 1 — regelbasiert über den Dokumenttyp
    Ein Beschluss gehört in die Beschlusssammlung, eine EV-Einladung zu den
    Eigentümerversammlungen. Eine Handvoll fester Zuordnungen.

  Stufe 2 — Claude, nur für den Rest
    Freie Korrespondenz. Die KI bekommt die Registerliste des Objekts und
    schlägt eines vor.

LEITLINIE: vorschlagen, nicht einsortieren.

Ein falsch abgelegtes Dokument ist schlimmer als ein unsortiertes — das
unsortierte findet man unter "Ohne Register", das falsch einsortierte
nirgends. Unterhalb von ``MINDESTKONFIDENZ`` bleibt das Register deshalb
leer, und der Vorschlag wird nur zurückgemeldet.
"""
import json
import logging
import re

logger = logging.getLogger(__name__)

# Unterhalb dieser Selbsteinschätzung wird nichts gesetzt. 0.8 ist bewusst
# streng: die Register sind thematisch trennscharf, ein Zögern der KI heisst
# hier meist, dass der Fall wirklich mehrdeutig ist.
MINDESTKONFIDENZ = 0.8

KI_TEXT_LAENGE = 3000

# Stufe 1: Dokumenttyp -> Registercode. Bewusst knapp — nur was eindeutig ist.
TYP_ZU_REGISTER = {
    'beschluss': '15',    # Beschlusssammlung
    'abrechnung': '19',   # Abrechnung / Wirtschaftsplan
}

_SYSTEM_PROMPT = """Du ordnest ein Dokument einer WEG-Hausverwaltung in deren \
Aktengliederung ein.

Du bekommst die Registerliste und eine Kurzbeschreibung des Dokuments \
(Betreff und Textauszug). Waehle GENAU EIN Register.

- code: exakt einer der vorgegebenen Codes. Passt nichts eindeutig, gib \
null zurueck statt zu raten — ein falsch einsortiertes Dokument ist \
schlimmer als ein unsortiertes.
- konfidenz: 0.0 bis 1.0, wie sicher du bist.
- begruendung: ein knapper Satz, woran du es festmachst.

Achte auf die Abgrenzungen, die in den Registerhinweisen stehen. Erfinde \
keine Codes.

Antworte AUSSCHLIESSLICH mit einem JSON-Objekt mit den Schluesseln code, \
konfidenz, begruendung. Kein Markdown, keine Code-Fences."""


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


def _ueber_kreditor(dokument):
    """Stufe 0: Standardregister des Kreditors, falls gepflegt."""
    try:
        rechnung = dokument.rechnung
    except Exception:
        return None
    if rechnung is None or not rechnung.kreditor_id:
        return None
    return getattr(rechnung.kreditor, 'standard_register', None)


def _ueber_dokumenttyp(dokument, register_nach_code: dict):
    """Stufe 1: feste Zuordnung über den Dokumenttyp."""
    code = TYP_ZU_REGISTER.get(dokument.dokument_typ)
    return register_nach_code.get(code) if code else None


def schlage_register_vor(dokument, register: list) -> dict:
    """Ermittelt einen Registervorschlag für ein Dokument.

    ``register`` ist die Liste der in dieser Akte gültigen Register (inkl.
    der objektspezifischen Untergliederung).

    Rückgabe immer vollständig:
    ``{register, quelle, konfidenz, begruendung, fehler}`` — ``register``
    ist ``None``, wenn nichts Sicheres gefunden wurde.
    """
    ergebnis = {'register': None, 'quelle': 'keine', 'konfidenz': None,
                'begruendung': '', 'fehler': ''}
    if not register:
        ergebnis['fehler'] = 'Keine Register vorhanden.'
        return ergebnis

    nach_code = {r.code: r for r in register}

    treffer = _ueber_kreditor(dokument)
    if treffer is not None:
        return {**ergebnis, 'register': treffer, 'quelle': 'kreditor',
                'konfidenz': 1.0,
                'begruendung': 'Standardregister des Kreditors.'}

    treffer = _ueber_dokumenttyp(dokument, nach_code)
    if treffer is not None:
        return {**ergebnis, 'register': treffer, 'quelle': 'dokumenttyp',
                'konfidenz': 1.0,
                'begruendung': f'Feste Zuordnung fuer Typ '
                               f'"{dokument.get_dokument_typ_display()}".'}

    return _ueber_ki(dokument, register, nach_code, ergebnis)


def _baue_prompt(dokument, register: list) -> str:
    zeilen = []
    for r in register:
        zeile = f'- {r.code}: {r.bezeichnung}'
        if r.hinweis:
            zeile += f' — {r.hinweis}'
        zeilen.append(zeile)

    beschreibung = [
        f'Bezeichnung: {dokument.anzeigename}',
        f'Dateiname: {dokument.dateiname}',
    ]
    if dokument.beschreibung:
        beschreibung.append(f'Beschreibung: {dokument.beschreibung[:500]}')
    if dokument.mail_import_id:
        protokoll = dokument.mail_import
        beschreibung.append(f'Absender: {protokoll.absender}')
        beschreibung.append(f'Betreff: {protokoll.betreff}')
        if protokoll.body_auszug:
            beschreibung.append(
                f'Textauszug:\n{protokoll.body_auszug[:KI_TEXT_LAENGE]}')

    return ('Registerliste:\n' + '\n'.join(zeilen)
            + '\n\nDokument:\n' + '\n'.join(beschreibung))


def _ueber_ki(dokument, register: list, nach_code: dict, ergebnis: dict) -> dict:
    """Stufe 2 — wirft nie; ein Fehler landet als Text in ``fehler``."""
    try:
        import anthropic
        from django.conf import settings

        api_key = getattr(settings, 'ANTHROPIC_API_KEY', None)
        if not api_key:
            raise RuntimeError('ANTHROPIC_API_KEY nicht konfiguriert')

        modell = getattr(settings, 'ANTHROPIC_MODEL', 'claude-sonnet-4-5')
        client = anthropic.Anthropic(api_key=api_key)
        antwort = client.messages.create(
            model=modell,
            max_tokens=1000,
            system=_SYSTEM_PROMPT,
            messages=[{'role': 'user',
                       'content': _baue_prompt(dokument, register)}],
        )
        roh = next((b.text for b in antwort.content
                    if getattr(b, 'type', None) == 'text'), '')
        daten = _entpacke_json(roh)

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

        code = daten.get('code')
        code = str(code).strip() if code else ''
        if not code or code.lower() == 'null':
            ergebnis['begruendung'] = (
                ergebnis['begruendung'] or 'Kein Register passt eindeutig.')
            return ergebnis
        if code not in nach_code:
            # Halluzinierter Code: nicht uebernehmen, aber sichtbar lassen —
            # genau solche Faelle will ein Testlauf zeigen.
            ergebnis['fehler'] = f'Unbekannter Registercode von der KI: {code!r}'
            return ergebnis
        if konfidenz is not None and konfidenz < MINDESTKONFIDENZ:
            ergebnis['begruendung'] = (
                f'{ergebnis["begruendung"]} (Konfidenz {konfidenz:.2f} unter '
                f'{MINDESTKONFIDENZ} — nicht gesetzt)').strip()
            return ergebnis

        ergebnis['register'] = nach_code[code]
        return ergebnis

    except Exception as exc:
        logger.warning('Registervorschlag fuer %s fehlgeschlagen: %s',
                       dokument.dateiname, exc)
        ergebnis['fehler'] = f'{type(exc).__name__}: {exc}'
        return ergebnis
