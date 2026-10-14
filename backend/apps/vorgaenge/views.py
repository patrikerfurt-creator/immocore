"""
API-Views für Vorgang / VorgangTyp (Kap. 2 der Spec Vorgang & DMS v1.0).

KEINE Business-Logik hier — jede Mutation delegiert an
``vorgang_service`` bzw. ``dokument_service``. Ungültige Übergänge/Eingaben
werden als ``django.core.exceptions.ValidationError`` von den Services
geworfen und hier zu HTTP 400 übersetzt.
"""
import csv
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from .models import Vorgang, VorgangAntwortVorschlag, VorgangTyp, VorgangZeiteintrag
from .serializers import (
    VorgangAntwortVorschlagSerializer,
    VorgangCreateSerializer,
    VorgangDetailSerializer,
    VorgangDokumentSerializer,
    VorgangListSerializer,
    VorgangTypSerializer,
    VorgangZeiteintragCreateSerializer,
)
from .services import antwort_vorschlag_service, dokument_service, vorgang_service

# Handwerkerauftrag-Anlage aus einem Vorgang heraus (Phase C, Orchestrator-
# Vorgabe Schritt 3) — Action AM bestehenden VorgangViewSet, wie in der Spec
# vorgesehen. Business-Logik bleibt in apps.handwerker.services.auftrag_service.
from apps.handwerker.serializers import HandwerkerauftragCreateSerializer, HandwerkerauftragDetailSerializer
from apps.handwerker.services import auftrag_service as handwerker_auftrag_service

User = get_user_model()


def _validation_error_response(exc: DjangoValidationError) -> Response:
    nachricht = '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)
    return Response({'detail': nachricht}, status=status.HTTP_400_BAD_REQUEST)


def _parse_bool(value) -> bool:
    """Parst einen Bool-Wert aus ``request.data`` — muss sowohl echte
    JSON-Booleans (``True``/``False``) als auch Formular-/Multipart-Strings
    (``'true'``/``'false'``) korrekt behandeln. Ein simples ``bool(value)``
    würde ``'False'`` (nicht-leerer String) fälschlich als wahr auswerten
    (Muster: ``apps.mitarbeiter.views``/``apps.konten.views``, dort ebenfalls
    manuelles String-Parsing statt eines nackten ``bool()``)."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _minuten_hhmm(minuten: int) -> str:
    """Minuten als ``h:mm`` (z.B. 90 -> '1:30') für die Export-Tabelle."""
    return f"{minuten // 60}:{minuten % 60:02d}"


def _de_dezimal(wert) -> str:
    """Deutsche Dezimalschreibweise (Komma statt Punkt) für den CSV-Export."""
    return str(wert).replace('.', ',')


def _user_anzeige(user) -> str:
    if user is None:
        return ''
    return user.get_full_name() or user.get_username()


class VorgangViewSet(mixins.ListModelMixin,
                      mixins.RetrieveModelMixin,
                      mixins.CreateModelMixin,
                      viewsets.GenericViewSet):
    """``/api/v1/vorgaenge/`` — Liste, Anlage, Detail plus Aktionen für
    Statuswechsel, Kommentar, Zuweisung und Dokument-Upload.

    Bewusst KEIN ``ModelViewSet``: Update/Delete direkt auf ``Vorgang`` gibt
    es nicht — jede Mutation läuft über eine der Service-Aktionen unten.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get_queryset(self):
        qs = Vorgang.objects.select_related(
            'typ', 'objekt', 'einheit', 'person', 'zugewiesen_an', 'erstellt_von',
        )
        params = self.request.query_params
        for feld in ('objekt', 'einheit', 'status', 'zugewiesen_an', 'quelle', 'typ'):
            wert = params.get(feld)
            if wert:
                qs = qs.filter(**{feld: wert})
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return VorgangListSerializer
        if self.action == 'retrieve':
            return VorgangDetailSerializer
        if self.action == 'create':
            return VorgangCreateSerializer
        return VorgangDetailSerializer

    def create(self, request, *args, **kwargs):
        eingabe = VorgangCreateSerializer(data=request.data)
        eingabe.is_valid(raise_exception=True)
        daten = eingabe.validated_data
        try:
            vorgang = vorgang_service.erstelle_vorgang(
                erstellt_von=request.user,
                quelle='manuell',  # serverseitig fest — Client kann sie nicht setzen
                **daten,
            )
        except DjangoValidationError as exc:
            return _validation_error_response(exc)
        return Response(
            VorgangDetailSerializer(vorgang).data, status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'], url_path='status')
    def status_wechsel(self, request, pk=None):
        vorgang = self.get_object()
        neuer_status = request.data.get('status')
        if not neuer_status:
            return Response({'detail': "'status' ist erforderlich."}, status=status.HTTP_400_BAD_REQUEST)
        kommentar = request.data.get('kommentar') or None
        wiedervorlage_am = request.data.get('wiedervorlage_am') or None
        try:
            vorgang_service.wechsle_status(
                vorgang, neuer_status, erstellt_von=request.user,
                kommentar=kommentar, wiedervorlage_am=wiedervorlage_am,
            )
        except DjangoValidationError as exc:
            return _validation_error_response(exc)
        return Response(VorgangDetailSerializer(vorgang).data)

    @action(detail=True, methods=['post'], url_path='kommentar')
    def kommentar(self, request, pk=None):
        vorgang = self.get_object()
        text = request.data.get('text', '')
        # Default bleibt bewusst 'intern' (Patrik-Entscheidung) — nur ein
        # ausdrücklich übergebenes True macht den Kommentar eigentümer-sichtbar.
        intern = not _parse_bool(request.data.get('sichtbar_fuer_eigentuemer', False))
        try:
            vorgang_service.kommentiere(vorgang, text, request.user, intern=intern)
        except DjangoValidationError as exc:
            return _validation_error_response(exc)
        return Response(VorgangDetailSerializer(vorgang).data)

    @action(detail=True, methods=['post'], url_path='portal-sichtbar')
    def portal_sichtbar_setzen(self, request, pk=None):
        """Setzt ``Vorgang.portal_sichtbar`` — Body ``{"portal_sichtbar": true|false}``.
        Steuert ausschließlich, ob ``portal_ansicht``/``portal-vorschau`` etwas
        liefert; erzeugt bewusst kein ``VorgangEreignis`` (siehe
        ``vorgang_service.setze_portal_sichtbar``)."""
        vorgang = self.get_object()
        sichtbar = _parse_bool(request.data.get('portal_sichtbar'))
        try:
            vorgang_service.setze_portal_sichtbar(vorgang, sichtbar)
        except DjangoValidationError as exc:
            return _validation_error_response(exc)
        return Response(VorgangDetailSerializer(vorgang).data)

    @action(detail=True, methods=['get'], url_path='portal-vorschau')
    def portal_vorschau(self, request, pk=None):
        """Mitarbeiter-Vorschau: zeigt genau das, was der Eigentümer im
        (noch nicht existierenden) Portal sehen würde. Bewusst hinter
        ``IsAuthenticated`` (Klassenattribut ``permission_classes`` dieses
        ViewSets) — KEIN öffentlicher/anonymer Zugriff, siehe Modul-Docstring
        von ``vorgang_service.portal_ansicht``."""
        vorgang = self.get_object()
        return Response(vorgang_service.portal_ansicht(vorgang))

    @action(detail=True, methods=['post'], url_path='zuweisen')
    def zuweisen(self, request, pk=None):
        vorgang = self.get_object()
        user_id = request.data.get('user_id')
        user = None
        if user_id not in (None, ''):
            user = get_object_or_404(User, pk=user_id)
        try:
            vorgang_service.weise_zu(vorgang, user, request.user)
        except DjangoValidationError as exc:
            return _validation_error_response(exc)
        return Response(VorgangDetailSerializer(vorgang).data)

    @action(detail=True, methods=['post'], url_path='abrechenbar')
    def abrechenbar_setzen(self, request, pk=None):
        """Setzt den Schalter ``Vorgang.abrechenbar`` — Body
        ``{"abrechenbar": true|false}``. Schaltet die Zeiterfassung frei."""
        vorgang = self.get_object()
        abrechenbar = _parse_bool(request.data.get('abrechenbar'))
        try:
            vorgang_service.setze_abrechenbar(vorgang, abrechenbar)
        except DjangoValidationError as exc:
            return _validation_error_response(exc)
        return Response(VorgangDetailSerializer(vorgang).data)

    @action(detail=True, methods=['post'], url_path='zeiteintraege')
    def zeiteintrag_hinzufuegen(self, request, pk=None):
        """Legt einen Zeiteintrag (Sonderkosten-Erfassung) an. Nur möglich,
        wenn der Vorgang als "separat abrechenbar" markiert ist — sonst 400."""
        vorgang = self.get_object()
        eingabe = VorgangZeiteintragCreateSerializer(data=request.data)
        eingabe.is_valid(raise_exception=True)
        try:
            vorgang_service.fuege_zeiteintrag_hinzu(
                vorgang, erstellt_von=request.user, **eingabe.validated_data,
            )
        except DjangoValidationError as exc:
            return _validation_error_response(exc)
        return Response(VorgangDetailSerializer(vorgang).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'], url_path=r'zeiteintraege/(?P<eid>[^/.]+)')
    def zeiteintrag_loeschen(self, request, pk=None, eid=None):
        """Löscht einen einzelnen Zeiteintrag dieses Vorgangs."""
        vorgang = self.get_object()
        eintrag = get_object_or_404(VorgangZeiteintrag, pk=eid, vorgang=vorgang)
        try:
            vorgang_service.loesche_zeiteintrag(eintrag)
        except DjangoValidationError as exc:
            return _validation_error_response(exc)
        return Response(VorgangDetailSerializer(vorgang).data)

    @action(detail=True, methods=['get'], url_path='zeiten-export')
    def zeiten_export(self, request, pk=None):
        """CSV-Export der Zeiten/Kilometer dieses Vorgangs (Nachweis-Tabelle
        für die externe Rechnungsstellung). Semikolon-getrennt mit UTF-8-BOM,
        damit Excel (de) Spalten und Umlaute korrekt übernimmt."""
        vorgang = self.get_object()
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        dateiname = f"Vorgang_{vorgang.nummer}_Zeiten.csv"
        response['Content-Disposition'] = f'attachment; filename="{dateiname}"'
        response.write('﻿')  # BOM für Excel

        writer = csv.writer(response, delimiter=';')
        writer.writerow([
            'Datum', 'Mitarbeiter', 'Tätigkeit',
            'Dauer (hh:mm)', 'Dauer (Minuten)', 'Kilometer', 'Notiz',
        ])

        summe_minuten = 0
        summe_km = Decimal('0')
        for e in vorgang.zeiteintraege.select_related('mitarbeiter').all():
            summe_minuten += e.dauer_minuten
            summe_km += e.kilometer or Decimal('0')
            writer.writerow([
                e.datum.strftime('%d.%m.%Y'),
                _user_anzeige(e.mitarbeiter),
                e.taetigkeit,
                _minuten_hhmm(e.dauer_minuten),
                e.dauer_minuten,
                _de_dezimal(e.kilometer or 0),
                e.notiz,
            ])
        writer.writerow([])
        writer.writerow([
            'Summe', '', '',
            _minuten_hhmm(summe_minuten), summe_minuten, _de_dezimal(summe_km), '',
        ])
        return response

    @action(detail=True, methods=['post'], url_path='dokumente', parser_classes=[MultiPartParser, FormParser])
    def dokumente(self, request, pk=None):
        vorgang = self.get_object()
        datei = request.FILES.get('datei')
        if not datei:
            return Response({'detail': "'datei' ist erforderlich."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            ergebnis = dokument_service.lade_dokument_hoch(
                datei.read(), datei.name, request.user,
                vorgang=vorgang,
                kategorie=request.data.get('kategorie', 'Sonstiges'),
                dokument_typ=request.data.get('dokument_typ', 'sonstiges'),
                beschreibung=request.data.get('beschreibung', ''),
            )
        except DjangoValidationError as exc:
            return _validation_error_response(exc)
        return Response(
            {
                'dokument': VorgangDokumentSerializer(ergebnis.dokument).data,
                'duplikat_warnung': ergebnis.duplikat_warnung,
            },
            status=status.HTTP_201_CREATED,
        )

    def _aktueller_entwurf(self, vorgang):
        return VorgangAntwortVorschlag.objects.filter(
            vorgang=vorgang, status='entwurf',
        ).order_by('-erzeugt_am').first()

    @action(detail=True, methods=['post', 'patch'], url_path='antwort-vorschlag')
    def antwort_vorschlag(self, request, pk=None):
        vorgang = self.get_object()

        if request.method == 'POST':
            # Neu generieren — synchron, damit der Nutzer sofort ein Ergebnis
            # sieht (der Automatismus bei Anlage läuft dagegen asynchron über
            # den Celery-Task).
            vorschlag = antwort_vorschlag_service.erzeuge_vorschlag(
                vorgang, erstellt_von=request.user,
            )
            return Response(
                VorgangAntwortVorschlagSerializer(vorschlag).data,
                status=status.HTTP_201_CREATED,
            )

        # PATCH: bestehenden Entwurf bearbeiten
        vorschlag = self._aktueller_entwurf(vorgang)
        if vorschlag is None:
            return Response(
                {'detail': 'Kein Antwortvorschlag im Status "entwurf" vorhanden.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        text = request.data.get('text', '')
        try:
            antwort_vorschlag_service.bearbeite_vorschlag(vorschlag, text, request.user)
        except DjangoValidationError as exc:
            return _validation_error_response(exc)
        return Response(VorgangAntwortVorschlagSerializer(vorschlag).data)

    @action(detail=True, methods=['post'], url_path='antwort-vorschlag/freigeben')
    def antwort_vorschlag_freigeben(self, request, pk=None):
        vorgang = self.get_object()
        vorschlag = self._aktueller_entwurf(vorgang)
        if vorschlag is None:
            return Response(
                {'detail': 'Kein Antwortvorschlag im Status "entwurf" vorhanden.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            antwort_vorschlag_service.gib_frei(vorschlag, request.user)
        except DjangoValidationError as exc:
            return _validation_error_response(exc)
        return Response(VorgangAntwortVorschlagSerializer(vorschlag).data)

    @action(detail=True, methods=['post'], url_path='handwerkerauftrag')
    def handwerkerauftrag(self, request, pk=None):
        """Legt einen ``Handwerkerauftrag`` aus diesem Vorgang an. ``objekt``
        im Body ist nur nötig, wenn der Vorgang selbst keinen Objektbezug hat
        (weder direkt noch über die Einheit) — siehe
        ``auftrag_service.erstelle_auftrag``."""
        vorgang = self.get_object()
        eingabe = HandwerkerauftragCreateSerializer(data=request.data)
        eingabe.is_valid(raise_exception=True)
        daten = eingabe.validated_data
        try:
            auftrag = handwerker_auftrag_service.erstelle_auftrag(
                erstellt_von=request.user, vorgang=vorgang, **daten,
            )
        except DjangoValidationError as exc:
            return _validation_error_response(exc)
        return Response(
            HandwerkerauftragDetailSerializer(auftrag).data, status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'], url_path='antwort-vorschlag/verwerfen')
    def antwort_vorschlag_verwerfen(self, request, pk=None):
        vorgang = self.get_object()
        vorschlag = self._aktueller_entwurf(vorgang)
        if vorschlag is None:
            return Response(
                {'detail': 'Kein Antwortvorschlag im Status "entwurf" vorhanden.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        grund = request.data.get('grund') or None
        try:
            antwort_vorschlag_service.verwirf(vorschlag, request.user, grund=grund)
        except DjangoValidationError as exc:
            return _validation_error_response(exc)
        return Response(VorgangAntwortVorschlagSerializer(vorschlag).data)


class VorgangTypViewSet(viewsets.ReadOnlyModelViewSet):
    """``/api/v1/vorgang-typen/`` — nur aktive Typen, für Dropdowns."""
    serializer_class = VorgangTypSerializer
    permission_classes = [IsAuthenticated]
    queryset = VorgangTyp.objects.filter(aktiv=True).order_by('sortierung', 'bezeichnung')


class VorgangTypAdminViewSet(viewsets.ModelViewSet):
    """``/api/v1/vorgang-typen/admin/`` — Stammdaten-Pflege, nur Admin
    (``is_staff``) — minimale Lösung ohne eigenes Rollensystem.
    """
    serializer_class = VorgangTypSerializer
    permission_classes = [IsAdminUser]
    queryset = VorgangTyp.objects.all().order_by('sortierung', 'bezeichnung')

    def perform_create(self, serializer):
        serializer.save(erstellt_von=self.request.user)
