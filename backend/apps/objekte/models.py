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
    reihenfolge  = models.PositiveIntegerField(default=1)
    aktiv        = models.BooleanField(default=True)

    class Meta:
        verbose_name        = 'Bankkonto'
        verbose_name_plural = 'Bankkonten'
        ordering            = ['reihenfolge', 'bezeichnung']

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
