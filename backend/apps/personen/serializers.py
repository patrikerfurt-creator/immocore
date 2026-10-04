from rest_framework import serializers
from .models import Person, SEPAMandat, EigentumsVerhaeltnis, HausgeldHistorie, Mietvertrag


class SEPAMandatSerializer(serializers.ModelSerializer):
    class Meta:
        model = SEPAMandat
        fields = '__all__'
        read_only_fields = ['id']


class PersonSerializer(serializers.ModelSerializer):
    name = serializers.CharField(read_only=True)
    zustellungsbevollmaechtigter_name = serializers.CharField(
        source='zustellungsbevollmaechtigter.name', read_only=True, default=None
    )

    class Meta:
        model = Person
        fields = '__all__'
        read_only_fields = ['id']

    def validate_zustellungsbevollmaechtigter(self, wert):
        if wert is None:
            return wert
        if self.instance is not None and wert.pk == self.instance.pk:
            raise serializers.ValidationError(
                'Eine Person kann nicht ihr eigener Zustellungsbevollmächtigter sein.'
            )
        if wert.person_typ != '500':
            raise serializers.ValidationError(
                'Der Zustellungsbevollmächtigte muss vom Typ '
                '"Zustellungsbevollmächtigter" (500) sein.'
            )
        return wert


class PersonListSerializer(serializers.ModelSerializer):
    name = serializers.CharField(read_only=True)
    hat_zustellbevollmaechtigten = serializers.SerializerMethodField()

    class Meta:
        model = Person
        fields = [
            'id', 'personennummer', 'name', 'person_typ', 'ist_firma',
            'email', 'telefon', 'hat_zustellbevollmaechtigten',
        ]

    def get_hat_zustellbevollmaechtigten(self, obj) -> bool:
        return obj.zustellungsbevollmaechtigter_id is not None


class HausgeldHistorieSerializer(serializers.ModelSerializer):
    erstellt_von = serializers.HiddenField(default=serializers.CurrentUserDefault())
    abrechnungsart_code = serializers.CharField(source='abrechnungsart.code', read_only=True)
    abrechnungsart_bezeichnung = serializers.CharField(
        source='abrechnungsart.bezeichnung', read_only=True
    )

    class Meta:
        model = HausgeldHistorie
        fields = [
            'id', 'eigentumsverhaeltnis', 'abrechnungsart', 'abrechnungsart_code',
            'abrechnungsart_bezeichnung', 'betrag', 'gueltig_ab', 'wirtschaftsplan_jahr',
            'quelle', 'bemerkung', 'erstellt_von', 'erstellt_am',
        ]
        read_only_fields = ['id', 'erstellt_am']


class EigentumsVerhaeltnisSerializer(serializers.ModelSerializer):
    hausgeld_soll = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    ist_aktiv = serializers.BooleanField(read_only=True)
    hausgeld_eintraege = HausgeldHistorieSerializer(many=True, read_only=True)
    person_name = serializers.CharField(source='person.name', read_only=True)
    einheit_nr = serializers.CharField(source='einheit.einheit_nr', read_only=True)
    personenkonto_id = serializers.SerializerMethodField()
    personenkonto_nr = serializers.SerializerMethodField()

    def get_personenkonto_id(self, obj):
        pk = getattr(obj, 'personenkonto', None)
        return str(pk.id) if pk else None

    def get_personenkonto_nr(self, obj):
        pk = getattr(obj, 'personenkonto', None)
        return pk.kontonummer if pk else None

    class Meta:
        model = EigentumsVerhaeltnis
        fields = '__all__'
        read_only_fields = ['id']


class MietvertragSerializer(serializers.ModelSerializer):
    class Meta:
        model = Mietvertrag
        fields = '__all__'
        read_only_fields = ['id']
