# API-Vertrag: Belegübersicht-Anreicherung v1.0 (verbindlich)

**Bezug:** `docs/CLAUDE_CODE_ANLEITUNG_BELEGUEBERSICHT_ANREICHERUNG_v1_0.md`, Abschnitt 4
**Status:** Von Opus vor Umsetzungsstart fixiert (Phase-Gate 1). Änderungen nur über neue Vertragsversion.

## Endpunkt

`GET /api/dokumente/` (`apps.dokumente.views.DokumentViewSet`, `DokumentSerializer`)
Unverändert **ohne Pagination** — Antwort ist ein flaches JSON-Array.

## Neue read-only Felder

Alle sechs Felder sind `null`, wenn **nicht** (`dokument_typ == 'beleg'` **und** verknüpfte
`Rechnung` über `Rechnung.beleg_dokument` vorhanden). Es gibt keine Teilbefüllung:
entweder alle sechs tragen Werte, oder alle sechs sind `null`.

| JSON-Feld | Typ | Quelle |
|---|---|---|
| `rechnungsdatum` | `string \| null` — ISO `YYYY-MM-DD` | `rechnung.rechnungsdatum` (kann auch bei Beleg `null` sein) |
| `eingangsdatum` | `string \| null` — ISO-8601 DateTime | `rechnung.erstellt_am` (bei Beleg immer gesetzt) |
| `kreditor_name` | `string \| null` | `rechnung.kreditor.name`, sonst `rechnung.lieferant_name`, sonst `null` |
| `kreditor_unbestaetigt` | `boolean \| null` | `rechnung.kreditor_id is None` |
| `betrag_brutto` | `string \| null` — Decimal als String (DRF) | `rechnung.betrag_brutto` |
| `kurztext` | `string \| null` | `rechnung.leistungsbeschreibung`, auf 120 Zeichen gekürzt |
| `kurztext_volltext` | `string \| null` | Volltext, **nur** gesetzt wenn tatsächlich gekürzt wurde — sonst `null` |

### Kürzungsregel `kurztext`

- Leerer/fehlender Leistungstext → `kurztext = null`, `kurztext_volltext = null`.
- Länge <= 120 → `kurztext` = Volltext, `kurztext_volltext = null`.
- Länge > 120 → `kurztext` = erste 119 Zeichen + `…` (Gesamtlänge exakt 120),
  `kurztext_volltext` = ungekürzter Text.

## Sortierung

`ordering_fields` wird ergänzt um `rechnung__rechnungsdatum` und `rechnung__betrag_brutto`
(zusätzlich zu den bestehenden `hochgeladen_am`, `dateiname`, `kategorie`).
Aufruf: `GET /api/dokumente/?ordering=rechnung__betrag_brutto` bzw. `-rechnung__betrag_brutto`.
NULL-Handling: Postgres-Default (`ASC` → NULLs zuletzt, `DESC` → NULLs zuerst).

## Performance

`DokumentViewSet.get_queryset()` ergänzt `select_related('rechnung', 'rechnung__kreditor')`.
Query-Anzahl der Liste muss unabhängig von der Beleganzahl konstant bleiben.

## Nicht Teil des Vertrags

Keine Schemaänderung, keine Migration, kein Backfill. `Dokument.dateiname` bleibt unberührt.
`ObjektDokumentSerializer` (`GET /api/objekte/{id}/dokumente/`) wird **nicht** angefasst.

---

# Nachtrag v1.1 — Löschsperre für geprüfte Belege (verbindlich)

**Anlass:** Belege zu Rechnungen, die die Prüfung passiert haben, dürfen nicht gelöscht werden.
**Entscheidung des Auftraggebers:** Schwelle ist `zur_freigabe` (Stufe-1-Prüfung bestanden).
Der Mechanismus ist eine **Statusprüfung zum Löschzeitpunkt** — das bestehende
`Dokument.revisionssicher` (GoBD, unumkehrbar) wird NICHT früher gesetzt und behält seine
Bedeutung. Eine später abgelehnte oder stornierte Rechnung ist damit wieder löschbar.

## Geprüfte Status (Löschsperre)

`Rechnung.STATUS_GEPRUEFT = {zur_freigabe, freigegeben, teilbezahlt, bezahlt, wkz_beleg}`

Nicht gesperrt: `erfasst`, `erkannt`, `pruefung_match`, `nicht_erkannt`, `in_pruefung`,
`prueffall`, `in_buchhaltung`, `abgelehnt`, `storniert`, `fehler`.

## Ist-Zustand, der mit abgedeckt wird

- `Rechnung.beleg_dokument` ist `on_delete=PROTECT`. Dadurch ist **jedes** Dokument mit
  verknüpfter Rechnung ohnehin nicht löschbar — bisher aber als unbehandelter
  `ProtectedError` und damit HTTP 500 statt einer klaren Meldung.
- `RechnungViewSet` hatte **keinen** `destroy`-Override: `DELETE /api/rechnungen/{id}/`
  löschte jede Rechnung. Geschützt waren faktisch nur Rechnungen mit `KreditorOP`
  (entsteht erst bei Freigabe) — `zur_freigabe` und `wkz_beleg` waren löschbar.

## Verhalten der Endpunkte

| Endpunkt | Bedingung | Antwort |
|---|---|---|
| `DELETE /api/dokumente/{id}/` | `revisionssicher` | 400, `{"error": …}` (unverändert) |
| `DELETE /api/dokumente/{id}/` | verknüpfte Rechnung ist geprüft | 400 mit Statusangabe |
| `DELETE /api/dokumente/{id}/` | verknüpfte Rechnung, ungeprüft | 400 (Hinweis: zuerst Rechnung entfernen) |
| `DELETE /api/rechnungen/{id}/` | Status in `STATUS_GEPRUEFT` | 400 mit Statusangabe |
| `DELETE /api/rechnungen/{id}/` | `ProtectedError` (z. B. KreditorOP) | 400 statt 500 |

Kein Endpunkt darf für diese Fälle noch 500 liefern.

## Neue read-only Felder auf dem Dokument-Serializer

Anders als die sieben Anreicherungsfelder sind diese **immer** befüllt, auch für Dokumente
ohne Rechnungsbezug — die UI braucht sie für jede Zeile.

| Feld | Typ | Bedeutung |
|---|---|---|
| `loeschbar` | `boolean` | `false`, wenn ein `DELETE` abgelehnt würde |
| `loeschsperre_grund` | `string \| null` | Klartextgrund auf Deutsch, wenn `loeschbar=false`; sonst `null` |

Regelreihenfolge für `loeschsperre_grund` (erste zutreffende gewinnt):

1. `revisionssicher` → „Revisionssicherer Beleg (GoBD) — Löschen nicht zulässig."
2. Rechnung geprüft → „Rechnung ist geprüft (Status: `<label>`) — Beleg muss erhalten bleiben."
3. Rechnung vorhanden, ungeprüft → „Beleg ist mit einer Rechnung verknüpft — zuerst die Rechnung entfernen."

## Frontend

Der Löschen-Button ist bei `loeschbar === false` deaktiviert (nicht versteckt) und trägt
`loeschsperre_grund` als Tooltip. Der Öffnen-Button bleibt immer aktiv.

## Nachtrag zu v1.1 — Sperre auch außerhalb der ViewSets

Bei der Umsetzung fiel auf, dass der Django-Admin unter `/admin/` gemountet und
`Rechnung` dort registriert ist. Eine Rechnung im Status `zur_freigabe` (noch ohne
`KreditorOP`) war darüber löschbar — an beiden ViewSet-Wächtern vorbei. Ergänzt wurde
deshalb:

- `Rechnung.delete()` wirft bei `ist_geprueft` eine `ValidationError` (analog zur
  bestehenden GoBD-Sperre in `Dokument.delete()`). Deckt jeden Pfad ab, der
  `instance.delete()` aufruft, inklusive Admin-Einzellöschung.
- `RechnungAdmin.has_delete_permission()` verweigert geprüfte Rechnungen.
- `RechnungAdmin.get_actions()` entfernt `delete_selected` — diese Massenaktion löscht
  über das QuerySet und würde `Rechnung.delete()` überspringen.

Für `Dokument` ist keine Model-Ergänzung nötig: `Rechnung.beleg_dokument` ist
`on_delete=PROTECT`, ein Dokument mit verknüpfter Rechnung ist damit auf DB-Ebene
ohnehin nicht löschbar.
