# IMMOCORE — Personen-Import: Ergebnisdatei mit Personennummern | Claude Code Prompt v1.0

**IMMOCORE**
*Webbasiertes Immobilienverwaltungssystem*

**Claude Code Implementierungsprompt**
Modul: Eigentümer-CSV-Import — Ergebnis-Download mit Personennummern
Demme Immobilien Verwaltung GmbH
Coventrystraße 32, 65934 Frankfurt am Main
Version 1.0  |  Stand: Mai 2026

---

## 1. Zweck dieses Dokuments

Dieses Dokument beschreibt eine **Erweiterung des Eigentümer-CSV-Imports** im 10-Schritt-Wizard (Schritt 4). Nach erfolgreichem Commit liefert das System dem Nutzer automatisch eine **Ergebnis-CSV** zum Download zurück, die zeilenweise dokumentiert, welche `personennummer` für jeden Datensatz vergeben (oder gematcht) wurde — inklusive Status für übersprungene und fehlgeschlagene Zeilen.

Diese Funktion adressiert drei konkrete Bedürfnisse:

1. **Rückverfolgbarkeit:** Der Nutzer kann nachvollziehen, welche `personennummer` in IMMOCORE für jeden CSV-Datensatz angelegt oder zugeordnet wurde — wichtig für die spätere manuelle Pflege oder externe Buchhaltungssysteme.
2. **GoBD-Auditierbarkeit:** Der Importlauf wird als versionierter Beleg dokumentiert; jede angelegte oder geänderte Person ist eindeutig auf eine CSV-Zeile zurückführbar.
3. **Idempotente Re-Imports:** Bei wiederholtem Upload derselben CSV (versehentlich oder nach Korrektur) zeigt die Ergebnisdatei klar `created` vs. `updated` vs. `skipped`.

> **Voraussetzung:** Phase 4 (10-Schritt-Wizard) implementiert; CSV-Upload-Endpunkt `POST /prozesse/{id}/steps/4/csv-upload/` funktional. Bezug: `IMMOCORE_ClaudeCode_WEG_Objektanlage v1.2` (Kap. 3.5).

---

## 2. Architektur-Entscheidung: Direkt-Download statt Dateisystem

### 2.1 Begründung

Der CSV-Upload in Schritt 4 erfolgt über einen HTTP-Multipart-Request — die Datei lebt nur kurz im Request-Body bzw. als Django `UploadedFile`-Objekt. Es existiert **kein persistenter "Quellordner" auf dem Server**. Eine Ergebnisdatei "neben der Quelldatei abzulegen" ist daher technisch nicht sinnvoll.

Stattdessen wird die Ergebnisdatei direkt im HTTP-Response des Commit-Endpunkts zurückgeliefert. Der Browser triggert automatisch den Download. Der ursprüngliche Dateiname der hochgeladenen CSV wird übernommen und um Suffix + Zeitstempel ergänzt.

### 2.2 Naming-Schema

```
{originalname}_ergebnis_{YYYYMMDD_HHMMSS}.csv
```

**Beispiel:**
Hochgeladen: `eigentuemer_weg_mainufer.csv`
Zurückgegeben: `eigentuemer_weg_mainufer_ergebnis_20260508_143012.csv`

Der Zeitstempel verhindert Kollisionen bei wiederholten Importen und dokumentiert implizit den Importzeitpunkt.

### 2.3 Was nicht serverseitig persistiert wird

Die Ergebnis-CSV wird **nicht** zusätzlich in S3 oder im Dateisystem abgelegt. Die für GoBD-Zwecke nötige Auditierbarkeit ist bereits durch den `ImportJob.ergebnis`-JSONField (siehe Kap. 6) gegeben — die CSV ist nur ein **Export-Format** dieser strukturierten Daten, keine eigene Quelle der Wahrheit.

---

## 3. CSV-Format der Ergebnisdatei

### 3.1 Spaltenstruktur

Die Ergebnisdatei übernimmt **alle Spalten der Eingabe-CSV unverändert** und ergänzt drei neue Spalten am Ende:

| Spalte | Quelle | Beschreibung |
|---|---|---|
| ... | Eingabe-CSV | Alle ursprünglichen Spalten (`einheit_nr`, `ist_firma`, `vorname`, `nachname`, `firmenname`, `email`, `telefon`, `adresse`, `iban`) bleiben erhalten — Reihenfolge identisch zur Vorlage. |
| `personennummer` | **NEU** | Vergebene oder gematchte Personennummer (leer bei `failed`). |
| `status` | **NEU** | `created` \| `updated` \| `skipped` \| `failed` |
| `meldung` | **NEU** | Klartext-Hinweis: bei `created`/`updated` leer oder Match-Begründung; bei `skipped`/`failed` Begründung (z.B. "IBAN ungültig", "Duplikat zu personennummer 100089"). |

### 3.2 Encoding & Trennzeichen

| Eigenschaft | Wert |
|---|---|
| Encoding | UTF-8 mit BOM (Excel-kompatibel) |
| Trennzeichen | Semikolon (`;`) — identisch zur Vorlage |
| Zeilenende | `\r\n` (CRLF) für Windows-Kompatibilität |
| Zitierung | RFC 4180-konform (Felder mit `;`, `"` oder Zeilenumbruch werden in `"..."` eingeschlossen) |

### 3.3 Status-Semantik

| Status | Bedeutung | personennummer |
|---|---|---|
| `created` | Neue Person wurde angelegt | Neu vergebene Nummer |
| `updated` | Bestehende Person wurde aktualisiert (z.B. neue IBAN ergänzt) | Vorhandene Nummer |
| `skipped` | Datensatz übersprungen wegen Duplikat (E-Mail oder IBAN-Treffer in Stammdaten); Nutzer hat im Match-Dialog "bestehende Person verwenden" gewählt | Vorhandene Nummer |
| `failed` | Validierungsfehler — kein Datensatz angelegt | leer |

### 3.4 Beispielausgabe

```csv
einheit_nr;ist_firma;vorname;nachname;firmenname;email;telefon;adresse;iban;personennummer;status;meldung
WE01;FALSE;Klaus;Müller;;k.mueller@email.de;0170 123456;Musterstr. 1, 60001 Frankfurt;DE89370400440532013000;100234;created;
WE02;FALSE;Eva;Schmidt;;e.schmidt@email.de;;Beispielweg 2, 60002 Frankfurt;DE75512108001245126199;100156;updated;Bestehende Person um neue IBAN ergänzt
WE03;FALSE;Hans;Müller;;h.mueller@email.de;;Musterstr. 1, 60001 Frankfurt;DE89370400440532013000;100234;skipped;Duplikat zu personennummer 100234 (gleiche IBAN)
G01;TRUE;;;MusterGmbH;info@mustergmbh.de;069 123456;Gewerbestr. 5, 60002 Frankfurt;DE-INVALID;;failed;IBAN ungültig: Format nicht DE-konform
```

---

## 4. Backend-Implementierung

### 4.1 Service-Layer-Erweiterung

In `services/personen_import.py` (oder analoger bestehender Service-Datei) wird die bestehende Funktion `importiere_eigentuemer_csv()` so erweitert, dass sie pro CSV-Zeile ein **strukturiertes Ergebnisobjekt** zurückgibt — nicht nur die angelegten Personen.

```python
# services/personen_import.py

from dataclasses import dataclass
from typing import Literal, Optional

@dataclass
class PersonenImportZeilenergebnis:
    """Ergebnis der Verarbeitung einer einzelnen CSV-Zeile."""
    zeilennummer: int                      # 1-basiert, ohne Header
    rohdaten: dict                         # Ursprungs-Spalten der CSV-Zeile
    status: Literal["created", "updated", "skipped", "failed"]
    personennummer: Optional[str]          # None bei failed
    meldung: str = ""                      # Match- oder Fehlerbegründung


def importiere_eigentuemer_csv(
    prozess_id: str,
    csv_datei: UploadedFile,
    user: User,
    match_entscheidungen: dict,            # {zeilennr: "use_existing" | "create_new"}
) -> list[PersonenImportZeilenergebnis]:
    """
    Verarbeitet die hochgeladene Eigentümer-CSV.
    Liefert pro Zeile ein Ergebnisobjekt zurück — auch für skipped/failed.

    WICHTIG: Auch fehlerhafte Zeilen werden im Ergebnis abgebildet.
    Reihenfolge des Ergebnisses == Reihenfolge der CSV-Zeilen.
    """
    ergebnisse = []

    for zeilennummer, rohdaten in _parse_csv(csv_datei):
        try:
            with transaction.atomic():
                ergebnis = _verarbeite_zeile(
                    zeilennummer=zeilennummer,
                    rohdaten=rohdaten,
                    user=user,
                    match_entscheidung=match_entscheidungen.get(zeilennummer),
                )
        except ValidierungsFehler as exc:
            ergebnis = PersonenImportZeilenergebnis(
                zeilennummer=zeilennummer,
                rohdaten=rohdaten,
                status="failed",
                personennummer=None,
                meldung=str(exc),
            )

        ergebnisse.append(ergebnis)

    return ergebnisse
```

**Lean-Code-Prinzip:** Das `transaction.atomic()` umschließt **nur die einzelne Zeile** — ein Fehler in Zeile 5 verhindert nicht die Anlage von Zeile 6. Konsistent mit dem Pattern aus `Massenimport_WEG v1.0` Kap. 6.3.

### 4.2 View-Layer: CSV-Generierung & Response

In `views/wizard.py` (oder analoger Datei) wird der bestehende Commit-Endpunkt erweitert:

```python
# views/wizard.py

import csv
import io
from datetime import datetime
from django.http import HttpResponse

from services.personen_import import importiere_eigentuemer_csv

ORIGINAL_SPALTEN = [
    "einheit_nr", "ist_firma", "vorname", "nachname", "firmenname",
    "email", "telefon", "adresse", "iban",
]
ERGEBNIS_SPALTEN = ["personennummer", "status", "meldung"]


@api_view(["POST"])
def commit_eigentuemer_csv(request, prozess_id: str):
    """
    POST /prozesse/{id}/steps/4/csv-commit/

    Body: multipart/form-data
      - csv_datei: UploadedFile (gleiche Datei wie beim Preview)
      - match_entscheidungen: JSON {zeilennr: "use_existing" | "create_new"}

    Response: text/csv (UTF-8 BOM) als Browser-Download.
    """
    csv_datei = request.FILES["csv_datei"]
    original_name = _extrahiere_basisname(csv_datei.name)  # ohne .csv

    ergebnisse = importiere_eigentuemer_csv(
        prozess_id=prozess_id,
        csv_datei=csv_datei,
        user=request.user,
        match_entscheidungen=json.loads(request.POST["match_entscheidungen"]),
    )

    # Ergebnis als ImportJob persistieren (GoBD-Audit)
    _persistiere_import_job(prozess_id, ergebnisse, request.user)

    # CSV-Response generieren
    return _ergebnis_csv_response(original_name, ergebnisse)


def _ergebnis_csv_response(
    original_name: str,
    ergebnisse: list[PersonenImportZeilenergebnis],
) -> HttpResponse:
    """Baut die Ergebnis-CSV und gibt sie als Download-Response zurück."""
    buffer = io.StringIO()
    buffer.write("\ufeff")  # UTF-8 BOM für Excel-Kompatibilität

    writer = csv.DictWriter(
        buffer,
        fieldnames=ORIGINAL_SPALTEN + ERGEBNIS_SPALTEN,
        delimiter=";",
        lineterminator="\r\n",
        quoting=csv.QUOTE_MINIMAL,
    )
    writer.writeheader()

    for e in ergebnisse:
        zeile = {spalte: e.rohdaten.get(spalte, "") for spalte in ORIGINAL_SPALTEN}
        zeile["personennummer"] = e.personennummer or ""
        zeile["status"] = e.status
        zeile["meldung"] = e.meldung
        writer.writerow(zeile)

    zeitstempel = datetime.now().strftime("%Y%m%d_%H%M%S")
    dateiname = f"{original_name}_ergebnis_{zeitstempel}.csv"

    response = HttpResponse(buffer.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{dateiname}"'
    return response


def _extrahiere_basisname(uploaded_name: str) -> str:
    """'eigentuemer.csv' -> 'eigentuemer'. Robust gegen fehlende Endung."""
    if uploaded_name.lower().endswith(".csv"):
        return uploaded_name[:-4]
    return uploaded_name
```

### 4.3 ImportJob-Persistenz (GoBD)

Der Importlauf wird in einem `ImportJob`-Datensatz dokumentiert (analog zum bestehenden Model aus `Massenimport_WEG v1.0` Kap. 8.1, ggf. um `typ="personen_import"` erweitert):

```python
def _persistiere_import_job(
    prozess_id: str,
    ergebnisse: list[PersonenImportZeilenergebnis],
    user: User,
) -> ImportJob:
    return ImportJob.objects.create(
        typ="personen_import",
        status=_aggregat_status(ergebnisse),  # "erfolgreich" | "teilweise" | "fehlgeschlagen"
        zeilen_gesamt=len(ergebnisse),
        zeilen_ok=sum(1 for e in ergebnisse if e.status in ("created", "updated")),
        zeilen_warnung=sum(1 for e in ergebnisse if e.status == "skipped"),
        zeilen_fehler=sum(1 for e in ergebnisse if e.status == "failed"),
        ergebnis=[
            {
                "zeile": e.zeilennummer,
                "status": e.status,
                "personennummer": e.personennummer,
                "meldung": e.meldung,
            }
            for e in ergebnisse
        ],
        erstellt_von=user,
    )
```

---

## 5. Frontend-Anpassung (React)

Der bestehende Upload-Dialog in Step 4 wird minimal erweitert:

1. Nach erfolgreichem Commit (HTTP 200, `Content-Type: text/csv`) triggert der Browser **automatisch** den Download über das `Content-Disposition: attachment`-Header.
2. Im UI wird zusätzlich ein **Erfolgs-Banner** angezeigt mit Summen-Statistik:
   > „12 Eigentümer angelegt, 3 aktualisiert, 1 übersprungen, 0 Fehler. Ergebnisdatei wurde heruntergeladen."
3. Optional: **„Erneut herunterladen"-Button** ruft `GET /import-jobs/{id}/ergebnis-csv/` auf, falls der ursprüngliche Download fehlschlug oder verloren ging. Dieser Endpunkt baut die CSV aus dem persistierten `ImportJob.ergebnis`-JSON neu auf — der Inhalt ist identisch zum ursprünglichen Download.

```typescript
// services/personenImport.ts

export async function commitPersonenImport(
  prozessId: string,
  csvDatei: File,
  matchEntscheidungen: Record<number, "use_existing" | "create_new">,
): Promise<void> {
  const formData = new FormData();
  formData.append("csv_datei", csvDatei);
  formData.append("match_entscheidungen", JSON.stringify(matchEntscheidungen));

  const response = await fetch(
    `/api/v1/prozesse/${prozessId}/steps/4/csv-commit/`,
    { method: "POST", body: formData },
  );

  if (!response.ok) {
    throw new Error(`Import fehlgeschlagen: HTTP ${response.status}`);
  }

  // Download triggern
  const blob = await response.blob();
  const dateiname = extrahiereDateinameAusHeader(response.headers.get("Content-Disposition"));
  triggerBrowserDownload(blob, dateiname);
}
```

---

## 6. Validierungsregeln (Ergänzung Spec v1.2 Kap. 3.6)

| Schritt | Regel | Verhalten |
|---|---|---|
| 4 | Commit ohne vorausgegangenes Preview | HTTP 400 — User muss erst Preview-Schritt durchlaufen |
| 4 | `match_entscheidungen` enthält Zeile, die im CSV nicht existiert | Eintrag wird ignoriert; Warnung im `ImportJob.ergebnis` |
| 4 | CSV im Commit weicht vom Preview ab (Hash-Vergleich) | HTTP 409 Conflict — User muss Preview erneut durchlaufen |
| 4 | Kein einziger Datensatz erfolgreich (`zeilen_ok = 0`) | Ergebnisdatei wird trotzdem ausgeliefert; Wizard-Schritt 4 bleibt nicht abgeschlossen |

---

## 7. Tests

### 7.1 Unit-Tests

- `_extrahiere_basisname("foo.csv") == "foo"`
- `_extrahiere_basisname("foo.CSV") == "foo"` (Case-Insensitivity)
- `_extrahiere_basisname("foo") == "foo"` (kein Suffix)
- CSV-Generierung mit BOM: erste 3 Bytes == `\xef\xbb\xbf`
- CSV-Generierung mit Sonderzeichen (Müller, Sträße): korrekt UTF-8-codiert
- CSV-Generierung mit Semikolon im Feld (z.B. Adresse `Musterstr. 1; 60001 Frankfurt`): wird in `"..."` eingeschlossen
- Ergebnisreihenfolge entspricht Eingabereihenfolge auch bei `failed`-Zeilen

### 7.2 Integrationstests

- CSV mit 5 Zeilen: 3× `created`, 1× `updated`, 1× `failed` → Ergebnisdatei enthält alle 5 Zeilen in Originalreihenfolge
- Re-Import derselben CSV → alle Zeilen `skipped` mit Verweis auf bestehende `personennummer`
- CSV mit ungültiger IBAN in Zeile 3 → Zeilen 1, 2, 4, 5 angelegt, Zeile 3 als `failed` in Ergebnis-CSV
- Header `Content-Disposition: attachment; filename="..._ergebnis_YYYYMMDD_HHMMSS.csv"` korrekt gesetzt
- Excel-Import der Ergebnis-CSV: Umlaute, Trennzeichen und Zeilenenden korrekt erkannt
- `ImportJob.ergebnis` enthält alle Zeilen-Ergebnisse als JSON

### 7.3 Edge-Cases

- Leere CSV (nur Header) → CSV-Response mit nur Header + Status 200
- CSV mit Dateiname `eigentuemer mit leerzeichen.csv` → `eigentuemer mit leerzeichen_ergebnis_...csv` (Leerzeichen erlaubt in `Content-Disposition`-Quoting)
- CSV ohne `.csv`-Endung → Basisname unverändert übernommen
- Sehr große CSV (500+ Zeilen) → Streaming-Response erwägen, aber für MVP: synchroner Download akzeptabel

---

## 8. Was ausdrücklich NICHT Bestandteil dieser Spec ist

- **S3-Persistenz der Ergebnisdatei** — bewusst nicht umgesetzt; `ImportJob.ergebnis` ist die Quelle der Wahrheit, CSV ist nur Export-Format.
- **Zeitstempel im Dateinamen mit Zeitzone** — Servertime (Europe/Berlin) reicht; UTC-Konversion nicht nötig.
- **Async-Generierung über Celery** — synchron im Request-Cycle ausreichend bei max. 500 Zeilen Wizard-Limit.
- **Excel-Format (.xlsx)** statt CSV — explizit als CSV vorgegeben.
- **Übertragung des Schemas auf den Massenimport-WEG-Excel** — separates Konzept, ggf. eigene Spec.

---

## 9. Implementierungs-Reihenfolge

1. `services/personen_import.py`: `PersonenImportZeilenergebnis`-Dataclass + Refactoring der bestehenden Funktion auf strukturierte Rückgabe.
2. `views/wizard.py`: `_ergebnis_csv_response()` + `commit_eigentuemer_csv()` ergänzen.
3. `models.py`: `ImportJob.typ` um `"personen_import"`-Choice erweitern (falls nicht bereits enthalten).
4. Frontend: Download-Trigger + Erfolgs-Banner.
5. Optional: `GET /import-jobs/{id}/ergebnis-csv/` für Re-Download.
6. Tests gemäß Kap. 7.

---

## 10. Dokumentenmetadaten

| Feld | Wert |
|---|---|
| Auftraggeber | Demme Immobilien Verwaltung GmbH |
| Adresse | Coventrystraße 32, 65934 Frankfurt am Main |
| Dokument-Typ | Claude Code Implementierungsprompt |
| Modul | Eigentümer-CSV-Import — Ergebnis-Download |
| Bezug | `IMMOCORE_ClaudeCode_WEG_Objektanlage v1.2` (Kap. 3.5) |
| Phase | Erweiterung Phase 4 |
| KI-Modell | claude-sonnet-4-6 |
| Version | 1.0 |
| Stand | Mai 2026 |
| Status | Freigegeben zur Verwendung in Claude Code |

> **Kritische Punkte für die Implementierung:**
> - Ergebnisdatei wird **direkt im HTTP-Response** zurückgegeben — keine Server-Persistenz im Dateisystem.
> - Reihenfolge der Ergebnisdatei == Reihenfolge der Eingabe-CSV. Auch `failed`-Zeilen werden ausgegeben.
> - UTF-8 mit BOM, Semikolon, CRLF — konsistent zur Vorlage aus Spec v1.2 Kap. 3.5.
> - `ImportJob.ergebnis`-JSON ist die GoBD-relevante Quelle der Wahrheit, nicht die CSV.
