# Spezifikation: EV-Modul — Kataloge, Verteilerschlüssel-Mehrfachauswahl, Checkout/Check-in

Stand: 2026-09-26. Entwurf v1.0 — enthält bewusst offene Punkte, die vor
Umsetzung zu bestätigen sind (siehe jeweils „Offen"). Baut auf
`docs/IMMOCORE_ClaudeCode_Eigentuemerversammlung_v1_1.md` und
`docs/API_VERTRAG_VERSAMMLUNGSTOOL_v1_0.md` auf.

## 0. Überblick der Änderungen

1. Neuer Menübereich **Kataloge**, darin Katalog **Versammlungsorte**.
2. `Eigentuemerversammlung.ort` wird von Freitext auf Pflichtauswahl aus
   diesem Katalog umgestellt.
3. Bei Anlage der EV: **Mehrfachauswahl der Verteilerschlüssel**, die zur
   Abstimmung genutzt werden dürfen (ersetzt das bisherige
   `stimmprinzip`/`stimm_verteilerschluessel`-Einzelfeld-Paar).
4. **Kopfprinzip wird zu einem normalen Verteilerschlüssel** (`vs_typ='kopf'`)
   statt eines separaten `stimmprinzip`-Felds.
5. Jeder Tagesordnungspunkt bekommt ein eigenes Stimmprinzip
   (= welcher der ausgewählten Verteilerschlüssel für diesen TOP gilt),
   vorbelegt mit dem Wert des vorherigen TOP.
6. Task 4 (Durchführung) und Task 5 (Beschlussfassung) entfallen als manuelle
   Immocore-Arbeitsschritte. Ersatz: **Checkout** (sperrt die EV-Daten in
   Immocore, übergibt an das externe Abstimmtool) und **Check-in** (Ergebnis +
   Protokoll-PDF kommen vom Abstimmtool zurück, Beschlussbuch + DMS-Ablage
   laufen automatisch).

## 1. Kataloge: Versammlungsorte

### Ist
- Kein „Kataloge"-Menübereich vorhanden. Vergleichbare reine Katalog-Seiten
  liegen unter „Stammdaten" (`frontend/src/components/Sidebar.tsx:15–17`:
  `/stammdaten/abrechnungsarten`, `/stammdaten/verteilerschluessel`,
  `/stammdaten/kontenplan`), objekt-bezogen (`objektAware: true`,
  Sidebar.tsx:67–72 hängt `?objekt=<id>` an).
- `Eigentuemerversammlung.ort` ist ein freies `CharField(max_length=255,
  blank=True, default='')`. Referenziert in:
  - `einladung_service.py:241` (Pflichtprüfung `if not ev.ort.strip()`)
  - `beschluss_service.py:232` (`ort=ev.ort` — Snapshot in `Beschluss.ort`)
  - Protokoll-PDF-Template erhält `ev.ort` im Kontext (`beschluss_service.py:284`)

### Soll
- Neuer Sidebar-Bereich **Kataloge** (eigener Top-Level-Eintrag, nicht unter
  Stammdaten — er ist bewusst nicht objekt-gebunden, siehe unten). Erster
  Eintrag: **Versammlungsorte**.
- Neues Modell `Versammlungsort` (vermutlich in `apps/versammlung/models.py`
  oder einer neuen, schlanken App `apps/kataloge`):
  - `bezeichnung` (Pflicht)
  - Adressfelder (Straße, PLZ, Ort, optional Zusatz/Raum)
  - **Offen:** global (mandantenweit) oder je Objekt? Empfehlung: **global**,
    da Versammlungsorte (Hotels, externe Veranstaltungsräume) oft
    objektübergreifend genutzt werden — anders als Verteilerschlüssel, die
    fachlich an ein Objekt gebunden sind.
- `Eigentuemerversammlung.ort` (CharField) → `versammlungsort`
  (`ForeignKey(Versammlungsort, on_delete=PROTECT)`, Pflichtfeld).
  - **Migration:** bestehende Freitext-Werte müssen in `Versammlungsort`-
    Datensätze überführt werden (distinct `ort`-Werte je einmal anlegen,
    dann EVs umhängen). Für bereits archivierte/GoBD-relevante EVs reicht die
    Umhängung, da `Beschluss.ort` als Text-Snapshot unverändert bleibt.
  - Templates/Services anpassen: `ev.ort` → `ev.versammlungsort.bezeichnung`
    an den 3 oben genannten Stellen.

## 2. Verteilerschlüssel-Mehrfachauswahl + Kopfprinzip als Verteilerschlüssel

### Ist
- `Verteilerschluessel` (`apps/objekte/models.py:161–192`): FK auf `Objekt`
  (Zeile 173, also objekt-gebunden), Feld `vs_typ` mit Choices `flaeche`,
  `mea`, `kopf`, `direkt`, `verbrauch` (Zeile 167). **„Kopf" existiert bereits
  als `vs_typ`-Wert** — es ist kein neues Modell nötig, nur sicherzustellen,
  dass jedes Objekt einen solchen Eintrag hat (siehe Migration unten).
- `Eigentuemerversammlung` hat `stimmprinzip` (Choices `kopf` /
  `verteilerschluessel`) **und** ein einzelnes
  `stimm_verteilerschluessel`-FK-Feld (nur relevant, wenn `stimmprinzip=
  'verteilerschluessel'`).

### Soll
- `stimmprinzip` und `stimm_verteilerschluessel` (Einzelfeld) entfallen.
- Neues Feld: `Eigentuemerversammlung.verteilerschluessel =
  ManyToManyField(Verteilerschluessel)` — Auswahl bei EV-Anlage, beschränkt
  auf Verteilerschlüssel des gewählten Objekts (Validierung im
  `ev_service.erstelle_ev`).
- **Migration/Datenpflege:** Für jedes Objekt, das noch keinen
  Verteilerschlüssel mit `vs_typ='kopf'` hat, wird einer automatisch
  angelegt (Bezeichnung z. B. „Kopfprinzip"). Bestehende EVs: alter
  `stimmprinzip='kopf'` → `verteilerschluessel = [Kopf-VS des Objekts]`;
  alter `stimmprinzip='verteilerschluessel'` → `verteilerschluessel = [alter
  stimm_verteilerschluessel]`.
- Frontend: EV-Anlageformular bekommt eine Mehrfachauswahl (Checkboxen oder
  Multi-Select) der Verteilerschlüssel des gewählten Objekts.

### ⚠️ Wichtige Konsequenz für Stimmkraft-Berechnung

Aktuell wird `EVTeilnehmer.stimmkraft` **einmal je Teilnehmer und EV**
berechnet und gespeichert (`stimmkraft_service.ermittle_teilnehmer`,
Snapshot in `EVTeilnehmerAnteil.mea_wert_snapshot`) — das setzt voraus, dass
es **einen** Verteilerschlüssel für die ganze Versammlung gibt.

Mit unterschiedlichen Verteilerschlüsseln **je TOP** (siehe Abschnitt 3) gilt
das nicht mehr: ein Eigentümer kann bei einem TOP mit Kopfprinzip 1 Stimme
haben und beim nächsten TOP mit MEA-Verteilerschlüssel z. B. 125,5 Stimmen.
**Die Stimmkraft muss also pro (Teilnehmer × Verteilerschlüssel) vorgehalten
werden, nicht mehr pro (Teilnehmer × EV).**

Das betrifft direkt das bereits verfasste
`docs/API_VERTRAG_VERSAMMLUNGSTOOL_v1_0.md`: dort liefert
`GET /versammlungen/{id}/teilnehmer/` aktuell ein einzelnes `stimmkraft`-Feld.
Das muss überarbeitet werden zu entweder:
- (a) einer Liste `stimmkraft_je_verteilerschluessel: [{verteilerschluessel_id,
  wert}]` je Teilnehmer, oder
- (b) das Abstimmtool ruft die Stimmkraft separat je TOP ab
  (`GET /tagesordnungspunkte/{id}/teilnehmer-stimmkraft/`, neu).

**Offen:** Variante (a) oder (b) — das ist vor der Umsetzung zu entscheiden,
da es sowohl das Backend-Serializer-Design als auch den bereits an das
externe Tool kommunizierten API-Vertrag ändert.

## 3. Stimmprinzip je Tagesordnungspunkt (mit Vererbung)

### Soll
- Neues Feld `Tagesordnungspunkt.verteilerschluessel` (FK, `PROTECT`),
  muss einer der in `ev.verteilerschluessel` ausgewählten sein
  (Validierung in `tagesordnung_service.top_anlegen`/`top_aktualisieren`).
- **Vorbelegung:** beim Anlegen eines neuen TOP wird automatisch der Wert
  des vorherigen TOP (nach `nummer` sortiert) übernommen, sofern beim Anlegen
  kein eigener Wert übergeben wird. Änderbar wie jedes andere TOP-Feld.
- **Offen — erster TOP der Versammlung:** es gibt keinen Vorgänger. Vorschlag:
  Pflichtfeld bei TOP Nr. 1 (kein impliziter Default), ab TOP Nr. 2 greift
  die Vererbung. Bitte bestätigen oder alternativen Default vorgeben (z. B.
  immer das Kopfprinzip als Ausgangswert).

## 4. Checkout ersetzt Task 4 + Task 5

### Ist (`ev_service.py:38–44`, `models.py:33–40/103–107`)
- `Eigentuemerversammlung.status`-Choices: `entwurf`, `in_bearbeitung`,
  `einladungen_versendet`, `durchgefuehrt`, `beschluesse_verarbeitet`,
  `archiviert`.
- **Task 4 (Durchführung)**: `durchfuehrung_service.schliesse_durchfuehrung_ab()`
  — prüft Anwesenheit/Abstimmungen/TOP-Bewertung, setzt Status →
  `durchgefuehrt`. Erfassung von Anwesenheit und Abstimmung geschieht bisher
  über die Immocore-eigene Oberfläche (`PATCH /ev-teilnehmer/`,
  `POST .../abstimmung/` bzw. `.../einzelstimmen/`).
- **Task 5 (Beschlussfassung)**: `beschluss_service.uebernimm_in_sammlung()`
  — übernimmt akzeptierte TOPs in die Beschluss-Sammlung, erzeugt
  Folgeaufgaben, **erzeugt das Protokoll-PDF selbst** (WeasyPrint,
  `erzeuge_protokoll_pdf`), Status → `beschluesse_verarbeitet`.

### Soll
Task 4 und Task 5 entfallen als manuelle Immocore-Arbeitsschritte. Ersatz:

**A) Checkout** (neue Aktion, ersetzt Task 4 fachlich als „Datenübergabe"):
- Neuer Endpoint `POST /versammlungen/{id}/checkout/`.
- Voraussetzung: Tagesordnung vollständig, jeder abstimmungspflichtige TOP
  hat einen Verteilerschlüssel (Abschnitt 3).
- Wirkung: TOPs, Teilnehmerliste und Verteilerschlüssel-Zuordnung werden in
  Immocore **gesperrt** (keine Änderung mehr möglich, analog zur
  bestehenden TOP-Sperre nach Einladungsversand). Neuer Status, z. B.
  `ausgecheckt` (ersetzt das bisherige `durchgefuehrt` als Bedeutung).
- Ab hier läuft die Anwesenheitserfassung (Check-in vor Ort) und die
  Stimmerfassung **nicht mehr in Immocore**, sondern ausschließlich im
  externen Abstimmtool (per `docs/API_VERTRAG_VERSAMMLUNGSTOOL_v1_0.md`,
  `PATCH /ev-teilnehmer/` und `POST .../einzelstimmen/` bleiben als
  Schreibpfade **für das Tool** bestehen — nur die Immocore-eigene
  Bedienoberfläche dafür entfällt).

**B) Check-in** (neuer, eingehender Endpoint, ersetzt Task 5):
- Neuer Endpoint, z. B. `POST /versammlungen/{id}/checkin/` (multipart:
  Protokoll-PDF-Datei + Abschlussbestätigung).
- Wirkung: führt die bisherige Logik aus `beschluss_service.
  uebernimm_in_sammlung()` aus (Beschluss-Sammlung nach § 24 Abs. 7 WEG,
  Folgevorgänge), **aber ohne selbst ein PDF zu erzeugen** — stattdessen wird
  die vom Abstimmtool mitgelieferte PDF-Datei als `Dokument` im DMS abgelegt
  (gleiches Muster wie `beschluss_service.py:233–279`: `Dokument.objects.
  create(datei=..., dateiname=..., kategorie='EV-Protokoll', dokument_typ=
  'beschluss', objekt=ev.objekt, hochgeladen_von=request.user)`), und als
  `ev.protokoll_pdf` verknüpft.
- Status → `beschluesse_verarbeitet` (bestehender Wert, Bedeutung bleibt
  gleich).
- **Offen (vom Auftraggeber bereits als „später zu spezifizieren" markiert):**
  exaktes Payload-Format des Check-in — insbesondere, ob die
  Abstimmungsergebnisse hier nochmal explizit mitgeliefert werden oder ob
  sie bereits vollständig über die laufenden `einzelstimmen`-Aufrufe während
  der Versammlung in Immocore vorliegen und Check-in nur noch die PDF
  nachliefert + den Abschluss auslöst. **Empfehlung:** letzteres (schlanker,
  keine Doppelerfassung) — bitte bestätigen.

### Auswirkung auf Task-Fortschrittsanzeige
`ev_service.task_status()` liefert aktuell 5 Tasks. Nach der Änderung: Task 1
(Grunddaten), Task 2 (Tagesordnung), Task 3 (Einladung) unverändert; Task 4
wird zu „Checkout"; Task 5 entfällt als manueller Task und wird zu einem
automatischen Statusübergang, der durch den Check-in-Aufruf ausgelöst wird
(kein Button in der Oberfläche mehr, sondern reine Status-/Ereignisanzeige).

## 5. Offene Punkte (Zusammenfassung)

1. Versammlungsorte: eigenes Modell/eigene App oder Erweiterung von
   `apps/versammlung`? Globaler Katalog wie oben angenommen — bitte
   bestätigen.
2. Stimmkraft je (Teilnehmer × Verteilerschlüssel) statt je (Teilnehmer × EV)
   — API-Vertrag mit dem externen Tool muss entsprechend angepasst werden
   (Variante a oder b, Abschnitt 2).
3. Default-Verteilerschlüssel für den ersten TOP einer Versammlung.
4. Exaktes Check-in-Payload-Format (nur PDF + Abschluss, oder zusätzlich
   Ergebnis-Rohdaten) — laut Auftraggeber bewusst für später offengehalten.
