"""
Datenmodell des Eigentümer-Portals (Spec 1a, Kap. 4).

Abgrenzung zum internen IMMOCORE-Login: ein Eigentümer bekommt bewusst
KEINEN ``django.contrib.auth.User``. Die interne Userbasis ist die der
Mitarbeiter — ein Eigentümer-User dort würde über Gruppen-/Permission-
Defaults und das Django-Admin eine Angriffsfläche öffnen, die es für ein
reines Lese-/Selbstpflege-Portal nicht braucht. Stattdessen:

    PortalZugang  → wer darf grundsätzlich ins Portal (an Person gebunden)
    PortalToken   → Einmal-Links (Einladung, Magic Link, E-Mail-Bestätigung)
    PortalSession → ausgestelltes Sitzungs-Token nach erfolgreichem Login

Spec Kap. 7 spricht von ``request.user.person``; im realen Code existiert
kein User-Person-Bezug (Real-Code-vor-Spec-Prinzip). Die Autorisierung
läuft deshalb über ``request.portal_zugang.person`` — siehe
``apps.portal.auth``. Fachlich identisch: der Server leitet die Person
ausschließlich aus dem Sitzungs-Token ab, nie aus einem Client-Parameter.
"""
import secrets
from uuid import uuid4

from django.db import models
from django.utils import timezone

from apps.personen.models import Person


# Gültigkeitsdauern (Spec Kap. 3.1, 3.2, 5.3) — an einer Stelle, damit
# Service, Mailtext und Tests nicht auseinanderlaufen können.
EINLADUNG_GUELTIG_STUNDEN = 72
MAGIC_LINK_GUELTIG_MINUTEN = 15
EMAIL_BESTAETIGUNG_GUELTIG_STUNDEN = 24
SESSION_GUELTIG_STUNDEN = 12


class PortalZugang(models.Model):
    """Portal-Berechtigung einer Person (Spec Kap. 4.1)."""

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    person = models.OneToOneField(
        Person, on_delete=models.CASCADE, related_name='portal_zugang',
        verbose_name='Person',
    )
    aktiv = models.BooleanField(
        default=True,
        help_text='Die Verwaltung kann den Zugang jederzeit sperren, ohne ihn zu löschen.',
    )
    eingeladen_von = models.ForeignKey(
        'mitarbeiter.Mitarbeiter', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='portal_einladungen',
        verbose_name='Eingeladen von',
    )
    eingeladen_am = models.DateTimeField(default=timezone.now)
    erstaktivierung_am = models.DateTimeField(
        null=True, blank=True,
        help_text='Null, solange die Einladung nicht angenommen wurde.',
    )
    letzter_login = models.DateTimeField(null=True, blank=True)
    email_pending = models.EmailField(
        blank=True, default='',
        verbose_name='Ausstehende E-Mail-Änderung',
        help_text='Neue Adresse, solange sie noch nicht bestätigt ist (Spec Kap. 5.3). '
                  'Bis zur Bestätigung bleibt die alte Adresse für den Login gültig.',
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)
    geaendert_am = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Portal-Zugang'
        verbose_name_plural = 'Portal-Zugänge'
        ordering = ['-eingeladen_am']

    def __str__(self):
        return f'Portal-Zugang {self.person}'

    @property
    def status(self) -> str:
        if not self.aktiv:
            return 'gesperrt'
        if self.erstaktivierung_am is None:
            return 'eingeladen'
        return 'aktiv'


class PortalToken(models.Model):
    """Einmal-Link für Einladung, Magic-Link-Login und E-Mail-Bestätigung.

    Alle drei Flows brauchen dasselbe: ein zufälliges Geheimnis, eine
    Ablaufzeit und Einmalverwendung. Ein gemeinsames Modell mit ``typ``
    statt dreier fast identischer Tabellen — die Einlöse-Logik existiert
    damit genau einmal (``apps.portal.services.zugang_service``).

    Bewusst ein Zufallstoken (wie ``AuftragsbestaetigungsToken``) statt
    eines signierten ``TimestampSigner``-Tokens: Einmalverwendung ist ohne
    Datenbank-Zustand nicht abbildbar, und eine Signatur, die man trotzdem
    in der DB nachschlagen muss, bringt keinen zusätzlichen Schutz.
    """

    TYP_EINLADUNG = 'einladung'
    TYP_MAGIC = 'magic'
    TYP_EMAIL_BESTAETIGUNG = 'email_bestaetigung'
    TYP_CHOICES = [
        (TYP_EINLADUNG, 'Einladung'),
        (TYP_MAGIC, 'Magic Link'),
        (TYP_EMAIL_BESTAETIGUNG, 'E-Mail-Bestätigung'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    zugang = models.ForeignKey(
        PortalZugang, on_delete=models.CASCADE, related_name='tokens',
    )
    typ = models.CharField(max_length=30, choices=TYP_CHOICES)
    token = models.CharField(max_length=100, unique=True, db_index=True, blank=True)
    ziel_email = models.EmailField(
        blank=True, default='',
        help_text='Nur bei typ=email_bestaetigung: die zu bestätigende neue Adresse. '
                  'Wird hier festgehalten, damit ein später geändertes '
                  'email_pending einen bereits versendeten Link nicht umlenken kann.',
    )
    gueltig_bis = models.DateTimeField()
    verbraucht_am = models.DateTimeField(
        null=True, blank=True,
        help_text='Einmalverwendung — gesetzt beim Einlösen.',
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Portal-Token'
        verbose_name_plural = 'Portal-Token'
        ordering = ['-erstellt_am']
        indexes = [models.Index(fields=['zugang', 'typ'])]

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(48)
        super().save(*args, **kwargs)

    def ist_gueltig(self) -> bool:
        return self.verbraucht_am is None and timezone.now() < self.gueltig_bis

    def __str__(self):
        return f'{self.get_typ_display()} für {self.zugang.person}'


class PortalSession(models.Model):
    """Sitzung nach erfolgreichem Login (Spec Kap. 7: Session/JWT ausstellen).

    Opakes Zufallstoken statt JWT: SimpleJWT-Token setzen einen
    ``django.contrib.auth``-User voraus, den es hier bewusst nicht gibt
    (siehe Modul-Docstring). Ein Datenbank-Token hat für ein Portal
    zusätzlich den Vorteil, dass die Verwaltung eine Sitzung sofort beenden
    kann — beim Sperren des Zugangs greift das ohne Wartezeit bis zum
    Ablauf eines signierten Tokens.
    """

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    zugang = models.ForeignKey(
        PortalZugang, on_delete=models.CASCADE, related_name='sessions',
    )
    token = models.CharField(max_length=100, unique=True, db_index=True, blank=True)
    gueltig_bis = models.DateTimeField()
    letzter_zugriff = models.DateTimeField(default=timezone.now)
    erstellt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Portal-Sitzung'
        verbose_name_plural = 'Portal-Sitzungen'
        ordering = ['-erstellt_am']

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(48)
        super().save(*args, **kwargs)

    def ist_gueltig(self) -> bool:
        return timezone.now() < self.gueltig_bis

    def __str__(self):
        return f'Sitzung {self.zugang.person} (bis {self.gueltig_bis:%d.%m.%Y %H:%M})'


class PersonStammdatenAenderung(models.Model):
    """Audit-Log jeder Stammdatenänderung (Spec Kap. 4.2, GoBD).

    Ein Eintrag JE GEÄNDERTEM FELD — keine Sammelbuchung, damit die
    Historie eines einzelnen Feldes ohne Aufdröseln lesbar bleibt.

    ``on_delete=PROTECT`` auf ``person``: ein Audit-Eintrag darf nicht
    stillschweigend mit dem Objekt verschwinden, das er dokumentiert.
    """

    QUELLE_PORTAL = 'Portal-Selbständerung'

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    person = models.ForeignKey(
        Person, on_delete=models.PROTECT, related_name='stammdaten_aenderungen',
    )
    feld = models.CharField(
        max_length=50,
        help_text="Feldname, z.B. adresse, telefon, email, iban, bic",
    )
    alter_wert = models.TextField(blank=True, default='')
    neuer_wert = models.TextField(blank=True, default='')
    quelle = models.CharField(max_length=50, default=QUELLE_PORTAL)
    zeitstempel = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Stammdaten-Änderung'
        verbose_name_plural = 'Stammdaten-Änderungen'
        ordering = ['-zeitstempel']
        indexes = [models.Index(fields=['person', 'feld'])]

    def __str__(self):
        return f'{self.person}: {self.feld} -> {self.neuer_wert}'
