"""Antwort an den Kunden — die beiden Versandwege der Chat-Ansicht.

Zwei Kanäle, beide als ``VorgangEreignis`` (``intern=False``) im Verlauf, damit
sie in der Mitarbeiter-Chat-Ansicht UND im Eigentümer-Portal erscheinen:

- ``gib_antwort_frei``  → Freigabe fürs Portal (kein Mailversand; der Kunde
  liest die Antwort im Portal). Ereignis ``antwort_freigegeben``.
- ``sende_mail_antwort`` → direkte E-Mail-Antwort an den Kunden (für Kunden
  ohne Portal-Zugang). Ereignis ``mail_antwort_gesendet``.

Die Mail trägt die Vorgangsnummer im Betreff (``[V-26-xxxxx]``) — dadurch
ordnet ``mail_import_service.finde_thread_vorgang`` die Kundenantwort
automatisch wieder DIESEM Vorgang zu, und die Konversation bleibt im Chat
zusammen. Zusätzlich wird ``In-Reply-To``/``References`` der letzten
eingegangenen Mail gesetzt (saubere Thread-Bildung in den Mailprogrammen).

Business-Logik bewusst hier, nicht in der View (Projekt-Konvention).
"""
import logging
from email.utils import make_msgid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.utils.html import linebreaks

from apps.vorgaenge.models import MailImportProtokoll, VorgangEreignis

logger = logging.getLogger(__name__)


def _empfaenger(vorgang) -> str:
    """E-Mail-Adresse des Kunden — gleiche Leseregel wie Portal-Login/Einladung."""
    if vorgang.person_id is None:
        raise ValidationError(
            "Dieser Vorgang hat keine Person — es gibt keine Empfängeradresse für die Mail-Antwort."
        )
    from apps.portal.services.zugang_service import person_email
    email = person_email(vorgang.person)
    if not email:
        raise ValidationError(
            "Für die Person dieses Vorgangs ist keine E-Mail-Adresse hinterlegt."
        )
    return email


def _letzte_eingegangene(vorgang):
    """Letzte eingegangene Mail dieses Vorgangs (für In-Reply-To/References)."""
    return (
        MailImportProtokoll.objects
        .filter(vorgang=vorgang).exclude(message_id='')
        .order_by('-gesendet_am', '-id')
        .first()
    )


@transaction.atomic
def gib_antwort_frei(vorgang, text: str, freigegeben_von) -> VorgangEreignis:
    """Gibt eine (frei formulierte oder aus dem KI-Vorschlag übernommene)
    Antwort fürs Portal frei — ``intern=False``, kein Mailversand."""
    if not text or not text.strip():
        raise ValidationError("Antworttext darf nicht leer sein.")
    return VorgangEreignis.objects.create(
        vorgang=vorgang, typ='antwort_freigegeben', text=text.strip(),
        erstellt_von=freigegeben_von, intern=False,
    )


@transaction.atomic
def portal_antwort(vorgang, text: str, erstellt_von) -> VorgangEreignis:
    """Rückantwort des Kunden über das Eigentümer-Portal — ``intern=False``,
    damit sie im Mitarbeiter-Chat UND (für den Kunden selbst) im Portal
    erscheint. ``erstellt_von`` ist der technische Portal-System-User."""
    if not text or not text.strip():
        raise ValidationError("Antworttext darf nicht leer sein.")
    return VorgangEreignis.objects.create(
        vorgang=vorgang, typ='portal_antwort', text=text.strip(),
        erstellt_von=erstellt_von, intern=False,
    )


@transaction.atomic
def sende_mail_antwort(vorgang, text: str, gesendet_von) -> VorgangEreignis:
    """Versendet die Antwort als E-Mail an den Kunden und hält sie als
    ``intern=False``-Ereignis im Verlauf fest.

    Wirft ``ValidationError`` bei leerem Text, fehlender Empfängeradresse oder
    nicht konfiguriertem Versand — der Aufrufer (View) übersetzt das zu 400.
    """
    if not text or not text.strip():
        raise ValidationError("Antworttext darf nicht leer sein.")
    text = text.strip()

    # Kopie der Versand-Prüfung aus korrespondenz.mail_versand_service — Import
    # erst hier, um einen Modul-Importzyklus (korrespondenz importiert vorgaenge)
    # zu vermeiden.
    from apps.korrespondenz.services.mail_versand_service import versand_konfiguriert
    if not versand_konfiguriert():
        raise ValidationError(
            "E-Mail-Versand ist nicht konfiguriert — die Antwort kann nicht per Mail gesendet werden."
        )

    empfaenger = _empfaenger(vorgang)
    betreff = f"AW: {vorgang.betreff} [{vorgang.nummer}]"

    letzte = _letzte_eingegangene(vorgang)
    in_reply_to = letzte.message_id if letzte else ''

    nachricht = EmailMultiAlternatives(
        subject=betreff,
        body=text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[empfaenger],
    )
    nachricht.attach_alternative(linebreaks(text), 'text/html')
    nachricht.extra_headers['Message-ID'] = make_msgid()
    if in_reply_to:
        nachricht.extra_headers['In-Reply-To'] = in_reply_to
        nachricht.extra_headers['References'] = in_reply_to

    try:
        nachricht.send(fail_silently=False)
    except Exception as exc:  # Transport-/Konfigurationsfehler
        logger.exception("Mail-Antwort für Vorgang %s fehlgeschlagen.", vorgang.nummer)
        raise ValidationError(f"Mail konnte nicht versendet werden: {exc}")

    return VorgangEreignis.objects.create(
        vorgang=vorgang, typ='mail_antwort_gesendet', text=text,
        neuer_wert=empfaenger[:100], erstellt_von=gesendet_von, intern=False,
    )
