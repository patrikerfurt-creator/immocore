# IMMOCORE — Generischer Sollstellungs-Korrektur-Service

**Version:** v1.2 (eigenständige Spec; ersetzt den früheren Patch v1.1)
**Status:** 🟢 Implementierungsreif
**Ersetzt:** `IMMOCORE_ClaudeCode_Patch_KorrekturService_v1_1.md` vollständig
**Bezug:**
- Erweitert `CLAUDE_CODE_ANLEITUNG_HAUSGELD_NEBENBUCH_v1_1.md`
- Wird verwendet von `IMMOCORE_ClaudeCode_RueckwirkenderEigentuemerwechsel_v1_1.md`
- Wird verwendet von `IMMOCORE_ClaudeCode_Wirtschaftsplan_Beschluss_v1_2.md`

---

## Änderungsverzeichnis gegenüber Patch v1.1

| Bereich | Patch v1.1 (alt) | Spec v1.2 (neu) |
|---|---|---|
| Spec-Typ | Patch (verweist auf v1.0) | Eigenständige, vollständige Spec |
| Felder-Anlage | Beschrieben als „bleiben bestehen aus Wechsel-Spec" | **Hier vollständig spezifiziert und neu angelegt** |
| Wechsel-Service-Refaktoring (A3) | Eigene Phase | Entfernt — die Wechsel-Spec implementiert direkt auf den neuen Service |
| Mahn-Filter (A4) | „im Mahn-Modul implementieren" | Als Dokumentation in `docs/mahnwesen_pflicht_filter.md` abgelegt — kein Code, da Mahn-Modul nicht existiert |
| Splits-Struktur | „Sub-Tabelle HausgeldSollstellungSplit" | Bleibt; Spec ergänzt aber: **`HausgeldHistorie` selbst hat 1 Zeile pro `(EV, BA)`**, kein eigenes Split-Modell für die Historie (siehe Hausgeld/Nebenbuch-Spec Schritt 3) |

---

## 1. Zweck

Mehrere Geschäftsvorgänge müssen bestehende, GoBD-unwiderrufliche
Sollstellungen rückwirkend korrigieren:

- **Rückwirkender Eigentümerwechsel**: Sollstellung lautete auf den
  Voreigentümer, soll auf den Neueigentümer übergehen
- **Rückwirkende Wirtschaftsplan-Änderung**: Sollstellung war mit altem
  Hausgeldsatz, soll mit neuem Satz neu angelegt werden
- (Zukünftig) weitere Korrektur-Auslöser

Diese Spec definiert den **gemeinsamen Mechanismus** dafür:
„Original-Sollstellung neutralisieren durch eine negative Korrektur-
Sollstellung; gleichzeitig eine neue Sollstellung mit korrekten Werten
anlegen."

## 2. Architekturprinzipien

| Prinzip | Verhalten |
|---|---|
| Original bleibt unangetastet | Original-Sollstellung wird **nicht** storniert (`ist_betrag` darf != 0 sein), nicht umdatiert, nicht gelöscht. Sie behält ihre OPOS-Nr. und ihren Tilgungs-Status. |
| Korrektur ist eigene Sollstellung | Negativ-Sollstellung mit eigener OPOS-Nr., eigenem Soll-Saldo, eigenem Lebenszyklus |
| Verkettung explizit | Über zwei neue Felder `neutralisiert_durch_opos` (am Original) und `neutralisiert_opos_nr` (an der Korrektur) ist die Beziehung 1:1 sichtbar |
| Neuanlage hat gleiche Periode wie Original | Saubere Salden-Historie pro Periode |
| Splits-Verhalten parametrisiert | Wenn `neue_splits=None`: Splits aus Original geklont (Use-Case Wechsel). Wenn `neue_splits=[(ba,betrag),...]`: neue Splits (Use-Case Wirtschaftsplan). |
| Idempotenz | Ein Original darf nur einmal neutralisiert werden (Constraint) |
| Mahn-Sperre auf Neutralisierte | Sollstellungen mit `neutralisiert_durch_opos != NULL` werden vom späteren Mahnwesen ignoriert (Pflicht-Filter, dokumentiert) |
| Vorzeichen-konsistente Tilgung | Korrektur-Sollstellungen haben negativen `soll_betrag` und negativen `ist_betrag` nach Auszahlung |

---

## 3. Datenmodell-Erweiterungen am `HausgeldSollstellung`-Modell

Alle Felder werden in **einer** Migration durch diese Spec angelegt
(nicht in Wechsel-Spec, nicht in Wirtschaftsplan-Spec).

### 3.1 Neue Felder

| Feld | Typ | Anmerkung |
|---|---|---|
| `sollstellungs_typ` | (bereits vorhanden) | Erweiterung um Enum-Wert `korrektur` |
| `korrektur_grund` | CharField(40), nullable, choices | NULL bei normalen Sollstellungen. Bei Korrektur- und Neuanlage-Sollstellungen Pflicht. Choices: `('eigentuemerwechsel', 'wirtschaftsplan_aenderung')` |
| `korrektur_vorgang_id` | UUIDField, nullable | UUID des auslösenden Vorgangs. Kein FK, weil Ziel-Tabelle vom `korrektur_grund` abhängt. Helper-Funktion löst auf. |
| `neutralisiert_durch_opos` | FK → HausgeldSollstellung (self), nullable, on_delete=PROTECT | An der **Original**-Sollstellung. Zeigt auf die Korrektur. |
| `neutralisiert_opos_nr` | FK → HausgeldSollstellung (self), nullable, on_delete=PROTECT | An der **Korrektur**-Sollstellung. Zeigt auf das Original. |

`on_delete=PROTECT` verhindert versehentliches Löschen bei
GoBD-relevanten Verkettungen.

### 3.2 Indizes

Pflicht-Indizes auf:
- `neutralisiert_durch_opos` (Mahn-Filter)
- `sollstellungs_typ` (Mahn-Filter und Reporting)
- `korrektur_vorgang_id` (Vorgangs-Detailansicht)

### 3.3 Constraints

**CheckConstraint `negative_nur_bei_korrektur`:**
```python
class Meta:
    constraints = [
        models.CheckConstraint(
            name='negative_betrag_nur_korrektur',
            check=(
                Q(soll_betrag__gte=0)
                | Q(sollstellungs_typ='korrektur')
            ),
        ),
        models.CheckConstraint(
            name='korrektur_grund_consistency',
            check=(
                Q(sollstellungs_typ='korrektur', korrektur_grund__isnull=False, korrektur_vorgang_id__isnull=False)
                | ~Q(sollstellungs_typ='korrektur')
            ),
        ),
    ]
```

---

## 4. Service-Architektur

```
apps/buchhaltung/services/
└── korrektur_sollstellung_service.py    # NEU
```

### 4.1 Public-API

```python
def korrigiere_sollstellung(
    original: HausgeldSollstellung,
    neue_eigentumsverhaeltnis: EigentumsVerhaeltnis,
    neue_splits: list[tuple[Buchungsart, Decimal]] | None,
    korrektur_grund: str,
    korrektur_vorgang_id: UUID,
    user: User,
) -> tuple[HausgeldSollstellung, HausgeldSollstellung]:
    """
    Erzeugt für eine Original-Sollstellung:
      (a) Korrektur-Sollstellung auf original.eigentumsverhaeltnis
          mit negierten Splits
      (b) Neuanlage-Sollstellung auf neue_eigentumsverhaeltnis
          mit neuen oder geklonten Splits

    Splits-Verhalten:
      - neue_splits=None: Splits werden 1:1 aus Original geklont
        (Use-Case: Eigentümerwechsel, gleicher Hausgeldsatz, andere Person)
      - neue_splits=[(ba, betrag), ...]: Splits werden aus dieser Liste
        gebildet (Use-Case: Wirtschaftsplan-Änderung, andere Beträge)

    Verkettung:
      - original.neutralisiert_durch_opos = korrektur
      - korrektur.neutralisiert_opos_nr = original
      - korrektur.korrektur_grund = korrektur_grund
      - korrektur.korrektur_vorgang_id = korrektur_vorgang_id
      - neuanlage.korrektur_grund = korrektur_grund
      - neuanlage.korrektur_vorgang_id = korrektur_vorgang_id

    Returns:
      (korrektur_sollstellung, neuanlage_sollstellung)

    Raises:
      ValidationError wenn original bereits neutralisiert wurde
      (original.neutralisiert_durch_opos != None)
    """
```

### 4.2 Helper für Vorgangs-Auflösung

```python
def get_korrektur_vorgang(sollstellung: HausgeldSollstellung):
    """
    Lädt den verlinkten Vorgang anhand korrektur_grund + korrektur_vorgang_id.

    Returns:
      EigentuemerwechselVorgang | WirtschaftsplanBeschluss | None
    """
    if sollstellung.korrektur_vorgang_id is None:
        return None
    if sollstellung.korrektur_grund == 'eigentuemerwechsel':
        from apps.buchhaltung.models import EigentuemerwechselVorgang
        return EigentuemerwechselVorgang.objects.get(pk=sollstellung.korrektur_vorgang_id)
    elif sollstellung.korrektur_grund == 'wirtschaftsplan_aenderung':
        from apps.buchhaltung.models import WirtschaftsplanBeschluss
        return WirtschaftsplanBeschluss.objects.get(pk=sollstellung.korrektur_vorgang_id)
    return None
```

---

## 5. Pseudocode

### 5.1 `korrigiere_sollstellung`

```python
@transaction.atomic
def korrigiere_sollstellung(
    original,
    neue_eigentumsverhaeltnis,
    neue_splits,
    korrektur_grund,
    korrektur_vorgang_id,
    user,
):
    # 1. Idempotenz-Check
    if original.neutralisiert_durch_opos is not None:
        raise ValidationError(
            f"Sollstellung {original.opos_nr} wurde bereits neutralisiert "
            f"(durch {original.neutralisiert_durch_opos.opos_nr})."
        )

    # 2. Korrektur-Sollstellung anlegen (negativ, gleiche EV wie Original)
    korrektur = HausgeldSollstellung.objects.create(
        objekt=original.objekt,
        eigentumsverhaeltnis=original.eigentumsverhaeltnis,
        periode=original.periode,
        sollstellungs_typ='korrektur',
        soll_betrag=-original.soll_betrag,
        ist_betrag=Decimal('0.00'),
        korrektur_grund=korrektur_grund,
        korrektur_vorgang_id=korrektur_vorgang_id,
        neutralisiert_opos_nr=original,
        erstellt_von=user,
    )
    # OPOS-Nr. wird durch Modell-save() oder bestehenden Service vergeben

    # Splits der Korrektur (negierte Original-Splits)
    _negiere_splits(original, korrektur)

    # 3. Rückverkettung am Original
    original.neutralisiert_durch_opos = korrektur
    original.save(update_fields=['neutralisiert_durch_opos'])

    # 4. Neuanlage-Sollstellung
    if neue_splits is None:
        # Use-Case Wechsel: gleiche Beträge wie Original
        neuanlage_betrag = original.soll_betrag
    else:
        # Use-Case Wirtschaftsplan: Summe der neuen Splits
        neuanlage_betrag = sum(b for _, b in neue_splits)

    neuanlage = HausgeldSollstellung.objects.create(
        objekt=original.objekt,
        eigentumsverhaeltnis=neue_eigentumsverhaeltnis,
        periode=original.periode,
        sollstellungs_typ='hausgeld',
        soll_betrag=neuanlage_betrag,
        ist_betrag=Decimal('0.00'),
        korrektur_grund=korrektur_grund,
        korrektur_vorgang_id=korrektur_vorgang_id,
        erstellt_von=user,
    )

    if neue_splits is None:
        _klone_splits(original, neuanlage)
    else:
        _setze_splits(neuanlage, neue_splits)

    return korrektur, neuanlage


def _negiere_splits(original, korrektur):
    """
    Erzeugt für jeden Original-Split einen Split mit negiertem Betrag
    an der Korrektur.
    """
    from apps.buchhaltung.models import HausgeldSollstellungSplit
    for s in original.splits.all():
        HausgeldSollstellungSplit.objects.create(
            sollstellung=korrektur,
            buchungsart=s.buchungsart,
            betrag=-s.betrag,
        )


def _klone_splits(original, neuanlage):
    """1:1-Kopie der Original-Splits an die Neuanlage."""
    from apps.buchhaltung.models import HausgeldSollstellungSplit
    for s in original.splits.all():
        HausgeldSollstellungSplit.objects.create(
            sollstellung=neuanlage,
            buchungsart=s.buchungsart,
            betrag=s.betrag,
        )


def _setze_splits(sollstellung, splits):
    """Splits aus expliziter Liste anlegen."""
    from apps.buchhaltung.models import HausgeldSollstellungSplit
    for ba, betrag in splits:
        HausgeldSollstellungSplit.objects.create(
            sollstellung=sollstellung,
            buchungsart=ba,
            betrag=betrag,
        )
```

---

## 6. Mahn-Filter — Dokumentations-Pflicht

Diese Spec implementiert das Mahnwesen NICHT (eigene zukünftige Spec).
Sie hinterlegt aber den **Pflicht-Filter**, den die zukünftige Mahn-Spec
zu nutzen hat, als Datei im Repository:

```
docs/mahnwesen_pflicht_filter.md
```

Inhalt der Datei:

```markdown
# Pflicht-Filter für zukünftiges Mahnwesen

Sobald das Mahnwesen-Modul implementiert wird, MUSS die Selektion
der zu mahnenden Sollstellungen folgende zwei Filter setzen:

```python
mahnbare = HausgeldSollstellung.objects.filter(
    soll_betrag__gt=models.F('ist_betrag'),
    neutralisiert_durch_opos__isnull=True,
).exclude(
    sollstellungs_typ='korrektur',
)
```

Begründung:
- `neutralisiert_durch_opos__isnull=True`: Originale, die durch eine
  Korrektur (Eigentümerwechsel, Wirtschaftsplan-Änderung) neutralisiert
  wurden, dürfen nicht gemahnt werden.
- `sollstellungs_typ != 'korrektur'`: Korrektur-Sollstellungen selbst
  (mit negativem Betrag) dürfen nicht gemahnt werden — sie sind keine
  Forderungen gegen den Eigentümer, sondern Verbindlichkeiten.

Quellen:
- IMMOCORE_ClaudeCode_KorrekturService_v1_2.md Kap. 6
- IMMOCORE_ClaudeCode_RueckwirkenderEigentuemerwechsel_v1_1.md Kap. 9
```

---

## 7. Tilgungs-Vorzeichen für Korrektur-Sollstellungen

Da Korrektur-Sollstellungen einen negativen `soll_betrag` haben, muss
die Tilgungs-Logik vorzeichenrichtig arbeiten. Bestehender Tilgungs-
Service braucht eine kleine Erweiterung:

```python
def tilge_sollstellung(sollstellung, betrag_eingang: Decimal):
    """
    betrag_eingang ist immer positiv (echter Geldfluss).

    Bei Standard-Sollstellung (soll_betrag > 0):
      ist_betrag wächst gegen soll_betrag (positiver Bereich)

    Bei Korrektur-Sollstellung (soll_betrag < 0):
      Das System muss Geld AUSZAHLEN (an Eigentümer).
      Der Ausgang vom Bank-Konto kommt als "Tilgung" durch.
      ist_betrag wird negativer (Richtung soll_betrag).
    """
    if sollstellung.soll_betrag < 0:
        # Korrektur-Sollstellung: Auszahlung
        sollstellung.ist_betrag -= betrag_eingang
    else:
        sollstellung.ist_betrag += betrag_eingang
    sollstellung.save(update_fields=['ist_betrag'])
```

Wichtig: Bestehender Tilgungs-Service muss diese Vorzeichen-Logik
implementieren. Tests sind Pflicht.

---

## 8. Akzeptanzkriterien (Smoke-Test)

1. **Klonen-Modus:** `korrigiere_sollstellung(original, neue_ev, neue_splits=None, ...)` erzeugt Korrektur mit negierten Splits und Neuanlage mit identischen Splits wie Original.
2. **Neue-Splits-Modus:** `korrigiere_sollstellung(original, gleiche_ev, neue_splits=[(BA1, 360.00), (BA2, 60.00)], ...)` erzeugt Korrektur mit negierten Original-Splits und Neuanlage mit den angegebenen Splits (Summe 420.00).
3. **Idempotenz:** Zweiter Aufruf für dasselbe Original → ValidationError.
4. **Verkettung:** `original.neutralisiert_durch_opos.pk == korrektur.pk` und `korrektur.neutralisiert_opos_nr.pk == original.pk`.
5. **CheckConstraint negativ:** `HausgeldSollstellung.objects.create(soll_betrag=-100, sollstellungs_typ='hausgeld', ...)` → IntegrityError.
6. **CheckConstraint korrektur_grund:** `create(sollstellungs_typ='korrektur', korrektur_grund=None, ...)` → IntegrityError.
7. **OPOS-Nr.:** Korrektur und Neuanlage bekommen je eigene OPOS-Nr. (per bestehendem OPOS-Service).
8. **Tilgungs-Vorzeichen:** Korrektur mit `soll_betrag=-720`. Eingang 720 → `ist_betrag=-720` (vollständig getilgt).
9. **Vorgangs-Auflöser:** `get_korrektur_vorgang(neuanlage)` mit `korrektur_grund='eigentuemerwechsel'` lädt korrekt einen `EigentuemerwechselVorgang`.
10. **Mahn-Filter-Doku:** `docs/mahnwesen_pflicht_filter.md` existiert mit korrekten Inhalten.

---

## 9. Aufgaben für Claude Code

> **Hinweis:** Diese Spec ist Vorbedingung für Wechsel- und
> Wirtschaftsplan-Spec. Phase A komplett abschließen, dann harter Stopp.

### Phase A — Vollständige Implementierung

**A1: Migration `HausgeldSollstellung`-Erweiterung**
Datei: `apps/buchhaltung/migrations/0XXX_korrektur_service.py`
- Enum-Wert `korrektur` zu `sollstellungs_typ` ergänzen
- Felder `korrektur_grund`, `korrektur_vorgang_id`,
  `neutralisiert_durch_opos`, `neutralisiert_opos_nr` anlegen
- Indizes auf `neutralisiert_durch_opos`, `sollstellungs_typ`,
  `korrektur_vorgang_id`
- CheckConstraints `negative_betrag_nur_korrektur` und
  `korrektur_grund_consistency`

**A2: Service `korrektur_sollstellung_service.py`**
Datei: `apps/buchhaltung/services/korrektur_sollstellung_service.py`
- Funktion `korrigiere_sollstellung` aus Kap. 5.1
- Helper `_negiere_splits`, `_klone_splits`, `_setze_splits`
- Helper `get_korrektur_vorgang` aus Kap. 4.2
  (mit lazy import wegen zukünftiger Models)

**A3: Erweiterung Tilgungs-Service**
Bestehenden Tilgungs-Service so anpassen, dass er mit negativem
`soll_betrag` umgehen kann (Kap. 7).

**A4: Mahn-Filter-Dokumentation**
Datei `docs/mahnwesen_pflicht_filter.md` mit Inhalt aus Kap. 6 anlegen.

**A5: Unit-Tests**
- Smoke-Tests 1-9 aus Kap. 8
- Klonen vs. neue Splits abdecken
- Vorzeichen-Tests für Tilgung

🛑 **HARTER STOPP nach Phase A.**

Erst danach kann die Wechsel-Spec oder die Wirtschaftsplan-Spec starten.

---

**Ende der Spezifikation.**
