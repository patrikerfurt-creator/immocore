from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Kreditor, KreditorRegel, Rechnung, Freigabe, Verarbeitungslog,
    FreigabelimitDefault, RechnungsMatchRegel, RechnungsErkennungsLog,
    RechnungsBearbeitungsLock,
)
from .serializers import (
    KreditorSerializer, RechnungSerializer, RechnungListSerializer,
    FreigabeSerializer, VerarbeitungslogSerializer,
    RechnungsMatchRegelSerializer, RechnungsErkennungsLogSerializer,
)


def _finde_dubletten_kandidaten(name: str, iban=None, schwelle: float = 0.65) -> list:
    """Sucht ähnliche Kreditoren anhand Name und optionaler IBAN."""
    from .recognition import _fuzzy_score

    gefunden_ids: set = set()
    kandidaten: list = []

    if iban:
        k = Kreditor.objects.filter(iban=iban, aktiv=True).first()
        if k:
            return [{
                'id': str(k.id),
                'name': k.name,
                'kreditorennummer': k.kreditorennummer or '',
                'iban': k.iban or '',
                'score': 1.0,
                'match_typ': 'iban',
            }]

    name_norm = name.lower().strip()
    exact = Kreditor.objects.filter(name_normalisiert__iexact=name_norm, aktiv=True).first()
    if exact:
        kandidaten.append({
            'id': str(exact.id),
            'name': exact.name,
            'kreditorennummer': exact.kreditorennummer or '',
            'iban': exact.iban or '',
            'score': 0.92,
            'match_typ': 'name_exakt',
        })
        gefunden_ids.add(exact.id)

    for k in Kreditor.objects.filter(aktiv=True).exclude(id__in=gefunden_ids):
        score = _fuzzy_score(name, k.name)
        if score >= schwelle:
            kandidaten.append({
                'id': str(k.id),
                'name': k.name,
                'kreditorennummer': k.kreditorennummer or '',
                'iban': k.iban or '',
                'score': min(score, 0.85),
                'match_typ': 'name_fuzzy',
            })

    kandidaten.sort(key=lambda x: x['score'], reverse=True)
    return kandidaten[:10]


class KreditorViewSet(viewsets.ModelViewSet):
    serializer_class = KreditorSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'iban', 'ort', 'kreditorennummer']
    ordering = ['name']

    def get_queryset(self):
        qs = Kreditor.objects.all()
        if self.request.query_params.get('aktiv') == 'false':
            qs = qs.filter(aktiv=False)
        else:
            qs = qs.filter(aktiv=True)
        return qs

    @action(detail=True, methods=['post'], url_path='deaktivieren')
    def deaktivieren(self, request, pk=None):
        k = self.get_object()
        k.aktiv = False
        k.save(update_fields=['aktiv'])
        return Response(KreditorSerializer(k).data)

    @action(detail=False, methods=['post'], url_path='duplikat-pruefen')
    def duplikat_pruefen(self, request):
        """Prüft ob ein Kreditor mit gegebenem Namen/IBAN bereits existiert."""
        name = request.data.get('name', '').strip()
        iban_raw = request.data.get('iban', '')
        iban = iban_raw.replace(' ', '').upper() if iban_raw else None
        if not name:
            return Response({'error': 'Name fehlt'}, status=status.HTTP_400_BAD_REQUEST)
        kandidaten = _finde_dubletten_kandidaten(name, iban)
        return Response({'kandidaten': kandidaten})

    @action(detail=True, methods=['get'], url_path='kontoauszug')
    def kontoauszug(self, request, pk=None):
        """Kreditorenkonto: alle Rechnungen eines Kreditors mit OPOS-Nummer."""
        kreditor = self.get_object()
        qs = (
            Rechnung.objects
            .filter(kreditor=kreditor)
            .select_related('objekt', 'buchung', 'buchung__soll_konto')
            .order_by('-rechnungsdatum', '-erstellt_am')
        )
        if objekt_id := request.query_params.get('objekt'):
            qs = qs.filter(objekt_id=objekt_id)

        positionen = []
        for r in qs:
            b = r.buchung
            sk = (b.soll_konto if b else None) or r.kostenstelle
            positionen.append({
                'id': str(r.id),
                'rechnungsnummer': r.rechnungsnummer,
                'rechnungsdatum': str(r.rechnungsdatum) if r.rechnungsdatum else None,
                'faelligkeitsdatum': str(r.faelligkeitsdatum) if r.faelligkeitsdatum else None,
                'betrag_brutto': float(r.betrag_brutto) if r.betrag_brutto else None,
                'status': r.status,
                'objekt': r.objekt.bezeichnung if r.objekt else None,
                'sachkonto_nr': sk.kontonummer if sk else None,
                'sachkonto_name': sk.kontoname if sk else None,
                'opos_nr': b.belegnr if b else None,
                'buchungsdatum': str(b.buchungsdatum) if b else None,
                'buchung_status': b.status if b else None,
            })

        return Response({
            'kreditor': {
                'id': str(kreditor.id),
                'name': kreditor.name,
                'iban': kreditor.iban or '',
                'ort': kreditor.ort or '',
            },
            'positionen': positionen,
        })


class RechnungViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['rechnungsnummer', 'lieferant_name', 'dateiname', 'leistungsbeschreibung']
    ordering_fields = ['rechnungsdatum', 'betrag_brutto', 'status', 'erstellt_am']
    ordering = ['-erstellt_am']

    def get_queryset(self):
        from django.db.models import Q
        qs = Rechnung.objects.select_related(
            'kreditor', 'lieferant', 'duplikat_von', 'objekt',
            'vorgeschlagenes_konto', 'kostenstelle',
            'buchungskonto', 'zugewiesen_an', 'match_regel',
        )
        p = self.request.query_params
        if objekt_id := p.get('objekt'):
            qs = qs.filter(Q(objekt_id=objekt_id) | Q(objekt__isnull=True))
        if s := p.get('status'):
            qs = qs.filter(status=s)
        if stufe := p.get('stufe'):
            qs = qs.filter(erkennungs_stufe=stufe)
        if kreditor_id := p.get('kreditor'):
            qs = qs.filter(kreditor_id=kreditor_id)
        if (zugewiesen := p.get('zugewiesen_an')) == 'me':
            qs = qs.filter(zugewiesen_an=self.request.user)
        elif zugewiesen == 'null':
            qs = qs.filter(zugewiesen_an__isnull=True)
        elif zugewiesen:
            qs = qs.filter(zugewiesen_an_id=zugewiesen)
        if routing_ziel := p.get('routing_ziel'):
            qs = qs.filter(routing_ziel=routing_ziel)
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return RechnungListSerializer
        return RechnungSerializer

    @action(detail=True, methods=['post'], url_path='freigeben')
    def freigeben(self, request, pk=None):
        from apps.konten.models import Konto
        from .services.rechnung_op_service import rechnung_freigeben as op_freigeben
        from django.core.exceptions import ValidationError as DjangoValidationError

        rechnung = self.get_object()
        if rechnung.status not in ('importiert', 'prueffall', 'in_pruefung', 'erfasst', 'erkannt',
                                    'pruefung_match', 'nicht_erkannt'):
            return Response(
                {'error': f'Freigabe im Status "{rechnung.status}" nicht möglich'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Trigger B: Buchungskonto-Korrektur → Lernlogik
        neues_konto_id = request.data.get('buchungskonto_id')
        lernen = request.data.get('lernen', True)
        if neues_konto_id and rechnung.buchungskonto_id and str(rechnung.buchungskonto_id) != neues_konto_id:
            from .recognition import lege_match_regel_an
            try:
                neues_konto = Konto.objects.get(pk=neues_konto_id, objekt=rechnung.objekt)
                rechnung.buchungskonto = neues_konto
                rechnung.kostenstelle  = neues_konto
                lege_match_regel_an(rechnung, request.user, 'freigabe_korrektur', lernen=lernen)
            except Konto.DoesNotExist:
                pass

        # OP-Service: aufwandskonto validieren und speichern
        aufwandskonto_id = request.data.get('aufwandskonto_id')
        if aufwandskonto_id:
            try:
                aufwandskonto = Konto.objects.get(pk=aufwandskonto_id)
                try:
                    op_freigeben(rechnung, aufwandskonto, request.user)
                except DjangoValidationError as exc:
                    return Response({'error': exc.message}, status=status.HTTP_400_BAD_REQUEST)
            except Konto.DoesNotExist:
                return Response({'error': 'Aufwandskonto nicht gefunden'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            rechnung.status = 'freigegeben'
            rechnung.save(update_fields=['status', 'buchungskonto', 'kostenstelle'])

        Freigabe.objects.create(
            rechnung=rechnung,
            bearbeiter=request.user,
            rolle=_bestimme_rolle(request.user),
            entscheidung='freigegeben',
            begruendung=request.data.get('begruendung', ''),
        )
        Verarbeitungslog.objects.create(
            rechnung=rechnung, aktion='Freigegeben', status='freigegeben',
            details=f'Freigabe durch {request.user.get_full_name() or request.user.username}',
        )
        return Response(RechnungSerializer(rechnung, context={'request': request}).data)

    @action(detail=True, methods=['post'], url_path='ablehnen')
    def ablehnen(self, request, pk=None):
        rechnung = self.get_object()
        if rechnung.status in ('gebucht', 'bezahlt', 'abgelehnt'):
            return Response(
                {'error': f'Ablehnung im Status "{rechnung.status}" nicht möglich'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        Freigabe.objects.create(
            rechnung=rechnung,
            bearbeiter=request.user,
            rolle=_bestimme_rolle(request.user),
            entscheidung='abgelehnt',
            begruendung=request.data.get('begruendung', ''),
        )
        rechnung.status = 'abgelehnt'
        rechnung.save(update_fields=['status'])
        Verarbeitungslog.objects.create(
            rechnung=rechnung, aktion='Abgelehnt', status='abgelehnt',
            details=request.data.get('begruendung', ''),
        )
        return Response(RechnungSerializer(rechnung, context={'request': request}).data)

    @action(detail=True, methods=['post'], url_path='als-neu')
    def als_neu(self, request, pk=None):
        """Prüffall oder Duplikat manuell als neue Rechnung bestätigen."""
        rechnung = self.get_object()
        if rechnung.status not in ('prueffall', 'duplikat'):
            return Response(
                {'error': 'Nur für Prüffälle und Duplikate möglich'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        rechnung.status = 'importiert'
        rechnung.duplikat_typ = ''
        rechnung.duplikat_von = None
        rechnung.save(update_fields=['status', 'duplikat_typ', 'duplikat_von'])
        Verarbeitungslog.objects.create(
            rechnung=rechnung, aktion='Als neue Rechnung bestätigt', status='importiert',
        )
        return Response(RechnungSerializer(rechnung, context={'request': request}).data)

    @action(detail=True, methods=['post'], url_path='buchen')
    def buchen(self, request, pk=None):
        """Sachkonto und Objekt erfassen — Buchung erfolgt erst bei Zahlung."""
        from apps.objekte.models import Objekt
        from apps.konten.models import Konto

        rechnung = self.get_object()
        if rechnung.status in ('bezahlt', 'abgelehnt'):
            return Response({'error': f'Sachkonto im Status "{rechnung.status}" nicht änderbar'}, status=status.HTTP_400_BAD_REQUEST)

        objekt_id = request.data.get('objekt_id')
        konto_id = request.data.get('konto_id')

        if not objekt_id:
            return Response({'error': 'Objekt fehlt'}, status=status.HTTP_400_BAD_REQUEST)
        if not konto_id:
            return Response({'error': 'Sachkonto fehlt'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            objekt = Objekt.objects.get(id=objekt_id)
        except Objekt.DoesNotExist:
            return Response({'error': 'Objekt nicht gefunden'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            sachkonto = Konto.objects.get(id=konto_id, objekt=objekt)
        except Konto.DoesNotExist:
            return Response({'error': 'Sachkonto nicht gefunden'}, status=status.HTTP_400_BAD_REQUEST)

        rechnung.kostenstelle = sachkonto
        rechnung.objekt = objekt
        if rechnung.status not in ('freigegeben', 'gebucht'):
            rechnung.status = 'erfasst'
        rechnung.save(update_fields=['kostenstelle', 'objekt', 'status'])

        # Kreditor-Regel lernen
        if rechnung.kreditor:
            regel, created = KreditorRegel.objects.get_or_create(
                kreditor=rechnung.kreditor,
                kundennummer=rechnung.kundennummer or '',
                defaults={'objekt': objekt, 'konto': sachkonto},
            )
            if not created:
                regel.objekt = objekt
                regel.konto = sachkonto
                regel.treffer += 1
                regel.save(update_fields=['objekt', 'konto', 'treffer', 'zuletzt_angewendet'])

        Verarbeitungslog.objects.create(
            rechnung=rechnung,
            aktion='Sachkonto erfasst',
            status=rechnung.status,
            details=f'Sachkonto: {sachkonto.kontonummer} {sachkonto.kontoname} | Objekt: {objekt.bezeichnung}',
        )
        return Response(RechnungSerializer(rechnung, context={'request': request}).data)

    @action(detail=True, methods=['post'], url_path='bezahlen')
    def bezahlen(self, request, pk=None):
        """Zahlung buchen (Kassenprinzip): Soll Aufwandskonto / Haben Bankkonto."""
        from datetime import date, datetime
        from decimal import Decimal
        from apps.konten.models import Konto
        from .services.rechnung_zahlung_service import rechnung_bezahlen as op_bezahlen
        from django.core.exceptions import ValidationError as DjangoValidationError

        rechnung = self.get_object()
        haben_konto_id    = request.data.get('haben_konto_id')
        buchungsdatum_str = request.data.get('buchungsdatum')

        if not haben_konto_id:
            return Response({'error': 'Bankkonto fehlt'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            haben_konto = Konto.objects.get(id=haben_konto_id, objekt=rechnung.objekt)
        except Konto.DoesNotExist:
            return Response({'error': 'Bankkonto nicht gefunden'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            buchungsdatum = datetime.strptime(buchungsdatum_str, '%Y-%m-%d').date() if buchungsdatum_str else date.today()
        except ValueError:
            buchungsdatum = date.today()

        betrag = Decimal(str(request.data.get('betrag', rechnung.betrag_brutto or 0)))

        try:
            buchung = op_bezahlen(
                rechnung=rechnung,
                bankkonto=haben_konto,
                betrag=betrag,
                buchungsdatum=buchungsdatum,
                gebucht_von=request.user,
            )
        except DjangoValidationError as exc:
            return Response({'error': exc.message}, status=status.HTTP_400_BAD_REQUEST)

        konto_soll = rechnung.aufwandskonto or rechnung.kostenstelle
        Verarbeitungslog.objects.create(
            rechnung=rechnung,
            aktion='Bezahlt',
            status='bezahlt',
            details=(
                f'Soll: {konto_soll.kontonummer} {konto_soll.kontoname} | '
                f'Haben: {haben_konto.kontonummer} {haben_konto.kontoname} | '
                f'Betrag: {betrag} EUR'
            ) if konto_soll else f'Haben: {haben_konto.kontonummer} | Betrag: {betrag} EUR',
        )
        return Response(RechnungSerializer(rechnung, context={'request': request}).data)

    @action(detail=True, methods=['get'], url_path='pdf')
    def pdf(self, request, pk=None):
        """PDF-Datei aus dem Dateisystem liefern."""
        from pathlib import Path
        from django.http import FileResponse
        rechnung = self.get_object()
        pfad = Path(rechnung.pfad) if rechnung.pfad else None
        if rechnung.pdf_upload:
            pfad = Path(rechnung.pdf_upload.path)
        if not pfad or not pfad.exists():
            return Response({'error': 'PDF nicht gefunden'}, status=status.HTTP_404_NOT_FOUND)
        return FileResponse(open(pfad, 'rb'), content_type='application/pdf')

    # ------------------------------------------------------------------
    # Frontoffice Soft-Lock
    # ------------------------------------------------------------------
    @action(detail=True, methods=['post'], url_path='lock')
    def lock_setzen(self, request, pk=None):
        """Lock setzen oder verlängern (5 Minuten)."""
        from django.utils import timezone
        from datetime import timedelta
        rechnung = self.get_object()
        gueltig_bis = timezone.now() + timedelta(minutes=5)
        lock, created = RechnungsBearbeitungsLock.objects.update_or_create(
            rechnung=rechnung,
            defaults={'user': request.user, 'gueltig_bis': gueltig_bis},
        )
        if not created and lock.user != request.user and lock.ist_aktiv:
            return Response(
                {'error': f'In Bearbeitung von {lock.user.get_full_name() or lock.user.username}',
                 'locked_by': lock.user.get_full_name() or lock.user.username,
                 'gueltig_bis': lock.gueltig_bis},
                status=status.HTTP_409_CONFLICT,
            )
        lock.user = request.user
        lock.gueltig_bis = gueltig_bis
        lock.save()
        return Response({'locked': True, 'gueltig_bis': lock.gueltig_bis})

    @action(detail=True, methods=['delete'], url_path='lock')
    def lock_loesen(self, request, pk=None):
        """Lock freigeben."""
        rechnung = self.get_object()
        RechnungsBearbeitungsLock.objects.filter(
            rechnung=rechnung, user=request.user,
        ).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='lock/heartbeat')
    def lock_heartbeat(self, request, pk=None):
        """Lock um 5 Minuten verlängern (alle 30 Sek. von der UI)."""
        from django.utils import timezone
        from datetime import timedelta
        rechnung = self.get_object()
        try:
            lock = RechnungsBearbeitungsLock.objects.get(rechnung=rechnung, user=request.user)
            lock.gueltig_bis = timezone.now() + timedelta(minutes=5)
            lock.save(update_fields=['gueltig_bis'])
            return Response({'gueltig_bis': lock.gueltig_bis})
        except RechnungsBearbeitungsLock.DoesNotExist:
            return Response({'error': 'Kein aktiver Lock'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['get'], url_path='logs')
    def logs(self, request, pk=None):
        rechnung = self.get_object()
        logs = rechnung.logs.all()
        return Response(VerarbeitungslogSerializer(logs, many=True).data)

    # ------------------------------------------------------------------
    # Erkennungs-Pipeline manuell anstoßen
    # ------------------------------------------------------------------
    @action(detail=True, methods=['post'], url_path='erkennung-ausfuehren')
    def erkennung_ausfuehren(self, request, pk=None):
        rechnung = self.get_object()
        from .recognition import fuehre_erkennung_aus
        rechnung = fuehre_erkennung_aus(rechnung)
        Verarbeitungslog.objects.create(
            rechnung=rechnung, aktion='Erkennung ausgeführt', status=rechnung.status,
            details=f'Stufe {rechnung.erkennungs_stufe} | Konfidenz: {rechnung.erkennungs_konfidenz}',
        )
        return Response(RechnungSerializer(rechnung, context={'request': request}).data)

    # ------------------------------------------------------------------
    # Erkennungs-Log abrufen
    # ------------------------------------------------------------------
    @action(detail=True, methods=['get'], url_path='erkennungs-log')
    def erkennungs_log(self, request, pk=None):
        rechnung = self.get_object()
        logs = rechnung.erkennungs_logs.all()
        return Response(RechnungsErkennungsLogSerializer(logs, many=True).data)

    # ------------------------------------------------------------------
    # Identifizieren (Stufe 2+3 Prüffall → Doppelfunktion)
    # ------------------------------------------------------------------
    @action(detail=True, methods=['post'], url_path='identifizieren')
    def identifizieren(self, request, pk=None):
        """
        Body: { kreditor_id, objekt_id, buchungskonto_id,
                modus: 'speichern'|'freigeben', lernen: true }
        Erzeugt Match-Regel und routet neu.
        """
        from apps.objekte.models import Objekt
        from apps.konten.models import Konto
        from .recognition import (
            lege_match_regel_an, route_rechnung, darf_betreuer_direkt_freigeben,
            leistungstext_hash,
        )

        rechnung = self.get_object()
        if rechnung.status not in ('pruefung_match', 'nicht_erkannt', 'erkannt'):
            return Response(
                {'error': f'Identifizieren im Status "{rechnung.status}" nicht möglich'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data        = request.data
        kreditor_id = data.get('kreditor_id')
        objekt_id   = data.get('objekt_id')
        konto_id    = data.get('buchungskonto_id')
        modus       = data.get('modus', 'speichern')
        lernen      = data.get('lernen', True)

        if not kreditor_id:
            return Response({'error': 'kreditor_id fehlt'}, status=status.HTTP_400_BAD_REQUEST)
        if not objekt_id:
            return Response({'error': 'objekt_id fehlt'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            kreditor = Kreditor.objects.get(pk=kreditor_id)
        except Kreditor.DoesNotExist:
            return Response({'error': 'Kreditor nicht gefunden'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            objekt = Objekt.objects.get(pk=objekt_id)
        except Objekt.DoesNotExist:
            return Response({'error': 'Objekt nicht gefunden'}, status=status.HTTP_400_BAD_REQUEST)

        if konto_id:
            try:
                buchungskonto = Konto.objects.get(pk=konto_id, objekt=objekt)
            except Konto.DoesNotExist:
                return Response(
                    {'error': 'Buchungskonto nicht gefunden oder gehört nicht zu diesem Objekt'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            # Auto-detect: erstes direktes Buchungskonto des Objekts
            buchungskonto = Konto.objects.filter(
                objekt=objekt, direktes_buchen=True, aktiv=True,
            ).order_by('kontonummer').first()

        # Felder setzen
        rechnung.kreditor      = kreditor
        rechnung.objekt        = objekt
        rechnung.buchungskonto = buchungskonto
        rechnung.leistungstext_hash = leistungstext_hash(
            rechnung.leistungstext or rechnung.leistungsbeschreibung or ''
        )
        rechnung.status        = 'erkannt'

        # Lernlogik (Trigger A oder C)
        erstellt_aus = 'manuell' if rechnung.erkennungs_stufe == 3 else 'pruefung'
        regel = lege_match_regel_an(rechnung, request.user, erstellt_aus, lernen=lernen)
        if regel:
            rechnung.match_regel = regel

        if modus == 'freigeben':
            if not darf_betreuer_direkt_freigeben(rechnung, request.user):
                return Response(
                    {'error': 'Direktfreigabe nicht erlaubt — Betrag über Ihrem Freigabelimit'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            rechnung.status = 'freigegeben'

            # OP-Buchung: aufwandskonto optional speichern
            aufwandskonto_id = data.get('aufwandskonto_id')
            if aufwandskonto_id:
                from apps.konten.models import Konto as _Konto
                from .services.rechnung_op_service import _validiere_aufwandskonto
                from django.core.exceptions import ValidationError as _VE
                try:
                    awk = _Konto.objects.get(pk=aufwandskonto_id)
                    _validiere_aufwandskonto(awk, rechnung.objekt_id)
                    rechnung.aufwandskonto = awk
                except (_Konto.DoesNotExist, _VE):
                    pass  # Validation errors are non-fatal here; can be corrected later

            Freigabe.objects.create(
                rechnung=rechnung,
                bearbeiter=request.user,
                rolle=_bestimme_rolle(request.user),
                entscheidung='freigegeben',
                begruendung='Identifizieren + Freigeben durch Objektbetreuer',
            )
        else:
            # Neu routen → Limit-Workflow
            route_rechnung(rechnung)

        rechnung.save()
        Verarbeitungslog.objects.create(
            rechnung=rechnung, aktion='Identifiziert', status=rechnung.status,
            details=(
                f'Modus: {modus} | Kreditor: {kreditor.name} | '
                f'Konto: {buchungskonto.kontonummer} | Lernen: {lernen}'
            ),
        )
        return Response(RechnungSerializer(rechnung, context={'request': request}).data)

    # ------------------------------------------------------------------
    # Manuell erfassen (Stufe 3 — komplett neue Rechnung von Hand)
    # ------------------------------------------------------------------
    @action(detail=True, methods=['post'], url_path='manuell-erfassen')
    def manuell_erfassen(self, request, pk=None):
        """
        Vollständige manuelle Erfassung für nicht erkannte Rechnungen.
        Optional: neuer Kreditor per { kreditor_neu: { name, iban } }.
        """
        from apps.objekte.models import Objekt
        from apps.konten.models import Konto
        from .recognition import lege_match_regel_an, leistungstext_hash

        rechnung = self.get_object()
        if rechnung.status != 'nicht_erkannt':
            return Response(
                {'error': 'manuell-erfassen nur für Status nicht_erkannt'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = request.data

        # Kreditor anlegen oder holen
        kreditor = None
        if neu := data.get('kreditor_neu'):
            name = neu.get('name', '').strip()
            iban_raw = neu.get('iban', '')
            iban = iban_raw.replace(' ', '').upper() or None
            force_new = data.get('force_new', False)
            if not name:
                return Response({'error': 'Kreditorname fehlt'}, status=status.HTTP_400_BAD_REQUEST)
            if not force_new:
                kandidaten = _finde_dubletten_kandidaten(name, iban)
                if kandidaten and kandidaten[0]['score'] >= 0.70:
                    return Response(
                        {
                            'error': 'Mögliche Duplikate gefunden — bitte prüfen',
                            'dubletten_kandidaten': kandidaten,
                            'code': 'dublikat_verdacht',
                        },
                        status=status.HTTP_409_CONFLICT,
                    )
            kreditor, _ = Kreditor.objects.get_or_create(
                name=name,
                defaults={
                    'iban': iban,
                    'name_normalisiert': name.lower(),
                },
            )
        elif kreditor_id := data.get('kreditor_id'):
            try:
                kreditor = Kreditor.objects.get(pk=kreditor_id)
            except Kreditor.DoesNotExist:
                return Response({'error': 'Kreditor nicht gefunden'}, status=status.HTTP_400_BAD_REQUEST)

        if not kreditor:
            return Response({'error': 'kreditor_id oder kreditor_neu erforderlich'}, status=status.HTTP_400_BAD_REQUEST)

        objekt_id = data.get('objekt_id')
        konto_id  = data.get('buchungskonto_id')
        if not objekt_id or not konto_id:
            return Response({'error': 'objekt_id und buchungskonto_id erforderlich'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            objekt = Objekt.objects.get(pk=objekt_id)
        except Objekt.DoesNotExist:
            return Response({'error': 'Objekt nicht gefunden'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            buchungskonto = Konto.objects.get(pk=konto_id, objekt=objekt)
        except Konto.DoesNotExist:
            return Response({'error': 'Buchungskonto gehört nicht zu diesem Objekt'}, status=status.HTTP_400_BAD_REQUEST)

        # OCR-Felder optional überschreiben
        for feld in ('leistungstext', 'rechnungsnummer', 'betrag_brutto', 'rechnungsdatum'):
            if val := data.get(feld):
                setattr(rechnung, feld, val)

        rechnung.kreditor      = kreditor
        rechnung.objekt        = objekt
        rechnung.buchungskonto = buchungskonto
        rechnung.status        = 'erkannt'
        rechnung.erfasst_von   = request.user
        rechnung.leistungstext_hash = leistungstext_hash(
            rechnung.leistungstext or rechnung.leistungsbeschreibung or ''
        )

        lernen = data.get('lernen', True)
        regel = lege_match_regel_an(rechnung, request.user, 'manuell', lernen=lernen)
        if regel:
            rechnung.match_regel = regel

        rechnung.save()
        Verarbeitungslog.objects.create(
            rechnung=rechnung, aktion='Manuell erfasst', status=rechnung.status,
            details=f'Durch {request.user.get_full_name() or request.user.username}',
        )
        return Response(RechnungSerializer(rechnung, context={'request': request}).data)

    # ------------------------------------------------------------------
    # Freigabe mit Konto-Korrektur-Hook (Trigger B)
    # ------------------------------------------------------------------

    @action(detail=False, methods=['post'], url_path='sepa-export')
    def sepa_export(self, request):
        """Generiert pain.001 SEPA-Überweisungs-XML für ausgewählte Rechnungen."""
        from decimal import Decimal
        from datetime import date, datetime
        from django.http import HttpResponse
        from apps.buchhaltung.services.sepa_export import exportiere_sepa
        from apps.objekte.models import Bankkonto

        rechnung_ids = request.data.get('rechnung_ids', [])
        haben_konto_id = request.data.get('haben_konto_id')
        faelligkeitsdatum_str = request.data.get('faelligkeitsdatum')

        if not rechnung_ids:
            return Response({'error': 'Keine Rechnungen ausgewählt'}, status=status.HTTP_400_BAD_REQUEST)
        if not haben_konto_id:
            return Response({'error': 'Bankkonto fehlt'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            bankkonto = Bankkonto.objects.select_related('objekt').get(id=haben_konto_id)
        except Bankkonto.DoesNotExist:
            return Response({'error': 'Bankkonto nicht gefunden'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            faelligkeitsdatum = datetime.strptime(faelligkeitsdatum_str, '%Y-%m-%d').date() if faelligkeitsdatum_str else date.today()
        except ValueError:
            faelligkeitsdatum = date.today()

        rechnungen = Rechnung.objects.filter(
            id__in=rechnung_ids,
            kreditor__isnull=False,
        ).select_related('kreditor')

        if not rechnungen.exists():
            return Response({'error': 'Keine gültigen Rechnungen mit Kreditor gefunden'}, status=status.HTTP_400_BAD_REQUEST)

        zahlungen = []
        for r in rechnungen:
            if not r.betrag_brutto:
                continue
            kreditor = r.kreditor
            if not kreditor or not kreditor.iban:
                continue
            zahlungen.append({
                'betrag': Decimal(str(r.betrag_brutto)),
                'empfaenger_name': kreditor.name,
                'empfaenger_iban': kreditor.iban,
                'empfaenger_bic': kreditor.bic or 'NOTPROVIDED',
                'verwendungszweck': (
                    f"{r.rechnungsnummer or r.dateiname or str(r.id)[:8]} / "
                    f"{kreditor.name}"
                )[:140],
                'faelligkeitsdatum': faelligkeitsdatum,
                'end_to_end_id': f"RG-{str(r.id)[:12].upper()}",
            })

        if not zahlungen:
            return Response({'error': 'Keine Rechnungen mit IBAN-Kreditor gefunden'}, status=status.HTTP_400_BAD_REQUEST)

        auftraggeber = {
            'name': bankkonto.kontoinhaber or bankkonto.objekt.bezeichnung,
            'iban': bankkonto.iban,
            'bic': bankkonto.bic,
            'bank_bezeichnung': bankkonto.bezeichnung,
        }

        xml_bytes = exportiere_sepa(zahlungen, auftraggeber)
        dateiname = f"zahlungen_{faelligkeitsdatum.strftime('%Y%m%d')}.xml"
        response = HttpResponse(xml_bytes, content_type='application/xml')
        response['Content-Disposition'] = f'attachment; filename="{dateiname}"'
        return response


def _bestimme_rolle(user) -> str:
    if user.groups.filter(name='Geschaeftsfuehrer').exists():
        return 'geschaeftsfuehrer'
    if user.groups.filter(name='Objektmanager').exists():
        return 'objektmanager'
    if user.groups.filter(name='Sachbearbeiter').exists():
        return 'sachbearbeiter'
    try:
        abteilungen = user.mitarbeiter_profil.abteilungen or []
        if 'geschaeftsfuehrer' in abteilungen or 'prokurist' in abteilungen:
            return 'geschaeftsfuehrer'
        if 'objektmanagement' in abteilungen:
            return 'objektmanager'
    except Exception:
        pass
    return 'auto'


class FreigabelimitDefaultView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        config = FreigabelimitDefault.lade()
        return Response({'grenzen': config.grenzen})

    def put(self, request):
        grenzen = request.data.get('grenzen', [])
        config = FreigabelimitDefault.lade()
        config.grenzen = grenzen
        config.save()
        return Response({'grenzen': config.grenzen})


class RechnungsMatchRegelViewSet(viewsets.ModelViewSet):
    serializer_class   = RechnungsMatchRegelSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [filters.SearchFilter, filters.OrderingFilter]
    search_fields      = ['kreditor__name', 'leistungstext_sample']
    ordering           = ['-trefferzahl', '-letzte_anwendung']

    def get_queryset(self):
        qs = RechnungsMatchRegel.objects.select_related(
            'kreditor', 'objekt', 'buchungskonto', 'erstellt_durch'
        )
        p = self.request.query_params
        if kreditor_id := p.get('kreditor'):
            qs = qs.filter(kreditor_id=kreditor_id)
        if objekt_id := p.get('objekt'):
            qs = qs.filter(objekt_id=objekt_id)
        if s := p.get('status'):
            qs = qs.filter(status=s)
        else:
            qs = qs.filter(status='aktiv')
        if ea := p.get('erstellt_aus'):
            qs = qs.filter(erstellt_aus=ea)
        return qs

    @action(detail=True, methods=['post'], url_path='deaktivieren')
    def deaktivieren(self, request, pk=None):
        regel = self.get_object()
        regel.status = 'veraltet'
        regel.save(update_fields=['status'])
        return Response(RechnungsMatchRegelSerializer(regel).data)


class FreigabeViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = FreigabeSerializer
    permission_classes = [IsAuthenticated]
    ordering = ['-zeitstempel']

    def get_queryset(self):
        qs = Freigabe.objects.select_related('rechnung', 'bearbeiter')
        if rid := self.request.query_params.get('rechnung'):
            qs = qs.filter(rechnung_id=rid)
        return qs
