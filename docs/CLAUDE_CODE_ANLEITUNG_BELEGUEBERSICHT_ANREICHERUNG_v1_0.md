# CLAUDE CODE – ANLEITUNG: Belegübersicht-Anreicherung (Rechnungsdaten in der Dokumente-Ansicht)

**Version:** 1.0
**Modul:** `apps.dokumente` (API/Serializer), Frontend Dokumente-/Belege-Übersicht
**Bezug:** Aufbauend auf "Beleg-Dokument-Kopplung (DMS-Basis) v1.1" (fertig, live) und der 3-stufigen Rechnungserkennung (v1.3)
**Vorbedingung geprüft:** `IMMOCORE_PROJEKTSTAND_AKTUELL.md` (Stand 2026-08-19) gelesen. `dokumente.Dokument` und `rechnungen.Rechnung` existieren wie unten beschrieben, keine Deltas zu dieser Spec.

---

## 0. Orchestrierung (Rollenverteilung für die Umsetzung)

Diese Spec wird von **Opus** orchestriert. Opus übernimmt: Aufgabenzerlegung in Arbeitspakete, Vergabe an günstigere Modelle, Review/Integration der Teilergebnisse, finale Konsistenzprüfung zwischen Backend-Vertrag und Frontend-Erwartung. Opus schreibt selbst möglichst wenig Code – die Umsetzung liegt bei den delegierten Agenten.

Die Aufgabe ist bewusst klein geschnitten (keine Schemaänderung, kein Backfill) und eignet sich daher gut für parallele Bearbeitung durch mehrere Agenten, sobald der API-Vertrag (Abschnitt 3) feststeht:

| Arbeitspaket | Agent/Modell | Abhängigkeit | Arbeitet parallel zu |
|---|---|---|---|
| A. Serializer-Erweiterung + Queryset-Optimierung (`apps/dokumente`) | Sonnet-Agent 1 (Backend) | Keine | B, sobald Vertrag aus Abschnitt 3 fixiert ist |
| B. Frontend-Tabellenspalten + Hinweis-Icon-Komponente | Sonnet-Agent 2 (Frontend) | Feldnamen aus Abschnitt 3 (Vertrag, nicht Code) | A |
| C. Backend-Tests (Serializer, Fallback-Logik, Sortierung) | Sonnet-Agent 3 (Test) | A muss fertig sein | – |
| D. Frontend-Test (Hinweis-Icon-Zustände) | Haiku-Agent (einfache Komponententests, klar spezifiziert) | B muss fertig sein | C |
| E. Review & Integration | Opus | A–D fertig | – |

Empfehlung: Opus legt den API-Vertrag (Abschnitt 3) als erstes fest und schreibt ihn fest (z. B. als kurzes Interface-Dokument oder Kommentar im PR), bevor A und B parallel gestartet werden — das vermeidet Rückfragen zwischen den Agenten. Phase-Gates siehe Abschnitt 8.

---

## 1. Problem

In der Dokumente-Übersicht (DMS) erscheinen Belege (Rechnungen, verknüpft über `Rechnung.beleg_dokument`) ausschließlich mit ihrem technischen Original-Dateinamen (`Dokument.dateiname`, z. B. aus Scan/E-Mail-Anhang). Es ist ohne Öffnen des Dokuments nicht erkennbar, um welchen Kreditor, welchen Betrag oder welche Rechnung es sich handelt – obwohl diese Daten über die 3-stufige Rechnungserkennung bereits im System vorhanden sind (`Rechnung.rechnungsdatum`, `Rechnung.kreditor`/`lieferant_name`, `Rechnung.betrag_brutto`, `Rechnung.leistungsbeschreibung`).

## 2. Ziel

Die Dokumente-Übersicht zeigt für Belege zusätzlich zum Dateinamen: Rechnungsdatum, Eingangsdatum (Systemerfassung), Kreditor-Name (mit Hinweis, falls nicht sicher zugeordnet), Bruttobetrag und einen Kurztext aus der Leistungsbeschreibung. Für Dokumente ohne Rechnungsbezug (Verträge, Beschlüsse, Korrespondenz, Sonstiges) ändert sich nichts – das ist explizit **nicht** Teil dieser Spec (siehe Abschnitt 9, Ausblick).

## 3. Scope-Entscheidung: kein neues Datenbankfeld

Alle benötigten Werte liegen bereits vollständig auf der verknüpften `Rechnung`. `Dokument` hat über das `OneToOneField Rechnung.beleg_dokument` (related_name `rechnung`) direkten Zugriff darauf. Es wird **kein** neues Feld auf `Dokument` angelegt, **keine** Migration, **kein** Backfill-Command – die Anreicherung ist ein reiner Read-Join und wirkt sofort auch für alle Bestandsbelege.

## 4. API-Vertrag (`apps.dokumente`, `DokumentViewSet`/Serializer)

Neue, read-only Felder auf dem `Dokument`-Serializer. Sie werden nur befüllt, wenn `dokument_typ == 'beleg'` **und** eine verknüpfte `Rechnung` existiert (`hasattr(instance, 'rechnung')` bzw. try/except auf die Reverse-OneToOne, da Django bei fehlender Relation `RelatedObjectDoesNotExist` wirft) – sonst `null`.

| Feld | Quelle | Typ | Bemerkung |
|---|---|---|---|
| `rechnungsdatum` | `rechnung.rechnungsdatum` | Date \| null | Wie erkannt, kann fehlen (schlechte OCR) |
| `eingangsdatum` | `rechnung.erstellt_am` | DateTime | Zeitpunkt der Systemerfassung, immer vorhanden |
| `kreditor_name` | `rechnung.kreditor.name` falls gesetzt, sonst `rechnung.lieferant_name` | str | Anzeigename für die Liste |
| `kreditor_unbestaetigt` | `rechnung.kreditor is None` | bool | Steuert das Hinweis-Icon im Frontend |
| `betrag_brutto` | `rechnung.betrag_brutto` | Decimal \| null | Wie erkannt |
| `kurztext` | `rechnung.leistungsbeschreibung`, serverseitig auf 120 Zeichen gekürzt (`…` bei Kürzung) | str | Volltext zusätzlich als `kurztext_volltext` für Tooltip, falls gekürzt wurde |

Implementierungshinweis: `SerializerMethodField`e verwenden, keine denormalisierten Felder. Im Queryset des `DokumentViewSet` (`get_queryset`) `select_related('rechnung', 'rechnung__kreditor')` ergänzen, um N+1-Queries in der Liste zu vermeiden – das ist bei potenziell hunderten Belegen pro Seite relevant.

Sortierbarkeit: `ordering_fields` um `rechnung__rechnungsdatum` und `rechnung__betrag_brutto` erweitern, damit die Übersicht nach Rechnungsdatum und Betrag sortierbar ist (DRF erlaubt Sortierung über Relationen mit `__`).

## 5. Kreditor-Fallback-Logik (Detailspezifikation)

```python
def get_kreditor_name(self, obj):
    rechnung = getattr(obj, "rechnung", None)
    if rechnung is None:
        return None
    if rechnung.kreditor_id:
        return rechnung.kreditor.name
    return rechnung.lieferant_name or None

def get_kreditor_unbestaetigt(self, obj):
    rechnung = getattr(obj, "rechnung", None)
    if rechnung is None:
        return None
    return rechnung.kreditor_id is None
```

`kreditor_unbestaetigt=True` bedeutet: Der angezeigte Name stammt aus dem KI-Rohtext (`lieferant_name`), es existiert (noch) kein gematchter `Kreditor`-Stammdatensatz. Das ist bei Stufe-1/2-Erkennung ohne Matchtreffer der Regelfall.

## 6. Frontend (Dokumente-/Belege-Übersicht)

Neue Spalten in der Tabelle (Reihenfolge wie in Abschnitt 4, Dateiname bleibt zusätzlich als sekundäre Spalte bzw. Download-Link erhalten, keine Entfernung):

- **Rechnungsdatum** – Datumsformat `TT.MM.JJJJ`; leer/„–" wenn `null`.
- **Eingangsdatum** – Datumsformat `TT.MM.JJJJ`, immer vorhanden.
- **Kreditor** – Klartext. Wenn `kreditor_unbestaetigt === true`: Hinweis-Icon (z. B. ⚠ oder Outline-Warndreieck) direkt neben dem Namen, mit Tooltip „Kreditor nicht eindeutig zugeordnet – Name aus Rechnungstext, kein Stammdatensatz". Kein Blocker, nur visueller Hinweis.
- **Bruttobetrag** – deutsches Zahlenformat, `1.234,56 €`, rechtsbündig.
- **Kurztext** – gekürzter Text; bei Kürzung Tooltip mit `kurztext_volltext`.

Für Dokumente ohne Rechnungsbezug (alle o. g. Felder `null`): Zeile zeigt wie bisher nur Dateiname/Kategorie/Objekt – keine leeren Spalten-Platzhalter, die verwirren.

## 7. Tests

**Backend (Arbeitspaket C):**
- Serializer liefert alle Felder korrekt bei vollständig erkannter Rechnung.
- `kreditor_name` fällt korrekt auf `lieferant_name` zurück, wenn `kreditor` nicht gesetzt ist; `kreditor_unbestaetigt=True` in diesem Fall.
- Alle Felder `null`, wenn `Dokument.dokument_typ != 'beleg'` oder keine verknüpfte Rechnung existiert (kein `RelatedObjectDoesNotExist`-Fehler).
- `kurztext` wird korrekt auf 120 Zeichen gekürzt, `kurztext_volltext` nur gesetzt, wenn tatsächlich gekürzt wurde.
- Sortierung nach `rechnung__rechnungsdatum` und `rechnung__betrag_brutto` liefert korrekte Reihenfolge inkl. NULL-Handling.
- Queryset-Test: Anzahl der DB-Queries bei einer Liste mit N Belegen bleibt konstant (kein N+1) – z. B. mit `django.test.utils.CaptureQueriesContext`.

**Frontend (Arbeitspaket D):**
- Hinweis-Icon erscheint nur bei `kreditor_unbestaetigt=true`, mit korrektem Tooltip-Text.
- Spalten rendern korrekt bei vollständigen Daten, bei teilweise fehlenden Daten (`rechnungsdatum=null`) und bei Dokumenten ohne Rechnungsbezug (keine leeren Spalten-Artefakte).
- Sortierung über die Spalten-Header funktioniert und spiegelt sich im API-Request (`ordering=`-Parameter) wider.

## 8. Phase-Gate

1. Opus fixiert den API-Vertrag aus Abschnitt 4 verbindlich.
2. Arbeitspaket A (Backend) + C (Backend-Tests) werden umgesetzt und müssen grün sein, **bevor** B (Frontend) integriert wird – B kann parallel entwickelt werden, aber der Merge/die Integration gegen die echte API erfolgt erst nach grünem Backend-Test-Lauf.
3. Nach B: Arbeitspaket D (Frontend-Tests).
4. Opus führt abschließendes Review durch: Feldnamen-Konsistenz Backend↔Frontend, Tooltip-Texte, Sortierverhalten, Performance-Check (Queries) bei realistischer Beleganzahl.

## 9. Konventionen

- Lean & readable code – eine Funktion, eine Aufgabe; keine Django-Signals für diese Anreicherung, da reiner Read-Pfad.
- `Decimal` für Beträge, kein `float`.
- Deutsche Datums-/Zahlenformate im Frontend.
- Keine Änderung an `Dokument.dateiname` oder der gespeicherten Originaldatei – GoBD-Nachvollziehbarkeit bleibt unangetastet, diese Spec ist rein additiv auf Anzeigeebene.

## 10. Explizit nicht Teil dieser Spec (Ausblick)

- Ein generisches Anzeigenamen-/Titel-Feld für Dokumente **ohne** Rechnungsbezug (Verträge, Beschlüsse, Korrespondenz, Sonstiges) – eigenes Thema, ggf. mit KI-gestütztem Titel-Vorschlag analog der Rechnungserkennung.
- Die größere „virtuelle Aktenstruktur"/Navigationsschicht über der Dokumente-Ablage (Objekt → Themengruppe), die in der vorangegangenen fachlichen Diskussion besprochen wurde – dafür ist eine eigene Spec vorgesehen, sobald geklärt ist, wie die heutigen Akten inhaltlich gegliedert sind.
- Der „DMS-Eingangskorb" als Ersatz für den stillgelegten `dokumente.ordner_scan`-Task (im Projektstand als offen vermerkt).

---

*Ende der Spezifikation v1.0*
