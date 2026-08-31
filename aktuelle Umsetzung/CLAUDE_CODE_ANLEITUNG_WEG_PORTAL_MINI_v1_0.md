# CLAUDE CODE — IMMOCORE
## WEG-Portal „Mini" — Eigene Daten & Einheiten (Spec 1a)

**Version:** 1.0
**Stand:** August 2026
**Status:** 🟡 Bereit zur Umsetzung — **Voraussetzung: Spec 0 (Mandantenfähigkeit) muss live sein, bevor diese Spec ausgeführt wird**
**Bezug:** `IMMOCORE_PROJEKTSTAND_AKTUELL.md`, `CLAUDE_CODE_ANLEITUNG_MANDANTENFAEHIGKEIT_v1_0.md` (Spec 0)

---

## 0. Orchestrierung

**Orchestrator: Opus.**
Plant die Gesamtumsetzung, entscheidet bei Unklarheiten zur SEPA-Mandat-Verknüpfung (Kap. 5) und gibt die Phasenübergänge frei.

**Sub-Agenten:**

| Agent | Modell | Aufgabe |
|---|---|---|
| `immo-explorer` | Haiku | Bestandsaufnahme bestehender Modelle (`Person`, `SEPAMandat`, `Eigentumsverhaeltnis`, `Einheit`) vor dem Umbau; Verifikation nach jeder Phase |
| `immo-builder` | Sonnet | Backend: `PortalZugang`-Modell, Magic-Link-Auth, Portal-Endpoints, Mandat-Sync-Logik; Frontend: React-Portal-App auf Basis des bestätigten Mockups |
| `immo-architect` | Opus | Eskalation bei Fällen, in denen die bestehende `SEPAMandat`-Datenstruktur nicht 1:1 zur hier beschriebenen Logik passt (Real-Code-vor-Spec-Prinzip) |

**Parallelisierung:** `immo-builder` kann Backend (Kap. 3–5) und Frontend (Kap. 6, auf Basis des bereits abgenommenen Mockups) als zwei parallele Teilaufgaben bearbeiten, da die API-Verträge in Kap. 4 vorab feststehen. `immo-explorer` verifiziert die bestehende `SEPAMandat`-Struktur **vor** Beginn von Kap. 5, damit `immo-architect` bei Abweichungen sofort eskalieren kann, statt dass `immo-builder` auf Annahmen baut.

---

## 1. Zweck und Abgrenzung

### 1.1 Ziel

Ein bewusst reduziertes erstes Portal-Release: Ein Eigentümer kann sich einloggen und sieht **seine Stammdaten** sowie **seine Einheiten** über alle WEGs hinweg (Mockup-Ansicht, Kap. 6), und kann **Adresse, Telefon, E-Mail und Bankverbindung** selbst ändern.

### 1.2 Explizit NICHT Teil dieser Spec

| Thema | Status |
|---|---|
| Personenkonto-Verlauf (Kontoauszug-Ansicht mit Soll/Haben/Saldo) | Folgt in Spec 1 (vollständig) |
| Dokumente-Tab | Folgt in Spec 1 (vollständig) |
| Vorgänge-Tab | Folgt in Spec 1 (vollständig) |
| Mandanten-Branding (Logo/Farben je Hausverwaltung) | Folgt in Spec 1 (vollständig) |
| Self-Service-Erstregistrierung ohne Einladung | Bewusst nicht vorgesehen — Zugang ausschließlich per Einladung (Kap. 3) |
| Änderung von Name/Geburtsdatum durch den Eigentümer selbst | Nicht vorgesehen — identitätsrelevante Stammdaten bleiben Verwaltungssache |

---

## 2. Voraussetzung

Diese Spec setzt voraus, dass **Spec 0 vollständig live ist**: Das Portal-Backend läuft innerhalb des Tenant-Schemas des jeweiligen Mandanten. Kein Code aus dieser Spec darf vor Abschluss von Spec 0 auf Produktion ausgerollt werden.

---

## 3. Zugang: Einladung + Magic Link

### 3.1 Erstzugang (nur durch die Verwaltung ausgelöst)

- Neue Aktion im internen IMMOCORE-Backend (nicht im Portal): „Portal-Zugang einladen" auf einer `Person` mit Rolle Eigentümer
- Erzeugt `PortalZugang`-Datensatz (Kap. 4.1) und versendet eine E-Mail mit Einladungs-Link (signierter Token, **72h gültig**, Einmalverwendung)
- Klick aktiviert den Zugang (`erstaktivierung_am` wird gesetzt) und loggt direkt ein

### 3.2 Folge-Logins (Magic Link, wie in Kap. „Magic Link" bereits besprochen)

- Eigentümer gibt auf der Portal-Login-Seite seine E-Mail ein
- System prüft: existiert ein **aktiver** `PortalZugang` mit dieser E-Mail? Falls ja, wird ein neuer Magic Link versendet (**15 Minuten gültig**, Einmalverwendung)
- Kein Zugang bei fehlendem oder deaktiviertem `PortalZugang` — **keine Fehlermeldung, die verrät, ob die E-Mail existiert** (Schutz vor Enumeration), stattdessen neutrale Meldung „Falls ein Zugang besteht, wurde eine E-Mail versendet"

### 3.3 Rate-Limiting

- Max. 5 Magic-Link-Anfragen je E-Mail-Adresse pro Stunde (Schutz gegen Mail-Flooding/Spam-Missbrauch)

---

## 4. Datenmodell (neu, TENANT_APPS)

### 4.1 `PortalZugang` (App `mandanten` oder neue App `portal`, immo-architect entscheidet Zuordnung)

| Feld | Typ | Anmerkung |
|---|---|---|
| `person` | OneToOneField → `Person` | |
| `aktiv` | BooleanField, default `True` | Verwaltung kann Zugang jederzeit sperren |
| `eingeladen_von` | FK → Mitarbeiter | Nachvollziehbarkeit, wer eingeladen hat |
| `eingeladen_am` | DateTimeField | |
| `erstaktivierung_am` | DateTimeField, nullable | `null` solange Einladung nicht angenommen |
| `letzter_login` | DateTimeField, nullable | |
| `email_pending` | EmailField, nullable | siehe Kap. 5.3, E-Mail-Änderung mit Bestätigung |

### 4.2 `PersonStammdatenAenderung` (Audit-Log, GoBD-Nachvollziehbarkeit)

| Feld | Typ | Anmerkung |
|---|---|---|
| `person` | FK → `Person` | |
| `feld` | CharField | z.B. `adresse`, `telefon`, `email`, `iban`, `bic` |
| `alter_wert` | TextField | |
| `neuer_wert` | TextField | |
| `quelle` | CharField | fest `"Portal-Selbständerung"` für diese Spec |
| `zeitstempel` | DateTimeField, auto_now_add | |

Jede Änderung über das Portal erzeugt **einen Eintrag je geändertem Feld** — keine Sammel-Buchung, damit einzelne Feldhistorien sauber nachvollziehbar bleiben.

---

## 5. Bearbeitbare Felder & SEPA-Mandat-Synchronisation

### 5.1 Direkt änderbar, sofort wirksam, mit Audit-Log

- Adresse (Straße, PLZ, Ort)
- Telefon

### 5.2 Bankverbindung (IBAN, BIC, Kontoinhaber)

Wie festgelegt:

1. `immo-explorer` prüft vor Umsetzung die reale Struktur von `SEPAMandat` (Feldnamen, Status-Werte) — Real-Code-vor-Spec-Prinzip
2. Beim Speichern einer geänderten Bankverbindung:
   - **Aktives SEPA-Mandat vorhanden** (Status `aktiv`, verknüpft mit dieser Person/Einheit) → IBAN/BIC/Kontoinhaber werden **direkt im bestehenden Mandat** aktualisiert, **Mandatsreferenz bleibt unverändert**. Audit-Log-Eintrag (Kap. 4.2) für `iban`/`bic` zusätzlich zum normalen Feld-Log.
   - **Kein aktives Mandat** → nur die Bankverbindung auf `Person` wird aktualisiert, kein Mandat berührt
3. Der nächste SEPA-Lastschriftlauf verwendet automatisch die neue IBAN, da die Änderung direkt im Mandat landet

> **Hinweis (kein Rechtsrat):** Ob eine Bank die Fortführung derselben Mandatsreferenz bei geänderter IBAN akzeptiert, kann je nach Bank/Verfahren variieren. Das ist an dieser Stelle bewusst so umgesetzt wie besprochen — falls es bei den ersten Lastschriftläufen nach einer Portal-Änderung zu Rückläufern kommt, ist das ein guter Anlass, das mit eurer Bank kurz zu verifizieren.

### 5.3 E-Mail-Änderung — Bestätigung an neue Adresse zwingend erforderlich

Da die E-Mail-Adresse zugleich der Login-Identifier für den Magic Link ist, **wird eine E-Mail-Änderung nicht sofort wirksam**:

1. Eigentümer trägt neue E-Mail ein → landet in `PortalZugang.email_pending`, **nicht** in `Person.email`
2. Bestätigungslink geht an die **neue** Adresse (24h gültig, Einmalverwendung)
3. Erst nach Klick wird `Person.email` aktualisiert, `email_pending` geleert, Audit-Log-Eintrag geschrieben
4. Bis zur Bestätigung bleibt die **alte** E-Mail für Logins gültig — verhindert Aussperrung bei Tippfehlern

---

## 6. Frontend: Eigene Daten & Einheiten

### 6.1 Einheiten-Ansicht

Übernahme des bereits abgenommenen Mockups 1:1: WEG-Karten (bei mehreren WEGs) → Einheiten-Tabs (bei mehreren Einheiten je WEG). In dieser Mini-Version zeigt die Einheiten-Ansicht **nur Stammdaten je Einheit** (Objektname, Einheitsbezeichnung, Miteigentumsanteil, Nutzungsart) — **keine** Saldo-Karte, **kein** Buchungsverlauf (das kommt in Spec 1 vollständig, Anbindung an `/portal/personenkonto/`).

### 6.2 Eigene-Daten-Ansicht (neu)

- Anzeigefelder (read-only): Name, Person-ID/Kundennummer falls vorhanden
- Editierbare Felder: Adresse, Telefon, E-Mail (mit Bestätigungs-Flow Kap. 5.3), Bankverbindung (mit Hinweistext zum Mandat-Bezug, wenn ein aktives Mandat existiert — Transparenz für den Eigentümer, dass die Änderung sein Lastschriftmandat mit umfasst)
- Speichern-Button je Sektion (Adresse/Kontakt getrennt von Bankverbindung), damit ein Fehler in einem Bereich nicht das Speichern des anderen blockiert

---

## 7. API-Endpoints (neu, unter `/api/v1/portal/`)

| Endpoint | Methode | Zweck |
|---|---|---|
| `/portal/auth/magic-link/request/` | POST | E-Mail entgegennehmen, Magic Link versenden (neutrale Antwort, Kap. 3.2) |
| `/portal/auth/magic-link/verify/` | POST | Token prüfen, Session/JWT ausstellen |
| `/portal/meine-einheiten/` | GET | Liste aller WEGs + Einheiten des eingeloggten Eigentümers (serverseitig strikt auf `request.user.person` gefiltert) |
| `/portal/meine-daten/` | GET | Eigene Stammdaten |
| `/portal/meine-daten/` | PATCH | Adresse/Telefon aktualisieren, Audit-Log-Eintrag |
| `/portal/meine-daten/email/` | POST | Neue E-Mail anstoßen (Kap. 5.3) |
| `/portal/meine-daten/email/bestaetigen/` | POST | Bestätigungstoken einlösen |
| `/portal/meine-daten/bankverbindung/` | PATCH | IBAN/BIC/Kontoinhaber aktualisieren inkl. Mandat-Sync (Kap. 5.2) |

Jeder Endpoint prüft serverseitig die Zuordnung zu `request.user.person` — nie ein Personen- oder Einheiten-Identifier vom Client als alleinige Autorisierung akzeptieren.

---

## 8. Akzeptanzkriterien

- [ ] Ein von der Verwaltung eingeladener Eigentümer kann den Einladungslink genau einmal verwenden, danach ist er ungültig
- [ ] Magic-Link-Login funktioniert, abgelaufene/bereits verwendete Links werden abgelehnt
- [ ] Eigentümer mit mehreren WEGs/Einheiten sieht exakt das abgenommene Mockup-Verhalten (WEG-Karten, Einheiten-Tabs)
- [ ] Adress-/Telefonänderung erzeugt je Feld einen `PersonStammdatenAenderung`-Eintrag
- [ ] Bankverbindungsänderung bei vorhandenem aktivem Mandat aktualisiert das Mandat direkt, Mandatsreferenz bleibt gleich, Audit-Log vorhanden
- [ ] Bankverbindungsänderung ohne aktives Mandat ändert nur die Personendaten, kein Mandat wird berührt
- [ ] E-Mail-Änderung wird erst nach Klick auf den Bestätigungslink in der neuen Postfach wirksam; Login mit alter E-Mail funktioniert bis dahin weiter
- [ ] Kein Endpoint liefert Daten einer anderen Person als `request.user.person` — Stichprobe mit zwei Test-Eigentümern in der Sandbox
