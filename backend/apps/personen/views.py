import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from django.db.models import Max
from django.http import HttpResponse
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Person, SEPAMandat, EigentumsVerhaeltnis, HausgeldHistorie, Mietvertrag
from .serializers import (
    PersonSerializer, PersonListSerializer,
    SEPAMandatSerializer, EigentumsVerhaeltnisSerializer,
    HausgeldHistorieSerializer, MietvertragSerializer,
)

ANREDE_WERTE = {'Herr', 'Frau', 'Eheleute', 'Herren', 'Damen', 'Herr und Frau', 'Firma', ''}
PERSON_TYP_WERTE = {'100', '200', '300', '400'}

@dataclass
class PersonenImportZeilenergebnis:
    zeilennummer: int
    rohdaten: dict
    personennummer: str
    meldung: str = field(default='')


def _ergebnis_csv_response(original_name: str, fieldnames: list, ergebnisse: list) -> HttpResponse:
    buf = io.StringIO()
    buf.write('﻿')  # UTF-8 BOM
    writer = csv.DictWriter(
        buf,
        fieldnames=fieldnames + ['personennummer'],
        delimiter=';',
        lineterminator='\r\n',
        quoting=csv.QUOTE_MINIMAL,
        extrasaction='ignore',
    )
    writer.writeheader()
    for e in ergebnisse:
        zeile = dict(e.rohdaten)
        zeile['personennummer'] = e.personennummer
        writer.writerow(zeile)

    basisname = original_name[:-4] if original_name.lower().endswith('.csv') else original_name
    zeitstempel = datetime.now().strftime('%Y%m%d_%H%M%S')
    dateiname = f'{basisname}_ergebnis_{zeitstempel}.csv'

    response = HttpResponse(buf.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{dateiname}"'
    return response


class PersonViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['vorname', 'nachname', 'firmenname', 'email', 'personennummer']
    ordering_fields = ['nachname', 'firmenname', 'personennummer']
    ordering = ['personennummer']

    def get_queryset(self):
        qs = Person.objects.select_related('sepa_mandat')
        typ = self.request.query_params.get('typ')
        if typ:
            qs = qs.filter(person_typ=typ)
        objekt_id = self.request.query_params.get('objekt')
        if objekt_id:
            qs = qs.filter(eigentumsverhaeltnisse__einheit__objekt_id=objekt_id).distinct()
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return PersonListSerializer
        return PersonSerializer

    @action(detail=False, methods=['get'], url_path='csv-vorlage')
    def csv_vorlage(self, request):
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="IMMOCORE_Personen_Vorlage.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow(['# person_typ: 100=Eigentümer | 200=Mieter | 300=Kreditor | 400=Sonstiges'])
        writer.writerow(['# Anrede-Werte: Herr | Frau | Eheleute | Herren | Damen | Herr und Frau | Firma'])
        writer.writerow([
            'person_typ', 'ist_firma', 'Firma',
            'Anrede', 'Anrede1', 'Vorname1', 'Nachname1',
            'Anrede2', 'Vorname2', 'Nachname2',
            'Anschrift', 'PLZ', 'Ort', 'Email1', 'Email2', 'IBAN',
        ])
        writer.writerow(['100', 'FALSE', '', 'Herr', 'Herr', 'Klaus', 'Müller',
                         '', '', '', 'Musterstr. 1', '60001', 'Frankfurt',
                         'k.mueller@email.de', '', 'DE89370400440532013000'])
        writer.writerow(['100', 'FALSE', '', 'Eheleute', 'Frau', 'Maria', 'Schmidt',
                         'Herr', 'Peter', 'Schmidt', 'Hauptstr. 5', '60001', 'Frankfurt',
                         'm.schmidt@email.de', '', ''])
        writer.writerow(['300', 'TRUE', 'Musterfirma GmbH', 'Firma', '', '', '',
                         '', '', '', 'Gewerbestr. 10', '60001', 'Frankfurt',
                         'info@musterfirma.de', '', ''])
        return response

    @action(detail=False, methods=['post'], url_path='csv-vorschau')
    def csv_vorschau(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response({'errors': ['Keine Datei hochgeladen']}, status=400)

        try:
            raw = file.read()
            for enc in ('utf-8-sig', 'cp1252', 'latin-1'):
                try:
                    content = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            lines = [l.lstrip('﻿').rstrip() for l in content.splitlines()]
            lines = [l for l in lines if l and not l.startswith('#')]
            reader = csv.DictReader(io.StringIO('\n'.join(lines)), delimiter=';')

            rows = []
            seen_emails: dict = {}
            seen_ibans: dict = {}
            seen_namen: dict = {}
            seen_firmen: dict = {}

            for i, row in enumerate(reader, start=2):
                ist_firma = row.get('ist_firma', '').strip().upper() == 'TRUE'
                anrede = row.get('Anrede', '').strip()
                person_typ = row.get('person_typ', '100').strip() or '100'
                firmenname = row.get('Firma', '').strip()
                vorname1 = row.get('Vorname1', '').strip()
                vorname2 = row.get('Vorname2', '').strip()
                nachname1 = row.get('Nachname1', '').strip()

                row_errors = []
                if anrede not in ANREDE_WERTE:
                    row_errors.append(
                        f'Anrede „{anrede}" ungültig – erlaubt: Herr, Frau, Eheleute, Herren, Damen, Herr und Frau, Firma'
                    )
                if person_typ not in PERSON_TYP_WERTE:
                    row_errors.append(
                        f'person_typ „{person_typ}" ungültig – erlaubt: 100, 200, 300, 400'
                    )
                if ist_firma and not firmenname:
                    row_errors.append('Firmenname fehlt, obwohl ist_firma=TRUE')
                if not ist_firma and not vorname1:
                    row_errors.append('Vorname1 fehlt')
                if not ist_firma and not nachname1:
                    row_errors.append('Nachname1 fehlt')

                iban = row.get('IBAN', '').replace(' ', '').upper()
                email1 = row.get('Email1', '').strip()
                vorname = f'{vorname1} und {vorname2}' if vorname2 else vorname1
                anschrift = row.get('Anschrift', '').strip()
                plz = row.get('PLZ', '').strip()
                ort = row.get('Ort', '').strip()
                adresse = '\n'.join(p for p in [anschrift, f'{plz} {ort}'.strip()] if p)

                csv_data = {
                    'person_typ': person_typ,
                    'ist_firma': ist_firma,
                    'anrede': anrede,
                    'firmenname': firmenname,
                    'anrede1': row.get('Anrede1', '').strip(),
                    'vorname1': vorname1,
                    'nachname1': nachname1,
                    'anrede2': row.get('Anrede2', '').strip(),
                    'vorname2': vorname2,
                    'nachname2': row.get('Nachname2', '').strip(),
                    'vorname': vorname,
                    'nachname': nachname1,
                    'email': email1,
                    'email2': row.get('Email2', '').strip(),
                    'adresse': adresse,
                    'iban': iban,
                }

                if row_errors:
                    if email1 and email1.lower() not in seen_emails:
                        seen_emails[email1.lower()] = i
                    if iban and iban not in seen_ibans:
                        seen_ibans[iban] = i
                    if ist_firma and firmenname and firmenname.lower() not in seen_firmen:
                        seen_firmen[firmenname.lower()] = i
                    elif not ist_firma and vorname and nachname1 and f'{vorname.lower()}|{nachname1.lower()}' not in seen_namen:
                        seen_namen[f'{vorname.lower()}|{nachname1.lower()}'] = i
                    rows.append({
                        'zeile': i, 'csv_data': csv_data,
                        'status': 'fehler', 'fehler': row_errors,
                        'duplikat': None, 'aktion': 'ablehnen',
                    })
                    continue

                duplikat = None
                if email1:
                    ref = seen_emails.get(email1.lower())
                    if ref:
                        name_str = firmenname if ist_firma else f'{vorname} {nachname1}'
                        duplikat = _dup_info_datei(ref, name_str, f'E-Mail „{email1}" bereits in Zeile {ref}')
                if not duplikat and iban:
                    ref = seen_ibans.get(iban)
                    if ref:
                        name_str = firmenname if ist_firma else f'{vorname} {nachname1}'
                        duplikat = _dup_info_datei(ref, name_str, f'IBAN „{iban}" bereits in Zeile {ref}')
                if not duplikat:
                    if ist_firma and firmenname:
                        ref = seen_firmen.get(firmenname.lower())
                        if ref:
                            duplikat = _dup_info_datei(ref, firmenname, f'Firmenname bereits in Zeile {ref}')
                    elif vorname and nachname1:
                        ref = seen_namen.get(f'{vorname.lower()}|{nachname1.lower()}')
                        if ref:
                            duplikat = _dup_info_datei(ref, f'{vorname} {nachname1}', f'Name bereits in Zeile {ref}')

                if not duplikat:
                    if email1:
                        m = Person.objects.filter(email=email1).first()
                        if m:
                            duplikat = _dup_info(m, f'E-Mail „{email1}" bereits vorhanden')
                    if not duplikat and iban:
                        m = Person.objects.filter(ibans__contains=iban).first()
                        if m:
                            duplikat = _dup_info(m, f'IBAN „{iban}" bereits vorhanden')
                    if not duplikat:
                        if ist_firma and firmenname:
                            m = Person.objects.filter(firmenname__iexact=firmenname).first()
                            if m:
                                duplikat = _dup_info(m, f'Firmenname „{firmenname}" bereits vorhanden')
                        elif vorname and nachname1:
                            m = Person.objects.filter(
                                vorname__iexact=vorname, nachname__iexact=nachname1
                            ).first()
                            if m:
                                duplikat = _dup_info(m, f'Name „{vorname} {nachname1}" bereits vorhanden')

                if email1 and email1.lower() not in seen_emails:
                    seen_emails[email1.lower()] = i
                if iban and iban not in seen_ibans:
                    seen_ibans[iban] = i
                if ist_firma and firmenname and firmenname.lower() not in seen_firmen:
                    seen_firmen[firmenname.lower()] = i
                elif not ist_firma and vorname and nachname1 and f'{vorname.lower()}|{nachname1.lower()}' not in seen_namen:
                    seen_namen[f'{vorname.lower()}|{nachname1.lower()}'] = i

                rows.append({
                    'zeile': i, 'csv_data': csv_data,
                    'status': 'duplikat' if duplikat else 'neu',
                    'fehler': [],
                    'duplikat': duplikat,
                    'aktion': 'ablehnen' if duplikat else 'importieren',
                })

            return Response({'rows': rows, 'errors': []})
        except Exception as e:
            return Response({'errors': [f'Fehler beim Lesen: {str(e)}']}, status=400)

    @action(detail=False, methods=['post'], url_path='csv-import')
    def csv_import(self, request):
        import json as _json
        from apps.massenimport.models import ImportJob

        csv_datei = request.FILES.get('csv_datei')
        if not csv_datei:
            return Response({'errors': ['Keine Datei hochgeladen']}, status=400)

        aktionen_raw = request.POST.get('aktionen', '{}')
        try:
            aktionen = _json.loads(aktionen_raw)
        except Exception:
            return Response({'errors': ['aktionen-JSON ungültig']}, status=400)

        raw = csv_datei.read()
        filename = csv_datei.name
        content = None
        for enc in ('utf-8-sig', 'cp1252', 'latin-1'):
            try:
                content = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if content is None:
            return Response({'errors': ['Datei-Encoding nicht erkannt']}, status=400)

        lines = [l.lstrip('﻿').rstrip() for l in content.splitlines()]
        lines_filtered = [l for l in lines if l and not l.startswith('#')]
        reader = csv.DictReader(io.StringIO('\n'.join(lines_filtered)), delimiter=';')
        fieldnames = list(reader.fieldnames or [])

        ergebnisse = []
        zeilen_ok = zeilen_skip = zeilen_fail = 0

        for i, row in enumerate(reader, start=2):
            aktion_info = aktionen.get(str(i), {})
            aktion = aktion_info.get('aktion', 'ablehnen')
            duplikat_pnr = aktion_info.get('duplikat_personennummer') or ''
            original_row = dict(row)

            if aktion == 'importieren':
                ist_firma = row.get('ist_firma', '').strip().upper() == 'TRUE'
                anrede = row.get('Anrede', '').strip()
                person_typ = row.get('person_typ', '100').strip() or '100'
                firmenname = row.get('Firma', '').strip()
                vorname1 = row.get('Vorname1', '').strip()
                vorname2 = row.get('Vorname2', '').strip()
                nachname1 = row.get('Nachname1', '').strip()
                nachname2 = row.get('Nachname2', '').strip()
                vorname = f'{vorname1} und {vorname2}' if vorname2 else vorname1
                email1 = row.get('Email1', '').strip()
                anschrift = row.get('Anschrift', '').strip()
                plz = row.get('PLZ', '').strip()
                ort = row.get('Ort', '').strip()
                adresse = '\n'.join(p for p in [anschrift, f'{plz} {ort}'.strip()] if p)
                iban = row.get('IBAN', '').replace(' ', '').upper()
                try:
                    person = Person.objects.create(
                        person_typ=person_typ, anrede=anrede, ist_firma=ist_firma,
                        vorname=vorname, nachname=nachname1, vorname2=vorname2, nachname2=nachname2,
                        firmenname=firmenname, email=email1, adresse=adresse,
                        ibans=[iban] if iban else [],
                    )
                    ergebnisse.append(PersonenImportZeilenergebnis(
                        zeilennummer=i, rohdaten=original_row, personennummer=person.personennummer,
                    ))
                    zeilen_ok += 1
                except Exception as exc:
                    ergebnisse.append(PersonenImportZeilenergebnis(
                        zeilennummer=i, rohdaten=original_row, personennummer='', meldung=str(exc),
                    ))
                    zeilen_fail += 1
            else:
                preview_status = aktion_info.get('preview_status', 'neu')
                if preview_status == 'fehler':
                    zeilen_fail += 1
                else:
                    zeilen_skip += 1
                ergebnisse.append(PersonenImportZeilenergebnis(
                    zeilennummer=i, rohdaten=original_row, personennummer=duplikat_pnr,
                ))

        if zeilen_ok == len(ergebnisse):
            job_status = 'committed'
        elif zeilen_ok == 0 and zeilen_skip == 0:
            job_status = 'failed'
        else:
            job_status = 'partial'

        ImportJob.objects.create(
            typ='personen_import', status=job_status,
            zeilen_gesamt=len(ergebnisse), zeilen_ok=zeilen_ok,
            zeilen_warnung=zeilen_skip, zeilen_fehler=zeilen_fail,
            ergebnis=[
                {'zeile': e.zeilennummer, 'personennummer': e.personennummer, 'meldung': e.meldung}
                for e in ergebnisse
            ],
            erstellt_von=request.user,
        )

        return _ergebnis_csv_response(filename, fieldnames, ergebnisse)


def _dup_info(person: Person, grund: str) -> dict:
    return {
        'id': str(person.id), 'personennummer': person.personennummer,
        'name': person.name, 'email': person.email, 'adresse': person.adresse,
        'grund': grund, 'quelle': 'datenbank', 'zeile_ref': None,
    }


def _dup_info_datei(zeile_ref: int, name: str, grund: str) -> dict:
    return {
        'id': None, 'personennummer': None, 'name': name,
        'email': '', 'adresse': '', 'grund': grund,
        'quelle': 'datei', 'zeile_ref': zeile_ref,
    }


class SEPAMandatViewSet(viewsets.ModelViewSet):
    serializer_class = SEPAMandatSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SEPAMandat.objects.all()


def _parse_datum(s: str) -> str:
    s = s.strip()
    if not s:
        return s
    if '.' in s:
        parts = s.split('.')
        if len(parts) == 3:
            return f'{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}'
    return s


class EigentumsVerhaeltnisViewSet(viewsets.ModelViewSet):
    serializer_class = EigentumsVerhaeltnisSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering = ['-beginn']

    def get_queryset(self):
        qs = EigentumsVerhaeltnis.objects.select_related(
            'person', 'einheit', 'einheit__objekt'
        ).prefetch_related('hausgeld_eintraege__abrechnungsart')
        objekt_id = self.request.query_params.get('objekt')
        einheit_id = self.request.query_params.get('einheit')
        person_id = self.request.query_params.get('person')
        aktiv = self.request.query_params.get('aktiv')
        if objekt_id:
            qs = qs.filter(einheit__objekt_id=objekt_id)
        if einheit_id:
            qs = qs.filter(einheit_id=einheit_id)
        if person_id:
            qs = qs.filter(person_id=person_id)
        if aktiv == 'true':
            qs = qs.filter(ende__isnull=True)
        return qs

    def create(self, request, *args, **kwargs):
        einheit_id = request.data.get('einheit')
        if einheit_id:
            aktives_ev = (
                EigentumsVerhaeltnis.objects
                .filter(einheit_id=einheit_id, ende__isnull=True)
                .select_related('person')
                .first()
            )
            if aktives_ev:
                return Response(
                    {
                        'error': (
                            f'Einheit ist bereits {aktives_ev.person.name} zugewiesen '
                            f'(seit {aktives_ev.beginn}). Bitte zuerst das bestehende '
                            f'Eigentumsverhältnis beenden.'
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        return super().create(request, *args, **kwargs)

    @action(detail=True, methods=['get'], url_path='hausgeld-aktuell')
    def hausgeld_aktuell(self, request, pk=None):
        """Aktueller Hausgeld-Stand zum Stichtag (Default: heute)."""
        ev = self.get_object()
        stichtag_str = request.query_params.get('stichtag')
        if stichtag_str:
            try:
                stichtag = date.fromisoformat(stichtag_str)
            except ValueError:
                return Response({'error': f'stichtag ungültig: {stichtag_str}'}, status=400)
        else:
            stichtag = date.today()

        betraege = ev.hausgeld_alle_aktuell(stichtag)
        return Response({
            'stichtag': str(stichtag),
            'gesamt': float(sum(betraege.values(), Decimal('0'))),
            'positionen': [
                {'abrechnungsart': code, 'betrag': float(betrag)}
                for code, betrag in sorted(betraege.items())
            ],
        })

    @action(detail=True, methods=['get'], url_path='hausgeld-historie')
    def hausgeld_historie_detail(self, request, pk=None):
        """Komplette Historie nach Abrechnungsart gruppiert."""
        ev = self.get_object()
        from apps.konten.models import Abrechnungsart
        heute = date.today()

        alle = (
            HausgeldHistorie.objects
            .filter(eigentumsverhaeltnis=ev)
            .select_related('abrechnungsart')
            .order_by('abrechnungsart__code', '-gueltig_ab')
        )

        gruppen: dict = {}
        for h in alle:
            code = h.abrechnungsart.code if h.abrechnungsart else '?'
            bez = h.abrechnungsart.bezeichnung if h.abrechnungsart else ''
            if code not in gruppen:
                gruppen[code] = {'abrechnungsart_code': code, 'bezeichnung': bez, 'eintraege': []}

            aktiv_str = '✓ aktiv'
            if h.gueltig_ab > heute:
                aktiv_str = '⏳ künftig'
            else:
                # Prüfe ob neuerer Eintrag für dieselbe Abrechnungsart existiert
                neuerer = HausgeldHistorie.objects.filter(
                    eigentumsverhaeltnis=ev,
                    abrechnungsart=h.abrechnungsart,
                    gueltig_ab__gt=h.gueltig_ab,
                    gueltig_ab__lte=heute,
                ).exists()
                if neuerer:
                    aktiv_str = '📜 historisch'

            gruppen[code]['eintraege'].append({
                'id': str(h.id),
                'gueltig_ab': str(h.gueltig_ab),
                'betrag': float(h.betrag),
                'wirtschaftsplan_jahr': h.wirtschaftsplan_jahr,
                'quelle': h.quelle,
                'bemerkung': h.bemerkung,
                'erstellt_am': h.erstellt_am.isoformat() if h.erstellt_am else None,
                'status': aktiv_str,
            })

        return Response({
            'eigentumsverhaeltnis_id': str(ev.id),
            'person': ev.person.name,
            'einheit_nr': ev.einheit.einheit_nr,
            'gruppen': list(gruppen.values()),
        })


class HausgeldHistorieViewSet(viewsets.ModelViewSet):
    serializer_class = HausgeldHistorieSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = HausgeldHistorie.objects.select_related(
            'eigentumsverhaeltnis', 'abrechnungsart', 'erstellt_von'
        )
        ev_id = self.request.query_params.get('eigentumsverhaeltnis')
        if ev_id:
            qs = qs.filter(eigentumsverhaeltnis_id=ev_id)
        return qs


class MietvertragViewSet(viewsets.ModelViewSet):
    serializer_class = MietvertragSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Mietvertrag.objects.select_related('einheit', 'mieter')
        einheit_id = self.request.query_params.get('einheit')
        if einheit_id:
            qs = qs.filter(einheit_id=einheit_id)
        return qs
