import csv
import io
from datetime import date
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

    # ------------------------------------------------------------------
    # CSV-Vorlage
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # CSV-Vorschau (Parse + Dublettenprüfung)
    # ------------------------------------------------------------------
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
            lines = [l.lstrip('\ufeff').rstrip() for l in content.splitlines()]
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
                        f'person_typ „{person_typ}" ungültig – erlaubt: 100 (Eigentümer), 200 (Mieter), 300 (Kreditor), 400 (Sonstiges)'
                    )
                if ist_firma and not firmenname:
                    row_errors.append('Firmenname (Spalte „Firma") fehlt, obwohl ist_firma=TRUE gesetzt ist')
                if not ist_firma and not vorname1:
                    row_errors.append('Vorname1 fehlt – bei Privatpersonen ist Vorname1 erforderlich')
                if not ist_firma and not nachname1:
                    row_errors.append('Nachname1 fehlt – bei Privatpersonen ist Nachname1 erforderlich')

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
                        'zeile': i,
                        'csv_data': csv_data,
                        'status': 'fehler',
                        'fehler': row_errors,
                        'duplikat': None,
                        'aktion': 'ablehnen',
                    })
                    continue

                # Dublettenprüfung in der Datei selbst
                duplikat = None
                if email1:
                    ref = seen_emails.get(email1.lower())
                    if ref:
                        name_str = firmenname if ist_firma else f'{vorname} {nachname1}'
                        duplikat = _dup_info_datei(ref, name_str, f'E-Mail „{email1}" bereits in Zeile {ref} der Datei vorhanden')
                if not duplikat and iban:
                    ref = seen_ibans.get(iban)
                    if ref:
                        name_str = firmenname if ist_firma else f'{vorname} {nachname1}'
                        duplikat = _dup_info_datei(ref, name_str, f'IBAN „{iban}" bereits in Zeile {ref} der Datei vorhanden')
                if not duplikat:
                    if ist_firma and firmenname:
                        ref = seen_firmen.get(firmenname.lower())
                        if ref:
                            duplikat = _dup_info_datei(ref, firmenname, f'Firmenname „{firmenname}" bereits in Zeile {ref} der Datei vorhanden')
                    elif vorname and nachname1:
                        ref = seen_namen.get(f'{vorname.lower()}|{nachname1.lower()}')
                        if ref:
                            duplikat = _dup_info_datei(ref, f'{vorname} {nachname1}', f'Name „{vorname} {nachname1}" bereits in Zeile {ref} der Datei vorhanden')

                # Dublettenprüfung gegen Datenbank
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

                # Aktuelle Zeile in seen-dicts eintragen (nur erste Zeile je Wert)
                if email1 and email1.lower() not in seen_emails:
                    seen_emails[email1.lower()] = i
                if iban and iban not in seen_ibans:
                    seen_ibans[iban] = i
                if ist_firma and firmenname and firmenname.lower() not in seen_firmen:
                    seen_firmen[firmenname.lower()] = i
                elif not ist_firma and vorname and nachname1 and f'{vorname.lower()}|{nachname1.lower()}' not in seen_namen:
                    seen_namen[f'{vorname.lower()}|{nachname1.lower()}'] = i

                rows.append({
                    'zeile': i,
                    'csv_data': csv_data,
                    'status': 'duplikat' if duplikat else 'neu',
                    'fehler': [],
                    'duplikat': duplikat,
                    'aktion': 'ablehnen' if duplikat else 'importieren',
                })

            return Response({'rows': rows, 'errors': []})
        except Exception as e:
            return Response({'errors': [f'Fehler beim Lesen: {str(e)}']}, status=400)

    # ------------------------------------------------------------------
    # CSV-Import (mit Nutzerentscheidungen)
    # ------------------------------------------------------------------
    @action(detail=False, methods=['post'], url_path='csv-import')
    def csv_import(self, request):
        rows = request.data.get('rows', [])
        if not rows:
            return Response({'errors': ['Keine Zeilen']}, status=400)

        importiert = 0
        abgelehnt = 0
        errors = []

        for row in rows:
            if row.get('aktion') != 'importieren':
                abgelehnt += 1
                continue
            d = row.get('csv_data', {})
            try:
                iban = d.get('iban', '')
                Person.objects.create(
                    person_typ=d.get('person_typ', '100'),
                    anrede=d.get('anrede', ''),
                    ist_firma=d.get('ist_firma', False),
                    vorname=d.get('vorname', ''),
                    nachname=d.get('nachname', ''),
                    firmenname=d.get('firmenname', ''),
                    email=d.get('email', ''),
                    adresse=d.get('adresse', ''),
                    ibans=[iban] if iban else [],
                )
                importiert += 1
            except Exception as e:
                errors.append(f'Zeile {row.get("zeile", "?")}: {str(e)}')

        return Response({'importiert': importiert, 'abgelehnt': abgelehnt, 'errors': errors})


def _dup_info(person: Person, grund: str) -> dict:
    return {
        'id': str(person.id),
        'personennummer': person.personennummer,
        'name': person.name,
        'email': person.email,
        'adresse': person.adresse,
        'grund': grund,
        'quelle': 'datenbank',
        'zeile_ref': None,
    }


def _dup_info_datei(zeile_ref: int, name: str, grund: str) -> dict:
    return {
        'id': None,
        'personennummer': None,
        'name': name,
        'email': '',
        'adresse': '',
        'grund': grund,
        'quelle': 'datei',
        'zeile_ref': zeile_ref,
    }


class SEPAMandatViewSet(viewsets.ModelViewSet):
    serializer_class = SEPAMandatSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SEPAMandat.objects.all()


def _parse_datum(s: str) -> str:
    """DD.MM.YYYY → YYYY-MM-DD, YYYY-MM-DD bleibt unverändert."""
    s = s.strip()
    if not s:
        return s
    if '.' in s:
        parts = s.split('.')
        if len(parts) == 3:
            return f'{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}'
    return s


def _norm_kontoart(s: str) -> str:
    """'900' → '.900', '.900' bleibt unverändert."""
    s = s.strip()
    if s and not s.startswith('.'):
        return f'.{s}'
    return s


class EigentumsVerhaeltnisViewSet(viewsets.ModelViewSet):
    serializer_class = EigentumsVerhaeltnisSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering = ['-beginn']

    def get_queryset(self):
        qs = EigentumsVerhaeltnis.objects.select_related(
            'person', 'einheit', 'einheit__objekt'
        ).prefetch_related('hausgeld_historie')
        objekt_id = self.request.query_params.get('objekt')
        person_id = self.request.query_params.get('person')
        aktiv = self.request.query_params.get('aktiv')
        if objekt_id:
            qs = qs.filter(einheit__objekt_id=objekt_id)
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

    # ------------------------------------------------------------------
    # Verträge CSV-Vorlage (Flächen vorbelegt + bestehende Daten)
    # ------------------------------------------------------------------
    @action(detail=False, methods=['get'], url_path='vertraege-vorlage')
    def vertraege_vorlage(self, request):
        from apps.objekte.models import Objekt, Einheit as EinheitModel
        objekt_id = request.query_params.get('objekt')
        if not objekt_id:
            return Response({'errors': ['objekt Parameter fehlt']}, status=400)
        try:
            objekt = Objekt.objects.get(pk=objekt_id)
        except Objekt.DoesNotExist:
            return Response({'errors': ['Objekt nicht gefunden']}, status=404)

        einheiten = EinheitModel.objects.filter(objekt=objekt).order_by('flaechennummer', 'einheit_nr')
        evs = (
            EigentumsVerhaeltnis.objects
            .filter(einheit__objekt=objekt, ende__isnull=True)
            .select_related('person')
            .prefetch_related('hausgeld_historie')
        )
        ev_by_einheit = {str(ev.einheit_id): ev for ev in evs}

        objnr = objekt.objektnummer or str(objekt_id)[:8]
        filename = f"{objnr}-Vertraege.csv"
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        writer = csv.writer(response, delimiter=';')
        writer.writerow([
            'Fl Nr. ', 'Personnummer', 'ET ab',
            'SA1', 'Betrag1', 'SA1 ab',
            'SA2', 'Betrag2', 'SA2 ab',
            'SA3', 'Betrag3', 'SA3 ab',
            'SA4', 'Betrag4', 'SA4 ab',
            'SA5', 'Betrag5', 'SA5 ab',
            'SA6', 'Betrag6', 'SA6 ab',
            'SA7', 'Betrag7', 'SA7 ab',
        ])

        heute = date.today()
        for einheit in einheiten:
            ev = ev_by_einheit.get(str(einheit.id))
            row = [einheit.flaechennummer or '']
            if ev:
                row.append(ev.person.personennummer)
                row.append(str(ev.beginn))
                latest = (
                    ev.hausgeld_historie
                    .filter(gueltig_ab__lte=heute)
                    .values('kontoart')
                    .annotate(max_datum=Max('gueltig_ab'))
                    .order_by('kontoart')
                )
                sollarten = []
                for art in latest:
                    eintrag = ev.hausgeld_historie.filter(
                        kontoart=art['kontoart'], gueltig_ab=art['max_datum']
                    ).first()
                    if eintrag:
                        sollarten.append((art['kontoart'], str(eintrag.betrag), str(art['max_datum'])))
                for i in range(7):
                    if i < len(sollarten):
                        row.extend(sollarten[i])
                    else:
                        row.extend(['', '', ''])
            else:
                row.extend(['', ''])
                row.extend(['', '', ''] * 7)
            writer.writerow(row)

        return response

    # ------------------------------------------------------------------
    # Verträge CSV-Vorschau (Parse + Prüfung ohne Speichern)
    # ------------------------------------------------------------------
    @action(detail=False, methods=['post'], url_path='vertraege-vorschau')
    def vertraege_vorschau(self, request):
        from apps.objekte.models import Einheit as EinheitModel
        objekt_id = request.query_params.get('objekt')
        if not objekt_id:
            return Response({'errors': ['objekt Parameter fehlt']}, status=400)

        file = request.FILES.get('file')
        if not file:
            return Response({'errors': ['Keine Datei hochgeladen']}, status=400)

        raw = file.read()
        content = None
        for enc in ('utf-8-sig', 'cp1252', 'latin-1'):
            try:
                content = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if content is None:
            return Response({'errors': ['Datei-Encoding nicht erkannt']}, status=400)

        lines = [l.rstrip() for l in content.splitlines()]
        lines = [l for l in lines if l and not l.startswith('#')]
        reader = csv.DictReader(io.StringIO('\n'.join(lines)), delimiter=';')

        # Alle Einheiten des Objekts vorladen (für Fallback + Hint)
        alle_einheiten = list(
            EinheitModel.objects.filter(objekt_id=objekt_id)
            .order_by('flaechennummer', 'einheit_nr')
            .values('id', 'flaechennummer', 'einheit_nr', 'lage')
        )
        fl_nr_index = {e['flaechennummer']: e for e in alle_einheiten if e['flaechennummer']}
        einheit_nr_index = {str(e['einheit_nr']): e for e in alle_einheiten}

        verfuegbare_fl = [e['flaechennummer'] or e['einheit_nr'] for e in alle_einheiten[:15]]
        fl_hint = ', '.join(str(v) for v in verfuegbare_fl)
        if len(alle_einheiten) > 15:
            fl_hint += f' … ({len(alle_einheiten)} gesamt)'

        rows = []
        for i, row in enumerate(reader, start=2):
            fl_nr = (row.get('Fl Nr. ') or row.get('Fl Nr.') or '').lstrip('﻿').strip()
            personnummer = row.get('Personnummer', '').strip()
            et_ab = _parse_datum(row.get('ET ab', ''))

            if not fl_nr:
                continue

            eintrag = {
                'zeile': i,
                'fl_nr': fl_nr,
                'personnummer': personnummer,
                'et_ab': et_ab,
                'sollarten': [],
                'status': 'ok',
                'fehler': [],
                'info': [],
                'einheit_info': None,
                'person_info': None,
                'ev_aktion': None,
            }

            # Einheit suchen: erst per flaechennummer, dann per einheit_nr
            gefunden = fl_nr_index.get(fl_nr) or einheit_nr_index.get(fl_nr)
            if gefunden:
                if not fl_nr_index.get(fl_nr):
                    eintrag['info'].append(f'Gefunden über Einheit-Nr. „{fl_nr}" (Fl.Nr. lautet {gefunden["flaechennummer"] or fl_nr})')
                eintrag['einheit_info'] = {
                    'id': str(gefunden['id']),
                    'einheit_nr': gefunden['einheit_nr'],
                    'lage': gefunden['lage'] or '',
                }
            else:
                eintrag['fehler'].append(
                    f'Fläche „{fl_nr}" nicht gefunden. Im Objekt vorhanden: {fl_hint}'
                )
                eintrag['status'] = 'fehler'

            # Person suchen
            if personnummer:
                try:
                    person = Person.objects.get(personennummer=personnummer)
                    eintrag['person_info'] = {
                        'id': str(person.id),
                        'name': person.name,
                    }
                except Person.DoesNotExist:
                    eintrag['fehler'].append(f'Person „{personnummer}" nicht gefunden')
                    eintrag['status'] = 'fehler'
            elif fl_nr:
                eintrag['info'].append('Kein Eigentümer angegeben – Zeile wird übersprungen')

            if personnummer and not et_ab:
                eintrag['fehler'].append('ET ab (Eintrittsdatum) fehlt')
                eintrag['status'] = 'fehler'

            # Vorhandenes EV + Personenkonto prüfen
            if eintrag['einheit_info'] and eintrag['person_info']:
                from apps.konten.models import Personenkonto
                einheit_obj = EinheitModel.objects.get(pk=eintrag['einheit_info']['id'])
                existing_ev = (
                    EigentumsVerhaeltnis.objects
                    .filter(einheit=einheit_obj, ende__isnull=True)
                    .select_related('person')
                    .first()
                )
                if existing_ev:
                    if str(existing_ev.person.id) == eintrag['person_info']['id']:
                        eintrag['ev_aktion'] = 'aktualisieren'
                        eintrag['info'].append(f'EV vorhanden ab {existing_ev.beginn} → Beginn wird aktualisiert')
                        # Personenkonto-Status
                        try:
                            pk_nr = existing_ev.personenkonto.kontonummer
                            eintrag['info'].append(f'Personenkonto {pk_nr} bereits vorhanden')
                        except Personenkonto.DoesNotExist:
                            eintrag['info'].append('Personenkonto wird neu angelegt')
                    else:
                        eintrag['ev_aktion'] = 'ersetzen'
                        eintrag['info'].append(f'Fläche hat bereits Eigentümer: {existing_ev.person.name}')
                        if eintrag['status'] == 'ok':
                            eintrag['status'] = 'warnung'
                        eintrag['info'].append('Personenkonto wird neu angelegt')
                else:
                    eintrag['ev_aktion'] = 'neu'
                    eintrag['info'].append('Personenkonto wird neu angelegt')

            # Sollarten parsen
            for idx in range(1, 8):
                sa = _norm_kontoart(row.get(f'SA{idx}', ''))
                betrag_raw = row.get(f'Betrag{idx}', '').strip()
                sa_ab = _parse_datum(row.get(f'SA{idx} ab', ''))
                if not sa and not betrag_raw:
                    continue
                try:
                    betrag_val = float(betrag_raw.replace(',', '.')) if betrag_raw else None
                except ValueError:
                    betrag_val = None
                    eintrag['fehler'].append(f'SA{idx}: Betrag „{betrag_raw}" ungültig')
                    eintrag['status'] = 'fehler'
                eintrag['sollarten'].append({
                    'kontoart': sa,
                    'betrag': betrag_val,
                    'betrag_raw': betrag_raw,
                    'gueltig_ab': sa_ab or et_ab,
                })

            rows.append(eintrag)

        ok_count = sum(1 for r in rows if r['status'] in ('ok', 'warnung') and r['person_info'])
        fehler_count = sum(1 for r in rows if r['status'] == 'fehler')
        return Response({
            'rows': rows,
            'ok_count': ok_count,
            'fehler_count': fehler_count,
            'objekt_einheiten': len(alle_einheiten),
            'fl_hint': fl_hint,
        })

    # ------------------------------------------------------------------
    # Verträge CSV-Import
    # ------------------------------------------------------------------
    @action(detail=False, methods=['post'], url_path='vertraege-import')
    def vertraege_import(self, request):
        from apps.objekte.models import Einheit as EinheitModel
        objekt_id = request.query_params.get('objekt')
        if not objekt_id:
            return Response({'errors': ['objekt Parameter fehlt']}, status=400)

        file = request.FILES.get('file')
        if not file:
            return Response({'errors': ['Keine Datei hochgeladen']}, status=400)

        try:
            raw = file.read()
            content = None
            for enc in ('utf-8-sig', 'cp1252', 'latin-1'):
                try:
                    content = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            if content is None:
                return Response({'errors': ['Datei-Encoding nicht erkannt']}, status=400)

            lines = [l.rstrip() for l in content.splitlines()]
            lines = [l for l in lines if l and not l.startswith('#')]
            reader = csv.DictReader(io.StringIO('\n'.join(lines)), delimiter=';')

            importiert = 0
            personenkonten_angelegt = 0
            fehler = []

            # Alle Einheiten vorladen für Fallback-Suche (einheit_nr)
            alle_einheiten_import = list(
                EinheitModel.objects.filter(objekt_id=objekt_id)
                .values('id', 'flaechennummer', 'einheit_nr')
            )
            fl_nr_idx = {e['flaechennummer']: e for e in alle_einheiten_import if e['flaechennummer']}
            einheit_nr_idx = {str(e['einheit_nr']): e for e in alle_einheiten_import}

            for i, row in enumerate(reader, start=2):
                fl_nr = (row.get('Fl Nr. ') or row.get('Fl Nr.') or '').lstrip('﻿').strip()
                personnummer = row.get('Personnummer', '').strip()
                et_ab = _parse_datum(row.get('ET ab', ''))

                if not fl_nr:
                    continue

                einheit_data = fl_nr_idx.get(fl_nr) or einheit_nr_idx.get(fl_nr)
                if not einheit_data:
                    fehler.append(f'Zeile {i}: Fläche „{fl_nr}" nicht im Objekt gefunden')
                    continue
                try:
                    einheit = EinheitModel.objects.get(pk=einheit_data['id'])
                except EinheitModel.DoesNotExist:
                    fehler.append(f'Zeile {i}: Fläche „{fl_nr}" nicht im Objekt gefunden')
                    continue

                if not personnummer:
                    continue

                try:
                    person = Person.objects.get(personennummer=personnummer)
                except Person.DoesNotExist:
                    fehler.append(f'Zeile {i}: Person „{personnummer}" nicht gefunden')
                    continue

                if not et_ab:
                    fehler.append(f'Zeile {i}: ET ab fehlt')
                    continue

                anderes_ev = (
                    EigentumsVerhaeltnis.objects
                    .filter(einheit=einheit, ende__isnull=True)
                    .exclude(person=person)
                    .select_related('person')
                    .first()
                )
                if anderes_ev:
                    fehler.append(
                        f'Zeile {i}: Einheit {einheit.einheit_nr} (Fl.Nr. {fl_nr}) '
                        f'ist bereits {anderes_ev.person.name} zugewiesen'
                    )
                    continue

                ev_qs = EigentumsVerhaeltnis.objects.filter(
                    einheit=einheit, person=person, ende__isnull=True
                )
                if ev_qs.exists():
                    ev = ev_qs.first()
                    if str(ev.beginn) != et_ab:
                        ev.beginn = et_ab
                        ev.save(update_fields=['beginn'])
                else:
                    ev = EigentumsVerhaeltnis.objects.create(
                        einheit=einheit, person=person, beginn=et_ab
                    )

                # Personenkonto anlegen (idempotent)
                from apps.konten.services import personenkonto_anlegen
                _, pk_created = personenkonto_anlegen(ev, einheit.objekt)
                if pk_created:
                    personenkonten_angelegt += 1

                for idx in range(1, 8):
                    sa = _norm_kontoart(row.get(f'SA{idx}', ''))
                    betrag_raw = row.get(f'Betrag{idx}', '').strip()
                    sa_ab = _parse_datum(row.get(f'SA{idx} ab', '')) or et_ab

                    if not sa or not betrag_raw:
                        continue

                    try:
                        betrag = Decimal(betrag_raw.replace(',', '.'))
                    except Exception:
                        fehler.append(f'Zeile {i}, SA{idx}: Betrag „{betrag_raw}" ungültig')
                        continue

                    HausgeldHistorie.objects.create(
                        eigentumsverhaeltnis=ev,
                        betrag=betrag,
                        gueltig_ab=sa_ab,
                        kontoart=sa,
                        erstellt_von=request.user,
                    )

                importiert += 1

            return Response({'importiert': importiert, 'personenkonten_angelegt': personenkonten_angelegt, 'fehler': fehler})

        except Exception as e:
            return Response({'errors': [f'Fehler: {str(e)}']}, status=400)



class HausgeldHistorieViewSet(viewsets.ModelViewSet):
    serializer_class = HausgeldHistorieSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = HausgeldHistorie.objects.select_related('eigentumsverhaeltnis', 'erstellt_von')
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
