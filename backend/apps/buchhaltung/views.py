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

from .models import (
    Buchungsart, Buchung, Buchungsstapel, OffenerPosten,
    SollstellungsLauf, Sollstellung,
    CamtImportEinstellung, CamtImportLog, ImportOrdnerEinstellung, Kontoumsatz,
    Mahnlauf, Mahnung, Mahnsperre,
    Forderungsfall, Basiszinssatz,
    RAPPosition, RAPAufloesung,
    BankImport, Jahresabrechnung, EinzelAbrechnung,
    LastschriftLauf,
)
from .serializers import (
    BuchungsartSerializer,
    BuchungSerializer, BuchungListSerializer, BuchungsstapelSerializer,
    OffenerPostenSerializer,
    SollstellungsLaufSerializer, SollstellungSerializer,
    CamtImportEinstellungSerializer, CamtImportLogSerializer,
    ImportOrdnerEinstellungSerializer, KontoumsatzSerializer,
    MahnlaufSerializer, MahnungSerializer, MahnsperreSerializer,
    ForderungsfallSerializer, BasiszinssatzSerializer,
    RAPPositionSerializer, RAPAufloesungSerializer,
    BankImportSerializer, JahresabrechnungSerializer, EinzelAbrechnungSerializer,
    LastschriftLaufSerializer,
)
from .services.camt053 import parse_camt053
from .services.buchungserkennung import erkenne_buchung, lerne_aus_buchung
from .services.sepa_export import exportiere_sepa
from .services.sepa_lastschrift import exportiere_lastschrift
from .services.sollstellung import simuliere_lauf, fuehre_lauf_aus
from .services.mahnwesen import simuliere_mahnlauf, fuehre_mahnlauf_aus
from .services.zinsen import berechne_verzugszinsen


class BuchungsartViewSet(viewsets.ReadOnlyModelViewSet):
    """BA-Katalog — read-only für alle Nutzer."""
    serializer_class = BuchungsartSerializer
    permission_classes = [IsAuthenticated]
    queryset = Buchungsart.objects.filter(aktiv=True).order_by('nr')

    @action(detail=False, methods=['get'], url_path='manuell-waehlbar')
    def manuell_waehlbar(self, request):
        """Nur die BAs, die manuell wählbar sind (nicht system_buchungsart)."""
        qs = self.get_queryset().filter(system_buchungsart=False)
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


class SollstellungsLaufViewSet(viewsets.ModelViewSet):
    serializer_class = SollstellungsLaufSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering = ['-erstellt_am']

    def get_queryset(self):
        qs = SollstellungsLauf.objects.select_related('objekt', 'ausgefuehrt_von')
        if objekt_id := self.request.query_params.get('objekt'):
            qs = qs.filter(objekt_id=objekt_id)
        return qs

    @action(detail=False, methods=['post'], url_path='simulieren')
    def simulieren(self, request):
        objekt_id = request.data.get('objekt')
        periode_von = request.data.get('periode_von')
        periode_bis = request.data.get('periode_bis')
        ba_filter = request.data.get('ba_filter', [])

        if not all([objekt_id, periode_von, periode_bis]):
            return Response(
                {'error': 'objekt, periode_von und periode_bis erforderlich'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from datetime import date as _date
        try:
            von = _date.fromisoformat(periode_von)
            bis = _date.fromisoformat(periode_bis)
        except ValueError:
            return Response(
                {'error': 'Ungültiges Datumsformat (YYYY-MM-DD)'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        vorschau = simuliere_lauf(objekt_id, von, bis, ba_filter or None)
        return Response(vorschau)

    @action(detail=True, methods=['post'], url_path='ausfuehren')
    def ausfuehren(self, request, pk=None):
        try:
            ergebnis = fuehre_lauf_aus(pk, request.user)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ergebnis)

    @action(detail=True, methods=['post'], url_path='freigeben')
    def freigeben(self, request, pk=None):
        lauf = self.get_object()
        if lauf.status != 'simulation':
            return Response(
                {'error': 'Nur Simulationen können freigegeben werden'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        lauf.status = 'freigegeben'
        lauf.freigabe_user = request.user
        lauf.freigabe_am = timezone.now()
        lauf.save(update_fields=['status', 'freigabe_user', 'freigabe_am'])
        return Response(SollstellungsLaufSerializer(lauf, context={'request': request}).data)


class SollstellungViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SollstellungSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Sollstellung.objects.select_related(
            'lauf', 'personenkonto', 'buchungsart'
        )
        if lauf_id := self.request.query_params.get('lauf'):
            qs = qs.filter(lauf_id=lauf_id)
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
        if objekt_id := params.get('objekt'):
            qs = qs.filter(objekt_id=objekt_id)
        if s := params.get('status'):
            qs = qs.filter(status=s)
        return qs

    @action(detail=False, methods=['post'], url_path='camt-vorschau')
    def camt_vorschau(self, request):
        """
        CAMT.053-Datei parsen und Vorschau zurückgeben. Kein DB-Commit.
        Body: multipart mit objekt (UUID) + datei (XML).
        Antwort: { transaktionen, neu_anzahl, duplikat_anzahl, gesamt, objekt, objekt_bezeichnung }
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
            'transaktionen':   vorschau,
            'neu_anzahl':      neu_anzahl,
            'duplikat_anzahl': duplikat_anzahl,
            'gesamt':          len(vorschau),
            'objekt':          str(objekt.id),
            'objekt_bezeichnung': objekt.bezeichnung,
            'import_datei':    datei.name,
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
                import_datei=import_datei,
            )

            vorschlag = erkenne_buchung(ku)
            if vorschlag:
                ku.ki_vorschlag = vorschlag
                ku.status = 'erkannt'
                ku.save(update_fields=['ki_vorschlag', 'status'])
                erkannt += 1

            importiert += 1

        return Response({
            'importiert': importiert,
            'duplikate':  duplikate,
            'erkannt':    erkannt,
            'gesamt':     len(transaktionen),
        })

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
            'objekt', 'sollstellungs_lauf', 'erstellt_von'
        )
        if objekt_id := self.request.query_params.get('objekt'):
            qs = qs.filter(objekt_id=objekt_id)
        return qs

    def create(self, request, *args, **kwargs):
        from decimal import Decimal
        from apps.objekte.models import Bankkonto

        objekt_id = request.data.get('objekt_id')
        sollstellungs_lauf_id = request.data.get('sollstellungs_lauf_id')
        faelligkeitsdatum_str = request.data.get('faelligkeitsdatum')
        bezeichnung = request.data.get('bezeichnung', '')

        if not objekt_id:
            return Response({'error': 'Objekt fehlt'}, status=status.HTTP_400_BAD_REQUEST)
        if not faelligkeitsdatum_str:
            return Response({'error': 'Fälligkeitsdatum fehlt'}, status=status.HTTP_400_BAD_REQUEST)

        from datetime import datetime
        try:
            faelligkeitsdatum = datetime.strptime(faelligkeitsdatum_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Ungültiges Fälligkeitsdatum'}, status=status.HTTP_400_BAD_REQUEST)

        from apps.objekte.models import Objekt
        try:
            objekt = Objekt.objects.prefetch_related('bankkonten').get(id=objekt_id)
        except Objekt.DoesNotExist:
            return Response({'error': 'Objekt nicht gefunden'}, status=status.HTTP_400_BAD_REQUEST)

        if not objekt.glaeubiger_id:
            return Response({'error': 'Kein Gläubiger-ID am Objekt hinterlegt'}, status=status.HTTP_400_BAD_REQUEST)

        bankkonto = objekt.bankkonten.filter(aktiv=True, konto_typ='bewirtschaftung').first()
        if not bankkonto:
            return Response({'error': 'Kein aktives Bewirtschaftungs-Bankkonto am Objekt'}, status=status.HTTP_400_BAD_REQUEST)

        sollstellungs_lauf = None
        if sollstellungs_lauf_id:
            try:
                sollstellungs_lauf = SollstellungsLauf.objects.prefetch_related(
                    'sollstellungen__personenkonto__eigentuemer__sepa_mandat'
                ).get(id=sollstellungs_lauf_id, objekt=objekt)
            except SollstellungsLauf.DoesNotExist:
                return Response({'error': 'Sollstellungslauf nicht gefunden'}, status=status.HTTP_400_BAD_REQUEST)

            if sollstellungs_lauf.status not in ('ausgefuehrt', 'freigegeben'):
                return Response(
                    {'error': f'Sollstellungslauf hat Status "{sollstellungs_lauf.status}" — nur "ausgefuehrt" oder "freigegeben" erlaubt'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Positionen aus Sollstellungslauf aufbauen
        positionen = []
        ohne_mandat = []

        if sollstellungs_lauf:
            # Aggregate per Personenkonto — sum all Sollstellungen
            von_pk: dict[str, dict] = {}
            for s in sollstellungs_lauf.sollstellungen.filter(status__in=('vorschau', 'gebucht')):
                pk = s.personenkonto
                person = getattr(pk, 'eigentuemer', None)
                if not person:
                    from apps.konten.models import Personenkonto as PKModel
                    pk_obj = PKModel.objects.select_related('eigentuemer__sepa_mandat').filter(id=pk.id).first()
                    person = pk_obj.eigentuemer if pk_obj else None

                if not person:
                    ohne_mandat.append({'sollstellung_id': str(s.id), 'grund': 'Keine Person gefunden'})
                    continue

                mandat = person.sepa_mandat
                if not mandat or not mandat.aktiv:
                    ohne_mandat.append({
                        'person_name': person.name,
                        'personenkonto_nr': pk.kontonummer,
                        'sollstellung_id': str(s.id),
                        'grund': 'Kein aktives SEPA-Mandat',
                    })
                    continue

                pk_key = str(pk.id)
                if pk_key not in von_pk:
                    von_pk[pk_key] = {
                        'betrag': Decimal('0'),
                        'personenkonto_id': str(pk.id),
                        'personenkonto_nr': pk.kontonummer,
                        'schuldner_name': person.name,
                        'schuldner_iban': mandat.iban,
                        'schuldner_bic': mandat.bic or 'NOTPROVIDED',
                        'mandatsreferenz': mandat.mandatsreferenz,
                        'mandat_datum': str(mandat.unterzeichnet_am),
                        'verwendungszweck': (
                            f"Hausgeld {faelligkeitsdatum.strftime('%m/%Y')} "
                            f"{objekt.bezeichnung}"
                        ),
                        'faelligkeitsdatum': str(faelligkeitsdatum),
                        'seq_typ': 'RCUR',
                    }
                von_pk[pk_key]['betrag'] += s.betrag

            # Decimal → float für JSON-Serialisierung (psycopg2 kennt kein Decimal)
            for p in von_pk.values():
                p['betrag'] = float(p['betrag'])
            positionen = list(von_pk.values())

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
            sollstellungs_lauf=sollstellungs_lauf,
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
            gegenkonto = Konto.objects.filter(objekt=objekt, kontonummer='13650').first()
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
                        wirtschaftsjahr=lauf.faelligkeitsdatum.year,
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
