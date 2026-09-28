from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.objekte.models import Objekt, Einheit
from apps.personen.models import Person


PRIORITAET_CHOICES = [
    ('niedrig', 'Niedrig'),
    ('normal',  'Normal'),
    ('hoch',    'Hoch'),
]


class VorgangTyp(models.Model):
    """Pflegbare Stammdaten für Vorgangs-Typen (Spec Kap. 1.1)."""

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    code = models.CharField(max_length=30, unique=True)
    bezeichnung = models.CharField(max_length=100)
    standard_prioritaet = models.CharField(
        max_length=10, choices=PRIORITAET_CHOICES, default='normal',
    )
    aktiv = models.BooleanField(default=True)
    sortierung = models.IntegerField(default=0)
    antwort_vorschlag_aktiv = models.BooleanField(
        default=False,
        verbose_name='KI-Antwortvorschlag bei Anlage',
        help_text='Erzeugt bei Anlage eines Vorgangs dieses Typs automatisch '
                  'einen KI-Antwortvorschlag (Folgeauftrag KI-Antwortvorschlag).',
    )
    portal_erstellbar = models.BooleanField(
        default=False,
        verbose_name='Im Portal erstellbar',
        help_text='Steuert, ob der Typ im Portal-Formular "Neuer Vorgang" zur '
                  'Auswahl steht (Spec Portal-Erweiterung v1.1, Kap. 4).',
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='erstellte_vorgang_typen',
    )

    class Meta:
        verbose_name = 'Vorgangs-Typ'
        verbose_name_plural = 'Vorgangs-Typen'
        ordering = ['sortierung', 'bezeichnung']

    def __str__(self):
        return self.bezeichnung


class VorgangNummerZaehler(models.Model):
    """Zähler pro Kalenderjahr für ``Vorgang.nummer`` (Format ``V-{JJ}-{LFD5}``).

    Zugriff ausschließlich über ``VorgangNummerZaehler.naechste_nummer()`` —
    SELECT FOR UPDATE innerhalb einer Transaktion verhindert doppelte
    Nummernvergabe bei gleichzeitigen Anfragen (analog ``BelegnummerZaehler``,
    ``OposSequenz``).
    """
    jahr = models.IntegerField(primary_key=True)
    letzter_zaehler = models.IntegerField(default=0)

    class Meta:
        verbose_name = 'Vorgang-Nummer-Zähler'
        verbose_name_plural = 'Vorgang-Nummer-Zähler'

    @classmethod
    @transaction.atomic
    def naechste_nummer(cls, jahr: int | None = None) -> str:
        """Vergibt atomar die nächste Vorgangsnummer für das angegebene Jahr
        (Default: laufendes Jahr). Muss innerhalb einer Transaktion enden,
        wird hier selbst über ``@transaction.atomic`` sichergestellt.
        """
        jahr = jahr or timezone.now().year
        zaehler, _ = cls.objects.select_for_update().get_or_create(
            jahr=jahr, defaults={'letzter_zaehler': 0},
        )
        zaehler.letzter_zaehler += 1
        zaehler.save(update_fields=['letzter_zaehler'])
        jj = f"{jahr % 100:02d}"
        return f"V-{jj}-{zaehler.letzter_zaehler:05d}"


class Vorgang(models.Model):
    """Generische Fallakte (Spec Kap. 1.2) — ersetzt das alte ``Ticket``-Modell."""

    QUELLE_CHOICES = [
        ('manuell',  'Manuell'),
        ('mail',     'E-Mail'),
        ('telefon',  'Telefon'),
        ('beschluss','Beschluss'),
        ('portal',   'Eigentümer-Portal'),
    ]
    STATUS_CHOICES = [
        ('offen',           'Offen'),
        ('in_bearbeitung',  'In Bearbeitung'),
        ('wartet_extern',   'Wartet auf Dritte'),
        ('wiedervorlage',   'Wiedervorlage'),
        ('erledigt',        'Erledigt'),
        ('storniert',       'Storniert'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    nummer = models.CharField(max_length=20, unique=True, editable=False)
    typ = models.ForeignKey(
        VorgangTyp, on_delete=models.PROTECT, related_name='vorgaenge',
    )
    quelle = models.CharField(max_length=10, choices=QUELLE_CHOICES, default='manuell')

    objekt = models.ForeignKey(
        Objekt, on_delete=models.PROTECT, null=True, blank=True,
        related_name='vorgaenge',
    )
    einheit = models.ForeignKey(
        Einheit, on_delete=models.PROTECT, null=True, blank=True,
        related_name='vorgaenge',
    )
    person = models.ForeignKey(
        Person, on_delete=models.PROTECT, null=True, blank=True,
        related_name='vorgaenge',
    )

    betreff = models.CharField(max_length=200)
    beschreibung = models.TextField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='offen')
    prioritaet = models.CharField(max_length=10, choices=PRIORITAET_CHOICES, default='normal')

    zugewiesen_an = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='zugewiesene_vorgaenge',
    )

    faellig_am = models.DateField(null=True, blank=True)
    wiedervorlage_am = models.DateField(null=True, blank=True)

    mail_referenz = models.CharField(max_length=255, null=True, blank=True)
    telefon_rufnummer = models.CharField(max_length=30, null=True, blank=True)
    portal_sichtbar = models.BooleanField(default=False)

    erstellt_am = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='erstellte_vorgaenge',
    )
    geschlossen_am = models.DateTimeField(null=True, blank=True)
    geschlossen_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='geschlossene_vorgaenge',
    )

    class Meta:
        verbose_name = 'Vorgang'
        verbose_name_plural = 'Vorgänge'
        ordering = ['-erstellt_am']

    def clean(self):
        super().clean()
        if not (self.objekt_id or self.einheit_id or self.person_id):
            raise ValidationError(
                'Ein Vorgang ohne Objekt, Einheit oder Person ist nicht auswertbar '
                '— mindestens eines der drei Felder muss gesetzt sein.'
            )
        if self.einheit_id and self.objekt_id and self.einheit.objekt_id != self.objekt_id:
            raise ValidationError('Einheit gehört nicht zum angegebenen Objekt.')
        if self.wiedervorlage_am and self.status != 'wiedervorlage':
            raise ValidationError(
                'wiedervorlage_am darf nur bei status="wiedervorlage" gesetzt sein.'
            )

    def save(self, *args, **kwargs):
        if not self.nummer:
            jahr = (self.erstellt_am or timezone.now()).year
            self.nummer = VorgangNummerZaehler.naechste_nummer(jahr)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nummer} — {self.betreff} [{self.get_status_display()}]"


class VorgangEreignis(models.Model):
    """Unveränderlicher Audit-Verlauf zu einem Vorgang (Spec Kap. 1.5, GoBD)."""

    TYP_CHOICES = [
        ('kommentar',                   'Kommentar'),
        ('statuswechsel',               'Statuswechsel'),
        ('zuweisung_geaendert',         'Zuweisung geändert'),
        ('dokument_verknuepft',         'Dokument verknüpft'),
        ('system_wiedervorlage_faellig','System: Wiedervorlage fällig'),
        ('antwort_vorschlag_erzeugt',   'KI-Antwortvorschlag erzeugt'),
        ('antwort_vorschlag_bearbeitet','KI-Antwortvorschlag bearbeitet'),
        ('antwort_vorschlag_freigegeben','KI-Antwortvorschlag freigegeben'),
        ('antwort_vorschlag_verworfen', 'KI-Antwortvorschlag verworfen'),
        ('handwerker_beauftragt',       'Handwerker beauftragt'),
        ('handwerker_angenommen',       'Handwerker: Auftrag angenommen'),
        ('handwerker_abgelehnt',        'Handwerker: Auftrag abgelehnt'),
        ('handwerker_abgeschlossen',    'Handwerker: Auftrag abgeschlossen'),
        ('handwerker_abgelaufen',       'Handwerker: Auftragsbestätigung abgelaufen'),
        ('mail_eingegangen',            'E-Mail eingegangen'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    vorgang = models.ForeignKey(
        Vorgang, on_delete=models.CASCADE, related_name='ereignisse',
    )
    typ = models.CharField(max_length=30, choices=TYP_CHOICES)
    text = models.TextField(null=True, blank=True)
    alter_wert = models.CharField(max_length=100, null=True, blank=True)
    neuer_wert = models.CharField(max_length=100, null=True, blank=True)
    intern = models.BooleanField(
        default=True,
        verbose_name='Intern',
        help_text='True (Default, sichere Seite) = nur für Mitarbeiter im '
                  'Verlauf sichtbar. False = für den Eigentümer sichtbar '
                  '(siehe vorgang_service.portal_ansicht) — muss bei jeder '
                  'Erzeugung eines Ereignisses bewusst gesetzt werden, ein '
                  'Versehen bedeutet dadurch immer "zu wenig", nie "zu viel" '
                  'preisgegeben. Bestandszeilen vor Einführung dieses Felds '
                  'sind automatisch intern (Migration ohne Datenmigration). '
                  'Wird ausschließlich bei der Anlage gesetzt — GoBD: kein '
                  'Endpunkt/keine UI zum nachträglichen Umschalten.',
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='erstellte_vorgang_ereignisse',
    )

    class Meta:
        verbose_name = 'Vorgangs-Ereignis'
        verbose_name_plural = 'Vorgangs-Ereignisse'
        ordering = ['erstellt_am']

    def __str__(self):
        return f"{self.vorgang.nummer} — {self.get_typ_display()}"


class VorgangAntwortVorschlag(models.Model):
    """KI-Antwortvorschlag zu einem ``Vorgang`` (Folgeauftrag KI-Antwortvorschlag,
    nicht Teil der ursprünglichen Vorgang & DMS-Spec).

    ``text_ki`` bleibt für die GoBD-Nachvollziehbarkeit UNVERÄNDERT der
    Originaltext der KI-Antwort — Bearbeitungen landen ausschließlich in
    ``text``. Statuswechsel laufen ausschließlich über
    ``antwort_vorschlag_service`` (nie durch direktes Setzen von ``status``).
    """

    STATUS_CHOICES = [
        ('entwurf',      'Entwurf'),
        ('freigegeben',  'Freigegeben'),
        ('verworfen',    'Verworfen'),
        ('fehlgeschlagen','Fehlgeschlagen'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    vorgang = models.ForeignKey(
        Vorgang, on_delete=models.CASCADE, related_name='antwort_vorschlaege',
    )
    text_ki = models.TextField(
        blank=True, default='',
        verbose_name='KI-Originaltext',
        help_text='Unveränderter KI-Originaltext — wird nie überschrieben (GoBD).',
    )
    text = models.TextField(
        blank=True, default='',
        verbose_name='Aktueller Text',
        help_text='Aktueller (ggf. vom Mitarbeiter bearbeiteter) Stand.',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='entwurf')
    modell = models.CharField(max_length=50, blank=True, default='')
    fehler = models.TextField(null=True, blank=True)

    erzeugt_am = models.DateTimeField(auto_now_add=True)
    erzeugt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='erzeugte_antwort_vorschlaege',
        help_text='None = automatisch bei Vorgangsanlage erzeugt.',
    )
    bearbeitet_am = models.DateTimeField(null=True, blank=True)
    bearbeitet_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='bearbeitete_antwort_vorschlaege',
    )
    freigegeben_am = models.DateTimeField(null=True, blank=True)
    freigegeben_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='freigegebene_antwort_vorschlaege',
    )

    class Meta:
        verbose_name = 'KI-Antwortvorschlag'
        verbose_name_plural = 'KI-Antwortvorschläge'
        ordering = ['-erzeugt_am']
        constraints = [
            models.UniqueConstraint(
                fields=['vorgang'],
                condition=models.Q(status='entwurf'),
                name='uniq_ein_entwurf_je_vorgang',
            ),
        ]

    def __str__(self):
        return f"{self.vorgang.nummer} — Antwortvorschlag ({self.get_status_display()})"


class MailImportProtokoll(models.Model):
    """Ein Eintrag je verarbeiteter ``.eml``-Datei aus dem Mail-Posteingang.

    Zweck ist AUSDRÜCKLICH die Messbarkeit der Erkennung: jede Datei
    hinterlässt hier eine Zeile mit dem, was Stufe 1 (regelbasiert) und
    Stufe 2 (KI) erkannt haben — auch dann, wenn kein Vorgang entstanden ist.
    Ohne dieses Protokoll liesse sich die Trefferquote nur aus Logzeilen
    rekonstruieren.

    ``bewertung`` wird NICHT vom System gesetzt, sondern beim Testlauf vom
    Menschen — daraus entsteht die eigentliche Auswertung (``mail_scan
    --auswertung``). Das Protokoll ist reine Diagnose und hat deshalb bewusst
    keine GoBD-Relevanz: es darf gelöscht und neu erzeugt werden.
    """

    STATUS_CHOICES = [
        ('vorgang_neu',       'Neuer Vorgang angelegt'),
        ('thread_zuordnung',  'Bestehendem Vorgang zugeordnet'),
        ('duplikat',          'Duplikat (Message-ID bereits verarbeitet)'),
        ('nicht_zugeordnet',  'Nicht zugeordnet (Absender unbekannt)'),
        ('fehler',            'Fehler'),
    ]
    # Wie die Person gefunden wurde — die entscheidende Kennzahl dafür, ob die
    # regelbasierte Stufe trägt oder ob die KI die Arbeit macht.
    ZUORDNUNG_CHOICES = [
        ('email_exakt',   'E-Mail-Adresse exakt'),
        ('email_geteilt', 'E-Mail-Adresse, von mehreren Personen genutzt'),
        ('name_betreff',  'Name/Objekt aus Betreff'),
        ('ki',            'KI-Vorschlag'),
        ('keine',         'Keine Zuordnung'),
    ]
    BEWERTUNG_CHOICES = [
        ('offen',    'Noch nicht bewertet'),
        ('richtig',  'Erkennung korrekt'),
        ('teilweise','Teilweise korrekt'),
        ('falsch',   'Erkennung falsch'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)

    # --- Quelle -----------------------------------------------------------
    dateiname = models.CharField(max_length=255)
    message_id = models.CharField(
        max_length=255, blank=True, default='', db_index=True,
        help_text='Message-ID-Header der Mail — Duplikatkennung.',
    )
    bezug_message_id = models.CharField(
        max_length=255, blank=True, default='',
        verbose_name='Bezug (In-Reply-To)',
        help_text='Message-ID der Mail, auf die geantwortet wurde. Ohne '
                  'dieses Feld laesst sich im Nachhinein nicht mehr '
                  'feststellen, ob eine Thread-Zuordnung mangels Bezug '
                  'unterblieb oder weil der bezogene Vorgang zum '
                  'Verarbeitungszeitpunkt noch nicht existierte.',
    )
    absender = models.CharField(max_length=320, blank=True, default='')
    absender_name = models.CharField(max_length=200, blank=True, default='')
    betreff = models.CharField(max_length=500, blank=True, default='')
    gesendet_am = models.DateTimeField(null=True, blank=True)
    body_auszug = models.TextField(
        blank=True, default='',
        help_text='Erste Zeichen des Mailtexts — für die Sichtprüfung im Report.',
    )
    anhaenge_anzahl = models.IntegerField(default=0)

    # --- Ergebnis ---------------------------------------------------------
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    vorgang = models.ForeignKey(
        Vorgang, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='mail_importe',
        help_text='Der angelegte bzw. zugeordnete Vorgang (SET_NULL: das '
                  'Protokoll überlebt das Löschen eines Testvorgangs).',
    )

    # --- Stufe 1: regelbasiert -------------------------------------------
    person = models.ForeignKey(
        Person, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='mail_import_protokolle',
    )
    objekt = models.ForeignKey(
        Objekt, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='mail_import_protokolle',
    )
    einheit = models.ForeignKey(
        Einheit, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='mail_import_protokolle',
    )
    zuordnung_quelle = models.CharField(
        max_length=20, choices=ZUORDNUNG_CHOICES, default='keine',
    )
    mehrdeutig = models.BooleanField(
        default=False,
        help_text='True = Person oder Einheit liessen sich nicht eindeutig '
                  'bestimmen (Adresse von mehreren Personen genutzt, mehrere '
                  'Einheiten, oder nur ein beendetes Eigentumsverhaeltnis). '
                  'Was offen blieb, wurde bewusst NICHT geraten.',
    )
    personen_treffer = models.IntegerField(
        default=0,
        verbose_name='Personen unter dieser Adresse',
        help_text='Wie viele Personen die Absenderadresse fuehren. >1 heisst '
                  'geteilte Adresse — in den Stammdaten sind das teils '
                  'Ehepaare mit getrennten Datensaetzen, teils echte '
                  'Dubletten. Macht die Kennzahl "Einheit eindeutig" '
                  'erklaerbar.',
    )

    # --- Stufe 2: KI ------------------------------------------------------
    ki_typ_code = models.CharField(max_length=30, blank=True, default='')
    ki_prioritaet = models.CharField(max_length=10, blank=True, default='')
    ki_betreff = models.CharField(max_length=200, blank=True, default='')
    ki_konfidenz = models.DecimalField(
        max_digits=4, decimal_places=3, null=True, blank=True,
        help_text='0.000–1.000, Selbsteinschätzung der KI.',
    )
    ki_begruendung = models.TextField(blank=True, default='')
    ki_modell = models.CharField(max_length=50, blank=True, default='')
    ki_fehler = models.TextField(blank=True, default='')

    # --- Auswertung (manuell) --------------------------------------------
    # --- Posteingang (Schritt 2) -----------------------------------------
    # Bewusst GETRENNT von ``status``: dort steht, was beim Import passiert
    # ist (unveraenderliche Tatsache), hier, was ein Mensch daraus gemacht
    # hat. Wuerde man ``status`` ueberschreiben, ginge die Erkennungs-
    # auswertung verloren, sobald jemand im Posteingang arbeitet.
    POSTEINGANG_CHOICES = [
        ('automatisch', 'Automatisch zugeordnet'),
        ('offen',       'Offen — wartet auf Zuordnung'),
        ('zugeordnet',  'Von Hand zugeordnet'),
        ('abgelegt',    'Nur abgelegt (kein Vorgang noetig)'),
        ('verworfen',   'Verworfen'),
    ]
    posteingang_status = models.CharField(
        max_length=12, choices=POSTEINGANG_CHOICES, default='offen',
        db_index=True,
        verbose_name='Posteingang',
        help_text='"automatisch" = beim Import bereits zugeordnet, gehoert '
                  'nie in die Posteingangsliste. "offen" = wartet auf eine '
                  'Entscheidung.',
    )
    erledigt_am = models.DateTimeField(null=True, blank=True)
    erledigt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='erledigte_mail_importe',
    )
    erledigt_notiz = models.TextField(
        blank=True, default='',
        help_text='Warum so entschieden — vor allem beim Verwerfen die '
                  'einzige Spur, die bleibt.',
    )

    bewertung = models.CharField(
        max_length=10, choices=BEWERTUNG_CHOICES, default='offen',
    )
    bewertung_notiz = models.TextField(blank=True, default='')

    fehler = models.TextField(blank=True, default='')
    verarbeitet_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Mail-Import-Protokoll'
        verbose_name_plural = 'Mail-Import-Protokolle'
        ordering = ['-verarbeitet_am']

    def __str__(self):
        return f"{self.dateiname} — {self.get_status_display()}"
