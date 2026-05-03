# IMMOCORE — Versionsverlauf & Abweichungsprotokoll

**Projekt:** IMMOCORE — Hausverwaltungssystem
**Auftraggeber:** Demme Immobilien Verwaltung GmbH

---

## Versionsstrategie

| Version | Bezeichnung | Ziel |
|---------|-------------|------|
| 1.0-MVP | WEG Live | Erste produktive Version — ausschließlich WEG-Verwaltung |
| 1.x | MVP-Stabilisierung | Bugfixes, Performance, Feedback aus Live-Betrieb |
| 2.0 | Phase 2 — ZH & SEV | Zinshaus & Sondereigentumsverwaltung |
| 2.x | Phase 2 Erweiterungen | Portal, App, DATEV, Eigentümerversammlung |

---

## Version 1.0-MVP (Ziel: ~KW 28 2026)

### Geplanter Scope (SOLL laut Spezifikation v1.0 vom 03.04.2026)

**WEG-Kernfunktionen:**
- Vollständiges Django-Backend mit allen Models (inkl. ZH/SEV-Felder als optionale Felder)
- Alle ZH/SEV-Prozessendpunkte als HTTP 501 Stubs mit Marker `# ZH/SEV: extend in Phase 2`
- Hybride Buchungserkennung: Stufe 1 regelbasiert, Stufe 2 Claude API (claude-sonnet-4)
- KI-OCR für Rechnungs-PDFs (Claude API)
- Alle 3 WEG-Prozess-Wizards (11 + 7 + 8 Schritte)
- Jahresabrechnung auf Soll-Basis mit .950-Buchung
- Freigabe-Workflow mit 4 Betragsstufen
- React 18 SPA Frontend

**Explizit nicht im MVP-Scope:**
- DATEV-Export
- Eigentümer-Portal (eigene React-App)
- Mieter-App (React Native)
- DOPRE E-Mail-Eingang
- ZH/SEV Prozesse/Wizards/UI
- PDF-Versand der Jahresabrechnungen (nur Vorschau)
- Eigentümerversammlung & Beschlussverwaltung

### Abweichungen zum Soll

| Nr. | Datum | Betroffener Bereich | Soll (Spezifikation) | Ist (tatsächlich umgesetzt) | Grund | Auswirkung |
|-----|-------|--------------------|--------------------|---------------------------|-------|------------|
| — | — | — | — | — | — | — |

*Abweichungen werden hier fortlaufend eingetragen sobald bekannt.*

### Status-History

| Datum | Ereignis |
|-------|---------|
| 03.04.2026 | Spezifikation v1.0 konsolidiert, Projektstart |
| 03.04.2026 | Phase 1 abgeschlossen: 20 Models, 9 Migrations, JWT-Auth, Django Admin — Server läuft auf http://127.0.0.1:8000/admin/ |
| 03.04.2026 | Phase 2 abgeschlossen: Vollständige REST-API (alle Apps), camt.053-Parser, hybride KI-Pipeline (Stufe 1 regelbasiert + Stufe 2 Claude API), SEPA pain.001.001.09, SKR-WEG Vorlage (24 Sachkonten), Prozess-Wizard-Engine, CSV-Export, ZH/SEV-Stubs HTTP 501. `django check` ohne Fehler. |
| 07.04.2026 | Abweichung 001 erfasst: Unterkonto-Suffix erste Rücklage korrigiert von `.910` auf `.911`. `.910` ist gesperrt und wird systemseitig abgelehnt. Sachkonto-Systematik 419XX = AA.XX festgelegt. Korrektur in Code und Spezifikation ausstehend. |
| 12.04.2026 | Abweichung 001 behoben: `personen/signals.py` korrigiert (`.910+idx` → `.911+idx`), Kommentar in `konten/models.py` aktualisiert. |
| 12.04.2026 | Abweichungen 002–005 erfasst und behoben: Phase 3+4 Status in PROJEKT_STATUS.md korrigiert (❌→🔄), Section 9 API-Endpunkte nachgepflegt (❌→✅), KI-OCR in `rechnungen/services/ocr.py` ausgelagert. |
| 13.04.2026 | Infrastruktur aufgesetzt: `docker-compose.yml` erstellt, PostgreSQL 16 + Redis per Docker gestartet, alle 33 Migrations applied, Superuser `admin` angelegt. Dev-Server läuft auf http://127.0.0.1:8000. |
| 27.04.2026 | Import-Sicherheit (Abw. 007): Alle direkten Datei-Imports auf Vorschau→Bestätigen umgestellt. `EinheitViewSet`: neuer `csv-vorschau`-Endpunkt + `csv-import` akzeptiert nur noch vorgeprüfte Rows. `KontoumsatzViewSet`: neuer `camt-vorschau`-Endpunkt + `camt-upload` akzeptiert nur noch geparste Transaktionen. `BankImportViewSet` (Legacy) analog. |
| 30.04.2026 | **Mitarbeiter-Zuordnung mit Aufgabe:** `MitarbeiterObjektZuordnung` um `aufgabe`-Feld erweitert (Migration 0003). Aufgabe = Rolle des Mitarbeiters im spezifischen Objekt (z.B. Objektmanagement, Buchhaltung), muss in den Abteilungen des Mitarbeiters enthalten sein. Frontend: ObjektDetail zeigt Aufgabe farbig hervorgehoben, per-Mitarbeiter-Auswahl beim Zuordnen, nachträgliche Änderung inline. Bugfix: Render-Fallback-Wert wurde im Click-Handler nicht gespiegelt (Mitarbeiter mit einer Abteilung konnten nicht zugeordnet werden). |
| 30.04.2026 | **Freigabelimits Konfiguration:** Globale Standard-Freigabelimits über neues `FreigabelimitDefault`-Modell (Singleton, rechnungen/Migration 0004) und Endpunkt `GET/PUT /api/v1/freigabelimits-standard/`. Neue Rolle `objektmanager` überall eingebaut — `_bestimme_rolle()` erkennt Mitarbeiter mit Abteilung `objektmanagement` automatisch. Standard-Werte: ≤500 € automatisch · ≤5.000 € Objektmanager · >5.000 € Geschäftsführer. Einstellungen-Seite: neuer Tab "Freigabelimits" für globale Defaults (bearbeitbar, Stufen hinzufügen/entfernen). ObjektDetail: neuer Abschnitt "Freigabelimits" für objektspezifische Abweichungen. Abw. 002 teilweise behoben (Konfiguration ✅, automatische Enforcement beim Freigeben noch ausstehend). |

---

## Version 2.0 — Phase 2 (nach MVP-Stabilisierung)

### Geplanter Scope (SOLL)

| Feature | Beschreibung |
|---------|-------------|
| Zinshaus-Prozesse | Mieterwechsel-Wizard, Betriebskostenabrechnung, USt-Logik (Brutto/Netto je Einheit) |
| SEV-Prozesse | Einzelwohnung-Mietverwaltung, SEV-Jahresabrechnung |
| PDF-Versand | Automatischer E-Mail-Versand der Jahresabrechnungen |
| Eigentümer-Portal | Eigene React-App: Dokumente, Abrechnungen, Tickets |
| Mieter-App | React Native / Expo — separates Projekt |
| DATEV-Export | Steuerberater-Übergabe |
| Eigentümerversammlung | Beschlussverwaltung |
| DOPRE E-Mail-Eingang | Microsoft Graph API Anbindung |
| S3-Dateiablage | Migration von lokaler Ablage auf S3 |

### Abweichungen zum Soll

| Nr. | Datum | Betroffener Bereich | Soll | Ist | Grund | Auswirkung |
|-----|-------|--------------------|----|-----|-------|------------|
| — | — | — | — | — | — | — |

---

## Abweichungsprotokoll — Gesamtübersicht

*Dieses Protokoll erfasst alle Abweichungen zwischen Spezifikation und tatsächlicher Implementierung, unabhängig von der Version.*

| Nr. | Version | Datum | Schwere | Bereich | Beschreibung | Status |
|-----|---------|-------|---------|---------|-------------|--------|
| 001 | 1.0-MVP | 07.04.2026 | 1 — Kritisch | Buchhaltung / Unterkonto-Systematik | Unterkonto-Suffix für erste Rücklage war in Spezifikation und Implementierung (Phase 2) als `.910` definiert. Korrekt ist `.911` — `.910` existiert nicht und wird vom System abgelehnt. Sachkonto-Systematik folgt direkt: 419XX = AA.XX, erste Rücklage also 41911. Validierungsregel: Suffix `.910` ist gesperrt, Eingabe wird mit Fehler abgewiesen. | ✅ Behoben 12.04.2026 — `personen/signals.py:70` |
| 002 | 1.0-MVP | 12.04.2026 | 2 — Wesentlich | Rechnungen / Freigabe-Workflow | Freigabelimits (Betragsstufen, wer welchen Betrag freigeben darf) waren nicht konfigurierbar und wurden beim Freigeben nicht geprüft. | 🔄 Teilweise behoben 30.04.2026 — Konfiguration (global + je Objekt) ✅; automatische Prüfung beim `freigeben`-Endpunkt noch offen |
| 003 | 1.0-MVP | 12.04.2026 | 3 — Geringfügig | Dokumentation / Phase 4 Status | PROJEKT_STATUS.md zeigte Phase 4 (Prozesse) als ❌. Tatsächlich war die Wizard-Engine mit allen 3 Schrittketten (11+7+8) und ZH/SEV-Stubs bereits implementiert. Fehlend bleibt die Schritt-Logik (Abgrenzung, .950-Buchungen, PDF-Vorschau). | ✅ Behoben 12.04.2026 — Status auf 🔄 gesetzt |
| 004 | 1.0-MVP | 12.04.2026 | 3 — Geringfügig | Dokumentation / API-Endpunkte Section 9 | Alle 12 API-Endpunkt-Gruppen in Section 9 standen auf ❌, obwohl sie nach Phase 1+2 vollständig implementiert waren. | ✅ Behoben 12.04.2026 — alle auf ✅ aktualisiert |
| 005 | 1.0-MVP | 12.04.2026 | 3 — Geringfügig | Architektur / rechnungen | `_ki_ocr_rechnung()` war direkt in `rechnungen/views.py` implementiert — inkonsistent zur buchhaltung-App (`services/buchungserkennung.py`). | ✅ Behoben 12.04.2026 — nach `rechnungen/services/ocr.py` ausgelagert |
| 006 | 1.0-MVP | 13.04.2026 | 4 — Verbesserung | Infrastruktur / PostgreSQL Port | PostgreSQL Docker-Container läuft auf Port 5433 statt 5432, da Port 5432 durch eine lokale PostgreSQL-Installation belegt ist. `.env` und `docker-compose.yml` angepasst. | Offen — kein Handlungsbedarf solange lokale PG läuft |
| 007 | 1.0-MVP | 27.04.2026 | 4 — Verbesserung | Import-Sicherheit / Vorschau-Pflicht | Alle direkten Datei-Imports (Einheiten-CSV, CAMT.053) wurden auf ein zweistufiges Vorschau→Bestätigen-Verfahren umgestellt. Hintergrund: Einheiten-Import hatte Daten angelegt die manuell per SQL gelöscht werden mussten. | ✅ Umgesetzt 27.04.2026 |

### Schwere-Klassifizierung

| Stufe | Bezeichnung | Beschreibung |
|-------|-------------|--------------|
| 1 | Kritisch | Kernfunktion fehlt oder funktioniert nicht wie spezifiziert |
| 2 | Wesentlich | Wichtiges Feature abweichend, Workaround erforderlich |
| 3 | Geringfügig | Kleinere Abweichung ohne wesentliche Auswirkung |
| 4 | Verbesserung | Bewusste Verbesserung gegenüber Spezifikation |

---

## Nachtragshistorie zur Spezifikation

| Nr. | Datum | Inhalt | Eingearbeitet in |
|-----|-------|--------|-----------------|
| — | 03.04.2026 | Alle Nachträge konsolidiert in v1.0 | Spezifikation v1.0 |

*Zukünftige Nachträge zur Spezifikation werden hier dokumentiert bevor sie eingearbeitet werden.*

---

*Zuletzt aktualisiert: 30.04.2026*
