from uuid import uuid4
from django.conf import settings
from django.db import models
from apps.objekte.models import Objekt
from apps.personen.models import Person
from apps.konten.models import Konto
from apps.buchhaltung.models import Buchung


class Kreditor(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    kreditorennummer = models.CharField(
        max_length=10, blank=True, null=True, unique=True,
        help_text='Automatisch vergeben ab 70000',
    )
    name = models.CharField(max_length=255)
    name_normalisiert = models.CharField(max_length=255, blank=True)
    iban = models.CharField(max_length=34, blank=True, null=True, unique=True)
    bic  = models.CharField(max_length=11, blank=True)
    strasse = models.CharField(max_length=255, blank=True)
    plz = models.CharField(max_length=10, blank=True)
    ort = models.CharField(max_length=100, blank=True)
    telefon = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    aktiv = models.BooleanField(default=True)
    erstellt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Kreditor'
        verbose_name_plural = 'Kreditoren'
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.kreditorennummer:
            from django.db import transaction
            with transaction.atomic():
                existing = list(
                    Kreditor.objects
                    .filter(kreditorennummer__regex=r'^\d+$')
                    .select_for_update()
                    .values_list('kreditorennummer', flat=True)
                )
                numeric = [int(n) for n in existing if int(n) >= 70000] if existing else []
                self.kreditorennummer = str((max(numeric) + 1) if numeric else 70000)
        super().save(*args, **kwargs)

    def __str__(self):
        nr = f" [{self.kreditorennummer}]" if self.kreditorennummer else ""
        return f"{self.name}{nr}" + (f" ({self.iban})" if self.iban else "")


class Rechnung(models.Model):
    STATUS_CHOICES = [
        ('importiert',    'Importiert'),
        ('duplikat',      'Duplikat'),
        ('prueffall',     'Prüffall (alt)'),
        ('erfasst',       'Erfasst'),
        # --- Erkennungs-Pipeline (neu) ---
        ('erkannt',       'Erkannt (Stufe 1)'),
        ('pruefung_match','Prüffall (Stufe 2)'),
        ('nicht_erkannt', 'Nicht erkannt (Stufe 3)'),
        # ---------------------------------
        ('in_pruefung',   'In Prüfung'),
        ('freigegeben',   'Freigegeben'),
        ('gebucht',       'Gebucht'),
        ('bezahlt',       'Bezahlt'),
        ('abgelehnt',     'Abgelehnt'),
        ('fehler',        'Fehler'),
    ]
    ERKENNUNGS_STUFE_CHOICES = [
        ('1', 'Stufe 1 — Erkannt'),
        ('2', 'Stufe 2 — Prüffall (Objektbetreuer)'),
        ('3', 'Stufe 3 — Nicht erkannt (Frontoffice)'),
    ]
    ROUTING_ZIEL_CHOICES = [
        ('limit_workflow',  'Limit-Workflow'),
        ('objektbetreuer',  'Objektbetreuer'),
        ('frontoffice',     'Frontoffice-Inbox'),
    ]
    DUPLIKAT_TYP_CHOICES = [
        ('hash', 'Exaktes Duplikat (Hash)'),
        ('rechnungsnummer', 'Gleiche Rechnungsnummer'),
        ('iban_betrag_datum', 'IBAN + Betrag + Datum'),
        ('unscharf', 'Unscharfe Übereinstimmung'),
        ('ocr_unvollstaendig', 'OCR unvollständig'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt = models.ForeignKey(
        Objekt, on_delete=models.PROTECT, related_name='rechnungen',
        null=True, blank=True,
    )
    # Kreditor (automatisch erkannt)
    kreditor = models.ForeignKey(
        Kreditor, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='rechnungen',
    )
    # Person-Lieferant (manuell zugeordnet, optional)
    lieferant = models.ForeignKey(
        Person, on_delete=models.PROTECT, null=True, blank=True,
        related_name='rechnungen_als_lieferant',
    )
    # Aus OCR extrahierte Felder
    dateiname = models.CharField(max_length=500, blank=True)
    pfad = models.CharField(max_length=1000, blank=True)
    sha256_hash = models.CharField(max_length=64, blank=True, db_index=True)
    lieferant_name = models.CharField(max_length=255, blank=True)
    lieferant_normalisiert = models.CharField(max_length=255, blank=True)
    lieferant_iban = models.CharField(max_length=34, blank=True)
    rechnungsnummer = models.CharField(max_length=100, blank=True)
    rechnungsnummer_normalisiert = models.CharField(max_length=100, blank=True)
    rechnungsdatum = models.DateField(null=True, blank=True)
    faelligkeitsdatum = models.DateField(null=True, blank=True)
    betrag_netto = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    betrag_brutto = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    mwst_satz = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    waehrung = models.CharField(max_length=3, default='EUR')
    leistungsbeschreibung = models.TextField(blank=True)
    textauszug = models.TextField(blank=True)
    # Status & Duplikat
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='importiert')
    duplikat_typ = models.CharField(max_length=30, choices=DUPLIKAT_TYP_CHOICES, blank=True)
    duplikat_von = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='duplikate',
    )
    verarbeitungsnotiz = models.TextField(blank=True)
    # Buchhaltung
    kostenstelle = models.ForeignKey(
        Konto, on_delete=models.PROTECT, null=True, blank=True,
        related_name='rechnungen',
    )
    pdf_upload = models.FileField(upload_to='rechnungen/', blank=True)
    ki_extraktion = models.JSONField(null=True, blank=True)
    buchung = models.ForeignKey(
        Buchung, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='rechnung',
    )
    kundennummer = models.CharField(max_length=50, blank=True)
    vorgeschlagenes_konto = models.ForeignKey(
        Konto, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='vorschlaege',
    )
    erfasst_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='erfasste_rechnungen',
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)

    # --- Erkennungs-Pipeline (Phase 3-Erweiterung) ---
    leistungstext = models.TextField(blank=True, help_text='Normierter Leistungstext aus OCR/XRechnung')
    leistungstext_hash = models.CharField(max_length=64, blank=True, db_index=True)
    erkennungs_stufe = models.CharField(
        max_length=3, null=True, blank=True, choices=ERKENNUNGS_STUFE_CHOICES,
    )
    routing_ziel = models.CharField(
        max_length=20, blank=True, choices=ROUTING_ZIEL_CHOICES,
        help_text='Ergebnis Phase B: limit_workflow | objektbetreuer | frontoffice',
    )
    erkennungs_konfidenz = models.JSONField(
        null=True, blank=True,
        help_text='{"kreditor": 0.95, "objekt": 0.80, "konto": 0.0}',
    )
    zugewiesen_an = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='zugewiesene_rechnungen',
    )
    match_regel = models.ForeignKey(
        'RechnungsMatchRegel', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='angewendet_auf',
    )
    # --- OP-Buchung (Kassenprinzip §28 WEG) ---
    aufwandskonto = models.ForeignKey(
        Konto, on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='rechnungen_als_aufwand',
        help_text='Aufwandskonto (50000–55999), wird bei Zahlung gebucht',
    )
    op_buchung = models.OneToOneField(
        Buchung, on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='rechnung_op',
        help_text='Phase-1-Buchung bei Freigabe (reserviert für Kreditor-Subledger)',
    )
    aufwand_buchung = models.OneToOneField(
        Buchung, on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='rechnung_aufwand',
        help_text='Phase-2-Buchung: Aufwand / Bank bei Zahlung',
    )
    sepa_lastschrift = models.BooleanField(
        default=False,
        help_text='Zahlung erfolgt per SEPA-Lastschrift (Abbuchung durch Kreditor)',
    )

    class Meta:
        verbose_name = 'Rechnung'
        verbose_name_plural = 'Rechnungen'
        ordering = ['-erstellt_am']

    def __str__(self):
        name = (
            self.kreditor.name if self.kreditor
            else self.lieferant.name if self.lieferant
            else self.lieferant_name or '?'
        )
        return f"Rechnung {self.rechnungsnummer or self.id} — {name} | {self.betrag_brutto} € [{self.status}]"


class KreditorRegel(models.Model):
    """Gelernte Zuordnung: Kreditor (+ optionale Kundennummer) → Objekt + Konto."""
    kreditor = models.ForeignKey(Kreditor, on_delete=models.CASCADE, related_name='regeln')
    kundennummer = models.CharField(max_length=50, blank=True)
    objekt = models.ForeignKey(
        Objekt, on_delete=models.SET_NULL, null=True, blank=True,
    )
    konto = models.ForeignKey(
        Konto, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='kreditor_regeln',
    )
    treffer = models.IntegerField(default=1)
    zuletzt_angewendet = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('kreditor', 'kundennummer')]
        verbose_name = 'Kreditor-Regel'
        verbose_name_plural = 'Kreditor-Regeln'

    def __str__(self):
        return f"{self.kreditor.name} | '{self.kundennummer}' → {self.objekt} / {self.konto}"


class Freigabe(models.Model):
    ENTSCHEIDUNG_CHOICES = [
        ('freigegeben', 'Freigegeben'),
        ('abgelehnt', 'Abgelehnt'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    rechnung = models.ForeignKey(Rechnung, on_delete=models.CASCADE, related_name='freigaben')
    bearbeiter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='freigaben',
    )
    rolle = models.CharField(max_length=50)
    entscheidung = models.CharField(max_length=20, choices=ENTSCHEIDUNG_CHOICES)
    begruendung = models.TextField(blank=True)
    zeitstempel = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Freigabe'
        verbose_name_plural = 'Freigaben'
        ordering = ['-zeitstempel']

    def __str__(self):
        return f"Freigabe {self.rechnung_id} [{self.entscheidung}] von {self.bearbeiter}"


class RechnungsMatchRegel(models.Model):
    """Lernende Zuordnungsregel: (Kreditor, Objekt, Leistungstext-Hash) → Aufwandskonto."""

    STATUS_CHOICES = [
        ('aktiv',   'Aktiv'),
        ('veraltet','Veraltet'),
    ]
    ERSTELLT_AUS_CHOICES = [
        ('pruefung',            'Prüffall-Identifikation'),
        ('freigabe_korrektur',  'Freigabe-Korrektur'),
        ('manuell',             'Manuelle Erfassung'),
    ]

    id                  = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    kreditor            = models.ForeignKey(
        Kreditor, on_delete=models.CASCADE, related_name='match_regeln',
    )
    objekt              = models.ForeignKey(
        Objekt, on_delete=models.CASCADE, related_name='match_regeln',
    )
    leistungstext_hash  = models.CharField(max_length=64)
    leistungstext_sample= models.TextField(blank=True, help_text='Original-Leistungstext der ersten Bestätigung')
    aufwandskonto       = models.ForeignKey(
        Konto, on_delete=models.PROTECT, related_name='match_regeln',
    )
    status              = models.CharField(max_length=10, choices=STATUS_CHOICES, default='aktiv')
    trefferzahl         = models.PositiveIntegerField(default=1)
    erstellt_durch      = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='erstellte_match_regeln',
    )
    erstellt_aus        = models.CharField(max_length=25, choices=ERSTELLT_AUS_CHOICES)
    erstellt_am         = models.DateTimeField(auto_now_add=True)
    aktualisiert_am     = models.DateTimeField(auto_now=True)
    letzte_anwendung    = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name        = 'Rechnungs-Match-Regel'
        verbose_name_plural = 'Rechnungs-Match-Regeln'
        ordering            = ['-trefferzahl', '-letzte_anwendung']
        # Nur 1 aktive Regel pro (Kreditor, Objekt, Leistungstext-Hash)
        constraints = [
            models.UniqueConstraint(
                fields=['kreditor', 'objekt', 'leistungstext_hash'],
                condition=models.Q(status='aktiv'),
                name='unique_aktive_matchregel',
            )
        ]

    def __str__(self):
        return f"{self.kreditor.name} / {self.objekt} → {self.aufwandskonto} [{self.status}]"


class RechnungsErkennungsLog(models.Model):
    """Audit-Tabelle: jeder Erkennungslauf je Rechnung."""

    id              = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    rechnung        = models.ForeignKey(
        Rechnung, on_delete=models.CASCADE, related_name='erkennungs_logs',
    )
    zeitpunkt       = models.DateTimeField(auto_now_add=True)
    stufe           = models.CharField(max_length=3, null=True, blank=True, choices=Rechnung.ERKENNUNGS_STUFE_CHOICES)
    routing_ziel    = models.CharField(max_length=20, blank=True)
    auto_gebucht    = models.BooleanField(default=False)
    dimensionen     = models.JSONField(
        default=dict,
        help_text='{"kreditor": {match_typ, kandidat_id, konfidenz}, "objekt": {...}, "konto": {...}}',
    )
    regel_treffer   = models.ForeignKey(
        RechnungsMatchRegel, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='log_eintraege',
    )
    ki_aufruf       = models.BooleanField(default=False)
    ki_kosten_token = models.PositiveIntegerField(default=0)
    ergebnis_status = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name        = 'Erkennungs-Log'
        verbose_name_plural = 'Erkennungs-Logs'
        ordering            = ['-zeitpunkt']

    def __str__(self):
        return f"Erkennung {self.rechnung_id} | Stufe {self.stufe} @ {self.zeitpunkt:%Y-%m-%d %H:%M}"


DEFAULT_FREIGABE_GRENZEN = [
    {'bis': 500,   'rolle': 'auto',             'frist_tage': 0, 'beschreibung': 'Automatische Freigabe'},
    {'bis': 5000,  'rolle': 'objektmanager',    'frist_tage': 3, 'beschreibung': 'Objektmanager-Freigabe'},
    {'bis': None,  'rolle': 'geschaeftsfuehrer', 'frist_tage': 5, 'beschreibung': 'Geschäftsführer-Freigabe'},
]


class FreigabelimitDefault(models.Model):
    grenzen = models.JSONField(default=list)

    class Meta:
        verbose_name = 'Freigabelimit-Standard'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def lade(cls):
        obj, _ = cls.objects.get_or_create(pk=1, defaults={'grenzen': DEFAULT_FREIGABE_GRENZEN})
        return obj


class Verarbeitungslog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    rechnung = models.ForeignKey(
        Rechnung, on_delete=models.CASCADE, null=True, blank=True,
        related_name='logs',
    )
    aktion = models.CharField(max_length=100)
    status = models.CharField(max_length=20, blank=True)
    details = models.TextField(blank=True)
    zeitpunkt = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Verarbeitungslog'
        verbose_name_plural = 'Verarbeitungslogs'
        ordering = ['-zeitpunkt']

    def __str__(self):
        return f"{self.zeitpunkt:%Y-%m-%d %H:%M} | {self.aktion}"


class RechnungsBearbeitungsLock(models.Model):
    """Soft-Lock für Frontoffice-Inbox: verhindert Doppelbearbeitung."""
    rechnung   = models.OneToOneField(
        Rechnung, on_delete=models.CASCADE, primary_key=True,
        related_name='bearbeitungslock',
    )
    user       = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='rechnungs_locks',
    )
    gueltig_bis = models.DateTimeField()
    erstellt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Bearbeitungs-Lock'

    @property
    def ist_aktiv(self):
        from django.utils import timezone
        return self.gueltig_bis > timezone.now()

    def __str__(self):
        return f"Lock {self.rechnung_id} → {self.user} bis {self.gueltig_bis:%H:%M}"
