# CLAUDE CODE — IMMOCORE
## Eigentümerwechsel (Wizard + Nebenbuch-Anpassungen)

**Version:** 1.0
**Stand:** Mai 2026
**Status:** 🟢 Aktiv — ersetzt Kap. 5.2 der Ausgangsspezifikation v1.1
**Bezug:** Nebenbuch-Spec v1.1 (Kap. 4, 8, 10.5, 13.2), Ausgangsspec v1.1 Kap. 4.6/4.7

---

## 1. Zweck und Abgrenzung

### 1.1 Was diese Spec regelt

Diese Spezifikation beschreibt den **Eigentümerwechsel-Workflow** im
Wizard-Modus für WEG-Objekte. Sie löst Kap. 5.2 der Ausgangsspec v1.1
ab (welche noch auf das entfernte `Personenkonto`-Modell setzte) und
verankert das Verhalten im **Nebenbuch** (Spec v1.1).

**Zwei Hauptszenarien:**

| Szenario | Auslöser | Mechanik |
|---|---|---|
| **Sauberer Wechsel** | Stichtag ≥ 1. des Folgemonats nach Wizard-Anlage | Käufer-EV anlegen, HausgeldHistorie übertragen, fertig — der reguläre Monats-Sollstellungslauf greift automatisch ab nächster Periode |
| **Nachträglicher Wechsel** | Stichtag liegt in der Vergangenheit; eine oder mehrere Sollstellungen für den Verkäufer wurden bereits erzeugt | Verkäufer-Sollstellungen ab Stichtag stornieren + ggf. zu unrecht gezahltes Hausgeld an Verkäufer rückerstatten; Käufer erhält Nachhol-Sollstellungen pro versäumter Periode mit 14-tägiger Mahnkarenz |

### 1.2 Was diese Spec NICHT regelt

- Finanzieller Ausgleich Käufer ↔ Verkäufer auf Kaufvertrags-/Notarebene
  bleibt **außerhalb des Systems** (kein Salden-Transfer zwischen EVs).
- ZH- und SEV-Objekttypen: aktuell HTTP 501 (Phase 2).
- Erbfolge, Zwangsversteigerung, Insolvenz: gleiches Verfahren auf
  Modellebene, aber UI-spezifische Sonderfälle (z.B. Erbengemeinschaft
  als Person) sind nicht Teil dieser Spec.

### 1.3 Greenfield-Annahme

Die in Ausgangsspec v1.1 Kap. 5.2 beschriebenen Schritte 3 und 4
(Abgrenzungsbuchung + Personenkonto archivieren) **entfallen
ersatzlos** — sie setzten auf das entfernte `Personenkonto`-Modell.
Diese Spec ersetzt den gesamten Wizard.

---

## 2. Datenmodell-Anpassungen

### 2.1 `EigentumsVerhaeltnis` — Feldergänzungen

| Feld | Typ | Anmerkung |
|---|---|---|
| `wechsel_grund` | Enum: `verkauf` / `erbfolge` / `zwangsversteigerung` / `sonstiges` | optional, default `verkauf` |
| `notarurkunde` | FK → Dokument, nullable | hochgeladene Urkunde |
| `vorgaenger` | FK → EigentumsVerhaeltnis, nullable | bei Wechsel: Verweis auf den Verkäufer-EV |

`beginn` und `ende` bleiben unverändert. `beginn` des Käufer-EV liegt
**immer auf einem Monatsersten** (Geschäftsregel, vom Wizard erzwungen
— siehe Kap. 3.1).

### 2.2 `HausgeldSollstellung` — Feldergänzung

| Feld | Typ | Anmerkung |
|---|---|---|
| `mahnkarenz_bis` | DateField, nullable | bis zu diesem Datum schließt das Mahnwesen die Sollstellung aus, unabhängig von `faellig_am` |
| `nachhol_aus_wechsel` | FK → EigentuemerwechselVorgang, nullable | nur bei rückwirkend angelegten Nachhol-Sollstellungen befüllt |

**Wirkung von `mahnkarenz_bis`:**

Die Mahnwesen-Spec (siehe Hook 14.1 der Nebenbuch-Spec) filtert
mahnreife OPs mittels `faellig_am < heute - tage_karenz_global`.
`mahnkarenz_bis` wirkt als **OP-spezifischer Override**: Solange
`mahnkarenz_bis >= heute`, gilt die Sollstellung als nicht mahnreif.

### 2.3 Neues Modell `EigentuemerwechselVorgang`

Dokumentiert einen abgeschlossenen Wechselvorgang als Audit-Anker.
Ermöglicht spätere Auswertung und sauberen Bezug der Nachhol-/Storno-
Aktionen auf den auslösenden Vorgang.

| Feld | Typ | Anmerkung |
|---|---|---|
| `id` | UUID (PK) | |
| `einheit` | FK → Einheit | |
| `verkaeufer_ev` | FK → EigentumsVerhaeltnis | |
| `kaeufer_ev` | FK → EigentumsVerhaeltnis | |
| `stichtag` | DateField | Tag der Eigentumsumschreibung (lt. Notar) |
| `wirkungs_periode` | DateField | erster Monatserster ab `stichtag` — ab hier ist der Käufer sollstellungspflichtig |
| `art` | Enum: `zukuenftig` / `rueckwirkend` | abgeleitet aus Vergleich `wirkungs_periode` ↔ heute |
| `verkaeufer_erstattung_betrag` | DecimalField(12,2), default 0 | Summe der an Verkäufer zurückzuerstattenden Beträge |
| `verkaeufer_erstattung_iban` | CharField, nullable | IBAN aus Verkäufer-Person zum Zeitpunkt des Wechsels (Snapshot) |
| `auszahlungslauf` | FK → Auszahlungslauf, nullable | befüllt sobald Erstattung in einen pain.001-Lauf gepackt wurde |
| `notarurkunde` | FK → Dokument, nullable | |
| `bemerkung` | TextField, nullable | |
| `erstellt_am`, `erstellt_von` | | |
| `abgeschlossen_am`, `abgeschlossen_von` | nullable | |

**Constraints:**

- `UniqueConstraint(fields=['einheit', 'stichtag'])` — pro Einheit pro
  Stichtag genau ein Wechselvorgang.

### 2.4 Erweiterung `Auszahlungslauf` (Nebenbuch-Spec Kap. 10.5)

Bisher war der `Auszahlungslauf` ausschließlich für Guthaben aus der
Jahresabrechnung gedacht. Diese Spec erweitert ihn um den Typ
`verkaeufer_erstattung`.

| Feld | Anpassung |
|---|---|
| `typ` | **neu** — Enum: `abrechnungsguthaben` / `verkaeufer_erstattung`; default `abrechnungsguthaben` |
| `wirtschaftsjahr` | nun **nullable** (bei `verkaeufer_erstattung` nicht gefüllt) |
| `eigentuemerwechsel` | **neu** — FK → EigentuemerwechselVorgang, nullable (befüllt nur bei `verkaeufer_erstattung`) |

EndToEndId-Suffix `-AUSZ` bleibt wiederverwendet (gleicher Buchungs-
Workflow), Differenzierung erfolgt über `typ` am Lauf.

**Verwendungszweck** bei `verkaeufer_erstattung`:

```
Erstattung Hausgeld {Periode} - {Einheit_Nr} - Objekt {Objekt_Kurzbez}
```

Beispiel: `Erstattung Hausgeld 03/2026 - WE01 - Objekt Coventrystr. 32`

---

## 3. Wizard — 6 Schritte

Der Wizard nutzt die bestehende Prozess-Engine (Persistierung als
JSONField, unterbrechbar und fortsetzbar — siehe Ausgangsspec Kap. 5).

### 3.1 Schritt-Übersicht

| Schritt | Bezeichnung | Inhalt | Pflicht |
|---|---|---|---|
| 1 | Einheit & Stichtag | Einheit wählen, Datum Eigentumsumschreibung, Wechsel-Grund, Notarurkunde hochladen | Ja |
| 2 | Käufer erfassen | Person aus Stammdaten oder neu anlegen; IBAN, E-Mail, Adresse, SEPA-Mandat | Ja |
| 3 | Hausgeld-Sollwerte | Beträge je BA für den Käufer-EV (default: identisch zur Verkäufer-HausgeldHistorie zum Stichtag) | Ja |
| 4 | Sollstellungs-Analyse | **Nur bei `rueckwirkend`** — System listet Verkäufer-Sollstellungen ab `wirkungs_periode`, Klassifizierung in „stornieren" und „rückerstatten" | Bedingt |
| 5 | Vorschau & Bestätigung | Zusammenfassung aller geplanten Änderungen (EV-Anlage, HausgeldHistorie, Stornos, Erstattung, Nachhol-Sollstellungen) | Ja |
| 6 | Commit & Abschluss | Atomare Ausführung, Verweis auf Auszahlungslauf (falls Erstattung), Hinweis Notarausgleich | Ja |

### 3.2 Schritt 1 — Einheit & Stichtag

**Eingaben:**

- Einheit (Dropdown, gefiltert auf Objekt)
- Stichtag (`stichtag`) — Datum der Eigentumsumschreibung lt. Notar
- Wechsel-Grund (Enum, default `verkauf`)
- Notarurkunde-Upload (PDF, optional)

**Systemberechnungen:**

- `wirkungs_periode = monatserster_nach(stichtag)`

  Konkret: Wenn `stichtag = 2026-03-15`, dann `wirkungs_periode = 2026-04-01`.
  Wenn `stichtag = 2026-03-01`, dann `wirkungs_periode = 2026-03-01`
  (der Erste eines Monats zählt als Beginn dieses Monats).

- `art = "rueckwirkend"` wenn `wirkungs_periode < heute_monatserster`,
  sonst `art = "zukuenftig"`.

**Anzeige:**

- Aktueller Eigentümer (= `verkaeufer_ev`) wird angezeigt — wenn keiner
  aktiv: Fehlermeldung, Wizard kann nicht starten.
- Hinweisbox bei `rueckwirkend`: *„Stichtag liegt in der Vergangenheit.
  Schritt 4 zeigt die zu korrigierenden Sollstellungen."*

**Validierung:**

- `stichtag` darf nicht in der Zukunft jenseits 90 Tage liegen
  (Sanity-Check gegen Tippfehler).
- `stichtag >= verkaeufer_ev.beginn` (Verkäufer muss zum Stichtag
  Eigentümer gewesen sein).

### 3.3 Schritt 2 — Käufer erfassen

**Eingaben:**

- Person-Auswahl: Stammdaten-Suche oder neue Person anlegen (analog
  Wizard WEG-Objektanlage Schritt 4)
- IBAN für Lastschrift/Erstattung
- E-Mail, Adresse (auf Person)
- SEPA-Mandat: neu anlegen oder Hinweis „Dauerauftrag"

**Validierung:**

- Käufer ≠ Verkäufer (Person-IDs unterschiedlich) — sonst Hinweis
  „selbe Person, ist das beabsichtigt?" (Soft-Warning, kein Hard-Block;
  Erbfolge auf sich selbst ist denkbar).
- IBAN-Format DE-konform.

### 3.4 Schritt 3 — Hausgeld-Sollwerte

**Eingaben (Grid):**

| BA | Bezeichnung | Verkäufer-Soll (Anzeige) | Käufer-Soll (Eingabe) |
|---|---|---|---|
| `.900` | Hausgeld lfd. | 250,00 € | [250,00 €] |
| `.911` | 1. Rücklage | 80,00 € | [80,00 €] |
| `.912` | 2. Rücklage | 30,00 € | [30,00 €] |

Default-Werte werden aus `HausgeldHistorie` des `verkaeufer_ev` zum
Stichtag gezogen und sind editierbar (z.B. bei Sonderkonditionen).

**Output:** Pro BA wird beim Commit eine neue `HausgeldHistorie`-Zeile
für den `kaeufer_ev` mit `gueltig_ab = wirkungs_periode` angelegt.

### 3.5 Schritt 4 — Sollstellungs-Analyse (nur bei `rueckwirkend`)

**Bei `art = zukuenftig` wird dieser Schritt übersprungen.**

**Systemberechnung:** Service ermittelt alle aktiven (nicht
stornierten) Sollstellungen des `verkaeufer_ev` mit
`periode >= wirkungs_periode` und klassifiziert sie:

```
fuer ss in verkaeufer_sollstellungen:
    if ss.ist_betrag == 0:
        bucket["zu_stornieren"].append(ss)
    elif 0 < ss.ist_betrag < ss.soll_betrag:
        bucket["teilweise_erstatten"].append(ss)
    elif ss.ist_betrag == ss.soll_betrag:
        bucket["voll_erstatten"].append(ss)
    elif ss.ist_betrag > ss.soll_betrag:
        bucket["ueberzahlt_erstatten"].append(ss)
```

**Anzeige:** Drei Tabellen.

#### 4a — Stornieren (ist_betrag = 0)

| OPOS-Nr. | Periode | Soll | Status | Aktion |
|---|---|---|---|---|
| 100001000458301 | 2026-04-01 | 360,00 € | offen | ☑ stornieren |
| 100001000458315 | 2026-05-01 | 360,00 € | offen | ☑ stornieren |

Alle Sollstellungen sind defaultmäßig zum Storno markiert. Buchhalter
kann einzelne abwählen (z.B. wenn er weiß, dass eine Sollstellung
fachlich doch bleiben muss — selten, aber möglich).

#### 4b — An Verkäufer rückerstatten (ist_betrag > 0)

| OPOS-Nr. | Periode | Soll | Ist | Erstattungsbetrag | Aktion |
|---|---|---|---|---|---|
| 100001000458288 | 2026-03-01 | 360,00 € | 360,00 € | 360,00 € | ☑ erstatten |
| 100001000458270 | 2026-02-01 | 360,00 € | 200,00 € | 200,00 € | ☑ erstatten |

**Erstattungsbetrag = `ist_betrag`** (das, was der Verkäufer tatsächlich
gezahlt hat — nicht das `soll_betrag`).

**Summe Erstattung** wird live am Tabellenfuß angezeigt; das wird der
Betrag für den `verkaeufer_erstattung`-Auszahlungslauf.

**Hinweis-Banner** bei Erstattungspositionen:

> ⚠ Der Verkäufer hat in diesem Zeitraum bereits Hausgeld bezahlt. Das
> System wird **eine SEPA-Überweisung an die hinterlegte IBAN des
> Verkäufers** vorbereiten (siehe Schritt 5). Stelle sicher, dass die
> Verkäufer-IBAN noch aktiv ist.

#### 4c — Überzahlt (ist_betrag > soll_betrag, Sonderfall)

Tritt nur auf, wenn der Verkäufer mehr gezahlt hat als geschuldet
(z.B. Dauerauftrag nicht gestoppt). Wird wie 4b behandelt:
**Erstattungsbetrag = `ist_betrag`** (komplette Zahlung zurück).

**Verkäufer-IBAN:**

Wird aus `verkaeufer_ev.person.ibans` gezogen (siehe Ausgangsspec Kap.
4.5). Wenn mehrere IBANs hinterlegt sind: Dropdown zur Auswahl mit
Default = zuletzt verwendete IBAN für Lastschrift.

**Wenn keine IBAN verfügbar:** Hard-Stop mit Aufforderung, IBAN am
Person-Stammdatensatz zu ergänzen, bevor der Wizard fortgesetzt
werden kann.

### 3.6 Schritt 5 — Vorschau & Bestätigung

Eine konsolidierte Übersicht aller geplanten Änderungen:

```
EIGENTÜMERWECHSEL — VORSCHAU

Einheit:        WE01, 1.OG links
Stichtag:       15.03.2026
Wirkungsperiode: 01.04.2026
Art:            rückwirkend

VERKÄUFER (EV beenden)
  Hans Müller, EV-Nr. 0001
  beginn: 01.01.2020 → ende: 31.03.2026

KÄUFER (EV anlegen)
  Maria Schmidt, neu angelegt
  beginn: 01.04.2026
  Hausgeld-Soll:
    .900  Hausgeld lfd.   250,00 €
    .911  1. Rücklage      80,00 €
    .912  2. Rücklage      30,00 €

SOLLSTELLUNGS-KORREKTUREN
  Stornieren:               2 Sollstellungen (Summe Soll: 720,00 €)
  An Verkäufer erstatten:   2 Sollstellungen (Summe Ist:  560,00 €)
  → Auszahlungslauf wird vorbereitet (pain.001), IBAN DE89...

NACHHOL-SOLLSTELLUNGEN KÄUFER (mit 14 Tagen Mahnkarenz)
  Periode 2026-04-01  Soll 360,00 €  Karenz bis 28.05.2026
  Periode 2026-05-01  Soll 360,00 €  Karenz bis 28.05.2026

NEUE NORMALE SOLLSTELLUNGEN
  ab 2026-06-01 läuft Käufer im regulären Monats-Sollstellungslauf
```

**Buttons:**

- `Zurück` — zurück zu Schritt 4 / 3
- `Bestätigen & Ausführen` — startet Commit (Schritt 6)
- `Abbrechen` — Wizard wird verworfen (nichts wird geschrieben)

### 3.7 Schritt 6 — Commit & Abschluss

Alle Operationen laufen in einer einzigen `transaction.atomic()`:

1. `verkaeufer_ev.ende = stichtag - 1 Tag` (z.B. 15.03.2026 → 14.03.2026)

   *Hinweis:* Das `ende`-Datum dokumentiert das tatsächliche Ende der
   Eigentümerschaft. Sollstellungspflicht endet aber bereits mit dem
   `wirkungs_periode - 1 Tag` (also dem Monatsende vor `wirkungs_periode`).
   Diese Doppeldeutigkeit ist gewollt: `ende` ist juristisch, der
   Sollstellungslauf-Filter (`beginn__lte=periode AND (ende__isnull OR ende__gte=periode)`)
   regelt die fachliche Sollstellungspflicht. Für eine im April laufende
   Massensollstellung ist `ende = 14.03.2026` < `2026-04-01` → Verkäufer
   wird ausgeschlossen. ✓

2. `kaeufer_ev` anlegen mit `beginn = wirkungs_periode`, `vorgaenger = verkaeufer_ev`.

3. `HausgeldHistorie`-Zeilen für `kaeufer_ev` pro BA aus Schritt 3
   anlegen mit `gueltig_ab = wirkungs_periode`.

4. **Storno-Liste (Schritt 4a):** Für jede markierte Sollstellung
   `storniere_sollstellung(ss, grund=f"Eigentümerwechsel {stichtag}", user)`
   aufrufen. Vorbedingung `ist_betrag = 0` ist garantiert.

5. **Erstattungs-Liste (Schritt 4b/4c):**

   a) Für jede zu erstattende Sollstellung **wird zunächst nur** der
      `EigentuemerwechselVorgang.verkaeufer_erstattung_betrag` aufkumuliert.
      Die Sollstellungen werden **noch nicht** storniert — sie bleiben
      bis zum Eingang der Erstattungsbuchung in der camt.053 im Status
      `ausgeglichen` bzw. `teilbezahlt`.

   b) Ein `Auszahlungslauf` mit `typ='verkaeufer_erstattung'` und
      `status='vorschau'` wird angelegt, gebunden an den
      `EigentuemerwechselVorgang`.

   c) Pro zu erstattender Sollstellung wird eine Position im
      Auszahlungslauf hinterlegt (pain.001-Position-Pseudo: IBAN
      Verkäufer, Betrag = `ist_betrag` der Sollstellung, EndToEndId
      mit Schema `{OPOS_NR}-AUSZ`, Verwendungszweck wie in Kap. 2.4).

6. **Nachhol-Sollstellungen Käufer:** Pro Periode von
   `wirkungs_periode` bis (einschließlich) dem **Monat vor** dem
   aktuellen Sollstellungslauf-Monat wird eine Hausgeld-Sollstellung
   für den `kaeufer_ev` angelegt:

   - `periode` = jeweilige Periode
   - `faellig_am` = `periode`
   - `mahnkarenz_bis` = `heute + 14 Tage`
   - `nachhol_aus_wechsel` = neuer `EigentuemerwechselVorgang`
   - Splits gemäß Käufer-HausgeldHistorie aus Schritt 3
   - OPOS-Nr. wird regulär vom `opos_nr_service` vergeben

   Die Logik nutzt `sollstellung_service.lege_hausgeld_sollstellung_an`
   pro Periode — kein separater Massenlauf.

7. **`EigentuemerwechselVorgang.abgeschlossen_am`** setzen.

8. Wizard-Prozess als `abgeschlossen` markieren.

**Abschluss-Anzeige:**

```
✓ Eigentümerwechsel erfolgreich abgeschlossen.

NÄCHSTE SCHRITTE:
  → Auszahlungslauf {ID} wartet auf Freigabe.
    [Zur Freigabe-Maske wechseln]
  → Nachhol-Sollstellungen sind im nächsten Lastschriftlauf enthalten.
  → Hinweis: Finanzieller Ausgleich Käufer ↔ Verkäufer erfolgt auf
    Kaufvertrags-/Notarebene, nicht im System.
```

Falls keine Erstattung anfällt (Fall `zukuenftig` oder Verkäufer hat
nichts gezahlt), wird der Auszahlungslauf-Hinweis weggelassen.

---

## 4. Verkäufer-Erstattung — detaillierter Workflow

### 4.1 Trigger und Übergabe an Auszahlungs-Service

Der Wizard erzeugt in Schritt 6 einen `Auszahlungslauf` mit
`status='vorschau'`. Der bestehende `auszahlungs_service` (Nebenbuch-
Spec Kap. 10.5, 12.2) wird **erweitert**, um diesen Typ zu verarbeiten.

### 4.2 Buchungslogik bei Erstattungs-Abgang (camt.053)

Beim Abgang vom Bewirtschaftungskonto:

```
Soll  41900  Erlöse Hausgeld VZ                      200,00
Soll  41911  Erlöse Rücklage I                        80,00     (anteilig)
Soll  41912  Erlöse Rücklage II                       30,00     (anteilig)
Haben 18000  Bank 1 Bewirtschaftung                  310,00
```

Wird die Erstattung pro Sollstellung gebucht, müssen die ursprünglich
**im Haben gebuchten Erlöskonten** in derselben Aufteilung wieder ins
Soll gebucht werden. Dazu liest der Service die ursprünglichen
`SollstellungZahlung`-Einträge:

```python
def buche_erstattung_abgang(sollstellung, betrag, bankkonto, user):
    """
    Erstattet eine zuvor eingegangene Hausgeldzahlung. Bucht die
    ursprünglichen Erlöskonten anteilig im Soll gegen Bank im Haben.
    """
    urspruengliche_zahlungen = SollstellungZahlung.objects.filter(
        sollstellung=sollstellung,
        storniert_am__isnull=True,
    )
    # Anteile der Splits aus ursprünglicher Tilgung rekonstruieren
    anteile = {}
    for z in urspruengliche_zahlungen:
        if z.split:
            anteile[z.split.erloeskonto] = anteile.get(z.split.erloeskonto, 0) + z.betrag
        else:
            # Sonderumlage/Abrechnung: ein Erlöskonto
            anteile[sollstellung.ba.erloeskonto_default] = z.betrag

    # Bei Teilerstattung: anteilig proportional kürzen (sollte nicht
    # vorkommen, da Erstattungsbetrag = ist_betrag)
    erzeuge_buchung(
        soll=anteile,                # Erlöskonten
        haben={bankkonto: betrag},   # Bank
        beleg=f"Erstattung Hausgeld {sollstellung.periode}",
        user=user,
    )
```

Parallel im Nebenbuch:

- `SollstellungZahlung`-Einträge der ursprünglichen Tilgung werden als
  `storniert` markiert (nicht löschen, GoBD-konformer Audit).
- `ist_betrag` der Sollstellung wird auf 0 zurückgesetzt.
- Sollstellung kann jetzt regulär storniert werden — der Service ruft
  automatisch `storniere_sollstellung(ss, grund=f"Eigentümerwechsel
  {wechsel.stichtag} — Erstattung", user)` auf.
- Status der Sollstellung: `storniert`.

### 4.3 Rückläufer (Bank meldet IBAN ungültig)

Identisch zum Rückläufer-Verhalten in Nebenbuch-Spec Kap. 10.5:

1. GoBD-Storno der Erstattungs-Buchung (`Soll 18000 / Haben 41xxx`)
2. Im Nebenbuch: `SollstellungZahlung`-Storno-Markierungen zurückrollen,
   Sollstellung-`ist_betrag` wieder auf ursprünglichen Wert, Status
   zurück auf `ausgeglichen`/`teilbezahlt`.
3. Sollstellung **bleibt nicht-storniert** (denn die Erstattung war
   nicht erfolgreich).
4. Frontoffice-Aufgabe an Buchhalter mit Verweis auf den
   `EigentuemerwechselVorgang`.

### 4.4 Edge Case — Verkäufer hat per Lastschrift gezahlt, Wechsel rückwirkend

Wenn der Verkäufer per SEPA-Lastschrift gezahlt hat und die Zahlung
nicht älter als 8 Wochen ist, könnte rein theoretisch der **Verkäufer
selbst** die Lastschrift bei seiner Bank zurückgeben (R-Transaction).
Dieser Fall ist von der Erstattung **zu trennen**:

- Wenn der Wizard läuft, **bevor** ein R-Transaction-Eingang vermerkt
  ist → System geht von „bezahlt" aus und erstattet aktiv (dieser
  Workflow).
- Wenn nach dem Wizard noch eine R-Transaction eingeht → standard
  Rücklastschrift-Hook (Nebenbuch-Spec Kap. 11) greift, die
  ursprüngliche Tilgung wird zurückgerollt. **Die bereits ausgelöste
  Erstattung an den Verkäufer ist dann eine unberechtigte
  Doppel-Erstattung** und muss manuell zurückgefordert werden.

→ **Frontoffice-Warnung im Wizard Schritt 4b** bei Sollstellungen, die
per Lastschrift jünger als 56 Tage getilgt wurden:

> ⚠ Diese Zahlung wurde vor weniger als 8 Wochen per Lastschrift
> eingezogen. Der Verkäufer könnte die Lastschrift bei seiner Bank
> zurückgeben. Empfehlung: Erstattung erst auslösen, wenn die
> Rückgabefrist (8 Wochen ab Lastschriftbuchung) abgelaufen ist —
> oder Vorgehen mit Verkäufer abstimmen.

Hard-Stop ist es **nicht** — der Buchhalter trifft die fachliche
Entscheidung.

---

## 5. Nachhol-Sollstellungen Käufer — Karenz-Mechanik

### 5.1 Anlage

Wie in Kap. 3.7 Schritt 6 beschrieben: Pro Periode von
`wirkungs_periode` bis einschließlich dem **Monat vor dem aktuellen
Lauf** wird eine reguläre Hausgeld-Sollstellung angelegt — mit dem
Unterschied:

- `mahnkarenz_bis = heute + 14 Tage`
- `nachhol_aus_wechsel = wechsel_vorgang`

OPOS-Nr. und Splits werden wie bei regulärem Lauf erzeugt; die
Sollstellung ist im Lastschriftlauf **sofort einzugsfähig** (Lastschrift
≠ Mahnung) — die Karenz wirkt nur gegenüber dem Mahnwesen.

### 5.2 Wirkung im Mahnwesen

Die Mahnwesen-Spec liest `faellig_am` und `mahnkarenz_bis` als
Filter:

```python
mahnreif = HausgeldSollstellung.objects.filter(
    status_cached__in=["offen", "teilbezahlt"],
    faellig_am__lt=heute - timedelta(days=MAHN_KARENZ_GLOBAL),
    storniert_am__isnull=True,
).filter(
    Q(mahnkarenz_bis__isnull=True) | Q(mahnkarenz_bis__lt=heute)
)
```

`MAHN_KARENZ_GLOBAL` ist die Standard-Karenz (z.B. 7 Tage), die für
alle Sollstellungen gilt. `mahnkarenz_bis` ist der OP-spezifische
Override und überschreibt die globale Karenz nach oben.

### 5.3 Wirkung in der Jahresabrechnung

Nachhol-Sollstellungen zählen für die Einzelabrechnung des **Käufers**
in der Spalte „VZ Soll" — siehe Ausgangsspec Kap. 6.1 und Nebenbuch-
Spec Kap. 13.2 (Anpassung Einzelabrechnung-Generator). Die Spec
„Eine Abrechnung je Einheit, Adressat = aktueller Eigentümer" bleibt
unverändert; durch die rückwirkende Käufer-Sollstellung ist der
Käufer auch fachlich korrekt der Schuldner für das gesamte Jahr.

---

## 6. Service-Architektur

### 6.1 Übersicht

```
apps/buchhaltung/services/
├── eigentuemerwechsel_service.py   # NEU
└── auszahlungs_service.py          # Erweiterung um typ='verkaeufer_erstattung'
```

### 6.2 `eigentuemerwechsel_service` — Funktionen

| Funktion | Zweck |
|---|---|
| `analysiere_wechsel(einheit, stichtag) -> WechselAnalyse` | Liest Verkäufer-EV, ermittelt `wirkungs_periode`, klassifiziert Verkäufer-Sollstellungen ab Wirkungsperiode in Storno-/Erstattungs-Buckets. Read-only. |
| `commite_wechsel(wechsel_vorgang, schritt_5_entscheidungen, user) -> dict` | Atomare Ausführung aller Schritte aus Kap. 3.7. Gibt Auszahlungslauf-ID + Liste angelegter Sollstellungs-IDs zurück. |
| `bestimme_wirkungs_periode(stichtag) -> date` | Helper: nächster Monatserster ≥ stichtag. |
| `nachhol_perioden(wirkungs_periode, heute) -> List[date]` | Helper: alle Monatserster von wirkungs_periode bis ausschließlich dem aktuellen Monat. |

### 6.3 `auszahlungs_service` — Erweiterung

Neue Funktion:

```python
def erstelle_verkaeufer_erstattungslauf(
    wechsel: EigentuemerwechselVorgang,
    positionen: List[tuple[HausgeldSollstellung, Decimal]],
    user: User,
) -> Auszahlungslauf:
    """
    Erzeugt einen Auszahlungslauf vom Typ verkaeufer_erstattung.
    Positionen = Liste (sollstellung, betrag) — Betrag = ist_betrag.
    pain.001 wird beim Commit (manueller Workflow-Schritt) generiert.
    """
```

Bestehende `vorschau_auszahlungslauf`, `commite_auszahlungslauf`,
`generiere_pain001` werden erweitert um den Typ-Switch.

`verbuche_auszahlung_abgang` wird ebenfalls erweitert: Bei
`typ='verkaeufer_erstattung'` ruft sie `buche_erstattung_abgang`
(Kap. 4.2) statt der Standard-Guthabenbuchung auf.

### 6.4 Pseudocode — `commite_wechsel`

```python
@transaction.atomic
def commite_wechsel(wechsel, entscheidungen, user) -> dict:
    """
    Führt den gesamten Wechselvorgang atomar aus.

    entscheidungen = {
        "kaeufer_person_id": UUID,
        "kaeufer_iban": str,
        "kaeufer_sepa_mandat_id": UUID | None,
        "hausgeld_je_ba": {ba_code: Decimal},
        "stornieren_ids": [UUID, ...],            # Sollstellungs-IDs
        "erstatten": [(UUID, Decimal), ...],      # (Sollstellungs-ID, ist_betrag)
        "verkaeufer_iban": str | None,            # bei Erstattung Pflicht
    }
    """
    verkaeufer_ev = wechsel.verkaeufer_ev
    wirkungs_periode = wechsel.wirkungs_periode

    # 1) Verkäufer-EV beenden
    verkaeufer_ev.ende = wechsel.stichtag - timedelta(days=1)
    verkaeufer_ev.save(update_fields=["ende"])

    # 2) Käufer-EV anlegen
    kaeufer_ev = EigentumsVerhaeltnis.objects.create(
        einheit=wechsel.einheit,
        person_id=entscheidungen["kaeufer_person_id"],
        beginn=wirkungs_periode,
        ende=None,
        vorgaenger=verkaeufer_ev,
        wechsel_grund=wechsel.art,
    )
    wechsel.kaeufer_ev = kaeufer_ev

    # 3) HausgeldHistorie für Käufer
    for ba_code, betrag in entscheidungen["hausgeld_je_ba"].items():
        if betrag > 0:
            HausgeldHistorie.objects.create(
                eigentumsverhaeltnis=kaeufer_ev,
                ba=Buchungsart.objects.get(code=ba_code),
                betrag=betrag,
                gueltig_ab=wirkungs_periode,
                erstellt_von=user,
            )

    # 4) Storno-Liste
    for ss_id in entscheidungen["stornieren_ids"]:
        ss = HausgeldSollstellung.objects.select_for_update().get(id=ss_id)
        assert ss.ist_betrag == 0
        storniere_sollstellung(
            ss, grund=f"Eigentümerwechsel {wechsel.stichtag}", user=user
        )

    # 5) Erstattungs-Auszahlungslauf vorbereiten
    auszahlungslauf = None
    if entscheidungen["erstatten"]:
        if not entscheidungen.get("verkaeufer_iban"):
            raise ValidationError("Verkäufer-IBAN fehlt für Erstattung.")

        positionen = []
        gesamt = Decimal("0")
        for ss_id, ist_betrag in entscheidungen["erstatten"]:
            ss = HausgeldSollstellung.objects.get(id=ss_id)
            assert ss.ist_betrag == ist_betrag  # Konsistenz-Check
            positionen.append((ss, ist_betrag))
            gesamt += ist_betrag

        auszahlungslauf = erstelle_verkaeufer_erstattungslauf(
            wechsel=wechsel, positionen=positionen, user=user
        )
        wechsel.verkaeufer_erstattung_betrag = gesamt
        wechsel.verkaeufer_erstattung_iban = entscheidungen["verkaeufer_iban"]
        wechsel.auszahlungslauf = auszahlungslauf

    # 6) Nachhol-Sollstellungen für Käufer
    karenz_bis = timezone.now().date() + timedelta(days=14)
    angelegte_nachhol = []
    for periode in nachhol_perioden(wirkungs_periode, timezone.now().date()):
        ss = lege_hausgeld_sollstellung_an(
            ev=kaeufer_ev,
            periode=periode,
            betraege_je_ba=entscheidungen["hausgeld_je_ba"],
            lauf=None,                       # kein Massenlauf-Header
            user=user,
            mahnkarenz_bis=karenz_bis,       # neu
            nachhol_aus_wechsel=wechsel,     # neu
        )
        angelegte_nachhol.append(ss.id)

    # 7) Wechsel abschließen
    wechsel.abgeschlossen_am = timezone.now()
    wechsel.abgeschlossen_von = user
    wechsel.save()

    return {
        "wechsel_id": wechsel.id,
        "kaeufer_ev_id": kaeufer_ev.id,
        "auszahlungslauf_id": auszahlungslauf.id if auszahlungslauf else None,
        "nachhol_sollstellungs_ids": angelegte_nachhol,
        "stornierte_sollstellungs_ids": entscheidungen["stornieren_ids"],
    }
```

---

## 7. Anzupassende bestehende Komponenten

| Element | Anpassung |
|---|---|
| `HausgeldSollstellung` | Felder `mahnkarenz_bis`, `nachhol_aus_wechsel` ergänzen (Migration) |
| `EigentumsVerhaeltnis` | Felder `wechsel_grund`, `notarurkunde`, `vorgaenger` ergänzen (Migration) |
| `Auszahlungslauf` | Felder `typ`, `eigentuemerwechsel` ergänzen; `wirtschaftsjahr` nullable machen (Migration) |
| `sollstellung_service.lege_hausgeld_sollstellung_an` | Optionale Parameter `mahnkarenz_bis` und `nachhol_aus_wechsel` annehmen |
| `auszahlungs_service` | Erweiterung um `typ='verkaeufer_erstattung'` inkl. `buche_erstattung_abgang` |
| Wizard Kap. 5.2 in Ausgangsspec v1.1 | Komplett ersetzen durch diese Spec |
| Frontend: Eigentümerwechsel-Wizard | Neuimplementierung der 6 Schritte |

---

## 8. Aufgaben für Claude Code

> **Hinweis an Claude Code:** Phase-Gates beachten — nach Phase B
> **STOP** und manuelle Bestätigung abwarten, bevor Phase C ausgeführt
> wird. Alle Geschäftslogik **ausschließlich** in `services/`. Tests
> nach jeder Phase laufen lassen.

### Phase A — Datenmodell-Anpassungen

1. Migration `apps/buchhaltung/migrations/00XX_eigentuemerwechsel_modell.py`:
   - Felder an `EigentumsVerhaeltnis`: `wechsel_grund`, `notarurkunde`, `vorgaenger`
   - Felder an `HausgeldSollstellung`: `mahnkarenz_bis`, `nachhol_aus_wechsel`
   - Felder an `Auszahlungslauf`: `typ` (default `abrechnungsguthaben`), `eigentuemerwechsel`; `wirtschaftsjahr` nullable
   - Neues Modell `EigentuemerwechselVorgang` mit allen Feldern aus Kap. 2.3
2. Unit-Tests für Constraints (z.B. UniqueConstraint Einheit+Stichtag).

### Phase B — Service-Schicht

1. `apps/buchhaltung/services/eigentuemerwechsel_service.py`:
   - `analysiere_wechsel`, `commite_wechsel`, `bestimme_wirkungs_periode`, `nachhol_perioden`
2. `apps/buchhaltung/services/auszahlungs_service.py`:
   - Erweiterung um `typ='verkaeufer_erstattung'`
   - Neue Funktion `erstelle_verkaeufer_erstattungslauf`
   - Neue Funktion `buche_erstattung_abgang`
   - Type-Switch in `vorschau_auszahlungslauf`, `commite_auszahlungslauf`, `generiere_pain001`, `verbuche_auszahlung_abgang`
3. `apps/buchhaltung/services/sollstellung_service.py`:
   - `lege_hausgeld_sollstellung_an` um optionale Parameter
     `mahnkarenz_bis` und `nachhol_aus_wechsel` erweitern
4. Unit-Tests:
   - `bestimme_wirkungs_periode` (Stichtag = 1.; Stichtag = 15.; Stichtag = Monatsletzter)
   - `analysiere_wechsel` (alle drei Buckets, leerer Bucket)
   - `commite_wechsel` happy path
   - `commite_wechsel` ohne Erstattung
   - `commite_wechsel` ohne Storno
   - `commite_wechsel` ohne Nachhol (Fall `zukuenftig`)
   - `buche_erstattung_abgang` produziert korrekte Buchungssätze
     (Erlöskonten anteilig Soll, Bank Haben)

### ⛔ STOP — Manuelle Bestätigung erforderlich

> Vor Phase C: End-to-End-Test über die Service-API mit einem
> Test-Objekt manuell durchgespielt, alle vier Akzeptanzkriterien aus
> Kap. 9 grün. Danach Freigabe abwarten.

### Phase C — Frontend-Wizard

1. Wizard-Komponenten gemäß 6 Schritten aus Kap. 3.
2. Wiederverwendung der Person-Such-Komponente aus WEG-Objektanlage Schritt 4.
3. Schritt 4: Tabellen mit Checkbox-Steuerung, Live-Summe in Footer.
4. Schritt 5: Read-only Vorschau-Layout.
5. API-Endpunkte:
   - `GET /eigentuemerwechsel/{id}/analyse/` → `WechselAnalyse`
   - `POST /eigentuemerwechsel/{id}/commit/` → Commit-Ergebnis
6. Integration: nach Commit zur Auszahlungslauf-Freigabe-Maske leiten,
   falls Auszahlungslauf erzeugt wurde.

### Phase D — Cleanup

1. Alte Wizard-Implementation gem. Ausgangsspec Kap. 5.2 entfernen:
   - Schritte 3 (Abgrenzungsbuchung) und 4 (Personenkonto archivieren)
     komplett raus
   - JSONField-Zwischenstände in Datenbank für genau diesen Wizard-Typ
     migrieren (sollte greenfield-bedingt leer sein)
2. Hinweis-Doku-Update: Eintrag in Ausgangsspec markieren als
   „ersetzt durch CLAUDE_CODE_ANLEITUNG_EIGENTUEMERWECHSEL_v1_0.md".

---

## 9. Akzeptanzkriterien (Smoke-Test vor Go-Live)

Manueller End-to-End-Test mit einem Test-Objekt:

1. **Sauberer Wechsel (Fall `zukuenftig`):**
   Stichtag = heute + 20 Tage. Schritt 4 wird übersprungen.
   Nach Commit: Verkäufer-EV hat `ende = stichtag - 1 Tag`, Käufer-EV
   beginnt zur nächsten `wirkungs_periode`, HausgeldHistorie für Käufer
   ist gesetzt. **Keine** Sollstellungs-Stornos, **keine** Nachhol-
   Sollstellungen, **kein** Auszahlungslauf.

2. **Rückwirkender Wechsel ohne gezahlte Sollstellungen:**
   Stichtag = vor 2 Monaten, Verkäufer hatte 2 offene (`ist_betrag=0`)
   Sollstellungen. Wizard listet beide in Bucket 4a, alle storniert.
   Käufer bekommt 2 Nachhol-Sollstellungen mit korrekter Periode und
   `mahnkarenz_bis = heute + 14 Tage`. Kein Auszahlungslauf.

3. **Rückwirkender Wechsel mit Voll-Tilgung Verkäufer:**
   Stichtag = vor 2 Monaten, Verkäufer hat 2 Sollstellungen voll
   gezahlt. Wizard listet beide in Bucket 4b. Nach Commit: Auszahlungs-
   lauf `typ='verkaeufer_erstattung'` mit 2 Positionen, Summe = beide
   `ist_betrag`-Beträge. Sollstellungen sind noch **nicht** storniert
   (warten auf camt.053-Abgang). Käufer hat 2 Nachhol-Sollstellungen.

4. **Auszahlungslauf simulieren:**
   Auszahlungslauf aus Test 3 commiten → pain.001-XML enthält 2
   `<CdtTrfTxInf>` mit Verkäufer-IBAN, korrekten Beträgen, EndToEndId
   `{OPOS_NR}-AUSZ`, Verwendungszweck enthält „Erstattung Hausgeld".
   Simulierten camt.053-Abgang einspielen → pro Position:
   Buchungssatz mit Erlöskonten (`41900`, `41911`, `41912`)
   anteilig im **Soll**, Bank `18000` im **Haben**. `SollstellungZahlung`-
   Einträge der ursprünglichen Tilgung als `storniert` markiert,
   Sollstellung `ist_betrag = 0` und Status `storniert`.

5. **Mahnkarenz wirkt:**
   Direkt nach Test 3: Mahnwesen-Auswahl-Query für mahnreife OPs
   liefert **keine** der Nachhol-Sollstellungen, auch wenn ihre
   `periode` und `faellig_am` weit in der Vergangenheit liegen. Nach
   `mahnkarenz_bis + 1 Tag` (simuliertes Datum) erscheinen sie regulär.

6. **Verkäufer-IBAN fehlt:**
   Erstattungs-Szenario, Verkäufer-Person hat keine IBAN → Wizard
   Schritt 4 zeigt Hard-Stop mit klarer Fehlermeldung; Commit ist nicht
   möglich.

7. **Doppelter Wechsel verhindert:**
   Zweiter Wizard mit gleicher Einheit + gleichem Stichtag wird durch
   UniqueConstraint abgewiesen.

8. **R-Transaction-Warnung:**
   Erstattungs-Szenario, eine Sollstellung wurde vor 30 Tagen per
   Lastschrift getilgt → Wizard Schritt 4b zeigt das Warnungs-Banner
   aus Kap. 4.4 (Soft-Warning, kein Hard-Block).

Wenn alle 8 Punkte grün sind, ist diese Spec implementierungs-vollständig.

---

## 10. Schnittstellen zu anderen Specs

### 10.1 Nebenbuch-Spec v1.1

Diese Spec ist eine **echte Erweiterung** der Nebenbuch-Spec. Sie:

- nutzt `HausgeldSollstellung`, `SollstellungSplit`, `SollstellungZahlung`,
  `Auszahlungslauf` unverändert in ihrer Grundmechanik
- erweitert `Auszahlungslauf` um `typ` und `eigentuemerwechsel` (FK)
- nutzt `sollstellung_service.storniere_sollstellung` und
  `sollstellung_service.lege_hausgeld_sollstellung_an` (mit erweiterter
  Parameterliste)
- nutzt die OPOS-Nr.-Vergabe unverändert (Suffix `-AUSZ` wiederverwendet)

### 10.2 Mahnwesen-Spec (geplant)

Hooks, die diese Spec für das Mahnwesen bereitstellt:

- Feld `HausgeldSollstellung.mahnkarenz_bis` mit dokumentierter
  Filter-Semantik (Kap. 5.2)
- Feld `HausgeldSollstellung.nachhol_aus_wechsel` für mögliche
  Sondertexte im Mahnschreiben („Diese Forderung stammt aus einem
  rückwirkenden Eigentümerwechsel...") — Implementierung in der
  Mahnwesen-Spec, nicht hier.

### 10.3 Jahresabrechnung

Keine direkten Änderungen an der Jahresabrechnung-Spec. Der bestehende
Mechanismus „Adressat = aktueller Eigentümer zum Erstellungsdatum"
greift unverändert. Nachhol-Sollstellungen zählen in der Hausgeld-
Spalte des Käufers korrekt mit, da sie reguläre `HausgeldSollstellung`-
Einträge sind.

---

**Ende der Spezifikation.**
