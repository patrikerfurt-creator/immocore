# Claude Code – Anleitung: Buchungsnummer & Kreditoren-OP-Nummer (IMMOCORE)

**Version:** 1.0
**Status:** Implementierungsreif
**Bezug:** Ergänzt
- Hausgeld-Nebenbuch v1.1 (Debitoren-OPOS-Nr.)
- OP-Buchung v1.1 (Kreditoren-OP-Mechanik auf 15900)
- Ausgangsspezifikation v1.3 (Buchung/Buchungssatz-Modell)

---

## 1. Ziel

Drei Nummernkreise, die heute teils fehlen oder vermischt sind, werden
formal getrennt und systematisch eingeführt:

| Nummer | Wofür | Gilt für |
|---|---|---|
| **Buchungsnummer** | identifiziert jede Sachkontenbuchung im Hauptbuch | jede `Buchung`, egal ob Debitor/Kreditor/Bank/Sammeltransfer/Storno |
| **Kreditoren-OP-Nr.** | identifiziert jeden offenen Posten im Kreditoren-Nebenbuch (`15900`) | jede Eingangsrechnung als OP |
| **Debitoren-OPOS-Nr.** (bestehend) | identifiziert jede Forderung im Debitoren-Nebenbuch | jede `HausgeldSollstellung` |

Alle drei sind **eigene Identifikatoren mit eigenen Sequenz-Generatoren**
und dürfen niemals miteinander vermischt werden. Insbesondere: Eine
OP-Nr. ist **niemals** identisch mit einer Buchungsnummer — sie
identifizieren unterschiedliche Dinge auf unterschiedlichen Ebenen.

## 2. Format-Übersicht

| Bereich | Format | Beispiel | Länge | Prüfziffer | EndToEndId-fähig |
|---|---|---|---|---|---|
| Buchungsnummer | `{JJ}-{LFD5}` | `26-00147` | 8 | nein | nein (intern) |
| Kreditoren-OP-Nr. | `K{OBJ6}{JJ2}{LFD5}-{LUHN}` | `K10000126000038-8` | 16 | ja (Luhn) | ja (pain.001/camt.053) |
| Debitoren-OPOS-Nr. | `{OBJ6}{LFD8}-{LUHN}` | `100001000045829-7` | 16 | ja (Luhn) | ja (pain.008/camt.054) |

### 2.1 Visuelle Unterscheidbarkeit

Die drei Formate sind absichtlich so gewählt, dass sie **auf einen
Blick** unterscheidbar sind:

- **Buchungsnummer** ist kurz (8 Zeichen) und hat genau einen
  Bindestrich nach Position 2 (`26-`).
- **Kreditoren-OP-Nr.** beginnt mit `K` und ist 16 Zeichen lang.
- **Debitoren-OPOS-Nr.** beginnt mit einer Ziffer und ist 16 Zeichen
  lang, ohne Präfix.

Im Frontoffice/Reporting kann ein Beleg-Suchfeld automatisch erkennen,
welche Art Nummer eingegeben wurde, und in der richtigen Tabelle suchen
— ohne dass der Benutzer den Suchtyp vorher wählen muss.

## 3. Buchungsnummer

### 3.1 Format

```
Format:    {JJ}-{LFD5}
Beispiel:  26-00147
Länge:     2 + 1 + 5 = 8 Zeichen

Aufbau:
  JJ      = Anlagejahr zweistellig (z.B. 26 für 2026)
  -       = Trenner
  LFD5    = lfd. Nr. innerhalb Objekt + Anlagejahr, fortlaufend ab 00001
```

**Begründung der Kompaktheit:** Da `Buchung.objekt` als FK existiert,
ist die Objektnummer im Kontext bereits eindeutig. Eine zusätzliche
Objektnummer in der Buchungsnummer wäre redundant. Die volle
Eindeutigkeit ergibt sich aus dem zusammengesetzten Schlüssel
`(objekt, buchungs_nr)`.

### 3.2 Sequenz-Strategie — wichtig

Die Sequenz wird **pro Objekt + Anlagejahr** geführt. Ein Reset auf
`00001` erfolgt am 1.1. jedes Jahres.

**Entscheidung: Buchungsnummer folgt `Buchung.erstellt_am` (technisches
Anlagedatum), nicht `Buchung.belegdatum`.**

Konsequenz: Eine Buchung, die am 5.1.2027 mit Belegdatum 28.12.2026
angelegt wird, bekommt eine `27-...`-Nummer (nicht `26-...`). Die
Buchungsnummer-Reihenfolge ist damit **entkoppelt vom Wirtschaftsjahr**.

**Was das bedeutet — explizit dokumentieren:**

| Frage | Antwort |
|---|---|
| Welche Buchungen gehören zum Wirtschaftsjahr 2026? | alle mit `belegdatum BETWEEN '2026-01-01' AND '2026-12-31'` — **nicht** anhand der Buchungsnummer filtern |
| Ist die Buchungsnummer GoBD-konform? | Ja. GoBD verlangt lückenlose Nummerierung und Unveränderbarkeit, nicht die Übereinstimmung mit dem Wirtschaftsjahr |
| Was zeigt das Buchungsjournal als Sortierung? | Standard: `belegdatum, buchungs_nr`. Buchungsnummer als reiner technischer Schlüssel |

### 3.3 Datenmodell-Erweiterung

Modell `Buchung` (in `apps/buchhaltung/models.py`) bekommt ein neues
Pflichtfeld:

```python
class Buchung(models.Model):
    # ... bestehende Felder ...

    buchungs_nr = models.CharField(
        max_length=8,
        editable=False,
        db_index=True,
        help_text="Buchungsnummer im Format JJ-LFD5, fortlaufend pro Objekt+Anlagejahr"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['objekt', 'buchungs_nr'],
                name='uniq_buchung_objekt_nr'
            ),
        ]
        indexes = [
            models.Index(fields=['objekt', 'buchungs_nr']),
        ]
```

Neue Sequenz-Tabelle:

```python
class BuchungsNrSequenz(models.Model):
    """Sequenzgenerator für Buchungsnummern, pro Objekt + Jahr."""
    objekt = models.ForeignKey(Objekt, on_delete=models.PROTECT)
    jahr   = models.IntegerField(help_text="4-stellig, z.B. 2026")
    naechste_lfd_nr = models.IntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['objekt', 'jahr'], name='uniq_buchungsnr_objekt_jahr'),
        ]
```

### 3.4 Service zur Vergabe

Datei: `apps/buchhaltung/services/buchungs_nr_service.py`

```python
from django.db import transaction
from datetime import datetime
from apps.buchhaltung.models import BuchungsNrSequenz


@transaction.atomic
def naechste_buchungs_nr(objekt, anlagedatum: datetime = None) -> str:
    """
    Vergibt die nächste Buchungsnummer für (objekt, anlagejahr).
    anlagedatum default = jetzt; wird intern auf das Jahr reduziert.

    Race-safe via SELECT ... FOR UPDATE auf BuchungsNrSequenz.
    """
    jahr = (anlagedatum or datetime.now()).year

    seq, _ = BuchungsNrSequenz.objects.select_for_update().get_or_create(
        objekt=objekt, jahr=jahr,
        defaults={'naechste_lfd_nr': 1}
    )
    lfd = seq.naechste_lfd_nr
    seq.naechste_lfd_nr = lfd + 1
    seq.save(update_fields=['naechste_lfd_nr'])

    jj_str  = str(jahr)[-2:]              # 2026 → "26"
    lfd_str = str(lfd).zfill(5)            # 1 → "00001"
    return f"{jj_str}-{lfd_str}"
```

### 3.5 Integration in alle Buchung-erzeugenden Services

**Jede** Stelle, die `Buchung.objects.create(...)` aufruft, muss
`buchungs_nr` setzen. Folgende Services sind betroffen:

| Service | Datei |
|---|---|
| Zahlungseingang (Debitor) | `apps/buchhaltung/services/zahlungs_zuordnung_service.py` |
| Eingangsrechnung als OP | `apps/rechnungen/services/rechnung_op_service.py` |
| Eingangsrechnung Zahlung | `apps/rechnungen/services/rechnung_zahlung_service.py` |
| Sammeltransfer BWK→Rücklage | `apps/buchhaltung/services/sammeltransfer_service.py` |
| Camt.053-Import (Bankbuchungen) | `apps/buchhaltung/services/camt053.py` |
| Auszahlungs-Service (Guthaben) | `apps/buchhaltung/services/auszahlungs_service.py` |
| Storno-Buchungen | überall, wo Stornos erzeugt werden |
| Sonstige (Eröffnungssalden, manuelle Buchungen) | je nach Stelle |

Empfehlung: Die Vergabe **zentralisieren** in einer Factory-Funktion
`erzeuge_buchung(...)`, die immer auch die Buchungsnummer setzt. Damit
kann kein Service die Nummer vergessen.

```python
# apps/buchhaltung/services/buchung_service.py  (neu, falls noch nicht vorhanden)
from django.db import transaction
from apps.buchhaltung.models import Buchung
from .buchungs_nr_service import naechste_buchungs_nr


@transaction.atomic
def erzeuge_buchung(*, objekt, belegdatum, buchungstext, art, erstellt_von, **kwargs) -> Buchung:
    """
    Zentraler Einstiegspunkt für alle Buchungs-Erzeugungen.
    Vergibt automatisch die Buchungsnummer.
    """
    return Buchung.objects.create(
        objekt=objekt,
        belegdatum=belegdatum,
        buchungstext=buchungstext,
        art=art,
        erstellt_von=erstellt_von,
        buchungs_nr=naechste_buchungs_nr(objekt),
        **kwargs,
    )
```

Alle Stellen, die heute `Buchung.objects.create(...)` direkt aufrufen,
werden auf `erzeuge_buchung(...)` umgestellt.

---

## 4. Kreditoren-OP-Nummer

### 4.1 Bestandsaufnahme

Die heute im System vorhandenen Felder im Modell `Rechnung`
(`apps/rechnungen/models.py`):

| Feld | Bedeutung | Bleibt |
|---|---|---|
| `Kreditor.kreditorennummer` | Kontonummer des Lieferanten im SKR (z.B. 70000) | ja |
| `Rechnung.rechnungsnummer` | externe Rechnungsnummer des Lieferanten | ja |
| `Rechnung.kundennummer` | Kundennummer **bei** dem Lieferanten | ja |

**Was fehlt:** Eine systematische mandantenseitige OP-Nr., die genau
diesen Rechnungs-OP eindeutig identifiziert — analog zur Debitoren-
OPOS-Nr. Diese Nr. wird benötigt für:

- `EndToEndId` in `pain.001` bei Überweisung an den Lieferanten
- Rück-Identifikation im `camt.053` beim Abgang vom Bankkonto
- R-Transactions (Rückläufer, Bankablehnung)
- Mahnwesen-Bezug (Lieferant mahnt → wir identifizieren über OP-Nr.)
- internes Suchfeld für Buchhalter

### 4.2 Format

```
Format:    K{OBJ6}{JJ2}{LFD5}-{LUHN}
Beispiel:  K10000126000038-8
Länge:     1 + 6 + 2 + 5 + 1 + 1 = 16 Zeichen

Aufbau:
  K        = Präfix (visuelles Erkennungsmerkmal Kreditor)
  OBJ6     = Objekt-Nr. 6-stellig (für Banken-Roundtrip ohne DB-Lookup)
  JJ2      = Anlagejahr 2-stellig
  LFD5     = lfd. Nr. innerhalb Objekt + Anlagejahr, fortlaufend ab 00001
  -        = Trenner vor Prüfziffer
  LUHN     = Luhn-Prüfziffer (Mod-10) über die 13 Ziffern OBJ6+JJ2+LFD5
```

**Wichtig:** Das Präfix `K` ist **nicht** Teil der Luhn-Berechnung —
Luhn rechnet ausschließlich über Ziffern. Berechnungsgrundlage:
`{OBJ6}{JJ2}{LFD5}` = 13 Ziffern.

Beispielrechnung: `OBJ=100001, JJ=26, LFD=00038`, Basis `1000012600038`:

```
Position rechts→links:  8 3 0 0 0 6 2 1 0 0 0 0 1
Verdoppeln (i ungerade):  6   12  6  2     0    0
Quersumme (>9):           6    3  6  2     0    0
Ergebnis:               8 6 0 3 0 6 6 1 2 0 0 0 1
Summe:                  33
Prüfziffer:             (10 - 33 % 10) % 10 = (10 - 3) % 10 = 7
```

→ Vollständige Nummer: `K10000126000038-7`. *(Hinweis: die exakte
Berechnung ergibt 7, nicht 8 wie in einer früheren Iteration mündlich
geschätzt — der Service-Code unten ist die maßgebliche Implementierung.)*

### 4.3 Sequenz-Strategie

Analog Buchungsnummer:
- Pro Objekt + Anlagejahr
- Reset jeden 1.1.
- Anlagejahr nach `Rechnung.erstellt_am`, **nicht** nach
  `Rechnung.belegdatum` oder `Rechnung.faelligkeit` (Konsistenz mit
  Buchungsnummer-Logik)

### 4.4 Datenmodell-Erweiterung

Modell `Rechnung` (in `apps/rechnungen/models.py`):

```python
class Rechnung(models.Model):
    # ... bestehende Felder (kreditorennummer, rechnungsnummer, kundennummer, ...) ...

    op_nr = models.CharField(
        max_length=16,
        editable=False,
        unique=True,             # mandantenweit eindeutig durch Objekt-Präfix
        db_index=True,
        help_text="Kreditoren-OP-Nr. im Format K{OBJ6}{JJ2}{LFD5}-{LUHN}"
    )
```

Neue Sequenz-Tabelle (analog zur Buchungsnummer):

```python
class KreditorenOpNrSequenz(models.Model):
    """Sequenzgenerator für Kreditoren-OP-Nummern, pro Objekt + Jahr."""
    objekt = models.ForeignKey(Objekt, on_delete=models.PROTECT)
    jahr   = models.IntegerField()
    naechste_lfd_nr = models.IntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['objekt', 'jahr'], name='uniq_kreditor_opnr_objekt_jahr'),
        ]
```

### 4.5 Service zur Vergabe

Datei: `apps/rechnungen/services/kreditor_op_nr_service.py`

```python
from django.db import transaction
from datetime import datetime
from apps.rechnungen.models import KreditorenOpNrSequenz

# Wiederverwendung der Luhn-Implementierung aus opos_nr_service
from apps.buchhaltung.services.opos_nr_service import luhn_pruefziffer


@transaction.atomic
def naechste_kreditor_op_nr(objekt, anlagedatum: datetime = None) -> str:
    """Vergibt die nächste Kreditoren-OP-Nr."""
    jahr = (anlagedatum or datetime.now()).year

    seq, _ = KreditorenOpNrSequenz.objects.select_for_update().get_or_create(
        objekt=objekt, jahr=jahr,
        defaults={'naechste_lfd_nr': 1}
    )
    lfd = seq.naechste_lfd_nr
    seq.naechste_lfd_nr = lfd + 1
    seq.save(update_fields=['naechste_lfd_nr'])

    obj_str = str(objekt.objekt_nr).zfill(6)
    jj_str  = str(jahr)[-2:]
    lfd_str = str(lfd).zfill(5)
    basis   = obj_str + jj_str + lfd_str         # 13 Ziffern

    pruefz  = luhn_pruefziffer(basis)
    return f"K{basis}-{pruefz}"


def validiere_kreditor_op_nr(op_nr: str) -> bool:
    """Prüft Format und Luhn-Validität."""
    if len(op_nr) != 16 or not op_nr.startswith("K"):
        return False
    rest = op_nr[1:]                              # ohne K
    if rest[13] != "-":                           # Bindestrich an Position 13
        return False
    basis    = rest[:13]                          # 13 Ziffern
    pruefz   = rest[14]                           # 1 Ziffer
    if not basis.isdigit() or not pruefz.isdigit():
        return False
    return luhn_pruefziffer(basis) == int(pruefz)
```

### 4.6 Integration

Die OP-Nr. wird **bei Anlage der Rechnung** vergeben — typischerweise
im `rechnung_op_service.py`, sobald die Rechnungserkennung
abgeschlossen ist und die Rechnung im System persistiert wird:

```python
# apps/rechnungen/services/rechnung_op_service.py
from .kreditor_op_nr_service import naechste_kreditor_op_nr

def lege_rechnung_als_op_an(...):
    rechnung = Rechnung.objects.create(
        ...,
        op_nr=naechste_kreditor_op_nr(objekt),
    )
    # ... bestehende Logik (Buchung 15900 / 70xxx) ...
```

### 4.7 Verwendung der OP-Nr.

| Ort | Verwendung |
|---|---|
| `pain.001` Überweisungslauf | `<EndToEndId>{op_nr}</EndToEndId>` |
| `camt.053` Abgang vom Bankkonto | Lookup über `EndToEndId` → eindeutige Rechnung |
| Rückläufer (Bank weist Überweisung zurück) | Lookup über `EndToEndId` → Storno + Wiedervorlage |
| Frontoffice-Suchfeld | Eingabe der OP-Nr. → direkter Rechnungs-Treffer |
| Mahnschreiben des Lieferanten | OP-Nr. kann als Aktenzeichen referenziert werden |

### 4.8 Verwendungszweck — analog Lastschrift menschenlesbar

Der `<Ustrd>` des pain.001 enthält **keine** OP-Nr. (analog Lastschrift-
Konzept aus Nebenbuch v1.1). Format:

```
RE {rechnungsnummer} {kreditor_name} Objekt {objekt_kurzbez}
```

Beispiel:
```
RE 2026-04738 Stadtwerke Frankfurt Objekt Coventrystr. 32
```

Der Lieferant sieht auf seinem Kontoauszug eine eindeutig zuordenbare
Position — ohne kryptische OP-Nr.

---

## 5. Daten-Lebenszyklus und Konsistenz

### 5.1 Eindeutigkeitsregeln

| Constraint | Geltungsbereich |
|---|---|
| `(Buchung.objekt, Buchung.buchungs_nr)` unique | innerhalb Objekt eindeutig |
| `Rechnung.op_nr` unique | mandantenweit eindeutig (durch Objekt-Präfix in Nr.) |
| `HausgeldSollstellung.opos_nr` unique | mandantenweit eindeutig (bestehend) |

### 5.2 Wiederverwendung — verboten

Sobald eine Nummer vergeben ist, wird sie **niemals wiederverwendet**.
Auch bei:

- Stornierung der Buchung (eine Storno-Buchung bekommt eine **eigene
  neue** Buchungsnummer, die stornierte Originalbuchung behält ihre)
- Stornierung der Rechnung/des OPs (die OP-Nr. bleibt am stornierten
  Datensatz hängen)
- Stornierung einer Sollstellung (OPOS-Nr. bleibt)

Die Sequenz-Tabellen zählen **nur vorwärts**.

### 5.3 GoBD-Konformität

Die Buchungsnummer erfüllt das GoBD-Kriterium der "fortlaufenden,
unveränderbaren Nummerierung" pro Mandant. Lückenlosigkeit gilt **pro
Objekt + Anlagejahr** — das ist der relevante Mandanten-Scope in
IMMOCORE.

Achtung: Da Variante b gewählt wurde (Buchungsnr folgt Anlagedatum),
folgt die Lückenlosigkeit der Anlagereihenfolge, **nicht** der
Wirtschaftsjahr-Reihenfolge. Für die GoBD-Prüfung ist das zulässig,
solange im Buchungsjournal beide Sortierungen (Belegdatum und
Buchungsnummer) verfügbar sind — was sie sind.

---

## 6. UI-Hinweise

### 6.1 Anzeige

- **Buchungsjournal:** Spalte "Buchungs-Nr." links neben Belegdatum,
  in Festbreite-Schrift (`monospace`) für gute Lesbarkeit
- **Rechnungsliste:** Spalte "OP-Nr." prominent neben externer
  Rechnungsnummer
- **Sollstellungsliste:** Spalte "OPOS-Nr." (unverändert wie heute)

### 6.2 Suchfeld

Globales Beleg-Suchfeld erkennt die Nummernart automatisch:

| Eingabe-Muster | Suche in |
|---|---|
| `^\d{2}-\d{5}$` (z.B. `26-00147`) | `Buchung.buchungs_nr` |
| `^K\d{13}-\d$` (z.B. `K10000126000038-7`) | `Rechnung.op_nr` |
| `^\d{14}-\d$` (z.B. `100001000045829-7`) | `HausgeldSollstellung.opos_nr` |
| sonst | Volltext über Belegfelder |

---

## 7. Aufgaben für Claude Code

> **Hinweis an Claude Code:** Diese Spec ergänzt zwei neue
> Nummernkreise. Die Reihenfolge der Schritte ist wichtig — die
> Sequenzen müssen existieren, **bevor** die ersten Buchungen erzeugt
> werden. Greenfield-Annahme: keine Migration historischer Daten nötig,
> weil noch keine Sollstellung produktiv gebucht wurde.

### Schritt 1 — Sequenz-Modelle anlegen

Datei: `apps/buchhaltung/models.py`

- Modell `BuchungsNrSequenz` ergänzen (Kap. 3.3)
- Migration erzeugen: `makemigrations buchhaltung`

Datei: `apps/rechnungen/models.py`

- Modell `KreditorenOpNrSequenz` ergänzen (Kap. 4.4)
- Migration erzeugen: `makemigrations rechnungen`

### Schritt 2 — Datenmigrationen für Sequenz-Init

In beiden Migrationen je eine `RunPython`-Datenmigration: Für jedes
existierende Objekt × jedes Jahr, in dem Daten existieren könnten
(realistisch: aktuelles Jahr + Vorjahr), wird ein Sequenz-Eintrag
angelegt mit `naechste_lfd_nr=1`.

### Schritt 3 — Felder `buchungs_nr` und `op_nr` ergänzen

- `Buchung.buchungs_nr` (CharField(8), editable=False, db_index=True)
- `Rechnung.op_nr` (CharField(16), unique=True, editable=False, db_index=True)
- UniqueConstraint `(Buchung.objekt, Buchung.buchungs_nr)`
- Migration erzeugen

### Schritt 4 — Services für Nummer-Vergabe

Datei: `apps/buchhaltung/services/buchungs_nr_service.py` (neu)

- Funktion `naechste_buchungs_nr(objekt, anlagedatum=None) -> str`
- Race-safe via `select_for_update()` (Kap. 3.4)

Datei: `apps/rechnungen/services/kreditor_op_nr_service.py` (neu)

- Funktion `naechste_kreditor_op_nr(objekt, anlagedatum=None) -> str`
- Funktion `validiere_kreditor_op_nr(op_nr: str) -> bool`
- Wiederverwendung der `luhn_pruefziffer`-Implementierung aus
  `apps.buchhaltung.services.opos_nr_service`

### Schritt 5 — Zentrale Buchung-Factory

Datei: `apps/buchhaltung/services/buchung_service.py` (neu, sofern noch nicht vorhanden)

- Funktion `erzeuge_buchung(...)` aus Kap. 3.5

### Schritt 6 — Bestehende Services umstellen

Alle Stellen, die `Buchung.objects.create(...)` direkt aufrufen, auf
`erzeuge_buchung(...)` umstellen. Konkrete Stellen (aus Bestandsanalyse):

- `apps/rechnungen/services/rechnung_op_service.py` (15900-Buchung bei Rechnungseingang)
- `apps/rechnungen/services/rechnung_zahlung_service.py` (Bezahlung der ER)
- `apps/buchhaltung/services/zahlungs_zuordnung_service.py` (Hausgeld-Eingang)
- `apps/buchhaltung/services/camt053.py` (camt-Import)
- `apps/buchhaltung/services/sammeltransfer_service.py` (BWK→Rücklage)
- `apps/buchhaltung/services/auszahlungs_service.py` (Guthaben-Auszahlung)
- ggf. weitere — per Grep prüfen:

```powershell
Select-String -Path apps -Recurse -Include *.py -Pattern "Buchung\.objects\.create|Buchung\(.*objekt"
```

Diese Liste durchgehen und jede Stelle umstellen.

### Schritt 7 — OP-Nr.-Vergabe in `rechnung_op_service.py`

In der Funktion, die die Rechnung als OP anlegt, `op_nr` mit
`naechste_kreditor_op_nr(objekt)` setzen, bevor `Rechnung.objects.create`
ausgeführt wird.

### Schritt 8 — pain.001-Generator anpassen

Der Service, der pain.001-Überweisungen an Lieferanten erzeugt
(typischerweise `apps/buchhaltung/services/sepa_export.py` oder
ähnlich), nutzt `Rechnung.op_nr` als `<EndToEndId>`. Verwendungszweck
gemäß Kap. 4.8 menschenlesbar formatieren, OP-Nr. **nicht** im
Verwendungszweck.

### Schritt 9 — camt.053-Import erweitert

Im camt.053-Parser:

- Wenn `EndToEndId` einem Muster `K{13 Ziffern}-{1 Ziffer}` entspricht
  → Lookup in `Rechnung.op_nr` → automatische Zuordnung des Abgangs
  zum Kreditoren-OP, Storno-Logik bei R-Transactions
- Wenn `EndToEndId` einem Muster `{15 Ziffern}-{Suffix}` entspricht
  → Lookup in `HausgeldSollstellung.opos_nr` (bestehende Logik)
- Sonstige Eingänge → bestehende Pfade (IBAN-Match etc.)

### Schritt 10 — UI-Anpassungen Backend-Endpoints

Die Serializers für Buchung, Rechnung und HausgeldSollstellung müssen
die Nummer-Felder enthalten (sind bei `editable=False` nicht automatisch
im DRF-Output). Felder explizit in `fields = [...]` aufnehmen.

### Schritt 11 — Frontend

(nur Hinweise — Frontend-Umsetzung ist außerhalb dieser Spec)

- Buchungsjournal: Spalte "Buchungs-Nr." links
- Rechnungsliste: Spalte "OP-Nr."
- Globales Beleg-Suchfeld mit Pattern-Detection (Kap. 6.2)

### Schritt 12 — Tests

| Testfall | Erwartung |
|---|---|
| Buchungsnummer-Vergabe einzeln | `26-00001`, `26-00002`, ... fortlaufend |
| Buchungsnummer parallel (Concurrency) | keine Doppelvergabe, `select_for_update` blockt korrekt |
| Buchungsnummer Jahreswechsel | letzte 2026-Buchung am 31.12. → `26-04217`; erste 2027-Buchung am 1.1. → `27-00001` |
| Buchungsnummer rückdatierte Buchung | am 5.1.2027 angelegt mit Belegdatum 28.12.2026 → bekommt `27-00...`-Nummer (Anlagedatum entscheidet) |
| Kreditoren-OP-Nr.-Vergabe | korrektes Format, korrekte Luhn-Prüfziffer |
| Luhn-Validierung | positive und negative Beispiele |
| pain.001 EndToEndId | enthält OP-Nr. korrekt |
| camt.053 R-Transaction Match | findet Rechnung anhand EndToEndId |
| Visuelle Trennbarkeit | Pattern-Regex aus Kap. 6.2 trennt die drei Nummernkreise korrekt |

### Schritt 13 — Smoke-Test (E2E)

1. Neue Rechnung erfassen → `op_nr` automatisch vergeben, Format
   `K{13}-{1}`, Luhn valide
2. Rechnung als OP buchen → Buchung erzeugt, `buchungs_nr` automatisch
   vergeben, Format `{2}-{5}`
3. Zahlung der Rechnung → zweite Buchung mit nächster `buchungs_nr`,
   Tilgung des OPs
4. SEPA-Überweisungslauf erzeugen → pain.001 enthält `op_nr` als
   `<EndToEndId>`, Verwendungszweck menschenlesbar ohne `op_nr`
5. camt.053 mit Abgang einspielen → automatische Zuordnung via
   EndToEndId, Buchung mit nächster Buchungsnummer
6. Manuelle Suche im Frontoffice nach OP-Nr. → trifft genau eine
   Rechnung
7. Manuelle Suche nach Buchungsnummer → trifft genau eine Buchung
8. Jahreswechsel-Simulation (Systemzeit auf 1.1.2027 setzen) → neue
   Buchung in beiden Sequenzen startet mit `27-00001` bzw.
   `K{OBJ}27{00001}-{LUHN}`

---

**Ende der Spezifikation.**
