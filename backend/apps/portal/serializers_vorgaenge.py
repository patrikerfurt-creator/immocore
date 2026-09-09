"""
Eigene, schlanke Serializer für die Portal-Vorgangs-Endpunkte (Spec
Portal-Erweiterung v1.1, Kap. 4/5).

Bewusst KEINE Wiederverwendung der internen Serializer aus
``apps.vorgaenge.serializers`` — die internen Serializer enthalten interne
Felder (``zugewiesen_an``, ``mail_referenz``, ``status_anzeige`` uvm.) und
folgen einem anderen Response-Contract. Zwei getrennte Serializer-Sätze
verhindern, dass eine spätere Änderung am internen Serializer versehentlich
ein internes Feld ins Portal durchreicht.
"""
from rest_framework import serializers

from apps.vorgaenge.models import Vorgang, VorgangEreignis, VorgangTyp


class PortalVorgangTypSerializer(serializers.ModelSerializer):
    """``GET /api/v1/portal/vorgang-typen/`` — nur, was das Formular braucht."""

    class Meta:
        model = VorgangTyp
        fields = ['id', 'bezeichnung']
        read_only_fields = fields


class PortalVorgangEreignisSerializer(serializers.ModelSerializer):
    """Nur die für den Eigentümer freigegebenen Ereignis-Felder — die
    Filterung auf ``intern=False`` erfolgt in der View/im Queryset, nicht hier."""

    typ_anzeige = serializers.CharField(source='get_typ_display', read_only=True)

    class Meta:
        model = VorgangEreignis
        fields = ['typ', 'typ_anzeige', 'text', 'erstellt_am']
        read_only_fields = fields


class PortalVorgangListSerializer(serializers.ModelSerializer):
    """``GET /api/v1/portal/vorgaenge/`` — reine Liste, siehe Response-Contract
    (Kap. 4.1). ``status`` bleibt der interne Code, das Portal-Label mappt
    das Frontend bewusst selbst (kein ``status_anzeige`` hier)."""

    typ = serializers.CharField(source='typ.bezeichnung', read_only=True)
    # ``objekt_id`` mitliefern, obwohl das Portal die WEG nur mit Namen
    # anzeigt: das Frontend muss WEG-weite Vorgänge (einheit_id=None) der
    # ausgewählten WEG zuordnen. Über die Bezeichnung wäre das ein
    # String-Vergleich, der bei zwei gleich benannten WEGs falsch zuordnet.
    objekt_id = serializers.CharField(source='objekt.id', read_only=True, default=None)
    objekt_bezeichnung = serializers.CharField(source='objekt.bezeichnung', read_only=True, default=None)
    einheit_id = serializers.CharField(source='einheit.id', read_only=True, default=None)
    einheit_nr = serializers.CharField(source='einheit.einheit_nr', read_only=True, default=None)

    class Meta:
        model = Vorgang
        fields = [
            'id', 'nummer', 'typ', 'betreff', 'status', 'erstellt_am',
            'faellig_am', 'objekt_id', 'objekt_bezeichnung',
            'einheit_id', 'einheit_nr',
        ]
        read_only_fields = fields


class PortalVorgangDetailSerializer(PortalVorgangListSerializer):
    """``GET /api/v1/portal/vorgaenge/<id>/`` — Listenfelder plus Beschreibung
    und die für den Eigentümer freigegebenen Ereignisse."""

    beschreibung = serializers.CharField(read_only=True)
    ereignisse = serializers.SerializerMethodField()

    class Meta(PortalVorgangListSerializer.Meta):
        fields = PortalVorgangListSerializer.Meta.fields + ['beschreibung', 'ereignisse']
        read_only_fields = fields

    def get_ereignisse(self, obj):
        ereignisse = obj.ereignisse.filter(intern=False).order_by('erstellt_am')
        return PortalVorgangEreignisSerializer(ereignisse, many=True).data


class PortalVorgangCreateSerializer(serializers.Serializer):
    """Eingabe-Validierung für ``POST /portal/vorgaenge/`` — reine Formprüfung
    (Pflichtfelder, UUID-Format). Die fachlichen Regeln (Typ aktiv/portal_-
    erstellbar, Einheit gehört zu einer aktiven EV der anfragenden Person)
    prüft die View zusammen mit ``vorgang_service``, nicht dieser Serializer.
    Die eigentliche Anlage läuft über ``vorgang_service.erstelle_vorgang``.
    """
    typ_id = serializers.UUIDField()
    betreff = serializers.CharField(max_length=200)
    beschreibung = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    einheit_id = serializers.UUIDField()
