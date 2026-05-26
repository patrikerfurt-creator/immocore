"""
WKZ — Serializers für Wiederkehrende Buchungen.
"""
from rest_framework import serializers
from .models import WiederkehrendeBuchungVorlage, WiederkehrendeBuchungOP, WiederkehrendeBuchungSplit


class WKZSplitSerializer(serializers.ModelSerializer):
    class Meta:
        model = WiederkehrendeBuchungSplit
        fields = ['id', 'kontonummer', 'bezeichnung', 'betrag', 'reihenfolge']


class WKZSplitCreateSerializer(serializers.Serializer):
    kontonummer = serializers.CharField(max_length=8)
    bezeichnung = serializers.CharField(max_length=200)
    betrag = serializers.DecimalField(max_digits=14, decimal_places=2)
    reihenfolge = serializers.IntegerField(required=False, default=0)


class WKZVorlageSerializer(serializers.ModelSerializer):
    kreditor_name = serializers.CharField(source='kreditor.name', read_only=True)
    objekt_bezeichnung = serializers.CharField(source='objekt.bezeichnung', read_only=True)
    jahresbetrag = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )
    perioden_pro_jahr = serializers.IntegerField(read_only=True)

    class Meta:
        model = WiederkehrendeBuchungVorlage
        fields = [
            'id', 'objekt', 'objekt_bezeichnung',
            'kreditor', 'kreditor_name',
            'bezeichnung', 'typ', 'status',
            'betrag_gesamt', 'rhythmus',
            'erste_faelligkeit', 'gueltig_ab', 'gueltig_bis',
            'jahresbetrag', 'perioden_pro_jahr',
            'bescheid_pflicht',
            'rechnung_id',
            'freigegeben_am', 'erstellt_am',
        ]


class WKZVorlageDetailSerializer(serializers.ModelSerializer):
    kreditor_name = serializers.CharField(source='kreditor.name', read_only=True)
    objekt_bezeichnung = serializers.CharField(source='objekt.bezeichnung', read_only=True)
    jahresbetrag = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )
    perioden_pro_jahr = serializers.IntegerField(read_only=True)
    splits = WKZSplitSerializer(many=True, read_only=True)
    erstellt_von_name = serializers.CharField(
        source='erstellt_von.get_full_name', read_only=True
    )
    freigegeben_von_name = serializers.CharField(
        source='freigegeben_von.get_full_name', read_only=True
    )
    ersetzt_vorlage_id = serializers.UUIDField(source='ersetzt_vorlage.id', read_only=True)

    class Meta:
        model = WiederkehrendeBuchungVorlage
        fields = [
            'id', 'objekt', 'objekt_bezeichnung',
            'kreditor', 'kreditor_name',
            'bezeichnung', 'typ', 'status',
            'betrag_gesamt', 'rhythmus',
            'erste_faelligkeit', 'bei_wochenende', 'vorlauf_tage',
            'toleranz_betrag', 'toleranz_tage',
            'sepa_mandat_id', 'bescheid_pflicht',
            'gueltig_ab', 'gueltig_bis',
            'jahresbetrag', 'perioden_pro_jahr',
            'freigegeben_am', 'freigegeben_von_name', 'freigabe_jahresbetrag',
            'ersetzt_vorlage_id',
            'erstellt_von_name', 'erstellt_am', 'geaendert_am',
            'rechnung_id',
            'splits',
        ]


class WKZVorlageCreateSerializer(serializers.Serializer):
    objekt = serializers.UUIDField()
    kreditor = serializers.UUIDField()
    bezeichnung = serializers.CharField(max_length=200)
    typ = serializers.ChoiceField(choices=['bescheid', 'vertrag'])
    betrag_gesamt = serializers.DecimalField(max_digits=14, decimal_places=2)
    rhythmus = serializers.ChoiceField(choices=[
        'monatlich', 'zweimonatlich', 'quartalsweise',
        'halbjaehrlich', 'jaehrlich', 'frei',
    ])
    erste_faelligkeit = serializers.DateField()
    bei_wochenende = serializers.ChoiceField(
        choices=['vor', 'zurueck', 'unveraendert'], default='zurueck'
    )
    vorlauf_tage = serializers.IntegerField(default=7)
    toleranz_betrag = serializers.DecimalField(
        max_digits=14, decimal_places=2, default='5.00'
    )
    toleranz_tage = serializers.IntegerField(default=14)
    sepa_mandat_id = serializers.CharField(max_length=35, allow_blank=True, default='')
    bescheid_pflicht = serializers.BooleanField(required=False)
    gueltig_ab = serializers.DateField()
    gueltig_bis = serializers.DateField(required=False, allow_null=True)
    rechnung_id = serializers.UUIDField(required=False, allow_null=True)
    splits = WKZSplitCreateSerializer(many=True)

    def validate(self, data):
        if data.get('gueltig_bis') and data['gueltig_bis'] < data['gueltig_ab']:
            raise serializers.ValidationError(
                'gueltig_bis muss nach oder gleich gueltig_ab liegen.'
            )
        if not data.get('splits'):
            raise serializers.ValidationError('Mindestens ein Split ist erforderlich.')
        return data


class WKZOPSerializer(serializers.ModelSerializer):
    vorlage_bezeichnung = serializers.CharField(source='vorlage.bezeichnung', read_only=True)
    kreditor_name = serializers.CharField(source='vorlage.kreditor.name', read_only=True)
    op_nummer = serializers.IntegerField(source='kreditor_op.op_nummer', read_only=True)
    erwarteter_betrag = serializers.DecimalField(
        source='kreditor_op.betrag_ursprung', max_digits=14, decimal_places=2, read_only=True
    )

    class Meta:
        model = WiederkehrendeBuchungOP
        fields = [
            'id', 'vorlage', 'vorlage_bezeichnung',
            'kreditor_name', 'op_nummer',
            'periode_von', 'periode_bis', 'faellig_am',
            'status', 'erwarteter_betrag',
            'abweichung_betrag', 'erzeugt_am',
        ]


class WKZOPDetailSerializer(serializers.ModelSerializer):
    vorlage_bezeichnung = serializers.CharField(source='vorlage.bezeichnung', read_only=True)
    kreditor_name = serializers.CharField(source='vorlage.kreditor.name', read_only=True)
    objekt_bezeichnung = serializers.CharField(source='vorlage.objekt.bezeichnung', read_only=True)
    op_nummer = serializers.IntegerField(source='kreditor_op.op_nummer', read_only=True)
    erwarteter_betrag = serializers.DecimalField(
        source='kreditor_op.betrag_ursprung', max_digits=14, decimal_places=2, read_only=True
    )
    splits = WKZSplitSerializer(source='vorlage.splits', many=True, read_only=True)
    bank_match_buchung_id = serializers.UUIDField(
        source='bank_match_buchung.id', read_only=True
    )

    class Meta:
        model = WiederkehrendeBuchungOP
        fields = [
            'id', 'vorlage', 'vorlage_bezeichnung',
            'objekt_bezeichnung', 'kreditor_name', 'op_nummer',
            'periode_von', 'periode_bis', 'faellig_am',
            'status', 'erwarteter_betrag',
            'abweichung_betrag', 'klaerungs_grund',
            'bank_match_buchung_id',
            'erzeugt_am', 'splits',
        ]


class WKZForecastSerializer(serializers.Serializer):
    faellig_am = serializers.DateField()
    periode_von = serializers.DateField()
    periode_bis = serializers.DateField()
    kreditor = serializers.CharField()
    bezeichnung = serializers.CharField()
    betrag = serializers.DecimalField(max_digits=14, decimal_places=2)
    vorlage_id = serializers.UUIDField()
