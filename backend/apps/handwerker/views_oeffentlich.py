"""
Öffentliche (nicht angemeldete) API-Views für die Auftragsbestätigung per
Token (Phase C — die ERSTEN öffentlichen Endpunkte des Projekts).

Sicherheitsregeln (Orchestrator-Vorgabe Schritt 4, verbindlich):

- ``GET`` ist STRENG NEBENWIRKUNGSFREI — Mail-Scanner, Outlook SafeLinks und
  Linkvorschauen rufen GET-Links automatisch ab. Ein GET, das den Status
  ändert, würde Aufträge ohne Zutun des Handwerkers annehmen. ``GET`` liest
  hier ausschließlich, es mutiert nichts.
- ``authentication_classes = []`` EXPLIZIT auf beiden Views (nicht nur
  ``permission_classes = [AllowAny]``): bliebe DRFs ``SessionAuthentication``
  in der Kette, würde sie für unsichere Methoden CSRF erzwingen — ein
  anonymer POST würde für jeden mit noch gültigem Session-Cookie sporadisch
  mit „403 CSRF Failed" scheitern. Der Token selbst ist das Geheimnis, ein
  CSRF-Risiko entsteht dadurch nicht.
- ``ScopedRateThrottle`` mit ``throttle_scope = 'auftrag_token'`` auf beiden
  Views (Rate in ``settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']``).
- Fehler-Mapping: unbekannter Token → 404 (generische Meldung — keine
  Auskunft, ob der Token existiert), abgelaufen → 410, bereits verwendet →
  409 (mit aktuellem Status), ungültiger Statusübergang → 409.
- Niemals den jeweils anderen Token (accept/reject) mitliefern, immer die
  Auftragsnummer statt der UUID.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import AuftragsbestaetigungsToken
from .services import auftrag_service
from .services.auftrag_service import TokenAbgelaufen, TokenVerbraucht

_GENERISCHE_TOKEN_MELDUNG = 'Dieser Link ist ungültig.'


def _token_oder_404(token: str):
    """Lädt den Token unabhängig davon, ob er als Accept- oder Reject-Token
    hinterlegt ist. Gibt ``None`` zurück, wenn kein Token existiert."""
    return (
        AuftragsbestaetigungsToken.objects
        .select_related('auftrag', 'auftrag__objekt', 'auftrag__kreditor')
        .filter(Q(accept_token=token) | Q(reject_token=token))
        .first()
    )


def _aktion_fuer(tok: AuftragsbestaetigungsToken, token: str) -> str:
    return 'annehmen' if tok.accept_token == token else 'ablehnen'


class OeffentlicherAuftragDetailView(APIView):
    """``GET /api/v1/oeffentlich/auftrag/<token>/`` — Daten für die
    Bestätigungsseite. NEBENWIRKUNGSFREI (siehe Modul-Docstring)."""
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auftrag_token'

    def get(self, request, token):
        tok = _token_oder_404(token)
        if tok is None:
            return Response({'detail': _GENERISCHE_TOKEN_MELDUNG}, status=status.HTTP_404_NOT_FOUND)

        auftrag = tok.auftrag
        objekt = auftrag.objekt
        abgelaufen = tok.verbraucht_am is None and timezone.now() >= tok.gueltig_bis

        return Response({
            'nummer': auftrag.nummer,
            'objekt_bezeichnung': objekt.bezeichnung,
            'objekt_adresse': f"{objekt.strasse}, {objekt.plz} {objekt.ort}",
            'titel': auftrag.titel,
            'beschreibung': auftrag.beschreibung,
            'prioritaet': auftrag.prioritaet,
            'gewuenscht_ab': auftrag.gewuenscht_ab,
            'geschaetzte_kosten': auftrag.geschaetzte_kosten,
            'kreditor_name': auftrag.kreditor.name,
            'gueltig_bis': tok.gueltig_bis,
            'aktion': _aktion_fuer(tok, token),
            'status': auftrag.status,
            'bereits_verwendet': tok.verbraucht_am is not None,
            'abgelaufen': abgelaufen,
        })


class OeffentlicherAuftragBestaetigenView(APIView):
    """``POST /api/v1/oeffentlich/auftrag/<token>/bestaetigen/`` — führt die
    Aktion aus (Annahme bzw. Ablehnung). Body optional ``{grund}`` (nur für
    die Ablehnung relevant)."""
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auftrag_token'

    def post(self, request, token):
        tok = _token_oder_404(token)
        if tok is None:
            return Response({'detail': _GENERISCHE_TOKEN_MELDUNG}, status=status.HTTP_404_NOT_FOUND)

        aktion = _aktion_fuer(tok, token)
        grund = request.data.get('grund') or ''

        try:
            if aktion == 'annehmen':
                auftrag = auftrag_service.akzeptiere_via_token(token)
            else:
                auftrag = auftrag_service.lehne_ab_via_token(token, grund=grund)
        except TokenAbgelaufen as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_410_GONE)
        except TokenVerbraucht as exc:
            tok.auftrag.refresh_from_db()
            return Response(
                {'detail': str(exc), 'status': tok.auftrag.status},
                status=status.HTTP_409_CONFLICT,
            )
        except DjangoValidationError as exc:
            nachricht = '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)
            tok.auftrag.refresh_from_db()
            return Response(
                {'detail': nachricht, 'status': tok.auftrag.status},
                status=status.HTTP_409_CONFLICT,
            )

        return Response({'nummer': auftrag.nummer, 'status': auftrag.status, 'aktion': aktion})
