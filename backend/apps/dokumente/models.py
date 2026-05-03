from uuid import uuid4
from django.conf import settings
from django.db import models
from apps.objekte.models import Objekt, Einheit


class Dokument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    datei = models.FileField(upload_to='dokumente/')
    dateiname = models.CharField(max_length=255)
    kategorie = models.CharField(max_length=100)  # z.B. Teilungserklärung, Versicherung, Protokoll
    beschreibung = models.TextField(blank=True)
    verknuepfung_typ = models.CharField(max_length=50)  # Objekt / Einheit / Ticket / Rechnung
    objekt = models.ForeignKey(
        Objekt, on_delete=models.CASCADE, null=True, blank=True,
        related_name='dokumente'
    )
    einheit = models.ForeignKey(
        Einheit, on_delete=models.CASCADE, null=True, blank=True,
        related_name='dokumente'
    )
    hochgeladen_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='hochgeladene_dokumente'
    )
    hochgeladen_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Dokument'
        verbose_name_plural = 'Dokumente'
        ordering = ['-hochgeladen_am']

    def __str__(self):
        return f"{self.dateiname} ({self.kategorie})"
