# Modul Buchhaltung — Prozessbeschreibung

**Projekt:** IMMOCORE
**Stand:** 2026-04-19
**Status:** Spezifikationsentwurf v0.2
**Geltungsbereich:** WEG-, ZH- und SEV-Verwaltung

---

## 1. Zielsetzung

Das Modul **Buchhaltung** ist die zentrale buchhalterische Arbeitsumgebung in IMMOCORE. Es bildet die doppelte Buchführung WEG-konform auf Basis des SKR-WEG-Kontenrahmens ab und dient als Integrationsschicht zwischen Objektanlage, BelegPilot, E-Banking, Mahnwesen, Forderungsfall, Rücklagen, Jahresabschluss und Casavi.

Das Modul ist **objektstrikt mandantenfähig**: jede Buchung ist eindeutig einem Objekt und einem Buchungsjahr zugeordnet. Jede Buchung trägt zusätzlich eine **Buchungsart (BA)** — das zentrale Steuerungsattribut für Abrechnungslogik, Rücklagenrelevanz und Umlageverhalten (siehe Abschnitt 3).

---

## 2. Menüstruktur

```
Buchhaltung
├── Debitoren / Eigentümerkonten
├── Sollstellungen
├── E-Banking
│   └── Einstellungen (CAMT-Import-Ordner)
├── Buchungserfassung / Buchungsjournal   ← Dialogbuchhaltung
├── Kreditoren                             [Roadmap — DOPRE-Ansatz]
├── Mahnwesen
├── Forderungsfälle
├── Rücklagen
├── Rechnungsabgrenzung (ARAP/PRAP)
├── Kontenrahmen / Kontenplan
├── Jahresabschluss / Saldenvorträge
└── Auswertungen
```

Alle Menüpunkte sind objektbezogen — die Objektwahl erfolgt global in der Kopfzeile (aktives Objekt, umschaltbar), nicht je Untermenü.

Zugriff ausschließlich für Rollen mit `perm.buchhaltung.access` (Buchhalter, Objektbetreuer mit Buchhaltungsfreigabe, Geschäftsführung).

---

## 3. Querschnittskonzept: Buchungsart (BA)

### 3.1 Zweck

Jede Buchung wird genau **einer Buchungsart** zugeordnet. Die BA steuert:

- **Abrechnungsrelevanz** (Einzelabrechnung / Gesamtabrechnung / Rücklagenentwicklung)
- **Umlagepflicht** (Umlageschlüssel Pflicht / optional / gesperrt)
- **Kontenlogik** (Default-Kontierung, erlaubte Kontoarten für Soll/Haben)
- **Belegpflicht** (Beleg Pflicht / optional)
- **Beschlusspflicht** (Beschluss-Referenz Pflicht bei Rücklagen-Entnahme, Sonderumlage)
- **Vier-Augen-Schwelle** (ab welchem Betrag Freigabe nötig)
- **Sperre nach Jahresabschluss** (z. B. Saldenvorträge gesperrt außer per Admin-Release)

Diese Attribute sind als Metadaten je BA in der Datenbank gepflegt (`model Buchungsart`), nicht im Code hartkodiert.

### 3.2 BA-Katalog (Vorschlag)

| BA-Nr. | Kürzel | Bezeichnung | Einzelabr. | Gesamtabr. | Rücklage | Umlage |
|---|---|---|---|---|---|---|
| **001** | `SAVO-S` | Saldenvortrag Sachkonten | — | — | — | — |
| **002** | `SAVO-P` | Saldenvortrag Personenkonten | — | — | — | — |
| **003** | `SAVO-K` | Saldenvortrag Kreditoren | — | — | — | — |
| **004** | `SAVO-B` | Saldenvortrag Bankkonten | — | — | — | — |
| **010** | `HGV` | Sollstellung Hausgeldvorauszahlung | Soll-Seite | Soll-Seite | — | nein (Vorauszahlung) |
| **011** | `RLZ` | Sollstellung Rücklagenzuführung | — | — | ja (Zuführung) | nein |
| **012** | `SU` | Sonderumlage | ja | ja | optional | ja |
| **013** | `NZJA` | Nachzahlung aus Jahresabrechnung | — | — | — | — |
| **014** | `GJA` | Guthaben aus Jahresabrechnung | — | — | — | — |
| **015** | `MIETE` | Miete (ZH/SEV) | — | — | — | — |
| **016** | `NKVZ` | Nebenkostenvorauszahlung (ZH/SEV) | — | — | — | — |
| **020** | `EING-P` | Eingang Personenkonto (Zahlung) | — | — | — | — |
| **021** | `AUSG-P` | Ausgang Personenkonto (Erstattung/Rückzahlung) | — | — | — | — |
| **022** | `UMB-P` | Umbuchung Personenkonto | — | — | — | — |
| **023** | `MAHNG` | Mahngebühr | — | — | — | — |
| **024** | `VERZZ` | Verzugszinsen (§ 288 BGB) | — | — | — | — |
| **040** | `SACH-A` | Sachkontenbuchung Aufwand (Bewirtschaftung) | **ja** | **ja** | nein | **ja (Pflicht)** |
| **041** | `SACH-AR` | Sachkontenbuchung Aufwand (Rücklage, `.911`) | nein | nein | **ja (Entnahme)** | nein |
| **042** | `SACH-E` | Sachkontenbuchung Ertrag (Bewirtschaftung) | **ja** | **ja** | nein | ja |
| **043** | `SACH-ER` | Sachkontenbuchung Ertrag (Rücklage, Zinsen) | nein | nein | **ja** | nein |
| **044** | `SACH-U` | Sachkonten-Umbuchung (nicht abr.-relevant) | — | — | — | — |
| **050** | `EING-K` | Eingang Kreditor (Rechnungseingang) | indirekt | indirekt | — | — |
| **051** | `AUSG-K` | Ausgang Kreditor (Zahlung) | — | — | — | — |
| **052** | `GS-K` | Kreditoren-Gutschrift | — | — | — | — |
| **053** | `SKT-K` | Skonto / Rabatt Kreditor | — | — | — | — |
| **080** | `ARAP-B` | ARAP-Bildung | — | — | — | — |
| **081** | `ARAP-A` | ARAP-Auflösung | ja | ja | — | ja |
| **082** | `PRAP-B` | PRAP-Bildung | — | — | — | — |
| **083** | `PRAP-A` | PRAP-Auflösung | ja | ja | — | ja |
| **090** | `JA-ABS` | Jahresabschluss-Buchung | — | — | — | — |
| **091** | `RL-ENT` | Rücklagenentwicklung (Jahresbuchung) | — | — | **ja** | — |
| **098** | `STO` | Storno (spiegelt Original-BA) | — | — | — | — |
| **099** | `KOR` | Korrekturbuchung (spiegelt Original-BA) | — | — | — | — |

**Hinweis:** Die BA-Nummern sind ein *Vorschlag* — offene Blöcke (030–039, 060–079) sind bewusst für Erweiterungen frei. Die Abrechnungslogik (Modul Jahresabrechnung) filtert ausschließlich über BA — kein direkter Kontenfilter.

### 3.3 Technisches Modell (skizziert)

```python
class Buchungsart(models.Model):
    nr = models.CharField(max_length=3, unique=True)   # "040"
    kuerzel = models.CharField(max_length=12)
    bezeichnung = models.CharField(max_length=120)
    einzelabrechnung = models.CharField(
        choices=[("ja","ja"),("nein","nein"),("anteilig","anteilig")]
    )
    gesamtabrechnung = models.BooleanField(default=False)
    ruecklagen_relevant = models.BooleanField(default=False)
    umlage = models.CharField(
        choices=[("pflicht","pflicht"),("optional","optional"),("gesperrt","gesperrt")]
    )
    beleg_pflicht = models.BooleanField(default=True)
    beschluss_pflicht = models.BooleanField(default=False)
    vier_augen_schwelle = models.DecimalField(null=True, blank=True)
    sperre_nach_jahresabschluss = models.BooleanField(default=True)
    default_konto_soll_pattern = models.CharField(blank=True)   # z.B. ".911"
    default_konto_haben_pattern = models.CharField(blank=True)
```

Jede `Buchung` trägt `buchungsart = ForeignKey(Buchungsart)`. Die Abrechnungslogik liest ausschließlich diese Relation.

---

## 4. Untermenü: Debitoren / Eigentümerkonten

### 4.1 Zweck

Übersichts- und Detailansicht aller **Personenkonten** des aktiven Objekts. Kombiniert Debitorensicht (offene Posten) mit Konto-Drill-Down (Soll/Haben-Bewegungen).

### 4.2 Listenansicht

Tabellarische Darstellung aller Personenkonten des Objekts:

| Spalte | Quelle |
|---|---|
| Einheits-Nr. | Objektanlage |
| Eigentümer (Name, Anschrift-Kurz) | Person |
| Konto-Nr. | Kontenrahmen |
| Saldo (aktuell) | Summe aller Buchungen |
| Offene Posten (Anzahl / Summe) | ungeklärte Soll-Salden aus BA 010–016 |
| Älteste OP (Datum) | Fälligkeitsreferenz |
| Mahnstatus | Mahnmodul (Stufe 0–3 + Forderungsfall) |
| Letzte Zahlung | BA 020 |

Filter: Alle / Nur OP / Nur Mahnsperre / Nur im Forderungsfall / Eigentümerwechsel im Zeitraum.

Sortierung: Einheits-Nr. (Default), Saldo absteigend, älteste OP.

Export: PDF (Kontoauszug-Sammlung), Excel (flache Liste).

### 4.3 Detailansicht (Drill-Down bei Klick)

Klick auf eine Zeile öffnet den **Kontoauszug Personenkonto**:

**Kopfbereich:**
- Eigentümer (Name, Adresse, Kommunikationsdaten, Beiratsrolle falls vorhanden)
- Einheit (Lage, Miteigentumsanteil, Umlageschlüssel-Werte)
- Aktueller Saldo + Rücklagenanteil (kumuliert)
- Mahnstatus + Forderungsfall-Info

**Buchungsliste (Kernanforderung):**

| Spalte | Format |
|---|---|
| Buchungsdatum | TT.MM.JJJJ |
| Belegdatum | TT.MM.JJJJ |
| Beleg-Nr. | String |
| BA-Nr. + Kürzel | "010 HGV" |
| Buchungstext | Text |
| Soll (€) | Zahl, rechtsbündig |
| Haben (€) | Zahl, rechtsbündig |
| Saldo (€) | fortlaufend |
| OP-Status | offen / verrechnet / storniert |

- Zwei-Spalten-Darstellung (Soll | Haben) wie im klassischen Kontoauszug.
- Laufender Saldo je Zeile.
- Farbcodierung: offene Posten (rot), verrechnet (grün), storniert (grau durchgestrichen).
- Klick auf Buchung → Modal mit Belegvorschau (aus BelegPilot) + Gegenkonto-Info.
- Zeitfilter: Aktuelles Wirtschaftsjahr (Default), Vorjahr, frei wählbar, alle.

**Aktionen im Detail:**
- Kontoauszug als PDF exportieren (formatiert für Eigentümer-Versand)
- Mahnsperre setzen/aufheben
- Manuelle Zahlung buchen (öffnet Dialogbuchhaltung mit vorbelegtem Personenkonto)
- OP-Verrechnung neu berechnen (§ 367 BGB-Reihenfolge anwenden)

### 4.4 Kritische Regeln

- Beirats-Eigentümer: **ein** Personenkonto pro natürlicher/juristischer Person, auch wenn zusätzlich Beiratsrolle. Konsistent mit Datenmodell-Festlegung (Beirat ist `zusatzfunktionen` JSONField auf `Person`).
- Eigentümerwechsel: Bei Wechsel im laufenden Jahr bleibt Altkonto bestehen (historische Salden einsehbar), Neu-Eigentümer erhält neues Personenkonto. Beide werden in der Listenansicht angezeigt, gruppiert nach Einheit.

---

## 5. Untermenü: Sollstellungen

### 5.1 Zweck

Erzeugt **periodische Forderungen** gegenüber Eigentümern (HGV, RLZ, SU, NZJA, MIETE, NKVZ) als Buchung auf den Eigentümerkonten. Jede Sollstellung erzeugt **gleichzeitig einen Offenen Posten (OP)** auf dem Personenkonto.

### 5.2 Automatischer Monatslauf

- **Trigger:** Scheduled Job (`celery beat`) am 1. Werktag des Monats, 06:00 Uhr (konfigurierbar je Objekt).
- **Vorgehen:**
  1. Für jedes Objekt mit Status `aktiv` und gültigem Wirtschaftsplan für den Ziel-Monat wird der Lauf erzeugt.
  2. System ermittelt je Eigentümer den aktuellen Wirtschaftsplan-Anteil und zerlegt in Bewirtschaftung (BA 010) und Rücklage (BA 011).
  3. Buchung + OP-Erzeugung atomar in einer Transaktion.
  4. Log-Eintrag mit Lauf-ID, Zeitstempel, Anzahl Buchungen, Summe.
  5. Automatische Benachrichtigung an Buchhaltung bei Abweichung zum Wirtschaftsplan-Soll (Warn-Schwelle: 1 %).
- **Fehlerbehandlung:** Einzelne Eigentümer mit fehlenden Stammdaten (z. B. fehlender Umlageschlüssel-Wert) werden übersprungen und einzeln in Fehler-Liste gelogged — der Gesamtlauf schlägt *nicht* fehl.

### 5.3 Manueller Lauf (Neuanlage / Nachzug)

Für später angelegte Objekte (Jahresstart bereits überschritten, Wirtschaftsplan nachträglich freigegeben) muss der Lauf manuell angestoßen werden können.

- **Button „Sollstellungslauf starten"** im Untermenü Sollstellungen.
- **Auswahl:**
  - Objekt (bei Admin: Mehrfachauswahl möglich)
  - Zeitraum: einzelner Monat, Quartal, oder „alle offenen Monate des Jahres"
  - BA-Filter: alle / nur HGV+RLZ / nur SU / …
- **Simulation vor Ausführung:** Vorschau mit allen zu erzeugenden Buchungen, Summen je Eigentümer und Gesamtsumme, Differenz zum Wirtschaftsplan-Soll.
- **Freigabe:** Vier-Augen-Prinzip ab Gesamtsumme > Schwellwert (Default 5.000 €).
- **Nach Ausführung:** identisches Log-Verhalten wie Monatslauf.

### 5.4 OP-Erzeugung

Jede Sollstellungsbuchung erzeugt einen korrespondierenden `OffenerPosten`-Eintrag:

```python
class OffenerPosten(models.Model):
    buchung = OneToOneField(Buchung)
    personenkonto = ForeignKey(Personenkonto)
    betrag_ursprung = DecimalField()
    betrag_offen = DecimalField()          # wird bei Verrechnung reduziert
    faellig_ab = DateField()
    status = CharField(choices=["offen","teilverrechnet","verrechnet","storniert"])
    mahnstufe = IntegerField(default=0)
    mahnsperre_bis = DateField(null=True)
```

Die OP-Verrechnung (durch E-Banking-Zahlungseingänge) folgt **§ 367 BGB**: Kosten → Zinsen → Hauptforderung, älteste zuerst.

### 5.5 Kritische Regeln

- **Rücklagen-Unterkonto-Suffix:** `.911` (nicht `.910`). Siehe *Abweichung 001 (Kritisch)* in `VERSIONEN.md` / Spec v1.1. Implementation-Lücke: `services/buchungserkennung.py` und SKR-WEG-Template müssen vor Produktivgang korrigiert werden.
- **Eigentumswechsel im Monat:** Taggenaue Aufteilung (Erwerber / Veräußerer) gemäß Notartermin bzw. abweichender Beschlussfassung. Zwei OPs pro Wechsel-Monat.
- **Doppelsollstellungssperre:** Pro Eigentümer + Monat + BA darf nur **eine** aktive Sollstellung existieren. System lehnt Duplikate ab (Constraint).
- **Stornofähigkeit:** Nur per Spiegelbuchung (BA 098), zugehöriger OP wird auf `storniert` gesetzt. Kein Hard-Delete.

### 5.6 UI-Elemente

- Lauf-Übersicht (Historie, filterbar nach Objekt/Periode/Trigger automatisch/manuell)
- „Neuer Lauf"-Wizard (3 Schritte: Auswahl → Simulation → Freigabe)
- Fehler-Liste pro Lauf mit Drill-Down zu betroffenem Eigentümer

---

## 6. Untermenü: E-Banking

### 6.1 Zweck

Import, Abgleich und Verbuchung von Kontoumsätzen der objektgebundenen Bankkonten. Basis: CAMT.053-Dateien (XML), die von der Bank in einen **überwachten Ordner** abgelegt werden.

### 6.2 Import-Ordner: Konfiguration und Überwachung

#### 6.2.1 Konfigurationsquellen (Priorität absteigend)

1. **UI-Einstellung** (DB-Eintrag via Untermenü „E-Banking → Einstellungen")
2. **Umgebungsvariable** (`.env`-Datei)
3. **System-Default** (`./data/camt_import`)

Die UI-Einstellung überschreibt die `.env`-Variable. Wird die UI-Einstellung gelöscht (Wert leer), greift wieder `.env`.

#### 6.2.2 `.env`-Variablen

```env
IMMOCORE_CAMT_IMPORT_FOLDER=\\fileserver\buchhaltung\camt_import
IMMOCORE_CAMT_ARCHIVE_FOLDER=\\fileserver\buchhaltung\camt_archive
IMMOCORE_CAMT_FAILED_FOLDER=\\fileserver\buchhaltung\camt_failed
IMMOCORE_CAMT_POLL_INTERVAL=30            # Sekunden
IMMOCORE_CAMT_FILE_PATTERN=*.xml,*.camt   # Komma-separiert
```

#### 6.2.3 UI-Dialog „Einstellungen"

- Textfeld „Import-Ordner" mit Button **„Durchsuchen…"** (nativer Datei-/Ordner-Dialog bei Desktop-Client; Pfad-Eingabe + Server-Validierung bei Web-Client).
- Analog: Archiv-Ordner, Fehler-Ordner.
- Feld „Poll-Intervall (Sek.)" — Default 30.
- Feld „Dateimuster" — Default `*.xml,*.camt`.
- Button **„Verbindung testen"** — prüft: Ordner existiert, Lese- und Schreibrechte vorhanden, Testdatei schreib- und löschbar.
- Anzeige: zuletzt verarbeitete Datei + Zeitstempel, aktive Überwachung (grüner/roter Status).

#### 6.2.4 Ordner-Überwachung (Backend)

- **Library:** `watchdog` mit **`PollingObserver`** (nicht `Observer`) — stellt Kompatibilität mit UNC-Pfaden (`\\server\share\...`) und Netzwerk-Mounts sicher. Diese Entscheidung ist vom Invoice-Sorter übernommen.
- **Event-Handler:** `on_created` und `on_modified` mit Debounce (Datei muss 5 Sek. unverändert sein, bevor Import startet — Schutz vor Halb-Fertig-Dateien).
- **Duplikatserkennung:** SHA-256 über den Datei-Inhalt. Bereits importierte Hashes werden in `CamtImport`-Tabelle gespeichert. Duplikate werden ignoriert und in `camt_failed/` mit Suffix `.duplicate` abgelegt.
- **Verarbeitung:**
  1. Parse CAMT.053 (Python-Lib, z. B. `camt.py`, oder eigene XSD-basierte Lösung).
  2. Extrahiere Bank-IBAN → match gegen Objektanlage (`Bankkonto.iban`) → Objekt-Zuordnung automatisch.
  3. Erzeuge `Kontoumsatz`-Records (Status `importiert`).
  4. Move Originaldatei nach `camt_archive/YYYY-MM-DD/` mit Original-Dateinamen.
  5. Bei Fehler: Move nach `camt_failed/YYYY-MM-DD/` mit Fehler-Log als Begleitdatei.
- **Live-Feedback:** WebSocket-Signal an aktive Frontend-Sessions → UI aktualisiert Umsatzliste ohne Reload.

#### 6.2.5 Manueller Import-Trigger

Button „Jetzt importieren" im Menü für Fälle, in denen eine Datei außerhalb des Überwachungsfensters abgelegt wurde oder der Polling-Zyklus noch nicht gelaufen ist.

### 6.3 Abgleich und Buchungsvorschlag

Logik in `services/buchungserkennung.py`:

- **Zahlungseingänge Eigentümer** (→ BA 020): Match über Verwendungszweck (Objekt-/Einheiten-Nr., Eigentümername), Regex + Fuzzy-Match, Scoring-Schwelle 0.85 für Auto-Verbuchung.
- **Zahlungsausgänge Kreditoren** (→ BA 051): Match gegen offene Rechnungen aus BelegPilot über IBAN + Betrag + Referenz.
- **Rücklagen-Buchungen:** Nur auf `.911`-Unterkonten zulässig, System lehnt Auto-Zuordnung auf Bewirtschaftungskonto ab.
- **OP-Verrechnung Eigentümer:** § 367 BGB (Kosten → Zinsen → Hauptforderung, älteste zuerst). Teilzahlungen anteilig.

### 6.4 Kritische Regeln

- Ausschließlich objektbezogene Bankkonten dürfen importiert werden — Sammelkonten/Treuhand untersagt (WEMoG-Konformität).
- Forderungsfall-Kopplung: Zahlungseingänge auf Forderungen im Status „Forderungsfall" triggern Benachrichtigung + Statusprüfung.
- UNC-Pfade sind Pflicht-unterstützt — auf `PollingObserver` nicht verzichten.

### 6.5 UI-Elemente

- Bankkonten-Dashboard (Saldo, letzter Import, offene Posten)
- Umsatzliste mit Ampel-Status (grün = Auto-Match, gelb = Vorschlag, rot = unzugeordnet)
- Einstellungen-Untermenü (siehe 6.2.3)

---

## 7. Untermenü: Buchungserfassung / Buchungsjournal (Dialogbuchhaltung)

### 7.1 Zweck

Manueller Buchungsarbeitsplatz + Journal-Ansicht. Jede Buchung wird über eine **BA-spezifische Eingabemaske** erfasst — die Maske passt sich an die gewählte BA an (Kontenauswahl, Pflichtfelder, Validierungen).

### 7.2 Auswahl der Buchungsart

Einstiegsdialog zeigt die BA-Gruppen, die manuell erfassbar sind:

| Gruppe | BAs | UI-Verhalten |
|---|---|---|
| **Saldenvorträge** | 001, 002, 003, 004 | nur im Jahresübergangs-Fenster, Admin-Only |
| **Sachkontenbuchung** | 040, 042, 044 | Soll/Haben beide Sachkonten |
| **Sachkonten-Rücklage** | 041, 043 | Gegenkonto muss `.911`-Konto sein |
| **Eingang Personenkonto** | 020 | Gegenkonto = Bank; OP-Verrechnung § 367 BGB |
| **Ausgang Personenkonto** | 021 | z. B. Guthaben-Auszahlung, Mahngebühr-Storno |
| **Eingang Kreditor** | 050 | Rechnungseingang → Verbindlichkeit, meist via BelegPilot |
| **Ausgang Kreditor** | 051 | Zahlung Kreditor, meist via E-Banking, manuell für Kasse |
| **ARAP/PRAP** | 080–083 | Wizard mit Zeitraum + Auto-Auflösung |
| **Storno/Korrektur** | 098, 099 | Spiegel-Buchung, Referenz auf Original-Buchung |

Die manuell **nicht** auswählbaren BAs (010–016, 023, 024, 090, 091) werden ausschließlich durch System-Prozesse erzeugt (Sollstellungslauf, Mahnmodul, Jahresabschluss) und dienen hier nur der Anzeige im Journal.

### 7.3 Buchungsmaske (generisch)

Pflichtfelder je BA unterschiedlich — Common-Fields:

- **Objekt** (aus aktivem Objekt, nicht änderbar)
- **Buchungsart** (gewählt in Schritt 7.2)
- **Buchungsdatum** (in offener Periode)
- **Belegdatum**
- **Beleg-Nr.** (automatisch fortlaufend, überschreibbar)
- **Soll-Konto** + **Haben-Konto** (BA-abhängige Auswahl, Typ-Validierung)
- **Betrag** (brutto)
- **Steuer-Schlüssel** (bei ZH/SEV relevant; WEG i. d. R. nein)
- **Buchungstext**
- **Umlageschlüssel** (Pflicht wenn BA `umlage=pflicht`)
- **Kostenstelle** (optional)
- **Beleg-Referenz** (BelegPilot-UUID, Beschluss-ID, oder PDF-Upload)
- **Kreditor** (bei BA 050–053: Typ 500 extern / Typ 400 intern)

Validierungen sind BA-gesteuert (siehe 3.1 BA-Metadaten).

### 7.4 BA-spezifische Sondermasken

- **BA 020 Eingang Personenkonto:** Nach Auswahl Personenkonto werden offene Posten angezeigt; User ordnet Zahlungsbetrag explizit zu (oder lässt § 367 BGB-Automatik laufen).
- **BA 041 Sachkontenbuchung Aufwand Rücklage:** Haben-Konto-Lookup nur auf `.911`-Unterkonten gefiltert; ohne Treffer blockiert die Eingabe mit Fehler.
- **BA 012 Sonderumlage (nur durch Sollstellungslauf aufrufbar, aber lesbar im Journal):** Beschluss-Referenz Pflicht.
- **ARAP/PRAP (BA 080–083):** Wizard mit Feld „Zeitraum" → erzeugt Ursprungsbuchung + N Monatsauflösungen automatisch in einem Stapel.
- **Storno (BA 098):** User wählt Original-Buchung aus dem Journal; System erzeugt Spiegelbuchung mit identischen Kontenseiten, getauscht.

### 7.5 Journal-Ansicht

Tabellarische Darstellung aller Buchungen des Objekts, filter- und exportfähig:

| Spalte | Filter |
|---|---|
| Buchungsdatum | Zeitraum |
| Beleg-Nr. | Volltext |
| BA (Nr. + Kürzel) | Auswahl |
| Soll-Konto | Auswahl |
| Haben-Konto | Auswahl |
| Betrag | Range |
| Status | Entwurf/Festgeschrieben/Storniert |
| User | Auswahl |
| Buchungstext | Volltext |

Export: PDF (revisionssicher), Excel, DATEV-CSV (EXTF-Format, später).

### 7.6 Entwurf / Festschreibung

- Buchungen zunächst `Entwurf` (editierbar, löschbar innerhalb Session).
- Festschreibung manuell oder automatisch am Tagesende (Batch-Job).
- Nach Festschreibung: nur noch Storno (BA 098) oder Korrektur (BA 099).
- Festgeschriebene Buchungen im abgeschlossenen Jahr: **gesperrt**, nur per Admin-Release entsperrbar (Auditlog-Eintrag).

### 7.7 Abrechnungslogik-Kopplung

Die Jahresabrechnung (Einzel- und Gesamtabrechnung) liest ausschließlich über BA — **nicht über Konten-Nr.**. Dadurch:

- Neue Konten werden durch BA-Zuordnung automatisch korrekt einsortiert.
- Umbuchungen (BA 044) sind nie abrechnungsrelevant, auch wenn sie Aufwandskonten berühren.
- Rücklagen-Bewegungen (BA 011, 041, 043, 091) landen garantiert in der Rücklagenentwicklung, nicht in der Bewirtschaftungs-Abrechnung.

### 7.8 UI-Elemente

- Buchungsstapel (Arbeitsvorrat, gefiltert nach Status und User)
- Schnellerfassungs-Modus (Tastatur-Shortcuts, Kontonummern-Autocomplete)
- Journal-Ansicht mit Drill-Down auf Beleg
- Storno-/Korrektur-Workflow mit Pflichtbegründung

---

## 8. Untermenü: Kreditoren (Roadmap)

### 8.1 Zweck

Verwaltung von Lieferanten-/Handwerker-Stammdaten, Rechnungseingang (OP-Liste Kreditoren), Zahlungsvorschlägen und Zahlungsläufen.

### 8.2 Umsetzungs-Ansatz

**Später zu bauen.** Funktionale Orientierung am bestehenden **DOPRE-Tool**. Vorgesehene Bausteine (bereits in Vorprojekten erarbeitet):

- OCR-Pipeline (Tesseract + pdf2image) für gescannte Rechnungen
- Claude-API-basierte Extraktion in strukturiertes JSON
- XRechnung/ZUGFeRD-XML-Parsing für elektronische Rechnungen
- Status-basierter Freigabe-Workflow
- Ordner-Überwachung analog E-Banking (`PollingObserver`, SHA-256-Dedup)
- SMTP-Benachrichtigungen via Office 365 (OAuth2 später)

### 8.3 Schnittstelle zur Buchhaltung

- Freigegebene Rechnung aus Kreditoren-Modul → automatische Buchung (BA 050) im Buchungsstapel
- Zahlungslauf → automatische BA 051 via E-Banking-Ausgang

Detailspezifikation folgt in eigener Spec-Datei.

---

## 9. Untermenü: Mahnwesen (Vorschlag)

### 9.1 Zweck

Automatisierte Eskalation offener Forderungen gegenüber Eigentümern/Mietern in definierten Mahnstufen. Output: formelle Mahnschreiben (PDF) + Buchung der Mahngebühren.

### 9.2 Mahnstufen

| Stufe | Bezeichnung | Verzug ab | Gebühr (Default) | Aktion |
|---|---|---|---|---|
| 0 | Zahlungserinnerung | 14 Tage | 0,00 € | freundlicher Hinweis, keine Gebühr |
| 1 | 1. Mahnung | 28 Tage | 5,00 € | förmliche Mahnung, Zinsen ab hier |
| 2 | 2. Mahnung | 42 Tage | 10,00 € | Androhung Forderungsfall |
| 3 | Letzte Mahnung / Forderungsfall-Übergabe | 56 Tage | 15,00 € + Zinsen | Übergabe ans Forderungsfall-Modul, Anwaltsankündigung |

Alle Werte je Objekt konfigurierbar (Schwellen in Tagen, Gebührenhöhe, Zinssatz). Defaults gelten bei fehlender objektspezifischer Einstellung.

### 9.3 Prozess

1. **Mahnlauf** (monatlich, erster Werktag; manuell zusätzlich startbar):
   - Ermittelt alle OPs mit Verzug, filtert Mahnsperren raus.
   - Gruppiert je Personenkonto, aggregiert alle offenen Posten in eine Mahnung.
   - Berechnet Zinsen ab Mahnstufe 1 (Basiszinssatz Bundesbank + 5 % p. a. für Verbraucher, + 9 % für Unternehmer — siehe Forderungsfall-Modul, § 288 BGB).
2. **Simulation:** Preview-Liste mit betroffenen Eigentümern, berechneten Gebühren und Zinsen.
3. **Freigabe:** optional Vier-Augen bei Summe > Schwellwert.
4. **Ausführung:**
   - Buchung Mahngebühr (BA 023) auf Personenkonto.
   - Buchung Verzugszinsen (BA 024) auf Personenkonto.
   - Anhebung Mahnstufe in zugehörigen OPs.
   - PDF-Mahnschreiben generieren (Template je Stufe, WEG-konform, objektspezifische Kopfzeile).
   - Versand: Casavi-Postbox + optional Post (Druckschnittstelle später).
5. **Protokollierung:** Mahnlauf-ID, Zeitstempel, User, Anzahl Mahnungen, Eskalationen ans Forderungsfall-Modul.

### 9.4 Mahnsperren

- Manuell setzbar pro Personenkonto („Stundung bis 31.05." / „Ratenzahlung vereinbart").
- Automatisch bei laufender Ratenvereinbarung (wenn Ratenzahlung pünktlich → Sperre bis zur nächsten Rate).
- Auditlog: wer hat wann wie lange gesperrt.

### 9.5 Kritische Regeln

- Mahnstufe 3 löst automatisch Übergabe ans Forderungsfall-Modul aus — OP-Status wechselt auf `forderungsfall`.
- Mahngebühren sind **keine** Abrechnungspositionen (BA 023 mit `abrechnung=nein`), sondern Ertrag der Gemeinschaft auf speziellem Konto.
- Verzugszinsen folgen § 288 BGB (taggenau berechnet, nicht pauschal).

### 9.6 UI-Elemente

- Mahnlauf-Wizard (Auswahl → Simulation → Freigabe)
- Mahnhistorie je Personenkonto
- Mahnsperren-Verwaltung
- PDF-Template-Editor je Objekt (Kopf, Fuß, Tonfall)

---

## 10. Untermenü: Forderungsfälle (Vorschlag)

### 10.1 Zweck

Management uneinbringlicher oder eskalierter Forderungen. Übernimmt Fälle aus dem Mahnwesen (Mahnstufe 3) und führt sie durch außergerichtliche und gerichtliche Verfahren.

### 10.2 Status-Workflow

```
offen → außergerichtlich → gerichtlich → titulierung → vollstreckung → (erfolgreich | uneinbringlich)
                                                                         ↓
                                                                    abschreibung
```

| Status | Bedeutung | Aktionen |
|---|---|---|
| `offen` | neu aus Mahnwesen übernommen | Anwaltsübergabe vorbereiten |
| `außergerichtlich` | Anwalt tätig, Inkasso | Kostenverfolgung Anwalt |
| `gerichtlich` | Mahnbescheid eingeleitet | Gerichtskosten verfolgen |
| `titulierung` | Titel erwirkt (Vollstreckungsbescheid/Urteil) | Vollstreckungs-Schritte |
| `vollstreckung` | Gerichtsvollzieher aktiv | GV-Kosten verfolgen |
| `erfolgreich` | vollständig beigetrieben | Abschluss |
| `uneinbringlich` | keine Aussicht auf Beitreibung | Abschreibung nach Beschluss |
| `abschreibung` | Beschluss der WEG auf Forderungsverzicht | Ausbuchung gegen Sammelkonto |

### 10.3 Zinsberechnung

Gemäß **§ 288 BGB**:

- Verbraucher: Basiszinssatz + 5 Prozentpunkte p. a.
- Unternehmer: Basiszinssatz + 9 Prozentpunkte p. a.
- Basiszinssatz wird halbjährlich durch die Deutsche Bundesbank festgelegt (01.01. und 01.07.).
- System pflegt Historie der Basiszinssätze, Berechnung taggenau je Teilzahlung.

### 10.4 Kostenverfolgung

Jeder Forderungsfall hat Sub-Positionen:

| Art | Beispiel | Buchungsart |
|---|---|---|
| Mahngebühren | 5–15 € je Stufe | BA 023 |
| Verzugszinsen | § 288 BGB | BA 024 |
| Anwaltskosten | RVG-Tabelle | BA 040 (Aufwand) + Erstattungsforderung |
| Gerichtskosten | GKG | BA 040 + Erstattungsforderung |
| GV-Kosten | Gerichtsvollzieher | BA 040 + Erstattungsforderung |

Erstattungsforderungen werden als zusätzliche OPs auf dem Personenkonto geführt; Verrechnungsreihenfolge § 367 BGB bleibt erhalten.

### 10.5 Zwischenkonto Forderungsfall

Ein objektspezifisches Sammelkonto (Vorschlag: SKR-WEG-Konto `.1460`) nimmt Forderungsfälle auf, die nicht mehr „normal" auf dem Personenkonto stehen sollen. Bei Eingang einer Zahlung erfolgt Umbuchung zurück aufs Personenkonto mit § 367 BGB-Verrechnung.

### 10.6 Beschlussfähigkeit

Abschreibung uneinbringlicher Forderungen (BA 099 mit Flag `abschreibung=true`) ist nur nach WEG-Beschluss zulässig. System verlangt Beschluss-Referenz Pflicht.

### 10.7 UI-Elemente

- Forderungsfall-Kanban (Spalten = Status)
- Detail-Ansicht je Fall (Kostenverfolgung, Kommunikation, Schriftverkehr)
- Zins-Rechner (Preview vor Buchung)
- Beschluss-Import für Abschreibung

---

## 11. Untermenü: Rücklagen (Vorschlag)

### 11.1 Zweck

Verwaltung der Instandhaltungsrücklage und weiterer Rücklagentöpfe gemäß WEMoG. Pflege der **`.911`-Unterkontostruktur**, Rücklagenentwicklung, Zuführung/Entnahme, Verzinsung.

### 11.2 Rücklagenarten

| Typ | Zweck | Unterkonto-Suffix | Beschlussfähigkeit |
|---|---|---|---|
| Instandhaltungsrücklage | klassische IHR gemäß WEMoG | `.911` | Standard |
| Sonderrücklage | zweckgebunden, z. B. Dach-Sanierung | `.911` mit Teilbezeichnung | Beschluss Pflicht |
| Liquiditätsrücklage | Betriebsmittel-Puffer | `.911` mit Teilbezeichnung | Beschluss Pflicht |

### 11.3 Rücklagenkonten-Struktur

Ein Objekt hat ein Hauptkonto Rücklage (z. B. `.1210`) und Unterkonten je Rücklagentyp und je Eigentümer:

```
1210                Rücklage (Hauptkonto)
1210.911.01         Instandhaltungsrücklage — Einheit 01
1210.911.02         Instandhaltungsrücklage — Einheit 02
...
1210.911.SON       Sonderrücklage Dach-Sanierung (zweckgebunden)
```

Die exakte Nummern-Struktur ist im Kontenrahmen (Abschnitt 13) definiert.

### 11.4 Prozesse

- **Zuführung** (BA 011): aus Sollstellung Monatslauf oder Sonderumlage-Beschluss.
- **Entnahme** (BA 041): nur mit Beschluss-Referenz + Beleg (z. B. Handwerker-Rechnung zur Dach-Sanierung).
- **Zinsgutschrift** (BA 043): automatisch aus E-Banking-Zinserträgen auf separiertem Bankkonto.
- **Jahresentwicklung** (BA 091): zum Jahresabschluss wird die Entwicklung (Anfangsbestand + Zuführungen + Zinsen − Entnahmen = Endbestand) gebucht und dokumentiert.

### 11.5 Rücklagenentwicklungsbericht

Standard-Auswertung je Objekt + Jahr:

| Position | Betrag |
|---|---|
| Anfangsbestand 01.01. | x.xxx € |
| + Zuführungen (Summe BA 011) | x.xxx € |
| + Zinserträge (Summe BA 043) | xxx € |
| − Entnahmen (Summe BA 041) | (x.xxx €) |
| = Endbestand 31.12. | x.xxx € |
| davon zweckgebunden (Sonderrücklagen) | x.xxx € |

### 11.6 Kritische Regeln

- **`.911`-Suffix Pflicht** für alle Rücklagen-Unterkonten. Buchungen auf Rücklage ohne `.911` werden vom System abgelehnt. Ausführung von Abweichung 001 ist Voraussetzung für den Produktivgang dieses Untermoduls.
- Separiertes Bankkonto (nicht mit Bewirtschaftungskonto gemischt) — WEMoG-Pflicht seit 01.12.2020.
- Entnahmen ohne Beschluss-Referenz werden blockiert.

### 11.7 UI-Elemente

- Rücklagen-Dashboard (Stand, Entwicklung, zweckgebundene Teile)
- Entnahme-Wizard mit Beschluss-Auswahl + Beleg-Referenz
- Entwicklungsbericht (PDF-Export für Jahresabrechnung)

---

## 12. Untermenü: Rechnungsabgrenzung (ARAP/PRAP) (Vorschlag)

### 12.1 Zweck

Periodengerechte Verteilung von Aufwendungen und Erträgen, die Zeiträume überspannen (Versicherung 01.07.2025 – 30.06.2026, Grundsteuer Jahresvorauszahlung, Wartungsverträge, Miet-Vorauszahlungen).

### 12.2 Fälle

- **ARAP** (Aktive Rechnungsabgrenzung): Aufwand, der schon bezahlt wurde, aber Folgeperioden betrifft.
- **PRAP** (Passive Rechnungsabgrenzung): Ertrag, der schon vereinnahmt wurde, aber Folgeperioden betrifft.

### 12.3 Wizard-Ablauf

1. Auswahl: ARAP oder PRAP.
2. Eingabe: Gesamtbetrag, Zeitraum (Von–Bis), Kontierung (Aufwands-/Ertragskonto, Gegenkonto Bank/Kreditor).
3. System berechnet Verteilungsplan (monatsgenau oder taggenau auf Wunsch).
4. Preview: N Buchungen mit Datum und Betrag.
5. Ausführung: Ursprungsbuchung (BA 080 / 082) + alle Auflösungsbuchungen (BA 081 / 083) als Buchungsstapel mit Buchungsdatum am Monatsletzten.
6. Freigabe einzeln oder Stapel.

### 12.4 Automatisierung

- Bei periodisch wiederkehrenden Aufwendungen (Versicherung jährlich): Vorlage speicherbar.
- Jahresabschluss-Check listet alle offenen ARAP/PRAP zum Stichtag.

### 12.5 UI-Elemente

- Wizard (geführt)
- ARAP/PRAP-Übersicht je Objekt (Bestand, Auflösungsplan, offene Restbeträge)
- Buchungsstapel-Preview

---

## 13. Untermenü: Kontenrahmen / Kontenplan (Vorschlag)

### 13.1 Zweck

Verwaltung des objektspezifischen Kontenplans auf Basis eines SKR-WEG-Master-Templates. WEMoG-konform.

### 13.2 Struktur

- **Kontenklassen** (wie SKR 04 adaptiert): 0 Anlagevermögen, 1 Umlaufvermögen/Bank/Personen, 2–3 Aufwand/Ertrag, 4 Abschluss, 9 Sonder (Rücklage).
- **Kontenarten:**
  - Sachkonto (Aufwand, Ertrag, Bestand)
  - Personenkonto (Eigentümer, Mieter)
  - Kreditor (Typ 500 extern / Typ 400 intern)
  - Bankkonto (Bewirtschaftung, Rücklage)
  - Abschlusskonto (GuV-Konto, Schlussbilanzkonto)

### 13.3 Objektspezifischer Kontenrahmen

Beim Anlegen eines neuen Objekts wird aus dem SKR-WEG-Template der Kontenrahmen geklont:

- Sachkonten und Umlageschlüssel-Zuordnung aus Template
- Personenkonten automatisch je Einheit (z. B. Nummernkreis `3000.xx`)
- Rücklagenkonten mit `.911`-Unterkonten je Einheit
- Kreditoren zunächst leer, wachsen durch Rechnungseingang

### 13.4 Kontenpflege

- Neues Konto anlegen: Nummer (validiert gegen Kontenrahmen-Logik), Bezeichnung, Kontenart, Umlageschlüssel, aktiv/inaktiv.
- Konto sperren: keine neuen Buchungen mehr möglich, bestehende bleiben.
- Konto löschen: nur wenn nie bebucht.
- Umlageschlüssel je Konto: MEA, Wohnfläche, Anzahl Personen, fester Anteil, individueller Schlüssel (JSONField mit Verteilungs-Matrix).

### 13.5 Kritische Regeln

- SKR-WEG-Template muss **Abweichung 001** umsetzen (`.911` statt `.910`). Bestandsobjekte per Migration korrigieren.
- Kontenrahmen gesperrt nach Jahresabschluss — Änderungen am Kontenrahmen eines abgeschlossenen Jahres blockiert.

### 13.6 UI-Elemente

- Kontenliste (hierarchisch, Baum-Ansicht)
- Konto-Detail (Saldo, Umlageschlüssel, Verwendungshistorie)
- Template-Vergleich „Objekt vs. Master" → fehlende Konten nachziehen

---

## 14. Untermenü: Jahresabschluss / Saldenvorträge (Vorschlag)

### 14.1 Zweck

Strukturierter Jahresabschluss mit Übergang der Salden in das Folgejahr. Voraussetzung für Einzel-/Gesamtabrechnung.

### 14.2 Checklisten-Prozess

1. **Vor-Check:**
   - Alle Eingangsrechnungen aus BelegPilot freigegeben?
   - Alle E-Banking-Umsätze verbucht?
   - Alle ARAP/PRAP aufgelöst oder korrekt gebildet?
   - Sollstellungen vollständig (alle 12 Monate)?
   - Rücklagen-Bewegungen konsistent?
   - Offene Monierungen im BelegPilot-Audit-Protokoll = 0?
2. **Abschlussbuchungen** (BA 090):
   - Aufwände/Erträge → GuV-Konto
   - ARAP/PRAP-Abgrenzung
   - Rücklagenentwicklung (BA 091)
3. **Erstellung Einzel- und Gesamtabrechnung** (Modul Jahresabrechnung)
4. **Beschluss** der Eigentümerversammlung
5. **Nach Beschluss:**
   - Buchungen NZJA (BA 013) / GJA (BA 014) auf Personenkonten
   - Saldenvorträge (BA 001–004) ins Folgejahr
   - Altperiode wird hart gesperrt

### 14.3 Saldenvorträge

- **BA 001 Sachkonten:** Bestandskonten (Aktiva, Passiva) → Eröffnungsbilanz Folgejahr.
- **BA 002 Personenkonten:** OPs und Guthaben der Eigentümer.
- **BA 003 Kreditoren:** offene Kreditoren-OPs.
- **BA 004 Bankkonten:** Kontensalden zum 31.12.

Generiert als Buchungsstapel mit Datum 01.01. Folgejahr, Referenz auf Quellbuchungen.

### 14.4 Kritische Regeln

- **BelegPilot-Hard-Lock:** Einzelabrechnung kann nicht finalisiert werden, solange Monierungen offen.
- Abgeschlossenes Jahr ist read-only. Entsperrung nur durch Admin mit Auditbegründung, Protokoll zwingend.
- Saldenvortrag gegen Abschlussbuchung muss auf 0,00 € aufgehen — Abweichungen blockieren den Abschluss.

### 14.5 UI-Elemente

- Abschluss-Checkliste mit Ampelstatus
- Abschluss-Wizard (geführt)
- Saldenvortrags-Preview mit Summenkontrolle

---

## 15. Untermenü: Auswertungen (Vorschlag)

### 15.1 Zweck

Standard-Auswertungen für Buchhaltung, Geschäftsführung und externe Stellen (Beirat, Steuerberater).

### 15.2 Standard-Reports

| Report | Inhalt | Format |
|---|---|---|
| **BWA** (Betriebswirtschaftliche Auswertung) | Monatlich: Aufwände/Erträge je Kontengruppe, Vergleich Vorjahr, Kumulation YTD | PDF, Excel |
| **Summen- und Saldenliste** | Alle Konten mit Anfangsbestand, Soll-Summe, Haben-Summe, Endbestand für Zeitraum | PDF, Excel |
| **Kontoauszug Sachkonto** | Bewegungen eines Sachkontos im Zeitraum | PDF, Excel |
| **Kontoauszug Personenkonto** | Bewegungen + OPs je Eigentümer | PDF |
| **OP-Liste Debitoren** | alle offenen Posten Eigentümer, sortiert nach Alter | PDF, Excel |
| **OP-Liste Kreditoren** | alle offenen Kreditoren-Verbindlichkeiten | PDF, Excel |
| **Rücklagenentwicklung** | Zuführungen, Entnahmen, Zinsen je Rücklagentopf | PDF |
| **Wirtschaftsplan Soll-Ist** | Plan vs. Ist je Kontengruppe | PDF, Excel |
| **DATEV-Export** | EXTF-CSV Buchungsstapel für Steuerberater (ZH/SEV) | CSV |
| **BA-Auswertung** | Summen je BA über Zeitraum (Audit/Abrechnungs-Check) | Excel |

### 15.3 Filter (generisch)

- Objekt (aktives oder Multi-Select für konsolidierte Sicht)
- Zeitraum (Wirtschaftsjahr, Quartal, frei)
- Status (Entwurf inkludieren / nur Festgeschrieben)
- BA-Filter
- Umlageschlüssel-Filter

### 15.4 Exportziele

- Direkt-Download PDF / Excel
- Versand per Mail (SMTP via Office 365)
- Upload nach Casavi (für Eigentümer/Beirat)
- DATEV-Export zusätzlich als direkter Upload via DATEV-API (Roadmap)

### 15.5 UI-Elemente

- Report-Katalog (Kachel-Ansicht)
- Filter-Dialog je Report
- Zuletzt generierte Reports (Session-History)
- Scheduled Reports (z. B. BWA monatlich automatisch an Geschäftsführung)

---

## 16. Abhängigkeiten / Schnittstellen (konsolidiert)

| Richtung | Modul | Interface |
|---|---|---|
| IN | Objektanlage | Stammdaten Objekt, Einheit, Eigentümer, Kreditor, Kontenrahmen, Bankkonten, Umlageschlüssel |
| IN | BelegPilot | Freigegebene Eingangsrechnung (JSON + PDF-Referenz), Audit-Monierungen |
| IN | Wirtschaftsplan | Sollstellungs-Basis |
| IN | Beschlusswesen | Sonderumlage, Rücklagenentnahme, Abschreibung Forderungen, Genehmigung Jahresabrechnung |
| IN | Bank (CAMT-Dateiexport in Ordner) | CAMT.053 |
| OUT | Mahnwesen | Offene Posten + Altersstruktur |
| OUT | Forderungsfall | Eskalierte Forderungen inkl. § 367 BGB-Reihenfolge |
| OUT | Jahresabrechnung | Buchungssalden via BA, Rücklagenentwicklung, Einzelabrechnungs-Daten |
| OUT | Casavi | Eigentümer-Kontoauszug, Mahnschreiben, Belegeinsicht (read-only) |
| OUT | DATEV-Export | Buchungsstapel EXTF für externe Steuerberatung (SEV/ZH) |

---

## 17. Rollen & Berechtigungen (konsolidiert)

| Rolle | Debitoren | Sollstellg. | E-Banking | Buchungs­erfassung | Kreditoren | Mahn­wesen | Forder. | Rücklagen | RAP | Konten­rahmen | Jahres­abschl. | Auswert. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Buchhalter:in | L/S | anlegen | abholen, buchen | buchen, stornieren | (später) | lauf starten | bearbeiten | buchen | buchen | pflegen | durchführen | alle |
| Objektbetreuung | L | einsehen | einsehen, manuell zuordnen | Entwurf erfassen | (später) | einsehen | einsehen | einsehen | einsehen | einsehen | einsehen | alle |
| Geschäftsführung | L | freigeben | freigeben | freigeben | (später) | freigeben | freigeben | freigeben | freigeben | freigeben | freigeben | alle |
| Beirat (via Casavi) | — | — | — | — | — | — | — | Bericht | — | — | Bericht | BWA, Kontoauszug eigener Einheit |
| Auditor (Magic Link) | L | L | L | L | L | L | L | L | L | L | L | L |

L = Lesezugriff, S = Schreibzugriff

---

## 18. Offene Punkte / Technische Schulden

1. **`services/buchungserkennung.py`:** Rücklagen-Unterkonto-Suffix auf `.911` umstellen. *Abweichung 001 (Kritisch).*
2. **SKR-WEG-Template:** Gleiche Korrektur im Kontenrahmen-Seed + Migrationsskript für Bestandsobjekte.
3. **BA-Katalog freigeben:** Nummernkreis und Metadaten-Konfiguration (Abschnitt 3.2) durch Geschäftsführung abstimmen. Nach Freigabe: Seed-Migration.
4. **EBICS-Schlüsselmanagement:** Produktions-tauglicher HSM-/Keyvault-Anschluss offen.
5. **DATEV-Export-Format:** EXTF-CSV-Spezifikation final festlegen; Alternative DATEV-API später.
6. **Vier-Augen-Schwellwerte:** Default-Werte mit Geschäftsführung abstimmen, je Objekt/BA konfigurierbar.
7. **Kreditoren-Modul:** Detailspezifikation ausarbeiten, DOPRE-Funktionsumfang als Baseline beschreiben.
8. **Mahn-PDF-Templates:** WEG-konforme Vorlagen je Stufe, objektspezifische Kopfzeilen (Demme-Branding).
9. **Casavi-Postbox-API:** technische Integration für automatisierten Mahn-/Abrechnungs-Versand.
10. **Scheduled Reports:** Scheduler-Infrastruktur (Celery Beat) und Empfängerliste.

---

## 19. Versionshistorie

| Version | Datum | Autor | Änderung |
|---|---|---|---|
| 0.1 | 2026-04-19 | Patrik | Initialentwurf Modul Buchhaltung (Sollstellungen, E-Banking, Dialogbuchhaltung) |
| 0.2 | 2026-04-19 | Patrik | Erweitert: Debitoren, BA-Querschnittskonzept, Folder-Watcher-Konfiguration, Buchungserfassung/Journal mit BA-Masken, Kreditoren (Roadmap), Mahnwesen, Forderungsfälle, Rücklagen, ARAP/PRAP, Kontenrahmen, Jahresabschluss, Auswertungen |
