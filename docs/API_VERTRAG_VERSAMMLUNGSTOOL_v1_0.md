# API-Vertrag: Externes Abstimmungs-Tool (Reply-Interact-Keypads)

Stand: 2026-09-25. Beschreibt die Anbindung eines externen, separat entwickelten
Tools für elektronische Abstimmungen in Eigentümerversammlungen (WEG) an die
bestehende Immocore-API. Die fachliche Logik (Stimmkraft-Berechnung,
Mehrheitsregeln, Beschluss-Sammlung nach § 24 Abs. 7 WEG) liegt vollständig im
Backend (`apps/versammlung`) — das externe Tool erfasst nur Rohdaten und
schickt sie weiter.

**Scope dieser Anbindung:** nur Beschlussfassung (Ja/Nein/Enthaltung per
Judge-Modus der Keypads). Keine Wahlen/Mehrfachauswahl — dafür gibt es auf
Immocore-Seite aktuell keine passenden Endpunkte.

## 1. Auth

- Login-Endpoint: `POST /api/v1/auth/token/` mit `{"username": "...", "password": "..."}`
  → liefert `{"access": "...", "refresh": "..."}` (SimpleJWT).
- Das Tool meldet sich mit einem **echten Mitarbeiter-Login** an (kein
  separater technischer Account).
- Access-Token gilt **8 Stunden**, Refresh-Token **7 Tage**
  (`config/settings.py`, `SIMPLE_JWT`). Für einen einzelnen Versammlungstag
  reicht ein einmaliges Login vor der Versammlung ohne Refresh-Handling.
- Token als `Authorization: Bearer <access>`-Header auf allen Requests.
- Refresh bei Bedarf: `POST /api/v1/auth/token/refresh/` mit `{"refresh": "..."}`.

## 2. Ablauf (Offline-first)

1. **Vorher (online):** Login → Tagesordnung + Teilnehmerliste der Versammlung
   abrufen, lokal cachen.
2. **Check-in (lokal/offline):** Anwesenheit und Vertretung werden im Tool
   selbst erfasst (kein Netz nötig) und in einer lokalen Outbox-Tabelle
   vorgehalten. Zusätzlich: Zuordnung Keypad-ID ↔ `teilnehmer_id` — das ist
   reine Tool-interne Logik, betrifft die Immocore-API nicht.
3. **Während der Versammlung (offline):** Keypad-Stimmen (1=Ja/2=Nein/
   3=Enthaltung) werden lokal pro Teilnehmer gesammelt.
4. **Danach (online):** Outbox abarbeiten —
   - Anwesenheits-/Vertretungsänderungen per `PATCH /ev-teilnehmer/{id}/`
   - Abstimmungsergebnis je TOP per `POST /tagesordnungspunkte/{id}/einzelstimmen/`

Beide Schreib-Endpunkte überschreiben bei erneuter Erfassung den vorherigen
Stand (keine Duplikate) — ein Retry nach Verbindungsabbruch ist daher
unkritisch.

## 3. Relevante Endpunkte

Alle Pfade unter `/api/v1/`, Auth `IsAuthenticated` (JWT oder Session).

### 3.1 Tagesordnung lesen

`GET /versammlungen/{ev_id}/tagesordnung/`

```json
{
  "tagesordnung": [
    {
      "id": "uuid", "ev": "uuid", "nummer": 1, "titel": "...",
      "erlaeuterung": "...", "beschlussvorlage": "...",
      "abstimmungsmodus": "einfache_mehrheit",
      "abstimmungsmodus_display": "Einfache Mehrheit (Ja > Nein)",
      "mehrheit_schwelle": null,
      "abstimmung_ja": "0.0000", "abstimmung_nein": "0.0000",
      "abstimmung_enthaltung": "0.0000",
      "abstimmungsergebnis": "", "abstimmungsergebnis_display": "",
      "ergebnis_bemerkung": "",
      "triggert_vorgang": false, "triggert_wirtschaftsplan": false
    }
  ],
  "probleme": [ ]
}
```

`abstimmungsmodus` (informativ, wirkt sich nur auf die serverseitige
Mehrheitsberechnung aus, nicht auf das Erfassungsformat):
`einfache_mehrheit`, `qualifizierte_mehrheit`, `einstimmigkeit`,
`allstimmigkeit`, `kein_beschluss`.

### 3.2 Teilnehmer + Stimmkraft lesen

`GET /versammlungen/{ev_id}/teilnehmer/`

```json
[
  {
    "id": "uuid (= teilnehmer_id)",
    "ev": "uuid",
    "person": "uuid", "person_name": "Max Mustermann",
    "stimmkraft": "125.5000",
    "zusage_status": "zugesagt", "zusage_am": "...", "zusage_quelle": "portal",
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

- `stimmkraft` ist der bereits fertig berechnete Stimmwert (Kopf- oder
  Verteilerschlüssel-Prinzip, Snapshot zum Zeitpunkt der Ermittlung) —
  **das Tool muss nicht selbst mit MEA-Werten rechnen.**
- `id` dieses Objekts ist der `teilnehmer_id`, der bei der Stimmerfassung
  (3.4) verwendet wird.
- `stimmkraft`, `anteile`, `person` sind read-only — nur `ist_anwesend`,
  `vertreten_durch`, `vertreter_name`, `vollmacht_dokument`, `zusage_status`
  sind vom Tool aus änderbar (siehe 3.3).

### 3.3 Check-in: Anwesenheit/Vertretung schreiben

`PATCH /ev-teilnehmer/{teilnehmer_id}/`

```json
{
  "ist_anwesend": true,
  "vertreten_durch": "person_uuid_des_vertreters",
  "vertreter_name": "Freitext-Fallback, falls Vertreter keine Person im Stamm ist",
  "vollmacht_dokument": null
}
```

Alle Felder optional — nur was mitgeschickt wird, wird geändert.
`ist_anwesend: null` setzt die Erfassung explizit auf "offen" zurück.
`vollmacht_dokument` referenziert ein bereits im DMS vorhandenes Dokument
(uuid); i.d.R. beim Check-in vor Ort nicht verfügbar — kann leer bleiben und
später nachgetragen werden.

### 3.4 Abstimmungsergebnis je TOP schreiben (namentlich, gewichtet)

`POST /tagesordnungspunkte/{top_id}/einzelstimmen/`

```json
{
  "voten": {
    "teilnehmer_id_1": "ja",
    "teilnehmer_id_2": "nein",
    "teilnehmer_id_3": "enthaltung"
  }
}
```

- Erlaubte Werte: `"ja"`, `"nein"`, `"enthaltung"`.
- Genau das Judge-Y/N/A-Format der Reply-Keypads (Taste 1/2/3).
- Die Gewichtung (`stimmkraft` je Teilnehmer) übernimmt der Server; das Tool
  schickt nur das Rohvotum je Person.
- Server leitet daraus automatisch `abstimmung_ja/_nein/_enthaltung` und
  `abstimmungsergebnis` am TOP ab (ein Bewertungspfad, keine separate
  Summen-Eingabe nötig, wenn `einzelstimmen` genutzt wird).
- Teilnehmer, die nicht abgestimmt haben (z. B. nicht anwesend), einfach
  weglassen — kein Pflichtfeld für alle `teilnehmer_id`s.
- Erneute Erfassung überschreibt das bisherige Ergebnis (Korrektur möglich,
  wird serverseitig protokolliert).

Alternative (hier nicht genutzt, nur zur Abgrenzung): `POST
/tagesordnungspunkte/{top_id}/abstimmung/` mit `{"ja": 16, "nein": 4,
"enthaltung": 3}` — reine Summenerfassung ohne Namensbezug. Für dieses Tool
nicht relevant, da die namentliche Erfassung (`einzelstimmen`) die
Stimmkraft-Gewichtung automatisch mitliefert.

### 3.5 Nur lesend / informativ (optional für das Tool)

- `GET /versammlungen/{ev_id}/quorum/` — anwesende Stimmkraft, rein
  informativ, kein Gate für Abstimmungen.
- `GET /tagesordnungspunkte/{top_id}/stimmen/` — bereits erfasste
  Einzelvoten eines TOP (zur Anzeige/Kontrolle im Tool, z. B. nach
  Wiederverbindung zur Bestätigung, dass der Push angekommen ist).

## 4. Wichtige Fallstricke

- **Enthaltungen zählen nicht in den Nenner** bei einfacher/qualifizierter
  Mehrheit (serverseitige Logik, das Tool muss hier nichts tun).
- **TOP-Sperre nach Einladungsversand:** Neuanlage/Änderung von TOPs ist nach
  Versand der Einladung gesperrt (§ 23 Abs. 2 WEG) — für dieses Tool
  irrelevant, da es TOPs nur liest, nicht anlegt.
- **Keine Wahlen-Unterstützung:** Falls später doch Mehrpersonenwahlen
  (Verwalterbestellung, Beiratswahl) gebraucht werden, fehlt dafür aktuell
  ein passender Endpunkt — das wäre ein separates Anschlussstück.
- **`teilnehmer_id` ist EV-spezifisch:** Derselbe Eigentümer bekommt bei
  jeder neuen Versammlung einen neuen `EVTeilnehmer`-Datensatz (Snapshot der
  Stimmkraft zum jeweiligen Zeitpunkt) — die ID aus einer alten Versammlung
  nicht wiederverwenden.
- **Berechtigungen:** Bisher nur `IsAuthenticated` verifiziert; ob der
  angemeldete Mitarbeiter zusätzlich objektbezogen eingeschränkt wird
  (Mandantenfähigkeit), ist bei Bedarf gesondert zu prüfen, bevor das Tool an
  mehrere Verwalter/Mandanten ausgerollt wird.

## 5. Referenzen im Backend

- Modelle: `backend/apps/versammlung/models.py`
- Views/Endpunkte: `backend/apps/versammlung/views.py`
- Serializer (exakte Feldnamen): `backend/apps/versammlung/serializers.py`
- Fachliche Spec: `docs/IMMOCORE_ClaudeCode_Eigentuemerversammlung_v1_1.md`
