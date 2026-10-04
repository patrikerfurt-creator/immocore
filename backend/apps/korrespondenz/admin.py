from django.contrib import admin

from .models import (
    Briefbogen, Druckstapel, Schreiben, Serienlauf, Textbaustein, Vorlage, VorlageAnlage,
    VorlagenVersion,
)


@admin.register(Briefbogen)
class BriefbogenAdmin(admin.ModelAdmin):
    list_display = ('bezeichnung', 'firma_name', 'ist_standard', 'aktiv')
    list_filter = ('ist_standard', 'aktiv')
    search_fields = ('bezeichnung', 'firma_name')
    raw_id_fields = ('logo', 'fuss_logo')


class VorlageAnlageInline(admin.TabularInline):
    model = VorlageAnlage
    extra = 0
    raw_id_fields = ('dokument',)
    fields = ('reihenfolge', 'bezeichnung', 'art', 'dokument', 'objekt_kategorie', 'pflicht', 'bedingung')


@admin.register(Vorlage)
class VorlageAdmin(admin.ModelAdmin):
    inlines = [VorlageAnlageInline]
    list_display = ('code', 'bezeichnung', 'anlass', 'objekt', 'kanal_standard', 'aktiv')
    list_filter = ('anlass', 'kanal_standard', 'aktiv')
    search_fields = ('code', 'bezeichnung')
    raw_id_fields = ('objekt', 'briefbogen', 'aktive_version')


@admin.register(Textbaustein)
class TextbausteinAdmin(admin.ModelAdmin):
    list_display = ('code', 'bezeichnung', 'objekt', 'aktiv')
    list_filter = ('aktiv',)
    search_fields = ('code', 'bezeichnung')
    raw_id_fields = ('objekt',)


@admin.register(VorlagenVersion)
class VorlagenVersionAdmin(admin.ModelAdmin):
    list_display = ('vorlage', 'version', 'status', 'freigegeben_am', 'erstellt_am')
    list_filter = ('status',)
    search_fields = ('vorlage__code', 'betreff')
    raw_id_fields = ('vorlage', 'freigegeben_von', 'erstellt_von')


@admin.register(Schreiben)
class SchreibenAdmin(admin.ModelAdmin):
    list_display = ('nummer', 'status', 'kanal', 'empfaenger', 'objekt', 'erstellt_am')
    list_filter = ('status', 'kanal')
    search_fields = ('nummer',)
    raw_id_fields = (
        'vorlage_version', 'empfaenger', 'objekt', 'einheit', 'eigentumsverhaeltnis', 'vorgang',
        'mahnung', 'eigentuemerwechsel', 'serienlauf', 'unterzeichner', 'dokument',
        'druckstapel', 'freigegeben_von', 'erstellt_von',
    )


@admin.register(Druckstapel)
class DruckstapelAdmin(admin.ModelAdmin):
    list_display = ('id', 'status', 'erstellt_am', 'bestaetigt_am')
    list_filter = ('status',)
    raw_id_fields = ('dokument', 'erstellt_von', 'bestaetigt_von')


@admin.register(Serienlauf)
class SerienlaufAdmin(admin.ModelAdmin):
    list_display = ('id', 'vorlage_version', 'objekt', 'status', 'anzahl', 'erstellt_am')
    list_filter = ('status',)
    raw_id_fields = (
        'vorlage_version', 'objekt', 'unterzeichner', 'druck_dokument', 'erstellt_von',
        'freigegeben_von',
    )
