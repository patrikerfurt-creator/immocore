from rest_framework import serializers
from .models import Wirtschaftsplan, WirtschaftsplanPosition, WirtschaftsplanAnteil


class WirtschaftsplanAnteilSerializer(serializers.ModelSerializer):
    einheit_nr = serializers.CharField(source='einheit.einheit_nr', read_only=True)
    einheit_lage = serializers.CharField(source='einheit.lage', read_only=True)

    class Meta:
        model = WirtschaftsplanAnteil
        fields = [
            'id', 'einheit', 'einheit_nr', 'einheit_lage',
            'vs_anteil_einheit', 'vs_anteil_gesamt',
            'betrag_anteil', 'monatsbetrag_anteil',
        ]


class WirtschaftsplanPositionSerializer(serializers.ModelSerializer):
    konto_nr = serializers.CharField(source='konto.kontonummer', read_only=True)
    konto_name = serializers.CharField(source='konto.kontoname', read_only=True)
    konto_kontoart = serializers.CharField(source='konto.kontoart', read_only=True)
    anteile = WirtschaftsplanAnteilSerializer(many=True, read_only=True)
    summe_anteile = serializers.SerializerMethodField()
    differenz = serializers.SerializerMethodField()

    class Meta:
        model = WirtschaftsplanPosition
        fields = [
            'id', 'konto', 'konto_nr', 'konto_name', 'konto_kontoart',
            'vs_code', 'betrag', 'verteilung_validiert',
            'verteilung_freigegeben_trotz_diff', 'bemerkung',
            'anteile', 'summe_anteile', 'differenz',
        ]

    def get_summe_anteile(self, obj):
        return sum(a.betrag_anteil for a in obj.anteile.all())

    def get_differenz(self, obj):
        s = self.get_summe_anteile(obj)
        return float(obj.betrag) - float(s)


class WirtschaftsplanListSerializer(serializers.ModelSerializer):
    wirtschaftsjahr_jahr = serializers.IntegerField(source='wirtschaftsjahr.jahr', read_only=True)
    objekt_id = serializers.UUIDField(source='wirtschaftsjahr.objekt_id', read_only=True)
    objekt_bezeichnung = serializers.CharField(source='wirtschaftsjahr.objekt.bezeichnung', read_only=True)
    erstellt_von_name = serializers.CharField(source='erstellt_von.get_full_name', read_only=True)

    class Meta:
        model = Wirtschaftsplan
        fields = [
            'id', 'wirtschaftsjahr', 'wirtschaftsjahr_jahr',
            'objekt_id', 'objekt_bezeichnung',
            'status', 'gesamtsumme', 'gesamtsumme_hausgeld', 'gesamtsumme_ruecklage',
            'beschluss_datum', 'beschluss_tagesordnungspunkt', 'wirkung_ab',
            'bemerkung', 'aufhebt_wp',
            'erstellt_am', 'erstellt_von', 'erstellt_von_name',
            'beschlossen_am',
        ]


class WirtschaftsplanDetailSerializer(WirtschaftsplanListSerializer):
    positionen = WirtschaftsplanPositionSerializer(many=True, read_only=True)

    class Meta(WirtschaftsplanListSerializer.Meta):
        fields = WirtschaftsplanListSerializer.Meta.fields + ['positionen']
