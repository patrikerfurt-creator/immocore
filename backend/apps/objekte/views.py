import csv
import io

from django.db.models import Q
from django.http import HttpResponse
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Objekt, Eingang, Bankkonto, Einheit, Verteilerschluessel, VerteilerschluesselWert
from .serializers import (
    ObjektSerializer, ObjektListSerializer,
    EingangSerializer, BankkontoSerializer, EinheitSerializer,
    VerteilerschluesselSerializer, VerteilerschluesselWertSerializer,
)


class ObjektViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['bezeichnung', 'strasse', 'ort']
    ordering_fields = ['bezeichnung', 'objekt_typ', 'status']
    ordering = ['bezeichnung']

    def get_queryset(self):
        qs = Objekt.objects.prefetch_related('eingaenge', 'bankkonten', 'einheiten')
        typ = self.request.query_params.get('typ')
        status = self.request.query_params.get('status')
        if typ:
            qs = qs.filter(objekt_typ=typ)
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return ObjektListSerializer
        return ObjektSerializer

    @action(detail=True, methods=['get'], url_path='vertraege/csv-vorlage')
    def vertraege_csv_vorlage(self, request, pk=None):
        """
        CSV-Vorlage für Vertragsmanagement-Import herunterladen.
        Vorbelegt mit Einheiten und Abrechnungsarten des Objekts.
        """
        objekt = self.get_object()
        from apps.konten.models import Abrechnungsart
        from apps.personen.models import EigentumsVerhaeltnis

        einheiten = list(objekt.einheiten.order_by('einheit_nr'))
        abrechnungsarten = list(
            Abrechnungsart.objects.filter(objekt=objekt, aktiv=True).order_by('code')
        )

        # Aktive Verträge vorbeladen: einheit_id → Person
        ev_person_map = {
            ev.einheit_id: ev.person
            for ev in EigentumsVerhaeltnis.objects.filter(
                einheit__objekt=objekt, ende__isnull=True
            ).select_related('person')
        }

        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        writer.writerow([
            'einheit_nr', 'flaechennummer', 'personennummer', 'eigentuemer_email',
            'vertrag_beginn', 'vertrag_ende',
            'abrechnungsart', 'betrag', 'gueltig_ab', 'wirtschaftsplan_jahr', 'bemerkung',
        ])

        today = __import__('datetime').date.today()
        for einheit in einheiten:
            person = ev_person_map.get(einheit.pk)
            personennummer = person.personennummer if person else ''
            email = person.email if person else ''
            for abr in abrechnungsarten:
                writer.writerow([
                    einheit.einheit_nr, einheit.flaechennummer,
                    personennummer, email,
                    today.strftime('%Y-01-01'), '',
                    abr.code, '0.00', today.strftime('%Y-01-01'), today.year, '',
                ])

        if not einheiten:
            writer.writerow(['WE01', '', '100000', 'eigentuemer@example.de', '2025-01-01', '', '900', '250.00', '2025-01-01', '2025', ''])

        dateiname = f'{objekt.objektnummer}-Vertraege.csv'
        response = HttpResponse(
            output.getvalue().encode('utf-8-sig'),
            content_type='text/csv; charset=utf-8-sig',
        )
        response['Content-Disposition'] = f'attachment; filename="{dateiname}"'
        return response

    @action(detail=True, methods=['post'], url_path='vertraege/csv-preview')
    def vertraege_csv_preview(self, request, pk=None):
        """
        CSV hochladen, parsen und validieren. Keine DB-Änderung.
        Antwort: { zusammenfassung, zeilen }
        """
        objekt = self.get_object()
        datei = request.FILES.get('datei')
        if not datei:
            return Response({'error': 'datei erforderlich'}, status=status.HTTP_400_BAD_REQUEST)

        from apps.personen.services.vertragsimport import parse_csv, vorschau, ImportFehler

        try:
            zeilen_roh = parse_csv(datei.read())
        except ImportFehler as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        ergebnisse = vorschau(zeilen_roh, objekt)

        from dataclasses import asdict
        zeilen_data = [asdict(z) for z in ergebnisse]

        zusammenfassung = {
            'zeilen_gesamt':  len(ergebnisse),
            'zeilen_ok':      sum(1 for z in ergebnisse if z.status == 'ok'),
            'zeilen_warnung': sum(1 for z in ergebnisse if z.status == 'warnung'),
            'zeilen_fehler':  sum(1 for z in ergebnisse if z.status == 'fehler'),
        }

        return Response({
            'objekt': {'id': str(objekt.id), 'bezeichnung': objekt.bezeichnung, 'objekt_nr': objekt.objektnummer},
            'zusammenfassung': zusammenfassung,
            'zeilen': zeilen_data,
        })

    @action(detail=True, methods=['post'], url_path='vertraege/csv-commit')
    def vertraege_csv_commit(self, request, pk=None):
        """
        CSV hochladen und atomar importieren.
        Bei Fehler in einer Zeile vollständiger Rollback.
        """
        objekt = self.get_object()
        datei = request.FILES.get('datei')
        if not datei:
            return Response({'error': 'datei erforderlich'}, status=status.HTTP_400_BAD_REQUEST)

        from apps.personen.services.vertragsimport import parse_csv, commit, ImportFehler

        try:
            zeilen_roh = parse_csv(datei.read())
        except ImportFehler as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            ergebnis = commit(zeilen_roh, objekt, request.user)
        except ImportFehler as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        from dataclasses import asdict
        return Response(
            {
                'status': ergebnis.status,
                'zusammenfassung': ergebnis.zusammenfassung,
                'zeilen': [asdict(z) for z in ergebnis.zeilen],
            },
            status=status.HTTP_200_OK,
        )


class EingangViewSet(viewsets.ModelViewSet):
    serializer_class = EingangSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Eingang.objects.select_related('objekt')
        objekt_id = self.request.query_params.get('objekt')
        if objekt_id:
            qs = qs.filter(objekt_id=objekt_id)
        return qs


class BankkontoViewSet(viewsets.ModelViewSet):
    serializer_class = BankkontoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Bankkonto.objects.select_related('objekt')
        objekt_id = self.request.query_params.get('objekt')
        if objekt_id:
            qs = qs.filter(objekt_id=objekt_id)
        return qs


class VerteilerschluesselViewSet(viewsets.ModelViewSet):
    serializer_class = VerteilerschluesselSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering = ['reihenfolge', 'bezeichnung']

    def get_queryset(self):
        qs = Verteilerschluessel.objects.select_related('objekt').prefetch_related('werte__einheit')
        objekt_id = self.request.query_params.get('objekt')
        if objekt_id:
            qs = qs.filter(objekt_id=objekt_id)
        return qs

    @action(detail=True, methods=['post'], url_path='wert-setzen')
    def wert_setzen(self, request, pk=None):
        """
        Wert für eine Einheit setzen oder aktualisieren.
        Body: { einheit: UUID, wert: Decimal }
        """
        schluessel = self.get_object()
        einheit_id = request.data.get('einheit')
        wert = request.data.get('wert')

        if not einheit_id or wert is None:
            return Response(
                {'error': 'einheit und wert erforderlich'},
                status=status.HTTP_400_BAD_REQUEST
            )

        obj, created = VerteilerschluesselWert.objects.update_or_create(
            schluessel=schluessel,
            einheit_id=einheit_id,
            defaults={'wert': wert},
        )
        return Response(
            VerteilerschluesselWertSerializer(obj).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


class VerteilerschluesselWertViewSet(viewsets.ModelViewSet):
    serializer_class = VerteilerschluesselWertSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = VerteilerschluesselWert.objects.select_related('schluessel', 'einheit')
        schluessel_id = self.request.query_params.get('schluessel')
        einheit_id = self.request.query_params.get('einheit')
        if schluessel_id:
            qs = qs.filter(schluessel_id=schluessel_id)
        if einheit_id:
            qs = qs.filter(einheit_id=einheit_id)
        return qs


# ---------------------------------------------------------------------------
# Einheiten-CSV-Import — Hilfsfunktionen
# ---------------------------------------------------------------------------

CSV_SPALTEN = [
    'Objektnummer',
    'Eingang',
    'Flächennummer',
    'Bez. Einheit',
    'Einheit-Typ',
    'Lage',
]

EINHEIT_TYP_MAP = {
    '100': 'Wohnung',
    '200': 'Gewerbe',
    '300': 'Stellplatz',
    '400': 'Sonstiges',
}
EINHEIT_TYP_CHOICES = list(EINHEIT_TYP_MAP.keys())


def _parse_einheiten_csv(raw: bytes) -> tuple[list, str | None]:
    """
    CSV parsen, Pflichtfelder + Objekt/Eingang gegen DB prüfen.
    Gibt (rows, global_error) zurück — global_error ist None wenn Parsing ok.
    Kein DB-Commit.
    """
    inhalt = None
    for enc in ('utf-8-sig', 'cp1252', 'latin-1'):
        try:
            inhalt = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if inhalt is None:
        return [], 'Datei konnte nicht dekodiert werden (unterstützte Encodings: UTF-8, cp1252, Latin-1)'

    lines = [l.lstrip('﻿').strip() for l in inhalt.splitlines()]
    lines = [l for l in lines if l and not l.startswith('#')]
    if not lines:
        return [], 'CSV leer oder ungültig'

    try:
        dialect = csv.Sniffer().sniff('\n'.join(lines[:3]), delimiters=';,\t')
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ';'

    reader = csv.DictReader(io.StringIO('\n'.join(lines)), delimiter=delimiter)
    if reader.fieldnames:
        reader.fieldnames = [f.lstrip('﻿').strip() for f in reader.fieldnames]
    if reader.fieldnames is None:
        return [], 'CSV leer oder ungültig'

    rows = []
    objekt_cache: dict = {}
    eingang_cache: dict = {}
    flaechennr_csv_set: set = set()   # (objekt_id, flaechennr) in dieser Datei
    flaechennr_db_cache: dict = {}    # objekt_id → set bereits in DB

    for zeile_nr, zeile in enumerate(reader, start=2):
        objekt_nr   = zeile.get('Objektnummer', '').strip()
        eingang_bez = zeile.get('Eingang', '').strip()
        flaechennr  = zeile.get('Flächennummer', '').strip()
        bez_einheit = zeile.get('Bez. Einheit', '').strip()
        typ_code    = (zeile.get('Einheit-Typ') or zeile.get('Einheit Typ') or '').strip() or '100'
        lage        = zeile.get('Lage', '').strip()

        if objekt_nr.startswith('#'):
            continue

        fehler: list[str] = []

        if not objekt_nr:
            fehler.append('Objektnummer fehlt')
        if not bez_einheit:
            fehler.append('Bez. Einheit fehlt')

        einheit_typ = EINHEIT_TYP_MAP.get(typ_code)
        if not einheit_typ:
            fehler.append(
                f'Ungültiger Einheit-Typ "{typ_code}" — erlaubt: '
                '100=Wohnung, 200=Gewerbe, 300=Stellplatz, 400=Sonstiges'
            )

        objekt_id  = None
        eingang_id = None

        if objekt_nr and not fehler:
            if objekt_nr not in objekt_cache:
                try:
                    objekt_cache[objekt_nr] = Objekt.objects.get(objektnummer=objekt_nr)
                except Objekt.DoesNotExist:
                    objekt_cache[objekt_nr] = None
            obj = objekt_cache[objekt_nr]
            if obj is None:
                fehler.append(f'Objekt "{objekt_nr}" nicht gefunden')
            else:
                objekt_id = str(obj.id)

                if flaechennr:
                    csv_key = (objekt_id, flaechennr)
                    if csv_key in flaechennr_csv_set:
                        fehler.append(
                            f'Flächennummer "{flaechennr}" kommt in dieser Datei mehrfach vor'
                        )
                    else:
                        flaechennr_csv_set.add(csv_key)
                        if objekt_id not in flaechennr_db_cache:
                            flaechennr_db_cache[objekt_id] = set(
                                Einheit.objects.filter(objekt_id=objekt_id)
                                .exclude(flaechennummer='')
                                .values_list('flaechennummer', flat=True)
                            )
                        if flaechennr in flaechennr_db_cache[objekt_id]:
                            fehler.append(
                                f'Flächennummer "{flaechennr}" existiert bereits in Objekt "{objekt_nr}"'
                            )

                if eingang_bez:
                    cache_key = f'{objekt_nr}|{eingang_bez}'
                    if cache_key not in eingang_cache:
                        eg = Eingang.objects.filter(
                            Q(strasse__iexact=eingang_bez) | Q(bezeichnung__iexact=eingang_bez),
                            objekt=obj,
                        ).first()
                        eingang_cache[cache_key] = eg
                    eg = eingang_cache[f'{objekt_nr}|{eingang_bez}']
                    if eg is None:
                        fehler.append(f'Eingang "{eingang_bez}" in Objekt "{objekt_nr}" nicht gefunden')
                    else:
                        eingang_id = str(eg.id)

        rows.append({
            'zeile':  zeile_nr,
            'status': 'fehler' if fehler else 'ok',
            'fehler': fehler,
            'daten': {
                'objekt_nr':      objekt_nr,
                'objekt_id':      objekt_id,
                'eingang_bez':    eingang_bez,
                'eingang_id':     eingang_id,
                'flaechennummer': flaechennr,
                'einheit_nr':     bez_einheit,
                'einheit_typ':    einheit_typ or '',
                'lage':           lage,
            },
        })

    return rows, None


# ---------------------------------------------------------------------------
# EinheitViewSet
# ---------------------------------------------------------------------------

class EinheitViewSet(viewsets.ModelViewSet):
    serializer_class = EinheitSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['einheit_nr', 'lage', 'flaechennummer']
    ordering_fields = ['einheit_nr', 'einheit_typ', 'flaechennummer']
    ordering = ['einheit_nr']

    def get_queryset(self):
        qs = Einheit.objects.select_related('objekt', 'eingang')
        objekt_id = self.request.query_params.get('objekt')
        if objekt_id:
            qs = qs.filter(objekt_id=objekt_id)
        return qs

    @action(detail=False, methods=['get'], url_path='csv-vorlage')
    def csv_vorlage(self, request):
        """
        CSV-Importvorlage herunterladen.
        ?objekt=UUID — Objektnummer und Eingänge werden vorausgefüllt.
        """
        objekt_param = request.query_params.get('objekt')
        objekt = None
        eingaenge = []

        if objekt_param:
            try:
                objekt = Objekt.objects.prefetch_related('eingaenge').get(pk=objekt_param)
                eingaenge = list(objekt.eingaenge.order_by('bezeichnung'))
            except Objekt.DoesNotExist:
                return Response(
                    {'error': f'Objekt nicht gefunden'},
                    status=status.HTTP_404_NOT_FOUND
                )

        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        writer.writerow(['# Einheit-Typ: 100=Wohnung | 200=Gewerbe | 300=Stellplatz | 400=Sonstiges'])
        writer.writerow(CSV_SPALTEN)

        if objekt and eingaenge:
            for eingang in eingaenge:
                writer.writerow([objekt.objektnummer, eingang.strasse, '', '', '100', ''])
        elif objekt:
            writer.writerow([objekt.objektnummer, '', '', '', '100', ''])
        else:
            writer.writerow(['# Objektnummer', '# Eingang', '# z.B. 100001', '# z.B. 1', '# 100', '# z.B. EG links'])

        dateiname = f'{objekt.objektnummer if objekt else "leer"}-Einheiten.csv'
        response = HttpResponse(
            output.getvalue().encode('utf-8-sig'),
            content_type='text/csv; charset=utf-8-sig'
        )
        response['Content-Disposition'] = f'attachment; filename="{dateiname}"'
        return response

    @action(detail=False, methods=['post'], url_path='csv-vorschau')
    def csv_vorschau(self, request):
        """
        CSV-Datei validieren und Vorschau zurückgeben. Kein DB-Commit.
        Antwort: { rows, ok_anzahl, fehler_anzahl, gesamt }
        """
        datei = request.FILES.get('datei')
        if not datei:
            return Response({'error': 'datei erforderlich'}, status=status.HTTP_400_BAD_REQUEST)

        rows, global_error = _parse_einheiten_csv(datei.read())
        if global_error:
            return Response({'error': global_error}, status=status.HTTP_400_BAD_REQUEST)

        ok_anzahl     = sum(1 for r in rows if r['status'] == 'ok')
        fehler_anzahl = sum(1 for r in rows if r['status'] == 'fehler')

        return Response({
            'rows':          rows,
            'ok_anzahl':     ok_anzahl,
            'fehler_anzahl': fehler_anzahl,
            'gesamt':        len(rows),
        })

    @action(detail=False, methods=['post'], url_path='csv-import')
    def csv_import(self, request):
        """
        Vorgeprüfte Rows aus csv-vorschau importieren. Kein direkter Datei-Upload.
        Body: { rows: [...] }
        Rows mit status='fehler' werden übersprungen.
        """
        rows = request.data.get('rows')
        if not rows:
            return Response(
                {'error': 'rows fehlt — Datei zuerst mit csv-vorschau prüfen'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from apps.konten.services import verteilerschluessel_anlegen

        angelegt    = 0
        fehler      = []
        objekt_ids  = set()

        for row in rows:
            if row.get('status') == 'fehler':
                continue
            daten = row.get('daten', {})
            try:
                Einheit.objects.create(
                    objekt_id=daten['objekt_id'],
                    eingang_id=daten.get('eingang_id') or None,
                    flaechennummer=daten.get('flaechennummer', ''),
                    einheit_nr=daten['einheit_nr'],
                    lage=daten.get('lage', ''),
                    einheit_typ=daten['einheit_typ'],
                )
                if daten.get('objekt_id'):
                    objekt_ids.add(daten['objekt_id'])
                angelegt += 1
            except Exception as exc:
                fehler.append(f'Zeile {row.get("zeile", "?")}: {exc}')

        # VSBeteiligung für alle betroffenen Objekte nachlegen
        for oid in objekt_ids:
            try:
                verteilerschluessel_anlegen(oid)
            except Exception:
                pass

        return Response(
            {'angelegt': angelegt, 'fehler_anzahl': len(fehler), 'fehler': fehler},
            status=status.HTTP_201_CREATED if angelegt > 0 else status.HTTP_400_BAD_REQUEST,
        )
