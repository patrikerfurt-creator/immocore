from django.contrib import admin
from .models import Mitarbeiter


@admin.register(Mitarbeiter)
class MitarbeiterAdmin(admin.ModelAdmin):
    list_display  = ['__str__', 'telefon', 'aktiv', 'eingetreten_am']
    list_filter   = ['aktiv']
    search_fields = ['user__first_name', 'user__last_name', 'user__email']
