from rest_framework import serializers
from .models import Person, SEPAMandat, EigentumsVerhaeltnis, HausgeldHistorie, Mietvertrag


class SEPAMandatSerializer(serializers.ModelSerializer):
    class Meta:
        model = SEPAMandat
        fields = '__all__'
        read_only_fields = ['id']


class PersonSerializer(serializers.ModelSerializer):
    name = serializers.CharField(read_only=True)

    class Meta:
        model = Person
        fields = '__all__'
        read_only_fields = ['id']


class PersonListSerializer(serializers.ModelSerializer):
    name = serializers.CharField(read_only=True)

    class Meta:
        model = Person
        fields = ['id', 'personennummer', 'name', 'person_typ', 'ist_firma', 'email', 'telefon']


class HausgeldHistorieSerializer(serializers.ModelSerializer):
    erstellt_von = serializers.HiddenField(default=serializers.CurrentUserDefault())
    abrechnungsart_code = serializers.CharField(source='abrechnungsart.code', read_only=True)
    abrechnungsart_bezeichnung = serializers.CharField(
        source='abrechnungsart.bezeichnung', read_only=True
    )
    beschluss_datum = serializers.SerializerMethodField()

    def get_beschluss_datum(self, obj):
        if obj.beschluss:
            return str(obj.beschluss.beschluss_datum)
        return None

    class Meta:
        model = HausgeldHistorie
        fields = [
            'id', 'eigentumsverhaeltnis', 'abrechnungsart', 'abrechnungsart_code',
            'abrechnungsart_bezeichnung', 'betrag', 'gueltig_ab', 'wirtschaftsplan_jahr',
            'quelle', 'bemerkung', 'erstellt_von', 'erstellt_am', 'beschluss_datum',
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

    class Meta:
        model = EigentumsVerhaeltnis
        fields = '__all__'
        read_only_fields = ['id']


class MietvertragSerializer(serializers.ModelSerializer):
    class Meta:
        model = Mietvertrag
        fields = '__all__'
        read_only_fields = ['id']
