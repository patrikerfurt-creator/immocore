from itertools import combinations
from uuid import uuid4
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models
from django.db.models import Q
from apps.objekte.models import Objekt, Einheit
from apps.personen.models import Person


# Kontext-FKs, von denen ein Dokument höchstens eines gesetzt haben darf
# (Owner-Regel B-Hybrid, siehe Dokument.clean() und die DB-Constraint unten).
_KONTEXT_FELDER = ['objekt', 'einheit', 'vorgang', 'person']


class DokumentQuerySet(models.QuerySet):
    """Zentrale Abfrage-API: löst den Beziehungsgraphen auf (Objekt/Einheit/
    Vorgang/Person/Rechnung), statt dass Aufrufer einzelne FKs verodern.
    """

    def fuer_objekt(self, objekt):
        return self.filter(
            Q(objekt=objekt)
            | Q(einheit__objekt=objekt)
            | Q(vorgang__objekt=objekt)
            | Q(rechnung__objekt=objekt)
        ).distinct()

    def fuer_einheit(self, einheit):
        # Rechnung hat kein einheit-Feld — daher hier bewusst kein Q(rechnung__einheit=einheit).
        return self.filter(
            Q(einheit=einheit)
            | Q(vorgang__einheit=einheit)
        ).distinct()

    def fuer_person(self, person):
        return self.filter(
            Q(person=person)
            | Q(vorgang__person=person)
        ).distinct()


DokumentManager = models.Manager.from_queryset(DokumentQuerySet)


def _max_ein_kontext_check() -> Q:
    """Baut die DB-CheckConstraint 'höchstens einer der vier Kontext-FKs gesetzt'
    rein aus Q-Objekten (kein Raw-SQL): für jedes Paar von Kontext-Feldern gilt
    NICHT (beide gesetzt) — das entspricht in Summe 'Anzahl gesetzter Felder <= 1'.
    """
    check = Q()
    for a, b in combinations(_KONTEXT_FELDER, 2):
        paar_nicht_beide = ~(Q(**{f'{a}__isnull': False}) & Q(**{f'{b}__isnull': False}))
        check &= paar_nicht_beide
    return check


# ─────────────────────────────────────────────────────────────────────────────
# Belegnummer-Format:  AA00000001 … AA99999999 → AB00000001 … ZZ99999999
# Kapazität:  676 Präfixe × 99.999.999 = ~67,6 Milliarden eindeutige Nummern
# ─────────────────────────────────────────────────────────────────────────────

_PER_PREFIX = 99_999_999  # Nummern pro Buchstaben-Präfix (1–99999999)


def _format_belegnummer(n: int) -> str:
    """Wandelt einen 1-basierten Integer-Zähler in das Belegnummer-Format um.

    n=1         → AA00000001
    n=99999999  → AA99999999
    n=100000000 → AB00000001
    """
    idx           = n - 1
    prefix_index  = idx // _PER_PREFIX
    number        = idx % _PER_PREFIX + 1          # 1 … 99999999
    first         = chr(ord('A') + prefix_index // 26)
    second        = chr(ord('A') + prefix_index % 26)
    return f"{first}{second}{number:08d}"


class BelegnummerZaehler(models.Model):
    """Singleton-Tabelle: globaler Zähler für alle Belegnummern.

    Immer genau eine Zeile (pk=1). Zugriff ausschließlich über
    ``BelegnummerZaehler.naechste_nummer()`` innerhalb einer Transaktion —
    SELECT FOR UPDATE verhindert doppelte Nummernvergabe bei gleichzeitigen
    Anfragen.
    """
    id              = models.IntegerField(primary_key=True, default=1)
    letzter_zaehler = models.BigIntegerField(default=0)

    class Meta:
        verbose_name = 'Belegnummer-Zähler'

    def save(self, *args, **kwargs):
        self.pk = 1   # Singleton erzwingen
        super().save(*args, **kwargs)

    @classmethod
    def naechste_nummer(cls) -> str:
        """Vergibt atomar die nächste Belegnummer. Muss in atomic() aufgerufen werden."""
        zaehler, _ = cls.objects.select_for_update().get_or_create(
            pk=1, defaults={'letzter_zaehler': 0}
        )
        zaehler.letzter_zaehler += 1
        zaehler.save(update_fields=['letzter_zaehler'])
        return _format_belegnummer(zaehler.letzter_zaehler)


class Aktenregister(models.Model):
    """Gliederung der Akten — das "Register" im Sinne der Papierablage.

    Pflegbare Stammdaten, KEINE Code-Konstante: welche Register eine
    Hausverwaltung fuehrt, ist ihre eigene Ordnung und aendert sich ueber die
    Jahre. Deshalb hier eine Tabelle, die im Admin bearbeitet wird.

    ``eltern`` erlaubt Unterregister ("04 Versicherungen" -> "04.1 Gebaeude").
    Flache Gliederungen lassen das Feld einfach leer.

    ``aktenart`` sagt, in welcher Akte das Register erscheint. Ein Register
    kann in mehreren Akten gelten (z.B. "Schriftwechsel"); dafuer gibt es
    ``ALLE``, statt dasselbe Register mehrfach anzulegen.
    """

    AKTENART_HAUS = 'haus'
    AKTENART_WOHNUNG = 'wohnung'
    AKTENART_EIGENTUEMER = 'eigentuemer'
    AKTENART_ALLE = 'alle'
    AKTENART_CHOICES = [
        (AKTENART_HAUS,        'Hausakte'),
        (AKTENART_WOHNUNG,     'Wohnungsakte'),
        (AKTENART_EIGENTUEMER, 'Eigentuemerakte'),
        (AKTENART_ALLE,        'In allen Akten'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    code = models.CharField(
        max_length=20,
        help_text='Kurzzeichen der Ablage, z.B. "05" oder "05/A". Wird beim '
                  'Import aus einer Ordnerstruktur zum Wiedererkennen genutzt. '
                  'Nur zusammen mit objekt eindeutig — derselbe Code darf in '
                  'zwei Objekten fuer Verschiedenes stehen.',
    )
    objekt = models.ForeignKey(
        Objekt, on_delete=models.CASCADE, null=True, blank=True,
        related_name='aktenregister',
        help_text='Leer = gilt fuer ALLE Akten (die gemeinsame Gliederung). '
                  'Gesetzt = nur in der Akte dieses Objekts sichtbar — das '
                  'digitale Gegenstueck zum Trennblatt, das bei Bedarf in '
                  'genau einen Ordner gelegt wird ("05/A Hebeanlage"). '
                  'CASCADE: verschwindet das Objekt, verschwindet auch seine '
                  'eigene Untergliederung.',
    )
    bezeichnung = models.CharField(max_length=120)
    aktenart = models.CharField(
        max_length=12, choices=AKTENART_CHOICES, default=AKTENART_HAUS)
    eltern = models.ForeignKey(
        'self', on_delete=models.PROTECT, null=True, blank=True,
        related_name='unterregister',
        help_text='Leer = Register oberster Ebene.',
    )
    sortierung = models.IntegerField(default=0)
    aktiv = models.BooleanField(
        default=True,
        help_text='Inaktive Register verschwinden aus der Auswahl, die darin '
                  'bereits abgelegten Dokumente bleiben unberuehrt.',
    )
    hinweis = models.TextField(
        blank=True, default='',
        help_text='Was gehoert hier hinein — erscheint als Hilfetext an der '
                  'Ablagemaske.',
    )

    class Meta:
        verbose_name = 'Aktenregister'
        verbose_name_plural = 'Aktenregister'
        ordering = ['sortierung', 'code']
        constraints = [
            # Eindeutig je Objekt statt global: "05/A" heisst in Haus A
            # "Hebeanlage" und in Haus B vielleicht "Aufzug".
            models.UniqueConstraint(
                fields=['code', 'objekt'], name='uniq_register_code_je_objekt'),
            models.UniqueConstraint(
                fields=['code'], condition=Q(objekt__isnull=True),
                name='uniq_register_code_global'),
        ]

    def __str__(self):
        if self.objekt_id:
            return f"{self.code} {self.bezeichnung} ({self.objekt})"
        return f"{self.code} {self.bezeichnung}"

    def clean(self):
        super().clean()
        # Ein Register darf nicht sein eigener Vorfahr sein — sonst laeuft
        # jeder Aufbau des Baums endlos.
        knoten, gesehen = self.eltern, {self.pk}
        while knoten is not None:
            if knoten.pk in gesehen:
                raise ValidationError(
                    'Das uebergeordnete Register darf nicht zu einem Kreis fuehren.')
            gesehen.add(knoten.pk)
            knoten = knoten.eltern

        # Ein objektspezifisches Register haengt unter einem globalen ("05
        # Wartung") oder unter einem eigenen desselben Objekts. Unter dem
        # Register eines FREMDEN Objekts waere es in keiner Akte erreichbar.
        if (self.eltern is not None and self.eltern.objekt_id
                and self.eltern.objekt_id != self.objekt_id):
            raise ValidationError(
                'Das uebergeordnete Register gehoert zu einem anderen Objekt.')

    @property
    def voller_pfad(self) -> str:
        """"01 Stammdaten / 01.2 Teilungserklaerung" — fuer Listen und Export."""
        teile, knoten = [], self
        while knoten is not None:
            teile.append(str(knoten))
            knoten = knoten.eltern
        return ' / '.join(reversed(teile))


class Dokument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    datei = models.FileField(upload_to='dokumente/', max_length=1000)
    ABLAGE_WURZEL_CHOICES = [
        ('media',       'MEDIA_ROOT'),
        ('rechnungen',  'Rechnungen-Bind-Mount'),
    ]
    ablage_wurzel = models.CharField(
        max_length=20, choices=ABLAGE_WURZEL_CHOICES, default='media',
        help_text='Wurzel, unter der datei relativ aufgelöst wird — Zugriff nur über beleg_service.dokument_pfad()',
    )
    dateiname = models.CharField(max_length=255)
    titel = models.CharField(
        max_length=200, blank=True, default='',
        help_text='Sprechender Anzeigename. Der DATEINAME bleibt davon '
                  'unberuehrt — er ist die Bruecke zur Datei im Archivordner, '
                  'gehoert bei revisionssicheren Belegen zur '
                  'Nachvollziehbarkeit und ist der Name, unter dem der '
                  'Absender sein Dokument kennt. Leer = es wird der '
                  'Dateiname angezeigt (siehe anzeigename).',
    )
    kategorie = models.CharField(max_length=100)  # z.B. Teilungserklärung, Versicherung, Protokoll
    beschreibung = models.TextField(blank=True)
    objekt = models.ForeignKey(
        Objekt, on_delete=models.PROTECT, null=True, blank=True,
        related_name='dokumente'
    )
    einheit = models.ForeignKey(
        Einheit, on_delete=models.PROTECT, null=True, blank=True,
        related_name='dokumente'
    )
    vorgang = models.ForeignKey(
        'vorgaenge.Vorgang', on_delete=models.PROTECT, null=True, blank=True,
        related_name='dokumente'
    )
    person = models.ForeignKey(
        Person, on_delete=models.PROTECT, null=True, blank=True,
        related_name='dokumente'
    )
    register = models.ForeignKey(
        'Aktenregister', on_delete=models.PROTECT, null=True, blank=True,
        related_name='dokumente',
        help_text='Einordnung in die Aktengliederung. Leer = noch nicht '
                  'einsortiert; solche Dokumente sammelt die Aktenansicht '
                  'unter "Ohne Register", damit nichts unsichtbar wird.',
    )
    dokument_datum = models.DateField(
        null=True, blank=True,
        verbose_name='Datum des Dokuments',
        help_text='Das FACHLICHE Datum: wann die Mail gesendet, die Rechnung '
                  'gestellt, der Vertrag geschlossen wurde — nicht wann die '
                  'Datei abgelegt wurde. Entscheidet in der Eigentuemerakte '
                  'darueber, in wessen Besitzzeit ein Dokument faellt; ohne '
                  'Angabe gilt ersatzweise das Ablagedatum, was bei spaet '
                  'nachgereichten Altunterlagen falsch liegen kann.',
    )
    mail_import = models.ForeignKey(
        'vorgaenge.MailImportProtokoll', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='dokumente',
        help_text='Herkunft: aus dieser eingegangenen Mail stammt das Dokument '
                  '(die Mail selbst oder einer ihrer Anhaenge). Bewusst KEIN '
                  'Kontext-FK im Sinne der Owner-Regel — es sagt, WOHER das '
                  'Dokument kam, nicht WOZU es gehoert. Der Kontext wird '
                  'nachgetragen, sobald die Mail im Posteingang zugeordnet '
                  'wird.',
    )
    version = models.IntegerField(default=1)
    vorgaenger_version = models.ForeignKey(
        'self', on_delete=models.PROTECT, null=True, blank=True,
        related_name='nachfolger_versionen',
    )
    hochgeladen_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='hochgeladene_dokumente'
    )
    hochgeladen_am = models.DateTimeField(auto_now_add=True)

    # ── Beleg-/GoBD-Felder (Spec Beleg↔Dokument-Kopplung, Phase A) ──
    TYP_CHOICES = [
        ('beleg',          'Beleg'),
        ('vertrag',        'Vertrag'),
        ('korrespondenz',  'Korrespondenz'),
        ('beschluss',      'Beschluss'),
        ('abrechnung',     'Abrechnung'),
        ('sonstiges',      'Sonstiges'),
    ]
    dokument_typ = models.CharField(max_length=20, choices=TYP_CHOICES, default='sonstiges')
    revisionssicher = models.BooleanField(default=False)   # True = Lösch-/Austauschsperre (GoBD), Durchsetzung in Phase B
    revisionssicher_seit = models.DateTimeField(null=True, blank=True)
    sha256 = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    abgelegt_am = models.DateTimeField(auto_now_add=True)
    beleg_nummer = models.CharField(
        max_length=12, unique=True, null=True, blank=True, editable=False,
        help_text='Globale Belegnummer (AA00000001 …), Vergabe über BelegnummerZaehler',
    )

    objects = DokumentManager()

    class Meta:
        verbose_name = 'Dokument'
        verbose_name_plural = 'Dokumente'
        ordering = ['-hochgeladen_am']
        # HINWEIS Migrations-Reihenfolge (Live-Sicherheit): das CheckConstraint wurde
        # bewusst in einer separaten, späteren Migration aktiviert (siehe
        # 0008_dokument_max_ein_kontext_constraint.py) — NICHT in derselben
        # Migration wie die additiven Felder (0006). Dazwischen läuft die
        # Datenmigration 0007, die für alle über Rechnung.beleg_dokument
        # gekoppelten Dokumente objekt/einheit auf NULL setzt.
        constraints = [
            models.CheckConstraint(
                name='dokument_max_ein_kontext',
                check=_max_ein_kontext_check(),
            ),
        ]

    def clean(self):
        super().clean()
        anzahl = sum(1 for f in _KONTEXT_FELDER if getattr(self, f'{f}_id'))
        if anzahl > 1:
            raise ValidationError(
                'Dokument darf höchstens einen Kontext-FK (objekt/einheit/vorgang/person) '
                'gesetzt haben — der Owner muss eindeutig sein.'
            )
        if anzahl == 0:
            # Zwei Ausnahmen von der Owner-Regel, beide mit eigenem Anker:
            # der Rechnungsbeleg (Rechnung.beleg_dokument) und die eingegangene
            # Mail (mail_import). Bei der Mail ist die Kontextlosigkeit ein
            # ÜBERGANGSZUSTAND: aufbewahrt wird sofort, die Zuordnung trifft
            # später ein Mensch im Posteingang. Ohne diese Ausnahme wäre jede
            # Mail von einem unbekannten Absender nicht ablegbar — und damit
            # die Aufbewahrung lueckenhaft.
            if self.mail_import_id:
                return
            try:
                self.rechnung
            except ObjectDoesNotExist:
                raise ValidationError(
                    'Dokument ohne Kontext-FK ist nur zulässig, wenn es über '
                    'Rechnung.beleg_dokument gekoppelt oder über mail_import '
                    'einer eingegangenen Mail zugeordnet ist.'
                )

    def save(self, *args, **kwargs):
        # GoBD: bei revisionssicherem Dokument darf die Datei nicht ausgetauscht werden
        if self.pk:
            alt = Dokument.objects.filter(pk=self.pk).values('revisionssicher', 'datei').first()
            if alt and alt['revisionssicher'] and alt['datei'] != self.datei.name:
                raise ValidationError(
                    'Revisionssicheres Dokument: Datei darf nicht ausgetauscht werden (GoBD).'
                )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.revisionssicher:
            raise ValidationError(
                'Revisionssicheres Dokument darf nicht gelöscht werden (GoBD).'
            )
        return super().delete(*args, **kwargs)

    @property
    def anzeigename(self) -> str:
        """Was in Listen und Akten steht.

        Drei Stufen, absteigend:

        1. ``titel``, wenn jemand (oder die KI) einen gesetzt hat
        2. bei einem Rechnungsbeleg aus der Rechnung ABGELEITET — bewusst
           nicht gespeichert, damit eine spaeter korrigierte Rechnung sofort
           durchschlaegt
        3. der Dateiname

        Kein Fall liefert eine leere Zeichenkette: eine Zeile ohne
        Bezeichnung waere in einer Liste nicht anklickbar.
        """
        if self.titel:
            return self.titel
        try:
            rechnung = self.rechnung
        except ObjectDoesNotExist:
            rechnung = None
        if rechnung is not None:
            teile = [
                (rechnung.kreditor.name if rechnung.kreditor_id
                 else rechnung.lieferant_name) or 'Unbekannter Kreditor',
                f'RG {rechnung.rechnungsnummer}' if rechnung.rechnungsnummer else '',
                f'{rechnung.rechnungsdatum:%d.%m.%Y}' if rechnung.rechnungsdatum else '',
            ]
            zusammen = ' · '.join(t for t in teile if t)
            if zusammen:
                return zusammen
        return self.dateiname

    def __str__(self):
        return f"{self.anzeigename} ({self.kategorie})"
