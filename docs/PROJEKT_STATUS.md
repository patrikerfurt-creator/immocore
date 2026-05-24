# IMMOCORE — Projekt-Status (Soll / Ist)

**Auftraggeber:** Demme Immobilien Verwaltung GmbH, Coventrystraße 32, 65934 Frankfurt am Main
**Spezifikations-Version:** 1.0 konsolidiert
**Spezifikationsstand:** 03.04.2026
**MVP-Ziel:** Live-Version in 10 Wochen (WEG-fokussiert), ca. KW 28 2026
**Stack:** React 18 + Django 5 REST + PostgreSQL 16

---

## Legende

| Symbol | Bedeutung |
|--------|-----------|
| ✅ | Vollständig umgesetzt |
| 🔄 | In Arbeit / teilweise |
| ❌ | Noch nicht begonnen |
| ⚠️ | Abweichung zur Spezifikation |
| 🚫 | Explizit nicht im Scope (Phase 2) |

---

## 1. Entwicklungsphasen (10-Wochen-Plan)

| Phase | Wochen | Scope | Status | Hinweis |
|-------|--------|-------|--------|---------|
| 1 — Foundation | 1–2 | Django-Setup, alle Models, Auth, Migrations | ✅ | Vollständig abgeschlossen |
| 2 — Buchhaltung | 3–4 | Kontenplan, Buchungsjournal, camt.053, KI-Pipeline | ✅ | Vollständig inkl. Frontend |
| 3 — Rechnungen | 5–6 | Rechnungserfassung, KI-OCR, Freigabe | 🔄 | Backend + Frontend fertig; ZUGFeRD, Celery, E-Mail, Freigabelimits fehlen ⚠️ Abw. 002 |
| 4 — Prozesse | 7–8 | Prozess-Engine, WEG-Wizards | 🔄 | Wizard-Engine + Schrittdefinitionen fertig; Schritt-Logik (Abgrenzung, .950, PDF) fehlt ⚠️ Abw. 003 |
| Zahlungsverkehr | — | SEPA Lastschrift + Zahlungen (Zusatzmodul) | ✅ | Nicht in ursprünglicher Spezifikation, vollständig implementiert |
| 5 — Frontend + Live | 9–10 | React SPA vollständig, Deployment | 🔄 | SPA weitgehend fertig; Mahnwesen-UI, Deployment fehlen |

---

## 2. Backend — Django Models

### 2.1 Kern-Models

| Model | Status | Hinweis |
|-------|--------|---------|
| Objekt | ✅ | UUID PK, objekt_typ, Adresse, Bankkonten, Freigabelimits, glaeubiger_id |
| Liegenschaft | ✅ | Sub-Model zu Objekt, ist_hauptadresse-Signal |
| Bankkonto | ✅ | konto_typ (bewirtschaftung/ruecklage), IBAN, BIC, kontoinhaber |
| Einheit | ✅ | einheit_typ Enum, Fläche, MEA |
| Person | ✅ | person_typ, ist_firma, ibans (JSONField), sepa_mandat (OneToOne) |
| SEPAMandat | ✅ | mandatsreferenz, iban, bic, unterzeichnet_am, aktiv |
| EigentumsVerhaeltnis | ✅ | Person + Einheit, beginn/ende, post_save → Personenkonto anlegen |
| HausgeldHistorie | ✅ | Historisierung Hausgeld-Soll je EigentumsVerhaeltnis + Kontoart |
| Personenkonto | ✅ | 4-stellig sequenziell, eigentuemer (FK Person), vertrag (OneToOne) |
| Unterkonto | ✅ | suffix .900/.911/.940/.950, volle_kontonummer |
| Konto (Sachkonto) | ✅ | SKR-WEG Kontenplan, Klassen 1–6, Kontoart-Enum |
| Buchungsart | ✅ | kuerzel, system_buchungsart Flag |
| Buchung | ✅ | soll_konto/haben_konto/personenkonto/soll_unterkonto, belegnr, status, parent_buchung |
| OffenerPosten | ✅ | OneToOne→Buchung, betrag_ursprung/betrag_offen, status, mahnstufe |
| SollstellungsLauf | ✅ | periode_von/bis, status-Lifecycle (simulation→freigegeben→ausgefuehrt) |
| Sollstellung | ✅ | je Buchungsart + Personenkonto, verknüpft mit Gesamt-Buchung |
| CamtImportEinstellung | ✅ | IBAN, Mapping, letzter_import |
| Kontoumsatz | ✅ | sha256_hash Duplikatschutz, ki_vorschlag (JSONField), buchung (FK) |
| Mahnlauf | ✅ | Model + API; Frontend ❌ |
| Mahnung | ✅ | Mahnstufe, Gebühren, Zinsen; Frontend ❌ |
| Mahnsperre | ✅ | gesperrt_bis, Grund; Frontend ❌ |
| Forderungsfall | ✅ | Model + API; Frontend ❌ |
| MitarbeiterObjektZuordnung | ✅ | inkl. `aufgabe`-Feld (Rolle des Mitarbeiters im Objekt), Migration 0003 |
| FreigabelimitDefault | ✅ | Singleton-Modell für globale Freigabe-Standardwerte, Migration rechnungen/0004 |
| Basiszinssatz | ✅ | gueltig_ab, satz |
| RAPPosition / RAPAufloesung | ✅ | Rechnungsabgrenzung |
| BankImport | ✅ | camt.053 Roh-Datensatz, sha256_hash |
| Jahresabrechnung | ✅ | Wirtschaftsjahr, sperren/freigeben; Frontend 🔄 |
| EinzelAbrechnung | ✅ | je Einheit, positionen/ruecklagen JSONField |
| LastschriftLauf | ✅ | positionen/ohne_mandat (JSONField), buchungen_erstellt, Migrations 0012+0013 angewendet |
| Kreditor | ✅ | name_normalisiert, iban (unique nullable) |
| Rechnung | ✅ | sha256_hash, duplikat-Erkennung, 10 Status, kostenstelle FK |
| Freigabe | ✅ | Freigabe-Event mit Rolle + Entscheidung |
| Prozess | ✅ | Wizard-Zustand, steps_data JSONField |
| Dokument | ✅ | Datei-Upload, Kategorisierung |
| Ticket | ✅ | Status-Workflow, Zuweisung |
| Mietvertrag | ✅ | Model (ZH/SEV), Wizard Phase 2 🚫 |

### 2.2 Migrations-Stand

| App | Letzte Migration | Status |
|-----|-----------------|--------|
| buchhaltung | 0015_wkz_models | ✅ angewendet |
| konten | aktuell | ✅ |
| objekte | aktuell | ✅ |
| personen | aktuell | ✅ |
| mitarbeiter | 0003_mitarbeiterobjektzuordnung_aufgabe | ✅ angewendet |
| rechnungen | 0011_wkz_models | ✅ angewendet |
| prozesse | aktuell | ✅ |

**WKZ-Models (0015 / rechnungen 0011):**
- `WiederkehrendeBuchungVorlage` — Vertrag/Bescheid, rhythmus, erste_faelligkeit, Wochenend-Regel, Vorlauf-Tage, Toleranz, gueltig_ab/bis, SEPA-Mandat-ID
- `WiederkehrendeBuchungSplit` — kontonummer, betrag, reihenfolge; M2M zur Vorlage
- `WiederkehrendeBuchungOP` — Fälligkeits-OP pro Periode, Status-Lifecycle (offen→bankabgang_erfolgt/abweichend_geklaert/verworfen)
- `KreditorOP` — Offener Posten je Kreditor + Objekt (herkunft: wkz_vorlage / manuell)

---

## 3. Backend — Services & Logik

| Service | Datei | Status | Hinweis |
|---------|-------|--------|---------|
| Sollstellungslauf | `services/sollstellung.py` | ✅ | Gesamt-Buchung + Teilbuchungen + OffenerPosten |
| SEPA Lastschrift | `services/sepa_lastschrift.py` | ✅ | pain.008.003.02 XML, gruppiert nach Fälligkeitsdatum + SeqTp |
| Mahnwesen | `services/mahnwesen.py` | ✅ | Berechnung Gebühren + Basiszinsen; keine Frontend-Page |
| Buchungserkennung KI | `services/buchungserkennung.py` | ✅ | Stufe 0 WKZ, Stufe 1 regelbasiert (IBAN), Stufe 2 Claude API |
| WKZ Vorlage-Service | `services/wkz/vorlage_service.py` | ✅ | Anlage, Split-Validierung, Freigabe-Workflow, Pausieren/Reaktivieren, Beenden, Versionierung |
| WKZ OP-Generator | `services/wkz/op_generator_service.py` | ✅ | Fälligkeitsberechnung, Wochenend-Regel, Idempotenz, Celery-Task tägl. 03:00 Uhr |
| WKZ Bank-Match | `services/wkz/bank_match_service.py` | ✅ | IBAN-/MREF-Erkennung, Toleranz-Fenster (Betrag + Tage), Auto-Match <1% |
| WKZ Buchungs-Service | `services/wkz/buchungs_service.py` | ✅ | Kassenprinzip-Aufwandsbuchung (Sammelbuchung + Teilbuchungen), verbuche_mit_anpassung |
| Rechnungs-OCR | `rechnungen/services/invoice_parser.py` | ✅ | PyMuPDF + Tesseract-Fallback + Claude API |
| Rechnungsverarbeitung | `rechnungen/services/verarbeitung.py` | ✅ | 5-stufige Duplikaterkennung, Kreditor-Abgleich, Objekt-Erkennung |
| Zinsen | `services/zinsen.py` | ✅ | Basiszinssatz-Abfrage |

---

## 4. Backend — API-Endpunkte

| Endpunkt-Gruppe | Aktionen | Status |
|-----------------|----------|--------|
| `/objekte/` | CRUD + Liegenschaften + Bankkonten + Einheiten + csv-import | ✅ |
| `/personen/` | CRUD + SEPAMandat | ✅ |
| `/eigentumsverhaeltnisse/` | POST löst Personenkonto-Signal aus | ✅ |
| `/personenkonten/` | mit-saldo, kontoauszug, buchung-detail (Buchungs-basierter Saldo) | ✅ |
| `/unterkonten/` | ReadOnly | ✅ |
| `/konten/` | Kontenplan CRUD + vorlage-anlegen + csv-import | ✅ |
| `/buchungen/` | Journal CRUD + festschreiben + stornieren + CSV-Export | ✅ |
| `/buchungsarten/` | CRUD + manuell-waehlbar | ✅ |
| `/buchungsstapel/` | CRUD + ausbuchen | ✅ |
| `/offeneposten/` | ReadOnly + Filter | ✅ |
| `/sollstellungslaeufe/` | simulieren + ausfuehren + freigeben | ✅ |
| `/sollstellungen/` | ReadOnly | ✅ |
| `/camt-einstellungen/` | CRUD + verbindung-testen + jetzt-importieren | ✅ |
| `/kontoumstaetze/` | camt-vorschau + camt-upload + buchen (Zahlungseingang/Abgang) | ✅ |
| `/bankimporte/` | ReadOnly | ✅ |
| `/mahnlaeufe/` | simulieren + ausfuehren + freigeben | ✅ |
| `/mahnungen/` | CRUD | ✅ |
| `/mahnsperren/` | CRUD | ✅ |
| `/forderungsfaelle/` | CRUD + status-wechsel | ✅ |
| `/basiszinssaetze/` | CRUD + aktuell | ✅ |
| `/rap-positionen/` | CRUD | ✅ |
| `/rap-aufloesungen/` | ReadOnly | ✅ |
| `/jahresabrechnungen/` | CRUD + sperren/freigeben | ✅ |
| `/einzelabrechnungen/` | CRUD | ✅ |
| `/lastschrift-laeufe/` | CRUD + xml (pain.008 Download + Buchungen erstellen) | ✅ |
| `/rechnungen/` | CRUD + ki-ocr + freigeben + ablehnen + buchen + sepa-export | ✅ |
| `/kreditoren/` | CRUD + deaktivieren | ✅ |
| `/wkz-vorlagen/` | CRUD + einreichen + freigeben + pausieren + reaktivieren + beenden + ersetzen + forecast | ✅ |
| `/wkz-ops/` | ReadOnly + verwerfen + manuell-verbuchen | ✅ |
| `/objekte/<pk>/wkz-vorlagen/` | gefiltert nach Objekt | ✅ |
| `/objekte/<pk>/wkz-forecast/` | 90-Tage-Liquiditätsvorschau | ✅ |
| `/kreditoren/<pk>/wkz-vorlagen/` | Vorlagen eines Kreditors über alle Objekte | ✅ |
| `/freigabelimits-standard/` | GET + PUT (globale Standard-Freigabelimits) | ✅ |
| `/mitarbeiter-zuordnungen/` | GET + POST + PATCH (aufgabe) + DELETE | ✅ |
| `/prozesse/` | start + schritte + schritt-speichern + abbrechen | ✅ |
| `/dokumente/` | Upload + Liste | ✅ |
| `/tickets/` | CRUD + Status-Workflow + zuweisen | ✅ |

---

## 5. Buchhaltungslogik — Buchungsrichtungen

| Vorgang | Soll | Haben | Implementierung | Status |
|---------|------|-------|-----------------|--------|
| Sollstellung (Hausgeld) | Personenkonto (via soll_unterkonto .900) | Erlöskonto 41XXX | `services/sollstellung.py`, Gesamt + Teilbuchungen | ✅ |
| Lastschrift-Einreichung | 13650 DCL-Debitor | Personenkonto | `LastschriftLaufViewSet.xml()`, beim XML-Download | ✅ |
| Zahlungseingang (CAMT) | 18000 Bank | Personenkonto | `KontoumsatzViewSet.buchen()` | ✅ |
| Zahlungsausgang (Rechnung) | Aufwandskonto | 18000 Bank | `RechnungViewSet.buchen()` | ✅ |
| Kontoauszug SOLL/HABEN-Logik | `soll_konto=None` → SOLL | `soll_konto gesetzt` → HABEN | `konten/views.py:kontoauszug()` | ✅ |
| Personenkonto-Saldo Übersicht | Buchungs-basiert (SOLL−HABEN) | — | `mit_saldo()` 2 Bulk-Queries | ✅ |

---

## 6. Frontend (React 18 SPA)

### 6.1 Infrastruktur

| Komponente | Status | Hinweis |
|------------|--------|---------|
| React 18 + TypeScript + Tailwind CSS | ✅ | Vite, react-router-dom v6 |
| JWT-Authentifizierung (SimpleJWT) | ✅ | Login.tsx, axios Interceptor, Token-Refresh |
| ObjektStore (Zustand) | ✅ | Globale Objekt-Auswahl in der Sidebar |
| Sidebar mit Navigation | ✅ | Kollabierbare Sektionen, Objekt-Switcher |
| API-Client (axios) | ✅ | `src/api/` mit typisierten Modulen |

### 6.2 Module / Pages

| Modul | Page | Status | Hinweis |
|-------|------|--------|---------|
| **Stammdaten** | ObjekteListe / ObjektDetail | ✅ | Bankkonto, Einheiten, Liegenschaften, Mitarbeiter-Zuordnung mit Aufgabe, Freigabelimits |
| | PersonenListe / PersonNeu / PersonDetail | ✅ | Inkl. SEPAMandat, PersonenImport |
| | EinheitenPage | ✅ | |
| | VertragsmanagementPage | ✅ | EigentumsVerhältnisse, HausgeldHistorie |
| | AbrechnungsartenPage | ✅ | |
| | VerteilerschluesselPage | ✅ | |
| | KontenplanPage | ✅ | |
| | FlaechenPage | ✅ | |
| **Buchhaltung** | Buchungsjournal | ✅ | Filter, CSV-Export |
| | BankImport (CAMT.053) | ✅ | Upload, Vorschau, Import |
| | EBanking (Kontoumsatz) | ✅ | Zahlungseingang OPO-Auswahl, Abgang Sachkonto |
| | Dialogbuchhaltung | ✅ | Manuelle Buchungsmaske, T-Konto-Layout |
| | Debitoren / Personenkonten | ✅ | Übersicht (Buchungs-Saldo), Kontoauszug, Buchungs-Detail |
| | Kontoauszug (Sachkonto) | ✅ | Gegenkonto-Anzeige inkl. Personenkonto |
| | Sollstellungen | ✅ | Simulation, Freigabe, Ausführung |
| | Mahnwesen | ❌ | Model + API vorhanden, Frontend-Page fehlt |
| | **Wiederkehrende Buchungen (WKZ)** | ✅ | VorlagenListe, VorlageWizard (4 Schritte), VorlageDetail, OPDetail, Forecast |
| **Rechnungen** | RechnungenListe + DetailModal | ✅ | KI-OCR, Freigabe, BuchungsForm |
| | KreditorenListe | ✅ | Inline-Editformular, Deaktivieren |
| **Zahlungsverkehr** | Lastschrift | ✅ | SEPA pain.008; Protokoll, Buchungen beim XML-Download |
| | Zahlungen | ✅ | SEPA pain.001 für Rechnungen |
| **Prozesse** | ProzessWizard (WEG anlegen) | 🔄 | Schritte 1–11 definiert; Schritt-Logik unvollständig |
| | Eigentümerwechsel-Wizard | 🔄 | Schritte definiert; Abgrenzung fehlt |
| | Jahresabrechnungs-Wizard | 🔄 | Schritte definiert; .950-Buchung + PDF fehlt |
| **Sonstige** | DokumenteListe | ✅ | Upload + Liste |
| | TicketsListe | ✅ | Status-Workflow |
| | MassenimportWEG | ✅ | CSV-Massenimport |
| | Einstellungen | ✅ | Tabs: E-Banking, Rechnungen, Dokumente, **Freigabelimits (neu)** |
| | Dashboard | ✅ | |

---

## 7. Zahlungsverkehr — Details

| Feature | Status | Hinweis |
|---------|--------|---------|
| LastschriftLauf erstellen | ✅ | Basis: SollstellungsLauf; aggregiert Sollstellungen je Personenkonto |
| SEPA-Mandat Prüfung | ✅ | Fehlende Mandate in `ohne_mandat` JSONField protokolliert |
| pain.008 XML Export | ✅ | Gruppiert nach Fälligkeitsdatum + SeqTp (RCUR) |
| Buchungen beim XML-Download | ✅ | Soll 13650 / Haben Personenkonto; nur beim ersten Download |
| OffenerPosten ausgleichen | ✅ | Alle offenen OPOs des Personenkontos → status='verrechnet' |
| Protokoll je Lauf | ✅ | positionen JSONField mit buchung_id, belegnr, opos_ausgeglichen |
| Status-Lifecycle | ✅ | erstellt → exportiert → eingereicht |
| SEPA Ausgangsüberweisung (pain.001) | ✅ | Für Rechnungen mit Kreditor-IBAN |

---

## 8. Offene Punkte (priorisiert)

### Kurzfristig
| Punkt | Priorität | Hinweis |
|-------|-----------|---------|
| Mahnwesen Frontend | Hoch | Mahnlauf-Übersicht, Mahnungsanzeige je Personenkonto |
| Freigabe-Enforcement | Mittel | Freigabelimits sind konfigurierbar (✅), werden aber beim `freigeben`-Endpunkt noch nicht automatisch gegen Betrag geprüft |

### Mittelfristig
| Punkt | Priorität | Hinweis |
|-------|-----------|---------|
| Wizard-Schritt-Logik vervollständigen | Mittel | Abgrenzung, .950-Buchung, PDF-Vorschau ⚠️ Abw. 003 |
| ZUGFeRD / XRechnung Parser | Niedrig | — |
| Celery Tasks (Eskalation, Fristüberwachung) | Niedrig | Redis läuft, Celery konfiguriert |
| E-Mail-Benachrichtigungen | Niedrig | Django Email + SMTP |
| BWA / Summen-Saldenliste | Niedrig | Auswertungs-Reports |

### Phase 2 (nicht im MVP-Scope)
| Punkt |
|-------|
| Rollenmanagement + objektspezifische Berechtigungen 🚫 |
| Eigentümer-Portal (separate React-App) 🚫 |
| Mieter-App (React Native) 🚫 |
| DATEV-Export 🚫 |
| Mieterwechsel-Wizard 🚫 |
| DOPRE E-Mail-Eingang (Microsoft Graph API) 🚫 |
| Deployment (Docker, CI/CD, S3) 🚫 |

---

## 9. Abweichungsprotokoll

| Nr | Beschreibung | Schwere | Status |
|----|-------------|---------|--------|
| Abw. 002 | Freigabe-Workflow: Betragsstufen konfigurierbar (Standard + pro Objekt); automatische Enforcement beim `freigeben`-Endpunkt noch ausstehend | Mittel | Teilweise behoben 30.04.2026 |
| Abw. 003 | Prozess-Wizards: Schritt-Logik (Abgrenzungsberechnung, .950-Buchungen, PDF-Vorschau) fehlt | Mittel | Offen |
| Abw. 006 | PostgreSQL Port 5433 statt 5432 (lokal belegt) | Gering | Akzeptiert |

---

## 10. Infrastruktur

| Komponente | Status | Hinweis |
|------------|--------|---------|
| PostgreSQL 16 | ✅ | Docker Container `immocore_db`, Port 5433 |
| Redis 7 | ✅ | Docker Container `immocore_redis`, Port 6379 |
| Django 5 + Python 3.11 | ✅ | `py -3.11 manage.py runserver` |
| Celery | 🔄 | Konfiguriert, keine Tasks implementiert |
| WeasyPrint | 🔄 | Installiert, noch nicht genutzt |
| Anthropic Claude API | ✅ | Buchungserkennung + Rechnungs-OCR |
| Django Storages | ✅ | Lokale Dateiablage |
| Rechnung Watch-Ordner | ✅ | `rechnung_watch` Management-Command, Ordner `C:\Projekte\immocore\Rechnungen\` |

---

*Zuletzt aktualisiert: 30.04.2026*
*Nächste Priorität: Mahnwesen Frontend-Page*
