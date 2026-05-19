from decimal import Decimal
from rest_framework import serializers
from apps.abrechnung_wp.models import Wirtschaftsplan, WirtschaftsplanPosition, WirtschaftsplanAnteil
from apps.konten.models import Konto, KontoVerteilerSchluessel


class WirtschaftsplanAnteilSerializer(serializers.ModelSerializer):
    einheit_nr = serializers.CharField(source='einheit.einheit_nr', read_only=True)
    einheit_lage = serializers.CharField(source='einheit.lage', read_only=True)

    class Meta:
        model = WirtschaftsplanAnteil
        fields = ['id', 'einheit', 'einheit_nr', 'einheit_lage',
                  'vs_anteil_einheit', 'vs_anteil_gesamt',
                  'betrag_anteil', 'monatsbetrag_anteil']
        read_only_fields = fields


class WirtschaftsplanPositionSerializer(serializers.ModelSerializer):
    kontonummer = serializers.CharField(source='konto.kontonummer', read_only=True)
    kontoname = serializers.CharField(source='konto.kontoname', read_only=True)
    abrechnungsart = serializers.CharField(source='konto.abrechnungsart', read_only=True)
    anteile = WirtschaftsplanAnteilSerializer(many=True, read_only=True)
    anteile_summe = serializers.SerializerMethodField()
    differenz = serializers.SerializerMethodField()

    class Meta:
        model = WirtschaftsplanPosition
        fields = ['id', 'wirtschaftsplan', 'konto', 'kontonummer', 'kontoname',
                  'abrechnungsart', 'vs_code', 'betrag',
                  'verteilung_validiert', 'verteilung_freigegeben_trotz_diff',
                  'bemerkung', 'anteile', 'anteile_summe', 'differenz']
        read_only_fields = ['id', 'kontonummer', 'kontoname', 'abrechnungsart',
                            'anteile', 'anteile_summe', 'differenz']

    def get_anteile_summe(self, obj):
        return str(sum(a.betrag_anteil for a in obj.anteile.all()))

    def get_differenz(self, obj):
        summe = sum(a.betrag_anteil for a in obj.anteile.all())
        return str(obj.betrag - summe)

    def validate_konto(self, konto):
        # Whitelist: 50000–55999 oder 57xxx
        nr = konto.kontonummer
        if not (
            ('50000' <= nr <= '55999') or nr.startswith('579') or nr.startswith('57')
        ):
            raise serializers.ValidationError(
                f"Konto {nr} liegt nicht im erlaubten Bereich 50000–55999 oder 57xxx."
            )
        # VS-Zuordnung prüfen
        if not KontoVerteilerSchluessel.objects.filter(konto=konto).exists():
            raise serializers.ValidationError(
                f"Konto {nr} hat keinen aktiven Verteilerschlüssel."
            )
        return konto


class WirtschaftsplanSerializer(serializers.ModelSerializer):
    positionen = WirtschaftsplanPositionSerializer(many=True, read_only=True)
    wj_jahr = serializers.IntegerField(source='wirtschaftsjahr.jahr', read_only=True)
    objekt_id = serializers.UUIDField(source='wirtschaftsjahr.objekt.id', read_only=True)
    objekt_bezeichnung = serializers.CharField(source='wirtschaftsjahr.objekt.bezeichnung', read_only=True)
    erstellt_von_name = serializers.CharField(source='erstellt_von.get_full_name', read_only=True)

    class Meta:
        model = Wirtschaftsplan
        fields = [
            'id', 'wirtschaftsjahr', 'wj_jahr', 'objekt_id', 'objekt_bezeichnung',
            'status', 'gesamtsumme', 'gesamtsumme_hausgeld', 'gesamtsumme_ruecklage',
            'beschluss_datum', 'beschluss_tagesordnungspunkt', 'wirkung_ab',
            'bemerkung', 'aufhebt_wp', 'erstellt_am', 'erstellt_von', 'erstellt_von_name',
            'beschlossen_am', 'beschlossen_von', 'positionen',
        ]
        read_only_fields = ['id', 'status', 'gesamtsumme', 'gesamtsumme_hausgeld',
                            'gesamtsumme_ruecklage', 'erstellt_am', 'erstellt_von',
                            'beschlossen_am', 'beschlossen_von', 'positionen']


class WirtschaftsplanListSerializer(serializers.ModelSerializer):
    wj_jahr = serializers.IntegerField(source='wirtschaftsjahr.jahr', read_only=True)
    objekt_id = serializers.UUIDField(source='wirtschaftsjahr.objekt.id', read_only=True)
    objekt_bezeichnung = serializers.CharField(source='wirtschaftsjahr.objekt.bezeichnung', read_only=True)
    anzahl_positionen = serializers.SerializerMethodField()

    class Meta:
        model = Wirtschaftsplan
        fields = ['id', 'wirtschaftsjahr', 'wj_jahr', 'objekt_id', 'objekt_bezeichnung',
                  'status', 'gesamtsumme', 'gesamtsumme_hausgeld', 'wirkung_ab',
                  'beschluss_datum', 'erstellt_am', 'anzahl_positionen']

    def get_anzahl_positionen(self, obj):
        return obj.positionen.count()
