"""E-Mail-Versand eines Schreibens (Spec 7.3).

Mechanik wie ``apps.versammlung.services.einladung_service._versende_mail``:
``EmailMultiAlternatives`` mit Text-Body, HTML-Alternative und PDF-Anhang über
das globale ``EMAIL_BACKEND`` (SMTP oder Graph) und ``DEFAULT_FROM_EMAIL``.

Dieser Service kennt keinen Schreiben-Status - er versendet nur und wirft bei
jedem Problem eine Exception. Die Statusübergänge liegen ausschließlich in
``schreiben_service``.

``versand_konfiguriert`` ist bewusst eine Kopie von
``einladung_service.versand_konfiguriert`` / ``handwerker.tasks._versand_konfiguriert``
(kein Import über App-Grenzen, der bei Phase 6 einen Zyklus zwischen
``versammlung`` und ``korrespondenz`` erzeugen würde). Mit dieser Kopie gibt es
drei Stellen - sobald es konsolidiert wird, gehört die Prüfung in einen
gemeinsamen Helfer.
"""
from email.utils import make_msgid

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import linebreaks

# Backends, die nie tatsächlich versenden (Konsole/Dummy).
_NICHT_VERSANDFAEHIGE_BACKENDS = (
    'django.core.mail.backends.console.EmailBackend',
    'django.core.mail.backends.dummy.EmailBackend',
)

STANDARD_TEXT = (
    'Sehr geehrte Damen und Herren,\n\n'
    'anbei erhalten Sie unser Schreiben "{betreff}" ({nummer}) als PDF.\n\n'
    'Mit freundlichen Grüßen\n{firma}'
)


class MailVersandFehler(Exception):
    """Mail konnte nicht versendet werden (Konfiguration oder Transport)."""


def versand_konfiguriert() -> bool:
    """Prüft, ob ``settings.EMAIL_BACKEND`` tatsächlich versendet.

    Ohne diese Prüfung meldet das Konsolen-Backend (Default ohne
    ``.env.prod``-Konfiguration) jede Mail als erfolgreich, obwohl sie nur ins
    Log geschrieben wird. ``locmem`` (Django-Tests) gilt als versandfähig.
    """
    backend = settings.EMAIL_BACKEND
    if backend in _NICHT_VERSANDFAEHIGE_BACKENDS:
        return False
    if backend == 'django.core.mail.backends.smtp.EmailBackend' and not settings.EMAIL_HOST:
        return False
    if backend == 'config.email_backends.GraphEmailBackend' and not (
        settings.MS_GRAPH_TENANT_ID and settings.MS_GRAPH_CLIENT_ID
        and settings.MS_GRAPH_CLIENT_SECRET
    ):
        return False
    return True


def baue_text(begleittext: str, *, betreff: str, nummer: str, firma: str) -> str:
    """Mail-Body: ``VorlagenVersion.email_begleittext`` (Klartext), sonst Standardtext."""
    if (begleittext or '').strip():
        return begleittext.strip()
    return STANDARD_TEXT.format(betreff=betreff, nummer=nummer, firma=firma or '')


def neue_message_id() -> str:
    """Eigene Message-ID, damit sie am Schreiben gespeichert werden kann."""
    domain = settings.DEFAULT_FROM_EMAIL.rsplit('@', 1)[-1] or None
    return make_msgid(domain=domain)


def sende_schreiben(*, adresse: str, betreff: str, text: str, pdf: bytes,
                    dateiname: str, message_id: str) -> None:
    """Versendet die Mail mit HTML-Alternative und PDF-Anhang.

    Wirft ``MailVersandFehler``, wenn kein Versand konfiguriert ist oder der
    Transport scheitert - nie ein stiller Erfolg.
    """
    if not versand_konfiguriert():
        raise MailVersandFehler(
            'E-Mail-Versand ist auf diesem Server nicht konfiguriert '
            f'(EMAIL_BACKEND={settings.EMAIL_BACKEND!r}) - es wurde nichts versendet.'
        )
    mail = EmailMultiAlternatives(
        subject=betreff, body=text, from_email=settings.DEFAULT_FROM_EMAIL, to=[adresse],
        headers={'Message-ID': message_id},
    )
    mail.attach_alternative(linebreaks(text, autoescape=True), 'text/html')
    mail.attach(dateiname, pdf, 'application/pdf')
    try:
        gesendet = mail.send()
    except Exception as exc:  # noqa: BLE001 - Transportfehler jeder Art -> fachlicher Fehler
        raise MailVersandFehler(f'E-Mail-Versand fehlgeschlagen: {exc}') from exc
    if not gesendet:
        raise MailVersandFehler('E-Mail-Versand fehlgeschlagen: Backend hat keine Mail versendet.')
