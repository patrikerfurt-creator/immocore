"""
Serializer für die EV-API (Spec v1.1 Kap. 10.1).

Reine Ein-/Ausgabe-Übersetzung — jede Mutation läuft über die Services in
``apps.versammlung.services``. Serializer enthalten bewusst KEINE
Business-Logik (Architekturprinzip des Projekts).
"""
from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.dokumente.models import Dokument
from apps.objekte.models import Objekt, Verteilerschluessel
from apps.personen.models import Person
from apps.versammlung.models import (
    Beschluss, EVEreignis, EVStimme, EVTeilnehmer, EVTeilnehmerAnteil,
    EVVersandprotokoll, Eigentuemerversammlung, Tagesordnungspunkt,
)
from apps.versammlung.services import ev_service

User = get_user_model()


def _user_name(user) -> str | None:
    if user is None:
        return None
    return user.get_full_name() or user.get_username()


class EVEreignisSerializer(serializers.ModelSerializer):
    typ_display = serializers.CharField(source='get_typ_display', read_only=True)
    erstellt_von_name = serializers.SerializerMethodField()

    class Meta:
        model = EVEreignis
        fields = [
            'id', 'typ', 'typ_display', 'top', 'text', 'alter_wert',
            'neuer_wert', 'erstellt_am', 'erstellt_von', 'erstellt_von_name',
        ]
        read_only_fields = fields

    def get_erstellt_von_name(self, obj):
        return _user_name(obj.erstellt_von)


class TagesordnungspunktSerializer(serializers.ModelSerializer):
    abstimmungsmodus_display = serializers.CharField(
        source='get_abstimmungsmodus_display', read_only=True,
    )
    abstimmungsergebnis_display = serializers.CharField(
        source='get_abstimmungsergebnis_display', read_only=True,
    )

    class Meta:
        model = Tagesordnungspunkt
        fields = [
            'id', 'ev', 'nummer', 'titel', 'erlaeuterung', 'beschlussvorlage',
            'abstimmungsmodus', 'abstimmungsmodus_display', 'mehrheit_schwelle',
            'abstimmung_ja', 'abstimmung_nein', 'abstimmung_enthaltung',
            'abstimmungsergebnis', 'abstimmungsergebnis_display',
            'ergebnis_bemerkung', 'triggert_vorgang', 'triggert_wirtschaftsplan',
        ]
        # Ergebnis-Felder werden erst in Phase D über den
        # Durchführungs-Service gesetzt, nie direkt per API.
        read_only_fields = [
            'id', 'ev', 'abstimmung_ja', 'abstimmung_nein',
            'abstimmung_enthaltung', 'abstimmungsergebnis',
        ]


class TagesordnungspunktCreateSerializer(serializers.Serializer):
    """Eingabe für ``POST /tagesordnungspunkte/`` — Anlage über den Service."""

    ev = serializers.PrimaryKeyRelatedField(
        queryset=Eigentuemerversammlung.objects.all(),
    )
    titel = serializers.CharField(max_length=255)
    nummer = serializers.IntegerField(required=False, allow_null=True)
    erlaeuterung = serializers.CharField(required=False, allow_blank=True, default='')
    beschlussvorlage = serializers.CharField(required=False, allow_blank=True, default='')
    abstimmungsmodus = serializers.ChoiceField(
        choices=Tagesordnungspunkt.MODUS_CHOICES, default='einfache_mehrheit',
    )
    mehrheit_schwelle = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, allow_null=True,
    )
    triggert_vorgang = serializers.BooleanField(default=False)
    triggert_wirtschaftsplan = serializers.BooleanField(default=False)


class EVTeilnehmerAnteilSerializer(serializers.ModelSerializer):
    class Meta:
        model = EVTeilnehmerAnteil
        fields = [
            'id', 'eigentumsverhaeltnis', 'einheit_nr_snapshot', 'mea_wert_snapshot',
        ]
        read_only_fields = fields


class EVTeilnehmerSerializer(serializers.ModelSerializer):
    person_name = serializers.CharField(source='person.name', read_only=True)
    vertreten_durch_name = serializers.SerializerMethodField()
    anteile = EVTeilnehmerAnteilSerializer(many=True, read_only=True)

    class Meta:
        model = EVTeilnehmer
        fields = [
            'id', 'ev', 'person', 'person_name', 'stimmkraft',
            'zusage_status', 'zusage_am', 'zusage_quelle',
            'ist_anwesend', 'anwesenheit_erfasst_am',
            'vertreten_durch', 'vertreten_durch_name', 'vertreter_name',
            'vollmacht_dokument', 'anteile',
        ]
        read_only_fields = [
            'id', 'ev', 'person', 'person_name', 'stimmkraft', 'anteile',
            'zusage_am', 'anwesenheit_erfasst_am',
        ]

    def get_vertreten_durch_name(self, obj):
        return obj.vertreten_durch.name if obj.vertreten_durch_id else None


class EVVersandprotokollSerializer(serializers.ModelSerializer):
    person_name = serializers.CharField(source='person.name', read_only=True)
    kanal_display = serializers.CharField(source='get_kanal_display', read_only=True)
    versendet_von_name = serializers.SerializerMethodField()

    class Meta:
        model = EVVersandprotokoll
        fields = [
            'id', 'person', 'person_name', 'kanal', 'kanal_display', 'status',
            'empfaenger', 'epost_pfad', 'fehlertext',
            'versendet_am', 'versendet_von', 'versendet_von_name',
        ]
        read_only_fields = fields

    def get_versendet_von_name(self, obj):
        return _user_name(obj.versendet_von)


class EigentuemerversammlungListSerializer(serializers.ModelSerializer):
    objekt_bezeichnung = serializers.CharField(
        source='objekt.bezeichnung', read_only=True,
    )
    objektnummer = serializers.CharField(source='objekt.objektnummer', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    anzahl_tops = serializers.IntegerField(source='tagesordnung.count', read_only=True)
    anzahl_teilnehmer = serializers.IntegerField(source='teilnehmer.count', read_only=True)
    tasks_erledigt = serializers.SerializerMethodField()

    class Meta:
        model = Eigentuemerversammlung
        fields = [
            'id', 'objekt', 'objekt_bezeichnung', 'objektnummer', 'arbeitsname',
            'art', 'termin', 'ort', 'status', 'status_display', 'stimmprinzip',
            'anzahl_tops', 'anzahl_teilnehmer', 'tasks_erledigt',
            'einladung_versendet_am', 'durchgefuehrt_am', 'erstellt_am',
        ]
        read_only_fields = fields

    def get_tasks_erledigt(self, obj):
        return ev_service.task_status(obj)['anzahl_erledigt']


class EigentuemerversammlungDetailSerializer(serializers.ModelSerializer):
    objekt_bezeichnung = serializers.CharField(
        source='objekt.bezeichnung', read_only=True,
    )
    objektnummer = serializers.CharField(source='objekt.objektnummer', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    art_display = serializers.CharField(source='get_art_display', read_only=True)
    stimmprinzip_display = serializers.CharField(
        source='get_stimmprinzip_display', read_only=True,
    )
    stimm_verteilerschluessel_text = serializers.SerializerMethodField()
    tagesordnung = TagesordnungspunktSerializer(many=True, read_only=True)
    task_status = serializers.SerializerMethodField()
    ladungsfrist = serializers.SerializerMethodField()
    erstellt_von_name = serializers.SerializerMethodField()
    einladungs_pdf_dateiname = serializers.CharField(
        source='einladungs_pdf.dateiname', read_only=True, default=None,
    )

    class Meta:
        model = Eigentuemerversammlung
        fields = [
            'id', 'objekt', 'objekt_bezeichnung', 'objektnummer',
            'arbeitsname', 'art', 'art_display',
            'termin', 'ort', 'raum_buchung_notizen', 'terminvorschlaege',
            'stimmprinzip', 'stimmprinzip_display',
            'stimm_verteilerschluessel', 'stimm_verteilerschluessel_text',
            'stimm_wirtschaftsjahr',
            'status', 'status_display', 'task_status', 'ladungsfrist',
            'einladungstext', 'einladungs_pdf', 'einladungs_pdf_dateiname',
            'protokoll_pdf', 'tagesordnung',
            'versammlungsleiter', 'protokollfuehrer',
            'einladung_versendet_am', 'durchgefuehrt_am',
            'erstellt_am', 'erstellt_von', 'erstellt_von_name',
        ]
        read_only_fields = fields

    def get_stimm_verteilerschluessel_text(self, obj):
        vs = obj.stimm_verteilerschluessel
        return f'{vs.schluessel} {vs.bezeichnung}' if vs else None

    def get_task_status(self, obj):
        return ev_service.task_status(obj)

    def get_ladungsfrist(self, obj):
        # Lokaler Import: einladung_service zieht WeasyPrint nach, das soll
        # nicht bei jedem Serializer-Import geladen werden.
        from apps.versammlung.services import einladung_service

        return einladung_service.pruefe_ladungsfrist(obj)

    def get_erstellt_von_name(self, obj):
        return _user_name(obj.erstellt_von)


class EigentuemerversammlungCreateSerializer(serializers.Serializer):
    """Eingabe für ``POST /versammlungen/``."""

    objekt = serializers.PrimaryKeyRelatedField(queryset=Objekt.objects.all())
    arbeitsname = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default='',
    )
    art = serializers.ChoiceField(
        choices=Eigentuemerversammlung.ART_CHOICES, default='ordentlich',
    )
    stimmprinzip = serializers.ChoiceField(
        choices=Eigentuemerversammlung.STIMMPRINZIP_CHOICES, default='kopf',
    )
    stimm_verteilerschluessel = serializers.PrimaryKeyRelatedField(
        queryset=Verteilerschluessel.objects.all(), required=False, allow_null=True,
    )
    stimm_wirtschaftsjahr = serializers.IntegerField(default=0)
    einladungstext = serializers.CharField(required=False, allow_blank=True)


class EigentuemerversammlungUpdateSerializer(serializers.Serializer):
    """Eingabe für ``PATCH /versammlungen/{id}/``.

    Terminfelder laufen über ``ev_service.aktualisiere_terminierung`` (Audit),
    die übrigen Felder werden direkt gesetzt. ``status`` und die Task-Flags
    sind hier bewusst NICHT enthalten — dafür gibt es eigene Aktionen.
    """

    termin = serializers.DateTimeField(required=False, allow_null=True)
    ort = serializers.CharField(max_length=255, required=False, allow_blank=True)
    raum_buchung_notizen = serializers.CharField(required=False, allow_blank=True)
    terminvorschlaege = serializers.ListField(required=False)

    arbeitsname = serializers.CharField(
        max_length=200, required=False, allow_blank=True,
    )
    art = serializers.ChoiceField(
        choices=Eigentuemerversammlung.ART_CHOICES, required=False,
    )
    stimmprinzip = serializers.ChoiceField(
        choices=Eigentuemerversammlung.STIMMPRINZIP_CHOICES, required=False,
    )
    stimm_verteilerschluessel = serializers.PrimaryKeyRelatedField(
        queryset=Verteilerschluessel.objects.all(), required=False, allow_null=True,
    )
    stimm_wirtschaftsjahr = serializers.IntegerField(required=False)
    einladungstext = serializers.CharField(required=False, allow_blank=True)
    versammlungsleiter = serializers.CharField(
        max_length=200, required=False, allow_blank=True,
    )
    protokollfuehrer = serializers.CharField(
        max_length=200, required=False, allow_blank=True,
    )

    TERMIN_FELDER = ('termin', 'ort', 'raum_buchung_notizen', 'terminvorschlaege')
    DIREKT_FELDER = (
        'arbeitsname', 'art', 'stimmprinzip', 'stimm_verteilerschluessel',
        'stimm_wirtschaftsjahr',
        'einladungstext', 'versammlungsleiter', 'protokollfuehrer',
    )


# ---------------------------------------------------------------------------
# Phase D: Durchführung und Beschlussfassung (Spec v1.1 Kap. 10.1)
# ---------------------------------------------------------------------------

class EVStimmeSerializer(serializers.ModelSerializer):
    person_name = serializers.CharField(source='teilnehmer.person.name', read_only=True)
    votum_display = serializers.CharField(source='get_votum_display', read_only=True)

    class Meta:
        model = EVStimme
        fields = [
            'id', 'top', 'teilnehmer', 'person_name', 'votum', 'votum_display',
            'stimmkraft', 'erfasst_am', 'erfasst_von',
        ]
        read_only_fields = fields


class AnwesenheitSerializer(serializers.Serializer):
    """Eingabe für ``PATCH /ev-teilnehmer/{id}/``.

    Alle Felder optional — es wird nur geändert, was übergeben wird.
    ``ist_anwesend=null`` setzt die Erfassung bewusst auf "offen" zurück.
    """

    ist_anwesend = serializers.BooleanField(required=False, allow_null=True)
    vertreten_durch = serializers.PrimaryKeyRelatedField(
        queryset=Person.objects.all(), required=False, allow_null=True,
    )
    vertreter_name = serializers.CharField(
        max_length=200, required=False, allow_blank=True,
    )
    vollmacht_dokument = serializers.PrimaryKeyRelatedField(
        queryset=Dokument.objects.all(), required=False, allow_null=True,
    )
    zusage_status = serializers.ChoiceField(
        choices=EVTeilnehmer.ZUSAGE_CHOICES, required=False,
    )


class AbstimmungSerializer(serializers.Serializer):
    """Eingabe für ``POST /tagesordnungspunkte/{id}/abstimmung/`` (Summenerfassung)."""

    ja = serializers.DecimalField(max_digits=12, decimal_places=4)
    nein = serializers.DecimalField(max_digits=12, decimal_places=4)
    enthaltung = serializers.DecimalField(
        max_digits=12, decimal_places=4, required=False, default=0,
    )
    bemerkung = serializers.CharField(required=False, allow_blank=True)


class EinzelstimmenSerializer(serializers.Serializer):
    """Eingabe für ``POST /tagesordnungspunkte/{id}/einzelstimmen/``."""

    voten = serializers.DictField(
        child=serializers.ChoiceField(choices=EVStimme.VOTUM_CHOICES),
    )


class ErgebnisStatusSerializer(serializers.Serializer):
    """Eingabe für ``POST /tagesordnungspunkte/{id}/ergebnis-status/``."""

    ergebnis = serializers.ChoiceField(choices=['vertagt', 'entfallen'])
    bemerkung = serializers.CharField(required=False, allow_blank=True, default='')


class BeschlussSerializer(serializers.ModelSerializer):
    objekt_bezeichnung = serializers.CharField(
        source='objekt.bezeichnung', read_only=True,
    )
    top_nummer = serializers.IntegerField(source='top.nummer', read_only=True, default=None)
    top_titel = serializers.CharField(source='top.titel', read_only=True, default=None)
    anfechtung_status_display = serializers.CharField(
        source='get_anfechtung_status_display', read_only=True,
    )
    dokument_dateiname = serializers.CharField(
        source='dokument.dateiname', read_only=True, default=None,
    )
    vorgang_nummer = serializers.CharField(
        source='vorgang.nummer', read_only=True, default=None,
    )
    erstellt_von_name = serializers.SerializerMethodField()

    class Meta:
        model = Beschluss
        fields = [
            'id', 'objekt', 'objekt_bezeichnung', 'nummer', 'ev',
            'top', 'top_nummer', 'top_titel',
            'beschluss_datum', 'ort', 'wortlaut',
            'ergebnis_ja', 'ergebnis_nein', 'ergebnis_enthaltung',
            'dokument', 'dokument_dateiname', 'vorgang', 'vorgang_nummer',
            'anfechtung_status', 'anfechtung_status_display', 'anfechtung_notiz',
            'aufgehoben_am', 'gerichtlicher_hinweis',
            'erstellt_am', 'erstellt_von', 'erstellt_von_name',
        ]
        # § 24 Abs. 7 WEG: Wortlaut und Ergebnis sind unveränderlich; Anfechtung
        # wird ausschließlich über die Aktion 'anfechtung' vermerkt.
        read_only_fields = fields

    def get_erstellt_von_name(self, obj):
        return _user_name(obj.erstellt_von)


class AnfechtungSerializer(serializers.Serializer):
    """Eingabe für ``POST /beschluesse/{id}/anfechtung/``."""

    anfechtung_status = serializers.ChoiceField(choices=Beschluss.ANFECHTUNG_CHOICES)
    notiz = serializers.CharField(required=False, allow_blank=True, default='')
    aufgehoben_am = serializers.DateField(required=False, allow_null=True)
    gerichtlicher_hinweis = serializers.CharField(
        required=False, allow_blank=True, default='',
    )
