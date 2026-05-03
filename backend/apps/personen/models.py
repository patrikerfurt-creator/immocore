from decimal import Decimal
from uuid import uuid4
from datetime import date
from django.conf import settings
from django.db import models
from django.db.models import Max
from apps.objekte.models import Einheit


class SEPAMandat(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    mandatsreferenz = models.CharField(max_length=35, unique=True)
    iban = models.CharField(max_length=34)
    bic = models.CharField(max_length=11, blank=True)
    unterzeichnet_am = models.DateField()
    aktiv = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'SEPA-Mandat'
        verbose_name_plural = 'SEPA-Mandate'
        ordering = ['-unterzeichnet_am']

    def __str__(self):
        return f"{self.mandatsreferenz} ({self.iban})"


class Person(models.Model):
    PERSON_TYP_CHOICES = [
        ('100', 'Eigentümer'),
        ('200', 'Mieter'),
        ('300', 'Kreditor'),
        ('400', 'Sonstiges'),
    ]

    ANREDE_CHOICES = [
        ('Herr', 'Herr'),
        ('Frau', 'Frau'),
        ('Eheleute', 'Eheleute'),
        ('Herren', 'Herren'),
        ('Damen', 'Damen'),
        ('Herr und Frau', 'Herr und Frau'),
        ('Firma', 'Firma'),
        ('', '–'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    personennummer = models.CharField(max_length=20, unique=True, blank=True)
    person_typ = models.CharField(max_length=100, choices=PERSON_TYP_CHOICES)
    anrede = models.CharField(max_length=20, blank=True, default='', choices=ANREDE_CHOICES)
    ist_firma = models.BooleanField(default=False)
    vorname = models.CharField(max_length=100, blank=True)
    nachname = models.CharField(max_length=100, blank=True)
    vorname2 = models.CharField(max_length=100, blank=True)
    nachname2 = models.CharField(max_length=100, blank=True)
    firmenname = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    telefon = models.CharField(max_length=50, blank=True)
    adresse = models.TextField(blank=True)
    ibans = models.JSONField(default=list)  # Liste aller bekannten IBANs inkl. historischer
    sepa_mandat = models.ForeignKey(
        SEPAMandat, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='personen'
    )

    class Meta:
        verbose_name = 'Person'
        verbose_name_plural = 'Personen'
        ordering = ['nachname', 'vorname', 'firmenname']

    @property
    def name(self):
        if self.ist_firma:
            return self.firmenname
        name1 = f"{self.vorname} {self.nachname}".strip()
        name2 = f"{self.vorname2} {self.nachname2}".strip()
        if name2:
            return f"{name1} und {name2}"
        return name1

    def __str__(self):
        return self.name or f"Person {self.id}"


class EigentumsVerhaeltnis(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    einheit = models.ForeignKey(
        Einheit, on_delete=models.CASCADE, related_name='eigentumsverhaeltnisse'
    )
    person = models.ForeignKey(
        Person, on_delete=models.PROTECT, related_name='eigentumsverhaeltnisse'
    )
    beginn = models.DateField()
    ende = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = 'Eigentumsverhältnis'
        verbose_name_plural = 'Eigentumsverhältnisse'
        ordering = ['-beginn']

    @property
    def hausgeld_soll(self):
        """Summe der jeweils neuesten Beträge pro Kontoart (gueltig_ab <= today)."""
        today = date.today()
        latest_per_art = (
            self.hausgeld_historie
            .filter(gueltig_ab__lte=today)
            .values('kontoart')
            .annotate(max_datum=Max('gueltig_ab'))
        )
        if not latest_per_art.exists():
            return None
        total = Decimal('0')
        for row in latest_per_art:
            eintrag = self.hausgeld_historie.filter(
                kontoart=row['kontoart'],
                gueltig_ab=row['max_datum'],
            ).first()
            if eintrag:
                total += eintrag.betrag
        return total

    @property
    def ist_aktiv(self):
        return self.ende is None

    def __str__(self):
        return f"{self.person.name} — {self.einheit} (ab {self.beginn})"


class HausgeldHistorie(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    eigentumsverhaeltnis = models.ForeignKey(
        EigentumsVerhaeltnis, on_delete=models.CASCADE, related_name='hausgeld_historie'
    )
    betrag = models.DecimalField(max_digits=10, decimal_places=2)
    gueltig_ab = models.DateField()
    kontoart = models.CharField(max_length=10, blank=True, default='', help_text='z.B. .900, .911, .912, .940')
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='hausgeld_historien'
    )

    class Meta:
        verbose_name = 'Hausgeld-Historie'
        verbose_name_plural = 'Hausgeld-Historien'
        ordering = ['-gueltig_ab']

    def __str__(self):
        return f"{self.eigentumsverhaeltnis} — {self.betrag} € ab {self.gueltig_ab}"


class Mietvertrag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    einheit = models.ForeignKey(
        Einheit, on_delete=models.CASCADE, related_name='mietvertraege'
    )
    mieter = models.ForeignKey(
        Person, on_delete=models.PROTECT, related_name='mietvertraege'
    )
    beginn = models.DateField()
    ende = models.DateField(null=True, blank=True)
    kaltmiete = models.DecimalField(max_digits=10, decimal_places=2)
    nebenkosten_vorauszahlung = models.DecimalField(
        max_digits=10, decimal_places=2, default=0
    )
    # ZH/SEV: extend in Phase 2

    class Meta:
        verbose_name = 'Mietvertrag'
        verbose_name_plural = 'Mietverträge'
        ordering = ['-beginn']

    def __str__(self):
        return f"{self.mieter.name} — {self.einheit} (ab {self.beginn})"
