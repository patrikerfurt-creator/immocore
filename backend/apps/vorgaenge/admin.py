from django.contrib import admin

from apps.vorgaenge.models import GraphMailAbruf, MailImportProtokoll


@admin.register(GraphMailAbruf)
class GraphMailAbrufAdmin(admin.ModelAdmin):
    """Schalter für den Graph-Mailabruf des info@-Postfachs (Singleton).

    Nur hier im Admin wird der Abruf ein-/ausgeschaltet — bewusst nicht im
    Frontend. Der Zeitstempel und die Meldung sind Ergebnis der Läufe und
    deshalb schreibgeschützt.
    """

    list_display = ('__str__', 'aktiv', 'letzter_abruf', 'zuletzt_gelaufen',
                    'letzte_meldung')
    list_editable = ('aktiv',)
    readonly_fields = ('letzter_abruf', 'zuletzt_gelaufen', 'letzte_meldung')

    def has_delete_permission(self, request, obj=None):
        return False  # Singleton nie löschen

    def has_add_permission(self, request):
        # Genau eine Zeile; sie entsteht über GraphMailAbruf.load().
        return not GraphMailAbruf.objects.exists()


@admin.register(MailImportProtokoll)
class MailImportProtokollAdmin(admin.ModelAdmin):
    """Auswertungsmaske für den Mail-Import-Testlauf.

    Hier wird ``bewertung`` gesetzt — das ist der einzige Wert, den ein
    Mensch beisteuert und aus dem ``mail_scan --auswertung`` die echte
    Trefferquote rechnet. Alle übrigen Felder sind Ergebnis der Verarbeitung
    und deshalb schreibgeschützt: eine nachträglich "korrigierte" Erkennung
    würde genau die Messung verfälschen, für die das Protokoll da ist.
    """

    list_display = (
        'verarbeitet_am', 'dateiname', 'status', 'absender', 'person',
        'einheit', 'ki_typ_code', 'ki_konfidenz', 'mehrdeutig', 'bewertung',
    )
    list_filter = ('status', 'bewertung', 'zuordnung_quelle', 'mehrdeutig',
                   'ki_typ_code')
    search_fields = ('dateiname', 'absender', 'betreff', 'message_id')
    list_editable = ('bewertung',)
    date_hierarchy = 'verarbeitet_am'
    list_select_related = ('person', 'einheit', 'vorgang')

    fieldsets = (
        ('Bewertung', {
            'fields': ('bewertung', 'bewertung_notiz'),
            'description': 'Das Einzige, was hier gepflegt wird: War die '
                           'Erkennung richtig? Daraus entsteht die Trefferquote.',
        }),
        ('Mail', {
            'fields': ('dateiname', 'message_id', 'bezug_message_id',
                       'absender', 'absender_name',
                       'betreff', 'gesendet_am', 'anhaenge_anzahl', 'body_auszug'),
        }),
        ('Ergebnis', {
            'fields': ('status', 'vorgang', 'fehler'),
        }),
        ('Stufe 1 — regelbasiert', {
            'fields': ('person', 'objekt', 'einheit', 'zuordnung_quelle',
                       'mehrdeutig'),
        }),
        ('Stufe 2 — KI', {
            'fields': ('ki_typ_code', 'ki_prioritaet', 'ki_betreff',
                       'ki_konfidenz', 'ki_begruendung', 'ki_modell', 'ki_fehler'),
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        bearbeitbar = {'bewertung', 'bewertung_notiz'}
        return [f.name for f in self.model._meta.fields
                if f.name not in bearbeitbar]

    def has_add_permission(self, request):
        # Protokollzeilen entstehen ausschliesslich durch die Verarbeitung.
        return False
