# IMMOCORE — Rechnungserkennung 3-stufig | Claude Code Implementierungsprompt

**Modul:** 3-stufige Rechnungserkennung mit lernender Buchungslogik
**Version:** 1.3
**Stand:** Mai 2026
**Auftraggeber:** Demme Immobilien Verwaltung GmbH, Coventrystraße 32, 65934 Frankfurt am Main
**KI-Modell:** claude-sonnet-4-6
**Status:** Freigegeben zur Verwendung in Claude Code

> **Änderungen ggü. v1.2:** Routing-Schlüssel ist ausschließlich die Objekt-Erkennung. Stufe 2a/2b zu Stufe 2/3 zusammengefasst. Durchgängige Umbenennung Buchungskonto → Aufwandskonto (konsistent mit OP-Buchung-Modul). Neuer Abschnitt 6.5 + 8.4: Aufwandskonto-Übergabe an Folge-Freigabeschritt (vorbelegt + änderbar; Änderung = Trigger B Lernlogik). API-Body-Feld `aufwandskonto_id` ersetzt `buchungskonto_id`.

---

## 1. Zweck dieses Dokuments

Dieses Dokument ist der vollständige Claude Code Implementierungsprompt für das Modul „Rechnungserkennung mit Lernlogik". Es löst die Versionen 1.0, 1.1 und 1.2 ab. Erweitert bzw. präzisiert werden:

- vereinfachtes, eindimensionales Routing: das Vorhandensein des Objekts ist der einzige Routing-Schlüssel
- durchgängige Umbenennung Buchungskonto → Aufwandskonto (konsistent mit OP-Buchung-Modul, `rechnung.aufwandskonto`)
- Aufwandskonto wird im Folge-Freigabeschritt vorbelegt und nicht erneut als Pflichteingabe verlangt
- lernendes Regelwerk und Frontoffice-Soft-Lock unverändert übernommen aus v1.2
- Pflichtfeld `Objekt.betreuer` und Rolle Frontoffice unverändert übernommen aus v1.2

> **Voraussetzung**
> Phasen 1–3 abgeschlossen. Models `Rechnung`, `Freigabe`, `Konto`, `Person` (mit Rolle Dienstleister), `Objekt` vorhanden. OP-Buchung-Modul (`CLAUDE_CODE_ANLEITUNG_OP_BUCHUNG_v1_1.md`) implementiert: `Rechnung.aufwandskonto`-Feld existiert mit Validierung 50000–55999 / Standardkonto / `direktes_buchen=False`.
>
> KI-OCR-Endpunkt und ZUGFeRD/XRechnung-Parser funktional. Bezug: `IMMOCORE_Ausgangsspezifikation v1.1` Kap. 7 + 7.3.

---

## 2. Workflow im Überblick

### 2.1 Drei Phasen

Erkennung und Freigabe sind sauber getrennt. Zwischen den beiden Phasen entscheidet ein Routing-Schritt anhand der erkannten Objekt-Dimension, wer die Rechnung bearbeitet.

- **Phase A — Erkennung:** automatisch, technisch, ohne Nutzerinteraktion.
- **Phase B — Routing:** technisch, weist Rechnung dem richtigen Bearbeiter zu (Limit-Workflow / Objektbetreuer / Frontoffice).
- **Phase C — Bearbeitung:** Auto-Buchung ODER manuelle Identifikation/Freigabe.

### 2.2 Erkennungsstufen (NEU in v1.3)

Routing-Schlüssel ist ausschließlich, ob das Objekt eindeutig erkannt wurde. Die alte Differenzierung „nur Kreditor erkannt vs. nichts erkannt" entfällt — beide Fälle gehen einheitlich ins Frontoffice.

| Stufe | Bedingung | Status | Routing-Ziel |
|-------|-----------|--------|--------------|
| **1 — Erkannt** | Kreditor + Objekt + Aufwandskonto eindeutig | `erkannt` | Limit-Workflow (`zahlungsfreigabe_grenzen`) |
| **2 — Prüffall Objektbetreuer** | Objekt erkannt; Kreditor und/oder Aufwandskonto offen | `pruefung_match` | Objektbetreuer (`Objekt.betreuer`) |
| **3 — Frontoffice** | Objekt **NICHT** erkannt (egal ob Kreditor erkannt) | `pruefung_match` oder `nicht_erkannt` | Frontoffice-Inbox |

> **Routing-Schlüssel: nur das Objekt**
> Ohne erkanntes Objekt kann kein Objektbetreuer ermittelt werden — die Rechnung geht IMMER ins Frontoffice, unabhängig davon, ob der Kreditor schon erkannt wurde oder nicht. Sobald das Frontoffice das Objekt zugeordnet hat, läuft die Rechnung in den Limit-Workflow weiter (NICHT zurück zum Objektbetreuer).

### 2.3 Bearbeitungspfade

| Bearbeiter | Aktion | Folge |
|------------|--------|-------|
| **Auto** | Stufe 1 + Betrag < Auto-Limit + `erkennungs_konfidenz ≥ 95%` in allen drei Dimensionen | → gebucht (sofort, ohne Nutzer) |
| **Limit-Workflow** | Stufe 1, aber NICHT auto-fähig (Betrag ≥ Limit ODER Konfidenz < 95%) | → `in_pruefung` mit `zugewiesen_an` = Sachbearbeiter / GF gemäß Limit |
| **Objektbetreuer** | Stufe 2 (Objekt erkannt). Doppelfunktion: identifizieren + ggf. freigeben | Nach Identifikation → Limit-Workflow |
| **Frontoffice** | Stufe 3 (Objekt NICHT erkannt). Doppelfunktion: identifizieren + ggf. freigeben | Nach Identifikation → Limit-Workflow |

### 2.4 Entscheidungsbaum

```
Rechnungseingang
      │
      v
  [ Erkennungs-Pipeline ] (Phase A)
      │
      v
  [ Routing ] (Phase B)
      │
      ├── Stufe 1 (alle drei: Kreditor + Objekt + Aufwandskonto) ───┐
      │                                                              v
      │                          Konfidenz ≥ 95% & Betrag < Auto-Limit?
      │                                   /                    \
      │                                  ja                    nein
      │                                   │                      │
      │                                   v                      v
      │                                AUTO              Limit-Workflow
      │                              (gebucht)          (Sachbearb. / GF)
      │
      ├── Stufe 2 (Objekt erkannt; Kreditor und/oder Konto offen) ──┐
      │                                                              │
      │                                                              v
      │                                              Objektbetreuer-Inbox
      │                                                              │
      │                                                              v (nach Identifikation)
      │                                                       Limit-Workflow
      │
      └── Stufe 3 (Objekt NICHT erkannt) ──────────────────────────┐
                                                                    │
                                                                    v
                                                         Frontoffice-Inbox
                                                                    │
                                                                    v (nach Identifikation)
                                                              Limit-Workflow
```

---

## 3. Datenmodell-Erweiterungen

### 3.1 Objekt — Pflichtfeld `betreuer` (unverändert ggü. v1.2)

Wird im WEG-Anlage-Wizard (v1.2) als Pflichtfeld in Schritt 8 ergänzt. Für Bestandsobjekte erfolgt eine Daten-Migration mit Pflicht-Nachpflege.

| Feld | Typ | Anmerkung |
|------|-----|-----------|
| `betreuer` | FK → User (PROTECT) | Pflichtfeld. Routing-Ziel für Stufe 2. |
| `betreuer_vertretung` | FK → User (SET_NULL) | Optional. Bei Abwesenheit (`User.abwesend`) fällt Routing auf Vertretung. |

### 3.2 Rolle Frontoffice (unverändert ggü. v1.2)

Neue Rolle in `Group` oder im Rollensystem (gemäß Ausgangsspezifikation Kap. 10). Inbox sehen alle User mit dieser Rolle. Soft-Lock-Mechanismus 5 Min, Heartbeat alle 30 Sek.

### 3.3 Rechnung — relevante Felder

Das Modul nutzt das bereits im OP-Buchung-Modul angelegte Feld `aufwandskonto`.

| Feld | Typ | Anmerkung |
|------|-----|-----------|
| `aufwandskonto` | FK → Konto (PROTECT) | Bestehend (OP-Buchung-Modul). Validierung: Bereich 50000–55999, `kontoart='Standardkonto'`, `direktes_buchen=False`, `weg=rechnung.weg`. |
| `status` | CharField | Bestehende Choices: `eingegangen` / `in_pruefung` / `freigegeben` / `bezahlt` / `teilbezahlt` / `abgelehnt` / `storniert`. Erweitert um: `erkannt`, `pruefung_match`, `nicht_erkannt`, `gebucht`. |
| `zugewiesen_an` | FK → User (SET_NULL) | Bestehend. NULL signalisiert Frontoffice-Queue (in Verbindung mit `routing_ziel='frontoffice'`). |
| `routing_ziel` | CharField (NEU) | Werte: `'limit_workflow'` / `'objektbetreuer'` / `'frontoffice'`. Wird durch `route_rechnung` gesetzt. |
| `erkennungs_konfidenz` | JSONField (NEU) | `{'kreditor': 0.0–1.0, 'objekt': 0.0–1.0, 'aufwandskonto': 0.0–1.0}`. NULL für nicht erkannte Dimensionen. |

> **WICHTIG — Feld-Umbenennung**
> Das in v1.0/v1.1/v1.2 verwendete Feld `buchungskonto` entfällt vollständig. Durchgängig wird ausschließlich das bereits aus dem OP-Buchung-Modul vorhandene Feld `rechnung.aufwandskonto` verwendet. Eine Daten-Migration ist nicht nötig, da v1.2 noch nicht produktiv ist (falls doch: `rename_field` migration `buchungskonto` → `aufwandskonto`).
> Im UI-Label und in API-Bodies heißt das Feld einheitlich „Aufwandskonto" bzw. `aufwandskonto_id`.

---

## 4. Erkennungs-Pipeline (Phase A)

Pipeline läuft unverändert ggü. v1.2. Drei Erkenner pro Dimension liefern jeweils eine Konfidenz 0.0–1.0. Im Folgenden nur Kurzdarstellung — Vollspezifikation siehe v1.2 Kap. 4.

### 4.1 Kreditor-Erkennung

- IBAN-Match (perfekt → 1.0)
- USt-IdNr-Match (perfekt → 1.0)
- Fuzzy-Name + Adresse (max 0.85)
- KI-Fallback `claude-sonnet-4-6` (mit Erklärungstext)

### 4.2 Objekt-Erkennung

- Mietobjekt-/Liegenschaftsnummer aus Rechnungs-Referenztext
- Adresse-Match gegen `Objekt.adresse` (Straße + PLZ + HausNr)
- Buchungskennung-Match (Format `{objekt_nr}-{kontonummer}`) im Verwendungszweck
- KI-Fallback bei mehreren Kandidaten — wenn unentschieden → `objekt = NULL`

### 4.3 Aufwandskonto-Erkennung

- Lookup in `RechnungsMatchRegel` via `(kreditor_id, objekt_id, leistungstext_hash)`
- Fallback: `kreditor.letztes_aufwandskonto` + Objekt-Konsistenz
- KI-Fallback mit Leistungstext + objektbezogenem Kontenplan
- Validierung: Kandidat muss zum Objekt passen UND im Bereich 50000–55999 / Standardkonto / `direktes_buchen=False` liegen

---

## 5. Stufenermittlung

### 5.1 `ermittle_stufe` — Pseudocode

```python
def ermittle_stufe(rechnung: Rechnung) -> str:
    k = rechnung.kreditor_id is not None
    o = rechnung.objekt_id is not None
    a = rechnung.aufwandskonto_id is not None

    if k and o and a:
        return 'erkannt'           # Stufe 1
    if o:
        return 'pruefung_match'    # Stufe 2 (Objektbetreuer)
    # Objekt fehlt -> Stufe 3 (Frontoffice)
    if k:
        return 'pruefung_match'    # nur Kreditor, kein Objekt
    return 'nicht_erkannt'         # gar nichts erkannt
```

### 5.2 `konfidenz_min`

```python
def konfidenz_min(rechnung: Rechnung) -> float:
    werte = [
        rechnung.erkennungs_konfidenz.get('kreditor', 0.0),
        rechnung.erkennungs_konfidenz.get('objekt', 0.0),
        rechnung.erkennungs_konfidenz.get('aufwandskonto', 0.0),
    ]
    return min(werte) if werte else 0.0
```

---

## 6. Routing-Logik (Phase B)

### 6.1 `route_rechnung` — Pseudocode

```python
def route_rechnung(rechnung: Rechnung) -> None:
    stufe = ermittle_stufe(rechnung)
    rechnung.status = stufe

    # Stufe 1 — Limit-Workflow
    if stufe == 'erkannt':
        rechnung.routing_ziel = 'limit_workflow'
        grenzen = rechnung.objekt.zahlungsfreigabe_grenzen
        freigabe_stufe = ermittle_freigabestufe(rechnung.betrag, grenzen)

        # Auto-Buchung nur wenn Auto-Stufe UND Konfidenz >= 95%
        if (freigabe_stufe['rolle'] == 'auto'
                and konfidenz_min(rechnung) >= 0.95):
            buche_rechnung(rechnung)        # Status -> 'gebucht'
            return

        # Sonst manuelle Freigabe gemaess Limit-Stufe
        rechnung.status = 'in_pruefung'
        rechnung.zugewiesen_an = ermittle_freigabeperson(
            rechnung.objekt, freigabe_stufe
        )
        starte_eskalations_task(rechnung, freigabe_stufe['frist_tage'])
        return

    # Stufe 2 — Objektbetreuer (Objekt erkannt)
    if rechnung.objekt_id is not None:
        rechnung.routing_ziel = 'objektbetreuer'
        betreuer = rechnung.objekt.betreuer
        if betreuer.abwesend and rechnung.objekt.betreuer_vertretung:
            betreuer = rechnung.objekt.betreuer_vertretung
        rechnung.zugewiesen_an = betreuer
        return

    # Stufe 3 — Frontoffice (Objekt nicht erkannt)
    rechnung.routing_ziel = 'frontoffice'
    rechnung.zugewiesen_an = None      # geteilte Inbox via Rolle
```

> **Vereinfachung ggü. v1.2**
> v1.2 differenzierte zwischen Stufe 2a (Objekt erkannt → Objektbetreuer) und Stufe 2b (nur Kreditor → Frontoffice). v1.3 vereinfacht: das Vorhandensein des Objekts ist der einzige Routing-Schlüssel. Stufe 2b wird Teil von Stufe 3. Damit gibt es genau drei Routing-Pfade: Limit-Workflow, Objektbetreuer, Frontoffice.

### 6.2 Routing-Matrix

| Kreditor erk. | Objekt erk. | Aufwandskonto erk. | Stufe | Routing-Ziel |
|---------------|-------------|--------------------|-------|--------------|
| ja | ja | ja | 1 — `erkannt` | Limit-Workflow |
| ja | ja | nein | 2 — Prüffall | Objektbetreuer |
| nein | ja | ja | 2 — Prüffall | Objektbetreuer |
| nein | ja | nein | 2 — Prüffall | Objektbetreuer |
| ja | nein | — | 3 — Prüffall | Frontoffice |
| nein | nein | — | 3 — `nicht_erkannt` | Frontoffice |

### 6.3 Doppelfunktion bei Identifikation

Sowohl Objektbetreuer (Stufe 2) als auch Frontoffice (Stufe 3) haben in der UI zwei Aktionen mit unterschiedlicher Wirkung. Pflichtfeld in der Identifikations-Maske ist **Aufwandskonto** — kein Buchungskonto.

| Button | Wirkung | Voraussetzung |
|--------|---------|---------------|
| **Identifizieren + Speichern** | Erzeugt Match-Regel; Status → `erkannt`; ruft `route_rechnung` erneut auf → Limit-Workflow. | Pflichtfelder Kreditor, Objekt, Aufwandskonto vollständig. |
| **Identifizieren + Freigeben** | Wie oben + direkter Sprung `erkannt` → `freigegeben` (überspringt `in_pruefung`). | Bearbeiter ist in der Limit-Stufe der Rechnung als Freigeber konfiguriert (siehe `darf_direkt_freigeben`). |
| **Ablehnen** | Status → `abgelehnt`; Begründung Pflicht; KEIN Lerneffekt. | Begründungstext eingegeben. |

### 6.4 `darf_direkt_freigeben`

```python
def darf_direkt_freigeben(rechnung: Rechnung, bearbeiter: User) -> bool:
    grenzen = rechnung.objekt.zahlungsfreigabe_grenzen
    stufe = ermittle_freigabestufe(rechnung.betrag, grenzen)

    if stufe['rolle'] == 'auto':
        # Direktes Buchen — nach Identifikation ist Konfidenz immer 1.0
        # (Bearbeiter-Bestaetigung).
        return True

    if stufe['rolle'] == 'sachbearbeiter':
        # Frontoffice-User duerfen wie Sachbearbeiter freigeben.
        # Objektbetreuer nur wenn er auch Sachbearbeiter fuer das Objekt ist.
        if bearbeiter.has_role('Frontoffice'):
            return True
        return bearbeiter in rechnung.objekt.sachbearbeiter.all()

    if stufe['rolle'] == 'geschaeftsfuehrer':
        return bearbeiter.has_role('Geschaeftsfuehrer')

    return False
```

### 6.5 Aufwandskonto-Übergabe an Folge-Freigabeschritt (NEU in v1.3)

Kernregel: Wenn ein Bearbeiter (Objektbetreuer oder Frontoffice) im Identifikations-Schritt das Aufwandskonto gesetzt hat, darf der Folge-Freigabeschritt im Limit-Workflow das Aufwandskonto **NICHT erneut** als Pflichteingabe verlangen.

> **Verhalten im Folge-Freigabeschritt**
> - **Vorbelegt:** Das Feld zeigt initial den Wert aus dem Identifikations-Schritt (`rechnung.aufwandskonto`).
> - **Änderbar:** Der Folge-Freigeber kann das Konto ändern. Eine Änderung löst Trigger B (Freigabe-Korrektur) der Lernlogik aus — alte Match-Regel wird auf `veraltet` gesetzt, neue Regel mit `erstellt_aus='freigabe_korrektur'` wird angelegt.
> - **Keine Doppel-Pflichtprüfung:** Das Form bei der Folge-Freigabe macht nur eine Sichtprüfung (`Aufwandskonto != NULL`). Falls aus irgendeinem Grund leer (Datenanomalie): Eingabe wieder Pflicht.

Pseudocode für die Folge-Freigabe-Form-Logik:

```python
def freigabe_form_initial(rechnung: Rechnung) -> dict:
    return {
        'aufwandskonto_id': rechnung.aufwandskonto_id,   # vorbelegt
        'kreditor_id': rechnung.kreditor_id,
        'objekt_id': rechnung.objekt_id,
    }

def freigabe_form_validate(form, rechnung):
    # Pflicht nur als Sichtpruefung — kein erneuter Eingabezwang
    if form.cleaned_data.get('aufwandskonto_id') is None:
        if rechnung.aufwandskonto_id is None:
            raise ValidationError('Aufwandskonto fehlt.')

def freigabe_form_save(form, rechnung, freigeber):
    altes_konto = rechnung.aufwandskonto_id
    neues_konto = form.cleaned_data['aufwandskonto_id']

    if altes_konto != neues_konto:
        # Trigger B — Freigabe-Korrektur
        rechnung.aufwandskonto_id = neues_konto
        aktualisiere_match_regel(
            rechnung, neues_konto,
            erstellt_aus='freigabe_korrektur',
            erstellt_von=freigeber,
        )
    rechnung.save()
```

---

## 7. Lernlogik

### 7.1 Trigger

- **Trigger A** — Identifikation in Prüffall (egal ob Objektbetreuer oder Frontoffice): erzeugt Regel mit `erstellt_aus='pruefung'`.
- **Trigger B** — Aufwandskonto-Korrektur in der Freigabe (auch in der Folge-Freigabe nach Identifikation): alte Regel → `veraltet`; neue Regel mit `erstellt_aus='freigabe_korrektur'`.
- **Trigger C** — Manuelle Erfassung in Stufe 3 (neuer Kreditor): Anlage Person mit Rolle Dienstleister; Regel mit `erstellt_aus='manuell'`.

### 7.2 Idempotenz und Konflikt

- Doppelte Bestätigung gleiche Konto-Wahl: keine neue Regel, `trefferzahl++` + `letzte_anwendung`.
- Pro `(kreditor, objekt, leistungstext_hash)` max. 1 aktive Regel — `unique_together`-Constraint.
- Korrektur ersetzt: alte Regel → `veraltet`, neue Regel → `aktiv`.
- Opt-out: Checkbox „Einzelfall — keine Regel speichern" am Speichern-Dialog.

---

## 8. UI-Anforderungen (React)

### 8.1 Dashboard — Mein Posteingang

Der bestehende Dashboard-Button „Rechnungen zur Prüfung" wird inhaltlich erweitert. Er zeigt mitarbeiterspezifisch alle Rechnungen wo `current_user` betroffen ist:

- **Prüffälle als Objektbetreuer (Stufe 2)** — `zugewiesen_an = current_user`, gelbe Badge
- **Aus Frontoffice-Queue (Stufe 3)** — nur sichtbar wenn `current_user` die Rolle Frontoffice hat, dann `zugewiesen_an = NULL` UND `routing_ziel = frontoffice`; orange Badge mit Lock-Indikator
- **Zur Freigabe (Stufe 1, `in_pruefung`)** — `zugewiesen_an = current_user`, blaue Badge

> **Zähler im Button-Badge**
> Tooltip beim Hover: „3 Prüffälle Objekt, 5 Frontoffice-Queue, 7 Freigaben." Frontoffice-Zähler nur wenn der User die Rolle hat.

### 8.2 Frontoffice-Inbox (eigene Seite)

- URL `/rechnungen/frontoffice` — nur für Rolle Frontoffice.
- Liste aller Rechnungen mit `routing_ziel='frontoffice'` und `zugewiesen_an=NULL`.
- Spalten: Eingang, Erkennungsstufe, erkannter Kreditor (sofern), Betrag, Leistungstext-Auszug, Lock-Status.
- Klick auf Zeile = Lock setzen (5 Min, verlängert sich beim Tippen, Heartbeat alle 30 Sek). Andere Frontoffice-User sehen „In Bearbeitung von <name>".
- Sortierung default: ältester Eingang oben.

### 8.3 Prüffall-Detailansicht (gemeinsam für Stufe 2 und 3)

- Linke Spalte: PDF-Vorschau / XRechnung-Strukturansicht.
- Rechte Spalte oben: drei Karten **Kreditor / Objekt / Aufwandskonto**, jede mit Status-Badge. Erkannte Karten ausgegraut, fehlende hervorgehoben.
- Bei Stufe 3 (Frontoffice): Objekt-Auswahl prominenter; Hinweis-Banner: „Nach Identifikation läuft die Rechnung in den regulären Limit-Workflow."
- Bei Stufe 2 (Objektbetreuer): Hinweis-Banner: „Sie bearbeiten als Objektbetreuer von `<Objekt-Nr>`."
- **Aufwandskonto-Auswahl:** Top-3 historische Kandidaten + KI-Vorschlag + Suche im Objekt-Kontenplan. Validierung clientseitig: Bereich 50000–55999, Standardkonto, `direktes_buchen=False`, `weg=rechnung.weg`.
- Aktions-Buttons: „Identifizieren + Speichern" (immer) | „Identifizieren + Freigeben" (nur wenn `darf_direkt_freigeben` True) | „Ablehnen".
- Tooltip am gesperrten Freigabe-Button: „Betrag über Ihrem Freigabelimit — wird nach Identifikation eskaliert."
- Lernhinweis + Opt-out-Checkbox „Einzelfall — keine Regel speichern".

> **WICHTIG — kein Feld „Buchungskonto" mehr**
> Das früher in v1.0/v1.1/v1.2 verwendete Feld „Buchungskonto" entfällt vollständig. Im Prüffall existiert ausschließlich das Feld „Aufwandskonto". Hintergrund: Konsistenz mit dem OP-Buchung-Modul (`rechnung.aufwandskonto`). Das Aufwandskonto wird im Identifikations-Schritt gesetzt und im Folge-Freigabeschritt vorbelegt — siehe nächster Abschnitt 8.4.

### 8.4 Folge-Freigabe-Maske (NEU in v1.3)

Wenn nach Identifikation durch Objektbetreuer/Frontoffice eine weitere Freigabe nach Limit-Workflow nötig ist, gilt für die Freigabe-Maske des Folge-Bearbeiters:

- Das Feld Aufwandskonto ist mit dem Wert aus dem Identifikations-Schritt vorbelegt.
- Das Feld ist nicht erneut Pflichteingabe (Sichtprüfung `!= NULL` reicht).
- Der Freigeber kann das Aufwandskonto bei Bedarf ändern.
- Eine Änderung löst Trigger B (Freigabe-Korrektur) der Lernlogik aus — die alte Match-Regel wird auf `veraltet` gesetzt, eine neue mit `erstellt_aus='freigabe_korrektur'` angelegt.
- Toast-Hinweis bei Änderung: „Regel wird aktualisiert: `<Kreditor>` / `<Objekt>` / `<Leistungstext>` → neues Konto."
- Optional Checkbox „Nicht als Regel speichern" — unterdrückt Trigger B.

### 8.5 Wizard-Erweiterung (unverändert ggü. v1.2)

- WEG-Anlage-Wizard v1.2 Schritt 8 („Freigabe & Verantwortliche"): Felder `betreuer` (Pflicht) und `betreuer_vertretung` (optional).
- Validierung: Betreuer muss min. eine Rolle aus `{Sachbearbeiter, Geschaeftsfuehrer, Administrator, Frontoffice}` haben.

### 8.6 Regel-Verwaltung (unverändert ggü. v1.2)

- Seite `/admin/rechnungen/match-regeln` (Admin + Buchhalter).
- Filter: Kreditor, Objekt, Status, `erstellt_aus`.
- Aktion: manuell deaktivieren ohne Rechnungsänderung.

---

## 9. API-Endpunkte

| Methode | Pfad | Beschreibung |
|---------|------|--------------|
| `POST` | `/rechnungen/{id}/erkennung-ausfuehren/` | Pipeline manuell anstoßen |
| `GET` | `/rechnungen/?routing_ziel=frontoffice&zugewiesen_an=null` | Frontoffice-Inbox |
| `GET` | `/rechnungen/?zugewiesen_an=me` | Mein Posteingang |
| `GET` | `/rechnungen/{id}/erkennungs-log/` | Audit-Trail |
| `POST` | `/rechnungen/{id}/lock/` | Frontoffice-Lock setzen (Body: leer) |
| `DELETE` | `/rechnungen/{id}/lock/` | Lock lösen |
| `POST` | `/rechnungen/{id}/lock/heartbeat/` | Lock-Verlängerung (alle 30 Sek von UI) |
| `POST` | `/rechnungen/{id}/identifizieren/` | Body: `{kreditor_id, objekt_id, aufwandskonto_id, modus: 'speichern'\|'freigeben', lernen: true}` |
| `POST` | `/rechnungen/{id}/freigeben/` | Body: `{aufwandskonto_id}` (optional, nur bei Änderung) |
| `POST` | `/rechnungen/{id}/ablehnen/` | Body: `{begruendung}` |
| `POST` | `/rechnungen/{id}/manuell-erfassen/` | Stufe 3: Vollerfassung |
| `GET/POST/PATCH/DELETE` | `/match-regeln/...` | CRUD |

> **Body-Format `/identifizieren/` — Änderung ggü. v1.2**
> Das Body-Feld heißt nun `aufwandskonto_id` (vorher: `buchungskonto_id`). Das Backend prüft: Konto existiert UND `weg=rechnung.weg` UND Bereich 50000–55999 UND Standardkonto UND `direktes_buchen=False`. Bei Verstoß HTTP 400 mit `detail='Aufwandskonto-Validierung fehlgeschlagen: <Grund>'`.

---

## 10. Tests

### 10.1 Unit-Tests

- `normalisiere_leistungstext` + `leistungstext_hash`.
- `match_kreditor`: IBAN = 1.0; Fuzzy-Name max 0.85.
- Stufenableitung: 8 Kombinationen aus `(k, o, a)` → korrekte Stufe (1, 2, 3).
- `konfidenz_min` mit fehlenden Dimensionen (0.0).
- `darf_direkt_freigeben`: alle Limit-Stufen × Bearbeiter-Rollen-Kombinationen (Frontoffice / Objektbetreuer / Sachbearbeiter / GF).
- `RechnungsBearbeitungsLock`: Heartbeat verlängert; Ablauf nach 5 Min.
- Aufwandskonto-Validierung: Konto außerhalb 50000–55999 → `ValidationError`; `direktes_buchen=True` → `ValidationError`; falsches WEG → `ValidationError`.
- Folge-Freigabe-Form: leere Auswahl bei vorhandenem `rechnung.aufwandskonto` → kein Fehler; Änderung → Trigger B.

### 10.2 Integrations-Tests — Workflow-Pfade

- **Pfad 1** — Stufe 1, Konfidenz 98%, Betrag 250 € → AUTO gebucht.
- **Pfad 2** — Stufe 1, Konfidenz 92%, Betrag 250 € → NICHT auto, `in_pruefung` an Sachbearbeiter.
- **Pfad 3** — Stufe 1, Konfidenz 98%, Betrag 5.000 € → `in_pruefung` an GF (Limit greift).
- **Pfad 4** — Stufe 2 (Objekt erkannt, Aufwandskonto fehlt) → Routing Objektbetreuer → Identifizieren+Freigeben → `freigegeben`.
- **Pfad 5** — Stufe 2 (nur Objekt erkannt, Kreditor + Aufwandskonto fehlen) → Routing Objektbetreuer.
- **Pfad 6** — Stufe 3 (nur Kreditor erkannt, Objekt fehlt) → Routing Frontoffice → Identifizieren → Limit-Workflow Sachbearbeiter.
- **Pfad 7** — Stufe 3 (nichts erkannt) → Routing Frontoffice → Identifizieren+Manuell-Erfassen → Limit-Workflow.
- **Pfad 8** — Identifikation durch Objektbetreuer (Aufwandskonto gesetzt) → Folge-Freigabe Sachbearbeiter: Aufwandskonto vorbelegt, kein Pflicht-Eingabezwang, unverändert speicherbar.
- **Pfad 9** — Wie 8, aber Sachbearbeiter ändert Aufwandskonto → alte Regel `veraltet`, neue Regel mit `erstellt_aus='freigabe_korrektur'`.
- **Pfad 10** — Wie 9, aber Opt-out-Checkbox „Nicht als Regel speichern" gesetzt → keine Regelaktualisierung.
- **Pfad 11** — Frontoffice-Lock: User A öffnet, User B sieht Lock; A schickt Heartbeat, B kann nicht übernehmen; A schließt → B übernimmt.
- **Pfad 12** — Betreuer abwesend → Vertretung übernimmt Stufe 2.
- **Pfad 13** — KEIN `buchungskonto`-Feld mehr in API: `POST /identifizieren/` mit Legacy-Feld `buchungskonto_id` → HTTP 400 „Unbekanntes Feld".

---

## 11. Migration und Roll-out

- **Migration A:** Falls Vorgängerversion produktiv (unwahrscheinlich, da v1.2 noch nicht ausgerollt): `rename_field Rechnung.buchungskonto → Rechnung.aufwandskonto`. Alternativ: Datenmigration (alte Werte kopieren) + alten Field entfernen.
- **Migration B:** Bestandsrechnungen im Status `erfasst` durchlaufen Erkennungs-Pipeline.
- **Migration C:** API-Konsumenten informieren — Body-Feld `buchungskonto_id` ist entfernt, neues Feld `aufwandskonto_id`.
- **Frontend-Komponentennamen:** `BuchungskontoAuswahl` → `AufwandskontoAuswahl` (oder neutraler `KontoAuswahl` mit Prop `kind='aufwand'`).
- **i18n-Keys:** `feld.buchungskonto` → `feld.aufwandskonto` in `messages/de.json`.

---

## 12. Wichtige Hinweise für die Implementierung

> **ROUTING NACH OBJEKT-ERKENNUNG**
> Das Vorhandensein des Objekts ist der einzige Routing-Schlüssel. Keine Differenzierung mehr nach Stufe 2a/2b. Objekt erkannt → Objektbetreuer; Objekt nicht erkannt → Frontoffice (egal ob Kreditor erkannt).

> **AUFWANDSKONTO STATT BUCHUNGSKONTO**
> Durchgängige Umbenennung. Im UI, in API-Bodies, in der Datenbank, in i18n-Keys, in Test-Fixtures, in der Doku. Konsistenz mit OP-Buchung-Modul (`rechnung.aufwandskonto`). Validierung: 50000–55999, Standardkonto, `direktes_buchen=False`, `weg=rechnung.weg`.

> **KEINE DOPPELABFRAGE IM FOLGE-FREIGABESCHRITT**
> Wenn der Identifikator (Objektbetreuer/Frontoffice) das Aufwandskonto bereits gesetzt hat, darf der Folge-Freigeber das Konto nicht erneut als Pflichteingabe bekommen. Vorbelegt + änderbar; eine Änderung löst Trigger B der Lernlogik aus.

> **95% NUR FÜR AUTO-BUCHUNG**
> Die 95%-Schwelle ist ein zusätzliches Kriterium AN DER AUTO-STUFE — nicht an Stufe 1 als Ganzes. Stufe-1-Rechnungen mit Konfidenz < 95% laufen ganz normal in den Limit-Workflow (mit manueller Sichtung), auch wenn der Betrag unter dem Auto-Limit liegt. Begründung: ‚gerade so erkannt' soll nicht ohne Sichtung gebucht werden.

> **FRONTOFFICE IST GETEILTE INBOX**
> Mehrere User können die Rolle Frontoffice haben. Soft-Lock von 5 Minuten beim Bearbeiten verhindert Doppelbearbeitung. Heartbeat alle 30 Sekunden verlängert den Lock während aktiver Bearbeitung.

> **NACH IDENTIFIKATION IMMER LIMIT-WORKFLOW**
> Egal ob Objektbetreuer (Stufe 2), Frontoffice (Stufe 3) oder Doppelfunktion-Freigabe — nach Identifikation greift der reguläre Limit-Workflow gemäß `zahlungsfreigabe_grenzen`. KEIN Rückweg zum Objektbetreuer aus Frontoffice und kein Sonderpfad.

> **OBJEKTSPEZIFISCHE REGELN, SOFORTIGES LERNEN**
> Match-Regeln gelten je `(kreditor, objekt, leistungstext_hash)`. Jede manuelle Korrektur lernt sofort, mit optionaler Opt-out-Checkbox.

---

## 13. Claude Code Prompt — Direktverwendung

Folgender Block kann unverändert in Claude Code eingefügt werden:

```
Lies IMMOCORE_Ausgangsspezifikation.docx Kapitel 7,
CLAUDE_CODE_ANLEITUNG_OP_BUCHUNG_v1_1.md (Aufwandskonto-Modell)
sowie IMMOCORE_ClaudeCode_Rechnungserkennung_3stufig_v1_3.md vollständig.

Phasen 1-3 sind abgeschlossen. OP-Buchung-Modul ist implementiert
(Rechnung.aufwandskonto-Feld vorhanden mit Validierung).

Erweitere den Rechnungs-Lifecycle um drei Erkennungsstufen mit
objekt-basiertem Routing, geteilter Frontoffice-Inbox und lernendem
Match-Regelwerk:

  1. Felder Rechnung.routing_ziel + Rechnung.erkennungs_konfidenz
     hinzufuegen. Status-Choices um 'erkannt', 'pruefung_match',
     'nicht_erkannt', 'gebucht' erweitern.
  2. Pflichtfeld Objekt.betreuer + optional betreuer_vertretung
     anlegen. Datenmigration mit Pflicht-Nachpflege.
  3. Rolle Frontoffice anlegen.
  4. Model RechnungsMatchRegel mit unique_together
     (kreditor, objekt, leistungstext_hash, status='aktiv').
  5. Model RechnungsBearbeitungsLock (5 Min, Heartbeat 30 Sek).
  6. Erkennungs-Pipeline (Spec Kap. 4): Kreditor / Objekt /
     Aufwandskonto. Validierung Aufwandskonto-Kandidaten:
     50000-55999, Standardkonto, direktes_buchen=False, weg-Match.
  7. ermittle_stufe (Spec Kap. 5.1) — drei Stufen, Routing-Schluessel
     ist ausschliesslich rechnung.objekt_id.
  8. route_rechnung (Spec Kap. 6.1) inkl. 95%-Auto-Schwelle.
  9. darf_direkt_freigeben (Spec Kap. 6.4).
 10. API-Endpunkte (Spec Kap. 9). Body-Feld heisst aufwandskonto_id,
     NICHT buchungskonto_id.
 11. Lernlogik in identifizieren-Endpoint (Trigger A) +
     Freigabe-Korrektur-Hook (Trigger B) + manuelle Erfassung
     (Trigger C). Spec Kap. 7.
 12. Folge-Freigabe-Form (Spec Kap. 6.5 + 8.4):
     - Aufwandskonto vorbelegt aus rechnung.aufwandskonto
     - keine erneute Pflichteingabe (Sichtpruefung != NULL reicht)
     - Aenderung loest Trigger B aus
     - optionale Opt-out-Checkbox unterdrueckt Trigger B.
 13. Wizard v1.2 Schritt 8 erweitern (Spec Kap. 8.5).
 14. React-UI (Spec Kap. 8):
     - Dashboard-Button mit drei Zaehlern
     - Frontoffice-Inbox-Seite mit Lock-Anzeige
     - Pruefall-Detail mit drei Karten Kreditor/Objekt/Aufwandskonto
     - Aktions-Buttons inkl. bedingtem Freigabe-Button
     - Folge-Freigabe-Maske mit vorbelegtem, aenderbarem Aufwandskonto
     - Regel-Verwaltung
     - Komponentennamen Buchungskonto* -> Aufwandskonto*
     - i18n: feld.buchungskonto -> feld.aufwandskonto
 15. Tests: Unit + Integration Pfade 1-13 (Spec Kap. 10).
 16. Datenmigration: Erkennungslauf auf Bestandsrechnungen.

Anforderungen:
  - Match-Regeln objektspezifisch
  - unique_together (kreditor, objekt, leistungstext_hash, 'aktiv')
  - Idempotenz: doppelte Bestaetigung = trefferzahl++, keine neue Regel
  - Alle Erkennungslaeufe in RechnungsErkennungsLog protokollieren
  - KI-Modell fuer optionalen KI-Fallback: claude-sonnet-4-6
  - Aufwandskonto-Validierung: 50000-55999 / Standardkonto /
    direktes_buchen=False / weg=rechnung.weg
  - Bei Vertretung: Objekt.betreuer.abwesend = True ->
    Routing an betreuer_vertretung
  - Frontoffice-Lock: 5 Min, Heartbeat alle 30 Sek
  - Suffix .910 bleibt gesperrt (Konsistenz mit WEG-Wizard v1.2)
  - GoBD: keine Buchungs-/Buchungssatz-Loeschungen, alle Korrekturen
    via Stornobuchungen (separates Modul)
  - Keine Buchungslogik in Views/Models, nur in services/.
```

---

## 14. Dokumentenmetadaten

| Feld | Wert |
|------|------|
| Auftraggeber | Demme Immobilien Verwaltung GmbH |
| Adresse | Coventrystraße 32, 65934 Frankfurt am Main |
| Dokument-Typ | Claude Code Implementierungsprompt |
| Modul | 3-stufige Rechnungserkennung mit lernender Buchungslogik |
| Bezug | `IMMOCORE_Ausgangsspezifikation v1.1` Kap. 7 + 7.3; `CLAUDE_CODE_ANLEITUNG_OP_BUCHUNG_v1_1.md`; `IMMOCORE_ClaudeCode_WEG_Objektanlage v1.2` Schritt 8 |
| Phase | Erweiterung Phase 3 / Phase 5 |
| KI-Modell | `claude-sonnet-4-6` |
| Version | 1.3 |
| Stand | Mai 2026 |
| Änderungen ggü. v1.2 | Routing-Schlüssel auf Objekt-Erkennung vereinfacht (Stufe 2a/2b zu Stufe 2/3 zusammengefasst). Durchgängige Umbenennung Buchungskonto → Aufwandskonto. Neuer Abschnitt 6.5 + 8.4: Aufwandskonto-Übergabe an Folge-Freigabeschritt (vorbelegt + änderbar; Änderung = Trigger B Lernlogik). API-Body-Feld `aufwandskonto_id` ersetzt `buchungskonto_id`. |
| Status | Freigegeben zur Verwendung in Claude Code |

*Demme Immobilien Verwaltung GmbH | Vertraulich*
