"""
API für den Mail-Posteingang — die menschliche Entscheidung über Mails, die
der Import nicht zuordnen konnte.

Vier Aktionen je Mail, alle ``POST``: neuen Vorgang anlegen, einem
bestehenden zuordnen, nur ablegen, verwerfen. Ein generisches ``PATCH`` gibt
es bewusst nicht (gleiche Begründung wie bei ``KreditorDublettenPruefung``):
der Posteingangs-Status darf sich nur über die Aktionen ändern, sonst laufen
Dokument-Kontext, Vorgangsbezug und Audit-Felder auseinander.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.objekte.models import Einheit, Objekt
from apps.personen.models import Person
from apps.vorgaenge.models import MailImportProtokoll, Vorgang, VorgangTyp
from apps.vorgaenge.serializers_posteingang import (
    NurAblegenSerializer, PosteingangSerializer, VerwerfenSerializer,
    VorgangAnlegenSerializer, VorgangZuordnenSerializer,
)
from apps.vorgaenge.services import posteingang_service


class MailPosteingangViewSet(mixins.ListModelMixin,
                             mixins.RetrieveModelMixin,
                             viewsets.GenericViewSet):
    """``/api/v1/mail-posteingang/``"""

    permission_classes = [IsAuthenticated]
    serializer_class = PosteingangSerializer

    def get_queryset(self):
        qs = (MailImportProtokoll.objects
              .select_related('person', 'objekt', 'einheit', 'vorgang', 'erledigt_von')
              .prefetch_related('dokumente'))
        # Default ist die Arbeitsliste: nur was noch zu entscheiden ist.
        gewuenscht = self.request.query_params.get('posteingang_status', 'offen')
        if gewuenscht != 'alle':
            qs = qs.filter(posteingang_status=gewuenscht)
        return qs.order_by('gesendet_am', 'verarbeitet_am')

    # -- Hilfen -----------------------------------------------------------

    def _protokoll(self):
        return get_object_or_404(MailImportProtokoll, pk=self.kwargs['pk'])

    def _antwort(self, protokoll):
        protokoll.refresh_from_db()
        return Response(PosteingangSerializer(protokoll).data)

    def _eingabe(self, serializer_klasse, request):
        eingabe = serializer_klasse(data=request.data)
        eingabe.is_valid(raise_exception=True)
        return eingabe.validated_data

    def _kontext(self, daten) -> dict:
        """Löst die übergebenen IDs in Objekte auf (404, wenn es sie nicht gibt)."""
        return {
            'objekt': get_object_or_404(Objekt, pk=daten['objekt']) if daten.get('objekt') else None,
            'einheit': get_object_or_404(Einheit, pk=daten['einheit']) if daten.get('einheit') else None,
            'person': get_object_or_404(Person, pk=daten['person']) if daten.get('person') else None,
        }

    @staticmethod
    def _fehler(exc):
        meldungen = getattr(exc, 'messages', None) or [str(exc)]
        return Response({'detail': ' '.join(meldungen)},
                        status=status.HTTP_400_BAD_REQUEST)

    # -- Aktionen ---------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='vorgang-anlegen')
    def vorgang_anlegen(self, request, pk=None):
        protokoll = self._protokoll()
        daten = self._eingabe(VorgangAnlegenSerializer, request)
        typ = get_object_or_404(VorgangTyp, pk=daten['typ'])
        try:
            posteingang_service.lege_vorgang_an(
                protokoll, typ=typ, benutzer=request.user,
                betreff=daten.get('betreff', ''),
                prioritaet=daten.get('prioritaet', ''),
                notiz=daten.get('notiz', ''),
                **self._kontext(daten),
            )
        except DjangoValidationError as exc:
            return self._fehler(exc)
        return self._antwort(protokoll)

    @action(detail=True, methods=['post'], url_path='vorgang-zuordnen')
    def vorgang_zuordnen(self, request, pk=None):
        protokoll = self._protokoll()
        daten = self._eingabe(VorgangZuordnenSerializer, request)
        vorgang = get_object_or_404(Vorgang, pk=daten['vorgang'])
        try:
            posteingang_service.ordne_vorgang_zu(
                protokoll, vorgang, benutzer=request.user,
                notiz=daten.get('notiz', ''),
            )
        except DjangoValidationError as exc:
            return self._fehler(exc)
        return self._antwort(protokoll)

    @action(detail=True, methods=['post'], url_path='nur-ablegen')
    def nur_ablegen(self, request, pk=None):
        protokoll = self._protokoll()
        daten = self._eingabe(NurAblegenSerializer, request)
        try:
            posteingang_service.lege_nur_ab(
                protokoll, benutzer=request.user,
                notiz=daten.get('notiz', ''),
                **self._kontext(daten),
            )
        except DjangoValidationError as exc:
            return self._fehler(exc)
        return self._antwort(protokoll)

    @action(detail=True, methods=['post'], url_path='verwerfen')
    def verwerfen(self, request, pk=None):
        protokoll = self._protokoll()
        daten = self._eingabe(VerwerfenSerializer, request)
        try:
            ergebnis = posteingang_service.verwirf(
                protokoll, benutzer=request.user, notiz=daten['notiz'],
            )
        except DjangoValidationError as exc:
            return self._fehler(exc)
        antwort = self._antwort(protokoll)
        antwort.data['geloeschte_dokumente'] = ergebnis['geloescht']
        antwort.data['gesperrte_dokumente'] = ergebnis['gesperrt']
        return antwort
