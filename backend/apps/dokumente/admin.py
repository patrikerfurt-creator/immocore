from django.contrib import admin
from .models import Aktenregister, Dokument


@admin.register(Aktenregister)
class AktenregisterAdmin(admin.ModelAdmin):
    """Pflege der Aktengliederung.

    Bewusst im Admin und nicht als Code-Konstante: welche Register eine
    Verwaltung fuehrt, ist ihre eigene Ordnung. Die Reihenfolge steuert
    ``sortierung`` — sie bestimmt, wie die Akte aufgeblaettert wird.
    """
    list_display = ['code', 'bezeichnung', 'aktenart', 'eltern',
                    'sortierung', 'aktiv', 'anzahl_dokumente']
    list_filter = ['aktenart', 'aktiv']
    search_fields = ['code', 'bezeichnung', 'hinweis']
    list_editable = ['sortierung', 'aktiv']
    ordering = ['sortierung', 'code']

    @admin.display(description='Dokumente')
    def anzahl_dokumente(self, obj):
        return obj.dokumente.count()


@admin.register(Dokument)
class DokumentAdmin(admin.ModelAdmin):
    list_display = [
        'dateiname', 'register', 'dokument_datum', 'objekt',
        'einheit', 'hochgeladen_von', 'hochgeladen_am'
    ]
    list_filter = ['register', 'kategorie', 'objekt']
    search_fields = ['dateiname', 'kategorie', 'beschreibung']
    ordering = ['-hochgeladen_am']
    readonly_fields = ['hochgeladen_am']
