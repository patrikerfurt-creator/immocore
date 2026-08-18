"""
Serializer für die Vorgang/VorgangTyp/VorgangEreignis-API (Kap. 2 der Spec).

Reine Ein-/Ausgabe-Übersetzung — jede Mutation läuft über die Services
(``vorgang_service`` / ``dokument_service``); Serializer enthalten bewusst
KEINE Business-Logik (Architekturprinzip).
"""
from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.dokumente.models import Dokument
from apps.objekte.models import Einheit, Objekt
from apps.personen.models import Person

from .models import (
    PRIORITAET_CHOICES,
    Vorgang,
    VorgangAntwortVorschlag,
    VorgangEreignis,
    VorgangTyp,
)

User = get_user_model()


def _user_name(user) -> str | None:
    if user is None:
        return None
    voller_name = user.get_full_name()
    return voller_name or user.get_username()


class VorgangTypSerializer(serializers.ModelSerializer):
    class Meta:
        model = VorgangTyp
        fields = [
            'id', 'code', 'bezeichnung', 'standard_prioritaet',
            'aktiv', 'sortierung', 'antwort_vorschlag_aktiv',
            'erstellt_am', 'erstellt_von',
        ]
        read_only_fields = ['id', 'erstellt_am']


class VorgangEreignisSerializer(serializers.ModelSerializer):
    erstellt_von_name = serializers.SerializerMethodField()

    class Meta:
        model = VorgangEreignis
        fields = [
            'id', 'typ', 'text', 'alter_wert', 'neuer_wert', 'intern',
            'erstellt_am', 'erstellt_von', 'erstellt_von_name',
        ]
        read_only_fields = fields

    def get_erstellt_von_name(self, obj):
        return _user_name(obj.erstellt_von)


class VorgangDokumentSerializer(serializers.ModelSerializer):
    hochgeladen_von_name = serializers.SerializerMethodField()

    class Meta:
        model = Dokument
        fields = [
            'id', 'dateiname', 'kategorie', 'dokument_typ', 'beschreibung',
            'version', 'vorgaenger_version', 'sha256',
            'hochgeladen_am', 'hochgeladen_von', 'hochgeladen_von_name',
        ]
        read_only_fields = fields

    def get_hochgeladen_von_name(self, obj):
        return _user_name(obj.hochgeladen_von)


class VorgangAntwortVorschlagSerializer(serializers.ModelSerializer):
    erzeugt_von_name = serializers.SerializerMethodField()
    bearbeitet_von_name = serializers.SerializerMethodField()
    freigegeben_von_name = serializers.SerializerMethodField()

    class Meta:
        model = VorgangAntwortVorschlag
        fields = [
            'id', 'vorgang', 'text_ki', 'text', 'status', 'modell', 'fehler',
            'erzeugt_am', 'erzeugt_von', 'erzeugt_von_name',
            'bearbeitet_am', 'bearbeitet_von', 'bearbeitet_von_name',
            'freigegeben_am', 'freigegeben_von', 'freigegeben_von_name',
        ]
        read_only_fields = fields

    def get_erzeugt_von_name(self, obj):
        return _user_name(obj.erzeugt_von)

    def get_bearbeitet_von_name(self, obj):
        return _user_name(obj.bearbeitet_von)

    def get_freigegeben_von_name(self, obj):
        return _user_name(obj.freigegeben_von)


class VorgangListSerializer(serializers.ModelSerializer):
    typ_bezeichnung = serializers.CharField(source='typ.bezeichnung', read_only=True)
    objekt_bezeichnung = serializers.CharField(source='objekt.bezeichnung', read_only=True, default=None)
    einheit_nr = serializers.CharField(source='einheit.einheit_nr', read_only=True, default=None)
    person_name = serializers.CharField(source='person.name', read_only=True, default=None)
    zugewiesen_an_name = serializers.SerializerMethodField()

    class Meta:
        model = Vorgang
        fields = [
            'id', 'nummer', 'typ', 'typ_bezeichnung', 'quelle',
            'objekt', 'objekt_bezeichnung', 'einheit', 'einheit_nr',
            'person', 'person_name', 'betreff', 'status', 'prioritaet',
            'zugewiesen_an', 'zugewiesen_an_name', 'faellig_am',
            'wiedervorlage_am', 'erstellt_am',
        ]
        read_only_fields = fields

    def get_zugewiesen_an_name(self, obj):
        return _user_name(obj.zugewiesen_an)


class VorgangDetailSerializer(serializers.ModelSerializer):
    typ_bezeichnung = serializers.CharField(source='typ.bezeichnung', read_only=True)
    objekt_bezeichnung = serializers.CharField(source='objekt.bezeichnung', read_only=True, default=None)
    einheit_nr = serializers.CharField(source='einheit.einheit_nr', read_only=True, default=None)
    person_name = serializers.CharField(source='person.name', read_only=True, default=None)
    zugewiesen_an_name = serializers.SerializerMethodField()
    erstellt_von_name = serializers.SerializerMethodField()
    geschlossen_von_name = serializers.SerializerMethodField()
    ereignisse = VorgangEreignisSerializer(many=True, read_only=True)
    dokumente = VorgangDokumentSerializer(many=True, read_only=True)
    antwort_vorschlag = serializers.SerializerMethodField()

    class Meta:
        model = Vorgang
        fields = [
            'id', 'nummer', 'typ', 'typ_bezeichnung', 'quelle',
            'objekt', 'objekt_bezeichnung', 'einheit', 'einheit_nr',
            'person', 'person_name', 'betreff', 'beschreibung',
            'status', 'prioritaet', 'zugewiesen_an', 'zugewiesen_an_name',
            'faellig_am', 'wiedervorlage_am', 'mail_referenz',
            'telefon_rufnummer', 'portal_sichtbar',
            'erstellt_am', 'erstellt_von', 'erstellt_von_name',
            'geschlossen_am', 'geschlossen_von', 'geschlossen_von_name',
            'ereignisse', 'dokumente', 'antwort_vorschlag',
        ]
        read_only_fields = fields

    def get_zugewiesen_an_name(self, obj):
        return _user_name(obj.zugewiesen_an)

    def get_erstellt_von_name(self, obj):
        return _user_name(obj.erstellt_von)

    def get_geschlossen_von_name(self, obj):
        return _user_name(obj.geschlossen_von)

    def get_antwort_vorschlag(self, obj):
        """Liefert den neuesten Vorschlag im Status 'entwurf' oder
        'fehlgeschlagen' (der aktuell für den Mitarbeiter relevante Stand) —
        oder ``None``, wenn keiner existiert (z.B. nach Freigabe/Verwerfen,
        ohne dass neu generiert wurde)."""
        vorschlag = obj.antwort_vorschlaege.filter(
            status__in=['entwurf', 'fehlgeschlagen'],
        ).order_by('-erzeugt_am').first()
        if vorschlag is None:
            return None
        return VorgangAntwortVorschlagSerializer(vorschlag).data


class VorgangCreateSerializer(serializers.Serializer):
    """Eingabe-Validierung für ``POST /vorgaenge/`` — die eigentliche Anlage
    läuft über ``vorgang_service.erstelle_vorgang``. ``quelle`` ist bewusst
    NICHT Teil dieses Serializers: sie wird in der View immer auf
    ``'manuell'`` gesetzt (Client kann sie nicht beeinflussen).
    """
    typ = serializers.PrimaryKeyRelatedField(queryset=VorgangTyp.objects.all())
    objekt = serializers.PrimaryKeyRelatedField(queryset=Objekt.objects.all(), required=False, allow_null=True)
    einheit = serializers.PrimaryKeyRelatedField(queryset=Einheit.objects.all(), required=False, allow_null=True)
    person = serializers.PrimaryKeyRelatedField(queryset=Person.objects.all(), required=False, allow_null=True)
    betreff = serializers.CharField(max_length=200)
    beschreibung = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    prioritaet = serializers.ChoiceField(choices=PRIORITAET_CHOICES, required=False)
    faellig_am = serializers.DateField(required=False, allow_null=True)
    zugewiesen_an = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), required=False, allow_null=True,
    )
    mail_referenz = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    telefon_rufnummer = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=30)
    portal_sichtbar = serializers.BooleanField(required=False)
