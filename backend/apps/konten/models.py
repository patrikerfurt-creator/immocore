from uuid import uuid4
from django.db import models
from apps.objekte.models import Objekt, Bankkonto, Wirtschaftsjahr
from apps.personen.models import Person, EigentumsVerhaeltnis


class Konto(models.Model):
    class Kontoart(models.TextChoices):
        STANDARD   = 'standard',   'Standard'
        SUMMIERUNG = 'summierung', 'Summierungskonto'
        UNTERKONTO = 'unterkonto', 'Unterkonto'

    id              = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    wirtschaftsjahr = models.ForeignKey(
        Wirtschaftsjahr, on_delete=models.CASCADE,
        related_name='konten', null=True, blank=True,
    )
    kontonummer         = models.CharField(max_length=6)
    kontoname           = models.CharField(max_length=120)
    abrechnungsart      = models.CharField(max_length=3, null=True, blank=True)
    direktes_buchen     = models.BooleanField(default=True)
    verteilerschluessel = models.CharField(max_length=3, null=True, blank=True)
    kontoart            = models.CharField(max_length=12, choices=Kontoart.choices, default=Kontoart.STANDARD)
    arge_konto          = models.BooleanField(default=False)
    arge_kostenart      = models.CharField(max_length=20, null=True, blank=True)
    aktiv               = models.BooleanField(default=True)

    class Meta:
        verbose_name        = 'Konto (Sachkonto)'
        verbose_name_plural = 'Konten (Sachkonten)'
        ordering            = ['kontonummer']
        constraints = [
            models.UniqueConstraint(
                fields=['wirtschaftsjahr', 'kontonummer'],
                name='unique_wj_kontonummer',
                condition=models.Q(wirtschaftsjahr__isnull=False),
            ),
        ]

    @property
    def objekt(self):
        if self.wirtschaftsjahr_id:
            return self.wirtschaftsjahr.objekt
        return None

    def save(self, *args, **kwargs):
        if self.kontoart == self.Kontoart.SUMMIERUNG:
            self.direktes_buchen = False
        if self.kontoart == self.Kontoart.UNTERKONTO:
            self.arge_konto = True
        super().save(*args, **kwargs)

    def __str__(self):
        wj = self.wirtschaftsjahr
        objekt_str = wj.objekt.bezeichnung if wj else '?'
        return f"{self.kontonummer} — {self.kontoname} ({objekt_str})"


# ---------------------------------------------------------------------------
# KontoVerteilerSchluessel — VS-Zuordnung je Konto (Spec v1.0 Kap. 3.3)
# ---------------------------------------------------------------------------

class KontoVerteilerSchluessel(models.Model):
    id         = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    konto      = models.ForeignKey(Konto, on_delete=models.CASCADE, related_name='vs_zuordnungen')
    vs_code    = models.CharField(max_length=3)
    gueltig_ab = models.DateField()

    class Meta:
        verbose_name        = 'Konto-Verteilerschlüssel'
        verbose_name_plural = 'Konto-Verteilerschlüssel'
        ordering            = ['konto', 'gueltig_ab']

    def __str__(self):
        return f"VS {self.vs_code} → {self.konto.kontonummer} ab {self.gueltig_ab}"


class Personenkonto(models.Model):
    STATUS_CHOICES = [
        ('aktiv', 'Aktiv'),
        ('archiviert', 'Archiviert'),
    ]

    id          = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt      = models.ForeignKey(Objekt, on_delete=models.CASCADE, related_name='personenkonten')
    eigentuemer = models.ForeignKey(Person, on_delete=models.PROTECT, related_name='personenkonten')
    vertrag     = models.OneToOneField(EigentumsVerhaeltnis, on_delete=models.CASCADE, related_name='personenkonto')
    kontonummer = models.CharField(max_length=4)
    status      = models.CharField(max_length=20, choices=STATUS_CHOICES, default='aktiv')
    archiviert_am = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name        = 'Personenkonto'
        verbose_name_plural = 'Personenkonten'
        ordering            = ['objekt', 'kontonummer']
        unique_together     = [['objekt', 'kontonummer']]

    def __str__(self):
        return f"{self.kontonummer} — {self.eigentuemer.name} ({self.objekt.bezeichnung})"


class Abrechnungsart(models.Model):
    id          = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt      = models.ForeignKey(Objekt, on_delete=models.CASCADE, related_name='abrechnungsarten')
    code        = models.CharField(max_length=3)
    bezeichnung = models.CharField(max_length=100)
    aktiv       = models.BooleanField(default=True)

    class Meta:
        verbose_name        = 'Abrechnungsart'
        verbose_name_plural = 'Abrechnungsarten'
        ordering            = ['code']
        unique_together     = [['objekt', 'code']]

    def __str__(self):
        return f"{self.code} — {self.bezeichnung}"


class Unterkonto(models.Model):
    id           = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    personenkonto = models.ForeignKey(Personenkonto, on_delete=models.CASCADE, related_name='unterkonten')
    suffix       = models.CharField(max_length=4)
    bezeichnung  = models.CharField(max_length=255)
    sachkonto    = models.ForeignKey(Konto, on_delete=models.PROTECT, null=True, blank=True, related_name='unterkonten')
    bankkonto    = models.ForeignKey(Bankkonto, on_delete=models.SET_NULL, null=True, blank=True, related_name='unterkonten')

    class Meta:
        verbose_name        = 'Unterkonto'
        verbose_name_plural = 'Unterkonten'
        ordering            = ['personenkonto', 'suffix']
        unique_together     = [['personenkonto', 'suffix']]

    @property
    def volle_kontonummer(self):
        return f"{self.personenkonto.kontonummer}{self.suffix}"

    def __str__(self):
        return f"{self.volle_kontonummer} — {self.bezeichnung}"
