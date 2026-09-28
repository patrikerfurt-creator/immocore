import logging
import mimetypes

from django.db.models import ProtectedError
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.http import FileResponse, HttpResponse
from .models import Dokument
from .serializers import DokumentSerializer
from .services.beleg_service import dokument_pfad, loeschsperre_grund

logger = logging.getLogger(__name__)


class DokumentViewSet(viewsets.ModelViewSet):
    serializer_class = DokumentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['dateiname', 'beschreibung', 'kategorie']
    ordering_fields = [
        'hochgeladen_am', 'dateiname', 'kategorie',
        'rechnung__rechnungsdatum', 'rechnung__betrag_brutto',
    ]
    ordering = ['-hochgeladen_am']

    def get_queryset(self):
        # select_related('rechnung', 'rechnung__kreditor') vermeidet N+1-Queries für die
        # Rechnungsanreicherung im DokumentSerializer (Belegübersicht-Anreicherung v1.0).
        qs = Dokument.objects.select_related(
            'objekt', 'einheit', 'hochgeladen_von', 'rechnung', 'rechnung__kreditor',
        )
        objekt_id = self.request.query_params.get('objekt')
        einheit_id = self.request.query_params.get('einheit')
        kategorie = self.request.query_params.get('kategorie')
        if objekt_id:
            # fuer_objekt() akzeptiert auch eine reine PK (Django löst FK-Vergleiche
            # gegen einen Roh-Wert genauso auf wie gegen eine Modell-Instanz).
            qs = qs.fuer_objekt(objekt_id)
        if einheit_id:
            qs = qs.fuer_einheit(einheit_id)
        if kategorie:
            qs = qs.filter(kategorie=kategorie)
        return qs

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.revisionssicher:
            return Response(
                {'error': 'Revisionssicheres Dokument darf nicht gelöscht werden (GoBD).'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # loeschsperre_grund() bewertet ab hier nur noch die Rechnungs-Verknüpfung
        # (revisionssicher wurde oben bereits ausgeschlossen) — einzige Entscheidungs-
        # quelle, dieselbe wie im DokumentSerializer (Nachtrag v1.1).
        grund = loeschsperre_grund(instance)
        if grund is not None:
            return Response({'error': grund}, status=status.HTTP_400_BAD_REQUEST)
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            # Sicherheitsnetz für Referenzen, die oben nicht explizit geprüft werden.
            return Response(
                {'error': 'Dokument kann nicht gelöscht werden: es wird an anderer Stelle referenziert.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=['get'], url_path='datei')
    def datei(self, request, pk=None):
        """Liefert die Dokumentdatei über die zentrale Pfadauflösung (beleg_service.dokument_pfad)."""
        dokument = self.get_object()
        pfad = dokument_pfad(dokument)
        if not pfad.exists():
            return Response({'error': 'Datei nicht gefunden'}, status=status.HTTP_404_NOT_FOUND)
        content_type, _ = mimetypes.guess_type(str(pfad))
        return FileResponse(open(pfad, 'rb'), content_type=content_type or 'application/octet-stream')

    @action(detail=True, methods=['get'], url_path='mail-vorschau')
    def mail_vorschau(self, request, pk=None):
        """Lesbare Textvorschau einer abgelegten Mail (.eml/.msg).

        Browser stellen das Outlook-Format nicht dar, sondern laden es nur
        herunter. Hier wird die Mail stattdessen aus der Originaldatei
        gerendert — ohne eine zweite Datei anzulegen.

        Der Inhalt stammt von aussen und wird deshalb ausschliesslich
        HTML-escaped ausgegeben (siehe ``mail_vorschau_service``); die
        CSP-Header sind die zweite Verteidigungslinie gegen XSS.
        """
        from apps.vorgaenge.services import mail_vorschau_service

        dokument = self.get_object()
        if not mail_vorschau_service.ist_mail_dokument(dokument):
            return Response(
                {'error': 'Dieses Dokument ist keine E-Mail — die Vorschau '
                          'gibt es nur für .eml- und .msg-Dateien.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pfad = dokument_pfad(dokument)
        if not pfad.exists():
            return Response({'error': 'Datei nicht gefunden'}, status=status.HTTP_404_NOT_FOUND)

        try:
            inhalt = mail_vorschau_service.baue_vorschau(
                pfad, dokument.dateiname,
                kompakt=request.query_params.get('kompakt') in ('1', 'true'),
            )
        except Exception:
            logger.exception('Mail-Vorschau fuer Dokument %s fehlgeschlagen.', dokument.pk)
            return Response(
                {'error': 'Die Mail konnte nicht gelesen werden. Die '
                          'Originaldatei steht weiterhin zum Download bereit.'},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        antwort = HttpResponse(inhalt, content_type='text/html; charset=utf-8')
        antwort['Content-Security-Policy'] = mail_vorschau_service.CSP
        antwort['X-Content-Type-Options'] = 'nosniff'
        # Kein Caching: der Inhalt ist personenbezogen.
        antwort['Cache-Control'] = 'no-store'
        return antwort
