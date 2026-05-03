from rest_framework import serializers
from .models import Dokument


class DokumentSerializer(serializers.ModelSerializer):
    hochgeladen_von = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = Dokument
        fields = '__all__'
        read_only_fields = ['id', 'hochgeladen_am']
