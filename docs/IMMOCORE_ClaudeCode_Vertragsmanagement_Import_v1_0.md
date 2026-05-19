# IMMOCORE — Vertragsmanagement-Import mit Hausgeld-/Rücklagen-Historie

**Claude Code Implementierungsprompt**
**Version:** 1.0
**Stand:** Mai 2026
**Auftraggeber:** Demme Immobilien Verwaltung GmbH, Coventrystraße 32, 65934 Frankfurt am Main
**KI-Modell:** claude-sonnet-4-6
**Bezug:**
- `IMMOCORE_Ausgangsspezifikation_v1.1.docx`, Kap. 4.6–4.8 (EigentumsVerhältnis, HausgeldHistorie, Personenkonto)
- `IMMOCORE_ClaudeCode_WEG_Objektanlage_v1.2.docx`, Schritt 7 (Verträge im Wizard)
- `IMMOCORE_ClaudeCode_Wirtschaftsjahre_v1_0.md` (Wirtschaftsjahr-Modell)
- `Abrechnungsarten.xlsx`, `Musterkontenrahmen_WEG.xlsx`

---

## 1. Zweck dieses Dokuments

Das aktuelle Vertragsmanagement importiert Hausgeld- und Rücklagenbeträge je Eigentumsverhältnis als **Einzelwert** und überschreibt bestehende Werte. Das ist fachlich nicht korrekt:

1. **Hausgeld und Rücklagen ändern sich jährlich** durch den Wirtschaftsplan. Frühere Werte müssen lesbar bleiben — nicht nur für die Jahresabrechnung des laufenden Jahres, sondern auch für historische Abrechnungen, Salden­ermittlung und Eigentümerwechsel-Abgrenzungen.
2. **Es muss jederzeit erkennbar sein, welcher Wert aktuell gilt** — und ab wann ein neu beschlossener Wert greift (Folgejahresplan kann bereits beschlossen sein, während das laufende Jahr noch läuft).
3. **Ein Wirtschaftsplan kann selektiv ändern** — z.B. nur Hausgeld `.900`, ohne Rücklage `.911` anzufassen. Der Import muss das je Abrechnungsart einzeln behandeln.
4. **Re-Import muss idempotent gegenüber bestehenden Daten sein:** Eine bereits importierte Hausgeld-Position für `(Vertrag, Abrechnungsart, gueltig_ab)` darf nicht dupliziert, eine neue Position mit anderem `gueltig_ab` muss zusätzlich angelegt werden.

Diese Spezifikation beschreibt das überarbeitete Datenmodell, das CSV-Format und die Import-Logik. Die Spezifikation ersetzt die Hausgeld-Behandlung in `WEG_Objektanlage v1.2` Schritt 7 und ergänzt sie um einen wiederverwendbaren CSV-Import.

> **Kritisches Designprinzip:** `HausgeldHistorie` ist die einzige Quelle der Wahrheit für Soll-Beträge. Es gibt **kein** Feld `hausgeld_aktuell` am `EigentumsVerhältnis` und auch keinen materialisierten Aktiv-Eintrag. Der aktuell gültige Wert wird zur Laufzeit aus der Historie abgeleitet (siehe Kap. 3.2).

---

## 2. Fachliche Anforderungen

### 2.1 Was muss erkennbar sein

| Anforderung | Umsetzung |
|---|---|
| Welcher Hausgeld-Betrag gilt **heute** je Vertrag und Abrechnungsart? | Funktion `hausgeld_aktuell(vertrag, abr_art, stichtag=heute)` |
| Welcher Betrag galt zu einem **beliebigen Stichtag** in der Vergangenheit? | Gleiche Funktion mit `stichtag=...` |
| Welcher Betrag gilt **ab Folgejahr**, weil der Plan bereits beschlossen wurde? | Eintrag mit `gueltig_ab > heute` ist sichtbar, wird aber erst aktiv |
| Welche Wirtschaftspläne haben den Betrag verändert? | Feld `wirtschaftsplan_jahr` je Eintrag |
| Hat sich nur Hausgeld `.900`, oder auch eine Rücklage geändert? | Historie wird je `(vertrag, abrechnungsart)` separat geführt |
| Ist eine Rücklage 2 nachträglich hinzugefügt worden? | Erster Eintrag für `.912` mit `gueltig_ab` = Beschlussdatum |

### 2.2 Beispiel-Szenario

WEG mit 1 Rücklage. Eigentümer Müller, Einheit WE01, Verwaltung übernommen 01.01.2023.

| Ereignis | gueltig_ab | abr_art | betrag | wirtschaftsplan_jahr |
|---|---|---|---|---|
| Erstanlage Vertrag (Wizard 2023) | 2023-01-01 | 900 | 250,00 | 2023 |
| Erstanlage Vertrag (Wizard 2023) | 2023-01-01 | 911 | 50,00 | 2023 |
| WP 2024 beschlossen am 15.11.2023 | 2024-01-01 | 900 | 280,00 | 2024 |
| WP 2024 beschlossen am 15.11.2023 | 2024-01-01 | 911 | 60,00 | 2024 |
| WP 2025 beschlossen 20.10.2024, **nur Hausgeld** ändert sich | 2025-01-01 | 900 | 295,00 | 2025 |

Stand 08.05.2026, Abfrage `hausgeld_aktuell(vertrag_mueller_we01, '900', 2026-05-08)`:
- Antwort: `295,00` (letzter Eintrag mit `gueltig_ab <= 2026-05-08` für `abr_art='900'`)

Stand 08.05.2026, Abfrage `hausgeld_aktuell(vertrag_mueller_we01, '911', 2026-05-08)`:
- Antwort: `60,00` (kein neuer Eintrag in 2025; letzter gültiger Wert ist aus WP 2024)

Die UI zeigt im Vertragsdetail eine **Tabelle pro Abrechnungsart** mit chronologischer Historie und einer eindeutigen Markierung des heute aktiven Eintrags.

### 2.3 Was passiert bei Eigentümerwechsel

Eigentümerwechsel beendet das `EigentumsVerhältnis` (Setzen von `ende`). Das Personenkonto wird archiviert. Die Historie des alten Vertrags bleibt unangetastet — sie wird für rückwirkende Abrechnungen weiter benötigt.

Der neue Eigentümer erhält ein **neues** `EigentumsVerhältnis` mit eigener Historie. Der erste Historieneintrag des neuen Vertrags hat typischerweise `gueltig_ab = beginn_neuer_vertrag` und übernimmt die letzten Werte des Vorgängers (Default-Vorbelegung im Wizard, kein Automatismus). Es ist explizit gewollt, dass die beiden Historien **getrennt** geführt werden.

---

## 3. Datenmodell-Änderungen

### 3.1 Bestehendes Modell (Ist-Zustand laut Ausgangsspezifikation v1.1)

```python
# core/models/vertrag.py
class EigentumsVerhaeltnis(models.Model):
    einheit = models.ForeignKey(Einheit, on_delete=models.PROTECT)
    person = models.ForeignKey(Person, on_delete=models.PROTECT)
    beginn = models.DateField()
    ende = models.DateField(null=True, blank=True)
    # ...
    # hausgeld_soll als Property — berechnet aus HausgeldHistorie

class HausgeldHistorie(models.Model):
    eigentumsverhaeltnis = models.ForeignKey(EigentumsVerhaeltnis, on_delete=models.CASCADE)
    betrag = models.DecimalField(max_digits=10, decimal_places=2)
    gueltig_ab = models.DateField()
    erstellt_von = models.ForeignKey(User, on_delete=models.PROTECT)
```

**Probleme:**
- Kein Feld für die Abrechnungsart — Historie behandelt nur einen Gesamtbetrag, nicht aufgeschlüsselt nach `.900 / .911 / .912 / …`.
- Kein Feld für den Wirtschaftsplan-Bezug — die fachliche Begründung der Änderung ist nicht im Datensatz hinterlegt.
- Keine Unique-Bedingung — derselbe Eintrag kann mehrfach angelegt werden (Re-Import-Problem).

### 3.2 Neues Modell

```python
# core/models/vertrag.py

class EigentumsVerhaeltnis(models.Model):
    """
    Verbindet Person und Einheit. Pro aktivem Vertrag genau ein Personenkonto.
    KEINE direkten Hausgeld-Felder mehr — alles in HausgeldHistorie.
    """
    einheit = models.ForeignKey(Einheit, on_delete=models.PROTECT, related_name='vertraege')
    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name='vertraege')
    beginn = models.DateField()
    ende = models.DateField(null=True, blank=True,
                            help_text="Null = aktuell aktiv")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['einheit'],
                condition=Q(ende__isnull=True),
                name='uniq_aktiver_vertrag_je_einheit',
            ),
        ]

    def hausgeld_aktuell(self, abrechnungsart_code: str, stichtag: date | None = None) -> Decimal:
        """
        Liefert den am `stichtag` (Default: heute) gueltigen Soll-Betrag fuer
        die uebergebene Abrechnungsart. Letzter Eintrag mit gueltig_ab <= stichtag.

        Wirft `HausgeldHistorie.DoesNotExist`, wenn fuer Vertrag + Abrechnungsart
        zum Stichtag noch kein Eintrag existiert (z.B. Rueckfrage vor Vertragsbeginn).
        """
        stichtag = stichtag or timezone.now().date()
        return (HausgeldHistorie.objects
                .filter(eigentumsverhaeltnis=self,
                        abrechnungsart__code=abrechnungsart_code,
                        gueltig_ab__lte=stichtag)
                .order_by('-gueltig_ab', '-erstellt_am')
                .values_list('betrag', flat=True)
                .first())

    def hausgeld_alle_aktuell(self, stichtag: date | None = None) -> dict[str, Decimal]:
        """
        Liefert ein Dict { abr_code: betrag } mit dem aktuell gueltigen Wert
        je Abrechnungsart, fuer die ueberhaupt eine Historie existiert.
        """
        stichtag = stichtag or timezone.now().date()
        rows = (HausgeldHistorie.objects
                .filter(eigentumsverhaeltnis=self, gueltig_ab__lte=stichtag)
                .order_by('abrechnungsart__code', '-gueltig_ab', '-erstellt_am')
                .distinct('abrechnungsart__code')
                .values_list('abrechnungsart__code', 'betrag'))
        return dict(rows)


class HausgeldHistorie(models.Model):
    """
    Historisiert das Hausgeld-Soll je Vertrag UND Abrechnungsart.
    Mehrere Eintraege je Vertrag erlaubt — einer je (abrechnungsart, gueltig_ab).
    Aktueller Wert wird zur Laufzeit aus der Tabelle abgeleitet.
    """
    eigentumsverhaeltnis = models.ForeignKey(
        EigentumsVerhaeltnis,
        on_delete=models.CASCADE,
        related_name='hausgeld_eintraege',
    )
    abrechnungsart = models.ForeignKey(
        'Abrechnungsart',
        on_delete=models.PROTECT,
        related_name='hausgeld_eintraege',
        help_text="z.B. 900, 911, 912, 940",
    )
    betrag = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Monatliches Soll in EUR. 0,00 ist erlaubt (z.B. ausgesetzte Sonderumlage).",
    )
    gueltig_ab = models.DateField(
        help_text="Datum, ab dem dieser Betrag gilt. Typisch der 1. eines Monats.",
    )
    wirtschaftsplan_jahr = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Wirtschaftsplan-Jahr, das diese Aenderung ausgeloest hat. "
                  "Nullable fuer Erstanlage und Eigentuemerwechsel.",
    )
    quelle = models.CharField(
        max_length=20,
        choices=[
            ('wizard', 'Wizard'),
            ('csv_import', 'CSV-Import'),
            ('massenimport', 'Massenimport'),
            ('manuell', 'Manuelle Pflege'),
            ('eigentuemerwechsel', 'Eigentuemerwechsel'),
        ],
        default='manuell',
    )
    bemerkung = models.CharField(max_length=200, blank=True)
    erstellt_von = models.ForeignKey(User, on_delete=models.PROTECT)
    erstellt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['eigentumsverhaeltnis', 'abrechnungsart', 'gueltig_ab'],
                name='uniq_historie_je_vertrag_abrart_datum',
            ),
        ]
        indexes = [
            models.Index(fields=['eigentumsverhaeltnis', 'abrechnungsart', '-gueltig_ab']),
        ]
        ordering = ['eigentumsverhaeltnis', 'abrechnungsart', '-gueltig_ab']
```

> **Kein `aktiv`-Flag.** Welcher Eintrag aktiv ist, ergibt sich ausschließlich aus `gueltig_ab` und dem Abfrage-Stichtag. Das vermeidet Inkonsistenzen (zwei Eintraege gleichzeitig aktiv markiert) und macht den Re-Import unkompliziert.

> **Unique-Constraint** verhindert Duplikate beim Re-Import. Der gleiche Eintrag (gleicher Vertrag, gleiche Abrechnungsart, gleiches `gueltig_ab`) darf nur einmal existieren. Ein zweiter Import mit anderem `gueltig_ab` ist erlaubt und wird zusaetzlich angelegt.

### 3.3 Migration vom Bestand

Die bisherige `HausgeldHistorie` enthält Eintraege ohne Abrechnungsart-Bezug. Diese werden in der Migration gegen die Standard-Abrechnungsart `900` (Hausgeld) gemappt. Falls `wirtschaftsplan_jahr` aus dem Datum rekonstruierbar ist (`gueltig_ab` ist ein 1.1.JJJJ), wird `JJJJ` eingetragen, sonst `NULL`.

```python
# migrations/00XX_hausgeldhistorie_abrart_wp.py

def migrate_forward(apps, schema_editor):
    HausgeldHistorie = apps.get_model('core', 'HausgeldHistorie')
    Abrechnungsart = apps.get_model('core', 'Abrechnungsart')

    for h in HausgeldHistorie.objects.all():
        objekt = h.eigentumsverhaeltnis.einheit.objekt
        ar_900, _ = Abrechnungsart.objects.get_or_create(
            objekt=objekt, code='900',
            defaults={'bezeichnung': 'Hausgeld'},
        )
        h.abrechnungsart = ar_900
        h.quelle = 'manuell'
        if h.gueltig_ab.month == 1 and h.gueltig_ab.day == 1:
            h.wirtschaftsplan_jahr = h.gueltig_ab.year
        h.save(update_fields=['abrechnungsart', 'quelle', 'wirtschaftsplan_jahr'])
```

Vor Anlage des Unique-Constraints muss eine Daten-Validierungsmigration prüfen, ob doppelte Eintraege existieren und diese bereinigen — Default-Strategie: ältesten Eintrag behalten, Konflikte als Issue für manuelle Klärung loggen.

---

## 4. CSV-Import-Format

Der Vertragsmanagement-Import wird als eigenständiger CSV-Import realisiert — analog zu Einheiten- und Eigentümer-Import in `WEG_Objektanlage v1.2`. Er kann an zwei Stellen aufgerufen werden:

1. **Wizard Schritt 7** (WEG-Objektanlage) — Erstanlage aller Verträge eines Objekts.
2. **Objekt-Detailseite → Tab "Verträge" → Button "CSV-Import"** — laufende Pflege (neue Wirtschaftsplan-Werte, neue Rücklage-Beträge etc.).

### 4.1 Dateiname und Encoding

```
Dateiname:    IMMOCORE_Vertragsmanagement_Vorlage.csv
Encoding:     UTF-8 mit BOM (Excel-kompatibel)
Trennzeichen: Semikolon
Zeilenende:   CRLF
```

### 4.2 Spalten

| Spalte | Feldname | Pflicht | Beschreibung |
|---|---|---|---|
| A | `einheit_nr` | Ja | Einheitennummer (z.B. `WE01`, `G01`, `S01`). Muss im Objekt existieren. |
| B | `eigentuemer_email` | Bedingt | E-Mail des Eigentuemers. Pflicht bei neuem Vertrag. Bei bestehendem Vertrag kann leer bleiben — System ordnet ueber `einheit_nr` zu. |
| C | `vertrag_beginn` | Ja | Format `YYYY-MM-DD`. Beginn des Eigentumsverhaeltnisses. Muss bei wiederholtem Import identisch zum bestehenden Vertrag sein. |
| D | `vertrag_ende` | Optional | Format `YYYY-MM-DD`. Leer = aktuell aktiv. Wird nur bei Beendigung gesetzt — nicht durch normalen Re-Import. |
| E | `abrechnungsart` | Ja | Code der Abrechnungsart: `900`, `911`, `912`, … `931`, `940`. Muss am Objekt existieren. |
| F | `betrag` | Ja | Monatliches Soll in EUR. Dezimalpunkt oder -komma. Mindestens `0.00`. |
| G | `gueltig_ab` | Ja | Format `YYYY-MM-DD`. Datum, ab dem der Betrag gilt. Muss `>= vertrag_beginn` sein. |
| H | `wirtschaftsplan_jahr` | Optional | 4-stellig (z.B. `2025`). Bei Erstanlage typisch leer; bei jaehrlichem Update Pflicht-Empfehlung. |
| I | `bemerkung` | Optional | Freitext bis 200 Zeichen. |

### 4.3 Beispieldatei

Drei Einheiten, eine Rücklage. Erstanlage 2023, Wirtschaftsplan-Update 2024, Wirtschaftsplan-Update 2025 (nur Hausgeld).

```csv
einheit_nr;eigentuemer_email;vertrag_beginn;vertrag_ende;abrechnungsart;betrag;gueltig_ab;wirtschaftsplan_jahr;bemerkung
WE01;mueller@example.de;2023-01-01;;900;250.00;2023-01-01;2023;Erstanlage
WE01;mueller@example.de;2023-01-01;;911;50.00;2023-01-01;2023;Erstanlage Ruecklage
WE01;mueller@example.de;2023-01-01;;900;280.00;2024-01-01;2024;WP 2024 vom 15.11.2023
WE01;mueller@example.de;2023-01-01;;911;60.00;2024-01-01;2024;WP 2024
WE01;mueller@example.de;2023-01-01;;900;295.00;2025-01-01;2025;WP 2025 nur Hausgeld
WE02;schmidt@example.de;2023-01-01;;900;220.00;2023-01-01;2023;
WE02;schmidt@example.de;2023-01-01;;911;45.00;2023-01-01;2023;
WE02;schmidt@example.de;2023-01-01;;900;245.00;2024-01-01;2024;
WE02;schmidt@example.de;2023-01-01;;911;55.00;2024-01-01;2024;
WE02;schmidt@example.de;2023-01-01;;900;260.00;2025-01-01;2025;
G01;muster-gmbh@example.de;2023-01-01;;900;480.00;2023-01-01;2023;
G01;muster-gmbh@example.de;2023-01-01;;911;90.00;2023-01-01;2023;
G01;muster-gmbh@example.de;2023-01-01;;900;510.00;2024-01-01;2024;
G01;muster-gmbh@example.de;2023-01-01;;911;105.00;2024-01-01;2024;
G01;muster-gmbh@example.de;2023-01-01;;900;540.00;2025-01-01;2025;
```

### 4.4 Was die Datei NICHT enthaelt

- Keine Stammdaten der Person (Name, IBAN, Adresse). Diese werden im Eigentümer-CSV gepflegt. Die Verknüpfung läuft über `eigentuemer_email`.
- Keine `.910`-Spalte. Suffix `.910` ist permanent gesperrt (siehe `WEG_Objektanlage v1.2`).
- Keine Aktiv-/Inaktiv-Markierung. Aktivierung ergibt sich aus `gueltig_ab` und dem Stichtag der Abfrage.

---

## 5. Import-Logik

### 5.1 Drei-Stufen-Ablauf

Wie beim Massenimport WEG (`Massenimport_v1.0`):

| Stufe | Endpunkt | Verhalten |
|---|---|---|
| 1. Vorlage holen | `GET /api/v1/objekte/{id}/vertraege/csv-vorlage/` | Server-seitig generiert; Einheiten und Abrechnungsarten des Objekts vorbelegt |
| 2. Preview | `POST /api/v1/objekte/{id}/vertraege/csv-preview/` | Datei hochladen, parsen, validieren, Vorschau-JSON. **Keine DB-Änderung.** |
| 3. Commit | `POST /api/v1/objekte/{id}/vertraege/csv-commit/` | Vorschau-Token bestätigen → atomare Anlage |

### 5.2 Schritt-für-Schritt-Logik je Zeile

```python
# services/vertragsimport.py

def importiere_zeile(zeile: dict, objekt: Objekt, user: User) -> ZeilenErgebnis:
    """
    Verarbeitet eine CSV-Zeile. Wird innerhalb einer transaction.atomic()
    aufgerufen. Wirft Exception bei Validierungsfehler — Caller fasst alle
    Zeilen einer Datei in einer atomic()-Klammer zusammen.
    """
    # 1. Einheit aufloesen
    try:
        einheit = Einheit.objects.get(objekt=objekt, einheit_nr=zeile['einheit_nr'])
    except Einheit.DoesNotExist:
        raise FachlicherFehler(
            f"Einheit '{zeile['einheit_nr']}' im Objekt {objekt.bezeichnung} nicht gefunden"
        )

    # 2. Abrechnungsart aufloesen
    try:
        abr_art = Abrechnungsart.objects.get(objekt=objekt, code=zeile['abrechnungsart'])
    except Abrechnungsart.DoesNotExist:
        raise FachlicherFehler(
            f"Abrechnungsart '{zeile['abrechnungsart']}' im Objekt nicht definiert"
        )

    # 3. Vertrag aufloesen oder anlegen
    vertrag = _vertrag_aufloesen(einheit, zeile, user)

    # 4. Historieneintrag idempotent anlegen
    historie, created = HausgeldHistorie.objects.update_or_create(
        eigentumsverhaeltnis=vertrag,
        abrechnungsart=abr_art,
        gueltig_ab=date.fromisoformat(zeile['gueltig_ab']),
        defaults={
            'betrag': Decimal(zeile['betrag'].replace(',', '.')),
            'wirtschaftsplan_jahr': int(zeile['wirtschaftsplan_jahr']) if zeile.get('wirtschaftsplan_jahr') else None,
            'bemerkung': zeile.get('bemerkung', ''),
            'quelle': 'csv_import',
            'erstellt_von': user,
        },
    )

    return ZeilenErgebnis(
        einheit_nr=zeile['einheit_nr'],
        abr_code=zeile['abrechnungsart'],
        gueltig_ab=zeile['gueltig_ab'],
        aktion='created' if created else 'updated',
        historie_id=historie.id,
    )


def _vertrag_aufloesen(einheit: Einheit, zeile: dict, user: User) -> EigentumsVerhaeltnis:
    """
    Sucht aktiven Vertrag fuer Einheit. Bei Erstanlage wird Person ueber
    eigentuemer_email aufgeloest und Vertrag angelegt.
    """
    beginn = date.fromisoformat(zeile['vertrag_beginn'])
    ende = date.fromisoformat(zeile['vertrag_ende']) if zeile.get('vertrag_ende') else None

    # Aktiver Vertrag (ende=None) hat Vorrang
    aktiver = EigentumsVerhaeltnis.objects.filter(einheit=einheit, ende__isnull=True).first()

    if aktiver and aktiver.beginn == beginn:
        # Bestehender Vertrag, idempotenter Re-Import
        return aktiver

    if aktiver and aktiver.beginn != beginn:
        raise FachlicherFehler(
            f"Aktiver Vertrag fuer {einheit.einheit_nr} hat Beginn {aktiver.beginn}, "
            f"CSV liefert {beginn}. Eigentuemerwechsel ueber dedizierten Wizard durchfuehren."
        )

    # Kein aktiver Vertrag — Person + neuen Vertrag anlegen
    if not zeile.get('eigentuemer_email'):
        raise FachlicherFehler(
            f"Einheit {einheit.einheit_nr}: kein aktiver Vertrag, "
            f"eigentuemer_email ist Pflicht fuer Neuanlage"
        )

    try:
        person = Person.objects.get(email=zeile['eigentuemer_email'])
    except Person.DoesNotExist:
        raise FachlicherFehler(
            f"Person mit E-Mail '{zeile['eigentuemer_email']}' nicht in Stammdaten. "
            f"Bitte zuerst Eigentuemer-Import durchfuehren."
        )

    return EigentumsVerhaeltnis.objects.create(
        einheit=einheit,
        person=person,
        beginn=beginn,
        ende=ende,
    )
```

### 5.3 Atomarität

Eine CSV-Datei wird in **einer** `transaction.atomic()`-Klammer verarbeitet. Bei Fehler in einer Zeile rollt der gesamte Import zurück. Keine Partial-Imports — der Nutzer korrigiert die Datei und lädt erneut hoch.

> **Begruendung:** Vertragsdaten sind eng verknuepft. Halb importierte Wirtschaftsplaene fuehren zu inkonsistenten Salden in Folgeprozessen (Sollstellung, Jahresabrechnung). Vollstaendiger Rollback ist hier korrekter als Partial-Commit.

```python
def commit(datei: UploadedFile, objekt: Objekt, user: User) -> ImportErgebnis:
    zeilen = list(parse_csv(datei))  # Validiert Schema, Encoding, Pflichtfelder
    ergebnisse = []
    try:
        with transaction.atomic():
            for zeile in zeilen:
                ergebnisse.append(importiere_zeile(zeile, objekt, user))
    except FachlicherFehler as e:
        return ImportErgebnis(status='fehler', meldung=str(e), ergebnisse=[])
    return ImportErgebnis(status='ok', meldung=None, ergebnisse=ergebnisse)
```

### 5.4 Idempotenz im Detail

`update_or_create` mit dem Lookup `(eigentumsverhaeltnis, abrechnungsart, gueltig_ab)` sorgt dafuer, dass:

| Szenario | Verhalten |
|---|---|
| Datei zum ersten Mal importiert | Alle Zeilen `created` |
| Identische Datei nochmal importiert | Alle Zeilen `updated` mit gleichen Werten — keine Aenderung am Datensatz, aber `erstellt_am` aktualisiert sich nicht (`update_or_create` verwendet `defaults`, das Feld `erstellt_am` ist `auto_now_add=True` und bleibt). **Optional:** Felder `aktualisiert_am` / `aktualisiert_von` ergaenzen, falls Audit erforderlich. |
| Datei mit korrigiertem Betrag fuer bestehende `(vertrag, abr, datum)`-Kombi | Eintrag wird aktualisiert (`updated`) |
| Datei mit neuem `gueltig_ab` fuer denselben Vertrag und dieselbe Abrechnungsart | Neuer Eintrag wird angelegt (`created`) |
| Datei mit neuer Abrechnungsart (z.B. erstmals `.912`) | Neuer Eintrag wird angelegt (`created`) |
| Datei loescht eine Zeile | **Kein Loeschvorgang.** Der Eintrag bleibt bestehen. Loeschungen muessen explizit ueber UI/API erfolgen — der Import ist additiv. |

> **Wichtig:** Der Import _entfernt_ keine bestehenden Historie-Eintraege. Wer einen falschen Eintrag aus der Vergangenheit korrigieren will, muss ihn entweder per UI/API loeschen oder per gleichem `gueltig_ab` ueberschreiben. Das ist Absicht — versehentliches Loeschen historisch belegter Werte durch eine unvollstaendige CSV waere ein Datenintegritaets-Risiko.

---

## 6. Validierung

### 6.1 Schema-Validierung (Stufe 1, sofort nach Upload)

| Schwere | Regel | Verhalten |
|---|---|---|
| Fehler | Datei ist nicht UTF-8 | HTTP 400, Hinweis "Bitte als UTF-8 mit BOM speichern" |
| Fehler | Trennzeichen ist nicht `;` | HTTP 400 |
| Fehler | Spaltenkopf weicht ab | HTTP 400, Liste der unbekannten / fehlenden Spalten |
| Fehler | Datei > 5 MB oder > 10000 Zeilen | HTTP 400 |

### 6.2 Zeilen-Validierung (Stufe 2, im Preview)

| Schwere | Regel | Meldung |
|---|---|---|
| Fehler | `einheit_nr` leer | "Pflichtfeld einheit_nr fehlt" |
| Fehler | `einheit_nr` existiert nicht im Objekt | "Einheit {nr} nicht gefunden" |
| Fehler | `vertrag_beginn` kein gueltiges ISO-Datum | "Datum ungueltig: {wert}" |
| Fehler | `gueltig_ab` < `vertrag_beginn` | "gueltig_ab darf nicht vor Vertragsbeginn liegen" |
| Fehler | `gueltig_ab` > `vertrag_ende` (wenn gesetzt) | "gueltig_ab liegt nach Vertragsende" |
| Fehler | `abrechnungsart` existiert nicht am Objekt | "Abrechnungsart {code} nicht definiert" |
| Fehler | `abrechnungsart` = `910` | "Suffix .910 ist gesperrt" |
| Fehler | `betrag` < 0 | "Betrag muss >= 0 sein" |
| Fehler | `betrag` nicht parsbar | "Betrag ungueltig: {wert}" |
| Fehler | Bei Neuanlage: `eigentuemer_email` leer | "Neuer Vertrag erfordert eigentuemer_email" |
| Fehler | `eigentuemer_email` nicht in Stammdaten | "Person {email} nicht gefunden — Eigentuemer-Import zuerst" |
| Fehler | Aktiver Vertrag existiert mit anderem `vertrag_beginn` | "Vertrag {einheit} hat anderes Beginn-Datum — Eigentuemerwechsel-Wizard nutzen" |
| Fehler | Doppelte Zeile in CSV `(einheit_nr, abrechnungsart, gueltig_ab)` | "Doppelte Zeile fuer {einheit}/{abr}/{datum}" |
| Warnung | `wirtschaftsplan_jahr` leer und `gueltig_ab.month==1, day==1` | "Tipp: WP-Jahr {year} eintragen" |
| Warnung | `wirtschaftsplan_jahr` != `gueltig_ab.year` | "WP-Jahr {wp} weicht von gueltig_ab-Jahr {gj} ab — bitte pruefen" |
| Warnung | `betrag` = 0 fuer Abrechnungsart `900` | "Hausgeld 0,00 — vermutlich Eingabefehler" |
| Warnung | `gueltig_ab` liegt mehr als 2 Jahre in der Zukunft | "Eintrag fuer {datum} weit in der Zukunft — pruefen" |
| Hinweis | Eintrag identisch zu bestehendem Datensatz | "Bestehender Eintrag — keine Aenderung" |

### 6.3 Cross-Row-Validierungen

Werden **nach** der zeilenweisen Pruefung ausgefuehrt:

- **Vollstaendigkeit Abrechnungsart `900` je Vertrag**: Wenn fuer einen Vertrag in der Datei mindestens ein Eintrag existiert, muss auch die Abrechnungsart `900` enthalten sein (Hausgeld ist Pflicht). Schwere: **Warnung**, nicht Fehler — bei laufender Pflege wird ggf. nur eine Ruecklage aktualisiert.
- **Plan-Konsistenz**: Wenn fuer ein `wirtschaftsplan_jahr` einer der Vertraege eine Aenderung importiert wird, sollte das auch fuer die anderen Vertraege gelten. Schwere: **Warnung** — selektive Updates sind erlaubt (z.B. einzelner Eigentuemerwechsel), aber sollten dokumentiert werden.

---

## 7. Vorschau-JSON

### 7.1 Response `csv-preview`

```json
{
  "preview_token": "uuid-30-min-cache-key",
  "objekt": {
    "id": "uuid",
    "bezeichnung": "WEG Mainufer 1-3",
    "objekt_nr": "100001"
  },
  "zusammenfassung": {
    "zeilen_gesamt": 15,
    "zeilen_ok": 14,
    "zeilen_warnung": 1,
    "zeilen_fehler": 0,
    "vertraege_neu": 0,
    "vertraege_bestehend": 3,
    "historie_eintraege_neu": 5,
    "historie_eintraege_aktualisiert": 10,
    "betroffene_abrechnungsarten": ["900", "911"]
  },
  "zeilen": [
    {
      "zeilennummer": 1,
      "einheit_nr": "WE01",
      "abrechnungsart": "900",
      "gueltig_ab": "2023-01-01",
      "betrag": "250.00",
      "wirtschaftsplan_jahr": 2023,
      "aktion": "bestehend_unveraendert",
      "status": "ok",
      "meldungen": []
    },
    {
      "zeilennummer": 5,
      "einheit_nr": "WE01",
      "abrechnungsart": "900",
      "gueltig_ab": "2025-01-01",
      "betrag": "295.00",
      "wirtschaftsplan_jahr": 2025,
      "aktion": "neu",
      "status": "ok",
      "meldungen": []
    }
  ]
}
```

### 7.2 Felder `aktion`

| Wert | Bedeutung |
|---|---|
| `neu` | Eintrag wird neu angelegt |
| `aktualisiert` | Eintrag mit gleichem `(vertrag, abr, datum)` existiert, Betrag/WP-Jahr/Bemerkung aendern sich |
| `bestehend_unveraendert` | Eintrag existiert exakt wie in CSV — kein Schreibvorgang |
| `vertrag_neu` | Vertrag wird neu angelegt (zusammen mit erstem Historieneintrag) |
| `fehler` | Zeile kann nicht importiert werden — Status `fehler` |

---

## 8. UI

### 8.1 CSV-Import-Maske (Wizard Schritt 7 + Objekt-Detail)

Drei Tabs:

1. **Manuell** — bestehende Tabellen-Eingabe wie in `WEG_Objektanlage v1.2` Schritt 7. Pro Einheit eine Zeile, Spalten je Abrechnungsart. Diese Maske erzeugt im Hintergrund Historie-Eintraege mit `gueltig_ab = vertrag_beginn` und `quelle='wizard'`.
2. **CSV-Import** — Vorlage-Download, Datei-Upload, Vorschau-Tabelle, Bestaetigung.
3. **Historie** (nur auf Objekt-Detail) — Zeitstrahl je Vertrag und Abrechnungsart. Tabelle mit:
   - Spalte 1: Vertrag (Einheit + Eigentuemer)
   - Spalte 2: Abrechnungsart
   - Spalte 3: gueltig_ab
   - Spalte 4: Betrag
   - Spalte 5: WP-Jahr
   - Spalte 6: Quelle
   - Spalte 7: Status (`✓ aktiv` / `⏳ kuenftig` / `📜 historisch`)

### 8.2 Anzeige im Vertrags-Detail

```
Vertrag: WE01 — Klaus Mueller (mueller@example.de)
Vertragsbeginn: 01.01.2023
Status: aktiv

Hausgeld (.900)
┌──────────────┬──────────┬──────────┬───────────┐
│ gueltig_ab   │ Betrag   │ WP-Jahr  │ Status    │
├──────────────┼──────────┼──────────┼───────────┤
│ 01.01.2023   │ 250,00 € │ 2023     │ historisch│
│ 01.01.2024   │ 280,00 € │ 2024     │ historisch│
│ 01.01.2025   │ 295,00 € │ 2025     │ ✓ aktiv   │
└──────────────┴──────────┴──────────┴───────────┘

Ruecklage I (.911)
┌──────────────┬──────────┬──────────┬───────────┐
│ gueltig_ab   │ Betrag   │ WP-Jahr  │ Status    │
├──────────────┼──────────┼──────────┼───────────┤
│ 01.01.2023   │ 50,00 €  │ 2023     │ historisch│
│ 01.01.2024   │ 60,00 €  │ 2024     │ ✓ aktiv   │
└──────────────┴──────────┴──────────┴───────────┘

Aktuelles Gesamt-Soll: 355,00 €/Monat (Stand 08.05.2026)
```

### 8.3 Manuelle Pflege

Eintraege werden ueber separate Inline-Aktionen verwaltet — nicht ueber das CSV-Format. Ueberlegungen:

- **Neuer Eintrag**: Modal "Neuer Hausgeld-Eintrag" — Felder: Abrechnungsart, gueltig_ab, betrag, wirtschaftsplan_jahr, bemerkung. Nach Speichern wird die Tabelle neu gerendert.
- **Eintrag korrigieren**: Edit-Icon je Zeile — gleiches Modal, vorbelegt. Nur erlaubt fuer Eintraege mit `quelle='manuell'` oder fuer den letzten Eintrag — frühere Eintraege sind nur loeschbar, nicht editierbar (Audit-Trail).
- **Eintrag loeschen**: Loesch-Icon — Bestaetigungsdialog, soft delete (Feld `geloescht_am`/`geloescht_von` ergaenzen, falls Loeschungen nachweisbar sein muessen — sonst hard delete). **Default-Empfehlung:** soft delete, denn fuer GoBD-Konformitaet wird Nachvollziehbarkeit benoetigt.

> **Hinweis:** Soft-Delete fuer `HausgeldHistorie` wurde in dieser Spec **nicht** modelliert. Falls erforderlich, ist ein eigener Spec-Punkt sinnvoll. Default: harte Loeschung, aber Audit-Log ueber `django-auditlog` o.ae.

---

## 9. Endpunkte

| Methode | Pfad | Beschreibung |
|---|---|---|
| GET | `/api/v1/objekte/{objekt_id}/vertraege/csv-vorlage/` | CSV-Vorlage herunterladen — vorbelegt mit Einheiten + Abrechnungsarten des Objekts |
| POST | `/api/v1/objekte/{objekt_id}/vertraege/csv-preview/` | Datei hochladen, parsen, validieren, Vorschau |
| POST | `/api/v1/objekte/{objekt_id}/vertraege/csv-commit/` | Vorschau-Token bestaetigen, atomarer Import |
| GET | `/api/v1/vertraege/{vertrag_id}/hausgeld-historie/` | Komplette Historie eines Vertrags, gruppiert nach Abrechnungsart |
| GET | `/api/v1/vertraege/{vertrag_id}/hausgeld-aktuell/?stichtag=YYYY-MM-DD` | Aktueller Stand zum Stichtag (Default: heute) |
| POST | `/api/v1/vertraege/{vertrag_id}/hausgeld-historie/` | Einzelner manueller Eintrag (alternativ zur CSV) |
| PATCH | `/api/v1/hausgeld-historie/{id}/` | Korrektur eines bestehenden Eintrags |
| DELETE | `/api/v1/hausgeld-historie/{id}/` | Loeschung eines Eintrags |

---

## 10. Tests

### 10.1 Unit-Tests

```python
# tests/test_hausgeld_historie.py

def test_historie_aktueller_wert_einfacher_fall(vertrag, abr_900):
    HausgeldHistorie.objects.create(
        eigentumsverhaeltnis=vertrag, abrechnungsart=abr_900,
        gueltig_ab=date(2023, 1, 1), betrag=Decimal('250.00'),
        wirtschaftsplan_jahr=2023, erstellt_von=user,
    )
    assert vertrag.hausgeld_aktuell('900', date(2024, 6, 1)) == Decimal('250.00')

def test_historie_aktueller_wert_mit_wp_aenderung(vertrag, abr_900):
    HausgeldHistorie.objects.create(
        eigentumsverhaeltnis=vertrag, abrechnungsart=abr_900,
        gueltig_ab=date(2023, 1, 1), betrag=Decimal('250.00'), erstellt_von=user)
    HausgeldHistorie.objects.create(
        eigentumsverhaeltnis=vertrag, abrechnungsart=abr_900,
        gueltig_ab=date(2024, 1, 1), betrag=Decimal('280.00'), erstellt_von=user)
    HausgeldHistorie.objects.create(
        eigentumsverhaeltnis=vertrag, abrechnungsart=abr_900,
        gueltig_ab=date(2025, 1, 1), betrag=Decimal('295.00'), erstellt_von=user)

    assert vertrag.hausgeld_aktuell('900', date(2023, 6, 1)) == Decimal('250.00')
    assert vertrag.hausgeld_aktuell('900', date(2024, 6, 1)) == Decimal('280.00')
    assert vertrag.hausgeld_aktuell('900', date(2025, 6, 1)) == Decimal('295.00')

def test_historie_zukunfts_eintrag_wird_erst_aktiv_ab_datum(vertrag, abr_900):
    """Wirtschaftsplan 2025 beschlossen am 20.10.2024, gueltig ab 01.01.2025."""
    HausgeldHistorie.objects.create(
        eigentumsverhaeltnis=vertrag, abrechnungsart=abr_900,
        gueltig_ab=date(2024, 1, 1), betrag=Decimal('280.00'), erstellt_von=user)
    HausgeldHistorie.objects.create(
        eigentumsverhaeltnis=vertrag, abrechnungsart=abr_900,
        gueltig_ab=date(2025, 1, 1), betrag=Decimal('295.00'), erstellt_von=user)

    # Zukuenftiger Eintrag existiert, ist aber am 31.12.2024 noch nicht aktiv
    assert vertrag.hausgeld_aktuell('900', date(2024, 12, 31)) == Decimal('280.00')
    # Ab 01.01.2025 ist der neue Wert aktiv
    assert vertrag.hausgeld_aktuell('900', date(2025, 1, 1)) == Decimal('295.00')

def test_historie_selektive_aenderung_nur_hausgeld(vertrag, abr_900, abr_911):
    """WP 2025 aendert nur .900, .911 bleibt auf 2024er Wert."""
    HausgeldHistorie.objects.create(
        eigentumsverhaeltnis=vertrag, abrechnungsart=abr_900,
        gueltig_ab=date(2024, 1, 1), betrag=Decimal('280.00'), erstellt_von=user)
    HausgeldHistorie.objects.create(
        eigentumsverhaeltnis=vertrag, abrechnungsart=abr_911,
        gueltig_ab=date(2024, 1, 1), betrag=Decimal('60.00'), erstellt_von=user)
    HausgeldHistorie.objects.create(
        eigentumsverhaeltnis=vertrag, abrechnungsart=abr_900,
        gueltig_ab=date(2025, 1, 1), betrag=Decimal('295.00'), erstellt_von=user)

    assert vertrag.hausgeld_aktuell('900', date(2025, 6, 1)) == Decimal('295.00')
    assert vertrag.hausgeld_aktuell('911', date(2025, 6, 1)) == Decimal('60.00')

def test_unique_constraint_verhindert_duplikat(vertrag, abr_900):
    HausgeldHistorie.objects.create(
        eigentumsverhaeltnis=vertrag, abrechnungsart=abr_900,
        gueltig_ab=date(2024, 1, 1), betrag=Decimal('280.00'), erstellt_von=user)
    with pytest.raises(IntegrityError):
        HausgeldHistorie.objects.create(
            eigentumsverhaeltnis=vertrag, abrechnungsart=abr_900,
            gueltig_ab=date(2024, 1, 1), betrag=Decimal('999.99'), erstellt_von=user)
```

### 10.2 Integrations-Tests

```python
# tests/test_vertrags_csv_import.py

def test_csv_import_idempotent(client, objekt, csv_datei):
    response1 = client.post(f'/api/v1/objekte/{objekt.id}/vertraege/csv-commit/', ...)
    assert response1.status_code == 200
    count1 = HausgeldHistorie.objects.filter(eigentumsverhaeltnis__einheit__objekt=objekt).count()

    response2 = client.post(f'/api/v1/objekte/{objekt.id}/vertraege/csv-commit/', ...)
    assert response2.status_code == 200
    count2 = HausgeldHistorie.objects.filter(eigentumsverhaeltnis__einheit__objekt=objekt).count()

    assert count1 == count2  # Kein zusaetzlicher Eintrag bei Re-Import

def test_csv_import_zusaetzliche_zeile_legt_neuen_eintrag_an(client, objekt, csv_v1, csv_v2):
    """csv_v1: Erstanlage 2023+2024. csv_v2: zusaetzlich Zeile fuer 2025."""
    client.post(..., csv_v1)
    count_after_v1 = HausgeldHistorie.objects.count()

    client.post(..., csv_v2)
    count_after_v2 = HausgeldHistorie.objects.count()

    assert count_after_v2 == count_after_v1 + 1  # Eine neue Zeile

def test_csv_import_korrektur_aktualisiert_bestehenden_eintrag(client, objekt, csv_v1, csv_v1_korrigiert):
    """csv_v1_korrigiert hat fuer (WE01, 900, 2024-01-01) anderen Betrag."""
    client.post(..., csv_v1)
    eintrag = HausgeldHistorie.objects.get(
        eigentumsverhaeltnis__einheit__einheit_nr='WE01',
        abrechnungsart__code='900',
        gueltig_ab=date(2024, 1, 1),
    )
    assert eintrag.betrag == Decimal('280.00')

    client.post(..., csv_v1_korrigiert)
    eintrag.refresh_from_db()
    assert eintrag.betrag == Decimal('285.00')  # Korrigierter Wert

def test_csv_import_partial_wp_change(client, objekt, csv_wp_2025_nur_hausgeld):
    """WP 2025 enthaelt nur .900-Aenderungen — .911 bleibt unangetastet."""
    # Vorher: .911 hat Wert 60,00 ab 2024-01-01
    client.post(..., csv_wp_2025_nur_hausgeld)

    eintrag_911 = HausgeldHistorie.objects.filter(
        eigentumsverhaeltnis__einheit__einheit_nr='WE01',
        abrechnungsart__code='911',
        gueltig_ab=date(2025, 1, 1),
    ).first()
    assert eintrag_911 is None  # Kein neuer Eintrag fuer Ruecklage

def test_csv_import_atomic_rollback(client, objekt, csv_mit_fehler):
    """Wenn Zeile 5 von 10 fehlerhaft ist, werden 0 Zeilen importiert."""
    count_before = HausgeldHistorie.objects.count()
    response = client.post(..., csv_mit_fehler)
    assert response.status_code == 400
    count_after = HausgeldHistorie.objects.count()
    assert count_before == count_after
```

### 10.3 Edge Cases

- Vertrag mit `ende` gesetzt: keine neuen Historieneintraege nach `ende` zulaessig.
- Eigentuemerwechsel: alter Vertrag bekommt `ende`, neuer Vertrag startet — zwei getrennte Historien.
- Suffix `.910` in CSV: harte Ablehnung mit klarer Meldung.
- Abrechnungsart, die am Objekt nicht existiert (z.B. `.913` ohne 3. Ruecklage): harte Ablehnung.
- `gueltig_ab` exakt gleich `vertrag_beginn`: erlaubt (typischer Erstanlage-Fall).
- `gueltig_ab` < `vertrag_beginn`: harte Ablehnung.
- CSV mit ausschliesslich bestehenden Zeilen (`bestehend_unveraendert`): erfolgreicher Commit ohne Datenaenderung.

---

## 11. Auswirkungen auf andere Module

### 11.1 Sollstellung

Die monatliche Sollstellung muss `vertrag.hausgeld_aktuell(abr_code, datum)` verwenden, nicht eine direkte Eigenschaft am Vertrag. Bei Plan-Aenderung greift automatisch der neue Wert ab `gueltig_ab`.

### 11.2 Jahresabrechnung

Die Berechnung des Jahres-Soll fuer eine Einheit erfolgt anteilig:

```
Jahres-Soll je Einheit und Abrechnungsart =
    SUMME ueber alle Monate des Abrechnungsjahres:
        hausgeld_aktuell(vertrag, abr_code, monatsanfang)
```

Bei Wirtschaftsplan-Aenderung mitten im Jahr (z.B. nachtraeglicher Beschluss zum 01.07.) wird das automatisch korrekt aufgeloest.

### 11.3 Eigentuemerwechsel

Wizard `Eigentuemerwechsel v1.1` muss bei Anlage des neuen Vertrags die letzten gueltigen Werte des Vorgaenger-Vertrags als Vorbelegung anbieten — der Nutzer entscheidet, ob er sie uebernimmt oder anpasst. Es gibt keine automatische Saldenuebernahme.

### 11.4 Massenimport WEG

Massenimport v1.0 legt keine Vertraege an. Nach Massenimport laeuft der Vertragsmanagement-CSV-Import als zweiter Schritt. Beide Schritte sind **nicht** verknuepft — der Massenimport schafft das Skelett, der Vertragsimport fuellt die Vertragsdaten.

---

## 12. Migrationsplan

| # | Schritt | Reihenfolge |
|---|---|---|
| 1 | Schema-Migration: Neue Felder an `HausgeldHistorie` (abrechnungsart, wirtschaftsplan_jahr, quelle, bemerkung, erstellt_am) | Vor Datenmigration |
| 2 | Daten-Migration: Mappe Bestand auf Abrechnungsart `900`, leite `wirtschaftsplan_jahr` aus `gueltig_ab` ab | Nach Schema |
| 3 | Bereinigung: Doppelte Eintraege identifizieren und konsolidieren | Vor Constraint |
| 4 | Schema-Migration: Unique-Constraint `(eigentumsverhaeltnis, abrechnungsart, gueltig_ab)` | Nach Bereinigung |
| 5 | Schema-Migration: Index `(eigentumsverhaeltnis, abrechnungsart, -gueltig_ab)` | Nach Constraint |
| 6 | Service-Layer: `vertrag.hausgeld_aktuell()` ersetzt bestehende Property `hausgeld_soll` | Nach Schema |
| 7 | Endpunkte fuer CSV-Import implementieren | Nach Service |
| 8 | UI: Tab "Historie" am Vertrags-Detail | Nach Endpunkten |
| 9 | UI: CSV-Import-Maske (Wizard Schritt 7 + Objekt-Detail) | Nach Tab |
| 10 | Bestehende Sollstellung / Jahresabrechnung auf neue API umstellen | Nach UI |

---

## 13. Claude Code Prompt

```
Implementiere das Vertragsmanagement-Hausgeld-Historie-Modul fuer IMMOCORE
gemaess dieser Spezifikation.

Reihenfolge:

1. core/models/vertrag.py:
   - HausgeldHistorie um Felder erweitern: abrechnungsart (FK Abrechnungsart),
     wirtschaftsplan_jahr (PositiveIntegerField, null=True), quelle (CharField
     mit choices), bemerkung (CharField max 200), erstellt_am (auto_now_add).
   - Unique-Constraint (eigentumsverhaeltnis, abrechnungsart, gueltig_ab).
   - Index (eigentumsverhaeltnis, abrechnungsart, -gueltig_ab).
   - Methoden hausgeld_aktuell(abr_code, stichtag) und
     hausgeld_alle_aktuell(stichtag) auf EigentumsVerhaeltnis.

2. Migration:
   - Schema-Migration fuer neue Felder.
   - Daten-Migration: Bestand auf Abrechnungsart "900" mappen.
   - Cleanup-Migration fuer Duplikate.
   - Constraint-Migration nach Cleanup.

3. services/vertragsimport.py:
   - parse_csv() — UTF-8-BOM, Semikolon, Schema-Validierung
   - validiere_zeile() — alle Regeln aus Kap. 6.2
   - importiere_zeile() — update_or_create-Logik aus Kap. 5.2
   - commit() — atomarer Import, alle Zeilen in einer transaction.atomic()
   - vorschau() — Liefert Preview-JSON ohne DB-Aenderung

4. api/views/vertragsimport.py:
   - GET /api/v1/objekte/{id}/vertraege/csv-vorlage/
   - POST /api/v1/objekte/{id}/vertraege/csv-preview/
   - POST /api/v1/objekte/{id}/vertraege/csv-commit/
   - GET /api/v1/vertraege/{id}/hausgeld-historie/
   - GET /api/v1/vertraege/{id}/hausgeld-aktuell/

5. Anpassung Wizard Schritt 7:
   - Tabelle erstellt im Hintergrund Historie-Eintraege mit
     gueltig_ab=vertrag.beginn, quelle='wizard',
     wirtschaftsplan_jahr=Wirtschaftsjahr.jahr.
   - Zusaetzlicher Tab "CSV-Import" im Schritt.

6. Anpassung Objekt-Detail:
   - Neuer Tab "Vertraege" mit drei Sub-Tabs: Liste / CSV-Import / Historie.

7. Tests:
   - Unit-Tests fuer hausgeld_aktuell() (alle Faelle aus Kap. 10.1)
   - Integrations-Tests fuer CSV-Import (alle Faelle aus Kap. 10.2)
   - Edge-Case-Tests aus Kap. 10.3
   - Migrations-Tests: Bestand wird korrekt gemappt.

8. Refactoring der Aufrufer:
   - sollstellung-Service nutzt neues hausgeld_aktuell()
   - jahresabrechnung-Service summiert ueber Monate mit hausgeld_aktuell()
   - Eigentuemerwechsel-Wizard liest letzte gueltige Werte aus altem Vertrag

Wichtige Regeln:
- Lean Code, keine cleveren Abstraktionen
- Service-Layer-Trennung: Modelle nur fuer Datenstruktur, Logik in services/
- Alle Schreibvorgaenge in transaction.atomic()
- Kein post_save-Signal fuer HausgeldHistorie — explizite Service-Aufrufe
- GoBD: keine harten Loeschungen ohne Audit-Trail (django-auditlog reicht)
- Tests gruen vor naechstem Schritt
```

---

## 14. Dokumentenmetadaten

| Feld | Wert |
|---|---|
| Auftraggeber | Demme Immobilien Verwaltung GmbH |
| Adresse | Coventrystraße 32, 65934 Frankfurt am Main |
| Dokument-Typ | Claude Code Implementierungsprompt |
| Bezug | Ausgangsspezifikation v1.1 Kap. 4.6–4.8; WEG_Objektanlage v1.2 Schritt 7; Wirtschaftsjahre v1.0 |
| Modul | Vertragsmanagement-Import mit Hausgeld-/Rücklagenhistorie |
| KI-Modell | claude-sonnet-4-6 |
| Version | 1.0 |
| Stand | Mai 2026 |
| Status | Entwurf — bereit zur Pruefung und Iteration |
