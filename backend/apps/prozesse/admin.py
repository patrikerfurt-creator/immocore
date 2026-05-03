from django.contrib import admin
from .models import Prozess


@admin.register(Prozess)
class ProzessAdmin(admin.ModelAdmin):
    list_display = [
        'prozess_typ', 'objekt', 'current_step', 'status',
        'gestartet_von', 'gestartet_am', 'abgeschlossen_am'
    ]
    list_filter = ['prozess_typ', 'status', 'objekt']
    search_fields = ['objekt__bezeichnung', 'gestartet_von__username']
    ordering = ['-gestartet_am']
    readonly_fields = ['gestartet_am']
