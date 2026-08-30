from django.contrib import admin
from .models import (
    Freigabe,
    Kreditor,
    KreditorBankverbindung,
    KreditorDublettenPruefung,
    Rechnung,
)


class KreditorBankverbindungInline(admin.TabularInline):
    """Weitere Bankverbindungen direkt beim Kreditor — sonst wäre bei einer
    Rückfrage nicht sichtbar, welche Konten neben der primären IBAN
    bekannt sind."""

    model = KreditorBankverbindung
    extra = 0
    fields = ['iban', 'bic', 'bemerkung', 'aktiv', 'erfasst_am']
    readonly_fields = ['erfasst_am']


@admin.register(Kreditor)
class KreditorAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'kreditorennummer', 'gewerke_liste', 'ist_handwerker', 'aktiv', 'ort',
    ]
    list_filter = ['gewerke', 'ist_handwerker', 'aktiv']
    search_fields = ['name', 'kreditorennummer', 'iban', 'email']
    ordering = ['name']
    filter_horizontal = ['gewerke']
    inlines = [KreditorBankverbindungInline]
    # Wird in save() aus 'name' abgeleitet — von Hand gesetzt würde er beim
    # nächsten Speichern ohnehin überschrieben.
    readonly_fields = ['name_normalisiert']

    @admin.display(description='Gewerke')
    def gewerke_liste(self, obj):
        return ', '.join(g.bezeichnung for g in obj.gewerke.all())


@admin.register(KreditorDublettenPruefung)
class KreditorDublettenPruefungAdmin(admin.ModelAdmin):
    """Nur lesend: der Status darf sich ausschließlich über die
    Entscheidungs-Aktionen ändern, damit Kreditor-Zuordnung,
    Rechnungsstatus und Audit-Felder nicht auseinanderlaufen."""

    list_display = [
        'erkannter_name', 'anlass', 'status', 'ergebnis_kreditor',
        'entschieden_von', 'entschieden_am', 'erstellt_am',
    ]
    list_filter = ['status', 'anlass']
    search_fields = ['erkannter_name', 'erkannte_iban', 'rechnung__rechnungsnummer']
    ordering = ['-erstellt_am']
    readonly_fields = [
        'rechnung', 'erkannter_name', 'erkannte_iban', 'anlass', 'kandidaten',
        'status', 'ergebnis_kreditor', 'entschieden_von', 'entschieden_am',
        'notiz', 'erstellt_am',
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


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
