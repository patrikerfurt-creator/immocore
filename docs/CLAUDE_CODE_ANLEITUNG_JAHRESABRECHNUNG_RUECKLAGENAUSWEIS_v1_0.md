# Claude Code – Anleitung: Rücklagen-Ausweis in der Jahresabrechnung (IMMOCORE)

**Version:** 1.0
**Bezug:** Ausgangsspezifikation Kap. 4.9 (Datenmodell), Kap. 5.3 Schritt 5
(Wizard), Kap. 6.4 (Rücklagen-Ausweis); Modul Jahresabrechnung (Projektstand:
✅ Fertig, 7 Services: Einzelabrechnung, Verteilerschlüssel, Rücklagen,
Kostenstellen, Freigabe, PDF, Wizard)
**Status:** Implementierungsreif
**Anlass:** Der je-Rücklage-Ausweis (Anfangsbestand/Zuführung/Entnahmen/
Endbestand) ist im Abrechnungs-PDF nicht bzw. nicht vollständig sichtbar,
obwohl Modell und Wizard-Schritt dafür bereits vorgesehen sind.

---

## 0. Orchestrierung für Claude Code

Diese Spec wird von einem **Opus-Modell als Orchestrator** bearbeitet.
Der Orchestrator:

1. liest diese Spec sowie die Referenzkapitel der Ausgangsspezifikation
   (4.9, 5.3, 6.4) und den aktuellen Code der drei betroffenen Services
   vollständig, bevor er Aufgaben verteilt;
2. zerlegt die Arbeit in die unten stehenden Teilaufgaben und **delegiert
   sie an mehrere parallele Subagenten** (güns­tigeres Modell, z. B.
   Sonnet) – nicht selbst implementieren, sondern verteilen und
   reviewen;
3. reviewt jedes Teilergebnis gegen diese Spec, lässt bei Abweichungen
   nachbessern, und führt erst danach die Integration + Gesamttestlauf
   durch;
4. entscheidet über die Freigabe zum jeweils nächsten Schritt (siehe
   Abhängigkeitsgraph unten).

### Abhängigkeitsgraph der Teilaufgaben

```
Agent 1 (Daten/Berechnung)  ──▶  Agent 2 (PDF-Template)
        │                              │
        └────────────▶  Agent 3 (Tests/QA)  ◀──┘
```

- **Agent 1 – Daten & Berechnung** (Sonnet): Kap. 4 + 5 dieser Spec.
  Muss zuerst abgeschlossen sein, da Kap. 6 (PDF) auf der von Agent 1
  festgelegten JSON-Struktur aufbaut.
- **Agent 2 – PDF-Template** (Sonnet): Kap. 6, beginnt erst nach Freigabe
  von Agent 1's Datenstruktur durch den Orchestrator.
- **Agent 3 – Tests/QA** (Sonnet oder Haiku für die reinen
  Konsistenz-/Regressionschecks): kann parallel zu Agent 2 starten,
  sobald Agent 1 fertig ist – schreibt die Service-Tests gegen die neue
  Berechnungslogik, während Agent 2 am Template arbeitet. Übernimmt
  anschließend auch die PDF-Snapshot-Tests aus Kap. 8.2.
- Der Orchestrator führt am Ende Kap. 9 (Aufgabenliste) als
  Gesamt-Checkliste ab und lässt die volle Testsuite laufen, bevor er
  den Abschluss meldet.

Kein Schritt darf ohne Migration + grüner Testlauf an den nächsten
übergeben werden (siehe auch Kap. 9, Hinweis an Claude Code).

---

## 1. Ziel

Der bestehende Rücklagen-Ausweis aus Kap. 6.4 der Ausgangsspezifikation
(„je Rücklage separat: Anfangsbestand, Zuführungen, Entnahmen,
Endbestand, Anteil Eigentümer") soll **vollständig und korrekt im
Einzelabrechnungs-PDF** erscheinen – für Objekte mit einer Rücklage
ebenso wie für Objekte mit mehreren Rücklagen (bis zu 21, Suffix
`.911`–`.931`).

Nicht-Ziel dieser Spec: Änderungen an der Berechnungsformel selbst
(Kap. 6.4 gilt unverändert), am Wirtschaftsplan-Modul oder am
Auszahlungslauf für Abrechnungsguthaben (Hausgeld-Nebenbuch Kap. 10.5).

---

## 2. Ist-Zustand

- `EinzelAbrechnung.ruecklagen` (JSONField) ist laut Datenmodell für
  „Anfangsbestand, Zuführung, Entnahmen, Endbestand je Rücklage"
  vorgesehen; `ruecklagen_zufuehrung_gesamt` (Decimal) existiert
  zusätzlich als Summenfeld.
- Wizard-Schritt 5 „Rücklagen" berechnet diese Werte je Rücklage
  bereits für die Objekt-Ebene (Kap. 5.3).
- Die PDF-Erzeugung läuft über **WeasyPrint** (HTML/CSS → PDF).
- **Lücke:** Der Rücklagen-Ausweis aus Kap. 6.4 wird im
  Einzelabrechnungs-PDF nicht (vollständig) dargestellt. Ob das Feld
  `ruecklagen` befüllt, aber im Template nicht gerendert wird, oder ob
  bereits die Befüllung unvollständig ist, muss **Agent 1 im ersten
  Schritt am tatsächlichen Code klären** (Rücklagen-Service +
  PDF-Template inspizieren, Ist-Zustand kurz dokumentieren, bevor
  Änderungen vorgenommen werden).

---

## 3. Fachliche Anforderung (Soll)

### 3.1 Rücklagen-Ausweis je Rücklage (Kap. 6.4 – unverändert gültig)

| Position | Quelle |
|---|---|
| Anfangsbestand | Bankkonto-Saldo zum 01.01. des Wirtschaftsjahres |
| + Zuführungen | Summe aller Buchungen auf Unterkonto-Suffix `.91X` im Wirtschaftsjahr |
| − Entnahmen | Buchungen, deren Gegenkonto das Rücklagenkonto ist (finanzierte Maßnahmen) |
| = Endbestand | Bankkonto-Saldo zum 31.12. (Soll = Bankauszug; Abweichung = Klärungsfall) |
| Anteil Eigentümer | Endbestand × MEA-Anteil der Einheit |

### 3.2 Mehrere Rücklagen

Objekte können bis zu 21 Rücklagen führen (Suffix `.911`–`.931`, siehe
Massenimport-Spec Kap. 4.1). Der Ausweis muss **jede aktive Rücklage
des Objekts einzeln** auflisten, in der Reihenfolge der Rücklagen-Nummer
(I, II, III, …), plus eine **Summenzeile**, sobald mehr als eine
Rücklage existiert. Bei genau einer Rücklage entfällt die Summenzeile
(redundant).

### 3.3 Abweichungs-Handling (Klärungsfall)

Weicht der berechnete Endbestand vom tatsächlichen Bankkonto-Saldo zum
31.12. ab (Rundungsdifferenzen ausgenommen, Toleranz analog zu anderen
Modulen z. B. `Basiszinssatz`-Rundung: 0,01 €), gilt dies laut Kap. 6.4
als **Klärungsfall**. Im PDF muss dieser Fall sichtbar markiert werden
(siehe Kap. 6.3) – die Abrechnung wird dadurch **nicht** blockiert
(Freigabe bleibt möglich, analog zu anderen bereits bestehenden
Hinweis-Fußnoten wie beim Eigentümerwechsel, Kap. 6.3
Ausgangsspezifikation), aber der Verwalter muss den Klärungsfall sehen,
bevor er freigibt.

### 3.4 Anteil Eigentümer

Der auf die einzelne Einheit entfallende Anteil (Endbestand × MEA) wird
je Rücklage **zusätzlich zur Objekt-Gesamtsumme** ausgewiesen – die
Objekt-Ebene liefert den Kontext (wie hoch ist die Rücklage insgesamt),
die Einheiten-Ebene den für den Eigentümer relevanten Wert.

---

## 4. Datenmodell — Struktur des `ruecklagen`-JSONFields

Agent 1 legt (falls noch nicht vorhanden) exakt diese Struktur je
Listenelement in `EinzelAbrechnung.ruecklagen` fest. Bestehende
abweichende Feldnamen im Code sind an diese Struktur anzugleichen
(Migration/Backfill für bereits erzeugte, aber noch nicht gesperrte
Abrechnungen; gesperrte/freigegebene Abrechnungen bleiben unverändert,
da laut Kap. 6.1 „Unveränderlichkeit" gilt).

```json
{
  "ruecklagen": [
    {
      "suffix": "911",
      "nummer_roemisch": "I",
      "bezeichnung": "Erhaltungsrücklage (Rücklage I)",
      "objekt_anfangsbestand": "12500.00",
      "objekt_zufuehrungen": "3600.00",
      "objekt_entnahmen": "1800.00",
      "objekt_endbestand_berechnet": "14300.00",
      "objekt_endbestand_bankauszug": "14300.00",
      "abweichung": "0.00",
      "klaerungsfall": false,
      "mea_anteil_einheit": "45/1000",
      "anteil_eigentuemer_betrag": "643.50"
    }
  ],
  "ruecklagen_summe": {
    "objekt_anfangsbestand": "12500.00",
    "objekt_zufuehrungen": "3600.00",
    "objekt_entnahmen": "1800.00",
    "objekt_endbestand_berechnet": "14300.00",
    "anteil_eigentuemer_betrag": "643.50"
  }
}
```

Hinweise:

- `objekt_*`-Felder sind je Rücklage für das **gesamte Objekt**
  identisch über alle `EinzelAbrechnung`-Datensätze einer
  `Jahresabrechnung` hinweg (nur `mea_anteil_einheit` und
  `anteil_eigentuemer_betrag` unterscheiden sich je Einheit). Diese
  Redundanz ist bewusst (Snapshot-Prinzip wie bei `eigentuemer` in
  Kap. 4.9 – die Einzelabrechnung muss auch nach späteren Änderungen am
  Objekt-Datenstand exakt reproduzierbar bleiben, sobald sie
  freigegeben ist).
- `ruecklagen_summe` wird nur befüllt, wenn `len(ruecklagen) > 1`
  (siehe Kap. 3.2); sonst `null`.
- `abweichung` = `objekt_endbestand_berechnet − objekt_endbestand_bankauszug`
  (kann negativ sein); `klaerungsfall = abs(abweichung) > Decimal("0.01")`.
- `ruecklagen_zufuehrung_gesamt` (bestehendes Decimal-Feld) bleibt
  bestehen und muss weiterhin `SUM(objekt_zufuehrungen über alle
  Rücklagen)` entsprechen – Agent 3 schreibt dafür einen
  Konsistenz-Test (Kap. 8.1).

---

## 5. Berechnungslogik (Pseudocode für Agent 1)

```python
def berechne_ruecklagen_ausweis(objekt, wirtschaftsjahr) -> list[RuecklagenZeile]:
    """
    Wird einmal je Jahresabrechnung auf Objekt-Ebene berechnet
    (nicht je Einheit) und anschließend beim Aufbau jeder
    EinzelAbrechnung um den einheitsspezifischen Anteil ergänzt.
    """
    zeilen = []
    for ruecklage in aktive_ruecklagen(objekt):  # .911 .. .931, nur aktive
        anfangsbestand = bankkonto_saldo(ruecklage.bankkonto, datum=wj.beginn)
        zufuehrungen = summe_buchungen(
            unterkonto_suffix=ruecklage.suffix, wirtschaftsjahr=wj,
            richtung="haben",  # Erlöskonto 41.91X
        )
        entnahmen = summe_buchungen(
            gegenkonto=ruecklage.bestandskonto, wirtschaftsjahr=wj,
        )
        endbestand_berechnet = anfangsbestand + zufuehrungen - entnahmen
        endbestand_bankauszug = bankkonto_saldo(ruecklage.bankkonto, datum=wj.ende)
        abweichung = endbestand_berechnet - endbestand_bankauszug

        zeilen.append(RuecklagenZeile(
            ruecklage=ruecklage,
            anfangsbestand=anfangsbestand,
            zufuehrungen=zufuehrungen,
            entnahmen=entnahmen,
            endbestand_berechnet=endbestand_berechnet,
            endbestand_bankauszug=endbestand_bankauszug,
            abweichung=abweichung,
            klaerungsfall=abs(abweichung) > Decimal("0.01"),
        ))
    return zeilen


def ergaenze_anteil_je_einheit(zeilen, einheit) -> list[dict]:
    """Wird je EinzelAbrechnung aufgerufen; reine Multiplikation, keine Neuberechnung."""
    mea_anteil = verteilerschluessel_mea_anteil(einheit)  # bestehende Funktion wiederverwenden
    return [
        {**zeile.as_dict(), "mea_anteil_einheit": mea_anteil, "anteil_eigentuemer_betrag": zeile.endbestand_berechnet * mea_anteil}
        for zeile in zeilen
    ]
```

Agent 1 gleicht Funktionsnamen (`bankkonto_saldo`, `summe_buchungen`,
`verteilerschluessel_mea_anteil` o. ä.) mit dem bestehenden
Rücklagen-Service ab und benennt sie **nicht um**, wenn bereits
passende Funktionen existieren — nur die fehlende Zusammenführung zu
obiger JSON-Struktur ist neu.

---

## 6. PDF-Layout (WeasyPrint)

### 6.1 Platzierung

Der Rücklagenspiegel erscheint im Einzelabrechnungs-PDF **nach der
Kostenpositionen-Tabelle und vor dem Abrechnungsergebnis** (gleiche
Reihenfolge wie im Wizard: Kostenstellen → Rücklagen →
Einzelabrechnung/Ergebnis, Kap. 5.3).

### 6.2 Tabellenstruktur (eine Tabelle je Rücklage, bzw. eine
gemeinsame Tabelle mit Rücklagen-Namen als Zeilengruppe – Agent 2 wählt
die Variante, die sich mit dem bestehenden CSS/Layout am saubersten
verträgt, und hält beide Optionen kurz fest, falls unklar):

```
Rücklage I – Erhaltungsrücklage
─────────────────────────────────────────────
Anfangsbestand zum 01.01.2025          12.500,00 €
+ Zuführungen                           3.600,00 €
− Entnahmen                             1.800,00 €
= Endbestand zum 31.12.2025            14.300,00 €
  Ihr Anteil (MEA 45/1000)                643,50 €

Rücklage II – Sonderrücklage Aufzug
─────────────────────────────────────────────
...

Summe aller Rücklagen
─────────────────────────────────────────────
Endbestand gesamt                      ... €
Ihr Anteil gesamt                      ... €
```

Bei `klaerungsfall = true` einer Zeile: Endbestand-Zeile optisch
hervorheben (z. B. `*` -Fußnotenzeichen mit Fußnotentext „Abweichung
zum Bankauszug – in Klärung", **keine** rote Fehlerfarbe, da das
kein Fehler der Abrechnung, sondern ein offener Klärungspunkt ist,
analog zum bestehenden Hinweis-Fußnoten-Muster bei
Eigentümerwechsel-PDFs).

### 6.3 CSS/HTML-Grundgerüst (Vorschlag, an bestehendes Template-CSS
anzupassen statt eigenes Stylesheet einzuführen)

```html
<section class="ruecklagenspiegel">
  <h3>Entwicklung der Rücklage{{ "n" if ruecklagen|length > 1 else "" }}</h3>
  {% for rl in ruecklagen %}
  <table class="ruecklagen-tabelle">
    <caption>{{ rl.bezeichnung }}</caption>
    <tr><td>Anfangsbestand zum 01.01.{{ wj.jahr }}</td><td class="betrag">{{ rl.objekt_anfangsbestand|eur }}</td></tr>
    <tr><td>+ Zuführungen</td><td class="betrag">{{ rl.objekt_zufuehrungen|eur }}</td></tr>
    <tr><td>− Entnahmen</td><td class="betrag">{{ rl.objekt_entnahmen|eur }}</td></tr>
    <tr class="endbestand{% if rl.klaerungsfall %} klaerungsfall{% endif %}">
      <td>= Endbestand zum 31.12.{{ wj.jahr }}{% if rl.klaerungsfall %} *{% endif %}</td>
      <td class="betrag">{{ rl.objekt_endbestand_berechnet|eur }}</td>
    </tr>
    <tr><td>Ihr Anteil (MEA {{ rl.mea_anteil_einheit }})</td><td class="betrag">{{ rl.anteil_eigentuemer_betrag|eur }}</td></tr>
  </table>
  {% endfor %}
  {% if ruecklagen_summe %}
  <table class="ruecklagen-summe">
    <tr><td>Endbestand aller Rücklagen</td><td class="betrag">{{ ruecklagen_summe.objekt_endbestand_berechnet|eur }}</td></tr>
    <tr><td>Ihr Anteil gesamt</td><td class="betrag">{{ ruecklagen_summe.anteil_eigentuemer_betrag|eur }}</td></tr>
  </table>
  {% endif %}
  {% if ruecklagen|selectattr("klaerungsfall")|list %}
  <p class="fussnote">* Abweichung zum Bankauszug zum 31.12. – wird durch die Verwaltung geklärt.</p>
  {% endif %}
</section>
```

(Template-Sprache/Filter-Namen an das tatsächlich verwendete
Template-Engine-Setup anpassen — Django-Templates oder Jinja2, je
nachdem was die bestehende WeasyPrint-Pipeline nutzt.)

### 6.4 Seitenumbruch bei vielen Rücklagen

Bei Objekten mit vielen Rücklagen (Praxis: meist 1–3, Spec erlaubt bis
21) muss die Tabelle **nicht** künstlich auf einer Seite gehalten
werden — normaler WeasyPrint-Seitenumbruch (`page-break-inside: avoid`
je Einzel-Tabelle, damit eine Rücklage nicht mitten in der Tabelle
umbricht) reicht aus.

---

## 7. Service-Architektur

```
apps/buchhaltung/services/jahresabrechnung/
├── ruecklagen_service.py       # ggf. bereits vorhanden — Funktionen ergänzen/anpassen
│   ├── berechne_ruecklagen_ausweis(objekt, wirtschaftsjahr) -> list[RuecklagenZeile]
│   └── ergaenze_anteil_je_einheit(zeilen, einheit) -> list[dict]
└── pdf_service.py               # ggf. bereits vorhanden — Template-Kontext ergänzen
    └── baue_ruecklagen_kontext(einzelabrechnung) -> dict
```

> **Hinweis:** Die tatsächlichen Dateinamen/Pfade sind von Agent 1 am
> realen Repo zu verifizieren (Projektstand nennt nur „PDF" und
> „Rücklagen" als zwei der 7 vorhandenen Services, ohne Dateipfad). Wenn
> abweichende Namen bestehen, **diese beibehalten** und nur die
> fehlenden Funktionen/Felder ergänzen — keine Umbenennung bestehender,
> produktiv genutzter Services ohne triftigen Grund.

---

## 8. Tests

### 8.1 Unit-Tests (Agent 3)

| Test | Prüft |
|---|---|
| `test_ruecklagen_ausweis_einzelne_ruecklage.py` | Objekt mit genau einer Rücklage: alle vier Positionen korrekt, keine Summenzeile |
| `test_ruecklagen_ausweis_mehrere_ruecklagen.py` | Objekt mit 3 Rücklagen: je Rücklage korrekt getrennt, Summenzeile = Summe der Einzelwerte |
| `test_ruecklagen_klaerungsfall.py` | Bankauszug-Endbestand ≠ berechneter Endbestand → `klaerungsfall=True`, Toleranz 0,01 € wird nicht fälschlich ausgelöst |
| `test_ruecklagen_anteil_eigentuemer.py` | Anteil je Einheit = Endbestand × MEA, Summe aller Einheiten-Anteile ≈ Objekt-Endbestand (Rundungstoleranz) |
| `test_ruecklagen_zufuehrung_gesamt_konsistenz.py` | `ruecklagen_zufuehrung_gesamt` == Summe `objekt_zufuehrungen` aller Rücklagen |

### 8.2 PDF-Tests (Agent 3, nach Fertigstellung von Agent 2)

- Snapshot-/Struktur-Test: generiertes PDF enthält für jede aktive
  Rücklage des Test-Objekts eine eigene Sektion mit allen vier
  Positionen + Eigentümeranteil.
- Test mit 1 Rücklage: keine Summenzeile im PDF.
- Test mit Klärungsfall: Fußnote erscheint, Endbestand-Zeile trägt die
  Markierung.

### 8.3 Integrationstest

- Vollständiger Wizard-Durchlauf (Schritt 1–8) für ein Test-Objekt mit
  2 Rücklagen → PDF-Vorschau (Schritt 7) zeigt den vollständigen
  Rücklagenspiegel für beide Rücklagen an → Freigabe (Schritt 8) →
  Endgültiges PDF entspricht der Vorschau (Unveränderlichkeit nach
  Sperrung, Kap. 6.1).

---

## 9. Aufgaben für Claude Code

> **Hinweis an Claude Code:** Reihenfolge unten strikt einhalten. Nach
> jedem Schritt: Migration erzeugen (falls Feldstruktur sich ändert),
> Tests laufen lassen, erst dann zum nächsten Schritt. Keine
> Datenbank-Änderungen ohne Migration. Geschäftslogik ausschließlich in
> `services/`, nie in Views, Models oder Templates.

### Schritt 1 (Agent 1) — Ist-Zustand am Code verifizieren

- Bestehenden Rücklagen-Service und PDF-Service lokalisieren, Ist-Stand
  gegen Kap. 2 dieser Spec abgleichen, kurz dokumentieren, was bereits
  vorhanden ist und was fehlt.

### Schritt 2 (Agent 1) — Datenstruktur & Berechnung

- `berechne_ruecklagen_ausweis` und `ergaenze_anteil_je_einheit` gemäß
  Kap. 4 + 5 implementieren bzw. anpassen.
- Bestehende Aufrufer (Wizard-Schritt 5, `EinzelAbrechnung`-Erzeugung)
  auf die neue/vollständige Struktur umstellen.
- Migration nur nötig, falls sich Feldtypen ändern (JSONField-Inhalt
  selbst braucht i. d. R. keine Migration).

### Schritt 3 (Orchestrator) — Review & Freigabe der Datenstruktur

- Struktur gegen Kap. 4 prüfen, insbesondere Konsistenz
  `ruecklagen_zufuehrung_gesamt` ↔ `ruecklagen`-Summe.
- Erst nach Freigabe: Schritt 4 und 5 parallel starten.

### Schritt 4 (Agent 2) — PDF-Template erweitern

- Rücklagenspiegel-Sektion gemäß Kap. 6 in das bestehende
  Einzelabrechnungs-Template einfügen.
- Bestehendes CSS/Layout wiederverwenden, kein neues Stylesheet ohne
  Notwendigkeit.

### Schritt 5 (Agent 3, parallel zu Schritt 4) — Service-Tests

- Tests aus Kap. 8.1 schreiben und grün bekommen.

### Schritt 6 (Agent 3, nach Schritt 4) — PDF-Tests

- Tests aus Kap. 8.2 schreiben und grün bekommen.

### Schritt 7 (Orchestrator) — Integrationstest & Abschluss

- Test aus Kap. 8.3 durchführen.
- Gesamte bestehende Testsuite des Jahresabrechnungs-Moduls laufen
  lassen (Regressionscheck), Ergebnis melden.

---

## 10. Abgrenzung / Nicht-Ziel

- Kein separates, eigenständiges „Rücklagenspiegel"-Dokument außerhalb
  der Einzelabrechnung — nur Integration in das bestehende PDF.
- Keine Änderung an der Berechnungsformel selbst (Kap. 6.4 bleibt
  fachlich unverändert).
- Kein Soll/Ist-Vergleich mit `WirtschaftsplanRuecklage` (geplante
  Zuführung) in dieser Spec — das wäre eine mögliche spätere
  Erweiterung, aber nicht Teil des aktuellen Auftrags.
- Kein Eingriff in den Auszahlungslauf für Abrechnungsguthaben
  (Hausgeld-Nebenbuch Kap. 10.5) — dieser bleibt unverändert.

*Ende der Spezifikation.*
