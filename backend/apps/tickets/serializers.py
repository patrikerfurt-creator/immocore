from rest_framework import serializers
from .models import Ticket


class TicketSerializer(serializers.ModelSerializer):
    erstellt_von = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = Ticket
        fields = '__all__'
        read_only_fields = ['id', 'erstellt_am', 'aktualisiert_am']


class TicketListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ticket
        fields = [
            'id', 'titel', 'ticket_typ', 'status', 'prioritaet',
            'objekt', 'erstellt_am'
        ]
