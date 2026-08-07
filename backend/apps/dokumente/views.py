import mimetypes

from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.http import FileResponse
from .models import Dokument
from .serializers import DokumentSerializer
from .services.beleg_service import dokument_pfad


class DokumentViewSet(viewsets.ModelViewSet):
    serializer_class = DokumentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['dateiname', 'beschreibung', 'kategorie']
    ordering_fields = ['hochgeladen_am', 'dateiname', 'kategorie']
    ordering = ['-hochgeladen_am']

    def get_queryset(self):
        qs = Dokument.objects.select_related('objekt', 'einheit', 'hochgeladen_von')
        objekt_id = self.request.query_params.get('objekt')
        einheit_id = self.request.query_params.get('einheit')
        kategorie = self.request.query_params.get('kategorie')
        typ = self.request.query_params.get('typ')
        if objekt_id:
            qs = qs.filter(objekt_id=objekt_id)
        if einheit_id:
            qs = qs.filter(einheit_id=einheit_id)
        if kategorie:
            qs = qs.filter(kategorie=kategorie)
        if typ:
            qs = qs.filter(verknuepfung_typ=typ)
        return qs

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.revisionssicher:
            return Response(
                {'error': 'Revisionssicheres Dokument darf nicht gelöscht werden (GoBD).'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['get'], url_path='datei')
    def datei(self, request, pk=None):
        """Liefert die Dokumentdatei über die zentrale Pfadauflösung (beleg_service.dokument_pfad)."""
        dokument = self.get_object()
        pfad = dokument_pfad(dokument)
        if not pfad.exists():
            return Response({'error': 'Datei nicht gefunden'}, status=status.HTTP_404_NOT_FOUND)
        content_type, _ = mimetypes.guess_type(str(pfad))
        return FileResponse(open(pfad, 'rb'), content_type=content_type or 'application/octet-stream')
