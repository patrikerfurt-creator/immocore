"""
Mail-Import: liest ``.eml``- und ``.msg``-Dateien aus einem Ordner-Posteingang
und erzeugt daraus Vorgänge (Testaufbau für die spätere DOPRE-/Graph-Anbindung,
siehe ``docs/VERSIONEN.md`` Phase 2).

Der Ordner ersetzt bewusst das echte Postfach: dieselbe Verarbeitungskette,
nur mit einer Dateiquelle statt IMAP/Graph. Wird später ein echtes Postfach
angebunden, tauscht man ausschliesslich ``parse_mail`` gegen den Postfach-
Abruf — ``verarbeite_mail`` und die gesamte Erkennung bleiben unverändert.

``.eml`` liest Python mit Bordmitteln, ``.msg`` (Outlook) über ``extract-msg``.
Beide Parser liefern dasselbe ``ParsedMail``; alles danach kennt das
Quellformat nicht mehr.

ERKENNUNG IN ZWEI STUFEN (gleiches Muster wie Buchungserkennung und
Rechnungs-OCR):

  Stufe 1 — regelbasiert, deterministisch, kostenlos:
    Absenderadresse -> ``Person`` -> aktives ``EigentumsVerhaeltnis`` ->
    ``Einheit``/``Objekt``. Findet Stufe 1 nichts, wird NICHT geraten: der
    Vorgang entsteht dann gar nicht (Status ``nicht_zugeordnet``). Das ist
    Absicht — ein Vorgang an der falschen Einheit ist teurer als keiner.

  Stufe 2 — Claude API, nur Klassifikation:
    Vorgangstyp, Priorität und ein aufgeräumter Betreff aus Betreff+Body.
    Die KI ordnet bewusst KEINE Person und KEIN Objekt zu — diese Zuordnung
    bleibt bei Stufe 1 gegen echte Stammdaten. Fällt die KI aus, entsteht der
    Vorgang trotzdem (Fallback-Typ ``sonstiges``); ein nicht erreichbarer
    Anthropic-Endpunkt darf den Posteingang nie blockieren.

Datenschutz-Hinweis (gleiches Muster wie ``antwort_vorschlag_service``):
Betreff und Mailtext gehen an die Anthropic-API. Absenderadresse und
Personenname werden dafür NICHT mitgeschickt — die Klassifikation braucht
sie nicht.

Jede verarbeitete Datei hinterlässt genau eine Zeile in
``MailImportProtokoll``, auch im Fehlerfall. Das ist die Grundlage der
Auswertung ``mail_scan --auswertung``.
"""
import email
import email.header
import email.policy
import email.utils
import hashlib
import json
import logging
import pathlib
import re
from dataclasses import dataclass, field
from datetime import datetime

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.personen.models import EigentumsVerhaeltnis, Person
from apps.vorgaenge.models import (
    MailImportProtokoll, Vorgang, VorgangEreignis, VorgangTyp,
)

logger = logging.getLogger(__name__)

MAIL_SYSTEM_USERNAME = 'immocore-mail'

ENDUNG_EML = '.eml'
ENDUNG_MSG = '.msg'
# ``.eml`` liest Python selbst, ``.msg`` (Outlook) braucht ``extract-msg``.
# Outlook legt beim Ziehen in einen Ordner ``.msg`` an — ohne dieses Format
# müsste jede Testmail erst umständlich konvertiert werden.
ERLAUBTE_ENDUNGEN = {ENDUNG_EML, ENDUNG_MSG}

# Anhänge dieser Typen werden als Dokument am Vorgang abgelegt. Alles andere
# (Signaturbilder, vCards, winzige Inline-Grafiken) wird nur gezählt — sonst
# besteht das DMS nach zehn Mails aus Firmenlogos.
ANHANG_ENDUNGEN = {'.pdf', '.jpg', '.jpeg', '.png', '.tiff', '.tif',
                   '.doc', '.docx', '.xls', '.xlsx', '.csv'}
ANHANG_MIN_BYTES = 20 * 1024

# "AW:", "Re:", "Fwd:" usw. am Betreffanfang — beliebig oft geschachtelt.
_REPLY_PRAEFIX = re.compile(
    r'^\s*(?:(?:re|aw|fw|fwd|wg|antw)\s*(?:\[\d+\])?\s*:\s*)+', re.IGNORECASE)
# Vorgangsnummer im Betreff, z.B. "[V-26-00042]" oder "V-26-00042"
_VORGANGSNUMMER = re.compile(r'\bV-\d{2}-\d{5}\b', re.IGNORECASE)
_HTML_TAG = re.compile(r'<[^>]+>')
_MEHRFACH_LEERZEILE = re.compile(r'\n{3,}')

BODY_AUSZUG_LAENGE = 2000
# Wie viel Mailtext an die KI geht. Mehr bringt für die Klassifikation nichts,
# kostet aber Tokens — und lange Zitat-Historien am Mailende sind ohnehin
# Rauschen.
KI_BODY_LAENGE = 4000


@dataclass
class ParsedMail:
    """Das aus einer ``.eml`` gelesene Rohmaterial — bewusst ohne jede
    Interpretation, damit ein späterer Postfach-Abruf dieselbe Struktur
    liefern kann."""
    dateiname: str
    absender_email: str = ''
    absender_name: str = ''
    empfaenger: str = ''
    betreff: str = ''
    betreff_bereinigt: str = ''
    body: str = ''
    message_id: str = ''
    in_reply_to: str = ''
    references: list = field(default_factory=list)
    gesendet_am: datetime | None = None
    anhaenge: list = field(default_factory=list)  # [(dateiname, bytes)]
    anhaenge_gesamt: int = 0
    # Die Originaldatei als Bytes — sie wird unveraendert im DMS abgelegt
    # (Aufbewahrungspflicht: das Original mit allen Headern ist der Nachweis,
    # nicht der extrahierte Text). Beim spaeteren Postfach-Abruf steht hier
    # die Rohmail statt des Dateiinhalts.
    rohdaten: bytes = b''


# ---------------------------------------------------------------------------
# Stufe 0 — Parsing
# ---------------------------------------------------------------------------

def _html_zu_text(html: str) -> str:
    """Grobe HTML->Text-Reduktion für Mails ohne text/plain-Teil.

    Bewusst ohne zusätzliche Bibliothek (kein BeautifulSoup als neue
    Abhängigkeit): für die Klassifikation reicht der Rohtext, es geht hier
    nicht um originalgetreue Darstellung.
    """
    text = re.sub(r'(?is)<(script|style).*?</\1>', ' ', html)
    text = re.sub(r'(?i)<br\s*/?>', '\n', text)
    text = re.sub(r'(?i)</p\s*>', '\n\n', text)
    text = _HTML_TAG.sub(' ', text)
    ersetzungen = [
        ('&nbsp;', ' '), ('&amp;', '&'), ('&lt;', '<'), ('&gt;', '>'),
        ('&quot;', '"'), ('&#39;', "'"), ('&auml;', 'ä'), ('&ouml;', 'ö'),
        ('&uuml;', 'ü'), ('&Auml;', 'Ä'), ('&Ouml;', 'Ö'), ('&Uuml;', 'Ü'),
        ('&szlig;', 'ß'),
    ]
    for roh, ersatz in ersetzungen:
        text = text.replace(roh, ersatz)
    text = re.sub(r'[ \t]+', ' ', text)
    return _MEHRFACH_LEERZEILE.sub('\n\n', text).strip()


def _lies_body(msg) -> str:
    """Liest den Mailtext, ``text/plain`` bevorzugt."""
    try:
        teil = msg.get_body(preferencelist=('plain', 'html'))
    except Exception:
        teil = None

    if teil is None:
        # Mail ohne erkennbaren Body-Teil (reine Anhangs-Mail o.ä.)
        return ''

    try:
        inhalt = teil.get_content()
    except Exception:
        # Defektes/unbekanntes Charset — Bytes roh mit Ersatzzeichen lesen.
        # Lieber ein paar kaputte Umlaute als eine nicht verarbeitbare Mail.
        nutzlast = teil.get_payload(decode=True) or b''
        inhalt = nutzlast.decode('utf-8', errors='replace')

    if teil.get_content_type() == 'text/html':
        return _html_zu_text(inhalt or '')
    return _MEHRFACH_LEERZEILE.sub('\n\n', (inhalt or '').strip())


def _ohne_nul(text: str) -> str:
    """Entfernt NUL-Bytes aus Text.

    PostgreSQL lehnt ``\x00`` in Textspalten ab ("A string literal cannot
    contain NUL characters"). Mails mit defektem Encoding enthalten sie
    gelegentlich — ohne diese Bereinigung scheitert das Speichern der
    Protokollzeile, und genau die Mail, die man sich ansehen müsste, wäre nur
    noch als Fehlermeldung sichtbar.
    """
    return (text or '').replace('\x00', '')


def dekodiere_header(wert: str) -> str:
    """Loest RFC-2047-Kodierung in einem Header-Wert auf.

    Bei ``.eml`` erledigt das ``email.policy.default`` von selbst. Die Header
    aus einer ``.msg`` liefert ``extract-msg`` dagegen mit der alten
    compat32-Policy, also unveraendert: ein Empfaenger stuende sonst als
    ``=?UTF-8?Q?Stra=C3=9Fe?=`` in der Vorschau statt als ``Straße``.

    Faellt die Dekodierung aus (defekter Header), bleibt der Rohwert stehen —
    lesbar genug, um den Fall zu erkennen, und nie ein Grund zu scheitern.
    """
    if not wert or '=?' not in wert:
        return wert or ''
    try:
        return str(email.header.make_header(email.header.decode_header(wert)))
    except Exception:
        return wert


def bereinige_betreff(betreff: str) -> str:
    """Entfernt Antwort-/Weiterleitungspräfixe ("AW:", "Re:", ...)."""
    return _REPLY_PRAEFIX.sub('', betreff or '').strip()


def parse_eml(pfad) -> ParsedMail:
    """Liest eine ``.eml``-Datei in ein ``ParsedMail``.

    ``email.policy.default`` liefert bereits dekodierte Header (RFC 2047), so
    dass Umlaute in Betreff und Absendername ohne Zusatzarbeit korrekt
    ankommen.
    """
    pfad = pathlib.Path(pfad)
    rohdaten = pfad.read_bytes()
    with pfad.open('rb') as fh:
        msg = email.message_from_binary_file(fh, policy=email.policy.default)

    absender_name, absender_email = email.utils.parseaddr(str(msg.get('From', '') or ''))

    gesendet_am = None
    roh_datum = msg.get('Date')
    if roh_datum:
        try:
            gesendet_am = email.utils.parsedate_to_datetime(str(roh_datum))
            if gesendet_am is not None and timezone.is_naive(gesendet_am):
                gesendet_am = timezone.make_aware(
                    gesendet_am, timezone.get_current_timezone())
        except (TypeError, ValueError):
            gesendet_am = None

    referenzen = [ref for ref in str(msg.get('References', '') or '').split() if ref.strip()]

    anhaenge = []
    anhaenge_gesamt = 0
    for teil in msg.iter_attachments():
        anhaenge_gesamt += 1
        name = teil.get_filename() or 'anhang'
        endung = pathlib.Path(name).suffix.lower()
        if endung not in ANHANG_ENDUNGEN:
            continue
        inhalt = teil.get_payload(decode=True) or b''
        # Signaturgrafiken sind fast immer klein, echte Belege fast nie.
        if endung in {'.jpg', '.jpeg', '.png', '.tif', '.tiff'} and len(inhalt) < ANHANG_MIN_BYTES:
            continue
        if inhalt:
            anhaenge.append((name, inhalt))

    betreff = str(msg.get('Subject', '') or '').strip()

    return ParsedMail(
        dateiname=pfad.name,
        absender_email=(absender_email or '').strip().lower(),
        absender_name=_ohne_nul(absender_name).strip(),
        empfaenger=str(msg.get('To', '') or '').strip(),
        betreff=_ohne_nul(betreff)[:500],
        betreff_bereinigt=_ohne_nul(bereinige_betreff(betreff)),
        body=_ohne_nul(_lies_body(msg)),
        message_id=str(msg.get('Message-ID', '') or '').strip()[:255],
        in_reply_to=str(msg.get('In-Reply-To', '') or '').strip(),
        references=referenzen,
        gesendet_am=gesendet_am,
        anhaenge=anhaenge,
        anhaenge_gesamt=anhaenge_gesamt,
        rohdaten=rohdaten,
    )


def parse_msg(pfad) -> ParsedMail:
    """Liest eine Outlook-``.msg``-Datei in ein ``ParsedMail``.

    Braucht das Paket ``extract-msg`` (in ``requirements.txt``). Fehlt es,
    gibt es eine klare Meldung statt eines ImportError irgendwo tief im
    Scan — die Datei landet dann im Fehlerordner und kann nach der
    Installation erneut abgelegt werden.

    Besonderheit gegenüber ``.eml``: Outlook speichert die Internet-Header nur
    bei EMPFANGENEN Mails mit. Message-ID, In-Reply-To und References werden
    deshalb bevorzugt aus diesen Headern gelesen und fallen sonst auf die
    MAPI-Eigenschaften zurück; fehlt beides, springt ``parse_mail`` mit einer
    Ersatzkennung ein.
    """
    try:
        import extract_msg
    except ImportError as exc:
        raise RuntimeError(
            'Fuer .msg-Dateien wird das Paket "extract-msg" benoetigt '
            '(pip install extract-msg bzw. Container neu bauen).'
        ) from exc

    pfad = pathlib.Path(pfad)
    rohdaten = pfad.read_bytes()
    with extract_msg.Message(str(pfad)) as msg:
        # Die Transport-Header sind die verlaesslichste Quelle; die
        # MAPI-Felder darunter sind Outlooks eigene Aufbereitung.
        header = None
        try:
            header = msg.header
        except Exception:
            header = None

        def kopf(name: str) -> str:
            if header is None:
                return ''
            return dekodiere_header(str(header.get(name, '') or '')).strip()

        roh_von = kopf('From') or str(msg.sender or '')
        absender_name, absender_email = email.utils.parseaddr(roh_von)
        if not absender_email and '@' in roh_von:
            # Outlook liefert bei internen Mails gelegentlich nur den
            # Klarnamen oder eine X.500-Adresse — dann bleibt die Adresse
            # bewusst leer, statt etwas zu erfinden.
            absender_email = roh_von.strip()

        # ``msg.date`` ist je nach extract-msg-Version ein datetime oder ein
        # Header-String; beide Wege sind abgedeckt.
        gesendet_am = None
        try:
            roh_datum = msg.date
        except Exception:
            roh_datum = None
        if isinstance(roh_datum, datetime):
            gesendet_am = roh_datum
        elif roh_datum:
            try:
                gesendet_am = email.utils.parsedate_to_datetime(str(roh_datum))
            except (TypeError, ValueError):
                gesendet_am = None
        if gesendet_am is not None and timezone.is_naive(gesendet_am):
            gesendet_am = timezone.make_aware(
                gesendet_am, timezone.get_current_timezone())

        body = msg.body or ''
        if not body.strip():
            html = msg.htmlBody or b''
            if isinstance(html, bytes):
                html = html.decode('utf-8', errors='replace')
            body = _html_zu_text(html)

        anhaenge = []
        anhaenge_gesamt = 0
        for anhang in (msg.attachments or []):
            anhaenge_gesamt += 1
            name = (getattr(anhang, 'longFilename', None)
                    or getattr(anhang, 'shortFilename', None) or 'anhang')
            endung = pathlib.Path(name).suffix.lower()
            if endung not in ANHANG_ENDUNGEN:
                continue
            inhalt = getattr(anhang, 'data', None)
            if not isinstance(inhalt, bytes) or not inhalt:
                continue
            if endung in {'.jpg', '.jpeg', '.png', '.tif', '.tiff'} and len(inhalt) < ANHANG_MIN_BYTES:
                continue
            anhaenge.append((name, inhalt))

        betreff = _ohne_nul(dekodiere_header(str(msg.subject or ''))).strip()
        message_id = kopf('Message-ID') or str(getattr(msg, 'messageId', '') or '').strip()
        in_reply_to = kopf('In-Reply-To') or str(getattr(msg, 'inReplyTo', '') or '').strip()

        return ParsedMail(
            dateiname=pfad.name,
            absender_email=_ohne_nul(absender_email).strip().lower(),
            absender_name=_ohne_nul(absender_name).strip(),
            empfaenger=kopf('To') or dekodiere_header(str(getattr(msg, 'to', '') or '')),
            betreff=betreff[:500],
            betreff_bereinigt=_ohne_nul(bereinige_betreff(betreff)),
            body=_ohne_nul(body),
            message_id=message_id[:255],
            in_reply_to=in_reply_to,
            references=[r for r in kopf('References').split() if r.strip()],
            gesendet_am=gesendet_am,
            anhaenge=anhaenge,
            anhaenge_gesamt=anhaenge_gesamt,
            rohdaten=rohdaten,
        )


def _ersatz_message_id(parsed: ParsedMail) -> str:
    """Stabile Ersatzkennung für Mails ohne Message-ID.

    Ohne Kennung greift die Duplikatprüfung nicht, und dieselbe Datei zweimal
    abgelegt erzeugt zwei Vorgänge. Der Hash über Absender, Betreff,
    Sendezeitpunkt und Textanfang ist für dieselbe Mail immer gleich und für
    verschiedene Mails praktisch nie — der Dateiname geht bewusst NICHT ein,
    denn eine umbenannte Kopie ist trotzdem dieselbe Mail.
    """
    rohdaten = '|'.join([
        parsed.absender_email,
        parsed.betreff_bereinigt,
        parsed.gesendet_am.isoformat() if parsed.gesendet_am else '',
        (parsed.body or '')[:500],
    ])
    kennung = hashlib.sha256(rohdaten.encode('utf-8')).hexdigest()[:32]
    return f'<ersatz-{kennung}@immocore.local>'


def parse_mail(pfad) -> ParsedMail:
    """Liest eine Mail-Datei, unabhängig vom Format (``.eml`` oder ``.msg``).

    Einziger Einstiegspunkt für die Verarbeitung: alles darunter arbeitet nur
    noch mit ``ParsedMail`` und kennt das Quellformat nicht mehr.
    """
    pfad = pathlib.Path(pfad)
    endung = pfad.suffix.lower()

    if endung == ENDUNG_MSG:
        parsed = parse_msg(pfad)
    elif endung == ENDUNG_EML:
        parsed = parse_eml(pfad)
    else:
        raise ValueError(f'Nicht unterstuetztes Mailformat: {pfad.name}')

    if not parsed.message_id:
        parsed.message_id = _ersatz_message_id(parsed)
    return parsed


# ---------------------------------------------------------------------------
# Stufe 1 — regelbasierte Zuordnung
# ---------------------------------------------------------------------------

def alle_adressen(person: Person) -> set[str]:
    """Alle E-Mail-Adressen einer Person, kleingeschrieben.

    Liest ``emails`` (JSON-Liste, Einträge als String ODER Dict — historisch
    gewachsen, siehe ``personen.models.erster_listenwert``) und zusätzlich
    das gespiegelte Legacy-Feld ``email``.
    """
    adressen: set[str] = set()
    for eintrag in (person.emails or []):
        if isinstance(eintrag, str):
            if eintrag.strip():
                adressen.add(eintrag.strip().lower())
        elif isinstance(eintrag, dict):
            for schluessel in ('adresse', 'email', 'wert'):
                wert = (eintrag.get(schluessel) or '').strip()
                if wert:
                    adressen.add(wert.lower())
                    break
    if person.email:
        adressen.add(person.email.strip().lower())
    return adressen


def finde_personen(absender_email: str) -> list[Person]:
    """Alle Personen, die diese Absenderadresse führen.

    Mehr als ein Treffer ist ein realer Fall (Ehepaare mit gemeinsamer
    Adresse, Hausmeister für mehrere Objekte) und wird deshalb NICHT
    aufgelöst, sondern nach oben gereicht — der Aufrufer markiert
    ``mehrdeutig``.

    Zwei Schritte, weil ``email`` ein indiziertes Feld ist, ``emails`` als
    JSONField aber nicht zuverlässig durchsuchbar (variable Schlüssel,
    Strings neben Dicts): erst der günstige Index-Treffer, nur bei Fehlschlag
    der Scan über die JSON-Spalte.
    """
    if not absender_email:
        return []
    absender_email = absender_email.strip().lower()

    treffer = list(Person.objects.filter(email__iexact=absender_email))
    if treffer:
        return treffer

    kandidaten = Person.objects.exclude(emails=[]).exclude(emails__isnull=True)
    return [p for p in kandidaten if absender_email in alle_adressen(p)]


def finde_kontext(person: Person) -> dict:
    """Ermittelt Einheit und Objekt zu einer Person über ihre
    Eigentumsverhältnisse.

    Regeln — bewusst konservativ:
    - genau ein aktives EV  -> Einheit + Objekt stehen fest
    - mehrere aktive EVs    -> Einheit bleibt leer (nicht raten). Liegen alle
      im selben Objekt, wird wenigstens das Objekt gesetzt; der Vorgang ist
      damit auswertbar, ohne eine falsche Wohnung zu behaupten.
    - kein aktives EV       -> letztes beendetes EV als Kontext, markiert als
      mehrdeutig (ehemaliger Eigentümer meldet sich z.B. zur
      Schlussabrechnung — das ist ein echter Fall, aber kein sicherer)
    """
    ergebnis = {'einheit': None, 'objekt': None, 'mehrdeutig': False}

    aktive = list(
        EigentumsVerhaeltnis.objects
        .filter(person=person, ende__isnull=True)
        .select_related('einheit', 'einheit__objekt')
    )

    if len(aktive) == 1:
        ergebnis['einheit'] = aktive[0].einheit
        ergebnis['objekt'] = aktive[0].einheit.objekt
        return ergebnis

    if len(aktive) > 1:
        ergebnis['mehrdeutig'] = True
        objekte = {ev.einheit.objekt_id: ev.einheit.objekt for ev in aktive}
        if len(objekte) == 1:
            ergebnis['objekt'] = next(iter(objekte.values()))
        return ergebnis

    letztes = (
        EigentumsVerhaeltnis.objects
        .filter(person=person)
        .select_related('einheit', 'einheit__objekt')
        .order_by('-ende', '-beginn')
        .first()
    )
    if letztes:
        ergebnis['einheit'] = letztes.einheit
        ergebnis['objekt'] = letztes.einheit.objekt
        ergebnis['mehrdeutig'] = True
    return ergebnis


def finde_kontext_geteilt(personen: list) -> dict:
    """Kontext für eine Adresse, die MEHRERE Personen führen.

    In den Stammdaten kommt das aus zwei Gründen vor, die man an den Daten
    nicht sauber unterscheiden kann und deshalb auch nicht unterscheiden
    muss:
      - Ehepaare mit getrennten Personensätzen und einer gemeinsamen Adresse
      - echte Dubletten desselben Eigentümers (gleicher Name zweimal, oder
        einmal "Hermann" und einmal "Herrmann")

    In beiden Fällen hat typischerweise nur EIN Satz ein aktives
    Eigentumsverhältnis — der andere ist leer. Genau daran hängt die
    Auflösung:

    - genau eine der Personen hat ein aktives EV -> diese Person ist die
      Vertragspartnerin, die Zuordnung ist vollständig
    - alle aktiven EVs zeigen auf dieselbe Einheit -> Einheit steht fest,
      auch wenn die Person offen bleibt
    - alle im selben Objekt -> wenigstens das Objekt
    - über mehrere Objekte verstreut -> keine Zuordnung

    Vorher wurde in all diesen Fällen gar nichts zugeordnet und der Vorgang
    entstand nicht. Geraten wird weiterhin nichts: offen Gebliebenes bleibt
    leer und ``mehrdeutig`` sagt, dass jemand nachsehen muss.
    """
    ergebnis = {'person': None, 'einheit': None, 'objekt': None,
                'mehrdeutig': True}

    evs = list(
        EigentumsVerhaeltnis.objects
        .filter(person__in=personen, ende__isnull=True)
        .select_related('person', 'einheit', 'einheit__objekt')
    )
    if not evs:
        return ergebnis

    personen_mit_ev = {ev.person_id: ev.person for ev in evs}
    einheiten = {ev.einheit_id: ev.einheit for ev in evs}
    objekte = {ev.einheit.objekt_id: ev.einheit.objekt for ev in evs}

    if len(personen_mit_ev) == 1:
        ergebnis['person'] = next(iter(personen_mit_ev.values()))

    if len(einheiten) == 1:
        einheit = next(iter(einheiten.values()))
        ergebnis['einheit'] = einheit
        ergebnis['objekt'] = einheit.objekt
    elif len(objekte) == 1:
        ergebnis['objekt'] = next(iter(objekte.values()))

    # Nur wenn Person UND Einheit feststehen, ist nichts mehr offen.
    ergebnis['mehrdeutig'] = not (ergebnis['person'] and ergebnis['einheit'])
    return ergebnis


def finde_thread_vorgang(parsed: ParsedMail) -> Vorgang | None:
    """Sucht den Vorgang, zu dem diese Mail gehört (Antwort auf einen
    laufenden Vorgang statt neuer Fall).

    Zwei Wege, in dieser Reihenfolge:

    1. ``In-Reply-To`` / ``References`` gegen ``Vorgang.mail_referenz``.
       Greift, sobald in einem Thread schon einmal eine Mail importiert wurde.
    2. Vorgangsnummer im Betreff (``V-26-00042``). Das ist der robustere Weg,
       sobald die Verwaltung die Nummer in ausgehende Betreffzeilen schreibt —
       Outlook und Co. erhalten Header beim Antworten nicht immer zuverlässig,
       die Betreffzeile dagegen schon.

    Geschlossene Vorgänge (``erledigt``/``storniert``) werden bewusst NICHT
    ausgeschlossen: eine Nachfrage zu einem abgeschlossenen Fall gehört an
    denselben Vorgang, nicht in einen neuen.
    """
    referenzen = [r for r in ([parsed.in_reply_to] + list(parsed.references)) if r]
    if referenzen:
        treffer = Vorgang.objects.filter(mail_referenz__in=referenzen).first()
        if treffer:
            return treffer

    nummer = _VORGANGSNUMMER.search(parsed.betreff or '')
    if nummer:
        return Vorgang.objects.filter(nummer__iexact=nummer.group(0)).first()

    return None


# ---------------------------------------------------------------------------
# Stufe 2 — KI-Klassifikation
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """Du klassifizierst eingehende E-Mails einer \
WEG-Hausverwaltung (Demme GmbH) für die Anlage eines Vorgangs.

Du bekommst Betreff und Text einer Mail sowie die Liste der zulässigen \
Vorgangstypen. Deine Aufgabe ist AUSSCHLIESSLICH die Einordnung:

- typ_code: exakt einer der vorgegebenen Codes. Rate nicht — passt nichts \
eindeutig, nimm "sonstiges".
- prioritaet: "niedrig", "normal" oder "hoch". "hoch" nur bei akuter Gefahr \
oder drohendem Schaden (Wasseraustritt, Heizungsausfall im Winter, \
Stromausfall, Einbruch, verschlossener Fluchtweg).
- betreff: eine sachliche Kurzfassung des Anliegens, höchstens 120 Zeichen, \
ohne "AW:"/"Re:"-Präfixe und ohne Grußfloskeln.
- zusammenfassung: 1-3 Sätze, was der Absender will. Keine Bewertung, keine \
Handlungsempfehlung.
- konfidenz: 0.0 bis 1.0, wie sicher du bei typ_code bist.
- begruendung: ein knapper Satz, woran du den Typ festmachst.

Du ordnest KEINE Personen, Wohnungen oder Objekte zu — das macht das System \
anhand seiner Stammdaten. Erfinde keine Namen, Adressen, Beträge oder Fristen.

Antworte AUSSCHLIESSLICH mit einem JSON-Objekt mit exakt diesen Schlüsseln: \
typ_code, prioritaet, betreff, zusammenfassung, konfidenz, begruendung. \
Kein Markdown, keine Code-Fences, kein weiterer Text."""


def _baue_ki_prompt(parsed: ParsedMail, typen) -> str:
    typ_zeilen = '\n'.join(f"- {t.code}: {t.bezeichnung}" for t in typen)
    body = (parsed.body or '')[:KI_BODY_LAENGE]
    return (
        f"Zulässige Vorgangstypen:\n{typ_zeilen}\n\n"
        f"Betreff: {parsed.betreff_bereinigt or '(kein Betreff)'}\n\n"
        f"Mailtext:\n{body or '(kein Text)'}"
    )


def _entpacke_json(text: str) -> dict:
    """Liest das JSON-Objekt aus der KI-Antwort.

    Trotz klarer Prompt-Anweisung kommen gelegentlich Code-Fences zurück —
    deshalb zusätzlich der Ausschnitt von der ersten ``{`` bis zur letzten
    ``}``, statt am Formatfehler zu scheitern.
    """
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


def klassifiziere(parsed: ParsedMail) -> dict:
    """Stufe 2: Vorgangstyp, Priorität und Kurzbetreff per Claude API.

    Wirft NIE — ein Fehler landet als Text in ``fehler`` und die Verarbeitung
    läuft mit dem Fallback-Typ weiter. Rückgabe ist immer vollständig
    befüllt.
    """
    ergebnis = {
        'typ_code': '', 'prioritaet': '', 'betreff': '', 'zusammenfassung': '',
        'konfidenz': None, 'begruendung': '', 'modell': '', 'fehler': '',
    }

    typen = list(VorgangTyp.objects.filter(aktiv=True).order_by('sortierung'))
    if not typen:
        ergebnis['fehler'] = 'Keine aktiven Vorgangstypen vorhanden.'
        return ergebnis

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
            max_tokens=2000,
            system=_SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': _baue_ki_prompt(parsed, typen)}],
        )
        roh = next(
            (b.text for b in antwort.content if getattr(b, 'type', None) == 'text'), '')
        daten = _entpacke_json(roh)

        gueltige_codes = {t.code for t in typen}
        typ_code = str(daten.get('typ_code') or '').strip()
        if typ_code not in gueltige_codes:
            # Halluzinierter Code: nicht übernehmen, aber im Protokoll
            # sichtbar lassen — genau solche Fälle will der Testlauf zeigen.
            ergebnis['fehler'] = f"Unbekannter typ_code von der KI: {typ_code!r}"
            typ_code = ''

        prioritaet = str(daten.get('prioritaet') or '').strip().lower()
        if prioritaet not in {'niedrig', 'normal', 'hoch'}:
            prioritaet = ''

        konfidenz = daten.get('konfidenz')
        try:
            konfidenz = round(float(konfidenz), 3) if konfidenz is not None else None
            if konfidenz is not None:
                konfidenz = min(max(konfidenz, 0.0), 1.0)
        except (TypeError, ValueError):
            konfidenz = None

        ergebnis.update({
            'typ_code': typ_code,
            'prioritaet': prioritaet,
            'betreff': str(daten.get('betreff') or '').strip()[:200],
            'zusammenfassung': str(daten.get('zusammenfassung') or '').strip(),
            'konfidenz': konfidenz,
            'begruendung': str(daten.get('begruendung') or '').strip(),
            'modell': modell,
        })
    except Exception as exc:
        logger.warning("Mail-Klassifikation fehlgeschlagen (%s): %s",
                       parsed.dateiname, exc)
        ergebnis['fehler'] = f"{type(exc).__name__}: {exc}"

    return ergebnis


# ---------------------------------------------------------------------------
# Verarbeitung
# ---------------------------------------------------------------------------

def mail_system_user():
    """Technischer System-User für ``Vorgang.erstellt_von`` bei Mail-Import.

    Gleiches Muster wie ``vorgang_service.portal_system_user``: eine
    eingehende Mail hat keinen angemeldeten Benutzer, ``erstellt_von`` ist
    aber ein Pflicht-FK. Der Absender bleibt über ``Vorgang.person`` und
    ``quelle='mail'`` nachvollziehbar.
    """
    User = get_user_model()
    user, _ = User.objects.get_or_create(
        username=MAIL_SYSTEM_USERNAME,
        defaults={
            'first_name': 'IMMOCORE',
            'last_name': 'Mail-Import',
            'email': 'mail-import@noreply.immocore.local',
            'is_active': False,
            'is_staff': False,
            'is_superuser': False,
        },
    )
    if user.has_usable_password():
        user.set_unusable_password()
        user.save(update_fields=['password'])
    return user


def _baue_beschreibung(parsed: ParsedMail, ki: dict) -> str:
    """Vorgangsbeschreibung = Herkunftskopf + vollständiger Mailtext.

    Der Originaltext bleibt ungekürzt erhalten — die KI-Zusammenfassung steht
    darüber, ersetzt ihn aber nicht. Wer den Vorgang bearbeitet, muss lesen
    können, was tatsächlich geschrieben wurde.
    """
    kopf = [
        f"Von: {parsed.absender_name} <{parsed.absender_email}>".strip(),
        f"Gesendet: {parsed.gesendet_am:%d.%m.%Y %H:%M}" if parsed.gesendet_am else None,
        f"Betreff: {parsed.betreff}",
    ]
    if parsed.anhaenge_gesamt:
        kopf.append(f"Anhänge: {parsed.anhaenge_gesamt}")

    teile = ['\n'.join(z for z in kopf if z)]
    if ki.get('zusammenfassung'):
        teile.append(f"Zusammenfassung (KI):\n{ki['zusammenfassung']}")
    teile.append(f"Nachricht:\n{parsed.body or '(kein Text)'}")
    return '\n\n---\n\n'.join(teile)


KATEGORIE_MAIL = 'E-Mail Posteingang'
KATEGORIE_ANHANG = 'E-Mail Anhang'


def _lege_im_dms_ab(protokoll: MailImportProtokoll, parsed: ParsedMail,
                    benutzer, vorgang: Vorgang | None = None) -> int:
    """Legt die Mail selbst UND ihre Anhänge als Dokumente ab.

    Aufbewahrung und Zuordnung sind bewusst getrennt:

    - Abgelegt wird IMMER und sofort, auch wenn niemand weiss, wohin die Mail
      gehört. Sonst hinge die Aufbewahrung daran, dass jemand eine Maske
      anklickt — und eine übersehene Mail wäre nach Jahren unauffindbar.
    - Der KONTEXT (``vorgang``) wird nur gesetzt, wenn er feststeht. Sonst
      bleibt das Dokument zunächst kontextlos und hängt über
      ``Dokument.mail_import`` am Protokoll; die Zuordnung trägt später ein
      Mensch im Posteingang nach.

    Die Mail geht als Originaldatei ins DMS (``.eml``/``.msg`` mit allen
    Headern) — nicht als extrahierter Text. Anhänge kommen ZUSÄTZLICH einzeln
    hinein, obwohl sie in der Mail schon enthalten sind: eine Rechnung, die
    nur eingebettet vorliegt, ist über die Dokumentensuche nicht auffindbar
    und nicht an eine ``Rechnung`` koppelbar.

    Ein Fehler beim Ablegen darf den Vorgang nie kippen — die Datei liegt in
    jedem Fall noch im Archivordner und kann nachgezogen werden.
    """
    from apps.vorgaenge.services import dokument_service

    anzahl = 0

    if parsed.rohdaten:
        # Dateiname aus dem Betreff wäre lesbarer, aber der Originalname ist
        # das, wonach im Archivordner gesucht wird.
        try:
            dokument_service.lade_dokument_hoch(
                parsed.rohdaten, parsed.dateiname, benutzer,
                vorgang=vorgang, mail_import=protokoll,
                # Der KI-Kurzbetreff liegt ohnehin im Protokoll — als Titel
                # macht er die Mail in der Akte lesbar, ohne dass der
                # Dateiname angetastet wird. Fehlt er, greift der bereinigte
                # Originalbetreff.
                titel=(protokoll.ki_betreff or parsed.betreff_bereinigt)[:200],
                # Sendedatum als fachliches Datum: es entscheidet in der
                # Eigentuemerakte darueber, in wessen Besitzzeit die Mail
                # faellt — das Ablagedatum waere dafuer untauglich, sobald
                # jemand Altbestaende nachreicht.
                dokument_datum=parsed.gesendet_am.date() if parsed.gesendet_am else None,
                kategorie=KATEGORIE_MAIL, dokument_typ='korrespondenz',
                beschreibung=(f"E-Mail von {parsed.absender_email} "
                              f"vom {parsed.gesendet_am:%d.%m.%Y %H:%M}"
                              if parsed.gesendet_am else
                              f"E-Mail von {parsed.absender_email}"),
            )
            anzahl += 1
        except Exception:
            logger.exception("Mail %s konnte nicht im DMS abgelegt werden.",
                             parsed.dateiname)

    for name, inhalt in parsed.anhaenge:
        try:
            dokument_service.lade_dokument_hoch(
                inhalt, name, benutzer,
                vorgang=vorgang, mail_import=protokoll,
                dokument_datum=parsed.gesendet_am.date() if parsed.gesendet_am else None,
                kategorie=KATEGORIE_ANHANG, dokument_typ='sonstiges',
                beschreibung=f"Anhang aus Mail-Import ({parsed.dateiname})",
            )
            anzahl += 1
        except Exception:
            logger.exception("Anhang %s aus %s konnte nicht abgelegt werden.",
                             name, parsed.dateiname)
    return anzahl


@transaction.atomic
def verarbeite_mail(parsed: ParsedMail, *, anlegen: bool = True) -> MailImportProtokoll:
    """Verarbeitet eine geparste Mail und schreibt genau eine Protokollzeile.

    Ablauf:
      1. Duplikatprüfung über die Message-ID
      2. Thread-Zuordnung -> Ereignis am bestehenden Vorgang
      3. Stufe 1 (Person/Einheit/Objekt) — ohne Treffer kein Vorgang
      4. Stufe 2 (KI-Klassifikation)
      5. Anlage des Vorgangs + Anhänge

    ``anlegen=False`` führt die komplette Erkennung aus, schreibt aber nur
    das Protokoll — für einen Trockenlauf über bereits archivierte Mails,
    ohne den Datenbestand erneut zu füllen.
    """
    protokoll = MailImportProtokoll(
        dateiname=parsed.dateiname,
        message_id=parsed.message_id,
        bezug_message_id=(parsed.in_reply_to or
                          (parsed.references[-1] if parsed.references else ''))[:255],
        absender=parsed.absender_email[:320],
        absender_name=parsed.absender_name[:200],
        betreff=parsed.betreff,
        gesendet_am=parsed.gesendet_am,
        body_auszug=(parsed.body or '')[:BODY_AUSZUG_LAENGE],
        anhaenge_anzahl=parsed.anhaenge_gesamt,
        status='nicht_zugeordnet',
    )

    # --- 1. Duplikat ----------------------------------------------------
    if parsed.message_id and MailImportProtokoll.objects.filter(
            message_id=parsed.message_id).exists():
        protokoll.status = 'duplikat'
        protokoll.posteingang_status = 'automatisch'
        protokoll.save()
        return protokoll

    benutzer = mail_system_user()

    # --- 2. Thread ------------------------------------------------------
    bestehender = finde_thread_vorgang(parsed)
    if bestehender is not None:
        protokoll.status = 'thread_zuordnung'
        protokoll.vorgang = bestehender
        protokoll.person = bestehender.person
        protokoll.objekt = bestehender.objekt
        protokoll.einheit = bestehender.einheit
        protokoll.zuordnung_quelle = 'email_exakt'
        protokoll.posteingang_status = 'automatisch'
        if anlegen:
            # intern=True: der Text stammt von aussen und kann Angaben zu
            # Dritten enthalten — im Portal sichtbar wird er nur, wenn ein
            # Mitarbeiter ihn bewusst dorthin stellt.
            VorgangEreignis.objects.create(
                vorgang=bestehender, typ='mail_eingegangen',
                text=f"E-Mail von {parsed.absender_email}: "
                     f"{parsed.betreff_bereinigt}\n\n{parsed.body}"[:5000],
                erstellt_von=benutzer, intern=True,
            )
        protokoll.save()
        if anlegen:
            _lege_im_dms_ab(protokoll, parsed, benutzer, vorgang=bestehender)
        return protokoll

    # --- 3. Stufe 1 -----------------------------------------------------
    personen = finde_personen(parsed.absender_email)
    protokoll.personen_treffer = len(personen)

    if len(personen) == 1:
        kontext = finde_kontext(personen[0])
        protokoll.person = personen[0]
        protokoll.objekt = kontext['objekt']
        protokoll.einheit = kontext['einheit']
        protokoll.mehrdeutig = kontext['mehrdeutig']
        protokoll.zuordnung_quelle = 'email_exakt'
    elif personen:
        # Geteilte Adresse (Ehepaar mit zwei Sätzen oder Dublette): so weit
        # auflösen, wie es die Eigentumsverhältnisse hergeben.
        kontext = finde_kontext_geteilt(personen)
        protokoll.person = kontext['person']
        protokoll.objekt = kontext['objekt']
        protokoll.einheit = kontext['einheit']
        protokoll.mehrdeutig = kontext['mehrdeutig']
        protokoll.zuordnung_quelle = 'email_geteilt'
    else:
        protokoll.zuordnung_quelle = 'keine'

    # --- 4. Stufe 2 -----------------------------------------------------
    ki = klassifiziere(parsed)
    protokoll.ki_typ_code = ki['typ_code']
    protokoll.ki_prioritaet = ki['prioritaet']
    protokoll.ki_betreff = ki['betreff']
    protokoll.ki_konfidenz = ki['konfidenz']
    protokoll.ki_begruendung = ki['begruendung']
    protokoll.ki_modell = ki['modell']
    protokoll.ki_fehler = ki['fehler']

    # Ohne Person/Objekt/Einheit verbietet ``Vorgang.clean()`` die Anlage —
    # und das zu Recht: ein Vorgang ohne Kontext ist nicht auswertbar.
    if protokoll.person is None and protokoll.objekt is None and protokoll.einheit is None:
        protokoll.status = 'nicht_zugeordnet'
        protokoll.posteingang_status = 'offen'
        protokoll.save()
        # Aufbewahrung haengt NICHT an der Zuordnung: die Mail wird abgelegt,
        # der Kontext bleibt offen bis jemand sie im Posteingang zuordnet.
        if anlegen:
            _lege_im_dms_ab(protokoll, parsed, benutzer, vorgang=None)
        return protokoll

    if not anlegen:
        protokoll.status = 'vorgang_neu'
        protokoll.save()
        return protokoll

    # --- 5. Anlage ------------------------------------------------------
    from apps.vorgaenge.services import vorgang_service

    typ = None
    if ki['typ_code']:
        typ = VorgangTyp.objects.filter(code=ki['typ_code'], aktiv=True).first()
    if typ is None:
        typ = (VorgangTyp.objects.filter(code='sonstiges', aktiv=True).first()
               or VorgangTyp.objects.filter(aktiv=True).order_by('sortierung').first())
    if typ is None:
        protokoll.status = 'fehler'
        protokoll.fehler = 'Kein aktiver Vorgangstyp vorhanden.'
        protokoll.save()
        return protokoll

    betreff = (ki['betreff'] or parsed.betreff_bereinigt or '(ohne Betreff)')[:200]

    vorgang = vorgang_service.erstelle_vorgang(
        typ=typ,
        betreff=betreff,
        erstellt_von=benutzer,
        quelle='mail',
        objekt=protokoll.objekt,
        einheit=protokoll.einheit,
        person=protokoll.person,
        beschreibung=_baue_beschreibung(parsed, ki),
        prioritaet=ki['prioritaet'] or None,
        mail_referenz=parsed.message_id or None,
    )
    protokoll.vorgang = vorgang
    protokoll.status = 'vorgang_neu'
    protokoll.posteingang_status = 'automatisch'
    protokoll.save()
    _lege_im_dms_ab(protokoll, parsed, benutzer, vorgang=vorgang)
    return protokoll


def _zielpfad(ordner: pathlib.Path, dateiname: str) -> pathlib.Path:
    """Kollisionsfreier Zielpfad im Archiv-/Fehlerordner."""
    ziel = ordner / dateiname
    if not ziel.exists():
        return ziel
    stamm = pathlib.Path(dateiname).stem
    endung = pathlib.Path(dateiname).suffix
    marke = timezone.now().strftime('%Y%m%d%H%M%S')
    return ordner / f"{stamm}_{marke}{endung}"


def verarbeite_datei(pfad, archiv: pathlib.Path, fehler_dir: pathlib.Path | None = None,
                     *, anlegen: bool = True, parsed: ParsedMail | None = None) -> MailImportProtokoll:
    """Verarbeitet eine ``.eml``-Datei und verschiebt sie anschliessend.

    Zielordner: ``archiv`` bei erfolgreicher Verarbeitung, ``fehler_dir`` bei
    ``nicht_zugeordnet`` und ``fehler`` — so liegen genau die Fälle, die
    jemand ansehen muss, getrennt von den erledigten. Ohne ``fehler_dir``
    wandert alles ins Archiv (die Datei muss den Eingang in jedem Fall
    verlassen, sonst verarbeitet der nächste Scan sie erneut).

    ``parsed`` kann übergeben werden, wenn die Datei bereits gelesen wurde
    (``scan_ordner`` tut das, um nach Sendezeitpunkt sortieren zu können) —
    dann wird sie nicht ein zweites Mal geparst.
    """
    pfad = pathlib.Path(pfad)
    try:
        if parsed is None:
            parsed = parse_mail(pfad)
        protokoll = verarbeite_mail(parsed, anlegen=anlegen)
    except Exception as exc:
        logger.exception("Mail-Import: %s konnte nicht verarbeitet werden.", pfad.name)
        protokoll = MailImportProtokoll.objects.create(
            dateiname=pfad.name, status='fehler',
            fehler=f"{type(exc).__name__}: {exc}",
        )

    ziel_ordner = archiv
    if protokoll.status in ('nicht_zugeordnet', 'fehler') and fehler_dir is not None:
        ziel_ordner = fehler_dir

    try:
        ziel_ordner.mkdir(parents=True, exist_ok=True)
        pfad.rename(_zielpfad(ziel_ordner, pfad.name))
    except Exception:
        logger.exception("Mail-Import: %s konnte nicht verschoben werden.", pfad.name)

    return protokoll


def scan_ordner(import_ordner, archiv_ordner=None, fehler_ordner=None,
                *, anlegen: bool = True) -> dict:
    """Verarbeitet alle ``.eml``-Dateien eines Ordners, älteste zuerst.

    SCHUTZ GEGEN PARALLELE LÄUFE: Jede Datei wird VOR der Verarbeitung in den
    Unterordner ``.arbeit`` verschoben. ``rename`` ist innerhalb desselben
    Dateisystems atomar — genau ein Prozess gewinnt, alle anderen laufen in
    ``FileNotFoundError`` und überspringen die Datei. Ohne diesen Schritt
    verarbeiten der Celery-Beat-Task und ein gleichzeitiger manueller Lauf
    dieselbe Mail doppelt und legen zwei Vorgänge an; die Duplikatprüfung
    über die Message-ID greift dabei nicht, weil beide Prozesse prüfen, bevor
    einer geschrieben hat.

    Bleibt nach einem Absturz eine Datei in ``.arbeit`` liegen, wird sie NICHT
    automatisch zurückgeholt — das könnte einem noch laufenden Prozess die
    Datei unter den Händen wegziehen. Solche Reste gehören von Hand geprüft
    und zurück in den Eingang gelegt.
    """
    ordner = pathlib.Path(import_ordner)
    if not ordner.is_dir():
        logger.warning("Mail-Import: Ordner nicht gefunden: %s", ordner)
        return {'dateien': 0, 'vorgang_neu': 0, 'thread_zuordnung': 0,
                'duplikat': 0, 'nicht_zugeordnet': 0, 'fehler': 0,
                'uebersprungen': 0}

    archiv = pathlib.Path(archiv_ordner) if archiv_ordner else ordner / 'archiv'
    archiv.mkdir(parents=True, exist_ok=True)
    fehler_dir = pathlib.Path(fehler_ordner) if fehler_ordner else None
    if fehler_dir:
        fehler_dir.mkdir(parents=True, exist_ok=True)
    arbeit = ordner / '.arbeit'
    arbeit.mkdir(parents=True, exist_ok=True)

    dateien = sorted(
        (p for p in ordner.iterdir()
         if p.is_file() and p.suffix.lower() in ERLAUBTE_ENDUNGEN),
        key=lambda p: p.name,
    )

    ergebnis = {'dateien': len(dateien), 'vorgang_neu': 0, 'thread_zuordnung': 0,
                'duplikat': 0, 'nicht_zugeordnet': 0, 'fehler': 0,
                'uebersprungen': 0}

    # Schritt 1: reservieren (siehe Docstring — Schutz gegen parallele Läufe).
    reserviert: list[pathlib.Path] = []
    for datei in dateien:
        ziel = _zielpfad(arbeit, datei.name)
        try:
            datei.rename(ziel)
        except (FileNotFoundError, PermissionError, OSError):
            # Ein anderer Lauf war schneller — Normalfall bei Parallelität,
            # kein Fehler.
            ergebnis['uebersprungen'] += 1
            logger.info("Mail-Import: %s wird bereits anderswo verarbeitet.",
                        datei.name)
            continue
        reserviert.append(ziel)

    # Schritt 2: lesen und nach SENDEZEITPUNKT ordnen — nicht nach Dateizeit.
    # Die Thread-Zuordnung hängt daran: eine Nachfassmail verweist per
    # In-Reply-To auf die Ursprungsmail, und dieser Verweis geht nur auf,
    # wenn der Vorgang zur Ursprungsmail bereits existiert. Legt jemand
    # einen ganzen Posteingang auf einmal ab, ist die Dateireihenfolge
    # beliebig — und die Nachfassmail landet als zweiter, eigenständiger
    # Vorgang statt als Ereignis am ersten.
    # Sortiert wird über den Zeitstempel als Zahl, nicht über datetime —
    # sonst verglichen sich hier None-Werte und zeitzonenbehaftete mit
    # naiven Datumsangaben.
    stapel: list[tuple[int, float, str, pathlib.Path, ParsedMail | None]] = []
    for pfad in reserviert:
        try:
            parsed = parse_mail(pfad)
        except Exception:
            # Defekte Datei: Reihenfolge egal, Fehlerbehandlung in
            # verarbeite_datei. Ans Ende, damit sie keine gute Mail aufhält.
            logger.exception("Mail-Import: %s nicht lesbar.", pfad.name)
            stapel.append((2, 0.0, pfad.name, pfad, None))
            continue
        # Mails ohne Datum hinter die datierten — sie können keinen
        # Thread-Bezug stiften, auf den etwas anderes wartet.
        if parsed.gesendet_am:
            stapel.append((0, parsed.gesendet_am.timestamp(), pfad.name, pfad, parsed))
        else:
            stapel.append((1, 0.0, pfad.name, pfad, parsed))

    stapel.sort(key=lambda eintrag: eintrag[:3])

    # Schritt 3: verarbeiten, älteste Mail zuerst.
    for _, _, _, pfad, parsed in stapel:
        protokoll = verarbeite_datei(pfad, archiv, fehler_dir,
                                     anlegen=anlegen, parsed=parsed)
        if protokoll.status in ergebnis:
            ergebnis[protokoll.status] += 1

    return ergebnis
