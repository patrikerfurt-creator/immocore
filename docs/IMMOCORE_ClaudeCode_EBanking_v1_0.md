# IMMOCORE — E-Banking-Modul | Claude Code Prompt v1.0

**IMMOCORE** — *Webbasiertes Immobilienverwaltungssystem*
**Modul:** E-Banking (camt-Import-Übersicht, Gegenkonto-Erkennung, Lernlogik, camt.054-Abzweig)
**Demme Immobilien Verwaltung GmbH** — Coventrystraße 32, 65934 Frankfurt am Main
**Version:** 1.0 | **Stand:** Mai 2026
**KI-Modell:** `claude-sonnet-4-6`

---

## 1. Zweck dieses Dokuments

Diese Spezifikation definiert das **E-Banking-Modul** als Bindeglied zwischen
dem bereits funktionierenden **camt.053-Import** und dem Buchungsjournal.
Ziel ist eine Bearbeitungs-Übersicht, in der **importierte, aber noch nicht
verbuchte Bankbuchungen** sichtbar sind — mit:

- bereits **erkanntem Gegenkonto** (aus den vorhandenen Erkennungsstufen),
- der Möglichkeit, **manuell zu bearbeiten** (Gegenkonto ändern, Split,
  Notiz),
- der Möglichkeit, **zweifelsfrei erkannte Buchungen automatisch zu
  verbuchen** (ohne Nutzerinteraktion),
- einer **Lernlogik**, die aus jeder Bestätigung und jeder Korrektur neue
  oder aktualisierte Regeln ableitet,
- einem **funktional vorbereiteten Abzweig für camt.054**
  (R-Transactions / Rücklastschriften), dessen Verarbeitung in dieser
  Spec **als Stub** bleibt — die Implementierung folgt mit der
  Mahnwesen-Spec.

| **Status** | **Inhalt** |
|---|---|
| ✅ Voraussetzung erfüllt | camt.053-Parser + SHA-256-Dedup (`BankImport`) |
| ✅ Voraussetzung erfüllt | Hybride Buchungserkennung Stufe 1 (IBAN-Match) / Stufe 2 (KI) — *Ausgangsspec Kap. 8* |
| ✅ Voraussetzung erfüllt | Hausgeld-Nebenbuch + automatische Tilgung über `EndToEndId` — *HAUSGELD_NEBENBUCH v1.1 Kap. 10* |
| ✅ Voraussetzung erfüllt | OP-Buchung mit `15900` und Aufwandsumbuchung — *OP_BUCHUNG v1.1* |
| 🆕 Diese Spec | Bearbeitungs-Übersicht **importiert → verbucht**, Lernlogik, camt.054-Stub |
| 🚫 Ausdrücklich nicht hier | EBICS-Anbindung (automatischer Upload/Download) — eigene Spec v2 |
| 🚫 Ausdrücklich nicht hier | UNC-Ordner-Watchdog (`PollingObserver`) — eigene Spec, falls gewünscht |
| 🚫 Ausdrücklich nicht hier | camt.054-Verarbeitungslogik (R-Transactions) — nur Abzweig, leerer Stub |

**Bezug:**
`IMMOCORE_Ausgangsspezifikation_v1.1.docx` (Kap. 8, 9),
`CLAUDE_CODE_ANLEITUNG_HAUSGELD_NEBENBUCH_v1_1.md` (Kap. 10, 11),
`CLAUDE_CODE_ANLEITUNG_OP_BUCHUNG_v1_1.md`,
`IMMOCORE_ClaudeCode_Rechnungserkennung_3stufig_v1_2.docx` (Lernlogik-Vorbild).

---

## 2. Kernkonzept

### 2.1 Drei-Stufen-Lebenszyklus einer Bankbuchung

Eine durch den camt.053-Import erzeugte Bankbuchung durchläuft in IMMOCORE
genau drei Zustände — vergleichbar dem dreistufigen Modell der
Rechnungserkennung:

```
                    camt.053-Import
                          │
                          ▼
                ┌─────────────────────┐
                │  importiert         │   (Stage 0: neu, noch keine Erkennung gelaufen)
                └──────────┬──────────┘
                           │ Erkennungs-Pipeline (synchron, im Import-Tail)
                           ▼
   ┌───────────────────────┼───────────────────────┐
   ▼                       ▼                       ▼
┌─────────┐         ┌──────────────┐         ┌──────────────┐
│ erkannt │         │ vorschlag    │         │ unklar       │
│ (Stufe 1)│        │ (Stufe 2)    │         │ (Stufe 3)    │
│ Konf.=1.0│        │ Konf. 0.5–<1 │         │ Konf. < 0.5  │
└────┬────┘         └──────┬───────┘         └──────┬───────┘
     │                     │                        │
     │ (Auto-Booking       │ (Manuelle Bestätigung  │ (Manuelle
     │  bei Konf. = 1.0    │  oder Korrektur in     │  Vollerfassung
     │  und Auto-Verbuchen │  Übersicht)            │  in Übersicht)
     │  erlaubt)           │                        │
     ▼                     ▼                        ▼
              ┌─────────────────────────────────┐
              │  verbucht                       │  (terminal — Hauptbuch geschrieben)
              └─────────────────────────────────┘
                           │
                           ▼  (bei nachträglichem Stornowunsch)
              ┌─────────────────────────────────┐
              │  storniert                      │  (GoBD-konformes Storno)
              └─────────────────────────────────┘
```

| Status | Bedeutung |
|---|---|
| `importiert` | Roh aus camt.053; noch keine Erkennung gelaufen (Übergangszustand, max. Sekunden) |
| `erkannt` | Eindeutiges Gegenkonto via Regel-Match (Konf. = 1.0) |
| `vorschlag` | Plausibles Gegenkonto vorhanden, aber nicht eindeutig (Konf. 0.5 bis < 1.0) |
| `unklar` | Keine eindeutige Zuordnung möglich (Konf. < 0.5) |
| `verbucht` | Hauptbuch-Buchung (`Buchung` + `Buchungssatz`) ist geschrieben |
| `storniert` | Hauptbuch-Storno geschrieben; Bankbuchung bleibt im camt.053-Log |

### 2.2 Auto-Booking

Buchungen im Status `erkannt` mit Konfidenz exakt `1.0` werden **am Ende
der Import-Transaktion automatisch verbucht**, sofern am Mandanten das
Flag `auto_verbuchen_aktiv = True` gesetzt ist (Default: `True`).

Das ist die einzige Stelle, an der das System ohne Nutzerinteraktion
Buchungen im Hauptbuch erzeugt — und sie ist auf eindeutige Regel-Treffer
(IBAN-Match oder bestätigte Lern-Regel) beschränkt.

### 2.3 Erkennungsquellen (in Prioritätsreihenfolge)

Die Erkennungspipeline arbeitet **deterministisch und in Stufen**. Stufe N
läuft nur, wenn Stufe N-1 nicht eindeutig war:

| Stufe | Quelle | Konfidenz bei Treffer | Konsequenz |
|---|---|---|---|
| 1a | **`EndToEndId`-Match** auf offene Hausgeld-Sollstellung (Suffix `-B`, `-R{n}`, `-S`, `-A`, `-AUSZ`) | 1.0 | Auto-Tilgung im Nebenbuch (HAUSGELD_NEBENBUCH Kap. 10.1) — Bankbuchung wird **direkt** als `verbucht` markiert, erscheint nicht in der E-Banking-Übersicht |
| 1b | **IBAN-Match** auf eindeutiges `EigentumsVerhältnis` + Betrag = Soll + Einnahmen-Check | 1.0 | Auto-Tilgung Nebenbuch (HAUSGELD_NEBENBUCH Kap. 10.2) — `verbucht`, nicht in Übersicht |
| 2 | **Bank-Match-Regel** (neu, siehe Kap. 4.2): `(bankkonto, kontrahent_iban, verwendungszweck_hash) → gegenkonto` | 1.0 | Status `erkannt`, Auto-Booking möglich |
| 3 | **IBAN-Match** auf Kreditor (`Person`, `person_typ='300'`) ohne OP-Treffer | 0.80 | Status `vorschlag`, Gegenkonto leer — kein Auto-Booking |
| 3b | **Kreditor-Lastschrift OP-Match** (`betrag < 0`): IBAN → `rechnungen.Kreditor` → `KreditorOP` mit `betrag_offen ≈ |betrag|` | 1.0 (genau 1 OP) / 0.85 (mehrere OPs) / 0.70 (Kreditor bekannt, kein OP) | Status `erkannt` oder `vorschlag`; Gegenkonto = Kreditorkonto (70xxx) |
| 4 | **KI-Vorschlag** (Claude API) mit WEG-Kontext | KI-Konfidenz, gecappt bei 0.85 | Status `vorschlag` |
| 5 | Kein Treffer | 0.0 | Status `unklar` |

> **Hinweis zur Stufung gegenüber Bestandscode:** Stufe 1a/1b sind die
> bestehenden Eingangswege aus der Nebenbuch-Spec — sie laufen am
> E-Banking-Modul vorbei in das Nebenbuch. Stufe 2–5 sind der neue
> Mechanismus, der **Aufwandsseite und alle nicht-EV-Eingänge** abdeckt
> (Kreditor-Zahlungen, Bankgebühren, Zinsen, Rückerstattungen,
> Nebenkostenabschläge etc.).

### 2.4 Lernlogik — Schlüssel

Lernschlüssel der `BankMatchRegel`:

```
(bankkonto, kontrahent_iban, verwendungszweck_hash) → gegenkonto
```

- **`bankkonto`** scoped die Regel auf das Objekt (jedes WEG-Bankkonto ist
  einem Objekt zugeordnet — Regeln generalisieren also **nicht** über
  Objekte hinweg).
- **`kontrahent_iban`** ist die IBAN der Gegenseite aus dem camt-Datensatz.
- **`verwendungszweck_hash`** ist ein normalisierter Hash analog
  `leistungstext_hash` aus der Rechnungserkennung (Datumsangaben,
  Belegnummern, Whitespace entfernt).
- Bei **fehlender IBAN** (Bargeld-Einzahlung, manche Auslandszahlungen)
  wird ein Platzhalter `"NO_IBAN"` verwendet — die Regel greift dann
  über Verwendungszweck-Hash allein.

**Sofort-Lernen:** Jede Bestätigung oder Korrektur erzeugt bzw.
aktualisiert eine Regel — analog Rechnungserkennung v1.2. Idempotenz:
gleiche Bestätigung zweimal = `trefferzahl++`, keine zweite Regel.

---

## 3. Architektur-Überblick

```
camt.053 (Datei oder API)
    │
    ▼
[bestehender camt.053-Parser]                  <-- unverändert
    │ erzeugt: BankImport + BankBuchung (Rohdaten)
    │
    ▼
[NEU: ebanking_erkennungs_service.fuehre_erkennung_aus]
    │  Stufen 1a → 1b → 2 → 3 → 4 → 5
    │
    ├── Treffer Stufe 1a/1b → Nebenbuch-Tilgung (bestehender Service)
    │                          → BankBuchung.status = 'verbucht'
    │
    └── Treffer Stufe 2 mit Konf. 1.0 und auto_verbuchen_aktiv=True
    │       → [ebanking_buchungs_service.verbuche]
    │       → Buchung + Buchungssatz erzeugen
    │       → BankBuchung.status = 'verbucht'
    │
    └── alle anderen Treffer → BankBuchung.status ∈ {erkannt, vorschlag, unklar}
                               → erscheinen in E-Banking-Übersicht

camt.054 (Datei oder API)                        <-- NEU als Abzweig
    │
    ▼
[NEU: camt054_parser_service]                    <-- STUB in v1.0
    │ legt CamtImport (typ='camt054') an
    │ ruft (in v1.0): NotImplementedError("R-Transactions: siehe Mahnwesen-Spec")
    │ Hook-Funktion ist vorhanden — bleibt aber unimplementiert.
    │
    └── (späterer Pfad in Mahnwesen-Spec:
         Rücklastschrift verarbeiten → Tilgung zurückrollen → Gebühr ansetzen)
```

---

## 4. Datenmodell

### 4.1 `BankBuchung` (existiert ggf. schon — anpassen / sicherstellen)

Falls vorhanden, ergänzen. Falls nur als Hilfsstruktur im Parser geführt:
als eigenständiges Model materialisieren.

| Feld | Typ | Anmerkung |
|---|---|---|
| `id` | UUID (PK) | |
| `bank_import` | FK → BankImport, on_delete=PROTECT | Quelle (camt.053) |
| `bankkonto` | FK → Bankkonto, on_delete=PROTECT | das eigene Konto |
| `valuta` | DateField | aus `<BookgDt>` |
| `buchungsdatum` | DateField | aus `<ValDt>` |
| `betrag` | DecimalField(14, 2) | Vorzeichen: + Eingang, − Ausgang |
| `waehrung` | CharField(3) | meist `EUR` |
| `kontrahent_name` | CharField(140) | aus `<Nm>` |
| `kontrahent_iban` | CharField(34), nullable | aus `<IBAN>` |
| `verwendungszweck` | TextField | konkateniert aus `<Ustrd>` |
| `end_to_end_id` | CharField(35), nullable | aus `<EndToEndId>` |
| `zahlungsart_code` | CharField(4), nullable | aus `<BkTxCd>/<Prtry>` |
| `transaktions_hash` | CharField(64), unique | SHA-256, Dedup-Schlüssel |
| **`status`** | Enum: `importiert` / `erkannt` / `vorschlag` / `unklar` / `verbucht` / `storniert` | siehe Kap. 2.1 |
| **`erkannt_gegenkonto`** | FK → Konto, nullable | Vorschlag aus Erkennungspipeline |
| **`erkannt_eigentumsverhaeltnis`** | FK → EigentumsVerhaeltnis, nullable | bei Hausgeld-Eingängen |
| **`erkannt_kreditor`** | FK → Person, nullable | bei Kreditor-Zahlungen |
| **`erkennungs_quelle`** | Enum: `e2e_id` / `iban_ev` / `bank_match_regel` / `iban_kreditor` / `kreditor_op_match` / `ki` / `keine` | für Audit + Lernlogik |
| **`erkannt_kreditor_op`** | FK → KreditorOP, nullable | bei Stufe 3b: der eindeutig gematchte offene Posten |
| **`erkennungs_konfidenz`** | DecimalField(3, 2) | 0.00 – 1.00 |
| **`erkennungs_begruendung`** | TextField | menschenlesbar, für Übersicht |
| `match_regel` | FK → BankMatchRegel, nullable | wenn Stufe 2 |
| **`buchung`** | FK → Buchung, nullable | gefüllt nach Verbuchung |
| **`verbucht_am`** | DateTimeField, nullable | |
| **`verbucht_von`** | FK → User, nullable | System-User bei Auto-Booking |
| `notiz` | TextField, blank | freie Eingabe in Übersicht |
| `erstellt_am` | DateTimeField, auto | |

**Indexe:**

- `(bankkonto, status)` — Filter für Übersicht.
- `(status, buchungsdatum)` — Sortierung.
- `transaktions_hash` (unique).

**Constraints:**

- `status = 'verbucht'` ⇒ `buchung_id IS NOT NULL` (Service-Validierung).
- `status = 'erkannt'` ⇒ `erkannt_gegenkonto_id IS NOT NULL`
  (Service-Validierung).

### 4.2 `BankMatchRegel` (NEU)

Lernlogik-Tabelle, vollständig analog zu `RechnungsMatchRegel` aus der
3-stufigen Rechnungserkennung.

| Feld | Typ | Anmerkung |
|---|---|---|
| `id` | UUID (PK) | |
| `bankkonto` | FK → Bankkonto, on_delete=CASCADE | scoped Regel aufs Objekt |
| `kontrahent_iban` | CharField(34) | `"NO_IBAN"` als Platzhalter erlaubt |
| `verwendungszweck_hash` | CharField(64) | normalisierter Hash, siehe Kap. 5.2 |
| `gegenkonto` | FK → Konto, on_delete=PROTECT | das gelernte Konto |
| `kreditor` | FK → Person, nullable | optional, falls Kreditor-Zahlung |
| `eigentumsverhaeltnis` | FK → EigentumsVerhaeltnis, nullable | optional, falls EV-Zuordnung |
| `status` | Enum: `aktiv` / `veraltet` | bei Korrektur wechselt alte Regel auf `veraltet` |
| `erstellt_aus` | Enum: `bestaetigung` / `korrektur` / `manuell` | |
| `trefferzahl` | IntegerField, default 0 | bei jeder Anwendung +1 |
| `letzte_anwendung` | DateTimeField, nullable | |
| `erstellt_am` | DateTimeField, auto | |
| `erstellt_von` | FK → User | |

**Constraints:**

- `UniqueConstraint(fields=['bankkonto', 'kontrahent_iban',
  'verwendungszweck_hash', 'status'], condition=Q(status='aktiv'),
  name='unique_aktive_bankregel')` — max. eine aktive Regel je Schlüssel.

### 4.3 `BankErkennungsLog` (Audit-Trail)

Schreibt **jeden** Erkennungsdurchlauf mit — analog
`RechnungsErkennungsLog`.

| Feld | Typ |
|---|---|
| `id` | UUID (PK) |
| `bank_buchung` | FK → BankBuchung, on_delete=CASCADE |
| `stufe_erreicht` | CharField (1a/1b/2/3/4/5) |
| `quelle` | siehe `BankBuchung.erkennungs_quelle` |
| `konfidenz` | DecimalField(3, 2) |
| `gegenkonto_vorschlag` | FK → Konto, nullable |
| `regel_treffer` | FK → BankMatchRegel, nullable |
| `auto_verbucht` | BooleanField |
| `details_json` | JSONField | KI-Antwort, Kandidatenliste, scoring |
| `erstellt_am` | DateTimeField, auto |

### 4.4 `CamtImport` — Erweiterung um camt.054-Stub

Bestehendes `BankImport`/`CamtImport`-Model wird um eine Typ-Spalte
erweitert (falls noch nicht vorhanden):

| Feld | Typ | Anmerkung |
|---|---|---|
| `typ` | Enum: `camt053` / `camt054` | Default `camt053` |
| ... bestehende Felder ... | | |

Bei `typ = camt054` wird kein `BankBuchung`-Datensatz erzeugt — sondern
ein **Stub-Pfad** durchlaufen (siehe Kap. 8).

### 4.5 `Mandant.auto_verbuchen_aktiv` (Konfigurations-Flag)

Neues Boolean-Feld am Mandant (oder analoge globale Settings-Tabelle).
Default `True`. Wenn `False`, werden auch eindeutig erkannte Buchungen
nicht automatisch verbucht — sie erscheinen mit Status `erkannt` in der
Übersicht und warten auf manuelle Bestätigung. Für vorsichtigen Roll-Out.

---

## 5. Erkennungs-Pipeline

### 5.1 Trigger

Die Pipeline läuft **synchron am Ende der camt.053-Import-Transaktion**
für jede neu erzeugte `BankBuchung`, idealerweise innerhalb derselben
`transaction.atomic()`. Lange KI-Aufrufe (Stufe 4) werden asynchron via
Celery nachgezogen — die Buchung erhält dann zunächst Status `unklar`,
nach KI-Antwort ggf. `vorschlag`.

### 5.2 Normalisierung Verwendungszweck

```python
def normalisiere_verwendungszweck(text: str) -> str:
    """
    Entfernt Belegnummern, Datumsangaben, Sollstellungs-Referenzen,
    Mehrfach-Whitespace und macht alles lowercase.
    """
    s = text.lower()
    s = re.sub(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", "", s)       # Daten
    s = re.sub(r"\b(re|rg|nr|nummer|kdnr|kdn|beleg)[-\s:]*\d+\b", "", s)
    s = re.sub(r"\b\d{4,}\b", "", s)                                # lange Zahlen
    s = re.sub(r"[^a-zäöüß\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def verwendungszweck_hash(text: str) -> str:
    norm = normalisiere_verwendungszweck(text)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()
```

Unit-Tests sicherstellen: Hash stabil gegen Whitespace, Groß/Klein,
unterschiedliche Belegnummern, abweichende Datumsformate.

### 5.3 Pseudocode — `fuehre_erkennung_aus`

```python
@transaction.atomic
def fuehre_erkennung_aus(bb: BankBuchung) -> BankBuchung:
    log = BankErkennungsLog(bank_buchung=bb)

    # ---- Stufe 1a: EndToEndId-Match (Hausgeld-Nebenbuch) ----
    if bb.end_to_end_id and bb.betrag > 0:
        treffer = nebenbuch.versuche_e2e_tilgung(bb)
        if treffer:
            bb.status = 'verbucht'           # Nebenbuch hat schon gebucht
            bb.erkennungs_quelle = 'e2e_id'
            bb.erkennungs_konfidenz = Decimal("1.00")
            bb.buchung = treffer.buchung
            log.stufe_erreicht = '1a'
            log.auto_verbucht = True
            _save_all(bb, log)
            return bb

    # ---- Stufe 1b: IBAN-Match auf EigentumsVerhältnis ----
    if bb.kontrahent_iban and bb.betrag > 0:
        treffer_ev = nebenbuch.versuche_iban_ev_tilgung(bb)
        if treffer_ev:
            bb.status = 'verbucht'
            bb.erkennungs_quelle = 'iban_ev'
            bb.erkennungs_konfidenz = Decimal("1.00")
            bb.buchung = treffer_ev.buchung
            log.stufe_erreicht = '1b'
            log.auto_verbucht = True
            _save_all(bb, log)
            return bb

    # ---- Stufe 2: BankMatchRegel ----
    iban_key = bb.kontrahent_iban or "NO_IBAN"
    vz_hash  = verwendungszweck_hash(bb.verwendungszweck or "")

    regel = BankMatchRegel.objects.filter(
        bankkonto=bb.bankkonto,
        kontrahent_iban=iban_key,
        verwendungszweck_hash=vz_hash,
        status='aktiv',
    ).first()

    if regel:
        bb.status = 'erkannt'
        bb.erkannt_gegenkonto = regel.gegenkonto
        bb.erkannt_kreditor = regel.kreditor
        bb.erkannt_eigentumsverhaeltnis = regel.eigentumsverhaeltnis
        bb.erkennungs_quelle = 'bank_match_regel'
        bb.erkennungs_konfidenz = Decimal("1.00")
        bb.erkennungs_begruendung = (
            f"Gelernte Regel #{regel.id} (Treffer #{regel.trefferzahl + 1})"
        )
        bb.match_regel = regel
        regel.trefferzahl += 1
        regel.letzte_anwendung = timezone.now()
        regel.save(update_fields=['trefferzahl', 'letzte_anwendung'])
        log.stufe_erreicht = '2'
        log.regel_treffer = regel

        # Auto-Booking
        if (bb.bankkonto.objekt.mandant.auto_verbuchen_aktiv
                and bb.erkennungs_konfidenz == Decimal("1.00")):
            ebanking_buchungs_service.verbuche(bb, verbucht_von=system_user())
            log.auto_verbucht = True

        _save_all(bb, log)
        return bb

    # ---- Stufe 3: IBAN-Match auf Kreditor (ohne OP, Eingänge / unklare Richtung) ----
    if bb.kontrahent_iban:
        kreditor = Person.objects.filter(
            ibans__contains=[bb.kontrahent_iban], rolle='dienstleister'
        ).first()
        if kreditor:
            bb.status = 'vorschlag'
            bb.erkannt_kreditor = kreditor
            bb.erkennungs_quelle = 'iban_kreditor'
            bb.erkennungs_konfidenz = Decimal("0.80")
            bb.erkennungs_begruendung = (
                f"IBAN identifiziert Kreditor {kreditor.anzeigename}, "
                f"Gegenkonto noch zu wählen."
            )
            log.stufe_erreicht = '3'
            _save_all(bb, log)
            return bb

    # ---- Stufe 3b: Kreditor-Lastschrift OP-Match (nur betrag < 0) ----
    # Bei Abbuchungen durch einen Kreditor per SEPA-Lastschrift:
    # IBAN → rechnungen.Kreditor → offene KreditorOPs nach Betrag.
    # Kein normalisierter VZ-Hash — der Betrag ist das primäre Matching-Kriterium.
    # Rechnungsnummer im Verwendungszweck dient als Konfidenz-Boost.
    if bb.betrag < 0 and bb.kontrahent_iban:
        treffer = _versuche_kreditor_op_match(bb)
        if treffer:
            bb.status = 'erkannt' if treffer['konfidenz'] == Decimal("1.00") else 'vorschlag'
            bb.erkannt_gegenkonto           = treffer['kreditorkonto']
            bb.erkannt_kreditor_op          = treffer['op']          # genau 1 OP oder None
            bb.erkennungs_quelle            = 'kreditor_op_match'
            bb.erkennungs_konfidenz         = treffer['konfidenz']
            bb.erkennungs_begruendung       = treffer['begruendung']
            log.stufe_erreicht              = '3b'
            log.quelle                      = 'kreditor_op_match'
            log.konfidenz                   = treffer['konfidenz']
            log.gegenkonto_vorschlag        = treffer['kreditorkonto']

            # Auto-Booking nur bei eindeutigem OP-Match (Konfidenz 1.0)
            if (bb.status == 'erkannt'
                    and bb.bankkonto.objekt.auto_verbuchen_aktiv
                    and bb.erkannt_gegenkonto):
                ebanking_buchungs_service.verbuche(bb, verbucht_von=system_user())
                log.auto_verbucht = True

            _save_all(bb, log)
            return bb

    # ---- Stufe 4: KI-Fallback ----
    try:
        ki = ki_buchungserkennung.frage(bb)
        if ki.konfidenz >= Decimal("0.50"):
            bb.status = 'vorschlag'
            bb.erkannt_gegenkonto = ki.gegenkonto
            bb.erkennungs_quelle = 'ki'
            bb.erkennungs_konfidenz = min(ki.konfidenz, Decimal("0.85"))
            bb.erkennungs_begruendung = ki.begruendung
            log.stufe_erreicht = '4'
            log.details_json = ki.raw_response
            _save_all(bb, log)
            return bb
    except KIError as e:
        log.details_json = {"ki_error": str(e)}

    # ---- Stufe 5: unklar ----
    bb.status = 'unklar'
    bb.erkennungs_quelle = 'keine'
    bb.erkennungs_konfidenz = Decimal("0.00")
    log.stufe_erreicht = '5'
    _save_all(bb, log)
    return bb
```

---

## 6. Verbuchungs-Service

### 6.1 `ebanking_buchungs_service.verbuche`

Erzeugt im Hauptbuch eine `Buchung` mit zwei `Buchungssatz`-Einträgen
(Soll / Haben) und setzt die `BankBuchung` auf `verbucht`.

```python
@transaction.atomic
def verbuche(bb: BankBuchung, verbucht_von: User,
             gegenkonto: Konto | None = None,
             eigentumsverhaeltnis: EigentumsVerhaeltnis | None = None,
             kreditor: Person | None = None,
             notiz: str = "") -> Buchung:
    """
    Verbucht eine BankBuchung im Hauptbuch.
    Args (optional) überschreiben die erkannten Werte (manueller Eingriff).
    """
    if bb.status == 'verbucht':
        raise ValidationError("BankBuchung ist bereits verbucht.")
    if bb.status == 'storniert':
        raise ValidationError("BankBuchung ist storniert.")

    gk  = gegenkonto or bb.erkannt_gegenkonto
    ev  = eigentumsverhaeltnis or bb.erkannt_eigentumsverhaeltnis
    kr  = kreditor or bb.erkannt_kreditor

    if not gk:
        raise ValidationError(
            "Gegenkonto fehlt — bitte erst wählen oder bestätigen."
        )

    bank_konto = bb.bankkonto.sachkonto  # 18xxx aus Bankkonto.sachkonto

    # Vorzeichen-Logik:
    # Betrag > 0 (Eingang):  Soll Bank   / Haben Gegenkonto
    # Betrag < 0 (Ausgang):  Soll Gegen. / Haben Bank
    betrag_abs = abs(bb.betrag)
    if bb.betrag > 0:
        soll_konto, haben_konto = bank_konto, gk
    else:
        soll_konto, haben_konto = gk, bank_konto

    b = Buchung.objects.create(
        weg=bb.bankkonto.objekt,
        beleg=bb,
        buchungstext=_buchungstext(bb, gk, ev, kr),
        belegdatum=bb.valuta,
        erstellt_von=verbucht_von,
        art='BANK_EBANKING',
    )
    Buchungssatz.objects.create(buchung=b, konto=soll_konto,
                                soll=betrag_abs, haben=Decimal("0"))
    Buchungssatz.objects.create(buchung=b, konto=haben_konto,
                                soll=Decimal("0"), haben=betrag_abs)

    bb.status = 'verbucht'
    bb.buchung = b
    bb.verbucht_am = timezone.now()
    bb.verbucht_von = verbucht_von
    if ev:  bb.erkannt_eigentumsverhaeltnis = ev
    if kr:  bb.erkannt_kreditor = kr
    bb.erkannt_gegenkonto = gk
    if notiz:
        bb.notiz = notiz
    bb.save()
    return b
```

**Wichtige Validierungen:**

- Wenn `gk.kontonr.startswith("70")` (Kreditor-Sachkonto):
  Buchung gleicht offenen Posten aus → zusätzlich `op_ausgleich_service`
  triggern (siehe OP_BUCHUNG v1.1 Phase 2 — die dortige Logik bleibt
  unangetastet, wird hier nur **angesprochen**).
- Wenn `gk` ein Aufwandskonto (`50xxx` / `55xxx`) **direkt** ist (also
  ohne OP-Hop): zulässig nur bei zahlungswirksamen Vorgängen ohne
  Eingangsrechnung (z.B. Bankgebühren direkt).
- `gk.kontoart != 'Summierungskonto'`.
- `gk.direktes_buchen == True` für die direkten Buchungswege.

### 6.2 `_buchungstext` (Helper)

```python
def _buchungstext(bb, gk, ev, kr) -> str:
    parts = []
    if kr: parts.append(kr.anzeigename)
    if ev: parts.append(f"WE{ev.einheit.einheit_nr}")
    if bb.verwendungszweck:
        parts.append(bb.verwendungszweck[:60])
    return " — ".join(p for p in parts if p) or "Banktransaktion"
```

---

## 7. Lernlogik

### 7.1 Drei Lern-Trigger

| Trigger | Auslöser | Aktion |
|---|---|---|
| **Bestätigung** | Nutzer klickt "Bestätigen & Verbuchen" auf einer Buchung im Status `erkannt` oder `vorschlag`, ohne das erkannte Gegenkonto zu ändern | Falls Quelle ≠ `bank_match_regel`: neue Regel mit `erstellt_aus='bestaetigung'`. Falls bereits Regel-Treffer: `trefferzahl++`. |
| **Korrektur** | Nutzer ändert vor dem Verbuchen das Gegenkonto / Kreditor / EV | Bestehende Regel (falls vorhanden) → `status='veraltet'`. Neue Regel mit `erstellt_aus='korrektur'`. |
| **Manuell-Erfassung** | Nutzer verbucht eine `unklar`-Buchung | Neue Regel mit `erstellt_aus='manuell'` (Opt-out-Checkbox "Einzelfall — keine Regel speichern" möglich). |

> **Hinweis Stufe 3b:** Buchungen mit Quelle `kreditor_op_match` lösen **keine** neue `BankMatchRegel` aus — die Zuordnung ist bereits durch den offenen OP eindeutig. Lernregeln werden nur angelegt, wenn der Nutzer ein abweichendes Gegenkonto wählt (Korrektur-Trigger) oder die Buchung aus dem `unklar`-Zustand manuell verbucht wird.

### 7.2 Opt-out

In der Detailansicht jeder Buchung ist eine Checkbox **"Einzelfall — keine
Regel speichern"** vorhanden, default `False`. Aktiviert: kein
Regel-Eintrag, keine Aktualisierung — die Buchung wird verbucht, das
System lernt nichts.

### 7.3 Idempotenz

Bei zweimaliger gleicher Bestätigung darf **keine** zweite aktive Regel
mit gleichem Schlüssel entstehen. Mechanik:

```python
def regel_anlegen_oder_aktualisieren(bb, gegenkonto, erstellt_aus, user):
    iban_key = bb.kontrahent_iban or "NO_IBAN"
    vz_hash  = verwendungszweck_hash(bb.verwendungszweck or "")

    bestehend = BankMatchRegel.objects.filter(
        bankkonto=bb.bankkonto,
        kontrahent_iban=iban_key,
        verwendungszweck_hash=vz_hash,
        status='aktiv',
    ).first()

    if bestehend:
        if bestehend.gegenkonto_id == gegenkonto.id:
            bestehend.trefferzahl += 1
            bestehend.letzte_anwendung = timezone.now()
            bestehend.save()
            return bestehend
        else:
            bestehend.status = 'veraltet'
            bestehend.save()

    return BankMatchRegel.objects.create(
        bankkonto=bb.bankkonto,
        kontrahent_iban=iban_key,
        verwendungszweck_hash=vz_hash,
        gegenkonto=gegenkonto,
        kreditor=bb.erkannt_kreditor,
        eigentumsverhaeltnis=bb.erkannt_eigentumsverhaeltnis,
        status='aktiv',
        erstellt_aus=erstellt_aus,
        trefferzahl=1,
        letzte_anwendung=timezone.now(),
        erstellt_von=user,
    )
```

---

## 8. camt.054-Abzweig (STUB in v1.0)

Diese Spec führt den **strukturellen** Andockpunkt für camt.054 ein. Die
Verarbeitungslogik bleibt v1.0 **leer** und gehört in die Mahnwesen-Spec.

### 8.1 Eingang

- Bestehender Upload-/Import-Endpunkt akzeptiert zusätzlich camt.054-XML.
- Parser erkennt Wurzelelement (`<BkToCstmrDbtCdtNtfctn>` vs.
  `<BkToCstmrStmt>`) und setzt `CamtImport.typ = 'camt054'`.

### 8.2 Stub-Verarbeitung

```python
# apps/buchhaltung/services/camt054_service.py

def verarbeite_camt054(camt_import: CamtImport) -> None:
    """
    STUB v1.0 — vollständige R-Transactions-Verarbeitung
    ist Teil der Mahnwesen-Spec (siehe HAUSGELD_NEBENBUCH v1.1 Kap. 11).
    """
    # camt.054-XML wird geparst, Notification-Entries werden ausgezählt
    # — aber NICHT in BankBuchung / Buchung übertragen.
    anzahl_entries = _zaehle_ntry(camt_import.xml_inhalt)
    camt_import.status = 'pending_mahnwesen_spec'
    camt_import.notiz = (
        f"camt.054 angenommen ({anzahl_entries} Einträge). "
        f"Verarbeitung erfolgt mit Mahnwesen-Spec."
    )
    camt_import.save(update_fields=['status', 'notiz'])
    logger.warning(
        "camt.054 import %s parked — implementation pending.",
        camt_import.id,
    )

def _zaehle_ntry(xml_inhalt: str) -> int:
    # leichtgewichtiges Mitzählen ohne Vollparse
    return xml_inhalt.count("<Ntry>")
```

### 8.3 Sichtbarkeit in der UI

In der E-Banking-Übersicht erscheint ein **separater Tab "camt.054"** mit
Liste aller eingegangenen, aber **unverarbeiteten** camt.054-Importe und
einem Hinweis-Banner:

> "Verarbeitung von Rücklastschriften wird in der Mahnwesen-Spec
> implementiert. Die Dateien sind sicher gespeichert und werden nach
> Implementierung nachgezogen."

Der Tab ist **lesend** — kein Button, keine Aktion.

### 8.4 Verifikation Stub

Ein Upload einer camt.054-Datei darf **nicht** abstürzen, die Datei
**muss** als `CamtImport` mit `typ='camt054'` und Status
`pending_mahnwesen_spec` gespeichert werden. Mehr nicht.

---

## 9. UI — E-Banking-Übersicht

### 9.1 Routing

```
/buchhaltung/e-banking                     Übersicht aktuelles Bankkonto
/buchhaltung/e-banking?bankkonto=<uuid>   wechselt Bankkonto
/buchhaltung/e-banking?tab=camt054        camt.054-Tab (read-only)
/buchhaltung/e-banking/regeln              Regelverwaltung (siehe Kap. 9.4)
```

### 9.2 Hauptansicht (Tab "camt.053 / Buchungen")

**Filterleiste (oben):**

| Filter | Optionen |
|---|---|
| Bankkonto | Dropdown aus den Bankkonten des aktiven Mandanten |
| Status | Multiselect: `erkannt`, `vorschlag`, `unklar`, `verbucht`, `storniert` (Default: ersten drei) |
| Datumsbereich | Default: letzte 30 Tage |
| Volltext | sucht in `kontrahent_name`, `verwendungszweck` |
| Betragsbereich | min / max |

**Tabelle (eine Zeile = eine `BankBuchung`):**

| Spalte | Inhalt |
|---|---|
| Status-Badge | farbig (siehe 9.3) |
| Datum | `buchungsdatum` |
| Gegenseite | `kontrahent_name` (+ IBAN klein darunter) |
| Verwendungszweck | gekürzt, voller Text im Tooltip |
| Betrag | rechtsbündig, +grün/-rot |
| **Gegenkonto** | `erkannt_gegenkonto.nummer + name`, bei `unklar` leer mit Hinweis "—" |
| Konfidenz | Balken 0–100 % |
| Aktionen | "✓ Verbuchen" (wenn `erkannt`) / "Bearbeiten" (immer) / "Storno" (wenn `verbucht`) |

### 9.3 Status-Badges (Farben)

| Status | Farbe | Symbol |
|---|---|---|
| `erkannt` | 🟢 grün | ✓ |
| `vorschlag` | 🟡 gelb | ? |
| `unklar` | 🔴 rot | ! |
| `verbucht` | ⚪ neutral grau | ✓✓ |
| `storniert` | ⚫ dunkelgrau, durchgestrichen | ✗ |

### 9.4 Detail-/Bearbeitungsdialog

Öffnet als Slide-Over rechts. Enthält:

- **Bankdaten** (read-only): Datum, Betrag, Kontrahent, IBAN, BIC,
  Verwendungszweck, EndToEndId, Zahlungsart.
- **Erkennungsergebnis** (read-only mit Begründung): Stufe, Quelle,
  Konfidenz, Begründungstext aus `erkennungs_begruendung`.
- **Editierbar:**
  - Gegenkonto (Autocomplete aus Kontenplan des Objekts; gefiltert nach
    `direktes_buchen=True` und `kontoart='Standardkonto'`)
  - Kreditor (Autocomplete, optional)
  - EigentumsVerhältnis (Autocomplete, optional)
  - Notiz (freier Text)
  - Checkbox: "Einzelfall — keine Regel speichern" (Opt-out Lernen)
- **Buttons (unten):**
  - **"Bestätigen & Verbuchen"** (primär, grün) — wenn Gegenkonto
    gesetzt; löst Lernlogik (Kap. 7.1) und `verbuche` (Kap. 6.1) aus.
  - **"Speichern ohne Verbuchen"** — speichert nur Felder + Notiz,
    Status bleibt `vorschlag`/`unklar`, kein Lerneffekt.
  - **"Abbrechen"** — schließt Dialog ohne Änderung.

### 9.5 Auto-Verbuchen-Hinweis

Oben in der Tabelle ein Banner, wenn `auto_verbuchen_aktiv = True`:

> "Auto-Verbuchen ist aktiv — eindeutig erkannte Buchungen werden direkt
> ins Hauptbuch übernommen und erscheinen hier nur noch im Tab
> 'Verbucht'."

### 9.6 Regel-Verwaltung (`/buchhaltung/e-banking/regeln`)

Analog zur Rechnungs-Match-Regel-Seite (3-stufige Rechnungserkennung
Kap. 8.5/8.6):

- Filter: Bankkonto, Kontrahent-IBAN, Status, `erstellt_aus`.
- Spalten: Bankkonto, Kontrahent-IBAN, normalisierter Vz-Auszug,
  Gegenkonto, Trefferzahl, letzte Anwendung, Status.
- Aktion: Regel auf `veraltet` setzen (kein Hard-Delete im MVP — GoBD).

### 9.7 camt.054-Tab (read-only Stub)

Liste der `CamtImport` mit `typ='camt054'`:

| Spalte | Inhalt |
|---|---|
| Eingangsdatum | `erstellt_am` |
| Dateiname | Original-Upload-Name |
| Anzahl Einträge | aus `notiz` ausgelesen |
| Status | `pending_mahnwesen_spec` (immer) |

Banner oben am Tab: siehe Kap. 8.3.

---

## 10. API-Endpunkte

| Methode | Pfad | Beschreibung |
|---|---|---|
| GET | `/api/v1/e-banking/bank-buchungen/` | Liste mit Filtern (siehe Kap. 9.2) |
| GET | `/api/v1/e-banking/bank-buchungen/{id}/` | Details inkl. Erkennungs-Log |
| POST | `/api/v1/e-banking/bank-buchungen/{id}/verbuchen/` | Body: `{ gegenkonto_id?, kreditor_id?, eigentumsverhaeltnis_id?, notiz?, opt_out_lernen: bool }` |
| POST | `/api/v1/e-banking/bank-buchungen/{id}/speichern/` | Speichert Felder ohne zu verbuchen |
| POST | `/api/v1/e-banking/bank-buchungen/{id}/erkennung-neu/` | Pipeline erneut ausführen |
| POST | `/api/v1/e-banking/bank-buchungen/{id}/storno/` | Body: `{ begruendung }`, GoBD-konformes Storno |
| GET | `/api/v1/e-banking/bank-match-regeln/` | Filter analog Rechnungs-Match-Regeln |
| PATCH | `/api/v1/e-banking/bank-match-regeln/{id}/` | Status auf `veraltet` |
| GET | `/api/v1/e-banking/camt054/` | Liste der geparkten camt.054-Importe |

JWT-Bearer-Token erforderlich. Berechtigung: nur Mandant-eigene
`Bankkonto`-Objekte.

---

## 11. Validierungsregeln (Service-Layer)

| Regel | Konsequenz |
|---|---|
| `gegenkonto` muss zu `bankkonto.objekt` gehören | ValidationError |
| `gegenkonto.kontoart != 'Summierungskonto'` | ValidationError |
| `gegenkonto.direktes_buchen == True` | ValidationError |
| Auto-Booking nur bei `erkennungs_konfidenz == 1.00` | sonst manuelle Bestätigung |
| Verbuchen nur in Status `erkannt`, `vorschlag` oder `unklar` | sonst Fehler |
| Storno nur in Status `verbucht` | sonst Fehler |
| Bankbuchungen werden **nie gelöscht** (GoBD) | nur Status `storniert` |
| Mandant-Isolation: Regeln und Buchungen sind je Mandant getrennt | API-Filter |

---

## 12. Tests

### 12.1 Unit-Tests

- `normalisiere_verwendungszweck` entfernt Daten, Belegnummern, Whitespace.
- `verwendungszweck_hash` stabil gegen Whitespace, Groß/Klein,
  Belegnummern-Variation.
- `regel_anlegen_oder_aktualisieren`: Idempotenz; alte Regel wird
  `veraltet`, neue aktiv.
- `verbuche`: Vorzeichen-Logik (Eingang vs. Ausgang), Soll/Haben korrekt.
- Erkennungs-Pipeline: alle Stufen 1a–5 mit jeweils einem positiven und
  einem Boundary-Testfall.

### 12.2 Integrationstests — Workflow-Pfade

| Pfad | Szenario | Erwartung |
|---|---|---|
| 1 | EndToEndId-Match (Hausgeld-Tilgung) | Stufe 1a, Status sofort `verbucht`, **nicht** in E-Banking-Übersicht |
| 2 | IBAN-Match auf EV mit Betrag = Soll | Stufe 1b, Status `verbucht`, Nebenbuch getilgt |
| 3 | Bank-Match-Regel-Treffer + Auto-Verbuchen aktiv | Stufe 2, Status `verbucht`, Buchung im Journal, Lernregel `trefferzahl++` |
| 4 | Bank-Match-Regel-Treffer + Auto-Verbuchen **inaktiv** | Stufe 2, Status `erkannt`, kein Eintrag im Journal — wartet auf manuelle Bestätigung |
| 5 | IBAN-Match nur auf Kreditor (keine Regel) | Stufe 3, Status `vorschlag`, Konfidenz 0.80, Gegenkonto leer |
| 6 | KI-Vorschlag mit Konfidenz 0.78 | Stufe 4, Status `vorschlag` |
| 7 | Keine Hits | Stufe 5, Status `unklar` |
| 8 | Manuelle Bestätigung (kein Wechsel des Gegenkontos) | neue Regel `erstellt_aus='bestaetigung'`, Status → `verbucht` |
| 9 | Manuelle Korrektur (Gegenkonto-Wechsel) | alte Regel → `veraltet`, neue Regel `erstellt_aus='korrektur'`, Status → `verbucht` |
| 10 | Manuelle Vollerfassung (unklar → verbucht) | neue Regel `erstellt_aus='manuell'`, Status → `verbucht` |
| 11 | Opt-out "Einzelfall" angeklickt | Status → `verbucht`, **keine** Regel angelegt/aktualisiert |
| 12 | Doppelte Bestätigung (Idempotenz) | `trefferzahl++`, keine zweite aktive Regel |
| 13 | Storno einer verbuchten BankBuchung | Status `storniert`, GoBD-konforme Storno-Buchung im Journal |
| 14 | camt.054-Upload | `CamtImport.typ='camt054'`, Status `pending_mahnwesen_spec`, kein Crash, kein `BankBuchung`-Eintrag |
| 15 | Kreditor-Lastschrift, genau 1 offener OP mit passendem Betrag | Stufe 3b, Status `erkannt`, Konfidenz 1.0, Gegenkonto = 70xxx, `erkannt_kreditor_op` gesetzt |
| 16 | Kreditor-Lastschrift, mehrere OPs mit passendem Betrag | Stufe 3b, Status `vorschlag`, Konfidenz 0.85, Nutzer wählt OP manuell |
| 17 | Kreditor-Lastschrift, IBAN bekannt aber kein passender OP | Stufe 3b, Status `vorschlag`, Konfidenz 0.70, Hinweis "OP noch nicht erfasst" |
| 18 | Kreditor-Lastschrift mit Rechnungsnummer im Verwendungszweck, 1 OP-Treffer | Stufe 3b, Konfidenz 1.0, `erkennungs_begruendung` enthält Rechnungsnummer-Match-Hinweis |

### 12.3 Edge Cases

- Bankgebühr ohne IBAN, ohne Verwendungszweck → `iban_key="NO_IBAN"`,
  Verwendungszweck-Hash = Hash von Leerstring; Regel kann trotzdem
  greifen, sobald einmal verbucht.
- Eingang über Lastschriftrückrechnung (camt.053, **nicht** camt.054):
  EndToEndId hat Suffix `-B` aber Vorzeichen ist negativ — Stufe 1a darf
  **nicht** greifen, fällt durch zu Stufe 2 ff.
- Kreditor mit mehreren IBANs: jede IBAN trägt eigene Regel.

---

## 13. Implementierungs-Reihenfolge für Claude Code

| Phase | Inhalt | Voraussetzung |
|---|---|---|
| **A — Datenmodell** | Migration: `BankBuchung`-Felder ergänzen, `BankMatchRegel`, `BankErkennungsLog`, `CamtImport.typ`, `Mandant.auto_verbuchen_aktiv`. Daten-Migration: bestehende Bankbuchungen erhalten Status `verbucht` (Backfill, falls schon im Journal) bzw. `unklar` (falls nicht). | — |
| **B — Erkennungspipeline** | `normalisiere_verwendungszweck`, `verwendungszweck_hash`, `fuehre_erkennung_aus`, `regel_anlegen_oder_aktualisieren`. Unit-Tests grün. | Phase A |
| **C — Verbuchungsservice** | `ebanking_buchungs_service.verbuche` inkl. Vorzeichen-Logik und 70xxx-/OP-Hop-Anbindung. Integrations-Tests Pfade 3/4/5/8/9. | Phase B |
| **D — Auto-Booking-Hook** | Einbinden in den **bestehenden** camt.053-Import-Tail. Manueller End-to-End-Test mit einer realen Test-Datei. | Phase C |
| **E — UI** | Übersicht (Tab camt.053), Detail-Dialog, Regelverwaltung. | Phase D |
| **F — camt.054-Stub** | Parser-Erkennung, `verarbeite_camt054`-Stub, Tab in UI. | parallel zu E möglich |
| **G — Integrations-Tests + Smoke-Test** | Pfade 1–14 grün; Smoke-Test laut Kap. 14. | E + F |

> **Hinweis an Claude Code:** Phase D ist die kritische Stelle —
> **erst** wenn Phase C grün ist und Phase B-Unit-Tests stehen, darf der
> bestehende camt.053-Import-Tail um den Hook erweitert werden.
> Andernfalls werden produktive Importe in einen halbfertigen Status
> getrieben.

---

## 14. Akzeptanzkriterien (Smoke-Test vor Go-Live)

Manueller End-to-End-Test mit einem Test-Objekt + Test-Bankkonto:

1. **camt.053 mit 6 Bewegungen importieren**:
   - 1 Hausgeld-Eingang mit `EndToEndId` (Hausgeld-Tilgung)
   - 1 Hausgeld-Eingang per Dauerauftrag (IBAN-Match)
   - 1 Bankgebühr (kein IBAN-Match, kein bestehender Regel-Match)
   - 1 Kreditor-Zahlung (Stadtwerke, IBAN bekannt, kein bestehender
     Regel-Match)
   - 1 Wiederholung der Stadtwerke-Zahlung nach Bestätigung von #4
   - 1 vollkommen unklare Bewegung
2. **Erwartung** nach Import:
   - #1 und #2: Status `verbucht`, nicht in der Übersicht sichtbar (außer
     im Tab "Verbucht").
   - #3: Status `unklar`, in Übersicht rot markiert.
   - #4: Status `vorschlag`, Kreditor "Stadtwerke" erkannt, Gegenkonto
     leer.
   - #6: Status `unklar`.
3. **Manuell** #4 das Gegenkonto `55400` setzen, "Bestätigen & Verbuchen"
   klicken.
   - Buchung im Journal erscheint mit korrekter Soll/Haben-Zuordnung
     (Soll 55400 / Haben 18000).
   - Neue `BankMatchRegel` mit Schlüssel
     `(bankkonto, IBAN_Stadtwerke, vz_hash)` und Gegenkonto `55400`,
     `trefferzahl = 1`, `erstellt_aus = 'bestaetigung'`.
4. **#5 läuft danach automatisch durch**:
   - Status sofort `erkannt` (Stufe 2, Regel-Treffer, Konfidenz 1.00).
   - Falls `auto_verbuchen_aktiv = True`: Status sofort `verbucht`,
     Buchung im Journal, `trefferzahl = 2`.
5. **#3 (Bankgebühr)** manuell auf Gegenkonto `55101` setzen,
   "Bestätigen & Verbuchen".
   - Regel mit `IBAN_KEY = "NO_IBAN"` entsteht.
6. **Korrektur-Szenario**: Eine spätere ähnliche Bewegung mit Konto
   `55101` aufrufen, in der UI auf `55102` ändern, verbuchen.
   - Alte Regel → `veraltet`, neue Regel mit `erstellt_aus='korrektur'`
     aktiv.
7. **Opt-out-Szenario**: Eine Bewegung verbuchen mit Checkbox
   "Einzelfall" aktiv.
   - Keine neue Regel, kein Update der `trefferzahl`.
8. **camt.054-Datei** hochladen.
   - `CamtImport` mit `typ='camt054'` und Status
     `pending_mahnwesen_spec` angelegt; im camt.054-Tab sichtbar;
     keine `BankBuchung`-Einträge entstanden; kein Crash.
9. **Storno-Szenario**: Eine `verbucht`-BankBuchung stornieren.
   - Status `storniert`, GoBD-Storno-Buchung erscheint im Journal,
     Originalbuchung bleibt erhalten.

Wenn alle 9 Punkte grün sind, ist diese Spec implementierungs-vollständig.

---

## 15. Wichtige Hinweise für die Implementierung

| **STUFEN 1a/1b GEHEN AM E-BANKING-MODUL VORBEI** Hausgeld-Tilgungen werden weiterhin direkt vom Nebenbuch verbucht (HAUSGELD_NEBENBUCH v1.1 Kap. 10). Sie tauchen in der E-Banking-Übersicht **nur** im Filter-Tab "Verbucht" auf, nicht im Bearbeitungs-Workflow. |
| --- |

| **AUTO-BOOKING NUR BEI KONFIDENZ = 1.00 UND `auto_verbuchen_aktiv=True`** Alles andere geht durch die manuelle Übersicht. Konfidenz 0.99 ist nicht 1.0. |
| --- |

| **REGELN SIND OBJEKT-LOKAL** Schlüssel enthält `bankkonto`, und jedes Bankkonto gehört zu genau einem Objekt. Es gibt keine mandantenweite Generalisierung — bewusst, weil Verwendungszweck-Konventionen je WEG unterschiedlich sind. |
| --- |

| **GoBD: KEIN HARD-DELETE** Weder `BankBuchung` noch `BankMatchRegel` werden je gelöscht. Status-Wechsel nur (`verbucht` → `storniert`, `aktiv` → `veraltet`). |
| --- |

| **camt.054 IST EIN ABZWEIG, KEINE LOGIK** Datei wird angenommen, geparkt, im UI angezeigt — **nicht** verarbeitet. Der vollständige Pfad (Tilgung zurückrollen, Rücklastschriftgebühr ansetzen) gehört in die Mahnwesen-Spec. Der Hook-Punkt steht bereit. |
| --- |

---

## 16. Claude Code Prompt — Direktverwendung

Folgender Block kann unverändert in Claude Code eingefügt werden:

```
Lies IMMOCORE_ClaudeCode_EBanking_v1_0.md vollständig.

Voraussetzung: camt.053-Import (BankImport + Roh-BankBuchung), Hausgeld-
Nebenbuch (HAUSGELD_NEBENBUCH v1.1), OP-Buchung (OP_BUCHUNG v1.1) und
hybride Buchungserkennung Stufe 1/2 aus der Ausgangsspezifikation sind
funktional und getestet.

Ziel: E-Banking-Modul als Bearbeitungs-Layer zwischen camt.053-Import
und Hauptbuch. Bestätigte/erkannte Buchungen werden ins Journal
geschrieben, das System lernt aus jeder Korrektur. camt.054 wird
als Abzweig vorbereitet, bleibt aber leer (Stub).

Implementiere in der Reihenfolge der Phasen A–G aus Kapitel 13:

Phase A — Datenmodell
  - Erweiterung BankBuchung um Status-Lifecycle, erkannt_* Felder,
    erkennungs_quelle, erkennungs_konfidenz, erkennungs_begruendung,
    buchung, verbucht_am/von, notiz
  - Neue Tabellen BankMatchRegel, BankErkennungsLog
  - CamtImport um typ-Feld ('camt053' / 'camt054') ergänzen
  - Mandant.auto_verbuchen_aktiv (Default True)
  - Migration inkl. Backfill bestehender BankBuchungen

Phase B — Erkennungspipeline
  - normalisiere_verwendungszweck + verwendungszweck_hash (mit Unit-Tests)
  - fuehre_erkennung_aus mit Stufen 1a, 1b, 2, 3, 4, 5
    (Stufen 1a/1b delegieren an bestehende Nebenbuch-Services!)
  - regel_anlegen_oder_aktualisieren (idempotent, sofortiges Lernen)
  - BankErkennungsLog wird in jedem Pipeline-Lauf geschrieben

Phase C — Verbuchungsservice
  - ebanking_buchungs_service.verbuche mit
    Vorzeichen-Logik (Eingang vs. Ausgang Soll/Haben)
  - Validierungen: Gegenkonto gehört zum Objekt, kein Summierungskonto,
    direktes_buchen=True
  - Falls Gegenkonto = 70xxx-Kreditorkonto: bestehenden
    op_ausgleich_service ansprechen (NICHT neu implementieren)

Phase D — Auto-Booking-Hook
  - Im bestehenden camt.053-Import-Tail (synchron, innerhalb der Import-
    Transaktion): pro BankBuchung fuehre_erkennung_aus aufrufen
  - Bei Stufe-2-Treffer + Konfidenz 1.00 + auto_verbuchen_aktiv:
    sofort verbuche aufrufen
  - Bei längeren KI-Calls (Stufe 4): asynchron via Celery,
    Buchung erhält zunächst Status 'unklar'

Phase E — UI (React)
  - Route /buchhaltung/e-banking mit Tabs:
    * camt.053 / Buchungen (Hauptansicht)
    * Verbucht (Filter)
    * camt.054 (read-only Stub)
  - Filterleiste, Tabelle mit Status-Badges, Detail-Slide-Over
  - Buttons "Bestätigen & Verbuchen" / "Speichern ohne Verbuchen"
  - Checkbox "Einzelfall — keine Regel speichern"
  - Route /buchhaltung/e-banking/regeln (Regel-CRUD)

Phase F — camt.054-Stub
  - Upload-Endpoint erkennt Wurzelelement, setzt typ='camt054'
  - verarbeite_camt054 schreibt nur CamtImport mit Status
    'pending_mahnwesen_spec' und Eintragszahl in Notiz
  - UI-Tab listet diese Imports read-only, mit Hinweis-Banner

Phase G — Tests
  - Unit-Tests aus Kap. 12.1
  - Integrationstests aus Kap. 12.2 (Pfade 1-14)
  - Smoke-Test laut Kap. 14 manuell durchspielen

WICHTIG:
  - GoBD: Keine Bankbuchung wird je gelöscht. Storno = neuer Status,
    Original bleibt.
  - Stufen 1a/1b (Hausgeld-Tilgung) gehen am E-Banking-Modul vorbei
    und werden vom Nebenbuch direkt verbucht — der existierende Code
    bleibt unangetastet.
  - Auto-Booking nur bei Konfidenz EXAKT 1.00.
  - Regeln scopen auf Bankkonto (= Objekt). Keine mandantenweite
    Generalisierung.
  - Service-Layer-Trennung beibehalten: keine Buchungslogik in Views
    oder Models.

Nach jeder Phase: Migration erzeugen, Tests laufen lassen, erst dann
zur nächsten Phase. Bei Phase D unbedingt erst End-to-End-Test gegen
Test-Bankkonto mit echter camt.053-Datei laufen lassen, BEVOR auf
Produktiv-Daten gelassen.
```

---

**Ende der Spezifikation.**
