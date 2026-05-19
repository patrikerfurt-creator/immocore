# Claude Code – Anleitung: Hausgeld-Nebenbuch mit OP-Verwaltung (IMMOCORE)

**Version:** 1.1
**Status:** Implementierungsreif
**Bezug:** Ergänzt / ersetzt die Sollstellungs-Logik der Ausgangsspezifikation
v1.1 (Kap. 4.7/4.8) und referenziert Musterkontenrahmen WEG v2 sowie
OP-Buchung v1.1 (Aufwandsseite).

## Changelog

### v1.1 (gegenüber v1.0)

- **Abrechnungsguthaben (negative `.950`-Sollstellung) wird NICHT mehr
  automatisch mit nächster Hausgeld-Sollstellung verrechnet.** Stattdessen
  wird das Guthaben über einen aktiven **Auszahlungslauf** an den
  Eigentümer überwiesen. Damit:
  - Entfällt: Konfigurationsfeld `abrechnungsguthaben_verrechnen` am
    `EigentumsVerhaeltnis`
  - Entfällt: Funktion `beruecksichtige_offene_guthaben()` im
    Sollstellungslauf-Service
  - Entfällt: Status `offen_guthaben` in der `status`-Property
  - Neu: Kap. 10.5 Auszahlungslauf-Workflow (ersetzt vormalige
    automatische Verrechnungslogik)
  - Neu: Service `auszahlungs_service.py` (Kap. 12.1 + 15 Schritt 10b)
  - Neu: Buchungslogik bei Guthaben-Auszahlung (Kap. 7.3)
  - Neu: EndToEndId-Suffix `-AUSZ` für ausgehende
    Guthaben-Überweisungen (Kap. 9.3)
  - Anpassung: Smoke-Test Punkt 8 (Kap. 16) auf Auszahlung statt
    Verrechnung umgestellt

### v1.0

- Erstfassung der Hausgeld-Nebenbuch-Spezifikation

---

## 1. Ziel

Forderungen der WEG gegen Eigentümer (laufendes Hausgeld, Sonderumlagen,
Abrechnungsergebnisse) werden in einem **eigenen Nebenbuch** geführt — nicht
mehr über Sachkonten-Buchungen auf einem Personenkonto-Sachkonto.

Bei einer Sollstellung entstehen **keine** Sachkontenbuchungen. Es entsteht
ein Offener Posten (OP) im Nebenbuch. Erst der **tatsächliche Zahlungseingang**
löst die Erlösbuchung auf die Sachkonten `41xxx` aus — strikt
zahlungswirksam.

Jede Sollstellung erhält eine eindeutige **OPOS-Nummer**, die als
`EndToEndId` in SEPA-Lastschriften (`pain.008`) verwendet und in der
camt.053/054-Verarbeitung deterministisch zurückgematcht wird.

### 1.1 Asymmetrie WEG-Hausgeldabrechnung

| Seite | Prinzip | Konsequenz im System |
|---|---|---|
| **Einnahmenseite Hausgeld** | **Soll-Prinzip** — Eigentümer schuldet die beschlossenen Vorauszahlungen unabhängig von der tatsächlichen Zahlung | Forderung lebt im Nebenbuch; HGA-Spalte "VZ Soll" zieht aus Nebenbuch |
| **Aufwandsseite Bewirtschaftung** | **Kassenprinzip § 28 WEG** — verteilt wird nur, was tatsächlich abgeflossen ist | OP-Buchung mit `15900` (siehe OP-Buchung v1.1) |

Beide Prinzipien greifen über das Sachkonten-Hauptbuch hinaus auf
Nebenbücher zu (Forderungs-Nebenbuch hier, Kreditoren-OP über `15900`
dort). Das Hauptbuch (4xxxx/5xxxx) bleibt durchgängig zahlungswirksam.

### 1.2 Greenfield-Annahme

IMMOCORE ist noch nicht im Produktivbetrieb. Es existieren keine
produktiv gebuchten Sollstellungen, die migriert werden müssen. Die in
der Ausgangsspezifikation v1.1 (Kap. 4.7/4.8) beschriebenen Modelle
`HausgeldHistorie`, `Personenkonto` und das post_save-Signal aus
`EigentumsVerhaeltnis` werden **ersetzt** durch das hier beschriebene
Nebenbuch. Siehe Kap. 13 (Migrationspfad / Greenfield-Cleanup).

---

## 2. Bezug zum Musterkontenrahmen WEG

Diese Spezifikation **berührt den Kontenrahmen nicht** — es werden keine
neuen Sachkonten eingeführt. Die bestehenden Erlöskonten `41900`, `41911`,
`41912`, …, `41940`, `41950` werden weiterverwendet — aber **nur bei
Zahlungseingang**, nicht bei Sollstellung.

### 2.1 Verwendete Kontenkategorien (alle bestehend)

| Bereich | Verwendung in dieser Spec |
|---|---|
| `18xxx` Bankkonten | Eingang Hausgeldzahlung → Soll |
| `14600` Bankübertrag / Geldtransit | Sammeltransfer Bewirtschaftung → Rücklage (Kap. 7.4) |
| `41900` Erlöse Hausgeld VZ | Haben bei Zahlungseingang Hausgeld-Split |
| `41911`–`4193N` Erlöse Rücklage I–N | Haben bei Zahlungseingang Rücklagen-Split |
| `41940` Erlöse Sonderumlage | Haben bei Zahlungseingang Sonderumlage |
| `41950` Erlöse Abrechnung VJ | Haben bei Zahlungseingang Abrechnungsergebnis |

### 2.2 Entfallende Sachkontensicht

Das Sachkonto **„Personenkonto"** mit Suffix `.900`/`.911`/… wird **nicht
mehr als Sachkonto** geführt. Es existiert kein eigenes Konto je
Eigentümer im Sachkontenrahmen. Die Forderungssicht je Eigentümer wird
ausschließlich aus dem Nebenbuch beantwortet.

**Folge für die Buchungssätze:** Bei Zahlungseingang wird **direkt**
gegen `41xxx` gebucht — der Umweg über ein `XXXXXX-NNNN.900`-Personenkonto
entfällt vollständig.

---

## 3. Sollstellungstypen

Drei Sollstellungstypen werden im selben Eltern-Modell
`HausgeldSollstellung` mit Diskriminator-Feld geführt:

| Typ | Auslöser | BA-Struktur | Lastschrift-Lauf |
|---|---|---|---|
| `hausgeld` | Monatlicher Massensollstellungslauf | **mehrere BAs** als Splits: `.900` + alle aktiven Rücklagen (`.911`/`.912`/…) | gemeinsam, gruppiert nach Zielbankkonto |
| `sonderumlage` | Beschluss-Wizard (manuell, pro Eigentümerbeschluss) | **genau eine BA** (`.940`), kein Split | separater Lauf je Sonderumlage |
| `abrechnungsergebnis` | Jahresabrechnungs-Wizard (nach Genehmigung) | **genau eine BA** (`.950`), kein Split | separater Lauf je Wirtschaftsjahr |

### 3.1 Splits — nur bei `hausgeld`

Splits (`SollstellungSplit`) existieren **ausschließlich** bei
Sollstellungen mit `sollstellungs_typ = 'hausgeld'`. Sonderumlage und
Abrechnungsergebnis tragen die BA direkt am Eltern-Datensatz.

Begründung: Bei Sonderumlage/Abrechnungsergebnis gibt es per Definition
nur eine BA. Splits wären leere Hülsen. Stattdessen wird die BA am
Eltern-Datensatz festgehalten (`ba`-FK, nullable, gefüllt nur bei
diesen beiden Typen).

### 3.2 Eigenschaften der drei Typen im Vergleich

| Eigenschaft | `hausgeld` | `sonderumlage` | `abrechnungsergebnis` |
|---|---|---|---|
| Periodizität | monatlich | einmalig pro Beschluss | einmalig pro Wirtschaftsjahr |
| Splits | ja | nein | nein |
| Eltern-`ba` befüllt | nein (NULL) | ja (`.940`) | ja (`.950`) |
| Zielbankkonto | je Split (Bewirtschaftung oder Rücklage) | aus Sonderumlage-Konfiguration | aus Objekt-Konfiguration (i.d.R. Bewirtschaftung) |
| Tilgungspriorität intern | relevant (Rücklage vor Hausgeld) | irrelevant | irrelevant |
| Automatische Tilgung bei IBAN-Match | nach § 366/367 BGB | nur bei exaktem Einzelmatch | nur bei exaktem Einzelmatch |
| Mahnstufe | eigenständig | eigenständig | eigenständig |

### 3.3 Negativsalden bei Abrechnungsergebnis (Guthaben)

Wenn die Jahresabrechnung für einen Eigentümer ein **Guthaben** ergibt,
wird eine Sollstellung mit **negativem `soll_betrag`** erzeugt. Damit
ist die Sollstellung eine Verbindlichkeit der WEG gegenüber dem
Eigentümer.

**Behandlung:** Guthaben werden **aktiv vom Verwalter ausgezahlt** —
sie werden **nicht** automatisch mit künftigen Hausgeld-Sollstellungen
verrechnet. Begründung: Eine automatische Verrechnung würde den
Eigentümer überraschen (z.B. niedriger Lastschrifteinzug ohne
Vorankündigung) und ist operativ schwerer zu kommunizieren als eine
saubere Überweisung mit Verwendungszweck "Guthaben aus Abrechnung
2025".

Nach Genehmigung der Jahresabrechnung erzeugt das System einen
**Auszahlungslauf** über alle EVs mit negativer `.950`-Sollstellung
(Kap. 10.5). Der Verwalter gibt diesen Lauf frei, eine SEPA-Sammel-
überweisung (pain.001) wird generiert. Nach Abgang vom Bewirtschaftungs-
konto erfolgt die Buchung gemäß Kap. 7.3 und das Nebenbuch wird
entsprechend aktualisiert (`ist_betrag` der Guthabensollstellung wird
auf `soll_betrag` gesetzt → Status `ausgeglichen`).

---

## 4. Datenmodell

### 4.1 `HausgeldSollstellung` (Eltern-Tabelle, alle Typen)

| Feld | Typ | Anmerkung |
|---|---|---|
| `id` | UUID (PK) | |
| `objekt` | FK → Objekt | |
| `eigentumsverhaeltnis` | FK → EigentumsVerhaeltnis | identifiziert Eigentümer + Einheit + Zeitraum |
| `sollstellungs_typ` | Enum: `hausgeld` / `sonderumlage` / `abrechnungsergebnis` | Diskriminator |
| `ba` | FK → Buchungsart (nullable) | NULL bei `hausgeld`; befüllt bei den anderen beiden |
| `periode` | DateField | bei `hausgeld`: Monatserster (z.B. `2026-03-01`); bei `sonderumlage`: Beschlussdatum; bei `abrechnungsergebnis`: 31.12. des Wirtschaftsjahrs |
| `faellig_am` | DateField | aus BA bzw. Beschluss; Default = `periode` (Hausgeld) |
| `opos_nr` | CharField(15), unique, indexed | Format siehe Kap. 5 |
| `soll_betrag` | DecimalField(12,2) | bei `hausgeld`: Summe über alle Splits; bei `sonderumlage`/`abrechnungsergebnis`: direkt; **darf negativ sein** (Guthaben aus Abrechnung) |
| `ist_betrag` | DecimalField(12,2), default 0 | aus Zahlungszuordnungen kumuliert |
| `sollstellungslauf` | FK → Sollstellungslauf | erlaubt Massen-Storno eines kompletten Laufs |
| `status` | Property (nicht persistiert) | siehe Kap. 4.4 |
| `storniert_am` | DateTimeField, nullable | siehe Kap. 8 |
| `storniert_von` | FK → User, nullable | |
| `storniert_grund` | TextField, nullable | |
| `erstellt_am` | DateTimeField, auto | |
| `erstellt_von` | FK → User | |

**Constraints (DB + Service):**

- `UniqueConstraint(fields=['eigentumsverhaeltnis', 'periode', 'sollstellungs_typ', 'ba'])`
  → bei `hausgeld` (ba=NULL): genau eine Sollstellung pro EV pro Periode;
  → bei `sonderumlage`/`abrechnungsergebnis`: genau eine pro EV pro Periode pro BA
- `CheckConstraint`: `sollstellungs_typ='hausgeld' AND ba IS NULL`
  ODER `sollstellungs_typ IN ('sonderumlage','abrechnungsergebnis') AND ba IS NOT NULL`
- `Index(fields=['objekt', 'status_cached'])` für Reporting (siehe 4.4)
- `Index(fields=['opos_nr'])` (heißer Pfad für camt-Match)

### 4.2 `SollstellungSplit` (Kind-Tabelle, **nur** für `hausgeld`)

| Feld | Typ | Anmerkung |
|---|---|---|
| `id` | UUID (PK) | |
| `sollstellung` | FK → HausgeldSollstellung | nur Eltern mit `sollstellungs_typ='hausgeld'` zulässig |
| `ba` | FK → Buchungsart | eine der BAs aus Kap. 6.3 |
| `betrag` | DecimalField(12,2) | |
| `bankkonto_ziel` | FK → Bankkonto | wirtschaftliches Ziel des Splits (siehe 6.3) |
| `erloeskonto` | FK → Konto | bei Zahlung im Haben anzusprechendes Erlöskonto (siehe 6.3) |
| `ist_betrag_split` | DecimalField(12,2), default 0 | wie viel auf diesen Split bereits getilgt wurde (siehe Kap. 7.2) |

**Constraints:**

- `UniqueConstraint(fields=['sollstellung', 'ba'])`
- Validierung im Service (nicht DB-CHECK, da Aggregation):
  `SUM(splits.betrag) == sollstellung.soll_betrag`
- Validierung im Service: `sollstellung.sollstellungs_typ == 'hausgeld'`

### 4.3 `SollstellungZahlung` (Verknüpfung Sollstellung ↔ Buchung)

| Feld | Typ | Anmerkung |
|---|---|---|
| `id` | UUID (PK) | |
| `sollstellung` | FK → HausgeldSollstellung | |
| `split` | FK → SollstellungSplit, nullable | nur bei `hausgeld`-Tilgung mit Split-Zuordnung befüllt |
| `buchung` | FK → Buchung | die Bankbuchung, die diese Tilgung auslöste |
| `betrag` | DecimalField(12,2) | wie viel dieser Buchung dieser Sollstellung/diesem Split zugeordnet wurde |
| `tilgungsstufe` | Enum: `kosten` / `zinsen` / `hauptforderung` | nach § 367 BGB (für Mahnwesen-Hook) |
| `erstellt_am` | DateTimeField, auto | |
| `erstellt_von` | FK → User | bei automatischer Tilgung: System-User |

**Hinweis:** Eine Bankbuchung kann mehrere `SollstellungZahlung`-Einträge
erzeugen (eine 720€-Zahlung tilgt zwei 360€-Sollstellungen). Eine
Sollstellung kann mehrere `SollstellungZahlung`-Einträge erhalten
(Teilzahlungen).

### 4.4 Status-Berechnung (Property)

`HausgeldSollstellung.status` ist **abgeleitet** aus `soll_betrag` und
`ist_betrag` — nicht persistiert, daher nie inkonsistent. Negativ-
Sollstellungen (Guthaben) durchlaufen denselben Status-Pfad wie
Forderungen — `ausgeglichen` bedeutet bei Guthaben: ausgezahlt.

```python
@property
def status(self) -> str:
    if self.storniert_am is not None:
        return "storniert"
    soll = self.soll_betrag
    ist  = self.ist_betrag
    # Vorzeichen-symmetrische Logik:
    # - Forderung (soll > 0):    ist wächst von 0 → soll
    # - Verbindlichkeit (soll < 0): ist wächst von 0 → soll (also Richtung negativ)
    if ist == 0:
        return "offen"
    if ist == soll:
        return "ausgeglichen"
    if abs(ist) < abs(soll) and (ist > 0) == (soll > 0):
        return "teilbezahlt"
    # Vorzeichen abweichend oder Betrag über Soll hinaus
    return "ueberzahlt"
```

Für Reporting-Queries existiert zusätzlich ein **denormalisiertes**
Feld `status_cached`, das per Service nach jeder Verrechnung
aktualisiert wird (für indexierbare Filter).

### 4.5 `Sollstellungslauf` (Header eines Massenlaufs)

| Feld | Typ | Anmerkung |
|---|---|---|
| `id` | UUID (PK) | |
| `objekt` | FK → Objekt | |
| `typ` | Enum: `hausgeld_monat` / `sonderumlage` / `abrechnungsergebnis_jahr` | |
| `periode` | DateField | bei Hausgeld: Monatserster; bei Sonderumlage: Beschlussdatum; bei Abrechnung: 31.12. WJ |
| `status` | Enum: `vorschau` / `commited` / `storniert` | |
| `anzahl_sollstellungen` | IntegerField | nach commit gesetzt |
| `summe` | DecimalField(14,2) | nach commit gesetzt |
| `erstellt_am`, `erstellt_von` | | |
| `commited_am`, `commited_von` | | nach Commit |
| `storniert_am`, `storniert_von`, `storniert_grund` | | nach Storno (Kap. 8.3) |

### 4.6 `OposSequenz` (Vergabe der OPOS-Nr. pro Objekt)

| Feld | Typ | Anmerkung |
|---|---|---|
| `objekt` | OneToOne → Objekt (PK) | |
| `naechste_lfd_nr` | BigIntegerField | beginnt bei 1 |

Vergabe via `SELECT … FOR UPDATE` im selben atomaren Transaktionsblock
wie die Sollstellungs-Erzeugung — siehe Kap. 5.3.

---

## 5. OPOS-Nummer

### 5.1 Format

```
Format:    {OBJEKT_NR}{LFD_NR}{PRUEFZIFFER}
Länge:     6 + 8 + 1 = 15 Zeichen, rein numerisch
Beispiel:  100001000458297

Aufbau:
  100001    = Objekt-Nr. (6-stellig, links mit Nullen gepolstert)
  00045829  = lfd. Nr. innerhalb des Objekts (8-stellig, links mit Nullen)
  7         = Luhn-Prüfziffer über die ersten 14 Stellen
```

### 5.2 Eigenschaften

- **15 Zeichen, rein numerisch** — weit unter SEPA-Grenze (35), keine Sonderzeichen, keine Banken-Kompatibilitätsprobleme
- **Mandantenweit eindeutig** durch Objekt-Präfix
- **Routing-erkennbar:** die ersten 6 Stellen identifizieren das Objekt direkt im camt-Parser, ohne DB-Lookup
- **Selbst-plausibilisierbar** über Luhn-Prüfziffer
- **Niemals wiederverwendet** — auch bei Stornierung bleibt die Nr. an der stornierten Sollstellung; das nächste Soll bekommt die nächste lfd. Nr.

### 5.3 Vergabe (race-safe)

```python
# apps/buchhaltung/services/opos_nr_service.py
from django.db import transaction

@transaction.atomic
def naechste_opos_nr(objekt) -> str:
    seq = OposSequenz.objects.select_for_update().get(objekt=objekt)
    lfd = seq.naechste_lfd_nr
    seq.naechste_lfd_nr = lfd + 1
    seq.save(update_fields=["naechste_lfd_nr"])

    objekt_nr = str(objekt.objekt_nr).zfill(6)   # immer 6-stellig
    lfd_str   = str(lfd).zfill(8)                 # immer 8-stellig
    basis     = objekt_nr + lfd_str               # 14 Ziffern
    pruefz    = luhn_pruefziffer(basis)
    return basis + str(pruefz)


def luhn_pruefziffer(basis: str) -> int:
    """Standard-Luhn-Algorithmus (Mod-10) über alle Ziffern."""
    summe = 0
    for i, ziffer in enumerate(reversed(basis)):
        n = int(ziffer)
        if i % 2 == 0:
            n *= 2
            if n > 9:
                n -= 9
        summe += n
    return (10 - summe % 10) % 10


def validiere_opos_nr(opos_nr: str) -> bool:
    if len(opos_nr) != 15 or not opos_nr.isdigit():
        return False
    return luhn_pruefziffer(opos_nr[:14]) == int(opos_nr[14])
```

### 5.4 Verwendung

| Ort | Wie |
|---|---|
| SEPA-Lastschrift pain.008 | `<EndToEndId>` (Kap. 9) |
| camt.054 R-Transactions | Lookup über `EndToEndId` → eindeutige Sollstellung (Kap. 11) |
| camt.053 Zahlungseingang | **kein** OPOS-Lookup im Verwendungszweck (bewusst weggelassen, da Verwendungszweck eigentümerlesbar bleibt) |
| Frontoffice-Suche | Suchfeld in Sollstellungs-Übersicht |
| Mahnschreiben | Aktenzeichen / interne Vorgangsnummer (sichtbar für Eigentümer ist optional) |

### 5.5 Ausschluss

Die OPOS-Nr. erscheint **nicht** im Verwendungszweck der Lastschrift.
Der Verwendungszweck bleibt menschenlesbar (Kap. 9.2).

---

## 6. Buchungsarten (BA) und Konfiguration

### 6.1 BA-Modell — Erweiterung

Bestehendes `Buchungsart`-Modell wird um folgende Felder erweitert:

| Feld | Typ | Anmerkung |
|---|---|---|
| `tilgungs_prioritaet` | IntegerField, nullable | nur für BAs gefüllt, die als Hausgeld-Split auftreten können; kleinere Zahl = höhere Priorität (= früher tilgen) |
| `erloeskonto_default` | FK → Konto (Konten-Vorlage), nullable | wird beim Anlegen einer Sollstellung herangezogen |
| `bankkonto_typ` | Enum: `bewirtschaftung` / `ruecklage_nach_index` / `frei` | Routing-Hinweis für Lastschriftlauf und Splits |

### 6.2 BA-Konfiguration (Standardwerte)

| BA | Bezeichnung | `tilgungs_prioritaet` | `erloeskonto_default` | `bankkonto_typ` |
|---|---|---|---|---|
| `.911` | 1. Rücklage | 20 | 41911 | `ruecklage_nach_index` (Rücklage 1) |
| `.912` | 2. Rücklage | 21 | 41912 | `ruecklage_nach_index` (Rücklage 2) |
| `.91N` | weitere Rücklagen | 22 ff. | 4191N | `ruecklage_nach_index` (N) |
| `.900` | Hausgeld lfd. | 90 | 41900 | `bewirtschaftung` |
| `.940` | Sonderumlage | (NULL) | 41940 | aus Sonderumlage-Konfiguration (frei wählbar) |
| `.950` | Abrechnungsergebnis VJ | (NULL) | 41950 | `bewirtschaftung` |

### 6.3 Tilgungspriorität — wo sie wirkt

Die Tilgungspriorität wirkt **ausschließlich auf Splits innerhalb einer
einzelnen `hausgeld`-Sollstellung**. Bei `sonderumlage`/`abrechnungs-
ergebnis` ist sie irrelevant, weil es keine Splits gibt.

Zwischen verschiedenen Sollstellungen gilt **§ 366 Abs. 2 BGB**: älteste
Sollstellung zuerst.

---

## 7. Buchungslogik

### 7.1 Sollstellung anlegen

**Sollstellung erzeugt KEINE Sachkontenbuchung.** Es entsteht nur ein
Datensatz im Nebenbuch:

```
HausgeldSollstellung erstellen
  + N × SollstellungSplit (nur bei sollstellungs_typ='hausgeld')
  + OPOS-Nr. vergeben
```

Kein Buchung/Buchungssatz wird angelegt. Das Hauptbuch bleibt
unangetastet.

### 7.2 Zahlungseingang — Hausgeld-Sollstellung

**Voll-Tilgung** einer Hausgeld-Sollstellung Müller, 360 € (Splits: `.900`=250, `.911`=80, `.912`=30):

```
Soll  18000  Bank 1 Bewirtschaftung                  360,00
Haben 41911  Erlöse Rücklage I                        80,00
Haben 41912  Erlöse Rücklage II                       30,00
Haben 41900  Erlöse Hausgeld VZ                      250,00
```

→ Nebenbuch: `ist_betrag = 360`, alle Splits `ist_betrag_split` voll.

**Teil-Tilgung** derselben Sollstellung mit Eingang 200 €
(Tilgungspriorität: Rücklage zuerst):

```
Soll  18000  Bank 1 Bewirtschaftung                  200,00
Haben 41911  Erlöse Rücklage I                        80,00     (voll)
Haben 41912  Erlöse Rücklage II                       30,00     (voll)
Haben 41900  Erlöse Hausgeld VZ                       90,00     (Rest)
```

→ Nebenbuch: `ist_betrag = 200`. `.911`- und `.912`-Splits voll,
`.900`-Split mit 160€ Restbetrag offen.

### 7.3 Zahlungseingang — Sonderumlage / Abrechnungsergebnis

Sonderumlage 5.000 €, Voll-Tilgung:

```
Soll  18xxx  (Zielbankkonto aus Sonderumlage-Konfig)  5.000,00
Haben 41940  Erlöse Sonderumlage                      5.000,00
```

Abrechnungsergebnis 480 € (Nachzahlung):

```
Soll  18000  Bank 1 Bewirtschaftung                     480,00
Haben 41950  Erlöse Abrechnung VJ                       480,00
```

**Abrechnungsergebnis −300 € (Guthaben → Auszahlung an Eigentümer):**

Beim Abgang vom Bewirtschaftungskonto im Auszahlungslauf (siehe
Kap. 10.5) wird Soll/Haben gegenüber dem Nachzahlungsfall umgekehrt
gebucht:

```
Soll  41950  Erlöse Abrechnung VJ                     300,00
Haben 18000  Bank 1 Bewirtschaftung                   300,00
```

Buchungstechnisch sauber: Erlöskonten dürfen bei Rückerstattungen im
Soll gebucht werden — wirtschaftlich richtig, weil das Konto `41950`
am Jahresende den **Netto-Saldo** aus Nachzahlungen und
Guthabenrückzahlungen führt. Im Nebenbuch wird parallel
`ist_betrag = -300` gesetzt → Status `ausgeglichen`.

### 7.4 Sammeltransfer Bewirtschaftung → Rücklage (Monatsende)

Eigentümer überweist per Dauerauftrag auf das Bewirtschaftungskonto
`18000`. Die Rücklagen-Erlöse landen wirtschaftlich auf `41911`/`41912`,
das Geld liegt aber physisch auf `18000`. Am Monatsende (oder
konfigurierbar: alle X Tage) generiert das System pro Objekt **eine**
Sammeltransfer-Überweisung pro Rücklagenkonto:

```
# Auslöser: Saldo aller Rücklagen-Splits, die im laufenden Monat
# auf 18000 eingegangen sind, ist > 0
Soll  14600  Bankübertrag / Geldtransit                 110,00
Haben 18000  Bank 1 Bewirtschaftung                     110,00

# Bei Bestätigung des Eingangs auf 18911 (durch camt.053 nächster Tag):
Soll  18911  Bank 2 Rücklage I                          110,00
Haben 14600  Bankübertrag / Geldtransit                 110,00
```

Die zugehörige SEPA-Überweisung wird im pain.001-Lauf vorbereitet und
muss vom Verwalter im üblichen Vier-Augen-Workflow freigegeben werden.

**Konfiguration je Objekt:**

- `transfer_aktiv: bool` — Default `True`
- `transfer_rhythmus: enum('monatsende', 'taeglich_ab_schwelle')` — Default `monatsende`
- `transfer_schwelle: Decimal` — nur bei `taeglich_ab_schwelle`

### 7.5 Konsistenz-Invariante

Solange keine Stornierung erfolgt ist, gilt für jede aktive
Sollstellung:

> `soll_betrag == SUM(splits.betrag)`  *(nur bei sollstellungs_typ='hausgeld')*
>
> `ist_betrag == SUM(zahlungen.betrag WHERE sollstellung=this)`
>
> `ist_betrag_split == SUM(zahlungen.betrag WHERE split=this)` *(je Split)*
>
> `SUM(splits.ist_betrag_split) == ist_betrag` *(nur bei hausgeld)*

Diese Invarianten werden in einem Test-Suite-Block (`test_invariants.py`)
unabhängig von der Service-Logik geprüft.

---

## 8. Storno

### 8.1 Storno einer einzelnen Sollstellung

Eine Sollstellung kann storniert werden **solange `ist_betrag = 0` ist**.
Das ist der einfache Fall: keine Sachkontenbuchung existiert (Sollstellung
hat ja keine erzeugt), keine `SollstellungZahlung` existiert — das
Storno ist ein reines Update am Nebenbuch:

```python
sollstellung.storniert_am   = timezone.now()
sollstellung.storniert_von  = user
sollstellung.storniert_grund = grund
sollstellung.status_cached  = "storniert"
sollstellung.save()
```

Die OPOS-Nr. bleibt erhalten (keine Wiederverwendung). Der Eintrag bleibt
in allen Listen mit Statusfilter `storniert` sichtbar.

**Wichtig:** Da keine Sachkontenbuchung existiert, ist das **kein**
GoBD-Storno und es entsteht **keine** Storno-Buchung im Buchungsjournal.
Das Storno wird ausschließlich am Nebenbuch protokolliert (Audit-Log
über Standard-Mechanismen).

### 8.2 Storno mit bereits erfolgten Zahlungen

Wenn bereits `SollstellungZahlung`-Einträge existieren, ist Storno
**nicht zulässig**. In diesem Fall muss der Buchhalter:

1. Die Zahlungen erst manuell rückabwickeln (Zahlungs-Zuordnung
   aufheben → Sachkontenbuchung wird per GoBD-Storno rückgängig gemacht),
2. dann die Sollstellung stornieren.

Das System prüft dies im Service und verweigert das Storno mit klarer
Fehlermeldung.

### 8.3 Massen-Storno eines Sollstellungslaufs

Ein kompletter `Sollstellungslauf` (z.B. ein versehentlich falsch
ausgeführter Monatslauf) kann **vor jeglicher Tilgung** komplett
storniert werden. Service iteriert über alle zugehörigen Sollstellungen
und prüft je Datensatz die Bedingung aus 8.2. Wenn auch nur eine
Sollstellung des Laufs bereits getilgt ist, bricht das Massen-Storno
mit Fehlerliste ab (keine Teil-Storno).

---

## 9. SEPA-Lastschriftlauf

### 9.1 Auswahl-Logik

Pro Objekt und Stichtag werden alle offenen Sollstellungen ermittelt,
deren EigentumsVerhältnis ein **aktives SEPA-Mandat** hat:

```python
def auswahl_lastschrift_kandidaten(objekt, stichtag):
    return HausgeldSollstellung.objects.filter(
        objekt=objekt,
        status_cached__in=["offen", "teilbezahlt"],
        faellig_am__lte=stichtag,
        storniert_am__isnull=True,
        eigentumsverhaeltnis__person__sepa_mandat__isnull=False,
        eigentumsverhaeltnis__person__sepa_mandat__aktiv=True,
    ).select_related("eigentumsverhaeltnis__person__sepa_mandat")
```

Sollstellungen ohne aktives Mandat bleiben außen vor (Dauerauftrag oder
manuelle Zahlung erwartet).

### 9.2 Gruppierung der Lastschriftpositionen

Pro Sollstellung **ein** `<DrctDbtTxInf>`-Block. **Aber:** Wenn Splits
einer `hausgeld`-Sollstellung auf **verschiedene Zielbankkonten** zeigen
(Bewirtschaftungskonto vs. Rücklagenkonto), wird die Sollstellung auf
**zwei separate Lastschriften** aufgeteilt — eine je Zielbankkonto:

| Beispiel Müller, März 2026 | Lastschrift A | Lastschrift B |
|---|---|---|
| Ziel-Bankkonto | 18000 (Bewirtschaftung) | 18911 (Rücklage I) ¹ |
| Splits | `.900` | `.911` + `.912` (beide auf 18911) ² |
| Betrag | 250,00 € | 110,00 € |
| EndToEndId | gemeinsame OPOS-Nr. + Suffix `-B` | gemeinsame OPOS-Nr. + Suffix `-R1` |

¹ Die Zuordnung Rücklage I → 18911 ergibt sich aus der
`Bankkonto.reihenfolge` am Objekt; siehe Bestandsspezifikation.

² Standardfall: Es gibt **ein** Rücklagenkonto, auf das alle Rücklagen
gemeinsam fließen — alle Rücklagen-Splits laufen über dieselbe
Lastschrift. Falls je Rücklage ein **separates** Bankkonto existiert,
entstehen entsprechend mehr Lastschriften.

### 9.3 EndToEndId-Format mit Suffix

Da eine Sollstellung in bis zu N Lastschriften zerfallen kann, muss die
EndToEndId die Aufteilung mitkodieren — sonst ist die Rück-Zuordnung
bei R-Transactions ambig:

```
EndToEndId-Schema:
  {OPOS_NR}-{SUFFIX}

Suffix-Konvention:
  B    = Bewirtschaftungskonto
  R{n} = Rücklagenkonto Nr. n   (z.B. R1, R2)
  S    = Sonderumlage (gesamt, eine Lastschrift)
  A    = Abrechnungsergebnis (gesamt, Nachzahlung)
  AUSZ = ausgehende Überweisung — Guthabenauszahlung an Eigentümer (pain.001)

Beispiele:
  100001000458297-B      Müller, März 2026, Bewirtschaftungs-Lastschrift
  100001000458297-R1     Müller, März 2026, Rücklage-I-Lastschrift
  100001000458298-S      Müller, Sonderumlage Dach 2026
  100001000458299-A      Müller, Abrechnung 2025 Nachzahlung
  100001000458300-AUSZ   Müller, Abrechnung 2025 Guthabenauszahlung
```

Gesamtlänge bleibt mit max. ca. 20 Zeichen (Suffix `-AUSZ`) weit unter
SEPA-Grenze (35).

### 9.4 Verwendungszweck (`<Ustrd>`)

Menschenlesbar, ohne OPOS-Nr.:

```
{Zweck} {Periode} - {Einheit_Nr} - Objekt {Objekt_Kurzbez}
```

Beispiele:

| Sollstellungstyp | Ustrd |
|---|---|
| Hausgeld, Lastschrift Bewirtschaftung | `Hausgeld 03/2026 - WE01 - Objekt Coventrystr. 32` |
| Hausgeld, Lastschrift Rücklage I | `Rücklage 03/2026 - WE01 - Objekt Coventrystr. 32` |
| Sonderumlage | `Sonderumlage Dachsanierung - WE01 - Objekt Coventrystr. 32` |
| Abrechnungsergebnis | `Abrechnung 2025 - WE01 - Objekt Coventrystr. 32` |

**Voraussetzung:** Das Objekt-Modell braucht ein Feld `kurzbezeichnung`
(z.B. „Coventrystr. 32") für den Verwendungszweck. Wenn nicht vorhanden,
in der Objektstammdaten-Erfassung ergänzen (Kap. 13).

### 9.5 pain.008-Struktur (Auszug pro Position)

```xml
<DrctDbtTxInf>
  <PmtId>
    <EndToEndId>100001000458297-B</EndToEndId>
  </PmtId>
  <InstdAmt Ccy="EUR">250.00</InstdAmt>
  <DrctDbtTx>
    <MndtRltdInf>
      <MndtId>{SEPA-Mandats-ID}</MndtId>
      <DtOfSgntr>{Datum Mandatserteilung}</DtOfSgntr>
    </MndtRltdInf>
  </DrctDbtTx>
  <Dbtr><Nm>{Eigentümer-Name}</Nm></Dbtr>
  <DbtrAcct><Id><IBAN>{Eigentümer-IBAN}</IBAN></Id></DbtrAcct>
  <RmtInf>
    <Ustrd>Hausgeld 03/2026 - WE01 - Objekt Coventrystr. 32</Ustrd>
  </RmtInf>
</DrctDbtTxInf>
```

### 9.6 Lastschriftlauf-Workflow

| Phase | Aktion |
|---|---|
| 1. Vorschau | Service ermittelt Kandidaten, gruppiert, berechnet Beträge → JSON-Vorschau |
| 2. Bestätigung | Verwalter sichtet, gibt frei (Vier-Augen-Prinzip möglich) |
| 3. Generierung | pain.008-XML wird erzeugt + Lastschriftlauf-Datensatz angelegt |
| 4. Upload | XML wird beim Kreditinstitut eingereicht (manuell oder via EBICS) |
| 5. Eingang | camt.053 zeigt Buchung des Sammeleingangs (siehe 10.1) |
| 6. R-Transactions | camt.054 zeigt etwaige Rücklastschriften → Tilgung wird zurückgerollt (siehe 11) |

---

## 10. Zahlungserkennung und automatische Tilgung

### 10.1 Eingangsweg 1 — Lastschrift-Rückmeldung (camt.053/054)

Wenn die Lastschrift erfolgreich gezogen wurde, erscheint sie als
**Sammelbuchung** im camt.053. Der camt-Parser zerlegt die Sammelposition
in ihre Einzelpositionen anhand der `EndToEndId`s:

```python
# pseudocode
for einzelposten in sammelbuchung.einzelposten:
    e2e_id = einzelposten.end_to_end_id
    opos_nr, suffix = e2e_id.split("-")

    sollstellung = HausgeldSollstellung.objects.get(opos_nr=opos_nr)
    splits = bestimme_betroffene_splits(sollstellung, suffix)

    verrechne_zahlung_lastschrift(
        sollstellung=sollstellung,
        splits=splits,
        buchung=einzelposten.buchung,
        betrag=einzelposten.betrag,
    )
```

Der `suffix` (`-B`, `-R1`, `-S`, `-A`) entscheidet, welche Splits getilgt
werden:

| Suffix | getilgte Splits |
|---|---|
| `-B` | alle Splits mit `bankkonto_ziel = Bewirtschaftungskonto` |
| `-R{n}` | alle Splits mit `bankkonto_ziel = Rücklagenkonto Nr. n` |
| `-S` | ganze Sollstellung (Sonderumlage hat keine Splits) |
| `-A` | ganze Sollstellung (Abrechnungsergebnis hat keine Splits) |

→ **Vollautomatisch.** Keine Vorschlags-/Bestätigungs-Schleife.

### 10.2 Eingangsweg 2 — IBAN-Match (Dauerauftrag oder freie Überweisung)

Der camt.053-Parser findet via IBAN das eindeutige EigentumsVerhältnis
(siehe bestehende Buchungserkennung Stufe 1). Dann wird das Nebenbuch
abgefragt:

```python
offene = HausgeldSollstellung.objects.filter(
    eigentumsverhaeltnis=ev,
    status_cached__in=["offen", "teilbezahlt"],
    storniert_am__isnull=True,
).order_by("periode", "erstellt_am")

verhalten = bestimme_verhalten(offene, eingangsbetrag)
```

### 10.3 Verhaltens-Matrix

| Konstellation | Verhalten |
|---|---|
| Keine offene Sollstellung | Frontoffice — Eingang ungeklärt (DCL 13700) |
| 1 offene Sollstellung, Typ `hausgeld`, Betrag = Restbetrag | **Automatisch** — voll tilgen, Splits nach Tilgungspriorität (Rücklage vor Hausgeld) |
| 1 offene Sollstellung, Typ `hausgeld`, Betrag < Restbetrag | **Automatisch** — Splits in Tilgungspriorität tilgen bis Eingang aufgebraucht |
| 1 offene Sollstellung, Typ `hausgeld`, Betrag > Restbetrag | **Vorschlag** — Überzahlung an Buchhalter zur Entscheidung |
| N offene Sollstellungen, **nur Typ `hausgeld`**, Betrag = Σ aller Restbeträge | **Automatisch** — alle tilgen, älteste zuerst (§ 366 BGB), je Sollstellung Splits nach Priorität |
| N offene Sollstellungen, **nur Typ `hausgeld`**, Betrag = Restbetrag genau einer einzelnen | **Automatisch** — genau diese tilgen |
| N offene Sollstellungen, **nur Typ `hausgeld`**, sonstiger Betrag | **Vorschlag** mit § 366/367-Vorbelegung (älteste zuerst, alles tilgen bis Eingang verbraucht) |
| Mindestens 1 offene Sollstellung Typ `sonderumlage`, Betrag = deren Restbetrag, eindeutig | **Automatisch** — diese Sonderumlage tilgen |
| Mindestens 1 offene Sollstellung Typ `abrechnungsergebnis`, Betrag = deren Restbetrag, eindeutig | **Automatisch** — diese tilgen |
| Mehrere offene Sonderumlagen/Abrechnungsergebnisse, Betrag passt zu mehreren | **Vorschlag** — niemals automatisch (Mehrdeutigkeit bei zweckgebundener Forderung) |
| Typ-übergreifender Summenmatch (z.B. HG + Sonderumlage zusammen) | **Vorschlag** — niemals automatisch |

### 10.4 Vorschlags-UI im Frontoffice

Wenn `Vorschlag` ausgelöst, landet der Eingang im
**Frontoffice-Posteingang** (siehe Rechnungserkennung-Spec, Soft-Lock).
Anzeige:

- Eingang: IBAN, Betrag, Verwendungszweck, Buchungsdatum
- Erkanntes EigentumsVerhältnis
- Liste der offenen Sollstellungen mit Vorschlags-Aufteilung
  (durch das System nach § 366/367 vorbelegt)
- Buchhalter kann: bestätigen / Aufteilung manuell anpassen / als DCL belassen

### 10.5 Sonderfall: Negatives Abrechnungsergebnis (Guthaben) — Auszahlungslauf

Guthaben aus der Jahresabrechnung werden **nicht automatisch verrechnet**,
sondern aktiv per SEPA-Überweisung an den Eigentümer ausgezahlt. Der
Workflow ist symmetrisch zum SEPA-Lastschriftlauf (Kap. 9), nur mit
umgekehrter Geldflussrichtung (pain.001 Sammelüberweisung statt pain.008
Sammeleinzug).

#### Auswahl-Logik

Pro Objekt werden alle offenen Guthaben-Sollstellungen ermittelt:

```python
def auswahl_auszahlungs_kandidaten(objekt):
    return HausgeldSollstellung.objects.filter(
        objekt=objekt,
        sollstellungs_typ="abrechnungsergebnis",
        soll_betrag__lt=0,                       # nur Guthaben
        status_cached="offen",                   # noch nicht ausgezahlt
        storniert_am__isnull=True,
        eigentumsverhaeltnis__person__iban__isnull=False,
    ).select_related("eigentumsverhaeltnis__person")
```

Eigentümer ohne hinterlegte IBAN bleiben außen vor — sie werden in
einem Ausnahmen-Bericht aufgeführt, der Verwalter klärt die IBAN-Pflege
und startet den Lauf erneut.

#### Workflow

| Phase | Aktion |
|---|---|
| 1. Trigger | Nach Genehmigung der Jahresabrechnung; manuell startbar je Objekt oder mandantenweit |
| 2. Vorschau | Service ermittelt Kandidaten, listet je EV: Name, IBAN, Guthabenbetrag, OPOS-Nr. |
| 3. Bestätigung | Verwalter sichtet, gibt frei (Vier-Augen-Prinzip möglich) |
| 4. Generierung | pain.001-XML mit einer Position je Eigentümer, EndToEndId mit Suffix `-AUSZ` |
| 5. Upload | XML wird beim Kreditinstitut eingereicht (manuell oder EBICS) |
| 6. Abgang im camt.053 | Pro identifizierter Position erfolgt die Buchung gemäß Kap. 7.3 (Soll 41950 / Haben 18000), parallel wird `SollstellungZahlung` mit `betrag = soll_betrag` (negativ) und `ist_betrag = soll_betrag` (negativ) gesetzt → Status `ausgeglichen` |

#### Auszahlungslauf-Datensatz

Analog zu `Lastschriftlauf` wird ein `Auszahlungslauf`-Datensatz angelegt:

| Feld | Typ |
|---|---|
| `id` | UUID (PK) |
| `objekt` | FK → Objekt |
| `wirtschaftsjahr` | FK → Wirtschaftsjahr |
| `status` | Enum: `vorschau` / `commited` / `eingereicht` / `abgeschlossen` |
| `anzahl_positionen` | IntegerField |
| `summe` | DecimalField(14,2) (positiver Betrag = Auszahlungssumme) |
| `pain001_xml` | TextField, nullable |
| `erstellt_am`, `erstellt_von`, `commited_am`, `commited_von` | |

#### pain.001-Position (Auszug)

```xml
<CdtTrfTxInf>
  <PmtId>
    <EndToEndId>100001000458300-AUSZ</EndToEndId>
  </PmtId>
  <Amt>
    <InstdAmt Ccy="EUR">300.00</InstdAmt>
  </Amt>
  <Cdtr><Nm>{Eigentümer-Name}</Nm></Cdtr>
  <CdtrAcct><Id><IBAN>{Eigentümer-IBAN}</IBAN></Id></CdtrAcct>
  <RmtInf>
    <Ustrd>Guthaben Abrechnung 2025 - WE01 - Objekt Coventrystr. 32</Ustrd>
  </RmtInf>
</CdtTrfTxInf>
```

Der Verwendungszweck ist menschenlesbar (analog Kap. 9.4) — der
Eigentümer sieht klar, wofür das Geld ist.

#### Rückläufer (Bank meldet IBAN ungültig)

Falls die Bank die Überweisung zurückweist (z.B. wegen falscher IBAN
oder gelöschtem Konto), erscheint die Gegenbuchung im camt.053. Sie
wird über die EndToEndId-Suffix `-AUSZ` der ursprünglichen
Auszahlungsbuchung zugeordnet:

1. Storno-Buchung im Hauptbuch (GoBD-konform): `Haben 41950 / Soll 18000`
2. Im Nebenbuch: `ist_betrag` der Guthabensollstellung wird auf 0
   zurückgesetzt, Status wieder `offen`
3. Frontoffice-Aufgabe an den Buchhalter: IBAN klären, im nächsten
   Auszahlungslauf erneut einreichen

---

## 11. R-Transactions (Rücklastschriften)

Beim Eingang einer Rücklastschrift (camt.054 mit `R-Transaction`-Status):

1. Über `EndToEndId` wird die ursprüngliche `SollstellungZahlung`
   identifiziert.
2. Die ursprüngliche Tilgung wird im Nebenbuch zurückgerollt
   (`ist_betrag` reduzieren, `SollstellungZahlung` als `storniert`
   markieren — nicht löschen, GoBD-konformer Audit).
3. Die ursprüngliche Sachkontenbuchung (Bank/41xxx) wird per
   GoBD-konformer Storno-Buchung rückabgewickelt.
4. **Hook für Mahnwesen-Spec:** Eine neue Sollstellung mit BA `.940`
   oder `.941` für Rücklastschriftgebühr wird erzeugt. Diese Logik
   gehört in die Mahnwesen-Spec, **nicht** in diese Spec — hier wird
   nur der Trigger-Punkt vermerkt.

Diese Spec dokumentiert R-Transactions auf konzeptioneller Ebene; die
detaillierte Implementierung ist Teil der Mahnwesen-Spec.

---

## 12. Service-Architektur

### 12.1 Übersicht

```
apps/buchhaltung/services/
├── opos_nr_service.py            # Vergabe OPOS-Nr.
├── sollstellung_service.py       # Anlegen, Storno
├── sollstellungslauf_service.py  # Massenlauf (Hausgeld monatlich, Sonderumlage, Abrechnung)
├── zahlungs_zuordnung_service.py # Tilgung (EndToEndId-Match, IBAN-Match, manuell)
├── sepa_lastschrift_service.py   # pain.008-Erzeugung (Einzüge)
├── auszahlungs_service.py        # pain.001-Erzeugung (Guthaben-Auszahlung an Eigentümer)
└── sammeltransfer_service.py     # Bewirtschaftung → Rücklage (Kap. 7.4)
```

### 12.2 Aufgabentrennung

| Service | Zuständigkeit | Liest aus | Schreibt nach |
|---|---|---|---|
| `opos_nr_service` | reine Nummern-Vergabe | OposSequenz | OposSequenz |
| `sollstellung_service` | einzelne Sollstellung anlegen/stornieren, Splits validieren | EV, BA, Bankkonto | HausgeldSollstellung, SollstellungSplit |
| `sollstellungslauf_service` | Massenlauf (iteriert über aktive EVs) | Objekt, EV, HausgeldHistorie | Sollstellungslauf, HausgeldSollstellung, SollstellungSplit |
| `zahlungs_zuordnung_service` | Eingang → Tilgung, erzeugt Buchung + Buchungssatz + SollstellungZahlung | camt-Buchung, Nebenbuch | Buchung, Buchungssatz, SollstellungZahlung |
| `sepa_lastschrift_service` | Lastschriftlauf aufsetzen, pain.008 erzeugen | offene Sollstellungen, SEPA-Mandate | Lastschriftlauf-Datensatz, XML-Datei |
| `auszahlungs_service` | Guthaben-Auszahlungslauf, pain.001 erzeugen, Abgang verbuchen | negative `.950`-Sollstellungen, Eigentümer-IBAN | Auszahlungslauf, Buchung, Buchungssatz, SollstellungZahlung |
| `sammeltransfer_service` | Monatsende-Job: SEPA-Überweisung BWK → Rücklage | gebuchte Eingänge des Monats | Buchung (Geldtransit), SEPA-pain.001 |

### 12.3 Pseudocode — `sollstellungslauf_service.run_hausgeld_monat`

```python
@transaction.atomic
def run_hausgeld_monat(objekt, periode: date, erstellt_von) -> Sollstellungslauf:
    """
    Erzeugt für jedes aktive EigentumsVerhaeltnis im Objekt zur Periode
    genau eine Hausgeld-Sollstellung mit Splits je aktiver BA.
    Idempotent: bei Wiederholung passiert nichts (Unique-Constraint).
    """
    lauf = Sollstellungslauf.objects.create(
        objekt=objekt,
        typ="hausgeld_monat",
        periode=periode,
        status="commited",
        erstellt_von=erstellt_von,
        commited_von=erstellt_von,
        commited_am=timezone.now(),
    )

    aktive_evs = EigentumsVerhaeltnis.objects.filter(
        einheit__objekt=objekt,
        beginn__lte=periode,
    ).exclude(ende__lt=periode)

    summe = Decimal("0")
    anzahl = 0

    for ev in aktive_evs:
        # 1) Beträge je BA aus HausgeldHistorie (mit ba-Feld!) ermitteln
        betraege = aktuelle_haushgeld_betraege(ev, periode)
        # → {"900": 250.00, "911": 80.00, "912": 30.00}

        soll_summe = sum(betraege.values())
        if soll_summe == 0:
            continue  # keine Sollstellung für reine 0-EVs

        # 2) Eltern-Sollstellung anlegen
        try:
            ss = HausgeldSollstellung.objects.create(
                objekt=objekt,
                eigentumsverhaeltnis=ev,
                sollstellungs_typ="hausgeld",
                ba=None,
                periode=periode,
                faellig_am=periode,
                opos_nr=naechste_opos_nr(objekt),
                soll_betrag=soll_summe,
                sollstellungslauf=lauf,
                erstellt_von=erstellt_von,
            )
        except IntegrityError:
            # Sollstellung existiert bereits (Idempotenz)
            continue

        # 3) Splits anlegen
        for ba_code, betrag in betraege.items():
            ba_obj = Buchungsart.objects.get(code=ba_code)
            bankkonto_ziel = bestimme_bankkonto(objekt, ba_obj)
            erloeskonto    = ba_obj.erloeskonto_default
            SollstellungSplit.objects.create(
                sollstellung=ss,
                ba=ba_obj,
                betrag=betrag,
                bankkonto_ziel=bankkonto_ziel,
                erloeskonto=erloeskonto,
            )

        summe += soll_summe
        anzahl += 1

    lauf.anzahl_sollstellungen = anzahl
    lauf.summe = summe
    lauf.save(update_fields=["anzahl_sollstellungen", "summe"])
    return lauf
```

### 12.4 Pseudocode — `zahlungs_zuordnung_service.verrechne_eingang`

```python
@transaction.atomic
def verrechne_eingang(camt_buchung, eigentumsverhaeltnis,
                       gebucht_von) -> List[SollstellungZahlung]:
    """
    Verrechnet einen Zahlungseingang (camt.053) gegen offene
    Sollstellungen nach Verhaltens-Matrix (Kap. 10.3).
    Erzeugt Sachkontenbuchung + SollstellungZahlung-Einträge.
    """
    eingang = camt_buchung.betrag
    offene = HausgeldSollstellung.objects.filter(
        eigentumsverhaeltnis=eigentumsverhaeltnis,
        status_cached__in=["offen", "teilbezahlt"],
        storniert_am__isnull=True,
    ).order_by("periode", "erstellt_am")

    verhalten = bestimme_verhalten(offene, eingang)

    if verhalten.modus == "automatisch":
        return _tilge_automatisch(camt_buchung, verhalten.plan, gebucht_von)
    elif verhalten.modus == "vorschlag":
        _erzeuge_frontoffice_aufgabe(camt_buchung, verhalten.vorschlag)
        return []
    else:
        _als_dcl_buchen(camt_buchung)   # auf 13700 Ungeklärte Posten
        return []


def _tilge_automatisch(camt_buchung, plan, user) -> List[SollstellungZahlung]:
    """
    plan: Liste von (sollstellung, split_or_none, betrag, tilgungsstufe)
    """
    # Eine Sachkontenbuchung mit N Buchungssätzen:
    #   Soll  Bank                                  Σ Beträge
    #   Haben 41xxx (je Split-Erloeskonto)          je Betrag
    buchung = Buchung.objects.create(
        objekt=camt_buchung.objekt,
        belegdatum=camt_buchung.buchungsdatum,
        buchungstext=f"Hausgeldzahlung {camt_buchung.eigentuemer_name}",
        erstellt_von=user,
        art="ZAHLUNGSEINGANG",
    )
    Buchungssatz.objects.create(
        buchung=buchung,
        konto=camt_buchung.bankkonto,
        soll=camt_buchung.betrag, haben=Decimal("0"),
    )
    # Haben-Seiten gemäß Plan:
    haben_summen_je_erloeskonto = defaultdict(Decimal)
    for ss, split, betrag, _ in plan:
        erloeskonto = split.erloeskonto if split else ss.ba.erloeskonto_default
        haben_summen_je_erloeskonto[erloeskonto] += betrag

    for konto, betrag in haben_summen_je_erloeskonto.items():
        Buchungssatz.objects.create(
            buchung=buchung, konto=konto,
            soll=Decimal("0"), haben=betrag,
        )

    # Nebenbuch-Updates
    ergebnis = []
    for ss, split, betrag, tilgungsstufe in plan:
        sz = SollstellungZahlung.objects.create(
            sollstellung=ss,
            split=split,
            buchung=buchung,
            betrag=betrag,
            tilgungsstufe=tilgungsstufe,
            erstellt_von=user,
        )
        ss.ist_betrag += betrag
        if split:
            split.ist_betrag_split += betrag
            split.save(update_fields=["ist_betrag_split"])
        ss.status_cached = ss.status  # Property → cached
        ss.save(update_fields=["ist_betrag", "status_cached"])
        ergebnis.append(sz)

    return ergebnis
```

---

## 13. Migrationspfad / Greenfield-Cleanup

Da IMMOCORE noch nicht produktiv läuft, werden die nicht mehr benötigten
Strukturen ersatzlos entfernt:

### 13.1 Zu entfernen

| Element | Ort | Grund |
|---|---|---|
| Modell `Personenkonto` | bisherige Ausgangsspec Kap. 4.8 | ersetzt durch Nebenbuch |
| Modell `Unterkonto` (Suffix `.900/.911/...`) | bisherige Ausgangsspec Kap. 4.8 | ersetzt durch Splits + BA |
| Suffix-Vergabe-Logik in Wizard Schritt 5/7 | WEG-Objektanlage v1.2, Kap. 5 | nicht mehr nötig — Splits ziehen Konfiguration aus BA |
| `post_save`-Signal auf `EigentumsVerhaeltnis` für Personenkonto-Anlage | bestehender Code | ersatzlos |
| Buchungserkennung-Stufe „Personenkonto-Match" | Rechnungserkennung v1.2 | ersetzt durch „EigentumsVerhältnis-Match → Nebenbuch-Verrechnung" |
| Sollstellungs-Buchungen `Personenkonto / 41xxx` | bisherige Buchungslogik | entfällt komplett — Sollstellung erzeugt keine Buchung |

### 13.2 Anzupassen

| Element | Anpassung |
|---|---|
| `HausgeldHistorie` | um `ba`-Feld erweitern; pro BA pro EV eine Historienzeile |
| Wizard WEG-Objektanlage Schritt 7 (Verträge & Hausgeld) | je Einheit/Eigentümer Beträge pro BA erfassen (`.900` + dynamische Rücklagen) — bestehender Aufbau bleibt im Wesentlichen, nur ohne Personenkonto-Anlage |
| Wizard Eigentümerwechsel (Spec v1.1 Kap. 5.2) | Schritte 3/4: nicht mehr Personenkonto archivieren, sondern: offene Sollstellungen des alten EV bleiben am alten EV; neuer EV beginnt mit leerem Nebenbuch. Etwaige offene Guthabensollstellungen (`.950` < 0) des alten EV werden im nächsten Auszahlungslauf ausgezahlt (an die hinterlegte IBAN des verkaufenden Eigentümers) — Verrechnung mit Hausgeld des Käufers ist ausgeschlossen. |
| Einzelabrechnung-Generator | Hausgeld-Spalte „VZ Soll" zieht aus Nebenbuch (Σ `soll_betrag` aller Hausgeld-Sollstellungen des Eigentümers im WJ), nicht mehr aus Sachkontenumsätzen |
| Buchungsjournal-UI | Sollstellungen erscheinen NICHT mehr im Buchungsjournal (sind keine Buchungen); eigenes „Sollstellungsjournal" als neue View |
| Objekt-Modell | Feld `kurzbezeichnung` (CharField, max_length=40) ergänzen für Verwendungszweck |

### 13.3 Neu anzulegen

| Element | Ort |
|---|---|
| Modelle aus Kap. 4 | `apps/buchhaltung/models/nebenbuch.py` |
| Services aus Kap. 12 | `apps/buchhaltung/services/` |
| Migration: Tabellen anlegen, `OposSequenz` für alle bestehenden Objekte initialisieren | `apps/buchhaltung/migrations/00XX_hausgeld_nebenbuch.py` |
| Initialdaten: `tilgungs_prioritaet` an bestehenden BAs setzen | gleiche Migration, RunPython |
| Frontend-View: Sollstellungsübersicht je Objekt + je EV | neue React-Komponenten |

---

## 14. Schnittstellen für künftige Spezifikationen

### 14.1 Mahnwesen-Spec

Diese Spec stellt folgende Hooks bereit, die das Mahnwesen nutzt:

- `HausgeldSollstellung.faellig_am` + `status_cached` → Auswahl mahnreifer OPs
- Property `HausgeldSollstellung.tage_ueberfaellig` → Mahnstufe-Bestimmung
- R-Transaction-Hook (Kap. 11) → Trigger für Rücklastschriftgebühr-Sollstellung
- Mahngebühren werden als eigene Sollstellung mit BA `.940`/`.941` modelliert (eigene OPOS-Nr.)

Die Mechanik (Mahnstufen, Eskalation, Gebührenhöhe) wird **nicht** hier
festgelegt, sondern in `IMMOCORE_ClaudeCode_Mahnwesen_v1_0.docx`.

### 14.2 Skonto / Storno-Erweiterung

Skonto betrifft die Aufwandsseite (Eingangsrechnungen) und ist
unabhängig von dieser Spec. Storno auf Sachkontenebene (GoBD-Storno)
ist von Kap. 8 zu unterscheiden — Kap. 8 regelt nur den
Nebenbuch-Storno.

### 14.3 Jahresabrechnung-Wizard

Die Schnittstelle zum Wirtschaftsjahres-Abschluss
(`IMMOCORE_ClaudeCode_Wirtschaftsjahre_v1_0.md`) erzeugt nach Genehmigung
der Abrechnung pro EigentumsVerhältnis eine Sollstellung mit
`sollstellungs_typ='abrechnungsergebnis'`. Positive Beträge =
Nachzahlung (Forderung der WEG → Lastschrift- oder
Daueraufträge-Eingang), negative = Guthaben (Verbindlichkeit der WEG →
Auszahlungslauf gemäß Kap. 10.5).

Nach Abschluss der Sollstellungs-Erzeugung sollte der Wizard den
Verwalter zur sofortigen Ausführung des **Auszahlungslaufs** für
Guthaben hinleiten — typischerweise erfolgt die Auszahlung zeitnah zur
Abrechnung, sodass beide Vorgänge fachlich zusammen wahrgenommen
werden.

---

## 15. Aufgaben für Claude Code

> **Hinweis an Claude Code:** Arbeite die Schritte in dieser Reihenfolge
> ab. Nach jedem Schritt: Migration erzeugen, Tests laufen lassen, erst
> dann zum nächsten Schritt. Keine Datenbank-Änderungen ohne Migration.
> Alle Geschäftslogik **ausschließlich** in `services/` — nie in Views
> oder Models. Bestehende Personenkonto-/Unterkonto-Strukturen werden
> in Schritt 9 entfernt — **nicht früher**, sonst brechen die noch nicht
> umgestellten Teile.

### Schritt 1 — Modelle anlegen

Datei: `apps/buchhaltung/models/nebenbuch.py`. Modelle gemäß Kap. 4
implementieren:

- `HausgeldSollstellung` mit allen Constraints und der `status`-Property
- `SollstellungSplit`
- `SollstellungZahlung`
- `Sollstellungslauf`
- `OposSequenz`

Migration mit `makemigrations` + Review der erzeugten SQL. CHECK-
Constraint aus Kap. 4.1 manuell ergänzen, falls Django ihn nicht
automatisch erzeugt.

### Schritt 2 — BA-Modell erweitern

Datei: `apps/buchhaltung/models/buchungsart.py`. Felder gemäß Kap. 6.1
ergänzen:

- `tilgungs_prioritaet` (nullable IntegerField)
- `erloeskonto_default` (FK auf Konten-Vorlage, nullable)
- `bankkonto_typ` (Enum)

Datenmigration (RunPython): Setze `tilgungs_prioritaet` für `.900`,
`.911`–`.93N`, `.950` und `.940` gemäß Tabelle Kap. 6.2.

### Schritt 3 — `HausgeldHistorie` erweitern

Datei: `apps/buchhaltung/models/eigentumsverhaeltnis.py`.

- Neues Pflichtfeld `ba` (FK → Buchungsart)
- Migration: pro bestehender Historienzeile (sollte keine geben, da
  Greenfield, aber zur Sicherheit) eine Default-Zuordnung zu `.900`
  schreiben. Bei leerer Tabelle: Migration ist No-Op.
- Unique-Constraint anpassen auf `(eigentumsverhaeltnis, ba, gueltig_ab)`.

### Schritt 4 — `Objekt`-Modell erweitern

Datei: `apps/buchhaltung/models/objekt.py`.

- Feld `kurzbezeichnung` (CharField(40), nullable initial, später Pflicht)
- Default-Befüllung aus bestehender Adresse für alle Objekte in
  Datenmigration

### Schritt 5 — Service: OPOS-Nr.

Datei: `apps/buchhaltung/services/opos_nr_service.py`. Funktionen aus
Kap. 5.3 implementieren:

- `naechste_opos_nr(objekt) -> str`
- `luhn_pruefziffer(basis: str) -> int`
- `validiere_opos_nr(opos_nr: str) -> bool`

Tests: Vergabe-Reihenfolge, Race-Condition (mit `transaction.atomic`
+ `select_for_update`), Luhn-Validierung (positive und negative Beispiele).

### Schritt 6 — Service: Sollstellung anlegen

Datei: `apps/buchhaltung/services/sollstellung_service.py`. Funktionen:

- `lege_hausgeld_sollstellung_an(ev, periode, betraege_je_ba, lauf, user)`
  → erzeugt `HausgeldSollstellung` + Splits + OPOS-Nr.
- `lege_sonderumlage_sollstellung_an(ev, ba, betrag, periode, faellig_am, user)`
- `lege_abrechnungsergebnis_sollstellung_an(ev, betrag, wj_ende, user)`
- `storniere_sollstellung(ss, grund, user)` mit Prüfung aus Kap. 8.2

### Schritt 7 — Service: Massenlauf

Datei: `apps/buchhaltung/services/sollstellungslauf_service.py`.

- `run_hausgeld_monat(objekt, periode, user)` — Pseudocode aus Kap. 12.3
- `run_sonderumlage(objekt, beschluss, user)` — pro EV anhand
  Verteilerschlüssel-Anteil
- `run_abrechnungsergebnis(objekt, wj, user)` — pro EV aus
  Jahresabrechnung-Ergebnis (positiv und negativ)
- `storniere_lauf(lauf, grund, user)` mit Prüfung aus Kap. 8.3

### Schritt 8 — Service: Zahlungszuordnung

Datei: `apps/buchhaltung/services/zahlungs_zuordnung_service.py`.

- `verrechne_lastschrift_eingang(camt_einzelposten, user)` — Eingangsweg 1
- `verrechne_eingang(camt_buchung, ev, user)` — Eingangsweg 2 mit
  Verhaltens-Matrix
- `bestimme_verhalten(offene, eingang) -> Verhalten` (Datenklasse mit
  Modus + Plan/Vorschlag)
- `bestimme_plan_unterzahlung(sollstellung, eingang)` — Splits nach
  Tilgungspriorität tilgen

### Schritt 9 — Service: SEPA-Lastschrift

Datei: `apps/buchhaltung/services/sepa_lastschrift_service.py`.

- `vorschau_lastschriftlauf(objekt, stichtag) -> dict`
- `commite_lastschriftlauf(vorschau, user) -> Lastschriftlauf`
- `generiere_pain008(lauf) -> str` — XML-Erzeugung
- `gruppiere_positionen_je_sollstellung(ss) -> List[Position]` —
  Aufteilung nach `bankkonto_ziel` der Splits (Kap. 9.2/9.3)
- EndToEndId-Suffix-Logik (`-B`, `-R{n}`, `-S`, `-A`)

### Schritt 10 — Service: Guthaben-Auszahlung

Datei: `apps/buchhaltung/services/auszahlungs_service.py`.

- `vorschau_auszahlungslauf(objekt, wirtschaftsjahr) -> dict` — listet
  alle EVs mit offenem `.950`-Guthaben, Filter aus Kap. 10.5
- `commite_auszahlungslauf(vorschau, user) -> Auszahlungslauf`
- `generiere_pain001(lauf) -> str` — XML-Erzeugung Sammelüberweisung
- EndToEndId-Suffix `-AUSZ`, Verwendungszweck menschenlesbar
- `verbuche_auszahlung_abgang(camt_einzelposten, user)` — beim
  camt.053-Eingang des Abgangs: Sachkontenbuchung `Soll 41950 / Haben 18000`
  + `SollstellungZahlung` mit negativem Betrag, Status auf `ausgeglichen`
- `verbuche_auszahlung_rueckweisung(camt_einzelposten, user)` —
  GoBD-Storno der Abgangsbuchung, Status zurück auf `offen`,
  Frontoffice-Aufgabe an Buchhalter

### Schritt 11 — Service: Sammeltransfer

Datei: `apps/buchhaltung/services/sammeltransfer_service.py`.

- Celery-Periodic-Task: `task_sammeltransfer_monatsende(objekt)`
- Berechnung der Beträge pro Rücklagenkonto (alle Tilgungen des Monats,
  die als Soll `18000` aber wirtschaftlich `41911`/`41912` waren)
- Erzeugt pain.001 für Überweisung + Geldtransit-Buchung 14600/18000

### Schritt 12 — Greenfield-Cleanup

Erst nachdem Schritte 1–11 lauffähig sind:

- Entferne Modell `Personenkonto`, `Unterkonto` (und alle Migrationen
  bis dahin als initial gestützt → bei Greenfield ggf. via squash)
- Entferne `post_save`-Signal in `apps/objekte/signals.py`
- Entferne Suffix-Logik aus `services/buchungserkennung.py` (Stufe
  Personenkonto)
- Passe Wizard WEG-Objektanlage (Schritt 5/7) und
  Eigentümerwechsel (Schritt 3/4) an: Personenkonto-bezogene Aktionen
  entfernen, durch Nebenbuch-Aktionen ersetzen

### Schritt 13 — Tests

Mindest-Tests pro Service:

1. **OPOS-Nr.**: Vergabe-Reihenfolge, Luhn-Validierung, Eindeutigkeit
   bei parallelen Transaktionen (Concurrency-Test)
2. **Sollstellung anlegen**: alle drei Typen; Unique-Constraint-Verletzung
   bei Doppelausführung
3. **Massenlauf**: Idempotenz (zweimal aufrufen ändert nichts);
   negative `.950`-Sollstellung bleibt unangetastet (kein automatisches
   Verrechnen mit Folgemonat)
4. **Tilgung**: alle 11 Zeilen der Verhaltens-Matrix (Kap. 10.3) als
   eigene Tests
5. **Tilgungspriorität**: Rücklage-vor-Hausgeld bei Unterzahlung
6. **Lastschrift**: Aufsplittung bei mehreren Zielbankkonten;
   EndToEndId-Suffix-Korrektheit
7. **Auszahlungslauf**: Vorschau enthält nur EVs mit negativer
   `.950`-Sollstellung + hinterlegter IBAN; pain.001-Generierung;
   Verbuchung Abgang (Soll 41950 / Haben 18000); Rückweisung führt zu
   Storno-Buchung und Status zurück auf `offen`
8. **Storno**: nur bei `ist_betrag=0`; Massen-Storno bricht ab, wenn
   eine Sollstellung getilgt ist
9. **Invarianten** (`test_invariants.py`): Eigenschaften aus Kap. 7.5
   nach jeder Operation prüfen

### Schritt 14 — Frontend-Views

(Nicht im Detail Teil dieser Backend-Spec, aber notwendig für MVP)

- Sollstellungsjournal je Objekt
- Sollstellungs-Detailansicht (mit Splits, Tilgungs-Historie, OPOS-Nr.)
- Lastschriftlauf-Wizard (Vorschau → Bestätigung → XML-Download)
- **Auszahlungslauf-Wizard** für Guthaben (Vorschau → Bestätigung →
  pain.001-Download)
- Frontoffice-Vorschlagsliste für mehrdeutige Eingänge

---

## 16. Akzeptanzkriterien (Smoke-Test vor Go-Live)

Manueller End-to-End-Test mit einem Test-Objekt:

1. **Massensollstellung März 2026** für 5 EVs erzeugen — alle 5
   Hausgeld-Sollstellungen entstehen, jede mit korrekten Splits, jede
   mit eindeutiger OPOS-Nr., **keine** Sachkontenbuchung im
   Buchungsjournal sichtbar.
2. **Lastschriftlauf** auf 5 EVs → pain.008 enthält 5–10 Positionen
   (je nach Anzahl Rücklagenkonten); jede EndToEndId hat korrektes
   Format und Suffix.
3. **camt.053 mit Sammeleingang** importieren → alle 5 Sollstellungen
   vollautomatisch getilgt, jede Tilgung erzeugt korrekte
   Sachkontenbuchung mit Bank-Soll und Erlöskonten-Haben (gesplittet).
4. **Dauerauftrag-Eingang** mit Unterzahlung (200 von 360 €) →
   automatische Verrechnung, Rücklagen-Splits voll, `.900`-Split
   teilweise; Nebenbuch zeigt `teilbezahlt`.
5. **Mehrdeutiger Eingang** (Eigentümer mit offener Sonderumlage und
   Hausgeld, überweist Hausgeld-Betrag) → Eingang landet im
   Frontoffice-Vorschlag, **nicht** automatisch verbucht.
6. **Storno** einer noch nicht getilgten Sollstellung → Status
   `storniert`, OPOS-Nr. bleibt erhalten, keine GoBD-Storno-Buchung.
7. **Storno-Versuch** einer bereits teilweise getilgten Sollstellung →
   Service verweigert mit klarer Fehlermeldung.
8. **Negatives Abrechnungsergebnis** (Guthaben −300 €) für einen EV
   anlegen → erscheint in der Auszahlungslauf-Vorschau, **nicht** in
   der nächsten Hausgeld-Sollstellung. Auszahlungslauf committen,
   pain.001-XML wird erzeugt; nach simuliertem camt.053-Abgang erfolgt
   Buchung `Soll 41950 / Haben 18000 = 300,00 €`, Guthabensollstellung
   wechselt auf Status `ausgeglichen`.

Wenn alle 8 Punkte grün sind, ist diese Spec implementierungs-vollständig.

---

**Ende der Spezifikation.**
