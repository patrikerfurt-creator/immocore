# IMMOCORE — Auto-Pipeline Hausgeld-Sollstellung & SEPA-Lastschrift

**Version:** v1.0
**Status:** 🟢 Implementierungsreif
**Bezug:** Erweitert `CLAUDE_CODE_ANLEITUNG_HAUSGELD_NEBENBUCH_v1_1.md`
**Greenfield-Annahme:** IMMOCORE noch nicht im Produktivbetrieb; keine Migration alter Auto-Läufe nötig.

---

## 1. Zweck

Diese Spec automatisiert den monatlich wiederkehrenden Vorgang
**Hausgeld-Sollstellung erzeugen → SEPA-Lastschriftdatei (pain.008)
ableiten → in Ablageordner schreiben**.

Bisher (Hausgeld/Nebenbuch-Spec v1.1) wird beides manuell je Objekt
über UI-Wizards mit Vier-Augen-Prinzip ausgelöst. Bei einem Bestand von
N Objekten ergibt das N×2 Wizard-Durchläufe pro Monat — purer
mechanischer Aufwand ohne sachlichen Mehrwert, weil:

- Sollstellungen eine **deterministische Funktion** der Stammdaten sind
  (`HausgeldHistorie` × aktive BAs); die wirkliche Kontrolle gehört in
  die Stammdatenpflege, nicht in die monatliche Sollstellung
- Die Vier-Augen-Prüfung der pain.008 weiterhin im **Banking-Tool
  Windata** stattfindet, in dem der Verwalter beim Import die Summen
  prüft und mit TAN/HBCI freigibt — die Letzte-Verteidigungslinie bleibt
  erhalten

Die Automatisierung greift **vor** dem Banking-Tool. IMMOCORE schreibt
die pain.008 in einen Ordner; Windata-Import bleibt manueller
Vier-Augen-Schritt.

## 2. Architekturprinzipien (was sich NICHT ändert)

| Prinzip | Verhalten |
|---|---|
| GoBD-Unwiderruflichkeit | Auto-erzeugte Sollstellungen sind nicht unterscheidbar von manuell erzeugten — gleiche Modelle, gleiche OPOS-Nr.-Vergabe, gleiche Storno-Regeln (Kap. 8 Hausgeld/Nebenbuch-Spec) |
| Idempotenz | `run_hausgeld_monat` bleibt idempotent über Unique-Constraint `(objekt, eigentumsverhaeltnis, sollstellungs_typ, periode)`. Zweiter Aufruf erzeugt keine Duplikate. |
| Service-Wiederverwendung | Auto-Pipeline ruft die bestehenden Services `sollstellungslauf_service.run_hausgeld_monat` und `sepa_lastschrift_service.commite_lastschriftlauf` auf — keine Parallel-Implementierung |
| Manuelle Läufe weiterhin möglich | Die UI-Wizards bleiben erhalten. Verwalter kann jederzeit zusätzlich manuell auslösen (z.B. bei deaktivierter Auto-Pipeline) |

## 3. Was sich ändert

| Bereich | Änderung |
|---|---|
| Celery-Beat | Neuer Periodic-Task `task_auto_hausgeld_pipeline` (mandantenweit, täglich 02:00 Uhr) |
| System-User | Neuer User „IMMOCORE-Autopilot" als `erstellt_von`/`commited_von` für Auto-Läufe |
| Vier-Augen-Constraint | Constraint `freigabe_user != erstellt_von` wird für Läufe mit `lauf_quelle='autopilot'` übersprungen |
| Audit-Trail | Neue Tabelle `AutoLaufProtokoll` (GoBD-relevant) |
| Konfiguration | `.env`-Variablen für Ordnerpfad, Stichtag, Notausschalter; Objekt-Flag `auto_pipeline_aktiv` |
| SEPA-Fristen | Neuer Service `sepa_fristen_service` mit Bankarbeitstags-Logik (Bundesweite Feiertage + objekt-spezifisches Bundesland) |

## 4. Annahmen

| Nr. | Annahme | Konsequenz bei Verletzung |
|---|---|---|
| A1 | Alle SEPA-Mandate sind `sequence_type=RCUR`. FRST-Lastschriften kommen in IMMOCORE nicht vor. | Wenn doch nötig: manueller Lauf außerhalb der Auto-Pipeline. Auto-Pipeline filtert FRST-Mandate explizit aus und meldet sie als Frontoffice-Aufgabe. |
| A2 | Demme reicht pain.008 manuell über Windata ein. Die Vier-Augen-Prüfung liegt in Windata. | Falls Demme auf EBICS-Watcher umstellt: globaler Kill-Switch `SEPA_AUTOPILOT_AKTIV=false` setzen und Spec neu evaluieren. |
| A3 | Pro Objekt existiert genau **ein** Hausgeld-Lastschriftlauf pro Monat. | Mehrfache Läufe werden über Unique-Constraint verhindert. |
| A4 | `auto_pipeline_aktiv` default = `True` für neue Objekte. | Manuelles Opt-out je Objekt möglich. |

---

## 5. Konfiguration

### 5.1 `.env`-Variablen

```env
# Auto-Pipeline Master-Switch (Notausschalter)
SEPA_AUTOPILOT_AKTIV=true

# Stichtag im Vormonat (Tag des Monats, an dem die Pipeline läuft)
# Empfohlen: 25 (genug Puffer für SEPA-Frist RCUR = 2 BD + Wochenenden)
SEPA_AUTOPILOT_STICHTAG=25

# UUID des System-Users "IMMOCORE-Autopilot"
SEPA_AUTOPILOT_USER_ID=00000000-0000-0000-0000-000000000001

# Ablageordner für erzeugte pain.008-Dateien
# UNC-Pfad wird unterstützt (\\server\share\...)
SEPA_OUTPUT_DIR=\\demme-server\sepa\out

# Archivordner (alte Läufe werden nach 90 Tagen hierhin verschoben)
SEPA_OUTPUT_ARCHIVE_DIR=\\demme-server\sepa\archive

# Soll-Vorlauf in Bankarbeitstagen vor Fälligkeit
# RCUR-Mindest: 2 BD; empfohlen: 5 BD Puffer
SEPA_AUTOPILOT_VORLAUF_BD=5
```

### 5.2 Objekt-Flag

| Feld | Typ | Default | Anmerkung |
|---|---|---|---|
| `objekt.auto_pipeline_aktiv` | Boolean | `True` | Pro-Objekt-Notbremse; deaktiviert nur diese eine Objekt-Pipeline |
| `objekt.bundesland` | CharField(2) | Pflicht bei Neuanlage | ISO-3166-2 Code (z.B. `HE`, `BY`); für Bankfeiertage-Berechnung |

`bundesland` ist neu — falls bei Bestandsobjekten nicht gepflegt, Default `HE` (Demme-Sitz Frankfurt) verwenden und im Logfile warnen.

### 5.3 System-User

Datenmigration legt einmalig einen User an:

```python
User.objects.create(
    id=settings.SEPA_AUTOPILOT_USER_ID,
    username='immocore-autopilot',
    first_name='IMMOCORE',
    last_name='Autopilot',
    email='autopilot@noreply.immocore.local',
    is_active=True,
    is_staff=False,
    is_superuser=False,
)
```

User darf nicht für Login benutzbar sein (`set_unusable_password()`).
In allen Audit-Anzeigen wird dieser User mit speziellem Icon
(z.B. Roboter-Symbol) dargestellt, damit auf den ersten Blick klar
ist: maschinell erzeugt.

---

## 6. Datenmodell-Ergänzungen

### 6.1 `HausgeldSollstellungslauf` (Erweiterung)

| Neues Feld | Typ | Default | Anmerkung |
|---|---|---|---|
| `lauf_quelle` | Enum: `manuell` / `autopilot` | `manuell` | Diskriminator |

### 6.2 `Lastschriftlauf` (Erweiterung)

| Neues Feld | Typ | Default | Anmerkung |
|---|---|---|---|
| `lauf_quelle` | Enum: `manuell` / `autopilot` | `manuell` | |
| `datei_pfad` | CharField(500), nullable | `None` | Absoluter Pfad der erzeugten pain.008-Datei |

### 6.3 Neue Tabelle `AutoLaufProtokoll`

GoBD-Audit-Tabelle. Ein Eintrag pro Auto-Pipeline-Aufruf je Objekt.

| Feld | Typ | Anmerkung |
|---|---|---|
| `id` | UUID (PK) | |
| `objekt` | FK → Objekt | |
| `ausgefuehrt_am` | DateTimeField | Zeitpunkt des Task-Starts |
| `periode` | DateField | Zielperiode des Laufs (z.B. 2026-04-01) |
| `status` | Enum: `erfolg` / `teilweise_erfolg` / `fehler` / `uebersprungen` | |
| `sollstellungslauf` | FK → HausgeldSollstellungslauf, nullable | NULL bei Fehler vor Sollstellungs-Erzeugung |
| `lastschriftlauf` | FK → Lastschriftlauf, nullable | NULL bei Fehler vor Lastschrift-Erzeugung |
| `anzahl_evs_geplant` | IntegerField | |
| `anzahl_evs_erfolgreich` | IntegerField | |
| `anzahl_evs_uebersprungen` | IntegerField | |
| `summe_sollstellungen` | DecimalField(14,2) | |
| `summe_lastschrift` | DecimalField(14,2) | Kann kleiner sein als Summe Sollstellungen, wenn EVs ohne Mandat |
| `datei_pfad` | CharField(500), nullable | Pfad der erzeugten pain.008 |
| `warnungen` | JSONField | Liste `[{ev_id, name, einheit, warnung_typ, nachricht}]` |
| `fehler` | TextField, nullable | Stack-Trace bei `status='fehler'` |

Read-only nach Erstellung. Niemals löschen.

### 6.4 Frontoffice-Aufgabe `AutoPipelineWarnung`

Bestehendes Frontoffice-Aufgaben-Modell wird genutzt; neuer
`aufgabe_typ='auto_pipeline_warnung'`:

| Warnungstyp | Beispieltext |
|---|---|
| `kein_sepa_mandat` | „Auto-Pipeline: SEPA-Mandat fehlt für Müller, WE01. EV wurde aus Lastschriftlauf ausgeschlossen — bitte Mandat anfordern und Lastschrift manuell erzeugen." |
| `keine_iban` | „Auto-Pipeline: Keine IBAN hinterlegt für Schulze, WE03." |
| `keine_hausgeldhistorie` | „Auto-Pipeline: Kein Hausgeldsatz in der Historie für Wagner, WE07 (Stichtag 01.04.2026)." |
| `mandat_typ_frst` | „Auto-Pipeline: Erst-Mandat (FRST) bei Becker, WE05 — wird nicht automatisch eingezogen." |
| `sepa_frist_unterschritten` | „Auto-Pipeline: Lauf zu spät gestartet, Fälligkeit musste auf 04.04.2026 verschoben werden." |
| `dateischreibfehler` | „Auto-Pipeline: pain.008-Datei konnte nicht geschrieben werden — Pfad nicht erreichbar." |

---

## 7. Celery-Beat-Schedule

```python
# config/celery.py
app.conf.beat_schedule = {
    'auto-hausgeld-pipeline': {
        'task': 'apps.buchhaltung.tasks.task_auto_hausgeld_pipeline',
        'schedule': crontab(hour=2, minute=0),  # täglich 02:00 Uhr
    },
    'task-sammeltransfer-monatsende': {
        # bestehend, siehe Hausgeld/Nebenbuch-Spec Kap. 7.4
        'task': 'apps.buchhaltung.tasks.task_sammeltransfer_monatsende',
        'schedule': crontab(day_of_month='last', hour=22, minute=0),
    },
}
```

**Warum täglich, nicht nur am Stichtag?**
Robustheit gegen Container-Ausfälle. Der Task prüft jeden Tag: „Bin ich
heute der Stichtag?" — wenn nein, sofort `return`. Wenn am Stichtag der
Server down war, fängt der Folgetag den Lauf nach (mit Warnung
`sepa_frist_unterschritten`). Ein einmaliger Cron-Eintrag würde bei
einem 24h-Ausfall den ganzen Monat überspringen.

---

## 8. Service-Architektur

### 8.1 Neue Module

```
apps/buchhaltung/services/
├── auto_pipeline_service.py      # NEU — Orchestrierung
└── sepa_fristen_service.py       # NEU — Bankarbeitstags-Logik

apps/buchhaltung/tasks/
└── auto_hausgeld_pipeline.py     # NEU — Celery-Task-Wrapper
```

### 8.2 Aufgabenverteilung

| Service / Task | Zuständigkeit |
|---|---|
| `task_auto_hausgeld_pipeline` | Celery-Eintrag; prüft Stichtag, iteriert über alle Objekte mit `auto_pipeline_aktiv=True`, ruft `auto_pipeline_service.run_objekt(objekt)` auf |
| `auto_pipeline_service.run_objekt(objekt, periode)` | Orchestrierung pro Objekt: Sollstellungslauf erzeugen → Lastschriftlauf erzeugen → pain.008 schreiben → Protokoll-Eintrag |
| `sepa_fristen_service.naechster_einreichungstag(stichtag, faelligkeit, bundesland)` | Bankarbeitstags-Berechnung |
| `sepa_fristen_service.ist_bankarbeitstag(datum, bundesland)` | Helfer; bundeseinheitliche + ggf. landesspezifische Feiertage |

---

## 9. Pseudocode

### 9.1 `task_auto_hausgeld_pipeline`

```python
@shared_task(bind=True, max_retries=0)
def task_auto_hausgeld_pipeline(self):
    """
    Täglich 02:00 Uhr. Prüft, ob heute der konfigurierte
    Stichtag im Monat ist. Wenn ja: läuft.
    """
    # 1. Master-Switch
    if not settings.SEPA_AUTOPILOT_AKTIV:
        logger.info("Auto-Pipeline deaktiviert (.env-Switch)")
        return

    # 2. Stichtag prüfen — sind wir HEUTE dran?
    heute = timezone.localdate()
    if not ist_stichtag_oder_nachholtag(heute):
        return  # Nicht heute. Sauber raus.

    # 3. Zielperiode bestimmen
    periode = naechste_periode(heute)  # erster Tag des Folgemonats

    # 4. Über alle aktiven Objekte iterieren
    objekte = Objekt.objects.filter(auto_pipeline_aktiv=True)
    autopilot_user = User.objects.get(pk=settings.SEPA_AUTOPILOT_USER_ID)

    for objekt in objekte:
        try:
            auto_pipeline_service.run_objekt(
                objekt=objekt,
                periode=periode,
                user=autopilot_user,
            )
        except Exception as e:
            # Fehler bei Objekt A führt NICHT zum Rollback bei Objekt B
            # (Verhalten wie Massenimport, Wirtschaftsjahre-Spec Kap. 5.4)
            logger.exception(f"Auto-Pipeline {objekt.objekt_nr} fehlgeschlagen")
            AutoLaufProtokoll.objects.create(
                objekt=objekt,
                periode=periode,
                status='fehler',
                fehler=traceback.format_exc(),
            )
```

### 9.2 `auto_pipeline_service.run_objekt`

```python
@transaction.atomic
def run_objekt(objekt, periode: date, user) -> AutoLaufProtokoll:
    """
    Atomarer Lauf pro Objekt. Bei Fehlern an einer beliebigen Stelle:
    Rollback des gesamten Objekt-Laufs. AutoLaufProtokoll bleibt
    bestehen (eigene Transaktion in Außenrahmen).

    Schritte:
      1. Idempotenz-Check: Existiert bereits ein commited Lauf
         für (objekt, periode, lauf_quelle='autopilot')?
      2. Sollstellungslauf erzeugen (run_hausgeld_monat)
      3. EVs für Lastschrift filtern (Mandat, IBAN, RCUR)
      4. Lastschriftlauf erzeugen
      5. pain.008-XML generieren
      6. Datei in SEPA_OUTPUT_DIR schreiben
      7. Protokoll-Eintrag schreiben
      8. Warnungen als Frontoffice-Aufgaben erzeugen
    """

    # 1. Idempotenz
    existierender_lauf = HausgeldSollstellungslauf.objects.filter(
        objekt=objekt,
        periode=periode,
        lauf_quelle='autopilot',
        status='commited',
    ).first()
    if existierender_lauf:
        logger.info(f"{objekt.objekt_nr}: Auto-Lauf für {periode} bereits vorhanden")
        return _protokoll_uebersprungen(objekt, periode, existierender_lauf)

    warnungen = []

    # 2. Sollstellungslauf (ruft bestehenden Service auf!)
    sollstellungslauf = run_hausgeld_monat(
        objekt=objekt,
        periode=periode,
        erstellt_von=user,
        skip_freigabe=True,      # Constraint übersprungen für Autopilot
        lauf_quelle='autopilot',
    )

    # 3. EVs für Lastschrift filtern
    kandidaten, ausgeschlossen = _filtere_lastschrift_kandidaten(
        sollstellungslauf
    )
    for eintrag in ausgeschlossen:
        warnungen.append(eintrag)
        _erzeuge_frontoffice_aufgabe(objekt, eintrag)

    if not kandidaten:
        # Keine Lastschrift-EVs — Sollstellungen sind aber erzeugt.
        # Verwalter klärt manuell.
        return _protokoll_teilerfolg_nur_sollstellung(
            objekt, periode, sollstellungslauf, warnungen
        )

    # 4. SEPA-Frist berechnen
    faelligkeit = sepa_fristen_service.naechster_einreichungstag(
        stichtag=timezone.localdate(),
        soll_faelligkeit=periode,
        bundesland=objekt.bundesland,
    )
    if faelligkeit > periode:
        warnungen.append({
            'warnung_typ': 'sepa_frist_unterschritten',
            'nachricht': f'Fälligkeit verschoben auf {faelligkeit}',
        })

    # 5. Lastschriftlauf erzeugen (ruft bestehenden Service auf!)
    lastschriftlauf = commite_lastschriftlauf(
        objekt=objekt,
        stichtag=faelligkeit,
        kandidaten=kandidaten,
        user=user,
        lauf_quelle='autopilot',
    )

    # 6. pain.008-XML generieren
    xml = generiere_pain008(lastschriftlauf)

    # 7. Datei schreiben
    datei_pfad = _schreibe_pain008_datei(
        xml=xml,
        objekt=objekt,
        periode=periode,
        lauf=lastschriftlauf,
    )
    lastschriftlauf.datei_pfad = datei_pfad
    lastschriftlauf.save(update_fields=['datei_pfad'])

    # 8. Protokoll
    return AutoLaufProtokoll.objects.create(
        objekt=objekt,
        periode=periode,
        status='erfolg' if not warnungen else 'teilweise_erfolg',
        sollstellungslauf=sollstellungslauf,
        lastschriftlauf=lastschriftlauf,
        anzahl_evs_geplant=sollstellungslauf.anzahl_sollstellungen,
        anzahl_evs_erfolgreich=len(kandidaten),
        anzahl_evs_uebersprungen=len(ausgeschlossen),
        summe_sollstellungen=sollstellungslauf.summe,
        summe_lastschrift=lastschriftlauf.summe,
        datei_pfad=datei_pfad,
        warnungen=warnungen,
    )
```

### 9.3 `_filtere_lastschrift_kandidaten`

```python
def _filtere_lastschrift_kandidaten(sollstellungslauf):
    """
    Filtert aus allen Sollstellungen des Laufs die EVs heraus, die
    NICHT per Lastschrift einziehbar sind. Diese werden im Sollstellungs-
    lauf belassen (Forderung steht!), aber aus pain.008 ausgeschlossen.

    Sammelt parallel die Ausschlussgründe als Warnungen.
    """
    kandidaten = []
    ausgeschlossen = []

    for sollstellung in sollstellungslauf.sollstellungen.filter(sollstellungs_typ='hausgeld'):
        ev = sollstellung.eigentumsverhaeltnis
        person = ev.person

        if not person.sepa_mandat:
            ausgeschlossen.append({
                'ev_id': ev.id,
                'name': person.anzeigename,
                'einheit': ev.einheit.einheit_nr,
                'warnung_typ': 'kein_sepa_mandat',
                'nachricht': f'{person.anzeigename}: SEPA-Mandat fehlt',
            })
            continue

        if person.sepa_mandat.sequence_type != 'RCUR':
            ausgeschlossen.append({
                'ev_id': ev.id,
                'name': person.anzeigename,
                'einheit': ev.einheit.einheit_nr,
                'warnung_typ': 'mandat_typ_frst',
                'nachricht': f'{person.anzeigename}: FRST-Mandat, manuelle Lastschrift nötig',
            })
            continue

        if not person.einzugs_iban():
            ausgeschlossen.append({
                'ev_id': ev.id,
                'name': person.anzeigename,
                'einheit': ev.einheit.einheit_nr,
                'warnung_typ': 'keine_iban',
                'nachricht': f'{person.anzeigename}: Keine IBAN hinterlegt',
            })
            continue

        kandidaten.append(sollstellung)

    return kandidaten, ausgeschlossen
```

### 9.4 `_schreibe_pain008_datei`

```python
def _schreibe_pain008_datei(xml, objekt, periode, lauf) -> str:
    """
    Schreibt pain.008 in SEPA_OUTPUT_DIR.

    UNC-Pfad-tauglich (analog Invoice-Sorter-Erfahrung: pathlib.Path
    + PollingObserver-Kompatibilität). Schreibt atomar via Temp-File +
    Rename, damit Windata nie eine halb-geschriebene Datei sieht.

    Dateinamen-Schema:
      {JJJJ-MM-TT}_{objekt_nr}_LS_{JJJJ-MM}.xml
    Beispiel: 2026-03-25_100001_LS_2026-04.xml
    """
    dateiname = (
        f'{timezone.localdate().isoformat()}_'
        f'{objekt.objekt_nr}_LS_'
        f'{periode.strftime("%Y-%m")}.xml'
    )

    zielordner = Path(settings.SEPA_OUTPUT_DIR)
    zielordner.mkdir(parents=True, exist_ok=True)
    ziel_pfad = zielordner / dateiname
    temp_pfad = zielordner / f'.{dateiname}.tmp'

    # Atomares Schreiben: temp + rename
    temp_pfad.write_text(xml, encoding='utf-8')
    temp_pfad.rename(ziel_pfad)

    logger.info(f'pain.008 geschrieben: {ziel_pfad}')
    return str(ziel_pfad)
```

### 9.5 `sepa_fristen_service.naechster_einreichungstag`

```python
def naechster_einreichungstag(
    stichtag: date,
    soll_faelligkeit: date,
    bundesland: str,
) -> date:
    """
    Gibt den frühestmöglichen Fälligkeitstag zurück, an dem eine
    pain.008-Einreichung mit RCUR-Mandaten gültig ist.

    SEPA-Regel RCUR: Einreichung mindestens 2 Bankarbeitstage vor
    Fälligkeit. Wir nehmen Vorlauf SEPA_AUTOPILOT_VORLAUF_BD (default 5).

    Wenn soll_faelligkeit erreichbar ist: gib soll_faelligkeit zurück.
    Wenn nicht: gib den nächstmöglichen Bankarbeitstag zurück.
    """
    benoetigt_bd = settings.SEPA_AUTOPILOT_VORLAUF_BD
    frueheste_faelligkeit = bd_addieren(stichtag, benoetigt_bd, bundesland)

    if frueheste_faelligkeit <= soll_faelligkeit:
        return soll_faelligkeit
    else:
        return frueheste_faelligkeit


def bd_addieren(start: date, anzahl_bd: int, bundesland: str) -> date:
    """Addiert N Bankarbeitstage auf start (= Tag X)."""
    kalender = _bankarbeitstag_kalender(bundesland)
    current = start
    addiert = 0
    while addiert < anzahl_bd:
        current += timedelta(days=1)
        if current.weekday() < 5 and current not in kalender.feiertage:
            addiert += 1
    return current


@functools.lru_cache(maxsize=64)
def _bankarbeitstag_kalender(bundesland: str):
    """
    Cache pro Bundesland. Nutzt holidays-Library:
      import holidays
      return holidays.Germany(state=bundesland, years=range(...))
    """
```

---

## 10. Idempotenz, Concurrency, Datei-Konflikte

### 10.1 Idempotenz auf Sollstellungs-Ebene

Bleibt unverändert: Unique-Constraint `(objekt, eigentumsverhaeltnis,
sollstellungs_typ, periode)`. Zweiter Aufruf erzeugt `IntegrityError`,
der im bestehenden Service abgefangen wird (Hausgeld/Nebenbuch-Spec
Kap. 12.3, Loop `continue`).

### 10.2 Idempotenz auf Lauf-Ebene

Neuer Unique-Constraint (Migration):

```python
class Meta:
    constraints = [
        models.UniqueConstraint(
            fields=['objekt', 'periode', 'lauf_quelle'],
            condition=Q(status='commited'),
            name='unique_commited_lauf_pro_periode_quelle',
        ),
    ]
```

→ Pro `(Objekt, Periode, autopilot)` darf maximal **ein** committed-Lauf
existieren. Vorschau- und storniert-Läufe sind beliebig oft erlaubt.

### 10.3 Datei-Konflikt

Wenn pro Tag mehrere Läufe für dasselbe Objekt geschrieben werden (sollte
nicht passieren, kann aber durch manuellen Zusatzlauf vorkommen):
Dateinamen kollidiert.

**Auflösung:** Wenn Zieldatei existiert, hänge `_v2`, `_v3` an:
```
2026-03-25_100001_LS_2026-04.xml
2026-03-25_100001_LS_2026-04_v2.xml
```

Das ist akzeptabel, weil Windata jede Datei beim Import einzeln zeigt
und der Verwalter erkennt: „Hier sind zwei für dasselbe Objekt — eine
ist falsch."

### 10.4 Concurrency

Celery-Beat triggert genau einmal pro Schedule-Eintrag. Falls
mehrere Worker laufen, garantiert Celery, dass nur **einer** den Task
übernimmt. Innerhalb des Tasks läuft `run_objekt` sequentiell pro
Objekt — keine Parallelisierung nötig (bei N=50 Objekten dauert der
Lauf wenige Minuten).

### 10.5 Archiv-Job

```python
@shared_task
def task_archiviere_alte_pain_dateien():
    """
    Verschiebt pain.008-Dateien älter als 90 Tage aus SEPA_OUTPUT_DIR
    nach SEPA_OUTPUT_ARCHIVE_DIR. Wöchentlich.
    """
```

---

## 11. Fehlerbehandlung — Zusammenfassung

| Fehler | Verhalten |
|---|---|
| `.env`-Switch aus | Task startet, returned sofort, kein Protokoll |
| Heute nicht Stichtag | Task startet, returned sofort, kein Protokoll |
| Objekt `auto_pipeline_aktiv=False` | Objekt überspringen, kein Protokoll |
| EV ohne SEPA-Mandat | EV überspringen, Frontoffice-Aufgabe, Sollstellung bleibt bestehen |
| EV mit FRST-Mandat | EV überspringen, Frontoffice-Aufgabe |
| EV ohne IBAN | EV überspringen, Frontoffice-Aufgabe |
| EV ohne Hausgeldhistorie | Sollstellungs-Service überspringt sowieso (Soll-Summe = 0); Frontoffice-Hinweis vom Auto-Pipeline-Service |
| SEPA-Frist unterschritten | Fälligkeit auf nächstmöglichen BD verschieben, Warnung erzeugen, Lauf läuft trotzdem |
| `SEPA_OUTPUT_DIR` nicht erreichbar | Lauf rollbacken (Sollstellung + Lastschrift), `AutoLaufProtokoll(status='fehler')` schreiben, Alarm |
| Bestehender commited Auto-Lauf für Periode | Lauf überspringen (Idempotenz), `status='uebersprungen'` |
| Sollstellungs-Lauf erfolgreich, Lastschrift fehlgeschlagen | Sollstellungs-Lauf bleibt bestehen (Forderung steht!), Protokoll `status='teilweise_erfolg'`, Verwalter erzeugt pain.008 manuell |
| Unerwartete Exception | Stack-Trace in `fehler`-Feld, Protokoll `status='fehler'`, Mail an Admin-User |

---

## 12. UI-Anforderungen

Drei neue Views, alle im bestehenden Buchhaltungs-Bereich:

### 12.1 Auto-Pipeline-Übersicht
`/buchhaltung/auto-pipeline/`

Zeigt:
- Aktueller Status `SEPA_AUTOPILOT_AKTIV`
- Nächster geplanter Lauf (Datum + Zeit)
- Anzahl Objekte mit `auto_pipeline_aktiv=True`
- Letzte 10 Läufe (Status, Objekt, Periode, Summe, Datei-Pfad)

### 12.2 Auto-Lauf-Protokoll Detail
`/buchhaltung/auto-pipeline/protokoll/{id}/`

Zeigt einen `AutoLaufProtokoll`-Eintrag mit:
- Verlinkung Sollstellungslauf + Lastschriftlauf
- Liste Warnungen mit Sprung zur Frontoffice-Aufgabe
- Datei-Pfad mit „Im Explorer anzeigen"-Button (Windows-Shell-Aufruf)

### 12.3 Objekt-Stammdaten — Auto-Pipeline-Konfig
Bestehender Objekt-Edit-View bekommt neuen Tab „Auto-Pipeline":
- Toggle `auto_pipeline_aktiv`
- Dropdown `bundesland` (ISO-Code, vorausgewählt aus Adresse wenn möglich)
- Read-only: Anzeige der letzten Auto-Läufe für dieses Objekt

---

## 13. Akzeptanzkriterien (Smoke-Test vor Go-Live)

Manuelle End-to-End-Tests mit Test-Mandant:

1. **Stichtag-Logik:** Task am 24. ausführen → kein Lauf. Am 25.
   ausführen → Lauf für Folgemonat. Am 26. (wenn 25. ausgesetzt
   wurde) → Nachhol-Lauf mit Warnung `sepa_frist_unterschritten` wenn
   nötig.
2. **Vollständiger Lauf:** Objekt mit 5 EVs, alle RCUR-Mandate, alle
   IBAN gepflegt → Sollstellungslauf erzeugt (5 Sollstellungen mit
   Splits), pain.008 mit 5–10 Positionen geschrieben (je nach
   Rücklagenkonten), Datei im Ablageordner mit korrektem Namen,
   `AutoLaufProtokoll(status='erfolg')`.
3. **Gemischter Lauf:** 3 EVs RCUR mit IBAN, 1 EV ohne SEPA-Mandat,
   1 EV mit FRST-Mandat → 5 Sollstellungen erzeugt, 3 in pain.008,
   2 Frontoffice-Aufgaben angelegt, `status='teilweise_erfolg'`.
4. **Idempotenz:** Task zweimal am gleichen Stichtag laufen lassen →
   Zweiter Aufruf erzeugt `AutoLaufProtokoll(status='uebersprungen')`,
   keine doppelten Sollstellungen, keine doppelte Datei.
5. **Notausschalter `.env`:** `SEPA_AUTOPILOT_AKTIV=false` →
   Task läuft, returned sofort.
6. **Objekt-Switch:** Ein Objekt mit `auto_pipeline_aktiv=False` →
   übersprungen, kein Protokoll-Eintrag.
7. **SEPA-Frist-Verschiebung:** Task am 31. März für Fälligkeit
   01. April starten (RCUR-Frist 2 BD unterschritten wenn 31. ein
   Freitag, weil Wochenende dazwischen) → Fälligkeit wird auf nächsten
   gültigen BD verschoben, Warnung erzeugt, Lauf läuft.
8. **Datei-Pfad nicht erreichbar:** `SEPA_OUTPUT_DIR` auf nicht
   existenten UNC-Pfad setzen → Lauf rollbacken (keine Sollstellungen
   im Nebenbuch!), `AutoLaufProtokoll(status='fehler')` mit Stack-Trace.
9. **Bundesland-Feiertage:** Lauf in HE testen am 31.10. (in HE kein
   Feiertag), Lauf in BY am 01.11. (Allerheiligen) — Bankarbeitstag-
   Logik berücksichtigt Bundesland korrekt.
10. **Audit-Sichtbarkeit:** Auto-erzeugte Sollstellung im
    Buchungsjournal öffnen → `erstellt_von` zeigt „IMMOCORE-Autopilot"
    mit Roboter-Icon, Verlinkung zum `AutoLaufProtokoll`-Eintrag.

Wenn alle 10 Punkte grün sind, ist diese Spec implementierungs-vollständig.

---

## 14. Schnittstellen zu anderen Specs

### 14.1 Mahnwesen-Spec
Auto-Pipeline berührt das Mahnwesen nicht direkt. Auto-erzeugte
Sollstellungen werden wie manuelle gemahnt.

### 14.2 Sammeltransfer (Hausgeld/Nebenbuch Kap. 7.4)
Beide Tasks sind unabhängig und laufen zu unterschiedlichen Zeitpunkten
(Sammeltransfer am Monatsende, Auto-Pipeline am 25. des Vormonats).

### 14.3 Eigentümerwechsel
Wenn ein Eigentümerwechsel zwischen Stichtag (25.03.) und Periode
(01.04.) erfolgt, kann die bereits erzeugte Sollstellung auf den alten
Eigentümer lauten. **Empfehlung:** Im Verkauf-Workflow den Verwalter
warnen: „Es existiert bereits eine Auto-Sollstellung für 04/2026 auf
den Voreigentümer — bitte manuell anpassen." Dies wird in der
Eigentümerwechsel-Spec ergänzt.

---

## 15. Aufgaben für Claude Code

> **Hinweis an Claude Code:** Arbeite die Phasen in dieser Reihenfolge
> ab. Phase B darf erst beginnen, wenn Phase A komplett durch ist und
> Patrik den **manuellen E2E-Smoke-Test 1–3** aus Kap. 13 bestätigt hat.
> Alle Geschäftslogik **ausschließlich** in `services/` — nie in Views,
> Tasks oder Models. Keine Datenbank-Änderungen ohne Migration.

### Phase A — Backend-Grundlagen

**Schritt A1: System-User-Migration**
Datei: `apps/accounts/migrations/000X_immocore_autopilot_user.py`. Legt
den System-User „IMMOCORE-Autopilot" mit UUID aus
`settings.SEPA_AUTOPILOT_USER_ID` an. `set_unusable_password()`.

**Schritt A2: Modell-Erweiterungen**
- `objekt.auto_pipeline_aktiv` (Boolean, Default True)
- `objekt.bundesland` (CharField(2), Default 'HE')
- `HausgeldSollstellungslauf.lauf_quelle` (Enum, Default 'manuell')
- `Lastschriftlauf.lauf_quelle` (Enum, Default 'manuell')
- `Lastschriftlauf.datei_pfad` (CharField(500), nullable)
- Unique-Constraint `unique_commited_lauf_pro_periode_quelle`
- Migration mit `makemigrations` + Review

**Schritt A3: Modell `AutoLaufProtokoll`**
Datei: `apps/buchhaltung/models/auto_pipeline.py`. Felder gemäß Kap. 6.3.
Read-only-Schutz im Admin und Service-Layer.

**Schritt A4: Service `sepa_fristen_service.py`**
Datei: `apps/buchhaltung/services/sepa_fristen_service.py`. Funktionen
aus Kap. 9.5. Library `holidays` zu `requirements.txt` ergänzen.

**Schritt A5: Service `auto_pipeline_service.py`**
Datei: `apps/buchhaltung/services/auto_pipeline_service.py`. Funktion
`run_objekt(objekt, periode, user)` gemäß Kap. 9.2 plus Helfer
`_filtere_lastschrift_kandidaten` und `_schreibe_pain008_datei`.

**Schritt A6: Erweiterung bestehender Services**
- `run_hausgeld_monat`: Parameter `skip_freigabe: bool = False` und
  `lauf_quelle: str = 'manuell'` hinzufügen. Wenn `skip_freigabe=True`,
  Status-Lebenszyklus `vorschau → freigegeben → commited` in einem
  Schritt durchlaufen, ohne Vier-Augen-Check.
- `commite_lastschriftlauf`: Parameter `lauf_quelle` hinzufügen,
  Direktaufruf mit vorgegebenen Kandidaten erlauben.

**Schritt A7: Celery-Task**
Datei: `apps/buchhaltung/tasks/auto_hausgeld_pipeline.py`. Funktion
`task_auto_hausgeld_pipeline` gemäß Kap. 9.1. Eintrag im Celery-Beat-
Schedule.

**Schritt A8: Tests Phase A**
- Unit-Tests `sepa_fristen_service` (Bundeslandkalender, BD-Addition)
- Unit-Tests `auto_pipeline_service.run_objekt` mit allen Fehler-Pfaden
  aus Kap. 11
- Integration-Test: Task end-to-end mit Test-Objekt
- Idempotenz-Test (zweimal aufrufen)

🛑 **HARTER STOPP nach Phase A.**
Bitte Patrik bestätigen, dass die Smoke-Tests 1–3 manuell durchgespielt
wurden und die pain.008-Datei in einem Test-Ordner korrekt landet.
Erst danach Phase B.

### Phase B — Frontoffice-Integration

**Schritt B1: Warnungs-Typen registrieren**
Bestehendes Frontoffice-Aufgaben-Modell um neue `aufgabe_typ`-Werte
erweitern (Kap. 6.4).

**Schritt B2: Helfer `_erzeuge_frontoffice_aufgabe`**
Erzeugt aus Warnung einen Aufgaben-Eintrag mit Soft-Lock-Mechanismus
(Hausgeld/Nebenbuch-Spec Kap. 10 Frontoffice-Vorschlag).

### Phase C — UI

**Schritt C1: Views Auto-Pipeline-Übersicht** (Kap. 12.1)
**Schritt C2: Protokoll-Detail** (Kap. 12.2)
**Schritt C3: Objekt-Konfig-Tab** (Kap. 12.3)

### Phase D — Wartung

**Schritt D1: Archiv-Task**
Datei: `apps/buchhaltung/tasks/archiv.py`. Funktion gemäß Kap. 10.5.
Wöchentliches Schedule.

### Phase E — Verifikation

**Schritt E1:** Akzeptanztests 1–10 aus Kap. 13 vollständig durchgehen.

---

**Ende der Spezifikation.**
