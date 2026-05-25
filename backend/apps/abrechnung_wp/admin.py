from django.contrib import admin
from .models import Wirtschaftsplan, WirtschaftsplanPosition, WirtschaftsplanAnteil

admin.site.register(Wirtschaftsplan)
admin.site.register(WirtschaftsplanPosition)
admin.site.register(WirtschaftsplanAnteil)
