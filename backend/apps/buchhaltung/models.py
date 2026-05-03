from uuid import uuid4
from django.conf import settings
from django.db import models
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
    wirtschaftsjahr = models.IntegerField(null=True, blank=True)
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
        related_name='buchungen'
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
# Sollstellungslauf — periodische Forderungen an Eigentümer
# ---------------------------------------------------------------------------

class SollstellungsLauf(models.Model):
    TRIGGER_CHOICES = [
        ('automatisch', 'Automatisch'),
        ('manuell', 'Manuell'),
    ]
    STATUS_CHOICES = [
        ('simulation', 'Simulation'),
        ('ausstehend', 'Ausstehend (wartet auf Freigabe)'),
        ('freigegeben', 'Freigegeben'),
        ('ausgefuehrt', 'Ausgeführt'),
        ('fehler', 'Fehler'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt = models.ForeignKey(
        Objekt, on_delete=models.PROTECT, related_name='sollstellungslaeufe'
    )
    periode_von = models.DateField()
    periode_bis = models.DateField()
    trigger = models.CharField(
        max_length=12, choices=TRIGGER_CHOICES, default='manuell'
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='simulation'
    )
    ba_filter = models.JSONField(default=list, blank=True)
    anzahl_buchungen = models.IntegerField(default=0)
    gesamt_summe = models.DecimalField(
        max_digits=14, decimal_places=2, default=0
    )
    freigabe_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='freigegebene_sollstellungslaeufe'
    )
    freigabe_am = models.DateTimeField(null=True, blank=True)
    ausgefuehrt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='sollstellungslaeufe'
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)
    fehler_log = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name = 'Sollstellungslauf'
        verbose_name_plural = 'Sollstellungsläufe'
        ordering = ['-erstellt_am']

    def __str__(self):
        return (
            f"Sollstellungslauf {self.periode_von}–{self.periode_bis} "
            f"| {self.objekt.bezeichnung} [{self.status}]"
        )


class Sollstellung(models.Model):
    STATUS_CHOICES = [
        ('vorschau', 'Vorschau'),
        ('gebucht', 'Gebucht'),
        ('fehler', 'Fehler'),
        ('storniert', 'Storniert'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    lauf = models.ForeignKey(
        SollstellungsLauf, on_delete=models.CASCADE,
        related_name='sollstellungen'
    )
    personenkonto = models.ForeignKey(
        Personenkonto, on_delete=models.PROTECT,
        related_name='sollstellungen'
    )
    buchungsart = models.ForeignKey(
        Buchungsart, on_delete=models.PROTECT,
        null=True, blank=True, related_name='sollstellungen'
    )
    buchung = models.OneToOneField(
        Buchung, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='sollstellung'
    )
    betrag = models.DecimalField(max_digits=12, decimal_places=2)
    periode_monat = models.IntegerField()
    periode_jahr = models.IntegerField()
    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default='vorschau'
    )
    fehler_meldung = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Sollstellung'
        verbose_name_plural = 'Sollstellungen'
        ordering = ['-periode_jahr', '-periode_monat']
        constraints = [
            models.UniqueConstraint(
                fields=['personenkonto', 'buchungsart', 'periode_monat', 'periode_jahr'],
                condition=models.Q(status__in=['vorschau', 'gebucht']),
                name='unique_aktive_sollstellung',
            )
        ]

    def __str__(self):
        return (
            f"Sollstellung {self.periode_monat:02d}/{self.periode_jahr} "
            f"| {self.personenkonto} | {self.betrag} €"
        )


# ---------------------------------------------------------------------------
# E-Banking — CAMT-Import-Einstellungen + Kontoumsätze
# ---------------------------------------------------------------------------

class CamtImportEinstellung(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
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


class Kontoumsatz(models.Model):
    STATUS_CHOICES = [
        ('importiert', 'Importiert'),
        ('erkannt', 'Erkannt (KI-Vorschlag)'),
        ('manuell', 'Manuell zugeordnet'),
        ('gebucht', 'Gebucht'),
        ('ignoriert', 'Ignoriert'),
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
    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default='importiert'
    )
    buchung = models.ForeignKey(
        Buchung, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='kontoumsaetze'
    )
    ki_vorschlag = models.JSONField(null=True, blank=True)
    import_datei = models.CharField(max_length=500, blank=True)
    importiert_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Kontoumsatz'
        verbose_name_plural = 'Kontoumsätze'
        ordering = ['-buchungsdatum', '-importiert_am']

    def __str__(self):
        return (
            f"{self.buchungsdatum} | {self.betrag} € | "
            f"{self.auftraggeber_name} [{self.status}]"
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

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt = models.ForeignKey(
        Objekt, on_delete=models.PROTECT, related_name='lastschrift_laeufe'
    )
    sollstellungs_lauf = models.ForeignKey(
        SollstellungsLauf, on_delete=models.PROTECT,
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

    class Meta:
        verbose_name = 'Lastschrift-Lauf'
        verbose_name_plural = 'Lastschrift-Läufe'
        ordering = ['-erstellt_am']

    def __str__(self):
        return (
            f"Lastschrift {self.bezeichnung or self.faelligkeitsdatum} "
            f"| {self.objekt.bezeichnung} [{self.status}]"
        )
