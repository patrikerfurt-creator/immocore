"""Handwerker-Verwaltung: Gewerke (Stammdaten), Objekt-Handwerker-Zuordnung
und Handwerkeraufträge mit GoBD-Audit-Spur (Ereignisse) und
Auftragsbestätigung per Token (Annahme/Ablehnung ohne Login).

Umsetzung von docs/CLAUDE_CODE_ANLEITUNG_HANDWERKERAUFTRAG_v1_0.md, Phase A —
mit verbindlichen Korrekturen gegenüber der Spec (siehe Orchestrator-Auftrag).
"""
import secrets
from datetime import datetime, time
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.buchhaltung.services.sepa_fristen_service import bd_addieren
from apps.objekte.models import Objekt
from apps.vorgaenge.models import PRIORITAET_CHOICES, Vorgang


class Gewerk(models.Model):
    """Pflegbare Stammdaten für Handwerker-Gewerke (Patrik-Entscheidung —
    bewusst KEIN CharField mit Choices, analog ``VorgangTyp``)."""

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    code = models.CharField(max_length=30, unique=True)
    bezeichnung = models.CharField(max_length=100)
    aktiv = models.BooleanField(default=True)
    sortierung = models.IntegerField(default=0)
    erstellt_am = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='erstellte_gewerke',
    )

    class Meta:
        verbose_name = 'Gewerk'
        verbose_name_plural = 'Gewerke'
        ordering = ['sortierung', 'bezeichnung']

    def __str__(self):
        return self.bezeichnung


class HandwerkerauftragNummerZaehler(models.Model):
    """Zähler pro Kalenderjahr für ``Handwerkerauftrag.nummer``
    (Format ``HWA-{JJ}-{LFD5}``) — 1:1 nach dem Muster von
    ``apps.vorgaenge.models.VorgangNummerZaehler``.

    Zugriff ausschließlich über ``naechste_nummer()`` — SELECT FOR UPDATE
    innerhalb einer Transaktion verhindert doppelte Nummernvergabe bei
    gleichzeitigen Anfragen (kein COUNT()+1).
    """
    jahr = models.IntegerField(primary_key=True)
    letzter_zaehler = models.IntegerField(default=0)

    class Meta:
        verbose_name = 'Handwerkerauftrag-Nummer-Zähler'
        verbose_name_plural = 'Handwerkerauftrag-Nummer-Zähler'

    @classmethod
    @transaction.atomic
    def naechste_nummer(cls, jahr: int | None = None) -> str:
        """Vergibt atomar die nächste Handwerkerauftragsnummer für das
        angegebene Jahr (Default: laufendes Jahr)."""
        jahr = jahr or timezone.now().year
        zaehler, _ = cls.objects.select_for_update().get_or_create(
            jahr=jahr, defaults={'letzter_zaehler': 0},
        )
        zaehler.letzter_zaehler += 1
        zaehler.save(update_fields=['letzter_zaehler'])
        jj = f"{jahr % 100:02d}"
        return f"HWA-{jj}-{zaehler.letzter_zaehler:05d}"


class ObjektHandwerker(models.Model):
    """Zuordnung: welcher Kreditor (Handwerker) ist für welches Objekt mit
    welcher Priorität zuständig (Spec: ``WEGObjektHandwerker``)."""

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt = models.ForeignKey(
        Objekt, on_delete=models.CASCADE, related_name='handwerker_zuordnungen',
    )
    kreditor = models.ForeignKey(
        'rechnungen.Kreditor', on_delete=models.CASCADE,
        related_name='objekt_zuordnungen',
    )
    prioritaet = models.PositiveIntegerField(default=1)
    notiz = models.TextField(blank=True)
    erstellt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Objekt-Handwerker-Zuordnung'
        verbose_name_plural = 'Objekt-Handwerker-Zuordnungen'
        ordering = ['prioritaet', 'kreditor__name']
        constraints = [
            models.UniqueConstraint(
                fields=['objekt', 'kreditor'], name='unique_objekt_handwerker',
            ),
        ]

    def __str__(self):
        return f"{self.objekt.bezeichnung} — {self.kreditor.name} (Prio {self.prioritaet})"


class Handwerkerauftrag(models.Model):
    """Handwerkerauftrag zu einem Objekt (Spec Kap. 2) — mit Korrekturen:
    ``objekt`` ist Pflichtfeld (PROTECT), ``vorgang`` ist optional (PROTECT,
    nicht CASCADE), kein direktes ``rechnung_dokument`` (siehe
    ``Rechnung.handwerkerauftrag`` für die n:1-Verknüpfung stattdessen).
    """

    STATUS_CHOICES = [
        ('entwurf',       'Entwurf'),
        ('versendet',     'Versendet'),
        ('angenommen',    'Angenommen'),
        ('abgelehnt',     'Abgelehnt'),
        ('in_arbeit',     'In Arbeit'),
        ('abgeschlossen', 'Abgeschlossen'),
        ('storniert',     'Storniert'),
        ('abgelaufen',    'Abgelaufen'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    nummer = models.CharField(max_length=20, unique=True, editable=False)

    vorgang = models.ForeignKey(
        Vorgang, on_delete=models.PROTECT, null=True, blank=True,
        related_name='handwerkerauftraege',
    )
    objekt = models.ForeignKey(
        Objekt, on_delete=models.PROTECT,
        related_name='handwerkerauftraege',
        help_text='Pflichtfeld — Adresse und Handwerkerzuordnung hängen daran.',
    )
    kreditor = models.ForeignKey(
        'rechnungen.Kreditor', on_delete=models.PROTECT,
        related_name='handwerkerauftraege',
        limit_choices_to={'ist_handwerker': True},
    )
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='erstellte_handwerkerauftraege',
    )

    titel = models.CharField(max_length=255)
    beschreibung = models.TextField(blank=True)
    gewuenscht_ab = models.DateField(null=True, blank=True)
    prioritaet = models.CharField(max_length=10, choices=PRIORITAET_CHOICES, default='normal')
    geschaetzte_kosten = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='entwurf')
    versendet_am = models.DateTimeField(null=True, blank=True)
    angenommen_am = models.DateTimeField(null=True, blank=True)
    abgelehnt_am = models.DateTimeField(null=True, blank=True)
    ablehnung_grund = models.TextField(blank=True)
    abgeschlossen_am = models.DateTimeField(null=True, blank=True)
    abschluss_notiz = models.TextField(blank=True)

    erstellt_am = models.DateTimeField(auto_now_add=True)
    geaendert_am = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Handwerkerauftrag'
        verbose_name_plural = 'Handwerkeraufträge'
        ordering = ['-erstellt_am']
        indexes = [
            models.Index(fields=['objekt', 'status']),
            models.Index(fields=['kreditor', 'status']),
            models.Index(fields=['erstellt_am']),
        ]

    def clean(self):
        super().clean()
        if self.vorgang_id and self.objekt_id:
            if self.vorgang.objekt_id and self.vorgang.objekt_id != self.objekt_id:
                raise ValidationError({
                    'objekt': 'Objekt weicht vom Objekt des verknüpften Vorgangs ab.',
                })
            if not self.vorgang.objekt_id and self.vorgang.einheit_id \
                    and self.vorgang.einheit.objekt_id != self.objekt_id:
                raise ValidationError({
                    'objekt': 'Objekt weicht vom Objekt der Einheit des verknüpften Vorgangs ab.',
                })
        if self.kreditor_id and self.status == 'entwurf':
            # limit_choices_to wirkt nur in Forms/Admin — echte Validierung hier.
            #
            # Korrektur aus der Phase-B-Abnahme (Orchestrator, Schritt 0):
            # diese Prüfung gilt NUR vor dem Versand (Status 'entwurf'). Sie
            # darf keine dauerhafte Invariante sein — sonst hängt ein bereits
            # versendeter/angenommener Auftrag für immer fest, sobald der
            # Kreditor nachträglich ist_handwerker=False gesetzt bekommt oder
            # seine E-Mail verliert, weil ``auftrag_service.wechsle_status()``
            # bei JEDEM Statuswechsel ``full_clean()`` aufruft.
            if not self.kreditor.ist_handwerker:
                raise ValidationError({
                    'kreditor': 'Der gewählte Kreditor ist nicht als Handwerker markiert '
                                '(ist_handwerker=False).',
                })
            if not self.kreditor.email:
                raise ValidationError({
                    'kreditor': 'Der gewählte Kreditor hat keine E-Mail-Adresse hinterlegt '
                                '— für den Auftragsversand zwingend erforderlich.',
                })

    def clean_fields(self, exclude=None):
        """Überschrieben (Orchestrator-Korrektur Schritt 0, Ergänzung): das
        ``kreditor``-Feld trägt ``limit_choices_to={'ist_handwerker': True}``.
        Djangos eingebaute ``ForeignKey.validate()`` prüft dieses
        ``limit_choices_to`` bei JEDEM ``full_clean()`` unabhängig von unserem
        eigenen ``clean()`` oben — ohne diese Ausnahme bliebe die Invariante
        trotz der ``clean()``-Korrektur bestehen, weil ``wechsle_status()``
        bei jedem Statuswechsel ``full_clean()`` aufruft. Deshalb wird die
        Feldvalidierung von ``kreditor`` hier ebenfalls nur im Status
        ``entwurf`` durchgeführt — keine Modelländerung, keine Migration."""
        exclude = set(exclude or [])
        if self.status != 'entwurf':
            exclude.add('kreditor')
        super().clean_fields(exclude=exclude)

    def save(self, *args, **kwargs):
        if not self.nummer:
            jahr = (self.erstellt_am or timezone.now()).year
            self.nummer = HandwerkerauftragNummerZaehler.naechste_nummer(jahr)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nummer} — {self.titel} [{self.get_status_display()}]"


class HandwerkerauftragEreignis(models.Model):
    """Unveränderlicher Audit-Verlauf zu einem Handwerkerauftrag (GoBD),
    analog ``apps.vorgaenge.models.VorgangEreignis``. Zeilen werden nie
    geändert oder gelöscht."""

    TYP_CHOICES = [
        ('statuswechsel',          'Statuswechsel'),
        ('versand',                'Versand'),
        ('versand_fehlgeschlagen', 'Versand fehlgeschlagen'),
        ('kommentar',              'Kommentar'),
        ('rechnung_zugeordnet',    'Rechnung zugeordnet'),
        ('system_abgelaufen',      'System: Auftrag abgelaufen'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    auftrag = models.ForeignKey(
        Handwerkerauftrag, on_delete=models.CASCADE, related_name='ereignisse',
    )
    typ = models.CharField(max_length=30, choices=TYP_CHOICES)
    text = models.TextField(null=True, blank=True)
    alter_wert = models.CharField(max_length=100, null=True, blank=True)
    neuer_wert = models.CharField(max_length=100, null=True, blank=True)
    erstellt_am = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='erstellte_handwerkerauftrag_ereignisse',
        help_text='None = System-Ereignis (z.B. automatischer Ablauf).',
    )

    class Meta:
        verbose_name = 'Handwerkerauftrag-Ereignis'
        verbose_name_plural = 'Handwerkerauftrag-Ereignisse'
        ordering = ['erstellt_am']

    def __str__(self):
        return f"{self.auftrag.nummer} — {self.get_typ_display()}"


# Bankarbeitstage bis Ablauf der Auftragsbestätigungs-Frist, je Priorität.
BANKARBEITSTAGE_JE_PRIORITAET = {
    'hoch': 3,
    'normal': 7,
    'niedrig': 14,
}


def berechne_gueltig_bis(auftrag: 'Handwerkerauftrag', start=None) -> datetime:
    """Berechnet das Gültigkeitsende eines Auftragsbestätigungs-Tokens:
    Ende des Tages, der ``N`` Bankarbeitstage (je nach Priorität des
    Auftrags) nach ``start`` (Default: heute) liegt.

    Nutzt bewusst den bestehenden ``sepa_fristen_service.bd_addieren``
    (bundeslandspezifische Feiertage über ``holidays``, kein fest
    verdrahtetes Jahr) statt einer eigenen Bankarbeitstags-Logik.
    ``start`` ist als Parameter vorgesehen, damit Tests ein festes
    Startdatum vorgeben können, statt auf ``today()`` angewiesen zu sein.
    """
    anzahl_bd = BANKARBEITSTAGE_JE_PRIORITAET.get(auftrag.prioritaet, 7)
    bundesland = auftrag.objekt.bundesland
    start = start or timezone.localdate()
    frist_tag = bd_addieren(start, anzahl_bd, bundesland)
    ende_des_tages = datetime.combine(frist_tag, time.max)
    return timezone.make_aware(ende_des_tages)


class AuftragsbestaetigungsToken(models.Model):
    """Zugangsmittel für die Auftragsbestätigung (Annahme/Ablehnung) per
    Link ohne Login. Anders als ``HandwerkerauftragEreignis`` kein
    Audit-Objekt — CASCADE ist hier korrekt."""

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    auftrag = models.OneToOneField(
        Handwerkerauftrag, on_delete=models.CASCADE, related_name='token',
    )
    accept_token = models.CharField(max_length=64, unique=True, db_index=True, blank=True)
    reject_token = models.CharField(max_length=64, unique=True, db_index=True, blank=True)
    gueltig_bis = models.DateTimeField()
    verbraucht_am = models.DateTimeField(
        null=True, blank=True,
        help_text='Einmalverwendung — gesetzt sobald Accept- oder Reject-Link '
                  'benutzt wurde. Bewusst kein Boolean-Feld (würde eine zweite '
                  'Wahrheit neben gueltig_bis erzeugen).',
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Auftragsbestätigungs-Token'
        verbose_name_plural = 'Auftragsbestätigungs-Token'

    def save(self, *args, **kwargs):
        if not self.accept_token:
            self.accept_token = secrets.token_urlsafe(48)
        if not self.reject_token:
            self.reject_token = secrets.token_urlsafe(48)
        if not self.gueltig_bis:
            self.gueltig_bis = berechne_gueltig_bis(self.auftrag)
        super().save(*args, **kwargs)

    def ist_gueltig(self) -> bool:
        return self.verbraucht_am is None and timezone.now() < self.gueltig_bis

    def __str__(self):
        return f"Token für {self.auftrag.nummer}"
