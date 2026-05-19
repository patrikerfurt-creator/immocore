from decimal import Decimal
from uuid import uuid4
from datetime import date
from django.conf import settings
from django.db import models
from django.db.models import Q
from apps.objekte.models import Einheit


class SEPAMandat(models.Model):
    SEQUENCE_TYPE_CHOICES = [
        ('RCUR', 'Wiederkehrend (RCUR)'),
        ('FRST', 'Erstlastschrift (FRST)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    mandatsreferenz = models.CharField(max_length=35, unique=True)
    iban = models.CharField(max_length=34)
    bic = models.CharField(max_length=11, blank=True)
    unterzeichnet_am = models.DateField()
    aktiv = models.BooleanField(default=True)
    sequence_type = models.CharField(
        max_length=4,
        choices=SEQUENCE_TYPE_CHOICES,
        default='RCUR',
        verbose_name='Sequenz-Typ',
    )

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
    ibans = models.JSONField(default=list)
    briefanrede  = models.CharField(max_length=200, blank=True, default='')
    briefanrede2 = models.CharField(max_length=200, blank=True, default='')
    sepa_mandat = models.ForeignKey(
        SEPAMandat, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='personen'
    )

    _PAAR = {
        'Eheleute':      ('Frau',  'Herr'),
        'Herren':        ('Herr',  'Herr'),
        'Damen':         ('Frau',  'Frau'),
        'Herr und Frau': ('Frau',  'Herr'),
    }

    @staticmethod
    def _zeile(einzel_anrede: str, name: str, gross: bool) -> str:
        prefix = 'Sehr' if gross else 'sehr'
        endung = 'er' if einzel_anrede == 'Herr' else 'e'
        return f'{prefix} geehrt{endung} {einzel_anrede} {name},'

    @classmethod
    def auto_briefanreden(
        cls,
        anrede: str,
        nachname: str = '',
        nachname2: str = '',
        firmenname: str = '',
        ist_firma: bool = False,
    ) -> tuple[str, str]:
        if ist_firma or anrede == 'Firma':
            return 'Sehr geehrte Damen und Herren,', ''

        paar = cls._PAAR.get(anrede)
        if paar:
            a1, a2 = paar
            n1 = nachname.strip()
            n2 = (nachname2.strip() or nachname.strip())
            return cls._zeile(a1, n1, gross=True), cls._zeile(a2, n2, gross=False)

        if anrede == 'Herr':
            return cls._zeile('Herr', nachname.strip(), gross=True), ''
        if anrede == 'Frau':
            return cls._zeile('Frau', nachname.strip(), gross=True), ''

        return '', ''

    def save(self, *args, **kwargs):
        if not self.briefanrede:
            self.briefanrede, self.briefanrede2 = self.auto_briefanreden(
                self.anrede, self.nachname, self.nachname2, self.firmenname, self.ist_firma
            )
        super().save(*args, **kwargs)

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
    ende = models.DateField(null=True, blank=True, help_text='Null = aktuell aktiv')

    class Meta:
        verbose_name = 'Eigentumsverhältnis'
        verbose_name_plural = 'Eigentumsverhältnisse'
        ordering = ['-beginn']
        constraints = [
            models.UniqueConstraint(
                fields=['einheit'],
                condition=Q(ende__isnull=True),
                name='uniq_aktiver_vertrag_je_einheit',
            ),
        ]

    def hausgeld_aktuell(self, abrechnungsart_code: str, stichtag: date | None = None):
        """Letzter Betrag mit gueltig_ab <= stichtag für die Abrechnungsart."""
        stichtag = stichtag or date.today()
        return (
            HausgeldHistorie.objects
            .filter(
                eigentumsverhaeltnis=self,
                abrechnungsart__code=abrechnungsart_code,
                gueltig_ab__lte=stichtag,
            )
            .order_by('-gueltig_ab', '-erstellt_am')
            .values_list('betrag', flat=True)
            .first()
        )

    def hausgeld_alle_aktuell(self, stichtag: date | None = None) -> dict:
        """Dict {abr_code: betrag} mit je letztem gültigem Wert je Abrechnungsart."""
        stichtag = stichtag or date.today()
        rows = (
            HausgeldHistorie.objects
            .filter(eigentumsverhaeltnis=self, gueltig_ab__lte=stichtag)
            .order_by('abrechnungsart__code', '-gueltig_ab', '-erstellt_am')
            .distinct('abrechnungsart__code')
            .values_list('abrechnungsart__code', 'betrag')
        )
        return dict(rows)

    @property
    def hausgeld_soll(self):
        """Summe der aktuell gültigen Beträge über alle Abrechnungsarten."""
        betraege = self.hausgeld_alle_aktuell()
        if not betraege:
            return None
        return sum(betraege.values(), Decimal('0'))

    @property
    def ist_aktiv(self):
        return self.ende is None

    def __str__(self):
        return f"{self.person.name} — {self.einheit} (ab {self.beginn})"


class HausgeldHistorie(models.Model):
    QUELLE_CHOICES = [
        ('beschluss',      'Beschluss'),
        ('import',         'Import (Massenimport / Erstanlage)'),
        ('wirtschaftsplan', 'Wirtschaftsplan-Beschluss'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    eigentumsverhaeltnis = models.ForeignKey(
        EigentumsVerhaeltnis, on_delete=models.CASCADE, related_name='hausgeld_eintraege'
    )
    abrechnungsart = models.ForeignKey(
        'konten.Abrechnungsart',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='hausgeld_eintraege',
        help_text='z.B. 900 (Hausgeld), 911 (Rücklage I)',
    )
    ba = models.ForeignKey(
        'buchhaltung.Buchungsart',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='hausgeld_historien',
        help_text='Buchungsart aus dem Hausgeld-Nebenbuch (z.B. 900, 911)',
    )
    betrag = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text='Monatliches Soll in EUR. 0,00 ist erlaubt.',
    )
    gueltig_ab = models.DateField(
        help_text='Datum, ab dem dieser Betrag gilt. Typisch der 1. eines Monats.',
    )
    gueltig_bis = models.DateField(
        null=True, blank=True,
        help_text='Letzter Gültigkeitstag. NULL = aktuell gültig.',
    )
    wirtschaftsplan_jahr = models.PositiveIntegerField(
        null=True, blank=True,
        help_text='Wirtschaftsplan-Jahr, das diese Änderung ausgelöst hat.',
    )
    quelle = models.CharField(max_length=20, choices=QUELLE_CHOICES)
    beschluss = models.ForeignKey(
        'buchhaltung.WirtschaftsplanBeschluss',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='hausgeld_historien',
    )
    quelle_wp = models.ForeignKey(
        'abrechnung_wp.Wirtschaftsplan',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='hausgeld_historien',
    )
    import_referenz = models.CharField(
        max_length=100, null=True, blank=True,
        help_text='Pflicht wenn quelle=import. Identifiziert den Import-Lauf.',
    )
    bemerkung = models.CharField(max_length=200, blank=True)
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='hausgeld_historien'
    )
    erstellt_am = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        verbose_name = 'Hausgeld-Historie'
        verbose_name_plural = 'Hausgeld-Historien'
        ordering = ['eigentumsverhaeltnis', 'abrechnungsart', '-gueltig_ab']
        constraints = [
            models.UniqueConstraint(
                fields=['eigentumsverhaeltnis', 'abrechnungsart', 'gueltig_ab'],
                name='uniq_historie_je_vertrag_abrart_datum',
            ),
            models.CheckConstraint(
                name='hausgeld_historie_quelle_consistency',
                check=(
                    (Q(quelle='beschluss') & Q(beschluss__isnull=False) & Q(import_referenz__isnull=True) & Q(quelle_wp__isnull=True))
                    | (Q(quelle='import') & Q(beschluss__isnull=True) & Q(import_referenz__isnull=False) & Q(quelle_wp__isnull=True))
                    | (Q(quelle='wirtschaftsplan') & Q(beschluss__isnull=True) & Q(import_referenz__isnull=True) & Q(quelle_wp__isnull=False))
                ),
            ),
        ]
        indexes = [
            models.Index(
                fields=['eigentumsverhaeltnis', 'abrechnungsart', '-gueltig_ab'],
                name='idx_hausgeld_ev_abr_datum',
            ),
        ]

    def __str__(self):
        abr = self.abrechnungsart.code if self.abrechnungsart else '—'
        return f"{self.eigentumsverhaeltnis} — {abr} — {self.betrag} € ab {self.gueltig_ab}"


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

    class Meta:
        verbose_name = 'Mietvertrag'
        verbose_name_plural = 'Mietverträge'
        ordering = ['-beginn']

    def __str__(self):
        return f"{self.mieter.name} — {self.einheit} (ab {self.beginn})"
