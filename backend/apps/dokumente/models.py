from uuid import uuid4
from django.conf import settings
from django.db import models, transaction
from apps.objekte.models import Objekt, Einheit


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


class Beleg(models.Model):
    """Zentrales Beleg-Modell — systemweite Klammer über alle eingehenden Dokumente.

    Jeder Beleg erhält eine unveränderliche, global eindeutige Belegnummer
    (Format AA00000001). Die Nummer wird beim ersten ``save()`` automatisch
    vergeben und kann danach nicht mehr geändert werden.

    Verknüpfungen:
      - rechnung  → Rechnung (1:1, optional)
      - dokument  → Dokument (1:1, optional)
      - Zukünftig: Konto-Belege, wiederkehrende Zahlungen, SEPA-Mandatsdokumente …
    """

    TYP_CHOICES = [
        ('rechnung',      'Rechnung'),
        ('dokument',      'Dokument'),
        ('wiederkehrend', 'Wiederkehrende Zahlung'),
        ('sonstiges',     'Sonstiges'),
    ]

    id          = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    belegnummer = models.CharField(
        max_length=12, unique=True, editable=False,
        help_text='Systemweit eindeutige, unveränderliche Belegnummer (AA00000001 …)',
    )
    typ         = models.CharField(max_length=20, choices=TYP_CHOICES)
    beschreibung = models.CharField(max_length=500, blank=True)

    objekt = models.ForeignKey(
        Objekt, on_delete=models.PROTECT,
        null=True, blank=True, related_name='belege',
    )

    # Verknüpfungen zu bestehenden Dokumenten-Modellen
    rechnung = models.OneToOneField(
        'rechnungen.Rechnung', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='beleg',
    )
    dokument = models.OneToOneField(
        'dokumente.Dokument', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='beleg',
    )

    erstellt_am  = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='erstellte_belege',
    )

    class Meta:
        verbose_name        = 'Beleg'
        verbose_name_plural = 'Belege'
        ordering            = ['-erstellt_am']

    def save(self, *args, **kwargs):
        if not self.belegnummer:
            with transaction.atomic():
                self.belegnummer = BelegnummerZaehler.naechste_nummer()
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)

    def __str__(self):
        return f"Beleg {self.belegnummer} [{self.get_typ_display()}]"


class Dokument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    datei = models.FileField(upload_to='dokumente/')
    dateiname = models.CharField(max_length=255)
    kategorie = models.CharField(max_length=100)  # z.B. Teilungserklärung, Versicherung, Protokoll
    beschreibung = models.TextField(blank=True)
    verknuepfung_typ = models.CharField(max_length=50)  # Objekt / Einheit / Ticket / Rechnung
    objekt = models.ForeignKey(
        Objekt, on_delete=models.CASCADE, null=True, blank=True,
        related_name='dokumente'
    )
    einheit = models.ForeignKey(
        Einheit, on_delete=models.CASCADE, null=True, blank=True,
        related_name='dokumente'
    )
    hochgeladen_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='hochgeladene_dokumente'
    )
    hochgeladen_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Dokument'
        verbose_name_plural = 'Dokumente'
        ordering = ['-hochgeladen_am']

    def __str__(self):
        return f"{self.dateiname} ({self.kategorie})"
