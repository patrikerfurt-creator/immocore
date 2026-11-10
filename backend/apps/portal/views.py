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
    SepaMandatAnfordernSerializer,
    SepaMandatBestaetigenSerializer,
    TokenSerializer,
    WegKarteSerializer,
)
from .services import (
    einheiten_service,
    iban_service,
    mail_service,
    sepa_mandat_service,
    stammdaten_service,
    zugang_service,
)
from .services.request_info import client_ip
from .services.sepa_mandat_service import SepaMandatFehler
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
                # Zustellung an den Bevollmächtigten, falls einer hinterlegt ist —
                # nicht zwingend an die eingegebene Adresse.
                mail_service.versende_magic_link(
                    token, zugang_service.zustell_email(zugang.person)
                )
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
        return Response(iban_service.pruefe_iban(request.query_params.get('iban') or ''))


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


class SepaMandatStatusView(APIView):
    """``GET /api/v1/portal/sepa-mandat/`` — Geltungsbereiche, Aktion, offene Anfrage."""

    authentication_classes = [PortalSessionAuthentication]
    permission_classes = [IstPortalNutzer]

    def get(self, request):
        return Response(sepa_mandat_service.status_fuer_zugang(request.portal_zugang))


class SepaMandatAnfordernView(APIView):
    """``POST /api/v1/portal/sepa-mandat/anfordern/`` — stößt die Mandatserteilung
    bzw. -änderung an. Es wird KEIN Mandat geschrieben, nur der Bestätigungslink
    an die eigene E-Mail-Adresse versendet."""

    authentication_classes = [PortalSessionAuthentication]
    permission_classes = [IstPortalNutzer]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'portal_sepa_mandat'

    def post(self, request):
        serializer = SepaMandatAnfordernSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        daten = serializer.validated_data

        ip, _forwarded = client_ip(request)
        try:
            antrag = sepa_mandat_service.stosse_mandat_an(
                request.portal_zugang,
                daten['schluessel'], daten['iban'], daten['bic'],
                ip=ip,
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                session_id=request.portal_session.id,
            )
        except SepaMandatFehler as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except mail_service.VersandNichtKonfiguriert as exc:
            return Response(
                {'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except Exception:
            # Antrag und Token sind zurückgerollt; der Eigentümer kann es erneut versuchen.
            logger.exception('Portal: SEPA-Mandat-Link konnte nicht versendet werden.')
            return Response(
                {'detail': 'Die E-Mail konnte nicht versendet werden. '
                           'Bitte versuchen Sie es später erneut.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        maskiert = sepa_mandat_service.maskiere_email(antrag.empfaenger_email)
        return Response({
            'detail': f'Wir haben Ihnen eine E-Mail an {maskiert} gesendet. '
                      f'Bitte bestätigen Sie das Mandat über den Link.',
            'empfaenger_email_maskiert': maskiert,
            'gueltig_bis': antrag.token.gueltig_bis,
        })


class SepaMandatVorschauView(APIView):
    """``GET /api/v1/portal/sepa-mandat/bestaetigen/<token>/`` — Mandatstext zur
    Bestätigungsseite. Verbraucht den Token NICHT (Mail-Scanner rufen Links ab)."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'portal_auth'

    def get(self, request, token):
        try:
            return Response(sepa_mandat_service.vorschau(token))
        except (TokenUngueltig, ZugangGesperrt):
            return Response(
                {'detail': _UNGUELTIGER_LINK}, status=status.HTTP_400_BAD_REQUEST
            )


class SepaMandatBestaetigenView(APIView):
    """``POST /api/v1/portal/sepa-mandat/bestaetigen/`` — Body ``token`` und
    ``kontoinhaber_erklaerung``. Wirksam wird das Mandat erst mit diesem POST."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'portal_auth'

    def post(self, request):
        serializer = SepaMandatBestaetigenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        daten = serializer.validated_data

        ip, forwarded_roh = client_ip(request)
        try:
            mandat = sepa_mandat_service.bestaetige_mandat(
                daten['token'],
                ip=ip,
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                forwarded_roh=forwarded_roh,
                kontoinhaber_erklaerung=daten['kontoinhaber_erklaerung'],
            )
        except SepaMandatFehler as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except (TokenUngueltig, ZugangGesperrt):
            return Response(
                {'detail': _UNGUELTIGER_LINK}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response(sepa_mandat_service.bestaetigungs_antwort(mandat))
