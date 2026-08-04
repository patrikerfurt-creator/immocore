# CLAUDE_CODE_ANLEITUNG_BELEG_DOKUMENT_KOPPLUNG_v1_0

**Modul:** Vereinheitlichung Rechnungs-Beleg ↔ DMS-Dokument
**Bezug:** IMMOCORE Ausgangsspezifikation Kap. 4.10 (`Dokument`, `Rechnung`), OP-Buchung-Spec v1.1
**Auftraggeber:** Demme Immobilien Verwaltung GmbH, Frankfurt am Main
**KI-Modell (Referenz):** claude-sonnet-4-6
**Status:** 🟡 Entwurf — Phase 0 (Ist-Verifikation) zwingend vor Umsetzung

---

## 0. Anpassung an Ist-Befunde (2026-08-03, freigegeben)

Phase 0 abgeschlossen (siehe `IST_BERICHT_BELEG_DOKUMENT.md`). Freigegebene Abweichungen vom ursprünglichen Spec-Text:

| Spec-Original | Verifizierter Ist-Stand / Beschluss |
|---|---|
| App `apps/dms` | App heißt `apps/dokumente`; Rechnung liegt in `apps/rechnungen` |
| `Dokument.datei` (Annahme) | bestätigt: `datei` (FileField, `upload_to='dokumente/'`) |
| Generische Verknüpfung (`verknuepfung_typ`+`verknuepfung_id`) | konkrete FKs `objekt`/`einheit` + `verknuepfung_typ` (CharField) |
| `Buchung.beleg` existiert | existiert NICHT (nur `belegnr`/`belegdatum`/`beleg_referenz`) |
| Alt-Datei-Feld an Rechnung | `pfad` (CharField, absolute Pfade `/app/rechnungen/…`), 154/154 live; `pdf_upload` ungenutzt |
| Storage S3/django-storages | lokales Dateisystem (MEDIA_ROOT); Phase C = reine Referenz-Übernahme |
| — | **E1-Beschluss (Option c):** `Rechnung.beleg_dokument` ist der einzige Kopplungsweg; Belegnummernkreis wandert als `Dokument.beleg_nummer` (Vergabe via bestehendem `BelegnummerZaehler` im Service, Phase B); Brückenmodel `Beleg` deprecated, Drop erst in v1_1 |
| `abgelegt_am` als Sperrzeitpunkt | `abgelegt_am` (auto_now_add) nur Ablagezeitpunkt; zusätzlich `revisionssicher_seit` (explizit gesetzt) |
| `Dokument.sha256` | NICHT unique (Duplikate real vorhanden), nur indiziert; Idempotenz über `beleg_dokument_id` |
| — | `Dokument.objekt`/`einheit`: `on_delete` CASCADE→PROTECT (GoBD: Cascade umgeht delete()-Sperre) |
| Sperr-Hook | nur in `rechnung_freigeben()` (rechnungen/services/rechnung_op_service.py); Views-Fallback `views.py:550` (Status ohne OP-Buchung) bleibt unverändert und ist als offener Bug dokumentiert |
| Phase C als Datenmigration (Abschnitt 6) | **Freigegeben 2026-08-03:** Management-Command `migriere_rechnungsbelege` (--dry-run/--limit/--sperren/--rueckabwicklung) — deploy.sh fährt `migrate --no-input` unbeaufsichtigt, Nummernvergabe braucht den echten `BelegnummerZaehler` |
| — | Phase-A-Nachtrag: `Dokument.ablage_wurzel` (media/rechnungen) + `datei` max_length 100→1000; Pfadauflösung NUR über `beleg_service.dokument_pfad()` |
| `hochgeladen_von` bei Migration | System-User `immocore-autopilot` (Fallback: erster Superuser), nicht `erfasst_von` |

---

## 1. Ziel & Kernentscheidung

Das Rechnungs-PDF ist konzeptionell ein DMS-Dokument. Statt einer zweiten,
parallelen Dateiablage am `Rechnung`-Model wird die **physische Datei genau
einmal** über das bestehende `Dokument`-Model geführt. `Rechnung` verweist per
`OneToOne` auf den zugehörigen Beleg.

**Bestätigte Architekturentscheidung:**

```
Rechnung.beleg_dokument  ──OneToOne──▶  Dokument  ──FK──▶  S3 (eine Ablage)
```

Folgen:
- Keine doppelte Dateiablage, kein zweiter Upload-Pfad.
- Rechnungs-Belege erscheinen automatisch im DMS-Objektfilter (Kategorie *Beleg/Rechnung*).
- GoBD-Belegprinzip: Beleg und Buchung bleiben über eine nachvollziehbare Referenz gekoppelt.

**Nicht Teil dieser Spec:** DMS-UI (Kategoriebaum, Volltext-Suche-Oberfläche,
dokumentbezogene Zugriffskontrolle), Beschluss-Modul, Mail-Intake-Anbindung.
Diese Spec liefert ausschließlich das **Datenfundament** und die
**GoBD-Revisionssicherheit**.

---

## 2. ⚠️ Phase 0 — Ist-Verifikation (HALT vor jeder Migration)

> **STOP.** Vor jeder Model- oder Datenänderung ist der reale Code zu prüfen.
> Die Projekt-Specs widersprechen sich in Details (siehe unten). Es gilt der
> Code, **nicht** die Spec. Ergebnis dieser Phase in einem kurzen Ist-Bericht
> festhalten und **auf Freigabe warten**, bevor Phase A startet.

Zu klären (Antworten aus dem tatsächlichen Quellcode, nicht aus Annahme):

| # | Frage | Fundort |
|---|---|---|
| V1 | Vollständige Feldliste des `Dokument`-Models. Gibt es bereits ein Datei-Feld? Wie heißt es (`datei`, `file`, `pfad`)? `FileField`/`CharField`? | `apps/**/models/dokument.py` |
| V2 | Wie ist die Objekt-/Einheit-Verlinkung im `Dokument`-Model realisiert — generische Relation (`verknuepfung_typ` + `verknuepfung_id`) oder konkrete FKs? | dito |
| V3 | Hat `Rechnung` bereits ein Datei-/PDF-Feld (z. B. `pdf_pfad`, `datei`, `scan`)? Wie viele Bestandsdatensätze haben dort einen nicht-leeren Wert? | `apps/buchhaltung/models/rechnung.py` + DB-Query |
| V4 | Führt `Rechnung` das Objekt als `objekt` (FK→Objekt) **oder** als `weg` (FK→WEG)? Ist `kreditor` FK→`Person` oder FK→`Kreditor`? | dito |
| V5 | Existiert am `Rechnung`-Model bereits ein Feld namens `beleg`? (Kollisionsprüfung — `Buchung.beleg` existiert bereits als generische Referenz.) | dito |
| V6 | Storage-Backend: schon S3/`django-storages` aktiv, oder noch lokal? Welcher `Storage` ist am Datei-Feld gebunden? | `settings/*.py`, Model-Feld |
| V7 | Welche Status-Werte hat der Rechnungs-Lifecycle real (`eingegangen`/`erfasst`, …, `gebucht`, `bezahlt`)? Ab welchem Status gilt die Rechnung als **gebucht**? | Model / Konstanten |

**Ergebnis-Artefakt:** `IST_BERICHT_BELEG_DOKUMENT.md` mit den V1–V7-Befunden.
→ **HALT. Freigabe abwarten.**

---

## 3. Datenmodell-Änderungen

> Die konkreten Feldnamen unten sind **an die V1–V5-Befunde anzupassen**.
> Wo diese Spec `Dokument.datei` schreibt, ist das reale Datei-Feld gemeint.

### 3.1 `Dokument` — Erweiterung um Belegtyp & Revisionssicherheit

Neue Felder (nur ergänzen, bestehende nicht anfassen):

| Feld | Typ | Default | Anmerkung |
|---|---|---|---|
| `dokument_typ` | Enum: `beleg` │ `vertrag` │ `korrespondenz` │ `beschluss` │ `abrechnung` │ `sonstiges` | `sonstiges` | Grobklassifikation. Rechnungs-Belege → `beleg`. |
| `revisionssicher` | Boolean | `False` | `True` sperrt Löschen und Datei-Austausch (GoBD). |
| `sha256` | CharField(64), nullable | `None` | Hash des Dateiinhalts bei Ablage. Integritätsnachweis + Duplikaterkennung. |
| `abgelegt_am` | DateTimeField (`auto_now_add`) | — | Zeitpunkt der revisionssicheren Ablage. |

Migration: additiv, `default`-Werte gesetzt → keine Datenmigration für Bestand nötig
(Bestand bleibt `dokument_typ='sonstiges'`, `revisionssicher=False`).

### 3.2 `Rechnung` — Kopplung an den Beleg

| Feld | Typ | Anmerkung |
|---|---|---|
| `beleg_dokument` | `OneToOneField(Dokument, on_delete=PROTECT, null=True, blank=True, related_name='rechnung')` | Verweis auf das physische PDF. `PROTECT`: Beleg-Dokument kann nicht gelöscht werden, solange eine Rechnung darauf zeigt. |

**Begründung Feldname:** `beleg` ist bereits durch `Buchung.beleg` (generische
Quell-Referenz) belegt. `beleg_dokument` vermeidet die Kollision und ist eindeutig.

**`null=True` bewusst:** Übergangszustand für Migration (Phase C) und für
Rechnungen ohne PDF (z. B. rein manuelle Erfassung ohne Scan). Fachliche
Pflicht („kein Buchen ohne Beleg") wird **im Service** erzwungen, nicht per
DB-`NOT NULL` — sonst blockiert die Migration.

---

## 4. Phase A — Model & Migration (Schema)

1. `Dokument` um die vier Felder aus 3.1 erweitern. Schema-Migration erzeugen.
2. `Rechnung.beleg_dokument` gemäß 3.2 ergänzen. Schema-Migration erzeugen.
3. **Keine** Datenmigration in dieser Phase.
4. `makemigrations` + `migrate` gegen eine Kopie der Produktions-DB testen.

**Smoke-Test A:**
- `Dokument`-Instanz mit `dokument_typ='beleg'`, `revisionssicher=True` anlegen → ok.
- `Rechnung` anlegen, `beleg_dokument` leer lassen → ok (kein DB-Fehler).
- `Rechnung.beleg_dokument = dok; rechnung.save()` → Zugriff `dok.rechnung` liefert die Rechnung.

→ **HALT vor Phase B.**

---

## 5. Phase B — Service: Beleg-Ablage & GoBD-Sperre

Alle Logik in `services/`, nie in Views/Models. Eine Funktion, eine Aufgabe.

### 5.1 Beleg ablegen

Datei: `apps/dms/services/beleg_service.py`

```python
import hashlib
from django.db import transaction
from django.core.exceptions import ValidationError

@transaction.atomic
def lege_rechnungsbeleg_ab(rechnung, datei_bytes: bytes, dateiname: str,
                           objekt, hochgeladen_von) -> "Dokument":
    """
    Legt das Rechnungs-PDF EINMAL als Dokument ab und koppelt es an die
    Rechnung. Idempotenzschutz über sha256.
    """
    if rechnung.beleg_dokument_id:
        raise ValidationError("Rechnung hat bereits einen Beleg.")

    sha = hashlib.sha256(datei_bytes).hexdigest()

    dok = Dokument.objects.create(
        # Feldnamen gemäß V1/V2 anpassen:
        datei=_speichere_datei(datei_bytes, dateiname),   # S3 via django-storages
        kategorie="Beleg",
        dokument_typ="beleg",
        sha256=sha,
        revisionssicher=False,   # wird bei Buchung auf True gesetzt (5.3)
        # Verlinkung gemäß V2 (generisch ODER FK):
        verknuepfung_typ="objekt",
        verknuepfung_id=objekt.id,
        hochgeladen_von=hochgeladen_von,
    )
    rechnung.beleg_dokument = dok
    rechnung.save(update_fields=["beleg_dokument"])
    return dok
```

### 5.2 GoBD-Löschsperre (Model-Ebene)

Datei: `Dokument`-Model — `delete()` überschreiben:

```python
def delete(self, *args, **kwargs):
    if self.revisionssicher:
        raise ValidationError(
            "Revisionssicheres Dokument darf nicht gelöscht werden (GoBD)."
        )
    return super().delete(*args, **kwargs)
```

Ergänzend: Datei-Austausch bei `revisionssicher=True` verhindern (in `save()`
prüfen, ob sich das Datei-Feld gegenüber der DB-Version ändert → `ValidationError`).

### 5.3 Revisionssicherheit bei Buchung setzen

Der Beleg wird **unveränderlich, sobald die Rechnung gebucht ist**. Einhängen
in den bestehenden Freigabe-/Buchungs-Service (OP-Buchung-Spec, Punkt „gebucht"):

```python
# innerhalb rechnung_freigeben() bzw. beim Übergang -> 'gebucht':
if rechnung.beleg_dokument_id:
    dok = rechnung.beleg_dokument
    dok.revisionssicher = True
    dok.save(update_fields=["revisionssicher", "abgelegt_am"])
```

> **Genauer Zeitpunkt = Ergebnis von V7.** Sperre setzen, sobald die
> OP-Buchung entsteht (Status `freigegeben`/`gebucht`), nicht schon bei `erfasst`
> — sonst lässt sich ein fehlerhaft gescannter Beleg vor Buchung nicht mehr
> korrigieren.

**Smoke-Test B:**
- Beleg ablegen (nicht revisionssicher) → Löschen möglich.
- Rechnung buchen → Beleg `revisionssicher=True`.
- `dok.delete()` → `ValidationError`.
- Datei-Austausch bei revisionssicherem Dok → `ValidationError`.
- Zweite Ablage auf Rechnung mit Beleg → `ValidationError`.

→ **HALT vor Phase C.**

---

## 6. Phase C — Migration bestehender Rechnungs-PDFs (nur falls V3 = ja)

> Nur ausführen, wenn `Rechnung` real ein Alt-Datei-Feld hat (V3). Sonst Phase
> überspringen.

Datenmigration, **idempotent**, in `transaction.atomic()` je Datensatz:

```python
def migriere_alt_belege(apps, schema_editor):
    Rechnung = apps.get_model("buchhaltung", "Rechnung")
    Dokument = apps.get_model("dms", "Dokument")   # App-Label gemäß V1

    for r in Rechnung.objects.filter(beleg_dokument__isnull=True)\
                             .exclude(**{ALT_FELD: ""}):   # ALT_FELD aus V3
        alt = getattr(r, ALT_FELD)
        if not alt:
            continue
        dok = Dokument.objects.create(
            datei=alt,                    # bestehenden Storage-Pfad übernehmen
            kategorie="Beleg",
            dokument_typ="beleg",
            revisionssicher=(r.status in GEBUCHTE_STATUS),   # aus V7
            verknuepfung_typ="objekt",
            verknuepfung_id=_objekt_id_von(r),   # gemäß V4 (r.objekt_id / r.weg…)
        )
        r.beleg_dokument = dok
        r.save(update_fields=["beleg_dokument"])
```

**Wichtig:**
- Datei **nicht kopieren/umbenennen** — nur den bestehenden Storage-Pfad in
  `Dokument.datei` übernehmen (keine S3-Neu-Uploads, keine Pfad-Brüche).
- Alt-Feld an `Rechnung` **noch nicht entfernen**. Erst nach erfolgreicher
  Migration + manueller Stichprobe in einer Folge-Migration (`v1_1`) deprecaten.
- Re-Run muss folgenlos sein (`filter(beleg_dokument__isnull=True)`).

**Smoke-Test C:**
- Anzahl migrierter Belege == Anzahl Rechnungen mit Alt-Datei (V3-Zählung).
- Stichprobe: 3 Belege im DMS-Objektfilter sichtbar, Datei öffnet korrekt.
- Migration erneut ausführen → 0 neue Dokumente.

→ **HALT. Manuelle Stichprobe. Freigabe vor Phase D.**

---

## 7. Phase D — Minimaler DMS-Lesezugriff (optional, empfohlen)

Kein volles DMS-UI. Nur ein Read-Endpoint, damit Belege am Objekt sichtbar sind:

| Methode | Pfad | Berechtigung | Antwort |
|---|---|---|---|
| `GET` | `/api/v1/objekte/{id}/dokumente/?typ=beleg` | `kann_objekt_lesen` | Liste `Dokument` (id, dateiname, dokument_typ, abgelegt_am, verknüpfte Rechnung-Nr.) |

Frontend: schlichte Tabellenansicht im Objekt-Detail-Tab „Dokumente", gefiltert
auf `dokument_typ`. Kein Upload-UI, kein Kategoriebaum (kommt mit der
Mail-Intake-/Portal-Ausbaustufe).

---

## 8. Abgrenzung & Sequenz-Hinweis

Das **volle DMS-Feature-Set** (Kategoriebaum, Volltext-Suche-UI, dokument-
bezogene ACL, Beschluss-/Beschlusssammlung-Modul) wird bewusst **nicht** hier
gebaut, sondern an die **Mail-Intake-Pipeline** gehängt — dort entstehen erstmals
heterogene, nicht-strukturierte Dokumente in Menge, gegen die sich die
Kategorisierung real modellieren lässt. Diese Spec macht nur das Fundament
tragfähig.

---

## 9. Offene Punkte (vor Freigabe zu klären)

1. **App-Zuordnung des `Dokument`-Models** (`apps/dms` vs. bestehende App) — aus V1.
2. **Sperrzeitpunkt Revisionssicherheit:** bei `freigegeben` oder erst bei `gebucht`? (Empfehlung: bei OP-Buchung, siehe 5.3 — Bestätigung aus V7.)
3. **Manuelle Rechnung ohne Beleg:** zulässig lassen (nur Service-Warnung) oder harte Pflicht ab Buchung? (Empfehlung: Pflicht ab Buchung, Warnung davor.)
4. **Alt-Feld-Deprecation:** Zeitpunkt für Entfernen des `Rechnung`-Alt-Datei-Felds nach Phase C festlegen (Folge-Spec `v1_1`).

---

## 10. Claude-Code-Implementierungsprompt

> Implementiere die Beleg↔Dokument-Kopplung gemäß
> `CLAUDE_CODE_ANLEITUNG_BELEG_DOKUMENT_KOPPLUNG_v1_0.md`.
>
> **Zwingend zuerst Phase 0:** Beantworte V1–V7 aus dem realen Quellcode und der
> DB, schreibe `IST_BERICHT_BELEG_DOKUMENT.md` und **stoppe dort**. Erst nach
> meiner Freigabe die Feldnamen dieser Spec an die Ist-Befunde anpassen und mit
> Phase A fortfahren.
>
> **Reihenfolge nach Freigabe:**
> 1. Phase A — `Dokument`-Felder + `Rechnung.beleg_dokument`, zwei Schema-Migrationen, Smoke-Test A. **HALT.**
> 2. Phase B — `beleg_service.lege_rechnungsbeleg_ab`, `Dokument.delete()`-Sperre, Datei-Austausch-Sperre, Revisionssicherheit-Setzen im Buchungs-Service, Smoke-Test B. **HALT.**
> 3. Phase C — nur falls V3=ja: idempotente Datenmigration, Alt-Feld NICHT entfernen, Smoke-Test C. **HALT + Stichprobe.**
> 4. Phase D — Read-Endpoint + schlichte Objekt-Dokumente-Tabelle.
>
> Regeln: Logik nur in `services/`. Eine Funktion, eine Aufgabe. Keine
> Django-Signals für die Sperre — expliziter Service-Aufruf im Buchungspfad.
> Idempotenz bei der Migration. Keine S3-Neu-Uploads in Phase C (nur Pfad-Übernahme).
