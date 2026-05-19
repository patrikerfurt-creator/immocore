from uuid import uuid4
from django.db import models


class Objekt(models.Model):
    OBJEKT_TYP_CHOICES = [
        ('WEG', 'WEG'),
        ('ZH', 'ZH'),
        ('SEV', 'SEV'),
    ]
    STATUS_CHOICES = [
        ('aktiv', 'Aktiv'),
        ('archiviert', 'Archiviert'),
    ]

    id                       = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objektnummer             = models.CharField(max_length=20, unique=True, blank=True)
    objekt_typ               = models.CharField(max_length=10, choices=OBJEKT_TYP_CHOICES)
    bezeichnung              = models.CharField(max_length=255)
    kurzbezeichnung          = models.CharField(max_length=40, blank=True,
        help_text='Kurzbeschreibung für SEPA-Verwendungszweck (z.B. „Coventrystr. 32")')
    strasse                  = models.CharField(max_length=255)
    plz                      = models.CharField(max_length=10)
    ort                      = models.CharField(max_length=100)
    baujahr                  = models.IntegerField(null=True, blank=True)
    verwaltung_seit          = models.DateField()
    wirtschaftsjahr_start    = models.IntegerField(default=1)
    zahlungsfreigabe_grenzen = models.JSONField(default=dict)
    status                   = models.CharField(max_length=20, choices=STATUS_CHOICES, default='aktiv')
    umsatzsteuer_pflichtig   = models.BooleanField(default=False)
    glaeubiger_id            = models.CharField(max_length=35, blank=True, verbose_name='Gläubiger-ID')
    betreuer                 = models.ForeignKey(
        'auth.User', on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='betreute_objekte',
        verbose_name='Objektbetreuer',
    )
    betreuer_vertretung      = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='vertretene_objekte',
        verbose_name='Betreuer-Vertretung',
    )
    auto_pipeline_aktiv      = models.BooleanField(
        default=True,
        verbose_name='Auto-Pipeline aktiv',
        help_text='Deaktivieren um dieses Objekt aus der monatlichen Auto-Pipeline auszuschließen.',
    )
    auto_verbuchen_aktiv     = models.BooleanField(
        default=True,
        verbose_name='Auto-Verbuchen aktiv (E-Banking)',
        help_text='Eindeutig erkannte Bankbuchungen (Konfidenz 1.0) automatisch ins Hauptbuch übernehmen.',
    )
    bundesland               = models.CharField(
        max_length=2,
        default='HE',
        verbose_name='Bundesland (ISO)',
        help_text='ISO-3166-2 Bundesland-Kürzel für Bankfeiertage (z.B. HE, BY, NW).',
    )

    class Meta:
        verbose_name        = 'Objekt'
        verbose_name_plural = 'Objekte'
        ordering            = ['bezeichnung']

    def __str__(self):
        return f"{self.bezeichnung} ({self.objekt_typ})"


class Eingang(models.Model):
    id          = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt      = models.ForeignKey(Objekt, on_delete=models.CASCADE, related_name='eingaenge')
    bezeichnung = models.CharField(max_length=255)
    strasse     = models.CharField(max_length=255)
    plz         = models.CharField(max_length=10)
    ort         = models.CharField(max_length=100)

    class Meta:
        verbose_name        = 'Eingang'
        verbose_name_plural = 'Eingänge'
        ordering            = ['bezeichnung']

    def __str__(self):
        return f"{self.bezeichnung} ({self.objekt.bezeichnung})"


class Bankkonto(models.Model):
    KONTO_TYP_CHOICES = [
        ('bewirtschaftung', 'Bewirtschaftung'),
        ('ruecklage', 'Rücklage'),
    ]

    id           = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt       = models.ForeignKey(Objekt, on_delete=models.CASCADE, related_name='bankkonten')
    konto_typ    = models.CharField(max_length=20, choices=KONTO_TYP_CHOICES)
    bezeichnung  = models.CharField(max_length=255)
    iban         = models.CharField(max_length=34, blank=True)
    bic          = models.CharField(max_length=11, blank=True)
    kontoinhaber = models.CharField(max_length=255, blank=True)
    reihenfolge     = models.PositiveIntegerField(default=1)
    aktiv           = models.BooleanField(default=True)
    zahlungsverkehr = models.BooleanField(
        default=False,
        verbose_name='Für Zahlungsverkehr',
        help_text='Standardkonto für Überweisungen – pro Objekt nur eines.',
    )

    class Meta:
        verbose_name        = 'Bankkonto'
        verbose_name_plural = 'Bankkonten'
        ordering            = ['reihenfolge', 'bezeichnung']

    def save(self, *args, **kwargs):
        if self.zahlungsverkehr:
            Bankkonto.objects.filter(
                objekt=self.objekt, zahlungsverkehr=True
            ).exclude(pk=self.pk).update(zahlungsverkehr=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.bezeichnung} ({self.iban})"


class Einheit(models.Model):
    EINHEIT_TYP_CHOICES = [
        ('Wohnung', 'Wohnung'),
        ('Gewerbe', 'Gewerbe'),
        ('Stellplatz', 'Stellplatz'),
        ('Sonstiges', 'Sonstiges'),
    ]
    UMSATZSTEUER_CHOICES = [
        ('brutto', 'Brutto'),
        ('netto', 'Netto'),
    ]

    id             = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt         = models.ForeignKey(Objekt, on_delete=models.CASCADE, related_name='einheiten')
    eingang        = models.ForeignKey(Eingang, on_delete=models.SET_NULL, null=True, blank=True, related_name='einheiten')
    flaechennummer = models.CharField(max_length=20, blank=True)
    einheit_nr     = models.CharField(max_length=20)
    einheit_typ    = models.CharField(max_length=20, choices=EINHEIT_TYP_CHOICES)
    lage           = models.CharField(max_length=255)
    umsatzsteuer_abrechnungsart = models.CharField(max_length=10, choices=UMSATZSTEUER_CHOICES, null=True, blank=True)

    class Meta:
        verbose_name        = 'Einheit'
        verbose_name_plural = 'Einheiten'
        ordering            = ['flaechennummer']

    def __str__(self):
        return f"{self.einheit_nr} — {self.lage} ({self.objekt.bezeichnung})"


class Verteilerschluessel(models.Model):
    """Verteilerschlüssel-Konfiguration je Objekt (entspricht VerteilerschluesselConfig in Spec)."""

    VS_TYP_CHOICES = [
        ('flaeche',   'Fläche'),
        ('mea',       'MEA'),
        ('kopf',      'Kopf'),
        ('direkt',    'Direkt'),
        ('verbrauch', 'Verbrauch'),
    ]

    id          = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt      = models.ForeignKey(Objekt, on_delete=models.CASCADE, related_name='verteilerschluessel')
    schluessel  = models.CharField(max_length=3, blank=True)   # '001', '010', '030', …
    bezeichnung = models.CharField(max_length=80)
    vs_typ      = models.CharField(max_length=20, choices=VS_TYP_CHOICES, null=True, blank=True)
    aktiv       = models.BooleanField(default=True)

    # Legacy-Felder – bleiben für Abwärtskompatibilität bis vollständige Migration
    schluessel_typ = models.CharField(max_length=20, blank=True, default='')
    einheit        = models.CharField(max_length=20, default='')
    reihenfolge    = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name        = 'Verteilerschlüssel'
        verbose_name_plural = 'Verteilerschlüssel'
        ordering            = ['objekt', 'schluessel', 'bezeichnung']
        unique_together     = [['objekt', 'bezeichnung']]

    def __str__(self):
        return f"{self.schluessel} {self.bezeichnung} ({self.objekt.bezeichnung})"


class VerteilerschluesselWert(models.Model):
    """Beteiligung einer Einheit an einem Verteilerschlüssel (entspricht VSBeteiligung in Spec)."""

    QUELLE_CHOICES = [
        ('stammdaten', 'Stammdaten'),
        ('manuell',    'Manuell'),
    ]

    id                 = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    schluessel         = models.ForeignKey(Verteilerschluessel, on_delete=models.CASCADE, related_name='werte')
    einheit            = models.ForeignKey(Einheit, on_delete=models.CASCADE, related_name='verteilerschluessel_werte')
    wirtschaftsjahr    = models.IntegerField(default=0)          # 0 = zeitlos (flaeche/mea/kopf)
    beteiligt          = models.BooleanField(default=True)
    wert               = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    einzelwert_einheit = models.CharField(max_length=20, blank=True, default='')
    quelle             = models.CharField(max_length=20, choices=QUELLE_CHOICES, default='stammdaten')

    class Meta:
        verbose_name        = 'Verteilerschlüssel-Wert'
        verbose_name_plural = 'Verteilerschlüssel-Werte'
        ordering            = ['schluessel', 'einheit__einheit_nr']
        unique_together     = [['schluessel', 'einheit', 'wirtschaftsjahr']]

    def __str__(self):
        return f"{self.schluessel.bezeichnung}: {self.einheit.einheit_nr} = {self.wert}"


# ---------------------------------------------------------------------------
# Wirtschaftsjahr — eigenständige Entität je Objekt (Spec v1.0 Kap. 3.1)
# ---------------------------------------------------------------------------

class Wirtschaftsjahr(models.Model):
    STATUS_CHOICES = [
        ('offen',         'Offen'),
        ('abgeschlossen', 'Abgeschlossen'),
    ]

    id            = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt        = models.ForeignKey(Objekt, on_delete=models.CASCADE, related_name='wirtschaftsjahre')
    jahr          = models.IntegerField()
    beginn_monat  = models.IntegerField()
    status        = models.CharField(max_length=20, choices=STATUS_CHOICES, default='offen')
    vorjahr       = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='folgejahre',
    )
    eroeffnet_am  = models.DateTimeField(auto_now_add=True)
    eroeffnet_von = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='eroeffnete_wirtschaftsjahre',
    )
    abgeschlossen_am = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name        = 'Wirtschaftsjahr'
        verbose_name_plural = 'Wirtschaftsjahre'
        ordering            = ['objekt', 'jahr']
        constraints = [
            models.UniqueConstraint(fields=['objekt', 'jahr'], name='unique_objekt_wirtschaftsjahr'),
            models.CheckConstraint(check=models.Q(jahr__gte=2000), name='wirtschaftsjahr_min_2000'),
        ]

    @property
    def beginn_datum(self):
        from datetime import date
        return date(self.jahr, self.beginn_monat, 1)

    @property
    def ende_datum(self):
        from datetime import date, timedelta
        return date(self.jahr + 1, self.beginn_monat, 1) - timedelta(days=1)

    def __str__(self):
        return f"WJ {self.jahr} ({self.objekt.bezeichnung}) [{self.status}]"


# ---------------------------------------------------------------------------
# EinheitVerbrauch — Verbrauchswerte je Einheit, WJ und VS-Code (Spec v1.0 Kap. 3.4)
# ---------------------------------------------------------------------------

class EinheitVerbrauch(models.Model):
    QUELLE_CHOICES = [
        ('manuell',        'Manuell'),
        ('heiwako_import', 'HEIWAKO-Import'),
    ]
    VS_CODE_CHOICES = [
        ('140', '140'), ('141', '141'), ('142', '142'),
        ('143', '143'), ('144', '144'), ('145', '145'),
    ]

    id              = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    wirtschaftsjahr = models.ForeignKey(
        Wirtschaftsjahr, on_delete=models.CASCADE, related_name='einheit_verbraeuche',
    )
    einheit         = models.ForeignKey(Einheit, on_delete=models.CASCADE, related_name='verbraeuche')
    vs_code         = models.CharField(max_length=3, choices=VS_CODE_CHOICES)
    wert            = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    einheit_text    = models.CharField(max_length=20, blank=True)
    quelle          = models.CharField(max_length=20, choices=QUELLE_CHOICES, null=True, blank=True)

    class Meta:
        verbose_name        = 'Einheit-Verbrauch'
        verbose_name_plural = 'Einheit-Verbräuche'
        constraints = [
            models.UniqueConstraint(
                fields=['wirtschaftsjahr', 'einheit', 'vs_code'],
                name='unique_einheit_verbrauch',
            ),
            models.CheckConstraint(
                check=models.Q(vs_code__in=['140', '141', '142', '143', '144', '145']),
                name='einheit_verbrauch_valid_vs_code',
            ),
        ]

    def __str__(self):
        return f"VS {self.vs_code}: {self.einheit} WJ {self.wirtschaftsjahr.jahr}"
