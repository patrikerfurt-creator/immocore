# IMMOCORE — Umbau Rechnungseingang | Claude Code Prompt v1.1

**IMMOCORE** — *Webbasiertes Immobilienverwaltungssystem*
**Modul:** Rechnungseingang — **zweistufig**: Buchhaltung prüft KI-Erfassung → Freigabe nach Objekt-Limit
**Demme Immobilien Verwaltung GmbH** — Coventrystraße 32, 65934 Frankfurt am Main
**Version:** 1.1 | **Stand:** Juli 2026
**KI-Modell:** `claude-sonnet-4-6`

> **Diese Version löst v1.0 vollständig ab.** v1.0 hatte den Prozess
> fälschlich einstufig gebaut, ein persönliches `User.freigabe_limit`
> eingeführt und den Erkennungs-/Routing-/Lern-Apparat in Phase D
> abgerissen. Das war falsch. Siehe Änderungsprotokoll Kap. 0.

---

## 0. Änderungsprotokoll v1.0 → v1.1

| # | v1.0 (falsch) | v1.1 (korrekt) |
|---|---|---|
| 1 | Einstufig (eine Inbox, Erfassen + ggf. Freigeben in einem) | **Zweistufig:** Stufe 1 Buchhaltung prüft KI-Erfassung → Stufe 2 Rechnungsfreigabe |
| 2 | `User.freigabe_limit` (persönliches Limit) | **Ersatzlos entfernt.** Freigabe wieder rein über objektbasierte `zahlungsfreigabe_grenzen` (Rolle + Betragsschwelle) |
| 3 | Auto-Erkennung + Routing + Match-Lernlogik in Phase D abgerissen | **Kompletter Abriss gestrichen.** Erkennung, Match, Identifizierung, Lernregeln, Routing **bleiben erhalten.** Deaktiviert wird **nur** die automatische Verbuchung |
| 4 | Buchhalter „erfasst" manuell | Buchhalter **prüft** die automatische KI-Erfassung (Stufe 1) |
| 5 | — | **Neuer Menüpunkt „Rechnungsfreigabe"** (Stufe 2) |
| 6 | Match-Regel-Handling unklar | Match-Regel wird bei Korrektur **nur in Stufe 2** aktualisiert, **mit Rückfrage** |
| 7 | — | Button **„Sachkonto speichern" → „Freigabe"** in der Freigabe-Ansicht (Funktion unverändert) |

**Aus v1.0 unverändert übernommen (war in Ordnung):** Skonto-Buchung
(Kap. 8), §35a-Feld, Kostenverursacher + Debitornummer im Buchungstext,
Schlussrechnung-Flag, Verifikations-Ampel (jetzt in **Stufe 1**),
GoBD/Kassenprinzip, Logik in `services/`, HALT-Gates.

---

## 1. Zielbild — der zweistufige Prozess

```
Rechnung kommt an (PDF / XRechnung / Mail-Intake)
        │
        ▼
[ Erkennungs-Pipeline v1.2 — UNVERÄNDERT ]
  KI-OCR, Match, Identifizierung, RechnungsMatchRegel, erkennungs_konfidenz
  Ergebnis: erkannt / pruefung_match / nicht_erkannt
        │
        │  ⚠ KEINE automatische Verbuchung mehr (einziger Eingriff, Kap. 4)
        ▼
┌───────────────────────────────────────────────────────────────┐
│ STUFE 1 — BUCHHALTUNG (dem Objekt zugeordnet)                  │
│   Menüpunkt: „Rechnungsprüfung"                                │
│   • prüft die automatische Erfassung (Kreditor, Konto, Betrag) │
│   • Verifikations-Ampel sichtbar (Kap. 6)                      │
│   • ergänzt §35a, Kostenverursacher, Skonto, Schlussrechnung   │
│   • darf korrigieren — löst KEIN Match-Regel-Update aus        │
│   • Aktion: „Geprüft → zur Freigabe"                           │
└───────────────────────────────────────────────────────────────┘
        │  Status: zur_freigabe
        ▼
┌───────────────────────────────────────────────────────────────┐
│ STUFE 2 — RECHNUNGSFREIGABE (neuer Menüpunkt)                  │
│   Freigeber = Objektbetreuer / Sachbearbeiter / GF            │
│              je nach zahlungsfreigabe_grenzen (Betragsschwelle)│
│   • gibt frei ODER passt an                                    │
│   • Sachkonto-Korrektur → Match-Regel-Update MIT Rückfrage     │
│   • Button „Freigabe" (ehem. „Sachkonto speichern")           │
└───────────────────────────────────────────────────────────────┘
        │  Status: freigegeben  →  OP-Buchung (Soll 15900 / Haben Kreditor)
        ▼
   Zahlungslauf → (Skonto-Prüfung, Kap. 8) → bezahlt / teilbezahlt
```

**Kernprinzip:** Der gesamte v1.2-Apparat bleibt als *Werkzeug* erhalten.
Die einzige strukturelle Änderung ist, dass **keine Rechnung mehr
automatisch gebucht wird** — stattdessen läuft jede Rechnung durch die
zwei menschlichen Stufen.

---

## 2. ⚠ Zwei Interpretationspunkte — VOR Implementierung bestätigen

> Diese beiden Punkte ließen sich aus der Anforderung nicht eindeutig
> ableiten. Ich habe je einen Default gewählt (unten umgesetzt). **Bitte
> bestätigen oder korrigieren, bevor Claude Code startet.**

**E1 — Zuordnung Buchhaltung ↔ Objekt.**
„Die Buchhaltung, die dem Objekt zugeordnet ist" setzt eine Zuordnung
voraus, die es bisher nicht gibt (v1.2 kennt nur `Objekt.betreuer`,
`Objekt.sachbearbeiter`, Rolle `Frontoffice`).
*Default v1.1:* neues Feld **`Objekt.buchhaltung`** (M2M → `User`) plus
Rolle **`Buchhaltung`**. Stufe-1-Rechnungen eines Objekts erscheinen in
der „Rechnungsprüfung"-Inbox aller zugeordneten Buchhalter.
*Zu klären:* genau eine Person (FK) statt mehrerer (M2M)? Und: ersetzt
die Rolle `Buchhaltung` die alte Rolle `Frontoffice`, oder bestehen beide?

**E2 — Wer bearbeitet Prüffälle (`pruefung_match` / `nicht_erkannt`) in Stufe 1?**
Im alten Ablauf gingen Prüffälle an Objektbetreuer bzw. Frontoffice.
*Default v1.1:* In Stufe 1 ist **die Buchhaltung** die einheitliche
Instanz für **alle** Erkennungsstufen — auch für Prüffälle. Der
Identifizierungs-Apparat (Kreditor/Konto ergänzen, Doppel-Button-Logik,
Matching) bleibt vollständig erhalten, wird aber in der Buchhaltungs-Inbox
bedient. Das alte Objektbetreuer-/Frontoffice-*Prüffall-Routing* entfällt
zugunsten der Buchhaltungs-Zuordnung (E1); der Objektbetreuer wird zum
**Stufe-2-Freigeber**.
*Zu klären:* Soll stattdessen das alte Prüffall-Routing (Objektbetreuer/
Frontoffice) für die Identifikation erhalten bleiben und die Buchhaltung
nur „sauber erkannte" Rechnungen prüfen?

---

## 3. Phase 0 — Verifikationsgate (PFLICHT vor jeder Migration)

> **HALT.** Erst gegen den realen Code beantworten, Ergebnis im PR
> dokumentieren. Bei Abweichung gilt der Code → STOP + Rückfrage.

| # | Frage | Annahme dieser Spec |
|---|---|---|
| **V1** | `Rechnung`-Model + App? | `apps/buchhaltung` — `Rechnung` |
| **V2** | Exakte `Rechnung`-Felder heute? | inkl. v1.2-Erkennungsfelder (`erkennungs_stufe`?, `erkennungs_konfidenz`, `zugewiesen_an`, `match_regel`, `leistungstext`, `leistungstext_hash`) |
| **V3** | Exaktes Statusenum heute? | `erkannt`/`pruefung_match`/`nicht_erkannt`/`in_pruefung`/`freigegeben`/`gebucht`/`bezahlt`/`abgelehnt` (+ evtl. `erfasst`/`auto_freigabe`) |
| **V4** | Debitornummer? | **GEKLÄRT:** `Personenkonto.kontonummer` (`apps.konten`, `CharField(4)`, führende Nullen, je Objekt fortlaufend). OneToOne `Personenkonto.vertrag → EigentumsVerhaeltnis` (`related_name='personenkonto'`). ⚠ Drift: Nebenbuch-Spec wollte `Personenkonto` entfernen — existiert real noch (Bestätigungspunkt B7). |
| **V5** | Aktueller Eigentümer einer Einheit? | Kein Property `aktuelles_eigentumsverhaeltnis`. Filter selbst: `einheit.eigentumsverhaeltnisse.filter(ende__isnull=True)` bzw. zum Stichtag (Kap. 7.2). |
| **V6** | Kreditor-Sachkonto (`70xxx`)? | `rechnung.kreditor.sachkonto` |
| **V7** | Existieren real: `route_rechnung`, `ermittle_freigabestufe`, `ermittle_freigabeperson`, `darf_betreuer_direkt_freigeben`, `buche_rechnung`, `RechnungsMatchRegel`, `RechnungsErkennungsLog`, `RechnungsBearbeitungsLock`, Rolle `Frontoffice`, `Objekt.betreuer`/`sachbearbeiter`? | Vermutlich ja (v1.2). **Alle bleiben erhalten** — nur der Auto-Buchungspfad wird umgebogen (Kap. 4). Liste real vorhandener Elemente erstellen. |
| **V8** | Struktur `zahlungsfreigabe_grenzen`? | `{"stufen":[{"bis":499.99,"rolle":"auto"},{"bis":1999.99,"rolle":"sachbearbeiter","frist_tage":3,"eskalation":"geschaeftsfuehrer"},{"bis":9999.99,"rolle":"geschaeftsfuehrer","frist_tage":5}],"ueber_10000":{"rollen":["geschaeftsfuehrer"],"frist_tage":7}}` |
| **V9** | Wie ist `buche_rechnung` heute verdrahtet (Aufrufstellen)? | In `route_rechnung`, Auto-Zweig + (v1.2) Konfidenz-≥95%-Zweig. **Diese Aufrufe entfernen** (Kap. 4). |
| **V10** | Gibt es bereits eine Buchhaltung↔Objekt-Zuordnung? | Vermutlich nein → neues Feld gem. E1. |

---

## 4. Der EINE Eingriff in die Pipeline: Auto-Buchung deaktivieren

Der Erkennungs-/Routing-Code bleibt. Geändert wird nur `route_rechnung`,
sodass **niemals** automatisch gebucht wird und jede Rechnung in Stufe 1
(Buchhaltung) landet.

**Vorher (v1.2, sinngemäß):**
```python
def route_rechnung(rechnung):
    if rechnung.status == 'erkannt':
        stufe = ermittle_freigabestufe(rechnung.betrag, grenzen)
        if stufe['rolle'] == 'auto' and rechnung.erkennungs_konfidenz >= 0.95:
            buche_rechnung(rechnung)          # ← AUTO-BUCHUNG
            return
        rechnung.status = 'in_pruefung'
        rechnung.zugewiesen_an = ermittle_freigabeperson(rechnung.objekt, stufe)
        ...
    if rechnung.status in ('pruefung_match', 'nicht_erkannt'):
        rechnung.zugewiesen_an = rechnung.objekt.betreuer  # bzw. Frontoffice
        ...
```

**Nachher (v1.1):**
```python
def route_rechnung(rechnung):
    """Kein Auto-Buchen mehr. Jede Rechnung geht in Stufe 1 (Buchhaltung).
    Die Erkennung (erkannt/pruefung_match/nicht_erkannt) bleibt als
    Prüf-Kontext erhalten und steuert die UI-Hinweise in Stufe 1."""
    rechnung.status = 'in_buchhaltung'
    rechnung.buchhaltung_inbox = _zustaendige_buchhaltung(rechnung.objekt)  # E1
    rechnung.save(update_fields=['status', ...])
```

- `buche_rechnung` wird **nicht gelöscht** — es wird künftig nur noch am
  Ende von **Stufe 2** (Freigabe) aufgerufen (Kap. 5.2).
- `ermittle_freigabestufe` / `ermittle_freigabeperson` bleiben und werden
  in Stufe 2 verwendet (Kap. 5.2).
- Der v1.2-Konfidenz-≥95%-Auto-Zweig entfällt. Die 95%-Schwelle lebt
  aber weiter — als **Ampel** in Stufe 1 (Kap. 6), nicht als Buchungs-Trigger.

---

## 5. Die zwei Stufen im Detail

### 5.1 Stufe 1 — Buchhaltung („Rechnungsprüfung")

**Zweck:** Prüfung der automatischen KI-Erfassung, keine Buchung.

- Inbox zeigt alle Rechnungen `in_buchhaltung` der Objekte, denen der
  User als Buchhaltung zugeordnet ist (E1). Filter: erkannt / Prüffall.
- Erkennungs-Kontext sichtbar: Erkennungsstufe, gematchter Kreditor/Konto,
  angewandte `RechnungsMatchRegel`, **Verifikations-Ampel** (Kap. 6).
- Prüffälle (`pruefung_match`/`nicht_erkannt`): der bestehende
  Identifizierungs-Apparat (Kreditor/Konto ergänzen) steht zur Verfügung
  (E2).
- Ergänzt hier: `betrag_haushaltsnah` (§35a), `kostenverursacher`,
  `skonto_*`, `ist_schlussrechnung` (Kap. 7 / 8 / Datenmodell).
- **Korrekturen in Stufe 1 lösen KEIN Match-Regel-Update aus** (bewusste
  Entscheidung; Lern-Loop hängt allein an Stufe 2).
- Abschluss-Aktion **„Geprüft → zur Freigabe"**: Status → `zur_freigabe`,
  ruft `route_zur_freigabe(rechnung)` (setzt Freigabestufe/-person via
  `ermittle_freigabestufe`/`ermittle_freigabeperson`).
- **Ablehnen** jederzeit möglich (mit Begründung) → `abgelehnt`.

> Auto-Stufe (`rolle == 'auto'`, Bagatellbeträge): Auch diese Rechnungen
> durchlaufen Stufe 1. Ob sie Stufe 2 überspringen dürfen (Buchhaltung
> gibt direkt frei) → Bestätigungspunkt **B1**. Default v1.1: **nein**,
> auch Bagatellen laufen durch Stufe 2, damit der Prozess einheitlich ist.

### 5.2 Stufe 2 — Rechnungsfreigabe (neuer Menüpunkt)

**Zweck:** Freigabe nach objektbasiertem Limit; letzte Korrekturmöglichkeit
mit Lern-Loop.

- Neuer Menüpunkt **„Rechnungsfreigabe"**. Liste aller Rechnungen
  `zur_freigabe`, für die der eingeloggte User laut
  `zahlungsfreigabe_grenzen` zuständig ist (Objektbetreuer/Sachbearbeiter
  in der passenden Betragsstufe bzw. GF).
- Zuständigkeit über bestehende Funktionen:
  ```python
  def darf_freigeben(rechnung, user) -> bool:
      stufe = ermittle_freigabestufe(rechnung.betrag_brutto,
                                     rechnung.objekt.zahlungsfreigabe_grenzen)
      person = ermittle_freigabeperson(rechnung.objekt, stufe)  # bzw. Rollencheck
      if stufe['rolle'] == 'sachbearbeiter':
          return user in rechnung.objekt.sachbearbeiter.all()
      if stufe['rolle'] == 'geschaeftsfuehrer':
          return user.has_role('Geschaeftsfuehrer')
      return False
  ```
- **Freigeben:** OP-Buchung via bestehendem `buche_rechnung` /
  Freigabe-Service → Status `freigegeben`. Buchungstext mit Debitornummer
  (Kap. 7.2).
- **Anpassen:** Freigeber darf das **Sachkonto** (und OCR-Felder)
  korrigieren.
- **Button „Freigabe"** (ersetzt „Sachkonto speichern"; Funktion
  technisch unverändert): speichert das ggf. korrigierte Sachkonto **und**
  schließt die Freigabe ab. Bei geändertem Sachkonto → Match-Regel-Rückfrage
  (Kap. 5.3).
- Über Limit → Eskalation an GF über den bestehenden Mechanismus
  (`eskalation`/`frist_tage` aus `zahlungsfreigabe_grenzen`).
- **Ablehnen** → `abgelehnt` (Begründung, kein Lerneffekt).

### 5.3 Match-Regel-Update — nur Stufe 2, mit Rückfrage

Der v1.2-Trigger B („Korrektur in der Freigabe") wird von *automatisch*
auf *mit Rückfrage* umgestellt und ist der **einzige** aktive Lern-Trigger.

```python
# beim Klick „Freigabe" in Stufe 2, wenn buchungskonto geändert wurde:
if neues_konto != altes_konto:
    # Frontend-Dialog: „Zuordnung geändert — Match-Regel aktualisieren? [Ja] [Nein]"
    if antwort == 'ja':
        alte_regel.status = 'veraltet'
        RechnungsMatchRegel.objects.create(
            kreditor=rechnung.kreditor, objekt=rechnung.objekt,
            leistungstext_hash=rechnung.leistungstext_hash,
            buchungskonto=neues_konto, erstellt_aus='freigabe_korrektur',
        )
    # 'nein' → keine Regeländerung, Freigabe trotzdem abschließen
```

- **Trigger A (Prüffall-Identifikation)** und **Trigger C (manuelle
  Erfassung)** aus v1.2 erzeugen in v1.1 **keine** Regeln mehr, da
  Identifikation jetzt in Stufe 1 passiert und dort nicht gelernt wird
  (E2 / „nur Stufe 2"). Falls die Buchhaltung bei ganz neuen Kreditoren
  doch lernen soll → Bestätigungspunkt **B6**.
- Idempotenz/Constraint `unique_together (kreditor, objekt,
  leistungstext_hash)` bleibt; gleiche Konto-Wahl → nur `trefferzahl++`.

---

## 6. Verifikations-Ampel (aus v1.0 — jetzt in Stufe 1)

Unverändert zur v1.0-Mechanik, nur der Ort ist Stufe 1 (Buchhaltung prüft
die KI-Erfassung). Kurzfassung; Details wie gehabt:

- **🟢 grün ≥ 95 %**, 🟡 80–94,99 %, 🔴 < 80 % (Konstanten, konfigurierbar → B8).
- Pro Feld hybrid: LLM-Selbstkonfidenz **+ deterministische Validierung**
  (IBAN-Prüfziffer + Treffer in `Person.ibans`; Rechenprobe
  `netto+USt=brutto`; Duplikat-Check `(kreditor, rechnungsnummer)`;
  Skonto-Plausibilität; `betrag_haushaltsnah ≤ brutto`; Kostenverursacher-
  Einheit im Objekt). Harte Bestätigung → grün; harter Widerspruch → rot,
  überstimmt LLM.
- **Gesamt per Veto:** grün nur, wenn alle kritischen Felder (`kreditor`,
  `betrag_brutto`, `rechnungsnummer`) ≥ 95 % und nichts rot; Gesamtwert =
  Minimum der kritischen Felder.
- Rotes kritisches Feld sperrt „Geprüft → zur Freigabe", bis korrigiert.
- Service `apps/buchhaltung/services/erkennung_ampel_service.py`,
  Felder `erkennung_ampel` / `erkennung_gesamt_konfidenz` /
  `erkennung_details`. Kalibrierungs-Logging über `RechnungsErkennungsLog`.
- Nutzt `erkennungs_konfidenz` (v1.2) als LLM-Basiswert — **nicht** entfernen.

---

## 7. Datenmodell — Änderungen

### 7.1 `Rechnung` — neue Felder (wie v1.0, unverändert)

| Feld | Typ | Anmerkung |
|---|---|---|
| `kostenverursacher` | FK → `Einheit` (SET_NULL, null) | Genau eine Einheit des Objekts. Durchsuchbares Dropdown (Kap. 7.3). |
| `betrag_haushaltsnah` | DecimalField(12,2), default 0 | §35a-Lohnanteil, per KI ausgelesen. `≤ betrag_brutto`. |
| `ist_schlussrechnung` | BooleanField, default False | Flag (B4). |
| `skonto_prozent` | DecimalField(5,2), null | Aus Rechnung. |
| `skonto_betrag` | DecimalField(12,2), null | Berechnet falls nur Prozent. |
| `skonto_faellig_bis` | DateField, null | Pflicht, sobald Skonto gesetzt. |
| `skonto_genutzt` | BooleanField, default False | Zahlungslauf setzt. |
| `erkennung_ampel` | CharField `gruen`/`gelb`/`rot`, null | Kap. 6. |
| `erkennung_gesamt_konfidenz` | DecimalField(5,2), null | 0–100, Kap. 6. |
| `erkennung_details` | JSONField, default dict | Anzeige-Snapshot je Feld (keine Logik). |
| `buchhaltung_inbox` | FK/M2M-Ableitung → siehe E1 | Zuordnung Stufe-1-Bearbeitung. |

**Neuer/geänderter Status-Fluss** (additiv, Cleanup erst Phase D):
`in_buchhaltung` (Stufe 1) → `zur_freigabe` (Stufe 2 offen) → `freigegeben`
→ `teilbezahlt`/`bezahlt`; quer: `abgelehnt`, `storniert`.
Erkennungsstatus `erkannt`/`pruefung_match`/`nicht_erkannt` bleiben als
**Erkennungs-Kontext** erhalten (eigenes Feld `erkennungs_stufe`), nicht
als Lifecycle-Status. `auto_freigabe`/`gebucht` entfallen (keine Auto-Buchung).

### 7.2 Buchungstext mit Debitornummer (aus v1.0, unverändert)

```python
from django.db.models import Q

def _aktives_ev(einheit, stichtag=None):
    qs = einheit.eigentumsverhaeltnisse.all()
    if stichtag is None:
        return qs.filter(ende__isnull=True).first()
    return qs.filter(beginn__lte=stichtag).filter(
        Q(ende__isnull=True) | Q(ende__gte=stichtag)).first()

def ermittle_debitor_nr(einheit, stichtag=None):
    ev = _aktives_ev(einheit, stichtag)
    pk = getattr(ev, "personenkonto", None) if ev else None
    return pk.kontonummer if pk else None            # V4

def baue_buchungstext(rechnung) -> str:
    basis = f"OP Rechnung {rechnung.rechnungsnummer} – {rechnung.kreditor.name}"
    einheit = rechnung.kostenverursacher
    if einheit:
        stichtag = rechnung.rechnungsdatum           # B2
        ev = _aktives_ev(einheit, stichtag)
        deb = ermittle_debitor_nr(einheit, stichtag)
        name = str(ev.person) if ev and ev.person else "?"
        deb_txt = f"PKto {deb} " if deb else ""
        basis += f" | Einzelkosten {deb_txt}{einheit.einheit_nr} {name}"
    return basis
```

### 7.3 `Objekt` — neue Buchhaltungs-Zuordnung (E1)

| Feld | Typ | Anmerkung |
|---|---|---|
| `buchhaltung` | M2M → `User` (limit rolle=`Buchhaltung`) | Stufe-1-Inbox-Zuordnung. Default M2M; ggf. FK (E1). |

Neue Rolle `Buchhaltung` (E1). `betreuer`/`sachbearbeiter`/`Frontoffice`
bleiben unverändert bestehen.

---

## 8. Skonto (aus v1.0 — unverändert)

OP bei Freigabe über Brutto. Zahlung innerhalb `skonto_faellig_bis`:
nur geminderter Betrag fließt, Skonto **mindert Aufwand**, **keine Einnahme**.

```
Freigabe:  Soll 15900 (Brutto)      / Haben 70xxx Kreditor (Brutto)
Zahlung (a): Soll 70xxx (Brutto) / Haben 18xxx Bank (Zahlbetrag) / Haben 15900 (Skonto)
Zahlung (b): Soll 5xxxx Aufwand (Zahlbetrag) / Haben 15900 (Zahlbetrag)
```
Kontrolle: 15900 → 0, Kreditor → 0, Aufwand = Zahlbetrag, kein Ertragskonto.
Skonto nur bei Vollzahlung innerhalb Frist (B5). WEG i. d. R. kein
Vorsteuerabzug → brutto, keine USt-Korrektur.

---

## 9. Frontend

- **Menüpunkt „Rechnungsprüfung" (Stufe 1):** Buchhaltungs-Inbox mit
  Erkennungs-Kontext + Verifikations-Ampel (gesamt + je Feld), Ergänzungs-
  felder, Aktion „Geprüft → zur Freigabe" / „Ablehnen".
- **Neuer Menüpunkt „Rechnungsfreigabe" (Stufe 2):** Liste der eigenen
  offenen Freigaben; Detail mit Sachkonto-Korrektur; **Button „Freigabe"**
  (ehem. „Sachkonto speichern"); bei Kontoänderung Match-Regel-Dialog.
- Kostenverursacher-Dropdown mit Suchzeile (Suche über `einheit_nr`,
  `lage`, Eigentümername; Anzeige inkl. „PKto 0005").
- Prüffall-Bearbeitung: bestehende Identifizierungs-UI aus v1.2 in Stufe 1
  weiternutzen (E2).

---

## 10. Phasen & HALT-Gates

| Phase | Inhalt | Gate |
|---|---|---|
| **0** | Verifikationsgate Kap. 3 (V1–V10) + E1/E2 bestätigt | **HALT** bis beantwortet |
| **A** | Migrationen: neue `Rechnung`-Felder, `Objekt.buchhaltung` + Rolle `Buchhaltung`, neue Status additiv; **nichts entfernen** | **HALT** — Migration grün, SQL-Review |
| **B** | `route_rechnung` auf „kein Auto-Buchen" umbiegen (Kap. 4); Stufe-1-Service (`route_zur_freigabe`), Stufe-2-Freigabe-Service (nutzt `buche_rechnung`/`ermittle_freigabestufe`), Match-Regel-Update-mit-Rückfrage, Ampel-Service, Skonto, Buchungstext | **HALT** — Pflichttests Kap. 11 grün |
| **C** | Frontend: Menüpunkte Rechnungsprüfung + Rechnungsfreigabe, Ampel-UI, Dropdown, Button-Umbenennung, Match-Dialog | **HALT** — Smoke-Test Kap. 11.3 durch Patrik |
| **D** | **Minimaler** Cleanup: nur `auto_freigabe`/`gebucht`-Status migrieren + toten Auto-Buchungs-Zweig entfernen. **KEIN** Abriss von Erkennung/Routing/Match/Lock | **HALT vor jeder Löschung** |

> **Wichtig:** Anders als v1.0 gibt es in Phase D **keinen** Rückbau der
> Erkennungs-/Routing-/Lernlogik. Entfernt wird ausschließlich der
> verwaiste Auto-Buchungspfad und die zwei toten Status.

---

## 11. Tests & Akzeptanz

### 11.1 Unit
- `route_rechnung`: erzeugt **nie** eine Buchung; jede Rechnung → `in_buchhaltung`.
- `darf_freigeben`: Sachbearbeiter-Stufe nur für konfigurierte Sachbearbeiter; GF-Stufe nur GF; korrekte Stufe je Betrag.
- Match-Update: Stufe-2-Kontoänderung + „Ja" → alte Regel `veraltet`, neue `freigabe_korrektur`; „Nein" → keine Regeländerung, Freigabe trotzdem; **Stufe-1-Korrektur erzeugt nie eine Regel**.
- Ampel: `feld_konfidenz` (fehler→0, ok→≥0,95, warnung→LLM); Gesamt-Veto (krit. Feld fehler→rot; 100/100/85 → gelb, nicht grün).
- Skonto/Buchungstext/`clean()` wie v1.0.

### 11.2 Integration (Workflow-Pfade)
- P1 — erkannt, 250 € (Auto-Stufe): landet in Stufe 1 (nicht auto gebucht) → geprüft → Stufe 2 → freigegeben.
- P2 — erkannt, 5.000 €: Stufe 1 → Stufe 2 nur für GF sichtbar → freigegeben (OP-Buchung).
- P3 — pruefung_match: Stufe 1 Buchhaltung identifiziert Konto (kein Regel-Update) → zur Freigabe.
- P4 — Stufe 2 Kontoänderung + „Ja" → Regel `freigabe_korrektur`.
- P5 — Skonto innerhalb Frist → nur Zahlbetrag gebucht, kein Ertragskonto.
- P6 — Freigabe über Limit → Eskalation GF.
- P7 — Kostenverursacher gesetzt → Buchungstext mit PKto.

### 11.3 Smoke-Test (vor Phase D)
1. Rechnung erscheint in „Rechnungsprüfung" (nicht gebucht), Ampel sichtbar.
2. Buchhaltung korrigiert Konto → keine Regel-Rückfrage.
3. „Geprüft → zur Freigabe" → Rechnung erscheint in „Rechnungsfreigabe" beim zuständigen Freigeber.
4. Freigeber ändert Konto, klickt **„Freigabe"** → Match-Dialog „Ja" → freigegeben + OP-Buchung, Regel aktualisiert.
5. Skonto-Zahlung innerhalb Frist → nur geminderter Betrag verbucht.

---

## 12. Offene Bestätigungspunkte

- **E1 — Buchhaltung↔Objekt** (Kap. 2): M2M + Rolle `Buchhaltung` (Default) vs. FK; Verhältnis zur alten Rolle `Frontoffice`.
- **E2 — Prüffall-Bearbeitung in Stufe 1** (Kap. 2): Buchhaltung übernimmt alle Erkennungsstufen (Default) vs. altes Objektbetreuer-/Frontoffice-Prüffall-Routing beibehalten.
- **B1 — Bagatell/Auto-Stufe:** Auch Bagatellbeträge durch Stufe 2 (Default) oder darf Stufe 1 sie direkt freigeben?
- **B2 — Eigentümer-Stichtag:** Debitor/Name zum Rechnungsdatum (Default).
- **B4 — Schlussrechnung:** nur Flag, keine Abschlags-Anrechnung.
- **B5 — Teil-Skonto:** nur bei Vollzahlung innerhalb Frist.
- **B6 — Lernen in Stufe 1:** Bei ganz neuen Kreditoren doch eine Regel erzeugen? (Default: nein — nur Stufe 2.)
- **B7 — Personenkonto vs. Nebenbuch-Spec:** `Personenkonto` bleibt Quelle der Debitornummer; falls später entfernt, `kontonummer` vorher auf bleibendes Model migrieren.
- **B8 — Ampel-Schwellen/kritische Felder:** Grenzen + kritische Feldmenge bestätigen; global oder je Objekt.

---

## 12a. Implementierungs-Änderungsprotokoll (Stand 14.07.2026 — umgesetzt)

> Dieses Kapitel dokumentiert die bei der Umsetzung getroffenen
> Entscheidungen und Abweichungen. Die Phasen A–D sind vollständig
> implementiert (Branch `feature/rechnungseingang-umbau`); Smoke-Test
> Kap. 11.3 durch Patrik bestanden.

### Aufgelöste Verifikations-Abweichungen (Phase 0, Code gilt)

| # | Spec-Annahme | Realer Code (umgesetzt) |
|---|---|---|
| V1 | `Rechnung` in `apps.buchhaltung` | **`apps.rechnungen`**; alle Services in `apps/rechnungen/services/` |
| V6 | `rechnung.kreditor.sachkonto` | `kreditor.kreditorennummer` → `get_or_create_kreditor_konto()` |
| V7 | `buche_rechnung` | existiert nicht — Buchung = `rechnung_freigeben` (rechnung_op_service) |
| V8 | verschachtelte Grenzen-Struktur | flache Liste `[{bis, rolle, frist_tage, beschreibung}]` + `FreigabelimitDefault`-Fallback |
| V9 | Auto-Buchung in `route_rechnung` | Auto-Pfad war `_route_limit_workflow` + `op_freigeben(freigegeben_von=None)` in `verarbeitung.py` — beide in Phase D entfernt |
| V10 | keine Buchhaltung↔Objekt-Zuordnung | **existierte bereits**: `MitarbeiterObjektZuordnung` (`aufgabe='buchhaltung'`) + Abteilung `buchhaltung` |

### Entschiedene Bestätigungspunkte

- **E1:** KEIN neues Feld `Objekt.buchhaltung`, KEINE neue Rolle — die
  vorhandene `MitarbeiterObjektZuordnung` (`aufgabe='buchhaltung'`) ist die
  Stufe-1-Zuordnung. Frontoffice-Strukturen bestehen unverändert weiter.
- **E2:** Default bestätigt — die Buchhaltung bearbeitet in Stufe 1 alle
  Erkennungsstufen (inkl. Prüffälle, Identifizierungs-Apparat in der
  Buchhaltungs-Inbox).
- **B1:** Default bestätigt — auch Bagatellen durchlaufen Stufe 2;
  zuständig ist die nächste manuelle Stufe der Grenzen-Konfiguration.
- **B2/B4/B5/B7/B8:** Defaults bestätigt (Rechnungsdatum-Stichtag; nur
  Flag; kein Teil-Skonto; Personenkonto bleibt Debitor-Quelle; Ampel 95/80
  global, kritische Felder kreditor/betrag_brutto/rechnungsnummer).
- **B6 — GEÄNDERT (Patrik, 14.07.2026), ersetzt Kap. 5.3 teilweise:**
  Die Match-Regel wird bereits beim **Stufe-1-Abschluss** „Geprüft → zur
  Freigabe" aus der geprüften Kontierung **erstellt/bestätigt**
  (`route_zur_freigabe(geprueft_von=…)`, `erstellt_aus='pruefung'`;
  gleiches Konto → `trefferzahl++`). Der Stufe-2-Freigeber **ändert** sie
  nur bei bewusster Konto-Korrektur **mit Rückfrage-Dialog** (Ja → alte
  Regel `veraltet`, neue `freigabe_korrektur`; Nein → keine Regeländerung).
  Reines Zwischenspeichern in Stufe 1 (`identifizieren` modus
  'speichern', Entwurf) lernt weiterhin nicht.

### Weitere nachträgliche Festlegungen (Patrik, 14.07.2026)

1. **Menüpunkt Stufe 1 heißt „Rechnungseingang"** (nicht
   „Rechnungsprüfung" wie Kap. 5.1/9); Stufe 2 heißt „Rechnungsfreigabe".
2. Rechnungen im Status `zur_freigabe` erscheinen NICHT mehr in der
   Stufe-1-Inbox (nur in der Rechnungsfreigabe).
3. **SEPA-Export zahlt Skonto-gemindert** (Konsistenz zu Kap. 8): Der
   pain.001-Betrag = Zahlbetrag via `skonto_anwendbar(faelligkeitsdatum)`,
   Verwendungszweck „abzgl. X Skonto", Zahlungslauf-Protokoll ebenso.
4. Skonto-Buchung an das reale 3-Phasen-Modell (Zwischenkonto 13600)
   angepasst: Phase 2 = Soll 70xxx/Haben 13600 (Zahlbetrag) **+**
   Soll 70xxx/Haben 15900 (Skonto); Bankabgang über 13600 = Zahlbetrag.
   Ergebnis identisch zur Kap.-8-Kontrolle. Der OP lautet unverändert
   über Brutto (kein „-Soll"/keine Minusbuchung — GoBD).
5. Duplikat-Verdachte (`status='duplikat'`) erscheinen in der
   Stufe-1-Inbox zur Prüfung; Erfassung in einem Schritt inkl.
   Gutschrift-Kennzeichen, Zahlweg (Überweisung/Lastschrift) und
   Split-Positionen; PDF-Vorschau parallel im Formular (auch für
   Ordner-Importe via `rechnung.pfad`).

### Phase D — durchgeführt (Freigabe Patrik, 14.07.2026)

- `gebucht` → `freigegeben` migriert (Migration 0020); `auto_freigabe`
  existierte nie; v1.0-Rest `in_freigabe` entfernt (Migration 0018).
  Finaler Lifecycle: `in_buchhaltung → zur_freigabe → freigegeben →
  teilbezahlt/bezahlt`; quer `abgelehnt`/`storniert`.
- Tote Auto-Buchungs-Zweige entfernt: `_route_limit_workflow`,
  Auto-`op_freigeben` in `verarbeitung.py` und in `erkennung-ausfuehren`.
- Erhalten (wie gefordert): Erkennungs-Pipeline, `RechnungsMatchRegel` +
  Lernlogik, `RechnungsErkennungsLog`, `RechnungsBearbeitungsLock`,
  Frontoffice-Strukturen, Routing-Helfer, `darf_betreuer_direkt_freigeben`.

---

## 13. Dokumentmetadaten

| Feld | Wert |
|---|---|
| Auftraggeber | Demme Immobilien Verwaltung GmbH, Coventrystraße 32, 65934 Frankfurt am Main |
| Dokument-Typ | Claude Code Implementierungsprompt |
| Modul | Umbau Rechnungseingang — zweistufig |
| Bezug | Ausgangsspec v1.1 Kap. 7; Rechnungserkennung v1.2 (**erhalten**); OP-Buchung v1.1; Hausgeld-Nebenbuch v1.1 |
| Löst ab | v1.0 (vollständig) |
| KI-Modell | claude-sonnet-4-6 |
| Version | 1.1 (inkl. Implementierungs-Änderungsprotokoll Kap. 12a) |
| Stand | 14. Juli 2026 |
| Status | Umgesetzt — Phasen A–D abgeschlossen, Smoke-Test bestanden; Entscheidungen siehe Kap. 12a |

*Demme Immobilien Verwaltung GmbH | Vertraulich*
