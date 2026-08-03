# IST_BERICHT_BELEG_DOKUMENT

**Phase 0 — Ist-Verifikation zur Spec `CLAUDE_CODE_ANLEITUNG_BELEG_DOKUMENT_KOPPLUNG_v1_0.md`**
**Erhoben am:** 2026-08-03 · **Quellen:** Quellcode (Branch `feature/DMS_Rechnung`, Stand main b8022f1), lokale DB (leer) und **Live-DB** (rein lesende COUNT-Abfragen per SSH)

---

## V1 — Dokument-Model: Lage und vollständige Feldliste

**Fundort:** `backend/apps/dokumente/models.py`, Zeilen 125–153 — App heißt **`dokumente`**, nicht `dms` (Spec-Annahme `apps/dms` ist falsch).

| Feld | Typ | Optionen |
|---|---|---|
| `id` | UUIDField | primary_key, default=uuid4, editable=False |
| `datei` | **FileField** | `upload_to='dokumente/'` |
| `dateiname` | CharField(255) | — |
| `kategorie` | CharField(100) | Freitext, z. B. Teilungserklärung, Versicherung, Protokoll |
| `beschreibung` | TextField | blank=True |
| `verknuepfung_typ` | CharField(50) | Freitext: Objekt / Einheit / Ticket / Rechnung |
| `objekt` | FK → Objekt | on_delete=CASCADE, null=True, blank=True, related_name='dokumente' |
| `einheit` | FK → Einheit | on_delete=CASCADE, null=True, blank=True, related_name='dokumente' |
| `hochgeladen_von` | FK → User | on_delete=PROTECT |
| `hochgeladen_am` | DateTimeField | auto_now_add=True |

**Datei-Feld:** existiert, heißt **`datei`** (FileField). **Nicht vorhanden:** `dokument_typ`, `revisionssicher`, `sha256`, `abgelegt_am` → alle vier Spec-Felder (3.1) sind additiv möglich.
**Bestand:** 0 Dokument-Datensätze lokal **und** live → keine Bestandsdaten-Migration am Dokument-Model nötig.

## V2 — Objekt-/Einheit-Verlinkung im Dokument-Model

**Konkrete ForeignKeys** (`objekt`, `einheit`), **keine** generische Relation (kein ContentType/GenericForeignKey). Daneben `verknuepfung_typ` als einfacher CharField-Diskriminator. Der Spec-Code (5.1) mit `verknuepfung_typ="objekt", verknuepfung_id=objekt.id` ist anzupassen auf: `verknuepfung_typ='Rechnung'` (o. ä.) + `objekt=<Objekt-Instanz>`.

## V3 — Rechnung: Datei-Felder und Bestandszählung

**Fundort:** `backend/apps/rechnungen/models.py` (Model `Rechnung`, ab Zeile 54).

| Feld | Typ | Zeile | Live-Nutzung (154 Rechnungen gesamt) |
|---|---|---|---|
| `pdf_upload` | FileField(upload_to='rechnungen/', blank=True) | 144 | **0 / 154 — ungenutzt** |
| `pfad` | CharField(max_length=1000, blank=True) | 116 | **154 / 154 — das reale Alt-Datei-Feld** |
| `dateiname` | CharField(500, blank=True) | 115 | gefüllt |
| `sha256_hash` | CharField(64, blank=True, db_index=True) | 117 | 154 / 154 |

**Pfadformat (Live-Beispiele):** `/app/rechnungen/archiv/2026/08/03.08.2026_10-21_J-26-01561-Rechnung.PDF` — **absolute Docker-Pfade** unter `/app/rechnungen/…` (Bind-Mount des Rechnungen-Ordners), **nicht** unter MEDIA_ROOT (`/app/media`).

**→ V3 = JA, Phase C ist nötig** (154 Bestandsbelege), aber das Alt-Feld ist `pfad` (CharField mit absolutem Pfad), nicht `pdf_upload`. Eine simple „Pfad-Übernahme in `Dokument.datei` (FileField)“ funktioniert nicht 1:1, da FileField MEDIA_ROOT-relative Namen erwartet — Klärung in Phase-C-Design nötig (Optionen: Pfad-String normiert übernehmen, eigenes CharField, oder Storage-Anpassung).

## V4 — Objekt- und Kreditor-Verlinkung an Rechnung

```python
objekt   = models.ForeignKey(Objekt,   on_delete=models.PROTECT,  related_name='rechnungen', null=True, blank=True)   # Z. 100–103
kreditor = models.ForeignKey(Kreditor, on_delete=models.SET_NULL, related_name='rechnungen', null=True, blank=True)   # Z. 105–108
lieferant = models.ForeignKey(Person, ...)  # Z. 110–113, separates optionales Feld
```

**Ergebnis:** Feld heißt **`objekt`** (FK → Objekt, nicht `weg`); **`kreditor`** ist FK auf ein eigenes **`Kreditor`**-Model (nicht Person). Zusätzlich existiert `lieferant` (FK → Person).

## V5 — Kollisionsprüfung `beleg` / `beleg_dokument`

- `Rechnung` hat **kein** direktes Feld `beleg` oder `beleg_dokument`.
- `Buchung` (backend/apps/buchhaltung/models.py) hat **kein** Feld `beleg`, sondern `belegnr` (Z. 142), `belegdatum` (Z. 144), `beleg_referenz` (Z. 154) — die Spec-Annahme „`Buchung.beleg` existiert als generische Referenz“ ist **falsch**.
- **ABER — zentraler Befund:** Es existiert bereits ein **`Beleg`-Model** (`backend/apps/dokumente/models.py`, Z. 59–122):
  - UUID-PK, systemweit eindeutige, unveränderliche **`belegnummer`** (Format `AA00000001`, Singleton-Zähler `BelegnummerZaehler` mit SELECT FOR UPDATE),
  - `typ` (rechnung/dokument/wiederkehrend/sonstiges), `objekt` (FK, PROTECT),
  - **`rechnung` = OneToOne → rechnungen.Rechnung (SET_NULL, related_name='beleg')**,
  - **`dokument` = OneToOne → dokumente.Dokument (SET_NULL, related_name='beleg')**.
  - Live-Bestand: **0 Beleg-Datensätze** (Model angelegt, aber noch ungenutzt).
- **Konsequenz:** `rechnung.beleg` ist als **Reverse-Relation bereits vergeben**. Der Spec-Feldname `beleg_dokument` kollidiert namentlich nicht, aber die Spec-Architektur (direktes OneToOne `Rechnung.beleg_dokument → Dokument`) **überschneidet sich konzeptionell** mit der bestehenden `Beleg`-Brücke (`Rechnung ←1:1— Beleg —1:1→ Dokument`). **Vor Phase A ist zu entscheiden, welcher Kopplungsweg gilt** (siehe „Entscheidungsbedarf“).

## V6 — Storage-Backend

- **Kein S3, kein django-storages, kein MinIO.** `MEDIA_URL='media/'`, `MEDIA_ROOT=BASE_DIR/'media'` (backend/config/settings.py, Z. 110–111); Docker-Volume `backend_media:/app/media`; kein `DEFAULT_FILE_STORAGE`/`STORAGES`/`AWS_*`, auch nicht in `.env.example`.
- Datei-Felder (Dokument.datei, Rechnung.pdf_upload) nutzen den Django-Default-Storage (lokales Dateisystem), kein explizites `storage=`-Argument.
- **Zusatzbefund:** Die realen Rechnungs-PDFs liegen **außerhalb** von MEDIA_ROOT im Bind-Mount `/app/rechnungen/…` (SFTP-Chroot-Upload-Pipeline). Die Spec-Formulierung „S3 via django-storages“ (5.1) und „keine S3-Neu-Uploads“ (Phase C) ist auf lokale Pfade zu übertragen: **keine Datei-Kopien/-Verschiebungen, nur Referenz-Übernahme.**

## V7 — Rechnungs-Lifecycle und Buchungszeitpunkt

**STATUS_CHOICES** (backend/apps/rechnungen/models.py, Z. 55–80): `importiert`, `duplikat`, `prueffall` (alt), `erfasst`, `erkannt` (Stufe 1), `pruefung_match` (Stufe 2), `nicht_erkannt` (Stufe 3), `in_pruefung`, `in_buchhaltung` (Stufe 1), `zur_freigabe` (Stufe 2), **`freigegeben` („Freigegeben (OP gebucht)“)**, `teilbezahlt`, `bezahlt`, `abgelehnt`, `storniert`, `fehler`. Default: `importiert`.

**OP-Entstehung:** `backend/apps/rechnungen/services/rechnung_op_service.py`, Funktion `rechnung_freigeben()` (Z. 102–219):
- Z. 175: `Buchung.objects.create(..., status="entwurf", ...)`
- Z. 197: `KreditorOP.objects.create(...)` (Nebenbuch)
- Z. 216: `rechnung.status = "freigegeben"` — Kommentar im Code: „v1.1: Freigabe erteilt, OP gebucht“
- Verlinkung über `Rechnung.op_buchung` (OneToOne, Z. 193).

**Ergebnis:** „Gebucht“ = Statusübergang nach **`freigegeben`** in `rechnung_freigeben()`. Das ist der korrekte Einhängepunkt für die Revisionssicherheits-Sperre (Spec 5.3); die Spec-Empfehlung „Sperre bei OP-Buchung, nicht bei `erfasst`“ ist damit bestätigt.

**Live-Statusverteilung (154):** in_buchhaltung 138 · freigegeben 10 · abgelehnt 3 · prueffall 2 · bezahlt 1.

---

## Auffälligkeiten / Spec-Abweichungen (Zusammenfassung)

1. **App-Zuordnung:** `apps/dokumente` (nicht `apps/dms`); Rechnung in `apps/rechnungen` (nicht `apps/buchhaltung`). Der Spec-Service-Pfad `apps/dms/services/beleg_service.py` → real `apps/dokumente/services/beleg_service.py`.
2. **`Beleg`-Brückenmodel existiert bereits** (ungenutzt, 0 Datensätze) und vergibt `related_name='beleg'` auf Rechnung UND Dokument. Größte Abweichung — Architekturentscheidung nötig.
3. **`Buchung.beleg` existiert nicht** (nur belegnr/belegdatum/beleg_referenz) — Begründung des Spec-Feldnamens entfällt, Kollisionslage ist real aber anders (Reverse-Relation durch `Beleg`-Model).
4. **Alt-Datei-Feld ist `pfad`** (CharField, absolute Docker-Pfade außerhalb MEDIA_ROOT); `pdf_upload` ist ungenutzt (0/154) und Deprecation-Kandidat.
5. **`sha256_hash` existiert bereits an Rechnung** (154/154 gefüllt) → Werte können in `Dokument.sha256` übernommen werden, Duplikaterkennung existiert dort schon.
6. **Kein S3** — Storage lokal; Phase-C-Regel lautet daher: keine Datei-Kopien, nur Referenz-Übernahme; FileField-vs-absoluter-Pfad-Frage klären.
7. **Verlinkung im Dokument-Model konkret** (FKs objekt/einheit + `verknuepfung_typ`-CharField), nicht generisch — Spec-Code 5.1 anpassen.

## Entscheidungsbedarf vor Phase A (Freigabe erforderlich)

| # | Frage | Optionen | Anmerkung |
|---|---|---|---|
| E1 | **Kopplungsweg:** neues `Rechnung.beleg_dokument` (OneToOne → Dokument, Spec) **oder** bestehendes `Beleg`-Brückenmodel nutzen/ausbauen? | (a) Spec-Feld zusätzlich, (b) Beleg-Model als einziger Weg, (c) Spec-Feld + Beleg-Model später deprecaten | `related_name='rechnung'` aus Spec 3.2 ist frei; `rechnung.beleg` ist durch Beleg-Model belegt |
| E2 | Sperrzeitpunkt Revisionssicherheit | bei `freigegeben` (= OP-Buchung) | durch V7 bestätigt, Empfehlung: so umsetzen |
| E3 | Phase-C-Technik für `pfad` → `Dokument.datei` | Pfad-String übernehmen vs. Storage-/Feld-Anpassung | 154 Datensätze, Dateien in `/app/rechnungen/…` |
| E4 | Umgang mit ungenutztem `pdf_upload` | in v1_1 deprecaten | nicht Teil dieser Spec-Phase |

---

**→ HALT. Freigabe abwarten, bevor die Spec-Feldnamen angepasst werden und Phase A startet.**
