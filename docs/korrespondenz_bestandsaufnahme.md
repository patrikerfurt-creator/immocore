# Korrespondenz — Bestandsaufnahme Phase 0

**Erstellt:** 2026-09-29
**Grundlage:** docs/CLAUDE_CODE_ANLEITUNG_VORLAGEN_KORRESPONDENZ_v1_2.md, Abschnitt 2.2
**Methode:** 7 parallele, rein lesende Lookups (immo-explorer). Alle Befunde vom Orchestrator gegen die Spec geprüft.
**Codebasis:** Backend unter `backend/apps/…`.

---

## Zusammenfassung / Ampel

| # | Lookup | Ergebnis | Spec-Folge |
|---|--------|----------|------------|
| 1 | PDF-Engine | WeasyPrint 65.1 prod-ready; **kein** gemeinsames Base-Template | Phase 3 baut Basis neu |
| 2 | Mahnschreiben heute | `pdf_pfad` heute leer; OP-Quelle = `OffenerPosten` | wie erwartet (Doppelbetrieb) |
| 3 | Mail-Service | 3 Wege; Versammlung kann bereits PDF-Anhang | Phase 4 nutzt Versammlungs-Muster |
| 4 | Freigabe-Stellen | Andockpunkte gefunden; **kein** on_commit; EW-Freigabe nicht API-exponiert; Mahnungen entstehen bei *ausführen*, nicht *freigeben* | ⚠️ Modell 9.1 anpassen |
| 5 | Frontend-Editor | **Kein** Editor installiert | TipTap wird installiert |
| 6 | Bankkonto ↔ 18000 | **Kein** Feld; aber `zahlungsverkehr=True` ist das Zahlkonto | ✅ **kein Feld/Migration nötig** (Patrik 2026-09-29) |
| 7 | Versammlungsmodul | Phase B committet auf main | 9.4 bleibt in Scope |

**Blocker-Entscheidungen für Patrik:** Lookup 6 (neues Feld + Datenmigration), Lookup 1/7 (Refaktor-Umfang Bestands-Templates), Lookup 4 (wo docken die Mahnschreiben an — Widerspruch zu Spec 9.1).

---

## Lookup 1 — PDF-Engine (WeasyPrint)

**Befund:**
- WeasyPrint **65.1** in `requirements.txt:11`; Systemabhängigkeiten (Pango, Cairo, GdkPixbuf) in Dev- **und** Prod-Dockerfile → **prod-ready**.
- Nutzung heute in 5 Templates mit jeweils **dupliziertem Inline-CSS**, kein gemeinsames Base:
  - `backend/apps/versammlung/services/einladung_service.py:235` → `templates/versammlung/einladung.html`
  - `backend/apps/versammlung/services/beschluss_service.py:75` → `beschluss.html`
  - `backend/apps/buchhaltung/services/jahresabrechnung/pdf_service.py:355` → `jahresabrechnung/einzelabrechnung.html`
  - `backend/apps/abrechnung_wp/services/wp_pdf_service.py:83,168` → Wirtschaftsplan `gesamt.html`/`einzeln.html`
- Gemeinsamer Look (Demme-Kopf, Farbe `#1a3c5e`, Arial) nur konzeptuell, nicht code-technisch geteilt.

**Abweichung zur Spec:** Die Spec-Änderungsnote (Zeile 8) formuliert „das Versammlungsmodul nutzt künftig Briefbogen und Vorlage dieses Moduls" so, als gäbe es bereits eine gemeinsame Basis. Gibt es nicht.

**Anpassungsvorschlag:** Phase 3 legt `backend/templates/pdf_brief_base.html` + zentrale CSS an; das Versammlungsmodul zieht in 9.4 darauf um. Umzug der übrigen Bestands-Templates (Jahresabrechnung, Wirtschaftsplan, Beschluss) ist **optionaler Zusatzaufwand** und berührt Fremdmodule → nur nach Freigabe.

---

## Lookup 2 — Mahnschreiben heute

**Befund:**
- `Mahnung` in `backend/apps/buchhaltung/models.py:636`; Feld `pdf_pfad = CharField(max_length=500, blank=True)` (Zeile 656) wird **heute nirgends befüllt**, keine PDF-Erzeugung. Genau der von Spec 3.11 gewollte Doppelbetrieb.
- Berechnung in `services/mahnwesen.py`: `simuliere_mahnlauf(objekt_id, stichtag=None)` (Z. 31), `fuehre_mahnlauf_aus(lauf_id, user)` (Z. 107) erzeugt `Mahnung.objects.create(...)` (Z. 159–168). Zinsen über `services/zinsen.py:berechne_verzugszinsen(...)`.
- **OP-Quelle = `OffenerPosten`** (`models.py:262`), gefiltert `status__in=['offen','teilverrechnet'], faellig_ab__lte=stichtag`, aggregiert in `offene_posten_summe`. `HausgeldSollstellung` existiert (`models.py:1506+`), wird für die Mahnung **nicht** genutzt.

**Abweichung zur Spec:** Keine inhaltliche. Hinweis: Code-Konstante `MAHNSTUFEN` nutzt `verzug_tage` 14/28/42/56 (Fälligkeitsschwelle) und Gebühr 5/10/15 €. Die Mustervorlagen Anhang A.3–A.5 nennen `frist_tage` 14/10/7 — das ist die **Zahlungsfrist im Schreiben** (`mahnung.frist = heute + parameter.frist_tage`), nicht dieselbe Größe. Nicht verwechseln.

**Anpassungsvorschlag:** Platzhalter-Tabelle `mahnung.offene_posten` (Registry 4.2) aus `OffenerPosten` speisen. `pdf_pfad` in Phase 6 aus `Schreiben.dokument` befüllen.

---

## Lookup 3 — Mail-Service

**Befund:** Drei Versandwege:
- **Versammlung** `apps/versammlung/services/einladung_service.py:383` `_versende_mail(ev, teilnehmer, adresse, pdf_bytes, dateiname)` — kann **HTML + PDF-Anhang** (`EmailMultiAlternatives` + `.attach(dateiname, pdf_bytes, 'application/pdf')`). Globales `EMAIL_BACKEND`, Absender `DEFAULT_FROM_EMAIL`.
- **Handwerker** `apps/handwerker/tasks.py:65` — HTML, kein PDF, globales Backend.
- **Portal** `apps/portal/services/mail_service.py` — eigener SMTP-Weg über `PORTAL_FROM_EMAIL`.
- **`GraphEmailBackend`** `config/email_backends.py:44` — OAuth2, Base64-Anhänge; lokal inaktiv (MS_GRAPH_* leer).
- Objekt-Gate `objekt.mailversand_aktiv` in Handwerker (Z. 127) und Versammlung (Z. 438).

**Abweichung zur Spec:** Spec 2.1 nennt nur handwerker/portal; der **Versammlungs-Service** (bester Kandidat, weil PDF-Anhang schon funktioniert) fehlt in der Liste. Versandprüfung ist dreifach dupliziert.

**Anpassungsvorschlag:** Phase-4-Versand auf dem Versammlungs-Muster aufbauen, backend-agnostisch (SMTP oder Graph). Zentralisierung der drei Versandprüfungen ist **eigenständige Refaktorierung**, nicht Teil dieser Spec — nur als Empfehlung notiert.

---

## Lookup 4 — Freigabe-Stellen

**Befund:**
- **Eigentümerwechsel:** `backend/apps/buchhaltung/services/eigentuemerwechsel_korrektur_service.py:89` `vorschau_committen(vorgang, freigabe_user, auszahlungs_iban, auszahlung_unterdruecken=False)`, `@transaction.atomic`, setzt Status→`freigegeben`, ruft `_erzeuge_frontoffice_aufgabe_neueigentuemer(vorgang)` (Z. 139). **Wird derzeit von keinem View-Endpoint aufgerufen** (nur Tests).
- **Mahnlauf-Freigabe:** `backend/apps/buchhaltung/views.py:708` `MahnlaufViewSet.freigeben()` — setzt nur Status→`freigegeben`, **kein** `@transaction.atomic`.
- **Mahnlauf-Ausführung:** `services/mahnwesen.py:108` `fuehre_mahnlauf_aus(lauf_id, user)`, `@transaction.atomic`, erzeugt hier die `Mahnung`-Objekte (Z. 159–168). View-Action `views.py:700` `ausfuehren()`.
- **Nirgends** `transaction.on_commit` oder post_save-Signale.

**Abweichung zur Spec (wichtig):** Spec 9.1 sagt „**Freigabe des Mahnlaufs = Freigabe der Schreiben**". Im Code entstehen die `Mahnung`-Objekte aber erst bei **`ausfuehren`**, nicht bei `freigeben`. Die tatsächliche Sequenz ist `simulieren → freigeben (nur Status) → ausfuehren (erzeugt Mahnungen)`. Ebenso ist die Eigentümerwechsel-Freigabe nicht API-exponiert (Spec 9.2 setzt eine Freigabe-Funktion voraus).

**Anpassungsvorschlag (Phase 6, zur Bestätigung):**
- Mahnschreiben an `fuehre_mahnlauf_aus` (nach `Mahnung.objects.create`, Z. 168) per `transaction.on_commit` koppeln — **nicht** an `freigeben`. Das ist die einzige Stelle, an der die Mahnungen existieren.
- Begrüßungsschreiben an `vorschau_committen` (nach Z. 139) per `transaction.on_commit`.
- Klären, ob die EW-Freigabe im MVP überhaupt über einen Endpoint läuft oder nur aus dem Wizard.

---

## Lookup 5 — Frontend

**Befund:**
- **Kein Rich-Text-Editor** installiert (`frontend/package.json` — kein tiptap/quill/slate/draft-js/ckeditor/tinymce).
- KI-Antwortvorschlag-Muster: `frontend/src/pages/vorgaenge/VorgangDetail.tsx:575` + Client `frontend/src/api/vorgaenge.ts:54–64` (`antwortVorschlagGenerieren` via React-Query `useMutation`).
- API-Client modular: `src/api/<app>.ts` + zentrale axios-Instanz `client.ts` (JWT-Interceptor, baseURL `/api/v1`). Backend-Router-Muster `config/urls.py:138` (`include('apps.versammlung.urls')`).
- **Keine** PDF-Viewer-Lib; Bestandsmuster ist Download/`openDatei` (`VersammlungDetail.tsx`).

**Abweichung zur Spec:** Keine — der Spec-Vorbehalt „TipTap, falls Lookup 5 nichts anderes ergibt" greift; TipTap wird installiert.

**Anpassungsvorschlag:** Phase 5: `@tiptap/react` + StarterKit installieren; Vorlagen-Assistent nach `vorgaenge`-Muster; Editor-PDF-Vorschau über `application/pdf` + Blob-URL/iframe, keine neue Lib.

---

## Lookup 6 — Bankkonto ↔ Sachkonto 18000 (Blocker)

**Befund:**
- `objekte.Bankkonto` (`backend/apps/objekte/models.py:101`) hat **kein** Feld Richtung Konto/Sachkonto. Felder: `objekt, konto_typ('bewirtschaftung'|'ruecklage'), bezeichnung, iban, bic, kontoinhaber, reihenfolge, aktiv, zahlungsverkehr`.
- `konten.Konto` (`backend/apps/konten/models.py:7`) hat **kein** Feld Richtung Bankkonto; jahresgebunden über `wirtschaftsjahr`-FK; `kontonummer` = CharChar(6).
- Verknüpfung heute **nur per Konvention** `konto_typ→kontonummer` (`bewirtschaftung→18000`, `ruecklage→18911`), dreifach hardkodiert: `ebanking_buchungs_service.py:64` `_ermittle_bank_sachkonto`, `ebanking_erkennungs_service.py:50`, `camt_matching_service.py:216`; zusätzlich direkt in `views.py:585` und `sepa_lastschrift.py:174`. Keine DB-Erzwingung.
- (Nebenfund: `Unterkonto` hat FKs `sachkonto`+`bankkonto`, ist aber Personenkonto-bezogen, **nicht** die gesuchte Objekt-Bank-Verknüpfung.)

**Abweichung zur Spec:** Spec 5.4/3.11 setzt „das mit Sachkonto 18000 verknüpfte Bankkonto" voraus. Ein solches Feld existiert nicht.

**Anpassungsvorschlag (REVIDIERT nach Patrik-Vorgabe 2026-09-29):** Kein Feld `sachkonto_nr`, keine Datenmigration. Das Fußzeilen-Bankkonto ist das Konto mit dem Schalter „für den Zahlungsverkehr verwenden" = `Bankkonto.zahlungsverkehr=True` (+ `aktiv=True`). Nachträglich verifiziert:
- `Bankkonto.save()` (`objekte/models.py:127`) erzwingt Exklusivität je Objekt (setzt andere auf False); Frontend `ObjektDetail.tsx:1341` ist Radio-Button.
- Bestehende Nutzung identisch: `.filter(zahlungsverkehr=True, aktiv=True).first()` in `sepa_lastschrift.py:304`, `views_wkz.py:459`, `rechnungen/views.py:760,1220`.
- Nicht DB-erzwungen (kein UniqueConstraint). Render-Service nutzt `.get(objekt=…, zahlungsverkehr=True, aktiv=True)` und wirft bei 0 oder >1 → „nicht erzeugbar" (deckt Spec 5.4 / Tests 9–10 ab).
- **Optional (Entscheidung offen):** partielle Eindeutigkeits-Constraint als Schema-Migration (kein Dateneingriff) zur Härtung gegen Direkt-SQL/Race.

Der ursprüngliche Spec-Text 5.4 („mit Sachkonto 18000 verknüpft") wird durch die direktere, im Code bereits etablierte Regel `zahlungsverkehr=True` ersetzt — bewusste, von Patrik vorgegebene Abweichung.

---

## Lookup 7 — Versammlungsmodul (Blocker)

**Befund:**
- `apps.versammlung` vollständig, **committet auf `main`** (`8e5974a`, 2026-08-20, „Phasen A, B, D"), keine uncommitteten Änderungen. Live-Deploy sehr wahrscheinlich, nicht live-verifiziert.
- Modelle `models.py:62` `Eigentuemerversammlung.einladungstext` (Z. 155), `EVVersandprotokoll` (Z. 714) mit Kanal `epost`.
- Service `einladung_service.py`: `erzeuge_einladungs_pdf(ev, erstellt_von, anlagen_ids=None)` (Z. 239), `versandplan(ev)` (Z. 287), `versende_einladungen(ev, versendet_von, plan=None)` (Z. 407). Personalisierte PDFs je Person, Anlagen-Merge via PyMuPDF.
- Template `einladung.html`: Letterhead **hardcoded** (Z. 120–131), Anschriftfeld nutzt heute `person.adresse` (zusammengesetzt), Running-Footer, Bezugszeichen/Termin-Box.
- `einladungstext` wird beim Anlegen aus `EINLADUNGSTEXT_VORLAGE` (`ev_service.py:75`, in `erstelle_ev()`) vorbelegt.

**Abweichung zur Spec:** Nur die noch fehlende Briefbogen-Entkopplung (Letterhead hardcoded statt über `Briefbogen`).

**Scope-Entscheidung:** Phase B committet → **9.4 bleibt in Scope** (nicht zurückgestellt). Phase 3 baut den gemeinsamen Briefbogen; Versammlung zieht danach darauf um.

**Migrationshinweis:** Beim Umzug des EV-Templates die Anschrift von `person.adresse` auf die führenden Einzelfelder `strasse/hausnummer/plz/ort` (Abw. 009) umstellen, konsistent mit der `anschrift_zeilen`-Logik (Spec 4.2).

---

## Contracts aus Phase 2 (verbindlich für Phase 3/5/7)

**Render-Engine:** `render_service.render(version, kontext, eingabewerte, *, bausteine=None) -> RenderErgebnis(html, betreff, snapshot, fehler)`. Jinja2 SandboxedEnvironment + StrictUndefined + AST-Härtung; nur 8 Filter (`euro, datum, datum_lang, datum_mittel, uhrzeit, iban, upper, default`). Fehlender Pflichtwert → `fehler`, kein HTML.

**Blockstruktur `inhalt` (vom Builder festgelegt):**
- `text`, `bedingt`, `anlage_seite`, `baustein` → HTML-Fragmente (Text ohne Tags → `<p>`).
- `tabelle`/`liste` haben Feld `quelle`; `bedingt` hat `bedingung` (Jinja-Ausdruck); `anlage_seite` hat `titel`.
- Bausteine werden über `bausteine={code: inhalt}` übergeben (`lade_bausteine`).

**Kontext-Gruppen (für Kopf/Fuß in Phase 3):** `empfaenger.anschrift_zeilen` (max 7, >7 → `AnschriftZuLang`, Phase 4 fängt es als „nicht erzeugbar"), `empfaenger.briefanrede/briefanrede2`; `verwaltung.firma/unterzeichner_*/betreuer_*`; `schreiben.unser_zeichen` (= `objektnummer/Personenkonto.kontonummer`), `ihr_zeichen`, `ihr_schreiben_vom`, `datum`, `nummer`; `bank.weg_name/iban/bic/bankname/kontoinhaber/glaeubiger_id` — **nur bei `objekt_typ=='WEG'`**, Quelle = Bankkonto `zahlungsverkehr=True` (0/>1 → Gruppe fehlt → Render-Fehler). `bank.bankname` per `schwifty` aus IBAN.

**Zu prüfen mit Patrik (später, blockiert nicht):** `mahnung.zinssatz` = Basiszins + 5 %-Punkte (Verbraucher) vs. Spec-Formulierung A.4; `mahnung.summe_hauptforderung` aus `Mahnung.offene_posten_summe`, `offene_posten`-Tabelle live aus `OffenerPosten` → mögliche Drift, in Phase 6 Snapshot zum Mahnlauf-Zeitpunkt erwägen; `mahnung.stufe` Rohwert 0–3 vs. Anlassnamen `_1.._3` (Phase-6-Mapping).

## Entscheidungen Phase 4 (Patrik 2026-09-29)

- **E-Mail-Sperre (A):** Objekt-Schalter `Objekt.mailversand_aktiv` gilt AUCH für Korrespondenz-Mails (konsistent mit Handwerker/EV). Ohne Freischaltung → `versand_fehlgeschlagen`, Brief bleibt möglich.
- **E-Mail-Sperre (B):** Ein Schreiben OHNE Objekt wird durch diesen Schalter NICHT blockiert (Sperre greift nur bei gesetztem Objekt). → Fix in Phase 5 (`schreiben_service.py`).
- **Betrieb:** Backend- und Worker-Image mussten wegen der neuen Dependency Jinja2 neu gebaut werden (requirements.txt war korrekt, Images 25 h alt). Live via `deploy.sh` (`build --no-cache`) automatisch; lokal am 2026-09-29 neu gebaut.

## Entscheidungen Phase 6 (Patrik 2026-09-30)

- **9.1 Mahnwesen:** EIN Schalter „Mahnlauf an/aus" (`KORRESPONDENZ_MAHNWESEN_AKTIV`, Default AUS, über settings/.env.prod — Admin live nicht erreichbar). Solange aus: bisheriger Mahnlauf unverändert.
- **Neue Anforderung:** Mahnbrief führt den **Kontoauszug des Personenkontos als Anlage** mit. Vor finaler Umstellung: Muster (Mahnbrief + Kontoauszug) zur Sichtprüfung (Sub-HALT).
- **9.4 Versammlung:** jetzt mitmachen (EV-Einladung auf gemeinsamen Briefbogen), mit Vorher/Nachher-HALT.
- **Kleine Backend-Nacharbeiten** (Druckstapel-Leseendpoint, `vorlage_version` im Schreiben-Detail, Serienlauf-Abbruch): in Phase 6 mitnehmen.
- **Mahn-Konfiguration je Objekt (Patrik 2026-09-30, bestätigt):** (1) feste Mahngebühr je Objekt (gleicher Betrag je Stufe), MUSS je Objekt eingestellt werden — ohne Einstellung kein Mahnlauf; (2) Anzahl Mahnstufen bis zum Anwalt je Objekt, Default 2, nach letzter Stufe → Forderungsfall; (3) Verzugszinsen nur bei separatem Schalter je Objekt, Default AUS; (4) Fristen bleiben global; (5) Text-Mapping stufenabhängig: letzte Stufe → „letzte Mahnung" (A.5), frühere → „Mahnung" (A.4). Ändert Live-Mahnberechnung → immo-architect-Check erfolgt.
- **Mahn-Konfig FINAL (Patrik 2026-09-30, nach Architekt-Check):** Modell `MahnEinstellung` (OneToOne→Objekt, in apps.buchhaltung): `mahngebuehr` (Pflicht, fest je Stufe), `anzahl_mahnstufen` (Default 2), `zinsen_erheben` (Default False). Ohne Konfig → Mahnlauf blockiert (kein Backfill). Berechnung immer konfig-getrieben; `KORRESPONDENZ_MAHNWESEN_AKTIV` bleibt nur Brief-Schalter. Globale Staffel NEU: Stufe 1 = 15 Tage Verzug / Frist 14 Tage; Stufe 2 = 30 Tage Verzug / Frist 10 Tage (ersetzt 14/28/42/56). Zinssatz-Typ fest „Verbraucher" (+5 %). „==3"-Annahme an 3 Stellen (Forderungsfall, kanal_service, STUFE_ZU_VORLAGE) → relativ auf „letzte Stufe". Verhaltensänderung: Zinsen früher faktisch immer, jetzt nur bei Schalter. Vor Live: Mahnlauf-/Beleg-Zählabfrage.

## Offene Entscheidungen (Halt vor Phase 1)

| # | Punkt | Vorschlag Orchestrator | braucht |
|---|-------|------------------------|---------|
| E1 | Fußzeilen-Bankkonto (Lookup 6) — **REVIDIERT/ENTSCHIEDEN (Patrik 2026-09-29)** | Auswahl über `Bankkonto.zahlungsverkehr=True` (+ `aktiv=True`); **kein** Feld `sachkonto_nr`, **keine** Datenmigration. Render-Regel: `.get(...)` → 0 oder >1 = „nicht erzeugbar" (Spec 5.4). Zählabfrage 2026-09-29: 40 Objekte, 0 Duplikate → optionale Eindeutigkeits-Constraint wäre konfliktfrei möglich | ✅ (Constraint-Frage offen) |
| E2 | Refaktor-Umfang Base-Template (Lookup 1/7) | **ENTSCHIEDEN (a), Patrik 2026-09-29:** Phase 3 baut neue Basis; nur `einladung.html` zieht in 9.4 um; Jahresabrechnung/Wirtschaftsplan/Beschluss/Protokoll bleiben unangetastet | ✅ |
| E3 | Andockpunkt Mahnschreiben (Lookup 4 vs. Spec 9.1) | **ENTSCHIEDEN (ok), Patrik 2026-09-29:** Schreiben entstehen in `fuehre_mahnlauf_aus` (ausführen) direkt im Status `freigegeben`; Bedienablauf unverändert | ✅ |
| E4 | GmbH-Pflichtangaben in WEG-Fußzeile (Spec 5.4/10) | **ENTSCHIEDEN (Patrik 2026-09-29): Schalter am Briefbogen, Default AN** | ✅ |
| E5 | Schrift Absenderzeile/Infoblock/Fußzeile (Spec 5.2/10) | **ENTSCHIEDEN (Patrik 2026-09-29): ARIAL** statt Letter Gothic MT Std → kein Lizenz-/Fallback-Thema; ganze Briefbogen in Arial. Hinweis: Kleintext-Blöcke (Infoblock/Fußzeile) sehen dadurch minimal anders aus als die Referenz; ±2 mm gilt für Block-Positionen | ✅ |
| E6 | Marker `Porto!Demme` (Spec 10) | 1:1 unsichtbar mitdrucken bis Bestätigung des Zwecks | offen (blockiert nicht) |
| E7 | Format „Unser Zeichen" `PerObjNrPerNr` (Anhang C) | **ENTSCHIEDEN (Patrik 2026-09-29):** `objektnummer` + `/` + `Personenkonto.kontonummer` | ✅ |
| E1-Constraint | Eindeutigkeits-Constraint auf `Bankkonto.zahlungsverkehr` | **NICHT umgesetzt** (nicht freigegeben); Eindeutigkeit via `save()` + Radio + saubere Daten | — |
