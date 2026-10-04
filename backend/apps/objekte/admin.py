from django.contrib import admin
from .models import Objekt, Eingang, Bankkonto, Einheit

from apps.buchhaltung.models import MahnEinstellung
from apps.handwerker.models import ObjektHandwerker


class ObjektHandwerkerInline(admin.TabularInline):
    model = ObjektHandwerker
    extra = 0
    fields = ['kreditor', 'prioritaet', 'notiz']
    ordering = ['prioritaet']
    raw_id_fields = ['kreditor']


class MahnEinstellungInline(admin.StackedInline):
    model = MahnEinstellung
    extra = 0
    max_num = 1
    fields = ['mahngebuehr', 'anzahl_mahnstufen', 'zinsen_erheben']


@admin.register(Objekt)
class ObjektAdmin(admin.ModelAdmin):
    list_display = ['bezeichnung', 'objekt_typ', 'ort', 'status', 'verwaltung_seit', 'mailversand_aktiv']
    list_editable = ['mailversand_aktiv']
    list_filter = ['objekt_typ', 'status', 'umsatzsteuer_pflichtig', 'mailversand_aktiv']
    search_fields = ['bezeichnung', 'strasse', 'ort', 'plz']
    ordering = ['bezeichnung']
    inlines = [ObjektHandwerkerInline, MahnEinstellungInline]


@admin.register(Eingang)
class EingangAdmin(admin.ModelAdmin):
    list_display = ['bezeichnung', 'objekt', 'strasse', 'ort']
    list_filter = ['objekt']
    search_fields = ['bezeichnung', 'strasse', 'ort']
    ordering = ['objekt__bezeichnung', 'bezeichnung']


@admin.register(Bankkonto)
class BankkontoAdmin(admin.ModelAdmin):
    list_display = ['bezeichnung', 'objekt', 'konto_typ', 'iban', 'aktiv', 'reihenfolge']
    list_filter = ['konto_typ', 'aktiv', 'objekt']
    search_fields = ['bezeichnung', 'iban', 'kontoinhaber']
    ordering = ['objekt__bezeichnung', 'reihenfolge']


@admin.register(Einheit)
class EinheitAdmin(admin.ModelAdmin):
    list_display = ['einheit_nr', 'objekt', 'einheit_typ', 'lage']
    list_filter = ['einheit_typ', 'objekt']
    search_fields = ['einheit_nr', 'lage']
    ordering = ['objekt__bezeichnung', 'einheit_nr']
