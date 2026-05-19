from uuid import uuid4
from django.conf import settings
from django.db import models
from django.db.models import Q


class Wirtschaftsplan(models.Model):
    STATUS_CHOICES = [
        ('entwurf',     'Entwurf'),
        ('beschlossen', 'Beschlossen'),
        ('aktiv',       'Aktiv'),
        ('aufgehoben',  'Aufgehoben'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    wirtschaftsjahr = models.ForeignKey(
        'objekte.Wirtschaftsjahr',
        on_delete=models.CASCADE,
        related_name='wirtschaftsplaene',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='entwurf')
    gesamtsumme = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gesamtsumme_hausgeld = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gesamtsumme_ruecklage = models.JSONField(default=dict)
    beschluss_datum = models.DateField(null=True, blank=True)
    beschluss_tagesordnungspunkt = models.CharField(max_length=200, null=True, blank=True)
    wirkung_ab = models.DateField()
    bemerkung = models.TextField(null=True, blank=True)
    aufhebt_wp = models.ForeignKey(
        'self',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='aufgehoben_durch',
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='wirtschaftsplaene_erstellt',
    )
    beschlossen_am = models.DateTimeField(null=True, blank=True)
    beschlossen_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name='wirtschaftsplaene_beschlossen',
    )

    class Meta:
        verbose_name = 'Wirtschaftsplan'
        verbose_name_plural = 'Wirtschaftspläne'
        ordering = ['-erstellt_am']
        constraints = [
            models.UniqueConstraint(
                fields=['wirtschaftsjahr'],
                condition=Q(status='beschlossen'),
                name='uniq_beschlossener_wp_je_wj',
            ),
            models.UniqueConstraint(
                fields=['wirtschaftsjahr'],
                condition=Q(status='aktiv'),
                name='uniq_aktiver_wp_je_wj',
            ),
        ]

    def __str__(self):
        return f"WP {self.wirtschaftsjahr} [{self.status}]"


class WirtschaftsplanPosition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    wirtschaftsplan = models.ForeignKey(
        Wirtschaftsplan,
        on_delete=models.CASCADE,
        related_name='positionen',
    )
    konto = models.ForeignKey(
        'konten.Konto',
        on_delete=models.PROTECT,
        related_name='wp_positionen',
    )
    vs_code = models.CharField(max_length=3)  # snapshot of KontoVerteilerSchluessel.vs_code
    betrag = models.DecimalField(max_digits=12, decimal_places=2)
    verteilung_validiert = models.BooleanField(default=False)
    verteilung_freigegeben_trotz_diff = models.BooleanField(default=False)
    bemerkung = models.CharField(max_length=500, null=True, blank=True)

    class Meta:
        verbose_name = 'Wirtschaftsplan-Position'
        verbose_name_plural = 'Wirtschaftsplan-Positionen'
        ordering = ['konto__kontonummer']
        constraints = [
            models.UniqueConstraint(
                fields=['wirtschaftsplan', 'konto'],
                name='uniq_wp_position_je_konto',
            ),
            models.CheckConstraint(
                check=Q(betrag__gte=0),
                name='wp_position_betrag_nicht_negativ',
            ),
        ]

    def __str__(self):
        return f"{self.wirtschaftsplan} — Konto {self.konto.kontonummer} — {self.betrag} €"


class WirtschaftsplanAnteil(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    position = models.ForeignKey(
        WirtschaftsplanPosition,
        on_delete=models.CASCADE,
        related_name='anteile',
    )
    einheit = models.ForeignKey(
        'objekte.Einheit',
        on_delete=models.PROTECT,
        related_name='wp_anteile',
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
                name='uniq_wp_anteil_je_einheit',
            ),
        ]

    def __str__(self):
        return f"{self.position} — Einheit {self.einheit.einheit_nr} — {self.betrag_anteil} €"
