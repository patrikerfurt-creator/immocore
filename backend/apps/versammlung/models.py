"""
Datenmodell des EV-Moduls (Spec v1.1 Kap. 4).

Neun Modelle: Eigentuemerversammlung, Tagesordnungspunkt, EVTeilnehmer,
EVTeilnehmerAnteil, EVStimme, EVVersandprotokoll, EVEreignis,
BeschlussNummerZaehler, Beschluss.

Grundsätze (Projektkonvention):
* Feldnamen und Choice-Codes ausschließlich ASCII — Umlaute nur in
  ``verbose_name``/``help_text``.
* Audit-Felder zeigen auf ``settings.AUTH_USER_MODEL`` und sind ``PROTECT``:
  bei anfechtbaren Beschlüssen (§ 45 WEG) darf der Urheber nicht verschwinden.
* Status und Task-Flags werden NIE direkt gesetzt, sondern ausschließlich über
  ``services/ev_service.py`` — dort entsteht auch der Audit-Eintrag
  (``EVEreignis``).
"""
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction


class Eigentuemerversammlung(models.Model):
    """Ein EV-Prozess über fünf Tasks (Spec v1.1 Kap. 4.1).

    Die fünf ``taskN_..._erledigt``-Flags sind Fortschrittsanzeige und
    absichtlich nicht in eine Reihenfolge gezwungen — die Verwaltung arbeitet
    die Tasks in beliebiger Folge ab. Jeder Flag-Wechsel erzeugt ein
    ``EVEreignis`` (GoBD, § 45 WEG).
    """

    STATUS_CHOICES = [
        ('entwurf',                 'Entwurf'),
        ('in_bearbeitung',          'In Bearbeitung'),
        ('einladungen_versendet',   'Einladungen versendet'),
        ('durchgefuehrt',           'Durchgeführt'),
        ('beschluesse_verarbeitet', 'Beschlüsse verarbeitet'),
        ('archiviert',              'Archiviert'),
    ]
    ART_CHOICES = [
        ('ordentlich',    'Ordentliche Versammlung'),
        ('ausserordentl', 'Außerordentliche Versammlung'),
        ('wiederholung',  'Wiederholungsversammlung'),
    ]
    STIMMPRINZIP_CHOICES = [
        ('kopf',              'Kopfprinzip (§ 25 Abs. 2 WEG: eine Stimme je Eigentümer)'),
        ('verteilerschluessel', 'Nach Verteilerschlüssel'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt = models.ForeignKey(
        'objekte.Objekt', on_delete=models.PROTECT,
        related_name='eigentuemerversammlungen',
    )
    arbeitsname = models.CharField(
        max_length=200, blank=True, default='',
        verbose_name='Arbeitsname',
        help_text='Interne Bezeichnung, z.B. "EV 2026 ordentlich".',
    )
    art = models.CharField(max_length=15, choices=ART_CHOICES, default='ordentlich')

    # ---- Task 1: Terminierung ----
    termin = models.DateTimeField(null=True, blank=True)
    ort = models.CharField(max_length=255, blank=True, default='')
    raum_buchung_notizen = models.TextField(blank=True, default='')
    terminvorschlaege = models.JSONField(
        default=list, blank=True,
        verbose_name='Terminvorschläge',
        help_text='Vorschlagsliste aus der Beiratsabstimmung: '
                  '[{"termin": "2026-03-15T19:00", "notiz": "..."}]',
    )

    # ---- Abstimmungsgrundlage ----
    stimmprinzip = models.CharField(
        max_length=20, choices=STIMMPRINZIP_CHOICES, default='kopf',
        help_text='Gesetzlicher Regelfall ist das Kopfprinzip (eine Stimme je '
                  'Eigentümer, unabhängig von der Anzahl der Einheiten); '
                  'abweichende Regelungen stehen in der Teilungserklärung und '
                  'werden über einen Verteilerschlüssel abgebildet.',
    )
    stimm_verteilerschluessel = models.ForeignKey(
        'objekte.Verteilerschluessel', on_delete=models.PROTECT,
        null=True, blank=True, related_name='eigentuemerversammlungen',
        verbose_name='Stimm-Verteilerschlüssel',
        help_text='Grundlage der Stimmkraft bei stimmprinzip='
                  '"verteilerschluessel" — z.B. "030 Anzahl Einheiten Gesamt" '
                  '(eine Stimme je Einheit), "031 Anzahl Wohnungen" '
                  '(Stellplätze stimmen nicht mit) oder "010 MEA Gesamt" '
                  '(Wertprinzip). Damit ist jede Regelung der '
                  'Teilungserklärung abbildbar, ohne den Code zu ändern.',
    )
    stimm_wirtschaftsjahr = models.IntegerField(
        default=0,
        verbose_name='Wirtschaftsjahr des Stimm-Verteilerschlüssels',
        help_text='Wirtschaftsjahr, aus dem die Werte gelesen werden; '
                  '0 = zeitlos (Regelfall bei flaeche/mea/kopf, siehe '
                  'VerteilerschluesselWert.wirtschaftsjahr).',
    )

    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='entwurf')

    task1_terminierung_erledigt     = models.BooleanField(default=False)
    task2_tagesordnung_erledigt     = models.BooleanField(default=False)
    task3_einladung_erledigt        = models.BooleanField(default=False)
    task4_durchfuehrung_erledigt    = models.BooleanField(default=False)
    task5_beschlussfassung_erledigt = models.BooleanField(default=False)

    einladungstext = models.TextField(
        blank=True, default='',
        help_text='Editierbarer Einladungstext (Vorlage wird beim Anlegen gesetzt).',
    )
    einladungs_pdf = models.OneToOneField(
        'dokumente.Dokument', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ev_einladung',
    )
    protokoll_pdf = models.OneToOneField(
        'dokumente.Dokument', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ev_protokoll',
    )

    erstellt_am = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='erstellte_eigentuemerversammlungen',
    )
    einladung_versendet_am = models.DateTimeField(null=True, blank=True)
    durchgefuehrt_am = models.DateTimeField(null=True, blank=True)
    versammlungsleiter = models.CharField(max_length=200, blank=True, default='')
    protokollfuehrer = models.CharField(max_length=200, blank=True, default='')

    class Meta:
        verbose_name        = 'Eigentümerversammlung'
        verbose_name_plural = 'Eigentümerversammlungen'
        ordering            = ['-termin', '-erstellt_am']
        indexes = [
            models.Index(fields=['objekt', '-termin']),
            models.Index(fields=['status']),
        ]

    def clean(self):
        super().clean()
        # SEV/ZH haben keine Eigentümerversammlung — eine EV dort wäre ein
        # Datenfehler, der sonst erst beim Versand auffiele (leere
        # Teilnehmerliste, weil es keine Eigentümergemeinschaft gibt).
        # Vergleich über upper(): der Bestand nutzt durchgehend 'WEG', in
        # älteren Testdaten kommt aber auch 'weg' vor — beides ist fachlich
        # dasselbe und soll hier nicht an der Schreibweise scheitern.
        if self.objekt_id and (self.objekt.objekt_typ or '').upper() != 'WEG':
            raise ValidationError(
                'Eine Eigentümerversammlung ist nur für WEG-Objekte vorgesehen '
                f'(Objekt ist Typ "{self.objekt.objekt_typ}").'
            )

        if self.stimmprinzip == 'verteilerschluessel':
            if not self.stimm_verteilerschluessel_id:
                raise ValidationError({
                    'stimm_verteilerschluessel':
                        'Bei stimmprinzip="verteilerschluessel" ist der '
                        'Verteilerschlüssel anzugeben.',
                })
            if (self.objekt_id
                    and self.stimm_verteilerschluessel.objekt_id != self.objekt_id):
                raise ValidationError({
                    'stimm_verteilerschluessel':
                        'Der Verteilerschlüssel gehört zu einem anderen Objekt.',
                })
        elif self.stimm_verteilerschluessel_id:
            raise ValidationError({
                'stimm_verteilerschluessel':
                    'Ein Verteilerschlüssel ist nur bei '
                    'stimmprinzip="verteilerschluessel" zulässig.',
            })

    def __str__(self):
        bezeichnung = self.arbeitsname or self.get_art_display()
        termin = self.termin.strftime('%d.%m.%Y') if self.termin else 'ohne Termin'
        return f"{bezeichnung} — {self.objekt.bezeichnung} ({termin})"


class Tagesordnungspunkt(models.Model):
    """Ein TOP mit Beschlussvorlage, Mehrheitsmodus und Ergebnis (Kap. 4.2)."""

    MODUS_CHOICES = [
        ('einfache_mehrheit',      'Einfache Mehrheit (Ja > Nein)'),
        ('qualifizierte_mehrheit', 'Qualifizierte Mehrheit (Schwelle laut TE)'),
        ('einstimmigkeit',         'Einstimmigkeit (alle abgegebenen Stimmen)'),
        ('allstimmigkeit',         'Allstimmigkeit (alle Eigentümer)'),
        ('kein_beschluss',         'Ohne Beschluss (Bericht/Information)'),
    ]
    ERGEBNIS_CHOICES = [
        ('offen',      'Noch nicht abgestimmt'),
        ('angenommen', 'Angenommen'),
        ('abgelehnt',  'Abgelehnt'),
        ('vertagt',    'Vertagt'),
        ('entfallen',  'Entfallen'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    ev = models.ForeignKey(
        Eigentuemerversammlung, on_delete=models.CASCADE, related_name='tagesordnung',
    )
    nummer = models.IntegerField(help_text='Fortlaufend ab 1.')
    titel = models.CharField(max_length=255)
    erlaeuterung = models.TextField(
        blank=True, default='',
        verbose_name='Erläuterung',
        help_text='Optionale Hintergrundinformation zum TOP.',
    )
    beschlussvorlage = models.TextField(
        blank=True, default='',
        help_text='Wortlaut, über den abgestimmt wird. Pflicht außer bei '
                  'abstimmungsmodus="kein_beschluss".',
    )

    abstimmungsmodus = models.CharField(
        max_length=25, choices=MODUS_CHOICES, default='einfache_mehrheit',
    )
    mehrheit_schwelle = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        verbose_name='Mehrheitsschwelle in Prozent',
        help_text='Nur bei abstimmungsmodus="qualifizierte_mehrheit": '
                  'erforderlicher Ja-Anteil an den abgegebenen Stimmen '
                  '(z.B. 66.67). Grundlage ist die Teilungserklärung — die '
                  'frühere "doppelt qualifizierte Mehrheit" ist mit der '
                  'WEG-Reform 2020 entfallen.',
    )

    # Ergebnis-Summen in Stimmkraft (nicht Köpfe) — daher Decimal.
    abstimmung_ja         = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    abstimmung_nein       = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    abstimmung_enthaltung = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    abstimmungsergebnis = models.CharField(
        max_length=12, choices=ERGEBNIS_CHOICES, default='offen',
    )
    ergebnis_bemerkung = models.TextField(blank=True, default='')

    # Automations-Trigger — greifen nur bei abstimmungsergebnis='angenommen'.
    triggert_vorgang = models.BooleanField(
        default=False,
        verbose_name='Folge-Vorgang anlegen',
        help_text='Erzeugt bei Annahme einen Vorgang (z.B. Sanierung). Ein '
                  'Handwerkerauftrag entsteht daraus manuell — '
                  'auftrag_service.erstelle_auftrag verlangt einen Kreditor.',
    )
    triggert_wirtschaftsplan = models.BooleanField(
        default=False,
        verbose_name='Wirtschaftsplan-Beschluss vormerken',
        help_text='Erzeugt bei Annahme eine Aufgabe zur Erfassung über '
                  'buchhaltung.wirtschaftsplan_beschluss_service.',
    )

    class Meta:
        verbose_name        = 'Tagesordnungspunkt'
        verbose_name_plural = 'Tagesordnungspunkte'
        ordering            = ['ev', 'nummer']
        constraints = [
            models.UniqueConstraint(fields=['ev', 'nummer'], name='uniq_top_nummer_je_ev'),
        ]

    def clean(self):
        super().clean()
        if self.abstimmungsmodus != 'kein_beschluss' and not (self.beschlussvorlage or '').strip():
            raise ValidationError({
                'beschlussvorlage': 'Beschlussvorlage erforderlich — über einen '
                                    'TOP ohne Wortlaut kann nicht abgestimmt werden.',
            })
        if self.abstimmungsmodus == 'qualifizierte_mehrheit' and not self.mehrheit_schwelle:
            raise ValidationError({
                'mehrheit_schwelle': 'Bei qualifizierter Mehrheit ist die Schwelle '
                                     'anzugeben (Grundlage: Teilungserklärung).',
            })
        if self.abstimmungsmodus != 'qualifizierte_mehrheit' and self.mehrheit_schwelle:
            raise ValidationError({
                'mehrheit_schwelle': 'Schwelle ist nur bei qualifizierter Mehrheit zulässig.',
            })

    def __str__(self):
        return f"TOP {self.nummer}: {self.titel}"


class EVTeilnehmer(models.Model):
    """Stimmberechtigter Eigentümer einer EV inkl. Zusage und Anwesenheit.

    Eine Zeile je Person (nicht je Einheit): beim Kopfprinzip hat ein
    Eigentümer mit drei Einheiten genau eine Stimme. Der Einheitenbezug hängt
    an ``EVTeilnehmerAnteil``.
    """

    ZUSAGE_CHOICES = [
        ('offen',    'Keine Rückmeldung'),
        ('zugesagt', 'Zusage'),
        ('abgesagt', 'Absage'),
    ]
    QUELLE_CHOICES = [
        ('portal',  'Portal'),
        ('manuell', 'Manuell erfasst'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    ev = models.ForeignKey(
        Eigentuemerversammlung, on_delete=models.CASCADE, related_name='teilnehmer',
    )
    person = models.ForeignKey(
        'personen.Person', on_delete=models.PROTECT, related_name='ev_teilnahmen',
    )

    zusage_status = models.CharField(max_length=10, choices=ZUSAGE_CHOICES, default='offen')
    zusage_am = models.DateTimeField(null=True, blank=True)
    zusage_quelle = models.CharField(
        max_length=10, choices=QUELLE_CHOICES, blank=True, default='',
        help_text='Wer die Rückmeldung erfasst hat.',
    )

    ist_anwesend = models.BooleanField(
        null=True, blank=True,
        verbose_name='Anwesend',
        help_text='NULL = noch nicht erfasst. (Django-5-Ersatz für das in '
                  'Django 4.0 entfernte NullBooleanField.)',
    )
    anwesenheit_erfasst_am = models.DateTimeField(null=True, blank=True)
    vertreten_durch = models.ForeignKey(
        'personen.Person', on_delete=models.PROTECT, null=True, blank=True,
        related_name='ev_vertretungen',
        help_text='Bevollmächtigter aus dem Personenstamm. Die Stimmkraft '
                  'bleibt bei diesem Teilnehmer und wird dem Vertreter nicht '
                  'zusätzlich angerechnet.',
    )
    vertreter_name = models.CharField(
        max_length=200, blank=True, default='',
        help_text='Freitext, wenn der Bevollmächtigte kein Person-Datensatz ist.',
    )
    vollmacht_dokument = models.ForeignKey(
        'dokumente.Dokument', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ev_vollmachten',
        help_text='Vollmachtnachweis — erster Prüfpunkt bei Anfechtung.',
    )

    stimmkraft = models.DecimalField(
        max_digits=12, decimal_places=4, default=0,
        help_text='Snapshot, ermittelt nach Eigentuemerversammlung.stimmprinzip '
                  '(siehe services/stimmkraft_service.py). 0 = nicht mehr '
                  'stimmberechtigt, z.B. nach Eigentümerwechsel — die Zeile '
                  'bleibt als Ladungsnachweis erhalten.',
    )

    class Meta:
        verbose_name        = 'EV-Teilnehmer'
        verbose_name_plural = 'EV-Teilnehmer'
        ordering            = ['ev', 'person__nachname', 'person__vorname']
        constraints = [
            models.UniqueConstraint(fields=['ev', 'person'], name='uniq_teilnehmer_je_ev'),
        ]

    def clean(self):
        super().clean()
        if self.vertreten_durch_id and self.vertreten_durch_id == self.person_id:
            raise ValidationError({
                'vertreten_durch': 'Eine Person kann sich nicht selbst vertreten.',
            })

    def __str__(self):
        return f"{self.person.name} ({self.stimmkraft} Stimmen)"


class EVTeilnehmerAnteil(models.Model):
    """Eine Einheit des Teilnehmers — Einheitenbezug und MEA-Snapshot.

    Der Snapshot ist bewusst redundant zu ``VerteilerschluesselWert``: ändert
    sich der MEA nach der Versammlung, muss das Protokoll weiterhin die damals
    gültige Stimmkraft ausweisen (§ 45 WEG, Anfechtbarkeit).
    """

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    teilnehmer = models.ForeignKey(
        EVTeilnehmer, on_delete=models.CASCADE, related_name='anteile',
    )
    eigentumsverhaeltnis = models.ForeignKey(
        'personen.EigentumsVerhaeltnis', on_delete=models.PROTECT,
        related_name='ev_teilnehmer_anteile',
    )
    einheit_nr_snapshot = models.CharField(max_length=20, blank=True, default='')
    mea_wert_snapshot = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True,
        verbose_name='MEA (Snapshot)',
        help_text='MEA aus Verteilerschluessel(vs_typ="mea") zum Snapshot-Zeitpunkt.',
    )

    class Meta:
        verbose_name        = 'EV-Teilnehmer-Anteil'
        verbose_name_plural = 'EV-Teilnehmer-Anteile'
        ordering            = ['teilnehmer', 'einheit_nr_snapshot']
        constraints = [
            models.UniqueConstraint(
                fields=['teilnehmer', 'eigentumsverhaeltnis'],
                name='uniq_anteil_je_teilnehmer',
            ),
        ]

    def __str__(self):
        return f"{self.einheit_nr_snapshot} (MEA {self.mea_wert_snapshot})"


class EVStimme(models.Model):
    """Einzelvotum eines Teilnehmers zu einem TOP (optionaler Audit-Trail).

    Wird nur gefüllt, wenn namentlich abgestimmt wird. Regelfall ist die
    Summenerfassung am TOP; beide Wege werden in Phase D über
    ``durchfuehrung_service`` konsistent gehalten.
    """

    VOTUM_CHOICES = [
        ('ja',         'Ja'),
        ('nein',       'Nein'),
        ('enthaltung', 'Enthaltung'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    top = models.ForeignKey(
        Tagesordnungspunkt, on_delete=models.CASCADE, related_name='stimmen',
    )
    teilnehmer = models.ForeignKey(
        EVTeilnehmer, on_delete=models.CASCADE, related_name='stimmen',
    )
    votum = models.CharField(max_length=10, choices=VOTUM_CHOICES)
    stimmkraft = models.DecimalField(max_digits=12, decimal_places=4)
    erfasst_am = models.DateTimeField(auto_now_add=True)
    erfasst_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='erfasste_ev_stimmen',
    )

    class Meta:
        verbose_name        = 'EV-Einzelstimme'
        verbose_name_plural = 'EV-Einzelstimmen'
        ordering            = ['top', 'teilnehmer']
        constraints = [
            models.UniqueConstraint(fields=['top', 'teilnehmer'], name='uniq_stimme_je_top'),
        ]

    def clean(self):
        super().clean()
        if self.top_id and self.teilnehmer_id and self.top.ev_id != self.teilnehmer.ev_id:
            raise ValidationError(
                'TOP und Teilnehmer gehören zu verschiedenen Versammlungen.'
            )

    def __str__(self):
        return f"TOP {self.top.nummer} — {self.teilnehmer.person.name}: {self.get_votum_display()}"


class EVVersandprotokoll(models.Model):
    """Protokolliert jeden Versandversuch je Person und Kanal.

    Bewusst OHNE unique_together (Abweichung von Spec v1.0): ein
    Wiederholversand nach Bounce oder Adresskorrektur muss dokumentierbar
    bleiben.
    """

    KANAL_CHOICES = [
        ('portal', 'Portal (Dokument + Benachrichtigungsmail)'),
        ('email',  'E-Mail mit PDF-Anhang'),
        ('epost',  'EPost (manueller Postversand)'),
    ]
    STATUS_CHOICES = [
        ('erfolgreich',    'Erfolgreich'),
        ('fehlgeschlagen', 'Fehlgeschlagen'),
        ('uebersprungen',  'Übersprungen'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    ev = models.ForeignKey(
        Eigentuemerversammlung, on_delete=models.CASCADE, related_name='versandprotokolle',
    )
    person = models.ForeignKey(
        'personen.Person', on_delete=models.PROTECT, related_name='ev_versandprotokolle',
    )
    kanal = models.CharField(max_length=10, choices=KANAL_CHOICES)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='erfolgreich')
    empfaenger = models.CharField(
        max_length=255, blank=True, default='',
        verbose_name='Empfänger',
        help_text='Verwendete E-Mail-Adresse bzw. Postanschrift (Nachweis).',
    )
    epost_pfad = models.CharField(
        max_length=500, blank=True, default='',
        help_text='Docker-Pfad der abgelegten PDF (unter MEDIA_ROOT/epost/…), '
                  'nie ein Host- oder Windows-Pfad.',
    )
    fehlertext = models.TextField(blank=True, default='')
    versendet_am = models.DateTimeField(auto_now_add=True)
    versendet_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='ev_versandprotokolle',
    )

    class Meta:
        verbose_name        = 'EV-Versandprotokoll'
        verbose_name_plural = 'EV-Versandprotokolle'
        ordering            = ['ev', 'person__nachname', '-versendet_am']
        indexes = [models.Index(fields=['ev', 'kanal'])]

    def __str__(self):
        return f"{self.person.name} — {self.get_kanal_display()} [{self.status}]"


class EVEreignis(models.Model):
    """Unveränderlicher Audit-Verlauf zur EV (§ 45 WEG, GoBD).

    Muster: ``apps.vorgaenge.VorgangEreignis``. Es gibt bewusst keinen
    Endpunkt und keine UI zum Ändern oder Löschen von Ereignissen.
    """

    TYP_CHOICES = [
        ('erstellt',              'EV erstellt'),
        ('task_erledigt',         'Task als erledigt markiert'),
        ('task_zurueckgesetzt',   'Task zurückgesetzt'),
        ('statuswechsel',         'Statuswechsel'),
        ('termin_geaendert',      'Termin/Ort geändert'),
        ('top_angelegt',          'TOP angelegt'),
        ('top_geaendert',         'TOP geändert'),
        ('top_geloescht',         'TOP gelöscht'),
        ('einladung_erzeugt',     'Einladungs-PDF erzeugt'),
        ('einladung_versendet',   'Einladung versendet'),
        ('versand_fehler',        'Versandfehler'),
        ('zusage_erfasst',        'Zusage/Absage erfasst'),
        ('stimmkraft_ermittelt',  'Stimmkraft ermittelt'),
        ('anwesenheit_erfasst',   'Anwesenheit erfasst'),
        ('abstimmung_erfasst',    'Abstimmung erfasst'),
        ('abstimmung_korrigiert', 'Abstimmung korrigiert'),
        ('beschluss_erzeugt',     'Beschluss in Sammlung aufgenommen'),
        ('vorgang_erzeugt',       'Folge-Vorgang erzeugt'),
        ('wp_aufgabe_erzeugt',    'Wirtschaftsplan-Aufgabe erzeugt'),
        ('protokoll_erzeugt',     'Protokoll-PDF erzeugt'),
        ('kommentar',             'Kommentar'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    ev = models.ForeignKey(
        Eigentuemerversammlung, on_delete=models.CASCADE, related_name='ereignisse',
    )
    top = models.ForeignKey(
        Tagesordnungspunkt, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ereignisse',
    )
    typ = models.CharField(max_length=25, choices=TYP_CHOICES)
    text = models.TextField(blank=True, default='')
    alter_wert = models.CharField(max_length=200, blank=True, default='')
    neuer_wert = models.CharField(max_length=200, blank=True, default='')
    erstellt_am = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='erstellte_ev_ereignisse',
        help_text='NULL = systemgeneriert (Celery-Task).',
    )

    class Meta:
        verbose_name        = 'EV-Ereignis'
        verbose_name_plural = 'EV-Ereignisse'
        ordering            = ['erstellt_am']

    def __str__(self):
        return f"{self.ev_id} — {self.get_typ_display()}"


class BeschlussNummerZaehler(models.Model):
    """Fortlaufende Beschlussnummer je Objekt (§ 24 Abs. 7 WEG).

    Zugriff ausschließlich über ``naechste_nummer()`` — SELECT FOR UPDATE
    innerhalb einer Transaktion verhindert doppelte Nummern bei gleichzeitigen
    Anfragen (Muster: ``BelegnummerZaehler``, ``VorgangNummerZaehler``).
    """

    objekt = models.OneToOneField(
        'objekte.Objekt', on_delete=models.CASCADE, primary_key=True,
        related_name='beschluss_zaehler',
    )
    letzter_zaehler = models.IntegerField(default=0)

    class Meta:
        verbose_name        = 'Beschluss-Nummern-Zähler'
        verbose_name_plural = 'Beschluss-Nummern-Zähler'

    @classmethod
    @transaction.atomic
    def naechste_nummer(cls, objekt) -> int:
        zaehler, _ = cls.objects.select_for_update().get_or_create(
            objekt=objekt, defaults={'letzter_zaehler': 0},
        )
        zaehler.letzter_zaehler += 1
        zaehler.save(update_fields=['letzter_zaehler'])
        return zaehler.letzter_zaehler

    def __str__(self):
        return f"{self.objekt_id}: {self.letzter_zaehler}"


class Beschluss(models.Model):
    """Eintrag der Beschluss-Sammlung nach § 24 Abs. 7 WEG.

    Einträge werden NIE gelöscht und der Wortlaut nie geändert. Anfechtung und
    gerichtliche Aufhebung werden ausschließlich vermerkt
    (``anfechtung_status``, ``aufgehoben_am``, ``gerichtlicher_hinweis``).
    """

    ANFECHTUNG_CHOICES = [
        ('keine',      'Keine Anfechtung bekannt'),
        ('anhaengig',  'Anfechtungsklage anhängig'),
        ('abgewiesen', 'Klage abgewiesen'),
        ('aufgehoben', 'Beschluss gerichtlich aufgehoben'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt = models.ForeignKey(
        'objekte.Objekt', on_delete=models.PROTECT, related_name='beschluesse',
    )
    nummer = models.IntegerField(
        editable=False,
        help_text='Fortlaufende Nummer je Objekt, Vergabe über BeschlussNummerZaehler.',
    )
    ev = models.ForeignKey(
        Eigentuemerversammlung, on_delete=models.PROTECT, null=True, blank=True,
        related_name='beschluesse',
        help_text='NULL bei Umlaufbeschluss (§ 23 Abs. 3 WEG) — vorgesehen, '
                  'Erfassungsweg folgt in einer späteren Phase.',
    )
    top = models.OneToOneField(
        Tagesordnungspunkt, on_delete=models.PROTECT, null=True, blank=True,
        related_name='beschluss',
    )

    beschluss_datum = models.DateField()
    ort = models.CharField(max_length=255, blank=True, default='')
    wortlaut = models.TextField(
        help_text='Wortlaut des Beschlusses — unveränderlich (§ 24 Abs. 7 WEG).',
    )
    ergebnis_ja         = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    ergebnis_nein       = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    ergebnis_enthaltung = models.DecimalField(max_digits=12, decimal_places=4, default=0)

    dokument = models.ForeignKey(
        'dokumente.Dokument', on_delete=models.PROTECT, null=True, blank=True,
        related_name='beschluesse',
        help_text='DMS-Dokument mit dokument_typ="beschluss".',
    )
    vorgang = models.ForeignKey(
        'vorgaenge.Vorgang', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ev_beschluesse',
    )

    anfechtung_status = models.CharField(
        max_length=12, choices=ANFECHTUNG_CHOICES, default='keine',
    )
    anfechtung_notiz = models.TextField(blank=True, default='')
    aufgehoben_am = models.DateField(null=True, blank=True)
    gerichtlicher_hinweis = models.TextField(blank=True, default='')

    erstellt_am = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='erstellte_beschluesse',
    )

    class Meta:
        verbose_name        = 'Beschluss'
        verbose_name_plural = 'Beschluss-Sammlung'
        ordering            = ['objekt', '-nummer']
        constraints = [
            models.UniqueConstraint(
                fields=['objekt', 'nummer'], name='uniq_beschluss_nummer_je_objekt',
            ),
        ]

    def clean(self):
        super().clean()
        if self.top_id and self.ev_id and self.top.ev_id != self.ev_id:
            raise ValidationError('TOP gehört nicht zu der angegebenen Versammlung.')
        if self.ev_id and self.objekt_id and self.ev.objekt_id != self.objekt_id:
            raise ValidationError('Versammlung gehört nicht zu dem angegebenen Objekt.')

    def save(self, *args, **kwargs):
        if not self.nummer:
            self.nummer = BeschlussNummerZaehler.naechste_nummer(self.objekt)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Beschluss {self.nummer} vom {self.beschluss_datum:%d.%m.%Y}"
