"""
Vorgänge im Eigentümer-Portal (Spec Portal-Erweiterung v1.1, Kap. 4 und 5).

``apps.portal`` ist hier ausschließlich Auth- und Scoping-Gatekeeper: die
Fachlogik (Anlage, Sichtbarkeitsregel, Prüfung der aktiven Einheit) bleibt in
``apps.vorgaenge.services.vorgang_service`` — sonst gäbe es zwei Wahrheiten
darüber, was ein Eigentümer sehen und auslösen darf.

Ein 404 statt 403 bei fehlendem Zugriff auf ein fremdes/nicht freigegebenes
``Vorgang`` (statt eines expliziten Berechtigungsfehlers): ein 403 würde die
Existenz des Datensatzes bestätigen — genau das soll ein Eigentümer über
einen fremden Vorgang nicht erfahren können.
"""
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.vorgaenge.models import VorgangTyp
from apps.vorgaenge.services import vorgang_service

from .auth import IstPortalNutzer, PortalSessionAuthentication
from .serializers_vorgaenge import (
    PortalVorgangCreateSerializer,
    PortalVorgangDetailSerializer,
    PortalVorgangListSerializer,
    PortalVorgangTypSerializer,
)


class PortalVorgangTypenView(APIView):
    """``GET /api/v1/portal/vorgang-typen/`` — im Portal auslösbare Typen."""

    authentication_classes = [PortalSessionAuthentication]
    permission_classes = [IstPortalNutzer]

    def get(self, request):
        typen = (
            VorgangTyp.objects
            .filter(portal_erstellbar=True, aktiv=True)
            .order_by('sortierung', 'bezeichnung')
        )
        return Response(PortalVorgangTypSerializer(typen, many=True).data)


class PortalVorgaengeView(APIView):
    """``GET|POST /api/v1/portal/vorgaenge/``

    GET liefert eine reine Liste (keine Pagination, wie alle anderen
    Portal-Listen) der für die anfragende Person sichtbaren Vorgänge. POST
    legt einen neuen Vorgang mit ``quelle='portal'`` an.

    Throttle nur für POST (Missbrauch beim Anlegen begrenzen) — GET auf
    derselben View bliebe sonst ebenfalls gedrosselt, obwohl reines Lesen
    kein Missbrauchspotenzial hat.
    """

    authentication_classes = [PortalSessionAuthentication]
    permission_classes = [IstPortalNutzer]

    def get_throttles(self):
        if self.request.method == 'POST':
            self.throttle_scope = 'portal_vorgang_erstellen'
            return [ScopedRateThrottle()]
        return []

    def get(self, request):
        person = request.portal_zugang.person
        vorgaenge = vorgang_service.portal_sichtbare_vorgaenge(person)
        return Response(PortalVorgangListSerializer(vorgaenge, many=True).data)

    def post(self, request):
        person = request.portal_zugang.person

        eingabe = PortalVorgangCreateSerializer(data=request.data)
        eingabe.is_valid(raise_exception=True)
        daten = eingabe.validated_data

        typ = (
            VorgangTyp.objects
            .filter(id=daten['typ_id'], aktiv=True, portal_erstellbar=True)
            .first()
        )
        if typ is None:
            return Response(
                {'detail': 'Dieser Vorgangs-Typ steht im Portal nicht zur Verfügung.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        einheit = vorgang_service.portal_aktive_einheit(person, daten['einheit_id'])
        if einheit is None:
            return Response(
                {'detail': 'Diese Einheit gehört nicht zu einem aktuellen Eigentumsverhältnis dieser Person.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        vorgang = vorgang_service.erstelle_vorgang(
            typ=typ,
            betreff=daten['betreff'],
            beschreibung=daten.get('beschreibung'),
            erstellt_von=vorgang_service.portal_system_user(),
            quelle='portal',
            objekt=einheit.objekt,
            einheit=einheit,
            person=person,
            portal_sichtbar=True,
        )
        return Response(
            PortalVorgangDetailSerializer(vorgang).data,
            status=status.HTTP_201_CREATED,
        )


class PortalVorgangDetailView(APIView):
    """``GET /api/v1/portal/vorgaenge/<id>/``"""

    authentication_classes = [PortalSessionAuthentication]
    permission_classes = [IstPortalNutzer]

    def get(self, request, vorgang_id):
        person = request.portal_zugang.person
        vorgaenge = vorgang_service.portal_sichtbare_vorgaenge(person)
        vorgang = get_object_or_404(vorgaenge, pk=vorgang_id)
        return Response(PortalVorgangDetailSerializer(vorgang).data)
