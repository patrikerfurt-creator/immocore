"""
Öffentliche und sitzungsgeschützte Portal-Endpunkte (Spec 1a, Kap. 7).

Sicherheitsregeln (übernommen aus den öffentlichen Handwerker-Endpunkten,
dort ausführlich begründet):

* ``authentication_classes = []`` auf den anonymen Endpunkten — bliebe
  DRFs ``SessionAuthentication`` in der Kette, würde ein anonymer POST für
  jeden mit noch gültigem Session-Cookie sporadisch an CSRF scheitern.
* Anmelde-Endpunkte sind POST. Ein GET, das eine Sitzung eröffnet, würde
  von Mail-Scannern und Link-Vorschauen ausgelöst — der Einmal-Token wäre
  verbraucht, bevor der Eigentümer den Link überhaupt anklickt.
* Die Person wird immer aus ``request.portal_zugang`` abgeleitet, nie aus
  einem Parameter des Clients.
"""
import logging

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .auth import IstPortalNutzer, PortalSessionAuthentication
from .models import SESSION_GUELTIG_STUNDEN
from .serializers import (
    BankverbindungSerializer,
    EmailAenderungSerializer,
    KontaktAenderungSerializer,
    MagicLinkAnfrageSerializer,
    MeineDatenSerializer,
    TokenSerializer,
    WegKarteSerializer,
)
from .services import einheiten_service, mail_service, stammdaten_service, zugang_service
from .services.stammdaten_service import StammdatenFehler
from .services.zugang_service import RateLimitErreicht, TokenUngueltig, ZugangGesperrt

logger = logging.getLogger(__name__)

# Neutrale Antwort auf die Magic-Link-Anfrage (Spec Kap. 3.2): sie darf
# NICHT verraten, ob zu einer Adresse ein Zugang besteht.
_NEUTRALE_ANTWORT = {
    'detail': 'Falls ein Zugang besteht, wurde eine E-Mail versendet.'
}
_UNGUELTIGER_LINK = 'Dieser Link ist ungültig oder abgelaufen.'


class MagicLinkAnfordernView(APIView):
    """``POST /api/v1/portal/auth/magic-link/request/``"""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'portal_auth'

    def post(self, request):
        serializer = MagicLinkAnfrageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']

        # Rate-Limit VOR der Zugangssuche — sonst wäre am unterschiedlichen
        # Verhalten ablesbar, welche Adressen existieren.
        try:
            zugang_service.pruefe_rate_limit(email)
        except RateLimitErreicht:
            return Response(_NEUTRALE_ANTWORT, status=status.HTTP_200_OK)

        zugang = zugang_service.finde_zugang_per_email(email)
        if zugang is not None:
            token = zugang_service.erzeuge_magic_link(zugang)
            try:
                mail_service.versende_magic_link(token, email)
            except Exception:
                # Auch ein Versandfehler darf die Antwort nicht verändern —
                # sonst wäre sie wieder ein Existenz-Orakel. Der Fehler
                # gehört ins Log, nicht in die Antwort.
                logger.exception('Portal: Magic-Link-Versand fehlgeschlagen.')

        return Response(_NEUTRALE_ANTWORT, status=status.HTTP_200_OK)


class MagicLinkEinloesenView(APIView):
    """``POST /api/v1/portal/auth/magic-link/verify/``

    Nimmt Magic-Link- UND Einladungs-Token an (Spec Kap. 3.1: der
    Einladungsklick loggt direkt ein).
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'portal_auth'

    def post(self, request):
        serializer = TokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            session, _tok, erstanmeldung = zugang_service.melde_an(
                serializer.validated_data['token']
            )
        except (TokenUngueltig, ZugangGesperrt):
            return Response(
                {'detail': _UNGUELTIGER_LINK}, status=status.HTTP_401_UNAUTHORIZED
            )

        return Response({
            'token': session.token,
            'gueltig_bis': session.gueltig_bis,
            'gueltig_stunden': SESSION_GUELTIG_STUNDEN,
            'erstanmeldung': erstanmeldung,
            'name': session.zugang.person.name,
        })


class AbmeldenView(APIView):
    """``POST /api/v1/portal/auth/logout/`` — beendet die Sitzung sofort."""

    authentication_classes = [PortalSessionAuthentication]
    permission_classes = [IstPortalNutzer]

    def post(self, request):
        zugang_service.melde_ab(request.portal_session)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeineEinheitenView(APIView):
    """``GET /api/v1/portal/meine-einheiten/``"""

    authentication_classes = [PortalSessionAuthentication]
    permission_classes = [IstPortalNutzer]

    def get(self, request):
        karten = einheiten_service.meine_einheiten(request.portal_zugang.person)
        return Response(WegKarteSerializer(karten, many=True).data)


def _meine_daten_dict(zugang) -> dict:
    person = zugang.person
    mandat = stammdaten_service.aktives_mandat(person)
    return {
        'person_id': person.id,
        'personennummer': person.personennummer,
        'name': person.name,
        'anrede': person.anrede,
        'strasse': person.strasse or '',
        'hausnummer': person.hausnummer or '',
        'plz': person.plz or '',
        'ort': person.ort or '',
        'telefon': stammdaten_service.erste_telefonnummer(person),
        'email': zugang_service.person_email(person),
        'email_pending': zugang.email_pending or '',
        'iban': stammdaten_service.erste_iban(person),
        'bic': mandat.bic if mandat else '',
        'hat_aktives_mandat': mandat is not None,
        'mandatsreferenz': mandat.mandatsreferenz if mandat else None,
    }


class MeineDatenView(APIView):
    """``GET`` / ``PATCH /api/v1/portal/meine-daten/``"""

    authentication_classes = [PortalSessionAuthentication]
    permission_classes = [IstPortalNutzer]

    def get(self, request):
        return Response(MeineDatenSerializer(_meine_daten_dict(request.portal_zugang)).data)

    def patch(self, request):
        serializer = KontaktAenderungSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        stammdaten_service.aktualisiere_kontakt(
            request.portal_zugang, serializer.validated_data
        )
        request.portal_zugang.refresh_from_db()
        return Response(MeineDatenSerializer(_meine_daten_dict(request.portal_zugang)).data)


class BankverbindungView(APIView):
    """``PATCH /api/v1/portal/meine-daten/bankverbindung/``"""

    authentication_classes = [PortalSessionAuthentication]
    permission_classes = [IstPortalNutzer]

    def patch(self, request):
        serializer = BankverbindungSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            ergebnis = stammdaten_service.aktualisiere_bankverbindung(
                request.portal_zugang, serializer.validated_data
            )
        except StammdatenFehler as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        request.portal_zugang.refresh_from_db()
        antwort = MeineDatenSerializer(_meine_daten_dict(request.portal_zugang)).data
        antwort.update(ergebnis)
        return Response(antwort)


class IbanPruefenView(APIView):
    """``GET /api/v1/portal/iban-check/?iban=…`` — Prüfung während der Eingabe.

    Eigener Endpunkt statt des internen ``/iban-check/``: der verlangt ein
    Mitarbeiter-JWT, das ein Eigentümer nicht hat. Inhaltlich identisch
    (``schwifty``), aber hinter der Portal-Sitzung — so kann er nicht
    anonym als IBAN-Orakel benutzt werden.

    Rein lesend und ohne Nebenwirkung; die verbindliche Prüfung findet
    beim Speichern erneut statt (``BankverbindungSerializer``).
    """

    authentication_classes = [PortalSessionAuthentication]
    permission_classes = [IstPortalNutzer]

    def get(self, request):
        roh = (request.query_params.get('iban') or '').replace(' ', '').upper()
        if not roh:
            return Response({'valid': False, 'error': 'Keine IBAN angegeben'})

        try:
            from schwifty import IBAN
            iban = IBAN(roh)
        except ImportError:
            # Ohne die optionale Abhängigkeit keine Aussage vortäuschen.
            return Response({'valid': True, 'iban': roh, 'bic': '', 'bank_name': ''})
        except Exception:
            # Bewusst ohne die Original-Fehlermeldung: die ist englisch und
            # technisch, im Portal steht ein Eigentümer davor.
            return Response({'valid': False, 'error': 'Diese IBAN ist ungültig.'})

        bic = ''
        bank_name = ''
        try:
            bic_obj = iban.bic
            if bic_obj:
                bic = str(bic_obj)
                bank_name = getattr(bic_obj, 'bank_name', '') or ''
        except Exception:
            pass

        return Response({
            'valid': True, 'iban': str(iban), 'bic': bic, 'bank_name': bank_name,
        })


class EmailAendernView(APIView):
    """``POST /api/v1/portal/meine-daten/email/`` — stößt die Änderung an."""

    authentication_classes = [PortalSessionAuthentication]
    permission_classes = [IstPortalNutzer]

    def post(self, request):
        serializer = EmailAenderungSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        neue_email = serializer.validated_data['email']

        try:
            token = stammdaten_service.stosse_email_aenderung_an(
                request.portal_zugang, neue_email
            )
        except StammdatenFehler as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            mail_service.versende_email_bestaetigung(token)
        except mail_service.VersandNichtKonfiguriert as exc:
            return Response(
                {'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        return Response({
            'detail': f'Bestätigungslink an {neue_email} versendet. '
                      f'Bis zur Bestätigung bleibt Ihre bisherige Adresse gültig.',
            'email_pending': neue_email,
        })


class EmailBestaetigenView(APIView):
    """``POST /api/v1/portal/meine-daten/email/bestaetigen/``

    Anonym erreichbar: der Bestätigungslink wird typischerweise im neuen
    Postfach geöffnet, oft in einem anderen Browser ohne Portal-Sitzung.
    Der Token selbst ist das Geheimnis.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'portal_auth'

    def post(self, request):
        serializer = TokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            person = stammdaten_service.bestaetige_email(
                serializer.validated_data['token']
            )
        except (TokenUngueltig, ZugangGesperrt, StammdatenFehler):
            return Response(
                {'detail': _UNGUELTIGER_LINK}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response({
            'detail': 'Ihre neue E-Mail-Adresse ist jetzt aktiv.',
            'email': zugang_service.person_email(person),
        })
