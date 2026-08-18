"""
Serializer für die Handwerker-API (Phase C: interne Endpunkte).

Reine Ein-/Ausgabe-Übersetzung — jede Mutation läuft über ``auftrag_service``;
Serializer enthalten bewusst KEINE Business-Logik (Architekturprinzip,
analog ``apps.vorgaenge.serializers``).

SICHERHEITSKRITISCH: ``AuftragsbestaetigungsToken.accept_token`` und
``reject_token`` dürfen NIEMALS über einen Serializer nach außen gelangen.
Deshalb ausschließlich explizite Feldlisten (nie ``fields = '__all__'``),
und der Token-Status wird über ``get_token_status()`` manuell auf genau
``gueltig_bis``/``verbraucht_am`` reduziert — das Token-Modell selbst wird
nirgends direkt serialisiert.
"""
from rest_framework import serializers

from apps.objekte.models import Objekt
from apps.rechnungen.models import Kreditor, Rechnung
from apps.vorgaenge.models import PRIORITAET_CHOICES

from .models import Gewerk, Handwerkerauftrag, HandwerkerauftragEreignis, ObjektHandwerker


def _user_name(user) -> str | None:
    if user is None:
        return None
    voller_name = user.get_full_name()
    return voller_name or user.get_username()


class GewerkSerializer(serializers.ModelSerializer):
    class Meta:
        model = Gewerk
        fields = ['id', 'code', 'bezeichnung', 'aktiv', 'sortierung', 'erstellt_am', 'erstellt_von']
        read_only_fields = ['id', 'erstellt_am']


class ObjektHandwerkerSerializer(serializers.ModelSerializer):
    kreditor_name = serializers.CharField(source='kreditor.name', read_only=True)
    gewerke_bezeichnung = serializers.SerializerMethodField()

    class Meta:
        model = ObjektHandwerker
        fields = [
            'id', 'objekt', 'kreditor', 'kreditor_name', 'gewerke_bezeichnung',
            'prioritaet', 'notiz', 'erstellt_am',
        ]
        read_only_fields = ['id', 'erstellt_am']

    def get_gewerke_bezeichnung(self, obj):
        bezeichnungen = [g.bezeichnung for g in obj.kreditor.gewerke.all()]
        return ', '.join(bezeichnungen) if bezeichnungen else None


class HandwerkerauftragEreignisSerializer(serializers.ModelSerializer):
    erstellt_von_name = serializers.SerializerMethodField()

    class Meta:
        model = HandwerkerauftragEreignis
        fields = [
            'id', 'typ', 'text', 'alter_wert', 'neuer_wert',
            'erstellt_am', 'erstellt_von', 'erstellt_von_name',
        ]
        read_only_fields = fields

    def get_erstellt_von_name(self, obj):
        return _user_name(obj.erstellt_von)


class HandwerkerauftragRechnungSerializer(serializers.ModelSerializer):
    """Zugeordnete Rechnungen im Detail-Serializer — bewusst nur die drei
    für die Übersicht relevanten Felder (Nummer, Datum, Betrag)."""

    class Meta:
        model = Rechnung
        fields = ['id', 'rechnungsnummer', 'rechnungsdatum', 'betrag_brutto']
        read_only_fields = fields


class HandwerkerauftragListSerializer(serializers.ModelSerializer):
    """Dashboard-Liste — ``GET /api/v1/handwerkerauftraege/``."""

    objekt_bezeichnung = serializers.CharField(source='objekt.bezeichnung', read_only=True)
    kreditor_name = serializers.CharField(source='kreditor.name', read_only=True)
    kreditor_gewerke_bezeichnung = serializers.SerializerMethodField()
    rechnungen_anzahl = serializers.SerializerMethodField()

    class Meta:
        model = Handwerkerauftrag
        fields = [
            'id', 'nummer', 'titel', 'status', 'prioritaet', 'geschaetzte_kosten',
            'objekt', 'objekt_bezeichnung',
            'kreditor', 'kreditor_name', 'kreditor_gewerke_bezeichnung',
            'erstellt_am', 'versendet_am', 'angenommen_am', 'abgelehnt_am', 'abgeschlossen_am',
            'rechnungen_anzahl',
        ]
        read_only_fields = fields

    def get_rechnungen_anzahl(self, obj):
        return obj.rechnungen.count()

    def get_kreditor_gewerke_bezeichnung(self, obj):
        bezeichnungen = [g.bezeichnung for g in obj.kreditor.gewerke.all()]
        return ', '.join(bezeichnungen) if bezeichnungen else None


class HandwerkerauftragDetailSerializer(serializers.ModelSerializer):
    """Detailansicht — ``GET /api/v1/handwerkerauftraege/{id}/``.

    ``vorgang`` und ``token_status`` sind bewusst als ``SerializerMethodField``
    deklariert (überschreiben damit die von ``ModelSerializer`` sonst
    automatisch erzeugten Felder) — ``vorgang`` liefert eine kompakte
    Klarnamen-Repräsentation statt der reinen PK, ``token_status`` reduziert
    das Token-Modell auf die zwei unkritischen Felder (siehe Modul-Docstring).
    """

    objekt_bezeichnung = serializers.CharField(source='objekt.bezeichnung', read_only=True)
    kreditor_name = serializers.CharField(source='kreditor.name', read_only=True)
    kreditor_gewerke_bezeichnung = serializers.SerializerMethodField()
    vorgang = serializers.SerializerMethodField()
    erstellt_von_name = serializers.SerializerMethodField()
    ereignisse = HandwerkerauftragEreignisSerializer(many=True, read_only=True)
    rechnungen = HandwerkerauftragRechnungSerializer(many=True, read_only=True)
    token_status = serializers.SerializerMethodField()

    class Meta:
        model = Handwerkerauftrag
        fields = [
            'id', 'nummer', 'titel', 'beschreibung', 'status', 'prioritaet',
            'gewuenscht_ab', 'geschaetzte_kosten',
            'objekt', 'objekt_bezeichnung',
            'kreditor', 'kreditor_name', 'kreditor_gewerke_bezeichnung',
            'vorgang', 'ablehnung_grund', 'abschluss_notiz',
            'erstellt_am', 'erstellt_von', 'erstellt_von_name',
            'versendet_am', 'angenommen_am', 'abgelehnt_am', 'abgeschlossen_am',
            'geaendert_am',
            'ereignisse', 'rechnungen', 'token_status',
        ]
        read_only_fields = fields

    def get_vorgang(self, obj):
        if not obj.vorgang_id:
            return None
        return {'id': obj.vorgang_id, 'nummer': obj.vorgang.nummer, 'betreff': obj.vorgang.betreff}

    def get_erstellt_von_name(self, obj):
        return _user_name(obj.erstellt_von)

    def get_kreditor_gewerke_bezeichnung(self, obj):
        bezeichnungen = [g.bezeichnung for g in obj.kreditor.gewerke.all()]
        return ', '.join(bezeichnungen) if bezeichnungen else None

    def get_token_status(self, obj):
        token = getattr(obj, 'token', None)
        if token is None:
            return None
        return {'gueltig_bis': token.gueltig_bis, 'verbraucht_am': token.verbraucht_am}


class HandwerkerauftragCreateSerializer(serializers.Serializer):
    """Eingabe-Validierung für die Anlage eines ``Handwerkerauftrag`` — sowohl
    aus einem Vorgang heraus (``POST /vorgaenge/{id}/handwerkerauftrag/``, dort
    setzt die View ``vorgang`` serverseitig) als auch eigenständig
    (``POST /handwerkerauftraege/``, dort ist ``objekt`` de facto Pflicht —
    das prüft ``auftrag_service.erstelle_auftrag`` und liefert bei fehlendem
    Objektbezug eine sprechende ``ValidationError``, die die View zu 400
    übersetzt).

    ``status``, ``nummer``, ``versendet_am`` etc. sind bewusst NICHT Teil
    dieses Serializers — nicht vom Client setzbar.
    """
    kreditor = serializers.PrimaryKeyRelatedField(queryset=Kreditor.objects.all())
    objekt = serializers.PrimaryKeyRelatedField(queryset=Objekt.objects.all(), required=False, allow_null=True)
    titel = serializers.CharField(max_length=255)
    beschreibung = serializers.CharField(required=False, allow_blank=True)
    gewuenscht_ab = serializers.DateField(required=False, allow_null=True)
    prioritaet = serializers.ChoiceField(choices=PRIORITAET_CHOICES, required=False)
    geschaetzte_kosten = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True,
    )
