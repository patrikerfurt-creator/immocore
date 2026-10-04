# IMMOCORE — Vorlagen & Korrespondenz (v1.2)

> **Änderungen zu v1.1 (Abgleich mit dem Repo `C:\Projekte\immocore`, 2026-09-29):**
> - `apps.versammlung` existiert bereits (Spec `docs/IMMOCORE_ClaudeCode_Eigentuemerversammlung_v1_1.md`)
>   mit `services/einladung_service.py`, WeasyPrint-Template `einladung.html`,
>   `Eigentuemerversammlung.einladungstext` und `EVVersandprotokoll`. Die
>   ETV-Einladung wird deshalb **nicht** als Serienbrief neu gebaut, sondern
>   das Versammlungsmodul nutzt künftig Briefbogen und Vorlage dieses Moduls
>   (neuer Abschnitt 9.4, Lookup 7).
> - **WeasyPrint** ist laut `docs/PROJEKT_STATUS.md` installiert und wird im
>   Versammlungsmodul genutzt → gesetzte PDF-Engine.
> - `Person` hat seit Abw. 009 die Einzelfelder `strasse`, `hausnummer`,
>   `plz`, `ort` (führend); `adresse` ist nur noch zusammengesetzter Textblock
>   → Anschriftzeilen aus den Einzelfeldern.
> - Referenz-Statusdatei für Claude Code ist `docs/PROJEKT_STATUS.md` im Repo.
> - Subagenten gemäß `.claude/agents/` (immo-explorer / immo-builder /
>   immo-architect); Start-Prompt in `ORCHESTRATOR_PROMPT_VORLAGEN_KORRESPONDENZ.md`.
>
> **Änderungen zu v1.0 (Patrik, 2026-09-29):**
> 1. **Keine KI-Formulierung je Schreiben.** Vorlagen werden **einmal**
>    erstellt und freigegeben; jedes Schreiben entsteht rein deterministisch
>    durch Befüllen der Platzhalter. Die KI hilft nur noch **im Editor beim
>    Erstellen einer Vorlage** (Abschnitt 6). `ki_modus`, KI-Entwurf je
>    Schreiben/Lauf und die zugehörigen Status entfallen.
> 2. **Briefbogen nach Referenzdatei** `Serienbrief_Vorlage.docx` (Demme,
>    Einladung ETV mit Vollmacht) — Layout vermessen in Abschnitt 5.
> 3. **Fußzeile bei WEG:** Name der WEG + Bankverbindung des Bankkontos, das
>    mit Sachkonto **18000** verknüpft ist (Abschnitt 5.4).
> 4. Neu: **Eingabefelder je Vorlage** (z. B. Datum/Ort/Tagesordnung einer
>    ETV), **Mapping der bisherigen Word-Seriendruckfelder** auf die neuen
>    Platzhalter, Mustervorlage **Einladung ETV + Vollmacht**.
>
> **Grundlage:** `IMMOCORE_PROJEKTSTAND_AKTUELL.md` (Export 2026-08-19, HEAD
> `3fb630d`, 87 Modelle, 718 Tests) und Portal-Spec v1.1. Der Projektstand
> ist älter als der Code — Fundstellen werden in Phase 0 bestätigt.

---

## 0. Ziel

Neues Modul `apps.korrespondenz`: Mitarbeiter pflegen Vorlagen für
wiederkehrende Schreiben und erzeugen daraus Einzel- und Serienschreiben
als PDF-Brief auf dem Demme-Briefbogen und/oder als E-Mail — z. B.
Begrüßung neuer Eigentümer, Zahlungserinnerung/Mahnung, Einladung zur
Eigentümerversammlung, allgemeine Eigentümeranschreiben.

Kernprinzipien:

1. **Einmal erstellen, beliebig oft verwenden.** Eine Vorlage wird einmal
   geschrieben, von einer berechtigten Person freigegeben und ist ab dann
   unveränderlich (Änderung = neue Version).
2. **Deterministisch.** Ein Schreiben = freigegebene Vorlagenversion +
   Platzhalterwerte aus der Datenbank + ggf. Eingabefelder. Zwei Schreiben
   derselben Version unterscheiden sich nur in den Daten.
3. **Keine leeren oder falschen Werte.** Fehlt ein Pflichtwert (z. B. keine
   Bankverbindung für die Fußzeile), wird das Schreiben nicht erzeugt,
   sondern mit klarer Fehlermeldung gemeldet.
4. **Freigabe vor Versand.** Kein Schreiben verlässt das Haus ohne
   Freigabe (Einzelschreiben im Postausgang, Mahnschreiben über die
   Mahnlauf-Freigabe, Serienbriefe über die Serienlauf-Freigabe).

---

## 1. Orchestrierung für Claude Code

Koordinierender Hauptagent: **Opus**. Er zerlegt die Arbeit, legt die
Contracts (Abschnitte 4, 8) verbindlich fest, prüft Zwischenergebnisse —
insbesondere die **Layout-Treue zur Referenzdatei** und die
**Determinismus-Regel** — und gibt jede Phase erst frei, wenn ihr
Abnahmekriterium erfüllt ist. Er schreibt selbst möglichst keinen Code.

| Rolle | Modell | Aufgabe | Abhängigkeit |
|---|---|---|---|
| **Orchestrator** | Opus | Zerlegung, Contract-Hoheit, Zwischenabnahme, visueller Abgleich PDF ↔ Referenz, Endabnahme | — |
| **Agent A — Lookups** | Haiku (7 parallele Instanzen) | Phase 0: je ein Lookup aus 2.2 | — |
| **Agent B — Kern-Backend** | Sonnet | Phase 1+2: Datenmodell, Migration, Render-Engine, Platzhalter-Registry, Eingabefelder, Textbausteine | A |
| **Agent C — Briefbogen & PDF** | Sonnet | Phase 3: Briefbogen-Layout nach Abschnitt 5, HTML→PDF, Fußzeilen-Logik, DMS-Ablage | A; parallel zu B |
| **Agent D — Versand** | Sonnet | Phase 4: Postausgang-Services, E-Mail-Versand, Druckstapel, Serienlauf | B, C |
| **Agent E — Frontend** | Sonnet | Phase 5: Vorlagen-Editor inkl. KI-Assistent, Postausgang, Serienbrief-Assistent | startet parallel gegen Contracts (8) |
| **Agent F — Prozess-Anbindung** | Sonnet | Phase 6: Mahnlauf, Eigentümerwechsel, Vorgang | B, C, D |
| **Agent G — Seed & Doku** | Haiku | Phase 7: Datenmigration Standard-Briefbogen + Mustervorlagen (Anhang A), Platzhalter-Doku, Feld-Mapping-Doku | B |
| **Agent H — Tests** | Sonnet | Phase 8: Tests aus Abschnitt 11, visuelle Regression, volle Regression | alle |

**Ablauf:** A (7× parallel) → B und C parallel → D → F; E und G parallel
dazu; H begleitend. Endabnahme durch Opus.

**Abnahmekriterium Layout:** Agent H erzeugt ein Testschreiben mit den
Beispieldaten aus Anhang B, rendert es zu PNG und legt es neben das
Referenz-Rendering der Word-Datei. Der Orchestrator gibt Phase 3 erst frei,
wenn Logo, Absenderzeile, Anschriftfeld, Infoblock, Bezugszeichenzeile,
Betreffblock und Fußzeile innerhalb ±2 mm übereinstimmen.

---

## 2. Bestandsaufnahme

### 2.1 Was laut Projektstand existiert und genutzt wird

| Baustein | Fundstelle | Nutzung |
|---|---|---|
| `Person` (`anrede`, `titel`, `briefanrede`, `briefanrede2`, `vorname2`/`nachname2`, `adresse`, `email`, `emails`, `personennummer`) | `apps.personen` | Anschrift, Anrede, Empfänger-Mail |
| `Objekt` (`objektnummer`, `bezeichnung`, `objekt_typ`, `bundesland`, `betreuer`) | `apps.objekte` | Objektzeile, Fußzeile, Ansprechpartner |
| `Einheit` (`einheit_nr`, `flaechennummer`, `lage`, `einheit_typ`) | `apps.objekte` | Flächenzeile |
| `Bankkonto` (`konto_typ`, `iban`, `bic`, `kontoinhaber`, `zahlungsverkehr`) | `apps.objekte` | Fußzeile WEG |
| `Konto` 18000 „Bank 1" (Musterkontenrahmen) | `apps.konten` | Verknüpfung Fußzeilen-Bankkonto, siehe Lookup 6 |
| `Personenkonto.kontonummer` | `apps.konten` | „Unser Zeichen", siehe Anhang C |
| `Mahnlauf`, `Mahnung` (`mahnstufe`, `offene_posten_summe`, `gebuehr`, `zinsen`, `pdf_pfad`, `versandt_am`), `Basiszinssatz` | `apps.buchhaltung` | Mahnschreiben |
| `EigentuemerwechselVorgang` | `apps.buchhaltung` | Begrüßungsschreiben |
| `HausgeldHistorie`, `SEPAMandat` | `apps.personen` | Begrüßungsschreiben |
| `Dokument` (`dokument_typ='korrespondenz'`, `revisionssicher`, `sha256`, Constraint `dokument_max_ein_kontext`) | `apps.dokumente` | Ablage |
| `Vorgang`, `VorgangEreignis` | `apps.vorgaenge` | Schreiben aus Vorgang |
| KI-Client des KI-Antwortvorschlags (`ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`) | `apps.vorgaenge` | nur für den Vorlagen-Assistenten im Editor |
| Mail-Service mit `_pruefe_versandfaehig()` | `apps.handwerker` / `apps.portal` | E-Mail-Versand |
| `apps.versammlung`: `einladung_service` (`erzeuge_einladungs_pdf`, `versandplan`, `versende_einladungen`), Template `einladung.html`, `Eigentuemerversammlung.einladungstext`, `EVVersandprotokoll`, Kanal `epost` | `apps.versammlung` | ETV-Einladung auf gemeinsamem Briefbogen (9.4) |
| `Person.strasse`, `hausnummer`, `plz`, `ort` (Abw. 009, führend) | `apps.personen` | Anschriftzeilen |
| WeasyPrint (installiert, im Versammlungsmodul genutzt) | Backend-Image | PDF-Engine |

### 2.2 Phase 0 — sieben gezielte Lookups (Agent A, Haiku, parallel)

Jeder Lookup liefert Datei:Zeile, Signatur, 3–5 Sätze Befund. Kein Umbau.

1. **PDF-Engine:** WeasyPrint-Nutzung in `apps.versammlung` (Template-Ort, Base-CSS, Schriften) und im Jahresabrechnung-PDF; im Prod-Image vorhanden?
2. **Mahnschreiben heute:** wo/wie wird `Mahnung.pdf_pfad` befüllt; Datenquelle der offenen Posten (`OffenerPosten` oder `HausgeldSollstellung`)?
3. **Mail-Service:** Lage, Signatur, Anhänge, HTML-Mails.
4. **Freigabe-Stellen:** Service-Funktionen für `EigentuemerwechselVorgang → freigegeben` und Mahnlauf-Freigabe/-Ausführung.
5. **Frontend:** vorhandener Rich-Text-Editor? Einbindung des KI-Antwortvorschlags (Komponente, API-Client)?
6. **Verknüpfung Bankkonto ↔ Sachkonto 18000:** Gibt es seit dem E-Banking-Umbau ein Feld, das ein `objekte.Bankkonto` einem `konten.Konto` zuordnet (z. B. `Bankkonto.sachkonto`, `Konto.bankkonto` o. ä.)? Im Projektstand vom 2026-08-19 ist keines dokumentiert.
7. **Versammlungsmodul:** Aufbau von `einladung.html` und `erzeuge_einladungs_pdf()` (Anschrift, Kopf/Fuß, personalisierte PDFs je Person), wie `einladungstext` vorbelegt wird, Stand Phase B (committet/deployt?).

---

## 3. Datenmodell (`apps.korrespondenz`)

### 3.1 `Briefbogen`

| Feld | Typ | Hinweis |
|---|---|---|
| `id` | UUID PK | |
| `bezeichnung` | Char(100) | „Demme — Standard" |
| `firma_name` | Char(200) | Demme Immobilien Verwaltung GmbH |
| `firma_strasse`, `firma_plz`, `firma_ort` | Char | Coventrystraße 32, 65934 Frankfurt am Main |
| `telefon`, `email`, `web` | Char | 069-96 75 20 90, info@demme-immobilien.de |
| `sprechzeiten` | Text | mehrzeilig, erscheint im Infoblock |
| `hinweis_infoblock` | Text | „Bürotermine nur nach vorheriger telefonischer Absprache" |
| `logo` | FK → `dokumente.Dokument` | Demme-Logo (aus Referenzdatei `word/media/image1.jpeg`) |
| `fuss_logo` | FK → `dokumente.Dokument`, null | Verbandslogo (aus `word/media/image2.png`) |
| `fuss_firma_zeile1/2/3` | Char | Fußzeile Nicht-WEG (5.4) |
| `pflichtangaben` | Char(300) | GmbH-Pflichtangaben, siehe 5.4 / offener Punkt |
| `steuerzeichen_unsichtbar` | Char(50), blank | übernimmt den unsichtbaren Marker `Porto!Demme` der Referenz, siehe 10 |
| `ist_standard`, `aktiv` | Bool | genau ein Standard |

### 3.2 `Vorlage`

| Feld | Typ | Hinweis |
|---|---|---|
| `id` | UUID PK | |
| `code` | Char(50) | `eigentuemer_begruessung`, `mahnung_stufe_1`, `etv_einladung` … |
| `bezeichnung` | Char(150) | |
| `anlass` | Char(40), choices | bestimmt verfügbare Platzhalter (4.2) |
| `objekt` | FK → `Objekt`, null | `null` = global; gesetzt = objektspezifische Übersteuerung |
| `briefbogen` | FK → `Briefbogen`, null | `null` = Standard |
| `kanal_standard` | choices `brief`, `email`, `beides` | |
| `einzeln_bearbeitbar` | Bool, Default `False` | ob ein Mitarbeiter ein einzelnes Schreiben vor Freigabe textlich anpassen darf (sinnvoll für Vorgangsantworten, nicht für Mahnungen/Serien) |
| `aktive_version` | FK → `VorlagenVersion`, null | |
| `aktiv` | Bool | |
| `erstellt_am/_von`, `geaendert_am` | | |

`UniqueConstraint(['code', 'objekt'])`; Auflösung objektspezifisch vor
global (`vorlage_service.aufloesen(code, objekt)`).

### 3.3 `VorlagenVersion` (nach Freigabe unveränderlich)

| Feld | Typ | Hinweis |
|---|---|---|
| `id` | UUID PK | |
| `vorlage` | FK, CASCADE | |
| `version` | PositiveInt | fortlaufend |
| `betreff` | Char(250) | mit Platzhaltern |
| `inhalt` | JSON | Blockstruktur (3.4) |
| `email_begleittext` | Text, blank | Mailtext, wenn der Brief als PDF-Anhang geht |
| `eingabefelder` | JSON list | siehe 3.5 |
| `pflicht_platzhalter` | JSON list | müssen im Endtext vorkommen |
| `parameter` | JSON dict | z. B. `{"frist_tage": 14}` |
| `status` | `entwurf`, `freigegeben`, `abgeloest` | |
| `freigegeben_am/_von` | | Permission `korrespondenz.vorlage_freigeben` |
| `erstellt_am/_von` | | |

### 3.4 Blockstruktur von `inhalt`

| Blocktyp | Inhalt |
|---|---|
| `text` | Fließtext mit Platzhaltern (fett/kursiv/Listen erlaubt) |
| `baustein` | Referenz auf `Textbaustein` |
| `tabelle` | systemerzeugte Tabelle, z. B. `mahnung.offene_posten`, `hausgeld.positionen` |
| `liste` | aus einem Listen-Eingabefeld, z. B. nummerierte Tagesordnung |
| `bedingt` | Text, nur wenn Bedingung erfüllt (z. B. `ev.sepa_mandat_fehlt`) |
| `seitenumbruch` | neue Seite (z. B. vor Vollmacht) |
| `anlage_seite` | vollständige Folgeseite mit eigenem Inhalt, ohne Briefkopf, mit Fußzeile (Vollmacht, Rückantwort) |

Absenderzeile, Anschriftfeld, Infoblock, Bezugszeichenzeile, Objekt-/
Flächenzeile, Grußformel mit Unterzeichner und Fußzeile liefert der
**Briefbogen** — sie sind nicht Teil des Vorlageninhalts. Die Vorlage
liefert Betreff und Brieftext ab Anrede.

### 3.5 Eingabefelder

Werte, die nicht in der Datenbank stehen, sondern je Schreiben bzw. je
Serienlauf einmal eingegeben werden. Definition in der Vorlagenversion:

```json
[{"name": "versammlung_datum", "label": "Datum der Versammlung", "typ": "datum", "pflicht": true},
 {"name": "versammlung_uhrzeit", "label": "Uhrzeit", "typ": "uhrzeit", "pflicht": true},
 {"name": "versammlung_ort", "label": "Ort / Adresse", "typ": "text", "pflicht": true},
 {"name": "tagesordnung", "label": "Tagesordnungspunkte", "typ": "liste", "pflicht": true}]
```

Typen: `text`, `mehrzeilig`, `datum`, `uhrzeit`, `betrag`, `liste`,
`ja_nein`. Im Text als `{{ eingabe.versammlung_ort }}`. Werte werden im
`Schreiben` bzw. `Serienlauf` gespeichert.

### 3.6 `Textbaustein`

`code` (unique je `objekt`, null = global), `bezeichnung`, `inhalt` (nur
`text`), `aktiv`. Keine Verschachtelung.

### 3.7 `VorlageAnlage`

`vorlage`, `art` (`dokument` = fester PDF-Anhang / `objekt_kategorie` =
objektbezogenes Dokument wie Hausordnung), `bezeichnung`, `pflicht`,
`reihenfolge`.

### 3.8 `Schreiben`

| Feld | Typ | Hinweis |
|---|---|---|
| `id` | UUID PK | |
| `nummer` | Char(20), unique | `KS-2026-000123` (Zähler analog `VorgangNummerZaehler`) |
| `vorlage_version` | FK, PROTECT | |
| `empfaenger` | FK → `Person`, PROTECT | |
| `objekt`, `einheit`, `eigentumsverhaeltnis` | FKs, null | |
| `vorgang` | FK → `Vorgang`, null | |
| `mahnung` | OneToOne → `Mahnung`, null | |
| `eigentuemerwechsel` | FK → `EigentuemerwechselVorgang`, null | |
| `serienlauf` | FK → `Serienlauf`, null | |
| `unterzeichner` | FK → `auth.User`, null | „gez. Vorname Nachname"; Default = erstellender Mitarbeiter, bei Automatik = Objektbetreuer |
| `ihr_zeichen`, `ihr_schreiben_vom` | Char / Date, blank | optional, Bezugszeichenzeile |
| `eingabewerte` | JSON | Werte der Eingabefelder |
| `kanal` | `brief`, `email` | |
| `status` | 3.10 | |
| `inhalt_angepasst` | JSON, null | nur wenn `einzeln_bearbeitbar` und Mitarbeiter geändert hat |
| `html_gerendert` | Text | Endfassung |
| `kontext_snapshot` | JSON | alle verwendeten Werte (Beweissicherung) |
| `dokument` | FK → `Dokument`, null | PDF im DMS |
| `freigegeben_am/_von`, `versendet_am`, `mail_message_id`, `fehler` | | |
| `erstellt_am/_von` | | |

CheckConstraint: höchstens einer von `mahnung`, `eigentuemerwechsel`, `serienlauf`.

### 3.9 `Serienlauf`

`vorlage_version`, `objekt`, `empfaenger_filter` (JSON), `eingabewerte`
(JSON, gelten für alle Empfänger), `unterzeichner`, `status` (`vorschau`,
`zur_pruefung`, `freigegeben`, `versendet`, `teilweise_fehler`), `anzahl`,
`druck_dokument` (FK → Dokument, Sammel-PDF), `erstellt/freigegeben_am/_von`.

### 3.10 Status `Schreiben`

```
entwurf → zur_pruefung → freigegeben → versendet
               ↓              ↓
           verworfen   versand_fehlgeschlagen → (erneut) freigegeben
```

Render-Fehler (fehlender Pflichtwert) → Schreiben bleibt `entwurf` mit
`fehler`, erscheint im Postausgang als „nicht erzeugbar" mit Ursache.
Übergänge ausschließlich über `schreiben_service`.

### 3.11 Erweiterungen bestehender Modelle

| Modell | Feld | Zweck |
|---|---|---|
| `personen.Person` | `zustellweg` (`post`/`email`, Default `post`), `zustellweg_zustimmung_am` | E-Mail nur mit Zustimmung |
| `vorgaenge.VorgangEreignis.typ` | + `schreiben_erstellt`, `schreiben_versendet` | Verlauf |
| `buchhaltung.FrontofficeAufgabe.aufgabe_typ` | + `schreiben_zur_pruefung`, `schreiben_nicht_erzeugbar` | Aufgabenliste |
| **nur falls Lookup 6 nichts findet:** `objekte.Bankkonto` | `sachkonto_nr` Char(6), blank | Verknüpfung Bankkonto ↔ Sachkonto (18000, 18911 …); Datenmigration: `bewirtschaftung` + `zahlungsverkehr=True` → `18000` |

`Mahnung.pdf_pfad` bleibt (Doppelbetrieb), wird aus `Schreiben.dokument` befüllt.

---

## 4. Render-Engine & Platzhalter (Agent B)

### 4.1 Engine

- Jinja2 `SandboxedEnvironment` + `StrictUndefined`.
- Filter: `euro` (`1.234,56 €`), `datum` (`29.09.2026`), `datum_lang`
  (`Dienstag, den 29. September 2026`), `datum_mittel` (`29. September 2026`),
  `uhrzeit` (`16.00 Uhr`), `iban` (Vierergruppen), `upper`, `default`.
- Die Engine sieht nur das flache Kontext-Dict der Registry, nie Modelle.
- `render_service.render(version, kontext, eingabewerte) -> RenderErgebnis(html, betreff, snapshot, fehler)`.

### 4.2 Platzhalter-Registry

Python-Registry je `anlass`, lädt Werte und liefert Metadaten (Name,
Beschreibung, Typ, Beispielwert). Speist Editor, Vorschau, Validierung und
die generierte Doku — eine Quelle.

| Gruppe | Platzhalter (Auszug) | Anlässe |
|---|---|---|
| `empfaenger` | `anschrift_zeilen` (Liste, max. 7), `briefanrede`, `briefanrede2`, `name`, `personennummer` | alle |
| `objekt` | `objektnummer`, `bezeichnung`, `anschrift`, `ist_weg` | alle mit Objekt |
| `einheit` | `einheit_nr`, `flaechennummer`, `lage`, `typ` | Einheit-bezogen |
| `schreiben` | `unser_zeichen`, `ihr_zeichen`, `ihr_schreiben_vom`, `datum`, `nummer` | alle |
| `verwaltung` | `firma`, `unterzeichner_vorname`, `unterzeichner_nachname`, `betreuer_name`, `betreuer_telefon`, `betreuer_email` | alle |
| `bank` | `weg_name`, `iban`, `bic`, `bankname`, `kontoinhaber`, `glaeubiger_id` | WEG-Objekte (5.4) |
| `ev` | `beginn`, `sepa_mandat_vorhanden`, `sepa_mandat_fehlt` | Eigentümer |
| `hausgeld` | `monatsbetrag`, `gueltig_ab`, `positionen` | Begrüßung |
| `wechsel` | `wechsel_datum`, `voreigentuemer_name` | Begrüßung/Verabschiedung |
| `mahnung` | `stufe`, `offene_posten`, `summe_hauptforderung`, `gebuehr`, `zinsen`, `gesamtbetrag`, `frist`, `zinssatz`, `basiszinssatz` | Mahnstufen |
| `vorgang` | `nummer`, `betreff` | Vorgangsantwort |
| `eingabe` | laut `eingabefelder` der Version | alle |

`mahnung.frist` = heute + `parameter.frist_tage`, verschoben auf den
nächsten Werktag (Feiertage nach `Objekt.bundesland`).

**Anschriftzeilen** (`empfaenger.anschrift_zeilen`) — ersetzt
`EmpfAnsZeile1–7`: Zeile 1 Anrede (`Herrn` / `Frau` / `Eheleute` /
`Firma`), Zeile 2 Titel + Vorname + Nachname (bzw. Firmenname), Zeile 3
ggf. zweite Person, danach Straße, PLZ Ort, ggf. Land. Leere Zeilen
entfallen. Quelle sind die führenden Einzelfelder `strasse`, `hausnummer`,
`plz`, `ort` (Abw. 009); die 7 Sonderfälle mit komplett in `strasse`
stehender Adresse werden unverändert übernommen.

Anlässe v1.1: `eigentuemer_begruessung`, `eigentuemer_verabschiedung`,
`mahnung_stufe_1`, `mahnung_stufe_2`, `mahnung_stufe_3`, `etv_einladung`,
`eigentuemer_allgemein`, `vorgang_antwort`.

### 4.3 Endpoint

```
GET /api/v1/korrespondenz/platzhalter/?anlass=<code>
→ [{name, beschreibung, typ, beispiel, gruppe}]
```

---

## 5. Briefbogen & PDF (Agent C)

### 5.1 Referenz

Die Datei `Serienbrief_Vorlage.docx` (von Patrik bereitgestellt) wird als
`docs/vorlagen/Demme_Briefbogen_Referenz.docx` ins Repo gelegt. Logo
(`word/media/image1.jpeg`, 528×358 px, 220 dpi) und Verbandslogo
(`word/media/image2.png`) werden daraus extrahiert und über die Seed-Migration
als `Dokument` am Standard-Briefbogen hinterlegt. **Die Referenzdatei ist
maßgeblich** — bei Widerspruch zu den Maßen unten gilt die Datei.

### 5.2 Seite & Schrift

| Element | Wert |
|---|---|
| Format | A4 hoch, DIN 5008 Form B |
| Ränder | oben 17,5 mm · links 25 mm · rechts 25 mm · unten 20 mm |
| Brieftext | **Arial 11 pt**, einfacher Zeilenabstand, Absätze durch Leerzeile |
| Bezugszeichen-Werte | Arial 9 pt |
| Überschrift auf Anlage-Seiten (z. B. „Vertretungsvollmacht") | Arial 16 pt, fett, unterstrichen |
| Absenderzeile, Infoblock, Fußzeile | **Letter Gothic MT Std** — Infoblock 8 pt, Sprechzeiten/Hinweis 6 pt |

**Schrift-Hinweis:** Letter Gothic MT Std ist eine lizenzpflichtige
Adobe-Schrift. Für das serverseitige Einbetten in PDFs muss eine
entsprechende Lizenz bzw. die Schriftdatei vorliegen (Patrik stellt sie
bereit). Fallback, bis sie vorliegt: eine metrisch ähnliche freie
Monospace-Schrift (Vorschlag Agent C), deutlich als Übergang markiert.

### 5.3 Positionen Seite 1 (gemessen am Rendering der Referenz, ±2 mm)

| Element | Position (vom Blattrand) | Inhalt |
|---|---|---|
| Logo | x 136 mm, y 5–47 mm, B 61 × H 41 mm | Demme-Logo, rechtsbündig |
| Absenderzeile | x 25 mm, y ≈ 42–46 mm | `Demme Immobilien Verwaltung GmbH` / `Coventrystraße 32 · 65934 Frankfurt am Main` (Letter Gothic 8 pt) |
| Anschriftfeld | x 25 mm, y 62,7–90 mm, max. 7 Zeilen, Arial 11 pt | `empfaenger.anschrift_zeilen` |
| Infoblock | x 140 mm, y ≈ 49–92 mm, B 46 mm | Firma (3-zeilig), Straße, PLZ Ort, `Fon …`, E-Mail, Trennlinie, Sprechzeiten, Trennlinie, Hinweis, Trennlinie |
| Bezugszeichenzeile | y ≈ 96 mm, volle Satzbreite 160 mm, 4 Spalten | `Ihr Zeichen:` · `Ihr Schreiben vom:` · `Unser Zeichen:` · `Datum:` — Werte darunter in 9 pt |
| Betreffblock | ab y ≈ 110 mm, fett | `Objekt: {{objektnummer}}-{{objekt.bezeichnung}}` / `Fläche: {{einheit.flaechennummer}}-{{einheit.lage}}` / Betreff der Vorlage |
| Anrede | eine Leerzeile unter dem Betreff | `briefanrede`, ggf. `briefanrede2` in zweiter Zeile |
| Schluss | nach Brieftext | `Mit freundlichen Grüßen` / Leerzeile / Firma / Leerzeile / `gez. {{unterzeichner_vorname}} {{unterzeichner_nachname}}` |

Folgeseiten: ohne Logo, Absenderzeile, Infoblock und Anschriftfeld;
oberer Rand 17,5 mm; Seitenzahl „Seite 2 von 3" rechts oben;
**Fußzeile auf jeder Seite**. Falz- und Lochmarken am linken Rand
(DIN 5008). Zeilen der Objekt-/Flächenzeile entfallen, wenn kein Objekt
bzw. keine Einheit gesetzt ist.

### 5.4 Fußzeile

**WEG-Objekt (`objekt_typ='WEG'`)** — wie in der Referenz (Letter Gothic):

```
{{ bank.weg_name }}
IBAN: {{ bank.iban }} · BIC: {{ bank.bic }} · {{ bank.bankname }}
```

- `bank.weg_name` = `Objekt.bezeichnung` (z. B. „WEG Schwalbacher Straße 47-49").
- Bankverbindung = das **aktive Bankkonto des Objekts, das mit Sachkonto
  18000 verknüpft ist** (Lookup 6 bzw. Feld aus 3.11).
- Kein oder mehr als ein passendes Bankkonto → Render-Fehler
  „Fußzeilen-Bankkonto (18000) nicht eindeutig" → Schreiben
  `nicht erzeugbar`, FrontofficeAufgabe `schreiben_nicht_erzeugbar`.
  Ein WEG-Brief ohne Bankverbindung geht nie raus.
- `bankname`: aus BIC ableiten, falls kein Feld vorhanden (Agent C prüft,
  ob eine BIC→Bankname-Tabelle im Projekt existiert; sonst Feld
  `Bankkonto.bankname` ergänzen).

**Nicht-WEG-Objekte und Schreiben ohne Objekt** — Inhalt der
Erste-Seite-Fußzeile der Referenz (dort derzeit nicht aktiv, `titlePg`
fehlt), mit Verbandslogo links:

```
Geschäftsführer: Patrik Maurer · HRB 7182 AG Königstein im Taunus
Frankfurter Volksbank · IBAN: DE02 5019 0000 6300 2110 10 · BIC FFVBDEFFXXX
Frankfurt - Königstein/Taunus - Erfurt
```

Werte stehen in `Briefbogen.fuss_firma_zeile1–3`, nicht im Code.

**GmbH-Pflichtangaben bei WEG-Briefen — offener Punkt für Patrik:**
Geschäftsbriefe einer GmbH an bestimmte Empfänger müssen Rechtsform,
Sitz, Registergericht, Registernummer und Geschäftsführer angeben (§ 35a
GmbHG). Die aktive WEG-Fußzeile der Referenz enthält das nicht. Vorschlag:
eine zusätzliche Zeile in 6 pt unter der WEG-Bankverbindung aus
`Briefbogen.pflichtangaben`. Umsetzung als Schalter am Briefbogen,
**Default an** — Patrik entscheidet vor Aktivierung.

### 5.5 Technik & Ablage

- HTML → PDF mit **WeasyPrint** (bereits im Einsatz; CSS Paged Media: `@page :first`, laufende Fußzeilen, absolute
  Positionierung in mm).
- Anlagen (3.7) hinter das Schreiben, Hinweis „Anlagen" am Briefende.
- Ablage als `Dokument` (`korrespondenz`, `revisionssicher=True`, `sha256`);
  genau ein Kontext: `vorgang`, sonst `person`.
- PDF entsteht **bei Freigabe** und wird danach nie neu gerendert.

---

## 6. KI-Assistent im Vorlagen-Editor (Agent B Backend, Agent E Frontend)

Die KI wird **ausschließlich beim Erstellen oder Überarbeiten einer
Vorlage** genutzt, nie beim Erzeugen eines Schreibens.

- Button „Mit KI entwerfen" im Editor: Mitarbeiter gibt Anlass und
  Stichworte ein („freundliche Begrüßung, SEPA-Hinweis, Ansprechpartner
  nennen"). Die KI erhält Anlass, Stichworte und die **Platzhalterliste
  mit Beschreibungen (ohne Werte)** und liefert einen Vorlagenentwurf in
  der Blockstruktur 3.4.
- „Mit KI überarbeiten" für einen markierten Block (kürzer, förmlicher,
  freundlicher …).
- Prüfung des KI-Outputs vor Übernahme in den Editor: gültige
  Blockstruktur, nur bekannte Platzhalter, keine literalen Beträge, IBANs
  oder Kalenderdaten außerhalb von Platzhaltern (sonst Hinweis an den
  Mitarbeiter).
- Der Entwurf ist ein normaler `entwurf` und durchläuft die reguläre
  Vorlagenfreigabe.
- Endpoint: `POST /api/v1/korrespondenz/vorlagen-assistent/`
  `{anlass, stichworte, block?} → {bloecke, hinweise}`. Synchron mit
  Timeout 60 s. Ohne `ANTHROPIC_API_KEY` ist der Button ausgeblendet.

---

## 7. Erstellung, Postausgang, Versand (Agent D)

### 7.1 Einzelschreiben

`schreiben_service.erstellen(vorlage_code, empfaenger, kontext_refs, eingabewerte, kanal=None)`
— löst Vorlage auf, rendert sofort, legt `Schreiben` in `zur_pruefung` an
(oder `entwurf` + Fehler). Aufrufbar aus Person-, Einheit- und
Vorgangsansicht sowie aus dem Postausgang.

### 7.2 Postausgang

Liste `zur_pruefung`, `nicht erzeugbar`, `versand_fehlgeschlagen`;
filterbar nach Objekt, Anlass, Betreuer. Prüfansicht zeigt die fertige
PDF-Vorschau. Textanpassung nur, wenn die Vorlage `einzeln_bearbeitbar`
ist. Aktionen: **Freigeben**, **Freigeben & Senden**, **Verwerfen**.

### 7.3 Versand

- Kanal = Vorlage `kanal_standard` × `Person.zustellweg`. E-Mail nur mit
  Zustimmung und Adresse, sonst Brief. Mahnstufe 3 immer auch als Brief.
- **E-Mail** über den bestehenden Mail-Service, PDF als Anhang. Ohne SMTP
  → `versand_fehlgeschlagen` mit Hinweis; Brief bleibt möglich.
- **Brief** → Druckstapel: Sammel-PDF (sortiert Objekt/Empfänger),
  `versendet_am` nach Bestätigung „gedruckt und kuvertiert".
- Tasks: `korrespondenz.versende_schreiben`, `korrespondenz.serienlauf_verarbeiten`.
- Bei Vorgang: `VorgangEreignis` `schreiben_versendet` (`intern=False`).

### 7.4 Serienbrief

1. Vorlage wählen (z. B. `etv_einladung`).
2. Empfängerkreis: Objekt + Filter (alle aktiven Eigentümer, `einheit_typ`,
   mit/ohne E-Mail-Zustimmung, manuelle Ab-/Zuwahl). Ein Schreiben **je
   Eigentumsverhältnis** (bei mehreren Einheiten eines Eigentümers je
   Einheit ein Schreiben — Flächenzeile und Vollmacht sind einheitsbezogen).
3. Eingabefelder einmal ausfüllen (Datum, Ort, Tagesordnung …),
   Unterzeichner wählen.
4. Vorschau mit 3 zufälligen Empfängern + Liste der nicht erzeugbaren
   Schreiben mit Ursache.
5. Freigabe → Mails raus, Briefe in den Druckstapel.

---

## 8. API-Contracts (verbindlich für Agent E)

```
GET/POST   /api/v1/korrespondenz/vorlagen/
GET/PATCH  /api/v1/korrespondenz/vorlagen/{id}/
GET/POST   /api/v1/korrespondenz/vorlagen/{id}/versionen/
PATCH      /api/v1/korrespondenz/versionen/{id}/            (nur entwurf)
POST       /api/v1/korrespondenz/versionen/{id}/freigeben/
POST       /api/v1/korrespondenz/versionen/{id}/vorschau/   {person_id, einheit_id?, eingabewerte?} → PDF (application/pdf)
POST       /api/v1/korrespondenz/vorlagen-assistent/
GET        /api/v1/korrespondenz/platzhalter/?anlass=
CRUD       /api/v1/korrespondenz/textbausteine/
CRUD       /api/v1/korrespondenz/briefboegen/               (IsAdminUser)

GET/POST   /api/v1/korrespondenz/schreiben/                 (?status=&objekt=&anlass=)
GET/PATCH  /api/v1/korrespondenz/schreiben/{id}/            (PATCH nur bei einzeln_bearbeitbar, Status zur_pruefung)
POST       /api/v1/korrespondenz/schreiben/{id}/freigeben/
POST       /api/v1/korrespondenz/schreiben/{id}/versenden/
POST       /api/v1/korrespondenz/schreiben/{id}/verwerfen/
GET        /api/v1/korrespondenz/schreiben/{id}/pdf/
POST       /api/v1/korrespondenz/druckstapel/
POST       /api/v1/korrespondenz/druckstapel/{id}/bestaetigen/

POST       /api/v1/korrespondenz/serienlaeufe/
GET        /api/v1/korrespondenz/serienlaeufe/{id}/
POST       /api/v1/korrespondenz/serienlaeufe/{id}/freigeben/
```

Permissions: `IsAuthenticated` + Objektzugriff wie bestehende Views;
Vorlagenfreigabe zusätzlich `korrespondenz.vorlage_freigeben`.

### 8.1 Frontend (Agent E)

- **Editor:** TipTap (falls Lookup 5 nichts anderes ergibt) mit
  Platzhalter-Chips (Seitenleiste + `{{`-Autovervollständigung),
  Blockrahmen je Typ, Eingabefeld-Designer (Name, Label, Typ, Pflicht),
  KI-Assistent (Abschnitt 6), **PDF-Vorschau auf echtem Briefbogen** gegen
  frei wählbaren Beispiel-Eigentümer.
- Vorlagenverwaltung (global / je Objekt, Versionen, Status).
- Postausgang, Druckstapel, Serienbrief-Assistent.
- Button „Schreiben erstellen" in Person-, Einheit- und Vorgangsansicht.

---

## 9. Prozess-Anbindung (Agent F)

### 9.1 Mahnwesen

- Codes `mahnung_stufe_1` (Zahlungserinnerung), `_2` (Mahnung), `_3`
  (letzte Mahnung), objektspezifisch übersteuerbar.
- Simulation zeigt je Mahnung die PDF-Vorschau (nicht persistiert).
- **Freigabe des Mahnlaufs = Freigabe der Schreiben**; Schreiben entstehen
  `freigegeben`, PDF → DMS, `Mahnung.pdf_pfad` befüllt, Versand nach 7.3.
  Unterzeichner = Objektbetreuer.
- Fehlt für eine vorkommende Stufe eine aktive Vorlage oder ist ein
  Schreiben nicht erzeugbar (z. B. Fußzeilen-Bankkonto), ist die Freigabe
  blockiert — außer `KORRESPONDENZ_MAHNWESEN_AKTIV=False` (bisheriger Weg,
  Doppelbetrieb bis zur Umstellung).
- Mahnsperren und Pflichtfilter bleiben unberührt.

### 9.2 Eigentümerwechsel

- In der Freigabe-Funktion (Lookup 4) per `transaction.on_commit`:
  `eigentuemer_begruessung` an den Neueigentümer (`zur_pruefung`),
  optional `eigentuemer_verabschiedung` an den Voreigentümer.
- Bedingte Blöcke: SEPA-Mandat fehlt → Hinweis + Pflichtanlage
  SEPA-Formular; Hausordnung als `objekt_kategorie`-Anlage.
- Fehler bei der Schreiben-Erzeugung rollt die Freigabe **nicht** zurück
  → FrontofficeAufgabe `schreiben_nicht_erzeugbar`.

### 9.3 Vorgang

„Schreiben erstellen" setzt `vorgang`; Anlass `vorgang_antwort` ist
`einzeln_bearbeitbar=True`. Der bestehende KI-Antwortvorschlag bleibt
unverändert.

### 9.4 Eigentümerversammlung (`apps.versammlung`)

Kein zweiter Einladungsweg. Stattdessen:
- `erzeuge_einladungs_pdf()` rendert Kopf, Anschrift, Bezugszeichen und
  Fußzeile künftig über den **Briefbogen-Service** dieses Moduls
  (gemeinsames Base-Template/CSS aus Phase 3). Das Versammlungsmodul bleibt
  Eigentümer von Termin, Ort, Tagesordnung, Versandplan und
  `EVVersandprotokoll`.
- `Eigentuemerversammlung.einladungstext` wird beim Anlegen aus der
  Vorlage `etv_einladung` (Anhang A.1) vorbelegt; Platzhalter-Gruppe
  `versammlung` (`termin`, `ort`, `tagesordnung`, `art`) liefert eine
  Kontext-Klasse, die aus der EV liest — die Eingabefelder aus A.1 entfallen
  dort.
- Vollmacht als `anlage_seite` je Person/Einheit.
- Umfang abhängig von Lookup 7; falls Phase B des Versammlungsmoduls noch
  nicht committet ist, wird 9.4 zurückgestellt und als eigener Folgeauftrag
  geführt (Orchestrator entscheidet mit Patrik).

---

## 10. Offene Punkte / Nicht-Ziele

| Punkt | Status |
|---|---|
| GmbH-Pflichtangaben in WEG-Fußzeile (5.4) | **Entscheidung Patrik**, Default an |
| Lizenz/Schriftdatei Letter Gothic MT Std | **Patrik stellt bereit**; bis dahin Fallback-Schrift |
| Unsichtbarer Marker `Porto!Demme` (weiße Schrift, oben links in der Referenz) | vermutlich Steuerzeichen für Frankierung/Druckdienstleister — **Patrik bestätigt Zweck**; wird bis dahin 1:1 unsichtbar mitgedruckt |
| „Unser Zeichen" (`PerObjNrPerNr`) | Annahme siehe Anhang C — **Patrik bestätigt Format** |
| Verknüpfung Bankkonto ↔ 18000 | Lookup 6, ggf. Feld nach 3.11 |
| SMTP auf Produktion | Voraussetzung für E-Mail-Versand |
| Hybridpost-Dienstleister per API | nicht v1.1; Druckstapel ist andockfähig |
| ETV-Einladung | über `apps.versammlung` + gemeinsamen Briefbogen (9.4); Protokoll/Beschlusssammlung nicht Teil dieser Spec |
| Portal-Postfach | später; `Schreiben.dokument` ist Grundlage |
| Juristische Prüfung der Mustertexte (Anhang A) | **vor Aktivierung durch Patrik** |

---

## 11. Tests (Pflicht vor Abnahme)

1. Vorlagen-Auflösung objektspezifisch vor global; inaktive ignoriert.
2. Freigegebene Version unveränderlich; Bearbeiten erzeugt neue Version.
3. **Determinismus:** zweimal rendern mit gleichem Kontext → identisches HTML.
4. `StrictUndefined`: fehlender Pflichtwert → Render-Fehler, Status „nicht erzeugbar", kein PDF.
5. Sandbox weist `__class__`, `.objects`, `{% import %}` ab.
6. Registry liefert je Anlass nur dokumentierte Platzhalter.
7. Pflicht-Eingabefeld fehlt → Serienlauf nicht freigebbar.
8. Anschriftzeilen: Einzelperson, Eheleute, Firma, Titel, Auslandsadresse; leere Zeilen entfallen; max. 7.
9. **Fußzeile WEG:** Objektbezeichnung + IBAN/BIC/Bank des mit 18000 verknüpften Kontos.
10. Fußzeile WEG: kein bzw. zwei passende Bankkonten → nicht erzeugbar.
11. Fußzeile Nicht-WEG: Firmenfußzeile aus Briefbogen.
12. Fußzeile erscheint auf jeder Seite inkl. Anlage-Seiten.
13. **Visuelle Regression:** Testschreiben (Anhang B) vs. Referenz-Rendering, Toleranz ±2 mm (Abschnitt 1).
14. KI-Assistent: Output mit literalem Betrag/IBAN/Datum oder unbekanntem Platzhalter wird markiert; KI erhält keine personenbezogenen Werte.
15. Freigabe erzeugt genau ein revisionssicheres `Dokument` mit korrektem Einzelkontext.
16. Kanal-Auflösung inkl. „Stufe 3 immer auch Brief"; ohne SMTP `versand_fehlgeschlagen`.
17. Mahnlauf-Freigabe erzeugt je Mahnung ein freigegebenes Schreiben, befüllt `pdf_pfad`; blockiert bei fehlender Vorlage (Flag an), unverändert bei Flag aus.
18. Eigentümerwechsel-Freigabe erzeugt Begrüßung `zur_pruefung`; Fehler rollt Freigabe nicht zurück.
19. Serienlauf: ein Schreiben je Eigentumsverhältnis; nicht erzeugbare blockieren nur sich selbst.
20. Frist verschiebt Wochenende/Feiertag auf den nächsten Werktag.
21. Volle Regression grün.

---

## 12. Aufgaben für Claude Code — Reihenfolge

> Nach jeder Phase: Migration, Tests, `docker restart immocore_celery_worker`, erst dann weiter.

1. **Phase 0 (Agent A, 7× Haiku):** Lookups 2.2 → Orchestrator passt Phasen an.
2. **Phase 1 (Agent B):** App, Modelle 3.1–3.9, Erweiterungen 3.11, Migrationen, Admin für Briefbogen/Vorlage/Textbaustein.
3. **Phase 2 (Agent B):** Render-Engine, Registry, Eingabefelder, Anschriftzeilen, Platzhalter-Endpoint; Tests 1–8, 20.
4. **Phase 3 (Agent C, parallel zu 2):** Referenzdatei ins Repo, Logos extrahieren, Briefbogen-Layout 5.2–5.4, PDF-Service, Ablage; Tests 9–13, 15.
5. **Phase 4 (Agent D):** Postausgang, Versand, Druckstapel, Serienlauf; Tests 16, 19.
6. **Phase 5 (Agent E, ab Start gegen Contracts):** Frontend 8.1 inkl. KI-Assistent; Test 14 (Backend-Teil durch Agent B).
7. **Phase 6 (Agent F):** Mahnwesen, Eigentümerwechsel, Vorgang, Versammlung (9.4); Tests 17, 18 + Einladungs-PDF der EV auf neuem Briefbogen, bestehende Versammlungstests grün.
8. **Phase 7 (Agent G, Haiku):** Seed Standard-Briefbogen + Mustervorlagen Anhang A (Status `entwurf`), Doku `docs/korrespondenz_platzhalter.md` aus Registry, Mapping-Doku aus Anhang C.
9. **Phase 8 (Agent H):** Testliste 11 komplett, Regression.
10. **Abnahme (Opus):** Layout-Abgleich, Determinismus, Tests grün, `PROJEKT_STATUS.md` ergänzt.

---

## Anhang A — Mustervorlagen (Entwurf, vor Aktivierung prüfen)

Briefkopf, Anschrift, Bezugszeichen, Objekt-/Flächenzeile, Grußformel und
Fußzeile kommen vom Briefbogen. Unten steht nur Betreff + Inhalt.
Legende: **[text]**, **[bedingt: …]**, **[tabelle: …]**, **[liste: …]**,
**[baustein: …]**, **[anlage_seite]**.

### A.1 `etv_einladung` — Einladung zur Eigentümerversammlung (nach Referenzdatei)

> Wird über `apps.versammlung` genutzt (9.4); dort kommen Termin, Ort und Tagesordnung aus der EV (`versammlung.*`). Die Eingabefelder unten gelten nur, falls die Vorlage ausnahmsweise als freier Serienbrief verwendet wird.

**Eingabefelder:** `versammlung_datum` (datum), `versammlung_uhrzeit`
(uhrzeit), `versammlung_ort` (mehrzeilig), `tagesordnung` (liste),
`art` (text, Default „ordentliche").
**Betreff:** Einberufung der Eigentümerversammlung

**[text]** wir berufen für

**{{ eingabe.versammlung_datum | datum_lang }} um {{ eingabe.versammlung_uhrzeit | uhrzeit }}**

eine {{ eingabe.art }} Eigentümerversammlung ein. Die Versammlung findet im
{{ eingabe.versammlung_ort }} statt.

Tagesordnung:
**[liste: eingabe.tagesordnung]** (nummeriert)

**[text, fett]** Die Tagesordnung können Sie im Serviceportal www.casavi.de
abrufen. Sofern die Einladungsunterlagen Entwürfe von Beschlusstexten
enthalten, handelt es sich hierbei ausdrücklich um Vorschläge zu einer
möglichen Beschlussfassung. Den Wohnungseigentümern steht es im Rahmen der
Eigentümerversammlung frei, diese Beschlussvorlage zu übernehmen, zu
ändern oder gänzlich zu verwerfen.

**[text]** Für Rückfragen stehen wir Ihnen gerne zur Verfügung.

**[anlage_seite] Vertretungsvollmacht**
Hiermit bevollmächtige ich
{{ empfaenger.anschrift_zeilen }}

☐ Herrn/Frau _______________________________
oder
☐ die Verwalterin, Demme Immobilien Verwaltung GmbH

mich in anstehenden Eigentümerversammlungen, an denen ich nicht teilnehmen
kann, zu vertreten und mein Stimmrecht auszuüben. Soweit ich zu den
Tagesordnungspunkten keine gesonderte Weisung zur Ausübung des Stimmrechts
erteile, soll mein Vertreter nach eigenem Ermessen mein Stimmrecht ausüben.

_______________________   __________________________
Ort, Datum                 Unterschrift

{{ schreiben.unser_zeichen }}

### A.2 `eigentuemer_begruessung`

**Betreff:** Willkommen in der Eigentümergemeinschaft

**[text]** wir freuen uns, Sie als neues Mitglied der Gemeinschaft der
Wohnungseigentümer {{ objekt.bezeichnung }} begrüßen zu dürfen. Als
Verwaltung sind wir ab dem {{ wechsel.wechsel_datum | datum }} Ihr
Ansprechpartner für alle Fragen rund um das gemeinschaftliche Eigentum.

Ihr monatliches Hausgeld beträgt ab dem {{ hausgeld.gueltig_ab | datum }}
{{ hausgeld.monatsbetrag | euro }} und ist jeweils zum Monatsbeginn fällig.

**[tabelle: hausgeld.positionen]**

**[bedingt: ev.sepa_mandat_fehlt]** Damit wir das Hausgeld bequem per
Lastschrift einziehen können, senden Sie uns bitte das beigefügte
SEPA-Lastschriftmandat unterschrieben zurück. Bis dahin überweisen Sie
bitte auf das Konto der Gemeinschaft (IBAN {{ bank.iban | iban }}).

**[text]** Ihr persönlicher Ansprechpartner ist {{ verwaltung.betreuer_name }},
erreichbar unter {{ verwaltung.betreuer_telefon }} oder
{{ verwaltung.betreuer_email }}. Wir freuen uns auf eine gute Zusammenarbeit.

**Anlagen:** SEPA-Mandat (pflicht, wenn `ev.sepa_mandat_fehlt`), Hausordnung (`objekt_kategorie`).

### A.3 `mahnung_stufe_1` — Zahlungserinnerung (frist_tage 14)

**Betreff:** Zahlungserinnerung Hausgeld

**[text]** bei der Durchsicht Ihres Hausgeldkontos ist uns aufgefallen,
dass folgende Beträge noch offen sind. Sicher handelt es sich um ein
Versehen.

**[tabelle: mahnung.offene_posten]**

**[text]** Offener Gesamtbetrag: {{ mahnung.gesamtbetrag | euro }}. Bitte
überweisen Sie diesen Betrag bis zum {{ mahnung.frist | datum }} auf das
unten genannte Konto der Gemeinschaft.

Sollte sich Ihre Zahlung mit diesem Schreiben überschnitten haben,
betrachten Sie es bitte als gegenstandslos.

### A.4 `mahnung_stufe_2` — Mahnung (frist_tage 10)

**Betreff:** Mahnung Hausgeld

**[text]** trotz unserer Zahlungserinnerung konnten wir bis heute keinen
Zahlungseingang für die folgenden Beträge feststellen:

**[tabelle: mahnung.offene_posten]**

**[text]** Hauptforderung {{ mahnung.summe_hauptforderung | euro }} ·
Mahngebühr {{ mahnung.gebuehr | euro }} · Verzugszinsen
{{ mahnung.zinsen | euro }} · **Gesamt {{ mahnung.gesamtbetrag | euro }}**,
zahlbar bis {{ mahnung.frist | datum }}.

**[bedingt: mahnung.gebuehr > 0]** Die Mahngebühr beruht auf dem Beschluss
der Eigentümergemeinschaft.

**[text]** Verzugszinsen berechnen wir in Höhe von 5 Prozentpunkten über
dem Basiszinssatz (derzeit {{ mahnung.zinssatz }}). Sollten Sie sich in
Zahlungsschwierigkeiten befinden, sprechen Sie uns bitte an.

### A.5 `mahnung_stufe_3` — Letzte Mahnung (frist_tage 7, immer auch Brief)

Wie A.4 mit Betreff „Letzte Mahnung Hausgeld", zusätzlich:

**[text]** Sollte der Betrag bis zum {{ mahnung.frist | datum }} nicht auf
dem Konto der Gemeinschaft eingegangen sein, werden wir die Forderung im
Namen der Gemeinschaft der Wohnungseigentümer ohne weitere Ankündigung
gerichtlich geltend machen. Die dadurch entstehenden Kosten gehen zu Ihren
Lasten.

### A.6 `eigentuemer_allgemein` — Serienbrief

Eingabefelder `betreff` (text), `inhalt` (mehrzeilig); Inhalt:
`{{ eingabe.inhalt }}` + Satz „Für Rückfragen stehen wir Ihnen gerne zur
Verfügung."

---

## Anhang B — Beispieldaten für den Layout-Test

Objekt `53` „WEG Musterstraße 1", Einheit Fläche `0012` „Wohnung 2. OG
links", Empfänger Eheleute Dr. Max und Erika Mustermann, Musterweg 5,
60311 Frankfurt am Main; Bankkonto 18000 IBAN DE00 0000 0000 0000 0000 00,
BIC TESTDEFFXXX; Unterzeichner Patrik Maurer; Vorlage A.1 mit vier
Tagesordnungspunkten (zweiseitig inkl. Vollmacht).

---

## Anhang C — Mapping der bisherigen Word-Seriendruckfelder

Damit Mitarbeiter ihre bisherigen Vorlagen wiedererkennen und Agent G
bestehende Word-Vorlagen später übertragen kann:

| Bisheriges Feld | Neuer Platzhalter | Hinweis |
|---|---|---|
| `EmpfAnsZeile1`–`7` | `empfaenger.anschrift_zeilen` | Briefbogen setzt sie ins Anschriftfeld |
| `EmpfAnredePers1` / `2` | `empfaenger.briefanrede` / `briefanrede2` | |
| `PerObjNrPerNr` | `schreiben.unser_zeichen` | **Annahme:** `objekt.objektnummer` + `/` + `Personenkonto.kontonummer` — Patrik bestätigt Format |
| `AktDatumLang` | `schreiben.datum \| datum_mittel` | |
| `ObjNr` / `ObjBez` | `objekt.objektnummer` / `objekt.bezeichnung` | |
| `FlNr` / `FlBez` | `einheit.flaechennummer` / `einheit.lage` | |
| `UserVorname` / `UserNachname` | `verwaltung.unterzeichner_vorname` / `_nachname` | |
| `ObjPerÜbBnkIBAN` | `bank.iban` | jetzt über Sachkonto 18000 |

---

*Ende der Spec.*
