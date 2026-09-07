# CLAUDE CODE — IMMOCORE / immospace.cloud
## Layout-Update: Button-Navigation & Konto-Reiter (Änderungsauftrag)

**Version:** 1.0
**Stand:** August 2026
**Status:** 🟡 Bereit zur Umsetzung — **Betrifft die bereits live geschaltete Portal-Anwendung**
**Bezug:** abgenommenes Mockup (`immocore_portal_mockup.html`), `CLAUDE_CODE_ANLEITUNG_WEG_PORTAL_MINI_v1_0.md` (Spec 1a), `CLAUDE_CODE_ANLEITUNG_WEG_PORTAL_KONTO_v1_0.md` (Spec 1b, Kap. 4)

---

## 0. Orchestrierung

**Orchestrator: Opus.**
Da es sich um eine Änderung an einer **bereits produktiv laufenden** Anwendung handelt, liegt der Schwerpunkt der Orchestrierung auf sauberem Vorgehen (Staging vor Produktion), nicht auf komplexer fachlicher Entscheidung.

**Sub-Agenten:**

| Agent | Modell | Aufgabe |
|---|---|---|
| `immo-explorer` | Haiku | Bestandsaufnahme der **realen** aktuellen Frontend-Komponentenstruktur (welche Komponente rendert aktuell die WEG-/Einheiten-Auswahl, wie ist der State dafür aufgebaut) — bevor irgendetwas geändert wird |
| `immo-builder` | Sonnet | Umsetzung des Layout-Updates auf Basis des Mockups, unter Wiederverwendung der bestehenden Datenanbindung |
| `immo-architect` | Opus | Eskalation nur, falls die reale Komponentenstruktur so stark vom Mockup-Aufbau abweicht, dass ein einfacher 1:1-Umbau nicht möglich ist |

Keine Parallelisierung nötig — reine sequenzielle Frontend-Aufgabe an einer bestehenden Codebasis.

---

## 1. Zweck und Abgrenzung

### 1.1 Ziel

Das aktuelle Layout der WEG-/Einheiten-Auswahl im Portal wird durch das abgenommene Button-Layout ersetzt:

```
[WEG-Buttons: eine Reihe, aktive WEG hervorgehoben]
      ↓ Klick auf WEG
[Einheiten-Buttons: erscheinen darunter, auch bei nur 1 Einheit sichtbar]
      ↓ Klick auf Einheit
[Reiter: Konto | Dokumente | Vorgänge — Konto ist Standard beim Öffnen]
```

Visuelle Referenz ist ausschließlich `immocore_portal_mockup.html` — Farben, Abstände, Button-Stil, Verhalten beim Wechsel (Rücksprung auf „Konto"-Reiter) 1:1 daraus übernehmen.

### 1.2 Explizit NICHT Teil dieses Auftrags

- Keine Änderung an Backend-Endpoints, sofern sie bereits funktionieren — nur die Darstellung wird umgebaut
- Keine Änderung an der Konto-Saldo-Berechnung (Spec 1b) — falls diese noch nicht live ist, bleibt der Konto-Reiter mit dem aktuellen Datenstand/Platzhalter bestehen, nur optisch im neuen Layout
- Kein Eingriff in Auth/Magic-Link-Logik

---

## 2. Vorgehen (Live-System — kein Hot-Patch)

1. **Phase 0 (immo-explorer):** reale Struktur der bestehenden Frontend-Komponenten dokumentieren (Komponentennamen, State-Management, wie WEG/Einheit aktuell ausgewählt werden)
2. **Umsetzung auf einem Feature-Branch**, nicht direkt auf dem Produktions-Branch
3. **Test auf Staging/lokal** (analog zur bereits eingerichteten lokalen Testumgebung) — Login, WEG-Wechsel, Einheiten-Wechsel, Reiter-Wechsel durchklicken
4. **Deploy erst nach visueller Bestätigung**, dass das Ergebnis dem Mockup entspricht — kein automatisiertes Ausrollen ohne diesen Schritt

---

## 3. Akzeptanzkriterien

- [ ] WEG-Auswahl erscheint als Button-Reihe, aktive WEG farblich hervorgehoben — entspricht optisch dem Mockup
- [ ] Einheiten-Buttons erscheinen nach WEG-Auswahl, auch bei nur einer Einheit sichtbar
- [ ] Reiter „Konto", „Dokumente", „Vorgänge" erscheinen nach Einheiten-Auswahl, „Konto" ist beim Öffnen aktiv
- [ ] Wechsel der WEG oder Einheit springt automatisch zurück auf den „Konto"-Reiter
- [ ] Bestehende Funktionalität (Login, Datenanzeige) funktioniert nach dem Umbau unverändert — keine Regression
- [ ] Änderung wurde auf Staging/lokal geprüft, bevor sie live geschaltet wurde
