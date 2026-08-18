"""
KI-Antwortvorschlag-Service (Folgeauftrag, nicht Teil der ursprünglichen
Vorgang & DMS-Spec).

Erzeugt bei Vorgangsanlage (steuerbar über ``VorgangTyp.antwort_vorschlag_aktiv``)
oder auf Anfrage einen Antwortvorschlag per Claude API und begleitet dessen
Lebenszyklus (Entwurf -> bearbeitet -> freigegeben/verworfen). Nach Freigabe
wird der Text AUSSCHLIESSLICH als ``VorgangEreignis`` im Verlauf hinterlegt —
es gibt bewusst KEINEN Mailversand/SMTP/PDF-Export (Entscheidung Patrik): der
Versand an den Empfänger erfolgt manuell durch den Mitarbeiter.

Datenschutz-Hinweis (bewusste Entscheidung, siehe Auftrag): Der Prompt
enthält personenbezogene Daten (Name der Person, Rolle Eigentümer/Mieter),
damit die KI eine korrekte Anrede formulieren kann. Diese Daten gehen an die
Anthropic-API (gleiches Muster wie ``rechnungen.services.ocr`` und
``buchhaltung.services.ebanking_erkennungs_service``).

Alle Statuswechsel laufen ausschließlich über die Funktionen dieses Moduls —
nie durch direktes Setzen von ``VorgangAntwortVorschlag.status``.
"""
import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.vorgaenge.models import VorgangAntwortVorschlag, VorgangEreignis

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """Du bist Assistent einer WEG-Hausverwaltung (Demme GmbH) \
und formulierst die Antwort auf einen Vorgang. Ziel ist ein fertiger, \
versandfähiger Brief-/Mailtext in der Sie-Form, sachlich und freundlich im \
Ton. Ein Mitarbeiter prüft den Text intern vor dem Versand — das ist ein \
rein interner Vorgang, der im Text selbst NICHT vorkommen darf.

WICHTIGE EINSCHRÄNKUNGEN — halte dich strikt daran:
- Mache KEINE verbindlichen Zusagen (keine festen Termine, keine Zusicherung \
von Reparaturen/Maßnahmen).
- Nenne KEINE konkreten Fristen, es sei denn, sie stehen bereits explizit im \
Vorgangstext.
- Nenne KEINE Kosten oder Beträge, sofern sie nicht bereits im Vorgangstext \
genannt sind.
- Gib KEINE Rechtsauskünfte und zitiere kein Gesetz.
- Schreibe den Text so, als würde er direkt an den Empfänger versendet. \
Weise NIEMALS darauf hin, dass es sich um einen Entwurf handelt, dass der \
Text noch intern/durch einen Mitarbeiter geprüft wird, dass er von einer KI \
erzeugt wurde, oder auf sonstige interne Abläufe der Verwaltung. Formulierungen \
wie „dieser Entwurf wird noch geprüft“, „wir melden uns intern zurück“ oder \
Ähnliches sind NICHT erlaubt.

Antworte NUR mit dem reinen Antworttext (Anrede bis Grußformel), ohne \
Einleitung, ohne Anführungszeichen, ohne Markdown."""


def _baue_prompt(vorgang) -> str:
    zeilen = [
        f"Vorgangstyp: {vorgang.typ.bezeichnung}",
        f"Priorität: {vorgang.get_prioritaet_display()}",
        f"Betreff: {vorgang.betreff}",
    ]
    if vorgang.objekt_id:
        zeilen.append(f"Objekt: {vorgang.objekt.bezeichnung}")
    if vorgang.einheit_id:
        zeilen.append(f"Einheit: {vorgang.einheit.einheit_nr}")
    if vorgang.person_id:
        person = vorgang.person
        rolle = person.get_person_typ_display() or 'unbekannt'
        zeilen.append(f"Ansprechpartner: {person.name} (Rolle: {rolle})")
    else:
        zeilen.append("Ansprechpartner: unbekannt — verwende eine neutrale Anrede.")
    zeilen.append("")
    zeilen.append("Beschreibung des Vorgangs:")
    zeilen.append(vorgang.beschreibung or '(keine Beschreibung angegeben)')

    return '\n'.join(zeilen)


def _rufe_ki_auf(vorgang) -> tuple[str, str]:
    """Ruft die Anthropic-API auf. Gibt (text, modell) zurück oder wirft eine
    Exception (Fehlerbehandlung obliegt dem Aufrufer)."""
    import anthropic
    from django.conf import settings

    api_key = getattr(settings, 'ANTHROPIC_API_KEY', None)
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY nicht konfiguriert")

    model = getattr(settings, 'ANTHROPIC_MODEL', 'claude-sonnet-4-5')
    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model=model,
        max_tokens=4000,  # claude-sonnet-5 denkt zuerst — Budget für Thinking + Text
        system=_SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': _baue_prompt(vorgang)}],
    )
    text = next((b.text for b in message.content if getattr(b, 'type', None) == 'text'), '').strip()
    if not text:
        raise RuntimeError("Claude API lieferte keinen Antworttext")
    return text, model


@transaction.atomic
def erzeuge_vorschlag(vorgang, erstellt_von=None) -> VorgangAntwortVorschlag:
    """Erzeugt einen neuen ``VorgangAntwortVorschlag`` für ``vorgang``.

    Existiert bereits ein Vorschlag mit ``status='entwurf'``, wird dieser
    zuvor auf ``'verworfen'`` gesetzt (Constraint: höchstens ein Entwurf je
    Vorgang) — mit eigenem ``VorgangEreignis``.

    Fehlerfall (fehlender API-Key, API-Fehler, Timeout, leere Antwort): KEIN
    Crash — es wird ein Vorschlag mit ``status='fehlgeschlagen'`` und
    ``fehler``-Text angelegt und geloggt. Die Vorgangsanlage darf NIEMALS an
    einer nicht erreichbaren KI scheitern.
    """
    bestehender_entwurf = VorgangAntwortVorschlag.objects.filter(
        vorgang=vorgang, status='entwurf',
    ).first()
    if bestehender_entwurf:
        _verwerfe_intern(
            bestehender_entwurf, verworfen_von=erstellt_von,
            grund='Automatisch verworfen: neuer Antwortvorschlag angefordert.',
        )

    try:
        text, modell = _rufe_ki_auf(vorgang)
    except Exception as exc:
        logger.warning(
            "KI-Antwortvorschlag für Vorgang %s fehlgeschlagen: %s", vorgang.nummer, exc,
        )
        vorschlag = VorgangAntwortVorschlag.objects.create(
            vorgang=vorgang, status='fehlgeschlagen', fehler=str(exc),
            erzeugt_von=erstellt_von,
        )
        VorgangEreignis.objects.create(
            vorgang=vorgang, typ='antwort_vorschlag_erzeugt',
            text=f"KI-Antwortvorschlag fehlgeschlagen: {exc}",
            erstellt_von=erstellt_von, intern=True,
        )
        return vorschlag

    vorschlag = VorgangAntwortVorschlag.objects.create(
        vorgang=vorgang, text_ki=text, text=text, status='entwurf',
        modell=modell, erzeugt_von=erstellt_von,
    )
    VorgangEreignis.objects.create(
        vorgang=vorgang, typ='antwort_vorschlag_erzeugt',
        text='KI-Antwortvorschlag erzeugt.', erstellt_von=erstellt_von, intern=True,
    )
    return vorschlag


@transaction.atomic
def bearbeite_vorschlag(vorschlag: VorgangAntwortVorschlag, text: str,
                         bearbeitet_von) -> VorgangAntwortVorschlag:
    """Aktualisiert ``text`` eines Vorschlags — nur im Status ``'entwurf'``
    erlaubt. ``text_ki`` bleibt unangetastet (GoBD-Nachvollziehbarkeit)."""
    if vorschlag.status != 'entwurf':
        raise ValidationError(
            f"Bearbeiten ist nur im Status 'entwurf' möglich (aktuell: '{vorschlag.status}')."
        )
    if not text or not text.strip():
        raise ValidationError("Text darf nicht leer sein.")

    vorschlag.text = text
    vorschlag.bearbeitet_am = timezone.now()
    vorschlag.bearbeitet_von = bearbeitet_von
    vorschlag.full_clean()
    vorschlag.save()

    VorgangEreignis.objects.create(
        vorgang=vorschlag.vorgang, typ='antwort_vorschlag_bearbeitet',
        text='KI-Antwortvorschlag bearbeitet.', erstellt_von=bearbeitet_von, intern=True,
    )
    return vorschlag


@transaction.atomic
def gib_frei(vorschlag: VorgangAntwortVorschlag, freigegeben_von) -> VorgangAntwortVorschlag:
    """Gibt einen Vorschlag frei — nur aus ``'entwurf'``. Der freigegebene
    Text wird dauerhaft im ``VorgangEreignis`` (Feld ``text``) hinterlegt —
    das ist die einzige Hinterlegung; es gibt keinen Mailversand hier.

    ``intern=False`` (Patrik-Entscheidung): erst die FREIGABE macht den Text
    für den Eigentümer sichtbar — der Entwurf davor (``antwort_vorschlag_erzeugt``/
    ``_bearbeitet``/``_verworfen``) bleibt immer intern.
    """
    if vorschlag.status != 'entwurf':
        raise ValidationError(
            f"Freigabe ist nur im Status 'entwurf' möglich (aktuell: '{vorschlag.status}')."
        )

    vorschlag.status = 'freigegeben'
    vorschlag.freigegeben_am = timezone.now()
    vorschlag.freigegeben_von = freigegeben_von
    vorschlag.full_clean()
    vorschlag.save()

    VorgangEreignis.objects.create(
        vorgang=vorschlag.vorgang, typ='antwort_vorschlag_freigegeben',
        text=vorschlag.text, erstellt_von=freigegeben_von, intern=False,
    )
    return vorschlag


def _verwerfe_intern(vorschlag: VorgangAntwortVorschlag, verworfen_von, grund=None):
    """Interne Mutation ohne erneute Status-Prüfung (wird bereits vom Aufrufer
    sichergestellt) — vermeidet doppelte Fehlermeldungen beim automatischen
    Verwerfen des alten Entwurfs in ``erzeuge_vorschlag``."""
    vorschlag.status = 'verworfen'
    vorschlag.save(update_fields=['status'])
    VorgangEreignis.objects.create(
        vorgang=vorschlag.vorgang, typ='antwort_vorschlag_verworfen',
        text=grund or 'KI-Antwortvorschlag verworfen.', erstellt_von=verworfen_von,
        intern=True,
    )


@transaction.atomic
def verwirf(vorschlag: VorgangAntwortVorschlag, verworfen_von, grund=None) -> VorgangAntwortVorschlag:
    """Verwirft einen Vorschlag — nur aus ``'entwurf'``."""
    if vorschlag.status != 'entwurf':
        raise ValidationError(
            f"Verwerfen ist nur im Status 'entwurf' möglich (aktuell: '{vorschlag.status}')."
        )
    _verwerfe_intern(vorschlag, verworfen_von, grund)
    return vorschlag
