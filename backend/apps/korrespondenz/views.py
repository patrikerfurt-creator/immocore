"""API-Views des Moduls Vorlagen & Korrespondenz.

Phase 2: Platzhalter-Endpoint (Spec 4.3).
Phase 4: Schreiben (Postausgang), Druckstapel, Serienläufe (Spec 8).
Phase 5a: Vorlagen-Editor (Vorlagen, Versionen, Vorschau, Textbausteine, Briefbögen) und
KI-Assistent (Spec 6, 8).

KEINE Geschäftslogik hier - jede Mutation delegiert an ``schreiben_service``,
``druckstapel_service``, ``serienlauf_service``, ``vorlage_service``, ``vorschau_service``
bzw. ``vorlagen_assistent_service``. Fachliche Fehler kommen als
``django.core.exceptions.ValidationError`` aus den Services und werden zu HTTP 400.

Berechtigung: ``IsAuthenticated``, wie in den bestehenden Views (eine
objektbezogene Zugriffsbeschränkung gibt es im Projekt bisher nicht).
"""
import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Prefetch, ProtectedError
from django.http import HttpResponse
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Briefbogen, Druckstapel, Schreiben, Serienlauf, Textbaustein, Vorlage, VorlagenVersion,
)
from .serializers import (
    BriefbogenSerializer, DruckstapelCreateSerializer, DruckstapelSerializer,
    SchreibenAnpassenSerializer, SchreibenCreateSerializer, SchreibenDetailSerializer,
    SchreibenListSerializer, SchreibenVersendenSerializer, SerienlaufCreateSerializer,
    SerienlaufDetailSerializer, TextbausteinSerializer, VersionAnlegenSerializer,
    VorlageAendernSerializer, VorlageDetailSerializer, VorlageListSerializer,
    VorlagenAssistentSerializer, VorlagenVersionSerializer, VorschauSerializer,
)
from .services import (
    druckstapel_service, postausgang_service, registry, schreiben_service, serienlauf_service,
    vorlage_service, vorlagen_assistent_service, vorschau_service,
)

logger = logging.getLogger(__name__)


def _fehler(exc) -> Response:
    """Fachlicher Fehler -> HTTP 400 mit lesbarer Meldung."""
    if isinstance(exc, DjangoValidationError):
        nachricht = '; '.join(exc.messages)
    else:
        nachricht = str(exc.args[0]) if exc.args else str(exc)
    return Response({'detail': nachricht}, status=status.HTTP_400_BAD_REQUEST)


FACHFEHLER = (DjangoValidationError, vorlage_service.VorlageNichtGefunden, ValueError)


class PlatzhalterView(APIView):
    """``GET /api/v1/korrespondenz/platzhalter/?anlass=<code>``

    Antwort: ``[{name, beschreibung, typ, beispiel, gruppe}]``. ``name`` ist der
    volle Platzhalter (``gruppe.name``), so wie er im Vorlagentext steht.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        anlass = request.query_params.get('anlass', '')
        if anlass not in registry.ANLAESSE:
            return Response(
                {'detail': 'Unbekannter oder fehlender Anlass.',
                 'anlaesse': list(registry.ANLAESSE)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(registry.metadaten(anlass))


class SchreibenViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                       mixins.CreateModelMixin, mixins.UpdateModelMixin,
                       viewsets.GenericViewSet):
    """``/api/v1/korrespondenz/schreiben/`` - Postausgang, Erstellen, Freigeben, Versenden, Verwerfen.

    Liste ohne ``?status=``: Postausgang (zur Prüfung, nicht erzeugbar, Versand
    fehlgeschlagen). Filter: ``status`` (kommagetrennt, ``nicht_erzeugbar``,
    ``alle``), ``objekt``, ``anlass``, ``betreuer``, ``serienlauf``, ``druckbereit=1``.
    """
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_queryset(self):
        if self.action != 'list':
            return Schreiben.objects.select_related(
                'vorlage_version__vorlage', 'empfaenger', 'objekt', 'einheit', 'dokument',
            )
        p = self.request.query_params
        return postausgang_service.postausgang(
            status=p.get('status', ''), objekt=p.get('objekt') or None,
            anlass=p.get('anlass', ''), betreuer=p.get('betreuer') or None,
            serienlauf=p.get('serienlauf') or None,
            druckbereit=p.get('druckbereit', '').lower() in ('1', 'true', 'ja'),
        )

    def get_serializer_class(self):
        if self.action == 'list':
            return SchreibenListSerializer
        return SchreibenDetailSerializer

    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except (ValueError, DjangoValidationError) as exc:
            return _fehler(exc)

    def create(self, request, *args, **kwargs):
        eingabe = SchreibenCreateSerializer(data=request.data)
        eingabe.is_valid(raise_exception=True)
        daten = dict(eingabe.validated_data)
        try:
            schreiben = schreiben_service.erstellen(
                daten.pop('vorlage_code'), daten.pop('empfaenger'), user=request.user, **daten,
            )
        except FACHFEHLER as exc:
            return _fehler(exc)
        return Response(SchreibenDetailSerializer(schreiben).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        schreiben = self.get_object()
        eingabe = SchreibenAnpassenSerializer(data=request.data)
        eingabe.is_valid(raise_exception=True)
        try:
            schreiben = schreiben_service.passe_an(schreiben, eingabe.validated_data['inhalt_angepasst'])
        except FACHFEHLER as exc:
            return _fehler(exc)
        return Response(SchreibenDetailSerializer(schreiben).data)

    @action(detail=True, methods=['post'])
    def freigeben(self, request, pk=None):
        try:
            schreiben = schreiben_service.freigeben(self.get_object(), request.user)
        except FACHFEHLER as exc:
            return _fehler(exc)
        return Response(SchreibenDetailSerializer(schreiben).data)

    @action(detail=True, methods=['post'])
    def versenden(self, request, pk=None):
        eingabe = SchreibenVersendenSerializer(data=request.data)
        eingabe.is_valid(raise_exception=True)
        try:
            ergebnis = schreiben_service.versenden(
                self.get_object(), request.user, kanal=eingabe.validated_data.get('kanal'),
            )
        except FACHFEHLER as exc:
            return _fehler(exc)
        daten = SchreibenDetailSerializer(ergebnis.schreiben).data
        daten['versand'] = {'ergebnis': ergebnis.ergebnis, 'hinweis': ergebnis.hinweis}
        return Response(daten)

    @action(detail=True, methods=['post'])
    def verwerfen(self, request, pk=None):
        try:
            schreiben = schreiben_service.verwerfen(self.get_object(), request.user)
        except FACHFEHLER as exc:
            return _fehler(exc)
        return Response(SchreibenDetailSerializer(schreiben).data)

    @action(detail=True, methods=['get'])
    def pdf(self, request, pk=None):
        schreiben = self.get_object()
        try:
            inhalt = schreiben_service.pdf_bytes(schreiben)
        except FACHFEHLER as exc:
            return _fehler(exc)
        antwort = HttpResponse(inhalt, content_type='application/pdf')
        antwort['Content-Disposition'] = f'inline; filename="{schreiben.nummer}.pdf"'
        return antwort


class DruckstapelViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """``GET /druckstapel/`` (Liste; Filter ``status`` offen|bestaetigt, ``objekt``),
    ``GET /druckstapel/{id}/`` (Detail), ``POST /druckstapel/`` (Stapel + Sammel-PDF erzeugen),
    ``POST /druckstapel/{id}/bestaetigen/``.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = DruckstapelSerializer

    def get_queryset(self):
        qs = Druckstapel.objects.select_related('dokument').prefetch_related(
            Prefetch('schreiben', queryset=Schreiben.objects.select_related('empfaenger', 'objekt')),
        )
        if self.action != 'list':
            return qs
        p = self.request.query_params
        if p.get('status'):
            if p['status'] not in dict(Druckstapel.STATUS_CHOICES):
                raise DRFValidationError({'status': 'Erlaubt sind "offen" und "bestaetigt".'})
            qs = qs.filter(status=p['status'])
        if p.get('objekt'):
            try:
                qs = qs.filter(schreiben__objekt=p['objekt']).distinct()
            except (ValueError, DjangoValidationError) as exc:
                raise DRFValidationError({'objekt': 'Ungültige Objekt-Id.'}) from exc
        return qs

    def create(self, request):
        eingabe = DruckstapelCreateSerializer(data=request.data)
        eingabe.is_valid(raise_exception=True)
        try:
            stapel = druckstapel_service.erzeuge(
                request.user, schreiben_ids=eingabe.validated_data.get('schreiben_ids'),
                objekt=eingabe.validated_data.get('objekt'),
            )
        except FACHFEHLER as exc:
            return _fehler(exc)
        return Response(DruckstapelSerializer(stapel).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def bestaetigen(self, request, pk=None):
        try:
            stapel = schreiben_service.bestaetige_druckstapel(self.get_object(), request.user)
        except FACHFEHLER as exc:
            return _fehler(exc)
        return Response(DruckstapelSerializer(stapel).data)


class SerienlaufViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """``POST /serienlaeufe/``, ``GET /serienlaeufe/{id}/``, ``POST /serienlaeufe/{id}/freigeben/``,
    ``POST /serienlaeufe/{id}/abbrechen/``."""
    permission_classes = [IsAuthenticated]
    queryset = Serienlauf.objects.select_related('objekt', 'vorlage_version__vorlage')
    serializer_class = SerienlaufDetailSerializer

    def create(self, request):
        eingabe = SerienlaufCreateSerializer(data=request.data)
        eingabe.is_valid(raise_exception=True)
        daten = eingabe.validated_data
        objekt = daten['objekt']
        try:
            if daten.get('vorlage_version'):
                version = self._version(daten['vorlage_version'])
            else:
                vorlage = vorlage_service.aufloesen(daten['vorlage_code'], objekt)
                version = vorlage_service.aktive_version(vorlage)
            lauf = serienlauf_service.starte(
                version, objekt, empfaenger_filter=daten.get('empfaenger_filter'),
                eingabewerte=daten.get('eingabewerte'), unterzeichner=daten.get('unterzeichner'),
                user=request.user,
            )
        except FACHFEHLER as exc:
            return _fehler(exc)
        return Response(SerienlaufDetailSerializer(lauf).data, status=status.HTTP_201_CREATED)

    @staticmethod
    def _version(version_id):
        from .models import VorlagenVersion
        version = VorlagenVersion.objects.select_related('vorlage').filter(pk=version_id).first()
        if version is None:
            raise DjangoValidationError('Vorlagenversion nicht gefunden.')
        return version

    @action(detail=True, methods=['post'])
    def freigeben(self, request, pk=None):
        """Gibt frei und stößt die Verarbeitung (Mails, Druckstapel) im Hintergrund an."""
        from .tasks import serienlauf_verarbeiten
        try:
            lauf = serienlauf_service.freigeben(self.get_object(), request.user)
        except FACHFEHLER as exc:
            return _fehler(exc)
        lauf_id, user_id = str(lauf.pk), request.user.pk
        transaction.on_commit(lambda: self._anstossen(serienlauf_verarbeiten, lauf_id, user_id))
        return Response(SerienlaufDetailSerializer(lauf).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=['post'])
    def abbrechen(self, request, pk=None):
        """Bricht einen noch nicht versendeten Lauf ab; offene Schreiben werden verworfen."""
        try:
            lauf = serienlauf_service.abbrechen(self.get_object(), request.user)
        except FACHFEHLER as exc:
            return _fehler(exc)
        return Response(SerienlaufDetailSerializer(lauf).data)

    @staticmethod
    def _anstossen(task, lauf_id, user_id) -> None:
        try:
            task.delay(lauf_id, user_id)
        except Exception:  # noqa: BLE001 - Broker down: Lauf bleibt "freigegeben", erneutes Freigeben stößt neu an
            logger.exception('Serienlauf %s: Verarbeitung konnte nicht angestoßen werden.', lauf_id)


# --------------------------------------------------------------------------
# Phase 5a: Vorlagen-Editor
# --------------------------------------------------------------------------

def _wahr(wert: str) -> bool:
    return wert.lower() in ('1', 'true', 'ja')


class VorlageViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                     mixins.CreateModelMixin, mixins.UpdateModelMixin,
                     viewsets.GenericViewSet):
    """``/vorlagen/`` (Liste, Anlegen), ``/vorlagen/{id}/`` (Detail, PATCH), ``/vorlagen/{id}/versionen/``.

    Filter der Liste: ``anlass``, ``code``, ``aktiv``, ``objekt`` (Id oder ``null`` = global).
    """
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_queryset(self):
        qs = Vorlage.objects.select_related('objekt', 'aktive_version').order_by('code')
        if self.action != 'list':
            return qs
        p = self.request.query_params
        if p.get('anlass'):
            qs = qs.filter(anlass=p['anlass'])
        if p.get('code'):
            qs = qs.filter(code=p['code'])
        if p.get('aktiv'):
            qs = qs.filter(aktiv=_wahr(p['aktiv']))
        if p.get('objekt') == 'null':
            qs = qs.filter(objekt__isnull=True)
        elif p.get('objekt'):
            qs = qs.filter(objekt=p['objekt'])
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return VorlageListSerializer
        if self.action == 'partial_update':
            return VorlageAendernSerializer
        return VorlageDetailSerializer

    def create(self, request, *args, **kwargs):
        eingabe = VorlageListSerializer(data=request.data)
        eingabe.is_valid(raise_exception=True)
        try:
            vorlage = vorlage_service.lege_vorlage_an(user=request.user, **eingabe.validated_data)
        except FACHFEHLER as exc:
            return _fehler(exc)
        return Response(VorlageDetailSerializer(vorlage).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        vorlage = self.get_object()
        eingabe = VorlageAendernSerializer(vorlage, data=request.data, partial=True)
        eingabe.is_valid(raise_exception=True)
        eingabe.save()
        return Response(VorlageDetailSerializer(vorlage).data)

    @action(detail=True, methods=['get', 'post'], url_path='versionen')
    def versionen(self, request, pk=None):
        vorlage = self.get_object()
        if request.method == 'GET':
            return Response(VorlagenVersionSerializer(vorlage.versionen.all(), many=True).data)
        eingabe = VersionAnlegenSerializer(data=request.data)
        eingabe.is_valid(raise_exception=True)
        werte = dict(eingabe.validated_data)
        basis = werte.pop('basis_version', None)
        try:
            version = vorlage_service.lege_version_an(vorlage, request.user, basis=basis, werte=werte)
        except FACHFEHLER as exc:
            return _fehler(exc)
        return Response(VorlagenVersionSerializer(version).data, status=status.HTTP_201_CREATED)


class VersionViewSet(mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """``/versionen/{id}/`` (GET, PATCH nur ``entwurf``), ``/freigeben/``, ``/vorschau/``."""
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    queryset = VorlagenVersion.objects.select_related('vorlage')
    serializer_class = VorlagenVersionSerializer

    def partial_update(self, request, *args, **kwargs):
        version = self.get_object()
        eingabe = VorlagenVersionSerializer(version, data=request.data, partial=True)
        eingabe.is_valid(raise_exception=True)
        try:
            version = vorlage_service.aktualisiere_entwurf(version, dict(eingabe.validated_data))
        except vorlage_service.VersionGesperrt as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)
        except FACHFEHLER as exc:
            return _fehler(exc)
        return Response(VorlagenVersionSerializer(version).data)

    @action(detail=True, methods=['post'])
    def freigeben(self, request, pk=None):
        """Braucht ``korrespondenz.vorlage_freigeben`` (der Service wirft sonst ``PermissionDenied`` -> 403)."""
        try:
            version = vorlage_service.freigeben(self.get_object(), request.user)
        except vorlage_service.VersionGesperrt as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)
        except FACHFEHLER as exc:
            return _fehler(exc)
        return Response(VorlagenVersionSerializer(version).data)

    @action(detail=True, methods=['post'])
    def vorschau(self, request, pk=None):
        """PDF auf dem echten Briefbogen gegen einen Beispiel-Empfänger - ohne Persistierung."""
        version = self.get_object()
        eingabe = VorschauSerializer(data=request.data)
        eingabe.is_valid(raise_exception=True)
        daten = eingabe.validated_data
        try:
            pdf = vorschau_service.erzeuge_vorschau_pdf(
                version, daten['person_id'], einheit=daten.get('einheit_id'),
                eingabewerte=daten.get('eingabewerte'), user=request.user,
            )
        except FACHFEHLER as exc:
            return _fehler(exc)
        antwort = HttpResponse(pdf, content_type='application/pdf')
        antwort['Content-Disposition'] = 'inline; filename="vorschau.pdf"'
        return antwort


class TextbausteinViewSet(viewsets.ModelViewSet):
    """``/textbausteine/`` - CRUD. Filter: ``objekt`` (Id oder ``null``), ``aktiv``, ``code``."""
    permission_classes = [IsAuthenticated]
    serializer_class = TextbausteinSerializer

    def get_queryset(self):
        qs = Textbaustein.objects.order_by('code')
        p = self.request.query_params
        if p.get('code'):
            qs = qs.filter(code=p['code'])
        if p.get('aktiv'):
            qs = qs.filter(aktiv=_wahr(p['aktiv']))
        if p.get('objekt') == 'null':
            qs = qs.filter(objekt__isnull=True)
        elif p.get('objekt'):
            qs = qs.filter(objekt=p['objekt'])
        return qs


class BriefbogenViewSet(viewsets.ModelViewSet):
    """``/briefboegen/`` - CRUD, nur für Administratoren (``IsAdminUser``)."""
    permission_classes = [IsAdminUser]
    queryset = Briefbogen.objects.order_by('bezeichnung')
    serializer_class = BriefbogenSerializer

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {'detail': 'Der Briefbogen ist einer Vorlage zugeordnet und kann nicht gelöscht werden.'},
                status=status.HTTP_409_CONFLICT,
            )


class VorlagenAssistentView(APIView):
    """KI-Assistent im Editor (Spec 6).

    ``GET``: ``{verfuegbar}`` - ohne ``ANTHROPIC_API_KEY`` blendet das Frontend den Button aus.
    ``POST {anlass, stichworte, block?, eingabefelder?}``: ``{bloecke, hinweise, betreff}``;
    503 wenn nicht verfügbar, 502/504 bei KI-Fehler bzw. Zeitüberschreitung (60 s).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({'verfuegbar': vorlagen_assistent_service.ist_verfuegbar()})

    def post(self, request):
        eingabe = VorlagenAssistentSerializer(data=request.data)
        eingabe.is_valid(raise_exception=True)
        daten = eingabe.validated_data
        try:
            ergebnis = vorlagen_assistent_service.entwerfe(
                daten['anlass'], daten['stichworte'], block=daten.get('block'),
                eingabefelder=daten.get('eingabefelder'),
            )
        except vorlagen_assistent_service.AssistentNichtVerfuegbar:
            return Response(
                {'detail': 'Der KI-Assistent ist nicht verfügbar (kein API-Schlüssel konfiguriert).',
                 'verfuegbar': False},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except vorlagen_assistent_service.AssistentFehler as exc:
            antwort = (status.HTTP_504_GATEWAY_TIMEOUT if exc.zeitueberschreitung
                       else status.HTTP_502_BAD_GATEWAY)
            return Response({'detail': str(exc), 'verfuegbar': True}, status=antwort)
        return Response(ergebnis)
