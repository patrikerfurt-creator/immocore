from decimal import Decimal
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.abrechnung_wp.models import Wirtschaftsplan, WirtschaftsplanPosition, WirtschaftsplanAnteil
from apps.abrechnung_wp.serializers import (
    WirtschaftsplanSerializer, WirtschaftsplanListSerializer,
    WirtschaftsplanPositionSerializer,
)
from apps.abrechnung_wp.services.wirtschaftsplan_service import (
    berechne_verteilung, aggregiere_ba_je_ev, commite_beschluss,
    korrekturbeschluss_anlegen, _aktualisiere_gesamtsummen,
)
from apps.konten.models import KontoVerteilerSchluessel
from apps.objekte.models import Wirtschaftsjahr
from apps.personen.models import EigentumsVerhaeltnis


class WirtschaftsplanViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'list':
            return WirtschaftsplanListSerializer
        return WirtschaftsplanSerializer

    def get_queryset(self):
        qs = Wirtschaftsplan.objects.select_related(
            'wirtschaftsjahr__objekt', 'erstellt_von', 'beschlossen_von'
        )
        objekt_id = self.request.query_params.get('objekt')
        if objekt_id:
            qs = qs.filter(wirtschaftsjahr__objekt_id=objekt_id)
        wj_id = self.request.query_params.get('wirtschaftsjahr')
        if wj_id:
            qs = qs.filter(wirtschaftsjahr_id=wj_id)
        jahr = self.request.query_params.get('jahr')
        if jahr:
            qs = qs.filter(wirtschaftsjahr__jahr=jahr)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    def perform_create(self, serializer):
        wj_id = self.request.data.get('wirtschaftsjahr')
        wj = get_object_or_404(Wirtschaftsjahr, pk=wj_id)
        # VS-Snapshot für alle Konten: vs_code aus KontoVerteilerSchluessel
        serializer.save(
            erstellt_von=self.request.user,
            wirkung_ab=serializer.validated_data.get('wirkung_ab', wj.beginn_datum),
        )

    # -----------------------------------------------------------------------
    # Positionen
    # -----------------------------------------------------------------------

    @action(detail=True, methods=['post', 'put'], url_path='positionen')
    def positionen_upsert(self, request, pk=None):
        """Position anlegen oder aktualisieren — triggert berechne_verteilung."""
        wp = get_object_or_404(Wirtschaftsplan, pk=pk)
        if wp.status != 'entwurf':
            return Response({'errors': ['WP ist nicht im Entwurf-Status.']}, status=400)

        konto_id = request.data.get('konto')
        betrag_raw = request.data.get('betrag')
        if not konto_id or betrag_raw is None:
            return Response({'errors': ['konto und betrag sind Pflichtfelder.']}, status=400)

        from apps.konten.models import Konto
        konto = get_object_or_404(Konto, pk=konto_id)

        # Whitelist
        nr = konto.kontonummer
        if not (('50000' <= nr <= '55999') or nr.startswith('57')):
            return Response(
                {'errors': [f'Konto {nr} liegt nicht im erlaubten Bereich 50000–55999 oder 57xxx.']},
                status=400,
            )

        # VS-Code ermitteln
        kvs = KontoVerteilerSchluessel.objects.filter(konto=konto).order_by('-gueltig_ab').first()
        if not kvs:
            return Response(
                {'errors': [f'Konto {nr} hat keinen aktiven Verteilerschlüssel.']},
                status=400,
            )

        betrag = Decimal(str(betrag_raw))
        pos, created = WirtschaftsplanPosition.objects.get_or_create(
            wirtschaftsplan=wp,
            konto=konto,
            defaults={'vs_code': kvs.vs_code, 'betrag': betrag},
        )
        if not created:
            pos.betrag = betrag
            pos.vs_code = kvs.vs_code
            pos.save(update_fields=['betrag', 'vs_code'])

        berechne_verteilung(pos)
        _aktualisiere_gesamtsummen(wp)

        serializer = WirtschaftsplanPositionSerializer(pos)
        return Response(serializer.data, status=201 if created else 200)

    @action(detail=True, methods=['delete'], url_path='positionen/(?P<pos_id>[^/.]+)')
    def positionen_delete(self, request, pk=None, pos_id=None):
        wp = get_object_or_404(Wirtschaftsplan, pk=pk)
        if wp.status != 'entwurf':
            return Response({'errors': ['WP ist nicht im Entwurf-Status.']}, status=400)
        pos = get_object_or_404(WirtschaftsplanPosition, pk=pos_id, wirtschaftsplan=wp)
        pos.delete()
        _aktualisiere_gesamtsummen(wp)
        return Response(status=204)

    @action(detail=True, methods=['post'], url_path='positionen/(?P<pos_id>[^/.]+)/freigabe-trotz-diff')
    def freigabe_trotz_diff(self, request, pk=None, pos_id=None):
        pos = get_object_or_404(WirtschaftsplanPosition, pk=pos_id, wirtschaftsplan__pk=pk)
        pos.verteilung_freigegeben_trotz_diff = True
        pos.save(update_fields=['verteilung_freigegeben_trotz_diff'])
        return Response({'ok': True})

    # -----------------------------------------------------------------------
    # Vorschau Hausgeld-Soll
    # -----------------------------------------------------------------------

    @action(detail=True, methods=['get', 'post'], url_path='vorschau-hausgeld')
    def vorschau_hausgeld(self, request, pk=None):
        wp = get_object_or_404(Wirtschaftsplan, pk=pk)
        ba_je_ev = aggregiere_ba_je_ev(wp)

        result = []
        ev_ids = list({ev_id for (ev_id, _) in ba_je_ev.keys()})
        evs = {str(ev.id): ev for ev in EigentumsVerhaeltnis.objects.filter(
            pk__in=ev_ids
        ).select_related('einheit', 'person')}

        for (ev_id, ba_code), betrag in ba_je_ev.items():
            ev = evs.get(str(ev_id))
            if not ev:
                continue
            # Suche bestehenden Eintrag
            existing = next((r for r in result if r['ev_id'] == str(ev_id)), None)
            if not existing:
                existing = {
                    'ev_id': str(ev_id),
                    'einheit_nr': ev.einheit.einheit_nr,
                    'lage': ev.einheit.lage,
                    'person_name': ev.person.name if hasattr(ev.person, 'name') else str(ev.person),
                    'bas': {},
                    'summe': Decimal('0'),
                }
                result.append(existing)
            existing['bas'][ba_code] = str(betrag)
            existing['summe'] = str(Decimal(existing.get('summe', '0')) + betrag)

        return Response({'positionen': result, 'wp_id': str(wp.id)})

    # -----------------------------------------------------------------------
    # Beschluss
    # -----------------------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='beschluss')
    def beschluss(self, request, pk=None):
        wp = get_object_or_404(Wirtschaftsplan, pk=pk)
        beschluss_data = {
            'beschluss_datum': request.data.get('beschluss_datum'),
            'top': request.data.get('top', ''),
            'bemerkung': request.data.get('bemerkung', ''),
        }
        if not beschluss_data['beschluss_datum']:
            return Response({'errors': ['beschluss_datum ist Pflichtfeld.']}, status=400)

        try:
            from datetime import date as date_type
            if isinstance(beschluss_data['beschluss_datum'], str):
                from datetime import datetime
                beschluss_data['beschluss_datum'] = datetime.strptime(
                    beschluss_data['beschluss_datum'], '%Y-%m-%d'
                ).date()
            result = commite_beschluss(wp, beschluss_data, request.user)
            return Response(result)
        except Exception as e:
            import traceback, logging
            logging.getLogger(__name__).error('commite_beschluss: %s', traceback.format_exc())
            return Response({'errors': [str(e)]}, status=400)

    # -----------------------------------------------------------------------
    # Korrekturbeschluss
    # -----------------------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='korrekturbeschluss')
    def korrekturbeschluss(self, request, pk=None):
        alt_wp = get_object_or_404(Wirtschaftsplan, pk=pk)
        if alt_wp.status not in ('beschlossen', 'aktiv'):
            return Response({'errors': ['Korrekturbeschluss nur für beschlossene/aktive WPs möglich.']}, status=400)
        neu = korrekturbeschluss_anlegen(alt_wp, request.user)
        serializer = WirtschaftsplanSerializer(neu)
        return Response(serializer.data, status=201)

    # -----------------------------------------------------------------------
    # Verfügbare Konten für WP
    # -----------------------------------------------------------------------

    @action(detail=True, methods=['get'], url_path='verfuegbare-konten')
    def verfuegbare_konten(self, request, pk=None):
        wp = get_object_or_404(Wirtschaftsplan, pk=pk)
        from apps.konten.models import Konto
        konten = Konto.objects.filter(
            wirtschaftsjahr=wp.wirtschaftsjahr,
            aktiv=True,
        ).filter(
            kontonummer__gte='50000',
            kontonummer__lte='55999',
        ) | Konto.objects.filter(
            wirtschaftsjahr=wp.wirtschaftsjahr,
            aktiv=True,
            kontonummer__startswith='57',
        )
        konten = konten.exclude(kontoart='unterkonto').order_by('kontonummer')

        result = []
        for k in konten:
            kvs = KontoVerteilerSchluessel.objects.filter(konto=k).order_by('-gueltig_ab').first()
            hat_position = wp.positionen.filter(konto=k).exists()
            result.append({
                'id': str(k.id),
                'kontonummer': k.kontonummer,
                'kontoname': k.kontoname,
                'kontoart': k.kontoart,
                'abrechnungsart': k.abrechnungsart,
                'vs_code': kvs.vs_code if kvs else None,
                'hat_vs': bool(kvs),
                'hat_position': hat_position,
            })

        return Response(result)
