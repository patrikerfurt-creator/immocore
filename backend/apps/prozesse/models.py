from uuid import uuid4
from django.conf import settings
from django.db import models
from apps.objekte.models import Objekt


class Prozess(models.Model):
    PROZESS_TYP_CHOICES = [
        ('objekt_anlegen', 'Objekt anlegen'),
        ('eigentuemerwechsel', 'Eigentümerwechsel'),
        ('jahresabrechnung', 'Jahresabrechnung'),
        ('mieterwechsel', 'Mieterwechsel'),
    ]
    STATUS_CHOICES = [
        ('aktiv', 'Aktiv'),
        ('abgeschlossen', 'Abgeschlossen'),
        ('abgebrochen', 'Abgebrochen'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    prozess_typ = models.CharField(max_length=30, choices=PROZESS_TYP_CHOICES)
    objekt = models.ForeignKey(
        Objekt, on_delete=models.CASCADE, null=True, blank=True,
        related_name='prozesse'
    )
    current_step = models.PositiveIntegerField(default=1)
    steps_data = models.JSONField(default=dict)  # alle bisherigen Eingaben
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='aktiv')
    gestartet_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='gestartete_prozesse'
    )
    gestartet_am = models.DateTimeField(auto_now_add=True)
    abgeschlossen_am = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Prozess'
        verbose_name_plural = 'Prozesse'
        ordering = ['-gestartet_am']

    def __str__(self):
        return (
            f"{self.get_prozess_typ_display()} — "
            f"{self.objekt.bezeichnung if self.objekt else '—'} [{self.status}]"
        )
