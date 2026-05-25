from uuid import uuid4
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError


class Wirtschaftsplan(models.Model):
    STATUS_CHOICES = [
        ('entwurf', 'Entwurf'),
        ('beschlossen', 'Beschlossen'),
        ('aktiv', 'Aktiv'),
        ('aufgehoben', 'Aufgehoben'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    wirtschaftsjahr = models.ForeignKey(
        'objekte.Wirtschaftsjahr', on_delete=models.CASCADE,
        related_name='wirtschaftsplaene',
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='entwurf')
    gesamtsumme = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    gesamtsumme_hausgeld = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    gesamtsumme_ruecklage = models.JSONField(default=dict)
    beschluss_datum = models.DateField(null=True, blank=True)
    beschluss_tagesordnungspunkt = models.CharField(max_length=100, null=True, blank=True)
    wirkung_ab = models.DateField()
    bemerkung = models.TextField(null=True, blank=True)
    aufhebt_wp = models.ForeignKey(
        'self', on_delete=models.PROTECT, null=True, blank=True,
        related_name='abgeloest_durch',
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='erstellte_wirtschaftsplaene',
    )
    beschlossen_am = models.DateTimeField(null=True, blank=True)
    beschlossen_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='beschlossene_wirtschaftsplaene',
    )

    class Meta:
        verbose_name = 'Wirtschaftsplan'
        verbose_name_plural = 'Wirtschaftspläne'
        ordering = ['-wirtschaftsjahr__jahr', 'status']
        constraints = [
            models.UniqueConstraint(
                fields=['wirtschaftsjahr', 'status'],
                condition=models.Q(status__in=['beschlossen', 'aktiv']),
                name='uniq_wp_wj_aktiv_beschlossen',
            ),
        ]

    def __str__(self):
        return f"WP {self.wirtschaftsjahr} [{self.status}]"


class WirtschaftsplanPosition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    wirtschaftsplan = models.ForeignKey(
        Wirtschaftsplan, on_delete=models.CASCADE, related_name='positionen',
    )
    konto = models.ForeignKey(
        'konten.Konto', on_delete=models.PROTECT, related_name='wp_positionen',
    )
    vs_code = models.CharField(max_length=3)
    betrag = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    verteilung_validiert = models.BooleanField(default=False)
    verteilung_freigegeben_trotz_diff = models.BooleanField(default=False)
    bemerkung = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        verbose_name = 'Wirtschaftsplan-Position'
        verbose_name_plural = 'Wirtschaftsplan-Positionen'
        ordering = ['konto__kontonummer']
        constraints = [
            models.UniqueConstraint(
                fields=['wirtschaftsplan', 'konto'],
                name='uniq_wp_position_wp_konto',
            ),
            models.CheckConstraint(
                check=models.Q(betrag__gte=0),
                name='wp_position_betrag_nicht_negativ',
            ),
        ]

    def __str__(self):
        return f"Pos {self.konto.kontonummer} — {self.betrag} € ({self.wirtschaftsplan})"


class WirtschaftsplanAnteil(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    position = models.ForeignKey(
        WirtschaftsplanPosition, on_delete=models.CASCADE, related_name='anteile',
    )
    einheit = models.ForeignKey(
        'objekte.Einheit', on_delete=models.PROTECT, related_name='wp_anteile',
    )
    vs_anteil_einheit = models.DecimalField(max_digits=18, decimal_places=6)
    vs_anteil_gesamt = models.DecimalField(max_digits=18, decimal_places=6)
    betrag_anteil = models.DecimalField(max_digits=12, decimal_places=2)
    monatsbetrag_anteil = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = 'Wirtschaftsplan-Anteil'
        verbose_name_plural = 'Wirtschaftsplan-Anteile'
        ordering = ['einheit__einheit_nr']
        constraints = [
            models.UniqueConstraint(
                fields=['position', 'einheit'],
                name='uniq_wp_anteil_position_einheit',
            ),
        ]

    def __str__(self):
        return f"Anteil {self.einheit.einheit_nr}: {self.betrag_anteil} € ({self.position})"
