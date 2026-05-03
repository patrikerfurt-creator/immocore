from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Ticket
from .serializers import TicketSerializer, TicketListSerializer

STATUS_UEBERGAENGE = {
    'offen': ['in_bearbeitung', 'geschlossen'],
    'in_bearbeitung': ['erledigt', 'offen', 'geschlossen'],
    'erledigt': ['geschlossen', 'in_bearbeitung'],
    'geschlossen': [],
}


class TicketViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['titel', 'beschreibung']
    ordering_fields = ['erstellt_am', 'prioritaet', 'status']
    ordering = ['-erstellt_am']

    def get_queryset(self):
        qs = Ticket.objects.select_related('objekt', 'einheit', 'zuweisung', 'erstellt_von')
        objekt_id = self.request.query_params.get('objekt')
        status_filter = self.request.query_params.get('status')
        prioritaet = self.request.query_params.get('prioritaet')
        typ = self.request.query_params.get('typ')
        zuweisung = self.request.query_params.get('zuweisung')
        if objekt_id:
            qs = qs.filter(objekt_id=objekt_id)
        if status_filter:
            qs = qs.filter(status=status_filter)
        if prioritaet:
            qs = qs.filter(prioritaet=prioritaet)
        if typ:
            qs = qs.filter(ticket_typ=typ)
        if zuweisung:
            qs = qs.filter(zuweisung_id=zuweisung)
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return TicketListSerializer
        return TicketSerializer

    @action(detail=True, methods=['post'], url_path='status-wechsel')
    def status_wechsel(self, request, pk=None):
        """Status-Übergang durchführen."""
        ticket = self.get_object()
        neuer_status = request.data.get('status')

        if not neuer_status:
            return Response(
                {'error': 'status erforderlich'},
                status=status.HTTP_400_BAD_REQUEST
            )

        erlaubt = STATUS_UEBERGAENGE.get(ticket.status, [])
        if neuer_status not in erlaubt:
            return Response(
                {
                    'error': f'Übergang von "{ticket.status}" nach "{neuer_status}" nicht erlaubt',
                    'erlaubte_uebergaenge': erlaubt,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        ticket.status = neuer_status
        ticket.save(update_fields=['status'])
        return Response(TicketSerializer(ticket, context={'request': request}).data)

    @action(detail=True, methods=['post'], url_path='zuweisen')
    def zuweisen(self, request, pk=None):
        """Ticket einem Benutzer zuweisen."""
        ticket = self.get_object()
        benutzer_id = request.data.get('benutzer')

        if benutzer_id is None:
            # Zuweisung aufheben
            ticket.zuweisung = None
        else:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                ticket.zuweisung = User.objects.get(pk=benutzer_id)
            except User.DoesNotExist:
                return Response(
                    {'error': 'Benutzer nicht gefunden'},
                    status=status.HTTP_404_NOT_FOUND
                )

        ticket.save(update_fields=['zuweisung'])
        return Response(TicketSerializer(ticket, context={'request': request}).data)
