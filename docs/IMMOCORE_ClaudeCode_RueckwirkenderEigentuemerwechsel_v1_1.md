# IMMOCORE — Rückwirkender Eigentümerwechsel mit Sollstellungs-Korrektur

**Version:** v1.1 (konsolidiert)
**Status:** 🟢 Implementierungsreif
**Ersetzt:** v1.0 vollständig
**Bezug:**
- Erweitert `CLAUDE_CODE_ANLEITUNG_HAUSGELD_NEBENBUCH_v1_1.md`
- Setzt `IMMOCORE_ClaudeCode_KorrekturService_v1_2.md` voraus

---

## Änderungsverzeichnis gegenüber v1.0

| Bereich | v1.0 (alt) | v1.1 (neu) |
|---|---|---|
| EV-Lifecycle-Feld | `aktiv` (Boolean) + `gueltig_bis` (DateField) | **`ende` (DateField, NULL = aktiv)** — entspricht tatsächlichem Modell aus Ausgangsspezifikation Kap. 4.6 |
| Korrektur-Mechanik | Inline in dieser Spec | Verlagert in `IMMOCORE_ClaudeCode_KorrekturService_v1_2.md` |
| `_filtere_lastschrift_kandidaten` | Eigenständig | Verweis auf AutoPipeline-Spec |
| UniqueConstraint-Handling | Implizit | Explizit dokumentiert (Reihenfolge in Transaktion) |
| Splits-Aufbau | Eigene Sub-Tabelle erwähnt | Verweis auf bestehende `HausgeldSollstellungSplit` aus Hausgeld/Nebenbuch-Spec |

---

## 1. Zweck

In der Praxis melden Eigentümer einen Eigentumswechsel **regelmäßig
mit drei oder mehr Monaten Verzögerung** bei Demme. In dieser
Zwischenzeit liefen monatliche Sollstellungen auf den **Voreigentümer**.

Diese Spec regelt die rückwirkende Korrektur über den **generischen
Korrektur-Service** aus Spec v1.2 und ergänzt die wechsel-spezifischen
Komponenten: Vorgangs-Modell, UI, Auszahlungs-Trigger.

## 2. Architekturprinzipien

| Prinzip | Verhalten |
|---|---|
| Original-Sollstellungen unangetastet | Siehe Korrektur-Service-Spec Kap. 2 |
| EV-Lifecycle über `ende`-Feld | Voreigentümer-EV: `ende = wechsel_datum - 1 Tag`. Neueigentümer-EV: `ende = NULL` (aktiv). |
| Vier-Augen-Workflow | Wechsel-Vorgang läuft als `vorschau → freigegeben` mit `freigegeben_von != erstellt_von` |
| Auszahlung über bestehenden Mechanismus | Voreigentümer-Habenseite per pain.001 (Hausgeld/Nebenbuch-Spec Kap. 10.5) |
| Auto-Pipeline ab Folgemonat | Sobald Wechsel committet, läuft die normale Auto-Pipeline auf die neue EV |

## 3. Abgrenzung

### 3.1 Was diese Spec NICHT regelt
- Vorwärtsgerichtete Eigentümerwechsel ohne Rückwirkung — normale EV-Anlage
- Sonderumlagen aus Beschlüssen vor Wechsel-Datum — bleiben beim Voreigentümer
- Abrechnungsergebnisse für Vorjahre — separate Spec
- Wechsel-Datum nicht am Monatsersten — siehe Kap. 7.5 (v1.0 nicht unterstützt)

### 3.2 Auslöser
Wizard wird manuell angestoßen bei Erfassung eines Wechsels mit
`wechsel_datum < heute - 30 Tage`. Bei kleineren Verzögerungen
schlägt das System einen einfacheren Workflow vor (eine Korrektur-Periode);
bei größeren Multi-Monats-Workflow.

## 4. Datenmodell

### 4.1 Bestehendes `HausgeldSollstellung` (Erweiterung durch Korrektur-Service-Spec)

Bereits in Korrektur-Service-Spec v1.2 Kap. 3 angelegt:
- `sollstellungs_typ` Enum-Wert `korrektur`
- `korrektur_grund`, `korrektur_vorgang_id`
- `neutralisiert_durch_opos`, `neutralisiert_opos_nr`

**Diese Spec fügt nichts mehr am Sollstellungs-Modell hinzu.**

### 4.2 Neue Tabelle `EigentuemerwechselVorgang`

| Feld | Typ | Anmerkung |
|---|---|---|
| `id` | UUID | |
| `objekt` | FK → Objekt | |
| `einheit` | FK → Einheit | |
| `voreigentuemer_ev` | FK → EigentumsVerhaeltnis | Die alte EV (vor Wechsel) |
| `neueigentuemer_ev` | FK → EigentumsVerhaeltnis | Die neue EV (wird beim Vorgang erzeugt) |
| `wechsel_datum` | DateField | Wirtschaftliches Wechseldatum (Monatserster) |
| `meldedatum` | DateField | Tag der Erfassung in IMMOCORE |
| `status` | CharField, choices=`[('vorschau','vorschau'),('freigegeben','freigegeben')]` | |
| `erstellt_von` | FK → User | |
| `freigegeben_von` | FK → User, nullable | Constraint: `freigegeben_von != erstellt_von` |
| `erstellt_am` | DateTimeField | |
| `freigegeben_am` | DateTimeField, nullable | |
| `auszahlungsbetrag` | DecimalField(14,2) | Erstattung an Voreigentümer |
| `auszahlungs_iban` | CharField | IBAN des Voreigentümers für Rückerstattung |
| `notiz` | TextField, nullable | |
| `auszahlung_unterdruecken` | BooleanField, default=False | Käufer/Verkäufer regeln untereinander |

### 4.3 Neue Tabelle `WechselKorrekturPaar`

| Feld | Typ | Anmerkung |
|---|---|---|
| `id` | UUID | |
| `wechsel_vorgang` | FK → EigentuemerwechselVorgang | |
| `periode` | DateField | |
| `original_sollstellung` | FK → HausgeldSollstellung | Voreigentümer, ursprünglich |
| `korrektur_sollstellung` | FK → HausgeldSollstellung, nullable | Voreigentümer, negativ (nach Commit gesetzt) |
| `neuanlage_sollstellung` | FK → HausgeldSollstellung, nullable | Neueigentümer, positiv (nach Commit gesetzt) |
| `original_ist_betrag_vor_korrektur` | DecimalField(14,2) | Snapshot zum Korrektur-Zeitpunkt |

Read-only nach Erstellung.

## 5. Service-Architektur

```
apps/buchhaltung/services/
└── eigentuemerwechsel_korrektur_service.py    # NEU

apps/buchhaltung/models/
└── eigentuemerwechsel.py                       # NEU
```

## 6. Pseudocode

### 6.1 Vorschau

```python
@transaction.atomic
def vorschau_erstellen(
    objekt: Objekt,
    einheit: Einheit,
    wechsel_datum: date,
    neueigentuemer_data: dict,
    user: User,
) -> EigentuemerwechselVorgang:
    """
    Erstellt den Vorgang im Status 'vorschau'. Berechnet Beträge OHNE
    persistente Korrektur-Sollstellungen anzulegen.
    """
    # Validierung
    if wechsel_datum.day != 1:
        raise ValidationError("Wechsel-Datum muss Monatserster sein.")

    # 1. Voreigentümer-EV finden (aktive EV der Einheit)
    voreigentuemer_ev = EigentumsVerhaeltnis.objects.get(
        einheit=einheit,
        ende__isnull=True,   # ende=NULL bedeutet aktiv
    )

    # 2. Neueigentümer-EV anlegen
    # WICHTIG: Wir können sie NICHT direkt mit ende=NULL anlegen, weil
    # das den UniqueConstraint uniq_aktiver_vertrag_je_einheit verletzen
    # würde (Voreigentümer hat noch ende=NULL).
    # Lösung: Vorschau-EV bekommt ende = wechsel_datum (im Status
    # 'vorschau' temporär). Beim Commit wird das umgedreht.
    neueigentuemer_ev = _erstelle_oder_finde_neueigentuemer_ev(
        einheit=einheit,
        wechsel_datum=wechsel_datum,
        person_data=neueigentuemer_data,
        ende_initial=wechsel_datum,  # platzhalter; wird beim Commit auf NULL gesetzt
    )

    # 3. Vorgang anlegen
    vorgang = EigentuemerwechselVorgang.objects.create(
        objekt=objekt,
        einheit=einheit,
        voreigentuemer_ev=voreigentuemer_ev,
        neueigentuemer_ev=neueigentuemer_ev,
        wechsel_datum=wechsel_datum,
        meldedatum=timezone.localdate(),
        status='vorschau',
        erstellt_von=user,
        auszahlungsbetrag=Decimal('0.00'),
    )

    # 4. Betroffene Sollstellungen vorbereiten
    betroffene_originals = _ermittle_betroffene_perioden(
        voreigentuemer_ev, wechsel_datum
    )

    auszahlungsbetrag = Decimal('0.00')
    for original in betroffene_originals:
        # Nur was wirklich geflossen ist, zählt zur Auszahlung
        auszahlungsbetrag += min(original.ist_betrag, original.soll_betrag)
        WechselKorrekturPaar.objects.create(
            wechsel_vorgang=vorgang,
            periode=original.periode,
            original_sollstellung=original,
            korrektur_sollstellung=None,
            neuanlage_sollstellung=None,
            original_ist_betrag_vor_korrektur=original.ist_betrag,
        )

    vorgang.auszahlungsbetrag = auszahlungsbetrag
    vorgang.save(update_fields=['auszahlungsbetrag'])

    return vorgang


def _ermittle_betroffene_perioden(voreigentuemer_ev, wechsel_datum):
    """Findet alle committeten Hausgeld-Sollstellungen ab wechsel_datum."""
    return HausgeldSollstellung.objects.filter(
        eigentumsverhaeltnis=voreigentuemer_ev,
        sollstellungs_typ='hausgeld',
        periode__gte=wechsel_datum,
        status='commited',
        neutralisiert_durch_opos__isnull=True,
    ).order_by('periode')
```

### 6.2 Commit

```python
@transaction.atomic
def vorschau_committen(
    vorgang: EigentuemerwechselVorgang,
    freigabe_user: User,
    auszahlungs_iban: str,
    auszahlung_unterdruecken: bool = False,
) -> EigentuemerwechselVorgang:
    """
    Vier-Augen-Freigabe. Erzeugt Korrekturen über generischen Service.
    """
    # Vier-Augen-Constraint
    if freigabe_user.id == vorgang.erstellt_von_id:
        raise ValidationError(
            "Freigabe-User muss von Ersteller verschieden sein"
        )
    if vorgang.status != 'vorschau':
        raise ValidationError(f"Status {vorgang.status} nicht freigabefähig")

    paare = vorgang.korrektur_paare.select_related('original_sollstellung')

    for paar in paare:
        original = paar.original_sollstellung

        # Generischer Korrektur-Service (aus KorrekturService_v1_2 Kap. 4)
        korrektur, neuanlage = korrektur_sollstellung_service.korrigiere_sollstellung(
            original=original,
            neue_eigentumsverhaeltnis=vorgang.neueigentuemer_ev,
            neue_splits=None,   # Klonen → gleicher Hausgeldsatz für Neueigentümer
            korrektur_grund='eigentuemerwechsel',
            korrektur_vorgang_id=vorgang.id,
            user=freigabe_user,
        )

        paar.korrektur_sollstellung = korrektur
        paar.neuanlage_sollstellung = neuanlage
        paar.save(update_fields=['korrektur_sollstellung', 'neuanlage_sollstellung'])

    # Vorgang finalisieren
    vorgang.status = 'freigegeben'
    vorgang.freigegeben_von = freigabe_user
    vorgang.freigegeben_am = timezone.now()
    vorgang.auszahlungs_iban = auszahlungs_iban
    vorgang.auszahlung_unterdruecken = auszahlung_unterdruecken
    vorgang.save()

    # EV-Lifecycle umstellen
    # WICHTIG: Reihenfolge entscheidend wegen UniqueConstraint
    # uniq_aktiver_vertrag_je_einheit (nur eine EV pro Einheit darf
    # ende=NULL haben).
    #
    # Schritt 1: Alte EV beenden (ende setzen)
    vorgang.voreigentuemer_ev.ende = vorgang.wechsel_datum - timedelta(days=1)
    vorgang.voreigentuemer_ev.save(update_fields=['ende'])

    # Schritt 2: Neue EV aktivieren (ende = NULL)
    # Vorher hatte sie ende=wechsel_datum als Platzhalter
    vorgang.neueigentuemer_ev.ende = None
    vorgang.neueigentuemer_ev.save(update_fields=['ende'])

    # Auszahlung (wenn nicht unterdrückt)
    if not auszahlung_unterdruecken and vorgang.auszahlungsbetrag > 0:
        _initiiere_rueckzahlung(vorgang)

    # Frontoffice-Aufgabe für Neueigentümer-Forderung
    _erzeuge_frontoffice_aufgabe_neueigentuemer(vorgang)

    return vorgang
```

### 6.3 Erstellung Neueigentümer-EV

```python
def _erstelle_oder_finde_neueigentuemer_ev(einheit, wechsel_datum,
                                            person_data, ende_initial):
    """
    Sucht nach existierender Person (über E-Mail oder IBAN) oder legt
    neue an. Erstellt EV mit ende=ende_initial (Platzhalter beim Vorschau,
    NULL beim Commit).
    """
    person = _finde_oder_erstelle_person(person_data)
    ev = EigentumsVerhaeltnis.objects.create(
        einheit=einheit,
        person=person,
        beginn=wechsel_datum,
        ende=ende_initial,  # wird beim Commit auf NULL gesetzt
    )
    return ev
```

## 7. Sonderfälle

### 7.1 Voreigentümer nicht alles gezahlt

| Originalzustand | Ergebnis nach Korrektur |
|---|---|
| Sollstellung 04: soll=360, ist=360 | Korrektur 04: soll=-360, ist=0 → durch Auszahlung wird ist=-360 |
| Sollstellung 06: soll=360, ist=0 (offen) | Korrektur 06: soll=-360, ist=0 → bleibt offen, neutralisiert Original |

**Auszahlung = Summe der gezahlten Beträge der neutralisierten Sollstellungen.**

```python
def auszahlungsbetrag_berechnen(vorgang):
    summe = Decimal('0.00')
    for paar in vorgang.korrektur_paare.all():
        summe += paar.original_ist_betrag_vor_korrektur
    return summe
```

### 7.2 Neueigentümer schuldet Geld
Frontoffice-Aufgabe „Neueigentümer 1.080 € rückwirkende Forderung" wird
beim Commit automatisch angelegt. Tilgung läuft über normale Mechanik.

### 7.3 Wechsel in bereits abgerechneter Periode
Hausgeld-Sollstellungen werden korrigiert. **Abrechnungsergebnis-
Sollstellung NICHT** — gehört in separate Spec.

Warnung in UI Schritt 2.

### 7.4 Käufer/Verkäufer regeln untereinander
Checkbox „Auszahlung unterdrücken". Korrektur-Sollstellungen werden
trotzdem erzeugt, aber pain.001 wird nicht angestoßen. Frontoffice-Aufgabe
„Interne Umbuchung manuell vornehmen" wird erzeugt.

### 7.5 Wechsel-Datum nicht am Monatsersten
Nicht unterstützt in v1.0. Validierung `wechsel_datum.day == 1`.

## 8. Auto-Pipeline-Verhalten

Nach Commit:
- `voreigentuemer_ev.ende != NULL` (beendet)
- `neueigentuemer_ev.ende = NULL` (aktiv)

Bestehende Auto-Pipeline iteriert über aktive EVs
(`ende__isnull=True`) → nächster Stichtag erzeugt automatisch
Sollstellung auf den Neueigentümer.

## 9. Mahn-Filter

Siehe Korrektur-Service-Spec Kap. 6 (`docs/mahnwesen_pflicht_filter.md`).

## 10. Auszahlungs-Mechanismus

Ruft bestehenden Auszahlungs-Service aus Hausgeld/Nebenbuch-Spec Kap. 10.5
auf:

```python
def _initiiere_rueckzahlung(vorgang):
    auszahlung_service.erstelle_auszahlung(
        empfaenger_iban=vorgang.auszahlungs_iban,
        empfaenger_name=_person_anzeigename(vorgang.voreigentuemer_ev.person),
        betrag=vorgang.auszahlungsbetrag,
        verwendungszweck=(
            f"Rückerstattung Eigentümerwechsel "
            f"{vorgang.einheit.einheit_nr} - "
            f"Objekt {vorgang.objekt.kurzbezeichnung or vorgang.objekt.bezeichnung}"
        ),
        referenz_vorgang_id=vorgang.id,
    )
```

## 11. UI-Anforderungen

### 11.1 Wizard `/objekte/{id}/eigentuemerwechsel/neu/`

**Schritt 1 — Stammdaten:**
- Einheit
- Wechsel-Datum (Validierung Monatserster)
- Neueigentümer (Person aus Stammdaten oder neu anlegen)
- IBAN des Voreigentümers

**Schritt 2 — Vorschau:**
- Tabelle aller betroffenen Perioden mit Beträgen
- Summenzeile: Rückerstattung Voreigentümer / Forderung Neueigentümer
- Checkbox „Auszahlung unterdrücken"
- Warnbox bei abgerechneter Periode

**Schritt 3 — Freigabe (Vier-Augen):**
- Zweiter User
- Constraint erzwungen

### 11.2 Vorgangs-Detail `/eigentuemerwechsel/{id}/`
Read-only nach Freigabe. Alle Sollstellungs-Verlinkungen.

## 12. Akzeptanzkriterien (Smoke-Test)

1. **Standardfall:** 3 Monate rückwirkend, alle gezahlt → 3 Korrektur-Sollstellungen, 3 Neuanlagen, Auszahlung initiiert.
2. **Vier-Augen-Constraint:** Gleicher User → ValidationError.
3. **Teilzahlung:** 3 Monate, 2 gezahlt → Auszahlung 720 €. Der dritte Monat: Original und Korrektur beide offen, beide vom Mahnwesen ausgenommen.
4. **Wechsel nicht am Monatsersten:** Validierung schlägt fehl.
5. **Auszahlung unterdrückt:** Keine pain.001, aber Frontoffice-Aufgabe.
6. **Wechsel in abgerechneter Periode:** Warnbox erscheint; Abrechnungs-Sollstellung nicht angefasst.
7. **Auto-Pipeline-Folge:** Nächster Stichtag läuft auf Neueigentümer.
8. **Tilgungs-Vorzeichen:** Rückzahlung tilgt Korrektur korrekt im negativen Bereich.
9. **EV-Lifecycle:** Nach Commit Voreigentümer `ende != NULL`, Neueigentümer `ende = NULL`. UniqueConstraint nicht verletzt.
10. **Audit:** Vorgangs-Detail zeigt alle drei Sollstellungen je Periode.

## 13. Aufgaben für Claude Code

> **Voraussetzung:** KorrekturService-Spec v1.2 muss vollständig
> implementiert sein.

### Phase A — Backend

**A1: Modelle**
- `EigentuemerwechselVorgang` (Kap. 4.2)
- `WechselKorrekturPaar` (Kap. 4.3)
- Vier-Augen-Constraint

**A2: Service `eigentuemerwechsel_korrektur_service.py`**
- `vorschau_erstellen`, `vorschau_committen` (Kap. 6)
- Helper `_finde_oder_erstelle_person`, `_initiiere_rueckzahlung`,
  `_erzeuge_frontoffice_aufgabe_neueigentuemer`
- **Reihenfolge im EV-Lifecycle strikt nach Kap. 6.2**

**A3: Auszahlungs-Integration**
- Aufruf des bestehenden Auszahlungs-Service mit korrektem
  Verwendungszweck (Kap. 10)

**A4: Tests Phase A**
- Smoke-Tests 1-9 aus Kap. 12
- Insbesondere Test 9: EV-Lifecycle und UniqueConstraint

🛑 **HARTER STOPP nach Phase A.**

### Phase B — UI

**B1: Wizard 3 Schritte** (Kap. 11.1)
**B2: Vorgangs-Detail** (Kap. 11.2)
**B3: Tab im Objekt-Detail**

### Phase C — Verifikation

**C1:** Smoke-Tests 1-10 vollständig.

---

**Ende der Spezifikation.**
