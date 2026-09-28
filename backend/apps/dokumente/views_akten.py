"""
API für die Aktenansicht.

``GET /api/v1/akten/hausakte/?objekt=<id>`` liefert die Hausakte als Liste
von Registergruppen. Die Sortierung und die Gruppierung kommen vollstaendig
aus ``akten_service`` — diese Schicht reicht nur durch.

Die Wohnungs- und Eigentuemerakte nutzen denselben Weg; sie brauchen nur
eine andere Quelle und Aktenart.
"""
import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.dokumente.models import Aktenregister, Dokument
from apps.dokumente.serializers_akten import (
    AktenregisterSerializer, DokumentVerschiebenSerializer,
    RegisterGruppeSerializer,
)
from apps.dokumente.services import akten_service
from apps.objekte.models import Einheit, Objekt
from apps.personen.models import Person

logger = logging.getLogger(__name__)


class AkteView(APIView):
    """Gemeinsame Basis der drei Aktensichten."""
    permission_classes = [IsAuthenticated]

    def _antwort(self, dokumente, aktenart, objekt=None, kopf=None):
        gruppen = akten_service.nach_registern(dokumente, aktenart, objekt=objekt)
        return Response({
            **(kopf or {}),
            'aktenart': aktenart,
            # Die Gesamtzahl aus den Gruppen, nicht aus der Queryset-Laenge:
            # ein Dokument kann nur in EINER Gruppe stehen, und so stimmt die
            # Summe garantiert mit der Anzeige ueberein.
            'anzahl_dokumente': sum(g['anzahl'] for g in gruppen),
            'register': RegisterGruppeSerializer(gruppen, many=True).data,
        })


class HausakteView(AkteView):
    """``/api/v1/akten/hausakte/?objekt=<id>``"""

    def get(self, request):
        objekt_id = request.query_params.get('objekt')
        if not objekt_id:
            return Response(
                {'detail': 'Parameter "objekt" ist erforderlich.'},
                status=status.HTTP_400_BAD_REQUEST)
        objekt = get_object_or_404(Objekt, pk=objekt_id)

        return self._antwort(
            akten_service.hausakte(objekt),
            Aktenregister.AKTENART_HAUS,
            objekt=objekt,
            kopf={'objekt': str(objekt.id), 'titel': objekt.bezeichnung},
        )


class WohnungsakteView(AkteView):
    """``/api/v1/akten/wohnungsakte/?einheit=<id>``"""

    def get(self, request):
        einheit_id = request.query_params.get('einheit')
        if not einheit_id:
            return Response(
                {'detail': 'Parameter "einheit" ist erforderlich.'},
                status=status.HTTP_400_BAD_REQUEST)
        einheit = get_object_or_404(
            Einheit.objects.select_related('objekt'), pk=einheit_id)

        return self._antwort(
            akten_service.wohnungsakte(einheit),
            Aktenregister.AKTENART_WOHNUNG,
            # Die Untergliederung des Objekts gilt auch in der Wohnungsakte.
            objekt=einheit.objekt,
            kopf={'einheit': str(einheit.id),
                  'titel': f'{einheit.objekt.bezeichnung} · {einheit.einheit_nr}'},
        )


class EigentuemerakteView(AkteView):
    """``/api/v1/akten/eigentuemerakte/?person=<id>``

    Zeitlich begrenzt auf die Besitzzeit — siehe ``akten_service``.
    """

    def get(self, request):
        person_id = request.query_params.get('person')
        if not person_id:
            return Response(
                {'detail': 'Parameter "person" ist erforderlich.'},
                status=status.HTTP_400_BAD_REQUEST)
        person = get_object_or_404(Person, pk=person_id)
        nur_aktuelle = request.query_params.get('nur_aktuelle') in ('1', 'true')

        return self._antwort(
            akten_service.eigentuemerakte(person, nur_aktuelle_evs=nur_aktuelle),
            Aktenregister.AKTENART_EIGENTUEMER,
            kopf={'person': str(person.id), 'titel': person.name},
        )


class AktenregisterViewSet(mixins.ListModelMixin,
                           mixins.CreateModelMixin,
                           mixins.UpdateModelMixin,
                           mixins.DestroyModelMixin,
                           viewsets.GenericViewSet):
    """``/api/v1/aktenregister/``

    Dient dem Anlegen objektspezifischer Untergliederung aus der Akte heraus
    ("05/A Hebeanlage"). Die gemeinsame Gliederung 01-21 wird hier zwar
    gelistet, aber nicht darueber gepflegt — das bleibt Stammdatenarbeit im
    Admin.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = AktenregisterSerializer

    def get_queryset(self):
        qs = Aktenregister.objects.select_related('eltern', 'objekt')
        objekt_id = self.request.query_params.get('objekt')
        if objekt_id:
            # Gemeinsame Register plus die dieses Objekts.
            qs = qs.filter(Q(objekt__isnull=True) | Q(objekt=objekt_id))
        aktenart = self.request.query_params.get('aktenart')
        if aktenart:
            qs = qs.filter(aktenart__in=[aktenart, Aktenregister.AKTENART_ALLE])
        return qs.order_by('sortierung', 'code')

    def perform_destroy(self, instance):
        # Ein Register mit Inhalt zu loeschen wuerde die Dokumente
        # heimatlos machen; PROTECT verhindert es ohnehin auf DB-Ebene,
        # hier gibt es dafuer eine verstaendliche Meldung.
        if instance.dokumente.exists():
            raise DjangoValidationError(
                'Das Register enthaelt Dokumente und kann nicht geloescht '
                'werden. Sortiere sie zuerst um oder setze das Register auf '
                'inaktiv.')
        if instance.objekt_id is None:
            raise DjangoValidationError(
                'Register der gemeinsamen Gliederung werden in der '
                'Verwaltung gepflegt, nicht hier.')
        instance.delete()

    def handle_exception(self, exc):
        if isinstance(exc, DjangoValidationError):
            return Response({'detail': ' '.join(exc.messages)},
                            status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)


class DokumentEinsortierenView(APIView):
    """``POST /api/v1/dokumente/<id>/einsortieren/``

    Setzt das Register eines Dokuments — der Weg, auf dem die Mails aus dem
    Posteingang aus "Ohne Register" herauskommen.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        dokument = get_object_or_404(Dokument, pk=pk)
        eingabe = DokumentVerschiebenSerializer(data=request.data)
        eingabe.is_valid(raise_exception=True)

        register_id = eingabe.validated_data['register']
        register = (get_object_or_404(Aktenregister, pk=register_id)
                    if register_id else None)

        # Ein objektspezifisches Register darf nur Dokumente aufnehmen, die
        # ueberhaupt zu diesem Objekt gehoeren — sonst waere das Dokument in
        # der Akte, in der es einsortiert wurde, gar nicht sichtbar.
        if register and register.objekt_id:
            sichtbar = Dokument.objects.fuer_objekt(register.objekt_id).filter(
                pk=dokument.pk).exists()
            if not sichtbar:
                return Response(
                    {'detail': f'Das Dokument gehoert nicht zur Akte von '
                               f'{register.objekt} und kann dort nicht '
                               f'einsortiert werden.'},
                    status=status.HTTP_400_BAD_REQUEST)

        dokument.register = register
        dokument.save(update_fields=['register'])
        logger.info('Dokument %s einsortiert nach %s durch %s',
                    dokument.dateiname, register or '(kein Register)', request.user)
        return Response({'id': str(dokument.id),
                         'register': str(register.id) if register else None,
                         'register_bezeichnung': str(register) if register else ''})
