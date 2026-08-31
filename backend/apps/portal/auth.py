"""
Authentifizierung der Portal-Endpunkte (Spec 1a, Kap. 7).

Eigene DRF-Authentication-Klasse statt SimpleJWT, weil ein Eigentümer
bewusst keinen ``django.contrib.auth``-User hat (Begründung im Docstring
von ``apps.portal.models``).

Kernregel dieser Spec: die Person wird AUSSCHLIESSLICH aus dem
Sitzungs-Token abgeleitet. Kein Portal-Endpunkt darf eine Personen- oder
Einheiten-ID vom Client als Autorisierung akzeptieren.
"""
from datetime import timedelta

from django.utils import timezone
from rest_framework import authentication, exceptions, permissions

from .models import PortalSession

_ZUGRIFF_SCHREIBINTERVALL = timedelta(minutes=5)


class PortalSessionAuthentication(authentication.BaseAuthentication):
    """``Authorization: Portal <token>``.

    Eigenes Schema-Präfix ``Portal`` statt ``Bearer``: so kann ein
    Portal-Token niemals versehentlich als Mitarbeiter-JWT durch die
    SimpleJWT-Kette laufen (und umgekehrt), auch wenn beide Systeme im
    selben Browser benutzt werden.

    ``authenticate`` gibt ``(None, session)`` NICHT zurück — DRF verlangt
    einen wahrheitswertigen User. Wir liefern deshalb ein leichtgewichtiges
    ``PortalNutzer``-Objekt, das sich für DRF wie ein authentifizierter
    User verhält, aber keinerlei Django-Permissions besitzt.
    """

    keyword = 'Portal'

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).split()
        if not header or header[0].lower() != self.keyword.lower().encode():
            return None
        if len(header) != 2:
            raise exceptions.AuthenticationFailed('Ungültiger Authorization-Header.')

        try:
            token = header[1].decode()
        except UnicodeError:
            raise exceptions.AuthenticationFailed('Ungültiger Authorization-Header.')

        session = (
            PortalSession.objects
            .select_related('zugang', 'zugang__person')
            .filter(token=token)
            .first()
        )
        if session is None or not session.ist_gueltig():
            raise exceptions.AuthenticationFailed('Sitzung ungültig oder abgelaufen.')

        # Ein zwischenzeitlich gesperrter Zugang wirkt sofort — genau dafür
        # ist die Sitzung ein DB-Datensatz und kein signiertes Token.
        if not session.zugang.aktiv:
            raise exceptions.AuthenticationFailed('Sitzung ungültig oder abgelaufen.')

        # Nur grob mitschreiben: ein DB-Write bei JEDEM Request wäre für
        # eine reine Aktivitätsanzeige unverhältnismäßig — eine Portal-Seite
        # setzt schnell mehrere Requests gleichzeitig ab.
        jetzt = timezone.now()
        if (jetzt - session.letzter_zugriff) > _ZUGRIFF_SCHREIBINTERVALL:
            session.letzter_zugriff = jetzt
            session.save(update_fields=['letzter_zugriff'])

        request.portal_session = session
        request.portal_zugang = session.zugang
        return (PortalNutzer(session.zugang), None)

    def authenticate_header(self, request):
        return self.keyword


class PortalNutzer:
    """Minimaler User-Ersatz für DRF.

    Absichtlich ohne ``has_perm``/``groups`` — ein Portal-Nutzer soll
    nirgendwo im internen Berechtigungssystem mitspielen können.
    """

    is_authenticated = True
    is_anonymous = False
    is_staff = False
    is_superuser = False
    is_active = True

    def __init__(self, zugang):
        self.zugang = zugang
        self.person = zugang.person
        self.pk = zugang.pk

    def __str__(self):
        return f'Portal-Nutzer {self.person}'


class IstPortalNutzer(permissions.BasePermission):
    """Erlaubt den Zugriff nur mit gültiger Portal-Sitzung.

    Prüft explizit auf ``PortalNutzer`` — ein eingeloggter Mitarbeiter darf
    die Portal-Endpunkte NICHT über sein normales JWT erreichen, sonst
    hinge an ``request.portal_zugang`` nichts und die Person-Ableitung
    liefe ins Leere.
    """

    message = 'Kein gültiger Portal-Zugang.'

    def has_permission(self, request, view):
        return isinstance(getattr(request, 'user', None), PortalNutzer)
