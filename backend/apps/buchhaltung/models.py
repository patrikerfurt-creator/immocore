from uuid import uuid4
from django.conf import settings
from django.db import models
from django.db.models import Q
from apps.objekte.models import Objekt, Einheit, Bankkonto
from apps.konten.models import Konto, Personenkonto, Unterkonto


# ---------------------------------------------------------------------------
# Buchungsart (BA) — zentrales Steuerungsattribut für alle Buchungen
# ---------------------------------------------------------------------------

class Buchungsart(models.Model):
    EINZELABRECHNUNG_CHOICES = [
        ('ja', 'Ja'),
        ('nein', 'Nein'),
        ('anteilig', 'Anteilig'),
    ]
    UMLAGE_CHOICES = [
        ('pflicht', 'Pflicht'),
        ('optional', 'Optional'),
        ('gesperrt', 'Gesperrt'),
    ]

    nr = models.CharField(max_length=3, unique=True)
    kuerzel = models.CharField(max_length=12)
    bezeichnung = models.CharField(max_length=120)
    einzelabrechnung = models.CharField(
        max_length=12, choices=EINZELABRECHNUNG_CHOICES, default='nein'
    )
    gesamtabrechnung = models.BooleanField(default=False)
    ruecklagen_relevant = models.BooleanField(default=False)
    umlage = models.CharField(
        max_length=12, choices=UMLAGE_CHOICES, default='gesperrt'
    )
    beleg_pflicht = models.BooleanField(default=True)
    beschluss_pflicht = models.BooleanField(default=False)
    vier_augen_schwelle = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    sperre_nach_jahresabschluss = models.BooleanField(default=True)
    system_buchungsart = models.BooleanField(
        default=False,
        help_text='Nur durch System-Prozesse erzeugbar, nicht manuell wählbar',
    )
    default_konto_soll_pattern = models.CharField(max_length=20, blank=True)
    default_konto_haben_pattern = models.CharField(max_length=20, blank=True)
    aktiv = models.BooleanField(default=True)
    # Hausgeld-Nebenbuch-Erweiterungen (Kap. 6.1)
    BANKKONTO_TYP_CHOICES = [
        ('bewirtschaftung',      'Bewirtschaftungskonto'),
        ('ruecklage_nach_index', 'Rücklage nach Konto-Index'),
        ('frei',                 'Frei konfigurierbar'),
    ]
    tilgungs_prioritaet     = models.IntegerField(null=True, blank=True,
        help_text='Kleinere Zahl = höhere Priorität. NULL = keine Tilgungs-Priorisierung.')
    erloeskonto_default_nr  = models.CharField(max_length=10, blank=True,
        verbose_name='Standard-Erlöskonto (Kontonummer)',
        help_text='Kontonummer des Erlöskontos (z.B. 41900). Wird beim Sollstellungslauf aufgelöst.')
    bankkonto_typ           = models.CharField(max_length=25, choices=BANKKONTO_TYP_CHOICES,
        null=True, blank=True,
        help_text='Routing-Hinweis für den Lastschriftlauf.')
    BUCHUNGSTYP_CHOICES = [
        ('sachkonto',    'Sachkontenbuchung'),
        ('personenkonto','Personenkontobuchung'),
        ('kreditor',     'Kreditorenbuchung'),
    ]
    buchungstyp = models.CharField(
        max_length=20, choices=BUCHUNGSTYP_CHOICES,
        null=True, blank=True,
        help_text='Buchungstyp für den Dialogbuchhaltung-Filter. Leer = nicht in der Dialogbuchhaltung wählbar.',
    )

    class Meta:
        verbose_name = 'Buchungsart'
        verbose_name_plural = 'Buchungsarten'
        ordering = ['nr']

    def __str__(self):
        return f"{self.nr} {self.kuerzel} — {self.bezeichnung}"


# ---------------------------------------------------------------------------
# Buchung — doppelte Buchführung, erweitert um BA-Steuerung
# ---------------------------------------------------------------------------

class Buchung(models.Model):
    STATUS_CHOICES = [
        ('entwurf', 'Entwurf'),
        ('festgeschrieben', 'Festgeschrieben'),
        ('storniert', 'Storniert'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt = models.ForeignKey(Objekt, on_delete=models.PROTECT, related_name='buchungen')
    buchungsart = models.ForeignKey(
        Buchungsart, on_delete=models.PROTECT,
        null=True, blank=True, related_name='buchungen'
    )
    betrag = models.DecimalField(max_digits=12, decimal_places=2)
    # Hauptbuch-Sachkonten (nullable bei Sammelbuchungen/Unterkonten-Buchungen)
    soll_konto = models.ForeignKey(
        Konto, on_delete=models.PROTECT, null=True, blank=True,
        related_name='soll_buchungen'
    )
    haben_konto = models.ForeignKey(
        Konto, on_delete=models.PROTECT, null=True, blank=True,
        related_name='haben_buchungen'
    )
    # Nebenbuch: Unterkonto auf Soll-Seite (z.B. 0001.900 an 41900)
    soll_unterkonto = models.ForeignKey(
        Unterkonto, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='soll_buchungen'
    )
    # Nebenbuch: Unterkonto allgemein (rückwärtskompatibel)
    unterkonto = models.ForeignKey(
        Unterkonto, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='buchungen'
    )
    personenkonto = models.ForeignKey(
        Personenkonto, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='hauptbuchungen'
    )
    # Sammelbuchung-Struktur: parent=None → Gesamtbuchung, parent gesetzt → Teilbuchung
    parent_buchung = models.ForeignKey(
        'self', on_delete=models.CASCADE, null=True, blank=True,
        related_name='teilbuchungen'
    )
    belegnr = models.CharField(max_length=50, blank=True)
    buchungsdatum = models.DateField()
    belegdatum = models.DateField(null=True, blank=True)
    wertstellungsdatum = models.DateField(null=True, blank=True)
    buchungstext = models.TextField(blank=True)
    verwendungszweck = models.TextField(blank=True)
    wirtschaftsjahr_nr = models.IntegerField(null=True, blank=True)
    wirtschaftsjahr = models.ForeignKey(
        'objekte.Wirtschaftsjahr', on_delete=models.PROTECT,
        null=True, blank=True, related_name='buchungen_wj',
    )
    kostenstelle = models.CharField(max_length=20, blank=True)
    beleg_referenz = models.CharField(max_length=255, blank=True)
    storno_von = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='stornobuchungen'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='entwurf')
    stapel = models.ForeignKey(
        'Buchungsstapel', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='buchungen'
    )
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='buchungen'
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Buchung'
        verbose_name_plural = 'Buchungen'
        ordering = ['-buchungsdatum', '-erstellt_am']

    def __str__(self):
        ba = f" [{self.buchungsart.kuerzel}]" if self.buchungsart else ''
        return f"{self.buchungsdatum} | {self.betrag} €{ba} | {self.status}"


# ---------------------------------------------------------------------------
# Buchungsstapel — sammelt Entwurfs-Buchungen vor dem Ausbuchen
# ---------------------------------------------------------------------------

class Buchungsstapel(models.Model):
    STATUS_CHOICES = [
        ('offen', 'Offen'),
        ('ausgebucht', 'Ausgebucht'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt = models.ForeignKey(Objekt, on_delete=models.PROTECT, related_name='buchungsstapel')
    bezeichnung = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='offen')
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='buchungsstapel'
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)
    ausgebucht_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ausgebuchte_stapel'
    )
    ausgebucht_am = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Buchungsstapel'
        verbose_name_plural = 'Buchungsstapel'
        ordering = ['-erstellt_am']

    def __str__(self):
        return f"Stapel {self.erstellt_am.strftime('%d.%m.%Y %H:%M')} — {self.objekt.bezeichnung} [{self.status}]"


# ---------------------------------------------------------------------------
# Offener Posten — entsteht bei Sollstellung, reduziert bei Zahlung
# ---------------------------------------------------------------------------

class OffenerPosten(models.Model):
    STATUS_CHOICES = [
        ('offen', 'Offen'),
        ('teilverrechnet', 'Teilverrechnet'),
        ('verrechnet', 'Verrechnet'),
        ('storniert', 'Storniert'),
        ('forderungsfall', 'Forderungsfall'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    buchung = models.OneToOneField(
        Buchung, on_delete=models.PROTECT, related_name='offener_posten'
    )
    personenkonto = models.ForeignKey(
        Personenkonto, on_delete=models.PROTECT, related_name='offene_posten'
    )
    betrag_ursprung = models.DecimalField(max_digits=12, decimal_places=2)
    betrag_offen = models.DecimalField(max_digits=12, decimal_places=2)
    faellig_ab = models.DateField()
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='offen'
    )
    mahnstufe = models.IntegerField(default=0)
    mahnsperre_bis = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = 'Offener Posten'
        verbose_name_plural = 'Offene Posten'
        ordering = ['faellig_ab']

    def __str__(self):
        return (
            f"OP {self.personenkonto} | "
            f"{self.betrag_offen} € offen | {self.status}"
        )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# E-Banking — CAMT-Import-Einstellungen + Kontoumsätze
# ---------------------------------------------------------------------------

class CamtImportEinstellung(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt = models.ForeignKey(
        'objekte.Objekt', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='camt_einstellungen',
        help_text='Fallback-Objekt wenn die Empfänger-IBAN keinem Bankkonto zugeordnet werden kann.',
    )
    import_ordner = models.CharField(max_length=500, blank=True)
    archiv_ordner = models.CharField(max_length=500, blank=True)
    fehler_ordner = models.CharField(max_length=500, blank=True)
    poll_intervall_sek = models.IntegerField(default=30)
    datei_muster = models.CharField(
        max_length=200, default='*.xml,*.camt'
    )
    aktiv = models.BooleanField(default=True)
    zuletzt_geprueft_am = models.DateTimeField(null=True, blank=True)
    letzter_import_am = models.DateTimeField(null=True, blank=True)
    letzter_import_datei = models.CharField(max_length=500, blank=True)

    class Meta:
        verbose_name = 'CAMT-Import-Einstellung'
        verbose_name_plural = 'CAMT-Import-Einstellungen'

    def __str__(self):
        return 'CAMT-Import-Einstellung (global)'


class CamtImportLog(models.Model):
    TYP_CHOICES = [
        ('camt053', 'camt.053 (Kontoauszug)'),
        ('camt054', 'camt.054 (R-Transactions / Rücklastschriften)'),
    ]
    STATUS_CHOICES = [
        ('ok',                      'OK'),
        ('pending_mahnwesen_spec',  'Ausstehend (Mahnwesen-Spec)'),
        ('fehler',                  'Fehler'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    einstellung = models.ForeignKey(
        'CamtImportEinstellung', on_delete=models.CASCADE,
        related_name='logs', null=True, blank=True
    )
    zeitpunkt = models.DateTimeField(auto_now_add=True)
    import_ordner = models.CharField(max_length=500, blank=True)
    anzahl_dateien = models.IntegerField(default=0)
    anzahl_importiert = models.IntegerField(default=0)
    anzahl_duplikate = models.IntegerField(default=0)
    anzahl_erkannt = models.IntegerField(default=0)
    anzahl_fehler = models.IntegerField(default=0)
    fehler_details = models.JSONField(default=list, blank=True)
    typ = models.CharField(max_length=8, choices=TYP_CHOICES, default='camt053')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='ok')
    notiz = models.TextField(blank=True)

    class Meta:
        verbose_name = 'CAMT-Import-Log'
        verbose_name_plural = 'CAMT-Import-Logs'
        ordering = ['-zeitpunkt']

    def __str__(self):
        return f"CAMT-Import {self.zeitpunkt:%d.%m.%Y %H:%M} — {self.anzahl_importiert} importiert, {self.anzahl_fehler} Fehler"


class ImportOrdnerEinstellung(models.Model):
    BEREICH_CHOICES = [
        ('rechnungen', 'Rechnungen'),
        ('dokumente', 'Dokumente'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    bereich = models.CharField(max_length=50, choices=BEREICH_CHOICES, unique=True)
    import_ordner = models.CharField(max_length=500, blank=True)
    archiv_ordner = models.CharField(max_length=500, blank=True)
    fehler_ordner = models.CharField(max_length=500, blank=True)
    aktiv = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Import-Ordner-Einstellung'
        verbose_name_plural = 'Import-Ordner-Einstellungen'

    def __str__(self):
        return f"{self.get_bereich_display()}-Import (global)"


class BankMatchRegel(models.Model):
    """Lernlogik-Tabelle: (bankkonto, kontrahent_iban, verwendungszweck_hash) → gegenkonto."""
    STATUS_CHOICES = [
        ('aktiv',    'Aktiv'),
        ('veraltet', 'Veraltet'),
    ]
    ERSTELLT_AUS_CHOICES = [
        ('bestaetigung', 'Bestätigung'),
        ('korrektur',    'Korrektur'),
        ('manuell',      'Manuell'),
    ]

    id                    = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    bankkonto             = models.ForeignKey(
        Bankkonto, on_delete=models.CASCADE, related_name='match_regeln'
    )
    kontrahent_iban       = models.CharField(max_length=34)
    verwendungszweck_hash = models.CharField(max_length=64)
    gegenkonto            = models.ForeignKey(
        Konto, on_delete=models.PROTECT, related_name='bank_match_regeln'
    )
    kreditor              = models.ForeignKey(
        'personen.Person', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='bank_match_regeln'
    )
    eigentumsverhaeltnis  = models.ForeignKey(
        'personen.EigentumsVerhaeltnis', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='bank_match_regeln'
    )
    status                = models.CharField(max_length=10, choices=STATUS_CHOICES, default='aktiv')
    erstellt_aus          = models.CharField(max_length=15, choices=ERSTELLT_AUS_CHOICES)
    trefferzahl           = models.IntegerField(default=0)
    letzte_anwendung      = models.DateTimeField(null=True, blank=True)
    erstellt_am           = models.DateTimeField(auto_now_add=True)
    erstellt_von          = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='erstellte_bank_match_regeln'
    )

    class Meta:
        verbose_name        = 'Bank-Match-Regel'
        verbose_name_plural = 'Bank-Match-Regeln'
        ordering            = ['-trefferzahl', '-letzte_anwendung']
        constraints = [
            models.UniqueConstraint(
                fields=['bankkonto', 'kontrahent_iban', 'verwendungszweck_hash'],
                condition=Q(status='aktiv'),
                name='unique_aktive_bankregel',
            ),
        ]

    def __str__(self):
        return (
            f"Regel [{self.status}] {self.bankkonto} "
            f"IBAN={self.kontrahent_iban} → {self.gegenkonto} "
            f"(Treffer: {self.trefferzahl})"
        )


class Kontoumsatz(models.Model):
    STATUS_CHOICES = [
        ('importiert',  'Importiert'),
        ('erkannt',     'Erkannt (eindeutig, Konfidenz 1.0)'),
        ('vorschlag',   'Vorschlag (Konfidenz 0.5–<1.0)'),
        ('unklar',      'Unklar (keine Erkennung)'),
        ('verbucht',    'Verbucht (Hauptbuch)'),
        ('storniert',   'Storniert (GoBD)'),
        # Legacy-Werte — bleiben für Rückwärtskompatibilität
        ('manuell',     'Manuell zugeordnet (Legacy)'),
        ('gebucht',     'Gebucht (Legacy)'),
        ('ignoriert',   'Ignoriert'),
        ('unbekannt',   'Unbekannt (kein Objekt)'),
    ]
    ERKENNUNGS_QUELLE_CHOICES = [
        ('e2e_id',           'EndToEndId-Match (Nebenbuch)'),
        ('iban_ev',          'IBAN-Match auf EigentumsVerhältnis'),
        ('bank_match_regel', 'BankMatchRegel'),
        ('iban_kreditor',    'IBAN-Match auf Kreditor'),
        ('ki',               'KI-Vorschlag'),
        ('keine',            'Keine Erkennung'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt = models.ForeignKey(
        Objekt, on_delete=models.CASCADE, related_name='kontoumsaetze',
        null=True, blank=True
    )
    bankkonto = models.ForeignKey(
        Bankkonto, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='kontoumsaetze'
    )
    sha256_hash = models.CharField(max_length=64, unique=True)
    betrag = models.DecimalField(max_digits=12, decimal_places=2)
    buchungsdatum = models.DateField()
    wertstellungsdatum = models.DateField(null=True, blank=True)
    auftraggeber_name = models.CharField(max_length=255, blank=True)
    auftraggeber_iban = models.CharField(max_length=34, blank=True)
    empfaenger_iban = models.CharField(max_length=34, blank=True)
    verwendungszweck = models.TextField(blank=True)
    end_to_end_id = models.CharField(max_length=35, blank=True)
    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default='importiert'
    )
    buchung = models.ForeignKey(
        Buchung, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='kontoumsaetze'
    )
    # E-Banking Erkennungs-Felder (Phase A)
    erkannt_gegenkonto = models.ForeignKey(
        Konto, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='kontoumsatz_gegenkonto'
    )
    erkannt_eigentumsverhaeltnis = models.ForeignKey(
        'personen.EigentumsVerhaeltnis', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='kontoumsaetze_erkannt'
    )
    erkannt_kreditor = models.ForeignKey(
        'personen.Person', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='kontoumsaetze_erkannt'
    )
    erkennungs_quelle = models.CharField(
        max_length=20, choices=ERKENNUNGS_QUELLE_CHOICES, blank=True
    )
    erkennungs_konfidenz = models.DecimalField(
        max_digits=3, decimal_places=2, null=True, blank=True
    )
    erkennungs_begruendung = models.TextField(blank=True)
    match_regel = models.ForeignKey(
        BankMatchRegel, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='angewendete_umsaetze'
    )
    verbucht_am = models.DateTimeField(null=True, blank=True)
    verbucht_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='verbuchte_umsaetze'
    )
    notiz = models.TextField(blank=True)
    ki_vorschlag = models.JSONField(null=True, blank=True)
    import_datei = models.CharField(max_length=500, blank=True)
    importiert_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Kontoumsatz'
        verbose_name_plural = 'Kontoumsätze'
        ordering = ['-buchungsdatum', '-importiert_am']
        indexes = [
            models.Index(fields=['bankkonto', 'status'],       name='idx_ku_bankkonto_status'),
            models.Index(fields=['status', 'buchungsdatum'],   name='idx_ku_status_datum'),
        ]

    def __str__(self):
        return (
            f"{self.buchungsdatum} | {self.betrag} € | "
            f"{self.auftraggeber_name} [{self.status}]"
        )


class BankErkennungsLog(models.Model):
    """Audit-Trail: jeder Erkennungsdurchlauf für einen Kontoumsatz."""
    ERKENNUNGS_QUELLE_CHOICES = Kontoumsatz.ERKENNUNGS_QUELLE_CHOICES

    id                   = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    kontoumsatz          = models.ForeignKey(
        Kontoumsatz, on_delete=models.CASCADE, related_name='erkennungs_logs'
    )
    stufe_erreicht       = models.CharField(max_length=3)
    quelle               = models.CharField(max_length=20, choices=ERKENNUNGS_QUELLE_CHOICES, blank=True)
    konfidenz            = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    gegenkonto_vorschlag = models.ForeignKey(
        Konto, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='bank_erkennungs_logs'
    )
    regel_treffer        = models.ForeignKey(
        BankMatchRegel, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='erkennungs_logs'
    )
    auto_verbucht        = models.BooleanField(default=False)
    details_json         = models.JSONField(null=True, blank=True)
    erstellt_am          = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Bank-Erkennungs-Log'
        verbose_name_plural = 'Bank-Erkennungs-Logs'
        ordering            = ['-erstellt_am']

    def __str__(self):
        return (
            f"ErkLog {self.kontoumsatz_id} Stufe={self.stufe_erreicht} "
            f"Konf={self.konfidenz}"
        )


# ---------------------------------------------------------------------------
# Mahnwesen
# ---------------------------------------------------------------------------

class Mahnlauf(models.Model):
    TRIGGER_CHOICES = [
        ('automatisch', 'Automatisch'),
        ('manuell', 'Manuell'),
    ]
    STATUS_CHOICES = [
        ('simulation', 'Simulation'),
        ('ausstehend', 'Ausstehend'),
        ('freigegeben', 'Freigegeben'),
        ('ausgefuehrt', 'Ausgeführt'),
        ('fehler', 'Fehler'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt = models.ForeignKey(
        Objekt, on_delete=models.PROTECT, related_name='mahnlaeufe'
    )
    trigger = models.CharField(
        max_length=12, choices=TRIGGER_CHOICES, default='manuell'
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='simulation'
    )
    ausgefuehrt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='mahnlaeufe'
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)
    freigabe_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='freigegebene_mahnlaeufe'
    )
    freigabe_am = models.DateTimeField(null=True, blank=True)
    anzahl_mahnungen = models.IntegerField(default=0)
    gesamt_gebuehren = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    gesamt_zinsen = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    protokoll = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name = 'Mahnlauf'
        verbose_name_plural = 'Mahnläufe'
        ordering = ['-erstellt_am']

    def __str__(self):
        return f"Mahnlauf {self.erstellt_am.date()} | {self.objekt.bezeichnung} [{self.status}]"


class Mahnung(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    lauf = models.ForeignKey(
        Mahnlauf, on_delete=models.CASCADE, related_name='mahnungen'
    )
    personenkonto = models.ForeignKey(
        Personenkonto, on_delete=models.PROTECT, related_name='mahnungen'
    )
    mahnstufe = models.IntegerField()
    offene_posten_summe = models.DecimalField(max_digits=12, decimal_places=2)
    gebuehr = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    zinsen = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    buchung_gebuehr = models.ForeignKey(
        Buchung, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='mahnung_gebuehr'
    )
    buchung_zinsen = models.ForeignKey(
        Buchung, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='mahnung_zinsen'
    )
    pdf_pfad = models.CharField(max_length=500, blank=True)
    versandt_am = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Mahnung'
        verbose_name_plural = 'Mahnungen'
        ordering = ['-lauf__erstellt_am']

    def __str__(self):
        return (
            f"Mahnung Stufe {self.mahnstufe} | "
            f"{self.personenkonto} | {self.offene_posten_summe} €"
        )


class Mahnsperre(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    personenkonto = models.ForeignKey(
        Personenkonto, on_delete=models.PROTECT, related_name='mahnsperren'
    )
    gesperrt_bis = models.DateField()
    grund = models.CharField(max_length=255)
    gesetzt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='gesetzte_mahnsperren'
    )
    gesetzt_am = models.DateTimeField(auto_now_add=True)
    aufgehoben_am = models.DateTimeField(null=True, blank=True)
    aufgehoben_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='aufgehobene_mahnsperren'
    )

    class Meta:
        verbose_name = 'Mahnsperre'
        verbose_name_plural = 'Mahnsperren'
        ordering = ['-gesetzt_am']

    def __str__(self):
        return f"Mahnsperre {self.personenkonto} bis {self.gesperrt_bis}"


# ---------------------------------------------------------------------------
# Forderungsfälle
# ---------------------------------------------------------------------------

class Forderungsfall(models.Model):
    STATUS_CHOICES = [
        ('offen', 'Offen'),
        ('aussergerichtlich', 'Außergerichtlich'),
        ('gerichtlich', 'Gerichtlich'),
        ('titulierung', 'Titulierung'),
        ('vollstreckung', 'Vollstreckung'),
        ('erfolgreich', 'Erfolgreich'),
        ('uneinbringlich', 'Uneinbringlich'),
        ('abschreibung', 'Abschreibung'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    personenkonto = models.ForeignKey(
        Personenkonto, on_delete=models.PROTECT, related_name='forderungsfaelle'
    )
    objekt = models.ForeignKey(
        Objekt, on_delete=models.PROTECT, related_name='forderungsfaelle'
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='offen'
    )
    eroeffnet_am = models.DateField(auto_now_add=True)
    eroeffnet_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='eroeffnete_forderungsfaelle'
    )
    hauptforderung = models.DecimalField(max_digits=12, decimal_places=2)
    mahngebuehren = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    verzugszinsen = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    anwaltskosten = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    gerichtskosten = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    gv_kosten = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    beschluss_referenz = models.CharField(max_length=255, blank=True)
    notizen = models.TextField(blank=True)
    abgeschlossen_am = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = 'Forderungsfall'
        verbose_name_plural = 'Forderungsfälle'
        ordering = ['-eroeffnet_am']

    @property
    def gesamtforderung(self):
        return (
            self.hauptforderung
            + self.mahngebuehren
            + self.verzugszinsen
            + self.anwaltskosten
            + self.gerichtskosten
            + self.gv_kosten
        )

    def __str__(self):
        return (
            f"Forderungsfall {self.personenkonto} | "
            f"{self.gesamtforderung} € [{self.status}]"
        )


# ---------------------------------------------------------------------------
# § 288 BGB Basiszinssatz-Historie
# ---------------------------------------------------------------------------

class Basiszinssatz(models.Model):
    gueltig_ab = models.DateField(unique=True)
    satz = models.DecimalField(max_digits=5, decimal_places=2)
    quelle = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = 'Basiszinssatz'
        verbose_name_plural = 'Basiszinssätze'
        ordering = ['-gueltig_ab']

    def __str__(self):
        return f"Basiszinssatz ab {self.gueltig_ab}: {self.satz} %"


# ---------------------------------------------------------------------------
# ARAP / PRAP — Rechnungsabgrenzung
# ---------------------------------------------------------------------------

class RAPPosition(models.Model):
    TYP_CHOICES = [
        ('ARAP', 'Aktive Rechnungsabgrenzung (Aufwand voraus bezahlt)'),
        ('PRAP', 'Passive Rechnungsabgrenzung (Ertrag voraus vereinnahmt)'),
    ]
    STATUS_CHOICES = [
        ('aktiv', 'Aktiv'),
        ('aufgeloest', 'Aufgelöst'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt = models.ForeignKey(
        Objekt, on_delete=models.PROTECT, related_name='rap_positionen'
    )
    bezeichnung = models.CharField(max_length=255)
    rap_typ = models.CharField(max_length=4, choices=TYP_CHOICES)
    gesamtbetrag = models.DecimalField(max_digits=12, decimal_places=2)
    zeitraum_von = models.DateField()
    zeitraum_bis = models.DateField()
    soll_konto = models.ForeignKey(
        Konto, on_delete=models.PROTECT, related_name='rap_positionen_soll'
    )
    haben_konto = models.ForeignKey(
        Konto, on_delete=models.PROTECT, related_name='rap_positionen_haben'
    )
    ursprungsbuchung = models.ForeignKey(
        Buchung, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='rap_positionen'
    )
    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default='aktiv'
    )
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='rap_positionen'
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'RAP-Position'
        verbose_name_plural = 'RAP-Positionen'
        ordering = ['-erstellt_am']

    def __str__(self):
        return (
            f"{self.rap_typ} {self.bezeichnung} "
            f"{self.zeitraum_von}–{self.zeitraum_bis} | {self.gesamtbetrag} €"
        )


class RAPAufloesung(models.Model):
    STATUS_CHOICES = [
        ('geplant', 'Geplant'),
        ('gebucht', 'Gebucht'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    position = models.ForeignKey(
        RAPPosition, on_delete=models.CASCADE, related_name='aufloesungen'
    )
    buchungsdatum = models.DateField()
    betrag = models.DecimalField(max_digits=12, decimal_places=2)
    buchung = models.ForeignKey(
        Buchung, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='rap_aufloesungen'
    )
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default='geplant'
    )

    class Meta:
        verbose_name = 'RAP-Auflösung'
        verbose_name_plural = 'RAP-Auflösungen'
        ordering = ['buchungsdatum']

    def __str__(self):
        return (
            f"RAP-Auflösung {self.buchungsdatum} | "
            f"{self.betrag} € [{self.status}]"
        )


# ---------------------------------------------------------------------------
# Legacy: BankImport bleibt für Rückwärtskompatibilität
# ---------------------------------------------------------------------------

class BankImport(models.Model):
    STATUS_CHOICES = [
        ('neu', 'Neu'),
        ('erkannt', 'Erkannt'),
        ('manuell', 'Manuell'),
        ('ignoriert', 'Ignoriert'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt = models.ForeignKey(Objekt, on_delete=models.CASCADE, related_name='bank_importe')
    sha256_hash = models.CharField(max_length=64, unique=True)
    auftraggeber_name = models.CharField(max_length=255, blank=True)
    auftraggeber_iban = models.CharField(max_length=34, blank=True)
    betrag = models.DecimalField(max_digits=12, decimal_places=2)
    buchungsdatum = models.DateField()
    wertstellungsdatum = models.DateField(null=True, blank=True)
    verwendungszweck = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='neu')
    buchung = models.ForeignKey(
        Buchung, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='bank_importe'
    )
    ki_vorschlag = models.JSONField(null=True, blank=True)
    importiert_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Bank-Import (Legacy)'
        verbose_name_plural = 'Bank-Importe (Legacy)'
        ordering = ['-buchungsdatum', '-importiert_am']

    def __str__(self):
        return f"{self.buchungsdatum} | {self.betrag} € | {self.auftraggeber_name} [{self.status}]"


class Jahresabrechnung(models.Model):
    STATUS_CHOICES = [
        ('entwurf', 'Entwurf'),
        ('freigegeben', 'Freigegeben'),
        ('gesperrt', 'Gesperrt'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt = models.ForeignKey(Objekt, on_delete=models.PROTECT, related_name='jahresabrechnungen')
    wirtschaftsjahr = models.IntegerField()
    erstellungsdatum = models.DateField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='entwurf')
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='jahresabrechnungen'
    )

    class Meta:
        verbose_name = 'Jahresabrechnung'
        verbose_name_plural = 'Jahresabrechnungen'
        ordering = ['-wirtschaftsjahr']
        unique_together = [['objekt', 'wirtschaftsjahr']]

    def __str__(self):
        return f"Jahresabrechnung {self.wirtschaftsjahr} — {self.objekt.bezeichnung} [{self.status}]"


class EinzelAbrechnung(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    jahresabrechnung = models.ForeignKey(
        Jahresabrechnung, on_delete=models.CASCADE, related_name='einzelabrechnungen'
    )
    einheit = models.ForeignKey(
        Einheit, on_delete=models.PROTECT, related_name='einzelabrechnungen'
    )
    eigentuemer_snapshot = models.JSONField()
    personenkonto = models.ForeignKey(
        Personenkonto, on_delete=models.PROTECT, related_name='einzelabrechnungen'
    )
    hausgeld_soll_gesamt = models.DecimalField(max_digits=12, decimal_places=2)
    kostenanteil_gesamt = models.DecimalField(max_digits=12, decimal_places=2)
    abrechnungsergebnis = models.DecimalField(max_digits=12, decimal_places=2)
    positionen = models.JSONField(default=list)
    ruecklagen = models.JSONField(default=list)
    pdf_pfad = models.CharField(max_length=500, blank=True)
    gebucht = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Einzelabrechnung'
        verbose_name_plural = 'Einzelabrechnungen'
        ordering = ['jahresabrechnung', 'einheit__einheit_nr']

    def __str__(self):
        return (
            f"Einzelabrechnung {self.jahresabrechnung.wirtschaftsjahr} — "
            f"{self.einheit.einheit_nr}"
        )


# ---------------------------------------------------------------------------
# Zahlungsverkehr — Lastschrift-Läufe (SEPA pain.008)
# ---------------------------------------------------------------------------

class LastschriftLauf(models.Model):
    STATUS_CHOICES = [
        ('erstellt', 'Erstellt'),
        ('exportiert', 'Exportiert (XML heruntergeladen)'),
        ('eingereicht', 'Eingereicht'),
    ]
    LAUF_QUELLE_CHOICES = [
        ('manuell',   'Manuell'),
        ('autopilot', 'Autopilot'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt = models.ForeignKey(
        Objekt, on_delete=models.PROTECT, related_name='lastschrift_laeufe'
    )
    hausgeld_sollstellungslauf = models.ForeignKey(
        'HausgeldSollstellungslauf', on_delete=models.PROTECT,
        null=True, blank=True, related_name='lastschrift_laeufe'
    )
    bezeichnung = models.CharField(max_length=255, blank=True)
    faelligkeitsdatum = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='erstellt')
    erstellt_am = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='lastschrift_laeufe'
    )
    anzahl_positionen = models.IntegerField(default=0)
    gesamt_summe = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    positionen = models.JSONField(default=list, blank=True)
    ohne_mandat = models.JSONField(default=list, blank=True)
    buchungen_erstellt = models.BooleanField(default=False)
    buchungen_datum = models.DateField(null=True, blank=True)
    lauf_quelle = models.CharField(
        max_length=10, choices=LAUF_QUELLE_CHOICES, default='manuell',
        verbose_name='Lauf-Quelle',
    )
    datei_pfad = models.CharField(
        max_length=500, null=True, blank=True,
        verbose_name='pain.008-Dateipfad',
    )

    class Meta:
        verbose_name = 'Lastschrift-Lauf'
        verbose_name_plural = 'Lastschrift-Läufe'
        ordering = ['-erstellt_am']

    def __str__(self):
        return (
            f"Lastschrift {self.bezeichnung or self.faelligkeitsdatum} "
            f"| {self.objekt.bezeichnung} [{self.status}]"
        )


# ---------------------------------------------------------------------------
# KreditorOP — Offener Posten für Eingangsrechnungen (Kreditoren-Subledger)
# ---------------------------------------------------------------------------

class KreditorOP(models.Model):
    STATUS_CHOICES = [
        ('offen',       'Offen'),
        ('bezahlt',     'Bezahlt'),
        ('teilbezahlt', 'Teilbezahlt'),
        ('storniert',   'Storniert'),
    ]

    op_nummer       = models.IntegerField(unique=True, db_index=True)
    rechnung        = models.OneToOneField(
        'rechnungen.Rechnung', on_delete=models.PROTECT,
        related_name='kreditor_op', null=True, blank=True,
    )
    kreditor        = models.ForeignKey(
        'rechnungen.Kreditor', on_delete=models.PROTECT,
        related_name='offene_posten',
    )
    objekt          = models.ForeignKey(
        Objekt, on_delete=models.PROTECT,
        related_name='kreditor_ops',
    )
    buchung         = models.ForeignKey(
        Buchung, on_delete=models.PROTECT,
        related_name='kreditor_op_erstellung',
    )
    zahlung_buchung = models.ForeignKey(
        Buchung, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='kreditor_op_zahlung',
    )
    betrag_ursprung = models.DecimalField(max_digits=12, decimal_places=2)
    betrag_offen    = models.DecimalField(max_digits=12, decimal_places=2)
    faellig_ab      = models.DateField()
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default='offen')
    erstellt_am     = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Kreditor-OP'
        verbose_name_plural = 'Kreditor-OPs'
        ordering            = ['-op_nummer']

    def __str__(self):
        return f"OP-{self.op_nummer} | {self.kreditor} | {self.betrag_offen} € | {self.status}"


# ---------------------------------------------------------------------------
# Hausgeld-Nebenbuch — OP-Verwaltung für Eigentümerforderungen (v1.1)
# ---------------------------------------------------------------------------

class HausgeldSollstellungslauf(models.Model):
    """Header eines Massen-Sollstellungslaufs (Hausgeld, Sonderumlage, Abrechnung)."""
    TYP_CHOICES = [
        ('hausgeld_monat',           'Hausgeld monatlich'),
        ('sonderumlage',             'Sonderumlage'),
        ('abrechnungsergebnis_jahr', 'Abrechnungsergebnis Wirtschaftsjahr'),
    ]
    STATUS_CHOICES = [
        ('vorschau',    'Vorschau'),
        ('freigegeben', 'Freigegeben (Vier-Augen)'),
        ('commited',    'Commited / Ausgeführt'),
        ('storniert',   'Storniert'),
    ]
    LAUF_QUELLE_CHOICES = [
        ('manuell',   'Manuell'),
        ('autopilot', 'Autopilot'),
    ]

    id                    = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt                = models.ForeignKey(Objekt, on_delete=models.PROTECT, related_name='hausgeld_laeufe')
    typ                   = models.CharField(max_length=30, choices=TYP_CHOICES)
    periode               = models.DateField()
    status                = models.CharField(max_length=20, choices=STATUS_CHOICES, default='vorschau')
    anzahl_sollstellungen = models.IntegerField(default=0)
    summe                 = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    fehler_details        = models.JSONField(default=list, blank=True)
    erstellt_am           = models.DateTimeField(auto_now_add=True)
    erstellt_von          = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    freigabe_user         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='freigegebene_hausgeld_laeufe')
    freigegeben_am        = models.DateTimeField(null=True, blank=True)
    commited_am           = models.DateTimeField(null=True, blank=True)
    commited_von          = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    storniert_am          = models.DateTimeField(null=True, blank=True)
    storniert_von         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    storniert_grund       = models.TextField(blank=True)
    lauf_quelle           = models.CharField(
        max_length=10, choices=LAUF_QUELLE_CHOICES, default='manuell',
        verbose_name='Lauf-Quelle',
    )

    class Meta:
        verbose_name        = 'Hausgeld-Sollstellungslauf'
        verbose_name_plural = 'Hausgeld-Sollstellungsläufe'
        ordering            = ['-periode', 'objekt']
        constraints = [
            models.UniqueConstraint(
                fields=['objekt', 'periode', 'lauf_quelle'],
                condition=models.Q(status='commited'),
                name='unique_commited_lauf_pro_periode_quelle',
            ),
        ]

    def __str__(self):
        return f"{self.objekt.bezeichnung} — {self.get_typ_display()} — {self.periode} [{self.status}]"


class OposSequenz(models.Model):
    """Zähler für OPOS-Nummern je Objekt (race-safe via SELECT FOR UPDATE)."""
    objekt          = models.OneToOneField(Objekt, on_delete=models.PROTECT, primary_key=True, related_name='opos_sequenz')
    naechste_lfd_nr = models.BigIntegerField(default=1)

    class Meta:
        verbose_name        = 'OPOS-Sequenz'
        verbose_name_plural = 'OPOS-Sequenzen'

    def __str__(self):
        return f"OposSequenz {self.objekt.bezeichnung} (nächste: {self.naechste_lfd_nr})"


class HausgeldSollstellung(models.Model):
    """Offener Posten im Eigentümer-Nebenbuch. Erzeugt KEINE Sachkontenbuchung."""
    TYP_CHOICES = [
        ('hausgeld',            'Hausgeld'),
        ('sonderumlage',        'Sonderumlage'),
        ('abrechnungsergebnis', 'Abrechnungsergebnis'),
        ('korrektur',           'Korrektur'),
    ]
    KORREKTUR_GRUND_CHOICES = [
        ('eigentuemerwechsel',        'Eigentümerwechsel'),
        ('wirtschaftsplan_aenderung', 'Wirtschaftsplan-Änderung'),
    ]

    id                   = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt               = models.ForeignKey(Objekt, on_delete=models.PROTECT, related_name='hausgeld_sollstellungen')
    eigentumsverhaeltnis = models.ForeignKey('personen.EigentumsVerhaeltnis', on_delete=models.PROTECT, related_name='sollstellungen')
    sollstellungs_typ    = models.CharField(max_length=20, choices=TYP_CHOICES)
    ba                   = models.ForeignKey(Buchungsart, on_delete=models.PROTECT, null=True, blank=True, related_name='+',
                                              help_text='NULL bei hausgeld; gesetzt bei sonderumlage/abrechnungsergebnis')
    periode              = models.DateField()
    faellig_am           = models.DateField()
    opos_nr              = models.CharField(max_length=15, unique=True, db_index=True)
    soll_betrag          = models.DecimalField(max_digits=12, decimal_places=2)
    ist_betrag           = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status_cached        = models.CharField(max_length=20, default='offen', db_index=True)
    sollstellungslauf    = models.ForeignKey(HausgeldSollstellungslauf, on_delete=models.PROTECT, null=True, blank=True, related_name='sollstellungen')
    storniert_am         = models.DateTimeField(null=True, blank=True)
    storniert_von        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    storniert_grund      = models.TextField(blank=True)
    erstellt_am          = models.DateTimeField(auto_now_add=True)
    erstellt_von         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    # Korrektur-Felder (Patch v1.1)
    korrektur_grund      = models.CharField(max_length=40, choices=KORREKTUR_GRUND_CHOICES, null=True, blank=True)
    korrektur_vorgang_id = models.UUIDField(null=True, blank=True)
    neutralisiert_durch_opos = models.ForeignKey(
        'self', on_delete=models.PROTECT, null=True, blank=True, related_name='+',
    )
    neutralisiert_opos_nr = models.ForeignKey(
        'self', on_delete=models.PROTECT, null=True, blank=True, related_name='+',
    )
    nachhol_aus_wp_beschluss = models.ForeignKey(
        'abrechnung_wp.Wirtschaftsplan',
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name='nachhol_sollstellungen',
    )

    @property
    def status(self) -> str:
        if self.storniert_am is not None:
            return 'storniert'
        soll = self.soll_betrag
        ist  = self.ist_betrag
        if ist == 0:
            return 'offen'
        if ist == soll:
            return 'ausgeglichen'
        if abs(ist) < abs(soll) and (ist > 0) == (soll > 0):
            return 'teilbezahlt'
        return 'ueberzahlt'

    class Meta:
        verbose_name        = 'Hausgeld-Sollstellung'
        verbose_name_plural = 'Hausgeld-Sollstellungen'
        ordering            = ['-periode', 'eigentumsverhaeltnis']
        constraints = [
            models.UniqueConstraint(
                fields=['eigentumsverhaeltnis', 'periode', 'sollstellungs_typ', 'ba'],
                name='uniq_sollstellung_ev_periode_typ_ba',
            ),
            models.CheckConstraint(
                name='negative_betrag_nur_korrektur',
                check=(
                    Q(soll_betrag__gte=0)
                    | Q(sollstellungs_typ='korrektur')
                ),
            ),
            models.CheckConstraint(
                name='korrektur_grund_consistency',
                check=(
                    Q(sollstellungs_typ='korrektur', korrektur_grund__isnull=False, korrektur_vorgang_id__isnull=False)
                    | ~Q(sollstellungs_typ='korrektur')
                ),
            ),
        ]
        indexes = [
            models.Index(fields=['objekt', 'status_cached'],      name='idx_hg_ss_objekt_status'),
            models.Index(fields=['opos_nr'],                      name='idx_hg_ss_opos_nr'),
            models.Index(fields=['neutralisiert_durch_opos'],     name='idx_hg_ss_neutralisiert'),
            models.Index(fields=['sollstellungs_typ'],            name='idx_hg_ss_typ'),
            models.Index(fields=['korrektur_vorgang_id'],         name='idx_hg_ss_korrektur_vorgang'),
        ]

    def __str__(self):
        return f"SS-{self.opos_nr} | {self.eigentumsverhaeltnis} | {self.soll_betrag} € [{self.status_cached}]"


class SollstellungSplit(models.Model):
    """Aufteilung einer hausgeld-Sollstellung auf BA-Ebene (nur bei sollstellungs_typ='hausgeld')."""
    id               = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    sollstellung     = models.ForeignKey(HausgeldSollstellung, on_delete=models.CASCADE, related_name='splits')
    ba               = models.ForeignKey(Buchungsart, on_delete=models.PROTECT, related_name='+')
    betrag           = models.DecimalField(max_digits=12, decimal_places=2)
    bankkonto_ziel   = models.ForeignKey(Bankkonto, on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    erloeskonto      = models.ForeignKey(Konto, on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    ist_betrag_split = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        verbose_name        = 'Sollstellungs-Split'
        verbose_name_plural = 'Sollstellungs-Splits'
        constraints = [
            models.UniqueConstraint(fields=['sollstellung', 'ba'], name='uniq_split_sollstellung_ba'),
        ]

    def __str__(self):
        return f"Split {self.ba} — {self.betrag} €"


class SollstellungZahlung(models.Model):
    """Verknüpfung zwischen einer Sollstellung und der tilgenden Buchung."""
    TILGUNGSSTUFE_CHOICES = [
        ('hauptforderung', 'Hauptforderung'),
        ('zinsen',         'Zinsen'),
        ('kosten',         'Kosten'),
    ]

    id            = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    sollstellung  = models.ForeignKey(HausgeldSollstellung, on_delete=models.PROTECT, related_name='zahlungen')
    split         = models.ForeignKey(SollstellungSplit, on_delete=models.PROTECT, null=True, blank=True, related_name='zahlungen')
    buchung       = models.ForeignKey(Buchung, on_delete=models.PROTECT, related_name='sollstellung_zahlungen')
    betrag        = models.DecimalField(max_digits=12, decimal_places=2)
    tilgungsstufe = models.CharField(max_length=20, choices=TILGUNGSSTUFE_CHOICES, default='hauptforderung')
    erstellt_am   = models.DateTimeField(auto_now_add=True)
    erstellt_von  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')

    class Meta:
        verbose_name        = 'Sollstellungs-Zahlung'
        verbose_name_plural = 'Sollstellungs-Zahlungen'
        ordering            = ['erstellt_am']

    def __str__(self):
        return f"Zahlung {self.betrag} € für {self.sollstellung.opos_nr}"


# ---------------------------------------------------------------------------
# Auto-Pipeline — Protokoll (GoBD-Audit-Tabelle, A3)
# ---------------------------------------------------------------------------

class AutoLaufProtokoll(models.Model):
    """
    GoBD-Audit-Tabelle. Ein Eintrag pro Auto-Pipeline-Aufruf je Objekt.
    Read-only nach Erstellung — niemals löschen.
    """
    STATUS_CHOICES = [
        ('erfolg',           'Erfolg'),
        ('teilweise_erfolg', 'Teilweise Erfolg'),
        ('fehler',           'Fehler'),
        ('uebersprungen',    'Übersprungen'),
    ]

    id                      = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt                  = models.ForeignKey(
        Objekt, on_delete=models.PROTECT, related_name='auto_lauf_protokolle',
    )
    ausgefuehrt_am          = models.DateTimeField()
    periode                 = models.DateField()
    status                  = models.CharField(max_length=20, choices=STATUS_CHOICES)
    sollstellungslauf       = models.ForeignKey(
        HausgeldSollstellungslauf, on_delete=models.PROTECT,
        null=True, blank=True, related_name='auto_lauf_protokolle',
    )
    lastschriftlauf         = models.ForeignKey(
        LastschriftLauf, on_delete=models.PROTECT,
        null=True, blank=True, related_name='auto_lauf_protokolle',
    )
    anzahl_evs_geplant      = models.IntegerField(default=0)
    anzahl_evs_erfolgreich  = models.IntegerField(default=0)
    anzahl_evs_uebersprungen = models.IntegerField(default=0)
    summe_sollstellungen    = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    summe_lastschrift       = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    datei_pfad              = models.CharField(max_length=500, null=True, blank=True)
    warnungen               = models.JSONField(default=list, blank=True)
    fehler                  = models.TextField(null=True, blank=True)

    class Meta:
        verbose_name        = 'Auto-Lauf-Protokoll'
        verbose_name_plural = 'Auto-Lauf-Protokolle'
        ordering            = ['-ausgefuehrt_am']

    def __str__(self):
        return (
            f"AutoLauf {self.objekt.bezeichnung} "
            f"{self.periode} [{self.status}]"
        )


# ---------------------------------------------------------------------------
# Frontoffice-Aufgabe (B1 — Auto-Pipeline-Warnungen als actionable Tasks)
# ---------------------------------------------------------------------------

class FrontofficeAufgabe(models.Model):
    """
    Actionable Task für Frontoffice-Bearbeiter.
    Wird u.a. von der Auto-Pipeline für Warnungen (kein SEPA-Mandat etc.)
    erzeugt. Soft-Lock via lock_user + lock_expires_at (5 Min, Phase C UI).
    """
    AUFGABE_TYP_CHOICES = [
        ('kein_sepa_mandat',                   'SEPA-Mandat fehlt'),
        ('keine_iban',                         'Keine IBAN hinterlegt'),
        ('keine_hausgeldhistorie',             'Kein Hausgeldsatz'),
        ('mandat_typ_frst',                    'Erst-Mandat (FRST)'),
        ('sepa_frist_unterschritten',          'SEPA-Frist unterschritten'),
        ('dateischreibfehler',                 'Dateischreibfehler'),
        ('eigentuemerwechsel_forderung',       'Eigentümerwechsel: Forderung Neueigentümer'),
        ('saldenmitteilung_wirtschaftsplan',   'Wirtschaftsplan: Saldenmitteilung versenden'),
        ('stundung_laeuft_ab',                 'Umlaufbeschluss-Stundung läuft ab'),
    ]
    STATUS_CHOICES = [
        ('offen',          'Offen'),
        ('in_bearbeitung', 'In Bearbeitung'),
        ('erledigt',       'Erledigt'),
    ]

    id              = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt          = models.ForeignKey(
        Objekt, on_delete=models.CASCADE, related_name='frontoffice_aufgaben',
    )
    aufgabe_typ     = models.CharField(max_length=40, choices=AUFGABE_TYP_CHOICES)
    beschreibung    = models.TextField()
    ev_id           = models.UUIDField(null=True, blank=True)
    einheit_nr      = models.CharField(max_length=20, blank=True)
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default='offen')
    erstellt_von    = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='erstellte_frontoffice_aufgaben',
    )
    erstellt_am     = models.DateTimeField(auto_now_add=True)
    erledigt_von    = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='erledigte_frontoffice_aufgaben',
    )
    erledigt_am     = models.DateTimeField(null=True, blank=True)
    lock_user       = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='frontoffice_locks',
    )
    lock_expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name        = 'Frontoffice-Aufgabe'
        verbose_name_plural = 'Frontoffice-Aufgaben'
        ordering            = ['-erstellt_am']

    def __str__(self):
        return f"[{self.get_aufgabe_typ_display()}] {self.objekt.bezeichnung} ({self.status})"


# ---------------------------------------------------------------------------
# Eigentümerwechsel — Vorgangs-Modell (Wechsel-Spec v1.1)
# ---------------------------------------------------------------------------

class EigentuemerwechselVorgang(models.Model):
    STATUS_CHOICES = [
        ('vorschau',    'Vorschau'),
        ('freigegeben', 'Freigegeben'),
    ]

    id                   = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt               = models.ForeignKey(Objekt, on_delete=models.PROTECT, related_name='eigentuemerwechsel_vorgaenge')
    einheit              = models.ForeignKey(Einheit, on_delete=models.PROTECT, related_name='eigentuemerwechsel_vorgaenge')
    voreigentuemer_ev    = models.ForeignKey(
        'personen.EigentumsVerhaeltnis', on_delete=models.PROTECT,
        related_name='eigentuemerwechsel_als_voreigentuemer',
    )
    neueigentuemer_ev    = models.ForeignKey(
        'personen.EigentumsVerhaeltnis', on_delete=models.PROTECT,
        related_name='eigentuemerwechsel_als_neueigentuemer',
    )
    wechsel_datum        = models.DateField()
    meldedatum           = models.DateField()
    status               = models.CharField(max_length=20, choices=STATUS_CHOICES, default='vorschau')
    erstellt_von         = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='erstellte_eigentuemerwechsel',
    )
    freigegeben_von      = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='freigegebene_eigentuemerwechsel',
    )
    erstellt_am          = models.DateTimeField(auto_now_add=True)
    freigegeben_am       = models.DateTimeField(null=True, blank=True)
    auszahlungsbetrag    = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    auszahlungs_iban     = models.CharField(max_length=34, blank=True)
    notiz                = models.TextField(null=True, blank=True)
    auszahlung_unterdruecken = models.BooleanField(default=False)

    class Meta:
        verbose_name        = 'Eigentümerwechsel-Vorgang'
        verbose_name_plural = 'Eigentümerwechsel-Vorgänge'
        ordering            = ['-erstellt_am']
        constraints = [
            models.CheckConstraint(
                name='ev_vorgang_vier_augen',
                check=(
                    Q(freigegeben_von_id__isnull=True)
                    | ~Q(freigegeben_von_id=models.F('erstellt_von_id'))
                ),
            ),
        ]

    def __str__(self):
        return f"Wechsel {self.einheit} — {self.wechsel_datum} [{self.status}]"


class WechselKorrekturPaar(models.Model):
    """Read-only nach Erstellung. Verknüpft Original, Korrektur und Neuanlage je Periode."""
    id                              = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    wechsel_vorgang                 = models.ForeignKey(EigentuemerwechselVorgang, on_delete=models.PROTECT, related_name='korrektur_paare')
    periode                         = models.DateField()
    original_sollstellung           = models.ForeignKey(HausgeldSollstellung, on_delete=models.PROTECT, related_name='wechsel_als_original')
    korrektur_sollstellung          = models.ForeignKey(HausgeldSollstellung, on_delete=models.PROTECT, null=True, blank=True, related_name='wechsel_als_korrektur')
    neuanlage_sollstellung          = models.ForeignKey(HausgeldSollstellung, on_delete=models.PROTECT, null=True, blank=True, related_name='wechsel_als_neuanlage')
    original_ist_betrag_vor_korrektur = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        verbose_name        = 'Wechsel-Korrektur-Paar'
        verbose_name_plural = 'Wechsel-Korrektur-Paare'
        ordering            = ['periode']

    def __str__(self):
        return f"Paar {self.periode} — {self.wechsel_vorgang}"


# ---------------------------------------------------------------------------
# Wirtschaftsplan-Beschluss (Wirtschaftsplan-Spec v1.2)
# ---------------------------------------------------------------------------

class WirtschaftsplanBeschluss(models.Model):
    BESCHLUSS_TYP_CHOICES = [
        ('wirtschaftsplan',          'wirtschaftsplan'),
        ('umlaufbeschluss_stundung', 'umlaufbeschluss_stundung'),
        ('umlaufbeschluss_sonstig',  'umlaufbeschluss_sonstig'),
    ]
    STATUS_CHOICES = [
        ('erfasst',   'erfasst'),
        ('gebucht',   'gebucht'),
        ('storniert', 'storniert'),
    ]

    id                    = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt                = models.ForeignKey(Objekt, on_delete=models.PROTECT, related_name='wirtschaftsplan_beschluesse')
    beschluss_typ         = models.CharField(max_length=30, choices=BESCHLUSS_TYP_CHOICES)
    beschluss_datum       = models.DateField()
    protokoll_position    = models.CharField(max_length=50, null=True, blank=True)
    wirtschaftsplan_beginn = models.DateField()
    wirtschaftsplan_ende  = models.DateField(null=True, blank=True)
    gesamt_volumen        = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    protokoll_dokument    = models.ForeignKey(
        'dokumente.Dokument', on_delete=models.PROTECT, null=True, blank=True,
        related_name='wirtschaftsplan_beschluesse',
    )
    notiz                 = models.TextField(null=True, blank=True)
    status                = models.CharField(max_length=12, choices=STATUS_CHOICES, default='erfasst')
    erstellt_von          = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='erstellte_wirtschaftsplan_beschluesse',
    )
    erstellt_am           = models.DateTimeField(auto_now_add=True)
    gebucht_am            = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name        = 'Wirtschaftsplan-Beschluss'
        verbose_name_plural = 'Wirtschaftsplan-Beschlüsse'
        ordering            = ['-beschluss_datum']

    def __str__(self):
        return f"{self.get_beschluss_typ_display()} {self.objekt.bezeichnung} ab {self.wirtschaftsplan_beginn} [{self.status}]"


class WirtschaftsplanPosition(models.Model):
    id                    = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    beschluss             = models.ForeignKey(WirtschaftsplanBeschluss, on_delete=models.PROTECT, related_name='positionen')
    eigentumsverhaeltnis  = models.ForeignKey('personen.EigentumsVerhaeltnis', on_delete=models.PROTECT, related_name='wirtschaftsplan_positionen')
    buchungsart           = models.ForeignKey(Buchungsart, on_delete=models.PROTECT, related_name='wirtschaftsplan_positionen')
    betrag                = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        verbose_name        = 'Wirtschaftsplan-Position'
        verbose_name_plural = 'Wirtschaftsplan-Positionen'
        ordering            = ['beschluss', 'eigentumsverhaeltnis', 'buchungsart']
        constraints = [
            models.UniqueConstraint(
                fields=['beschluss', 'eigentumsverhaeltnis', 'buchungsart'],
                name='uniq_wp_position_beschluss_ev_ba',
            ),
        ]

    def __str__(self):
        return f"{self.beschluss} — {self.eigentumsverhaeltnis} — {self.buchungsart} — {self.betrag} €"


class WirtschaftsplanKorrekturPaar(models.Model):
    """Read-only nach Erstellung. Verknüpft Original, Korrektur und Neuanlage je Periode."""
    id                     = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    beschluss              = models.ForeignKey(WirtschaftsplanBeschluss, on_delete=models.PROTECT, related_name='korrektur_paare')
    eigentumsverhaeltnis   = models.ForeignKey('personen.EigentumsVerhaeltnis', on_delete=models.PROTECT, related_name='wp_korrektur_paare')
    periode                = models.DateField()
    original_sollstellung  = models.ForeignKey(HausgeldSollstellung, on_delete=models.PROTECT, related_name='wp_als_original')
    korrektur_sollstellung = models.ForeignKey(HausgeldSollstellung, on_delete=models.PROTECT, related_name='wp_als_korrektur')
    neuanlage_sollstellung = models.ForeignKey(HausgeldSollstellung, on_delete=models.PROTECT, related_name='wp_als_neuanlage')
    differenz_betrag       = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        verbose_name        = 'Wirtschaftsplan-Korrektur-Paar'
        verbose_name_plural = 'Wirtschaftsplan-Korrektur-Paare'
        ordering            = ['beschluss', 'eigentumsverhaeltnis', 'periode']

    def __str__(self):
        return f"WP-Paar {self.periode} — {self.beschluss}"


# ---------------------------------------------------------------------------
# Auszahlungslauf — Gutschriften / Auszahlungen an Eigentümer
# ---------------------------------------------------------------------------

class Auszahlungslauf(models.Model):
    TYP_CHOICES = [
        ('abrechnungsguthaben', 'Abrechnungsguthaben'),
        ('ruecklage_entnahme',  'Rücklagen-Entnahme'),
        ('wp_gutschrift',       'WP-Gutschrift'),
    ]
    STATUS_CHOICES = [
        ('erstellt',    'Erstellt'),
        ('freigegeben', 'Freigegeben'),
        ('exportiert',  'Exportiert (XML heruntergeladen)'),
        ('eingereicht', 'Eingereicht'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt = models.ForeignKey(
        Objekt, on_delete=models.PROTECT, related_name='auszahlungslaeufe'
    )
    typ = models.CharField(max_length=25, choices=TYP_CHOICES)
    bezeichnung = models.CharField(max_length=255, blank=True)
    faelligkeitsdatum = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='erstellt')
    wirtschaftsplan = models.ForeignKey(
        'abrechnung_wp.Wirtschaftsplan',
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name='auszahlungslaeufe',
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='auszahlungslaeufe'
    )
    anzahl_positionen = models.IntegerField(default=0)
    gesamt_summe = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    positionen = models.JSONField(default=list, blank=True)
    datei_pfad = models.CharField(max_length=500, null=True, blank=True)

    class Meta:
        verbose_name = 'Auszahlungslauf'
        verbose_name_plural = 'Auszahlungsläufe'
        ordering = ['-erstellt_am']

    def __str__(self):
        return (
            f"Auszahlung {self.bezeichnung or self.faelligkeitsdatum} "
            f"| {self.objekt.bezeichnung} [{self.status}]"
        )
