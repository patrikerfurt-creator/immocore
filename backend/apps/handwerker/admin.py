from django.contrib import admin

from .models import (
    AuftragsbestaetigungsToken,
    Gewerk,
    Handwerkerauftrag,
    HandwerkerauftragEreignis,
    ObjektHandwerker,
)


@admin.register(Gewerk)
class GewerkAdmin(admin.ModelAdmin):
    list_display = ['bezeichnung', 'code', 'aktiv', 'sortierung']
    list_filter = ['aktiv']
    search_fields = ['code', 'bezeichnung']
    ordering = ['sortierung', 'bezeichnung']


class HandwerkerauftragEreignisInline(admin.TabularInline):
    """Read-only Audit-Verlauf — Ereignisse werden nie über das Admin
    angelegt, geändert oder gelöscht (GoBD, siehe apps.handwerker.models)."""
    model = HandwerkerauftragEreignis
    extra = 0
    fields = ['erstellt_am', 'typ', 'text', 'alter_wert', 'neuer_wert', 'erstellt_von']
    readonly_fields = fields
    ordering = ['erstellt_am']
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class AuftragsbestaetigungsTokenInline(admin.StackedInline):
    model = AuftragsbestaetigungsToken
    extra = 0
    readonly_fields = ['accept_token', 'reject_token', 'gueltig_bis', 'verbraucht_am', 'erstellt_am']
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Handwerkerauftrag)
class HandwerkerauftragAdmin(admin.ModelAdmin):
    list_display = ['nummer', 'titel', 'objekt', 'kreditor', 'status', 'prioritaet', 'erstellt_am']
    list_filter = ['status', 'prioritaet', 'objekt']
    search_fields = ['nummer', 'titel', 'kreditor__name', 'objekt__bezeichnung']
    ordering = ['-erstellt_am']
    readonly_fields = ['nummer', 'erstellt_am', 'geaendert_am']
    raw_id_fields = ['objekt', 'kreditor', 'vorgang', 'erstellt_von']
    inlines = [AuftragsbestaetigungsTokenInline, HandwerkerauftragEreignisInline]


@admin.register(HandwerkerauftragEreignis)
class HandwerkerauftragEreignisAdmin(admin.ModelAdmin):
    """Eigenständige Ansicht read-mostly — Anlage/Änderung/Löschung nur über
    den Buchungs-/Service-Pfad, nicht über das Admin (GoBD-Audit-Spur)."""
    list_display = ['auftrag', 'typ', 'erstellt_am', 'erstellt_von']
    list_filter = ['typ']
    search_fields = ['auftrag__nummer', 'text']
    ordering = ['erstellt_am']
    readonly_fields = [f.name for f in HandwerkerauftragEreignis._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ObjektHandwerker)
class ObjektHandwerkerAdmin(admin.ModelAdmin):
    list_display = ['objekt', 'kreditor', 'prioritaet', 'erstellt_am']
    list_filter = ['objekt']
    search_fields = ['objekt__bezeichnung', 'kreditor__name']
    ordering = ['prioritaet', 'kreditor__name']
    raw_id_fields = ['objekt', 'kreditor']
