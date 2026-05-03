from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from .models import Dokument
from .serializers import DokumentSerializer


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
