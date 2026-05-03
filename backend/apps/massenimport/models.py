from uuid import uuid4
from django.conf import settings
from django.db import models


class ImportJob(models.Model):
    STATUS_CHOICES = [
        ('pending',   'Ausstehend'),
        ('parsed',    'Vorschau bereit'),
        ('committed', 'Übernommen'),
        ('failed',    'Fehlgeschlagen'),
        ('partial',   'Teilweise übernommen'),
    ]
    TYP_CHOICES = [
        ('weg_objekt', 'WEG-Objekte'),
    ]

    id             = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    typ            = models.CharField(max_length=20, choices=TYP_CHOICES, default='weg_objekt')
    datei_pfad     = models.CharField(max_length=500, blank=True)
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    preview_token  = models.UUIDField(null=True, blank=True, unique=True)
    zeilen_gesamt  = models.PositiveIntegerField(default=0)
    zeilen_ok      = models.PositiveIntegerField(default=0)
    zeilen_warnung = models.PositiveIntegerField(default=0)
    zeilen_fehler  = models.PositiveIntegerField(default=0)
    ergebnis       = models.JSONField(default=dict)
    erstellt_von   = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='import_jobs',
    )
    erstellt_am    = models.DateTimeField(auto_now_add=True)
    aktualisiert_am = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Import-Job'
        verbose_name_plural = 'Import-Jobs'
        ordering            = ['-erstellt_am']

    def __str__(self):
        return f"ImportJob {self.get_typ_display()} {self.erstellt_am.date()} [{self.status}]"
