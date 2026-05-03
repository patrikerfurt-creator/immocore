from django.contrib import admin
from .models import Ticket


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = [
        'titel', 'ticket_typ', 'objekt', 'einheit', 'status',
        'prioritaet', 'zuweisung', 'erstellt_am'
    ]
    list_filter = ['ticket_typ', 'status', 'prioritaet', 'objekt']
    search_fields = ['titel', 'beschreibung', 'erstellt_von__username']
    ordering = ['-erstellt_am']
    readonly_fields = ['erstellt_am', 'aktualisiert_am']
