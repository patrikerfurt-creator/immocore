from django.contrib import admin
from .models import Buchung, BankImport, Jahresabrechnung, EinzelAbrechnung


@admin.register(Buchung)
class BuchungAdmin(admin.ModelAdmin):
    list_display = ['buchungsdatum', 'betrag', 'status', 'objekt', 'belegnr', 'erstellt_von']
    list_filter = ['status', 'objekt', 'buchungsdatum']
    search_fields = ['belegnr', 'verwendungszweck']
    ordering = ['-buchungsdatum', '-erstellt_am']
    date_hierarchy = 'buchungsdatum'


@admin.register(BankImport)
class BankImportAdmin(admin.ModelAdmin):
    list_display = [
        'buchungsdatum', 'betrag', 'auftraggeber_name', 'auftraggeber_iban',
        'status', 'objekt'
    ]
    list_filter = ['status', 'objekt', 'buchungsdatum']
    search_fields = ['auftraggeber_name', 'auftraggeber_iban', 'verwendungszweck']
    ordering = ['-buchungsdatum', '-importiert_am']
    readonly_fields = ['sha256_hash', 'importiert_am']


@admin.register(Jahresabrechnung)
class JahresabrechnungAdmin(admin.ModelAdmin):
    list_display = ['wirtschaftsjahr', 'objekt', 'status', 'erstellungsdatum', 'erstellt_von']
    list_filter = ['status', 'objekt', 'wirtschaftsjahr']
    ordering = ['-wirtschaftsjahr', 'objekt__bezeichnung']


@admin.register(EinzelAbrechnung)
class EinzelAbrechnungAdmin(admin.ModelAdmin):
    list_display = [
        'jahresabrechnung', 'einheit', 'hausgeld_soll_gesamt',
        'kostenanteil_gesamt', 'abrechnungsergebnis', 'gebucht'
    ]
    list_filter = ['gebucht', 'jahresabrechnung__objekt', 'jahresabrechnung__wirtschaftsjahr']
    search_fields = ['einheit__einheit_nr']
    ordering = ['jahresabrechnung__wirtschaftsjahr', 'einheit__einheit_nr']
