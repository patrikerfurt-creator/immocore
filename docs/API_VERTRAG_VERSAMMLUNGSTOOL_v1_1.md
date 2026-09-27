# API-Vertrag: Externes Abstimmungs-Tool (Reply-Interact-Keypads) — v1.1

Ersetzt `API_VERTRAG_VERSAMMLUNGSTOOL_v1_0.md`. Grund: die EV-Spezifikation
`CLAUDE_CODE_ANLEITUNG_EV_ABSTIMMTOOL_INTEGRATION_v1_1.md` ändert das
Stimmkraft- und Statusmodell so, dass mehrere Stellen des v1.0-Vertrags nicht
mehr stimmen. **Falls der externe Entwickler bereits gegen v1.0 implementiert,
bitte dieses Dokument vor Weiterarbeit mit ihm teilen.**

## Was sich gegenüber v1.0 ändert (Kurzfassung)

1. `stimmkraft` (einzelner Wert je Teilnehmer) → Liste
   `stimmkraft_je_grundlage` (ein Wert je Stimmgrundlage).
2. Jeder Tagesordnungspunkt hat jetzt eine `stimmgrundlage` (Objekt mit
   id + Anzeige-Bezeichnung) — das Tool muss sie **anzeigen**, damit der
   Versammlungsleiter weiß, mit welcher Gewichtung gerade abgestimmt wird.
3. `GET .../quorum/` liefert jetzt eine Liste je Stimmgrundlage statt einer
   Zahl.
4. Begriff **„Check-in" ist jetzt eindeutig nur die Anwesenheitserfassung**
   vor Ort (unverändert `PATCH /ev-teilnehmer/`). Die Rückgabe von Ergebnis +
   Protokoll nach der Versammlung heißt **„Abschluss"** und
   **„Protokoll-Upload"** (zwei neue, getrennte Schritte — siehe unten).
5. Schreibzugriffe (`PATCH /ev-teilnehmer/`, `POST .../einzelstimmen/`) sind
   jetzt **nur im EV-Status `ausgecheckt`** erlaubt — vorher und nachher
   liefert die API 400/403.
6. Neu: **das Tool erzeugt das fertige Protokoll-PDF selbst** und lädt es
   hoch — dafür muss es zuerst die serverseitig vergebenen Beschlussnummern
   abholen (Schritt „Abschluss", liefert die Nummern zurück), bevor es das
   PDF baut und hochlädt (Schritt „Protokoll-Upload").

## 1. Auth — unverändert

`POST /api/v1/auth/token/` → JWT (Access 8h, Refresh 7 Tage). Echter
Mitarbeiter-Login. Details siehe v1.0 Abschnitt 1.

**Offen (noch ungeklärt):** Der angemeldete Mitarbeiter wird bislang nur auf
`IsAuthenticated` geprüft, nicht objekt-/mandantenbezogen eingeschränkt. Mit
dem neuen Datei-Upload (Protokoll-PDF) ist das nachzuschärfen, sobald das
Tool an mehr als einen Verwalter/Mandanten geht — für den aktuellen
Einzelbetrieb unkritisch.

## 2. Ablauf (aktualisiert)

1. **Vorher (online):** Login → Tagesordnung + Teilnehmerliste inkl.
   Stimmkraft **je Stimmgrundlage** abrufen, lokal cachen.
2. **Checkout durch Immocore-Sachbearbeiter:** EV-Status wechselt zu
   `ausgecheckt` — **erst ab jetzt** akzeptiert die API Schreibzugriffe vom
   Tool. Vorher gibt jeder Schreibversuch einen Fehler zurück (keine
   Kulanz mehr wie in v1.0).
3. **Check-in (Anwesenheit, lokal/offline):** wie v1.0 — Outbox-Pattern,
   `PATCH /ev-teilnehmer/{id}/` sobald wieder online.
4. **Während der Versammlung (offline):** Keypad-Stimmen je TOP sammeln,
   TOP-Stimmgrundlage im UI anzeigen (Punkt 2 oben).
5. **Danach, Schritt 1 — Abschluss:** alle `einzelstimmen`-Ergebnisse
   übertragen, dann `POST /versammlungen/{id}/abschluss/` aufrufen →
   Response enthält die vergebenen Beschlussnummern je TOP.
6. **Danach, Schritt 2 — Protokoll-Upload:** Tool baut das Protokoll-PDF
   (mit den Beschlussnummern aus Schritt 5) und lädt es per
   `POST /versammlungen/{id}/protokoll-upload/` hoch.

Alle Schreib-Endpunkte außer dem Protokoll-Upload überschreiben bei
erneuter Erfassung den vorherigen Stand — Retry nach Verbindungsabbruch ist
unkritisch. Der Protokoll-Upload ist **nicht** retry-sicher gegen doppelten
Aufruf mit unterschiedlichem Inhalt (das zweite Hochladen ersetzt das PDF)
— das Tool sollte nach einem bestätigten Upload keinen zweiten Versuch mehr
unternehmen.

## 3. Endpunkte

### 3.1 Tagesordnung lesen (geändert)

`GET /versammlungen/{ev_id}/tagesordnung/`

```json
{
  "tagesordnung": [
    {
      "id": "uuid", "ev": "uuid", "nummer": 1, "titel": "...",
      "abstimmungsmodus": "einfache_mehrheit",
      "stimmgrundlage": { "id": "uuid", "bezeichnung": "Kopfprinzip" },
      "abstimmung_ja": "0.0000", "abstimmung_nein": "0.0000",
      "abstimmung_enthaltung": "0.0000",
      "abstimmungsergebnis": ""
    }
  ]
}
```

Neu: `stimmgrundlage` (Objekt statt fehlend). `bezeichnung` ist entweder
„Kopfprinzip" oder die Bezeichnung des zugrunde liegenden
Verteilerschlüssels — im UI des Tools **je TOP sichtbar** darstellen.

### 3.2 Teilnehmer + Stimmkraft lesen (geändert)

`GET /versammlungen/{ev_id}/teilnehmer/`

```json
[
  {
    "id": "uuid (= teilnehmer_id)",
    "person_name": "Max Mustermann",
    "stimmkraft_je_grundlage": [
      { "stimmgrundlage_id": "uuid-kopf", "wert": "1.0000" },
      { "stimmgrundlage_id": "uuid-mea", "wert": "125.5000" }
    ],
    "ist_anwesend": null, "vertreten_durch": null, "vertreter_name": "",
    "vollmacht_dokument": null
  }
]
```

Um den Stimmwert eines Teilnehmers bei einer bestimmten Abstimmung zu
ermitteln: `teilnehmer_id` + `top.stimmgrundlage.id` →
`stimmkraft_je_grundlage[...]` mit passender `stimmgrundlage_id` matchen.
Alles offline machbar, kein zusätzlicher Roundtrip je TOP nötig.

### 3.3 Check-in: Anwesenheit/Vertretung schreiben — unverändert

`PATCH /ev-teilnehmer/{teilnehmer_id}/` — wie v1.0 Abschnitt 3.3.
**Vollmacht-Dokument:** falls beim Check-in vor Ort ein Vollmachts-Scan
anfällt, läuft der Upload über den bestehenden, allgemeinen DMS-Upload-
Endpoint der Immocore-API (Pfad ist zu ergänzen, sobald final — außerhalb
des Scopes dieses EV-spezifischen Vertrags); die zurückgegebene Dokument-ID
wird dann in `vollmacht_dokument` referenziert.

### 3.4 Abstimmungsergebnis je TOP schreiben — unverändert, aber Status-Gate beachten

`POST /tagesordnungspunkte/{top_id}/einzelstimmen/` — wie v1.0 Abschnitt 3.4.
**Neu:** liefert HTTP 400, solange `ev.status != 'ausgecheckt'`.

### 3.5 Quorum lesen (geändert)

`GET /versammlungen/{ev_id}/quorum/`

```json
{
  "je_stimmgrundlage": [
    { "stimmgrundlage_id": "uuid-kopf", "anwesende_stimmkraft": "12.0000", "gesamt_stimmkraft": "20.0000" },
    { "stimmgrundlage_id": "uuid-mea", "anwesende_stimmkraft": "410.25", "gesamt_stimmkraft": "1000.00" }
  ]
}
```

Weiterhin rein informativ, kein Gate auf Abstimmungen.

### 3.6 Checkout-Status prüfen (neu, informativ)

`GET /versammlungen/{ev_id}/` (Detail-Endpoint, bestehend) — `status`-Feld
zeigt an, ob bereits `ausgecheckt` (Schreibzugriffe möglich) oder noch
gesperrt.

### 3.7 Abschluss (neu — Schritt 1 des Rückgabe-Prozesses)

`POST /versammlungen/{ev_id}/abschluss/` — kein Payload nötig.

```json
{
  "beschluesse": [
    { "top_id": "uuid", "beschluss_nummer": 12, "wortlaut": "..." }
  ]
}
```

Schlägt fehl (400), wenn ein abstimmungspflichtiger TOP noch kein Ergebnis
hat. Ab hier ist `ev.status == 'beschluesse_verarbeitet'` **noch nicht**
erreicht — erst nach dem Protokoll-Upload (3.8).

### 3.8 Protokoll-Upload (neu — Schritt 2, schließt die EV ab)

`POST /versammlungen/{ev_id}/protokoll-upload/` — multipart, Feld `datei`
(PDF). Muss **nach** 3.7 aufgerufen werden (Beschlussnummern müssen im PDF
bereits enthalten sein). Setzt `ev.status = 'beschluesse_verarbeitet'`.

```json
{ "dokument_id": "uuid", "dateiname": "protokoll_ev_....pdf" }
```

Fehlerfälle: falscher Dateityp (kein echtes PDF), Datei zu groß, Abschluss
(3.7) wurde noch nicht aufgerufen.

## 4. Wichtige Fallstricke (ergänzt gegenüber v1.0)

- **Reihenfolge zwingend:** Abschluss (3.7) vor Protokoll-Upload (3.8) — das
  PDF ohne die zurückgelieferten Beschlussnummern zu bauen, führt zu einem
  inhaltlich falschen Protokoll.
- **Kein Notfallpfad in Immocore:** Fällt das Tool während der Versammlung
  aus, gibt es aktuell keinen Fallback in Immocore, um Anwesenheit/Stimmen
  stattdessen dort zu erfassen. Das Tool muss entsprechend robust sein
  (Offline-Fähigkeit, lokale Datensicherung).
- **Checkout kann zurückgenommen werden** (`POST .../checkout-zuruecknehmen/`,
  EV-seitig, nicht vom Tool aufgerufen) — falls das passiert, während das
  Tool bereits Daten gecacht hat, muss es seine Teilnehmerliste/Tagesordnung
  neu abrufen, sobald erneut ausgecheckt wird.
- **`teilnehmer_id` ist EV-spezifisch** — unverändert aus v1.0.
- **Keine Wahlen-Unterstützung** — unverändert aus v1.0.

## 5. Referenzen

- `docs/CLAUDE_CODE_ANLEITUNG_EV_ABSTIMMTOOL_INTEGRATION_v1_1.md` (fachliche
  Spezifikation, Begründung der Änderungen)
- `docs/API_VERTRAG_VERSAMMLUNGSTOOL_v1_0.md` (Vorgängerversion, nur noch
  historisch)
