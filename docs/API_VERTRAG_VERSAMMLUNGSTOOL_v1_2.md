# API-Vertrag: Externes Abstimmungs-Tool (Reply-Interact-Keypads) — v1.2

**Finale, code-geprüfte Fassung** — jedes Feld und jede Response-Form in
diesem Dokument wurde am 2026-09-27 direkt gegen den implementierten Code
verifiziert (`backend/apps/versammlung/{models,serializers,views}.py` und
die zugehörigen Services). Ersetzt `API_VERTRAG_VERSAMMLUNGSTOOL_v1_1.md`
(dort waren einige Endpunkte noch geplant, nicht implementiert).

## Wer ruft was auf

- **Immocore-Mitarbeiter** (im Immocore-Frontend): legt die EV an, pflegt
  Tagesordnung, versendet Einladungen, löst **Checkout** und
  **Checkout-Rücknahme** aus.
- **Das Abstimmtool**: liest Tagesordnung/Teilnehmer, schreibt Anwesenheit
  und Abstimmungsergebnisse (nur im Status `ausgecheckt`), löst am Ende
  **Abschluss** und **Protokoll-Upload** aus.

## 1. Auth

`POST /api/v1/auth/token/` → `{"access": "...", "refresh": "..."}` (JWT,
SimpleJWT). Access-Token 8h, Refresh-Token 7 Tage. Echter Mitarbeiter-Login.
Header: `Authorization: Bearer <access>`.
Refresh: `POST /api/v1/auth/token/refresh/` mit `{"refresh": "..."}`.

**Offen:** nur `IsAuthenticated` geprüft, keine Objekt-/Mandanten-Einschränkung.

## 2. EV-Status — der zentrale Gate-Mechanismus

```
entwurf → in_bearbeitung → einladungen_versendet → ausgecheckt → beschluesse_verarbeitet → archiviert
```

`durchgefuehrt` ist ein alter, nicht mehr erreichbarer Statuswert (bleibt nur
für evtl. Altdaten in der DB gültig — für neue EVs irrelevant).

**Schreibzugriffe des Tools sind AUSSCHLIESSLICH im Status `ausgecheckt`
erlaubt:**
- `PATCH /ev-teilnehmer/{id}/` (Felder `ist_anwesend`, `vertreten_durch`,
  `vertreter_name`, `vollmacht_dokument` — **außer** `zusage_status`, das ist
  jederzeit änderbar)
- `POST /tagesordnungspunkte/{id}/einzelstimmen/`
- `POST /tagesordnungspunkte/{id}/abstimmung/`

Außerhalb `ausgecheckt`: HTTP 400 mit
`{"detail": "... kann nur im Status \"ausgecheckt\" erfasst werden (aktuell \"...\")."}`

Den aktuellen Status liest das Tool über `GET /versammlungen/{id}/` (Feld
`status`) — das Tool sollte vor jedem Schreibversuch (oder zumindest beim
Start der Versammlung) prüfen, ob bereits ausgecheckt wurde.

## 3. Ablauf

1. **Login**, dann `GET /versammlungen/{id}/tagesordnung/` +
   `GET /versammlungen/{id}/teilnehmer/` abrufen, lokal cachen.
2. Warten, bis ein Immocore-Mitarbeiter den **Checkout** ausgelöst hat
   (`status` wechselt zu `ausgecheckt`) — vorher lehnt die API alle
   Schreibzugriffe des Tools ab.
3. **Check-in vor Ort:** `PATCH /ev-teilnehmer/{id}/` je Teilnehmer.
4. **Während der Versammlung:** je TOP `POST .../einzelstimmen/`.
5. **Abschluss:** `POST /versammlungen/{id}/abschluss/` — liefert die
   vergebenen Beschlussnummern zurück.
6. **Protokoll-Upload:** Tool baut das Protokoll-PDF (mit den Nummern aus
   Schritt 5) und lädt es hoch: `POST /versammlungen/{id}/protokoll-upload/`.

## 4. Endpunkte

### 4.1 Tagesordnung lesen

`GET /api/v1/versammlungen/{ev_id}/tagesordnung/`

```json
{
  "tagesordnung": [
    {
      "id": "uuid", "ev": "uuid", "nummer": 1, "titel": "...",
      "erlaeuterung": "...", "beschlussvorlage": "...",
      "abstimmungsmodus": "einfache_mehrheit",
      "abstimmungsmodus_display": "Einfache Mehrheit (Ja > Nein)",
      "mehrheit_schwelle": null,
      "stimmgrundlage": { "id": "uuid", "bezeichnung": "Kopfprinzip" },
      "abstimmung_ja": "0.0000", "abstimmung_nein": "0.0000",
      "abstimmung_enthaltung": "0.0000",
      "abstimmungsergebnis": "", "abstimmungsergebnis_display": "",
      "ergebnis_bemerkung": "",
      "triggert_vorgang": false, "triggert_wirtschaftsplan": false
    }
  ],
  "probleme": []
}
```

`stimmgrundlage` ist `null`, falls (im Ausnahmefall) keine gesetzt ist —
im UI des Tools **je TOP anzeigen**, damit klar ist, mit welcher Gewichtung
gerade abgestimmt wird.

### 4.2 Teilnehmer + Stimmkraft lesen

`GET /api/v1/versammlungen/{ev_id}/teilnehmer/`

```json
[
  {
    "id": "uuid (= teilnehmer_id)",
    "ev": "uuid", "person": "uuid", "person_name": "Max Mustermann",
    "stimmkraft": "1.0000",
    "stimmkraft_je_grundlage": [
      { "stimmgrundlage_id": "uuid-kopf", "wert": "1.0000" },
      { "stimmgrundlage_id": "uuid-mea", "wert": "125.5000" }
    ],
    "zusage_status": "zugesagt", "zusage_am": "...", "zusage_quelle": "...",
    "ist_anwesend": null, "anwesenheit_erfasst_am": null,
    "vertreten_durch": null, "vertreten_durch_name": null,
    "vertreter_name": "", "vollmacht_dokument": null,
    "anteile": [
      { "id": "uuid", "eigentumsverhaeltnis": "uuid",
        "einheit_nr_snapshot": "WE 3", "mea_wert_snapshot": "125.5000" }
    ]
  }
]
```

Stimmwert einer Person bei einem bestimmten TOP: `teilnehmer_id` +
`top.stimmgrundlage.id` → in `stimmkraft_je_grundlage` den Eintrag mit
passender `stimmgrundlage_id` suchen. Das ältere Einzelfeld `stimmkraft`
bleibt zusätzlich vorhanden (erste/Standard-Grundlage), aber **für Voten
immer `stimmkraft_je_grundlage` verwenden**, nicht das Einzelfeld.

### 4.3 Anwesenheit/Vertretung schreiben (nur Status `ausgecheckt`)

`PATCH /api/v1/ev-teilnehmer/{teilnehmer_id}/`

```json
{
  "ist_anwesend": true,
  "vertreten_durch": "person-uuid-oder-null",
  "vertreter_name": "Freitext-Fallback",
  "vollmacht_dokument": "dokument-uuid-oder-null"
}
```

Alle Felder optional, nur Übergebenes wird geändert. `zusage_status` kann
im selben Request mitgeschickt werden, ist aber vom Status-Gate ausgenommen.

### 4.4 Abstimmung je TOP schreiben (nur Status `ausgecheckt`)

`POST /api/v1/tagesordnungspunkte/{top_id}/einzelstimmen/`

```json
{
  "voten": {
    "teilnehmer_id_1": "ja",
    "teilnehmer_id_2": "nein",
    "teilnehmer_id_3": "enthaltung"
  }
}
```

Erlaubte Werte: `"ja"`, `"nein"`, `"enthaltung"`. Server berechnet die
Gewichtung automatisch aus `stimmkraft_je_grundlage` zur `top.stimmgrundlage`.
Erneute Erfassung überschreibt das vorherige Ergebnis (Korrektur, unkritisch
bei Retry). Response: aktualisiertes TOP-Objekt (Form wie 4.1, mit befülltem
`abstimmung_ja/_nein/_enthaltung` + `abstimmungsergebnis`).

### 4.5 Quorum lesen (informativ, kein Gate)

`GET /api/v1/versammlungen/{ev_id}/quorum/`

```json
{
  "je_stimmgrundlage": [
    {
      "stimmgrundlage_id": "uuid-kopf",
      "bezeichnung": "Kopfprinzip",
      "anwesende_stimmkraft": "12.0000",
      "gesamt_stimmkraft": "20.0000"
    },
    {
      "stimmgrundlage_id": "uuid-mea",
      "bezeichnung": "010 MEA Gesamt",
      "anwesende_stimmkraft": "410.2500",
      "gesamt_stimmkraft": "1000.0000"
    }
  ]
}
```

### 4.6 Abschluss (Schritt 1 von 2 — löst den Beschlussnummern-Zirkelbezug)

`POST /api/v1/versammlungen/{ev_id}/abschluss/` — kein Payload.

```json
{
  "beschluesse": [
    { "top_id": "uuid", "beschluss_nummer": 12, "wortlaut": "Der Verwaltungsbeirat wird ... gewählt." }
  ]
}
```

`beschluss_nummer` ist eine **Ganzzahl** (kein formatierter String), objekt-
weit fortlaufend. Schlägt mit HTTP 400 fehl, wenn: Status ≠ `ausgecheckt`,
oder ein abstimmungspflichtiger TOP noch kein Ergebnis hat (Fehlermeldung
nennt die betroffenen TOP-Nummern). Status wechselt **noch nicht** — erst
nach 4.7.

### 4.7 Protokoll-Upload (Schritt 2 von 2)

`POST /api/v1/versammlungen/{ev_id}/protokoll-upload/` — `multipart/form-data`,
**Feld-Name exakt `datei`** (PDF). Muss nach 4.6 aufgerufen werden — die
Beschlussnummern aus 4.6 müssen im hochgeladenen PDF bereits enthalten sein.

```json
{ "dokument_id": "uuid", "dateiname": "Protokoll_....pdf" }
```

(HTTP 201). Fehler: 400 wenn Feld `datei` fehlt, kein echtes PDF ist
(Magic-Bytes-Prüfung), zu groß ist, oder Abschluss (4.6) noch nicht gelaufen
ist. Setzt `ev.status = 'beschluesse_verarbeitet'`.

## 5. Wichtige Fallstricke

- **Kein Notfallpfad in Immocore.** Es gibt keine Immocore-eigene
  Oberfläche mehr für Anwesenheit/Abstimmung — fällt das Tool aus, gibt es
  aktuell keinen Fallback.
- **`teilnehmer_id` ist EV-spezifisch** — bei jeder neuen Versammlung neu,
  nie über EVs hinweg wiederverwenden.
- **Keine Wahlen-Unterstützung** — nur Ja/Nein/Enthaltung je TOP, keine
  Mehrpersonenwahlen.
- **Reihenfolge 4.6 vor 4.7 ist zwingend** — das PDF ohne die
  Beschlussnummern aus dem Abschluss-Schritt zu bauen, ergibt ein inhaltlich
  falsches Protokoll.
- **`abstimmung/`** (Summenerfassung, `{"ja": ..., "nein": ..., "enthaltung": ...}`)
  existiert parallel zu `einzelstimmen/`, wird aber vom Tool nicht gebraucht
  — es liefert keine personenbezogene Gewichtung, sondern nur Summen. Für
  das Tool ist ausschließlich `einzelstimmen/` relevant.
- **Vollmacht-Dokument-Upload** läuft über den allgemeinen DMS-Endpunkt der
  Immocore-API (Pfad außerhalb des Scopes dieses Vertrags) — die
  zurückgegebene Dokument-ID wird dann in `vollmacht_dokument` referenziert.

## 6. Referenzen

- `docs/CLAUDE_CODE_ANLEITUNG_EV_ABSTIMMTOOL_INTEGRATION_v1_1.md` (fachliche
  Spezifikation)
- `docs/API_VERTRAG_VERSAMMLUNGSTOOL_v1_1.md`,
  `docs/API_VERTRAG_VERSAMMLUNGSTOOL_v1_0.md` (Vorgängerversionen, nur noch
  historisch)
