import csv
import io
import re
from datetime import datetime, timezone
from decimal import Decimal

from django.db import transaction
from django.http import HttpResponse
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.objekte.models import Objekt, Eingang, Bankkonto, Einheit, Verteilerschluessel, VerteilerschluesselWert
from apps.personen.models import Person
from apps.konten.models import Konto
from apps.konten.services import abrechnungsarten_anlegen, kontenrahmen_anlegen, ruecklagen_konten_anlegen
from .models import Prozess
from .serializers import ProzessSerializer
from .validators import ObjektAnlageValidator

try:
    from apps.buchhaltung.models import EigentuemerwechselVorgang
    from apps.buchhaltung.services.eigentuemerwechsel_service import analysiere_wechsel, commite_wechsel
    _EW_AVAILABLE = True
except ImportError:
    _EW_AVAILABLE = False


_NR_RANGES = {
    'WEG': (10001, 29999),
    'ZH':  (30001, 49999),
    'SEV': (50001, 69999),
}


def _get_next_objektnummer(objekt_typ: str) -> str:
    """Reserviert die nächste freie 5-stellige Objektnummer für den Wizard.
    WEG: 10001–29999, ZH: 30001–49999, SEV: 50001–69999
    Berücksichtigt bestehende Objekte UND laufende Prozesse.
    """
    start, max_nr = _NR_RANGES.get(objekt_typ, (10001, 29999))

    existing = (
        Objekt.objects
        .filter(objekt_typ=objekt_typ)
        .exclude(objektnummer='')
        .order_by('-objektnummer')
        .values_list('objektnummer', flat=True)
        .first()
    )

    process_nrs = []
    for p in Prozess.objects.filter(status='aktiv', prozess_typ='objekt_anlegen'):
        nr = (p.steps_data or {}).get('objektnummer', '')
        if nr:
            try:
                nr_int = int(nr)
                if start <= nr_int <= max_nr:
                    process_nrs.append(nr_int)
            except ValueError:
                pass

    candidates = [start]
    if existing:
        try:
            candidates.append(int(existing) + 1)
        except ValueError:
            pass
    if process_nrs:
        candidates.append(max(process_nrs) + 1)

    return str(max(candidates))


SCHRITT_DEFINITIONEN = {
    'objekt_anlegen': {
        1:  {'bezeichnung': 'Objekttyp',           'typ': 'objekttyp'},
        2:  {'bezeichnung': 'Stammdaten',           'typ': 'stammdaten'},
        3:  {'bezeichnung': 'Eingänge',             'typ': 'eingaenge'},
        4:  {'bezeichnung': 'Wirtschaftsjahr',      'typ': 'wirtschaftsjahr'},
        5:  {'bezeichnung': 'Einheiten',            'typ': 'einheiten'},
        6:  {'bezeichnung': 'Bankkonten',           'typ': 'bankkonten'},
        7:  {'bezeichnung': 'Kontenrahmen',         'typ': 'kontenrahmen'},
        8:  {'bezeichnung': 'Verträge',             'typ': 'vertraege'},
        9:  {'bezeichnung': 'Freigabelimits',       'typ': 'freigabelimits'},
        10: {'bezeichnung': 'Review & Aktivierung', 'typ': 'review'},
    },
    'eigentuemerwechsel': {i + 1: {'bezeichnung': s, 'typ': 'generic'} for i, s in enumerate([
        'Einheit & Stichtag',
        'Käufer erfassen',
        'Hausgeld-Sollwerte',
        'Sollstellungs-Analyse',
        'Vorschau & Bestätigung',
    ])},
    'jahresabrechnung': {i + 1: {'bezeichnung': s, 'typ': 'generic'} for i, s in enumerate([
        'Wirtschaftsjahr wählen', 'Buchungen prüfen', 'Kostenpositionen aufteilen',
        'Rücklagen zuordnen', 'Einzelabrechnungen berechnen', '.950-Buchungen erzeugen',
        'PDF-Vorschau', 'Abschluss & Freigabe',
    ])},
}

ZH_SEV_TYPEN = ['mieterwechsel']

FREIGABE_STANDARD = [
    {'bis': 500,   'rolle': 'auto',             'frist_tage': 0, 'beschreibung': 'Automatische Freigabe'},
    {'bis': 5000,  'rolle': 'objektmanager',    'frist_tage': 3, 'beschreibung': 'Objektmanager-Freigabe'},
    {'bis': None,  'rolle': 'geschaeftsfuehrer', 'frist_tage': 5, 'beschreibung': 'Geschäftsführer-Freigabe'},
]


class ProzessViewSet(viewsets.ModelViewSet):
    serializer_class = ProzessSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering = ['-gestartet_am']

    def get_queryset(self):
        qs = Prozess.objects.select_related('objekt', 'gestartet_von')
        objekt_id = self.request.query_params.get('objekt')
        typ = self.request.query_params.get('typ')
        status_filter = self.request.query_params.get('status')
        if objekt_id:
            qs = qs.filter(objekt_id=objekt_id)
        if typ:
            qs = qs.filter(prozess_typ=typ)
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    def create(self, request, *args, **kwargs):
        prozess_typ = request.data.get('prozess_typ', '')
        if prozess_typ in ZH_SEV_TYPEN:
            return Response(
                {'detail': 'ZH/SEV-Prozesse sind in Phase 2 geplant.'},
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )
        return super().create(request, *args, **kwargs)

    # ------------------------------------------------------------------
    # Schritte-Übersicht
    # ------------------------------------------------------------------
    @action(detail=True, methods=['get'], url_path='schritte')
    def schritte(self, request, pk=None):
        """Liefert Schrittdefinition + aktuellen Fortschritt."""
        prozess = self.get_object()
        defs = SCHRITT_DEFINITIONEN.get(prozess.prozess_typ, {})
        return Response({
            'prozess_typ': prozess.prozess_typ,
            'gesamt_schritte': len(defs),
            'aktueller_schritt': prozess.current_step,
            'schritte': [
                {
                    'nr': nr,
                    'bezeichnung': d['bezeichnung'],
                    'typ': d['typ'],
                    'erledigt': nr < prozess.current_step,
                    'aktiv': nr == prozess.current_step,
                    'daten': (prozess.steps_data or {}).get(str(nr), {}),
                }
                for nr, d in defs.items()
            ],
            'steps_data': prozess.steps_data,
        })

    # ------------------------------------------------------------------
    # Legacy schritt-speichern (kept for backwards compatibility)
    # ------------------------------------------------------------------
    @action(detail=True, methods=['post'], url_path='schritt-speichern')
    def schritt_speichern(self, request, pk=None):
        """
        Aktuellen Schritt speichern und zum nächsten wechseln.
        Body: { daten: {...} }
        """
        prozess = self.get_object()
        if prozess.status != 'aktiv':
            return Response(
                {'error': f'Prozess ist {prozess.status} — kein Fortschritt möglich'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        daten = request.data.get('daten', {})
        steps_data = prozess.steps_data or {}
        steps_data[str(prozess.current_step)] = daten

        defs = SCHRITT_DEFINITIONEN.get(prozess.prozess_typ, {})
        schritte_gesamt = len(defs)
        if prozess.current_step < schritte_gesamt:
            prozess.current_step += 1
        else:
            prozess.status = 'abgeschlossen'
            prozess.abgeschlossen_am = datetime.now(timezone.utc)

        prozess.steps_data = steps_data
        prozess.save(update_fields=['current_step', 'steps_data', 'status', 'abgeschlossen_am'])
        return Response(ProzessSerializer(prozess).data)

    # ------------------------------------------------------------------
    # Single-step GET/PATCH
    # ------------------------------------------------------------------
    @action(detail=True, methods=['get', 'patch'], url_path=r'step/(?P<nr>[0-9]+)')
    def step(self, request, pk=None, nr=None):
        """
        GET: Returns step definition + current saved data.
        PATCH: Validates and saves step data. Does NOT auto-advance current_step.
        """
        prozess = self.get_object()
        nr_int = int(nr)
        defs = SCHRITT_DEFINITIONEN.get(prozess.prozess_typ, {})
        step_def = defs.get(nr_int)
        if not step_def:
            return Response({'error': f'Schritt {nr} nicht gefunden'}, status=404)

        if request.method == 'GET':
            return Response({
                'nr': nr_int,
                'bezeichnung': step_def['bezeichnung'],
                'typ': step_def['typ'],
                'daten': (prozess.steps_data or {}).get(str(nr_int), {}),
                'steps_data': prozess.steps_data or {},
            })

        # PATCH
        if prozess.status != 'aktiv':
            return Response({'errors': ['Prozess ist nicht mehr aktiv']}, status=400)

        daten = request.data.get('daten', {})
        if prozess.prozess_typ == 'objekt_anlegen':
            validator = ObjektAnlageValidator()
            errors = validator.validate_step(nr_int, daten)
            if errors:
                return Response({'errors': errors}, status=400)

        steps_data = prozess.steps_data or {}
        steps_data[str(nr_int)] = daten

        # Schritt 1: Objektnummer sofort reservieren (einmalig)
        if nr_int == 1 and prozess.prozess_typ == 'objekt_anlegen':
            objekt_typ = daten.get('objekt_typ', '')
            if objekt_typ in ('WEG', 'ZH', 'SEV') and not steps_data.get('objektnummer'):
                steps_data['objektnummer'] = _get_next_objektnummer(objekt_typ)

        # Advance current_step to the next unvisited step
        total = len(defs)
        if nr_int >= prozess.current_step and nr_int < total:
            prozess.current_step = nr_int + 1
        elif nr_int >= total:
            prozess.current_step = total + 1  # signals "all steps visited"

        prozess.steps_data = steps_data
        prozess.save(update_fields=['current_step', 'steps_data'])
        return Response({'errors': [], 'prozess': ProzessSerializer(prozess).data})

    # ------------------------------------------------------------------
    # Abbrechen
    # ------------------------------------------------------------------
    @action(detail=True, methods=['post'], url_path='abbrechen')
    def abbrechen(self, request, pk=None):
        """Prozess abbrechen."""
        prozess = self.get_object()
        if prozess.status != 'aktiv':
            return Response(
                {'error': 'Nur aktive Prozesse können abgebrochen werden'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        prozess.status = 'abgebrochen'
        prozess.save(update_fields=['status'])
        return Response(ProzessSerializer(prozess).data)

    # ------------------------------------------------------------------
    # CSV-Vorlagen
    # ------------------------------------------------------------------
    @action(detail=True, methods=['get'], url_path='csv-vorlage/einheiten')
    def csv_vorlage_einheiten(self, request, pk=None):
        """Download CSV template for Einheiten.
        Typ-Codes: 100=Wohnung, 200=Gewerbe, 900=Stellplatz, 800=Sonstiges
        """
        prozess = self.get_object()
        sd = prozess.steps_data or {}
        step2 = sd.get('2', {})
        step3 = sd.get('3', {})

        objektnummer = sd.get('objektnummer', '')
        eingaenge = step3.get('eingaenge', [])

        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="IMMOCORE_Einheiten_Vorlage.csv"'
        writer = csv.writer(response, delimiter=';')

        # Legende
        writer.writerow(['# Typ-Codes: 100=Wohnung | 200=Gewerbe | 900=Stellplatz | 800=Sonstiges'])
        if eingaenge:
            eingang_info = ' | '.join(
                e.get('bezeichnung', f'Eingang {i+1}')
                for i, e in enumerate(eingaenge)
            )
            writer.writerow([f'# Eingänge: {eingang_info}'])

        writer.writerow(['Objektnummer', 'Eingang', 'Flächennummer', 'Bez. Einheit', 'Einheit Typ', 'Lage'])

        mehrere_eingaenge = len(eingaenge) > 1
        if eingaenge:
            for eingang in eingaenge:
                # Eingang nur ausfüllen wenn es mehrere gibt
                eingang_wert = eingang.get('bezeichnung', '') if mehrere_eingaenge else ''
                writer.writerow([objektnummer, eingang_wert, '', '', '100', ''])
        else:
            writer.writerow([objektnummer, '', '', 'WE01', '100', 'EG rechts'])
            writer.writerow([objektnummer, '', '', 'WE02', '100', '1.OG links'])

        return response

    @action(detail=True, methods=['get'], url_path='csv-vorlage/eigentuemer')
    def csv_vorlage_eigentuemer(self, request, pk=None):
        """Eigentümer-Stamm-Vorlage — ohne Wohnungsbezug. Zuordnung erfolgt in Schritt 8."""
        self.get_object()  # permission check
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="IMMOCORE_Eigentuemer_Vorlage.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow([
            '# Anrede-Werte: Herr | Frau | Eheleute | Herren | Damen | Herr und Frau | Firma'
        ])
        writer.writerow([
            'ist_firma', 'Firma',
            'Anrede', 'Anrede1', 'Vorname1', 'Nachname1',
            'Anrede2', 'Vorname2', 'Nachname2',
            'Anschrift', 'PLZ', 'Ort',
            'Email1', 'Email2', 'IBAN',
        ])
        # Beispielzeilen
        writer.writerow(['FALSE', '', 'Herr', 'Herr', 'Klaus', 'Müller',
                         '', '', '', 'Musterstr. 1', '60001', 'Frankfurt',
                         'k.mueller@email.de', '', 'DE89370400440532013000'])
        writer.writerow(['FALSE', '', 'Eheleute', 'Frau', 'Maria', 'Schmidt',
                         'Herr', 'Peter', 'Schmidt', 'Hauptstr. 5', '60001', 'Frankfurt',
                         'm.schmidt@email.de', '', ''])
        return response

    # ------------------------------------------------------------------
    # CSV-Uploads
    # ------------------------------------------------------------------
    @action(detail=True, methods=['post'], url_path='csv-upload/einheiten')
    def csv_upload_einheiten(self, request, pk=None):
        """Upload and validate Einheiten CSV. Returns {einheiten, errors}.
        Typ-Codes: 100=Wohnung, 200=Gewerbe, 900=Stellplatz, 800=Sonstiges
        """
        TYP_CODES = {'100': 'Wohnung', '200': 'Gewerbe', '900': 'Stellplatz', '800': 'Sonstiges'}

        file = request.FILES.get('file')
        if not file:
            return Response({'errors': ['Keine Datei hochgeladen']}, status=400)

        try:
            content = file.read().decode('utf-8-sig')
            # BOM-Zeichen aus jeder Zeile entfernen, Kommentarzeilen überspringen
            lines = [l.lstrip('\ufeff').rstrip() for l in content.splitlines()]
            lines = [l for l in lines if l and not l.startswith('#')]
            reader = csv.DictReader(io.StringIO('\n'.join(lines)), delimiter=';')
            einheiten = []
            errors = []
            required_cols = {'Bez. Einheit', 'Einheit Typ', 'Lage'}

            for i, row in enumerate(reader, start=2):
                row_errors = []
                for col in required_cols:
                    if not row.get(col, '').strip():
                        row_errors.append(f'Zeile {i}: Spalte "{col}" fehlt oder leer')

                typ_code = row.get('Einheit Typ', '').strip()
                if typ_code and typ_code not in TYP_CODES:
                    row_errors.append(f'Zeile {i}: Ungültiger Typ-Code "{typ_code}" (erlaubt: 100, 200, 900, 800)')

                if row_errors:
                    errors.extend(row_errors)
                    continue

                bez = row['Bez. Einheit'].strip()
                einheiten.append({
                    'wohnungsbezeichnung': bez,
                    'flaechennummer': row.get('Flächennummer', '').strip(),
                    'einheit_typ': TYP_CODES[typ_code],
                    'einheit_typ_code': typ_code,
                    'lage': row['Lage'].strip(),
                    'eingang': row.get('Eingang', '').strip(),
                })

            # Doppelte Bezeichnungen prüfen
            nrs = [e['wohnungsbezeichnung'] for e in einheiten]
            for nr in set(nrs):
                if nrs.count(nr) > 1:
                    errors.append(f'Bez. Einheit "{nr}" doppelt vorhanden.')

            return Response({'einheiten': einheiten, 'errors': errors})
        except Exception as e:
            return Response({'errors': [f'Fehler beim Lesen der Datei: {str(e)}']}, status=400)

    @action(detail=True, methods=['post'], url_path='csv-upload/eigentuemer')
    def csv_upload_eigentuemer(self, request, pk=None):
        """Upload and validate Eigentümer CSV (16-Spalten-Format). Returns {eigentuemer, errors}."""
        ANREDE_WERTE = {'Herr', 'Frau', 'Eheleute', 'Herren', 'Damen', 'Herr und Frau', 'Firma', ''}

        file = request.FILES.get('file')
        if not file:
            return Response({'errors': ['Keine Datei hochgeladen']}, status=400)

        try:
            content = file.read().decode('utf-8-sig')
            lines = [l.lstrip('\ufeff').rstrip() for l in content.splitlines()]
            lines = [l for l in lines if l and not l.startswith('#')]
            reader = csv.DictReader(io.StringIO('\n'.join(lines)), delimiter=';')
            eigentuemer = []
            errors = []
            iban_re = re.compile(r'^DE\d{20}$')

            for i, row in enumerate(reader, start=2):
                ist_firma = row.get('ist_firma', '').strip().upper() == 'TRUE'
                anrede = row.get('Anrede', '').strip()

                if anrede not in ANREDE_WERTE:
                    errors.append(
                        f'Zeile {i}: Anrede "{anrede}" ungültig '
                        f'(erlaubt: Herr, Frau, Eheleute, Herren, Damen, Herr und Frau, Firma)'
                    )

                if ist_firma:
                    if not row.get('Firma', '').strip():
                        errors.append(f'Zeile {i}: Firmenname fehlt bei ist_firma=TRUE')
                else:
                    if not row.get('Vorname1', '').strip() or not row.get('Nachname1', '').strip():
                        errors.append(f'Zeile {i}: Vorname1/Nachname1 fehlen')

                iban = row.get('IBAN', '').replace(' ', '').upper()
                if iban and not iban_re.match(iban):
                    errors.append(f'Zeile {i}: IBAN ungültig: {iban}')

                vorname1 = row.get('Vorname1', '').strip()
                vorname2 = row.get('Vorname2', '').strip()
                nachname1 = row.get('Nachname1', '').strip()
                nachname2 = row.get('Nachname2', '').strip()
                vorname = f'{vorname1} und {vorname2}' if vorname2 else vorname1

                anschrift = row.get('Anschrift', '').strip()
                plz = row.get('PLZ', '').strip()
                ort = row.get('Ort', '').strip()
                adresse = '\n'.join(p for p in [anschrift, f'{plz} {ort}'.strip()] if p)

                email1 = row.get('Email1', '').strip()

                existing = None
                if email1:
                    match = Person.objects.filter(email=email1).first()
                    if match:
                        existing = {'id': str(match.id), 'name': match.name, 'email': match.email}
                if not existing and iban:
                    match = Person.objects.filter(ibans__contains=iban).first()
                    if match:
                        existing = {'id': str(match.id), 'name': match.name, 'email': match.email}

                eigentuemer.append({
                    'ref': f'et-{i - 1}',
                    'ist_firma': ist_firma,
                    'anrede': anrede,
                    'firmenname': row.get('Firma', '').strip(),
                    'anrede1': row.get('Anrede1', '').strip(),
                    'vorname1': vorname1,
                    'nachname1': nachname1,
                    'anrede2': row.get('Anrede2', '').strip(),
                    'vorname2': vorname2,
                    'nachname2': nachname2,
                    'vorname': vorname,
                    'nachname': nachname1,
                    'adresse': adresse,
                    'email': email1,
                    'email2': row.get('Email2', '').strip(),
                    'iban': iban,
                    'existing_person': existing,
                    'use_existing': bool(existing),
                })

            return Response({'eigentuemer': eigentuemer, 'errors': errors})
        except Exception as e:
            return Response({'errors': [f'Fehler: {str(e)}']}, status=400)

    # ------------------------------------------------------------------
    # Abschliessen — atomare Aktivierung
    # ------------------------------------------------------------------
    @action(detail=True, methods=['get'], url_path='ew-analyse')
    def ew_analyse(self, request, pk=None):
        """Read-only Analyse der Verkäufer-Sollstellungen für Eigentümerwechsel."""
        if not _EW_AVAILABLE:
            return Response({'error': 'EW-Modul nicht verfügbar'}, status=503)
        prozess = self.get_object()
        sd = prozess.steps_data or {}
        step1 = sd.get('1', {})
        einheit_id = step1.get('einheit_id')
        stichtag_str = step1.get('stichtag')
        if not einheit_id or not stichtag_str:
            return Response({'error': 'Schritt 1 fehlt (einheit_id/stichtag)'}, status=400)
        from datetime import date as _date
        from apps.objekte.models import Einheit as _Einheit
        try:
            einheit = _Einheit.objects.get(id=einheit_id)
            stichtag = _date.fromisoformat(stichtag_str)
        except Exception as e:
            return Response({'error': str(e)}, status=400)
        try:
            analyse = analysiere_wechsel(einheit, stichtag)
        except Exception as e:
            return Response({'error': str(e)}, status=400)
        from dataclasses import asdict
        import dataclasses

        def _serial(obj):
            if dataclasses.is_dataclass(obj):
                return {k: _serial(v) for k, v in dataclasses.asdict(obj).items()}
            if isinstance(obj, list):
                return [_serial(i) for i in obj]
            from decimal import Decimal
            from datetime import date
            if isinstance(obj, Decimal):
                return str(obj)
            if isinstance(obj, date):
                return obj.isoformat()
            return obj

        return Response(_serial(analyse))

    @action(detail=True, methods=['post'], url_path='abschliessen')
    def abschliessen(self, request, pk=None):
        """Atomare Aktivierung — 13 Sub-Schritte gemäß Spec v1.4."""
        prozess = self.get_object()
        if prozess.status != 'aktiv':
            return Response({'errors': ['Prozess ist nicht aktiv']}, status=400)

        if prozess.prozess_typ == 'eigentuemerwechsel':
            return self._abschliessen_eigentuemerwechsel(request, prozess)

        sd = prozess.steps_data or {}
        step1 = sd.get('1', {})
        step2 = sd.get('2', {})
        step3 = sd.get('3', {})
        step4 = sd.get('4', {})   # Wirtschaftsjahr
        step5 = sd.get('5', {})   # Einheiten
        step6 = sd.get('6', {})   # Bankkonten
        step7 = sd.get('7', {})   # Kontenrahmen-Anpassungen
        step8 = sd.get('8', {})   # Verträge
        step9 = sd.get('9', {})   # Freigabelimits

        if step1.get('objekt_typ') not in ('WEG', 'ZH', 'SEV'):
            return Response({'errors': ['Objekttyp fehlt oder ungültig']}, status=400)

        try:
            with transaction.atomic():
                # Sub-Schritt 1: Objekt anlegen
                objekt = Objekt.objects.create(
                    objektnummer=sd.get('objektnummer', ''),
                    objekt_typ=step1['objekt_typ'],
                    bezeichnung=step2['bezeichnung'],
                    strasse=step2['strasse'],
                    plz=step2['plz'],
                    ort=step2['ort'],
                    baujahr=step2.get('baujahr') or None,
                    verwaltung_seit=step2['verwaltung_seit'],
                    wirtschaftsjahr_start=int(step2.get('wirtschaftsjahr_start', 1)),
                    zahlungsfreigabe_grenzen=step9.get('grenzen', FREIGABE_STANDARD),
                )

                # Sub-Schritt 2: Eingänge anlegen
                eingang_map = {}
                for i, e in enumerate(step3.get('eingaenge', []), start=1):
                    eingang = Eingang.objects.create(
                        objekt=objekt,
                        bezeichnung=e.get('bezeichnung', f'Eingang {i}'),
                        strasse=e.get('strasse', step2['strasse']),
                        plz=e.get('plz', step2['plz']),
                        ort=e.get('ort', step2['ort']),
                    )
                    eingang_map[i] = eingang

                # Sub-Schritt 3: Erstes Wirtschaftsjahr anlegen (Schritt 4 des Wizards)
                import datetime as _dt
                wj_jahr = int(step4.get('jahr', _dt.date.today().year))
                from apps.objekte.models import Wirtschaftsjahr, EinheitVerbrauch
                wj = Wirtschaftsjahr.objects.create(
                    objekt=objekt,
                    jahr=wj_jahr,
                    beginn_monat=objekt.wirtschaftsjahr_start,
                    status='offen',
                    vorjahr=None,
                    eroeffnet_von=request.user,
                )

                # Sub-Schritt 4: Einheiten anlegen (ohne VS — kommen in Sub-Schritt 10)
                einheiten_list = step5.get('einheiten', [])
                einheit_objects = []
                for seq, e in enumerate(einheiten_list, start=1):
                    eingang_bez = e.get('eingang', '').strip()
                    eingang_obj = next(
                        (v for v in eingang_map.values() if v.bezeichnung == eingang_bez),
                        eingang_map.get(1),
                    ) if eingang_bez else eingang_map.get(1)

                    einheit = Einheit.objects.create(
                        objekt=objekt,
                        eingang=eingang_obj,
                        einheit_nr=e.get('wohnungsbezeichnung', str(seq)),
                        flaechennummer=e.get('flaechennummer', ''),
                        einheit_typ=e.get('einheit_typ', 'Wohnung'),
                        lage=e.get('lage', ''),
                    )
                    einheit_objects.append((einheit, e))

                # Sub-Schritt 5: Bankkonten anlegen
                ruecklagen = []
                for b in step6.get('bankkonten', []):
                    Bankkonto.objects.create(
                        objekt=objekt,
                        konto_typ=b['konto_typ'],
                        bezeichnung=b['bezeichnung'],
                        iban=b.get('iban', ''),
                        bic=b.get('bic', ''),
                        kontoinhaber=b.get('kontoinhaber', ''),
                        reihenfolge=int(b.get('reihenfolge', 1)),
                    )
                    if b['konto_typ'] == 'ruecklage':
                        ruecklagen.append(b)

                # Sub-Schritt 6: Musterkontenrahmen laden (70 Basis-Konten) — an WJ hängen
                if objekt.objekt_typ == 'WEG':
                    kontenrahmen_anlegen(wirtschaftsjahr_id=str(wj.id))

                # Sub-Schritt 7: Rücklagen-Konten für Rücklage II+ generieren
                if len(ruecklagen) >= 2:
                    ruecklagen_konten_anlegen(ruecklagen, wirtschaftsjahr_id=str(wj.id))

                # Sub-Schritt 7b: Standard-Abrechnungsarten + Rücklage II+ anlegen
                abrechnungsarten_anlegen(str(objekt.id), ruecklagen)

                # Sub-Schritt 8: Kontenplan-Anpassungen aus Schritt 7 anwenden
                for k in step7.get('konten', []):
                    if not k.get('aktiv', True):
                        Konto.objects.filter(wirtschaftsjahr=wj, kontonummer=k.get('kontonummer', '')).update(aktiv=False)
                    elif k.get('kontonummer'):
                        Konto.objects.update_or_create(
                            wirtschaftsjahr=wj,
                            kontonummer=k['kontonummer'],
                            defaults={
                                'kontoname':           k.get('kontoname', k.get('bezeichnung', '')),
                                'abrechnungsart':      k.get('abrechnungsart') or None,
                                'direktes_buchen':     k.get('direktes_buchen', True),
                                'verteilerschluessel': k.get('verteilerschluessel') or None,
                                'kontoart':            k.get('kontoart', 'standard'),
                                'arge_konto':          k.get('arge_konto', False),
                                'aktiv':               k.get('aktiv', True),
                            },
                        )

                # Sub-Schritt 9: Verträge + Hausgeld-Historien aus Wizard-Schritt 8
                from apps.personen.models import EigentumsVerhaeltnis as EV, HausgeldHistorie
                from apps.konten.models import Abrechnungsart
                from apps.konten.services import personenkonto_anlegen

                einheit_by_nr = {e.einheit_nr: e for e, _ in einheit_objects}

                for vdata in step8.get('vertraege', []):
                    einheit_nr_v  = vdata.get('einheit_nr', '')
                    person_id_v   = vdata.get('person_id')
                    beginn_str_v  = vdata.get('beginn', '')

                    einheit_v = einheit_by_nr.get(einheit_nr_v)
                    if not einheit_v or not person_id_v or not beginn_str_v:
                        continue

                    import datetime as _dtv
                    beginn_v = _dtv.date.fromisoformat(beginn_str_v)
                    ev_obj = EV.objects.create(
                        einheit=einheit_v,
                        person_id=person_id_v,
                        beginn=beginn_v,
                    )
                    personenkonto_anlegen(ev_obj, objekt)

                    for he in vdata.get('hausgeld_eintraege', []):
                        abr_code_v  = he.get('abrechnungsart_code', '')
                        betrag_v    = he.get('betrag')
                        if not abr_code_v or betrag_v is None:
                            continue
                        try:
                            abr_v = Abrechnungsart.objects.get(objekt=objekt, code=abr_code_v)
                        except Abrechnungsart.DoesNotExist:
                            continue
                        HausgeldHistorie.objects.create(
                            eigentumsverhaeltnis=ev_obj,
                            abrechnungsart=abr_v,
                            betrag=Decimal(str(betrag_v).replace(',', '.')),
                            gueltig_ab=beginn_v,
                            wirtschaftsplan_jahr=wj_jahr,
                            quelle='import',
                            import_referenz='wizard_erstanlage',
                            erstellt_von=request.user,
                        )

                # Sub-Schritt 10: 7 Muster-Verteilerschlüssel + VSBeteiligung je Einheit
                MUSTER_VS = [
                    ('001', 'flaeche',   'Wohnfläche',              'qm'),
                    ('010', 'mea',       'MEA Gesamt',              'TEL'),
                    ('030', 'kopf',      'Anzahl Einheiten Gesamt', ''),
                    ('031', 'kopf',      'Anzahl Wohnungen',        ''),
                    ('032', 'kopf',      'Anzahl Stellplätze',      ''),
                    ('100', 'direkt',    'Direktkosten Eigentümer', ''),
                    ('140', 'verbrauch', 'Heizkosten nach Verbrauch', 'kWh'),
                ]
                import datetime as dt
                aktuelles_jahr = dt.date.today().year

                for schluessel, vs_typ, bezeichnung, einheit_einheit in MUSTER_VS:
                    vs = Verteilerschluessel.objects.create(
                        objekt=objekt,
                        schluessel=schluessel,
                        bezeichnung=bezeichnung,
                        vs_typ=vs_typ,
                        aktiv=True,
                        schluessel_typ=vs_typ,
                        einheit=einheit_einheit,
                        reihenfolge=int(schluessel),
                    )
                    # VSBeteiligung für alle Einheiten (außer direkt)
                    if vs_typ not in ('direkt',):
                        for einheit, e_data in einheit_objects:
                            beteiligt = True
                            if vs_typ == 'kopf' and schluessel == '031':
                                beteiligt = einheit.einheit_typ == 'Wohnung'
                            elif vs_typ == 'kopf' and schluessel == '032':
                                beteiligt = einheit.einheit_typ == 'Stellplatz'

                            wert = None
                            quelle = 'stammdaten'
                            if vs_typ == 'flaeche' and e_data.get('flaeche_qm'):
                                wert = Decimal(str(e_data['flaeche_qm']))
                            elif vs_typ == 'mea' and e_data.get('miteigentumsanteil'):
                                wert = Decimal(str(e_data['miteigentumsanteil']))
                            elif vs_typ == 'kopf':
                                wert = Decimal('1.0000')
                            elif vs_typ == 'verbrauch':
                                wert = None
                                quelle = 'manuell'

                            VerteilerschluesselWert.objects.create(
                                schluessel=vs,
                                einheit=einheit,
                                wirtschaftsjahr=aktuelles_jahr,
                                beteiligt=beteiligt,
                                wert=wert,
                                einzelwert_einheit=einheit_einheit,
                                quelle=quelle,
                            )

                # Sub-Schritt 11: EinheitVerbrauch-Strukturzeilen (VS 140–145) je Einheit
                for einheit, _ in einheit_objects:
                    for vs_code in ('140', '141', '142', '143', '144', '145'):
                        EinheitVerbrauch.objects.get_or_create(
                            wirtschaftsjahr=wj,
                            einheit=einheit,
                            vs_code=vs_code,
                        )

                # Sub-Schritt 13: Prozess abschließen
                prozess.status = 'abgeschlossen'
                prozess.abgeschlossen_am = datetime.now(timezone.utc)
                prozess.objekt = objekt
                prozess.steps_data = sd
                prozess.save(update_fields=['status', 'abgeschlossen_am', 'objekt', 'steps_data'])

                return Response({
                    'objekt_id': str(objekt.id),
                    'objektnummer': objekt.objektnummer,
                    'prozess': ProzessSerializer(prozess).data,
                })
        except Exception as e:
            import traceback
            return Response(
                {'errors': [f'Aktivierung fehlgeschlagen: {str(e)}. Rollback.'], 'detail': traceback.format_exc()},
                status=500,
            )

    def _abschliessen_eigentuemerwechsel(self, request, prozess):
        """Eigentümerwechsel-Commit via eigentuemerwechsel_service."""
        if not _EW_AVAILABLE:
            return Response({'errors': ['EW-Modul nicht verfügbar']}, status=503)
        sd = prozess.steps_data or {}
        step1 = sd.get('1', {})
        step2 = sd.get('2', {})
        step3 = sd.get('3', {})
        step4 = sd.get('4', {})

        einheit_id   = step1.get('einheit_id')
        stichtag_str = step1.get('stichtag')

        if not einheit_id or not stichtag_str:
            return Response({'errors': ['Schritt 1 unvollständig']}, status=400)
        if not step2.get('kaeufer_person_id'):
            return Response({'errors': ['Käufer fehlt (Schritt 2)']}, status=400)

        from datetime import date as _date
        from apps.objekte.models import Einheit as _Einheit

        try:
            einheit  = _Einheit.objects.get(id=einheit_id)
            stichtag = _date.fromisoformat(stichtag_str)
        except Exception as e:
            return Response({'errors': [str(e)]}, status=400)

        wirkungs_periode_str = step1.get('wirkungs_periode')
        try:
            wirkungs_periode = _date.fromisoformat(wirkungs_periode_str) if wirkungs_periode_str else None
        except ValueError:
            wirkungs_periode = None
        if not wirkungs_periode:
            wirkungs_periode = analysiere_wechsel(einheit, stichtag).wirkungs_periode

        verkaeufer_iban = step4.get('verkaeufer_iban') or ''

        entscheidungen = {
            'kaeufer_person_id': step2['kaeufer_person_id'],
            'kaeufer_iban': step2.get('kaeufer_iban', ''),
            'hausgeld_je_ba': step3.get('hausgeld_je_ba', {}),
            'stornieren_ids': step4.get('stornieren_ids', []),
            'erstatten': step4.get('erstatten', []),
            'verkaeufer_iban': verkaeufer_iban,
        }

        try:
            result = commite_wechsel(
                einheit=einheit,
                stichtag=stichtag,
                wirkungs_periode=wirkungs_periode,
                entscheidungen=entscheidungen,
                user=request.user,
            )
        except Exception as e:
            import traceback
            import logging
            logging.getLogger(__name__).error('commite_wechsel fehlgeschlagen: %s', traceback.format_exc())
            return Response({'errors': [str(e)]}, status=400)

        prozess.status = 'abgeschlossen'
        prozess.abgeschlossen_am = datetime.now(timezone.utc)
        prozess.save(update_fields=['status', 'abgeschlossen_am'])

        return Response({
            'wechsel_id': result['wechsel_id'],
            'kaeufer_ev_id': result['kaeufer_ev_id'],
            'auszahlungslauf_id': result['auszahlungslauf_id'],
            'nachhol_count': len(result['nachhol_sollstellungs_ids']),
            'storniert_count': len(result['stornierte_sollstellungs_ids']),
        })
