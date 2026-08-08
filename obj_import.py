"""
OBJImport – Objekt-CSV-Erzeugung aus PDF-Exporten (nicht-interaktiv)
====================================================================
Erzeugt aus den PDF-Dateien eines Objekt-Ordners:
    <Objektnr> Personen_Import.csv
    <Objektnr> Einheiten.csv
    <Objektnr>-Vertraege.csv

Aufruf:
    py -3.11 obj_import.py "<Ordner>" <Objektnummer>
    z.B.  py -3.11 obj_import.py "Testdateine IMPORT\PDF_1\10008" 10008

PDF-Rollen (automatisch erkannt am Dateinamen):
    - Personenliste  -> Name enthält "Personenliste" (Fallback: "Person")
    - Karteiblatt    -> Name enthält "Vertraege"/"Vertrag"/"Karteiblatt"
      Aus dem Flächen-Karteiblatt werden BEIDE erzeugt: Einheiten + Verträge.
      (Eine reine "Einheiten"/Flächenstamm-PDF hat NICHT das benötigte Format
       und wird NICHT verwendet.)

Die eigentliche Extraktion stammt aus immocore_import.py (dort getestet).
"""
import sys
from pathlib import Path
import importlib.util

# immocore_import.py aus demselben Verzeichnis laden
IMP_PFAD = Path(__file__).resolve().parent / "immocore_import.py"
if not IMP_PFAD.exists():
    print(f"FEHLER: {IMP_PFAD} nicht gefunden."); sys.exit(1)
_spec = importlib.util.spec_from_file_location("imptool", IMP_PFAD)
imp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(imp)   # setzt u.a. stdout auf UTF-8 (win32)


def finde_pdf(ordner: Path, *begriffe, ausschluss: Path = None):
    """Erste PDF, deren Name einen der Begriffe (in Reihenfolge) enthält."""
    pdfs = [f for f in sorted(ordner.glob("*.pdf")) if f != ausschluss]
    for b in begriffe:
        for f in pdfs:
            if b.lower() in f.name.lower():
                return f
    return None


def main():
    if len(sys.argv) < 3:
        print('Aufruf: py -3.11 obj_import.py "<Ordner>" <Objektnummer>')
        sys.exit(1)

    ordner = Path(sys.argv[1])
    objekt = sys.argv[2].strip()
    if not ordner.is_dir():
        print(f"FEHLER: Ordner nicht gefunden: {ordner}"); sys.exit(1)

    pdf_personen = finde_pdf(ordner, "personenliste", "person")
    pdf_flaechen = finde_pdf(ordner, "vertraege", "vertrag", "karteiblatt",
                             ausschluss=pdf_personen)

    if not pdf_personen:
        print("FEHLER: Keine Personenliste-PDF gefunden (Name muss 'Personenliste' enthalten).")
        sys.exit(1)
    if not pdf_flaechen:
        print("FEHLER: Keine Karteiblatt/Vertraege-PDF gefunden (Name muss 'Vertraege' oder 'Karteiblatt' enthalten).")
        sys.exit(1)

    print(f"  Objekt        : {objekt}")
    print(f"  Personenliste : {pdf_personen.name}")
    print(f"  Karteiblatt   : {pdf_flaechen.name}   (-> Einheiten + Verträge)")
    einh_pdf = finde_pdf(ordner, "einheiten")
    if einh_pdf and einh_pdf not in (pdf_personen, pdf_flaechen):
        print(f"  Hinweis       : '{einh_pdf.name}' (Flächenstamm) wird NICHT verwendet "
              f"– Einheiten kommen aus dem Karteiblatt.")

    csv_personen  = ordner / f"{objekt} Personen_Import.csv"
    csv_einheiten = ordner / f"{objekt} Einheiten.csv"
    csv_vertraege = ordner / f"{objekt}-Vertraege.csv"

    print()
    imp.extrahiere_personen(pdf_personen, csv_personen)
    imp.extrahiere_flaechen(pdf_flaechen, objekt, csv_einheiten, csv_vertraege)

    print("\n  Fertig. Erzeugte Dateien:")
    for c in (csv_personen, csv_einheiten, csv_vertraege):
        print(f"    {c.name}")


if __name__ == "__main__":
    main()
