# IMMOCORE — Wirtschaftsjahre | Claude Code Prompt v1.0

**IMMOCORE** — *Webbasiertes Immobilienverwaltungssystem*
**Modul:** Wirtschaftsjahre (Anlage, Folgejahr-Eröffnung, WJ-gebundener Kontenrahmen)
**Demme Immobilien Verwaltung GmbH** — Coventrystraße 32, 65934 Frankfurt am Main
**Version:** 1.0 | **Stand:** Mai 2026
**KI-Modell:** `claude-sonnet-4-6`

---

## 1. Zweck dieses Dokuments

Diese Spezifikation führt das **Wirtschaftsjahr (WJ)** als eigenständige Entität in IMMOCORE ein. Sie ergänzt die WEG-Objektanlage (v1.2) um einen neuen Wizard-Schritt für das erste Wirtschaftsjahr und definiert eine separate Massenaktion zur Eröffnung von Folgejahren mit kopiertem Kontenrahmen und kopierten Verteilerschlüssel-Zuordnungen.

**Bezug:** `IMMOCORE_Ausgangsspezifikation_v1.1.docx`, `IMMOCORE_ClaudeCode_WEG_Objektanlage_v1.2.docx`, `IMMOCORE_ClaudeCode_Massenimport_WEG_v1.0.docx`.

**Ausdrücklich nicht Teil dieser Spec (eigene Specs):**
- Saldenvortrag / Eröffnungsbuchungen (Konten 90xxx / 91xxx) — eigene Spec.
- Fachliche Bedeutung der Verbrauchsschlüssel `VS 140–145` — wird in der HEIWAKO-Unterkonten-Spec festgelegt. Diese Spec definiert nur die **Mechanik** (Werte beim Jahreswechsel `NULL`, Zuordnung bleibt erhalten).
- HEIWAKO-Datenimport (separate Spec, ARGE 3.10).
- Jahresabrechnung-Erzeugung (siehe Ausgangsspezifikation Kap. 5.3 / 6).

---

## 2. Kernkonzept

### 2.1 Wirtschaftsjahr als 1:N-Entität am Objekt

Bisher waren Konten, Verteilerschlüssel-Zuordnungen und Buchungen direkt am `Objekt` aufgehängt. Mit dieser Spec wird zwischen `Objekt` und allen buchungsrelevanten Entitäten die neue Ebene `Wirtschaftsjahr` eingezogen.

```
Objekt (1) ─── (N) Wirtschaftsjahr (1) ─── (N) Konto
                                       └── (N) KontoVerteilerSchluessel
                                       └── (N) EinheitVerbrauch
                                       └── (N) Buchung / Buchungssatz
```

### 2.2 Lebenszyklus eines Wirtschaftsjahres

| Status | Bedeutung | Übergang |
|---|---|---|
| `offen` | Buchungen erlaubt | wird bei Anlage gesetzt |
| `abgeschlossen` | Read-only; Jahresabrechnung freigegeben und gesperrt | nur durch Jahresabrechnungs-Workflow (separate Spec) |

Ein Objekt kann beliebig viele aufeinanderfolgende WJ haben. Mehrere `offen`-WJ gleichzeitig sind erlaubt (z.B. WJ 2024 noch nicht abgeschlossen, WJ 2025 bereits eröffnet).

### 2.3 Vier Eintrittspunkte

| Eintrittspunkt | Auslöser | Ergebnis |
|---|---|---|
| **A** Erstes WJ bei Objektanlage | Neuer Wizard-Schritt 2c | WJ N angelegt, Kontenrahmen daran gehängt |
| **B** Folgejahr-Eröffnung | Massenaktion in Objektliste | WJ N+1 angelegt, Kontenrahmen + VS-Zuordnungen kopiert |
| **C** Migration Bestandsobjekte | Einmalige Daten-Migration | WJ aus `objekt.wirtschaftsjahr_start` + aktuellem Jahr abgeleitet |
| **D** Massenimport WEG | Excel-Vorlage MI-WEG.xlsx mit Spalten WJ-Jahr / WJ-Beginn-Monat | Je Zeile WJ N angelegt, Kontenrahmen daran gehängt |

---

## 3. Datenmodell

### 3.1 Neues Model `Wirtschaftsjahr`

| Feld | Typ | Pflicht | Anmerkung |
|---|---|---|---|
| `id` | UUID (PK) | Ja | |
| `objekt` | FK → Objekt (CASCADE) | Ja | |
| `jahr` | IntegerField | Ja | 4-stellig, z.B. 2024 |
| `beginn_monat` | IntegerField (1–12) | Ja | aus `objekt.wirtschaftsjahr_start` übernommen |
| `status` | Enum: `offen` \| `abgeschlossen` | Ja | Default: `offen` |
| `vorjahr` | FK → Wirtschaftsjahr (SET_NULL) | Nein | NULL beim ersten WJ |
| `eroeffnet_am` | DateTimeField | Ja | `auto_now_add` |
| `eroeffnet_von` | FK → User (SET_NULL) | Nein | |
| `abgeschlossen_am` | DateTimeField | Nein | |

**Constraints:**
- `UniqueConstraint(objekt, jahr)` — pro Objekt ein WJ je Jahr.
- `CheckConstraint(jahr >= 2000)`.
- `vorjahr.objekt == self.objekt` (DB-Constraint via Validator, nicht via SQL).

**Berechnete Properties:**
- `beginn_datum` → `date(jahr, beginn_monat, 1)`
- `ende_datum` → `date(jahr + 1, beginn_monat, 1) - timedelta(days=1)` (Standard: Kalenderjahr → 31.12.)

### 3.2 Anpassung `Konto`

Bestehendes Feld `objekt` (FK → Objekt) wird ersetzt durch:

| Feld | Typ | Anmerkung |
|---|---|---|
| `wirtschaftsjahr` | FK → Wirtschaftsjahr (CASCADE) | Pflicht |

Über `konto.wirtschaftsjahr.objekt` ist das Objekt weiterhin erreichbar. Convenience-Property `konto.objekt` bleibt als reine Lese-Property erhalten.

**Stammdaten je Konto** (unverändert): `nummer`, `name`, `abrechnungsart`, `direktes_buchen`, `vs`, `kontoart`, `arge_konto`, `arge_kostenart`.

### 3.3 Neues Model `KontoVerteilerSchluessel`

Bisher war die VS-Zuordnung (welcher Verteilerschlüssel für welches Konto) als Einzelfeld `konto.vs` gespeichert. Für Folgejahr-Eröffnung mit unabhängiger Bearbeitbarkeit wird die Zuordnung als eigene Tabelle materialisiert:

| Feld | Typ | Anmerkung |
|---|---|---|
| `id` | UUID (PK) | |
| `konto` | FK → Konto (CASCADE) | |
| `vs_code` | CharField(3) | z.B. `010`, `031`, `140` |
| `gueltig_ab` | DateField | Default: WJ-Beginn |

**Migration-Hinweis:** Bestehende `konto.vs`-Einträge werden in dieser Tabelle materialisiert. Das Feld `konto.vs` bleibt zunächst als Cache erhalten (Lesepfad), die Schreibseite läuft über `KontoVerteilerSchluessel`.

### 3.4 Neues Model `EinheitVerbrauch`

Verbrauchswerte je Einheit, Wirtschaftsjahr und Verbrauchsschlüssel (VS 140–145):

| Feld | Typ | Pflicht | Anmerkung |
|---|---|---|---|
| `id` | UUID (PK) | Ja | |
| `wirtschaftsjahr` | FK → Wirtschaftsjahr (CASCADE) | Ja | |
| `einheit` | FK → Einheit (CASCADE) | Ja | |
| `vs_code` | CharField(3) | Ja | nur Werte aus Bereich `140`–`145` |
| `wert` | DecimalField(12,4) | Nein | NULL = noch nicht erfasst |
| `einheit_text` | CharField | Nein | z.B. `kWh`, `m³`, `Liter` |
| `quelle` | Enum: `manuell` \| `heiwako_import` | Nein | |

**Constraints:**
- `UniqueConstraint(wirtschaftsjahr, einheit, vs_code)`.
- `CheckConstraint(vs_code IN ('140','141','142','143','144','145'))`.

**Wichtig — Mechanik beim Jahreswechsel:**
- Die Existenz der Zeile (`wirtschaftsjahr`, `einheit`, `vs_code`) bleibt erhalten — wird also kopiert.
- Das Feld `wert` wird auf `NULL` zurückgesetzt.
- Das Feld `einheit_text` (Maßeinheit) bleibt erhalten.

Die fachliche Bedeutung der einzelnen Codes 140–145 ist **nicht** Teil dieser Spec.

### 3.5 Anpassung `Buchung` / `Buchungssatz`

Bestehende Buchungs-Models bekommen einen FK auf `Wirtschaftsjahr`:

| Feld | Typ | Anmerkung |
|---|---|---|
| `wirtschaftsjahr` | FK → Wirtschaftsjahr (PROTECT) | Pflicht |

`PROTECT` statt `CASCADE` — ein WJ mit Buchungen darf nicht gelöscht werden. GoBD-konform.

Die Zuordnung erfolgt anhand des Buchungsdatums: `buchung.datum` muss in `[wirtschaftsjahr.beginn_datum, wirtschaftsjahr.ende_datum]` liegen. Validator im Service-Layer.

---

## 4. Wizard-Erweiterung — Schritt 2c "Erstes Wirtschaftsjahr"

### 4.1 Position im Wizard

Eingefügt **nach** Schritt 2b (Eingänge), **vor** Schritt 3 (Einheiten). Die Wizard-Liste wird damit:

| Nr. | Bezeichnung |
|---|---|
| 1 | Objekttyp |
| 2 | Stammdaten |
| 2b | Eingänge |
| **2c** | **Erstes Wirtschaftsjahr** ← NEU |
| 3 | Einheiten |
| 4 | Eigentümer |
| 5 | Bankkonten |
| 6 | Kontenrahmen |
| 7 | Verträge |
| 8 | Freigabelimits |
| 9 | Review & Aktivierung |

### 4.2 UI-Spezifikation Schritt 2c

```
Eingabefelder:
  jahr         IntegerField, 4-stellig, Pflicht
               Default: aktuelles Jahr (datetime.now().year)
               Min: 2000
               Max: aktuelles Jahr + 1

Anzeige (read-only, abgeleitet aus Schritt 2):
  beginn_monat  aus objekt.wirtschaftsjahr_start
  beginn_datum  z.B. "01.01.2024"
  ende_datum    z.B. "31.12.2024"

Hinweistext:
  "Das erste Wirtschaftsjahr wird mit dem in Schritt 2 gewählten
   Beginn-Monat angelegt. Spätere Wirtschaftsjahre werden über die
   Massenaktion 'Nächstes Wirtschaftsjahr eröffnen' erzeugt."
```

### 4.3 Validierung Schritt 2c

| Regel | Fehlermeldung |
|---|---|
| `jahr` Pflicht | "Bitte Jahr eingeben." |
| `2000 <= jahr <= aktuelles_jahr + 1` | "Jahr muss zwischen 2000 und {max_jahr} liegen." |

Persistierung: noch nicht in DB; in `steps_data` puffern.

### 4.4 Atomare Anlage in Schritt 9

Im bestehenden atomaren Commit (Schritt 9) wird **nach** `Objekt anlegen` und **vor** `Kontenrahmen anlegen` das Wirtschaftsjahr erzeugt:

```python
# in services/objektanlage.py — atomic block

# 1. Objekt anlegen
objekt = Objekt.objects.create(...)

# 2. Eingänge anlegen
...

# 3. NEU — Erstes Wirtschaftsjahr anlegen
wj = Wirtschaftsjahr.objects.create(
    objekt=objekt,
    jahr=steps_data['schritt_2c']['jahr'],
    beginn_monat=objekt.wirtschaftsjahr_start,
    status='offen',
    vorjahr=None,
    eroeffnet_von=user,
)

# 4. Einheiten anlegen
...

# 7. Kontenrahmen — Konten erhalten FK auf wj
for konto_data in steps_data['schritt_6']['konten']:
    konto = Konto.objects.create(wirtschaftsjahr=wj, **konto_data)
    # VS-Zuordnung als KontoVerteilerSchluessel persistieren
    if konto_data.get('vs'):
        KontoVerteilerSchluessel.objects.create(
            konto=konto,
            vs_code=konto_data['vs'],
            gueltig_ab=wj.beginn_datum,
        )

# 7b. EinheitVerbrauch-Zeilen anlegen — Strukturzeilen für VS 140–145
#     je Einheit. Werte bleiben NULL bis HEIWAKO-Import oder manueller Eingabe.
for einheit in objekt.einheiten.all():
    for vs_code in ['140', '141', '142', '143', '144', '145']:
        EinheitVerbrauch.objects.create(
            wirtschaftsjahr=wj,
            einheit=einheit,
            vs_code=vs_code,
            wert=None,
        )
```

**Hinweis zur EinheitVerbrauch-Anlage:** Die strukturelle Anlage je Einheit × VS-Code bei Objektanlage ist eine Vorab-Materialisierung. Falls die HEIWAKO-Spec später entscheidet, dass nur tatsächlich genutzte VS pro Objekt angelegt werden, lässt sich diese Schleife auf eine konfigurierbare Liste reduzieren. Die Mechanik der Folgejahr-Kopie (Kapitel 5) bleibt davon unberührt.

---

## 4a. Integration mit Massenimport WEG

Der Massenimport (`IMMOCORE_ClaudeCode_Massenimport_WEG_v1.0.docx`) kennt das Konzept Wirtschaftsjahr nicht. Mit dieser Spec wird er um zwei Spalten und einen Anlage-Schritt erweitert. Der bestehende Massenimport bleibt rückwärtskompatibel: ältere Vorlagen ohne die neuen Spalten werden mit Default-Werten verarbeitet.

### 4a.1 Vorlagen-Erweiterung MI-WEG.xlsx

Zwei neue Spalten am Ende der Vorlage (nach `ANZ-RL`):

| Spalte | Feldname | Pflicht | Beschreibung | Mapping |
|---|---|---|---|---|
| AG | WJ-Jahr | Ja | Erstes Wirtschaftsjahr (4-stellig, z.B. 2024) | `Wirtschaftsjahr.jahr` |
| AH | WJ-Beginn-Monat | Optional | Beginn-Monat des Wirtschaftsjahres (1–12). Default: 1 | `Wirtschaftsjahr.beginn_monat` und `Objekt.wirtschaftsjahr_start` |

**Default-Verhalten bei alten Vorlagen** (Spalten AG/AH fehlen): `WJ-Jahr = aktuelles Jahr`, `WJ-Beginn-Monat = 1`. Der Importer erzeugt eine **Warnung** je Zeile ("WJ-Jahr nicht angegeben — auf {aktuelles_jahr} gesetzt"), legt das Objekt aber regulär an.

### 4a.2 Anpassung der Anlage-Reihenfolge

Die Reihenfolge aus Massenimport v1.0 Kap. 3.1 wird wie folgt erweitert:

| # | Entität | Änderung |
|---|---|---|
| 1 | Objekt | unverändert; `wirtschaftsjahr_start` aus Spalte AH |
| 2 | Liegenschaften (Eingänge) | unverändert |
| **2a** | **Wirtschaftsjahr** | **NEU** — vor Bankkonten und Kontenrahmen anlegen |
| 3 | Bankkonten | unverändert |
| 4 | Kontenrahmen (Sachkonten) | FK auf das in 2a angelegte WJ |
| 5 | Abrechnungsarten | unverändert (Objekt-bezogen, nicht WJ-bezogen) |
| 6 | Verteilerschlüssel | unverändert (global je Mandant) |
| 7 | Freigabelimits | unverändert |

**Wichtig:** EinheitVerbrauch-Strukturzeilen (siehe Kap. 4.4 dieser Spec) werden vom Massenimport **nicht** angelegt, weil der Massenimport keine Einheiten erzeugt. Die Verbrauchszeilen entstehen erst bei Einheiten-Nachpflege (Wizard-Schritt 3 oder separater CSV-Import). Der spätere Folgejahr-Eröffnungs-Mechanismus (Kap. 5) funktioniert dadurch nicht eingeschränkt — `_kopiere_einheit_verbrauch` kopiert genau das, was im Vorjahr-WJ existiert (also nichts, solange keine Einheiten gepflegt sind).

### 4a.3 Pseudocode — Anlage je Zeile (Erweiterung)

```python
# in services/massenimport.py — innerhalb der bestehenden
# transaction.atomic()-Klammer je Zeile

# 1. Objekt anlegen — wirtschaftsjahr_start aus Spalte AH
objekt = Objekt.objects.create(
    bezeichnung=zeile["bezeichnung"],
    strasse=zeile["a1"],
    plz=zeile["plz1"],
    ort=zeile["ort1"],
    baujahr=zeile.get("baujahr"),
    verwaltung_seit=timezone.now().date(),
    wirtschaftsjahr_start=zeile.get("wj_beginn_monat", 1),
    status="aktiv",
    zahlungsfreigabe_grenzen=STANDARD_FREIGABELIMITS,
)

# 2. Liegenschaften (Eingänge) anlegen
...

# 2a. NEU — Wirtschaftsjahr anlegen
wj = Wirtschaftsjahr.objects.create(
    objekt=objekt,
    jahr=zeile["wj_jahr"],
    beginn_monat=zeile.get("wj_beginn_monat", 1),
    status="offen",
    vorjahr=None,
    eroeffnet_von=user,
)

# 3. Bewirtschaftungskonto + Rücklagenkonten
...

# 4. Kontenrahmen — alle Konten an das WJ hängen
for konto_def in STANDARD_WEG_KONTENRAHMEN:
    konto = Konto.objects.create(wirtschaftsjahr=wj, **konto_def)
    if konto_def.get("vs"):
        KontoVerteilerSchluessel.objects.create(
            konto=konto,
            vs_code=konto_def["vs"],
            gueltig_ab=wj.beginn_datum,
        )

for n in range(1, zeile["anz_rl"] + 1):
    for konto_def in ruecklage_konten(n):
        konto = Konto.objects.create(wirtschaftsjahr=wj, **konto_def)
        if konto_def.get("vs"):
            KontoVerteilerSchluessel.objects.create(
                konto=konto,
                vs_code=konto_def["vs"],
                gueltig_ab=wj.beginn_datum,
            )

# 5./6./7. Abrechnungsarten, Verteilerschlüssel, Freigabelimits
...
```

### 4a.4 Validierungsregeln (Ergänzung Kap. 7 Massenimport-Spec)

| Schwere | Regel | Verhalten |
|---|---|---|
| Fehler | `WJ-Jahr` < 2000 oder > aktuelles Jahr + 1 | Zeile wird zurückgewiesen |
| Fehler | `WJ-Beginn-Monat` nicht in 1–12 | Zeile wird zurückgewiesen |
| Warnung | Spalten AG/AH fehlen (alte Vorlage) | Zeile wird angelegt; Default-Werte; Hinweis in UI |
| Warnung | `WJ-Jahr` ist Vorjahr oder älter | Zeile wird angelegt; Hinweis "Buchungen nur in offenen WJ möglich — bitte prüfen" |

### 4a.5 Vorschau-JSON-Erweiterung

Die Preview-Response (`POST /api/v1/massenimport/weg/preview/`) zeigt je Zeile zusätzlich das anzulegende WJ:

```json
{
  "zeilennummer": 1,
  "bezeichnung": "WEG Mainufer 1-3",
  "anz_rl": 2,
  "wj_jahr": 2024,
  "wj_beginn_monat": 1,
  "konten_anzahl": 87,
  "status": "ok",
  "warnungen": []
}
```

### 4a.6 Verweis aus Massenimport-Spec v1.0

Am Anfang der Massenimport-v1.0-Spec ist folgender Hinweis zu ergänzen (als Versionshinweis, nicht als inhaltliche Änderung dieser Spec selbst):

> **Hinweis:** Diese Spec wurde durch `IMMOCORE_ClaudeCode_Wirtschaftsjahre_v1_0.md` ergänzt. Die Excel-Vorlage MI-WEG.xlsx enthält die zusätzlichen Spalten **AG (WJ-Jahr)** und **AH (WJ-Beginn-Monat)**. Pro Zeile wird zusätzlich zum Objekt ein Wirtschaftsjahr angelegt; alle Konten hängen an diesem WJ. Details: Wirtschaftsjahre-Spec Kap. 4a.

---

## 5. Folgejahr-Eröffnung (Massenaktion)

### 5.1 Eintrittspunkt

In der Objektliste (`/objekte/`) wird je Zeile eine Checkbox angeboten. Über eine Mehrfachauswahl + Button "Nächstes Wirtschaftsjahr eröffnen" startet der Workflow.

Sichtbar nur für Rollen mit Berechtigung `wirtschaftsjahr.eroeffnen` (typisch: Sachbearbeiter, Geschäftsführer).

### 5.2 Bestätigungs-Dialog

```
Tabelle:
  Objekt-Nr. | Bezeichnung | Letztes WJ | Folgejahr | Status
  100001     | WEG Beispiel 1 | 2024 (offen) | 2025 | OK
  100002     | WEG Beispiel 2 | 2024 (offen) | 2025 | OK
  100003     | WEG Beispiel 3 | —            | —    | FEHLER: kein WJ vorhanden, bitte Wizard nutzen
  100004     | WEG Beispiel 4 | 2025 (offen) | 2026 | OK

Buttons:
  [ Abbrechen ]   [ Eröffnen für N gültige Objekte ]
```

Objekte mit Status `FEHLER` werden in der Massenaktion übersprungen, nicht blockiert.

### 5.3 Endpunkt

| Methode | Pfad | Beschreibung |
|---|---|---|
| POST | `/api/v1/wirtschaftsjahre/folgejahr/preview/` | Liste Objekt-IDs → Vorschau-JSON mit Status je Objekt |
| POST | `/api/v1/wirtschaftsjahre/folgejahr/commit/` | Vorschau-Token → atomare Anlage je Objekt |

**Request `commit`:**
```json
{
  "preview_token": "...",
  "objekt_ids": ["uuid1", "uuid2", ...]
}
```

**Response `commit`:**
```json
{
  "ergebnisse": [
    {"objekt_id": "uuid1", "wj_neu": 2025, "status": "ok",
     "konten_kopiert": 87, "vs_zuordnungen_kopiert": 42, "verbrauchszeilen_kopiert": 60},
    {"objekt_id": "uuid2", "wj_neu": 2025, "status": "fehler",
     "fehler": "Folgejahr 2025 existiert bereits"}
  ]
}
```

### 5.4 Atomarität — pro Objekt, nicht pro Batch

Jedes Objekt wird in einer **eigenen** `transaction.atomic()`-Klammer verarbeitet. Fehler bei Objekt A führen **nicht** zum Rollback bei Objekt B. Dies entspricht dem Verhalten beim Massenimport (v1.0).

```python
def folgejahr_eroeffnen_batch(objekt_ids: list[UUID], user: User) -> list[dict]:
    ergebnisse = []
    for objekt_id in objekt_ids:
        try:
            with transaction.atomic():
                ergebnis = _folgejahr_eroeffnen_einzeln(objekt_id, user)
            ergebnisse.append(ergebnis)
        except Exception as e:
            ergebnisse.append({
                "objekt_id": str(objekt_id),
                "status": "fehler",
                "fehler": str(e),
            })
    return ergebnisse
```

### 5.5 Ablauf je Objekt

```python
def _folgejahr_eroeffnen_einzeln(objekt_id: UUID, user: User) -> dict:
    # 1. Letztes Wirtschaftsjahr ermitteln
    wj_alt = (Wirtschaftsjahr.objects
              .filter(objekt_id=objekt_id)
              .order_by('-jahr')
              .first())
    if wj_alt is None:
        raise ValidationError(
            "Kein Wirtschaftsjahr vorhanden — bitte WEG-Anlage-Wizard nutzen."
        )

    jahr_neu = wj_alt.jahr + 1

    # 2. Existenzprüfung
    if Wirtschaftsjahr.objects.filter(
        objekt_id=objekt_id, jahr=jahr_neu
    ).exists():
        raise ValidationError(f"Folgejahr {jahr_neu} existiert bereits.")

    # 3. Neues Wirtschaftsjahr anlegen
    wj_neu = Wirtschaftsjahr.objects.create(
        objekt_id=objekt_id,
        jahr=jahr_neu,
        beginn_monat=wj_alt.beginn_monat,
        status='offen',
        vorjahr=wj_alt,
        eroeffnet_von=user,
    )

    # 4. Kontenrahmen kopieren
    konten_kopiert = _kopiere_konten(wj_alt, wj_neu)

    # 5. VS-Zuordnungen kopieren
    vs_kopiert = _kopiere_vs_zuordnungen(wj_alt, wj_neu)

    # 6. EinheitVerbrauch kopieren — Zuordnung erhalten, Werte NULL
    verbrauch_kopiert = _kopiere_einheit_verbrauch(wj_alt, wj_neu)

    return {
        "objekt_id": str(objekt_id),
        "wj_neu": jahr_neu,
        "status": "ok",
        "konten_kopiert": konten_kopiert,
        "vs_zuordnungen_kopiert": vs_kopiert,
        "verbrauchszeilen_kopiert": verbrauch_kopiert,
    }
```

### 5.6 Kontenrahmen kopieren

Stichtag = jetzt (`timezone.now()`). Alle aktuellen Konten des Vorjahres-WJ werden kopiert — auch die, die nachträglich (nach Wizard-Anlage) hinzugefügt wurden. Es findet **keine** Filterung nach "war beim ursprünglichen Wizard dabei" statt.

```python
def _kopiere_konten(wj_alt: Wirtschaftsjahr, wj_neu: Wirtschaftsjahr) -> int:
    konten_alt = list(Konto.objects.filter(wirtschaftsjahr=wj_alt))
    neue_konten = [
        Konto(
            wirtschaftsjahr=wj_neu,
            nummer=k.nummer,
            name=k.name,
            abrechnungsart=k.abrechnungsart,
            direktes_buchen=k.direktes_buchen,
            vs=k.vs,                     # Cache-Feld 1:1
            kontoart=k.kontoart,
            arge_konto=k.arge_konto,
            arge_kostenart=k.arge_kostenart,
        )
        for k in konten_alt
    ]
    Konto.objects.bulk_create(neue_konten)
    return len(neue_konten)
```

**Was NICHT kopiert wird:**
- Buchungen (`Buchung`, `Buchungssatz`)
- Salden / Anfangsbestände — Eröffnungsbuchungen sind separate Spec
- Buchungsperioden-Sperren

### 5.7 Verteilerschlüssel-Zuordnungen kopieren

```python
def _kopiere_vs_zuordnungen(wj_alt: Wirtschaftsjahr, wj_neu: Wirtschaftsjahr) -> int:
    # Map: alte konto_id -> neue konto_id (über kontonummer matchen)
    konten_map = {
        k.nummer: k.id
        for k in Konto.objects.filter(wirtschaftsjahr=wj_neu)
    }
    vs_alt = KontoVerteilerSchluessel.objects.filter(
        konto__wirtschaftsjahr=wj_alt
    ).select_related('konto')

    neue_vs = []
    for v in vs_alt:
        neue_konto_id = konten_map.get(v.konto.nummer)
        if neue_konto_id is None:
            continue  # sollte nicht vorkommen
        neue_vs.append(KontoVerteilerSchluessel(
            konto_id=neue_konto_id,
            vs_code=v.vs_code,
            gueltig_ab=wj_neu.beginn_datum,
        ))
    KontoVerteilerSchluessel.objects.bulk_create(neue_vs)
    return len(neue_vs)
```

### 5.8 EinheitVerbrauch kopieren — Mechanik

**Regel:** Die Zuordnung Einheit↔VS-Code wird kopiert. Die Werte (Feld `wert`) werden auf `NULL` gesetzt. Die Maßeinheit (`einheit_text`) bleibt erhalten.

```python
def _kopiere_einheit_verbrauch(wj_alt: Wirtschaftsjahr, wj_neu: Wirtschaftsjahr) -> int:
    verbrauch_alt = EinheitVerbrauch.objects.filter(wirtschaftsjahr=wj_alt)
    neue_verbrauch = [
        EinheitVerbrauch(
            wirtschaftsjahr=wj_neu,
            einheit=ev.einheit,
            vs_code=ev.vs_code,
            wert=None,                    # WICHTIG: zurückgesetzt
            einheit_text=ev.einheit_text, # Maßeinheit bleibt
            quelle=None,
        )
        for ev in verbrauch_alt
    ]
    EinheitVerbrauch.objects.bulk_create(neue_verbrauch)
    return len(neue_verbrauch)
```

---

## 6. Datenmigration für Bestandsobjekte

### 6.1 Ausgangslage

Bestehende Objekte haben heute Konten direkt am Objekt. Mit dieser Spec wird der FK auf Wirtschaftsjahr verschoben.

### 6.2 Migrationsschritt (Django data migration)

```python
def migrate_konten_zu_wj(apps, schema_editor):
    Objekt = apps.get_model('immocore', 'Objekt')
    Wirtschaftsjahr = apps.get_model('immocore', 'Wirtschaftsjahr')
    Konto = apps.get_model('immocore', 'Konto')
    KontoVerteilerSchluessel = apps.get_model('immocore', 'KontoVerteilerSchluessel')

    aktuelles_jahr = timezone.now().year

    for objekt in Objekt.objects.all():
        # Erstes WJ aus verwaltung_seit oder aktuellem Jahr ableiten
        startjahr = (
            objekt.verwaltung_seit.year
            if objekt.verwaltung_seit
            else aktuelles_jahr
        )
        wj = Wirtschaftsjahr.objects.create(
            objekt=objekt,
            jahr=startjahr,
            beginn_monat=objekt.wirtschaftsjahr_start or 1,
            status='offen',
            vorjahr=None,
        )
        # Bestehende Konten an das WJ binden
        Konto.objects.filter(objekt=objekt).update(wirtschaftsjahr=wj)
        # VS-Zuordnungen aus konto.vs materialisieren
        for konto in Konto.objects.filter(wirtschaftsjahr=wj):
            if konto.vs:
                KontoVerteilerSchluessel.objects.create(
                    konto=konto,
                    vs_code=konto.vs,
                    gueltig_ab=wj.beginn_datum,
                )
```

**Hinweis:** Buchungen werden in einem zweiten Schritt anhand `buchung.datum` dem passenden WJ zugeordnet. Wenn nur ein WJ existiert (Erstmigration), gehen alle Buchungen dorthin.

---

## 7. Berechtigungen & Sichtbarkeit

| Aktion | Rollen |
|---|---|
| Erstes WJ über Wizard anlegen | Wer Objekte anlegen darf |
| Folgejahr-Massenaktion ausführen | Sachbearbeiter, Geschäftsführer |
| WJ in Listen einsehen | Alle, die das Objekt sehen |
| WJ-Status `abgeschlossen` setzen | Nur Jahresabrechnungs-Workflow (separate Spec) |
| WJ löschen | **Nicht möglich** (GoBD) |

---

## 8. Endpunkte (Zusammenfassung)

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/api/v1/objekte/{id}/wirtschaftsjahre/` | Liste WJ eines Objekts |
| GET | `/api/v1/wirtschaftsjahre/{id}/` | Details eines WJ |
| POST | `/api/v1/wirtschaftsjahre/folgejahr/preview/` | Vorschau Folgejahr-Eröffnung |
| POST | `/api/v1/wirtschaftsjahre/folgejahr/commit/` | Folgejahr-Eröffnung committen |

**Bewusst nicht implementiert:**
- `DELETE /api/v1/wirtschaftsjahre/{id}/` — GoBD-Konflikt.
- `PATCH` auf `jahr` oder `beginn_monat` — diese Felder sind unveränderlich nach Anlage.

---

## 9. Validierungsregeln (Zusammenfassung)

| Kontext | Regel | Fehlermeldung |
|---|---|---|
| WJ anlegen | `2000 <= jahr <= aktuelles_jahr + 1` | "Jahr muss zwischen 2000 und {max} liegen." |
| WJ anlegen | `(objekt, jahr)` unique | "Wirtschaftsjahr {jahr} existiert bereits." |
| Folgejahr | Vorgänger-WJ muss existieren | "Bitte WEG-Anlage-Wizard nutzen — kein WJ vorhanden." |
| Buchung | `datum` in `[wj.beginn_datum, wj.ende_datum]` | "Buchungsdatum liegt außerhalb des Wirtschaftsjahres." |
| Buchung | WJ-Status muss `offen` sein | "Wirtschaftsjahr {jahr} ist abgeschlossen." |
| EinheitVerbrauch | `vs_code` ∈ {140..145} | "Ungültiger Verbrauchsschlüssel." |

---

## 10. Akzeptanzkriterien

1. Beim Anlegen eines neuen WEG-Objekts erscheint Schritt 2c mit Vorbelegung des aktuellen Jahres.
2. Nach Aktivierung des Objekts existiert genau ein `Wirtschaftsjahr` mit `vorjahr=NULL`.
3. Alle Konten aus Schritt 6 sind über `konto.wirtschaftsjahr` mit dem WJ verknüpft.
4. Je Einheit existieren 6 `EinheitVerbrauch`-Zeilen (VS 140–145), `wert=NULL`.
5. Die Massenaktion "Nächstes Wirtschaftsjahr eröffnen" ist in der Objektliste sichtbar.
6. Mehrfachauswahl + Eröffnung legt je Objekt ein neues WJ an, kopiert Kontenrahmen und VS-Zuordnungen.
7. Verbrauchswerte (VS 140–145) im neuen WJ sind alle `NULL`, Einheit↔VS-Zuordnung bleibt erhalten.
8. Fehler bei einem Objekt führt nicht zum Rollback bei anderen Objekten.
9. Versuch, ein bestehendes Folgejahr erneut zu eröffnen, schlägt mit klarer Fehlermeldung fehl.
10. Bestandsobjekte erhalten durch die Datenmigration je ein erstes WJ; bestehende Konten und Buchungen sind diesem zugeordnet.
11. Massenimport mit Spalten AG/AH legt je Zeile ein Objekt **inklusive** initialem Wirtschaftsjahr an; alle Konten hängen am WJ. Vorlagen ohne AG/AH werden mit Default-Werten + Warnung verarbeitet.

---

## 11. Claude Code Implementierungsprompt

> Implementiere die Wirtschaftsjahr-Logik gemäß Spezifikation `IMMOCORE_ClaudeCode_Wirtschaftsjahre_v1_0.md`.
>
> **Reihenfolge:**
>
> 1. **Models**
>    - Neues Model `Wirtschaftsjahr` (Kap. 3.1) inkl. Constraints und berechneten Properties.
>    - Anpassung `Konto`: FK `objekt` → FK `wirtschaftsjahr` (Kap. 3.2). Convenience-Property `objekt` als reiner Lesepfad.
>    - Neues Model `KontoVerteilerSchluessel` (Kap. 3.3).
>    - Neues Model `EinheitVerbrauch` (Kap. 3.4) inkl. Check-Constraint `vs_code IN ('140'…'145')`.
>    - Anpassung `Buchung` / `Buchungssatz`: FK `wirtschaftsjahr` (Kap. 3.5, `on_delete=PROTECT`).
>
> 2. **Migration**
>    - Schema-Migration für die neuen Tabellen.
>    - Daten-Migration (Kap. 6.2) — pro Bestandsobjekt ein erstes WJ anlegen, bestehende Konten und Buchungen daran binden, `KontoVerteilerSchluessel` aus `konto.vs` materialisieren.
>
> 3. **Services**
>    - `services/wirtschaftsjahr.py` mit `folgejahr_eroeffnen_batch()` und den drei Kopier-Funktionen (`_kopiere_konten`, `_kopiere_vs_zuordnungen`, `_kopiere_einheit_verbrauch`) — Pseudocode in Kap. 5.5–5.8.
>    - Pro Objekt eigene `transaction.atomic()`-Klammer.
>
> 4. **Wizard**
>    - Neuer Schritt 2c im WEG-Objektanlage-Wizard (Kap. 4.2). UI-Komponente nach Muster der bestehenden Schritte.
>    - Erweiterung des atomaren Commit in Schritt 9 (Kap. 4.4): WJ vor Kontenrahmen anlegen, Konten an WJ hängen, `EinheitVerbrauch`-Zeilen je Einheit × VS-Code anlegen.
>
> 5. **Massenimport-Erweiterung**
>    - MI-WEG.xlsx-Vorlagen-Generator um Spalten **AG (WJ-Jahr)** und **AH (WJ-Beginn-Monat)** erweitern.
>    - Excel-Parser akzeptiert beide Spalten; bei Fehlen → Default + Warnung (Kap. 4a.4).
>    - `services/massenimport.py`: Anlage-Reihenfolge erweitern (Kap. 4a.3) — WJ als Schritt 2a vor Bankkonten; Konten an WJ hängen; `KontoVerteilerSchluessel` aus Standard-Kontenrahmen materialisieren.
>    - Preview-JSON um `wj_jahr` und `wj_beginn_monat` ergänzen (Kap. 4a.5).
>
> 6. **Endpunkte**
>    - DRF-ViewSet für `Wirtschaftsjahr` (Listen-/Detail-Endpunkte, read-only).
>    - Zwei dedizierte Endpunkte für die Folgejahr-Massenaktion (`preview` + `commit`, Kap. 5.3).
>
> 7. **Frontend (React)**
>    - Massenaktion in `/objekte/`-Liste: Mehrfachauswahl-Checkboxes, Button "Nächstes Wirtschaftsjahr eröffnen".
>    - Bestätigungs-Dialog mit Tabelle (Kap. 5.2).
>    - Ergebnis-Dialog mit OK/Fehler je Objekt.
>
> 8. **Tests**
>    - Unit-Tests je Service-Funktion mit Fixtures für Vorjahr-WJ, Konten, VS-Zuordnungen, EinheitVerbrauch.
>    - Integrationstest: Wizard 2c → Aktivierung → Folgejahr-Eröffnung → Verifikation der kopierten/zurückgesetzten Daten.
>    - Integrationstest: Massenimport mit AG/AH-Spalten → Verifikation, dass je Zeile ein WJ angelegt und alle Konten daran gehängt sind.
>    - Integrationstest: Massenimport mit alter Vorlage (ohne AG/AH) → Default-Werte + Warnung; Objekt + WJ regulär angelegt.
>    - Edge Cases: Folgejahr existiert bereits; kein Vorjahr-WJ; Buchung außerhalb WJ-Datumsbereich; abgeschlossenes WJ + Buchungsversuch.
>
> **Nicht in dieser Implementierung:** Saldenvortrag, fachliche Bedeutung VS 141–145, HEIWAKO-Import, Jahresabrechnungs-Workflow (`abgeschlossen`-Übergang).
>
> **Code-Stil:** Lean, debuggbar; Service-Layer-Trennung; eine Funktion = eine Aufgabe; Signals nur wo zwingend nötig (hier: keine).

---

*Ende Spezifikation v1.0*
