from django.contrib import admin
from .models import Dokument


@admin.register(Dokument)
class DokumentAdmin(admin.ModelAdmin):
    list_display = [
        'dateiname', 'kategorie', 'objekt',
        'einheit', 'hochgeladen_von', 'hochgeladen_am'
    ]
    list_filter = ['kategorie', 'objekt']
    search_fields = ['dateiname', 'kategorie', 'beschreibung']
    ordering = ['-hochgeladen_am']
    readonly_fields = ['hochgeladen_am']
