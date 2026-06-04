# CAMT.053 Buchungslogik — ImmoCORE WEG-Verwaltung

**Stand:** 2026-05-05  
**Zweck:** Beschreibung aller Buchungsfälle die aus einem CAMT.053-Kontoauszug entstehen,
Ist-Stand der Implementierung und offene Punkte.

---

## 1. CAMT.053 Satzstruktur (Relevante Felder)

```
Stmt/Ntry (pro Buchungszeile)
├── Amt                          Betrag (immer positiv)
├── CdtDbtInd                    CRDT = Eingang | DBIT = Ausgang
├── BookgDt/Dt                   Buchungsdatum
├── ValDt/Dt                     Wertstellungsdatum
├── BkTxCd
│   ├── Domn/Cd                  PMNT = Zahlungsverkehr
│   ├── Fmly/Cd                  ICDT = Instant Credit | RCDT = Regular Credit | IDDT = Lastschrift
│   └── SubFmlyCd                ESCT = SEPA Credit Transfer
├── NtryDtls
│   ├── Btch                     Sammelposten (NbOfTxs > 1)
│   └── TxDtls
│       ├── RltdPties
│       │   ├── Dbtr/Pty/Nm      Auftraggeber-Name  (bei DBIT = eigene WEG)
│       │   ├── DbtrAcct/IBAN    Auftraggeber-IBAN
│       │   ├── Cdtr/Pty/Nm      Empfänger-Name     (bei DBIT = Lieferant)
│       │   └── CdtrAcct/IBAN    Empfänger-IBAN
│       └── RmtInf/Ustrd         Verwendungszweck (Freitext)
```

**Richtungslogik:**

| CdtDbtInd | Bedeutung | Dbtr | Cdtr |
|-----------|-----------|------|------|
| CRDT | Geldeingang auf WEG-Konto | Zahler (Eigentümer, Dritter) | WEG |
| DBIT | Geldausgang vom WEG-Konto | WEG | Empfänger (Lieferant, Eigentümer) |

---

## 2. Buchungsfälle

### Fall 1 — CRDT: Hausgeld-Eingang Eigentümer ✅ implementiert

**Erkennungsmerkmal:** `CdtDbtInd = CRDT`, Auftraggeber-IBAN in `Person.ibans`

**Buchungssatz:**
```
Soll:  18000 Bankonto
Haben: Personenkonto .900 (Hausgeld-Unterkonto des Eigentümers)
BA:    020 EING-P
```

**Offener Posten:** Reduziert/schließt den Hausgeld-OP des Eigentümers
(§ 367 BGB: Kosten → Zinsen → Hauptschuld, ältester OP zuerst)

**Erkennung:** Stufe 1 regelbasiert (IBAN-Lookup), Stufe 2 Claude API als Fallback

**Beispiel aus CAMT-Daten:** CRDT, Eigentümer-IBAN → Personenkonto

---

### Fall 2 — DBIT/Einzelüberweisung: Lieferantenzahlung mit KreditorOP ❌ fehlt

**Erkennungsmerkmal:** `CdtDbtInd = DBIT`, kein `Btch`-Element, Creditor-IBAN im Satz,
Verwendungszweck enthält Rechnungsnummer (z.B. `RE.164622(55028)`)

**Reales Beispiel aus CamtDAT (2026-01-07):**
```
DBIT | 12.849,63 € | Creditor: H&K Kloeber Versicherungsmakler GmbH
IBAN: DE98508501500000752363
Verwendungszweck: RE.164622(55028) vom 15.12.2025
```

**Buchungssatz Phase 2 (schließt den KreditorOP aus Phase 1):**
```
Phase 1 war (bei Rechnungsfreigabe):
  Soll:  15900 Schwebende Eingangsrechnungen
  Haben: 70xxx Kreditorenkonto (Lieferant)
  BA:    050 EING-K

Phase 2 (beim Bankausgang — dieser Fall):
  Soll:  70xxx Kreditorenkonto (Lieferant)
  Haben: 18000 Bankkonto
  BA:    051 AUSG-K
```

**Matching-Logik (noch zu implementieren):**
1. DBIT-Transaktion eingehend
2. Suche KreditorOP mit passendem Betrag + Kreditor-IBAN (Creditor-IBAN aus CAMT = IBAN des Kreditors)
3. Sekundär: Rechnungsnummer aus Verwendungszweck gegen `Rechnung.rechnungsnummer`
4. Match gefunden → Phase-2-Buchung anlegen, KreditorOP schließen (`betrag_offen = 0`), `Rechnung.status = 'bezahlt'`
5. Kein Match → manuell zuordnen (wie heute)

**Hinweis Zahlungslauf:** Wenn Rechnungen über den internen Zahlungslauf-Workflow bezahlt
werden, ist die Phase-2-Buchung bereits vom Zahlungslauf angelegt. Der eingehende CAMT-Satz
muss dann nur noch gegen die vorhandene Buchung abgeglichen werden (Bankabstimmung),
nicht neu buchen.

---

### Fall 3 — DBIT/Sammelüberweisung: Zahlungslauf ❌ fehlt

**Erkennungsmerkmal:** `CdtDbtInd = DBIT`, `Btch`-Element vorhanden (`NbOfTxs > 1`),
Verwendungszweck enthält "Sammel-Ueberweisung" oder windata/SEPA-Batch-Referenz

**Reales Beispiel aus CamtDAT (2026-01-29):**
```
DBIT | 5.102,72 € | Btch NbOfTxs=4
Verwendungszweck: SEPA Sammel-Ueberweisung mit 4 Ueberweisungen MSG-ID: windata-4-510272-...
```

**Problem:** Der CAMT-Satz enthält nur den Gesamtbetrag, nicht die Einzelbeträge
der 4 Überweisungen. Die Cdtr-IBANs der einzelnen Empfänger fehlen.

**Buchungssatz:** Wie Fall 2 (Phase 2), jedoch für jeden Einzel-OP separat

**Matching-Logik (noch zu implementieren):**
- Option A: Abgleich gegen internen Zahlungslauf anhand `PmtInfId` (z.B. `windata S0459300`) —
  sofern Zahlungsläufe in ImmoCORE mit dieser ID gespeichert werden
- Option B: Manuelles Aufteilen des Sammelpostens in der UI
- Option C: Summenabgleich — wenn ∑ offene KreditorOPs = CAMT-Betrag → Auto-Match

---

### Fall 4 — CRDT/RCDT: Rücküberweisung / Gutschrift ❌ fehlt

**Erkennungsmerkmal:** `CdtDbtInd = CRDT`, `Fmly/Cd = RCDT`, Verwendungszweck enthält
"Rückzahlung", "Gutschrift" oder "Doppelzahlung"

**Reales Beispiel aus CamtDAT (2026-01-08):**
```
CRDT | 150,00 € | Debtor: MGV 1875 Falkenstein
IBAN: DE36501900006200210091
Verwendungszweck: Rückzahlung Doppelüberweisung vom 27.12.2025
```

**Zwei Unterfälle:**

**4a — Lieferant überweist zurück (Gutschrift/Rückbuchung):**
```
Soll:  18000 Bankkonto
Haben: 70xxx Kreditorenkonto (Lieferant)  oder  5xxxx Sachkonto
BA:    052 GS-K
```
KreditorOP ggf. wieder öffnen oder neuen Gegenbuchungs-OP anlegen.

**4b — Rückzahlung einer Doppelzahlung:**
```
Soll:  18000 Bankkonto
Haben: Ursprungs-Sachkonto (das bei der Doppelzahlung belastet wurde)
BA:    099 KOR  (Korrekturbuchung)
```

**Erkennung (noch zu implementieren):**
- `RCDT` im Fmly-Code → Flag als "mögliche Rücküberweisung"
- Freitextsuche in Verwendungszweck: "Rückzahlung", "Gutschrift", "Storno"
- Abgleich Betrag + IBAN gegen letzte DBIT-Buchungen auf dieses Konto

---

### Fall 5 — CRDT: Zinsgutschrift Bank ❌ fehlt

**Erkennungsmerkmal:** `CdtDbtInd = CRDT`, Dbtr-IBAN = interne Bank-IBAN,
Verwendungszweck enthält "Habenzinsen", "Zinsen für Guthaben", "ZINSEN"

**Buchungssatz:**
```
Soll:  18000 Bankkonto
Haben: 36xxx Zinserträge (Sachkonto)
BA:    042 SACH-E
```

**Reales Beispiel aus camt.053 DKB (Theresenstraße, 01.10.2025):**
```
CRDT | 84,07 € | Dbtr: "Unbekannt" | IBAN: DE02120300009000922261
RmtInf: "Habenzinsen ZINSEN"
EndToEndId: NONREF   ← DKB-spezifisch (nicht NOTPROVIDED!)
BkTxCd: fehlt komplett
```

**⚠️ Bankabhängige Unterschiede:**

| Bank | Zinsbuchung | BkTxCd | EndToEndId |
|---|---|---|---|
| DKB | Separate CRDT-Buchung "Habenzinsen ZINSEN" | **keiner** | `NONREF` |
| Raiffeisenbank | Im Sammel-ABSCHLUSS (`ACMT/OPCL/ACCC`) enthalten | `NMSC+805+00905` | — |

**Erkennung (bankbergreifend zuverlässig):**
Freitextsuche in `RmtInf/Ustrd`:
- enthält "Zins" + CRDT → Zinsgutschrift
- Debtor-IBAN ist eine interne Bank-IBAN (nicht in `Person.ibans`, BIC stimmt mit Svcr überein)

---

### Fall 5b — DBIT: Kapitalertragsteuer (Zinsabschlagsteuer) ❌ fehlt

**Erkennungsmerkmal:** `CdtDbtInd = DBIT`, Cdtr-IBAN = interne Finanzamt-IBAN der Bank,
Verwendungszweck: "Kapitalertragsteuer ABSCHLUSS"

**Buchungssatz:**
```
Soll:  Kapitalertragsteuer-Sachkonto (z.B. 49xxx oder 25% von Zinsen)
Haben: 18000 Bankkonto
BA:    040 SACH-A
```

**Reales Beispiel aus camt.053 DKB (Theresenstraße, 01.10.2025):**
```
DBIT | 21,02 € | Cdtr: "Unbekannt" | IBAN: DE73120300009000299504
RmtInf: "Kapitalertragsteuer ABSCHLUSS"
EndToEndId: NONREF
BkTxCd: fehlt komplett

DBIT |  1,15 € | Cdtr: "Unbekannt" | IBAN: DE51120300009000299512
RmtInf: "Solidaritätszuschlag ABSCHLUSS"
EndToEndId: NONREF
```

> **Hinweis Kirchensteuer:** Bei kirchensteuerpflichtigen Kontoinhabern
> erscheint ggf. ein weiterer DBIT-Eintrag "Kirchensteuer ABSCHLUSS".

**Erkennung:** Freitextsuche `RmtInf/Ustrd`:
- "Kapitalertragsteuer" → Sachkonto Kapitalertragsteuer
- "Solidaritätszuschlag" → Sachkonto Solidaritätszuschlag
- "Kirchensteuer" → Sachkonto Kirchensteuer

---

### Fall 5c — CRDT Betrag 0,00: Abrechnungsinformationssatz ⚠️ ignorieren

**Erkennungsmerkmal:** `CdtDbtInd = CRDT`, `Amt = 0,00`, kein `RltdPties`,
ausführlicher Abrechnungstext im Verwendungszweck

**Reales Beispiel aus camt.053 DKB (Theresenstraße, 01.10.2025):**
```
CRDT | 0,00 € | (kein Dbtr/Cdtr)
RmtInf: "Abrechnung 30.09.2025 ... Zinsen für Guthaben 84,07+ 1,2000 v.H. ..."
```

Dieser Eintrag ist ein **reiner Informationssatz** der DKB — er enthält die
Berechnung als Freitext, hat aber keinen Buchungswert. Der Parser muss
0-Betrag-Einträge **erkennen und überspringen** (keine Buchung anlegen).

---

### Fall 6 — DBIT: Bankgebühren / Kontoabschluss ❌ fehlt

**Erkennungsmerkmal:** `CdtDbtInd = DBIT`,
- Raiffeisenbank: `BkTxCd = ACMT/OPCL/ACCC`, proprietär `NMSC+805+00905`, AddtlNtryInf: "ABSCHLUSS"
- DKB: kein BkTxCd, Verwendungszweck "ABSCHLUSS PER ..."

**Reales Beispiel Raiffeisenbank (Lortzingstr., 30.04.2026):**
```
DBIT | 3,90 € | BkTxCd: ACMT/OPCL/ACCC | NMSC+805+00905
RmtInf: "ABSCHLUSS PER 30.04.2026"
AddtlNtryInf: "ABSCHLUSS"
```

**Buchungssatz:**
```
Soll:  Kontoführungsgebühren-Sachkonto (z.B. 49xxx)
Haben: 18000 Bankkonto
BA:    040 SACH-A
```

**Erkennung (bankbergreifend):**
- `BkTxCd Domn = ACMT` → Kontoabschluss/Gebühren
- **oder** Freitextsuche: "ABSCHLUSS", "Entgelt", "Kontoführung", "Gebühr"

**⚠️ Wichtig:** Bei der DKB (Theresenstraße) werden Zinsen und Steuern als
**separate Einzelbuchungen** geliefert — der Abschluss-Satz ist nur die
Zusammenfassung/Gebühr. Bei der Raiffeisenbank (Lortzingstr.) ist der
ABSCHLUSS-Satz eine einzelne Buchung, die Zinsen + Gebühren gebündelt enthält.

---

### Fall 7 — DBIT: Direktzahlung ohne Rechnung im System ⚠️ manuell

**Erkennungsmerkmal:** `CdtDbtInd = DBIT`, keine passende Rechnung/KreditorOP im System

Beispiele: Kleinbeträge (< 50 €), Versorgungsleistungen ohne vorherige Rechnung,
einmalige Handwerkerleistungen.

**Buchungssatz:**
```
Soll:  5xxxx Sachkonto (Bewirtschaftung)
Haben: 18000 Bankkonto
BA:    040 SACH-A
```

**Handling:** Manuell zuordnen — Sachkonto aus Kontenplan wählen.
Optional: Rückwirkend Eingangsrechnung erfassen und direkt auf `bezahlt` setzen.

---

### Fall 8 — DBIT: Erstattung an Eigentümer (JA-Guthaben) ⚠️ manuell

**Erkennungsmerkmal:** `CdtDbtInd = DBIT`, Creditor-IBAN in `Person.ibans`
(Eigentümer erhält Geld zurück), Verwendungszweck "Guthaben", "Jahresabrechnung"

**Buchungssatz:**
```
Soll:  Personenkonto (Eigentümer — Haben-Saldo auflösen)
Haben: 18000 Bankkonto
BA:    021 AUSG-P
```

**Handling:** Erkennung über Creditor-IBAN gegen `Person.ibans` (gleiche Tabelle wie Fall 1,
nur DBIT statt CRDT).

---

## 3. camt.054 — Einzelbenachrichtigung und Sammelauflösung

### 3.1 Was ist camt.054?

`camt.054` ("Bank to Customer Debit Credit Notification") ist **kein Kontoauszug**,
sondern eine **Einzelbenachrichtigung** der Bank für jede Bewegung — typischerweise
am Abend nach Buchung. Im Gegensatz zu camt.053 enthält er **keinen Eröffnungs-
oder Schlusssaldo**.

Er wird von der Bank für alle Transaktionstypen geliefert:
- Eingehende Überweisungen (Hausgeld-Zahlungen von Eigentümern)
- Ausgehende Überweisungen (Lieferantenzahlungen)
- SEPA-Lastschriften (Energieversorger, Stadtgebühren)
- **Sammeleinzüge** (Hausgeld-Lastschriften der WEG an Eigentümer)

### 3.2 Warum ist camt.054 für die Rückkoppelung entscheidend?

Wenn die WEG Hausgeld per SEPA-Lastschrift **gebündelt einzieht** (Sammeleinzug),
liefert die Bank im camt.053 nur eine Summenposition:

```
CRDT | 2.404,76 € | "Hausgeld 05/2026" | 7 Einzeltransaktionen → unsichtbar
```

Der **camt.054** ist das einzige Instrument, das die einzelnen Zahler
(Eigentümer-IBAN, -Name, Betrag je Einheit) auflöst. Nur so kann das System
automatisch zuordnen, **wer** gezahlt hat → **welchem Eigentümer** → **welcher
offene Hausgeld-OP** wird getilgt.

Ohne camt.054-Vollauflösung ist keine automatische Rückkoppelung möglich.

### 3.3 Vollauflösung vs. Batchsummary — Abhängigkeit von Bankeinstellung

Der ISO-20022-Standard erlaubt innerhalb eines `<Ntry>` mehrere `<TxDtls>`,
einen pro Einzelzahler:

**Vollauflösung (Standard-konform — was wir brauchen):**
```xml
<NtryDtls>
  <Btch><NbOfTxs>7</NbOfTxs><TtlAmt>2404.76</TtlAmt></Btch>
  <TxDtls>  <!-- Zahler 1 -->
    <Refs><EndToEndId>...</EndToEndId><MndtId>...</MndtId></Refs>
    <Amt>380.00</Amt>
    <RltdPties><Dbtr><Nm>Max Mustermann</Nm></Dbtr><DbtrAcct><IBAN>DE12...</IBAN></DbtrAcct></RltdPties>
  </TxDtls>
  <TxDtls>  <!-- Zahler 2 ... bis 7 --></TxDtls>
</NtryDtls>
```

**Batchsummary (was Raiffeisenbank aktuell liefert — unzureichend):**
```xml
<NtryDtls>
  <Btch><NbOfTxs>7</NbOfTxs><TtlAmt>2404.76</TtlAmt></Btch>
  <TxDtls>  <!-- NUR EINE TxDtls für ALLE 7 — kein Debtor, kein Einzelbetrag -->
    <RmtInf><Ustrd>TAN:SECUREGO PLUS</Ustrd></RmtInf>
  </TxDtls>
</NtryDtls>
```

### 3.4 ⚠️ Handlungsbedarf Raiffeisenbank

**Aktuell liefert die Raiffeisenbank camt.054 nur im Batchsummary-Modus.**
Das bedeutet: Die 7 Einzelzahler des Sammeleinzugs "Hausgeld 05/2026" sind
**nicht erkennbar**. Die automatische Hausgeld-Zuordnung (Nebenbuch-Tilgung)
ist damit für Sammeleinzüge **nicht möglich**.

**Maßnahme:**
> Bei der **Raiffeisenbank** die Einstellung **"camt.054 mit vollständiger
> Transaktionsauflösung"** (auch: "Detailformat") aktivieren lassen.
> Das ist eine Konfigurationsoption im Online-Banking-Business-Bereich —
> kein technisches Problem, sondern eine Kontoeinstellung.

Bis diese Einstellung aktiviert ist, müssen Sammeleinzüge manuell aufgeteilt
werden.

### 3.5 EndToEndId-Situation in den Testdaten

Aus der Analyse der Testdateien (12 × camt.054, Zeitraum 13.04.–26.05.2026,
Konto DE50550606110000258148, WEG Lortzingstr. 14):

| EndToEndId | Häufigkeit | Typ |
|---|---|---|
| `NOTPROVIDED` | 18 von 22 Tx | Manuelle Überweisungen |
| `CCB.120.UE.POS00215884` | 1 Tx | Commerzbank-Überweisung |
| `1KVT0000000008372202` | 1 Tx | SEPA-Lastschrift goldgas |
| `585451` | 1 Tx | SEPA-Lastschrift Energiehaus |
| `26-0165-90` | 1 Tx | SEPA-Lastschrift Stadt Mörfelden |

**Konsequenz:** `NOTPROVIDED` muss vom Parser als `null` behandelt werden —
nicht als Referenzwert speichern, Stufe-1a-Matching darf auf `NOTPROVIDED`
**nicht** ansprechen.

### 3.6 Transaktionstypen in camt.054 (aus Testdaten)

| BkTxCd Fmly | SubFmly | Bedeutung | Richtung |
|---|---|---|---|
| `ICDT` | `ESCT` | Ausgehende Überweisung (WEG zahlt) | DBIT |
| `RCDT` | `ESCT` | Eingehende Überweisung (Eigentümer zahlt) | CRDT |
| `RRCT` | `ESCT` | Rücküberweisung / Gutschrift (Eingang) | CRDT |
| `RDDT` | `ESDD` | SEPA-Lastschrift Belastung (Lieferant zieht ein) | DBIT |
| `IDDT` | `ESDD` | SEPA-Sammeleinzug (WEG zieht Hausgeld ein) | CRDT |
| `ACMT` | `OPCL` | Kontoabschluss / Bankgebühren | DBIT |

---

## 4. Implementierungsstand

| Fall | Beschreibung | Status |
|------|--------------|--------|
| 1 | CRDT Hausgeld-Eingang Eigentümer | ✅ implementiert |
| 2 | DBIT Einzelüberweisung → KreditorOP schließen | ❌ fehlt |
| 3 | DBIT Sammelüberweisung (Zahlungslauf) | ❌ fehlt |
| 4 | CRDT Rücküberweisung / Gutschrift | ❌ fehlt |
| 5 | CRDT Zinsgutschrift Bank | ❌ fehlt |
| 5b | DBIT Kapitalertragsteuer (Zinsabschlagsteuer) | ❌ fehlt |
| 5c | CRDT Betrag 0,00 — Informationssatz | ❌ fehlt (muss ignoriert werden) |
| 6 | DBIT Bankgebühren / Kontoabschluss | ❌ fehlt |
| 7 | DBIT Direktzahlung ohne Rechnung | ⚠️ manuell möglich |
| 8 | DBIT Erstattung an Eigentümer | ⚠️ manuell möglich |

**Parser-Sonderfälle (bankspezifisch):**

| Sonderfall | DKB (Theresenstraße) | Raiffeisenbank (Lortzingstr.) |
|---|---|---|
| EndToEndId ohne Wert | `NONREF` | `NOTPROVIDED` |
| BkTxCd bei Zinsen | **fehlt komplett** | `ACMT/OPCL/ACCC` |
| Zinsen separate Buchung? | ✅ ja (CRDT 84,07 €) | ❌ nein (im Abschluss gebündelt) |
| Kapitalertragsteuer | separate DBIT-Buchung | im Abschluss gebündelt |
| 0-Betrag Infosatz | ✅ vorhanden (ignorieren) | ❌ nicht vorhanden |

---

## 4. Priorisierung für Weiterentwicklung

**Priorität 1 — Fall 2: KreditorOP-Matching (DBIT Einzelüberweisung)**

Das ist der wichtigste fehlende Baustein. Jede bezahlte Lieferantenrechnung erzeugt
einen DBIT-Satz im CAMT. Ohne dieses Matching muss jede Zahlung manuell abgeglichen
werden. Matching-Schlüssel in absteigender Verlässlichkeit:

1. Betrag (exakt) + Kreditor-IBAN (CdtrAcct aus CAMT = `Kreditor.iban`)
2. Betrag + Rechnungsnummer aus Verwendungszweck (Regex: `RE[.\-]?\d+`)
3. Nur Betrag + IBAN (ohne Rechnungsnummern-Match)

**Priorität 2 — Fall 8: Eigentümer-Erstattungen (DBIT gegen Person.ibans)**

Gleiche Erkennungslogik wie Fall 1, nur Richtung umgekehrt. Geringe Implementierungsarbeit.

**Priorität 3 — Fall 4: Rücküberweisungen**

Selten, aber relevant für korrekte Buchführung. Freitextbasierte Erkennung ausreichend
für einen ersten Schritt (manuelle Bestätigung).

**Priorität 4 — Fälle 5 + 6: Bank-Eigenposten (Zinsen, Gebühren)**

Volumen gering, aber buchhalterisch notwendig für korrekte BWA/JA.

---

## 5. Technische Hinweise für die Implementierung

### KreditorOP-Matching (Fall 2)

```python
# Pseudocode Matching-Logik
def matche_kreditor_op(umsatz: Kontoumsatz) -> KreditorOP | None:
    if umsatz.betrag >= 0:          # Nur DBIT (negativ gespeichert als positiv mit Vorzeichen?)
        return None

    betrag = abs(umsatz.betrag)
    cdtr_iban = umsatz.auftraggeber_iban  # Bei DBIT: auftraggeber_iban = Cdtr-IBAN

    # Stufe 1: Betrag + IBAN
    ops = KreditorOP.objects.filter(
        betrag_offen=betrag,
        kreditor__iban=cdtr_iban,
        status='offen',
    )
    if ops.count() == 1:
        return ops.first()

    # Stufe 2: Rechnungsnummer aus Verwendungszweck
    match = re.search(r'RE[.\-]?\s*(\d+)', umsatz.verwendungszweck, re.IGNORECASE)
    if match:
        re_nr = match.group(1)
        ops = KreditorOP.objects.filter(
            rechnung__rechnungsnummer__icontains=re_nr,
            status='offen',
        )
        if ops.count() == 1:
            return ops.first()

    return None  # → manuelle Zuordnung
```

### Felder im Kontoumsatz-Modell

Bei DBIT-Transaktionen gilt aktuell:
- `auftraggeber_name` = Creditor-Name (Lieferant)
- `auftraggeber_iban` = Creditor-IBAN (Lieferant)
- `empfaenger_iban` = eigene WEG-IBAN (aus Stmt/Acct)

Das ist **umgekehrt zur CRDT-Logik** und sollte beim Matching berücksichtigt werden.
Ggf. eigene Felder `cdtr_iban` / `dbtr_iban` einführen statt das Feld
`auftraggeber_iban` doppelt zu belegen.

### Sammelüberweisung (Fall 3)

`Btch/NbOfTxs > 1` → einzelne TxDtls können Creditor-IBANs enthalten oder nicht
(bankabhängig). Wenn die Bank nur den Gesamtbetrag liefert, ist automatisches Matching
nicht möglich — UI für manuelle Aufteilung nötig.

---

## 6. Abgrenzung: CAMT vs. interner Zahlungslauf

Der interne Zahlungslauf-Workflow in ImmoCORE erzeugt bereits Phase-2-Buchungen
(051 AUSG-K) und setzt `Rechnung.status = 'bezahlt'`. In diesem Fall:

- CAMT-Satz eingehend → Buchung bereits vorhanden
- Aufgabe: **Bankabstimmung** (Abgleich Buchung ↔ CAMT-Satz), nicht Neubuchung
- Technisch: `Kontoumsatz.buchung` auf vorhandene Phase-2-Buchung setzen

Wenn Rechnungen **außerhalb von ImmoCORE** per Banküberweisung bezahlt werden:
- Kein Phase-2-Satz vorhanden
- CAMT-Matching muss Phase-2-Buchung erst anlegen (wie Fall 2 oben)
