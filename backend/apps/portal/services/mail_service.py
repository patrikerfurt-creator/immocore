"""
Mailversand des Eigentümer-Portals (Spec 1a, Kap. 3 und 5.3).

Drei Mails, ein Muster: Einladung, Magic Link, E-Mail-Bestätigung.

Wie beim Handwerkerauftrag wird in Produktion geprüft, ob überhaupt ein
versandfähiges Backend konfiguriert ist. Ohne diese Prüfung würde bei
fehlender SMTP-Konfiguration das Konsolen-Backend greifen: ``send()``
meldet Erfolg, die Mail landet nur im Container-Log — der Eigentümer
bekäme seinen Zugangslink nie und niemand würde es merken.
"""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from ..models import (
    EINLADUNG_GUELTIG_STUNDEN,
    EMAIL_BESTAETIGUNG_GUELTIG_STUNDEN,
    MAGIC_LINK_GUELTIG_MINUTEN,
    PortalToken,
)

logger = logging.getLogger(__name__)

_NICHT_VERSANDFAEHIGE_BACKENDS = (
    'django.core.mail.backends.console.EmailBackend',
    'django.core.mail.backends.dummy.EmailBackend',
)


class VersandNichtKonfiguriert(Exception):
    """In Produktion ist kein versandfähiges Mail-Backend eingerichtet."""


def versand_konfiguriert() -> bool:
    backend = settings.EMAIL_BACKEND
    if backend in _NICHT_VERSANDFAEHIGE_BACKENDS:
        return False
    if backend == 'django.core.mail.backends.smtp.EmailBackend' and not settings.EMAIL_HOST:
        return False
    return True


def _pruefe_versandfaehig() -> None:
    """Lokal (DEBUG=True) darf das Konsolen-Backend durchlaufen — genau so
    wird der Magic Link beim lokalen Testen im Terminal sichtbar."""
    if settings.DEBUG or versand_konfiguriert():
        return
    logger.error(
        'Kein versandfähiges Mail-Backend konfiguriert (EMAIL_BACKEND=%r, '
        'EMAIL_HOST=%r) — Portal-Mail wird NICHT versendet.',
        settings.EMAIL_BACKEND, settings.EMAIL_HOST,
    )
    raise VersandNichtKonfiguriert(
        'E-Mail-Versand ist auf diesem Server nicht konfiguriert (SMTP fehlt) — '
        'der Portal-Link kann nicht zugestellt werden.'
    )


def anmelde_url(token: PortalToken) -> str:
    """Login-Link für Einladung und Magic Link.

    Beide führen auf dieselbe Frontend-Route: ``melde_an`` akzeptiert beide
    Token-Typen, und der Eigentümer soll bei beiden dasselbe erleben —
    Link klicken, eingeloggt sein.
    """
    return f'{settings.FRONTEND_BASE_URL.rstrip("/")}/portal/anmelden/{token.token}'


def email_bestaetigung_url(token: PortalToken) -> str:
    return f'{settings.FRONTEND_BASE_URL.rstrip("/")}/portal/email-bestaetigen/{token.token}'


def _sende(betreff: str, vorlage: str, empfaenger: str, kontext: dict) -> None:
    _pruefe_versandfaehig()
    text_body = render_to_string(f'email/{vorlage}.txt', kontext)
    html_body = render_to_string(f'email/{vorlage}.html', kontext)

    mail = EmailMultiAlternatives(
        subject=betreff,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[empfaenger],
    )
    mail.attach_alternative(html_body, 'text/html')
    mail.send()


def versende_einladung(token: PortalToken, empfaenger: str) -> None:
    _sende(
        betreff='Ihr Zugang zum Eigentümer-Portal',
        vorlage='portal_einladung',
        empfaenger=empfaenger,
        kontext={
            'person': token.zugang.person,
            'link': anmelde_url(token),
            'gueltig_stunden': EINLADUNG_GUELTIG_STUNDEN,
        },
    )


def versende_magic_link(token: PortalToken, empfaenger: str) -> None:
    _sende(
        betreff='Ihr Anmeldelink für das Eigentümer-Portal',
        vorlage='portal_magic_link',
        empfaenger=empfaenger,
        kontext={
            'person': token.zugang.person,
            'link': anmelde_url(token),
            'gueltig_minuten': MAGIC_LINK_GUELTIG_MINUTEN,
        },
    )


def versende_email_bestaetigung(token: PortalToken) -> None:
    """Geht bewusst an die NEUE Adresse (``token.ziel_email``) — nur wer
    das neue Postfach erreicht, kann die Änderung wirksam machen."""
    _sende(
        betreff='Bitte bestätigen Sie Ihre neue E-Mail-Adresse',
        vorlage='portal_email_bestaetigung',
        empfaenger=token.ziel_email,
        kontext={
            'person': token.zugang.person,
            'link': email_bestaetigung_url(token),
            'neue_email': token.ziel_email,
            'gueltig_stunden': EMAIL_BESTAETIGUNG_GUELTIG_STUNDEN,
        },
    )
