from django.contrib import admin

from .models import (
    Beschluss, BeschlussNummerZaehler, EVEreignis, EVStimme, EVStimmgrundlage,
    EVTeilnehmer, EVTeilnehmerAnteil, EVTeilnehmerAnteilWert,
    EVTeilnehmerStimmkraft, EVVersandprotokoll, Eigentuemerversammlung,
    Tagesordnungspunkt, Versammlungsort,
)


@admin.register(Versammlungsort)
class VersammlungsortAdmin(admin.ModelAdmin):
    list_display = ('bezeichnung', 'strasse', 'plz', 'ort_text', 'aktiv')
    list_filter = ('aktiv',)
    search_fields = ('bezeichnung', 'ort_text')


@admin.register(Eigentuemerversammlung)
class EigentuemerversammlungAdmin(admin.ModelAdmin):
    list_display = ('arbeitsname', 'objekt', 'termin', 'status', 'stimmprinzip')
    list_filter = ('status', 'art', 'stimmprinzip')
    raw_id_fields = ('stimm_verteilerschluessel', 'versammlungsort')
    search_fields = ('arbeitsname', 'objekt__bezeichnung')


@admin.register(EVStimmgrundlage)
class EVStimmgrundlageAdmin(admin.ModelAdmin):
    list_display = ('ev', 'bezeichnung_anzeige', 'ist_kopfprinzip', 'ist_standard')
    list_filter = ('ist_kopfprinzip', 'ist_standard')
    raw_id_fields = ('ev', 'verteilerschluessel')


@admin.register(Tagesordnungspunkt)
class TagesordnungspunktAdmin(admin.ModelAdmin):
    list_display = ('ev', 'nummer', 'titel', 'abstimmungsmodus', 'abstimmungsergebnis')
    list_filter = ('abstimmungsmodus', 'abstimmungsergebnis')
    raw_id_fields = ('stimmgrundlage',)


@admin.register(EVTeilnehmer)
class EVTeilnehmerAdmin(admin.ModelAdmin):
    list_display = ('ev', 'person', 'stimmkraft', 'zusage_status', 'ist_anwesend')
    list_filter = ('zusage_status', 'ist_anwesend')


@admin.register(Beschluss)
class BeschlussAdmin(admin.ModelAdmin):
    list_display = ('objekt', 'nummer', 'beschluss_datum', 'anfechtung_status')
    list_filter = ('anfechtung_status',)
    # § 24 Abs. 7 WEG: der Wortlaut wird nie geändert, Einträge nie gelöscht.
    readonly_fields = ('nummer', 'wortlaut', 'beschluss_datum', 'erstellt_am')


admin.site.register(EVTeilnehmerAnteil)
admin.site.register(EVTeilnehmerStimmkraft)
admin.site.register(EVTeilnehmerAnteilWert)
admin.site.register(EVStimme)
admin.site.register(EVVersandprotokoll)
admin.site.register(EVEreignis)
admin.site.register(BeschlussNummerZaehler)
