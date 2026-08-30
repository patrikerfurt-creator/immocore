"""
API für die menschliche Entscheidung über Kreditor-Dublettenverdacht.

Drei Aktionen je Prüffall: als neuen Kreditor anlegen, einem bestehenden
zuordnen, oder ablehnen. Alle drei sind ``POST`` und schreiben fest, wer
wann entschieden hat.
"""
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import KreditorDublettenPruefung
from .serializers_dubletten import KreditorDublettenPruefungSerializer
from .services import kreditor_dubletten
from .services.kreditor_dubletten import DublettenPruefungFehler


class KreditorDublettenPruefungViewSet(mixins.ListModelMixin,
                                       mixins.RetrieveModelMixin,
                                       viewsets.GenericViewSet):
    """``/api/v1/kreditor-dubletten/``

    Nur lesend plus die drei Entscheidungs-Aktionen — ein generisches
    PATCH gibt es bewusst nicht: der Status darf sich nur über die
    Aktionen ändern, damit Kreditor-Zuordnung, Rechnungsstatus und
    Audit-Felder nie auseinanderlaufen.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = KreditorDublettenPruefungSerializer

    def get_queryset(self):
        qs = (
            KreditorDublettenPruefung.objects
            .select_related('rechnung', 'ergebnis_kreditor', 'entschieden_von')
            .all()
        )
        # Default: nur offene Fälle — das ist die Arbeitsliste.
        gewuenschter_status = self.request.query_params.get('status', 'offen')
        if gewuenschter_status != 'alle':
            qs = qs.filter(status=gewuenschter_status)
        return qs

    def _pruefung(self):
        return get_object_or_404(KreditorDublettenPruefung, pk=self.kwargs['pk'])

    def _antwort(self, pruefung):
        pruefung.refresh_from_db()
        return Response(KreditorDublettenPruefungSerializer(pruefung).data)

    @action(detail=True, methods=['post'], url_path='als-neu-anlegen')
    def als_neu_anlegen(self, request, pk=None):
        pruefung = self._pruefung()
        try:
            kreditor_dubletten.als_neu_anlegen(
                pruefung, request.user, notiz=request.data.get('notiz', ''),
            )
        except DublettenPruefungFehler as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return self._antwort(pruefung)

    @action(detail=True, methods=['post'], url_path='zuordnen')
    def zuordnen(self, request, pk=None):
        pruefung = self._pruefung()
        kreditor_id = request.data.get('kreditor_id')
        if not kreditor_id:
            return Response(
                {'detail': 'kreditor_id fehlt.'}, status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            kreditor_dubletten.zuordnen(
                pruefung, kreditor_id, request.user,
                iban_uebernehmen=bool(request.data.get('iban_uebernehmen', True)),
                notiz=request.data.get('notiz', ''),
            )
        except DublettenPruefungFehler as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return self._antwort(pruefung)

    @action(detail=True, methods=['post'], url_path='ablehnen')
    def ablehnen(self, request, pk=None):
        pruefung = self._pruefung()
        try:
            kreditor_dubletten.ablehnen(
                pruefung, request.user, notiz=request.data.get('notiz', ''),
            )
        except DublettenPruefungFehler as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return self._antwort(pruefung)
