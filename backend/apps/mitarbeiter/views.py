from rest_framework import viewsets, filters, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Mitarbeiter, MitarbeiterObjektZuordnung
from .serializers import (
    MitarbeiterSerializer, MitarbeiterListSerializer,
    ZuordnungListSerializer, ZuordnungCreateSerializer, ZuordnungPatchSerializer,
)


class MitarbeiterViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends    = [filters.SearchFilter, filters.OrderingFilter]
    search_fields      = ['user__first_name', 'user__last_name', 'user__email']
    ordering_fields    = ['user__last_name', 'abteilung', 'eingetreten_am', 'aktiv']
    ordering           = ['user__last_name', 'user__first_name']

    def get_queryset(self):
        qs = Mitarbeiter.objects.select_related('user')
        if abteilung := self.request.query_params.get('abteilung'):
            qs = qs.filter(abteilung=abteilung)
        if (aktiv := self.request.query_params.get('aktiv')) is not None:
            qs = qs.filter(aktiv=aktiv.lower() == 'true')
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return MitarbeiterListSerializer
        return MitarbeiterSerializer

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        user = instance.user
        instance.delete()
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MitarbeiterObjektZuordnungViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    http_method_names  = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        qs = MitarbeiterObjektZuordnung.objects.select_related(
            'mitarbeiter__user'
        )
        if objekt_id := self.request.query_params.get('objekt'):
            qs = qs.filter(objekt_id=objekt_id)
        if ma_id := self.request.query_params.get('mitarbeiter'):
            qs = qs.filter(mitarbeiter_id=ma_id)
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return ZuordnungListSerializer
        if self.action == 'partial_update':
            return ZuordnungPatchSerializer
        return ZuordnungCreateSerializer
