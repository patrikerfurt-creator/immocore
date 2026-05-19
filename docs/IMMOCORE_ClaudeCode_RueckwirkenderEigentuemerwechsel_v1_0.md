# IMMOCORE — Rückwirkender Eigentümerwechsel mit Sollstellungs-Korrektur

**Version:** v1.0
**Status:** 🟢 Implementierungsreif
**Bezug:** Erweitert `CLAUDE_CODE_ANLEITUNG_HAUSGELD_NEBENBUCH_v1_1.md` und
`IMMOCORE_ClaudeCode_AutoPipeline_Hausgeld_v1_0.md`
**Greenfield-Annahme:** IMMOCORE noch nicht im Produktivbetrieb;
keine Datenmigration alter Korrekturfälle nötig.

---

## 1. Zweck

In der Praxis melden Eigentümer einen Eigentumswechsel **regelmäßig
mit drei oder mehr Monaten Verzögerung** bei Demme. In dieser
Zwischenzeit liefen monatliche Sollstellungen weiterhin auf den
**Voreigentümer**, oft per Dauerauftrag oder Lastschrift auch tatsächlich
bezahlt.

Diese Spec regelt die rückwirkende Korrektur. Sie kombiniert:

- **Sauberkeit gegenüber GoBD:** Original-Sollstellungen werden nicht
  gelöscht oder umdatiert, sondern durch **negative Korrektur-Sollstellungen
  in derselben Periode** neutralisiert
- **Sauberkeit gegenüber der Salden-Historie:** Negative Sollstellung
  liegt zeitlich dort, wo der Wechsel wirtschaftlich war (rückwirkende
  Periode), nicht im Erfassungsmonat
- **Sauberkeit gegenüber dem Neueigentümer:** Neue Sollstellung wird
  mit dem **historischen Hausgeldsatz** der jeweiligen Periode angelegt,
  nicht mit dem aktuellen Satz
- **Sauberkeit gegenüber dem Geldfluss:** Voreigentümer-Zahlungen werden
  per pain.001 zurücküberwiesen (über bestehenden Auszahlungs-Mechanismus
  aus Hausgeld/Nebenbuch-Spec Kap. 10.5); Neueigentümer hat einen offenen
  Saldo, den er begleichen muss

## 2. Architekturprinzipien

| Prinzip | Verhalten |
|---|---|
| Original bleibt unangetastet | Original-Sollstellung des Voreigentümers wird **nicht** storniert (`ist_betrag != 0`), nicht umdatiert, nicht gelöscht. Sie behält ihre OPOS-Nr. und ihren Tilgungs-Status. |
| Korrektur ist eigene Sollstellung | Negativ-Sollstellung mit eigener OPOS-Nr., eigenem Soll-Saldo, eigenem Lebenszyklus |
| Verkettung explizit | Über neue Felder `neutralisiert_durch_opos` (auf Original) und `neutralisiert_opos_nr` (auf Korrektur) ist die Beziehung 1:1 verkettet |
| Historischer Hausgeldsatz | Wird **nicht** aus `HausgeldHistorie` rekonstruiert (zu fehleranfällig), sondern direkt **aus den Splits der Original-Sollstellung** geklont |
| Mahnsperre auf Neutralisierte | Sollstellungen mit `neutralisiert_durch_opos != NULL` werden vom Mahnwesen ignoriert |
| Auszahlung über bestehenden Mechanismus | Die durch Korrektur entstehende Voreigentümer-Habenseite wird mit dem Auszahlungs-Mechanismus aus Kap. 10.5 (pain.001) ausgezahlt — keine neue Mechanik |
| Auto-Pipeline ab Folgemonat | Sobald Wechsel committet, läuft die normale Auto-Pipeline ab Folgemonat auf die neue EV — automatisch, ohne weiteren Eingriff |

## 3. Abgrenzung

### 3.1 Was diese Spec NICHT regelt

- **Vorwärtsgerichtete Eigentümerwechsel** (Wechsel zum 01. des Folgemonats wird vor Stichtag der Auto-Pipeline erfasst) → keine Korrektur nötig, normale EV-Aktivierung
- **Rückwirkende Erfassung in derselben Periode** (Wechsel zum 01.04. wird am 15.04. gemeldet, Auto-Pipeline für 04 ist bereits gelaufen, aber 04 ist noch nicht abgerechnet) → wird mit derselben Mechanik gelöst, aber ohne den Multi-Monats-Aspekt
- **Sonderumlagen, deren Beschluss-Datum vor dem Wechsel lag** → bleiben beim Voreigentümer (gemäß WEG-Reform: Sonderumlagen folgen Beschluss-Stichtag, nicht Wechsel)
- **Abrechnungsergebnisse für Jahre, in denen der Wechsel lag** → werden in der Einzelabrechnung über die EV-Wirksamkeitsperiode automatisch korrekt zugeordnet; separate Spec
- **Wechsel innerhalb einer noch nicht erstellten Abrechnung** vs. **Wechsel in bereits abgerechneter Periode** → siehe Kap. 7

### 3.2 Auslöser

Der Wizard wird **manuell** angestoßen durch Erfassung eines
Eigentümerwechsels mit `wechsel_datum < heute - 30 Tage`. Bei kleineren
Verzögerungen schlägt das System den Standard-Workflow vor (eine
Korrektur-Periode), bei größeren den Multi-Monats-Workflow.

## 4. Datenmodell-Ergänzungen

### 4.1 Erweiterung `HausgeldSollstellung`

| Neues Feld | Typ | Anmerkung |
|---|---|---|
| `sollstellungs_typ` | Enum, Erweiterung | Neuer Wert `korrektur_eigentuemerwechsel` |
| `neutralisiert_durch_opos` | ForeignKey → HausgeldSollstellung, nullable | Auf Original; zeigt auf die Korrektur-Sollstellung |
| `neutralisiert_opos_nr` | ForeignKey → HausgeldSollstellung, nullable | Auf Korrektur; zeigt auf die Original-Sollstellung |
| `wechsel_vorgang` | ForeignKey → EigentuemerwechselVorgang, nullable | Auf Korrektur und neuer Sollstellung; identifiziert den Vorgang |

**Constraint:** Negative Sollstellungen sind ausschließlich vom Typ
`korrektur_eigentuemerwechsel` erlaubt — andere Typen müssen positiv sein.

### 4.2 Neue Tabelle `EigentuemerwechselVorgang`

Ein Eintrag pro rückwirkendem Wechsel-Vorgang. Dient als
Audit-/Wiederholungs-Container.

| Feld | Typ | Anmerkung |
|---|---|---|
| `id` | UUID | |
| `objekt` | FK → Objekt | |
| `einheit` | FK → Einheit | |
| `voreigentuemer_ev` | FK → EigentumsVerhaeltnis | Die alte EV |
| `neueigentuemer_ev` | FK → EigentumsVerhaeltnis | Die neue EV (bei Anlage des Vorgangs erzeugt, falls nicht bereits vorhanden) |
| `wechsel_datum` | DateField | Wirtschaftliches Wechseldatum |
| `meldedatum` | DateField | Tag der Erfassung in IMMOCORE |
| `status` | Enum: `vorschau` / `freigegeben` | Zweistufiger Workflow |
| `erstellt_von` | FK → User | |
| `freigegeben_von` | FK → User, nullable | Constraint `freigegeben_von != erstellt_von` (Vier-Augen) |
| `erstellt_am` | DateTimeField | |
| `freigegeben_am` | DateTimeField, nullable | |
| `auszahlungsbetrag` | DecimalField(14,2) | Berechneter Erstattungsbetrag (Summe gezahlter Voreigentümer-Sollstellungen, neutralisiert) |
| `auszahlungs_iban` | CharField | IBAN des Voreigentümers für Rückerstattung |
| `notiz` | TextField, nullable | Verwalter-Notiz (z.B. „Käufer und Verkäufer regeln untereinander, keine Rückzahlung") |
| `auszahlung_unterdruecken` | Boolean | Default `False`; wenn `True`, wird die Rückzahlung **nicht** initiiert (s. Kap. 7.4) |

### 4.3 Neue Tabelle `WechselKorrekturPaar`

Ein Eintrag pro betroffene Periode. Zeigt klar: „Original X wurde
neutralisiert, Neuanlage Y wurde erzeugt."

| Feld | Typ | Anmerkung |
|---|---|---|
| `id` | UUID | |
| `wechsel_vorgang` | FK → EigentuemerwechselVorgang | |
| `periode` | DateField | Die rückwirkende Periode |
| `original_sollstellung` | FK → HausgeldSollstellung | Voreigentümer, ursprünglich |
| `korrektur_sollstellung` | FK → HausgeldSollstellung | Voreigentümer, negativ |
| `neuanlage_sollstellung` | FK → HausgeldSollstellung | Neueigentümer, positiv |
| `original_ist_betrag_vor_korrektur` | DecimalField(14,2) | Snapshot der Tilgung zum Korrektur-Zeitpunkt |

Read-only nach Erstellung.

## 5. Service-Architektur

### 5.1 Module

```
apps/buchhaltung/services/
└── eigentuemerwechsel_korrektur_service.py    # NEU

apps/buchhaltung/models/
└── eigentuemerwechsel.py                       # NEU
```

### 5.2 Funktionen

| Funktion | Zuständigkeit |
|---|---|
| `vorschau_erstellen(objekt, einheit, wechsel_datum, neueigentuemer_data, user)` | Erzeugt `EigentuemerwechselVorgang(status='vorschau')` + alle `WechselKorrekturPaar`-Einträge **ohne** Sollstellungen anzulegen; nur Beträge berechnen für UI-Anzeige |
| `vorschau_committen(vorgang, freigabe_user, auszahlungs_iban, auszahlung_unterdruecken)` | Vier-Augen-Freigabe; erzeugt die Korrektur- und Neuanlage-Sollstellungen, koppelt sie über die neuen FKs, triggert Auszahlung (wenn aktiv), erzeugt Frontoffice-Aufgabe für Neueigentümer-Forderung |
| `_ermittle_betroffene_perioden(voreigentuemer_ev, wechsel_datum)` | Findet alle committeten Hausgeld-Sollstellungen der Voreigentümer-EV mit `periode >= wechsel_datum` |
| `_klone_splits(original, neue_sollstellung)` | Kopiert `HausgeldSollstellungSplit`-Einträge von Original auf Neuanlage (BA-für-BA, Beträge unverändert) |
| `_negiere_splits(original, korrektur_sollstellung)` | Erzeugt Splits mit negierten Beträgen für Korrektur |
| `_initiiere_rueckzahlung(vorgang)` | Ruft bestehenden Auszahlungslauf-Mechanismus auf (Kap. 10.5) mit Betrag = `auszahlungsbetrag`, IBAN = `auszahlungs_iban` |

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
    Erstellt den Vorgang im Status 'vorschau'. Berechnet alle Beträge
    OHNE persistente Korrektur-/Neuanlage-Sollstellungen anzulegen.
    """

    # 1. Bestehendes (noch aktives) Voreigentümer-EV finden
    voreigentuemer_ev = EigentumsVerhaeltnis.objects.get(
        einheit=einheit,
        aktiv=True,
    )

    # 2. Neueigentümer-EV anlegen oder finden
    neueigentuemer_ev = _erstelle_oder_finde_neueigentuemer_ev(
        einheit=einheit,
        wechsel_datum=wechsel_datum,
        person_data=neueigentuemer_data,
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
        auszahlungsbetrag=Decimal('0.00'),  # Wird unten gefüllt
    )

    # 4. Betroffene Perioden + Beträge berechnen (OHNE Persistenz)
    betroffene_originals = _ermittle_betroffene_perioden(
        voreigentuemer_ev, wechsel_datum
    )

    auszahlungsbetrag = Decimal('0.00')
    for original in betroffene_originals:
        # Vorschau-Berechnung
        auszahlungsbetrag += min(original.ist_betrag, original.soll_betrag)

    vorgang.auszahlungsbetrag = auszahlungsbetrag
    vorgang.save(update_fields=['auszahlungsbetrag'])

    # 5. Vorschau-Daten in WechselKorrekturPaar (ohne Sollstellungs-FKs!)
    # Wird beim Commit ausgefüllt
    for original in betroffene_originals:
        WechselKorrekturPaar.objects.create(
            wechsel_vorgang=vorgang,
            periode=original.periode,
            original_sollstellung=original,
            korrektur_sollstellung=None,  # noch nicht erzeugt
            neuanlage_sollstellung=None,
            original_ist_betrag_vor_korrektur=original.ist_betrag,
        )

    return vorgang
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
    Vier-Augen-Freigabe. Erzeugt die Korrektur- und Neuanlage-Sollstellungen,
    koppelt sie, triggert Auszahlung (wenn aktiv).
    """

    # Vier-Augen
    if freigabe_user.id == vorgang.erstellt_von_id:
        raise ValidationError(
            "Freigabe-User muss von Ersteller verschieden sein"
        )

    if vorgang.status != 'vorschau':
        raise ValidationError(f"Status {vorgang.status} nicht freigabefähig")

    paare = vorgang.korrektur_paare.select_related('original_sollstellung')

    for paar in paare:
        original = paar.original_sollstellung

        # 1. Korrektur-Sollstellung (Voreigentümer, negativ)
        korrektur = HausgeldSollstellung.objects.create(
            objekt=vorgang.objekt,
            eigentumsverhaeltnis=vorgang.voreigentuemer_ev,
            periode=original.periode,
            sollstellungs_typ='korrektur_eigentuemerwechsel',
            soll_betrag=-original.soll_betrag,
            ist_betrag=Decimal('0.00'),  # Wird durch Auszahlung getilgt
            wechsel_vorgang=vorgang,
            neutralisiert_opos_nr=original,
            erstellt_von=freigabe_user,
        )
        # Splits negieren
        _negiere_splits(original, korrektur)

        # Rückverkettung
        original.neutralisiert_durch_opos = korrektur
        original.save(update_fields=['neutralisiert_durch_opos'])

        # 2. Neuanlage-Sollstellung (Neueigentümer, positiv,
        #    Splits geklont aus Original)
        neuanlage = HausgeldSollstellung.objects.create(
            objekt=vorgang.objekt,
            eigentumsverhaeltnis=vorgang.neueigentuemer_ev,
            periode=original.periode,
            sollstellungs_typ='hausgeld',
            soll_betrag=original.soll_betrag,
            ist_betrag=Decimal('0.00'),
            wechsel_vorgang=vorgang,
            erstellt_von=freigabe_user,
        )
        _klone_splits(original, neuanlage)

        # 3. Paar-Verkettung
        paar.korrektur_sollstellung = korrektur
        paar.neuanlage_sollstellung = neuanlage
        paar.save(update_fields=[
            'korrektur_sollstellung', 'neuanlage_sollstellung'
        ])

    # 4. Vorgang freigeben
    vorgang.status = 'freigegeben'
    vorgang.freigegeben_von = freigabe_user
    vorgang.freigegeben_am = timezone.now()
    vorgang.auszahlungs_iban = auszahlungs_iban
    vorgang.auszahlung_unterdruecken = auszahlung_unterdruecken
    vorgang.save()

    # 5. Voreigentümer-EV deaktivieren ab Wechsel-Datum
    vorgang.voreigentuemer_ev.gueltig_bis = vorgang.wechsel_datum - timedelta(days=1)
    vorgang.voreigentuemer_ev.aktiv = False
    vorgang.voreigentuemer_ev.save()

    # 6. Neueigentümer-EV aktivieren
    vorgang.neueigentuemer_ev.aktiv = True
    vorgang.neueigentuemer_ev.save()

    # 7. Auszahlung initiieren (wenn nicht unterdrückt)
    if not auszahlung_unterdruecken and vorgang.auszahlungsbetrag > 0:
        _initiiere_rueckzahlung(vorgang)

    # 8. Frontoffice-Aufgabe für offene Forderung Neueigentümer
    _erzeuge_frontoffice_aufgabe_neueigentuemer(vorgang)

    return vorgang
```

### 6.3 Splits negieren

```python
def _negiere_splits(original, korrektur):
    for s in original.splits.all():
        HausgeldSollstellungSplit.objects.create(
            sollstellung=korrektur,
            buchungsart=s.buchungsart,
            betrag=-s.betrag,
        )
```

### 6.4 Splits klonen

```python
def _klone_splits(original, neuanlage):
    for s in original.splits.all():
        HausgeldSollstellungSplit.objects.create(
            sollstellung=neuanlage,
            buchungsart=s.buchungsart,
            betrag=s.betrag,
        )
```

## 7. Sonderfälle und ihre Auflösung

### 7.1 Voreigentümer hat nicht alles gezahlt

**Konstellation:**
- April und Mai: gezahlt (je 360 €)
- Juni: offen
- Wechsel zum 01.04.

**Verhalten:**
- Original 04: `soll=360, ist=360` → Korrektur 04: `soll=-360, ist=0`
- Original 05: `soll=360, ist=360` → Korrektur 05: `soll=-360, ist=0`
- Original 06: `soll=360, ist=0` → Korrektur 06: `soll=-360, ist=0`

**Saldo Voreigentümer nach Korrektur:**
- 04/05: zwei offene Korrektur-Sollstellungen über je -360 € → Auszahlung 720 €
- 06: Original offen (-360 € Forderung), Korrektur offen (+360 € Verbindlichkeit) → **netto 0**, aber beide OPOS-Nrn. einzeln offen

**Wichtig:** Die offene 06-Original-Sollstellung muss vom Mahnwesen ausgenommen werden — gelöst durch das Feld `neutralisiert_durch_opos`. Die Korrektur-06 darf ebenfalls nicht zur Auszahlung führen, weil sie keine reale Gegenleistung hat. Mechanik:

```python
def auszahlungsbetrag_berechnen(vorgang):
    """
    Auszahlung = Summe der tatsächlich gezahlten Beträge
                der neutralisierten Sollstellungen.
    """
    summe = Decimal('0.00')
    for paar in vorgang.korrektur_paare.all():
        # Nur was wirklich geflossen ist
        summe += paar.original_ist_betrag_vor_korrektur
    return summe
```

### 7.2 Neueigentümer schuldet Geld

Nach Commit hat der Neueigentümer rückwirkende offene Sollstellungen (im Beispiel 1.080 € für 3 Monate). Diese sind normale Hausgeld-Sollstellungen — werden also über die normale Tilgungs-Logik (Dauerauftrag, Lastschrift, Banküberweisung) bezahlt.

**Wichtig — eine Frontoffice-Aufgabe automatisch erzeugen:**

```
„Eigentümerwechsel-Vorgang #12345 freigegeben.
Neueigentümer Müller hat 1.080 € rückwirkende Forderung (3 Monate).
Bitte Saldenmitteilung per Brief versenden und SEPA-Mandat einholen."
```

Diese Aufgabe darf **erst dann automatisch geschlossen werden**, wenn:
- Die rückwirkenden Sollstellungen vollständig getilgt sind, ODER
- Der Verwalter sie manuell als „in Klärung" schließt

### 7.3 Wechsel innerhalb einer bereits abgerechneten Periode

**Konstellation:** Wechsel zum 01.04.2025, gemeldet im Mai 2026, Jahresabrechnung 2025 wurde im März 2026 bereits beschlossen und ausgegangen.

**Problem:** Die Abrechnung wurde dem **Voreigentümer** zugestellt; das Abrechnungsergebnis steht als eigene Sollstellung in seinen Büchern.

**Verhalten dieser Spec:**
- Hausgeld-Sollstellungen für 04-12/2025 und 01-04/2026 werden korrigiert wie oben
- **Das Abrechnungsergebnis 2025 wird NICHT automatisch korrigiert** — es ist eine eigene `Sollstellung(typ='abrechnung')` und gehört in eine separate Spec für Abrechnungs-Korrekturen
- Der Wechsel-Vorgang erzeugt aber eine **Warnung in der UI**:
  „Achtung: Der Wechsel liegt vor dem Abrechnungs-Beschluss-Datum 15.03.2026. Das Abrechnungsergebnis 2025 wurde dem Voreigentümer zugestellt und muss separat behandelt werden."

Damit hat der Verwalter den Hinweis, aber das System macht keine versteckten Korrekturen an Abrechnungen.

### 7.4 Käufer und Verkäufer regeln untereinander

**Konstellation:** Im Notarvertrag wurde geregelt, dass der Käufer dem Verkäufer die bereits gezahlten Hausgelder erstattet. Demme soll **kein Geld zurückzahlen**, nur die Forderungs-Zuordnung korrigieren.

**Verhalten:** Im Commit-Wizard Checkbox „Auszahlung an Voreigentümer unterdrücken" (Default off). Wenn aktiviert:
- `vorgang.auszahlung_unterdruecken = True`
- Korrektur-Sollstellungen werden trotzdem erzeugt (Salden müssen stimmen!)
- Aber: Auszahlungslauf wird **nicht** angestoßen
- Die Korrektur-Sollstellungen bleiben in den Büchern als offene Verbindlichkeit gegenüber dem Voreigentümer, bis sie durch eine manuelle Umbuchung (Verbuchung gegen die Neueigentümer-Forderung) ausgeglichen werden

Der Verwalter erhält eine Frontoffice-Aufgabe:
„Eigentümerwechsel #12345: Auszahlung unterdrückt. Bitte interne Umbuchung Voreigentümer-Guthaben → Neueigentümer-Forderung manuell vornehmen."

### 7.5 Wechsel-Datum nicht am Monatsersten

Ausnahmefall: Wechsel zum 15.04. Hier müsste die April-Sollstellung **anteilig** auf beide Eigentümer verteilt werden.

**Verhalten in v1.0:** Nicht unterstützt. Validierung im Wizard: `wechsel_datum.day == 1` ist Pflicht. Wenn nicht am Monatsersten, weist die UI darauf hin und fordert vom Verwalter eine taggenaue Lösung außerhalb dieser Spec (manuelle Sollstellung-Splits über das normale Buchen-Modul).

**Begründung:** WEG-rechtlich ist der monatsgenaue Wechsel sowieso üblich (Beschluss „mit Wirkung zum Beginn des Folgemonats"); taggenaue Wechsel sind absolute Ausnahme.

## 8. Auto-Pipeline-Verhalten ab Freigabe

Sobald der Vorgang den Status `freigegeben` hat:
- `voreigentuemer_ev.aktiv = False` (ab Wechsel-Datum)
- `neueigentuemer_ev.aktiv = True`

Die **bestehende Auto-Pipeline** (`task_auto_hausgeld_pipeline`) erzeugt
für den nächsten Stichtag automatisch die Sollstellung auf den
Neueigentümer — **keine Änderung an der Auto-Pipeline-Spec nötig**, weil
sie sowieso über die aktive EV iteriert.

## 9. Mahnwesen-Integration

Die zukünftige Mahn-Spec muss bei der Selektion der zu mahnenden
Sollstellungen folgende Filter setzen:

```python
mahnbare_sollstellungen = HausgeldSollstellung.objects.filter(
    soll_betrag__gt=models.F('ist_betrag'),
).filter(
    neutralisiert_durch_opos__isnull=True,  # Original-Sollstellungen,
                                            # die neutralisiert wurden,
                                            # nicht mahnen
).exclude(
    sollstellungs_typ='korrektur_eigentuemerwechsel',  # Negative
                                                       # Sollstellungen
                                                       # nie mahnen
)
```

Dieser Filter ist eine **Pflicht-Anforderung an die Mahn-Spec**.
Bis die Mahn-Spec existiert, ist der Filter im Mahn-Service-Stub zu
implementieren.

## 10. Tilgungs-Logik und Korrektur-Sollstellungen

Die Korrektur-Sollstellung hat `soll_betrag < 0`. Wenn Geld an den
Voreigentümer zurücküberwiesen wird (per pain.001), kommt diese Buchung
als **Abgang vom Bewirtschaftungskonto** in das System.

**Buchungssatz:**
```
Soll  XXXX  Voreigentümer-OPOS-Konto                  720,00
Haben 18000 Bewirtschaftungskonto                     720,00
```

Die Tilgung wird **auf die Korrektur-Sollstellung** gerichtet (nicht
auf eine separate Sollstellung):
- Vor Auszahlung: Korrektur `soll=-720, ist=0` → Saldo -720 (Verbindlichkeit)
- Nach Auszahlung: Korrektur `soll=-720, ist=-720` → Saldo 0

**Wichtig:** Die `ist_betrag`-Logik muss vorzeichenrichtig sein —
negative `ist_betrag` bei negativen `soll_betrag`. Im Service:

```python
def tilge_korrektur(korrektur_sollstellung, betrag):
    # Betrag kommt als positiver Wert (720 €)
    # Da soll_betrag negativ ist, muss ist_betrag auch negativ werden
    if korrektur_sollstellung.soll_betrag < 0:
        korrektur_sollstellung.ist_betrag -= betrag
    else:
        korrektur_sollstellung.ist_betrag += betrag
    korrektur_sollstellung.save()
```

## 11. UI-Anforderungen

### 11.1 Eigentümerwechsel-Wizard `/objekte/{id}/eigentuemerwechsel/neu/`

**Schritt 1 — Stammdaten:**
- Einheit auswählen
- Wechsel-Datum (Validierung: muss Monatsletzter+1 sein)
- Neueigentümer: Person auswählen oder neu anlegen
- IBAN des Voreigentümers für Rückerstattung

**Schritt 2 — Vorschau:**
- Tabelle aller betroffenen Perioden mit:
  - Periode
  - Original-Sollstellung (OPOS-Nr., Soll, Ist)
  - Geplante Korrektur (negative Sollstellung)
  - Geplante Neuanlage (positive Sollstellung auf Neueigentümer)
- Summenzeile:
  - Rückerstattung an Voreigentümer
  - Forderung an Neueigentümer
- Checkbox „Auszahlung an Voreigentümer unterdrücken (regeln Käufer/Verkäufer selbst)"
- Bei abgerechneten Perioden im Wechsel-Bereich: **gelbe Warnbox**

**Schritt 3 — Freigabe (Vier-Augen):**
- Zweiter User loggt sich ein (oder gleicher Browser mit zweitem Account)
- Button „Vorgang freigeben und Sollstellungen erzeugen"
- Constraint `freigabe_user != erstellt_von` erzwungen

### 11.2 Vorgangs-Detail `/eigentuemerwechsel/{vorgang_id}/`

Read-only-Ansicht nach Freigabe. Zeigt:
- Alle `WechselKorrekturPaar`-Einträge mit Sollstellungs-Verlinkung
- Status der Auszahlung (initiiert / abgeschlossen)
- Status der Neueigentümer-Frontoffice-Aufgabe

## 12. Akzeptanzkriterien (Smoke-Test)

1. **Standardfall, alle gezahlt:** 3 Monate rückwirkend, alle gezahlt → 3 Korrektur-Sollstellungen erzeugt, 3 Neuanlagen, Auszahlung 1.080 € initiiert, Frontoffice-Aufgabe „Neueigentümer 1.080 €" angelegt.
2. **Vier-Augen-Constraint:** Versuch, mit gleichem User freizugeben → ValidationError.
3. **Teilzahlung Voreigentümer:** 3 Monate, nur 2 gezahlt → Auszahlung 720 €. Der dritte Monat: Original bleibt offen, Korrektur bleibt offen, beide vom Mahnwesen ausgenommen.
4. **Wechsel-Datum nicht am Monatsersten:** Validierung schlägt fehl.
5. **Auszahlung unterdrückt:** Checkbox aktiv → keine pain.001, aber Frontoffice-Aufgabe „interne Umbuchung manuell" erzeugt.
6. **Wechsel in abgerechneter Periode:** Warnbox erscheint; Abrechnungs-Sollstellung des Voreigentümers wird **nicht** angefasst.
7. **Auto-Pipeline-Folgeverhalten:** Am Stichtag nach Freigabe läuft die Auto-Pipeline auf den Neueigentümer, nicht auf den Voreigentümer.
8. **Tilgungs-Vorzeichen:** Eingehende Rückzahlung-Buchung tilgt die Korrektur-Sollstellung im negativen `ist_betrag` korrekt.
9. **Mahn-Filter:** Suche nach mahnbaren Sollstellungen schließt neutralisierte korrekt aus.
10. **Audit-Sichtbarkeit:** Vorgangs-Detail-Seite zeigt alle drei Sollstellungen pro Periode mit Verlinkung.

## 13. Aufgaben für Claude Code

> **Hinweis:** Phase B erst beginnen, wenn Phase A komplett ist und
> Patrik die Smoke-Tests 1, 2, 3 manuell bestätigt hat.

### Phase A — Backend

**A1: Modell-Migrationen**
- `HausgeldSollstellung`: neue Felder `neutralisiert_durch_opos`, `neutralisiert_opos_nr`, `wechsel_vorgang`; Enum-Wert `korrektur_eigentuemerwechsel`; CheckConstraint negative Beträge nur für diesen Typ
- `EigentuemerwechselVorgang` neu
- `WechselKorrekturPaar` neu

**A2: Service `eigentuemerwechsel_korrektur_service.py`**
- Funktionen aus Kap. 5.2 und Kap. 6
- Vier-Augen-Validierung
- Splits-Klonen und -Negieren als private Helfer

**A3: Erweiterung Tilgungs-Service**
- `tilge_korrektur` mit Vorzeichen-Logik (Kap. 10)
- Tilgungs-Prioritäten unverändert, aber Negativ-Sollstellungen separat behandeln

**A4: Auszahlungs-Integration**
- Bestehenden Auszahlungs-Mechanismus aus Hausgeld/Nebenbuch-Spec Kap. 10.5 aufrufen
- Auszahlungsbetrag = berechnet gemäß Kap. 7.1

**A5: Mahn-Service-Stub erweitern**
- Filter aus Kap. 9 anwenden

**A6: Tests Phase A**
- Unit-Tests für alle Sonderfälle aus Kap. 7
- Integration-Test: vollständiger Wechsel-Vorgang mit Mock-Auszahlung

🛑 **HARTER STOPP nach Phase A.**

### Phase B — UI

**B1: Wizard nach Kap. 11.1** (3 Schritte)
**B2: Vorgangs-Detail nach Kap. 11.2**
**B3: Verlinkung im Objekt-Detail** („Eigentümerwechsel" als Tab)

### Phase C — Verifikation

**C1:** Smoke-Tests 1–10 aus Kap. 12.

---

**Ende der Spezifikation.**
