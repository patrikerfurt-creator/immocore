import mimetypes

from django.db.models import ProtectedError
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.http import FileResponse
from .models import Dokument
from .serializers import DokumentSerializer
from .services.beleg_service import dokument_pfad, loeschsperre_grund


class DokumentViewSet(viewsets.ModelViewSet):
    serializer_class = DokumentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['dateiname', 'beschreibung', 'kategorie']
    ordering_fields = [
        'hochgeladen_am', 'dateiname', 'kategorie',
        'rechnung__rechnungsdatum', 'rechnung__betrag_brutto',
    ]
    ordering = ['-hochgeladen_am']

    def get_queryset(self):
        # select_related('rechnung', 'rechnung__kreditor') vermeidet N+1-Queries für die
        # Rechnungsanreicherung im DokumentSerializer (Belegübersicht-Anreicherung v1.0).
        qs = Dokument.objects.select_related(
            'objekt', 'einheit', 'hochgeladen_von', 'rechnung', 'rechnung__kreditor',
        )
        objekt_id = self.request.query_params.get('objekt')
        einheit_id = self.request.query_params.get('einheit')
        kategorie = self.request.query_params.get('kategorie')
        if objekt_id:
            # fuer_objekt() akzeptiert auch eine reine PK (Django löst FK-Vergleiche
            # gegen einen Roh-Wert genauso auf wie gegen eine Modell-Instanz).
            qs = qs.fuer_objekt(objekt_id)
        if einheit_id:
            qs = qs.fuer_einheit(einheit_id)
        if kategorie:
            qs = qs.filter(kategorie=kategorie)
        return qs

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.revisionssicher:
            return Response(
                {'error': 'Revisionssicheres Dokument darf nicht gelöscht werden (GoBD).'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # loeschsperre_grund() bewertet ab hier nur noch die Rechnungs-Verknüpfung
        # (revisionssicher wurde oben bereits ausgeschlossen) — einzige Entscheidungs-
        # quelle, dieselbe wie im DokumentSerializer (Nachtrag v1.1).
        grund = loeschsperre_grund(instance)
        if grund is not None:
            return Response({'error': grund}, status=status.HTTP_400_BAD_REQUEST)
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            # Sicherheitsnetz für Referenzen, die oben nicht explizit geprüft werden.
            return Response(
                {'error': 'Dokument kann nicht gelöscht werden: es wird an anderer Stelle referenziert.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=['get'], url_path='datei')
    def datei(self, request, pk=None):
        """Liefert die Dokumentdatei über die zentrale Pfadauflösung (beleg_service.dokument_pfad)."""
        dokument = self.get_object()
        pfad = dokument_pfad(dokument)
        if not pfad.exists():
            return Response({'error': 'Datei nicht gefunden'}, status=status.HTTP_404_NOT_FOUND)
        content_type, _ = mimetypes.guess_type(str(pfad))
        return FileResponse(open(pfad, 'rb'), content_type=content_type or 'application/octet-stream')
