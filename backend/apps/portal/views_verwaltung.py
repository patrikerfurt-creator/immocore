"""
Interner Bereich: Portal-Zugänge verwalten (Spec 1a, Kap. 3.1).

Diese Endpunkte liegen bewusst NICHT unter ``/portal/`` — sie gehören zum
internen IMMOCORE-Backend und werden mit dem normalen Mitarbeiter-JWT
aufgerufen. Ein Portal-Token darf hier nichts erreichen: die Views nutzen
die DRF-Standard-Authentifizierung aus den Settings, in der
``PortalSessionAuthentication`` nicht enthalten ist.

Self-Service-Registrierung ist ausdrücklich nicht vorgesehen — ein
Portal-Zugang entsteht ausschließlich hier, durch die Verwaltung.
"""
import logging

from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.personen.models import Person
from .models import PortalSession, PortalZugang
from .serializers import PortalZugangVerwaltungSerializer
from .services import mail_service, zugang_service

logger = logging.getLogger(__name__)

# Person.person_typ '100' = Eigentümer. Nur Eigentümer bekommen einen
# Portal-Zugang (Spec Kap. 3.1) — Mieter und Kreditoren sind in dieser
# Ausbaustufe kein Portal-Publikum.
PERSON_TYP_EIGENTUEMER = '100'


class PortalZugangViewSet(viewsets.ReadOnlyModelViewSet):
    """``/api/v1/portal-verwaltung/zugaenge/``"""

    permission_classes = [IsAuthenticated]
    serializer_class = PortalZugangVerwaltungSerializer

    def get_queryset(self):
        qs = (
            PortalZugang.objects
            .select_related('person', 'eingeladen_von', 'eingeladen_von__user')
            .all()
        )
        person_id = self.request.query_params.get('person')
        if person_id:
            qs = qs.filter(person_id=person_id)
        return qs

    def _mitarbeiter(self):
        return getattr(self.request.user, 'mitarbeiter_profil', None)

    @action(detail=False, methods=['post'], url_path='einladen')
    def einladen(self, request):
        """Legt bei Bedarf den Zugang an und versendet die Einladung.

        Erneutes Aufrufen ist zulässig und der normale Weg, wenn eine
        Einladung abgelaufen oder in einem Postfach verschwunden ist —
        es entsteht ein frischer Link, kein zweiter Zugang.
        """
        person_id = request.data.get('person_id') or request.data.get('person')
        if not person_id:
            return Response(
                {'detail': 'person_id fehlt.'}, status=status.HTTP_400_BAD_REQUEST
            )

        person = get_object_or_404(Person, pk=person_id)
        if person.person_typ != PERSON_TYP_EIGENTUEMER:
            return Response(
                {'detail': 'Ein Portal-Zugang ist nur für Eigentümer vorgesehen.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        empfaenger = zugang_service.person_email(person)
        if not empfaenger:
            return Response(
                {'detail': 'Für diese Person ist keine E-Mail-Adresse hinterlegt.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        zugang, token = zugang_service.lade_ein(person, self._mitarbeiter())

        try:
            mail_service.versende_einladung(token, empfaenger)
        except mail_service.VersandNichtKonfiguriert as exc:
            # Der Zugang bleibt bestehen (die Einladung kann nach dem
            # Einrichten von SMTP erneut versendet werden), aber die
            # Verwaltung erfährt, dass nichts rausgegangen ist.
            return Response(
                {'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        zugang.refresh_from_db()
        daten = PortalZugangVerwaltungSerializer(zugang).data
        daten['detail'] = f'Einladung an {empfaenger} versendet.'
        return Response(daten, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='sperren')
    def sperren(self, request, pk=None):
        """Sperrt den Zugang und beendet laufende Sitzungen sofort."""
        zugang = self.get_object()
        zugang.aktiv = False
        zugang.save(update_fields=['aktiv', 'geaendert_am'])
        PortalSession.objects.filter(zugang=zugang).delete()
        return Response(PortalZugangVerwaltungSerializer(zugang).data)

    @action(detail=True, methods=['post'], url_path='entsperren')
    def entsperren(self, request, pk=None):
        zugang = self.get_object()
        zugang.aktiv = True
        zugang.save(update_fields=['aktiv', 'geaendert_am'])
        return Response(PortalZugangVerwaltungSerializer(zugang).data)
