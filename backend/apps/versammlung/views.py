"""
API-Views für das EV-Modul (Spec v1.1 Kap. 10.1).

KEINE Business-Logik hier — jede Mutation delegiert an die Services in
``apps.versammlung.services``. Von dort geworfene
``django.core.exceptions.ValidationError`` werden zu HTTP 400 übersetzt.

Der Download des Einladungs-PDF läuft bewusst über den bestehenden
DMS-Endpunkt ``/api/v1/dokumente/{id}/datei/`` — das Dokument liegt im DMS,
ein zweiter Ausliefer-Pfad wäre eine unnötige zweite Rechteprüfung.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.versammlung.models import (
    Beschluss, EVTeilnehmer, Eigentuemerversammlung, Tagesordnungspunkt,
)
from apps.versammlung.serializers import (
    AbstimmungSerializer, AnfechtungSerializer, AnwesenheitSerializer,
    BeschlussSerializer, EVEreignisSerializer, EVStimmeSerializer,
    EVTeilnehmerSerializer, EVVersandprotokollSerializer,
    EigentuemerversammlungCreateSerializer,
    EigentuemerversammlungDetailSerializer,
    EigentuemerversammlungListSerializer,
    EigentuemerversammlungUpdateSerializer, EinzelstimmenSerializer,
    ErgebnisStatusSerializer,
    TagesordnungspunktCreateSerializer, TagesordnungspunktSerializer,
)
from apps.versammlung.services import (
    beschluss_service, durchfuehrung_service, einladung_service, ev_service,
    stimmkraft_service, tagesordnung_service,
)


def _fehler(exc: DjangoValidationError) -> Response:
    nachricht = '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)
    return Response({'detail': nachricht}, status=status.HTTP_400_BAD_REQUEST)


def _parse_bool(wert) -> bool:
    """Bool aus ``request.data`` — ``bool('false')`` wäre ``True``."""
    if isinstance(wert, bool):
        return wert
    return str(wert).strip().lower() in ('1', 'true', 'yes', 'on')


class EigentuemerversammlungViewSet(mixins.ListModelMixin,
                                    mixins.RetrieveModelMixin,
                                    mixins.CreateModelMixin,
                                    mixins.UpdateModelMixin,
                                    viewsets.GenericViewSet):
    """``/api/v1/versammlungen/`` — Liste, Anlage, Detail, Terminierung und
    die Aktionen der Tasks 1–3.

    Kein ``destroy``: eine EV mit Ereignis-Verlauf wird archiviert, nicht
    gelöscht (§ 45 WEG, GoBD).
    """

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = (
            Eigentuemerversammlung.objects
            .select_related('objekt', 'erstellt_von', 'einladungs_pdf', 'protokoll_pdf')
            .prefetch_related('tagesordnung')
        )
        params = self.request.query_params
        if objekt := params.get('objekt'):
            qs = qs.filter(objekt_id=objekt)
        if status_filter := params.get('status'):
            qs = qs.filter(status=status_filter)
        if jahr := params.get('jahr'):
            if str(jahr).isdigit():
                qs = qs.filter(termin__year=int(jahr))
        return qs

    def get_serializer_class(self):
        if self.action == 'create':
            return EigentuemerversammlungCreateSerializer
        if self.action in ('update', 'partial_update'):
            return EigentuemerversammlungUpdateSerializer
        if self.action == 'list':
            return EigentuemerversammlungListSerializer
        return EigentuemerversammlungDetailSerializer

    def create(self, request, *args, **kwargs):
        serializer = EigentuemerversammlungCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        daten = serializer.validated_data
        try:
            ev = ev_service.erstelle_ev(
                objekt=daten['objekt'],
                erstellt_von=request.user,
                arbeitsname=daten.get('arbeitsname', ''),
                art=daten['art'],
                stimmprinzip=daten['stimmprinzip'],
                stimm_verteilerschluessel=daten.get('stimm_verteilerschluessel'),
                stimm_wirtschaftsjahr=daten['stimm_wirtschaftsjahr'],
                einladungstext=daten.get('einladungstext'),
            )
        except DjangoValidationError as exc:
            return _fehler(exc)
        return Response(
            EigentuemerversammlungDetailSerializer(ev).data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        ev = self.get_object()
        serializer = EigentuemerversammlungUpdateSerializer(
            data=request.data, partial=True,
        )
        serializer.is_valid(raise_exception=True)
        daten = serializer.validated_data

        termin_daten = {
            feld: daten[feld]
            for feld in EigentuemerversammlungUpdateSerializer.TERMIN_FELDER
            if feld in daten
        }
        direkt_felder = [
            feld for feld in EigentuemerversammlungUpdateSerializer.DIREKT_FELDER
            if feld in daten
        ]

        try:
            with transaction.atomic():
                for feld in direkt_felder:
                    setattr(ev, feld, daten[feld])
                if direkt_felder:
                    ev.full_clean()
                    ev.save(update_fields=direkt_felder)
                if termin_daten:
                    ev_service.aktualisiere_terminierung(
                        ev, request.user, **termin_daten,
                    )
        except DjangoValidationError as exc:
            return _fehler(exc)

        ev.refresh_from_db()
        return Response(EigentuemerversammlungDetailSerializer(ev).data)

    # ── Task-Fortschritt ──────────────────────────────────────────────────

    @action(detail=True, methods=['post'], url_path='task-erledigt')
    def task_erledigt(self, request, pk=None):
        """``{"task_nr": 1..5}`` — markiert einen Task als erledigt."""
        ev = self.get_object()
        try:
            task_nr = int(request.data.get('task_nr'))
        except (TypeError, ValueError):
            return Response(
                {'detail': 'task_nr (1–5) ist erforderlich.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ev_service.markiere_task_erledigt(ev, task_nr, request.user)
        except DjangoValidationError as exc:
            return _fehler(exc)
        ev.refresh_from_db()
        return Response(EigentuemerversammlungDetailSerializer(ev).data)

    @action(detail=True, methods=['post'], url_path='task-zuruecksetzen')
    def task_zuruecksetzen(self, request, pk=None):
        """``{"task_nr": 1..5, "grund": "…"}`` — Grund ist Pflicht."""
        ev = self.get_object()
        try:
            task_nr = int(request.data.get('task_nr'))
        except (TypeError, ValueError):
            return Response(
                {'detail': 'task_nr (1–5) ist erforderlich.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ev_service.setze_task_zurueck(
                ev, task_nr, request.user, request.data.get('grund', ''),
            )
        except DjangoValidationError as exc:
            return _fehler(exc)
        ev.refresh_from_db()
        return Response(EigentuemerversammlungDetailSerializer(ev).data)

    @action(detail=True, methods=['get'])
    def ereignisse(self, request, pk=None):
        """Audit-Verlauf der EV (unveränderlich)."""
        ev = self.get_object()
        eintraege = ev.ereignisse.select_related('erstellt_von').all()
        return Response(EVEreignisSerializer(eintraege, many=True).data)

    # ── Task 2: Tagesordnung ──────────────────────────────────────────────

    @action(detail=True, methods=['get'])
    def tagesordnung(self, request, pk=None):
        ev = self.get_object()
        return Response({
            'tagesordnung': TagesordnungspunktSerializer(
                ev.tagesordnung.order_by('nummer'), many=True,
            ).data,
            'probleme': tagesordnung_service.pruefe_vollstaendigkeit(ev),
        })

    # ── Teilnehmer und Stimmkraft ─────────────────────────────────────────

    @action(detail=True, methods=['post'], url_path='teilnehmer-ermitteln')
    def teilnehmer_ermitteln(self, request, pk=None):
        """Erzeugt/aktualisiert Teilnehmer und Stimmkraft-Snapshot."""
        ev = self.get_object()
        try:
            stats = stimmkraft_service.ermittle_teilnehmer(ev, request.user)
        except DjangoValidationError as exc:
            return _fehler(exc)
        return Response(stats)

    @action(detail=True, methods=['get'])
    def teilnehmer(self, request, pk=None):
        ev = self.get_object()
        eintraege = (
            ev.teilnehmer
            .select_related('person', 'vertreten_durch')
            .prefetch_related('anteile')
            .all()
        )
        return Response(EVTeilnehmerSerializer(eintraege, many=True).data)

    # ── Task 3: Einladung ─────────────────────────────────────────────────

    @action(detail=True, methods=['post'], url_path='einladung-pdf')
    def einladung_pdf(self, request, pk=None):
        """``{"anlagen_ids": ["…"]}`` — erzeugt das Einladungs-PDF im DMS."""
        ev = self.get_object()
        anlagen_ids = request.data.get('anlagen_ids') or []
        if not isinstance(anlagen_ids, list):
            return Response(
                {'detail': 'anlagen_ids muss eine Liste von Dokument-IDs sein.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            dokument = einladung_service.erzeuge_einladungs_pdf(
                ev, request.user, anlagen_ids=anlagen_ids,
            )
        except DjangoValidationError as exc:
            return _fehler(exc)
        return Response({
            'dokument_id': str(dokument.id),
            'dateiname': dokument.dateiname,
            'download_url': f'/api/v1/dokumente/{dokument.id}/datei/',
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def versandplan(self, request, pk=None):
        """Vorgeschlagener Kanal je Teilnehmer plus Ladungsfrist-Hinweis."""
        ev = self.get_object()
        return Response(einladung_service.versandplan(ev))

    @action(detail=True, methods=['post'], url_path='einladungen-versenden')
    def einladungen_versenden(self, request, pk=None):
        """``{"plan": {teilnehmer_id: kanal}, "sofort": false}``

        Standard ist der asynchrone Versand über Celery (HTTP 202) — bei
        größeren Gemeinschaften würde der synchrone Lauf in den Timeout laufen.
        ``sofort=true`` versendet innerhalb des Requests und liefert das
        Ergebnis direkt zurück; nur für kleine Versammlungen und manuelle Läufe.
        """
        ev = self.get_object()
        plan = request.data.get('plan') or {}
        if not isinstance(plan, dict):
            return Response(
                {'detail': 'plan muss ein Objekt {teilnehmer_id: kanal} sein.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if _parse_bool(request.data.get('sofort')):
            try:
                ergebnis = einladung_service.versende_einladungen(
                    ev, request.user, plan=plan,
                )
            except DjangoValidationError as exc:
                return _fehler(exc)
            return Response(ergebnis)

        if ev.einladungs_pdf_id is None:
            return Response(
                {'detail': 'Es gibt noch kein Einladungs-PDF — bitte zuerst erzeugen.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from apps.versammlung.tasks import versende_ev_einladungen

        ev_id, user_id = str(ev.id), request.user.id
        transaction.on_commit(
            lambda: versende_ev_einladungen.delay(ev_id, user_id, plan),
        )
        return Response(
            {
                'detail': 'Versand wurde beauftragt. Das Ergebnis steht im '
                          'Versandprotokoll.',
                'anzahl_empfaenger': ev.teilnehmer.count(),
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=['get'])
    def versandprotokoll(self, request, pk=None):
        ev = self.get_object()
        eintraege = (
            ev.versandprotokolle
            .select_related('person', 'versendet_von')
            .all()
        )
        return Response(EVVersandprotokollSerializer(eintraege, many=True).data)

    # ── Task 4: Durchführung ──────────────────────────────────────────────

    @action(detail=True, methods=['get'])
    def quorum(self, request, pk=None):
        """Anwesende Stimmkraft — rein informativ, kein Gate auf Abstimmungen."""
        ev = self.get_object()
        return Response(stimmkraft_service.berechne_quorum(ev))

    @action(detail=True, methods=['post'], url_path='durchfuehrung-abschliessen')
    def durchfuehrung_abschliessen(self, request, pk=None):
        """Schließt Task 4 ab (Status → durchgefuehrt).

        Schlägt fehl, solange ein abstimmungspflichtiger TOP noch kein Ergebnis
        hat — ein vergessener TOP fehlt sonst im Protokoll.
        """
        ev = self.get_object()
        try:
            durchfuehrung_service.schliesse_durchfuehrung_ab(ev, request.user)
        except DjangoValidationError as exc:
            return _fehler(exc)
        ev.refresh_from_db()
        return Response(EigentuemerversammlungDetailSerializer(ev).data)

    # ── Task 5: Beschlussfassung ──────────────────────────────────────────

    @action(detail=True, methods=['post'], url_path='beschluesse-uebernehmen')
    def beschluesse_uebernehmen(self, request, pk=None):
        """Übernimmt angenommene TOPs in die Beschluss-Sammlung (§ 24 Abs. 7 WEG),
        legt Folgeaufgaben an und erzeugt das Protokoll."""
        ev = self.get_object()
        try:
            ergebnis = beschluss_service.uebernimm_in_sammlung(ev, request.user)
        except DjangoValidationError as exc:
            return _fehler(exc)
        return Response(ergebnis)

    @action(detail=True, methods=['post'], url_path='protokoll-pdf')
    def protokoll_pdf(self, request, pk=None):
        """Erzeugt das Protokoll neu (z.B. nach einer Ergebniskorrektur).

        Die vorherige Fassung bleibt als Dokument im DMS erhalten (GoBD).
        """
        ev = self.get_object()
        try:
            dokument = beschluss_service.erzeuge_protokoll_pdf(ev, request.user)
        except DjangoValidationError as exc:
            return _fehler(exc)
        return Response({
            'dokument_id': str(dokument.id),
            'dateiname': dokument.dateiname,
            'download_url': f'/api/v1/dokumente/{dokument.id}/datei/',
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def beschluesse(self, request, pk=None):
        """Beschlüsse dieser Versammlung."""
        ev = self.get_object()
        eintraege = (
            ev.beschluesse
            .select_related('objekt', 'top', 'dokument', 'vorgang', 'erstellt_von')
            .order_by('nummer')
        )
        return Response(BeschlussSerializer(eintraege, many=True).data)


class TagesordnungspunktViewSet(mixins.ListModelMixin,
                                mixins.RetrieveModelMixin,
                                mixins.CreateModelMixin,
                                mixins.UpdateModelMixin,
                                mixins.DestroyModelMixin,
                                viewsets.GenericViewSet):
    """``/api/v1/tagesordnungspunkte/`` — Pflege der TOPs.

    Anlage, Änderung und Löschung laufen über ``tagesordnung_service``; die
    dortige Sperre nach dem Einladungsversand (§ 23 Abs. 2 WEG) gilt damit
    auch für die API.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = TagesordnungspunktSerializer

    def get_queryset(self):
        qs = Tagesordnungspunkt.objects.select_related('ev').all()
        if ev_id := self.request.query_params.get('ev'):
            qs = qs.filter(ev_id=ev_id)
        return qs.order_by('ev', 'nummer')

    def create(self, request, *args, **kwargs):
        serializer = TagesordnungspunktCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        daten = dict(serializer.validated_data)
        ev = daten.pop('ev')
        try:
            top = tagesordnung_service.top_anlegen(
                ev=ev, erstellt_von=request.user, **daten,
            )
        except DjangoValidationError as exc:
            return _fehler(exc)
        return Response(
            TagesordnungspunktSerializer(top).data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        top = self.get_object()
        serializer = TagesordnungspunktSerializer(
            top, data=request.data, partial=True,
        )
        serializer.is_valid(raise_exception=True)
        felder = {
            feld: wert for feld, wert in serializer.validated_data.items()
            if feld != 'nummer'
        }
        if 'nummer' in request.data:
            return Response(
                {'detail': 'Die TOP-Nummer wird nicht einzeln geändert — sie '
                           'ergibt sich aus der Reihenfolge (Anlage mit '
                           'Position bzw. Löschen).'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            tagesordnung_service.top_aktualisieren(top, request.user, **felder)
        except DjangoValidationError as exc:
            return _fehler(exc)
        top.refresh_from_db()
        return Response(TagesordnungspunktSerializer(top).data)

    def destroy(self, request, *args, **kwargs):
        top = self.get_object()
        try:
            tagesordnung_service.top_loeschen(top, request.user)
        except DjangoValidationError as exc:
            return _fehler(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ── Task 4: Abstimmung am TOP ─────────────────────────────────────────

    @action(detail=True, methods=['post'])
    def abstimmung(self, request, pk=None):
        """``{"ja": 16, "nein": 4, "enthaltung": 3}`` — Summenerfassung.

        Enthaltungen zählen bei einfacher und qualifizierter Mehrheit nicht in
        den Nenner (Spec v1.1 Kap. 6.1). Eine erneute Erfassung überschreibt
        das Ergebnis und wird als Korrektur protokolliert.
        """
        top = self.get_object()
        serializer = AbstimmungSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            durchfuehrung_service.erfasse_abstimmung(
                top, request.user, **serializer.validated_data,
            )
        except DjangoValidationError as exc:
            return _fehler(exc)
        top.refresh_from_db()
        return Response(TagesordnungspunktSerializer(top).data)

    @action(detail=True, methods=['post'])
    def einzelstimmen(self, request, pk=None):
        """``{"voten": {teilnehmer_id: votum}}`` — namentliche Abstimmung.

        Erlaubte Voten: ja, nein, enthaltung. Das Summenergebnis wird daraus
        abgeleitet; es gibt nur einen Bewertungspfad.
        """
        top = self.get_object()
        serializer = EinzelstimmenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            durchfuehrung_service.erfasse_einzelstimmen(
                top, request.user, serializer.validated_data['voten'],
            )
        except DjangoValidationError as exc:
            return _fehler(exc)
        top.refresh_from_db()
        return Response(TagesordnungspunktSerializer(top).data)

    @action(detail=True, methods=['get'])
    def stimmen(self, request, pk=None):
        """Erfasste Einzelvoten des TOP (leer bei Summenerfassung)."""
        top = self.get_object()
        eintraege = top.stimmen.select_related('teilnehmer__person').all()
        return Response(EVStimmeSerializer(eintraege, many=True).data)

    @action(detail=True, methods=['post'], url_path='ergebnis-status')
    def ergebnis_status(self, request, pk=None):
        """``{"ergebnis": "vertagt" oder "entfallen", "bemerkung": "…"}``

        Für TOPs, über die gerade NICHT abgestimmt wurde — die Stimmenfelder
        bleiben auf 0.
        """
        top = self.get_object()
        serializer = ErgebnisStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            durchfuehrung_service.setze_ergebnis_status(
                top, request.user,
                serializer.validated_data['ergebnis'],
                serializer.validated_data.get('bemerkung', ''),
            )
        except DjangoValidationError as exc:
            return _fehler(exc)
        top.refresh_from_db()
        return Response(TagesordnungspunktSerializer(top).data)


class EVTeilnehmerViewSet(mixins.RetrieveModelMixin,
                          mixins.UpdateModelMixin,
                          viewsets.GenericViewSet):
    """``/api/v1/ev-teilnehmer/{id}/`` — Anwesenheit, Vertretung und Zusage.

    Nur PATCH: Teilnehmer entstehen ausschließlich über
    ``stimmkraft_service.ermittle_teilnehmer`` (Stimmkraft-Snapshot), nie über
    die API. ``stimmkraft`` ist damit von außen nicht setzbar.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = EVTeilnehmerSerializer

    def get_queryset(self):
        qs = (
            EVTeilnehmer.objects
            .select_related('ev', 'person', 'vertreten_durch')
            .prefetch_related('anteile')
        )
        if ev_id := self.request.query_params.get('ev'):
            qs = qs.filter(ev_id=ev_id)
        return qs

    def update(self, request, *args, **kwargs):
        teilnehmer = self.get_object()
        serializer = AnwesenheitSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        daten = serializer.validated_data

        anwesenheit_felder = {
            feld: daten[feld] for feld in
            ('ist_anwesend', 'vertreten_durch', 'vertreter_name', 'vollmacht_dokument')
            if feld in daten
        }

        try:
            with transaction.atomic():
                if anwesenheit_felder:
                    # ist_anwesend ist Pflichtargument des Services; bei einer
                    # reinen Vertretungsänderung bleibt der bisherige Wert.
                    anwesenheit_felder.setdefault('ist_anwesend', teilnehmer.ist_anwesend)
                    durchfuehrung_service.erfasse_anwesenheit(
                        teilnehmer, request.user, **anwesenheit_felder,
                    )
                if 'zusage_status' in daten:
                    durchfuehrung_service.erfasse_zusage(
                        teilnehmer, request.user,
                        zusage_status=daten['zusage_status'], quelle='manuell',
                    )
        except DjangoValidationError as exc:
            return _fehler(exc)

        teilnehmer.refresh_from_db()
        return Response(EVTeilnehmerSerializer(teilnehmer).data)


class BeschlussViewSet(mixins.ListModelMixin,
                       mixins.RetrieveModelMixin,
                       viewsets.GenericViewSet):
    """``/api/v1/beschluesse/`` — Beschluss-Sammlung nach § 24 Abs. 7 WEG.

    Lesend plus die Aktion ``anfechtung``. Kein POST/PATCH/DELETE: Beschlüsse
    entstehen ausschließlich über ``beschluss_service.uebernimm_in_sammlung``,
    ihr Wortlaut wird nie geändert und Einträge werden nie gelöscht.

    Abweichung von Spec Kap. 10.1: die Sammlung je Objekt läuft über
    ``?objekt=<id>`` statt über einen neuen Endpunkt am ObjektViewSet — dort
    ist der Query-Parameter ``typ`` schon doppelt belegt, und die Sammlung
    gehört fachlich in diese App.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = BeschlussSerializer

    def get_queryset(self):
        qs = Beschluss.objects.select_related(
            'objekt', 'ev', 'top', 'dokument', 'vorgang', 'erstellt_von',
        )
        params = self.request.query_params
        if objekt := params.get('objekt'):
            qs = qs.filter(objekt_id=objekt)
        if ev_id := params.get('ev'):
            qs = qs.filter(ev_id=ev_id)
        if anfechtung := params.get('anfechtung_status'):
            qs = qs.filter(anfechtung_status=anfechtung)
        if jahr := params.get('jahr'):
            if str(jahr).isdigit():
                qs = qs.filter(beschluss_datum__year=int(jahr))
        return qs.order_by('objekt', '-nummer')

    @action(detail=True, methods=['post'])
    def anfechtung(self, request, pk=None):
        """``{"anfechtung_status": "anhaengig", "notiz": "…"}``

        Vermerkt Anfechtung bzw. gerichtliche Aufhebung. Der Wortlaut des
        Beschlusses bleibt unangetastet — auch ein aufgehobener Beschluss
        bleibt in der Sammlung stehen.
        """
        beschluss = self.get_object()
        serializer = AnfechtungSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            beschluss_service.vermerke_anfechtung(
                beschluss, request.user, **serializer.validated_data,
            )
        except DjangoValidationError as exc:
            return _fehler(exc)
        beschluss.refresh_from_db()
        return Response(BeschlussSerializer(beschluss).data)
