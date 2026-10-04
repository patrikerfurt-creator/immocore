"""Vorlagen & Korrespondenz — Datenmodell (Phase 1).

Spec: docs/CLAUDE_CODE_ANLEITUNG_VORLAGEN_KORRESPONDENZ_v1_2.md, Kap. 3.1-3.9.

Phase 1 enthält bewusst NUR Felder, Constraints und ``__str__``. Geschäftslogik
(Nummernvergabe, Statusübergänge, Rendering) liegt später in ``services/``.
Fremdschlüssel auf andere Apps sind als String-Referenzen angelegt, um
Import-Zyklen zu vermeiden.
"""
from uuid import uuid4

from django.conf import settings
from django.db import models
from django.db.models import Q


class Briefbogen(models.Model):
    """Absender-, Infoblock- und Fußzeilendaten des Briefbogens (3.1)."""

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    bezeichnung = models.CharField(max_length=100)
    firma_name = models.CharField(max_length=200)
    firma_strasse = models.CharField(max_length=200, blank=True)
    firma_plz = models.CharField(max_length=10, blank=True)
    firma_ort = models.CharField(max_length=100, blank=True)
    telefon = models.CharField(max_length=50, blank=True)
    email = models.CharField(max_length=200, blank=True)
    web = models.CharField(max_length=200, blank=True)
    sprechzeiten = models.TextField(blank=True)
    hinweis_infoblock = models.TextField(blank=True)
    logo = models.ForeignKey(
        'dokumente.Dokument', on_delete=models.PROTECT, related_name='+',
    )
    fuss_logo = models.ForeignKey(
        'dokumente.Dokument', on_delete=models.PROTECT, related_name='+',
        null=True, blank=True,
    )
    fuss_firma_zeile1 = models.CharField(max_length=200, blank=True)
    fuss_firma_zeile2 = models.CharField(max_length=200, blank=True)
    fuss_firma_zeile3 = models.CharField(max_length=200, blank=True)
    pflichtangaben = models.CharField(max_length=300, blank=True)
    pflichtangaben_anzeigen = models.BooleanField(
        default=True,
        help_text='GmbH-Pflichtangaben (§ 35a GmbHG) als 6-pt-Zeile unter der '
                  'WEG-Bankverbindung drucken (Spec 5.4).',
    )
    steuerzeichen_unsichtbar = models.CharField(max_length=50, blank=True)
    ist_standard = models.BooleanField(default=False)
    aktiv = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Briefbogen'
        verbose_name_plural = 'Briefbögen'
        ordering = ['bezeichnung']

    def __str__(self):
        return self.bezeichnung


class Vorlage(models.Model):
    """Wiederverwendbare Schreibvorlage; der Inhalt steckt in ``VorlagenVersion`` (3.2)."""

    ANLASS_CHOICES = [
        ('eigentuemer_begruessung',    'Begrüßung neuer Eigentümer'),
        ('eigentuemer_verabschiedung', 'Verabschiedung Voreigentümer'),
        ('mahnung_stufe_1',            'Mahnung Stufe 1 (Zahlungserinnerung)'),
        ('mahnung_stufe_2',            'Mahnung Stufe 2'),
        ('mahnung_stufe_3',            'Mahnung Stufe 3 (letzte Mahnung)'),
        ('etv_einladung',              'Einladung Eigentümerversammlung'),
        ('eigentuemer_allgemein',      'Allgemeines Eigentümerschreiben'),
        ('vorgang_antwort',            'Vorgangsantwort'),
    ]
    KANAL_CHOICES = [
        ('brief',  'Brief'),
        ('email',  'E-Mail'),
        ('beides', 'Brief und E-Mail'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    code = models.CharField(max_length=50)
    bezeichnung = models.CharField(max_length=150)
    anlass = models.CharField(max_length=40, choices=ANLASS_CHOICES)
    objekt = models.ForeignKey(
        'objekte.Objekt', on_delete=models.PROTECT,
        null=True, blank=True, related_name='korrespondenz_vorlagen',
        help_text='Leer = globale Vorlage; gesetzt = objektspezifische Übersteuerung.',
    )
    briefbogen = models.ForeignKey(
        Briefbogen, on_delete=models.PROTECT,
        null=True, blank=True, related_name='vorlagen',
        help_text='Leer = Standard-Briefbogen.',
    )
    kanal_standard = models.CharField(
        max_length=10, choices=KANAL_CHOICES, default='brief',
    )
    einzeln_bearbeitbar = models.BooleanField(default=False)
    aktive_version = models.ForeignKey(
        'korrespondenz.VorlagenVersion', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )
    aktiv = models.BooleanField(default=True)
    erstellt_am = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='erstellte_korrespondenz_vorlagen',
    )
    geaendert_am = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Vorlage'
        verbose_name_plural = 'Vorlagen'
        ordering = ['code']
        constraints = [
            models.UniqueConstraint(
                fields=['code', 'objekt'], name='korr_vorlage_code_objekt_uniq',
            ),
            # NULL gilt in PostgreSQL als "verschieden": ohne diese zweite
            # Regel könnte ein Code mehrfach global (objekt=NULL) existieren.
            models.UniqueConstraint(
                fields=['code'], condition=Q(objekt__isnull=True),
                name='korr_vorlage_code_global_uniq',
            ),
        ]

    def __str__(self):
        return f"{self.code} — {self.bezeichnung}"


class VorlagenVersion(models.Model):
    """Versionsstand einer Vorlage; nach Freigabe unveränderlich (3.3-3.5)."""

    STATUS_CHOICES = [
        ('entwurf',     'Entwurf'),
        ('freigegeben', 'Freigegeben'),
        ('abgeloest',   'Abgelöst'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    vorlage = models.ForeignKey(
        Vorlage, on_delete=models.CASCADE, related_name='versionen',
    )
    version = models.PositiveIntegerField()
    betreff = models.CharField(max_length=250)
    inhalt = models.JSONField(default=list, help_text='Blockstruktur, siehe Spec 3.4.')
    email_begleittext = models.TextField(blank=True)
    eingabefelder = models.JSONField(default=list, blank=True, help_text='Spec 3.5.')
    pflicht_platzhalter = models.JSONField(default=list, blank=True)
    parameter = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='entwurf')
    freigegeben_am = models.DateTimeField(null=True, blank=True)
    freigegeben_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='freigegebene_korrespondenz_versionen',
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='erstellte_korrespondenz_versionen',
    )

    class Meta:
        verbose_name = 'Vorlagen-Version'
        verbose_name_plural = 'Vorlagen-Versionen'
        ordering = ['vorlage', '-version']
        constraints = [
            models.UniqueConstraint(
                fields=['vorlage', 'version'], name='korr_version_vorlage_nr_uniq',
            ),
        ]
        permissions = [
            ('vorlage_freigeben', 'Darf Vorlagenversionen freigeben'),
        ]

    def __str__(self):
        return f"{self.vorlage.code} v{self.version} [{self.status}]"


class Textbaustein(models.Model):
    """Wiederverwendbarer Textblock, im Vorlageninhalt per Baustein-Block referenziert (3.6)."""

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    code = models.CharField(max_length=50)
    bezeichnung = models.CharField(max_length=150)
    inhalt = models.TextField()
    objekt = models.ForeignKey(
        'objekte.Objekt', on_delete=models.PROTECT,
        null=True, blank=True, related_name='korrespondenz_textbausteine',
        help_text='Leer = global.',
    )
    aktiv = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Textbaustein'
        verbose_name_plural = 'Textbausteine'
        ordering = ['code']
        constraints = [
            models.UniqueConstraint(
                fields=['code', 'objekt'], name='korr_baustein_code_objekt_uniq',
            ),
            models.UniqueConstraint(
                fields=['code'], condition=Q(objekt__isnull=True),
                name='korr_baustein_code_global_uniq',
            ),
        ]

    def __str__(self):
        return f"{self.code} — {self.bezeichnung}"


class VorlageAnlage(models.Model):
    """Anlage, die hinter dem Schreiben angefügt wird (3.7)."""

    ART_CHOICES = [
        ('dokument',         'Festes PDF-Dokument'),
        ('objekt_kategorie', 'Objektbezogenes Dokument (Kategorie)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    vorlage = models.ForeignKey(
        Vorlage, on_delete=models.CASCADE, related_name='anlagen',
    )
    art = models.CharField(max_length=20, choices=ART_CHOICES)
    bezeichnung = models.CharField(max_length=150)
    pflicht = models.BooleanField(default=False)
    reihenfolge = models.PositiveIntegerField(default=0)
    # Phase 5a: Felder für die Auflösung; verdrahtet in Phase 6b (anlagen_service).
    dokument = models.ForeignKey(
        'dokumente.Dokument', on_delete=models.PROTECT, related_name='+',
        null=True, blank=True,
        help_text='Festes PDF (nur bei art="dokument").',
    )
    objekt_kategorie = models.CharField(
        max_length=100, blank=True,
        help_text='Dokumentkategorie des Objekts (nur bei art="objekt_kategorie"), z. B. Hausordnung.',
    )
    # Phase 6b: bedingte Anlage (Spec 9.2: SEPA-Formular nur, wenn das Mandat fehlt).
    bedingung = models.CharField(
        max_length=200, blank=True,
        help_text='Optional: Platzhalter-Bedingung, z. B. ev.sepa_mandat_fehlt. '
                  'Die Anlage wird nur beigefügt, wenn sie erfüllt ist (leer = immer).',
    )

    class Meta:
        verbose_name = 'Vorlagen-Anlage'
        verbose_name_plural = 'Vorlagen-Anlagen'
        ordering = ['vorlage', 'reihenfolge']

    def __str__(self):
        return f"{self.vorlage.code}: {self.bezeichnung}"


class SchreibenNummerZaehler(models.Model):
    """Zähler pro Kalenderjahr für ``Schreiben.nummer`` (Format ``KS-YYYY-000123``).

    Phase 1: nur das Modell (Struktur analog ``VorgangNummerZaehler``). Die
    atomare Nummernvergabe folgt als Service in einer späteren Phase.
    """
    jahr = models.IntegerField(primary_key=True)
    letzter_zaehler = models.IntegerField(default=0)

    class Meta:
        verbose_name = 'Schreiben-Nummer-Zähler'
        verbose_name_plural = 'Schreiben-Nummer-Zähler'

    def __str__(self):
        return f"{self.jahr}: {self.letzter_zaehler}"


class Serienlauf(models.Model):
    """Serienbrief-Lauf: ein Schreiben je Eigentumsverhältnis (3.9)."""

    STATUS_CHOICES = [
        ('vorschau',         'Vorschau'),
        ('zur_pruefung',     'Zur Prüfung'),
        ('freigegeben',      'Freigegeben'),
        ('versendet',        'Versendet'),
        ('teilweise_fehler', 'Teilweise Fehler'),
        ('abgebrochen',      'Abgebrochen'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    vorlage_version = models.ForeignKey(
        VorlagenVersion, on_delete=models.PROTECT, related_name='serienlaeufe',
    )
    objekt = models.ForeignKey(
        'objekte.Objekt', on_delete=models.PROTECT,
        related_name='korrespondenz_serienlaeufe',
    )
    empfaenger_filter = models.JSONField(default=dict, blank=True)
    eingabewerte = models.JSONField(default=dict, blank=True)
    unterzeichner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='unterzeichnete_serienlaeufe',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='vorschau')
    anzahl = models.PositiveIntegerField(default=0)
    druck_dokument = models.ForeignKey(
        'dokumente.Dokument', on_delete=models.PROTECT,
        null=True, blank=True, related_name='+',
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='erstellte_serienlaeufe',
    )
    freigegeben_am = models.DateTimeField(null=True, blank=True)
    freigegeben_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='freigegebene_serienlaeufe',
    )

    class Meta:
        verbose_name = 'Serienlauf'
        verbose_name_plural = 'Serienläufe'
        ordering = ['-erstellt_am']

    def __str__(self):
        return f"Serienlauf {self.vorlage_version} / {self.objekt_id} [{self.status}]"


class Druckstapel(models.Model):
    """Sammel-PDF der zu druckenden Briefe (Phase 4, Spec 7.3).

    In Spec Abschnitt 3 nicht definiert; bewusst minimal. ``status`` ``offen``
    = Sammel-PDF liegt vor, gedruckt/kuvertiert ist noch nicht bestätigt;
    ``bestaetigt`` = Bestätigung "gedruckt und kuvertiert" ist erfolgt. Erst
    dann bekommen die enthaltenen Schreiben ``versendet_am``.
    """

    STATUS_CHOICES = [
        ('offen',      'Offen'),
        ('bestaetigt', 'Bestätigt'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    dokument = models.ForeignKey(
        'dokumente.Dokument', on_delete=models.PROTECT,
        null=True, blank=True, related_name='+',
    )
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='offen')
    erstellt_am = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='erstellte_druckstapel',
    )
    bestaetigt_am = models.DateTimeField(null=True, blank=True)
    bestaetigt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='bestaetigte_druckstapel',
    )

    class Meta:
        verbose_name = 'Druckstapel'
        verbose_name_plural = 'Druckstapel'
        ordering = ['-erstellt_am']

    def __str__(self):
        return f"Druckstapel {str(self.id)[:8]} [{self.status}]"


class Schreiben(models.Model):
    """Einzelnes erzeugtes Schreiben (Brief und/oder E-Mail) (3.8, 3.10)."""

    KANAL_CHOICES = [
        ('brief', 'Brief'),
        ('email', 'E-Mail'),
    ]
    STATUS_CHOICES = [
        ('entwurf',               'Entwurf'),
        ('zur_pruefung',          'Zur Prüfung'),
        ('freigegeben',           'Freigegeben'),
        ('versendet',             'Versendet'),
        ('verworfen',             'Verworfen'),
        ('versand_fehlgeschlagen', 'Versand fehlgeschlagen'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    nummer = models.CharField(max_length=20, unique=True, editable=False)
    vorlage_version = models.ForeignKey(
        VorlagenVersion, on_delete=models.PROTECT, related_name='schreiben',
    )
    empfaenger = models.ForeignKey(
        'personen.Person', on_delete=models.PROTECT,
        related_name='korrespondenz_schreiben',
    )
    objekt = models.ForeignKey(
        'objekte.Objekt', on_delete=models.PROTECT,
        null=True, blank=True, related_name='korrespondenz_schreiben',
    )
    einheit = models.ForeignKey(
        'objekte.Einheit', on_delete=models.PROTECT,
        null=True, blank=True, related_name='korrespondenz_schreiben',
    )
    eigentumsverhaeltnis = models.ForeignKey(
        'personen.EigentumsVerhaeltnis', on_delete=models.PROTECT,
        null=True, blank=True, related_name='korrespondenz_schreiben',
    )
    vorgang = models.ForeignKey(
        'vorgaenge.Vorgang', on_delete=models.PROTECT,
        null=True, blank=True, related_name='korrespondenz_schreiben',
    )
    mahnung = models.OneToOneField(
        'buchhaltung.Mahnung', on_delete=models.PROTECT,
        null=True, blank=True, related_name='korrespondenz_schreiben',
    )
    eigentuemerwechsel = models.ForeignKey(
        'buchhaltung.EigentuemerwechselVorgang', on_delete=models.PROTECT,
        null=True, blank=True, related_name='korrespondenz_schreiben',
    )
    serienlauf = models.ForeignKey(
        Serienlauf, on_delete=models.PROTECT,
        null=True, blank=True, related_name='schreiben',
    )
    unterzeichner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='unterzeichnete_schreiben',
    )
    ihr_zeichen = models.CharField(max_length=100, blank=True)
    ihr_schreiben_vom = models.DateField(null=True, blank=True)
    eingabewerte = models.JSONField(default=dict, blank=True)
    kanal = models.CharField(max_length=10, choices=KANAL_CHOICES, default='brief')
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='entwurf')
    inhalt_angepasst = models.JSONField(null=True, blank=True)
    html_gerendert = models.TextField(blank=True)
    kontext_snapshot = models.JSONField(default=dict, blank=True)
    dokument = models.ForeignKey(
        'dokumente.Dokument', on_delete=models.PROTECT,
        null=True, blank=True, related_name='korrespondenz_schreiben',
    )
    druckstapel = models.ForeignKey(
        Druckstapel, on_delete=models.PROTECT,
        null=True, blank=True, related_name='schreiben',
    )
    freigegeben_am = models.DateTimeField(null=True, blank=True)
    freigegeben_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='freigegebene_schreiben',
    )
    versendet_am = models.DateTimeField(null=True, blank=True)
    mail_message_id = models.CharField(max_length=255, blank=True)
    fehler = models.TextField(blank=True)
    erstellt_am = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='erstellte_schreiben',
    )

    class Meta:
        verbose_name = 'Schreiben'
        verbose_name_plural = 'Schreiben'
        ordering = ['-erstellt_am']
        constraints = [
            models.CheckConstraint(
                name='korr_schreiben_max_ein_kontext',
                condition=(
                    Q(mahnung__isnull=True, eigentuemerwechsel__isnull=True)
                    | Q(mahnung__isnull=True, serienlauf__isnull=True)
                    | Q(eigentuemerwechsel__isnull=True, serienlauf__isnull=True)
                ),
            ),
        ]

    def __str__(self):
        return f"{self.nummer} [{self.status}]"
