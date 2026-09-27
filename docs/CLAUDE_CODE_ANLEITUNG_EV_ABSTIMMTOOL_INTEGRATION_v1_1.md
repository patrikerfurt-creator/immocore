# Spezifikation: EV-Modul — Kataloge, Stimmgrundlagen, Checkout/Abschluss (v1.1)

Stand: 2026-09-26. Ersetzt `CLAUDE_CODE_ANLEITUNG_EV_ABSTIMMTOOL_INTEGRATION_v1_0.md`
(dort dokumentiert als Grundlage für das Fable-5-Gutachten — die v1.0-Datei
bleibt als historischer Beleg bestehen, bitte nicht mehr als Umsetzungsgrundlage
verwenden). Wesentliche Korrektur gegenüber v1.0: **Kopfprinzip ist kein
Verteilerschlüssel** (siehe Abschnitt 2). Entscheidungen aus dem Fable-5-Review
sind eingearbeitet:
- Kopfprinzip → eigenes Zwischenmodell `EVStimmgrundlage`
- Versammlungsprotokoll wird weiterhin vom externen Abstimmtool erzeugt
  (zweistufiger Abschluss wegen Beschlussnummern-Zirkelbezug, Abschnitt 4)
- Kein Notfallpfad in Immocore — Task 4/5-UI entfällt vollständig

## 0. Überblick der Änderungen

1. Neuer Menübereich **Kataloge**, darin Katalog **Versammlungsorte**.
2. `Eigentuemerversammlung.ort` bleibt Freitext (GoBD-Snapshot), bekommt
   zusätzlich eine optionale FK auf den Katalog zur Vorbelegung.
3. Neues Modell **`EVStimmgrundlage`**: kapselt „welche Gewichtung gilt" —
   entweder ein Verteilerschlüssel des Objekts ODER echtes Kopfprinzip
   (personenbezogen), nie beides. Bei EV-Anlage werden mehrere
   Stimmgrundlagen ausgewählt/angelegt; eine davon ist „Standard".
4. Jeder Tagesordnungspunkt bekommt eine `stimmgrundlage`-FK, vorbelegt mit
   der Grundlage des vorherigen TOP (erster TOP: EV-Standard).
5. Task 4 (Durchführung) und Task 5 (Beschlussfassung) entfallen ersatzlos
   als manuelle Immocore-Arbeitsschritte, **kein Fallback**. Ersatz:
   **Checkout** (sperrt Daten, Übergabe ans Abstimmtool),
   **Checkout-Rücknahme** (Korrekturweg), **Abschluss** (serverseitige
   Beschluss-Erzeugung mit Nummern) und **Protokoll-Upload** (Tool liefert
   fertiges PDF).

## 1. Kataloge: Versammlungsorte

Unverändert zu v1.0 mit einer Korrektur:

- Neues Modell `Versammlungsort` (in `apps/versammlung`, kein eigenes App-
  Overhead nötig — erst bei einem zweiten, app-fremden Katalog eine eigene
  `apps/kataloge` erwägen): `bezeichnung`, `strasse`, `plz`, `ort_text`,
  `zusatz`, `aktiv` (Deaktivieren statt Löschen, da `PROTECT`-Referenzen aus
  alten EVs bestehen bleiben). Global, kein Objekt-Bezug.
- **Korrektur:** `Eigentuemerversammlung.ort` bleibt das bestehende
  `CharField` — es ist ein denormalisierter GoBD-Snapshot zum
  Versammlungszeitpunkt. Eine spätere Adresskorrektur am Katalogeintrag darf
  eine bereits versendete Einladung/ein bereits erzeugtes Protokoll nicht
  rückwirkend verändern. Neu ist nur `versammlungsort` als **optionale**
  FK (`null=True`), die beim Anlegen/Ändern der EV `ort` automatisch befüllt
  vorschlägt (Autocomplete), aber `ort` bleibt das maßgebliche, änderbare
  Textfeld. Die 9 bestehenden Referenzen auf `ev.ort` (u. a.
  `einladung_service.py:241`, `beschluss_service.py:232`,
  `ev_service.py:113–140,162`, Serializer-Felder, 3 Templates) bleiben
  dadurch unverändert funktionsfähig.

## 2. Stimmgrundlage statt Verteilerschlüssel-Mehrfachauswahl

### Warum nicht wie in v1.0 geplant

`Verteilerschluessel.vs_typ='kopf'` (`apps/objekte/models.py:161–192`,
Choice-Zeile 167) bedeutet im Bestand **„Anzahl je Einheit"** — jedes Objekt
hat davon bereits drei automatisch angelegte (`apps/konten/services/
__init__.py:229–283`, Nummernkreis 030–032: Anzahl Einheiten Gesamt /
Wohnungen / Stellplätze), mit `wert=1.0000` je Einheit. Das ist das
**Objektprinzip**, nicht das echte Kopfprinzip nach § 25 Abs. 2 WEG (eine
Stimme je **Person**, unabhängig von der Anzahl ihrer Einheiten). Ein
Eigentümer mit drei Einheiten hätte über einen „Kopf-Verteilerschlüssel"
fälschlich drei Stimmen. Das echte Kopfprinzip wird im Code bereits getrennt
berechnet: `stimmkraft_service._stimmkraft_kopf` (Zeile 125), personenbezogen.

### Neues Modell

```python
class EVStimmgrundlage(models.Model):
    ev = models.ForeignKey(Eigentuemerversammlung, related_name='stimmgrundlagen', ...)
    verteilerschluessel = models.ForeignKey(Verteilerschluessel, null=True, blank=True, on_delete=PROTECT)
    ist_kopfprinzip = models.BooleanField(default=False)
    wirtschaftsjahr = models.IntegerField(default=0)  # je Grundlage, nicht mehr EV-weit
    ist_standard = models.BooleanField(default=False)  # Vorbelegung für den ersten TOP
    bezeichnung_anzeige = models.CharField(...)  # z.B. "Kopfprinzip" oder Bezeichnung des VS

    class Meta:
        constraints = [
            CheckConstraint(check=Q(verteilerschluessel__isnull=False) ^ Q(ist_kopfprinzip=True), ...),
        ]
```

- Auswahl bei EV-Anlage: Mehrfachauswahl aus den Verteilerschlüsseln des
  Objekts **plus** einer festen Option „Kopfprinzip (echt, personenbezogen)".
- **Verbrauchsschlüssel (`vs_typ='verbrauch'`) sind als Stimmgrundlage
  ausgeschlossen** — Verbrauch ist keine Stimmgrundlage nach irgendeiner
  Teilungserklärung.
- Keine automatische Anlage von „Kopf-Verteilerschlüsseln" mehr nötig (v1.0-
  Migrationsidee entfällt ersatzlos).

### Snapshot-Modell (mehrdimensional)

- `EVTeilnehmerStimmkraft(teilnehmer, stimmgrundlage, stimmkraft)`,
  `unique_together (teilnehmer, stimmgrundlage)`.
- `EVTeilnehmerAnteilWert(anteil, stimmgrundlage, wert_snapshot)` — ersetzt
  den bisherigen Einzelwert in `EVTeilnehmerAnteil.mea_wert_snapshot`.
- `EVStimme.stimmkraft` (Snapshot je abgegebener Stimme, `models.py:426`)
  bleibt wie heute, wird aber aus `EVTeilnehmerStimmkraft` zur
  `top.stimmgrundlage` befüllt (`durchfuehrung_service.py:260–264` ändert
  sich entsprechend).
- `berechne_quorum(ev, stimmgrundlage)`, `bewerte_ergebnis(...,
  stimmgrundlage)` (`stimmkraft_service.py:297–335`,
  `durchfuehrung_service.py:158–176`) bekommen die Grundlage als Parameter
  statt EV-weit zu summieren.

### Migration Bestandsdaten

- Vorab prüfen: existieren produktive EVs mit Status ≥ `durchgefuehrt`? Falls
  nein (nur Testdaten), einfacher Schnitt möglich.
- Für jede bestehende EV: **eine** `EVStimmgrundlage` aus dem alten
  `stimmprinzip`/`stimm_verteilerschluessel`-Wertepaar anlegen, alle TOPs der
  EV darauf zeigen lassen. `EVTeilnehmer.stimmkraft` **kopieren** (nicht neu
  berechnen!) in `EVTeilnehmerStimmkraft` — eine Neuberechnung würde
  Stimmgewichte abgeschlossener Versammlungen nachträglich ändern.
- `EVEreignis`: für jede migrierte EV einen `kommentar`-Eintrag „Datenmodell-
  Migration v1.1, Stimmgrundlage übernommen aus stimmprinzip=…" (Audit-
  Lückenlosigkeit).
- Rückwärtsmigration als `noop` deklarieren (im Docstring begründen — ein
  sauberes Reverse ist nach Snapshot-Kopie nicht sinnvoll möglich).

## 3. Stimmgrundlage je Tagesordnungspunkt (mit Vererbung)

- Neues Feld `Tagesordnungspunkt.stimmgrundlage` (FK auf `EVStimmgrundlage`
  der eigenen EV, `PROTECT`).
- **Vorbelegung:** erster TOP der EV → die als `ist_standard=True` markierte
  Stimmgrundlage der EV (bei EV-Anlage festgelegt). Jeder weitere TOP →
  Wert des vorherigen TOP (nach `nummer`). Immer änderbar, solange die
  Einladung noch nicht versendet ist.
- **Sperre nach Einladungsversand:** `stimmgrundlage` gehört zu den
  pflegbaren, aber nach Versand **gesperrten** Feldern
  (`tagesordnung_service.py`, analog zur bestehenden TOP-Sperre nach § 23
  Abs. 2 WEG) — die Einladung muss die Stimmgrundlage je TOP nennen, sie darf
  sich danach nicht mehr ändern.
- **Einladungs-PDF:** `templates/versammlung/einladung.html` muss je TOP die
  Stimmgrundlage anzeigen (aktuell zeigt Zeile 155 nur den alten EV-weiten
  `stimmprinzip`-Wert — anpassen).
- **Protokoll:** muss je TOP die Stimmgrundlage samt deren Gesamtstimmkraft
  ausweisen, sonst ist das Ergebnis nicht nachprüfbar.

## 4. Checkout, Checkout-Rücknahme, Abschluss, Protokoll-Upload (ersetzt Task 4+5)

### A) Checkout
`POST /versammlungen/{id}/checkout/` — Voraussetzung: Tagesordnung
vollständig, jeder abstimmungspflichtige TOP hat eine Stimmgrundlage.
Sperrt TOPs, Teilnehmerliste und Stimmgrundlagen-Zuordnung in Immocore.
Status → neuer Wert `ausgecheckt`.

**Statuslogik:** `ausgecheckt` wird als **neuer, zusätzlicher** Status
zwischen `einladungen_versendet` und `beschluesse_verarbeitet` eingefügt —
der bestehende Wert `durchgefuehrt` wird nicht umbenannt oder wiederverwendet
(Bestandsdaten und Portal-Spec-Referenzen auf `status='durchgefuehrt'`
bleiben unangetastet gültig). Ab sofort durchlaufen **neue** EVs
`einladungen_versendet` → `ausgecheckt` → `beschluesse_verarbeitet` →
`archiviert`; `durchgefuehrt` bleibt nur für Altdaten belegt.

**Schreibzugriff ab Checkout:** `PATCH /ev-teilnehmer/{id}/` und
`POST /tagesordnungspunkte/{id}/einzelstimmen/` (aus dem API-Vertrag) sind
**nur noch im Status `ausgecheckt`** zulässig — vorher (z. B. direkt nach
`einladungen_versendet`) ebenso gesperrt wie nachher
(`beschluesse_verarbeitet`/`archiviert`). Das ist eine Verschärfung
gegenüber dem bisherigen `_pruefe_offen`, die im API-Vertrag v1.1
(Abschnitt unten) kommuniziert werden muss.

**Kein Notfallpfad:** Es gibt bewusst keine Immocore-eigene Oberfläche mehr,
um Anwesenheit/Stimmen zu erfassen, falls das Abstimmtool ausfällt. Das ist
eine bewusste Entscheidung (Rückfrage beantwortet) — operativ heißt das: das
Abstimmtool muss vor jeder Versammlung nachweislich einsatzbereit sein,
sonst kann die Versammlung in Immocore nicht dokumentiert werden.

### B) Checkout-Rücknahme
`POST /versammlungen/{id}/checkout-zuruecknehmen/` mit Pflichtfeld `grund`
(analog `ev_service.setze_task_zurueck`). Setzt Status zurück auf
`einladungen_versendet`, entsperrt TOPs/Teilnehmerliste wieder — nötig bei
verschobenem Termin, falscher Stimmgrundlage oder verworfenen Tool-Daten.
Erzeugt einen `EVEreignis`-Eintrag mit Begründung.

**Offen:** Eigentümerwechsel zwischen Checkout und tatsächlicher Versammlung
— bleibt `stimmkraft_neu_ermitteln` (Spec v1.1 Kap. 5.3 des Basis-Moduls)
nur *vor* Checkout erlaubt? Empfehlung: ja, danach nur über
Checkout-Rücknahme → Neuermittlung → erneuter Checkout. Bitte bestätigen,
sobald das Abstimmtool feststeht (betrifft dessen Cache-Invalidierung).

### C) Abschluss (Schritt 1 von 2 — löst den Beschlussnummern-Zirkelbezug)
`POST /versammlungen/{id}/abschluss/` — **kein Datei-Upload**. Prüft, dass
jeder abstimmungspflichtige TOP ein Ergebnis hat (aus den während der
Versammlung bereits per `einzelstimmen` übermittelten Daten — keine
Doppelerfassung). Führt die bestehende Logik aus
`beschluss_service.uebernimm_in_sammlung()` aus: erzeugt `Beschluss`-Zeilen
mit fortlaufender Nummer (`BeschlussNummerZaehler`), die revisionssicheren
Einzel-Beschluss-PDFs (`_beschluss_pdf`, bleiben **bei Immocore** — nur das
Gesamtprotokoll kommt vom Tool, siehe unten), legt Folgevorgänge an.
**Response enthält die vergebenen Beschlussnummern**, damit das Abstimmtool
sie ins von ihm erzeugte Protokoll-PDF übernehmen kann.

### D) Protokoll-Upload (Schritt 2 von 2)
`POST /versammlungen/{id}/protokoll-upload/` (multipart, PDF-Datei) — legt
die vom Abstimmtool gelieferte, fertige Protokoll-PDF als `Dokument` im DMS
ab. Feld-Muster wie bestehende Protokoll-Ablage
(`beschluss_service.py:297–308`, tatsächlich **`dokument_typ='korrespondenz'`**,
nicht `'beschluss'` — das ist den revisionssicheren Einzel-Beschluss-PDFs
vorbehalten), zusätzlich `revisionssicher=True` und `sha256` (Muster
`beleg_service.py:33`). Setzt `ev.protokoll_pdf`, Status →
`beschluesse_verarbeitet`.

**Validierung des Uploads:** MIME-/Magic-Bytes-Prüfung (muss echtes PDF
sein), Größenlimit, SHA-256 speichern. `Dokument.save()` schützt nur vor
nachträglichem Austausch, sobald `revisionssicher=True` gesetzt ist
(`dokumente/models.py:365–373`) — die Prüfung beim Upload selbst ist
zusätzlich nötig.

**Bestehender Endpoint `POST /versammlungen/{id}/protokoll-pdf/`**
(`views.py:352–367`, rendert Immocores eigenes Protokoll neu) muss ab Status
`beschluesse_verarbeitet` gesperrt werden, sonst überschreibt ein späterer
Aufruf versehentlich das vom Tool gelieferte PDF.

### Auswirkung auf Task-Fortschrittsanzeige
Task 1–3 unverändert. Task 4 wird zu „Checkout" (Button + Status). Task 5
entfällt als manueller Task vollständig — der Übergang zu
`beschluesse_verarbeitet` passiert automatisch durch den
Protokoll-Upload-Aufruf, nicht durch einen Button in der Oberfläche.

## 5. Folgeänderungen außerhalb des EV-Moduls

- **Portal-Sichtbarkeit** (Basis-Spec Kap. 8.3): Freigabe von
  Ergebnissen/Protokoll ist an `status='durchgefuehrt'` gekoppelt — muss um
  `ausgecheckt`/`beschluesse_verarbeitet` erweitert bzw. für neue EVs auf den
  neuen Status umgezogen werden.
- **Frontend:** `VersammlungDetail.tsx` (Quorum-Box, Anwesenheitstabelle,
  `durchfuehrungAbschliessen`-Aufruf ab ca. Zeile 880) muss als größerer
  Eingriff eingeplant werden, nicht nur als „Button entfernen". Ebenso
  `VersammlungenListe.tsx`, `Badge.tsx`, `types/index.ts` (Status- und
  `stimmprinzip`-Typen).
- **Testaufwand:** ca. 55 Fundstellen zu `stimmprinzip`/`ort` in 9
  Testdateien plus Factories/Seed-Skripte (`seed_ev_testdaten.py`) sind
  separat als Aufwandsposten einzuplanen.
- **Berechtigung des Tool-Logins:** bleibt offen (nur `IsAuthenticated`,
  keine Objekt-/Mandanten-Einschränkung geprüft) — wird mit dem neuen
  Datei-Upload-Endpoint dringlicher, ist aber eine eigene
  Mandantenfähigkeits-Entscheidung außerhalb dieser Spezifikation.

## 6. Verbleibende offene Punkte

1. Eigentümerwechsel-Handling zwischen Checkout und Versammlung (Abschnitt 4B).
2. Exaktes Feldschema von `Versammlungsort` (über die in Abschnitt 1
   genannten Felder hinaus, z. B. Raumkapazität?) — nur relevant, falls das
   Abstimmtool das für die Basisstations-Reichweite (max. 100m×100m laut
   RPI-1000-Datenblatt) auswerten soll.
3. Objekt-/Mandanten-Berechtigung des Tool-Logins (Abschnitt 5).
