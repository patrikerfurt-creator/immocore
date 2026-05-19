from django.contrib import admin
from .models import Wirtschaftsplan, WirtschaftsplanPosition, WirtschaftsplanAnteil


@admin.register(Wirtschaftsplan)
class WirtschaftsplanAdmin(admin.ModelAdmin):
    list_display = ['id', 'wirtschaftsjahr', 'status', 'wirkung_ab', 'gesamtsumme', 'erstellt_am']
    list_filter = ['status']
    search_fields = ['wirtschaftsjahr__objekt__bezeichnung']
    ordering = ['-erstellt_am']


@admin.register(WirtschaftsplanPosition)
class WirtschaftsplanPositionAdmin(admin.ModelAdmin):
    list_display = ['id', 'wirtschaftsplan', 'konto', 'vs_code', 'betrag', 'verteilung_validiert']
    list_filter = ['verteilung_validiert']
    search_fields = ['konto__kontonummer', 'konto__kontoname']


@admin.register(WirtschaftsplanAnteil)
class WirtschaftsplanAnteilAdmin(admin.ModelAdmin):
    list_display = ['id', 'position', 'einheit', 'betrag_anteil', 'monatsbetrag_anteil']
    search_fields = ['einheit__einheit_nr']
