"""
WKZ — DRF Views für Wiederkehrende Buchungen.

15 Endpoints gemäß Spec Kap. 11.
"""
import logging
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import WiederkehrendeBuchungVorlage, WiederkehrendeBuchungOP
from .serializers_wkz import (
    WKZVorlageSerializer,
    WKZVorlageDetailSerializer,
    WKZVorlageCreateSerializer,
    WKZOPSerializer,
    WKZOPDetailSerializer,
    WKZForecastSerializer,
)
from .services.wkz.vorlage_service import (
    erstelle_vorlage,
    reiche_vorlage_zur_freigabe_ein,
    aktiviere_vorlage,
    pausiere_vorlage,
    reaktiviere_vorlage,
    beende_vorlage,
    ersetze_vorlage,
)
from .services.wkz.op_generator_service import (
    berechne_fallige_perioden,
    verwirf_wkz_op,
)
from .services.wkz.buchungs_service import (
    verbuche_bankabgang,
    verbuche_mit_anpassung,
)

logger = logging.getLogger(__name__)


def _nur_weg(objekt):
    """HTTP 501 wenn das Objekt kein WEG ist."""
    if getattr(objekt, 'objekt_typ', None) != 'WEG':
        return Response(
            {'detail': 'WKZ ist nur für WEG-Objekte verfügbar.'},
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )
    return None


# ---------------------------------------------------------------------------
# WKZ-Vorlagen
# ---------------------------------------------------------------------------

class WKZVorlageViewSet(viewsets.ModelViewSet):
    """
    CRUD + Lifecycle-Aktionen für WiederkehrendeBuchungVorlagen.

    list/create via:  GET/POST /api/v1/objekte/{id}/wkz-vorlagen/
    detail/patch via: GET/PATCH /api/v1/wkz-vorlagen/{id}/
    actions via:      POST /api/v1/wkz-vorlagen/{id}/<aktion>/
    """
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'create':
            return WKZVorlageCreateSerializer
        if self.action in ('retrieve', 'update', 'partial_update'):
            return WKZVorlageDetailSerializer
        return WKZVorlageSerializer

    def get_queryset(self):
        qs = WiederkehrendeBuchungVorlage.objects.select_related(
            'objekt', 'kreditor', 'erstellt_von', 'freigegeben_von',
        ).prefetch_related('splits')

        params = self.request.query_params
        if objekt_id := params.get('objekt'):
            qs = qs.filter(objekt_id=objekt_id)
        if kreditor_id := params.get('kreditor'):
            qs = qs.filter(kreditor_id=kreditor_id)
        if s := params.get('status'):
            qs = qs.filter(status=s)
        return qs.order_by('bezeichnung')

    def create(self, request, *args, **kwargs):
        serializer = WKZVorlageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        splits_data = data.pop('splits', [])

        try:
            vorlage = erstelle_vorlage(data, splits_data, user=request.user)
        except Exception as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            WKZVorlageDetailSerializer(vorlage).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, *args, **kwargs):
        from django.db import transaction as db_transaction
        from .models import WiederkehrendeBuchungSplit
        from .services.wkz.vorlage_service import validiere_split_kontonummer

        vorlage = self.get_object()
        if vorlage.status != 'entwurf':
            return Response(
                {'detail': 'Nur Vorlagen im Status "entwurf" können bearbeitet werden.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        splits_data = request.data.get('splits')
        if splits_data is not None:
            if not splits_data:
                return Response(
                    {'detail': 'Mindestens ein Split ist erforderlich.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            for s in splits_data:
                try:
                    validiere_split_kontonummer(s['kontonummer'], vorlage.objekt)
                except Exception as exc:
                    return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            with db_transaction.atomic():
                vorlage.splits.all().delete()
                for i, s in enumerate(splits_data):
                    WiederkehrendeBuchungSplit.objects.create(
                        vorlage=vorlage,
                        kontonummer=s['kontonummer'],
                        bezeichnung=s.get('bezeichnung', ''),
                        betrag=Decimal(str(s['betrag'])),
                        reihenfolge=s.get('reihenfolge', i),
                    )
                vorlage.betrag_gesamt = sum(Decimal(str(s['betrag'])) for s in splits_data)
                vorlage.save(update_fields=['betrag_gesamt'])

        return super().partial_update(request, *args, **kwargs)

    # -----------------------------------------------------------------------
    # Lifecycle-Aktionen
    # -----------------------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='einreichen')
    def einreichen(self, request, pk=None):
        """Vorlage zur Freigabe einreichen."""
        try:
            vorlage = reiche_vorlage_zur_freigabe_ein(pk, request.user)
        except (ValueError, Exception) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(WKZVorlageDetailSerializer(vorlage).data)

    @action(detail=True, methods=['post'], url_path='freigeben')
    def freigeben(self, request, pk=None):
        """Freigabe erteilen — für Vorlagen im Status 'entwurf' oder 'eingereicht'."""
        vorlage = self.get_object()
        if vorlage.status not in ('entwurf', 'eingereicht'):
            return Response(
                {'detail': 'Nur Vorlagen im Status "entwurf" oder "eingereicht" können freigegeben werden.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            aktiviere_vorlage(vorlage, freigegeben_von=request.user)
        except Exception as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(WKZVorlageDetailSerializer(vorlage).data)

    @action(detail=True, methods=['post'], url_path='pausieren')
    def pausieren(self, request, pk=None):
        """Aktive Vorlage pausieren."""
        grund = request.data.get('grund', '')
        try:
            vorlage = pausiere_vorlage(pk, grund, request.user)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(WKZVorlageDetailSerializer(vorlage).data)

    @action(detail=True, methods=['post'], url_path='reaktivieren')
    def reaktivieren(self, request, pk=None):
        """Pausierte Vorlage reaktivieren."""
        try:
            vorlage = reaktiviere_vorlage(pk, request.user)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(WKZVorlageDetailSerializer(vorlage).data)

    @action(detail=True, methods=['post'], url_path='beenden')
    def beenden(self, request, pk=None):
        """Vorlage beenden (gueltig_bis setzen)."""
        gueltig_bis_str = request.data.get('gueltig_bis')
        grund = request.data.get('grund', '')
        if not gueltig_bis_str:
            return Response(
                {'detail': 'gueltig_bis ist erforderlich.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            gueltig_bis = date.fromisoformat(gueltig_bis_str)
            vorlage = beende_vorlage(pk, gueltig_bis, grund, request.user)
        except (ValueError, Exception) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(WKZVorlageDetailSerializer(vorlage).data)

    @action(detail=True, methods=['post'], url_path='ersetzen')
    def ersetzen(self, request, pk=None):
        """Bescheidsänderung — alte Vorlage beenden und neue anlegen."""
        neue_daten = request.data.get('neue_daten', {})
        neue_splits = request.data.get('splits', [])
        if not neue_daten:
            return Response(
                {'detail': 'neue_daten ist erforderlich.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            neue_vorlage = ersetze_vorlage(pk, neue_daten, neue_splits, request.user)
        except (ValueError, Exception) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            WKZVorlageDetailSerializer(neue_vorlage).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['get'], url_path='forecast')
    def forecast(self, request, pk=None):
        """Nächste 12 Fälligkeiten dieser Vorlage."""
        vorlage = self.get_object()
        stichtag = date.today()
        # Genug Vorlauf für 12 Perioden
        perioden = berechne_fallige_perioden(
            vorlage,
            stichtag=stichtag + timedelta(days=365 + vorlage.vorlauf_tage),
        )
        # Auf 12 Perioden begrenzen
        data = [
            {
                'periode_von': str(p.periode_von),
                'periode_bis': str(p.periode_bis),
                'faellig_am': str(p.faellig_am),
                'betrag': str(vorlage.betrag_gesamt),
            }
            for p in perioden[:12]
        ]
        return Response(data)


# ---------------------------------------------------------------------------
# WKZ-Ops
# ---------------------------------------------------------------------------

class WKZOPViewSet(viewsets.ReadOnlyModelViewSet):
    """
    WiederkehrendeBuchungOPs — read-only + Aktionen.

    detail via: GET /api/v1/wkz-ops/{id}/
    actions via: POST /api/v1/wkz-ops/{id}/<aktion>/
    """
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return WKZOPDetailSerializer
        return WKZOPSerializer

    def get_queryset(self):
        qs = WiederkehrendeBuchungOP.objects.select_related(
            'vorlage', 'vorlage__kreditor', 'vorlage__objekt',
            'kreditor_op', 'bank_match_buchung',
        ).prefetch_related('vorlage__splits')

        params = self.request.query_params
        if vorlage_id := params.get('vorlage'):
            qs = qs.filter(vorlage_id=vorlage_id)
        if objekt_id := params.get('objekt'):
            qs = qs.filter(vorlage__objekt_id=objekt_id)
        if s := params.get('status'):
            qs = qs.filter(status=s)
        return qs.order_by('-faellig_am')

    @action(detail=True, methods=['post'], url_path='verwerfen')
    def verwerfen(self, request, pk=None):
        """OP verwerfen — solange kein Bankabgang gebucht."""
        grund = request.data.get('grund', '')
        try:
            wkz_op = verwirf_wkz_op(pk, grund, request.user)
        except (ValueError, Exception) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(WKZOPDetailSerializer(wkz_op).data)

    @action(detail=True, methods=['post'], url_path='manuell-verbuchen')
    def manuell_verbuchen(self, request, pk=None):
        """
        Manuelle Verbuchung mit einem Kontoumsatz.

        Body: { "kontoumsatz_id": "...", "splits_override": {"50100": "450.00", ...} }
        """
        from .models import Kontoumsatz
        kontoumsatz_id = request.data.get('kontoumsatz_id')
        splits_override_raw = request.data.get('splits_override')

        if not kontoumsatz_id:
            return Response(
                {'detail': 'kontoumsatz_id ist erforderlich.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            wkz_op = WiederkehrendeBuchungOP.objects.get(pk=pk)
            kontoumsatz = Kontoumsatz.objects.get(pk=kontoumsatz_id)
        except (WiederkehrendeBuchungOP.DoesNotExist, Kontoumsatz.DoesNotExist) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_404_NOT_FOUND)

        if wkz_op.status in ('bankabgang_erfolgt', 'abweichend_geklaert', 'verworfen'):
            return Response(
                {'detail': f'OP im Status "{wkz_op.status}" kann nicht mehr verbucht werden.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            if splits_override_raw:
                splits_override = {
                    k: Decimal(str(v)) for k, v in splits_override_raw.items()
                }
                buchung = verbuche_mit_anpassung(
                    wkz_op, kontoumsatz, splits_override, request.user
                )
            else:
                buchung = verbuche_bankabgang(wkz_op, kontoumsatz, user=request.user)
        except (ValueError, Exception) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'wkz_op': WKZOPDetailSerializer(wkz_op).data,
            'buchung_id': str(buchung.id),
        })


# ---------------------------------------------------------------------------
# Forecast je Objekt (90-Tage-Liquiditätsvorschau)
# ---------------------------------------------------------------------------

class WKZForecastViewSet(viewsets.ViewSet):
    """
    GET /api/v1/objekte/{objekt_id}/wkz-forecast/
    Liquiditätsvorschau der nächsten 90 Tage.
    """
    permission_classes = [IsAuthenticated]

    def list(self, request, objekt_pk=None):
        from apps.objekte.models import Objekt
        try:
            objekt = Objekt.objects.get(pk=objekt_pk)
        except Objekt.DoesNotExist:
            return Response({'detail': 'Objekt nicht gefunden.'}, status=status.HTTP_404_NOT_FOUND)

        stichtag = date.today()
        grenze = stichtag + timedelta(days=90)

        aktive_vorlagen = WiederkehrendeBuchungVorlage.objects.filter(
            objekt=objekt,
            status='aktiv',
        ).prefetch_related('splits').select_related('kreditor')

        positionen = []
        for vorlage in aktive_vorlagen:
            perioden = berechne_fallige_perioden(vorlage, stichtag=grenze)
            for p in perioden:
                if p.faellig_am <= grenze:
                    positionen.append({
                        'faellig_am': str(p.faellig_am),
                        'periode_von': str(p.periode_von),
                        'periode_bis': str(p.periode_bis),
                        'kreditor': str(vorlage.kreditor),
                        'bezeichnung': vorlage.bezeichnung,
                        'betrag': str(vorlage.betrag_gesamt),
                        'vorlage_id': str(vorlage.id),
                    })

        positionen.sort(key=lambda x: x['faellig_am'])
        return Response(positionen)


# ---------------------------------------------------------------------------
# Kreditoren-WKZ-Vorlagen (über alle Objekte)
# ---------------------------------------------------------------------------

class KreditorWKZVorlagenViewSet(viewsets.ViewSet):
    """
    GET /api/v1/kreditoren/{kreditor_id}/wkz-vorlagen/
    Alle aktiven Vorlagen eines Kreditors über alle Objekte.
    """
    permission_classes = [IsAuthenticated]

    def list(self, request, kreditor_pk=None):
        qs = WiederkehrendeBuchungVorlage.objects.filter(
            kreditor_id=kreditor_pk,
        ).select_related('objekt', 'kreditor').prefetch_related('splits')

        if s := request.query_params.get('status'):
            qs = qs.filter(status=s)

        return Response(WKZVorlageSerializer(qs, many=True).data)
