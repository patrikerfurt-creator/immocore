# IMMOCORE — Jahresabrechnung (HGA) | Claude Code Prompt v1.0

**IMMOCORE** — *Webbasiertes Immobilienverwaltungssystem*
**Modul:** Jahresabrechnung — Wizard, Berechnungslogik, Nebenbuch-Anbindung
**Demme Immobilien Verwaltung GmbH** — Coventrystraße 32, 65934 Frankfurt am Main
**Version:** 1.0 | **Stand:** Juli 2026
**KI-Modell:** keines — dieses Modul enthält keine KI-gestützte Erkennung oder Extraktion

---

## 0. Vorprüfung vor Implementierung (HALT-Gate)

Diese Spec **löst Kap. 5.3/6 der Ausgangsspezifikation ab** und ersetzt
dort den Buchungsschritt (Schritt 8), der noch von einer direkten
Sachkontenbuchung `XXXX.950` ausgeht. Diese Annahme ist durch das
Hausgeld-Nebenbuch v1.1 überholt — dort entsteht bei
`abrechnungsergebnis` keine Sachkontenbuchung, sondern eine
`HausgeldSollstellung`.

**Bevor Claude Code mit Phase A beginnt, müssen folgende Punkte am
realen Code-Stand verifiziert werden (Phase-0-Prinzip):**

| # | Frage | Grund |
|---|---|---|
| 1 | Existiert bereits ein `Wirtschaftsplan`-Model mit Soll-Ansätzen je Konto, oder wird der Vergleich in Schritt 3 (Kostenstellen-Übersicht) noch aus einer anderen Quelle gespeist? | Kap. 6.2 setzt Wirtschaftsplan-Ansätze voraus; in den bisher gesichteten Specs ist kein `Wirtschaftsplan`-Modell auffindbar (nur als Abhängigkeit in `CLAUDE_CODE_ANLEITUNG_WIEDERKEHRENDE_BUCHUNGEN_v1_0.md` Kap. 17 als künftige Spec erwähnt) |
| 2 | Ist bereits eine PDF-Erzeugungs-Bibliothek im Projekt etabliert (z.B. WeasyPrint, ReportLab)? | Wizard-Schritt 7 (PDF-Vorschau) benötigt eine konkrete Rendering-Pipeline; diese Spec definiert nur die Datenstruktur, nicht die Bibliothekswahl |
| 3 | Ist `HausgeldHistorie` bereits vollständig auf das `ba`-Feld migriert (Nebenbuch-Spec Kap. 13.2, Schritt 3)? | Ohne diese Migration lässt sich das Hausgeld-Soll je BA in Schritt 6 nicht sauber ableiten |
| 4 | Ist `Wirtschaftsjahr` (siehe `IMMOCORE_ClaudeCode_Wirtschaftsjahre_v1_0.md`) bereits produktiv als FK-Ebene zwischen `Objekt` und `Konto` eingezogen? | Diese Spec geht davon aus, dass `Jahresabrechnung.wirtschaftsjahr` auf das WJ-Modell zeigt, nicht auf ein rohes Jahresfeld |

Falls einer dieser Punkte negativ beantwortet wird, ist vor Phase A ein
kurzer Abstimmungs-Zwischenschritt mit Patrik nötig — **kein
automatisches Weiterarbeiten mit Annahmen.**

**Bereits vom Product Owner entschiedene Scope-Fragen (verbindlich):**

- **Korrekturabrechnung** ist **nicht** Teil dieser Spec. Kap. 6.1 der
  Ausgangsspezifikation ("Korrekturen erfordern eine
  Korrekturabrechnung") bleibt als Prinzip stehen, wird aber erst in
  einer eigenen Folgespec (`Korrekturabrechnung_v1.0`) spezifiziert.
  Diese Spec deckt ausschließlich die reguläre Erst-Jahresabrechnung ab.
- **Auszahlungslauf für Guthaben** wird **bewusst nicht** automatisch
  aus Schritt 8 heraus angestoßen. Die Jahresabrechnung schließt mit
  Schritt 8 vollständig ab (Sperre + Sollstellungslauf-Erzeugung); der
  Auszahlungslauf (Nebenbuch-Spec Kap. 10.5) ist ein separater, manuell
  vom Verwalter gestarteter Folgeschritt — auf einer eigenen Seite,
  nicht im Wizard.
- **E898-Anlagen (Techem-Einzelabrechnungsbilder)** sind **nicht** Teil
  dieser Spec (siehe Kap. 13 „Ausdrücklich nicht Teil dieser Spec").

---

## 1. Zweck dieses Dokuments

Diese Spezifikation macht den Jahresabrechnungs-Wizard aus
`IMMOCORE_Ausgangsspezifikation_v1.1.docx` (Kap. 5.3/6)
implementierungsreif und **korrigiert Schritt 8**, damit er mit dem
Hausgeld-Nebenbuch (`CLAUDE_CODE_ANLEITUNG_HAUSGELD_NEBENBUCH_v1_1.md`)
konsistent ist: Statt einer Sachkontenbuchung `Soll XXXX.950 / Haben
Ausgleichskonto` entsteht bei Freigabe eine `HausgeldSollstellung` vom
Typ `abrechnungsergebnis` je Einheit, erzeugt über den bereits in der
Nebenbuch-Spec vorgesehenen Service `sollstellungslauf_service.
run_abrechnungsergebnis()`.

**Bezug:**
- `IMMOCORE_Ausgangsspezifikation_v1.1.docx` (Kap. 4.9, 5.3, 6 — Grundlage dieser Spec)
- `CLAUDE_CODE_ANLEITUNG_HAUSGELD_NEBENBUCH_v1_1.md` (Kap. 3.3, 10.5, 12, 13.2 — Zielservice für Schritt 8)
- `IMMOCORE_ClaudeCode_Wirtschaftsjahre_v1_0.md` (WJ-gebundener Kontenrahmen, Objekt→WJ→Konto)
- `CLAUDE_CODE_ANLEITUNG_EIGENTUEMERWECHSEL_v1_0.md` (Kap. 5.3 — Wirkung von Nachhol-Sollstellungen auf „VZ Soll")
- `CLAUDE_CODE_ANLEITUNG_VERTEILERSCHLUESSEL_IMPORT_v1_0.md` (VS-Werte je Einheit, `EinheitVerbrauch`, `KontoVerteilerSchluessel`)
- `Musterkontenrahmen_WEG.xlsx`, `Verteilerschlüssel.xlsx`, `Abrechnungsarten.xlsx`

**Ausdrücklich nicht Teil dieser Spec (eigene Specs):**
- Korrekturabrechnung (siehe Entscheidung Kap. 0)
- Auszahlungslauf-Trigger/-UI selbst — nur der Übergabepunkt wird hier definiert (Kap. 8.4); Ausführung ist bereits in der Nebenbuch-Spec spezifiziert
- E898-Anlagen / Techem-Einzelabrechnungsbild (siehe Kap. 13)
- Wirtschaftsplan-Erstellung und -Genehmigung selbst — wird als bestehend vorausgesetzt (siehe Kap. 0, Punkt 1)
- Beschlussprotokoll-Anbindung / Versammlungsbeschluss zur Genehmigung der Abrechnung (DMS/Beschluss-Modul, separat)
- PDF-Versand an Eigentümer (Ausgangsspec Kap. 5.3 Schritt 8: „PDF-Versand Phase 2")

---

## 2. Kernkonzept

### 2.1 Zwei-Ebenen-Modell

```
Jahresabrechnung (1) ─── (N) EinzelAbrechnung
   objekt, wirtschaftsjahr              einheit, eigentuemer (Snapshot)
   erstellungsdatum                     eigentumsverhaeltnis (Snapshot)
   status: entwurf│freigegeben│gesperrt hausgeld_soll_gesamt
   freigegeben_am, freigegeben_von      kostenanteil_gesamt
                                        abrechnungsergebnis
                                        positionen (JSON)
                                        ruecklagen (JSON)
                                        sollstellung (FK, nullable)
                                        dokument (FK, nullable)
```

Die `Jahresabrechnung` ist der Container je Objekt und Wirtschaftsjahr;
pro Einheit entsteht darunter genau eine `EinzelAbrechnung` — auch bei
mehrfachem Eigentümerwechsel im Jahr (Ausgangsspec Kap. 6.1).

### 2.2 Grundprinzipien (unverändert aus Ausgangsspec Kap. 6.1)

| Prinzip | Regel |
|---|---|
| Eine Abrechnung je Einheit | Pro Einheit und Abrechnungszeitraum genau eine `EinzelAbrechnung` |
| Aktueller Eigentümer | Adressat ist der Eigentümer zum Erstellungsdatum (Snapshot) |
| Soll-Basis | Grundlage sind Wirtschaftsplan-Ansätze, nicht tatsächliche Zahlungseingänge |
| Unveränderlichkeit | Freigegebene Abrechnung wird gesperrt (read-only); Korrekturen nur über eigene Folgespec |

### 2.3 Was sich gegenüber der Ausgangsspezifikation ändert

| Element | Ausgangsspec (Kap. 5.3/6) | Diese Spec |
|---|---|---|
| Schritt 8 Buchung | „Ergebnis auf `XXXX.950` buchen" | Aufruf `sollstellungslauf_service.run_abrechnungsergebnis(objekt, wj, user)` — erzeugt `HausgeldSollstellung(sollstellungs_typ='abrechnungsergebnis')` je Einheit, **keine** Sachkontenbuchung |
| `EinzelAbrechnung.gebucht` | Boolean „gebucht=True wenn .950-Buchung ausgeführt" | Ersetzt durch `EinzelAbrechnung.sollstellung` (FK, nullable) — Vorhandensein der FK **ist** der Statusindikator |
| Guthaben-Verrechnung | nicht spezifiziert | Läuft **nicht** automatisch — folgt Nebenbuch-Spec Kap. 3.3/10.5: negative Sollstellung → separater, manuell gestarteter Auszahlungslauf |
| „VZ Soll" in Schritt 6 | implizit aus Sachkonten | Explizit aus Nebenbuch: `SUM(HausgeldSollstellung.soll_betrag WHERE typ='hausgeld')` je EV im WJ (Nebenbuch-Spec Kap. 13.2) |

---

## 3. Datenmodell

### 3.1 `Jahresabrechnung`

| Feld | Typ | Pflicht | Anmerkung |
|---|---|---|---|
| `id` | UUID (PK) | Ja | |
| `objekt` | FK → Objekt | Ja | |
| `wirtschaftsjahr` | FK → Wirtschaftsjahr | Ja | muss `status='offen'` haben bei Anlage |
| `erstellungsdatum` | DateField | Ja | bestimmt den „aktuellen Eigentümer" je Einheit (Kap. 6.1) |
| `status` | Enum: `entwurf` / `freigegeben` / `gesperrt` | Ja | Default `entwurf`; `gesperrt` = unveränderlich |
| `prozess` | FK → Prozess | Ja | Wizard-Zwischenstand (Kap. 5 Ausgangsspec — Prozess-Engine) |
| `freigegeben_am`, `freigegeben_von` | DateTimeField / FK → User | Nein | gesetzt bei Statuswechsel `entwurf → freigegeben` (Schritt 8) |
| `sollstellungslauf` | FK → Sollstellungslauf, nullable | Nein | gesetzt nach erfolgreichem Aufruf `run_abrechnungsergebnis` |
| `erstellt_am`, `erstellt_von` | | | Standard-Audit |

**Constraints:**

```python
class Meta:
    constraints = [
        models.UniqueConstraint(
            fields=['objekt', 'wirtschaftsjahr'],
            condition=~Q(status='storniert'),
            name='jahresabrechnung_unique_je_wj'
        ),
    ]
```

Es gibt bewusst **keinen** Storno-Status in dieser Spec-Version — eine
fehlerhafte `entwurf`-Abrechnung wird gelöscht, keine gesperrte
Abrechnung kann storniert werden (dafür ist die Korrekturabrechnungs-
Folgespec zuständig).

### 3.2 `EinzelAbrechnung`

| Feld | Typ | Pflicht | Anmerkung |
|---|---|---|---|
| `id` | UUID (PK) | Ja | |
| `jahresabrechnung` | FK → Jahresabrechnung (CASCADE) | Ja | |
| `einheit` | FK → Einheit | Ja | |
| `eigentuemer` | FK → Person | Ja | Snapshot zum `erstellungsdatum` — bleibt korrekt nach späterem Eigentümerwechsel |
| `eigentumsverhaeltnis` | FK → EigentumsVerhaeltnis | Ja | Snapshot-Referenz für Nebenbuch-Verknüpfung |
| `hausgeld_soll_gesamt` | DecimalField(14,2) | Ja | Σ `HausgeldSollstellung.soll_betrag` (Typ `hausgeld`) im WJ, siehe Kap. 6.2 |
| `kostenanteil_gesamt` | DecimalField(14,2) | Ja | Σ Ist-Kosten × Verteilerschlüssel-Anteil |
| `abrechnungsergebnis` | DecimalField(14,2) | Ja | `kostenanteil_gesamt - hausgeld_soll_gesamt`; positiv = Nachzahlung, negativ = Guthaben |
| `positionen` | JSONField | Ja | Detailpositionen je Kostenstelle (Konto, Bezeichnung, Gesamtkosten, VS-Anteil, Einheit-Anteil) für PDF |
| `ruecklagen` | JSONField | Ja | je Rücklage: Anfangsbestand, Zuführung, Entnahme, Endbestand, Anteil Eigentümer (Kap. 6.4) |
| `sollstellung` | FK → HausgeldSollstellung, nullable | Nein | gesetzt nach Schritt 8 — Verknüpfung zur Nebenbuch-Sollstellung |
| `dokument` | FK → Dokument, nullable | Nein | gesetzt nach PDF-Erzeugung in Schritt 7/8 |
| `hinweis_eigentuemerwechsel` | Boolean | Ja | Default `False`; steuert Fußnote im PDF (Kap. 6.3) |

**Constraints:**

```python
class Meta:
    constraints = [
        models.UniqueConstraint(
            fields=['jahresabrechnung', 'einheit'],
            name='einzelabrechnung_unique_je_einheit'
        ),
    ]
```

**Invariante (Service-Ebene, `test_invariants.py`):**

```
abrechnungsergebnis == kostenanteil_gesamt - hausgeld_soll_gesamt
```

---

## 4. Berechnungslogik

### 4.1 Formel je Einheit (unverändert aus Ausgangsspec Kap. 6.2)

```
Abrechnungsergebnis =
    SUMME( Gesamtkosten_Konto_k  x  Anteil_Einheit_k )
    minus
    Hausgeld-Soll (anteilig bei Plan-Aenderung im Jahr)

Anteil_Einheit_k = Verteilerschluessel_k(Einheit)
                 = MEA | Flaeche_qm | Kopfanteil  (je nach Konto)

Hausgeld-Soll bei Plan-Aenderung:
    Monate mit altem Plan x altes Soll
  + Monate mit neuem Plan x neues Soll
  = Jahres-Soll gesamt
```

### 4.2 Herkunft von „Hausgeld-Soll" (Nebenbuch-Anbindung, NEU)

`hausgeld_soll_gesamt` wird **nicht** aus Sachkontenumsätzen abgeleitet
(wie in der Ausgangsspec implizit angenommen), sondern direkt aus dem
Nebenbuch:

```python
def berechne_hausgeld_soll(ev: EigentumsVerhaeltnis, wj: Wirtschaftsjahr) -> Decimal:
    """
    Summe aller Hausgeld-Sollstellungen des EV im Wirtschaftsjahr —
    unabhängig vom Zahlungsstatus (Soll-Prinzip, nicht Ist).
    Enthält auch Nachhol-Sollstellungen aus Eigentümerwechsel
    (siehe CLAUDE_CODE_ANLEITUNG_EIGENTUEMERWECHSEL_v1_0.md Kap. 5.3).
    """
    return HausgeldSollstellung.objects.filter(
        eigentumsverhaeltnis=ev,
        sollstellungs_typ='hausgeld',
        periode__gte=wj.beginn_datum,
        periode__lte=wj.ende_datum,
        storniert_am__isnull=True,
    ).aggregate(summe=Sum('soll_betrag'))['summe'] or Decimal('0.00')
```

Das ist die konkrete Umsetzung von Nebenbuch-Spec Kap. 13.2
(„Einzelabrechnung-Generator zieht VZ-Soll aus Nebenbuch").

### 4.3 Verteilerschlüssel-Auflösung je Konto

Je Konto wird der aktive Verteilerschlüssel über `KontoVerteilerSchluessel`
aufgelöst (siehe `CLAUDE_CODE_ANLEITUNG_VERTEILERSCHLUESSEL_IMPORT_v1_0.md`):

```python
def anteil_einheit(konto: Konto, einheit: Einheit, wj: Wirtschaftsjahr) -> Decimal:
    vs = KontoVerteilerSchluessel.objects.get(konto=konto, wirtschaftsjahr=wj).vs_code
    if vs in ('001', '010'):          # Fläche / MEA — Stammdaten am Objekt
        gesamt = einheit.objekt.einheiten.aggregate(s=Sum(vs_feldname(vs)))['s']
        wert = getattr(einheit, vs_feldname(vs))
    elif vs in ('030', '031', '032'): # Kopfanteil-Varianten
        gesamt, wert = anzahl_kopfanteil(einheit.objekt, vs)
    else:                              # 140-145 Verbrauchs-VS
        gesamt = EinheitVerbrauch.objects.filter(
            wirtschaftsjahr=wj, einheit__objekt=einheit.objekt, vs_code=vs
        ).aggregate(s=Sum('wert'))['s']
        wert = EinheitVerbrauch.objects.get(
            wirtschaftsjahr=wj, einheit=einheit, vs_code=vs
        ).wert
    if not gesamt:
        raise VerteilerschluesselFehlerException(konto, einheit, vs)
    return wert / gesamt
```

**Fehlerfall:** Fehlt ein Verbrauchswert (`EinheitVerbrauch.wert IS
NULL`) für ein Konto mit Verbrauchs-VS, wird Schritt 6 blockiert
("Verbrauchswerte unvollständig — bitte VS-Import nachholen oder
manuell erfassen") — kein automatischer Ausfall auf einen Fallback-Schlüssel.

### 4.4 Eigentümerwechsel im Abrechnungsjahr (unverändert aus Kap. 6.3)

| Szenario | Verhalten |
|---|---|
| Eigentümerwechsel im Jahr | Abrechnung läuft vollständig auf aktuellen Eigentümer (Käufer). Kein Split. `hinweis_eigentuemerwechsel=True`. |
| Mehrfacher Wechsel im Jahr | Gleiche Regel — immer der Eigentümer zum Erstellungsdatum |
| Archiviertes Personenkonto/EV | Wird nicht in Abrechnung einbezogen |
| Zivilrechtlicher Ausgleich | Nicht im System — Kaufvertrags-/Notarebene |

Durch die Nachhol-Sollstellungen aus dem Eigentümerwechsel-Modul
(`CLAUDE_CODE_ANLEITUNG_EIGENTUEMERWECHSEL_v1_0.md` Kap. 5.3) ist der
Käufer bereits im Nebenbuch rückwirkend Schuldner des vollen
Jahres-Solls — `berechne_hausgeld_soll()` (Kap. 4.2) liefert daher ohne
Sonderbehandlung den korrekten Wert.

### 4.5 Rücklagen-Ausweis (unverändert aus Kap. 6.4, je Rücklage separat)

| Position | Quelle |
|---|---|
| Anfangsbestand | Bankkonto-Saldo zum Beginn des WJ (`Wirtschaftsjahr.beginn_datum`) |
| + Zuführungen | Summe `SollstellungZahlung` auf Splits mit BA-Suffix `.91X` im WJ (Nebenbuch, nicht mehr Sachkontenbuchung direkt) |
| − Entnahmen | Buchungen mit Rücklagenkonto als Gegenkonto |
| = Endbestand | Bankkonto-Saldo zum Ende des WJ (Soll = Bankauszug; Abweichung = Klärungsfall, blockiert Schritt 5) |
| Anteil Eigentümer | Endbestand × MEA der Einheit |

**Wichtig:** Da Zuführungen jetzt über das Nebenbuch laufen
(`SollstellungZahlung.split.erloeskonto`), muss Schritt 5 die
Zuführungssumme aus `SollstellungZahlung` aggregieren, nicht mehr aus
rohen `Buchung`-Datensätzen mit Unterkonto-Suffix (das Unterkonto-Modell
entfällt laut Nebenbuch-Spec Kap. 13.1 vollständig).

---

## 5. Wizard-Schritte (Prozess-Engine, 8 Schritte)

Nutzt die bestehende Prozess-Engine (Ausgangsspec Kap. 5): Schritt-
Navigation, Validierung je Schritt, Persistierung in `Prozess.steps_data`
(JSONField), unterbrechbar/fortsetzbar.

### Schritt 1 — Jahr & Objekt

- Auswahl `Objekt` + `Wirtschaftsjahr` (nur `status='offen'`)
- Prüfung: existiert bereits eine `Jahresabrechnung` für diese
  Kombination mit Status `!= entwurf`? → Block ("Abrechnung bereits
  vorhanden, siehe Korrekturabrechnung")
- Hinweis-Banner, falls im WJ ein `EigentuemerwechselVorgang` mit
  `abgeschlossen_am` im WJ-Zeitraum existiert

### Schritt 2 — Buchungsprüfung

- Liste offener/ungebuchter `KreditorOP` (Status ≠ `bankabgang_erfolgt`)
  und offener `WiederkehrendeBuchungOP` im WJ
- **Hartes Blocking:** Es dürfen keine offenen Kreditoren-OPs mit
  `faellig_am <= wirtschaftsjahr.ende_datum` existieren — sonst
  Weiterschalten gesperrt (Meldung mit Link zur Liste)

### Schritt 3 — Kostenstellen-Übersicht

- Ist-Kosten je Sachkonto (Aggregation über `Buchung` im WJ, Soll auf
  Aufwandskonten `50xxx`/`55xxx`) vs. Wirtschaftsplan-Ansatz
- Abweichungsanzeige (absolut + Prozent)
- **Abhängigkeit von Vorprüfung Kap. 0, Punkt 1** — falls kein
  Wirtschaftsplan-Modell existiert, zeigt dieser Schritt nur Ist-Kosten
  ohne Vergleichsspalte (Degradation, kein Blocker)

### Schritt 4 — Umlageschlüssel

- Je Konto den aktiven Verteilerschlüssel anzeigen (`KontoVerteilerSchluessel`)
- Manuelle Korrektur nur für das aktuelle WJ, nicht rückwirkend
- Bei Korrektur: Neuberechnung der Vorschau-Kostenstellen live

### Schritt 5 — Rücklagen

- Je Rücklagenkonto: Tabelle gemäß Kap. 4.5
- **Hartes Blocking bei Abweichung Endbestand vs. Bankauszug:**
  Differenz > 0,01 € → Klärungsfall, Weiterschalten gesperrt

### Schritt 6 — Einzelabrechnungen

- Für jede aktive `Einheit` im Objekt:
  1. Aktuellen Eigentümer bestimmen (EV mit `ende IS NULL` oder
     `ende >= erstellungsdatum`, `beginn <= erstellungsdatum`)
  2. `hausgeld_soll_gesamt` via Kap. 4.2
  3. `kostenanteil_gesamt` via Kap. 4.3 über alle relevanten Konten
  4. `abrechnungsergebnis = kostenanteil_gesamt - hausgeld_soll_gesamt`
  5. `positionen`- und `ruecklagen`-JSON befüllen
  6. `EinzelAbrechnung`-Datensatz mit Status implizit `entwurf`
     (über `jahresabrechnung.status`) anlegen/aktualisieren
- Live editierbar; jede manuelle Korrektur schreibt in `positionen`
  mit Änderungsvermerk (`manuell_korrigiert: true`, `grund`)

### Schritt 7 — PDF-Vorschau

- Rendering aller `EinzelAbrechnung`-PDFs (Bibliothek gemäß Vorprüfung
  Kap. 0, Punkt 2) — noch **nicht** persistiert als `Dokument`,
  nur Vorschau-Rendering im Response
- Fußnote bei `hinweis_eigentuemerwechsel=True`
- Manuelle Korrekturen weiterhin möglich → zurück zu Schritt 6 möglich

### Schritt 8 — Freigabe & Buchung (KORRIGIERT, siehe Kap. 6)

---

## 6. Schritt 8 im Detail — Freigabe und Nebenbuch-Anbindung

### 6.1 Ablauf (atomar)

```python
@transaction.atomic
def freigebe_jahresabrechnung(ja: Jahresabrechnung, user: User) -> Jahresabrechnung:
    """
    Schritt 8: Sperrt die Jahresabrechnung, erzeugt PDFs final,
    und ruft den Sollstellungslauf für 'abrechnungsergebnis' auf.
    Erzeugt KEINE Sachkontenbuchung und KEINEN Auszahlungslauf.
    """
    if ja.status != 'entwurf':
        raise ValidationError("Nur Abrechnungen im Status 'entwurf' können freigegeben werden.")

    einzelabrechnungen = ja.einzelabrechnung_set.all()
    _validiere_vollstaendigkeit(einzelabrechnungen)  # jede aktive Einheit hat einen Datensatz

    # 1. PDFs final rendern + als Dokument persistieren (Kap. 6.2)
    for ea in einzelabrechnungen:
        dokument = pdf_service.rendere_und_speichere(ea)
        ea.dokument = dokument
        ea.save(update_fields=['dokument'])

    # 2. Sollstellungslauf aufrufen — NICHT direkt Buchung erzeugen
    lauf = sollstellungslauf_service.run_abrechnungsergebnis(
        objekt=ja.objekt, wj=ja.wirtschaftsjahr, user=user
    )

    # 3. EinzelAbrechnung mit erzeugter Sollstellung verknüpfen
    for ea in einzelabrechnungen:
        ss = lauf.hausgeldsollstellung_set.get(eigentumsverhaeltnis=ea.eigentumsverhaeltnis)
        ea.sollstellung = ss
        ea.save(update_fields=['sollstellung'])

    # 4. Jahresabrechnung sperren
    ja.status = 'gesperrt'
    ja.freigegeben_am = timezone.now()
    ja.freigegeben_von = user
    ja.sollstellungslauf = lauf
    ja.save(update_fields=['status', 'freigegeben_am', 'freigegeben_von', 'sollstellungslauf'])
    return ja
```

`sollstellungslauf_service.run_abrechnungsergebnis` ist **bereits** in
der Nebenbuch-Spec (Kap. 12.3, Schritt 7) vorgesehen — diese Spec
implementiert nur den **Aufrufer**, nicht den Service selbst.

### 6.2 Positiv/negativ — was danach passiert

| `abrechnungsergebnis` | Sollstellung im Nebenbuch | Weiterer Ablauf |
|---|---|---|
| `> 0` (Nachzahlung) | `HausgeldSollstellung` mit positivem `soll_betrag`, BA `.950` | Läuft wie jede offene Forderung: Lastschriftlauf, Zahlungseingang, Mahnwesen — **kein** Sonderfall in dieser Spec |
| `< 0` (Guthaben) | `HausgeldSollstellung` mit negativem `soll_betrag`, BA `.950` | Erscheint in der Auszahlungslauf-Vorschau (Nebenbuch-Spec Kap. 10.5). **Wird nicht automatisch ausgelöst** — der Verwalter startet den Auszahlungslauf manuell auf einer eigenen Seite außerhalb dieses Wizards |
| `= 0` | Keine Sollstellung nötig | `run_abrechnungsergebnis` überspringt EVs mit `abrechnungsergebnis == 0` (kein leerer OP) |

### 6.3 Was NICHT in Schritt 8 passiert (Abgrenzung)

- **Keine** automatische Weiterleitung zum Auszahlungslauf-Wizard
- **Keine** Sachkontenbuchung `Soll XXXX.950 / Haben Ausgleichskonto`
  (ersatzlos entfallen, analog Nebenbuch-Spec Kap. 13.1)
- **Kein** PDF-Versand an Eigentümer (Phase 2, separat)
- **Keine** Erzeugung von Beschlussprotokoll-Verknüpfungen (DMS/Beschluss-Modul, separat)

### 6.4 Übergabepunkt für den Auszahlungslauf (Information, keine Implementierung)

Nach Freigabe zeigt die UI lediglich einen Hinweis:

```
✓ Jahresabrechnung {Objekt} / WJ {Jahr} freigegeben und gesperrt.

{N} Einheiten mit Guthaben aus dieser Abrechnung.
→ Auszahlungslauf kann unter „Zahlungen → Auszahlungen" manuell
  gestartet werden (siehe Nebenbuch-Spec Kap. 10.5).
```

Kein Button, der direkt in den Auszahlungslauf-Wizard springt — bewusst
getrennter Vorgang laut Product-Owner-Entscheidung (Kap. 0).

---

## 7. Validierung — `_validiere_vollstaendigkeit`

```python
def _validiere_vollstaendigkeit(einzelabrechnungen):
    """
    Stellt sicher, dass jede zum Erstellungsdatum aktive Einheit des
    Objekts eine EinzelAbrechnung hat, und dass keine EinzelAbrechnung
    mit ungeklärten Verteilerschlüssel-Fehlern (Kap. 4.3) offen ist.
    """
    erwartete_einheiten = set(ja.objekt.einheiten.filter(aktiv=True).values_list('id', flat=True))
    vorhandene = set(einzelabrechnungen.values_list('einheit_id', flat=True))
    fehlende = erwartete_einheiten - vorhandene
    if fehlende:
        raise ValidationError(f"Fehlende Einzelabrechnungen für Einheiten: {fehlende}")
    for ea in einzelabrechnungen:
        if ea.positionen_hat_fehler():  # aus Schritt 6, VerteilerschluesselFehlerException geloggt
            raise ValidationError(f"Einzelabrechnung {ea.id} hat ungeklärte Verteilerschlüssel-Fehler.")
```

---

## 8. Service-Architektur

```
apps/buchhaltung/services/jahresabrechnung/
├── kostenstellen_service.py     # Schritt 3: Ist-Kosten je Konto, Wirtschaftsplan-Vergleich
├── verteilerschluessel_service.py  # Schritt 4/6: Anteil-Berechnung (Kap. 4.3)
├── ruecklagen_service.py        # Schritt 5: Ausweis je Rücklage (Kap. 4.5)
├── einzelabrechnung_service.py  # Schritt 6: Berechnungslogik je Einheit (Kap. 4)
├── pdf_service.py               # Schritt 7/8: Rendering + Persistierung als Dokument
└── freigabe_service.py          # Schritt 8: Sperre + Aufruf sollstellungslauf_service (Kap. 6.1)
```

**Bewusst außerhalb dieses Verzeichnisses:** `sollstellungslauf_service.
run_abrechnungsergebnis` bleibt in `apps/buchhaltung/services/` (Nebenbuch-
Spec) — wird hier nur **aufgerufen**, nicht neu implementiert.

### 8.1 Aufgabentrennung

| Service | Zuständigkeit | Schreibt nach |
|---|---|---|
| `kostenstellen_service` | Ist/Plan-Vergleich je Konto | (read-only) |
| `verteilerschluessel_service` | Anteil-Berechnung, Fehlerfall-Erkennung | (read-only, wirft Exception) |
| `ruecklagen_service` | Rücklagen-Ausweis, Bankauszug-Abgleich | (read-only) |
| `einzelabrechnung_service` | Orchestriert Schritt 6 je Einheit | `EinzelAbrechnung` |
| `pdf_service` | Rendering, Speicherung nach STRATO HiDrive S3 | `Dokument` |
| `freigabe_service` | Schritt 8 Ablauf (Kap. 6.1) | `Jahresabrechnung`, `EinzelAbrechnung.sollstellung` |

---

## 9. API-Endpunkte

| Methode | Pfad | Beschreibung |
|---|---|---|
| POST | `/api/v1/jahresabrechnung/` | Schritt 1: Prozess anlegen |
| GET/PATCH | `/api/v1/jahresabrechnung/{id}/schritt/{n}/` | Wizard-Navigation je Schritt |
| GET | `/api/v1/jahresabrechnung/{id}/kostenstellen/` | Schritt 3 Daten |
| GET/PATCH | `/api/v1/jahresabrechnung/{id}/umlageschluessel/` | Schritt 4 Daten + Korrektur |
| GET | `/api/v1/jahresabrechnung/{id}/ruecklagen/` | Schritt 5 Daten |
| GET/PATCH | `/api/v1/jahresabrechnung/{id}/einzelabrechnungen/{einheit_id}/` | Schritt 6 Daten + manuelle Korrektur |
| GET | `/api/v1/jahresabrechnung/{id}/pdf-vorschau/` | Schritt 7 Vorschau-Rendering |
| POST | `/api/v1/jahresabrechnung/{id}/freigeben/` | Schritt 8 — ruft `freigabe_service.freigebe_jahresabrechnung` |

**ZH/SEV-Guard:** HTTP 501, wenn `objekt.objekt_typ != 'WEG'` (analog
bestehender Guards in anderen Specs — Jahresabrechnung ist ein
WEG-spezifisches Konzept).

---

## 10. Anzupassende Elemente (Bestand)

| Element | Anpassung |
|---|---|
| `EinzelAbrechnung.gebucht` | Entfernen — ersetzt durch `sollstellung`-FK (Kap. 3.2) |
| `Jahresabrechnung`-Model | `wirtschaftsjahr`-FK statt rohem Jahresfeld, `sollstellungslauf`-FK ergänzen |
| `Prozess.prozess_typ` | Enum-Wert `jahresabrechnung` sicherstellen (falls noch nicht vorhanden) |

---

## 11. Tests

### 11.1 Unit-Tests

| Datei | Inhalt |
|---|---|
| `test_verteilerschluessel_service.py` | Alle VS-Kategorien (Stamm abgeleitet, Kopf, Verbrauch), Fehlerfall bei fehlendem Verbrauchswert |
| `test_einzelabrechnung_service.py` | Formel-Korrektheit (Kap. 4.1), Plan-Änderung im Jahr (anteilige Monate), Eigentümerwechsel-Fußnote |
| `test_ruecklagen_service.py` | Zuführung aus `SollstellungZahlung`, Bankauszug-Abweichung blockiert Schritt 5 |
| `test_freigabe_service.py` | Atomic-Verhalten, Aufruf `run_abrechnungsergebnis`, Verknüpfung `sollstellung`-FK, kein Auszahlungslauf-Trigger |

### 11.2 Integrationstests

- Vollständiger Wizard-Durchlauf 1→8 mit 5 Einheiten, davon 1 mit
  Eigentümerwechsel im Jahr → korrekte Fußnote, korrektes Hausgeld-Soll
  aus Nachhol-Sollstellungen
- Wizard-Durchlauf mit einer Einheit mit Guthaben (negatives Ergebnis)
  → nach Freigabe erscheint EV in Auszahlungslauf-Vorschau (Nebenbuch-
  Spec), aber **kein** automatischer Auszahlungslauf existiert
- Schritt 2 mit offenem Kreditoren-OP → Block funktioniert
- Schritt 5 mit Bankauszug-Abweichung → Block funktioniert
- Schritt 6 mit fehlendem Verbrauchswert an einem Konto mit VS 140 →
  Block mit klarer Fehlermeldung

### 11.3 Invarianten-Suite (`test_invariants.py`)

```python
def test_abrechnungsergebnis_konsistent():
    """abrechnungsergebnis == kostenanteil_gesamt - hausgeld_soll_gesamt für alle EinzelAbrechnung."""

def test_gesperrte_abrechnung_hat_sollstellung():
    """Jede EinzelAbrechnung einer gesperrten Jahresabrechnung mit Ergebnis != 0 hat eine sollstellung-FK."""

def test_keine_doppelte_einzelabrechnung():
    """UniqueConstraint (jahresabrechnung, einheit) wird eingehalten."""

def test_kein_automatischer_auszahlungslauf():
    """Nach freigebe_jahresabrechnung existiert kein Auszahlungslauf mit erstellt_am == freigegeben_am."""
```

---

## 12. Akzeptanzkriterien (Smoke-Test vor Go-Live)

Manueller End-to-End-Test mit einem Test-Objekt (5 Einheiten, davon 1
mit Eigentümerwechsel im WJ, 1 mit Guthaben-Ergebnis):

1. Wizard-Schritt 1–5 ohne Blocker durchlaufen (Buchungsprüfung sauber,
   Rücklagen stimmen mit Bankauszug überein)
2. Schritt 6: alle 5 Einzelabrechnungen korrekt berechnet, Formel per
   Hand nachgerechnet stimmt überein
3. Schritt 7: PDF-Vorschau zeigt Fußnote bei der Eigentümerwechsel-Einheit
4. Schritt 8: Freigabe → Jahresabrechnung Status `gesperrt`, 5
   `HausgeldSollstellung(sollstellungs_typ='abrechnungsergebnis')`
   erzeugt (4 positiv, 1 negativ), keine Sachkontenbuchung im
   Buchungsjournal sichtbar
5. Guthaben-Einheit erscheint in Auszahlungslauf-Vorschau — Auszahlungslauf
   **nicht** automatisch angelegt
6. Erneuter Aufruf von Schritt 1 mit derselben Objekt/WJ-Kombination →
   Block ("bereits vorhanden")

Wenn alle 6 Punkte grün sind, ist diese Spec implementierungs-vollständig.

---

## 13. Ausdrücklich nicht Teil dieser Spec

- **Korrekturabrechnung** — eigene Folgespec (siehe Kap. 0)
- **Auszahlungslauf-UI/-Trigger** — bereits in Nebenbuch-Spec spezifiziert, hier nur Übergabepunkt (Kap. 6.4)
- **E898-Anlagen (Techem-Einzelabrechnungsbild):** Sollen später als
  zusätzliche **Anlage** an die `EinzelAbrechnung` angehängt werden
  (Entscheidung: nur Anlage, ersetzt keine interne Berechnung — siehe
  vorheriger Chat-Verlauf). Vorbereitung dafür: `Dokument.
  verknuepfung_typ` müsste um `einzelabrechnung` erweitert werden — das
  ist bereits als Erweiterungsbaustein für die künftige ARGE-HEIWAKO-Spec
  vorgesehen und **nicht** Teil dieser Spec. Da diese Spec das
  `dokument`-Feld an `EinzelAbrechnung` ohnehin einführt (Kap. 3.2, für
  das intern erzeugte PDF), sollte die künftige HEIWAKO-Spec prüfen, ob
  E898-Anlagen als **zweiter** Dokument-Slot (`dokument_extern`) oder
  über eine generische M:N-Beziehung (`EinzelAbrechnung.anlagen`)
  modelliert werden — diese Entscheidung ist hier bewusst offengelassen.
- **Wirtschaftsplan-Erstellung** — vorausgesetzt als bestehend (Kap. 0)
- **Beschlussfassung / Versammlungsprotokoll** — DMS/Beschluss-Modul, separat
- **PDF-Versand an Eigentümer** — Phase 2

---

## 14. Aufgaben für Claude Code

> **Hinweis an Claude Code:** Bevor Phase A beginnt, die vier Punkte aus
> Kap. 0 am realen Code-Stand verifizieren und Ergebnis kurz
> dokumentieren. Danach Schritte in Reihenfolge abarbeiten. Nach jeder
> Phase: Migration erzeugen, Tests laufen lassen, erst dann weiter.
> Alle Geschäftslogik ausschließlich in
> `services/jahresabrechnung/` — nie in Views oder Models, nie in
> Django-Signals.

### Phase A — Datenmodelle und Migration

- `Jahresabrechnung`- und `EinzelAbrechnung`-Modelle gemäß Kap. 3
  anlegen bzw. bestehende Modelle (Ausgangsspec Kap. 4.9) migrieren:
  `gebucht`-Feld entfernen, `sollstellung`- und `dokument`-FK ergänzen,
  `wirtschaftsjahr`-FK statt rohem Jahresfeld
- Migration + Review der erzeugten SQL

### Phase B — Berechnungsservices (Schritte 3–5)

- `kostenstellen_service.py`, `verteilerschluessel_service.py`,
  `ruecklagen_service.py` gemäß Kap. 4.3/4.5 und Kap. 8
- Tests: `test_verteilerschluessel_service.py`, `test_ruecklagen_service.py`

### Phase C — Einzelabrechnung und PDF (Schritte 6–7)

- `einzelabrechnung_service.py` gemäß Kap. 4.1/4.2/4.4
- `pdf_service.py` — Rendering-Bibliothek gemäß Vorprüfung Kap. 0,
  Punkt 2; Speicherung nach STRATO HiDrive S3 über bestehenden
  `Dokument`-Upload-Mechanismus
- Tests: `test_einzelabrechnung_service.py`

### Phase D — Freigabe und Nebenbuch-Anbindung (Schritt 8)

- `freigabe_service.py` gemäß Kap. 6.1 — Aufruf des **bestehenden**
  `sollstellungslauf_service.run_abrechnungsergebnis` (keine
  Neu-Implementierung dieses Service in dieser Phase)
- Tests: `test_freigabe_service.py`, Invarianten-Suite Kap. 11.3

### Phase E — API und Wizard-UI

- Endpunkte gemäß Kap. 9
- Frontend `frontend/src/pages/buchhaltung/jahresabrechnung/`:
  `JahresabrechnungWizard.tsx` (8 Schritte), Detail-Ansichten je Schritt
- Hinweis-Banner nach Freigabe gemäß Kap. 6.4 (kein Direkt-Link zum
  Auszahlungslauf)

### Phase F — End-to-End-Tests

- Integrationstests gemäß Kap. 11.2
- **Hartstopp vor Go-Live:** Patrik gibt nach manuellem Smoke-Test
  (Kap. 12) frei — analog HALT-Gates in anderen Specs
  (`CLAUDE_CODE_CLEANUP_ALTE_SOLLSTELLUNG_v1_0.md`).

---

## 15. Offene Punkte / Schnittstellen für künftige Specs

| Punkt | Geplante Spec |
|---|---|
| Korrekturabrechnung | `Korrekturabrechnung_v1.0` |
| E898-Anlage (Techem-Einzelabrechnungsbild) | Erweiterung der noch zu schreibenden ARGE-HEIWAKO-Spec |
| Beschlussprotokoll-Verknüpfung zur Genehmigung | DMS/Beschluss-Modul |
| PDF-Versand an Eigentümer | Phase 2 |
| Wirtschaftsplan-Modul (falls in Kap. 0 Punkt 1 als fehlend festgestellt) | `Wirtschaftsplan_v1.0` |

---

**Ende der Spezifikation v1.0.**
