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
    werte = serializers.SerializerMethodField()
    summe = serializers.SerializerMethodField()

    # Verbrauchs-VS: Werte liegen in EinheitVerbrauch, nicht in VerteilerschluesselWert
    VERBRAUCH_CODES = ('140', '141', '142', '143', '144', '145')

    class Meta:
        model = Verteilerschluessel
        fields = '__all__'
        read_only_fields = ['id']

    def _wj(self):
        return self.context.get('wirtschaftsjahr', 0)

    def _verbrauch_wj(self, obj):
        from .models import Wirtschaftsjahr
        jahr = self._wj()
        return Wirtschaftsjahr.objects.filter(objekt=obj.objekt, jahr=jahr).first() if jahr else None

    def get_werte(self, obj):
        if obj.schluessel in self.VERBRAUCH_CODES:
            from .models import EinheitVerbrauch
            wj = self._verbrauch_wj(obj)
            if wj is None:
                return []
            rows = (
                EinheitVerbrauch.objects
                .filter(wirtschaftsjahr=wj, einheit__objekt=obj.objekt, vs_code=obj.schluessel)
                .select_related('einheit').order_by('einheit__einheit_nr')
            )
            return [{
                'id': str(r.id),
                'einheit': str(r.einheit_id),
                'einheit_nr': r.einheit.einheit_nr,
                'wert': str(r.wert) if r.wert is not None else None,
                'beteiligt': True,
                'wirtschaftsjahr': self._wj(),
                'quelle': r.quelle,
            } for r in rows]
        werte = obj.werte.filter(wirtschaftsjahr=self._wj())
        return VerteilerschluesselWertSerializer(werte, many=True).data

    def get_summe(self, obj):
        from django.db.models import Sum
        if obj.schluessel in self.VERBRAUCH_CODES:
            from .models import EinheitVerbrauch
            wj = self._verbrauch_wj(obj)
            if wj is None:
                return None
            return (
                EinheitVerbrauch.objects
                .filter(wirtschaftsjahr=wj, einheit__objekt=obj.objekt, vs_code=obj.schluessel)
                .aggregate(s=Sum('wert'))['s']
            )
        return obj.werte.filter(beteiligt=True, wirtschaftsjahr=self._wj()).aggregate(s=Sum('wert'))['s']


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
