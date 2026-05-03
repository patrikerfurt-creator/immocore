from rest_framework import serializers
from .models import Prozess


class ProzessSerializer(serializers.ModelSerializer):
    gestartet_von = serializers.HiddenField(default=serializers.CurrentUserDefault())
    prozess_typ_display = serializers.CharField(
        source='get_prozess_typ_display', read_only=True
    )

    class Meta:
        model = Prozess
        fields = '__all__'
        read_only_fields = ['id', 'gestartet_am', 'abgeschlossen_am']
