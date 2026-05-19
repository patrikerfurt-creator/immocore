# IMMOCORE — Wirtschaftsplan-Beschluss & Hausgeldhöhe-Verwaltung

**Version:** v1.2 (konsolidiert)
**Status:** 🟢 Implementierungsreif
**Ersetzt:** v1.0 und v1.1 vollständig
**Bezug:**
- Erweitert `CLAUDE_CODE_ANLEITUNG_HAUSGELD_NEBENBUCH_v1_1.md`
- Setzt `IMMOCORE_ClaudeCode_KorrekturService_v1_2.md` voraus
- Setzt `IMMOCORE_ClaudeCode_AutoPipeline_Hausgeld_v1_1.md` voraus
- Ergänzt `IMMOCORE_ClaudeCode_Massenimport_WEG_v1_0.docx` um den
  legitimen Sonderfall `quelle='import'`

---

## Änderungsverzeichnis gegenüber v1.1

| Bereich | v1.1 (alt) | v1.2 (neu) |
|---|---|---|
| `HausgeldHistorie`-Struktur | Eigene Sub-Tabelle `HausgeldHistorieSplit` neu | **Bereits vorhanden**: `HausgeldHistorie` hat `ba`-Feld (Hausgeld/Nebenbuch-Spec Schritt 3). Eine Zeile pro `(EV, BA, gueltig_ab)`. Spec passt sich daran an. |
| `hausgeld_monatlich` als eigenes Feld | Auf der `HausgeldHistorie` | **Existiert nicht**: Der Wert steht in `betrag`-Feld. Gesamthausgeld = Summe über BAs. |
| `WirtschaftsplanPosition` | Hatte eigene `hausgeld_monatlich` und Splits | Stark vereinfacht: Pro Position eine Zeile **pro EV pro BA**. Gesamtbetrag wird berechnet, nicht gespeichert. |
| Verweis auf Patch v1.1 | Ja | Verweis auf konsolidierte KorrekturService-Spec v1.2 |
| `EigentumsVerhaeltnis.aktiv` | Verwendet | Existiert nicht → `ende__isnull` |

---

## 1. Zweck

Diese Spec regelt:

**1.1 Wirtschaftsplan-Beschluss:** Die Eigentümerversammlung beschließt
einen Wirtschaftsplan, der pro EV und pro BA einen neuen monatlichen
Betrag festlegt. Die `HausgeldHistorie` jeder betroffenen EV bekommt
neue Einträge (pro BA eine Zeile) mit Verweis auf den Beschluss.

**1.2 Rückwirkende Wirksamkeit:** WEG-Beschlüsse werden in der Praxis
oft rückwirkend wirksam. Liegt der Wirtschaftsplan-Beginn vor dem
Beschluss-Datum, werden bereits committete Sollstellungen über den
generischen Korrektur-Service neutralisiert und mit neuem Satz
neuangelegt.

## 2. Architekturprinzipien

| Prinzip | Verhalten |
|---|---|
| `HausgeldHistorie` ist Single Source of Truth | Bestehend; pro `(EV, BA, gueltig_ab)` eine Zeile mit `betrag`. |
| Quelle = Beschluss (Regel) | Nach Go-Live ausschließlich. |
| Quelle = Import (Ausnahme) | Erstanlage durch Massenimport. Geschützt durch Feature-Flag. |
| Keine Verwalter-Anordnung | Stundungen und Sondervereinbarungen sind als Umlaufbeschluss zu erfassen (§ 23 Abs. 3 WEG). |
| Tilgungsvereinbarungen ≠ Hausgeldänderung | Ratenzahlungen sind Tilgungs-Plan am OPOS (separate Spec). |
| Direkte Buchung ohne Vier-Augen | Beschluss = Vielaugen-Validierung in der Versammlung. |
| Rückwirkung über generischen Korrektur-Service | Korrektur-Service-Spec v1.2 Kap. 4. |
| Saldo wird mit nächster Sollstellung eingezogen | Korrektur- und Neuanlage-OPOS bleiben separat; Auto-Pipeline sammelt sie auf. |

## 3. Abgrenzung

### 3.1 Was diese Spec NICHT regelt
- Wirtschaftsplan-Erstellung (Plan-Positionen, BA-Zuordnung) — eigene Spec
- Abrechnung — eigene Spec
- Tilgungspläne — am OPOS-Modell, separate Spec
- Massenimport selbst — siehe Massenimport-Spec; diese Spec definiert
  nur das Flag und die Quellen-Logik

### 3.2 Use-Cases

| UC | Beschreibung |
|---|---|
| UC-1 | Vorausschauender Beschluss (z.B. 12.12.2026 für 01.01.2027) |
| UC-2 | Rückwirkender Beschluss (z.B. 18.04.2027 für 01.01.2027) |
| UC-3 | Folge-Beschluss schließt alten ab (Dez 2027 für 01.01.2028) |
| UC-4 | Umlaufbeschluss-Stundung für einzelne EV, befristet |

## 4. Datenmodell

### 4.1 Neue Tabelle `WirtschaftsplanBeschluss`

| Feld | Typ | Anmerkung |
|---|---|---|
| `id` | UUID | |
| `objekt` | FK → Objekt | |
| `beschluss_typ` | CharField, choices=`[('wirtschaftsplan','wirtschaftsplan'), ('umlaufbeschluss_stundung','umlaufbeschluss_stundung'), ('umlaufbeschluss_sonstig','umlaufbeschluss_sonstig')]` | Diskriminator |
| `beschluss_datum` | DateField | Tag der ETV / des Umlaufbeschlusses |
| `protokoll_position` | CharField(50), nullable | z.B. „TOP 5.2" |
| `wirtschaftsplan_beginn` | DateField | Monatserster |
| `wirtschaftsplan_ende` | DateField, nullable | Monatsletzter; bei dauerhaftem Beschluss NULL |
| `gesamt_volumen` | DecimalField(14,2), nullable | Pflicht bei `wirtschaftsplan` |
| `protokoll_dokument` | FK → Dokument, nullable | |
| `notiz` | TextField, nullable | |
| `status` | CharField, choices=`[('erfasst','erfasst'),('gebucht','gebucht'),('storniert','storniert')]` | |
| `erstellt_von` | FK → User | |
| `erstellt_am` | DateTimeField | |
| `gebucht_am` | DateTimeField, nullable | |

**Validierung:**
- `wirtschaftsplan_beginn.day == 1`
- Bei gesetztem `wirtschaftsplan_ende`: Monatsletzter und > Beginn
- Bei `beschluss_typ='wirtschaftsplan'`: `gesamt_volumen` Pflicht
- Bei `beschluss_typ='umlaufbeschluss_stundung'`: `wirtschaftsplan_ende` Pflicht

### 4.2 Neue Tabelle `WirtschaftsplanPosition`

**Pro EV und BA eine Position.** Das spiegelt die bestehende
`HausgeldHistorie`-Struktur 1:1.

| Feld | Typ | Anmerkung |
|---|---|---|
| `id` | UUID | |
| `beschluss` | FK → WirtschaftsplanBeschluss | |
| `eigentumsverhaeltnis` | FK → EigentumsVerhaeltnis | |
| `buchungsart` | FK → Buchungsart | |
| `betrag` | DecimalField(8,2) | Monatlicher Betrag für diese BA |

**Unique-Constraint:** `(beschluss, eigentumsverhaeltnis, buchungsart)`.

**Validierung:** Bei `beschluss_typ='wirtschaftsplan'`:
- Pro aktive EV des Objekts mindestens eine Position
- Summe aller Positionen × 12 == `gesamt_volumen` (±0,01 €)

### 4.3 Erweiterung `HausgeldHistorie`

Bestehendes Modell (aus Ausgangsspezifikation Kap. 4.7):
- `eigentumsverhaeltnis`, `betrag`, `gueltig_ab`, `erstellt_von`
- `ba` (FK → Buchungsart, durch Hausgeld/Nebenbuch-Spec Schritt 3 hinzugefügt)

| Neues Feld | Typ | Anmerkung |
|---|---|---|
| `gueltig_bis` | DateField, nullable | Bisher implizit „aktuell aktiv wenn jüngster Eintrag". Jetzt explizit für saubere Zeit-Queries. |
| `quelle` | CharField, choices=`[('beschluss','beschluss'),('import','import')]` | Pflichtfeld |
| `beschluss` | FK → WirtschaftsplanBeschluss, nullable | Pflicht wenn `quelle='beschluss'` |
| `import_referenz` | CharField(100), nullable | Pflicht wenn `quelle='import'` |

**CheckConstraint:**
```python
class Meta:
    constraints = [
        models.CheckConstraint(
            name='hausgeld_historie_quelle_consistency',
            check=(
                (Q(quelle='beschluss') & Q(beschluss__isnull=False) & Q(import_referenz__isnull=True))
                | (Q(quelle='import') & Q(beschluss__isnull=True) & Q(import_referenz__isnull=False))
            ),
        ),
    ]
```

**Hinweis:** Pro EV können mehrere `HausgeldHistorie`-Zeilen gleichzeitig
aktiv sein (eine pro BA). Die bestehende Unique-Constraint
`(eigentumsverhaeltnis, ba, gueltig_ab)` deckt das ab.

### 4.4 Neue Tabelle `WirtschaftsplanKorrekturPaar`

| Feld | Typ | Anmerkung |
|---|---|---|
| `id` | UUID | |
| `beschluss` | FK → WirtschaftsplanBeschluss | |
| `eigentumsverhaeltnis` | FK → EigentumsVerhaeltnis | |
| `periode` | DateField | |
| `original_sollstellung` | FK → HausgeldSollstellung | |
| `korrektur_sollstellung` | FK → HausgeldSollstellung | |
| `neuanlage_sollstellung` | FK → HausgeldSollstellung | |
| `differenz_betrag` | DecimalField(8,2) | `neu − alt` |

Read-only nach Erstellung.

## 5. Feature-Flag und Migrations-Schutz

### 5.1 Setting `HAUSGELD_IMPORT_QUELLE_ERLAUBT`

```python
# settings.py
HAUSGELD_IMPORT_QUELLE_ERLAUBT = env.bool(
    'HAUSGELD_IMPORT_QUELLE_ERLAUBT',
    default=True,
)
```

**Lebenszyklus:**
1. Vor Go-Live: `True`. Massenimport darf `quelle='import'` setzen.
2. Nach Initialimport: Admin schaltet auf `False`.
3. Produktivbetrieb: `False`. Versuche werden vom Service abgelehnt.

### 5.2 Schutz im Service

```python
def setze_neue_saetze(..., quelle, ...):
    if quelle == 'import' and not settings.HAUSGELD_IMPORT_QUELLE_ERLAUBT:
        raise ValidationError(
            "Import-Quelle nicht erlaubt — Initialimport bereits abgeschlossen."
        )
```

### 5.3 Audit-Sichtbarkeit

In der EV-Detail-UI werden `quelle='import'`-Einträge mit eigenem Icon
+ Tooltip „Erstanlage durch Massenimport" angezeigt.

## 6. Service-Architektur

```
apps/buchhaltung/services/
├── wirtschaftsplan_beschluss_service.py    # NEU
├── korrektur_sollstellung_service.py       # aus KorrekturService-Spec
└── hausgeld_historie_service.py            # NEU
```

### 6.1 `hausgeld_historie_service`

```python
def setze_neue_saetze(
    ev: EigentumsVerhaeltnis,
    gueltig_ab: date,
    saetze_je_ba: list[tuple[Buchungsart, Decimal]],
    quelle: str,                              # 'beschluss' oder 'import'
    beschluss: WirtschaftsplanBeschluss | None,
    import_referenz: str | None,
    user: User,
) -> list[HausgeldHistorie]:
    """
    Schließt bestehende offene Einträge pro BA (gueltig_bis = gueltig_ab - 1 Tag).
    Legt pro BA einen neuen Eintrag an.

    Feature-Flag-Check für quelle='import'.

    Returns: Liste der neu angelegten HausgeldHistorie-Einträge.
    """
    # Validierung
    if quelle == 'import' and not settings.HAUSGELD_IMPORT_QUELLE_ERLAUBT:
        raise ValidationError("Import-Quelle nicht mehr erlaubt")
    if quelle == 'beschluss' and beschluss is None:
        raise ValidationError("quelle='beschluss' erfordert beschluss-FK")
    if quelle == 'import' and not import_referenz:
        raise ValidationError("quelle='import' erfordert import_referenz")

    neue_eintraege = []

    for ba, betrag in saetze_je_ba:
        # Bestehenden offenen Eintrag dieser BA schließen
        HausgeldHistorie.objects.filter(
            eigentumsverhaeltnis=ev,
            ba=ba,
            gueltig_bis__isnull=True,
        ).update(gueltig_bis=gueltig_ab - timedelta(days=1))

        # Bei rückwirkenden Beschlüssen: überlappende Einträge schließen
        HausgeldHistorie.objects.filter(
            eigentumsverhaeltnis=ev,
            ba=ba,
            gueltig_bis__gte=gueltig_ab,
        ).update(gueltig_bis=gueltig_ab - timedelta(days=1))

        # Neuen Eintrag anlegen
        neuer_eintrag = HausgeldHistorie.objects.create(
            eigentumsverhaeltnis=ev,
            ba=ba,
            gueltig_ab=gueltig_ab,
            gueltig_bis=None,
            betrag=betrag,
            quelle=quelle,
            beschluss=beschluss,
            import_referenz=import_referenz,
            erstellt_von=user,
        )
        neue_eintraege.append(neuer_eintrag)

    return neue_eintraege
```

### 6.2 `wirtschaftsplan_beschluss_service`

```python
def beschluss_erfassen(...) -> WirtschaftsplanBeschluss:
    """Status='erfasst'. Validiert Summen."""

def beschluss_buchen(beschluss, user) -> dict:
    """
    1. Pro EV: setze_neue_saetze() für alle BAs dieser EV
    2. Bei wirtschaftsplan_beginn < heute: pro EV alle betroffenen
       Sollstellungen über korrektur_sollstellung_service korrigieren
    3. status='gebucht'
    4. Frontoffice-Aufgabe „Saldenmitteilung versenden" je EV mit
       Nachforderung > 0
    """

def beschluss_stornieren(beschluss, user, grund) -> WirtschaftsplanBeschluss:
    """Nur aus status='erfasst' erlaubt."""
```

## 7. Lebenszyklus

```
       ┌───────────┐
       │  erfasst  │
       └─────┬─────┘
             │
   beschluss_buchen()
             ▼
       ┌───────────┐
       │  gebucht  │  ← Endzustand
       └───────────┘
             ▲
             │
       ┌─────┴─────┐
       │ storniert │  ← Nur aus 'erfasst'
       └───────────┘
```

Fehler-Korrekturen nach Buchung: durch neuen gegenläufigen Beschluss.

## 8. Pseudocode der Hauptoperation

### 8.1 `beschluss_buchen`

```python
@transaction.atomic
def beschluss_buchen(beschluss: WirtschaftsplanBeschluss, user: User) -> dict:
    if beschluss.status != 'erfasst':
        raise ValidationError(f"Status {beschluss.status} nicht buchbar")

    heute = timezone.localdate()
    ist_rueckwirkend = beschluss.wirtschaftsplan_beginn < heute

    stats = {
        'evs_aktualisiert': 0,
        'sollstellungen_korrigiert': 0,
        'saldenmitteilungen_erzeugt': 0,
        'gesamtdifferenz': Decimal('0.00'),
    }

    # Positionen nach EV gruppieren
    positionen_nach_ev = {}
    for position in beschluss.positionen.select_related('eigentumsverhaeltnis', 'buchungsart'):
        ev_id = position.eigentumsverhaeltnis_id
        positionen_nach_ev.setdefault(ev_id, []).append(position)

    for ev_id, positionen in positionen_nach_ev.items():
        ev = positionen[0].eigentumsverhaeltnis

        # 1. HausgeldHistorie aktualisieren (pro BA eine Zeile)
        saetze_je_ba = [(p.buchungsart, p.betrag) for p in positionen]
        hausgeld_historie_service.setze_neue_saetze(
            ev=ev,
            gueltig_ab=beschluss.wirtschaftsplan_beginn,
            saetze_je_ba=saetze_je_ba,
            quelle='beschluss',
            beschluss=beschluss,
            import_referenz=None,
            user=user,
        )
        stats['evs_aktualisiert'] += 1

        # 2. Rückwirkende Korrektur (wenn nötig)
        if ist_rueckwirkend:
            ev_differenz = _korrigiere_rueckwirkende_sollstellungen(
                beschluss=beschluss,
                ev=ev,
                positionen=positionen,
                user=user,
                stats=stats,
            )
            stats['gesamtdifferenz'] += ev_differenz

            if ev_differenz != 0:
                _erzeuge_saldenmitteilung_aufgabe(beschluss, ev, ev_differenz)
                stats['saldenmitteilungen_erzeugt'] += 1

    beschluss.status = 'gebucht'
    beschluss.gebucht_am = timezone.now()
    beschluss.save(update_fields=['status', 'gebucht_am'])

    return stats
```

### 8.2 `_korrigiere_rueckwirkende_sollstellungen`

```python
def _korrigiere_rueckwirkende_sollstellungen(
    beschluss, ev, positionen, user, stats
) -> Decimal:
    """
    Findet alle committeten Hausgeld-Sollstellungen im Wirkungszeitraum,
    korrigiert sie via Korrektur-Service.
    """
    differenz_summe = Decimal('0.00')

    periode_filter = Q(periode__gte=beschluss.wirtschaftsplan_beginn)
    if beschluss.wirtschaftsplan_ende:
        periode_filter &= Q(periode__lte=beschluss.wirtschaftsplan_ende)

    betroffene_originals = HausgeldSollstellung.objects.filter(
        periode_filter,
        eigentumsverhaeltnis=ev,
        sollstellungs_typ='hausgeld',
        status='commited',
        neutralisiert_durch_opos__isnull=True,
    ).order_by('periode')

    # Neue Splits: Liste (ba, betrag) aus den Beschluss-Positionen
    neue_splits = [(p.buchungsart, p.betrag) for p in positionen]
    neuer_gesamtbetrag = sum(b for _, b in neue_splits)

    for original in betroffene_originals:
        korrektur, neuanlage = korrektur_sollstellung_service.korrigiere_sollstellung(
            original=original,
            neue_eigentumsverhaeltnis=ev,
            neue_splits=neue_splits,
            korrektur_grund='wirtschaftsplan_aenderung',
            korrektur_vorgang_id=beschluss.id,
            user=user,
        )

        differenz = neuer_gesamtbetrag - original.soll_betrag
        differenz_summe += differenz

        WirtschaftsplanKorrekturPaar.objects.create(
            beschluss=beschluss,
            eigentumsverhaeltnis=ev,
            periode=original.periode,
            original_sollstellung=original,
            korrektur_sollstellung=korrektur,
            neuanlage_sollstellung=neuanlage,
            differenz_betrag=differenz,
        )
        stats['sollstellungen_korrigiert'] += 1

    return differenz_summe
```

## 9. UI-Anforderungen

### 9.1 Beschluss-Wizard `/objekte/{id}/beschluesse/neu/`

**Schritt 1:** Beschluss-Typ wählen.

**Schritt 2:** Stammdaten (Datum, Protokoll-Position, Wirksamkeit, Gesamt-Volumen, Dokument).

**Schritt 3:** Positionen pro EV
- Tabelle: pro Zeile eine EV, Spalten pro BA mit Beträgen
- Bei Wirtschaftsplan: alle aktiven EVs (`ende__isnull=True`) Pflicht
- Bei Umlaufbeschluss: nur betroffene EV(s)
- Vorbelegung: aktueller HausgeldHistorie-Wert je BA
- Validierung Summen

**Schritt 4:** Vorschau & Rückwirkungs-Hinweis (gelbe Warnbox bei `wirtschaftsplan_beginn < heute`).

**Schritt 5:** Direkt-Buchen (kein zusätzlicher Vier-Augen).

### 9.2 Beschluss-Detail `/beschluesse/{id}/`
Read-only. Verlinkungen zu HausgeldHistorie-Einträgen,
Korrektur-Paaren, Saldenmitteilungs-Aufgaben.

### 9.3 EV-Detail — Hausgeld-Verlauf
Neuer Tab. Tabelle aller `HausgeldHistorie`-Einträge gruppiert nach BA.
Quellen-Icon (Beschluss-Link oder Import-Migrations-Pfeil).

### 9.4 Admin-Setting „Import-Quelle erlaubt"
Toggle mit Audit-Log.

## 10. Akzeptanzkriterien (Smoke-Test)

1. **UC-1 (vorausschauend):** Beschluss am 12.12.2026 für 01.01.2027. `HausgeldHistorie` aktualisiert (pro BA eine Zeile mit `quelle='beschluss'`). Keine Korrekturen. Auto-Pipeline am 25.12. nutzt neue Sätze.
2. **UC-2 (rückwirkend):** Beschluss am 18.04.2027 für 01.01.2027. 4 Korrektur-Paare pro EV. Differenz summiert. Saldenmitteilungs-Aufgaben angelegt.
3. **UC-3 (Folge-Beschluss):** Beschluss 2 für 01.01.2028 schließt vorigen mit `gueltig_bis=31.12.2027`.
4. **UC-4 (Umlauf-Stundung):** Frontoffice-Aufgabe „Stundung läuft am 31.08.2027 ab" automatisch.
5. **CheckConstraint quelle:** `HausgeldHistorie(quelle='beschluss', beschluss=None)` → IntegrityError.
6. **Feature-Flag aktiv:** Massenimport-Service kann `quelle='import'`-Einträge anlegen.
7. **Feature-Flag inaktiv:** ValidationError.
8. **Admin-Toggle:** Setting umschaltbar mit Audit-Log.
9. **Gesamtvolumen-Validierung:** Summe ≠ Volumen → ValidationError.
10. **Pro-BA-Konsistenz:** Pro `(EV, BA)` niemals überlappende Einträge.
11. **Mahn-Filter:** Originale aus UC-2 nicht im Mahn-Selector.
12. **Lastschriftlauf-Aufsammlung:** Mai-Lauf enthält Mai-Sollstellung + 4 Neuanlage-Sollstellungen.
13. **GoBD-Stornier-Schutz:** Storno nach Buchung → ValidationError.
14. **Quellen-Indikator:** EV-Tab zeigt Icons korrekt.

## 11. Aufgaben für Claude Code

> **Voraussetzungen:** KorrekturService-Spec v1.2 und
> AutoPipeline-Spec v1.1 vollständig implementiert.

### Phase A — Datenmodell

**A1: Modelle**
- `WirtschaftsplanBeschluss` mit `beschluss_typ`-Diskriminator
- `WirtschaftsplanPosition` (eine Zeile pro EV+BA)
- `WirtschaftsplanKorrekturPaar`
- Erweiterung `HausgeldHistorie` (Felder `gueltig_bis`, `quelle`,
  `beschluss`, `import_referenz`)
- CheckConstraint `hausgeld_historie_quelle_consistency`

**A2: Feature-Flag**
- Setting `HAUSGELD_IMPORT_QUELLE_ERLAUBT`
- Admin-UI für Toggle (Kap. 9.4)

**A3: Service `hausgeld_historie_service.py`** (Kap. 6.1)

**A4: Massenimport-Anpassung**
- Importer ruft `setze_neue_saetze(quelle='import', ...)`
- Format `import_referenz` definieren

### Phase B — Beschluss-Service

**B1: Service `wirtschaftsplan_beschluss_service.py`** (Kap. 6.2, 8)

**B2: Frontoffice-Aufgaben-Typen**
- `aufgabe_typ='saldenmitteilung_wirtschaftsplan'`
- `aufgabe_typ='stundung_laeuft_ab'` (Trigger 30 Tage vor `wirtschaftsplan_ende`)

**B3: Tests Phase B**
- UC-1 bis UC-4
- Validierungs-Tests
- CheckConstraint-Tests

🛑 **HARTER STOPP nach Phase B.**

### Phase C — UI

C1-C4 gemäß Kap. 9.

### Phase D — Verifikation

D1: Smoke-Tests 1-14.

---

**Ende der Spezifikation.**
