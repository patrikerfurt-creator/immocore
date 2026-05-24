# IMMOCORE — Patch v1.1: Generischer Korrektur-Service

**Patch-Version:** Ergänzt `IMMOCORE_ClaudeCode_RueckwirkenderEigentuemerwechsel_v1_0.md`
**Status:** 🟢 Implementierungsreif
**Anlass:** Eine zweite Spec (`Wirtschaftsplan_Beschluss_v1_0`) benötigt
denselben Mechanismus „Original neutralisieren + Neuanlage erzeugen".
Statt zwei parallele Implementierungen wird der Kern als generischer Service
extrahiert.

---

## 1. Was sich ändert

Der Korrektur-Mechanismus aus Kap. 6.2 / 6.3 / 6.4 der Wechsel-Spec wird
in einen **eigenen Service** `korrektur_sollstellung_service` ausgelagert.
Die Wechsel-Spec und die kommende Wirtschaftsplan-Spec rufen diesen
Service jeweils als Bibliothek auf.

**Keine fachliche Änderung** an der Wechsel-Spec — nur Aufbau-/
Code-Organisation.

## 2. Neuer Service `korrektur_sollstellung_service`

```
apps/buchhaltung/services/
└── korrektur_sollstellung_service.py    # NEU (aus Wechsel-Spec extrahiert)
```

### 2.1 Public API

```python
def korrigiere_sollstellung(
    original: HausgeldSollstellung,
    neue_eigentumsverhaeltnis: EigentumsVerhaeltnis,
    neue_splits: list[tuple[Buchungsart, Decimal]] | None,
    korrektur_grund: str,         # Enum: 'eigentuemerwechsel' / 'wirtschaftsplan_aenderung'
    korrektur_vorgang_id: UUID,   # FK auf den auslösenden Vorgang
    user: User,
) -> tuple[HausgeldSollstellung, HausgeldSollstellung]:
    """
    Atomare Operation: erzeugt für eine Original-Sollstellung
      (a) eine Korrektur-Sollstellung mit negierten Splits
          auf die EV des Originals
      (b) eine Neuanlage-Sollstellung auf neue_eigentumsverhaeltnis

    Splits-Verhalten:
      - Wenn neue_splits=None: Splits werden 1:1 aus Original geklont
        (Use-Case: Eigentümerwechsel, gleicher Hausgeldsatz, andere Person)
      - Wenn neue_splits=[(ba, betrag), ...]: Splits werden aus dieser
        Liste gebildet (Use-Case: Wirtschaftsplan, andere Beträge)

    Verkettung:
      - original.neutralisiert_durch_opos = korrektur
      - korrektur.neutralisiert_opos_nr = original
      - korrektur.korrektur_grund = korrektur_grund
      - korrektur.korrektur_vorgang_id = vorgang_id
      - neuanlage.korrektur_grund = korrektur_grund
      - neuanlage.korrektur_vorgang_id = vorgang_id

    Returns:
      (korrektur_sollstellung, neuanlage_sollstellung)

    Idempotenz:
      Wenn original.neutralisiert_durch_opos != NULL bereits gesetzt:
      ValidationError. Originale dürfen nur einmal neutralisiert werden.
    """
```

### 2.2 Generische Datenmodell-Anpassung

Die Felder `wechsel_vorgang` und `neutralisiert_durch_opos` /
`neutralisiert_opos_nr` aus Kap. 4.1 der Wechsel-Spec **bleiben bestehen**,
aber werden umbenannt/erweitert:

| Feld | Wechsel-Spec v1.0 | Patch v1.1 |
|---|---|---|
| `wechsel_vorgang` | FK → EigentuemerwechselVorgang | **Entfernt** (ersetzt durch zwei generische Felder) |
| `korrektur_grund` | — | **NEU**: Enum `('eigentuemerwechsel', 'wirtschaftsplan_aenderung')` |
| `korrektur_vorgang_id` | — | **NEU**: UUID, nullable, FK abhängig von `korrektur_grund` |
| `neutralisiert_durch_opos` | FK auf HausgeldSollstellung | unverändert |
| `neutralisiert_opos_nr` | FK auf HausgeldSollstellung | unverändert |

**Warum kein generischer FK?** Django hat GenericForeignKey, aber das
macht Joins und Mahn-Filter umständlich. Stattdessen: zwei Felder
(`korrektur_grund` + `korrektur_vorgang_id`) und je Vorgangs-Typ ein
Helper, der den verlinkten Vorgang nachlädt:

```python
def get_korrektur_vorgang(sollstellung):
    if sollstellung.korrektur_grund == 'eigentuemerwechsel':
        return EigentuemerwechselVorgang.objects.get(pk=sollstellung.korrektur_vorgang_id)
    elif sollstellung.korrektur_grund == 'wirtschaftsplan_aenderung':
        return WirtschaftsplanBeschluss.objects.get(pk=sollstellung.korrektur_vorgang_id)
```

## 3. Konsequenz für die Wechsel-Spec

Die Wechsel-Spec Kap. 6.2 (`vorschau_committen`) wird inhaltlich
unverändert beibehalten — sie ruft jetzt nur den neuen Service auf:

```python
# Vorher (Wechsel-Spec v1.0):
korrektur = HausgeldSollstellung.objects.create(...)
_negiere_splits(original, korrektur)
neuanlage = HausgeldSollstellung.objects.create(...)
_klone_splits(original, neuanlage)

# Nachher (Patch v1.1):
korrektur, neuanlage = korrektur_sollstellung_service.korrigiere_sollstellung(
    original=original,
    neue_eigentumsverhaeltnis=vorgang.neueigentuemer_ev,
    neue_splits=None,                           # → 1:1 klonen
    korrektur_grund='eigentuemerwechsel',
    korrektur_vorgang_id=vorgang.id,
    user=freigabe_user,
)
```

Die Helper `_negiere_splits` und `_klone_splits` aus Wechsel-Spec Kap. 6.3/6.4
wandern in den generischen Service als private Helfer.

## 4. Konsequenz für `WechselKorrekturPaar`

Diese Tabelle bleibt **wechsel-spezifisch** und gehört zur Wechsel-Spec.
Sie ist kein generisches Korrektur-Paar, sondern ein Audit-Container für
**Wechsel-Vorgänge**. Die Wirtschaftsplan-Spec bringt ihre eigene
äquivalente Tabelle `WirtschaftsplanKorrekturPaar` mit (gleiche Struktur,
anderer Kontext).

Begründung: Audit-Tabellen sollten ihren Auslösungskontext klar zeigen.
Ein generisches `KorrekturPaar` mit `vorgang_typ`-Diskriminator wäre
abstraktes Over-Engineering ohne praktischen Mehrwert.

## 5. Anpassung Mahn-Filter

Der Filter aus Wechsel-Spec Kap. 9 bleibt korrekt:

```python
.filter(neutralisiert_durch_opos__isnull=True)
.exclude(sollstellungs_typ='korrektur_eigentuemerwechsel')
```

Aber: der Wert `sollstellungs_typ` wird in Patch v1.1 generischer.
Statt `korrektur_eigentuemerwechsel` wird der Enum-Wert
**`korrektur`** verwendet — der konkrete Grund steht im neuen Feld
`korrektur_grund`.

Mahn-Filter neu:
```python
mahnbare = HausgeldSollstellung.objects.filter(
    soll_betrag__gt=models.F('ist_betrag'),
    neutralisiert_durch_opos__isnull=True,
).exclude(
    sollstellungs_typ='korrektur',
)
```

## 6. Migrations-Reihenfolge

Da IMMOCORE Greenfield ist, in dieser Reihenfolge:

1. Generischer Korrektur-Service `korrektur_sollstellung_service`
2. Wechsel-Spec implementiert Wechsel-Vorgang → ruft Service
3. Wirtschaftsplan-Spec implementiert WP-Vorgang → ruft Service

## 7. Aufgaben für Claude Code

> **Hinweis:** Dieser Patch wird vor der Wirtschaftsplan-Spec implementiert
> und ersetzt den ursprünglichen Plan aus Wechsel-Spec Kap. 13 Phase A2/A4.
> Wenn der ursprüngliche Plan bereits umgesetzt war (Felder
> `wechsel_vorgang`, `sollstellungs_typ='korrektur_eigentuemerwechsel'`),
> ist eine kleine Daten-Migration nötig (siehe unten).

### Phase A — Refaktoring

**A1: Migration generisches Feldpaar**
- `HausgeldSollstellung.wechsel_vorgang` (falls schon existiert) entfernen
- `HausgeldSollstellung.korrektur_grund` (CharField, choices, nullable) hinzufügen
- `HausgeldSollstellung.korrektur_vorgang_id` (UUIDField, nullable) hinzufügen
- Enum `sollstellungs_typ`: `korrektur_eigentuemerwechsel` → `korrektur`
- Daten-Migration: bestehende Korrektur-Sollstellungen umstellen
  (sollte bei Greenfield = 0 Zeilen sein)

**A2: Service `korrektur_sollstellung_service.py`**
- Funktion `korrigiere_sollstellung` aus Kap. 2.1
- Helfer `_negiere_splits`, `_klone_splits` als private Funktionen
- Idempotenz-Check
- Unit-Tests

**A3: Anpassung Wechsel-Service**
- `vorschau_committen` ruft `korrigiere_sollstellung` statt Inline-Logik
- Bestehende Tests müssen weiterhin grün sein (gleiche Outputs)

**A4: Mahn-Filter aktualisieren** (Kap. 5)

🛑 **HARTER STOPP nach Phase A.**

Erst danach kann die Wirtschaftsplan-Spec implementiert werden.

---

**Ende des Patches.**
