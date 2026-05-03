from rest_framework import serializers
from .models import Abrechnungsart, Konto, Personenkonto, Unterkonto


class AbrechnungsartSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Abrechnungsart
        fields = '__all__'
        read_only_fields = ['id']


class KontoSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Konto
        fields = '__all__'
        read_only_fields = ['id']


class UnterkontoSerializer(serializers.ModelSerializer):
    volle_kontonummer = serializers.CharField(read_only=True)

    class Meta:
        model  = Unterkonto
        fields = '__all__'
        read_only_fields = ['id']


class PersonenkontoSerializer(serializers.ModelSerializer):
    unterkonten     = UnterkontoSerializer(many=True, read_only=True)
    eigentuemer_name = serializers.CharField(source='eigentuemer.name', read_only=True)

    class Meta:
        model  = Personenkonto
        fields = '__all__'
        read_only_fields = ['id', 'kontonummer']
