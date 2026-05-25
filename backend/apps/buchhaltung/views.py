import csv
import io
import os
from datetime import date

from django.http import HttpResponse
from django.utils import timezone
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.objekte.models import Wirtschaftsjahr, EinheitVerbrauch
from apps.konten.models import KontoVerteilerSchluessel
from .models import (
    Buchungsart, Buchung, Buchungsstapel, OffenerPosten, KreditorOP,
    CamtImportEinstellung, CamtImportLog, ImportOrdnerEinstellung, Kontoumsatz,
    BankMatchRegel,
    Mahnlauf, Mahnung, Mahnsperre,
    Forderungsfall, Basiszinssatz,
    RAPPosition, RAPAufloesung,
    BankImport, Jahresabrechnung, EinzelAbrechnung,
    LastschriftLauf,
    HausgeldSollstellungslauf, HausgeldSollstellung,
    AutoLaufProtokoll,
    SepaZahlungslauf,
)
from .serializers import (
    BuchungsartSerializer,
    BuchungSerializer, BuchungListSerializer, BuchungsstapelSerializer,
    OffenerPostenSerializer,
    CamtImportEinstellungSerializer, CamtImportLogSerializer,
    ImportOrdnerEinstellungSerializer, KontoumsatzSerializer,
    BankBuchungSerializer, BankMatchRegelSerializer, KreditorOPSerializer,
    MahnlaufSerializer, MahnungSerializer, MahnsperreSerializer,
    ForderungsfallSerializer, BasiszinssatzSerializer,
    RAPPositionSerializer, RAPAufloesungSerializer,
    BankImportSerializer, JahresabrechnungSerializer, EinzelAbrechnungSerializer,
    LastschriftLaufSerializer,
    WirtschaftsjahrSerializer, KontoVerteilerSchluesselSerializer, EinheitVerbrauchSerializer,
    HausgeldSollstellungslaufSerializer,
    HausgeldSollstellungSerializer, HausgeldSollstellungListSerializer,
    AutoLaufProtokollSerializer,
    SepaZahlungslaufSerializer,
)
from .services.camt053 import parse_camt053
from .services.buchungserkennung import erkenne_buchung, lerne_aus_buchung
from .services.ebanking_erkennungs_service import fuehre_erkennung_aus
from .services.sepa_export import exportiere_sepa
from .services.sepa_lastschrift import exportiere_lastschrift
from .services.mahnwesen import simuliere_mahnlauf, fuehre_mahnlauf_aus
from .services.zinsen import berechne_verzugszinsen


class BuchungsartViewSet(viewsets.ReadOnlyModelViewSet):
    """BA-Katalog — read-only für alle Nutzer."""
    serializer_class = BuchungsartSerializer
    permission_classes = [IsAuthenticated]
    queryset = Buchungsart.objects.filter(aktiv=True).order_by('nr')

    @action(detail=False, methods=['get'], url_path='manuell-waehlbar')
    def manuell_waehlbar(self, request):
        """Manuell wählbare BAs, optional gefiltert nach ?buchungstyp=sachkonto|personenkonto|kreditor."""
        qs = self.get_queryset().filter(system_buchungsart=False)
        buchungstyp = request.query_params.get('buchungstyp')
        if buchungstyp:
            qs = qs.filter(buchungstyp=buchungstyp)
        else:
            qs = qs.filter(buchungstyp__isnull=False)
        return Response(BuchungsartSerializer(qs, many=True).data)


class BuchungViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['belegnr', 'buchungstext', 'verwendungszweck']
    ordering_fields = ['buchungsdatum', 'betrag', 'status']
    ordering = ['-buchungsdatum']

    def get_queryset(self):
        qs = Buchung.objects.select_related(
            'objekt', 'soll_konto', 'haben_konto', 'unterkonto',
            'erstellt_von', 'buchungsart',
        )
        params = self.request.query_params
        if objekt_id := params.get('objekt'):
            qs = qs.filter(objekt_id=objekt_id)
        if s := params.get('status'):
            qs = qs.filter(status=s)
        if von := params.get('von'):
            qs = qs.filter(buchungsdatum__gte=von)
        if bis := params.get('bis'):
            qs = qs.filter(buchungsdatum__lte=bis)
        if konto := params.get('konto'):
            qs = qs.filter(soll_konto_id=konto) | qs.filter(haben_konto_id=konto)
        if ba := params.get('buchungsart'):
            qs = qs.filter(buchungsart__nr=ba)
        if jahr := params.get('wirtschaftsjahr'):
            qs = qs.filter(wirtschaftsjahr=jahr)
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return BuchungListSerializer
        return BuchungSerializer

    @action(detail=False, methods=['get'], url_path='export-csv')
    def export_csv(self, request):
        qs = self.filter_queryset(self.get_queryset())
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        writer.writerow([
            'Datum', 'Belegnr', 'Betrag', 'BA', 'Soll-Konto',
            'Haben-Konto', 'Buchungstext', 'Status',
        ])
        for b in qs:
            ba = b.buchungsart.kuerzel if b.buchungsart else ''
            writer.writerow([
                b.buchungsdatum,
                b.belegnr,
                str(b.betrag).replace('.', ','),
                ba,
                f"{b.soll_konto.kontonummer} {b.soll_konto.kontoname}",
                f"{b.haben_konto.kontonummer} {b.haben_konto.kontoname}",
                b.buchungstext or b.verwendungszweck,
                b.status,
            ])
        response = HttpResponse(
            output.getvalue().encode('utf-8-sig'),
            content_type='text/csv; charset=utf-8-sig',
        )
        response['Content-Disposition'] = 'attachment; filename="buchungsjournal.csv"'
        return response

    @action(detail=True, methods=['post'], url_path='festschreiben')
    def festschreiben(self, request, pk=None):
        buchung = self.get_object()
        if buchung.status != 'entwurf':
            return Response(
                {'error': 'Nur Entwürfe können festgeschrieben werden'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        buchung.status = 'festgeschrieben'
        buchung.save(update_fields=['status'])
        return Response(BuchungSerializer(buchung, context={'request': request}).data)

    @action(detail=True, methods=['post'], url_path='stornieren')
    def stornieren(self, request, pk=None):
        original = self.get_object()
        if original.status == 'storniert':
            return Response(
                {'error': 'Buchung ist bereits storniert'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ba_sto = Buchungsart.objects.filter(kuerzel='STO').first()
        storno = Buchung.objects.create(
            objekt=original.objekt,
            buchungsart=ba_sto,
            betrag=original.betrag,
            soll_konto=original.haben_konto,
            haben_konto=original.soll_konto,
            unterkonto=original.unterkonto,
            buchungsdatum=date.today(),
            buchungstext=f'Storno zu Buchung {original.belegnr or str(original.id)[:8]}',
            wirtschaftsjahr=original.wirtschaftsjahr,
            storno_von=original,
            status='festgeschrieben',
            erstellt_von=request.user,
        )
        original.status = 'storniert'
        original.save(update_fields=['status'])
        if hasattr(original, 'offener_posten'):
            original.offener_posten.status = 'storniert'
            original.offener_posten.save(update_fields=['status'])
        return Response(BuchungSerializer(storno, context={'request': request}).data)


class OffenerPostenViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OffenerPostenSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering = ['faellig_ab']

    def get_queryset(self):
        qs = OffenerPosten.objects.select_related(
            'buchung', 'personenkonto', 'personenkonto__eigentuemer',
            'personenkonto__vertrag__einheit',
        )
        params = self.request.query_params
        if objekt_id := params.get('objekt'):
            qs = qs.filter(personenkonto__objekt_id=objekt_id)
        if s := params.get('status'):
            qs = qs.filter(status=s)
        if pk_id := params.get('personenkonto'):
            qs = qs.filter(personenkonto_id=pk_id)
        return qs


class CamtImportEinstellungViewSet(viewsets.ModelViewSet):
    serializer_class = CamtImportEinstellungSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return CamtImportEinstellung.objects.all()

    @action(detail=True, methods=['post'], url_path='verbindung-testen')
    def verbindung_testen(self, request, pk=None):
        einstellung = self.get_object()
        ordner = einstellung.import_ordner
        if not ordner:
            return Response({'ok': False, 'fehler': 'Kein Import-Ordner konfiguriert'})

        import tempfile, pathlib
        p = pathlib.Path(ordner)
        if not p.exists():
            return Response({'ok': False, 'fehler': f'Ordner existiert nicht: {ordner}'})
        if not os.access(ordner, os.R_OK | os.W_OK):
            return Response({'ok': False, 'fehler': 'Keine Lese-/Schreibrechte'})

        test_datei = p / '.immocore_test'
        try:
            test_datei.write_text('test')
            test_datei.unlink()
        except Exception as e:
            return Response({'ok': False, 'fehler': str(e)})

        einstellung.zuletzt_geprueft_am = timezone.now()
        einstellung.save(update_fields=['zuletzt_geprueft_am'])
        return Response({'ok': True, 'ordner': ordner})

    @action(detail=True, methods=['post'], url_path='jetzt-importieren')
    def jetzt_importieren(self, request, pk=None):
        einstellung = self.get_object()
        if not einstellung.import_ordner:
            return Response({'error': 'Kein Import-Ordner konfiguriert'}, status=400)
        from .tasks import scan_camt_einstellung
        result = scan_camt_einstellung(einstellung)
        return Response(result)


class CamtImportLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CamtImportLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = CamtImportLog.objects.select_related('einstellung').order_by('-zeitpunkt')
        limit = self.request.query_params.get('limit')
        if limit:
            qs = qs[:int(limit)]
        return qs


class ImportOrdnerEinstellungViewSet(viewsets.ModelViewSet):
    serializer_class = ImportOrdnerEinstellungSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = ImportOrdnerEinstellung.objects.all()
        if bereich := self.request.query_params.get('bereich'):
            qs = qs.filter(bereich=bereich)
        return qs

    @action(detail=True, methods=['post'], url_path='jetzt-importieren')
    def jetzt_importieren(self, request, pk=None):
        einstellung = self.get_object()
        if not einstellung.import_ordner:
            return Response({'error': 'Kein Import-Ordner konfiguriert'}, status=400)
        if einstellung.bereich == 'rechnungen':
            from apps.rechnungen.tasks import scan_rechnungen_einstellung
            result = scan_rechnungen_einstellung(einstellung)
        elif einstellung.bereich == 'dokumente':
            from apps.dokumente.tasks import scan_dokumente_einstellung
            result = scan_dokumente_einstellung(einstellung)
        else:
            return Response({'error': f'Unbekannter Bereich: {einstellung.bereich}'}, status=400)
        return Response(result)


class KontoumsatzViewSet(viewsets.ModelViewSet):
    serializer_class = KontoumsatzSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering = ['-buchungsdatum']

    def get_queryset(self):
        qs = Kontoumsatz.objects.select_related('objekt', 'bankkonto', 'buchung')
        params = self.request.query_params
        s = params.get('status')
        if s == 'unbekannt':
            return qs.filter(status='unbekannt')
        if objekt_id := params.get('objekt'):
            qs = qs.filter(objekt_id=objekt_id)
        if s:
            qs = qs.filter(status=s)
        return qs

    @action(detail=False, methods=['post'], url_path='iban-verknuepfen')
    def iban_verknuepfen(self, request):
        """
        Verknüpft alle Kontoumsätze mit bankkonto=NULL rückwirkend,
        sofern ein Bankkonto mit passender empfaenger_iban existiert.
        Einmalig nach nachträglicher IBAN-Anlage aufzurufen.
        """
        from apps.objekte.models import Bankkonto
        from django.db.models import Case, F, Value, When

        aktualisiert_gesamt = 0
        for bk in Bankkonto.objects.filter(iban__gt=''):
            qs = Kontoumsatz.objects.filter(empfaenger_iban=bk.iban, bankkonto__isnull=True)
            anzahl = qs.count()
            if anzahl:
                qs.update(
                    bankkonto=bk,
                    objekt=bk.objekt,
                    status=Case(
                        When(status='unbekannt', then=Value('importiert')),
                        default=F('status'),
                    ),
                )
                aktualisiert_gesamt += anzahl

        return Response({'aktualisiert': aktualisiert_gesamt})

    @action(detail=False, methods=['post'], url_path='camt-vorschau')
    def camt_vorschau(self, request):
        """
        CAMT-Datei parsen und Vorschau zurückgeben. Kein DB-Commit.
        Erkennt camt.054 und gibt entsprechendes Flag zurück.
        Body: multipart mit objekt (UUID) + datei (XML).
        """
        from .services.camt054_service import erkenne_camt_typ

        objekt_id = request.data.get('objekt')
        datei = request.FILES.get('datei')

        if not objekt_id or not datei:
            return Response(
                {'error': 'objekt und datei erforderlich'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from apps.objekte.models import Objekt
        try:
            objekt = Objekt.objects.get(pk=objekt_id)
        except Objekt.DoesNotExist:
            return Response({'error': 'Objekt nicht gefunden'}, status=status.HTTP_404_NOT_FOUND)

        xml_bytes = datei.read()
        camt_typ = erkenne_camt_typ(xml_bytes)

        # camt.054 → Stub-Response (kein Parsen der Transaktionen)
        if camt_typ == 'camt054':
            return Response({
                'camt_typ':          'camt054',
                'transaktionen':     [],
                'neu_anzahl':        0,
                'duplikat_anzahl':   0,
                'gesamt':            0,
                'objekt':            str(objekt.id),
                'objekt_bezeichnung': objekt.bezeichnung,
                'import_datei':      datei.name,
                'hinweis': (
                    'camt.054-Datei erkannt. Verarbeitung von Rücklastschriften '
                    'wird in der Mahnwesen-Spec implementiert. '
                    'Die Datei wird sicher gespeichert.'
                ),
            })

        try:
            transaktionen_roh = parse_camt053(xml_bytes)
        except Exception as exc:
            return Response(
                {'error': f'Fehler beim Parsen: {exc}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        vorschau = []
        for txn in transaktionen_roh:
            ist_duplikat = Kontoumsatz.objects.filter(sha256_hash=txn['sha256_hash']).exists()
            vorschau.append({**txn, 'status': 'duplikat' if ist_duplikat else 'neu'})

        neu_anzahl      = sum(1 for t in vorschau if t['status'] == 'neu')
        duplikat_anzahl = sum(1 for t in vorschau if t['status'] == 'duplikat')

        return Response({
            'camt_typ':          'camt053',
            'transaktionen':     vorschau,
            'neu_anzahl':        neu_anzahl,
            'duplikat_anzahl':   duplikat_anzahl,
            'gesamt':            len(vorschau),
            'objekt':            str(objekt.id),
            'objekt_bezeichnung': objekt.bezeichnung,
            'import_datei':      datei.name,
        })

    @action(detail=False, methods=['post'], url_path='camt-upload')
    def camt_upload(self, request):
        """
        Vorgeprüfte Transaktionen aus camt-vorschau importieren. Kein direkter Datei-Upload.
        Body: { objekt: UUID, transaktionen: [...], import_datei: str }
        Transaktionen mit status='duplikat' werden übersprungen.
        """
        objekt_id     = request.data.get('objekt')
        transaktionen = request.data.get('transaktionen')
        import_datei  = request.data.get('import_datei', '')

        if not objekt_id or not transaktionen:
            return Response(
                {'error': 'objekt und transaktionen fehlen — Datei zuerst mit camt-vorschau prüfen'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from apps.objekte.models import Objekt, Bankkonto
        try:
            objekt = Objekt.objects.get(pk=objekt_id)
        except Objekt.DoesNotExist:
            return Response({'error': 'Objekt nicht gefunden'}, status=status.HTTP_404_NOT_FOUND)

        importiert = 0
        duplikate  = 0
        erkannt    = 0

        for txn in transaktionen:
            if txn.get('status') == 'duplikat':
                duplikate += 1
                continue
            # Nochmals gegen DB prüfen (Race-Condition-Schutz)
            if Kontoumsatz.objects.filter(sha256_hash=txn['sha256_hash']).exists():
                duplikate += 1
                continue

            empfaenger_iban = txn.get('empfaenger_iban', '')
            bankkonto = None
            if empfaenger_iban:
                bankkonto = Bankkonto.objects.filter(
                    objekt=objekt, iban=empfaenger_iban
                ).first()

            ku = Kontoumsatz.objects.create(
                objekt=objekt,
                bankkonto=bankkonto,
                sha256_hash=txn['sha256_hash'],
                betrag=txn['betrag'],
                buchungsdatum=txn['buchungsdatum'],
                wertstellungsdatum=txn.get('wertstellungsdatum'),
                auftraggeber_name=txn.get('auftraggeber_name', ''),
                auftraggeber_iban=txn.get('auftraggeber_iban', ''),
                empfaenger_iban=empfaenger_iban,
                verwendungszweck=txn.get('verwendungszweck', ''),
                end_to_end_id=txn.get('end_to_end_id', ''),
                import_datei=import_datei,
            )

            try:
                fuehre_erkennung_aus(ku)
            except Exception as exc:
                import logging
                logging.getLogger(__name__).error("E-Banking Erkennung Fehler: %s", exc)

            if ku.status not in ('importiert', 'unbekannt'):
                erkannt += 1
            importiert += 1

        return Response({
            'importiert': importiert,
            'duplikate':  duplikate,
            'erkannt':    erkannt,
            'gesamt':     len(transaktionen),
        })

    @action(detail=False, methods=['post'], url_path='camt054-upload')
    def camt054_upload(self, request):
        """
        camt.054-Datei sicher speichern (STUB v1.0).
        Erzeugt CamtImportLog(typ='camt054', status='pending_mahnwesen_spec').
        Keine Buchung wird erzeugt.
        Body: multipart mit datei (XML).
        """
        from .services.camt054_service import verarbeite_camt054

        datei = request.FILES.get('datei')
        if not datei:
            return Response({'error': 'datei erforderlich'}, status=status.HTTP_400_BAD_REQUEST)

        xml_bytes = datei.read()
        log = CamtImportLog.objects.create(
            typ='camt054',
            import_ordner='',
            anzahl_dateien=1,
        )
        log._xml_inhalt = xml_bytes.decode('utf-8', errors='replace')
        verarbeite_camt054(log)

        return Response({
            'id':      str(log.id),
            'typ':     log.typ,
            'status':  log.status,
            'notiz':   log.notiz,
            'datei':   datei.name,
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'], url_path='camt054-liste')
    def camt054_liste(self, request):
        """Liste geparkter camt.054-Importe."""
        qs = CamtImportLog.objects.filter(typ='camt054').order_by('-zeitpunkt')
        serializer = CamtImportLogSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='zuordnen')
    def zuordnen(self, request, pk=None):
        ku = self.get_object()
        buchung_id = request.data.get('buchung')
        if not buchung_id:
            return Response({'error': 'buchung erforderlich'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            buchung = Buchung.objects.get(pk=buchung_id)
        except Buchung.DoesNotExist:
            return Response({'error': 'Buchung nicht gefunden'}, status=status.HTTP_404_NOT_FOUND)

        ku.buchung = buchung
        ku.status = 'manuell'
        ku.save(update_fields=['buchung', 'status'])
        return Response(KontoumsatzSerializer(ku).data)

    @action(detail=True, methods=['post'], url_path='buchen')
    def buchen(self, request, pk=None):
        from decimal import Decimal
        from django.db import transaction as db_transaction
        from apps.konten.models import Konto

        ku = self.get_object()

        if ku.status == 'gebucht':
            return Response({'error': 'Bereits gebucht'}, status=status.HTTP_400_BAD_REQUEST)

        buchungsart_id = request.data.get('buchungsart')
        buchungstext = request.data.get('buchungstext', '')
        betrag = abs(ku.betrag)
        ist_zugang = ku.betrag > 0

        buchungsart = None
        if buchungsart_id:
            buchungsart = Buchungsart.objects.filter(pk=buchungsart_id).first()

        bankkonto_sachkonto = Konto.objects.filter(
            objekt=ku.objekt, kontonummer='18000'
        ).first()

        if ist_zugang:
            # Zahlungseingang: Soll 18000 / Haben Personenkonto — OPOs ausgleichen
            opo_ids = request.data.get('offene_posten_ids', [])
            if not opo_ids:
                return Response(
                    {'error': 'Mindestens ein offener Posten erforderlich'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            opos = list(OffenerPosten.objects.filter(
                id__in=opo_ids,
                personenkonto__objekt=ku.objekt,
                status__in=['offen', 'teilverrechnet'],
            ).select_related('personenkonto'))

            if len(opos) != len(opo_ids):
                return Response(
                    {'error': 'Ungültige oder bereits verrechnete offene Posten'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if len({op.personenkonto_id for op in opos}) > 1:
                return Response(
                    {'error': 'Alle offenen Posten müssen zum gleichen Personenkonto gehören'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            summe = sum(op.betrag_offen for op in opos)
            if abs(summe - betrag) > Decimal('0.01'):
                return Response(
                    {'error': f'Summe der OPOs ({summe:.2f} €) stimmt nicht mit Transaktionsbetrag ({betrag:.2f} €) überein'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            with db_transaction.atomic():
                buchung = Buchung.objects.create(
                    objekt=ku.objekt,
                    buchungsart=buchungsart,
                    betrag=betrag,
                    soll_konto=bankkonto_sachkonto,
                    personenkonto=opos[0].personenkonto,
                    buchungsdatum=ku.buchungsdatum,
                    buchungstext=buchungstext or ku.verwendungszweck,
                    belegnr=f'ZE-{ku.buchungsdatum.strftime("%Y%m%d")}-{str(ku.id)[:8].upper()}',
                    erstellt_von=request.user,
                )
                for op in opos:
                    op.betrag_offen = Decimal('0')
                    op.status = 'verrechnet'
                    op.save(update_fields=['betrag_offen', 'status'])
                ku.buchung = buchung
                ku.status = 'gebucht'
                ku.save(update_fields=['buchung', 'status'])

        else:
            # Zahlungsausgang: Soll Sachkonto / Haben 18000
            soll_konto_id = request.data.get('soll_konto_id')
            if not soll_konto_id:
                return Response(
                    {'error': 'Sachkonto (soll_konto_id) erforderlich'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            soll_konto = Konto.objects.filter(
                pk=soll_konto_id, objekt=ku.objekt
            ).first()
            if not soll_konto:
                return Response(
                    {'error': 'Sachkonto nicht gefunden'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            with db_transaction.atomic():
                buchung = Buchung.objects.create(
                    objekt=ku.objekt,
                    buchungsart=buchungsart,
                    betrag=betrag,
                    soll_konto=soll_konto,
                    haben_konto=bankkonto_sachkonto,
                    buchungsdatum=ku.buchungsdatum,
                    buchungstext=buchungstext or ku.verwendungszweck,
                    belegnr=f'ZA-{ku.buchungsdatum.strftime("%Y%m%d")}-{str(ku.id)[:8].upper()}',
                    erstellt_von=request.user,
                )
                ku.buchung = buchung
                ku.status = 'gebucht'
                ku.save(update_fields=['buchung', 'status'])

        return Response(KontoumsatzSerializer(ku).data)


class MahnlaufViewSet(viewsets.ModelViewSet):
    serializer_class = MahnlaufSerializer
    permission_classes = [IsAuthenticated]
    ordering = ['-erstellt_am']

    def get_queryset(self):
        qs = Mahnlauf.objects.select_related('objekt', 'ausgefuehrt_von')
        if objekt_id := self.request.query_params.get('objekt'):
            qs = qs.filter(objekt_id=objekt_id)
        return qs

    @action(detail=False, methods=['post'], url_path='simulieren')
    def simulieren(self, request):
        objekt_id = request.data.get('objekt')
        if not objekt_id:
            return Response({'error': 'objekt erforderlich'}, status=status.HTTP_400_BAD_REQUEST)
        vorschau = simuliere_mahnlauf(objekt_id)
        return Response(vorschau)

    @action(detail=True, methods=['post'], url_path='ausfuehren')
    def ausfuehren(self, request, pk=None):
        try:
            ergebnis = fuehre_mahnlauf_aus(pk, request.user)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ergebnis)

    @action(detail=True, methods=['post'], url_path='freigeben')
    def freigeben(self, request, pk=None):
        lauf = self.get_object()
        if lauf.status != 'simulation':
            return Response({'error': 'Nur Simulationen können freigegeben werden'})
        lauf.status = 'freigegeben'
        lauf.freigabe_user = request.user
        lauf.freigabe_am = timezone.now()
        lauf.save(update_fields=['status', 'freigabe_user', 'freigabe_am'])
        return Response(MahnlaufSerializer(lauf, context={'request': request}).data)


class MahnungViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = MahnungSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Mahnung.objects.select_related('lauf', 'personenkonto', 'personenkonto__eigentuemer')
        if lauf_id := self.request.query_params.get('lauf'):
            qs = qs.filter(lauf_id=lauf_id)
        return qs


class MahnsperreViewSet(viewsets.ModelViewSet):
    serializer_class = MahnsperreSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Mahnsperre.objects.select_related('personenkonto', 'gesetzt_von')
        if pk_id := self.request.query_params.get('personenkonto'):
            qs = qs.filter(personenkonto_id=pk_id)
        if objekt_id := self.request.query_params.get('objekt'):
            qs = qs.filter(personenkonto__objekt_id=objekt_id)
        return qs

    @action(detail=True, methods=['post'], url_path='aufheben')
    def aufheben(self, request, pk=None):
        sperre = self.get_object()
        if sperre.aufgehoben_am:
            return Response({'error': 'Sperre ist bereits aufgehoben'})
        sperre.aufgehoben_am = timezone.now()
        sperre.aufgehoben_von = request.user
        sperre.save(update_fields=['aufgehoben_am', 'aufgehoben_von'])
        return Response(MahnsperreSerializer(sperre, context={'request': request}).data)


class ForderungsfallViewSet(viewsets.ModelViewSet):
    serializer_class = ForderungsfallSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Forderungsfall.objects.select_related(
            'personenkonto', 'personenkonto__eigentuemer', 'objekt'
        )
        params = self.request.query_params
        if objekt_id := params.get('objekt'):
            qs = qs.filter(objekt_id=objekt_id)
        if s := params.get('status'):
            qs = qs.filter(status=s)
        return qs

    @action(detail=True, methods=['post'], url_path='status-wechsel')
    def status_wechsel(self, request, pk=None):
        fall = self.get_object()
        neuer_status = request.data.get('status')
        erlaubte = dict(Forderungsfall.STATUS_CHOICES).keys()
        if neuer_status not in erlaubte:
            return Response(
                {'error': f'Ungültiger Status. Erlaubt: {list(erlaubte)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if neuer_status in ('uneinbringlich', 'abschreibung') and not request.data.get('beschluss_referenz'):
            return Response(
                {'error': 'Beschluss-Referenz Pflicht für Abschreibung'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        fall.status = neuer_status
        if request.data.get('beschluss_referenz'):
            fall.beschluss_referenz = request.data['beschluss_referenz']
        if neuer_status in ('erfolgreich', 'uneinbringlich', 'abschreibung'):
            from datetime import date
            fall.abgeschlossen_am = date.today()
        fall.save()
        return Response(ForderungsfallSerializer(fall, context={'request': request}).data)


class BasiszinssatzViewSet(viewsets.ModelViewSet):
    serializer_class = BasiszinssatzSerializer
    permission_classes = [IsAuthenticated]
    queryset = Basiszinssatz.objects.all()

    @action(detail=False, methods=['get'], url_path='aktuell')
    def aktuell(self, request):
        from .services.zinsen import get_basiszinssatz
        satz = get_basiszinssatz(date.today())
        return Response({'satz': str(satz), 'stichtag': str(date.today())})

    @action(detail=False, methods=['post'], url_path='zinsen-berechnen')
    def zinsen_berechnen(self, request):
        betrag = request.data.get('betrag')
        faellig_ab = request.data.get('faellig_ab')
        bis_datum = request.data.get('bis_datum')
        schuldner_typ = request.data.get('schuldner_typ', 'verbraucher')

        if not all([betrag, faellig_ab, bis_datum]):
            return Response({'error': 'betrag, faellig_ab, bis_datum erforderlich'})

        from decimal import Decimal
        from datetime import date as _date
        zinsen = berechne_verzugszinsen(
            Decimal(str(betrag)),
            _date.fromisoformat(faellig_ab),
            _date.fromisoformat(bis_datum),
            schuldner_typ,
        )
        return Response({'zinsen': str(zinsen)})


class RAPPositionViewSet(viewsets.ModelViewSet):
    serializer_class = RAPPositionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = RAPPosition.objects.select_related('objekt', 'soll_konto', 'haben_konto')
        if objekt_id := self.request.query_params.get('objekt'):
            qs = qs.filter(objekt_id=objekt_id)
        if s := self.request.query_params.get('status'):
            qs = qs.filter(status=s)
        return qs


class RAPAufloesungViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = RAPAufloesungSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = RAPAufloesung.objects.select_related('position')
        if position_id := self.request.query_params.get('position'):
            qs = qs.filter(position_id=position_id)
        return qs


# ---------------------------------------------------------------------------
# Legacy ViewSets (BankImport, Jahresabrechnung, EinzelAbrechnung)
# ---------------------------------------------------------------------------

class BankImportViewSet(viewsets.ModelViewSet):
    serializer_class = BankImportSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering = ['-buchungsdatum']

    def get_queryset(self):
        qs = BankImport.objects.select_related('objekt', 'buchung')
        if objekt_id := self.request.query_params.get('objekt'):
            qs = qs.filter(objekt_id=objekt_id)
        if s := self.request.query_params.get('status'):
            qs = qs.filter(status=s)
        return qs

    @action(detail=False, methods=['post'], url_path='camt053-vorschau')
    def camt053_vorschau(self, request):
        """
        CAMT.053-Datei parsen und Vorschau zurückgeben (Legacy BankImport). Kein DB-Commit.
        Body: multipart mit objekt (UUID) + datei (XML).
        """
        objekt_id = request.data.get('objekt')
        datei = request.FILES.get('datei')

        if not objekt_id or not datei:
            return Response(
                {'error': 'objekt und datei erforderlich'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from apps.objekte.models import Objekt
        try:
            objekt = Objekt.objects.get(pk=objekt_id)
        except Objekt.DoesNotExist:
            return Response({'error': 'Objekt nicht gefunden'}, status=status.HTTP_404_NOT_FOUND)

        try:
            transaktionen_roh = parse_camt053(datei.read())
        except Exception as exc:
            return Response({'error': f'Fehler beim Parsen: {exc}'}, status=status.HTTP_400_BAD_REQUEST)

        vorschau = []
        for txn in transaktionen_roh:
            ist_duplikat = BankImport.objects.filter(sha256_hash=txn['sha256_hash']).exists()
            vorschau.append({**txn, 'status': 'duplikat' if ist_duplikat else 'neu'})

        neu_anzahl      = sum(1 for t in vorschau if t['status'] == 'neu')
        duplikat_anzahl = sum(1 for t in vorschau if t['status'] == 'duplikat')

        return Response({
            'transaktionen':      vorschau,
            'neu_anzahl':         neu_anzahl,
            'duplikat_anzahl':    duplikat_anzahl,
            'gesamt':             len(vorschau),
            'objekt':             str(objekt.id),
            'objekt_bezeichnung': objekt.bezeichnung,
        })

    @action(detail=False, methods=['post'], url_path='camt053-upload')
    def camt053_upload(self, request):
        """
        Vorgeprüfte Transaktionen aus camt053-vorschau importieren (Legacy BankImport).
        Body: { objekt: UUID, transaktionen: [...] }
        """
        objekt_id     = request.data.get('objekt')
        transaktionen = request.data.get('transaktionen')

        if not objekt_id or not transaktionen:
            return Response(
                {'error': 'objekt und transaktionen fehlen — Datei zuerst mit camt053-vorschau prüfen'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from apps.objekte.models import Objekt
        try:
            objekt = Objekt.objects.get(pk=objekt_id)
        except Objekt.DoesNotExist:
            return Response({'error': 'Objekt nicht gefunden'}, status=status.HTTP_404_NOT_FOUND)

        importiert = 0
        duplikate  = 0
        ki_erkannt = 0

        for txn in transaktionen:
            if txn.get('status') == 'duplikat':
                duplikate += 1
                continue
            if BankImport.objects.filter(sha256_hash=txn['sha256_hash']).exists():
                duplikate += 1
                continue

            bi = BankImport.objects.create(
                objekt=objekt,
                sha256_hash=txn['sha256_hash'],
                auftraggeber_name=txn.get('auftraggeber_name', ''),
                auftraggeber_iban=txn.get('auftraggeber_iban', ''),
                betrag=txn['betrag'],
                buchungsdatum=txn['buchungsdatum'],
                wertstellungsdatum=txn.get('wertstellungsdatum'),
                verwendungszweck=txn.get('verwendungszweck', ''),
            )

            vorschlag = erkenne_buchung(bi)
            if vorschlag:
                bi.ki_vorschlag = vorschlag
                bi.status = 'erkannt'
                bi.save(update_fields=['ki_vorschlag', 'status'])
                ki_erkannt += 1

            importiert += 1

        return Response({
            'importiert':          importiert,
            'duplikate':           duplikate,
            'ki_erkannt':          ki_erkannt,
            'gesamt_transaktionen': len(transaktionen),
        })

    @action(detail=True, methods=['post'], url_path='bestaetigen')
    def bestaetigen(self, request, pk=None):
        bank_import = self.get_object()
        buchung_id = request.data.get('buchung')
        if not buchung_id:
            return Response({'error': 'buchung erforderlich'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            buchung = Buchung.objects.get(pk=buchung_id)
        except Buchung.DoesNotExist:
            return Response({'error': 'Buchung nicht gefunden'}, status=status.HTTP_404_NOT_FOUND)

        bank_import.buchung = buchung
        bank_import.status = 'manuell'
        bank_import.save(update_fields=['buchung', 'status'])
        lerne_aus_buchung(bank_import)
        return Response(BankImportSerializer(bank_import).data)

    @action(detail=False, methods=['post'], url_path='sepa-export')
    def sepa_export(self, request):
        objekt_id = request.data.get('objekt')
        buchung_ids = request.data.get('buchung_ids', [])
        bankkonto_id = request.data.get('auftraggeber_bankkonto')

        if not objekt_id or not buchung_ids or not bankkonto_id:
            return Response(
                {'error': 'objekt, buchung_ids und auftraggeber_bankkonto erforderlich'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from apps.objekte.models import Bankkonto
        try:
            bankkonto = Bankkonto.objects.get(pk=bankkonto_id)
        except Bankkonto.DoesNotExist:
            return Response({'error': 'Bankkonto nicht gefunden'}, status=status.HTTP_404_NOT_FOUND)

        buchungen = Buchung.objects.filter(
            id__in=buchung_ids,
            objekt_id=objekt_id,
            status='festgeschrieben',
        ).select_related('unterkonto__personenkonto__eigentuemer')

        if not buchungen.exists():
            return Response({'error': 'Keine buchbaren Buchungen gefunden'}, status=status.HTTP_404_NOT_FOUND)

        auftraggeber = {
            'name': bankkonto.kontoinhaber,
            'iban': bankkonto.iban,
            'bic': bankkonto.bic or 'NOTPROVIDED',
            'bank_bezeichnung': bankkonto.bezeichnung,
        }

        zahlungen = []
        for b in buchungen:
            if not b.unterkonto:
                continue
            ev = b.unterkonto.personenkonto.vertrag
            person = ev.person
            empfaenger_ibans = person.ibans or []
            if not empfaenger_ibans:
                continue
            zahlungen.append({
                'betrag': abs(b.betrag),
                'empfaenger_name': person.name,
                'empfaenger_iban': empfaenger_ibans[0],
                'empfaenger_bic': '',
                'verwendungszweck': b.buchungstext or b.verwendungszweck or f'Hausgeld {b.buchungsdatum.year}',
                'faelligkeitsdatum': b.wertstellungsdatum or date.today(),
                'end_to_end_id': str(b.id)[:35],
            })

        if not zahlungen:
            return Response({'error': 'Keine Zahlungen mit gültiger Empfänger-IBAN'}, status=status.HTTP_400_BAD_REQUEST)

        xml_bytes = exportiere_sepa(zahlungen, auftraggeber)
        response = HttpResponse(xml_bytes, content_type='application/xml')
        response['Content-Disposition'] = f'attachment; filename="sepa_export_{date.today().isoformat()}.xml"'
        return response


class JahresabrechnungViewSet(viewsets.ModelViewSet):
    serializer_class = JahresabrechnungSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering = ['-wirtschaftsjahr']

    def get_queryset(self):
        qs = Jahresabrechnung.objects.select_related('objekt', 'erstellt_von')
        if objekt_id := self.request.query_params.get('objekt'):
            qs = qs.filter(objekt_id=objekt_id)
        if s := self.request.query_params.get('status'):
            qs = qs.filter(status=s)
        return qs

    @action(detail=True, methods=['post'], url_path='sperren')
    def sperren(self, request, pk=None):
        ja = self.get_object()
        if ja.status == 'gesperrt':
            return Response({'error': 'Jahresabrechnung ist bereits gesperrt'}, status=status.HTTP_400_BAD_REQUEST)
        ja.status = 'gesperrt'
        ja.save(update_fields=['status'])
        return Response(JahresabrechnungSerializer(ja).data)

    @action(detail=True, methods=['post'], url_path='freigeben')
    def freigeben(self, request, pk=None):
        ja = self.get_object()
        if ja.status != 'entwurf':
            return Response({'error': 'Nur Entwürfe können freigegeben werden'}, status=status.HTTP_400_BAD_REQUEST)
        ja.status = 'freigegeben'
        ja.save(update_fields=['status'])
        return Response(JahresabrechnungSerializer(ja).data)


class EinzelAbrechnungViewSet(viewsets.ModelViewSet):
    serializer_class = EinzelAbrechnungSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = EinzelAbrechnung.objects.select_related('jahresabrechnung', 'einheit', 'personenkonto')
        if ja_id := self.request.query_params.get('jahresabrechnung'):
            qs = qs.filter(jahresabrechnung_id=ja_id)
        return qs


# ---------------------------------------------------------------------------
# Buchungsstapel
# ---------------------------------------------------------------------------

class BuchungsstapelViewSet(viewsets.ModelViewSet):
    serializer_class = BuchungsstapelSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Buchungsstapel.objects.select_related('erstellt_von', 'ausgebucht_von', 'objekt')
        if objekt_id := self.request.query_params.get('objekt'):
            qs = qs.filter(objekt_id=objekt_id)
        if status_filter := self.request.query_params.get('status'):
            qs = qs.filter(status=status_filter)
        return qs

    @action(detail=True, methods=['post'], url_path='ausbuchen')
    def ausbuchen(self, request, pk=None):
        from django.utils import timezone
        stapel = self.get_object()
        if stapel.status != 'offen':
            return Response(
                {'error': 'Nur offene Stapel können ausgebucht werden.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        anzahl = stapel.buchungen.filter(status='entwurf').update(status='festgeschrieben')
        stapel.status = 'ausgebucht'
        stapel.ausgebucht_von = request.user
        stapel.ausgebucht_am = timezone.now()
        stapel.save(update_fields=['status', 'ausgebucht_von', 'ausgebucht_am'])
        return Response({
            'ausgebucht': anzahl,
            'stapel': BuchungsstapelSerializer(stapel, context={'request': request}).data,
        })


class LastschriftLaufViewSet(viewsets.ModelViewSet):
    """Lastschrift-Läufe: Erstellung + SEPA pain.008 Export."""
    serializer_class = LastschriftLaufSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_queryset(self):
        qs = LastschriftLauf.objects.select_related(
            'objekt', 'hausgeld_sollstellungslauf', 'erstellt_von'
        )
        if objekt_id := self.request.query_params.get('objekt'):
            qs = qs.filter(objekt_id=objekt_id)
        return qs

    def create(self, request, *args, **kwargs):
        from decimal import Decimal
        from datetime import datetime
        from apps.objekte.models import Objekt

        objekt_id             = request.data.get('objekt_id')
        hg_lauf_id            = request.data.get('hg_lauf_id')
        faelligkeitsdatum_str = request.data.get('faelligkeitsdatum')
        bezeichnung           = request.data.get('bezeichnung', '')

        if not objekt_id:
            return Response({'error': 'Objekt fehlt'}, status=status.HTTP_400_BAD_REQUEST)
        if not faelligkeitsdatum_str:
            return Response({'error': 'Fälligkeitsdatum fehlt'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            faelligkeitsdatum = datetime.strptime(faelligkeitsdatum_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Ungültiges Fälligkeitsdatum'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            objekt = Objekt.objects.prefetch_related('bankkonten').get(id=objekt_id)
        except Objekt.DoesNotExist:
            return Response({'error': 'Objekt nicht gefunden'}, status=status.HTTP_400_BAD_REQUEST)

        if not objekt.glaeubiger_id:
            return Response({'error': 'Kein Gläubiger-ID am Objekt hinterlegt'}, status=status.HTTP_400_BAD_REQUEST)

        positionen = []
        ohne_mandat = []
        hg_lauf = None

        # ── Hausgeld-Nebenbuch ─────────────────────────────────────────
        if hg_lauf_id:
            from .models import HausgeldSollstellungslauf
            from .services.sepa_lastschrift import bestimme_suffix, baue_verwendungszweck
            try:
                hg_lauf = HausgeldSollstellungslauf.objects.prefetch_related(
                    'sollstellungen__splits__bankkonto_ziel',
                    'sollstellungen__eigentumsverhaeltnis__person__sepa_mandat',
                    'sollstellungen__eigentumsverhaeltnis__einheit',
                ).get(id=hg_lauf_id, objekt=objekt)
            except HausgeldSollstellungslauf.DoesNotExist:
                return Response({'error': 'Hausgeld-Lauf nicht gefunden'}, status=status.HTTP_400_BAD_REQUEST)

            if hg_lauf.status != 'commited':
                return Response(
                    {'error': f'Hausgeld-Lauf hat Status "{hg_lauf.status}" — nur "commited" erlaubt'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            for ss in hg_lauf.sollstellungen.filter(
                status_cached__in=('offen', 'teilbezahlt'), storniert_am__isnull=True
            ).select_related(
                'eigentumsverhaeltnis__person__sepa_mandat',
                'eigentumsverhaeltnis__einheit', 'objekt',
            ).prefetch_related('splits__bankkonto_ziel'):
                person = ss.eigentumsverhaeltnis.person
                mandat = getattr(person, 'sepa_mandat', None)
                if not mandat or not mandat.aktiv:
                    ohne_mandat.append({'sollstellung_id': str(ss.id), 'grund': 'Kein aktives SEPA-Mandat'})
                    continue

                if ss.sollstellungs_typ == 'hausgeld':
                    splits_je_bank: dict = {}
                    for split in ss.splits.all():
                        splits_je_bank.setdefault(str(split.bankkonto_ziel_id), []).append(split)
                    for bk_id_str, splits in splits_je_bank.items():
                        suffix = bestimme_suffix(bk_id_str, objekt)
                        betrag = sum(s.betrag for s in splits)
                        positionen.append({
                            'sollstellung_id':   str(ss.id),
                            'end_to_end_id':     f"{ss.opos_nr}-{suffix}",
                            'betrag':            float(betrag),
                            'schuldner_name':    person.name,
                            'schuldner_iban':    mandat.iban,
                            'schuldner_bic':     mandat.bic or 'NOTPROVIDED',
                            'mandatsreferenz':   mandat.mandatsreferenz,
                            'mandat_datum':      str(mandat.unterzeichnet_am),
                            'verwendungszweck':  baue_verwendungszweck(ss, suffix),
                            'faelligkeitsdatum': str(faelligkeitsdatum),
                            'seq_typ':           'RCUR',
                        })
                else:
                    # Sonderumlage / Abrechnungsergebnis: BA bestimmt Zielkonto
                    from .services.sollstellung_service import _bankkonto_fuer_ba
                    try:
                        bk = _bankkonto_fuer_ba(objekt, ss.ba)
                        suffix = bestimme_suffix(str(bk.pk), objekt)
                    except Exception:
                        suffix = 'S' if ss.sollstellungs_typ == 'sonderumlage' else 'A'
                    positionen.append({
                        'sollstellung_id':   str(ss.id),
                        'end_to_end_id':     f"{ss.opos_nr}-{suffix}",
                        'betrag':            float(ss.soll_betrag),
                        'schuldner_name':    person.name,
                        'schuldner_iban':    mandat.iban,
                        'schuldner_bic':     mandat.bic or 'NOTPROVIDED',
                        'mandatsreferenz':   mandat.mandatsreferenz,
                        'mandat_datum':      str(mandat.unterzeichnet_am),
                        'verwendungszweck':  baue_verwendungszweck(ss, suffix),
                        'faelligkeitsdatum': str(faelligkeitsdatum),
                        'seq_typ':           'RCUR',
                    })

        if not positionen:
            return Response(
                {
                    'error': 'Keine Lastschrift-Positionen — alle Eigentümer ohne SEPA-Mandat?' if ohne_mandat else 'Keine Sollstellungen vorhanden',
                    'ohne_mandat': ohne_mandat,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        gesamt = sum(Decimal(str(p['betrag'])) for p in positionen)

        lauf = LastschriftLauf.objects.create(
            objekt=objekt,
            hausgeld_sollstellungslauf=hg_lauf,
            bezeichnung=bezeichnung or f"Lastschrift {faelligkeitsdatum.strftime('%m/%Y')}",
            faelligkeitsdatum=faelligkeitsdatum,
            erstellt_von=request.user,
            anzahl_positionen=len(positionen),
            gesamt_summe=gesamt,
            positionen=positionen,
            ohne_mandat=ohne_mandat,
        )

        return Response(
            LastschriftLaufSerializer(lauf, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['get'], url_path='xml')
    def xml(self, request, pk=None):
        """SEPA pain.008 XML herunterladen + beim ersten Abruf Buchungen erstellen."""
        from decimal import Decimal
        from datetime import datetime
        from django.db import transaction as db_transaction
        from apps.konten.models import Konto, Personenkonto as PKModel

        lauf = self.get_object()
        objekt = lauf.objekt

        if not lauf.positionen:
            return Response({'error': 'Keine Positionen vorhanden'}, status=status.HTTP_400_BAD_REQUEST)

        bankkonto = objekt.bankkonten.filter(aktiv=True, konto_typ='bewirtschaftung').first()
        if not bankkonto:
            return Response({'error': 'Kein Bewirtschaftungs-Bankkonto gefunden'}, status=status.HTTP_400_BAD_REQUEST)

        # Buchungen beim ersten XML-Abruf erstellen
        if not lauf.buchungen_erstellt:
            from apps.objekte.models import Wirtschaftsjahr as WJModel
            wj_obj = WJModel.objects.filter(
                objekt=objekt, jahr=lauf.faelligkeitsdatum.year
            ).first()
            gegenkonto = Konto.objects.filter(wirtschaftsjahr__objekt=objekt, kontonummer='13650').first()
            if not gegenkonto:
                return Response(
                    {'error': 'Konto 13650 (DCL-Debitor) nicht im Kontenplan gefunden'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Belegnummer-Basis berechnen (einmalig vor dem Loop)
            prefix = f'LS-{lauf.faelligkeitsdatum.year}-'
            last_belegnr = (
                Buchung.objects.filter(belegnr__startswith=prefix)
                .order_by('-belegnr').values_list('belegnr', flat=True).first()
            )
            try:
                lfd = int(last_belegnr.rsplit('-', 1)[-1]) + 1 if last_belegnr else 1
            except ValueError:
                lfd = 1

            positionen_updated = []
            with db_transaction.atomic():
                for p in lauf.positionen:
                    pk_id = p.get('personenkonto_id')
                    if not pk_id:
                        positionen_updated.append(p)
                        continue

                    try:
                        pk_obj = PKModel.objects.get(id=pk_id)
                    except PKModel.DoesNotExist:
                        positionen_updated.append(p)
                        continue

                    betrag = Decimal(str(p['betrag']))
                    belegnr = f'{prefix}{lfd:05d}'
                    lfd += 1

                    buchung = Buchung.objects.create(
                        objekt=objekt,
                        soll_konto=gegenkonto,
                        personenkonto=pk_obj,
                        betrag=betrag,
                        buchungsdatum=lauf.faelligkeitsdatum,
                        buchungstext=(
                            p.get('verwendungszweck')
                            or f"SEPA-Lastschrift {p['schuldner_name']}"
                        ),
                        belegnr=belegnr,
                        beleg_referenz=f'LS-{str(lauf.id)[:8]}',
                        wirtschaftsjahr=wj_obj,
                        status='festgeschrieben',
                        erstellt_von=request.user,
                    )

                    # Offene Posten des Personenkontos ausgleichen
                    opos = list(OffenerPosten.objects.filter(
                        personenkonto=pk_obj,
                        status__in=['offen', 'teilverrechnet'],
                    ))
                    for op in opos:
                        op.betrag_offen = Decimal('0')
                        op.status = 'verrechnet'
                        op.save(update_fields=['betrag_offen', 'status'])

                    positionen_updated.append({
                        **p,
                        'buchung_id': str(buchung.id),
                        'belegnr': belegnr,
                        'opos_ausgeglichen': len(opos),
                    })

                lauf.buchungen_erstellt = True
                lauf.buchungen_datum = lauf.faelligkeitsdatum
                lauf.positionen = positionen_updated
                lauf.status = 'exportiert'
                lauf.save(update_fields=['buchungen_erstellt', 'buchungen_datum', 'positionen', 'status'])

        # SEPA XML generieren
        glaeubiger = {
            'name': bankkonto.kontoinhaber or objekt.bezeichnung,
            'iban': bankkonto.iban,
            'bic': bankkonto.bic,
            'glaeubiger_id': objekt.glaeubiger_id,
        }

        lastschriften = []
        for p in lauf.positionen:
            lastschriften.append({
                'betrag': Decimal(str(p['betrag'])),
                'schuldner_name': p['schuldner_name'],
                'schuldner_iban': p['schuldner_iban'],
                'schuldner_bic': p.get('schuldner_bic', 'NOTPROVIDED'),
                'mandatsreferenz': p['mandatsreferenz'],
                'mandat_datum': datetime.strptime(p['mandat_datum'], '%Y-%m-%d').date(),
                'verwendungszweck': p.get('verwendungszweck', ''),
                'faelligkeitsdatum': lauf.faelligkeitsdatum,
                'seq_typ': p.get('seq_typ', 'RCUR'),
            })

        xml_bytes = exportiere_lastschrift(lastschriften, glaeubiger)
        dateiname = f"lastschrift_{lauf.faelligkeitsdatum.strftime('%Y%m%d')}_{objekt.objektnummer}.xml"
        response = HttpResponse(xml_bytes, content_type='application/xml')
        response['Content-Disposition'] = f'attachment; filename="{dateiname}"'
        return response


# ---------------------------------------------------------------------------
# Wirtschaftsjahr — Liste, Detail, Folgejahr-Eröffnung
# ---------------------------------------------------------------------------

class WirtschaftsjahrViewSet(viewsets.ReadOnlyModelViewSet):
    """Wirtschaftsjahre — read-only Basis; Folgejahr via dedizierte Actions."""
    serializer_class   = WirtschaftsjahrSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [filters.OrderingFilter]
    ordering           = ['objekt__bezeichnung', 'jahr']

    def get_queryset(self):
        qs = Wirtschaftsjahr.objects.select_related('objekt', 'vorjahr')
        p  = self.request.query_params
        if p.get('objekt'):
            qs = qs.filter(objekt_id=p['objekt'])
        if p.get('status'):
            qs = qs.filter(status=p['status'])
        return qs

    @action(detail=False, methods=['post'], url_path='folgejahr/preview')
    def folgejahr_preview(self, request):
        """Vorschau: prüft je Objekt, ob Folgejahr angelegt werden kann."""
        from .services.wirtschaftsjahr import folgejahr_preview
        objekt_ids = request.data.get('objekt_ids', [])
        if not objekt_ids:
            return Response({'error': 'objekt_ids erforderlich'}, status=status.HTTP_400_BAD_REQUEST)
        ergebnisse = folgejahr_preview(objekt_ids)
        return Response({'ergebnisse': ergebnisse})

    @action(detail=False, methods=['post'], url_path='folgejahr/commit')
    def folgejahr_commit(self, request):
        """Folgejahr für mehrere Objekte atomisch anlegen."""
        from .services.wirtschaftsjahr import folgejahr_eroeffnen_batch
        objekt_ids = request.data.get('objekt_ids', [])
        if not objekt_ids:
            return Response({'error': 'objekt_ids erforderlich'}, status=status.HTTP_400_BAD_REQUEST)
        ergebnisse = folgejahr_eroeffnen_batch(objekt_ids, request.user)
        return Response({'ergebnisse': ergebnisse})


# ---------------------------------------------------------------------------
# Hausgeld-Nebenbuch ViewSets
# ---------------------------------------------------------------------------

class HausgeldSollstellungslaufViewSet(viewsets.ModelViewSet):
    """Hausgeld-Massenlauf: Vorschau, Commit, Storno."""
    serializer_class   = HausgeldSollstellungslaufSerializer
    permission_classes = [IsAuthenticated]
    http_method_names  = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        qs = HausgeldSollstellungslauf.objects.select_related('objekt', 'erstellt_von')
        if objekt_id := self.request.query_params.get('objekt'):
            qs = qs.filter(objekt_id=objekt_id)
        if typ := self.request.query_params.get('typ'):
            qs = qs.filter(typ=typ)
        return qs.order_by('-periode')

    def perform_create(self, serializer):
        serializer.save(erstellt_von=self.request.user)

    def _parse_periode(self, periode_str):
        """Akzeptiert 'YYYY-MM' oder 'YYYY-MM-DD', gibt date(year, month, 1) zurück."""
        from datetime import datetime
        if not periode_str:
            raise ValueError("periode fehlt")
        if len(periode_str) == 7:
            periode_str = periode_str + '-01'
        return datetime.strptime(periode_str, '%Y-%m-%d').date()

    @action(detail=False, methods=['post'], url_path='simulieren')
    def simulieren(self, request):
        """Vorschau ohne DB-Commit."""
        from .services.sollstellungslauf_service import simuliere_hausgeld_monat
        from apps.objekte.models import Objekt, Wirtschaftsjahr
        from django.core.exceptions import ValidationError as DjVE
        try:
            objekt  = Objekt.objects.get(pk=request.data.get('objekt_id'))
            periode = self._parse_periode(request.data.get('periode'))
        except (Objekt.DoesNotExist, ValueError) as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        wj = None
        if wj_id := request.data.get('wirtschaftsjahr_id'):
            try:
                wj = Wirtschaftsjahr.objects.get(pk=wj_id, objekt=objekt)
            except Wirtschaftsjahr.DoesNotExist:
                return Response({'error': 'Wirtschaftsjahr nicht gefunden'}, status=status.HTTP_400_BAD_REQUEST)
        vorschau = simuliere_hausgeld_monat(objekt, periode)
        if wj:
            vorschau['wirtschaftsjahr_id'] = str(wj.pk)
            vorschau['wirtschaftsjahr_jahr'] = wj.jahr
        return Response(vorschau)

    @action(detail=False, methods=['post'], url_path='erstellen')
    def erstellen(self, request):
        """Lauf-Datensatz mit Status 'vorschau' anlegen."""
        from .services.sollstellungslauf_service import erstelle_lauf_aus_vorschau
        from apps.objekte.models import Objekt, Wirtschaftsjahr
        from django.core.exceptions import ValidationError as DjVE
        try:
            objekt  = Objekt.objects.get(pk=request.data.get('objekt_id'))
            periode = self._parse_periode(request.data.get('periode'))
        except (Objekt.DoesNotExist, ValueError) as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        wj = None
        if wj_id := request.data.get('wirtschaftsjahr_id'):
            try:
                wj = Wirtschaftsjahr.objects.get(pk=wj_id, objekt=objekt)
            except Wirtschaftsjahr.DoesNotExist:
                return Response({'error': 'Wirtschaftsjahr nicht gefunden'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            lauf = erstelle_lauf_aus_vorschau(objekt, periode, request.user, wirtschaftsjahr=wj)
        except DjVE as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(HausgeldSollstellungslaufSerializer(lauf).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='freigeben')
    def freigeben(self, request, pk=None):
        """vorschau → freigegeben (Vier-Augen)."""
        from .services.sollstellungslauf_service import freigeben_lauf
        from django.core.exceptions import ValidationError as DjVE
        lauf = self.get_object()
        try:
            lauf = freigeben_lauf(lauf, request.user)
        except DjVE as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(HausgeldSollstellungslaufSerializer(lauf).data)

    @action(detail=True, methods=['post'], url_path='commiten')
    def commiten(self, request, pk=None):
        """freigegeben → commited — erzeugt alle Sollstellungen."""
        from .services.sollstellungslauf_service import commiten_lauf
        from django.core.exceptions import ValidationError as DjVE
        lauf = self.get_object()
        try:
            lauf = commiten_lauf(lauf, request.user)
        except DjVE as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(HausgeldSollstellungslaufSerializer(lauf).data)

    @action(detail=False, methods=['post'], url_path='hausgeld-lauf-starten')
    def hausgeld_lauf_starten(self, request):
        """Legacy-Direktcommit (rückwärtskompatibel, wird in Phase D entfernt)."""
        from .services.sollstellungslauf_service import run_hausgeld_monat
        from apps.objekte.models import Objekt
        from django.core.exceptions import ValidationError as DjVE

        objekt_id = request.data.get('objekt')
        periode_str = request.data.get('periode')
        if not objekt_id or not periode_str:
            return Response({'error': 'objekt und periode erforderlich'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            objekt  = Objekt.objects.get(pk=objekt_id)
            periode = self._parse_periode(periode_str)
        except (Objekt.DoesNotExist, ValueError) as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        try:
            lauf = run_hausgeld_monat(objekt, periode, request.user)
        except DjVE as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(HausgeldSollstellungslaufSerializer(lauf).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='stornieren')
    def stornieren(self, request, pk=None):
        from .services.sollstellungslauf_service import storniere_lauf
        from django.core.exceptions import ValidationError as DjVE
        lauf  = self.get_object()
        grund = request.data.get('grund', '')
        try:
            storniere_lauf(lauf, grund, request.user)
        except DjVE as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(HausgeldSollstellungslaufSerializer(lauf).data)


class HausgeldSollstellungViewSet(viewsets.ReadOnlyModelViewSet):
    """Lese-Zugriff + Storno für einzelne Hausgeld-Sollstellungen."""
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return HausgeldSollstellungSerializer
        return HausgeldSollstellungListSerializer

    def get_queryset(self):
        qs = HausgeldSollstellung.objects.select_related(
            'objekt', 'eigentumsverhaeltnis__person',
            'eigentumsverhaeltnis__einheit', 'eigentumsverhaeltnis__personenkonto',
            'ba', 'sollstellungslauf',
        ).prefetch_related('splits__ba', 'splits__bankkonto_ziel')
        p = self.request.query_params
        if objekt_id := p.get('objekt'):
            qs = qs.filter(objekt_id=objekt_id)
        if ev_id := p.get('eigentumsverhaeltnis'):
            qs = qs.filter(eigentumsverhaeltnis_id=ev_id)
        if s := p.get('status'):
            qs = qs.filter(status_cached=s)
        if typ := p.get('typ'):
            qs = qs.filter(sollstellungs_typ=typ)
        if lauf_id := p.get('lauf'):
            qs = qs.filter(sollstellungslauf_id=lauf_id)
        return qs.order_by('-periode')

    @action(detail=True, methods=['post'], url_path='stornieren')
    def stornieren(self, request, pk=None):
        from .services.sollstellung_service import storniere_sollstellung
        from django.core.exceptions import ValidationError as DjVE
        ss    = self.get_object()
        grund = request.data.get('grund', '')
        try:
            storniere_sollstellung(ss, grund, request.user)
        except DjVE as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(HausgeldSollstellungSerializer(ss).data)


class AutoLaufProtokollViewSet(viewsets.ReadOnlyModelViewSet):
    """Auto-Pipeline-Protokolle — read-only + Einstellungen + Datei-Download."""
    serializer_class   = AutoLaufProtokollSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = AutoLaufProtokoll.objects.select_related('objekt')
        if objekt_id := self.request.query_params.get('objekt'):
            qs = qs.filter(objekt_id=objekt_id)
        return qs.order_by('-ausgefuehrt_am')

    def list(self, request, *args, **kwargs):
        """Liste limitiert auf 100 Einträge."""
        from rest_framework.response import Response as DRFResponse
        qs = self.filter_queryset(self.get_queryset())[:100]
        serializer = self.get_serializer(qs, many=True)
        return DRFResponse(serializer.data)

    @action(detail=False, methods=['get'], url_path='einstellungen')
    def einstellungen(self, request):
        """Gibt SEPA_AUTOPILOT_AKTIV, nächsten Lauf und Objekt-Anzahl zurück."""
        from datetime import date as dt_date
        from django.conf import settings as dj_settings
        from apps.objekte.models import Objekt as ObjektModel

        heute = timezone.localdate()
        stichtag = dj_settings.SEPA_AUTOPILOT_STICHTAG
        if heute.day < stichtag:
            naechster_lauf = dt_date(heute.year, heute.month, stichtag)
        elif heute.month == 12:
            naechster_lauf = dt_date(heute.year + 1, 1, stichtag)
        else:
            naechster_lauf = dt_date(heute.year, heute.month + 1, stichtag)

        aktive_objekte = ObjektModel.objects.filter(
            auto_pipeline_aktiv=True, status='aktiv'
        ).count()

        return Response({
            'aktiv':           dj_settings.SEPA_AUTOPILOT_AKTIV,
            'stichtag':        stichtag,
            'naechster_lauf':  naechster_lauf,
            'aktive_objekte':  aktive_objekte,
            'sepa_output_dir': dj_settings.SEPA_OUTPUT_DIR,
            'vorlauf_bd':      dj_settings.SEPA_AUTOPILOT_VORLAUF_BD,
        })

    @action(detail=True, methods=['get'], url_path='download-pain008')
    def download_pain008(self, request, pk=None):
        """Lädt die pain.008-Datei des Protokoll-Eintrags herunter."""
        import os
        from django.http import FileResponse

        protokoll = self.get_object()
        if not protokoll.datei_pfad:
            return Response({'error': 'Kein Dateipfad hinterlegt.'}, status=status.HTTP_404_NOT_FOUND)
        if not os.path.exists(protokoll.datei_pfad):
            return Response(
                {'error': f'Datei nicht gefunden: {protokoll.datei_pfad}'},
                status=status.HTTP_404_NOT_FOUND,
            )
        filename = os.path.basename(protokoll.datei_pfad)
        response = FileResponse(open(protokoll.datei_pfad, 'rb'))
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Content-Type'] = 'application/xml'
        return response


# ---------------------------------------------------------------------------
# E-Banking Phase E — neue Endpunkte
# ---------------------------------------------------------------------------

class EBankingBuchungViewSet(viewsets.ModelViewSet):
    """
    Kontoumsätze mit E-Banking-spezifischen Aktionen und erweitertem Serializer.
    Registriert unter e-banking/bank-buchungen/.
    """
    serializer_class = BankBuchungSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_queryset(self):
        qs = Kontoumsatz.objects.select_related(
            'objekt', 'bankkonto', 'buchung',
            'erkannt_gegenkonto', 'erkannt_kreditor',
            'erkannt_eigentumsverhaeltnis__einheit',
            'erkannt_eigentumsverhaeltnis__person',
            'verbucht_von', 'match_regel',
            'buchung__personenkonto__eigentuemer',
            'buchung__personenkonto__vertrag__einheit',
        )
        p = self.request.query_params

        if objekt_id := p.get('objekt'):
            qs = qs.filter(objekt_id=objekt_id)
        if bankkonto_id := p.get('bankkonto'):
            qs = qs.filter(bankkonto_id=bankkonto_id)

        # Status-Filter: kommagetrennte Liste oder einzelner Wert
        status_param = p.get('status')
        if status_param:
            werte = [s.strip() for s in status_param.split(',') if s.strip()]
            if werte:
                qs = qs.filter(status__in=werte)

        if datum_von := p.get('datum_von'):
            qs = qs.filter(buchungsdatum__gte=datum_von)
        if datum_bis := p.get('datum_bis'):
            qs = qs.filter(buchungsdatum__lte=datum_bis)
        if betrag_min := p.get('betrag_min'):
            qs = qs.filter(betrag__gte=betrag_min)
        if betrag_max := p.get('betrag_max'):
            qs = qs.filter(betrag__lte=betrag_max)
        if suche := p.get('suche'):
            from django.db.models import Q
            qs = qs.filter(
                Q(auftraggeber_name__icontains=suche)
                | Q(auftraggeber_iban__icontains=suche)
                | Q(verwendungszweck__icontains=suche)
            )
        return qs.order_by('-buchungsdatum')

    @action(detail=True, methods=['post'], url_path='verbuchen')
    def verbuchen(self, request, pk=None):
        from decimal import Decimal
        from django.core.exceptions import ValidationError as DjValidationError
        from django.db import transaction as db_tx
        from django.utils import timezone as tz
        from apps.konten.models import Konto
        from apps.personen.models import Person, EigentumsVerhaeltnis
        from .services.ebanking_buchungs_service import verbuche
        from .services.ebanking_erkennungs_service import regel_anlegen_oder_aktualisieren

        ku = self.get_object()
        if ku.status == 'verbucht':
            return Response({'error': 'Kontoumsatz ist bereits verbucht.'}, status=status.HTTP_400_BAD_REQUEST)
        if ku.status == 'storniert':
            return Response({'error': 'Kontoumsatz ist storniert.'}, status=status.HTTP_400_BAD_REQUEST)

        buchungs_typ   = request.data.get('buchungs_typ', 'sachkonto')
        notiz          = request.data.get('notiz', '')
        opt_out_lernen = bool(request.data.get('opt_out_lernen', False))

        # ── Debitorische Buchung (Hausgeld-Zahlungseingang) ──────────────────
        if buchungs_typ == 'debitor':
            from apps.konten.models import Personenkonto
            from apps.objekte.models import Wirtschaftsjahr
            from .services.zahlungs_zuordnung_service import verrechne_eingang_manuell
            from .services.ebanking_buchungs_service import _ermittle_bank_sachkonto

            pk_id = request.data.get('personenkonto_id')
            if not pk_id:
                return Response(
                    {'error': 'personenkonto_id ist erforderlich.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                personenkonto = Personenkonto.objects.get(pk=pk_id, objekt=ku.objekt)
            except Personenkonto.DoesNotExist:
                return Response(
                    {'error': 'Personenkonto nicht gefunden oder gehört nicht zum Objekt.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            bank_konto = _ermittle_bank_sachkonto(ku)
            if not bank_konto:
                return Response({'error': 'Kein Bank-Sachkonto (18xxx) gefunden.'}, status=status.HTTP_400_BAD_REQUEST)

            wj = (
                Wirtschaftsjahr.objects.filter(objekt=ku.objekt, status='offen').order_by('-jahr').first()
                or Wirtschaftsjahr.objects.filter(objekt=ku.objekt).order_by('-jahr').first()
            )
            if not wj:
                return Response({'error': 'Kein aktives Wirtschaftsjahr gefunden.'}, status=status.HTTP_400_BAD_REQUEST)

            with db_tx.atomic():
                try:
                    b = verrechne_eingang_manuell(
                        personenkonto=personenkonto,
                        bank_sachkonto=bank_konto,
                        betrag=abs(ku.betrag),
                        buchungsdatum=ku.buchungsdatum,
                        buchungstext=ku.verwendungszweck or 'E-Banking Zahlungseingang',
                        wirtschaftsjahr=wj,
                        user=request.user,
                    )
                except Exception as exc:
                    return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
                ku.buchung      = b
                ku.status       = 'verbucht'
                ku.verbucht_am  = tz.now()
                ku.verbucht_von = request.user
                if notiz:
                    ku.notiz = notiz
                ku.save()
            ku.refresh_from_db()
            return Response(BankBuchungSerializer(ku, context={'request': request}).data)

        # ── Sachkonto- / Kreditorische Buchung ───────────────────────────────
        gegenkonto_id  = request.data.get('gegenkonto_id')
        kreditor_id    = request.data.get('kreditor_id')
        ev_id          = request.data.get('eigentumsverhaeltnis_id')
        kreditor_op_id = request.data.get('kreditor_op_id') or None

        gegenkonto = None
        if gegenkonto_id:
            try:
                gegenkonto = Konto.objects.get(pk=gegenkonto_id)
            except Konto.DoesNotExist:
                return Response({'error': 'Gegenkonto nicht gefunden'}, status=status.HTTP_400_BAD_REQUEST)

        kreditor = Person.objects.filter(pk=kreditor_id).first() if kreditor_id else None
        ev       = EigentumsVerhaeltnis.objects.filter(pk=ev_id).first() if ev_id else None

        try:
            verbuche(
                ku,
                verbucht_von=request.user,
                gegenkonto=gegenkonto,
                eigentumsverhaeltnis=ev,
                kreditor=kreditor,
                notiz=notiz,
                kreditor_op_id=kreditor_op_id,
            )
        except DjValidationError as e:
            return Response(
                {'error': e.messages[0] if e.messages else str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not opt_out_lernen:
            gk_final = gegenkonto or ku.erkannt_gegenkonto
            if gk_final:
                try:
                    regel_anlegen_oder_aktualisieren(ku, gk_final, 'bestaetigung', request.user)
                except Exception as exc:
                    import logging as _log
                    _log.getLogger(__name__).warning("Regel-Lernen fehlgeschlagen: %s", exc)

        ku.refresh_from_db()
        return Response(BankBuchungSerializer(ku, context={'request': request}).data)

    @action(detail=True, methods=['post'], url_path='speichern')
    def speichern(self, request, pk=None):
        """Felder speichern ohne Verbuchung — kein Lerneffekt, kein Status-Wechsel."""
        from apps.konten.models import Konto
        from apps.personen.models import Person, EigentumsVerhaeltnis

        ku = self.get_object()

        update_fields = []
        if 'gegenkonto_id' in request.data:
            gk = Konto.objects.filter(pk=request.data['gegenkonto_id']).first() if request.data['gegenkonto_id'] else None
            ku.erkannt_gegenkonto = gk
            update_fields.append('erkannt_gegenkonto')
        if 'kreditor_id' in request.data:
            kr = Person.objects.filter(pk=request.data['kreditor_id']).first() if request.data['kreditor_id'] else None
            ku.erkannt_kreditor = kr
            update_fields.append('erkannt_kreditor')
        if 'eigentumsverhaeltnis_id' in request.data:
            ev = EigentumsVerhaeltnis.objects.filter(pk=request.data['eigentumsverhaeltnis_id']).first() if request.data['eigentumsverhaeltnis_id'] else None
            ku.erkannt_eigentumsverhaeltnis = ev
            update_fields.append('erkannt_eigentumsverhaeltnis')
        if 'notiz' in request.data:
            ku.notiz = request.data['notiz']
            update_fields.append('notiz')

        if update_fields:
            ku.save(update_fields=update_fields)

        ku.refresh_from_db()
        return Response(BankBuchungSerializer(ku, context={'request': request}).data)

    @action(detail=True, methods=['post'], url_path='erkennung-neu')
    def erkennung_neu(self, request, pk=None):
        """Erkennungs-Pipeline erneut ausführen."""
        from .services.ebanking_erkennungs_service import fuehre_erkennung_aus

        ku = self.get_object()
        if ku.status in ('verbucht', 'storniert'):
            return Response(
                {'error': 'Erneute Erkennung für verbuchte/stornierte Buchungen nicht möglich.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        fuehre_erkennung_aus(ku)
        ku.refresh_from_db()
        return Response(BankBuchungSerializer(ku, context={'request': request}).data)

    @action(detail=True, methods=['post'], url_path='storno')
    def storno(self, request, pk=None):
        from django.core.exceptions import ValidationError as DjValidationError
        from .services.ebanking_buchungs_service import storniere

        ku = self.get_object()
        begruendung = request.data.get('begruendung', '')
        if not begruendung:
            return Response(
                {'error': 'Begründung ist Pflichtfeld.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            storniere(ku, begruendung, request.user)
        except DjValidationError as e:
            return Response(
                {'error': e.messages[0] if e.messages else str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ku.refresh_from_db()
        return Response(BankBuchungSerializer(ku, context={'request': request}).data)


class BankMatchRegelViewSet(viewsets.ModelViewSet):
    """
    Verwaltung der BankMatchRegel-Einträge.
    Registriert unter e-banking/bank-match-regeln/.
    Nur PATCH (status → 'veraltet') und GET erlaubt; keine POST/DELETE.
    """
    serializer_class = BankMatchRegelSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        qs = BankMatchRegel.objects.select_related(
            'bankkonto', 'gegenkonto', 'kreditor', 'eigentumsverhaeltnis',
            'erstellt_von',
        )
        p = self.request.query_params
        if bankkonto_id := p.get('bankkonto'):
            qs = qs.filter(bankkonto_id=bankkonto_id)
        if objekt_id := p.get('objekt'):
            qs = qs.filter(bankkonto__objekt_id=objekt_id)
        if status_p := p.get('status'):
            qs = qs.filter(status=status_p)
        if erstellt_aus := p.get('erstellt_aus'):
            qs = qs.filter(erstellt_aus=erstellt_aus)
        return qs.order_by('-erstellt_am')

    def partial_update(self, request, *args, **kwargs):
        regel = self.get_object()
        new_status = request.data.get('status')
        if new_status != 'veraltet':
            return Response(
                {'error': "Nur status='veraltet' ist zulässig."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        regel.status = 'veraltet'
        regel.save(update_fields=['status'])
        return Response(BankMatchRegelSerializer(regel, context={'request': request}).data)


class KreditorOPViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Offene Kreditor-OPs für E-Banking-Verbuchung (Kreditorische Buchung).
    Registriert unter e-banking/kreditor-ops/.
    """
    serializer_class = KreditorOPSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = KreditorOP.objects.select_related('kreditor', 'rechnung')
        p = self.request.query_params
        if objekt_id := p.get('objekt'):
            qs = qs.filter(objekt_id=objekt_id)
        status_p = p.get('status')
        if status_p:
            qs = qs.filter(status=status_p)
        else:
            qs = qs.filter(status__in=['offen', 'teilbezahlt'])
        return qs.order_by('faellig_ab')


class SepaZahlungslaufViewSet(viewsets.ReadOnlyModelViewSet):
    """SEPA-Zahlungslauf-Protokolle (Ausgangsüberweisungen pain.001) — read-only."""
    serializer_class   = SepaZahlungslaufSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SepaZahlungslauf.objects.select_related('erstellt_von').order_by('-erstellt_am')[:200]
