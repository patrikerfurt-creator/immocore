from rest_framework import serializers
from .models import Objekt, Eingang, Bankkonto, Einheit, Verteilerschluessel, VerteilerschluesselWert


class EingangSerializer(serializers.ModelSerializer):
    class Meta:
        model = Eingang
        fields = '__all__'
        read_only_fields = ['id']


class BankkontoSerializer(serializers.ModelSerializer):
    iban = serializers.CharField(required=False, allow_blank=True, default='')

    class Meta:
        model = Bankkonto
        fields = '__all__'
        read_only_fields = ['id']


class EinheitSerializer(serializers.ModelSerializer):
    eingang_bezeichnung = serializers.CharField(source='eingang.strasse', read_only=True, allow_null=True, default=None)

    class Meta:
        model = Einheit
        fields = '__all__'
        read_only_fields = ['id']


class ObjektSerializer(serializers.ModelSerializer):
    eingaenge = EingangSerializer(many=True, read_only=True)
    bankkonten = BankkontoSerializer(many=True, read_only=True)
    einheiten = EinheitSerializer(many=True, read_only=True)
    zahlungsfreigabe_grenzen = serializers.JSONField(default=dict)

    class Meta:
        model = Objekt
        fields = '__all__'
        read_only_fields = ['id', 'objektnummer']


class VerteilerschluesselWertSerializer(serializers.ModelSerializer):
    einheit_nr = serializers.CharField(source='einheit.einheit_nr', read_only=True)

    class Meta:
        model = VerteilerschluesselWert
        fields = '__all__'
        read_only_fields = ['id']


class VerteilerschluesselSerializer(serializers.ModelSerializer):
    werte = VerteilerschluesselWertSerializer(many=True, read_only=True)
    summe = serializers.SerializerMethodField()

    class Meta:
        model = Verteilerschluessel
        fields = '__all__'
        read_only_fields = ['id']

    def get_summe(self, obj):
        from django.db.models import Sum
        result = obj.werte.filter(beteiligt=True).aggregate(s=Sum('wert'))['s']
        return result


class ObjektListEingangSerializer(serializers.ModelSerializer):
    class Meta:
        model = Eingang
        fields = ['id', 'bezeichnung', 'strasse', 'plz', 'ort']


class ObjektListSerializer(serializers.ModelSerializer):
    """Kompakte Darstellung für Listen."""
    eingaenge = ObjektListEingangSerializer(many=True, read_only=True)

    class Meta:
        model = Objekt
        fields = ['id', 'objektnummer', 'bezeichnung', 'kurzbezeichnung', 'objekt_typ', 'strasse', 'plz', 'ort', 'status', 'eingaenge']
