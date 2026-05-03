from django import forms
from django.contrib import admin
from .models import SEPAMandat, Person, EigentumsVerhaeltnis, HausgeldHistorie, Mietvertrag


class PersonAdminForm(forms.ModelForm):
    class Meta:
        model = Person
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ibans'].required = False
        self.fields['ibans'].initial = []


@admin.register(SEPAMandat)
class SEPAMandatAdmin(admin.ModelAdmin):
    list_display = ['mandatsreferenz', 'iban', 'unterzeichnet_am', 'aktiv']
    list_filter = ['aktiv']
    search_fields = ['mandatsreferenz', 'iban']
    ordering = ['-unterzeichnet_am']


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    form = PersonAdminForm
    list_display = ['name', 'person_typ', 'email', 'telefon', 'ist_firma']
    list_filter = ['person_typ', 'ist_firma']
    search_fields = ['vorname', 'nachname', 'firmenname', 'email']
    ordering = ['nachname', 'vorname', 'firmenname']


@admin.register(EigentumsVerhaeltnis)
class EigentumsVerhaeltnisAdmin(admin.ModelAdmin):
    list_display = ['person', 'einheit', 'beginn', 'ende', 'ist_aktiv']
    list_filter = ['einheit__objekt']
    search_fields = ['person__nachname', 'person__vorname', 'person__firmenname']
    ordering = ['-beginn']

    @admin.display(boolean=True, description='Aktiv')
    def ist_aktiv(self, obj):
        return obj.ist_aktiv


@admin.register(HausgeldHistorie)
class HausgeldHistorieAdmin(admin.ModelAdmin):
    list_display = ['eigentumsverhaeltnis', 'betrag', 'gueltig_ab', 'erstellt_von']
    list_filter = ['gueltig_ab']
    search_fields = ['eigentumsverhaeltnis__person__nachname']
    ordering = ['-gueltig_ab']


@admin.register(Mietvertrag)
class MietvertragAdmin(admin.ModelAdmin):
    list_display = ['mieter', 'einheit', 'beginn', 'ende', 'kaltmiete']
    list_filter = ['einheit__objekt']
    search_fields = ['mieter__nachname', 'mieter__vorname', 'mieter__firmenname']
    ordering = ['-beginn']
