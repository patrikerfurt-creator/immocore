# Claude Code – Anleitung: OP-Buchung mit verzögerter Aufwandsbuchung (IMMOCORE)

**Version:** 1.1 (referenziert Musterkontenrahmen WEG v2)
**Status:** Implementierungsreif

## Ziel

Bei Rechnungseingang entsteht **nur ein offener Posten** auf dem Kreditor.
Der Aufwand wird **erst bei Zahlung** auf das Aufwandskonto gebucht.
Buchungstechnisch wird das Verrechnungskonto `15900 – Schwebende
Eingangsrechnungen` zwischengeschaltet. Das Aufwandskonto wird bereits bei
der Rechnungserfassung vom Buchhalter ausgewählt und an der Rechnung
gespeichert.

Hintergrund: Kassenprinzip nach § 28 WEG / § 11 EStG. Die Buchung folgt
nicht der HGB-Periodengerechtigkeit, sondern der zahlungswirksamen
Erfassung wie für Hausgeld-/Wirtschaftsplanabrechnungen erforderlich.

## Bezug zum Musterkontenrahmen WEG

Diese Spezifikation **erweitert** den bestehenden Musterkontenrahmen
(`Musterkontenrahmen_WEG.xlsx`). Die Spaltenstruktur ist:

| Spalte | Bedeutung |
|--------|-----------|
| `Kontonummer` | 5-stellig |
| `Kontoname` | Bezeichnung |
| `Abrechnungsart` | Suffix-Mapping (`900`, `911`, `930`, …); leer = nicht HGA-relevant |
| `Direktes Buchen` | `ja` = manuell buchbar (Bank/Kasse/RAP) / `nein` = nur via Service |
| `VS` | Verteilerschlüssel (`010`, `031`, `100`, `101`, `140`, …) |
| `Kontoart` | `Standardkonto` / `Unterkonto` / `Summierungskonto` |
| `ARGE-Konto` | `0` / `Ja` (HEIWAKO-Relevanz) |
| `ARGE-Kostenart` | optional |

### Neuer Eintrag (bereits in v2 ergänzt)

```
15900 | Schwebende Eingangsrechnungen | (leer) | nein | (leer) | Standardkonto | 0 | (leer)
```

**Begründung der Felder:**
- `Abrechnungsart = leer` → reines Bilanz-/Verrechnungskonto, **nicht**
  hausgeldabrechnungsrelevant.
- `Direktes Buchen = nein` → wird ausschließlich durch die OP-Services
  bebucht, nie manuell.
- `VS = leer` → keine Umlage.
- `Kontoart = Standardkonto`.
- `ARGE-Konto = 0` → keine HEIWAKO-Relevanz.

## Kontenkategorien (für Validierung relevant)

| Bereich | Bedeutung | Im Spec relevant als |
|---------|-----------|----------------------|
| `09xxx` | Rücklagenbestand | – |
| `13xxx` | DCL / Ungeklärte Posten | – |
| `15900` | **Schwebende Eingangsrechnungen** (NEU) | Verrechnungskonto |
| `18xxx` | Bankkonten (`18000` Bank 1, `18911` Bank 2 Rücklage) | Bankkonto-Quelle |
| `41xxx` / `49xxx` | Erlöse Hausgeld / sonstige Erlöse | – |
| `50xxx` | Bewirtschaftungskosten umlagefähig | **Aufwand auswählbar** |
| `55xxx` | Verwaltungs-/Reparatur-/Bankkosten | **Aufwand auswählbar** |
| `57xxx` | Rücklagenzuführung | **NICHT** über OP-Workflow |
| `90xxx` / `91xxx` | Saldenvorträge | – |

**Auswahlfilter für `aufwandskonto` an der Rechnung:**
- Kontonummer im Bereich `50000–55999`
- `Kontoart = "Standardkonto"`
- `Direktes Buchen = "nein"`

Damit fallen automatisch raus: `57911` Rücklagenzuführung (keine
Eingangsrechnung), `50299` Summierungskonto (kein Buchungskonto), die
`50300–50360` Unterkonten (keine direkte Buchung; werden über
HEIWAKO-Import bebucht).

## Buchungslogik

### Phase 1 – Rechnungseingang (Status: `freigegeben`)
```
Soll  15900 Schwebende Eingangsrechnungen   Brutto
Haben 70xxx Kreditor-Personenkonto          Brutto
```
→ OP entsteht, Aufwand bleibt **unberührt**. Das gewählte Aufwandskonto
(`50xxx`/`55xxx`) wird nur an der Rechnung gespeichert, **nicht gebucht**.

### Phase 2 – Zahlung (Status: `bezahlt`)
Zwei zusammengehörige Buchungen in **einer atomaren Transaktion**:

**Buchung 2a – OP-Ausgleich:**
```
Soll  70xxx Kreditor-Personenkonto          Zahlbetrag
Haben 18xxx Bank (aus Zahlung)              Zahlbetrag
```

**Buchung 2b – Aufwandsumbuchung:**
```
Soll  5xxxx Aufwand (an Rechnung gespeichert) Zahlbetrag
Haben 15900 Schwebende Eingangsrechnungen     Zahlbetrag
```

### Konsistenz-Invariante
Solange keine Zahlung erfolgt ist, gilt **immer**:
> Summe offener Posten je Kreditor (Haben-Saldo `70xxx`) ==
> Saldo `15900` (Soll-Saldo) je zugeordneter Rechnung

---

## Aufgaben für Claude Code

> **Hinweis an Claude Code:** Bitte arbeite die Aufgaben in der angegebenen
> Reihenfolge ab. Nach jedem Schritt: Migration erzeugen, Tests laufen
> lassen, erst dann zum nächsten Schritt. Keine Datenbank-Änderungen ohne
> Migration. Alle Buchungslogik **ausschließlich** in `services/` – nie in
> Views oder Models.

### Schritt 1 – Konto `15900` ist im Musterkontenrahmen anzulegen

Die aktualisierte xlsx-Datei (`Musterkontenrahmen_WEG_v2.xlsx`) enthält
die neue Zeile bereits. **Aktion für Claude Code:**

- Stelle sicher, dass der vorhandene Import-Mechanismus (Datenmigration
  oder Management-Command) die neue Datei einliest.
- Erzeuge eine **Datenmigration**, die für jede bestehende WEG das Konto
  `15900` mit den Feldwerten aus der xlsx anlegt, falls es nicht
  existiert (idempotent).

```python
# apps/buchhaltung/migrations/00XX_add_konto_15900.py
def add_konto_15900(apps, schema_editor):
    Konto = apps.get_model("buchhaltung", "Konto")
    WEG = apps.get_model("objekte", "WEG")
    for weg in WEG.objects.all():
        Konto.objects.get_or_create(
            weg=weg,
            nummer="15900",
            defaults=dict(
                name="Schwebende Eingangsrechnungen",
                abrechnungsart=None,
                direktes_buchen=False,
                verteilerschluessel=None,
                kontoart="Standardkonto",
                arge_konto=False,
                arge_kostenart=None,
            ),
        )
```

### Schritt 2 – Modellanpassung `Rechnung`

Datei: `apps/buchhaltung/models/rechnung.py`

```python
class Rechnung(models.Model):
    # ... bestehende Felder ...
    weg = models.ForeignKey("objekte.WEG", on_delete=models.PROTECT,
                            related_name="rechnungen")
    kreditor = models.ForeignKey("Kreditor", on_delete=models.PROTECT,
                                  related_name="rechnungen")

    aufwandskonto = models.ForeignKey(
        "Konto",
        on_delete=models.PROTECT,
        related_name="rechnungen_als_aufwand",
        help_text="Wird bei Zahlung als Aufwand gebucht (50xxx oder 55xxx).",
    )

    rechnungsnummer = models.CharField(max_length=64)
    rechnungsdatum  = models.DateField()
    betrag_brutto   = models.DecimalField(max_digits=12, decimal_places=2)
    betrag_netto    = models.DecimalField(max_digits=12, decimal_places=2)
    ust_betrag      = models.DecimalField(max_digits=12, decimal_places=2,
                                            default=Decimal("0"))

    STATUS_CHOICES = [
        ("eingegangen", "Eingegangen"),
        ("in_pruefung", "In Prüfung"),
        ("freigegeben", "Freigegeben"),  # → OP gebucht
        ("bezahlt",     "Bezahlt"),       # → Aufwand vollständig gebucht
        ("teilbezahlt", "Teilbezahlt"),
        ("abgelehnt",   "Abgelehnt"),
        ("storniert",   "Storniert"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES,
                               default="eingegangen")

    op_buchung      = models.OneToOneField("Buchung", null=True, blank=True,
                                            on_delete=models.PROTECT,
                                            related_name="rechnung_op")
    aufwand_buchung = models.OneToOneField("Buchung", null=True, blank=True,
                                            on_delete=models.PROTECT,
                                            related_name="rechnung_aufwand")

    def clean(self):
        # Aufwandskonto-Validierung: 50000–55999, Standardkonto, nicht direkt
        nr = self.aufwandskonto.nummer
        if not ("50000" <= nr <= "55999"):
            raise ValidationError(
                f"Aufwandskonto {nr} liegt außerhalb 50000–55999."
            )
        if self.aufwandskonto.kontoart != "Standardkonto":
            raise ValidationError(
                f"Aufwandskonto {nr} ist kein Standardkonto."
            )
        if self.aufwandskonto.direktes_buchen:
            raise ValidationError(
                f"Aufwandskonto {nr} ist als 'Direktes Buchen' markiert "
                f"und nicht für OP-Workflow zulässig."
            )
        # Brutto-Konsistenz
        if abs(self.betrag_brutto - (self.betrag_netto + self.ust_betrag)) \
                > Decimal("0.01"):
            raise ValidationError("Brutto ≠ Netto + USt.")

    def offener_betrag(self) -> Decimal:
        gezahlt = self.zahlungen.aggregate(s=models.Sum("betrag"))["s"] \
                  or Decimal("0")
        return self.betrag_brutto - gezahlt
```

**Auswahlfilter im Form/Serializer (nicht im Model, da WEG-spezifisch):**
```python
qs = Konto.objects.filter(
    weg=rechnung.weg,
    nummer__gte="50000", nummer__lte="55999",
    kontoart="Standardkonto",
    direktes_buchen=False,
)
```

### Schritt 3 – Konstanten

Datei: `apps/buchhaltung/konstanten.py`

```python
KONTO_SCHWEBENDE_ER       = "15900"
KONTO_BEREICH_AUFWAND_VON = "50000"
KONTO_BEREICH_AUFWAND_BIS = "55999"
# Bank kommt aus Zahlung.bankkonto (z. B. 18000 / 18911), NICHT aus Konstante
```

### Schritt 4 – Service: OP buchen bei Freigabe

Datei: `apps/buchhaltung/services/rechnung_op_service.py`

```python
from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from apps.buchhaltung.models import Rechnung, Buchung, Buchungssatz, Konto
from apps.buchhaltung.konstanten import KONTO_SCHWEBENDE_ER


@transaction.atomic
def rechnung_freigeben(rechnung: Rechnung, freigegeben_von) -> Buchung:
    """
    Erzeugt die OP-Buchung bei Rechnungsfreigabe.
        Soll  15900 Schwebende ER     (Brutto)
        Haben 70xxx Kreditor          (Brutto)
    Aufwand wird hier NICHT gebucht.
    """
    if rechnung.op_buchung_id:
        raise ValidationError("OP-Buchung existiert bereits.")
    if rechnung.status not in ("eingegangen", "in_pruefung"):
        raise ValidationError(
            f"Rechnung im Status '{rechnung.status}' kann nicht freigegeben werden."
        )

    konto_schwebend = Konto.objects.get(
        nummer=KONTO_SCHWEBENDE_ER, weg=rechnung.weg
    )
    konto_kreditor = rechnung.kreditor.sachkonto  # 70xxx Personenkonto

    buchung = Buchung.objects.create(
        weg=rechnung.weg,
        beleg=rechnung,
        buchungstext=f"OP Rechnung {rechnung.rechnungsnummer} – "
                     f"{rechnung.kreditor.name}",
        belegdatum=rechnung.rechnungsdatum,
        erstellt_von=freigegeben_von,
        art="OP_EINGANG",
    )
    Buchungssatz.objects.create(
        buchung=buchung, konto=konto_schwebend,
        soll=rechnung.betrag_brutto, haben=Decimal("0"),
    )
    Buchungssatz.objects.create(
        buchung=buchung, konto=konto_kreditor,
        soll=Decimal("0"), haben=rechnung.betrag_brutto,
    )

    rechnung.op_buchung = buchung
    rechnung.status = "freigegeben"
    rechnung.save(update_fields=["op_buchung", "status"])
    return buchung
```

### Schritt 5 – Service: Aufwand buchen bei Zahlung

Datei: `apps/buchhaltung/services/rechnung_zahlung_service.py`

```python
from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from apps.buchhaltung.models import (
    Rechnung, Buchung, Buchungssatz, Konto, Zahlung
)
from apps.buchhaltung.konstanten import (
    KONTO_SCHWEBENDE_ER,
    KONTO_BEREICH_AUFWAND_VON,
    KONTO_BEREICH_AUFWAND_BIS,
)


@transaction.atomic
def rechnung_bezahlen(rechnung: Rechnung, zahlung: Zahlung,
                      gebucht_von) -> Buchung:
    """
    Erzeugt zwei Buchungen in einer Transaktion:
      (a) OP-Ausgleich:        Soll Kreditor   / Haben Bank
      (b) Aufwandsumbuchung:   Soll 5xxxx      / Haben 15900

    Unterstützt Voll- und Teilzahlungen (zahlung.betrag).
    """
    if rechnung.status not in ("freigegeben", "teilbezahlt"):
        raise ValidationError(
            "Nur freigegebene oder teilbezahlte Rechnungen können bezahlt werden."
        )
    if not rechnung.op_buchung_id:
        raise ValidationError(
            "Keine OP-Buchung vorhanden – bitte erst freigeben."
        )

    offen = rechnung.offener_betrag()
    if zahlung.betrag <= 0 or zahlung.betrag > offen:
        raise ValidationError(
            f"Zahlbetrag {zahlung.betrag} ungültig (offen: {offen})."
        )

    konto_schwebend = Konto.objects.get(
        nummer=KONTO_SCHWEBENDE_ER, weg=rechnung.weg
    )
    konto_kreditor = rechnung.kreditor.sachkonto
    konto_bank     = zahlung.bankkonto       # 18000 / 18911 etc.
    konto_aufwand  = rechnung.aufwandskonto  # 50xxx / 55xxx

    nr = konto_aufwand.nummer
    if not (KONTO_BEREICH_AUFWAND_VON <= nr <= KONTO_BEREICH_AUFWAND_BIS):
        raise ValidationError(
            f"Aufwandskonto {nr} außerhalb {KONTO_BEREICH_AUFWAND_VON}"
            f"–{KONTO_BEREICH_AUFWAND_BIS}."
        )

    if not konto_bank.nummer.startswith("18"):
        raise ValidationError(
            f"Bankkonto {konto_bank.nummer} ist kein 18xxx-Konto."
        )

    betrag = zahlung.betrag

    # (a) OP-Ausgleich: Kreditor an Bank
    b_op = Buchung.objects.create(
        weg=rechnung.weg, beleg=zahlung,
        buchungstext=f"Zahlung Rechnung {rechnung.rechnungsnummer}",
        belegdatum=zahlung.valuta, erstellt_von=gebucht_von,
        art="OP_AUSGLEICH",
    )
    Buchungssatz.objects.create(buchung=b_op, konto=konto_kreditor,
                                soll=betrag, haben=Decimal("0"))
    Buchungssatz.objects.create(buchung=b_op, konto=konto_bank,
                                soll=Decimal("0"), haben=betrag)

    # (b) Aufwandsumbuchung: 5xxxx an 15900
    b_aufwand = Buchung.objects.create(
        weg=rechnung.weg, beleg=rechnung,
        buchungstext=f"Aufwand Rechnung {rechnung.rechnungsnummer} "
                     f"({konto_aufwand.nummer})",
        belegdatum=zahlung.valuta, erstellt_von=gebucht_von,
        art="AUFWAND_UMBUCHUNG",
    )
    Buchungssatz.objects.create(buchung=b_aufwand, konto=konto_aufwand,
                                soll=betrag, haben=Decimal("0"))
    Buchungssatz.objects.create(buchung=b_aufwand, konto=konto_schwebend,
                                soll=Decimal("0"), haben=betrag)

    # Status-Update
    if (offen - betrag) <= Decimal("0.00"):
        rechnung.status = "bezahlt"
    else:
        rechnung.status = "teilbezahlt"

    if rechnung.aufwand_buchung_id is None:
        rechnung.aufwand_buchung = b_aufwand  # erste Buchung als Referenz
    rechnung.save(update_fields=["status", "aufwand_buchung"])
    return b_aufwand
```

**Hinweis zu Teilzahlungen:** Die Aufwandsbuchung erfolgt zahlungs­anteilig.
Solange Restbetrag offen, bleibt anteiliger Saldo auf `15900` und `70xxx`
stehen → Konsistenz-Invariante bleibt gültig.

### Schritt 6 – Konsistenz-Check (Management-Command)

Datei: `apps/buchhaltung/management/commands/check_op_konsistenz.py`

```python
from django.core.management.base import BaseCommand
from decimal import Decimal
from apps.buchhaltung.models import Rechnung


class Command(BaseCommand):
    help = ("Prüft die OP-Invariante: Saldo 15900 je Rechnung "
            "== offener Betrag der Rechnung.")

    def handle(self, *args, **opts):
        fehler = 0
        qs = Rechnung.objects.filter(
            status__in=["freigegeben", "teilbezahlt"]
        )
        for r in qs.iterator():
            saldo_15900 = r.saldo_konto("15900")
            offen = r.offener_betrag()
            if abs(saldo_15900 - offen) > Decimal("0.01"):
                self.stdout.write(self.style.ERROR(
                    f"Rechnung {r.rechnungsnummer} (WEG {r.weg_id}): "
                    f"15900={saldo_15900}, offen={offen}"
                ))
                fehler += 1
        if fehler == 0:
            self.stdout.write(self.style.SUCCESS("OP-Konsistenz: OK"))
        else:
            self.stdout.write(self.style.ERROR(
                f"OP-Konsistenz: {fehler} Abweichung(en)"
            ))
```

### Schritt 7 – Tests

Datei: `apps/buchhaltung/tests/test_op_buchung.py`

Pflichttests:

1. **Freigabe ohne Aufwand:** Nach `rechnung_freigeben`:
   `saldo(50100) == 0`, `saldo(15900) == Brutto`,
   `saldo(Kreditor) == -Brutto`.
2. **Vollzahlung über Bank 18000:** Nach `rechnung_bezahlen`:
   `saldo(15900) == 0`, `saldo(50100) == Brutto`,
   `saldo(Kreditor) == 0`, `saldo(18000) == -Brutto`.
3. **Teilzahlung 50 %:** `saldo(50100) == 50%`, `saldo(15900) == 50%`,
   `saldo(Kreditor) == -50%`, Status = `"teilbezahlt"`.
4. **Restzahlung nach Teilzahlung:** Vollzahlungs-Endzustand erreicht,
   Status = `"bezahlt"`.
5. **Falsches Aufwandskonto** (`41900` Erlöse, `57911` Rücklagenzuführung,
   `50299` Summierungskonto): `ValidationError` im `clean()`.
6. **Aufwandskonto mit `direktes_buchen=True`:** `ValidationError`.
7. **Doppelte Freigabe:** `ValidationError`.
8. **Zahlung ohne vorherige Freigabe:** `ValidationError`.
9. **Konsistenz-Command** auf Testdaten meldet 0 Fehler.

### Schritt 8 – UI / Form

Im Erfassungsformular (`RechnungForm`):

- `aufwandskonto` als Pflichtfeld mit Queryset-Filter (siehe Schritt 2).
- Autocomplete-Suche nach Kontonummer **und** Bezeichnung.
- Per Default Vorschlag aus `Kreditor.letztes_aufwandskonto` (Caching auf
  Kreditor-Modell, wird beim erfolgreichen `rechnung_freigeben` gesetzt).

### Schritt 9 – Optional (separat spezifizieren)

Aus Scope dieser Anleitung **bewusst ausgeklammert** – bei Bedarf in
eigenen Specs:

- **Skonto** (Aufwandsminderung gegen `15900`)
- **Storno** (Gegenbuchungen bei `op_buchung` und `aufwand_buchung`)
- **Heizkosten-Unterkonten** (`50300–50360`): Werden über
  HEIWAKO-Importworkflow bebucht, **nicht** über OP-Service.

---

## Definition of Done

- [ ] Migration `00XX_add_konto_15900` läuft ohne Fehler auf leerer und
      bestehender DB; alle WEGs haben `15900` angelegt.
- [ ] Aufwandskonto-Filter im `RechnungForm` zeigt nur `50xxx`/`55xxx`
      Standardkonten mit `direktes_buchen=False`.
- [ ] Alle 9 Pflichttests grün.
- [ ] Konsistenz-Command meldet 0 Fehler auf Testdaten.
- [ ] Code-Review: keine Buchungslogik in Views/Models, nur in `services/`.
- [ ] GoBD: keine `delete()`-Calls auf `Buchung`/`Buchungssatz`.
- [ ] Doku in `docs/buchhaltung/op_buchung.md` aktualisiert.

---

## Zusammenfassung Buchungssätze (Spickzettel)

| Ereignis | Soll | Haben | Betrag |
|----------|------|-------|--------|
| Rechnungsfreigabe | `15900` Schwebende ER | `70xxx` Kreditor | Brutto |
| Zahlung (a) | `70xxx` Kreditor | `18xxx` Bank | Zahlbetrag |
| Zahlung (b) | `5xxxx` Aufwand (lt. Rechnung) | `15900` Schwebende ER | Zahlbetrag |
