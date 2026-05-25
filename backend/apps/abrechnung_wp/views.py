import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.objekte.models import Wirtschaftsjahr
from .models import Wirtschaftsplan, WirtschaftsplanPosition
from .serializers import (
    WirtschaftsplanDetailSerializer,
    WirtschaftsplanListSerializer,
    WirtschaftsplanPositionSerializer,
)
from .services.wirtschaftsplan_service import (
    berechne_verteilung,
    commite_beschluss,
    erstelle_wirtschaftsplan,
    freigabe_trotz_diff,
    korrekturbeschluss_anlegen,
    loesche_position,
    setze_position_betrag,
    vorschau_hausgeld,
    _aktiver_vs_code,
    _validiere_konto_whitelist,
)

logger = logging.getLogger(__name__)


class WirtschaftsplanViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Wirtschaftsplan.objects.all()

    def get_serializer_class(self):
        if self.action in ('retrieve', 'konten_konfigurieren'):
            return WirtschaftsplanDetailSerializer
        return WirtschaftsplanListSerializer

    def get_queryset(self):
        qs = Wirtschaftsplan.objects.select_related(
            'wirtschaftsjahr', 'wirtschaftsjahr__objekt', 'erstellt_von',
        )
        objekt_id = self.request.query_params.get('objekt')
        if objekt_id:
            qs = qs.filter(wirtschaftsjahr__objekt_id=objekt_id)
        jahr = self.request.query_params.get('jahr')
        if jahr:
            qs = qs.filter(wirtschaftsjahr__jahr=jahr)
        return qs.order_by('-wirtschaftsjahr__jahr', 'status')

    def create(self, request, *args, **kwargs):
        wj_id = request.data.get('wirtschaftsjahr_id')
        wirkung_ab = request.data.get('wirkung_ab')
        if not wj_id or not wirkung_ab:
            return Response(
                {'detail': 'wirtschaftsjahr_id und wirkung_ab sind Pflichtfelder.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            wj = Wirtschaftsjahr.objects.get(id=wj_id)
        except Wirtschaftsjahr.DoesNotExist:
            return Response({'detail': 'Wirtschaftsjahr nicht gefunden.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            from datetime import date
            wirkung_ab_date = date.fromisoformat(wirkung_ab)
            wp = erstelle_wirtschaftsplan(wj, wirkung_ab_date, request.user)
        except (ValidationError, ValueError) as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(WirtschaftsplanDetailSerializer(wp).data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        wp = self.get_object()
        return Response(
            WirtschaftsplanDetailSerializer(
                wp,
                context={'request': request},
            ).data
        )

    @action(detail=True, methods=['get'], url_path='konten')
    def konten(self, request, pk=None):
        """Gibt alle WP-fähigen Konten für den WP zurück (Whitelist Kap. 4.1)."""
        wp = self.get_object()
        wj = wp.wirtschaftsjahr

        from apps.konten.models import Konto, KontoVerteilerSchluessel
        konten_qs = Konto.objects.filter(
            wirtschaftsjahr=wj,
            kontoart__in=['standard', 'summierung'],
            aktiv=True,
        ).order_by('kontonummer')

        result = []
        for k in konten_qs:
            try:
                nr = int(k.kontonummer)
            except ValueError:
                continue
            if not ((50000 <= nr <= 55999) or (57000 <= nr <= 57999)):
                continue

            vs_code = _aktiver_vs_code(k)
            hat_vs = vs_code is not None

            # Bereits vorhandene Position für dieses Konto?
            position = wp.positionen.filter(konto=k).first()

            result.append({
                'id': str(k.id),
                'kontonummer': k.kontonummer,
                'kontoname': k.kontoname,
                'kontoart': k.kontoart,
                'abrechnungsart': k.abrechnungsart,
                'vs_code': vs_code,
                'hat_vs': hat_vs,
                'position_id': str(position.id) if position else None,
                'betrag': str(position.betrag) if position else '0.00',
                'verteilung_validiert': position.verteilung_validiert if position else False,
                'verteilung_freigegeben_trotz_diff': position.verteilung_freigegeben_trotz_diff if position else False,
            })

        return Response(result)

    @action(detail=True, methods=['post'], url_path='positionen')
    def positionen_upsert(self, request, pk=None):
        """Upsert einer Position (betrag) + Neuberechnung der Verteilung."""
        wp = self.get_object()
        konto_id = request.data.get('konto_id')
        betrag_raw = request.data.get('betrag')
        if not konto_id or betrag_raw is None:
            return Response({'detail': 'konto_id und betrag erforderlich.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from apps.konten.models import Konto
            konto = Konto.objects.get(id=konto_id)
            betrag = Decimal(str(betrag_raw))
            position = setze_position_betrag(wp, konto, betrag, request.user)
        except Konto.DoesNotExist:
            return Response({'detail': 'Konto nicht gefunden.'}, status=status.HTTP_404_NOT_FOUND)
        except (ValidationError, ValueError) as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(WirtschaftsplanPositionSerializer(position).data)

    @action(detail=True, methods=['delete'], url_path='positionen/(?P<konto_id>[^/.]+)')
    def positionen_loeschen(self, request, pk=None, konto_id=None):
        """Löscht eine Position."""
        wp = self.get_object()
        try:
            position = WirtschaftsplanPosition.objects.get(wirtschaftsplan=wp, konto_id=konto_id)
            loesche_position(wp, position)
        except WirtschaftsplanPosition.DoesNotExist:
            return Response({'detail': 'Position nicht gefunden.'}, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='freigabe-trotz-diff')
    def freigabe_trotz_diff(self, request, pk=None):
        """Markiert eine Position trotz Rundungsdifferenz als freigegeben."""
        wp = self.get_object()
        konto_id = request.data.get('konto_id')
        if not konto_id:
            return Response({'detail': 'konto_id erforderlich.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            position = WirtschaftsplanPosition.objects.get(wirtschaftsplan=wp, konto_id=konto_id)
            freigabe_trotz_diff(position)
        except WirtschaftsplanPosition.DoesNotExist:
            return Response({'detail': 'Position nicht gefunden.'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'ok': True})

    @action(detail=True, methods=['get'], url_path='vorschau-hausgeld')
    def vorschau_hausgeld(self, request, pk=None):
        """Schritt 4: Vorschau der Hausgeld-Sollanteile je EV."""
        wp = self.get_object()
        try:
            result = vorschau_hausgeld(wp)
        except Exception as e:
            logger.exception('Fehler bei vorschau_hausgeld: %s', e)
            return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response({'vorschau': result})

    @action(detail=True, methods=['post'], url_path='beschluss')
    def beschluss(self, request, pk=None):
        """Schritt 5: Beschluss durchführen (atomar)."""
        wp = self.get_object()
        beschluss_datum = request.data.get('beschluss_datum')
        top = request.data.get('top', '')
        bemerkung = request.data.get('bemerkung', '')

        if not beschluss_datum:
            return Response({'detail': 'beschluss_datum ist Pflicht.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from datetime import date
            bd = date.fromisoformat(beschluss_datum)
            stats = commite_beschluss(wp, bd, top, bemerkung, request.user)
            wp.refresh_from_db()
        except ValidationError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception('Fehler bei commite_beschluss: %s', e)
            return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            'wp': WirtschaftsplanDetailSerializer(wp).data,
            'stats': stats,
        })

    @action(detail=True, methods=['post'], url_path='korrekturbeschluss')
    def korrekturbeschluss(self, request, pk=None):
        """Legt einen neuen WP-Entwurf als Korrekturbeschluss an."""
        wp = self.get_object()
        try:
            neu = korrekturbeschluss_anlegen(wp, request.user)
        except ValidationError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(WirtschaftsplanDetailSerializer(neu).data, status=status.HTTP_201_CREATED)
