# IMMOCORE — Auto-Pipeline Hausgeld-Sollstellung & SEPA-Lastschrift

**Version:** v1.1 (konsolidiert)
**Status:** 🟢 Implementierungsreif
**Ersetzt:** v1.0 vollständig
**Bezug:** Erweitert `CLAUDE_CODE_ANLEITUNG_HAUSGELD_NEBENBUCH_v1_1.md`
**Greenfield-Annahme:** IMMOCORE noch nicht im Produktivbetrieb.

---

## Änderungsverzeichnis gegenüber v1.0

Diese Spec konsolidiert die folgenden Klarstellungen, die während der
Implementierung von v1.0 entstanden sind:

| Bereich | v1.0 (alt) | v1.1 (neu) |
|---|---|---|
| App-Zuordnung System-User-Migration | `apps/accounts/migrations/` | `apps/buchhaltung/migrations/` (kein neues App, `auth.User` wird direkt verwendet) |
| `SEPAMandat.sequence_type` | Verwendet, aber Anlage nicht erwähnt | Wird in Schritt A2 explizit am `SEPAMandat`-Modell angelegt (CharField, choices FRST/RCUR, default RCUR) |
| `_erzeuge_frontoffice_aufgabe` | Voll-Implementierung in Phase A | In Phase A als **Log-Stub**; volle Implementierung in Phase B |
| `Person.einzugs_iban()` | Methodenaufruf | **Methode existiert nicht**; IBAN wird aus `Person.ibans` (JSONField) bzw. `SEPAMandat.iban` gelesen |
| `objekt.objekt_nr` | Verwendet | **Existiert nicht**; verwende `objekt.bezeichnung` bzw. `objekt.kurzbezeichnung` (siehe Hausgeld/Nebenbuch-Spec Schritt 4) |

---

## 1. Zweck

Diese Spec automatisiert den monatlich wiederkehrenden Vorgang
**Hausgeld-Sollstellung erzeugen → SEPA-Lastschriftdatei (pain.008)
ableiten → in Ablageordner schreiben**.

Bisher (Hausgeld/Nebenbuch-Spec v1.1) wird beides manuell je Objekt
über UI-Wizards mit Vier-Augen-Prinzip ausgelöst. Bei einem Bestand von
N Objekten ergibt das N×2 Wizard-Durchläufe pro Monat — purer
mechanischer Aufwand ohne sachlichen Mehrwert.

Die Automatisierung greift **vor** dem Banking-Tool. IMMOCORE schreibt
die pain.008 in einen Ordner; Windata-Import bleibt manueller
Vier-Augen-Schritt.

## 2. Architekturprinzipien (was sich NICHT ändert)

| Prinzip | Verhalten |
|---|---|
| GoBD-Unwiderruflichkeit | Auto-erzeugte Sollstellungen sind nicht unterscheidbar von manuell erzeugten — gleiche Modelle, gleiche OPOS-Nr.-Vergabe, gleiche Storno-Regeln |
| Idempotenz | `run_hausgeld_monat` bleibt idempotent über bestehenden Unique-Constraint |
| Service-Wiederverwendung | Auto-Pipeline ruft `sollstellungslauf_service.run_hausgeld_monat` und `sepa_lastschrift_service.commite_lastschriftlauf` auf — keine Parallel-Implementierung |
| Manuelle Läufe weiterhin möglich | Bestehende UI-Wizards bleiben erhalten |

## 3. Annahmen

| Nr. | Annahme | Konsequenz bei Verletzung |
|---|---|---|
| A1 | Alle SEPA-Mandate sind `sequence_type=RCUR`. Demme hat nur RCUR. | Auto-Pipeline filtert FRST-Mandate explizit aus und meldet sie als Frontoffice-Aufgabe. Manueller Lauf für FRST. |
| A2 | Demme reicht pain.008 manuell über **Windata** ein. Vier-Augen-Prüfung liegt in Windata. | Falls Wechsel auf EBICS-Watcher: globaler Kill-Switch `SEPA_AUTOPILOT_AKTIV=false` setzen und Spec neu evaluieren. |
| A3 | Pro Objekt existiert genau **ein** Hausgeld-Lastschriftlauf pro Monat. | Wird über Constraint verhindert. |
| A4 | `auto_pipeline_aktiv` default = `True` für neue Objekte. | Manuelles Opt-out je Objekt möglich. |

---

## 4. Konfiguration

### 4.1 `.env`-Variablen

```env
SEPA_AUTOPILOT_AKTIV=true
SEPA_AUTOPILOT_STICHTAG=25
SEPA_AUTOPILOT_USER_ID=00000000-0000-0000-0000-000000000001
SEPA_OUTPUT_DIR=\\demme-server\sepa\out
SEPA_OUTPUT_ARCHIVE_DIR=\\demme-server\sepa\archive
SEPA_AUTOPILOT_VORLAUF_BD=5
```

### 4.2 Objekt-Flags

| Feld | Typ | Default | Anmerkung |
|---|---|---|---|
| `objekt.auto_pipeline_aktiv` | Boolean | `True` | Pro-Objekt-Notbremse |
| `objekt.bundesland` | CharField(2) | `'HE'` (Demme-Default) | ISO-3166-2 Code; für Bankfeiertage |

### 4.3 System-User

Datenmigration legt einmalig einen User an. **Migrations-App: `buchhaltung`**
(kein neues `accounts`-App, da Django `auth.User` direkt verwendet wird).

```python
# apps/buchhaltung/migrations/0XXX_autopilot_user.py
def create_autopilot_user(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    user = User.objects.create(
        id=settings.SEPA_AUTOPILOT_USER_ID,
        username='immocore-autopilot',
        first_name='IMMOCORE',
        last_name='Autopilot',
        email='autopilot@noreply.immocore.local',
        is_active=True,
        is_staff=False,
        is_superuser=False,
    )
    user.set_unusable_password()
    user.save()

def delete_autopilot_user(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    User.objects.filter(id=settings.SEPA_AUTOPILOT_USER_ID).delete()

class Migration(migrations.Migration):
    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('buchhaltung', '0XXX_vorherige_migration'),
    ]
    operations = [
        migrations.RunPython(create_autopilot_user, delete_autopilot_user),
    ]
```

User darf nicht für Login benutzbar sein (`set_unusable_password()`).
In allen Audit-Anzeigen mit speziellem Icon (Roboter-Symbol).

---

## 5. Datenmodell-Ergänzungen

### 5.1 `Objekt` (Erweiterung)

| Neues Feld | Typ | Anmerkung |
|---|---|---|
| `auto_pipeline_aktiv` | BooleanField, default=True | |
| `bundesland` | CharField(2), default='HE' | ISO-3166-2 |

### 5.2 `SEPAMandat` (Erweiterung — NEU in v1.1)

| Neues Feld | Typ | Anmerkung |
|---|---|---|
| `sequence_type` | CharField(4), choices=`[('FRST','FRST'),('RCUR','RCUR')]`, default='RCUR' | Lastschrift-Sequenz-Typ. Default = RCUR, weil Demme nur RCUR-Mandate führt. |

**Hinweis:** Auch wenn Annahme A1 sagt, dass FRST nicht vorkommt, wird
das Feld trotzdem angelegt, damit die Filter-Logik in
`_filtere_lastschrift_kandidaten` korrekt arbeiten kann und zukünftige
FRST-Mandate (z.B. bei Bestandsübernahme aus anderen Verwaltungen)
ohne weitere Migration unterstützt werden.

### 5.3 `HausgeldSollstellungslauf` (Erweiterung)

| Neues Feld | Typ | Default | Anmerkung |
|---|---|---|---|
| `lauf_quelle` | CharField, choices=`[('manuell','manuell'),('autopilot','autopilot')]` | `manuell` | Diskriminator |

### 5.4 `Lastschriftlauf` (Erweiterung)

| Neues Feld | Typ | Default | Anmerkung |
|---|---|---|---|
| `lauf_quelle` | CharField (siehe oben) | `manuell` | |
| `datei_pfad` | CharField(500), nullable | `None` | Absoluter Pfad der erzeugten pain.008-Datei |

### 5.5 Neue Tabelle `AutoLaufProtokoll`

GoBD-Audit-Tabelle. Ein Eintrag pro Auto-Pipeline-Aufruf je Objekt.

| Feld | Typ | Anmerkung |
|---|---|---|
| `id` | UUID (PK) | |
| `objekt` | FK → Objekt | |
| `ausgefuehrt_am` | DateTimeField | Zeitpunkt des Task-Starts |
| `periode` | DateField | Zielperiode |
| `status` | CharField, choices=`[('erfolg','erfolg'),('teilweise_erfolg','teilweise_erfolg'),('fehler','fehler'),('uebersprungen','uebersprungen')]` | |
| `sollstellungslauf` | FK → HausgeldSollstellungslauf, nullable | |
| `lastschriftlauf` | FK → Lastschriftlauf, nullable | |
| `anzahl_evs_geplant` | IntegerField | |
| `anzahl_evs_erfolgreich` | IntegerField | |
| `anzahl_evs_uebersprungen` | IntegerField | |
| `summe_sollstellungen` | DecimalField(14,2) | |
| `summe_lastschrift` | DecimalField(14,2) | |
| `datei_pfad` | CharField(500), nullable | |
| `warnungen` | JSONField | Liste `[{ev_id, name, einheit, warnung_typ, nachricht}]` |
| `fehler` | TextField, nullable | Stack-Trace bei `status='fehler'` |

Read-only nach Erstellung. Niemals löschen.

### 5.6 Idempotenz-Constraint

Auf `Lastschriftlauf` neuer Partial-Unique-Constraint (Migration):

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

### 5.7 Frontoffice-Aufgaben-Typen (Phase B)

Bestehendes Frontoffice-Aufgaben-Modell wird in Phase B um folgende
`aufgabe_typ`-Werte erweitert:

| Warnungstyp | Beispieltext |
|---|---|
| `kein_sepa_mandat` | „Auto-Pipeline: SEPA-Mandat fehlt für {Name}, {Einheit}. EV aus Lastschriftlauf ausgeschlossen — bitte Mandat anfordern." |
| `keine_iban` | „Auto-Pipeline: Keine IBAN hinterlegt für {Name}, {Einheit}." |
| `keine_hausgeldhistorie` | „Auto-Pipeline: Kein Hausgeldsatz in der Historie für {Name}, {Einheit} (Stichtag {Datum})." |
| `mandat_typ_frst` | „Auto-Pipeline: FRST-Mandat bei {Name}, {Einheit} — manuelle Lastschrift nötig." |
| `sepa_frist_unterschritten` | „Auto-Pipeline: Lauf zu spät gestartet, Fälligkeit musste auf {Datum} verschoben werden." |
| `dateischreibfehler` | „Auto-Pipeline: pain.008-Datei konnte nicht geschrieben werden — Pfad nicht erreichbar." |

In Phase A werden diese Warnungen **nur ins Log** geschrieben
(siehe Kap. 8.4).

---

## 6. Celery-Beat-Schedule

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

**Warum täglich?** Robustheit gegen Container-Ausfälle. Der Task prüft
jeden Tag „bin ich heute der Stichtag?" — wenn nein, sofort `return`.
Bei Server-Ausfall am Stichtag fängt der Folgetag den Lauf nach.

---

## 7. Service-Architektur

### 7.1 Neue Module

```
apps/buchhaltung/services/
├── auto_pipeline_service.py      # NEU — Orchestrierung
└── sepa_fristen_service.py       # NEU — Bankarbeitstags-Logik

apps/buchhaltung/tasks/
└── auto_hausgeld_pipeline.py     # NEU — Celery-Task-Wrapper
```

### 7.2 Aufgabenverteilung

| Service / Task | Zuständigkeit |
|---|---|
| `task_auto_hausgeld_pipeline` | Celery-Eintrag; prüft Stichtag, iteriert über alle Objekte mit `auto_pipeline_aktiv=True` |
| `auto_pipeline_service.run_objekt(objekt, periode, user)` | Orchestrierung pro Objekt |
| `sepa_fristen_service.naechster_einreichungstag(stichtag, faelligkeit, bundesland)` | Bankarbeitstags-Berechnung |
| `sepa_fristen_service.ist_bankarbeitstag(datum, bundesland)` | Helfer |

---

## 8. Pseudocode

### 8.1 `task_auto_hausgeld_pipeline`

```python
@shared_task(bind=True, max_retries=0)
def task_auto_hausgeld_pipeline(self):
    """Täglich 02:00 Uhr. Prüft, ob heute der konfigurierte Stichtag ist."""
    if not settings.SEPA_AUTOPILOT_AKTIV:
        logger.info("Auto-Pipeline deaktiviert (.env-Switch)")
        return

    heute = timezone.localdate()
    if not ist_stichtag_oder_nachholtag(heute):
        return

    periode = naechste_periode(heute)
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
            logger.exception(f"Auto-Pipeline {objekt.bezeichnung} fehlgeschlagen")
            AutoLaufProtokoll.objects.create(
                objekt=objekt,
                periode=periode,
                status='fehler',
                fehler=traceback.format_exc(),
            )
```

### 8.2 `auto_pipeline_service.run_objekt`

```python
@transaction.atomic
def run_objekt(objekt, periode: date, user) -> AutoLaufProtokoll:
    """Atomarer Lauf pro Objekt."""

    # 1. Idempotenz
    existierender_lauf = HausgeldSollstellungslauf.objects.filter(
        objekt=objekt,
        periode=periode,
        lauf_quelle='autopilot',
        status='commited',
    ).first()
    if existierender_lauf:
        return _protokoll_uebersprungen(objekt, periode, existierender_lauf)

    warnungen = []

    # 2. Sollstellungslauf (bestehender Service)
    sollstellungslauf = run_hausgeld_monat(
        objekt=objekt,
        periode=periode,
        erstellt_von=user,
        skip_freigabe=True,
        lauf_quelle='autopilot',
    )

    # 3. EVs für Lastschrift filtern
    kandidaten, ausgeschlossen = _filtere_lastschrift_kandidaten(sollstellungslauf)
    for eintrag in ausgeschlossen:
        warnungen.append(eintrag)
        _erzeuge_frontoffice_aufgabe(objekt, eintrag)

    if not kandidaten:
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

    # 5. Lastschriftlauf (bestehender Service)
    lastschriftlauf = commite_lastschriftlauf(
        objekt=objekt,
        stichtag=faelligkeit,
        kandidaten=kandidaten,
        user=user,
        lauf_quelle='autopilot',
    )

    # 6. pain.008-XML
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

### 8.3 `_filtere_lastschrift_kandidaten`

```python
def _filtere_lastschrift_kandidaten(sollstellungslauf):
    """
    Filtert aus allen Sollstellungen des Laufs die EVs heraus, die
    NICHT per Lastschrift einziehbar sind.

    Wichtig: Person.sepa_mandat ist die Single Source of Truth für
    die Einzugs-IBAN. Falls SEPAMandat.iban nicht gesetzt ist, ist
    der EV nicht einziehbar.
    """
    kandidaten = []
    ausgeschlossen = []

    for sollstellung in sollstellungslauf.sollstellungen.filter(sollstellungs_typ='hausgeld'):
        ev = sollstellung.eigentumsverhaeltnis
        person = ev.person

        # SEPA-Mandat-Check
        if not person.sepa_mandat:
            ausgeschlossen.append({
                'ev_id': str(ev.id),
                'name': _person_anzeigename(person),
                'einheit': ev.einheit.einheit_nr,
                'warnung_typ': 'kein_sepa_mandat',
                'nachricht': f'{_person_anzeigename(person)}: SEPA-Mandat fehlt',
            })
            continue

        # FRST-Filter (siehe Annahme A1)
        if person.sepa_mandat.sequence_type != 'RCUR':
            ausgeschlossen.append({
                'ev_id': str(ev.id),
                'name': _person_anzeigename(person),
                'einheit': ev.einheit.einheit_nr,
                'warnung_typ': 'mandat_typ_frst',
                'nachricht': f'{_person_anzeigename(person)}: FRST-Mandat, manuelle Lastschrift nötig',
            })
            continue

        # IBAN-Check (aus SEPAMandat.iban, nicht aus Person.ibans)
        if not person.sepa_mandat.iban:
            ausgeschlossen.append({
                'ev_id': str(ev.id),
                'name': _person_anzeigename(person),
                'einheit': ev.einheit.einheit_nr,
                'warnung_typ': 'keine_iban',
                'nachricht': f'{_person_anzeigename(person)}: Keine IBAN am SEPA-Mandat',
            })
            continue

        kandidaten.append(sollstellung)

    return kandidaten, ausgeschlossen


def _person_anzeigename(person) -> str:
    """
    Helfer zur einheitlichen Namensanzeige.
    Person hat: ist_firma, vorname, nachname, firmenname.
    """
    if person.ist_firma:
        return person.firmenname or ''
    return f"{person.vorname} {person.nachname}".strip()
```

### 8.4 `_erzeuge_frontoffice_aufgabe` — Phase-A-Stub

**In Phase A nur Log-Ausgabe:**

```python
def _erzeuge_frontoffice_aufgabe(objekt, warnung_eintrag):
    """
    Phase-A-Stub: schreibt nur einen Log-Eintrag.
    Phase B ersetzt den Body durch echte Frontoffice-Aufgaben-Erzeugung.
    Signatur bleibt unverändert.
    """
    logger.warning(
        "Frontoffice-Aufgabe (Phase B noch nicht aktiv): "
        "objekt=%s warnung_typ=%s nachricht=%s",
        objekt.bezeichnung,
        warnung_eintrag.get('warnung_typ'),
        warnung_eintrag.get('nachricht'),
    )
```

**Wichtig:** Das `warnungen`-Array, das ins `AutoLaufProtokoll.warnungen`
geschrieben wird, ist auch in Phase A vollständig. Nur die DB-seitige
Aufgaben-Erzeugung fehlt.

### 8.5 `_schreibe_pain008_datei`

```python
def _schreibe_pain008_datei(xml, objekt, periode, lauf) -> str:
    """
    Schreibt pain.008 in SEPA_OUTPUT_DIR. UNC-Pfad-tauglich.
    Atomares Schreiben via Temp-File + Rename.

    Dateinamen-Schema:
      {JJJJ-MM-TT}_{kurzbez_safe}_LS_{JJJJ-MM}.xml
    Beispiel: 2026-03-25_Coventrystr32_LS_2026-04.xml

    objekt.kurzbezeichnung wird sanitized (keine Sonderzeichen, max 30 Zeichen).
    Falls kurzbezeichnung leer: objekt.bezeichnung verwenden.
    """
    kurzbez = (objekt.kurzbezeichnung or objekt.bezeichnung or 'Objekt')
    kurzbez_safe = _sanitize_filename(kurzbez)[:30]

    dateiname = (
        f'{timezone.localdate().isoformat()}_'
        f'{kurzbez_safe}_LS_'
        f'{periode.strftime("%Y-%m")}.xml'
    )

    zielordner = Path(settings.SEPA_OUTPUT_DIR)
    zielordner.mkdir(parents=True, exist_ok=True)
    ziel_pfad = zielordner / dateiname

    # Bei Kollision: _v2, _v3 ...
    counter = 2
    while ziel_pfad.exists():
        dateiname_v = dateiname.replace('.xml', f'_v{counter}.xml')
        ziel_pfad = zielordner / dateiname_v
        counter += 1

    temp_pfad = ziel_pfad.with_suffix(ziel_pfad.suffix + '.tmp')
    temp_pfad.write_text(xml, encoding='utf-8')
    temp_pfad.rename(ziel_pfad)

    logger.info(f'pain.008 geschrieben: {ziel_pfad}')
    return str(ziel_pfad)


def _sanitize_filename(s: str) -> str:
    """Ersetzt alle Nicht-ASCII-Alphanumerischen Zeichen durch nichts."""
    import re
    return re.sub(r'[^a-zA-Z0-9]+', '', s)
```

### 8.6 `sepa_fristen_service.naechster_einreichungstag`

```python
def naechster_einreichungstag(
    stichtag: date,
    soll_faelligkeit: date,
    bundesland: str,
) -> date:
    """
    SEPA-Regel RCUR: Einreichung mindestens 2 BD vor Fälligkeit.
    Wir nehmen Vorlauf SEPA_AUTOPILOT_VORLAUF_BD (default 5).
    """
    benoetigt_bd = settings.SEPA_AUTOPILOT_VORLAUF_BD
    frueheste_faelligkeit = bd_addieren(stichtag, benoetigt_bd, bundesland)

    return max(frueheste_faelligkeit, soll_faelligkeit)


def bd_addieren(start: date, anzahl_bd: int, bundesland: str) -> date:
    """Addiert N Bankarbeitstage."""
    kalender = _bankarbeitstag_kalender(bundesland)
    current = start
    addiert = 0
    while addiert < anzahl_bd:
        current += timedelta(days=1)
        if current.weekday() < 5 and current not in kalender:
            addiert += 1
    return current


@functools.lru_cache(maxsize=64)
def _bankarbeitstag_kalender(bundesland: str):
    """Cache pro Bundesland. Nutzt holidays-Library."""
    import holidays
    return holidays.Germany(state=bundesland, years=range(2024, 2030))
```

---

## 9. Idempotenz, Concurrency, Datei-Konflikte

### 9.1 Idempotenz auf Sollstellungs-Ebene
Bleibt unverändert: bestehender Unique-Constraint.

### 9.2 Idempotenz auf Lauf-Ebene
Partial-Unique-Constraint (siehe Kap. 5.6).

### 9.3 Datei-Konflikt
Bei existierender Zieldatei: Suffix `_v2`, `_v3` (siehe Kap. 8.5).

### 9.4 Concurrency
Celery-Beat garantiert, dass nur ein Worker den Task übernimmt.
Innerhalb `run_objekt` sequentiell.

### 9.5 Archiv-Job

```python
@shared_task
def task_archiviere_alte_pain_dateien():
    """Verschiebt pain.008 älter als 90 Tage nach SEPA_OUTPUT_ARCHIVE_DIR. Wöchentlich."""
```

---

## 10. Fehlerbehandlung — Zusammenfassung

| Fehler | Verhalten |
|---|---|
| `.env`-Switch aus | Task startet, returned sofort |
| Heute nicht Stichtag | Task startet, returned sofort |
| Objekt `auto_pipeline_aktiv=False` | Objekt überspringen |
| EV ohne SEPA-Mandat | EV überspringen, Frontoffice-Warnung |
| EV mit FRST-Mandat | EV überspringen, Frontoffice-Warnung |
| EV ohne IBAN am SEPA-Mandat | EV überspringen, Frontoffice-Warnung |
| EV ohne HausgeldHistorie | Sollstellungs-Service überspringt (Soll-Summe=0) |
| SEPA-Frist unterschritten | Fälligkeit verschieben, Warnung |
| `SEPA_OUTPUT_DIR` nicht erreichbar | Rollback gesamter Objekt-Lauf, Protokoll-Eintrag, Alarm |
| Bestehender commited Auto-Lauf | Lauf überspringen (Idempotenz) |
| Sollstellung erfolgreich, Lastschrift fehlgeschlagen | Sollstellung bleibt (Forderung steht!), Protokoll `teilweise_erfolg` |
| Unerwartete Exception | Stack-Trace in `fehler`-Feld, `status='fehler'`, Admin-Mail |

---

## 11. UI-Anforderungen (Phase C)

### 11.1 Auto-Pipeline-Übersicht
`/buchhaltung/auto-pipeline/` — Status, nächster Lauf, letzte 10 Läufe

### 11.2 Auto-Lauf-Protokoll Detail
`/buchhaltung/auto-pipeline/protokoll/{id}/`

### 11.3 Objekt-Stammdaten — Auto-Pipeline-Konfig
Neuer Tab im Objekt-Edit-View.

---

## 12. Akzeptanzkriterien (Smoke-Test)

1. **Stichtag-Logik:** Task am 24. ausführen → kein Lauf. Am 25. → Lauf für Folgemonat. Am 26. (Nachholtag) → Lauf mit Warnung.
2. **Vollständiger Lauf:** Objekt mit 5 EVs, alle RCUR, alle IBAN → 5 Sollstellungen, pain.008 mit 5–10 Positionen, Datei mit korrektem Namen, `status='erfolg'`.
3. **Gemischter Lauf:** 3 EVs RCUR mit IBAN, 1 EV ohne SEPA-Mandat, 1 EV mit FRST → 5 Sollstellungen, 3 in pain.008, 2 Frontoffice-Warnungen (Phase A: nur Log), `status='teilweise_erfolg'`.
4. **Idempotenz:** Task zweimal am gleichen Stichtag → zweiter Aufruf: `status='uebersprungen'`.
5. **Notausschalter `.env`:** `SEPA_AUTOPILOT_AKTIV=false` → Task läuft, returned sofort.
6. **Objekt-Switch:** Objekt mit `auto_pipeline_aktiv=False` → übersprungen.
7. **SEPA-Frist-Verschiebung:** Lauf zu spät → Fälligkeit verschoben, Warnung.
8. **Datei-Pfad nicht erreichbar:** → Rollback, `status='fehler'`.
9. **Bundesland-Feiertage:** Lauf in HE vs. BY um Allerheiligen-Datum.
10. **Audit-Sichtbarkeit:** Auto-erzeugte Sollstellung zeigt `erstellt_von='immocore-autopilot'` mit Roboter-Icon.

---

## 13. Schnittstellen zu anderen Specs

### 13.1 Sammeltransfer (Hausgeld/Nebenbuch Kap. 7.4)
Beide Tasks unabhängig.

### 13.2 Eigentümerwechsel
Bei Wechsel zwischen Stichtag und Periode kann Auto-Sollstellung auf den
Voreigentümer laufen → siehe Rückwirkender-Eigentümerwechsel-Spec.

### 13.3 Mahnwesen
Beim späteren Bau des Mahnwesens beachten: Mahn-Sperre für neutralisierte
Sollstellungen (siehe `docs/mahnwesen_pflicht_filter.md`, wird in
Schritt-2-Spec angelegt).

---

## 14. Aufgaben für Claude Code

> **Hinweis:** Phase A komplett abarbeiten, dann harter Stopp. Phasen B/C/D
> erst nach manuellem Smoke-Test 1-3.

### Phase A — Backend-Grundlagen

**A1: System-User-Migration**
Datei: `apps/buchhaltung/migrations/0XXX_autopilot_user.py`. Code aus Kap. 4.3.

**A2: Modell-Erweiterungen (eine Migration)**
- `Objekt.auto_pipeline_aktiv` (Bool, default True)
- `Objekt.bundesland` (CharField(2), default 'HE')
- `SEPAMandat.sequence_type` (CharField(4), choices FRST/RCUR, default RCUR) — **NEU in v1.1**
- `HausgeldSollstellungslauf.lauf_quelle`
- `Lastschriftlauf.lauf_quelle`
- `Lastschriftlauf.datei_pfad`
- Partial-Unique-Constraint aus Kap. 5.6

**A3: Modell `AutoLaufProtokoll`**
Datei: `apps/buchhaltung/models/auto_pipeline.py`. Felder Kap. 5.5.
Read-only-Schutz im Admin und Service.

**A4: Service `sepa_fristen_service.py`**
Datei: `apps/buchhaltung/services/sepa_fristen_service.py`. Funktionen
Kap. 8.6. `holidays` zu `requirements.txt`.

**A5: Service `auto_pipeline_service.py`**
Datei: `apps/buchhaltung/services/auto_pipeline_service.py`. Funktionen
aus Kap. 8.2, 8.3, 8.5 plus Helfer `_protokoll_uebersprungen`,
`_protokoll_teilerfolg_nur_sollstellung`.

`_erzeuge_frontoffice_aufgabe` wird als **Log-Stub** gemäß Kap. 8.4
implementiert.

**A6: Erweiterung bestehender Services**
- `run_hausgeld_monat`: Parameter `skip_freigabe: bool = False` und
  `lauf_quelle: str = 'manuell'`. Wenn `skip_freigabe=True`,
  Status-Lebenszyklus `vorschau → freigegeben → commited` ohne
  Vier-Augen.
- `commite_lastschriftlauf`: Parameter `lauf_quelle`, Direktaufruf mit
  Kandidaten erlauben.

**A7: Celery-Task**
Datei: `apps/buchhaltung/tasks/auto_hausgeld_pipeline.py`. Funktion
aus Kap. 8.1. Schedule-Eintrag.

**A8: Tests Phase A**
- Unit-Tests `sepa_fristen_service`
- Unit-Tests `auto_pipeline_service.run_objekt` für alle Fehler-Pfade
- Integration-Test end-to-end mit Test-Objekt
- Idempotenz-Test
- Smoke-Test 1-3 aus Kap. 12 manuell durchspielen

🛑 **HARTER STOPP nach Phase A.**

### Phase B — Frontoffice-Integration

**B1: Warnungs-Typen registrieren**
Frontoffice-Aufgaben-Modell um `aufgabe_typ`-Werte aus Kap. 5.7 erweitern.

**B2: `_erzeuge_frontoffice_aufgabe` voll implementieren**
Stub aus Phase A durch echte DB-Einträge ersetzen.

### Phase C — UI

**C1, C2, C3:** Views aus Kap. 11.

### Phase D — Wartung

**D1: Archiv-Task** Kap. 9.5.

### Phase E — Verifikation

**E1:** Smoke-Tests 1–10 vollständig.

---

**Ende der Spezifikation.**
