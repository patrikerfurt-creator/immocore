from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models


ABTEILUNG_CHOICES = [
    ('objektmanagement', 'Objektmanagement'),
    ('buchhaltung',      'Buchhaltung'),
    ('frontoffice',      'Frontoffice'),
    ('backoffice',       'Backoffice'),
    ('fm_management',    'FM-Management'),
    ('geschaeftsfuehrer','Geschäftsführer'),
    ('prokurist',        'Prokurist'),
    ('auszubildender',   'Auszubildender'),
]

ABTEILUNG_MAP = dict(ABTEILUNG_CHOICES)


class Mitarbeiter(models.Model):
    user           = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='mitarbeiter_profil',
    )
    abteilungen    = ArrayField(
        models.CharField(max_length=50),
        default=list,
        verbose_name='Abteilungen',
    )
    telefon        = models.CharField(max_length=30, blank=True)
    aktiv          = models.BooleanField(default=True)
    abwesend       = models.BooleanField(default=False, verbose_name='Abwesend (Vertretung aktiv)')
    eingetreten_am = models.DateField(null=True, blank=True)
    erstellt_am    = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name          = 'Mitarbeiter'
        verbose_name_plural   = 'Mitarbeiter'
        ordering              = ['user__last_name', 'user__first_name']

    def __str__(self):
        labels = ', '.join(ABTEILUNG_MAP.get(a, a) for a in self.abteilungen)
        return f'{self.user.get_full_name()} ({labels})'


class MitarbeiterObjektZuordnung(models.Model):
    mitarbeiter = models.ForeignKey(
        Mitarbeiter,
        on_delete=models.CASCADE,
        related_name='objekt_zuordnungen',
    )
    objekt = models.ForeignKey(
        'objekte.Objekt',
        on_delete=models.CASCADE,
        related_name='mitarbeiter_zuordnungen',
    )
    aufgabe = models.CharField(
        max_length=50,
        choices=ABTEILUNG_CHOICES,
        blank=True,
        default='',
        verbose_name='Aufgabe im Objekt',
    )

    class Meta:
        unique_together        = ('mitarbeiter', 'objekt')
        verbose_name           = 'Mitarbeiter-Objekt-Zuordnung'
        verbose_name_plural    = 'Mitarbeiter-Objekt-Zuordnungen'
        ordering               = ['mitarbeiter__user__last_name']

    def __str__(self):
        aufgabe_label = ABTEILUNG_MAP.get(self.aufgabe, self.aufgabe)
        return f'{self.mitarbeiter} → {self.objekt_id} ({aufgabe_label})'
