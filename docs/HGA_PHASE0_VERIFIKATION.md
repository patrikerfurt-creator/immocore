# HGA (Jahresabrechnung) — Phase-0-Verifikation & Umsetzungsstand

Bezug: [CLAUDE_CODE_ANLEITUNG_JAHRESABRECHNUNG_v1_0.md](CLAUDE_CODE_ANLEITUNG_JAHRESABRECHNUNG_v1_0.md)
Branch: `feature/HGA_neu` · Stand: 2026-07-18

## HALT-Gate (Spec Kap. 0) — am realen Code-Stand verifiziert

| # | Frage | Ergebnis | Beleg |
|---|---|---|---|
| 1 | `Wirtschaftsplan`-Model mit Soll-Ansätzen je Konto? | ✅ JA | `apps/abrechnung_wp/models.py` — `Wirtschaftsplan` + `WirtschaftsplanPosition.konto`/`.betrag` + `WirtschaftsplanAnteil`. Schritt 3 voll umsetzbar (keine Degradation) |
| 2 | PDF-Bibliothek etabliert? | ✅ JA | WeasyPrint 65.1, produktiv in `abrechnung_wp/services/wp_pdf_service.py`. `pdf_service.py` (Phase C) setzt darauf auf |
| 3 | `HausgeldHistorie` auf `ba` migriert? | ✅ JA | Migration `personen/0010_hausgeldhistorie_ba.py`; `HausgeldSollstellung` vollständig (`sollstellungs_typ`, `soll_betrag`, `periode`, `storniert_am`, `eigentumsverhaeltnis`) |
| 4 | `Wirtschaftsjahr` als FK-Ebene Objekt→WJ→Konto? | ✅ JA | `Konto.wirtschaftsjahr`-FK (`konten/models.py:14`), `EinheitVerbrauch` vollständig |

**Kein HALT — alle vier Punkte positiv.**

## Abweichungen Spec ↔ Code (für Phasen B–D relevant)

1. `Wirtschaftsjahr.beginn_datum`/`ende_datum` sind **`@property`**, keine DB-Felder
   (abgeleitet aus `jahr` + `beginn_monat`). Kap-4.2-Query `periode__gte=wj.beginn_datum`
   funktioniert (Python-Wert), aber keine DB-seitige Annotation darauf möglich.
2. `KontoVerteilerSchluessel` hat **keinen `wirtschaftsjahr`-FK** — WJ-Zuordnung transitiv
   über `konto.wirtschaftsjahr` + Feld `gueltig_ab`. Kap-4.3-Query
   `.get(konto=konto, wirtschaftsjahr=wj)` muss in `verteilerschluessel_service` angepasst werden.
3. **Ziel-Service für Schritt 8 fehlt** — ✅ GEKLÄRT (Entscheidung Patrik 2026-07-18):
   `run_abrechnungsergebnis(objekt, wj, user)` wird in **Phase D mitgeliefert**, als
   Einschritt-Commit-Lauf nach `run_hausgeld_monat`-Muster im bestehenden
   `sollstellungslauf_service.py`. **Kein** eigener Vier-Augen-Zyklus auf dem Lauf —
   der Genehmigungsakt ist die Wizard-Freigabe in Schritt 8 (Spec ruft den Service
   synchron auf und liest sofort die Sollstellungen). Bausteine existieren bereits:
   `lege_abrechnungsergebnis_sollstellung_an` (sollstellung_service.py:145, BA 950),
   Lauf-Typ `'abrechnungsergebnis_jahr'` (models.py TYP_CHOICES).
4. **CheckConstraint-Konflikt** — ✅ ERLEDIGT (Entscheidung Patrik 2026-07-18):
   Constraint `negative_betrag_nur_korrektur` per Migration
   `0045_hga_negative_abrechnungsergebnis` erweitert:
   negativ jetzt erlaubt bei `sollstellungs_typ IN ('korrektur', 'abrechnungsergebnis')`
   (Guthaben aus Jahresabrechnung, Spec Kap. 6.2). In DB verifiziert.

## Phase A — Datenmodelle & Migration ✅ ABGESCHLOSSEN

Migration: `apps/buchhaltung/migrations/0044_hga_jahresabrechnung_umbau.py`
(Tabellen waren leer → reine Schema-Migration; vorwärts + rückwärts sauber getestet;
`makemigrations --check` = „No changes detected"; `manage.py check` sauber).

**`Jahresabrechnung`** (Kap. 3.1 + 10):
- `wirtschaftsjahr`: `IntegerField` → FK `objekte.Wirtschaftsjahr` (PROTECT)
- neu: `prozess`-FK (PROTECT, Pflicht), `freigegeben_am`, `freigegeben_von`-FK,
  `sollstellungslauf`-FK (`HausgeldSollstellungslauf`, nullable), `erstellt_am`
- `unique_together` → partielle `UniqueConstraint` `jahresabrechnung_unique_je_wj`
  (`objekt, wirtschaftsjahr` WHERE NOT status='storniert')

**`EinzelAbrechnung`** (Kap. 3.2 + 10):
- entfernt: `gebucht`, `eigentuemer_snapshot`, `personenkonto`, `pdf_pfad`
- neu: `eigentuemer`-FK (`personen.Person`), `eigentumsverhaeltnis`-FK, `sollstellung`-FK
  (`HausgeldSollstellung`, nullable), `dokument`-FK (nullable), `hinweis_eigentuemerwechsel`
- Decimals `12,2` → `14,2`
- neu: `UniqueConstraint` `einzelabrechnung_unique_je_einheit` (`jahresabrechnung, einheit`)

Mitangepasst (Bestand): `admin.py` (EinzelAbrechnungAdmin ohne `gebucht`),
`views.py` (Legacy-`EinzelAbrechnungViewSet.select_related` ohne `personenkonto`).

## Phase B — Berechnungsservices ✅ ABGESCHLOSSEN

Neues Paket `apps/buchhaltung/services/jahresabrechnung/` (alle read-only):

- **`verteilerschluessel_service.py`** (Kap. 4.3): `aktiver_vs_code(konto)` löst über
  `KontoVerteilerSchluessel.gueltig_ab` + Fallback `Konto.verteilerschluessel` auf
  (Abweichung 2 umgesetzt). `anteil_einheit(konto, einheit, wj)` — Stammdaten-VS
  (Fläche/MEA/Kopf) aus `VerteilerschluesselWert` (zeitlos=0, jahresspezifisch überschreibt),
  Verbrauchs-VS 140–145 aus `EinheitVerbrauch`. Fehlende Werte werfen
  `VerteilerschluesselFehler` (blockiert Schritt 6, kein Fallback). `mea_anteil()` für Rücklagen.
- **`kostenstellen_service.py`** (Schritt 3): Ist-Kosten je Aufwandskonto 50000–55999
  (Σ Soll − Σ Haben, Storno-Paare ausgeschlossen) vs. `WirtschaftsplanPosition`-Ansatz
  des beschlossenen/aktiven WP; Degradation ohne WP (nur Ist, kein Blocker).
- **`ruecklagen_service.py`** (Kap. 4.5): je Rücklagen-Bankkonto (reihenfolge→BA 911/912)
  Anfangs-/Endbestand aus `Kontoumsatz`-Summen (kein Saldo-Feld im System!),
  Zuführungen aus `SollstellungZahlung` (Nebenbuch), Entnahmen über Rücklagen-Sachkonto
  (abrechnungsart=BA) als Haben-Gegenkonto. Abweichung > 0,01 € → `klaerungsfall`
  (`pruefe_schritt5_blocker`). `anteil_eigentuemer` = Endbestand × MEA.

Tests: `test_verteilerschluessel_service.py` + `test_ruecklagen_service.py` — **28/28 grün**.
Keine Migration nötig (read-only). Smoke-Test gegen Live-DB erfolgreich.

**Hinweis Regression:** Volle buchhaltung-Suite hat 40 vorbestehende WKZ-Test-Errors
(`Konto.objects.create(objekt=...)` bricht seit Konto-WJ-Refactor) + 1 auto_pipeline-Failure —
unabhängig von HGA, als separate Aufgabe geflaggt.

## Phase C — Einzelabrechnung & PDF ✅ ABGESCHLOSSEN

- **`einzelabrechnung_service.py`** (Kap. 4.1/4.2/4.4): `berechne_hausgeld_soll()` exakt
  nach Kap.-4.2-Query (Nebenbuch, Soll-Prinzip — Plan-Änderungen + Nachhol-Sollstellungen
  implizit korrekt). `aktueller_eigentuemer()` zum Erstellungsdatum (Snapshot-FKs),
  `hat_eigentuemerwechsel_im_wj()` → Fußnoten-Flag. `berechne_alle_einzelabrechnungen(ja)`
  aggregiert Kostenstellen/Rücklagen einmal je Lauf (kein N+1). VS-Fehler brechen NICHT ab,
  sondern werden je Position als `fehler` in `positionen` geloggt —
  `EinzelAbrechnung.positionen_hat_fehler()` (neue Model-Methode) blockiert später die Freigabe
  (Kap. 7). Upsert je (jahresabrechnung, einheit); nur Status `entwurf` berechenbar.
  Abweichung: Einheit hat kein `aktiv`-Flag → alle Einheiten des Objekts.
- **`pdf_service.py`**: WeasyPrint über neues Template
  `buchhaltung/templates/jahresabrechnung/einzelabrechnung.html` (Layout analog
  Wirtschaftsplan-PDFs: Briefkopf Demme, Entwurfs-Banner, Kostenverteilung,
  Ergebnis-Box Nachzahlung/Guthaben, Rücklagen-Tabelle, Eigentümerwechsel-Fußnote).
  `render_einzelabrechnung_pdf()` = Schritt-7-Vorschau (Bytes, kein Dokument);
  `rendere_und_speichere()` = Schritt 8, persistiert als `Dokument`
  (kategorie='Jahresabrechnung', verknuepfung_typ='einzelabrechnung').

Tests: `test_einzelabrechnung_service.py` (Formel, Plan-Änderung anteilige Monate,
Eigentümerwechsel auf Käufer + Fußnote, VS-Fehler-Logging, Rücklagen-JSON mit MEA-Anteil,
PDF-Smoke inkl. Dokument) — **alle HGA-Suiten zusammen 46/46 grün**.
Keine Migration nötig (`positionen_hat_fehler` ist reine Python-Methode).

## Phase D — Freigabe & Nebenbuch-Anbindung ✅ ABGESCHLOSSEN

- **`sollstellungslauf_service.run_abrechnungsergebnis(objekt, wj, user)`** (Abweichung-3-
  Entscheidung umgesetzt): Einschritt-Commit-Lauf Typ `abrechnungsergebnis_jahr`,
  Periode = WJ-Ende, ohne eigenen Vier-Augen-Zyklus (Genehmigungsakt = Wizard-Freigabe).
  Duplikat-Schutz über `pruefe_duplikat_lauf`. Je EinzelAbrechnung mit Ergebnis ≠ 0 eine
  `HausgeldSollstellung(typ='abrechnungsergebnis', BA 950)` über die bestehende
  Einzelfunktion; Ergebnis == 0 wird übersprungen (kein leerer OP, Kap. 6.2).
  Guthaben = negative Sollstellung (Constraint 0045).
- **`jahresabrechnung/freigabe_service.py`** (Kap. 6.1, atomar): Validierung
  (nur `entwurf`; Vollständigkeit + keine VS-Fehler, Kap. 7) → finale PDFs als Dokument →
  `run_abrechnungsergebnis` → `sollstellung`-FK je EA → Sperre (`gesperrt`,
  `freigegeben_am/von`, `sollstellungslauf`-FK). Bewusst NICHT: Sachkontenbuchung,
  Auszahlungslauf-Trigger, PDF-Versand (Kap. 6.3).

Tests: `test_freigabe_service.py` (Ablauf, Guthaben-Sollstellung, keine Buchung,
kein Auszahlungslauf, Ergebnis-0-Fall, Validierungen, Atomic-Rollback) +
Invarianten-Suite `test_invariants.py` (alle 4 Invarianten aus Kap. 11.3).
**Alle HGA-Suiten zusammen: 59/59 grün.** Keine Migration nötig.

## Phase E — API & Wizard-UI ✅ ABGESCHLOSSEN

**Backend (Kap. 9):**
- `wizard_service.py` (neu in `services/jahresabrechnung/`): Schritt-1-Anlage
  (Entwurf-Fortsetzung; Block bei Status ≠ entwurf; WJ muss offen sein),
  Buchungsprüfung Schritt 2 (Kreditor-OPs = hartes Blocking, WKZ-OPs informativ),
  Eigentümerwechsel-Banner, Schritt-Navigation über Prozess-Engine
  (`steps_data`/`current_step`), VS-Korrektur Schritt 4 (nur aktuelles WJ,
  `gueltig_ab` = WJ-Beginn), manuelle EA-Korrektur Schritt 6 (Änderungsvermerk
  `manuell_korrigiert`/`grund` in `Prozess.steps_data`, Neuberechnung der Summen).
- `JahresabrechnungViewSet` komplett neu (Legacy-`sperren`/`freigeben` entfernt):
  POST `/api/v1/jahresabrechnungen/` (Schritt 1, **WEG-Guard → 501**),
  GET/PATCH `…/schritt/{1-8}/`, GET `…/kostenstellen/`, GET/PATCH `…/umlageschluessel/`,
  GET `…/ruecklagen/`, POST `…/einzelabrechnungen/berechnen/`,
  GET/PATCH `…/einzelabrechnungen/{einheit_id}/`, GET `…/pdf-vorschau/?einheit=`,
  POST `…/freigeben/` (prüft zusätzlich Schritt-2-/Schritt-5-Blocker; Antwort mit
  Kap.-6.4-Hinweis, KEIN Auszahlungslauf-Link). DELETE nur für Entwürfe.
  Pfad-Abweichung zur Spec: Router heißt `jahresabrechnungen` (Bestand), nicht
  `jahresabrechnung`. Serializer um Anzeige-Felder erweitert.
- Tests: `test_jahresabrechnung_api.py` — **18/18 grün** (Anlage/Fortsetzung/Block,
  501-Guard, Navigation, alle Schritt-Endpunkte, manuelle Korrektur, PDF, Freigabe
  inkl. Kreditor-OP-Blocker, Löschen).

**Frontend** (Pfad-Abweichung zur Spec: `pages/abrechnung-wp/jahresabrechnung/`
statt `pages/buchhaltung/jahresabrechnung/` — konsistent zur Menü-Gruppe „Abrechnung & WP"):
- `src/api/jahresabrechnung.ts` — typisiertes API-Modul (PDF als Blob wegen Bearer-Token)
- `JahresabrechnungListe.tsx` — Übersicht je Objekt, WEG-Hinweis, Einstieg in Wizard
- `JahresabrechnungWizard.tsx` — 8 Schritte mit `Stepper`, Blocker-Banner (Schritt 2/5),
  Ist/Plan-Tabelle, VS-Dropdown-Korrektur, EA-Tabelle mit aufklappbaren Positionen +
  manueller Korrektur (Grund Pflicht), PDF-Vorschau, Freigabe mit Kap.-6.4-Hinweis;
  gesperrte Abrechnungen read-only. Veraltete API-Stubs in `buchhaltung.ts` entfernt.
- Sidebar: neuer Punkt „Jahresabrechnung" (🧾) in Gruppe „Abrechnung & WP", Routen in App.tsx.
- `tsc --noEmit` sauber; App lädt (Sichtprüfung bis Login).

## Phase F — Integrationstests ✅ ABGESCHLOSSEN

`test_jahresabrechnung_integration.py` — voller Wizard-Durchlauf 1→8 über die API
mit 5 Einheiten (1 Eigentümerwechsel WE05, 1 Guthaben WE05), plus alle Blocker-Szenarien:
- **Happy Path:** Anlage → Schritt 2 sauber → Kostenstellen (Ist 1.000, kein WP) →
  Umlageschlüssel → Rücklagen → 5 Einzelabrechnungen (Ergebnisse +100/0/+50/+50/−300)
  → PDF-Vorschau (Fußnote WE05) → Freigabe → gesperrt, 4 Abrechnungsergebnis-Sollstellungen
  (WE02 mit 0 übersprungen), Guthaben WE05 als negative Sollstellung, keine Sachkontenbuchung.
- Guthaben → **kein** automatischer Auszahlungslauf.
- Wiederanlage derselben Objekt/WJ-Kombi blockiert (Kap. 12 Punkt 6).
- Schritt 2: offener Kreditor-OP blockiert Freigabe.
- Schritt 5: Rücklagen-Abweichung zum Bankauszug blockiert Freigabe.
- Schritt 6: fehlender Verbrauchswert (VS 140) → VS-Fehler → Freigabe gesperrt.

**Gesamtstand HGA-Tests: 84/84 grün** (7 Suiten: verteilerschluessel, ruecklagen,
einzelabrechnung, freigabe, invariants, api, integration).

## Bekannte Datenlücke (kein Code-Fehler)

Bei den importierten Testobjekten (z.B. 10001 WEG Theresenstraße 4) sind die
`VerteilerschluesselWert`-Datensätze mit `wert = NULL` angelegt (Import übernahm nur
die Einheiten-Texte „TEL"/„qm", keine Zahlen). Folge: Schritt 6 berechnet zwar
durch, liefert aber überall 0,00 € mit VS-Fehler. Für den manuellen Smoke-Test
(Kap. 12) muss ein Objekt mit vollständigen MEA-/Flächen-Zahlenwerten,
Ist-Buchungen und Hausgeld-Sollstellungen verwendet werden. Der frühere
Silent-No-Op bei Objekten ganz ohne Einheiten ist behoben (klare Fehlermeldung).

## Offen: manueller Smoke-Test (Kap. 12) — HALT-Gate vor Go-Live

Von Patrik durchzuführen an einem voll ausgestatteten Testobjekt. Alle
6 Akzeptanzpunkte sind durch die Integrationstests automatisiert vorgespielt.
