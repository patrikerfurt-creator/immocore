from django.contrib import admin

from .models import (
    PersonStammdatenAenderung,
    PortalSession,
    PortalToken,
    PortalZugang,
)


@admin.register(PortalZugang)
class PortalZugangAdmin(admin.ModelAdmin):
    list_display = ('person', 'status', 'aktiv', 'eingeladen_am',
                    'erstaktivierung_am', 'letzter_login')
    list_filter = ('aktiv',)
    search_fields = ('person__nachname', 'person__firmenname', 'person__personennummer')
    readonly_fields = ('erstellt_am', 'geaendert_am')
    raw_id_fields = ('person',)


@admin.register(PortalToken)
class PortalTokenAdmin(admin.ModelAdmin):
    list_display = ('zugang', 'typ', 'gueltig_bis', 'verbraucht_am', 'erstellt_am')
    list_filter = ('typ',)
    # Das Token selbst ist das Geheimnis — es gehört nicht in eine
    # Übersichtsliste, die beiläufig auf einem Bildschirm offen liegt.
    exclude = ('token',)
    readonly_fields = ('erstellt_am',)
    raw_id_fields = ('zugang',)


@admin.register(PortalSession)
class PortalSessionAdmin(admin.ModelAdmin):
    list_display = ('zugang', 'gueltig_bis', 'letzter_zugriff', 'erstellt_am')
    exclude = ('token',)
    readonly_fields = ('erstellt_am',)
    raw_id_fields = ('zugang',)


@admin.register(PersonStammdatenAenderung)
class PersonStammdatenAenderungAdmin(admin.ModelAdmin):
    """Audit-Log — im Admin bewusst nur lesbar (GoBD-Nachvollziehbarkeit)."""

    list_display = ('zeitstempel', 'person', 'feld', 'alter_wert', 'neuer_wert', 'quelle')
    list_filter = ('feld', 'quelle')
    search_fields = ('person__nachname', 'person__firmenname')
    readonly_fields = ('person', 'feld', 'alter_wert', 'neuer_wert', 'quelle', 'zeitstempel')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
