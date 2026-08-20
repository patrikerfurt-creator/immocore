# IMMOCORE — Modul Eigentümerversammlung (EV): Spezifikation v1.1

**Status:** 🟡 Entwurf zur Freigabe (HALT-Gate A)
**Version:** 1.1 — ersetzt v1.0 vom 2026-08-19
**Erstellt:** 2026-08-19
**Zielumgebung:** Django 5.1 / DRF 3.15 / React 18 + TypeScript / PostgreSQL 16
**Vorgänger:** v1.0 (`CLAUDE_CODE_ANLEITUNG Eigentümerversammlung (EV) Workflow — v1.0`)

---

## 0. Änderungsverzeichnis gegenüber v1.0

v1.1 entstand aus einem Abgleich der v1.0 mit dem tatsächlichen Code-Stand.
Jede Änderung ist unten begründet — v1.0 ist damit **überholt** und soll nicht
mehr als Bauvorlage verwendet werden.

### 0.1 Technische Korrekturen (nicht verhandelbar, sonst nicht baubar)

| # | v1.0 | v1.1 | Grund |
|---|------|------|-------|
| 1 | `NullBooleanField` | `BooleanField(null=True)` | `NullBooleanField` wurde in Django 4.0 **entfernt**; Projekt läuft `Django==5.1` |
| 2 | Feldnamen/Codes mit Umlauten (`task4_durchführung_erledigt`, `durchgeführt_am`, `status='beschlüsse_verarbeitet'`) | ASCII (`task4_durchfuehrung_erledigt`, `durchgefuehrt_am`, `'beschluesse_verarbeitet'`) | Projektkonvention: alle Feldnamen und Choice-Codes ASCII, Umlaute ausschließlich in `verbose_name`/`help_text`. Sonst UTF-8-Spaltennamen in Postgres |
| 3 | FK auf `mitarbeiter.Mitarbeiter`, `on_delete=SET_NULL` | `settings.AUTH_USER_MODEL`, `on_delete=PROTECT` | `Mitarbeiter` ist reines Profil (Abteilungen/Objektzuordnung). Alle Audit-Felder im Projekt zeigen auf den User und sind PROTECT (GoBD: Urheber darf nicht verschwinden) |
| 4 | Modell `Eigentuemeversammlung`; „6 Modelle", 5 gelistet | `Eigentuemerversammlung`; 9 Modelle, alle gelistet | Tippfehler (fehlendes „r"); Zählfehler |
| 5 | PDF via `reportlab` | **WeasyPrint 65.1 + Django-Template**, Anlagen-Merge via PyMuPDF | `reportlab` ist nicht installiert. Hausmuster: `abrechnung_wp/services/wp_pdf_service.py`, `buchhaltung/services/jahresabrechnung/pdf_service.py` |
| 6 | `Dokument.quelle='ev-einladung'`, `Dokument.portal_sichtbar=True` | `dokument_typ` / `kategorie`; Portal-Sichtbarkeit über die EV, nicht über das Dokument | Beide Felder existieren am `Dokument` **nicht**. Vorhanden: `kategorie`, `dokument_typ` (enthält bereits `'beschluss'`). `portal_sichtbar` gibt es nur an `Vorgang` |
| 7 | Einladungs-PDF gleichzeitig an Objekt und Person | 1 Dokument am **Objekt**, Personenbezug über `EVVersandprotokoll` | `dokumente/models.py` erzwingt per DB-CheckConstraint (Owner-Regel B-Hybrid) **höchstens einen** Kontext-FK aus (objekt, einheit, vorgang, person) |
| 8 | App `vorgaenge_ev` | App `apps.versammlung`, registriert in `LOCAL_APPS` + `config/urls.py` | `vorgaenge_ev` suggeriert eine Sub-App von `apps.vorgaenge`, die es nicht gibt. Registrierung fehlte in v1.0 komplett |
| 9 | `EVListPortal.jsx` usw. | `.tsx` | Im Repo existiert keine einzige `.jsx`-Datei; Frontend ist durchgehend TypeScript |
| 10 | `EVVersandlokal`, `unique_together (ev, person)` | `EVVersandprotokoll`, **ohne** unique_together | Ein dokumentierter Wiederholversand (Mail-Bounce, Adresskorrektur) war sonst nicht protokollierbar |
| 11 | EPost-Pfad `/dokumente/epost/…` | `MEDIA_ROOT/epost/…`, Auflösung über `beleg_service.dokument_pfad()` | Pfade in der DB sind immer Docker-Pfade (`/app/…`), nie Host-/Windows-Pfade |

### 0.2 Fachliche Korrekturen (WEG-Reform zum 01.12.2020)

| # | v1.0 | v1.1 | Grund |
|---|------|------|-------|
| 12 | Quorum 50 % blockiert Beschlüsse, Ergebnis `quorum_nicht_erreicht` | Quorum wird berechnet und **nur informativ angezeigt**; Ergebniswert entfällt | § 25 Abs. 3 WEG a.F. (Beschlussfähigkeit) ist mit der Reform entfallen — die Versammlung ist **immer beschlussfähig**. v1.0 hätte gültige Beschlüsse als ungültig geführt |
| 13 | Modus „doppelt qualifiziert (≥66,7 %)" | `qualifizierte_mehrheit` mit **konfigurierbarer** Schwelle je TOP | Die doppelt qualifizierte Mehrheit für Modernisierung ist entfallen (§ 20 WEG n.F.). Qualifizierte Mehrheiten gelten nur noch, wenn Teilungserklärung/Vereinbarung sie ausdrücklich vorschreibt |
| 14 | Enthaltungen ohne Regel | Enthaltungen zählen bei `einfache_mehrheit` und `qualifizierte_mehrheit` **nicht** in den Nenner | Ständige Praxis/Rechtsprechung: es zählen die abgegebenen Ja/Nein-Stimmen |
| 15 | keine Beschluss-Sammlung | Neues Modell `Beschluss` + `BeschlussNummerZaehler` (je Objekt fortlaufend) | § 24 Abs. 7 WEG: Führung der Beschluss-Sammlung ist **Verwalterpflicht** (fortlaufende Nummer, Wortlaut, Datum, Ort, Vermerk zu Anfechtung/Aufhebung) |
| 16 | 5 Boolean-Flags ohne Historie | Flags **bleiben** + neues `EVEreignis` (unveränderlicher Audit-Verlauf) | Beschlüsse sind binnen 1 Monat anfechtbar (§ 45 WEG). Wer wann welches Ergebnis erfasst hat, muss nachweisbar sein. Muster: `vorgaenge.VorgangEreignis` |
| 17 | `vertreten_durch` ohne Nachweis | `vertreten_durch` + `vollmacht_dokument` + Regel zur Stimmkraftübertragung | Vollmachtnachweis ist bei Anfechtung der erste Prüfpunkt |

### 0.3 Datenmodell- und Scope-Entscheidungen (von Patrik am 2026-08-19 bestätigt)

| # | Entscheidung |
|---|---|
| 18 | **Stimmkraft:** Feld `stimmprinzip` an der EV. Ursprünglich `kopf` / `objekt` / `mea`; **seit 2026-08-20** `kopf` / `verteilerschluessel` + FK `stimm_verteilerschluessel` (Details in Kap. 5). Teilnehmer werden aus den aktiven `EigentumsVerhaeltnis`-Datensätzen des Objekts erzeugt |
| 19 | **Portal:** Vollportal mit Eigentümer-Login. Das ist ein **eigenes Voraussetzungsmodul** (Kap. 11), nicht Teil dieses Moduls. EV-Phase C setzt es voraus |
| 20 | **Recht:** Quorum informativ, Mehrheitsmodi nach WEG n.F., Beschluss-Sammlung nach § 24 Abs. 7 WEG in Task 5 |

### 0.4 Wiederverwendung statt Neubau

| # | v1.0 | v1.1 |
|---|------|------|
| 21 | Task 5 „erstelle WP-Entwurf" | Andocken an vorhandenes `buchhaltung.WirtschaftsplanBeschluss` + `wirtschaftsplan_beschluss_service.beschluss_erfassen()` (bringt rückwirkende Sollstellungskorrektur und `HausgeldHistorie`-Kopplung mit) |
| 22 | Task 5 „HA-Entwurf mit `gewerk=NULL`" | Es entsteht ein **Vorgang** (`typ.code='ev-beschluss'`); der Handwerkerauftrag wird daraus manuell erzeugt. `handwerker.auftrag_service.erstelle_auftrag()` verlangt zwingend einen `kreditor` — ein HA ohne Handwerker ist nicht anlegbar |

---

## 1. Geltungsbereich

**In Scope (dieses Modul):**
Task-gesteuerter EV-Prozess von der Terminierung bis zur Beschluss-Sammlung,
Einladungs-PDF, Multi-Kanal-Versand, Anwesenheits- und Abstimmungserfassung,
Protokoll-PDF, Automations-Andockung an Wirtschaftsplan-Beschluss und Vorgang.

**Out of Scope (bewusst):**
- Eigentümer-Portal-Infrastruktur (eigenes Modul, Kap. 11)
- Umlaufbeschlüsse ohne Versammlung (§ 23 Abs. 3 WEG) — das Modell `Beschluss`
  ist dafür vorbereitet (`top` nullable), der Erfassungsweg kommt später
- Online-/Hybrid-Teilnahme (§ 23 Abs. 1a WEG)
- Elektronische Einzelabstimmung durch Eigentümer im Portal (v1.1 erfasst die
  Verwaltung die Ergebnisse; Einzelvoten sind im Modell abbildbar)

---

## 2. Verifizierter Ist-Stand im Code

Grundlage der Spec, jeweils selbst geprüft:

| Baustein | Ort | Für dieses Modul relevant |
|---|---|---|
| `Objekt` | `apps/objekte/models.py:5` | `objekt_typ` (WEG/ZH/SEV), `bezeichnung`, `betreuer` (auth.User) |
| `Einheit` | `apps/objekte/models.py:131` | `einheit_nr`, `lage`, `flaechennummer` — **kein** MEA-Feld |
| `Verteilerschluessel` / `VerteilerschluesselWert` | `apps/objekte/models.py:161` / `:194` | MEA liegt hier: `vs_typ='mea'` → `wert` je Einheit, `wirtschaftsjahr=0` (zeitlos), `beteiligt` |
| `Person` | `apps/personen/models.py:40` | `anrede`, `briefanrede`/`briefanrede2`, `emails` (JSON, neu) + `email` (Legacy), `adresse`, **kein** User-Bezug |
| `EigentumsVerhaeltnis` | `apps/personen/models.py:165` | `einheit`, `person`, `beginn`, `ende` (NULL = aktiv). **UniqueConstraint `uniq_aktiver_vertrag_je_einheit`: je Einheit höchstens ein aktives Verhältnis** |
| `Dokument` | `apps/dokumente/models.py:110` | Owner-Regel B-Hybrid (max. 1 Kontext-FK), `dokument_typ` incl. `'beschluss'`, `kategorie`, `revisionssicher`, `beleg_nummer` |
| `Vorgang` / `VorgangTyp` / `VorgangEreignis` | `apps/vorgaenge/models.py` | Andockpunkt für Beschluss-Folgeaufgaben; `quelle='beschluss'` existiert bereits als Choice |
| `WirtschaftsplanBeschluss` | `apps/buchhaltung/models.py:1802` | Ziel des WP-Triggers, inkl. `protokoll_dokument`, `protokoll_position` |
| `wirtschaftsplan_beschluss_service` | `apps/buchhaltung/services/` | `beschluss_erfassen()`, `beschluss_buchen()`, `beschluss_stornieren()` |
| `auftrag_service.erstelle_auftrag` | `apps/handwerker/services/` | `kreditor` ist Pflichtparameter |
| `AuftragsbestaetigungsToken` | `apps/handwerker/models.py:297` | Muster für Zugriff ohne Login (`secrets.token_urlsafe`, `views_oeffentlich.py`) |
| Mailversand | `apps/handwerker/tasks.py` | `_versand_konfiguriert()` — Konsolen-/Dummy-Backend gilt als nicht versandfähig. **Muss hier übernommen werden** |
| PDF | `apps/abrechnung_wp/services/wp_pdf_service.py` | WeasyPrint + `render_to_string`, deutsche Zahlenformatierung |
| Auth | `config/urls.py` | JWT (SimpleJWT), kein Custom-User, Rollen über `auth.Group` |

**Wichtige Konsequenz aus `uniq_aktiver_vertrag_je_einheit`:**
Miteigentum wird derzeit **nicht** über mehrere `EigentumsVerhaeltnis`-Zeilen
abgebildet, sondern über die Zweitperson-Felder der `Person`
(`vorname2`/`nachname2`/`briefanrede2`, Anrede „Eheleute"). Pro Einheit gibt es
also genau einen stimmberechtigten Datensatz. Die Stimmkraftlogik in Kap. 5
baut darauf auf.

---

## 3. Rechtsrahmen (Umsetzungsregeln, keine Rechtsberatung)

1. **Beschlussfähigkeit:** entfällt. Kein Quorum als Gate. Das berechnete
   Quorum wird angezeigt und ins Protokoll geschrieben, blockiert aber nie.
2. **Einfache Mehrheit:** `ja > nein`, Enthaltungen bleiben außen vor.
3. **Qualifizierte Mehrheit:** nur wenn Teilungserklärung/Vereinbarung sie
   vorschreibt. Schwelle je TOP konfigurierbar (`mehrheit_schwelle`, Default
   66.67), Bezugsgröße = abgegebene Ja/Nein-Stimmen.
4. **Einstimmigkeit:** keine Nein-Stimme unter den abgegebenen Stimmen und
   mindestens eine Ja-Stimme.
5. **Allstimmigkeit:** Zustimmung **aller** Eigentümer des Objekts, auch der
   nicht anwesenden — Bezugsgröße ist die Gesamtstimmkraft, nicht die anwesende.
6. **Beschluss-Sammlung (§ 24 Abs. 7 WEG):** fortlaufende Nummer je Objekt,
   Wortlaut, Datum und Ort der Versammlung, Vermerk über Anfechtungsklage und
   über gerichtliche Aufhebung. Einträge werden nie gelöscht, nur vermerkt.
7. **Anfechtung (§ 45 WEG, 1 Monat):** jede Änderung an Anwesenheit,
   Abstimmungsergebnis und Beschlusstext erzeugt ein `EVEreignis`.
8. **Ladungsfrist (§ 24 Abs. 4 WEG, 3 Wochen):** wird beim Versand geprüft und
   als **Warnung** ausgegeben (nicht blockierend — kurzfristige Ladung kann
   nötig sein und macht Beschlüsse anfechtbar, nicht nichtig).

---

## 4. Datenmodell v1.1 — App `apps.versammlung`

Registrierung (fehlte in v1.0):
- `config/settings.py` → `LOCAL_APPS += ['apps.versammlung']`
- `config/urls.py` → `path(API_PREFIX, include('apps.versammlung.urls'))`

### 4.1 `Eigentuemerversammlung`

```python
class Eigentuemerversammlung(models.Model):
    """Ein EV-Prozess über 5 Tasks (Spec v1.1 Kap. 4.1).

    Die fünf ``taskN_..._erledigt``-Flags sind reine Fortschrittsanzeige und
    absichtlich nicht gegated — die Verwaltung arbeitet die Tasks in
    beliebiger Reihenfolge ab. Jeder Flag-Wechsel erzeugt ein ``EVEreignis``
    (GoBD/§ 45 WEG), Statuswechsel laufen ausschließlich über
    ``ev_service`` und nie durch direktes Setzen von ``status``.
    """

    STATUS_CHOICES = [
        ('entwurf',                'Entwurf'),
        ('in_bearbeitung',         'In Bearbeitung'),
        ('einladungen_versendet',  'Einladungen versendet'),
        ('durchgefuehrt',          'Durchgeführt'),
        ('beschluesse_verarbeitet','Beschlüsse verarbeitet'),
        ('archiviert',             'Archiviert'),
    ]
    ART_CHOICES = [
        ('ordentlich',    'Ordentliche Versammlung'),
        ('ausserordentl', 'Außerordentliche Versammlung'),
        ('wiederholung',  'Wiederholungsversammlung'),
    ]
    STIMMPRINZIP_CHOICES = [
        ('kopf',                'Kopfprinzip (§ 25 Abs. 2 WEG: eine Stimme je Eigentümer)'),
        ('verteilerschluessel', 'Nach Verteilerschlüssel'),
    ]

    id      = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    objekt  = models.ForeignKey(
        'objekte.Objekt', on_delete=models.PROTECT,
        related_name='eigentuemerversammlungen',
    )
    arbeitsname = models.CharField(
        max_length=200, blank=True, default='',
        help_text='Interne Bezeichnung, z.B. "EV 2026 ordentlich".',
    )
    art = models.CharField(max_length=15, choices=ART_CHOICES, default='ordentlich')

    # ── Task 1: Terminierung ──
    termin                = models.DateTimeField(null=True, blank=True)
    ort                   = models.CharField(max_length=255, blank=True, default='')
    raum_buchung_notizen  = models.TextField(blank=True, default='')
    terminvorschlaege     = models.JSONField(
        default=list, blank=True,
        help_text='Vorschlagsliste aus der Beiratsabstimmung: '
                  '[{"termin": "2026-03-15T19:00", "notiz": "..."}]',
    )

    # ── Abstimmungsgrundlage ──
    stimmprinzip = models.CharField(
        max_length=20, choices=STIMMPRINZIP_CHOICES, default='kopf',
        help_text='Gesetzlicher Regelfall ist das Kopfprinzip; abweichende '
                  'Regelungen stehen in der Teilungserklärung.',
    )
    stimm_verteilerschluessel = models.ForeignKey(
        'objekte.Verteilerschluessel', on_delete=models.PROTECT,
        null=True, blank=True, related_name='eigentuemerversammlungen',
        help_text='Grundlage der Stimmkraft bei stimmprinzip='
                  '"verteilerschluessel" — z.B. 030 (je Einheit), 031 (nur '
                  'Wohnungen), 010 (MEA).',
    )
    stimm_wirtschaftsjahr = models.IntegerField(
        default=0,
        help_text='Wirtschaftsjahr für den MEA-Verteilerschlüssel; 0 = zeitlos '
                  '(Regelfall, siehe VerteilerschluesselWert.wirtschaftsjahr).',
    )

    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='entwurf')

    task1_terminierung_erledigt    = models.BooleanField(default=False)
    task2_tagesordnung_erledigt    = models.BooleanField(default=False)
    task3_einladung_erledigt       = models.BooleanField(default=False)
    task4_durchfuehrung_erledigt   = models.BooleanField(default=False)
    task5_beschlussfassung_erledigt= models.BooleanField(default=False)

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

    erstellt_am  = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='erstellte_eigentuemerversammlungen',
    )
    einladung_versendet_am = models.DateTimeField(null=True, blank=True)
    durchgefuehrt_am       = models.DateTimeField(null=True, blank=True)
    versammlungsleiter     = models.CharField(max_length=200, blank=True, default='')
    protokollfuehrer       = models.CharField(max_length=200, blank=True, default='')

    class Meta:
        verbose_name        = 'Eigentümerversammlung'
        verbose_name_plural = 'Eigentümerversammlungen'
        ordering            = ['-termin', '-erstellt_am']
        indexes = [
            models.Index(fields=['objekt', '-termin']),
            models.Index(fields=['status']),
        ]

    def clean(self):
        # SEV/ZH haben keine Eigentümerversammlung — eine EV dort wäre ein
        # Datenfehler, der erst beim Versand auffiele (leere Teilnehmerliste).
        if self.objekt_id and self.objekt.objekt_typ != 'WEG':
            raise ValidationError(
                'Eine Eigentümerversammlung ist nur für WEG-Objekte vorgesehen.'
            )
```

**Bewusst nicht übernommen:** `erstellt_von = SET_NULL, null=True` aus v1.0 —
Urheberzuordnung ist bei anfechtbaren Beschlüssen nicht optional.

### 4.2 `Tagesordnungspunkt`

```python
class Tagesordnungspunkt(models.Model):
    """Ein TOP mit Beschlussvorlage, Mehrheitsmodus und Ergebnis."""

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

    id     = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    ev     = models.ForeignKey(
        Eigentuemerversammlung, on_delete=models.CASCADE, related_name='tagesordnung',
    )
    nummer = models.IntegerField(help_text='Fortlaufend ab 1.')
    titel  = models.CharField(max_length=255)
    erlaeuterung      = models.TextField(blank=True, default='')
    beschlussvorlage  = models.TextField(
        blank=True, default='',
        help_text='Wortlaut, über den abgestimmt wird. Pflicht außer bei '
                  'abstimmungsmodus="kein_beschluss".',
    )

    abstimmungsmodus = models.CharField(
        max_length=25, choices=MODUS_CHOICES, default='einfache_mehrheit',
    )
    mehrheit_schwelle = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text='Nur bei abstimmungsmodus="qualifizierte_mehrheit": '
                  'erforderlicher Ja-Anteil an den abgegebenen Stimmen in '
                  'Prozent (z.B. 66.67). Grundlage ist die Teilungserklärung.',
    )

    # Ergebnis-Summen (Stimmkraft, nicht Köpfe — daher Decimal)
    abstimmung_ja         = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    abstimmung_nein       = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    abstimmung_enthaltung = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    abstimmungsergebnis   = models.CharField(
        max_length=12, choices=ERGEBNIS_CHOICES, default='offen',
    )
    ergebnis_bemerkung = models.TextField(blank=True, default='')

    # Automations-Trigger (greifen nur bei abstimmungsergebnis='angenommen')
    triggert_vorgang = models.BooleanField(
        default=False,
        verbose_name='Folge-Vorgang anlegen',
        help_text='Erzeugt bei Annahme einen Vorgang (z.B. Sanierung, '
                  'Handwerkerbeauftragung). Ein Handwerkerauftrag entsteht '
                  'daraus manuell — auftrag_service verlangt einen Kreditor.',
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
        if self.abstimmungsmodus != 'kein_beschluss' and not self.beschlussvorlage.strip():
            raise ValidationError({'beschlussvorlage': 'Beschlussvorlage erforderlich.'})
        if self.abstimmungsmodus == 'qualifizierte_mehrheit' and not self.mehrheit_schwelle:
            raise ValidationError({'mehrheit_schwelle': 'Schwelle bei qualifizierter Mehrheit erforderlich.'})
```

### 4.3 `EVTeilnehmer` und `EVTeilnehmerAnteil`

**Abweichung von der Entscheidung „FK auf EigentumsVerhaeltnis" — mit Begründung:**
Der FK sitzt nicht am `EVTeilnehmer`, sondern an einer Kindtabelle. Grund: beim
Kopfprinzip hat ein Eigentümer mit drei Einheiten **eine** Stimme. Läge der FK
direkt am Teilnehmer, gäbe es drei Teilnehmerzeilen und damit drei Stimmen —
oder man müsste die Stimmkraft auf 1/3 pro Zeile verteilen, was Anwesenheit und
Protokoll unlesbar macht. Deshalb:

- `EVTeilnehmer` = eine Zeile **je Person** (Stimmberechtigter, Anwesenheit, Zusage)
- `EVTeilnehmerAnteil` = eine Zeile **je aktivem `EigentumsVerhaeltnis`** dieser
  Person (Einheitenbezug + MEA-Snapshot)

Damit sind alle drei Stimmprinzipien aus derselben Struktur rechenbar.

```python
class EVTeilnehmer(models.Model):
    """Stimmberechtigter Eigentümer einer EV inkl. Zusage und Anwesenheit."""

    ZUSAGE_CHOICES = [
        ('offen',     'Keine Rückmeldung'),
        ('zugesagt',  'Zusage'),
        ('abgesagt',  'Absage'),
    ]

    id     = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    ev     = models.ForeignKey(
        Eigentuemerversammlung, on_delete=models.CASCADE, related_name='teilnehmer',
    )
    person = models.ForeignKey(
        'personen.Person', on_delete=models.PROTECT, related_name='ev_teilnahmen',
    )

    zusage_status = models.CharField(max_length=10, choices=ZUSAGE_CHOICES, default='offen')
    zusage_am     = models.DateTimeField(null=True, blank=True)
    zusage_quelle = models.CharField(
        max_length=10, blank=True, default='',
        help_text='"portal" oder "manuell" — wer die Rückmeldung erfasst hat.',
    )

    ist_anwesend = models.BooleanField(
        null=True, blank=True,
        help_text='NULL = noch nicht erfasst (Django-5-Ersatz für NullBooleanField).',
    )
    anwesenheit_erfasst_am = models.DateTimeField(null=True, blank=True)
    vertreten_durch = models.ForeignKey(
        'personen.Person', on_delete=models.PROTECT, null=True, blank=True,
        related_name='ev_vertretungen',
        help_text='Bevollmächtigter. Die Stimmkraft bleibt bei diesem '
                  'Teilnehmer und wird dem Vertreter nicht addiert.',
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
        help_text='Snapshot beim Einladungsversand, ermittelt nach '
                  'Eigentuemerversammlung.stimmprinzip (siehe stimmkraft_service).',
    )

    class Meta:
        verbose_name        = 'EV-Teilnehmer'
        verbose_name_plural = 'EV-Teilnehmer'
        ordering            = ['ev', 'person__nachname', 'person__vorname']
        constraints = [
            models.UniqueConstraint(fields=['ev', 'person'], name='uniq_teilnehmer_je_ev'),
        ]

    def clean(self):
        if self.vertreten_durch_id and self.vertreten_durch_id == self.person_id:
            raise ValidationError('Eine Person kann sich nicht selbst vertreten.')


class EVTeilnehmerAnteil(models.Model):
    """Eine Einheit des Teilnehmers — Einheitenbezug und MEA-Snapshot.

    Der Snapshot ist bewusst redundant zu ``VerteilerschluesselWert``: ändert
    sich der MEA nach der Versammlung, muss das Protokoll weiterhin die damals
    gültige Stimmkraft ausweisen (§ 45 WEG, Anfechtbarkeit).
    """

    id  = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    teilnehmer = models.ForeignKey(
        EVTeilnehmer, on_delete=models.CASCADE, related_name='anteile',
    )
    eigentumsverhaeltnis = models.ForeignKey(
        'personen.EigentumsVerhaeltnis', on_delete=models.PROTECT,
        related_name='ev_teilnehmer_anteile',
    )
    einheit_nr_snapshot = models.CharField(max_length=20, blank=True, default='')
    mea_wert_snapshot   = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True,
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
```

### 4.4 `EVStimme`

v1.0 nannte das Modell `EVAbstimmungsergebnis` — verwechselbar mit dem
Ergebnis am TOP. v1.1: `EVStimme` (Einzelvotum, optional; das Summenergebnis
am TOP kann auch direkt erfasst werden).

```python
class EVStimme(models.Model):
    """Einzelvotum eines Teilnehmers zu einem TOP (optionaler Audit-Trail).

    Wird nur gefüllt, wenn namentlich abgestimmt wird. Der Regelfall ist die
    Summenerfassung am TOP; beide Wege sind über
    ``durchfuehrung_service.erfasse_abstimmung`` bzw.
    ``erfasse_einzelstimmen`` konsistent gehalten.
    """

    VOTUM_CHOICES = [
        ('ja',         'Ja'),
        ('nein',       'Nein'),
        ('enthaltung', 'Enthaltung'),
    ]

    id  = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    top = models.ForeignKey(
        Tagesordnungspunkt, on_delete=models.CASCADE, related_name='stimmen',
    )
    teilnehmer = models.ForeignKey(
        EVTeilnehmer, on_delete=models.CASCADE, related_name='stimmen',
    )
    votum      = models.CharField(max_length=10, choices=VOTUM_CHOICES)
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
```

### 4.5 `EVVersandprotokoll`

```python
class EVVersandprotokoll(models.Model):
    """Protokolliert jeden Versandversuch je Person und Kanal.

    Ohne unique_together (bewusste Abweichung von v1.0): ein Wiederholversand
    nach Bounce oder Adresskorrektur muss dokumentierbar bleiben.
    """

    KANAL_CHOICES = [
        ('portal', 'Portal (Dokument + Benachrichtigungsmail)'),
        ('email',  'E-Mail mit PDF-Anhang'),
        ('epost',  'EPost (manueller Postversand)'),
    ]
    STATUS_CHOICES = [
        ('erfolgreich',   'Erfolgreich'),
        ('fehlgeschlagen','Fehlgeschlagen'),
        ('uebersprungen', 'Übersprungen'),
    ]

    id     = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    ev     = models.ForeignKey(
        Eigentuemerversammlung, on_delete=models.CASCADE, related_name='versandprotokolle',
    )
    person = models.ForeignKey(
        'personen.Person', on_delete=models.PROTECT, related_name='ev_versandprotokolle',
    )
    kanal        = models.CharField(max_length=10, choices=KANAL_CHOICES)
    status       = models.CharField(max_length=15, choices=STATUS_CHOICES, default='erfolgreich')
    empfaenger   = models.CharField(
        max_length=255, blank=True, default='',
        help_text='Verwendete E-Mail-Adresse bzw. Postanschrift (Nachweis).',
    )
    epost_pfad   = models.CharField(
        max_length=500, blank=True, default='',
        help_text='Docker-Pfad der abgelegten PDF (unter MEDIA_ROOT/epost/…), '
                  'nie ein Host-/Windows-Pfad.',
    )
    fehlertext   = models.TextField(blank=True, default='')
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
```

### 4.6 `EVEreignis`

```python
class EVEreignis(models.Model):
    """Unveränderlicher Audit-Verlauf zur EV (§ 45 WEG, GoBD).

    Muster: apps.vorgaenge.VorgangEreignis. Es gibt keinen Endpunkt zum
    Ändern oder Löschen von Ereignissen.
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

    id  = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    ev  = models.ForeignKey(
        Eigentuemerversammlung, on_delete=models.CASCADE, related_name='ereignisse',
    )
    top = models.ForeignKey(
        Tagesordnungspunkt, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ereignisse',
    )
    typ         = models.CharField(max_length=25, choices=TYP_CHOICES)
    text        = models.TextField(blank=True, default='')
    alter_wert  = models.CharField(max_length=200, blank=True, default='')
    neuer_wert  = models.CharField(max_length=200, blank=True, default='')
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
```

### 4.7 `Beschluss` und `BeschlussNummerZaehler` (§ 24 Abs. 7 WEG)

```python
class BeschlussNummerZaehler(models.Model):
    """Fortlaufende Beschlussnummer je Objekt (§ 24 Abs. 7 WEG).

    Zugriff ausschließlich über ``naechste_nummer()`` — SELECT FOR UPDATE
    innerhalb einer Transaktion (Muster: BelegnummerZaehler,
    VorgangNummerZaehler).
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


class Beschluss(models.Model):
    """Eintrag der Beschluss-Sammlung nach § 24 Abs. 7 WEG.

    Einträge werden NIE gelöscht und der Wortlaut nie geändert. Anfechtung
    und gerichtliche Aufhebung werden ausschließlich vermerkt
    (``anfechtung_status``, ``aufgehoben_am``, ``gerichtlicher_hinweis``).
    """

    ANFECHTUNG_CHOICES = [
        ('keine',      'Keine Anfechtung bekannt'),
        ('anhaengig',  'Anfechtungsklage anhängig'),
        ('abgewiesen', 'Klage abgewiesen'),
        ('aufgehoben', 'Beschluss gerichtlich aufgehoben'),
    ]

    id     = models.UUIDField(primary_key=True, default=uuid4, editable=False)
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
        help_text='NULL bei Umlaufbeschluss (§ 23 Abs. 3 WEG) — für später vorgesehen.',
    )
    top = models.OneToOneField(
        Tagesordnungspunkt, on_delete=models.PROTECT, null=True, blank=True,
        related_name='beschluss',
    )

    beschluss_datum = models.DateField()
    ort             = models.CharField(max_length=255, blank=True, default='')
    wortlaut        = models.TextField(
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

    anfechtung_status    = models.CharField(
        max_length=12, choices=ANFECHTUNG_CHOICES, default='keine',
    )
    anfechtung_notiz     = models.TextField(blank=True, default='')
    aufgehoben_am        = models.DateField(null=True, blank=True)
    gerichtlicher_hinweis = models.TextField(blank=True, default='')

    erstellt_am  = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='erstellte_beschluesse',
    )

    class Meta:
        verbose_name        = 'Beschluss'
        verbose_name_plural = 'Beschluss-Sammlung'
        ordering            = ['objekt', '-nummer']
        constraints = [
            models.UniqueConstraint(fields=['objekt', 'nummer'], name='uniq_beschluss_nummer_je_objekt'),
        ]

    def save(self, *args, **kwargs):
        if not self.nummer:
            self.nummer = BeschlussNummerZaehler.naechste_nummer(self.objekt)
        super().save(*args, **kwargs)
```

**Modelle insgesamt: 9** — `Eigentuemerversammlung`, `Tagesordnungspunkt`,
`EVTeilnehmer`, `EVTeilnehmerAnteil`, `EVStimme`, `EVVersandprotokoll`,
`EVEreignis`, `Beschluss`, `BeschlussNummerZaehler`.

---

## 5. Stimmkraft-Ermittlung (`services/stimmkraft_service.py`)

### 5.1 Teilnehmerkreis

```
aktive_verhaeltnisse = EigentumsVerhaeltnis.objects.filter(
    einheit__objekt=ev.objekt, ende__isnull=True,
).select_related('einheit', 'person')
```
Gruppierung nach `person_id` → je Person ein `EVTeilnehmer`, je Verhältnis ein
`EVTeilnehmerAnteil`.

### 5.2 Stimmkraft je Prinzip

| `stimmprinzip` | `EVTeilnehmer.stimmkraft` |
|---|---|
| `kopf` | `Decimal('1')` — unabhängig von der Anzahl Einheiten (§ 25 Abs. 2 WEG) |
| `verteilerschluessel` | Summe der Werte des gewählten Verteilerschlüssels über alle Einheiten der Person. Einheiten, die am Schlüssel nicht beteiligt sind, tragen bewusst nichts bei (z.B. Stellplätze in VS 031) |

Damit deckt ein Codepfad alle Regelungen der Teilungserklärung ab: VS `030`
„Anzahl Einheiten Gesamt" = eine Stimme je Einheit, VS `031` „Anzahl
Wohnungen" = Stellplätze stimmen nicht mit, VS `010` „MEA Gesamt" =
Wertprinzip, VS `001` = Fläche.

MEA-Quelle:
```
Verteilerschluessel.objects.get(objekt=ev.objekt, vs_typ='mea', aktiv=True)
  → VerteilerschluesselWert.objects.filter(
        schluessel=ev.stimm_verteilerschluessel, wirtschaftsjahr=ev.stimm_wirtschaftsjahr,
        beteiligt=True
    ).wert
```

**Datenlage (geprüft am 2026-08-19, lokale DB = Live-Kopie):** Der
MEA-Verteilerschlüssel existiert auf allen 40 Objekten (Schlüssel `010`,
„MEA Gesamt"), aber **alle 1096 Wertzeilen haben `wert = NULL`** — die
Muster-Anlage in `konten/services.py:MUSTER_VS` legt den MEA-Schlüssel
bewusst ohne Werte an, und nachgetragen wurde bisher nichts. Das Stimmprinzip
`mea` ist damit erst nutzbar, wenn die Werte gepflegt sind; `kopf` und `objekt`
funktionieren auf dem Bestand sofort.

Fehlerfälle beim MEA-Prinzip werden **nicht** stillschweigend zu 0:
- kein aktiver MEA-Verteilerschlüssel am Objekt → `ValidationError`
  („Objekt hat keinen aktiven MEA-Verteilerschlüssel — Stimmprinzip 'mea' nicht möglich")
- fehlender oder 0-Wert für eine beteiligte Einheit → `ValidationError` mit
  Auflistung der betroffenen Einheiten
Begründung: eine still verlorene Stimme macht jeden Beschluss angreifbar.

### 5.3 Snapshot-Zeitpunkt

Snapshot beim **Einladungsversand** (Task 3) — die Einladung geht an die zu
diesem Zeitpunkt eingetragenen Eigentümer.
Wechselt zwischen Einladung und Versammlung der Eigentümer, ruft die Verwaltung
in Task 4 `stimmkraft_neu_ermitteln(ev)` auf: neue Teilnehmer werden ergänzt,
weggefallene auf `stimmkraft=0` gesetzt (nicht gelöscht — Nachweis, wer geladen
wurde), jede Änderung erzeugt ein `EVEreignis('stimmkraft_ermittelt')`.

### 5.4 Quorum (informativ)

```python
def berechne_quorum(ev) -> dict:
    """{'gesamt_stimmkraft', 'anwesende_stimmkraft', 'anwesend_prozent',
        'hinweis'} — reine Information.

    Seit der WEG-Reform 2020 ist die Versammlung immer beschlussfähig; es gibt
    daher bewusst KEIN Feld 'quorum_erreicht' und kein Gate auf die
    Abstimmungserfassung.
    """
```

---

## 6. Service-Layer

Aufteilung nach Projektmuster (`apps/<app>/services/<thema>_service.py`,
Funktionen auf Modulebene, keine Klassen — vgl. `vorgang_service`,
`auftrag_service`). Business-Logik ausschließlich in `services/`, nie in Views
oder Tasks.

| Datei | Funktionen |
|---|---|
| `services/ev_service.py` | `erstelle_ev()`, `aktualisiere_terminierung()`, `markiere_task_erledigt()`, `setze_task_zurueck()`, `task_status()`, `wechsle_status()`, `vermerke_ereignis()` |
| `services/tagesordnung_service.py` | `top_anlegen()`, `top_aktualisieren()`, `top_loeschen()`, `neu_nummerieren()`, `pruefe_vollstaendigkeit()` |
| `services/stimmkraft_service.py` | `ermittle_teilnehmer()`, `stimmkraft_neu_ermitteln()`, `berechne_quorum()` |
| `services/einladung_service.py` | `erzeuge_einladungs_pdf()`, `versandplan()`, `versende_einladungen()`, `pruefe_ladungsfrist()` |
| `services/durchfuehrung_service.py` | `erfasse_anwesenheit()`, `erfasse_abstimmung()`, `erfasse_einzelstimmen()`, `bewerte_ergebnis()` |
| `services/beschluss_service.py` | `uebernimm_in_sammlung()`, `erzeuge_folgevorgaenge()`, `vermerke_anfechtung()`, `erzeuge_protokoll_pdf()` |
| `tasks.py` | `versende_ev_einladungen` (Celery, darf nie durchwerfen), `erinnere_zusagen` |

### 6.1 Ergebnisbewertung (`bewerte_ergebnis`)

```python
def bewerte_ergebnis(top, ja, nein, enthaltung, gesamt_stimmkraft) -> str:
    """Liefert 'angenommen' oder 'abgelehnt'.

    Enthaltungen zählen bei einfacher und qualifizierter Mehrheit nicht in
    den Nenner — es entscheiden die abgegebenen Ja/Nein-Stimmen.
    """
    abgegeben = ja + nein
    if top.abstimmungsmodus == 'einfache_mehrheit':
        return 'angenommen' if ja > nein else 'abgelehnt'
    if top.abstimmungsmodus == 'qualifizierte_mehrheit':
        if not abgegeben:
            return 'abgelehnt'
        anteil = (ja / abgegeben) * 100
        return 'angenommen' if anteil >= top.mehrheit_schwelle else 'abgelehnt'
    if top.abstimmungsmodus == 'einstimmigkeit':
        return 'angenommen' if (nein == 0 and ja > 0) else 'abgelehnt'
    if top.abstimmungsmodus == 'allstimmigkeit':
        # Bezugsgröße ist die Gesamtstimmkraft aller Eigentümer, auch der
        # nicht anwesenden.
        return 'angenommen' if ja >= gesamt_stimmkraft else 'abgelehnt'
    raise ValidationError('Modus "kein_beschluss" kennt kein Abstimmungsergebnis.')
```

Plausibilitätsprüfung vor dem Speichern: `ja + nein + enthaltung` darf die
anwesende Stimmkraft nicht überschreiten → sonst `ValidationError` mit beiden
Zahlen im Text. Jede Korrektur eines bereits erfassten Ergebnisses erzeugt
`EVEreignis('abstimmung_korrigiert')` mit `alter_wert`/`neuer_wert`.

---

## 7. PDF-Generierung

**Werkzeuge:** WeasyPrint 65.1 (HTML→PDF, wie `wp_pdf_service`) für den
generierten Teil, PyMuPDF (`fitz`) zum Anhängen hochgeladener PDF-Anlagen.

Templates unter `backend/templates/versammlung/`:
- `einladung.html` — Anschreiben, Termin/Ort, Ladungsfristhinweis, Tagesordnung
  je TOP (Nummer, Titel, Erläuterung, Beschlussvorlage, Mehrheitsmodus)
- `protokoll.html` — Kopf (Objekt, Termin, Ort, Versammlungsleiter,
  Protokollführer), Anwesenheitsliste mit Stimmkraft und Vertretungen,
  Quorum-Angabe (informativ), je TOP Ergebnis, Beschlusstexte

**Anlagen:**
- Nur PDF-Anlagen werden angehängt (PyMuPDF `insert_pdf`).
- Andere Dateitypen werden mit klarer Meldung abgelehnt, nicht stillschweigend
  weggelassen.
- ✅ **Auf Live geprüft (2026-08-20):** Im Prod-Container sind PyMuPDF 1.28.2
  und WeasyPrint 65.1 vorhanden, der Merge-Pfad (`insert_pdf`) funktioniert.
  Dabei fiel auf, dass der Alias `fitz` seit PyMuPDF 1.24 deprecated ist,
  `requirements.txt` aber nur `>=1.24` pinnt. Der Service lädt deshalb zuerst
  `pymupdf` und fällt nur für ältere Installationen auf `fitz` zurück — sonst
  würde der Wegfall des Alias als "PyMuPDF ist nicht installiert" gemeldet,
  also mit falscher Diagnose. Fehlt das Paket wirklich, wird die Anlage
  **nicht** verschluckt: `erzeuge_einladungs_pdf()` bricht mit klarer Meldung ab.

---

## 8. Versand

### 8.1 Kanalermittlung (`versandplan`)

Je Teilnehmer, in dieser Reihenfolge:

| Bedingung | Kanal |
|---|---|
| Person hat Portalzugang (Kap. 11) **und** eine E-Mail-Adresse | `portal` |
| Person hat E-Mail-Adresse, keinen Portalzugang | `email` |
| sonst | `epost` |

E-Mail-Ermittlung: erste Adresse aus `Person.emails` (JSON-Liste), sonst
`Person.email` (Legacy). Die Verwaltung kann den vorgeschlagenen Kanal je Person
im Frontend überschreiben — der Plan ist Vorschlag, keine Zwangsroute.

### 8.2 DMS-Ablage (Owner-Regel B-Hybrid)

Es entsteht **ein** Einladungs-Dokument je EV:
- `Dokument.objekt = ev.objekt` (einziger gesetzter Kontext-FK)
- `dokument_typ='korrespondenz'`, `kategorie='EV-Einladung'`
- `dateiname = f'Einladung_EV_{termin:%Y-%m-%d}.pdf'`
- verknüpft über `Eigentuemerversammlung.einladungs_pdf`

Kein Dokument-Datensatz je Person — der Personenbezug steht im
`EVVersandprotokoll`. Grund: der CheckConstraint erlaubt nur einen Kontext-FK,
ein personenbezogenes Dokument verlöre den Objektbezug.

Protokoll und Beschlüsse analog am Objekt, Beschlüsse mit
`dokument_typ='beschluss'` und `revisionssicher=True`.

### 8.3 Portal-Sichtbarkeit

`Dokument` hat kein `portal_sichtbar`. v1.1 fügt es **nicht** hinzu (Eingriff in
ein zentrales Modell mit GoBD-Bezug), sondern steuert die Sichtbarkeit über die
EV: das Portal liefert `ev.einladungs_pdf` aus, sobald
`ev.status` mindestens `einladungen_versendet` ist, und `ev.protokoll_pdf`,
sobald `beschluesse_verarbeitet` erreicht ist. Zugriffsprüfung: die anfragende
Person muss `EVTeilnehmer` dieser EV sein.

### 8.4 Kanal `email`

Mailversand über Celery-Task, `EmailMultiAlternatives` mit PDF-Anhang.
`_versand_konfiguriert()` aus `handwerker/tasks.py` wird übernommen: ist nur das
Konsolen-/Dummy-Backend konfiguriert, wird **nicht** als versendet markiert,
sondern `EVVersandprotokoll(status='fehlgeschlagen')` geschrieben. Sonst gilt
eine EV als eingeladen, obwohl keine Mail das Haus verlassen hat.

### 8.5 Kanal `epost`

- Ordner `MEDIA_ROOT/epost/EV_{ev.id}_{termin:%Y-%m-%d}/`
- Je Person `{Nachname}_{Vorname}_Einladung.pdf` mit personalisiertem
  Anschreiben (Briefanrede aus `Person.briefanrede`, Anschrift aus
  `Person.adresse`)
- `versand.csv` mit `Name;Anschrift;Einheit;PDF-Datei` (Semikolon, UTF-8 mit
  BOM — Excel-kompatibel)
- Pfade in `EVVersandprotokoll.epost_pfad` als Docker-Pfade

---

## 9. Beschlussfassung (Task 5)

Ablauf in `beschluss_service.uebernimm_in_sammlung(ev, user)`, eine Transaktion:

1. Je TOP mit `abstimmungsergebnis='angenommen'`:
   - `Beschluss` anlegen (Nummer über `BeschlussNummerZaehler`, `wortlaut` =
     `top.beschlussvorlage`, Datum/Ort aus der EV, Ergebnis-Summen)
   - Beschluss-PDF ins DMS (`dokument_typ='beschluss'`, `revisionssicher=True`)
2. `top.triggert_vorgang` → `Vorgang` mit `typ.code='ev-beschluss'`,
   `quelle='beschluss'`, `objekt=ev.objekt`, `zugewiesen_an=objekt.betreuer`.
   Der Handwerkerauftrag wird daraus **manuell** erzeugt (Kreditorauswahl).
3. `top.triggert_wirtschaftsplan` → `Vorgang` „Wirtschaftsplan-Beschluss
   erfassen" mit Verweis auf den Beschluss. Die eigentliche Erfassung läuft
   über das bestehende `wirtschaftsplan_beschluss_service.beschluss_erfassen()`
   (dort hängen Sollstellungskorrektur und `HausgeldHistorie`) — hier wird
   nichts nachgebaut.
4. Protokoll-PDF erzeugen, `ev.protokoll_pdf` setzen.
5. `ev.status='beschluesse_verarbeitet'`, `task5_..._erledigt=True`, Ereignisse.

`VorgangTyp(code='ev-beschluss')` wird per Datenmigration angelegt (Muster:
`buchhaltung/migrations/0021_seed_buchungsarten.py`).

Fehlerfall: Die Übernahme ist atomar. Schlägt ein Schritt fehl, bleibt Task 5
offen und die Meldung nennt den TOP — kein Teilzustand mit halber
Beschluss-Sammlung.

---

## 10. API

Prefix `api/v1/`, Router in `apps/versammlung/urls.py`.

### 10.1 Backoffice

```
GET    versammlungen/                          Liste (Filter: objekt, status, jahr)
POST   versammlungen/                          Anlegen {objekt, arbeitsname, art, stimmprinzip}
GET    versammlungen/{id}/                      Details inkl. Task-Status
PATCH  versammlungen/{id}/                      Termin, Ort, Notizen, Einladungstext, Stimmprinzip
POST   versammlungen/{id}/task-erledigt/        {"task_nr": 1..5}
POST   versammlungen/{id}/task-zuruecksetzen/   {"task_nr": 1..5, "grund": "..."}
GET    versammlungen/{id}/ereignisse/           Audit-Verlauf

GET    versammlungen/{id}/tagesordnung/         TOP-Liste
POST   tagesordnungspunkte/                     TOP anlegen
PATCH  tagesordnungspunkte/{id}/                TOP ändern
DELETE tagesordnungspunkte/{id}/                TOP löschen (nur solange status='entwurf'/'in_bearbeitung')

POST   versammlungen/{id}/teilnehmer-ermitteln/ Teilnehmer + Stimmkraft-Snapshot
GET    versammlungen/{id}/teilnehmer/           Teilnehmerliste mit Stimmkraft
POST   versammlungen/{id}/einladung-pdf/        {"anlagen_ids": [...]} → PDF erzeugen
GET    versammlungen/{id}/versandplan/          Vorschlag je Person + Ladungsfrist-Warnung
POST   versammlungen/{id}/einladungen-versenden/ {"plan": {person_id: kanal}}
GET    versammlungen/{id}/versandprotokoll/     Ergebnis je Person

PATCH  ev-teilnehmer/{id}/                      Anwesenheit, Vertretung, Zusage (manuell)
GET    versammlungen/{id}/quorum/               informativ
POST   tagesordnungspunkte/{id}/abstimmung/     {"ja","nein","enthaltung"} (Stimmkraft)
POST   tagesordnungspunkte/{id}/einzelstimmen/  [{"teilnehmer_id","votum"}]

POST   versammlungen/{id}/beschluesse-uebernehmen/  Task 5
GET    versammlungen/{id}/protokoll-pdf/           Download
GET    objekte/{id}/beschluss-sammlung/            § 24 Abs. 7 WEG, chronologisch
POST   beschluesse/{id}/anfechtung/                {"anfechtung_status","notiz"}
```

### 10.2 Portal (setzt Kap. 11 voraus)

```
GET  portal/versammlungen/                  eigene EVs (über EVTeilnehmer)
GET  portal/versammlungen/{id}/             Termin, Ort, Status
GET  portal/versammlungen/{id}/einladung/   PDF (ab status='einladungen_versendet')
GET  portal/versammlungen/{id}/tagesordnung/
POST portal/versammlungen/{id}/zusage/      {"zusage": true|false}
GET  portal/versammlungen/{id}/ergebnisse/  ab status='durchgefuehrt'
GET  portal/versammlungen/{id}/protokoll/   ab status='beschluesse_verarbeitet'
```

Rechteprüfung in jedem Portal-Endpunkt: `EVTeilnehmer.objects.filter(ev=…,
person=request.user.portal_zugang.person).exists()`. Kein Objekt- oder
EV-Filter über Query-Parameter, der Zugriff wird immer serverseitig aus dem
Portalzugang abgeleitet.

---

## 11. Voraussetzungsmodul: Eigentümer-Portal (Phase 0)

**Warum getrennt:** Im Code existiert kein Eigentümer-Portal. `Person` hat
keinen User-Bezug; vorhanden ist nur `Vorgang.portal_sichtbar` und der
Mitarbeiter-Endpunkt `vorgaenge/{id}/portal-vorschau/`. Eigentümer-Login,
Rechtemodell und eigene Frontend-Sektion sind ein eigenes Modul und keine
Teilaufgabe der EV.

**Mindestumfang (eigene Spezifikation, hier nur Rahmen):**
- `personen.PortalZugang`: `OneToOne(User)` + `FK(Person)`, `aktiv`,
  `letzter_login`, `erstellt_von`
- Rolle über `auth.Group('eigentuemer')`; DRF-Permission `IstPortalNutzer`,
  die jeden Backoffice-Endpunkt für diese Gruppe sperrt
- Einladungsverfahren: Verwaltung erzeugt einen Zugang, das System versendet
  einen zeitlich begrenzten Einmal-Link zum Setzen des Passworts (Muster:
  `AuftragsbestaetigungsToken`, `secrets.token_urlsafe`). Passwörter werden
  ausschließlich vom Eigentümer selbst gesetzt.
- Frontend: eigener Bereich `frontend/src/pages/portal/` mit eigenem Layout und
  eigener Navigation, strikt getrennt von der Mitarbeiter-Oberfläche
- Trennschärfe-Tests: ein Portalnutzer darf keinen Backoffice-Endpunkt und kein
  Dokument fremder Objekte erreichen (negative Tests sind hier Pflicht, nicht
  Beigabe)

**Abhängigkeit:** EV-Phase C startet erst, wenn Phase 0 abgenommen ist. Ohne
Phase 0 sind nur die Kanäle `email` und `epost` nutzbar — der Versandplan
liefert dann für alle Personen `email`/`epost`, das Modul bleibt voll
funktionsfähig.

---

## 12. Phasenplan

| Phase | Inhalt | Abhängigkeit | HALT-Gate |
|---|---|---|---|
| **A** ✅ | App `apps.versammlung`, 9 Modelle, Migration `0001_initial`, `ev_service`, `tagesordnung_service`, `stimmkraft_service`, `seed_ev_testdaten`, 87 Unit-Tests — **umgesetzt am 2026-08-19, lokal, nicht committet** | — | 🛑 Patrik bestätigt Datenmodell |
| **B** ✅ | Serializer/ViewSets, Backoffice-API (17 Routen), WeasyPrint-Template, `einladung_service`, Celery-Task, Backoffice-Frontend (Liste + Task-Dashboard für Tasks 1–3), 73 weitere Tests — **umgesetzt am 2026-08-20, lokal, nicht committet** | A | 🛑 Backoffice-Workflow mit Patrik durchgespielt |
| **D** ✅ | `durchfuehrung_service`, Quorum, Ergebnisbewertung, `beschluss_service`, Beschluss-Sammlung, Protokoll- und Beschluss-PDF, Andockung WP/Vorgang, Frontend (Durchführungsmaske, Beschlussfassung, Beschluss-Sammlung) — **umgesetzt am 2026-08-20, lokal, nicht committet** | B | 🛑 Durchführung und Beschluss-Sammlung geprüft |
| **0** | Modul Eigentümer-Portal (eigene Spec) | — | 🛑 Portal-Trennschärfe geprüft |
| **C** | Portal-Endpunkte, `.tsx`-Komponenten (`EVListPortal`, `EVDetailPortal`, `EVZusageModal`), ≥20 Portal-Tests inkl. negativer Zugriffstests | 0, B | 🛑 Portal-Usability |
| **E** | Smoke-Tests: vollständiger Durchlauf, Kanalmischung, alle Mehrheitsmodi inkl. Grenzfällen (Ja=Nein, alles Enthaltung, 0 Anwesende), Stimmprinzip-Wechsel, Eigentümerwechsel zwischen Einladung und Versammlung, PDF mit/ohne Anlagen | A–D | 🛑 Freigabe durch Patrik |

Reihenfolge bewusst A → B → D → C: die Durchführung ist der fachliche Kern und
hängt nicht am Portal. Phase C kann parallel zu D laufen, sobald Phase 0 steht.

**Frontend Backoffice** (Teil von B und D):
`frontend/src/pages/versammlungen/` — Task-Dashboard, TO-Builder,
Einladungs-Generator mit Versandvorschau, Durchführungsmaske,
Beschluss-Sammlung je Objekt.

---

## 13. Fehlerbehandlung

| Fall | Verhalten |
|---|---|
| TOP ohne Beschlussvorlage (Modus ≠ `kein_beschluss`) | `ValidationError` im `clean()`, Feldfehler am Formular |
| Qualifizierte Mehrheit ohne Schwelle | `ValidationError` am Feld `mehrheit_schwelle` |
| MEA-Prinzip ohne MEA-Verteilerschlüssel | Abbruch der Teilnehmerermittlung mit Klartextmeldung; kein stiller 0-Wert |
| Ungültige/fehlende E-Mail | Kanal fällt auf `epost`; `EVVersandprotokoll(status='uebersprungen')` mit Grund |
| SMTP nicht konfiguriert (Konsolen-Backend in Produktion) | Versand gilt als **fehlgeschlagen**, EV bleibt „nicht versendet" |
| PDF-Erzeugung schlägt fehl | Rollback, kein `einladungs_pdf` gesetzt, Fehlertext an den Aufrufer |
| Anlage ist kein PDF | Ablehnung mit Dateinamen; keine stille Auslassung |
| `fitz` im Prod-Image nicht importierbar | Abbruch mit Betriebshinweis (siehe Kap. 7) |
| Summe der Stimmen > anwesende Stimmkraft | `ValidationError` mit beiden Zahlen |
| Ladungsfrist < 3 Wochen | **Warnung** im Versandplan, kein Blocker |
| Beschlussübernahme scheitert teilweise | Gesamttransaktion zurück, Task 5 bleibt offen |
| Eigentümerwechsel nach Einladung | `stimmkraft_neu_ermitteln()`; alte Teilnehmer bleiben mit `stimmkraft=0` erhalten |
| Task-Rücksetzung nach Versand | erlaubt, aber nur mit Begrundung; `EVEreignis('task_zurueckgesetzt')` |

**Betriebshinweis (gilt für jede Migration dieses Moduls):** Der Celery-Worker
lädt Modelldefinitionen beim Start. Nach jeder Migration
`docker restart immocore_celery_worker` — sonst laufen die Versand-Tasks mit
veraltetem Schema-Wissen ins `ProgrammingError`.

---

## 14. Offene Punkte

| # | Punkt | Vorschlag |
|---|---|---|
| 1 | Einladungstext-Vorlage je Objekt oder global? | v1.1: global als Konstante im Service, überschreibbar je EV in `einladungstext`. Objektbezogene Vorlagen später |
| 2 | Umlaufbeschlüsse (§ 23 Abs. 3 WEG) | Modell `Beschluss` ist vorbereitet (`ev` nullable), Erfassungsweg in einer Folgephase |
| 3 | Online-/Hybridteilnahme (§ 23 Abs. 1a WEG) | nicht in v1.1 |
| 4 | Namentliche Einzelabstimmung als Regelfall | v1.1: Summenerfassung ist Standard, `EVStimme` optional |
| 5 | Zweitversammlung bei Nichtbeschlussfähigkeit | entfällt rechtlich; `art='wiederholung'` bleibt für Wiederholungsversammlungen aus anderen Gründen |
| 6 | Erinnerung an offene Zusagen | Celery-Task `erinnere_zusagen` vorgesehen, Auslösezeitpunkt (z.B. 7 Tage vor Termin) noch festzulegen |
| 7 | MEA-Werte sind systemweit nicht gepflegt (alle `NULL`, siehe Kap. 5.2) | Offen. Für eine EV nach MEA (VS `010`) müssen die Werte je Objekt nachgetragen werden; der Service bricht sonst mit Hinweis ab. `kopf` und VS `030` funktionieren sofort |
| 8 | ✅ **Entschieden 2026-08-20:** Stimmkraft-Grundlage ist ein FK auf `Verteilerschluessel`; `objekt` und `mea` sind entfallen. Migration `0003` bildet Bestandszeilen ab (`objekt`→VS 030, `mea`→VS 010, sonst `kopf`) | Umgesetzt |
| 9 | ✅ **Entschieden 2026-08-20:** Bei Stimmprinzip `verteilerschluessel` bricht `ermittle_teilnehmer` ab, wenn Einheiten mit Stimmkraft keinen aktiven Eigentümer haben — mit Nennung der Einheiten und der fehlenden Stimmkraft. Betrifft aktuell Objekt 10031 (16 von 32 Einheiten). Beim Kopfprinzip ist der Fall folgenlos und wird nicht blockiert | Umgesetzt |
| 10 | `versand_konfiguriert()` existiert doppelt (hier und `handwerker.tasks._versand_konfiguriert`) | Beim dritten Aufrufer in einen gemeinsamen Helfer ziehen |
| 11 | Statusübergang `in_bearbeitung` → `durchgefuehrt` wurde in Phase D ergänzt (Versammlung ohne über IMMOCORE dokumentierten Versand) — der Umweg über `einladungen_versendet` hätte die EV fälschlich als versendet ausgewiesen | Umgesetzt, hier nur zur Kenntnis |
| 12 | `Beschluss.vorgang` ist ein einzelner FK; ein TOP mit beiden Triggern erzeugt zwei Vorgänge, verlinkt aber nur den ersten (Umsetzungsvorgang). Beide nennen die Beschlussnummer im Text | Bewusst so; bei Bedarf später M2M |

---

**Autor:** Claude (Opus 5), auf Basis von v1.0
**Grundlage:** Code-Stand `main` @ 3fb630d, geprüft am 2026-08-19
**Freigabe:** offen — HALT-Gate A
