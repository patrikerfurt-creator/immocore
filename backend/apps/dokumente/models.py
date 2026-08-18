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
            try:
                self.rechnung
            except ObjectDoesNotExist:
                raise ValidationError(
                    'Dokument ohne Kontext-FK ist nur zulässig, wenn es über '
                    'Rechnung.beleg_dokument gekoppelt ist.'
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

    def __str__(self):
        return f"{self.dateiname} ({self.kategorie})"
