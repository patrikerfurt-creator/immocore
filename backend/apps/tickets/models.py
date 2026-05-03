from uuid import uuid4
from django.conf import settings
from django.db import models
from apps.objekte.models import Objekt, Einheit


class Ticket(models.Model):
    TICKET_TYP_CHOICES = [
        ('maengelmeldung', 'Mängelmedlung'),
        ('anfrage', 'Anfrage'),
        ('aufgabe', 'Aufgabe'),
        ('sonstiges', 'Sonstiges'),
    ]
    STATUS_CHOICES = [
        ('offen', 'Offen'),
        ('in_bearbeitung', 'In Bearbeitung'),
        ('erledigt', 'Erledigt'),
        ('geschlossen', 'Geschlossen'),
    ]
    PRIORITAET_CHOICES = [
        ('niedrig', 'Niedrig'),
        ('mittel', 'Mittel'),
        ('hoch', 'Hoch'),
        ('kritisch', 'Kritisch'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt = models.ForeignKey(Objekt, on_delete=models.CASCADE, related_name='tickets')
    einheit = models.ForeignKey(
        Einheit, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='tickets'
    )
    titel = models.CharField(max_length=255)
    beschreibung = models.TextField()
    ticket_typ = models.CharField(max_length=20, choices=TICKET_TYP_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='offen')
    prioritaet = models.CharField(max_length=10, choices=PRIORITAET_CHOICES, default='mittel')
    zuweisung = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='zugewiesene_tickets'
    )
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='erstellte_tickets'
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)
    aktualisiert_am = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Ticket'
        verbose_name_plural = 'Tickets'
        ordering = ['-erstellt_am']

    def __str__(self):
        return f"[{self.get_prioritaet_display()}] {self.titel} ({self.get_status_display()})"
