from django.contrib import admin
from .models import Rechnung, Freigabe, Kreditor


@admin.register(Kreditor)
class KreditorAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'kreditorennummer', 'gewerke_liste', 'ist_handwerker', 'aktiv', 'ort',
    ]
    list_filter = ['gewerke', 'ist_handwerker', 'aktiv']
    search_fields = ['name', 'kreditorennummer', 'iban', 'email']
    ordering = ['name']
    filter_horizontal = ['gewerke']

    @admin.display(description='Gewerke')
    def gewerke_liste(self, obj):
        return ', '.join(g.bezeichnung for g in obj.gewerke.all())


@admin.register(Rechnung)
class RechnungAdmin(admin.ModelAdmin):
    list_display = [
        'rechnungsnummer', 'lieferant', 'objekt', 'betrag_brutto',
        'rechnungsdatum', 'faelligkeitsdatum', 'status'
    ]
    list_filter = ['status', 'objekt', 'rechnungsdatum']
    search_fields = ['rechnungsnummer', 'lieferant__nachname', 'lieferant__firmenname']
    ordering = ['-rechnungsdatum', '-erstellt_am']
    date_hierarchy = 'rechnungsdatum'
    readonly_fields = ['erstellt_am', 'ki_extraktion']


@admin.register(Freigabe)
class FreigabeAdmin(admin.ModelAdmin):
    list_display = ['rechnung', 'bearbeiter', 'rolle', 'entscheidung', 'zeitstempel']
    list_filter = ['entscheidung', 'rolle']
    search_fields = ['rechnung__rechnungsnummer', 'bearbeiter__username']
    ordering = ['-zeitstempel']
    readonly_fields = ['zeitstempel']
