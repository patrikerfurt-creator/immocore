from django.contrib import admin
from .models import Konto, Personenkonto, Unterkonto


@admin.register(Konto)
class KontoAdmin(admin.ModelAdmin):
    list_display = ['kontonummer', 'kontoname', 'wirtschaftsjahr', 'kontoart', 'verteilerschluessel', 'aktiv']
    list_filter = ['kontoart', 'verteilerschluessel', 'aktiv', 'wirtschaftsjahr__objekt']
    search_fields = ['kontonummer', 'kontoname']
    ordering = ['wirtschaftsjahr__objekt__bezeichnung', 'kontonummer']


@admin.register(Personenkonto)
class PersonenkontoAdmin(admin.ModelAdmin):
    list_display = ['kontonummer', 'eigentuemer', 'objekt', 'status', 'archiviert_am']
    list_filter = ['status', 'objekt']
    search_fields = ['kontonummer', 'eigentuemer__nachname', 'eigentuemer__firmenname']
    ordering = ['objekt__bezeichnung', 'kontonummer']


@admin.register(Unterkonto)
class UnterkontoAdmin(admin.ModelAdmin):
    list_display = ['volle_kontonummer', 'bezeichnung', 'personenkonto', 'suffix', 'bankkonto']
    list_filter = ['personenkonto__objekt']
    search_fields = ['bezeichnung', 'suffix']
    ordering = ['personenkonto__kontonummer', 'suffix']

    @admin.display(description='Volle Kontonummer')
    def volle_kontonummer(self, obj):
        return obj.volle_kontonummer
