"""
Interne API-Views für Handwerkerauftrag / Gewerk / ObjektHandwerker (Phase C).

KEINE Business-Logik hier — jede Mutation delegiert an ``auftrag_service``.
Ungültige Übergänge/Eingaben werden als ``django.core.exceptions.ValidationError``
von den Services geworfen und hier zu HTTP 400 übersetzt (Muster:
``apps.vorgaenge.views``).

Die öffentlichen (nicht angemeldeten) Endpunkte liegen bewusst in einem
eigenen Modul, ``views_oeffentlich.py`` — andere Auth-/Throttle-/CSRF-Regeln,
klare Trennung.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from apps.rechnungen.models import Rechnung

from .models import Gewerk, Handwerkerauftrag, ObjektHandwerker
from .serializers import (
    GewerkSerializer,
    HandwerkerauftragCreateSerializer,
    HandwerkerauftragDetailSerializer,
    HandwerkerauftragListSerializer,
    ObjektHandwerkerSerializer,
)
from .services import auftrag_service

_ERLAUBTE_ORDERING = {
    '-erstellt_am', 'erstellt_am',
    'angenommen_am', '-angenommen_am',
    'abgelehnt_am', '-abgelehnt_am',
    'nummer', '-nummer',
}


def _validation_error_response(exc: DjangoValidationError) -> Response:
    nachricht = '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)
    return Response({'detail': nachricht}, status=status.HTTP_400_BAD_REQUEST)


class HandwerkerauftragPagination(PageNumberPagination):
    """Pagination NUR am Handwerkerauftrags-Dashboard (Orchestrator-Vorgabe) —
    global bleibt ``DEFAULT_PAGINATION_CLASS`` unangetastet."""
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


class HandwerkerauftragViewSet(mixins.ListModelMixin,
                                mixins.RetrieveModelMixin,
                                mixins.CreateModelMixin,
                                viewsets.GenericViewSet):
    """``/api/v1/handwerkerauftraege/`` — Dashboard-Liste, Detail, Anlage
    (auch ohne Vorgang — dann ist ``objekt`` Pflicht, siehe
    ``auftrag_service.erstelle_auftrag``) plus Aktionen für Statuswechsel,
    Kommentar, erneuten Versand und Rechnungszuordnung.

    Bewusst KEIN ``ModelViewSet``: jede Mutation läuft über eine der
    Service-Aktionen unten, kein direktes Update/Delete auf dem Modell.
    """
    permission_classes = [IsAuthenticated]
    pagination_class = HandwerkerauftragPagination

    def get_queryset(self):
        qs = Handwerkerauftrag.objects.select_related(
            'objekt', 'kreditor', 'vorgang', 'token',
        ).prefetch_related(
            'kreditor__gewerke', 'ereignisse', 'ereignisse__erstellt_von', 'rechnungen',
        )

        params = self.request.query_params

        status_param = params.get('status')
        if status_param:
            werte = [s.strip() for s in status_param.split(',') if s.strip()]
            if werte:
                qs = qs.filter(status__in=werte)

        for feld in ('objekt', 'kreditor'):
            wert = params.get(feld)
            if wert:
                qs = qs.filter(**{feld: wert})

        prioritaet = params.get('prioritaet')
        if prioritaet:
            qs = qs.filter(prioritaet=prioritaet)

        search = params.get('search')
        if search:
            qs = qs.filter(
                Q(titel__icontains=search)
                | Q(beschreibung__icontains=search)
                | Q(nummer__icontains=search)
            )

        ordering = params.get('ordering') or '-erstellt_am'
        if ordering not in _ERLAUBTE_ORDERING:
            ordering = '-erstellt_am'
        return qs.order_by(ordering)

    def get_serializer_class(self):
        if self.action == 'list':
            return HandwerkerauftragListSerializer
        if self.action == 'create':
            return HandwerkerauftragCreateSerializer
        return HandwerkerauftragDetailSerializer

    def create(self, request, *args, **kwargs):
        eingabe = HandwerkerauftragCreateSerializer(data=request.data)
        eingabe.is_valid(raise_exception=True)
        daten = eingabe.validated_data
        try:
            auftrag = auftrag_service.erstelle_auftrag(erstellt_von=request.user, **daten)
        except DjangoValidationError as exc:
            return _validation_error_response(exc)
        return Response(
            HandwerkerauftragDetailSerializer(auftrag).data, status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'], url_path='status')
    def status_wechsel(self, request, pk=None):
        auftrag = self.get_object()
        neuer_status = request.data.get('status')
        if not neuer_status:
            return Response({'detail': "'status' ist erforderlich."}, status=status.HTTP_400_BAD_REQUEST)
        kommentar = request.data.get('kommentar') or None
        if neuer_status == 'abgeschlossen':
            abschluss_notiz = request.data.get('abschluss_notiz')
            if abschluss_notiz is not None:
                # In-Memory gesetzt, NICHT separat gespeichert — wechsle_status()
                # ruft full_clean()+save() auf demselben Objekt auf und
                # persistiert damit Status und Notiz gemeinsam.
                auftrag.abschluss_notiz = abschluss_notiz
        try:
            auftrag_service.wechsle_status(auftrag, neuer_status, erstellt_von=request.user, kommentar=kommentar)
        except DjangoValidationError as exc:
            return _validation_error_response(exc)
        return Response(HandwerkerauftragDetailSerializer(auftrag).data)

    @action(detail=True, methods=['post'], url_path='kommentar')
    def kommentar(self, request, pk=None):
        auftrag = self.get_object()
        text = request.data.get('text', '')
        try:
            auftrag_service.kommentiere(auftrag, text, request.user)
        except DjangoValidationError as exc:
            return _validation_error_response(exc)
        return Response(HandwerkerauftragDetailSerializer(auftrag).data)

    @action(detail=True, methods=['post'], url_path='erneut-versenden')
    def erneut_versenden(self, request, pk=None):
        auftrag = self.get_object()
        try:
            auftrag_service.versende_erneut(auftrag, request.user)
        except DjangoValidationError as exc:
            return _validation_error_response(exc)
        return Response(HandwerkerauftragDetailSerializer(auftrag).data)

    @action(detail=True, methods=['post'], url_path='rechnung-zuordnen')
    def rechnung_zuordnen(self, request, pk=None):
        auftrag = self.get_object()
        rechnung_id = request.data.get('rechnung')
        if not rechnung_id:
            return Response({'detail': "'rechnung' ist erforderlich."}, status=status.HTTP_400_BAD_REQUEST)
        rechnung = get_object_or_404(Rechnung, pk=rechnung_id)
        try:
            auftrag_service.ordne_rechnung_zu(auftrag, rechnung, request.user)
        except DjangoValidationError as exc:
            return _validation_error_response(exc)
        return Response(HandwerkerauftragDetailSerializer(auftrag).data)

    @action(detail=True, methods=['post'], url_path='rechnung-loesen')
    def rechnung_loesen(self, request, pk=None):
        auftrag = self.get_object()
        rechnung_id = request.data.get('rechnung')
        if not rechnung_id:
            return Response({'detail': "'rechnung' ist erforderlich."}, status=status.HTTP_400_BAD_REQUEST)
        rechnung = get_object_or_404(Rechnung, pk=rechnung_id)
        try:
            auftrag_service.loese_rechnung_zuordnung(rechnung, request.user)
        except DjangoValidationError as exc:
            return _validation_error_response(exc)
        auftrag.refresh_from_db()
        return Response(HandwerkerauftragDetailSerializer(auftrag).data)


class GewerkViewSet(viewsets.ReadOnlyModelViewSet):
    """``/api/v1/gewerke/`` — nur aktive Gewerke, für Dropdowns."""
    serializer_class = GewerkSerializer
    permission_classes = [IsAuthenticated]
    queryset = Gewerk.objects.filter(aktiv=True).order_by('sortierung', 'bezeichnung')


class GewerkAdminViewSet(viewsets.ModelViewSet):
    """``/api/v1/gewerke/admin/`` — Stammdaten-Pflege, nur Admin
    (``is_staff``) — Muster: ``apps.vorgaenge.views.VorgangTypAdminViewSet``."""
    serializer_class = GewerkSerializer
    permission_classes = [IsAdminUser]
    queryset = Gewerk.objects.all().order_by('sortierung', 'bezeichnung')

    def perform_create(self, serializer):
        serializer.save(erstellt_von=self.request.user)


class ObjektHandwerkerViewSet(viewsets.ModelViewSet):
    """``/api/v1/objekt-handwerker/`` — Handwerkerzuordnung am Objekt
    (Zuordnungs-UI im Frontend), filterbar nach ``objekt``."""
    serializer_class = ObjektHandwerkerSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = ObjektHandwerker.objects.select_related('objekt', 'kreditor').prefetch_related('kreditor__gewerke')
        objekt_id = self.request.query_params.get('objekt')
        if objekt_id:
            qs = qs.filter(objekt_id=objekt_id)
        return qs
