# API-Vertrag: Externes Abstimmungs-Tool (Reply-Interact-Keypads) — v1.4

**Code-geprüfte Fassung** — ersetzt `API_VERTRAG_VERSAMMLUNGSTOOL_v1_3.md`.
Gegenüber v1.3 geändert (Stand 2026-10-09):

1. **Abschluss blockiert nicht mehr bei TOPs ohne Ergebnis.**
   `POST .../abschluss/` schlägt **nicht** mehr mit HTTP 400 fehl, wenn ein
   beschlusspflichtiger TOP kein Abstimmungsergebnis hat. Solche TOPs gelten als
   **„kein Beschluss gefasst"** (z. B. vertagt oder zurückgezogen): sie bekommen
   **keine Beschlussnummer** und werden im **Ereignis-Log** der EV vermerkt. Das
   einzige verbleibende 400 beim Abschluss ist das Status-Gate (Status ≠
   `ausgecheckt`). Siehe 4.6. Hintergrund: Das Tool kann einen TOP bewusst ohne
   Abstimmung lassen; ein lokales „ohne Abstimmung" wird nicht an immocore
   übertragen, daher darf das Fehlen eines Ergebnisses den Abschluss nicht
   verhindern.
2. **Beschlussnummern in Tagesordnungs-Reihenfolge.** Die fortlaufenden
   Beschlussnummern werden beim Abschluss strikt nach der Tagesordnungs-
   Reihenfolge (hierarchisch inkl. Unterpunkte: 1, 2, 3.1, 3.2, …) vergeben,
   nicht nach Datensatz-/Anlagereihenfolge. Siehe 4.6.

Aus v1.3 unverändert übernommen:

3. **Ergebnishoheit beim Abstimmtool.** `POST .../einzelstimmen/` nimmt
   zusätzlich zu den Einzelvoten einen optionalen `ergebnis`-Block mit den
   fertigen (gewichteten) Summen und der Entscheidung entgegen. Liefert das
   Tool ihn, speichert immocore ihn **1:1** und bewertet **nicht** neu — das
   Tool ist die Beschluss-Autorität (das vor Ort am Beamer verkündete Ergebnis
   muss im Protokoll stehen). Die namentlichen Einzelstimmen bleiben als
   Nachweis erhalten.
4. **Stimmengleichheit = abgelehnt** (kein Mehrheitsbeschluss). Das Tool
   liefert in diesem Fall `ergebnis: "abgelehnt"`.
5. **Kopfprinzip immer verfügbar.** Jede EV hat garantiert eine Kopfprinzip-
   Stimmgrundlage (§ 25 Abs. 2 WEG, eine Stimme je Person) — zusätzlich zu den
   aus Verteilerschlüsseln abgeleiteten Stimmgrundlagen.
6. **Nachweis-Einzelstimmen gewichtet** nach `top.stimmgrundlage` (nicht mehr
   nach dem Legacy-Einzelwert).

## Wer ruft was auf

- **Immocore-Mitarbeiter** (im Immocore-Frontend): legt die EV an, pflegt
  Tagesordnung und Stimmgrundlagen, versendet Einladungen, löst **Checkout**
  und **Checkout-Rücknahme** aus.
- **Das Abstimmtool**: liest Tagesordnung/Teilnehmer, schreibt Anwesenheit
  und — als Beschluss-Autorität — das bewertete Abstimmungsergebnis (nur im
  Status `ausgecheckt`), löst am Ende **Abschluss** und **Protokoll-Upload**
  aus.

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
4. **Während der Versammlung:** je TOP das Tool lokal auswerten und das
   Ergebnis per `POST .../einzelstimmen/` (mit `ergebnis`-Block) an immocore
   übergeben. TOPs, zu denen bewusst kein Beschluss gefasst wird (vertagt,
   zurückgezogen, reiner Bericht), bleiben ohne `einzelstimmen`-Aufruf.
5. **Abschluss:** `POST /versammlungen/{id}/abschluss/` — liefert die
   vergebenen Beschlussnummern zurück. TOPs ohne Ergebnis gelten als „kein
   Beschluss gefasst" und blockieren den Abschluss nicht (siehe 4.6).
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
gerade abgestimmt wird. Der Abstimmungsmodus (`abstimmungsmodus`,
`mehrheit_schwelle`) bestimmt, welche Mehrheit das Tool anwenden muss (siehe
4.4 und Abschnitt 5).

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
bleibt zusätzlich vorhanden (erste/Standard-Grundlage), aber **für die
gewichtete Auswertung immer `stimmkraft_je_grundlage` verwenden**, nicht das
Einzelfeld.

**Kopfprinzip ist garantiert vorhanden:** `stimmkraft_je_grundlage` enthält
für jede EV einen Eintrag zur Kopfprinzip-Stimmgrundlage (Wert `1.0000` je
anwesender Person). Welche `stimmgrundlage_id` das Kopfprinzip ist, zeigt die
Tagesordnung bzw. die Stimmgrundlagen-Liste der EV (`bezeichnung` =
`"Kopfprinzip"`).

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
  },
  "ergebnis": {
    "ja": "2.0000",
    "nein": "1.0000",
    "enthaltung": "0.0000",
    "ergebnis": "abgelehnt"
  }
}
```

**`voten`** (erforderlich): die namentlichen Einzelstimmen, `teilnehmer_id →
"ja"|"nein"|"enthaltung"`. Sie werden als **Nachweis** (`EVStimme`)
gespeichert — jede Stimme mit der nach `top.stimmgrundlage` gewichteten
Stimmkraft des Teilnehmers. Abwesende dürfen nicht abstimmen (HTTP 400, nennt
die betroffenen Namen); unbekannte `teilnehmer_id` → HTTP 400.

**`ergebnis`** (optional, Regelfall ab v1.3): das vom Tool **final bewertete**
Ergebnis. Ist es gesetzt, übernimmt immocore `ja`/`nein`/`enthaltung` (bereits
gewichtete Summen) und `ergebnis` **unverändert** und bewertet nicht neu — das
Tool ist die Beschluss-Autorität. `ergebnis` ist einer von `"angenommen"` /
`"abgelehnt"`; **Stimmengleichheit ist `"abgelehnt"`** (kein
Mehrheitsbeschluss). Weichen die Summen der namentlichen `voten` von den
gemeldeten Summen ab, vermerkt immocore das als Hinweis im Ereignis-Log, ohne
den Vorgang abzulehnen.

Fehlt `ergebnis` (Robustheit / Altpfad), leitet immocore das Summenergebnis
selbst aus den `voten` ab — dann gewichtet nach `top.stimmgrundlage` und
bewertet nach `top.abstimmungsmodus`.

Erneute Erfassung überschreibt das vorherige Ergebnis (Korrektur, unkritisch
bei Retry). Response: aktualisiertes TOP-Objekt (Form wie 4.1, mit befülltem
`abstimmung_ja/_nein/_enthaltung` + `abstimmungsergebnis`).

Für einen TOP, zu dem **kein Beschluss** gefasst wird, ruft das Tool
`einzelstimmen/` gar nicht erst auf — der TOP bleibt dann ohne
`abstimmungsergebnis` und wird beim Abschluss entsprechend behandelt (4.6).

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
weit fortlaufend. Nummern werden **nur** an TOPs mit erfasstem
`abstimmungsergebnis` vergeben.

**Reihenfolge der Nummernvergabe (v1.4-Klarstellung):** Die fortlaufenden
Beschlussnummern werden strikt in **Tagesordnungs-Reihenfolge** vergeben —
hierarchisch inklusive Unterpunkte (1, 2, 3, 3.1, 3.2, 3.3, 3.4, 4, 5, 6),
**nicht** in Datensatz-/Anlagereihenfolge (`id`/pk) und **nicht** in der
Reihenfolge, in der das Tool die Einzelstimmen gesendet hat. immocore sortiert
dazu die abstimmungspflichtigen TOPs vor der Vergabe nach ihrer
Anzeige-Nummer, wobei die Nummer numerisch je Ebene zu interpretieren ist
(`"3.1"` → `(3, 1)`, damit `"10"` **nach** `"2"` einsortiert, nicht davor).
So entspricht die Beschluss-Nummerierung der Reihenfolge im Protokoll.

**Geändert in v1.4:** Ein beschlusspflichtiger TOP **ohne** Ergebnis blockiert
den Abschluss **nicht** mehr (früher HTTP 400 mit Nennung der TOP-Nummern).
Solche TOPs werden als **„kein Beschluss gefasst"** gewertet:
- sie bekommen **keine** Beschlussnummer (fehlen in `beschluesse`),
- jeder betroffene TOP wird im **Ereignis-Log** der EV vermerkt
  (z. B. Typ `abschluss_top_ohne_beschluss`), damit eine *versehentlich*
  ausgelassene Abstimmung nachvollziehbar bleibt.

Der Abschluss schlägt nur noch mit HTTP 400 fehl, wenn der Status ≠
`ausgecheckt` ist. Status wechselt **noch nicht** — erst nach 4.7.

> Optional (Immocore-Ermessen): Statt stillschweigend durchzulaufen, kann das
> Frontend den Abschluss mit einem Bestätigungsschritt versehen
> („X TOP(s) ohne Beschluss — trotzdem abschließen?"). Der API-Endpunkt selbst
> blockiert jedoch nicht.

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

- **Das Tool bewertet, immocore speichert.** Mit dem `ergebnis`-Block aus 4.4
  trägt das Tool die volle Verantwortung für die Entscheidung
  (angenommen/abgelehnt). immocore prüft sie nicht gegen den Abstimmungsmodus
  — das vor Ort verkündete Ergebnis ist maßgeblich und muss im Protokoll
  stehen.
- **TOP ohne Beschluss ≠ Fehler.** Ein beschlusspflichtiger TOP, der ohne
  Ergebnis bleibt (vertagt/zurückgezogen), ist ab v1.4 ein gültiger Endzustand
  und verhindert den Abschluss nicht. Er erscheint nicht in `beschluesse` und
  wird im Ereignis-Log vermerkt. Kehrseite: Eine *vergessene* Abstimmung fällt
  nicht mehr hart auf — der Ereignis-Log-Eintrag ist die Gegenkontrolle.
- **Qualifizierte Mehrheiten liegen beim Tool.** Bei
  `abstimmungsmodus = "qualifizierte_mehrheit"` (Schwelle in
  `mehrheit_schwelle`), `"einstimmigkeit"` oder `"allstimmigkeit"` muss das
  Tool die passende Mehrheit selbst anwenden, bevor es `ergebnis` setzt. Eine
  nur auf einfache Mehrheit gerechnete Auswertung ist für diese Modi falsch —
  entweder rechnet das Tool die Schwelle korrekt, oder der Bearbeiter setzt das
  Ergebnis manuell (und das Tool sendet es erst dann).
- **Stimmengleichheit = abgelehnt.** Kein Mehrheitsbeschluss.
- **Kein Notfallpfad in Immocore.** Es gibt keine Immocore-eigene Oberfläche
  mehr für Anwesenheit/Abstimmung — fällt das Tool aus, gibt es aktuell keinen
  Fallback.
- **`teilnehmer_id` ist EV-spezifisch** — bei jeder neuen Versammlung neu,
  nie über EVs hinweg wiederverwenden.
- **Keine Wahlen-Unterstützung** — nur Ja/Nein/Enthaltung je TOP, keine
  Mehrpersonenwahlen.
- **Reihenfolge 4.6 vor 4.7 ist zwingend** — das PDF ohne die Beschlussnummern
  aus dem Abschluss-Schritt zu bauen, ergibt ein inhaltlich falsches Protokoll.
- **`abstimmung/`** (reine Summenerfassung,
  `{"ja": ..., "nein": ..., "enthaltung": ...}`) existiert weiterhin parallel
  zu `einzelstimmen/`, bewertet aber serverseitig und speichert keine
  namentlichen Stimmen — für das Tool ist ausschließlich `einzelstimmen/`
  relevant.
- **Vollmacht-Dokument-Upload** läuft über den allgemeinen DMS-Endpunkt der
  Immocore-API (Pfad außerhalb des Scopes dieses Vertrags) — die
  zurückgegebene Dokument-ID wird dann in `vollmacht_dokument` referenziert.

## 6. Referenzen

- `docs/CLAUDE_CODE_ANLEITUNG_EV_ABSTIMMTOOL_INTEGRATION_v1_1.md` (fachliche
  Spezifikation)
- `docs/API_VERTRAG_VERSAMMLUNGSTOOL_v1_3.md`,
  `docs/API_VERTRAG_VERSAMMLUNGSTOOL_v1_2.md`,
  `docs/API_VERTRAG_VERSAMMLUNGSTOOL_v1_1.md`,
  `docs/API_VERTRAG_VERSAMMLUNGSTOOL_v1_0.md` (Vorgängerversionen, nur noch
  historisch)
