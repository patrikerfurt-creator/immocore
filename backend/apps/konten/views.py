from decimal import Decimal

from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Abrechnungsart, Konto, Personenkonto, Unterkonto
from .serializers import AbrechnungsartSerializer, KontoSerializer, PersonenkontoSerializer, UnterkontoSerializer
from .services import kontenrahmen_anlegen


class AbrechnungsartViewSet(viewsets.ModelViewSet):
    serializer_class   = AbrechnungsartSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [filters.OrderingFilter]
    ordering           = ['code']

    def get_queryset(self):
        qs = Abrechnungsart.objects.select_related('objekt')
        if self.request.query_params.get('objekt'):
            qs = qs.filter(objekt_id=self.request.query_params['objekt'])
        return qs

    def perform_create(self, serializer):
        instance = serializer.save()
        # Für Rücklage II+ (912, 913 ...): passende Sachkonten automatisch anlegen
        code = instance.code
        if code.isdigit() and len(code) == 3:
            reihenfolge = int(code) - 910
            if reihenfolge >= 2:
                from .services import ruecklagen_konten_anlegen
                ruecklagen_konten_anlegen(
                    str(instance.objekt_id),
                    [{'reihenfolge': reihenfolge}],
                )


class KontoViewSet(viewsets.ModelViewSet):
    serializer_class   = KontoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [filters.SearchFilter, filters.OrderingFilter]
    search_fields      = ['kontonummer', 'kontoname']
    ordering_fields    = ['kontonummer', 'kontoart', 'abrechnungsart']
    ordering           = ['kontonummer']

    def get_queryset(self):
        qs = Konto.objects.select_related('wirtschaftsjahr__objekt')
        p = self.request.query_params
        if p.get('wirtschaftsjahr'):
            qs = qs.filter(wirtschaftsjahr_id=p['wirtschaftsjahr'])
        elif p.get('objekt'):
            from apps.objekte.models import Wirtschaftsjahr
            wj = (
                Wirtschaftsjahr.objects.filter(objekt_id=p['objekt'], status='offen')
                .order_by('-jahr').first()
                or Wirtschaftsjahr.objects.filter(objekt_id=p['objekt'])
                .order_by('-jahr').first()
            )
            qs = qs.filter(wirtschaftsjahr=wj) if wj else qs.filter(wirtschaftsjahr__objekt_id=p['objekt'])
        if p.get('kontoart'):
            qs = qs.filter(kontoart=p['kontoart'])
        if p.get('abrechnungsart'):
            qs = qs.filter(abrechnungsart=p['abrechnungsart'])
        if p.get('aktiv') is not None:
            qs = qs.filter(aktiv=p['aktiv'] == 'true')
        return qs

    @action(detail=False, methods=['post'], url_path='weg-vorlage')
    def weg_vorlage(self, request):
        """Lädt Musterkontenrahmen WEG (70 Konten) für ein WJ oder Objekt nach."""
        wj_id     = request.data.get('wirtschaftsjahr') or request.query_params.get('wirtschaftsjahr')
        objekt_id = request.data.get('objekt') or request.query_params.get('objekt')
        if not wj_id and not objekt_id:
            return Response({'error': 'wirtschaftsjahr oder objekt erforderlich'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            result = kontenrahmen_anlegen(wirtschaftsjahr_id=wj_id, objekt_id=objekt_id)
            return Response(result)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], url_path='bebuchte')
    def bebuchte(self, request):
        """
        Alle Sachkonten eines Objekts mit mindestens einer Buchung,
        inkl. Soll-/Haben-Summen und Saldo.
        """
        from django.db.models import Q, Sum
        from apps.buchhaltung.models import Buchung

        objekt_id = request.query_params.get('objekt')
        if not objekt_id:
            return Response({'error': 'objekt erforderlich'}, status=status.HTTP_400_BAD_REQUEST)

        # Konten-IDs die in Buchungen vorkommen (soll oder haben)
        buchungen = Buchung.objects.filter(objekt_id=objekt_id)
        if wj_id := request.query_params.get('wirtschaftsjahr'):
            buchungen = buchungen.filter(wirtschaftsjahr_id=wj_id)
        buchungen = buchungen.exclude(status='storniert')

        soll_ids = set(
            buchungen.exclude(soll_konto__isnull=True)
            .values_list('soll_konto_id', flat=True)
        )
        haben_ids = set(
            buchungen.exclude(haben_konto__isnull=True)
            .values_list('haben_konto_id', flat=True)
        )
        alle_ids = soll_ids | haben_ids

        if not alle_ids:
            return Response([])

        konten = Konto.objects.filter(id__in=alle_ids).order_by('kontonummer')

        # Pro Kontonummer nur einen Eintrag ausgeben (neuestes WJ gewinnt).
        # Mehrere Konto-Instanzen mit gleicher Nummer entstehen, wenn der
        # Kontenrahmen für mehrere Wirtschaftsjahre desselben Objekts angelegt wurde.
        seen: dict[str, dict] = {}
        for k in konten:
            soll_summe = (
                buchungen.filter(soll_konto=k)
                .aggregate(s=Sum('betrag'))['s'] or Decimal('0.00')
            )
            haben_summe = (
                buchungen.filter(haben_konto=k)
                .aggregate(s=Sum('betrag'))['s'] or Decimal('0.00')
            )
            if k.kontonummer in seen:
                seen[k.kontonummer]['soll_summe'] += float(soll_summe)
                seen[k.kontonummer]['haben_summe'] += float(haben_summe)
                seen[k.kontonummer]['saldo'] = (
                    seen[k.kontonummer]['soll_summe'] - seen[k.kontonummer]['haben_summe']
                )
            else:
                seen[k.kontonummer] = {
                    'id': str(k.id),
                    'kontonummer': k.kontonummer,
                    'kontoname': k.kontoname,
                    'kontoart': k.kontoart,
                    'abrechnungsart': k.abrechnungsart or '',
                    'soll_summe': float(soll_summe),
                    'haben_summe': float(haben_summe),
                    'saldo': float(soll_summe - haben_summe),
                }
        result = list(seen.values())

        return Response(result)

    @action(detail=True, methods=['get'], url_path='kontoauszug')
    def kontoauszug(self, request, pk=None):
        """
        Buchungen eines Sachkontos chronologisch mit laufendem Saldo.
        Soll-Buchungen: dieses Konto auf Soll-Seite (Belastung).
        Haben-Buchungen: dieses Konto auf Haben-Seite (Gutschrift).
        """
        from django.db.models import Q
        from apps.buchhaltung.models import Buchung

        konto = self.get_object()

        qs = Buchung.objects.filter(
            Q(soll_konto=konto) | Q(haben_konto=konto),
            objekt=konto.objekt,
        ).exclude(status='storniert')
        if wj_id := request.query_params.get('wirtschaftsjahr'):
            qs = qs.filter(wirtschaftsjahr_id=wj_id)
        buchungen = qs.select_related(
            'soll_konto', 'haben_konto',
            'soll_unterkonto', 'personenkonto',
            'buchungsart',
        ).order_by('buchungsdatum', 'erstellt_am')

        saldo = Decimal('0.00')
        positionen = []
        for b in buchungen:
            ist_soll = b.soll_konto_id == konto.pk
            if ist_soll:
                soll = b.betrag
                haben = Decimal('0.00')
                # Gegenkonto: haben_konto, Personenkonto oder Unterkonto
                if b.haben_konto:
                    gegenkonto = f"{b.haben_konto.kontonummer} {b.haben_konto.kontoname}"
                elif b.personenkonto:
                    gegenkonto = f"{b.personenkonto.kontonummer} {b.personenkonto.eigentuemer.name}"
                else:
                    gegenkonto = '—'
            else:
                soll = Decimal('0.00')
                haben = b.betrag
                # Gegenkonto: soll_konto oder soll_unterkonto
                if b.soll_unterkonto:
                    uk = b.soll_unterkonto
                    gegenkonto = f"{uk.volle_kontonummer} {uk.bezeichnung}"
                elif b.soll_konto:
                    gegenkonto = f"{b.soll_konto.kontonummer} {b.soll_konto.kontoname}"
                elif b.personenkonto:
                    gegenkonto = f"{b.personenkonto.kontonummer} {b.personenkonto.eigentuemer.name}"
                else:
                    gegenkonto = '—'

            saldo += soll - haben
            bu_nr = b.belegnr or f'BU-{str(b.id)[:8].upper()}'
            positionen.append({
                'id': str(b.id),
                'bu_nr': bu_nr,
                'buchungsdatum': str(b.buchungsdatum),
                'buchungstext': b.buchungstext,
                'gegenkonto': gegenkonto,
                'soll': float(soll) if soll else None,
                'haben': float(haben) if haben else None,
                'saldo': float(saldo),
            })

        return Response({
            'konto': {
                'id': str(konto.id),
                'kontonummer': konto.kontonummer,
                'kontoname': konto.kontoname,
            },
            'saldo_gesamt': float(saldo),
            'positionen': positionen,
        })


def _sepa_mandat_data(mandat):
    if not mandat:
        return None
    return {
        'id': str(mandat.id),
        'mandatsreferenz': mandat.mandatsreferenz,
        'iban': mandat.iban,
        'bic': mandat.bic,
        'unterzeichnet_am': str(mandat.unterzeichnet_am),
        'aktiv': mandat.aktiv,
    }


class PersonenkontoViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class   = PersonenkontoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [filters.OrderingFilter]
    ordering           = ['kontonummer']

    def get_queryset(self):
        qs = Personenkonto.objects.select_related(
            'objekt', 'eigentuemer', 'eigentuemer__sepa_mandat', 'vertrag'
        ).prefetch_related('unterkonten')
        p = self.request.query_params
        if p.get('objekt'):
            qs = qs.filter(objekt_id=p['objekt'])
        if p.get('status'):
            qs = qs.filter(status=p['status'])
        return qs

    @action(detail=False, methods=['get'], url_path='mit-saldo')
    def mit_saldo(self, request):
        """
        Gibt alle Personenkonten eines Objekts zurück inkl. Saldo.
        Soll = Nebenbuch (HausgeldSollstellung.soll_betrag, nicht storniert).
        Haben = Zahlungseingänge (Buchung mit soll_konto gesetzt, verknüpft via Personenkonto).
        """
        from django.db.models import Sum
        from apps.buchhaltung.models import Buchung, HausgeldSollstellung

        objekt_id = request.query_params.get('objekt')
        if not objekt_id:
            return Response({'error': 'objekt erforderlich'}, status=status.HTTP_400_BAD_REQUEST)

        pks = (
            Personenkonto.objects
            .filter(objekt_id=objekt_id)
            .select_related('eigentuemer', 'eigentuemer__sepa_mandat', 'vertrag__einheit')
            .order_by('kontonummer')
        )

        ev_ids = [pk.vertrag_id for pk in pks if pk.vertrag_id]
        pk_ids  = [pk.id for pk in pks]
        wj_id   = request.query_params.get('wirtschaftsjahr')

        # Soll aus Nebenbuch: Summe der nicht-stornierten Sollstellungen je EV
        ss_qs = (
            HausgeldSollstellung.objects
            .filter(eigentumsverhaeltnis_id__in=ev_ids, storniert_am__isnull=True)
        )
        if wj_id:
            from apps.objekte.models import Wirtschaftsjahr
            try:
                wj = Wirtschaftsjahr.objects.get(pk=wj_id)
                ss_qs = ss_qs.filter(periode__year=wj.jahr)
            except Wirtschaftsjahr.DoesNotExist:
                pass
        soll_per_ev = dict(
            ss_qs.values('eigentumsverhaeltnis_id')
            .annotate(s=Sum('soll_betrag'))
            .values_list('eigentumsverhaeltnis_id', 's')
        )

        # Haben aus Buchungen (Zahlungseingänge)
        haben_qs = (
            Buchung.objects
            .filter(personenkonto_id__in=pk_ids, soll_konto__isnull=False, parent_buchung__isnull=True)
            .exclude(status='storniert')
        )
        if wj_id:
            haben_qs = haben_qs.filter(wirtschaftsjahr_id=wj_id)
        haben_per_pk = dict(
            haben_qs.values('personenkonto_id').annotate(s=Sum('betrag')).values_list('personenkonto_id', 's')
        )

        result = []
        for pk in pks:
            soll  = soll_per_ev.get(pk.vertrag_id) or Decimal('0')
            haben = haben_per_pk.get(pk.id) or Decimal('0')
            saldo = soll - haben
            einheit_nr = ''
            try:
                einheit_nr = pk.vertrag.einheit.einheit_nr
            except Exception:
                pass
            result.append({
                'id': str(pk.id),
                'kontonummer': pk.kontonummer,
                'eigentuemer_id': str(pk.eigentuemer.id),
                'eigentuemer_name': pk.eigentuemer.name,
                'eigentuemer_ibans': pk.eigentuemer.ibans or [],
                'einheit_nr': einheit_nr,
                'status': pk.status,
                'saldo_offen': float(saldo),
                'sepa_mandat': _sepa_mandat_data(pk.eigentuemer.sepa_mandat),
            })

        return Response(result)

    @action(detail=True, methods=['get'], url_path='kontoauszug')
    def kontoauszug(self, request, pk=None):
        """
        Kontoauszug eines Personenkontos (Debitorensicht).
        Soll  = Forderungen aus dem Nebenbuch (HausgeldSollstellung).
        Haben = Zahlungseingänge (Buchung, verknüpft via Personenkonto oder SollstellungZahlung).
        Beide Listen werden nach Datum gemischt und chronologisch sortiert.
        """
        from apps.buchhaltung.models import Buchung, HausgeldSollstellung

        pk_obj = self.get_object()
        ev = pk_obj.vertrag
        wj_id = request.query_params.get('wirtschaftsjahr')

        # --- Soll-Seite: Sollstellungen aus Nebenbuch ---
        ss_qs = (
            HausgeldSollstellung.objects
            .filter(eigentumsverhaeltnis=ev, storniert_am__isnull=True)
            .select_related('sollstellungslauf')
            .order_by('periode', 'erstellt_am')
        )
        if wj_id:
            from apps.objekte.models import Wirtschaftsjahr
            try:
                wj = Wirtschaftsjahr.objects.get(pk=wj_id)
                ss_qs = ss_qs.filter(periode__year=wj.jahr)
            except Wirtschaftsjahr.DoesNotExist:
                pass

        # --- Haben-Seite: Zahlungseingänge (Buchungen) ---
        haben_qs = (
            Buchung.objects
            .filter(personenkonto=pk_obj, soll_konto__isnull=False, parent_buchung__isnull=True)
            .exclude(status='storniert')
        )
        if wj_id:
            haben_qs = haben_qs.filter(wirtschaftsjahr_id=wj_id)
        haben_qs = haben_qs.order_by('buchungsdatum', 'erstellt_am')

        # Einträge zusammenführen und chronologisch sortieren
        eintraege = []
        for ss in ss_qs:
            typ_label = {'hausgeld': 'Hausgeld', 'sonderumlage': 'Sonderumlage', 'abrechnungsergebnis': 'Abrechnung'}.get(ss.sollstellungs_typ, ss.sollstellungs_typ)
            eintraege.append({
                '_datum': ss.periode,
                '_sort2': ss.erstellt_am,
                'id': str(ss.id),
                'typ': 'sollstellung',
                'opos_nr': ss.opos_nr,
                'bu_nr': ss.opos_nr,
                'buchungsdatum': str(ss.periode),
                'buchungstext': f"{typ_label} {ss.periode.strftime('%m/%Y')}",
                'soll': float(ss.soll_betrag) if ss.soll_betrag > 0 else None,
                'haben': float(abs(ss.soll_betrag)) if ss.soll_betrag < 0 else None,
                'hat_detail': False,
                'status': ss.status_cached,
                'ist_betrag': float(ss.ist_betrag),
            })
        for b in haben_qs:
            eintraege.append({
                '_datum': b.buchungsdatum,
                '_sort2': b.erstellt_am,
                'id': str(b.id),
                'typ': 'buchung',
                'opos_nr': None,
                'bu_nr': b.belegnr or f'BU-{str(b.id)[:8].upper()}',
                'buchungsdatum': str(b.buchungsdatum),
                'buchungstext': b.buchungstext,
                'soll': None,
                'haben': float(b.betrag),
                'hat_detail': b.teilbuchungen.exists(),
                'status': None,
                'ist_betrag': None,
            })

        eintraege.sort(key=lambda x: (x['_datum'], x['_sort2'] or ''))

        saldo = Decimal('0.00')
        positionen = []
        for e in eintraege:
            soll_val  = Decimal(str(e['soll']))  if e['soll']  is not None else Decimal('0')
            haben_val = Decimal(str(e['haben'])) if e['haben'] is not None else Decimal('0')
            saldo += soll_val - haben_val
            e['saldo'] = float(saldo)
            e.pop('_datum')
            e.pop('_sort2')
            positionen.append(e)

        einheit_nr = ''
        try:
            einheit_nr = pk_obj.vertrag.einheit.einheit_nr
        except Exception:
            pass

        return Response({
            'personenkonto': {
                'id': str(pk_obj.id),
                'kontonummer': pk_obj.kontonummer,
                'eigentuemer_name': pk_obj.eigentuemer.name,
                'einheit_nr': einheit_nr,
                'status': pk_obj.status,
            },
            'saldo_gesamt': float(saldo),
            'positionen': positionen,
        })

    @action(detail=True, methods=['get'], url_path='buchung-detail')
    def buchung_detail(self, request, pk=None):
        """
        Gibt die Teilbuchungen einer Gesamt-Buchung zurück (Abrechnungsarten-Aufschlüsselung).
        Query-Parameter: buchung_id=<UUID der Gesamt-Buchung>
        """
        from apps.buchhaltung.models import Buchung

        buchung_id = request.query_params.get('buchung_id')
        if not buchung_id:
            return Response({'error': 'buchung_id erforderlich'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            gesamt = Buchung.objects.get(pk=buchung_id, parent_buchung__isnull=True)
        except Buchung.DoesNotExist:
            return Response({'error': 'Buchung nicht gefunden'}, status=status.HTTP_404_NOT_FOUND)

        teilbuchungen = (
            gesamt.teilbuchungen
            .select_related('haben_konto', 'soll_unterkonto', 'buchungsart')
            .order_by('soll_unterkonto__suffix')
        )

        positionen = []
        for t in teilbuchungen:
            uk = t.soll_unterkonto
            positionen.append({
                'id': str(t.id),
                'soll_unterkonto': uk.volle_kontonummer if uk else None,
                'soll_unterkonto_bezeichnung': uk.bezeichnung if uk else '',
                'haben_konto': t.haben_konto.kontonummer if t.haben_konto else '',
                'haben_konto_name': t.haben_konto.kontoname if t.haben_konto else '',
                'ba': t.buchungsart.kuerzel if t.buchungsart else '',
                'betrag': float(t.betrag),
            })

        return Response({
            'bu_nr': gesamt.belegnr,
            'buchungsdatum': str(gesamt.buchungsdatum),
            'gesamt_betrag': float(gesamt.betrag),
            'positionen': positionen,
        })


    @action(detail=True, methods=['post'], url_path='zahlungseingang')
    def zahlungseingang(self, request, pk=None):
        """
        Bucht einen manuellen Zahlungseingang gegen offene Sollstellungen im Nebenbuch.
        Body: { bank_sachkonto_id, betrag, buchungsdatum, buchungstext?, wirtschaftsjahr_id? }
        """
        from decimal import Decimal
        from apps.buchhaltung.services.zahlungs_zuordnung_service import verrechne_eingang_manuell
        from apps.konten.models import Konto
        from apps.objekte.models import Wirtschaftsjahr

        pk_obj = self.get_object()

        bank_konto_id  = request.data.get('bank_sachkonto_id')
        betrag_raw     = request.data.get('betrag')
        buchungsdatum  = request.data.get('buchungsdatum')
        buchungstext   = request.data.get('buchungstext', '')
        wj_id          = request.data.get('wirtschaftsjahr_id')

        if not bank_konto_id or not betrag_raw or not buchungsdatum:
            return Response(
                {'error': 'bank_sachkonto_id, betrag und buchungsdatum sind erforderlich'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            betrag = Decimal(str(betrag_raw))
            if betrag <= 0:
                raise ValueError
        except (ValueError, Exception):
            return Response({'error': 'Ungültiger Betrag'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            bank_konto = Konto.objects.get(pk=bank_konto_id)
        except Konto.DoesNotExist:
            return Response({'error': 'Sachkonto nicht gefunden'}, status=status.HTTP_404_NOT_FOUND)

        wj = None
        if wj_id:
            wj = Wirtschaftsjahr.objects.filter(pk=wj_id).first()
        if not wj:
            obj = pk_obj.objekt
            wj = (
                Wirtschaftsjahr.objects.filter(objekt=obj, status='offen').order_by('-jahr').first()
                or Wirtschaftsjahr.objects.filter(objekt=obj).order_by('-jahr').first()
            )

        try:
            buchung = verrechne_eingang_manuell(
                personenkonto=pk_obj,
                bank_sachkonto=bank_konto,
                betrag=betrag,
                buchungsdatum=buchungsdatum,
                buchungstext=buchungstext,
                wirtschaftsjahr=wj,
                user=request.user,
            )
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'buchung_id': str(buchung.id),
            'betrag': float(buchung.betrag),
            'nachricht': f'Zahlungseingang {float(betrag):.2f} EUR erfolgreich gebucht.',
        }, status=status.HTTP_201_CREATED)


class UnterkontoViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class   = UnterkontoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Unterkonto.objects.select_related('personenkonto')
        if self.request.query_params.get('personenkonto'):
            qs = qs.filter(personenkonto_id=self.request.query_params['personenkonto'])
        return qs
