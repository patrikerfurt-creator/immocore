"""
Zugangs- und Token-Logik des Eigentümer-Portals (Spec 1a, Kap. 3).

Alle drei Link-Typen (Einladung, Magic Link, E-Mail-Bestätigung) laufen
über dieselbe Einlöse-Funktion ``loese_token_ein`` — damit kann die
Einmalverwendung nicht in einem der Flows versehentlich fehlen.
"""
import logging
from datetime import timedelta

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.personen.models import Person
from ..models import (
    EINLADUNG_GUELTIG_STUNDEN,
    EMAIL_BESTAETIGUNG_GUELTIG_STUNDEN,
    MAGIC_LINK_GUELTIG_MINUTEN,
    SESSION_GUELTIG_STUNDEN,
    PortalSession,
    PortalToken,
    PortalZugang,
)

logger = logging.getLogger(__name__)


# Rate-Limiting (Spec Kap. 3.3): max. 5 Magic-Link-Anfragen je
# E-Mail-Adresse pro Stunde.
MAGIC_LINK_MAX_PRO_STUNDE = 5
_RATE_LIMIT_FENSTER_SEKUNDEN = 3600


class PortalFehler(Exception):
    """Basisklasse für fachliche Portal-Fehler."""


class TokenUngueltig(PortalFehler):
    """Token existiert nicht, ist abgelaufen oder wurde bereits verwendet."""


class ZugangGesperrt(PortalFehler):
    """Der Zugang existiert, ist aber deaktiviert."""


class RateLimitErreicht(PortalFehler):
    """Zu viele Magic-Link-Anfragen für dieselbe Adresse."""


# ---------------------------------------------------------------------------
# E-Mail-Auflösung
# ---------------------------------------------------------------------------

def person_email(person: Person) -> str:
    """Erste brauchbare E-Mail-Adresse einer Person.

    ``Person.emails`` (JSON-Liste) ist das neue Feld, ``Person.email`` das
    Legacy-Feld; beide sind im Bestand gefüllt. Einträge der JSON-Liste
    können Strings oder Dicts sein. Gleiche Reihenfolge wie in
    ``apps.versammlung.services.einladung_service._erste_email`` — bewusst
    identisches Verhalten, damit Einladungsmail und Portal-Login dieselbe
    Adresse verwenden.
    """
    for eintrag in (person.emails or []):
        if isinstance(eintrag, str) and eintrag.strip():
            return eintrag.strip()
        if isinstance(eintrag, dict):
            for schluessel in ('adresse', 'email', 'wert'):
                wert = (eintrag.get(schluessel) or '').strip()
                if wert:
                    return wert
    return (person.email or '').strip()


def finde_zugang_per_email(email: str):
    """Aktiver Zugang zu einer E-Mail-Adresse, sonst ``None``.

    Gesucht wird über die tatsächlich für den Login geltende Adresse —
    also die der Person, NICHT ``email_pending``: eine noch unbestätigte
    Adresse darf keinen Login ermöglichen (Spec Kap. 5.3).

    Die Schleife statt eines DB-Filters ist Absicht: ``Person.emails`` ist
    ein JSONField mit heterogenen Einträgen (Strings wie Dicts), das sich
    nicht zuverlässig in ein ``__contains`` übersetzen lässt. Iteriert wird
    nur über PortalZugänge, nicht über alle Personen — das bleibt bei der
    zu erwartenden Zahl an Portal-Nutzern unkritisch.
    """
    gesucht = (email or '').strip().lower()
    if not gesucht:
        return None

    for zugang in (
        PortalZugang.objects.select_related('person').filter(aktiv=True)
    ):
        if person_email(zugang.person).lower() == gesucht:
            return zugang
    return None


# ---------------------------------------------------------------------------
# Token erzeugen
# ---------------------------------------------------------------------------

def _erzeuge_token(zugang: PortalZugang, typ: str, gueltig_bis, ziel_email: str = '') -> PortalToken:
    return PortalToken.objects.create(
        zugang=zugang, typ=typ, gueltig_bis=gueltig_bis, ziel_email=ziel_email,
    )


def _entwerte_offene_token(zugang: PortalZugang, typ: str) -> None:
    """Ältere, noch offene Token desselben Typs entwerten.

    Sonst blieben nach mehreren Anfragen mehrere gültige Magic Links
    gleichzeitig im Umlauf — jede versendete Mail wäre ein eigener,
    dauerhaft nutzbarer Schlüssel.
    """
    (
        PortalToken.objects
        .filter(zugang=zugang, typ=typ, verbraucht_am__isnull=True)
        .update(verbraucht_am=timezone.now())
    )


@transaction.atomic
def lade_ein(person: Person, mitarbeiter=None) -> tuple[PortalZugang, PortalToken]:
    """Portal-Zugang anlegen (falls nötig) und Einladungs-Token erzeugen.

    Idempotent bezogen auf den Zugang: eine erneute Einladung legt keinen
    zweiten Zugang an, sondern erzeugt einen frischen Einladungslink.
    Ein bereits aktivierter Zugang wird dabei NICHT zurückgesetzt —
    ``erstaktivierung_am`` bleibt als Historie erhalten.
    """
    zugang, neu = PortalZugang.objects.get_or_create(
        person=person,
        defaults={'eingeladen_von': mitarbeiter, 'eingeladen_am': timezone.now()},
    )
    if not neu:
        zugang.eingeladen_von = mitarbeiter or zugang.eingeladen_von
        zugang.eingeladen_am = timezone.now()
        if not zugang.aktiv:
            zugang.aktiv = True
        zugang.save(update_fields=['eingeladen_von', 'eingeladen_am', 'aktiv', 'geaendert_am'])

    _entwerte_offene_token(zugang, PortalToken.TYP_EINLADUNG)
    token = _erzeuge_token(
        zugang,
        PortalToken.TYP_EINLADUNG,
        timezone.now() + timedelta(hours=EINLADUNG_GUELTIG_STUNDEN),
    )
    return zugang, token


def _rate_limit_schluessel(email: str) -> str:
    return f'portal:magic:{email.strip().lower()}'


def pruefe_rate_limit(email: str) -> None:
    """Zählt eine Magic-Link-Anfrage und wirft bei Überschreitung.

    Bewusst VOR der Prüfung, ob es den Zugang überhaupt gibt: sonst wäre
    aus dem unterschiedlichen Verhalten ablesbar, welche Adressen im
    System existieren (Enumeration, Spec Kap. 3.2).
    """
    schluessel = _rate_limit_schluessel(email)
    try:
        # Legt den Zähler mit TTL an, falls er noch nicht existiert — ``incr``
        # allein würde bei fehlendem Schlüssel scheitern und (je nach Backend)
        # einen Zähler ohne Ablaufzeit hinterlassen.
        cache.get_or_set(schluessel, 0, _RATE_LIMIT_FENSTER_SEKUNDEN)
        anzahl = cache.incr(schluessel)
    except ValueError:
        # Schlüssel zwischen get_or_set und incr abgelaufen — neu beginnen.
        cache.set(schluessel, 1, _RATE_LIMIT_FENSTER_SEKUNDEN)
        anzahl = 1
    except Exception:
        # Cache-Ausfall darf den Login nicht blockieren; das Rate-Limit ist
        # ein Missbrauchsschutz, keine Sicherheitsgrenze.
        logger.exception('Rate-Limit-Zähler nicht verfügbar — Anfrage wird durchgelassen.')
        return

    if anzahl > MAGIC_LINK_MAX_PRO_STUNDE:
        raise RateLimitErreicht(
            f'Mehr als {MAGIC_LINK_MAX_PRO_STUNDE} Anfragen pro Stunde.'
        )


@transaction.atomic
def erzeuge_magic_link(zugang: PortalZugang) -> PortalToken:
    _entwerte_offene_token(zugang, PortalToken.TYP_MAGIC)
    return _erzeuge_token(
        zugang,
        PortalToken.TYP_MAGIC,
        timezone.now() + timedelta(minutes=MAGIC_LINK_GUELTIG_MINUTEN),
    )


@transaction.atomic
def erzeuge_email_bestaetigung(zugang: PortalZugang, neue_email: str) -> PortalToken:
    _entwerte_offene_token(zugang, PortalToken.TYP_EMAIL_BESTAETIGUNG)
    return _erzeuge_token(
        zugang,
        PortalToken.TYP_EMAIL_BESTAETIGUNG,
        timezone.now() + timedelta(hours=EMAIL_BESTAETIGUNG_GUELTIG_STUNDEN),
        ziel_email=neue_email.strip(),
    )


# ---------------------------------------------------------------------------
# Token einlösen
# ---------------------------------------------------------------------------

@transaction.atomic
def loese_token_ein(token_wert: str, erwartete_typen: tuple[str, ...]) -> PortalToken:
    """Prüft und verbraucht einen Token. Wirft ``TokenUngueltig``.

    ``select_for_update`` gegen die Doppelverwendung bei zwei fast
    gleichzeitigen Klicks (Mail-Client mit Linkvorschau + Nutzerklick).
    Der Fehlertext ist bewusst für alle Fälle identisch — er darf nicht
    verraten, ob ein Token existiert, abgelaufen oder schon benutzt ist.
    """
    tok = (
        PortalToken.objects
        .select_for_update()
        .select_related('zugang', 'zugang__person')
        .filter(token=(token_wert or '').strip(), typ__in=erwartete_typen)
        .first()
    )
    if tok is None or not tok.ist_gueltig():
        raise TokenUngueltig('Dieser Link ist ungültig oder abgelaufen.')
    if not tok.zugang.aktiv:
        raise ZugangGesperrt('Dieser Zugang ist nicht aktiv.')

    tok.verbraucht_am = timezone.now()
    tok.save(update_fields=['verbraucht_am'])
    return tok


@transaction.atomic
def melde_an(token_wert: str) -> tuple[PortalSession, PortalToken, bool]:
    """Login per Einladungs- oder Magic-Link-Token.

    Beide Typen werden hier angenommen: fachlich ist die Einladung ein
    Magic Link mit längerer Frist (Spec Kap. 3.1: "Klick aktiviert den
    Zugang und loggt direkt ein").

    ``erstaktivierung_am`` haengt am ERFOLGREICHEN LOGIN, nicht am
    Token-Typ: laesst der Eingeladene den 72-Stunden-Link verfallen und
    meldet sich danach per Magic Link an, ist der Zugang genauso in
    Benutzung — der Verwaltung als "eingeladen, noch nicht aktiviert"
    anzuzeigen waere schlicht falsch.

    Drittes Rueckgabeelement: ob DIESER Login die Erstaktivierung war.
    """
    tok = loese_token_ein(
        token_wert, (PortalToken.TYP_EINLADUNG, PortalToken.TYP_MAGIC)
    )
    zugang = tok.zugang

    jetzt = timezone.now()
    felder = ['letzter_login', 'geaendert_am']
    zugang.letzter_login = jetzt
    erstanmeldung = zugang.erstaktivierung_am is None
    if erstanmeldung:
        zugang.erstaktivierung_am = jetzt
        felder.append('erstaktivierung_am')
    zugang.save(update_fields=felder)

    session = PortalSession.objects.create(
        zugang=zugang,
        gueltig_bis=jetzt + timedelta(hours=SESSION_GUELTIG_STUNDEN),
    )
    return session, tok, erstanmeldung


def melde_ab(session: PortalSession) -> None:
    session.delete()
