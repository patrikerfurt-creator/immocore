# Immocore-Anpassungen: Abschluss-Endpunkt

**Adressat:** Immocore-Backend (Django/Postgres)
**Betrifft:** `POST /api/v1/versammlungen/{ev_id}/abschluss/`
**Grundlage:** `API_VERTRAG_VERSAMMLUNGSTOOL_v1_4.md`, Abschnitt 4.6
**Stand:** 2026-10-09

Dieses Dokument fasst die zwei Änderungen zusammen, die auf der **Immocore-
Seite** umzusetzen sind. Das externe Abstimmtool übernimmt die Abschluss-
Antwort unverändert; beide Punkte sind reine Immocore-Logik und können dort
nicht vom Tool aus beeinflusst werden.

---

## Änderung 1 — Abschluss blockiert nicht mehr bei TOPs ohne Ergebnis

### Problem

Der Abschluss schlägt mit HTTP 400 fehl, sobald ein abstimmungspflichtiger TOP
(`abstimmungsmodus != "kein_beschluss"`) kein `abstimmungsergebnis` hat. In der
Versammlung wird aber zu einzelnen TOPs bewusst **kein Beschluss** gefasst
(vertagt, zurückgezogen, reiner Bericht). Das Tool sendet dazu gar keine
Einzelstimmen, Immocore hat folglich kein Ergebnis — und die ganze Versammlung
lässt sich nicht abschließen/übertragen.

> Konkreter Auslöser: Objekt 10024, ein beschlusspflichtiger TOP ohne
> Abstimmung → Abschluss blockiert.

Ein lokales „ohne Abstimmung" aus dem Tool wird **nicht** an Immocore
übertragen. Das Fehlen eines Ergebnisses ist daher ein **gültiger Endzustand**,
kein Fehler.

### Soll-Verhalten

Ein abstimmungspflichtiger TOP ohne `abstimmungsergebnis`:
- **blockiert den Abschluss nicht** (kein HTTP 400 mehr deswegen),
- gilt als **„kein Beschluss gefasst"**,
- bekommt **keine** Beschlussnummer (fehlt in `beschluesse`),
- wird im **Ereignis-Log** der EV vermerkt (damit eine *versehentlich*
  vergessene Abstimmung nachvollziehbar bleibt).

Das einzige verbleibende 400 beim Abschluss ist das **Status-Gate**
(Status ≠ `ausgecheckt`).

### Umsetzung (Skizze)

```python
# ENTFÄLLT: 400, wenn ein abstimmungspflichtiger TOP kein Ergebnis hat
# fehlende = [t for t in tops
#             if t.abstimmungsmodus != "kein_beschluss" and not t.abstimmungsergebnis]
# if fehlende:
#     raise ValidationError(f"... fehlt noch ein Abstimmungsergebnis: {fehlende}")

# NEU: solche TOPs als "kein Beschluss gefasst" vermerken, nicht blockieren
ohne_ergebnis = [
    t for t in tops
    if t.abstimmungsmodus != "kein_beschluss" and not t.abstimmungsergebnis
]
for t in ohne_ergebnis:
    EreignisLog.objects.create(
        ev=ev,
        typ="abschluss_top_ohne_beschluss",
        text=f"TOP {t.nummer_anzeige}: beschlusspflichtig, aber ohne "
             f"Abstimmungsergebnis – beim Abschluss als "
             f"'kein Beschluss gefasst' gewertet.",
    )
```

> Optional: Das Immocore-Frontend kann den Abschluss mit einem
> Bestätigungsschritt versehen („X TOP(s) ohne Beschluss — trotzdem
> abschließen?"). Der API-Endpunkt selbst blockiert aber nicht.

---

## Änderung 2 — Beschlussnummern in Tagesordnungs-Reihenfolge vergeben

### Problem

Die objektweit fortlaufenden Beschlussnummern werden **nicht** in Tagesordnungs-
Reihenfolge vergeben. Beobachtet (Objekt der Wingertstraße-Sitzung):

| Tagesordnung | erwartet | tatsächlich |
|---|---:|---:|
| TOP 1   | 5  | 5  |
| TOP 2   | **6**  | **8** ❌ |
| TOP 3 (kein Beschluss) | – | – |
| TOP 3.1 | 7  | 6  |
| TOP 3.2 | 8  | 7  |
| TOP 3.3 | 9  | 9  |
| TOP 3.4 | 10 | 11 |
| TOP 4   | 11 | 10 |
| TOP 5   | 12 | 12 |

Die tatsächliche Vergabereihenfolge war 1 → 3.1 → 3.2 → 2 → 3.3 → 4 → 3.4 → 5.
Das ist weder die Tagesordnungs-Reihenfolge noch die Sende-Reihenfolge des
Tools (die war sauber 1, 2, 3.1, …). Das Muster — die Unterpunkte **3.1/3.2
schieben sich vor TOP 2** — deutet darauf hin, dass der Abschluss die TOPs in
**Datensatz-/Anlagereihenfolge (`id`/pk)** durchläuft; die Unterpunkte von
TOP 3 wurden offenbar vor TOP 2 angelegt.

### Soll-Verhalten

Die fortlaufenden Beschlussnummern werden strikt in **Tagesordnungs-
Reihenfolge** vergeben — hierarchisch inklusive Unterpunkte
(1, 2, 3, 3.1, 3.2, 3.3, 3.4, 4, 5, 6) — nicht nach `id`/Anlagezeit.

Wichtig: Nach dem **String** `nummer_anzeige` sortieren reicht nicht
(`"10"` käme vor `"2"`). Die Anzeige-Nummer muss **je Ebene numerisch**
interpretiert werden.

### Umsetzung (Skizze)

```python
def _agenda_sort_key(top):
    # "3.1" -> (3, 1); "2" -> (2, 0); "10" -> (10, 0)
    return tuple(int(teil) for teil in str(top.nummer_anzeige).split("."))

naechste_nummer = naechste_freie_beschluss_nummer(objekt)   # objektweit fortlaufend
for top in sorted(tops, key=_agenda_sort_key):
    if top.abstimmungsmodus == "kein_beschluss" or not top.abstimmungsergebnis:
        continue   # kein Beschluss -> keine Nummer (siehe Änderung 1)
    top.beschluss_nummer = naechste_nummer
    naechste_nummer += 1
    top.save(update_fields=["beschluss_nummer"])
```

So entspricht die Beschluss-Nummerierung der Reihenfolge im Protokoll.

---

## Prüfung nach dem Deploy

Mit korrektem Verhalten liefert `POST /abschluss/`:
1. **200** auch dann, wenn abstimmungspflichtige TOPs ohne Ergebnis vorhanden
   sind (nur das Status-Gate kann noch 400 liefern),
2. `beschluesse` ausschließlich für TOPs mit Ergebnis,
3. die Beschlussnummern in Tagesordnungs-Reihenfolge (im obigen Beispiel
   TOP 2 = 6, TOP 3.1 = 7, …).

Erst danach lässt sich Objekt 10024 abschließen und das Protokoll hochladen.

## Verweise

- `API_VERTRAG_VERSAMMLUNGSTOOL_v1_4.md`, Abschnitt 4.6 (vertragliche Fassung)
- Mock-Nachbildung im Tool: `tests/immocore_mock.py`
  (`POST /abschluss/`) — bildet Änderung 1 bereits ab.
