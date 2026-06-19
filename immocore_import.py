"""
IMMOCORE Import-Tool
====================
Automatisiert den dreistufigen Massenimport:
  Schritt 1 – PDFs extrahieren  → Personen-CSV, Einheiten-CSV, Verträge-CSV (Platzhalter)
  Schritt 2 – Verträge abgleichen → Verträge-CSV (finale Personnummern)

Aufruf:
  python immocore_import.py
"""

import csv
import io
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Windows-Konsole auf UTF-8 setzen
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

try:
    import pdfplumber
except ImportError:
    print("FEHLER: pdfplumber nicht installiert.")
    print("  Bitte ausführen: pip install pdfplumber")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def frage_pfad(bezeichnung: str, muss_existieren=True) -> Path:
    while True:
        eingabe = input(f"  {bezeichnung}: ").strip().strip('"')
        p = Path(eingabe)
        if muss_existieren and not p.exists():
            print(f"  ! Datei nicht gefunden: {p}")
            continue
        return p


def frage_text(bezeichnung: str, standard="") -> str:
    hinweis = f" [{standard}]" if standard else ""
    eingabe = input(f"  {bezeichnung}{hinweis}: ").strip()
    return eingabe if eingabe else standard


def trennlinie(titel=""):
    breite = 60
    if titel:
        print(f"\n{'- ' * 2} {titel} " + "-" * max(0, breite - len(titel) - 6))
    else:
        print("-" * breite)


# ---------------------------------------------------------------------------
# Schritt 1a – Personen aus PDF extrahieren
# ---------------------------------------------------------------------------

ANREDEN   = {"Firma", "Frau", "Herr", "Eheleute", "Herr und Frau", "Herren", "Damen", "Familie"}
TITEL_RE  = re.compile(r'^(Dr\.|Prof\.|Prof\.Dr\.|Dipl\.-Ing\.|Ing\.|Mag\.)\s+', re.I)
# PLZ muss mit Buchstaben beginnen (Stadtname), damit Telefon "06181 976624" nicht matcht
PLZ_RE    = re.compile(r'^(\d{5})\s+([A-ZÄÖÜa-zäöüß].+)$')
PHONE_RE  = re.compile(r'^[\d\s\+\-\/\(\)]{6,}$')
IBAN_RE   = re.compile(r'IBAN\.*:\s*([A-Z]{2}\d{2}[A-Z0-9]+)')
PERSON_RE = re.compile(r'^Person:\s+(\d+)\s+\+(\d+)')


def ist_telefon(zeile):
    return bool(PHONE_RE.match(zeile.strip())) and '@' not in zeile


def zerlege_name(voll):
    m = TITEL_RE.match(voll)
    titel = ""
    if m:
        titel = m.group(1)
        voll = voll[m.end():]
    teile = voll.strip().split()
    if not teile:
        return titel, "", ""
    return titel, " ".join(teile[:-1]), teile[-1]


def _block_linke_spalte(page):
    """Gibt den Anschrift-Block nur aus der linken Spalte zurück (verhindert Anschrift-2-Merge)."""
    try:
        words = page.extract_words()
        anschrift_top = ustid_top = None
        for w in words:
            if anschrift_top is None and w["text"] == "Anschrift":
                anschrift_top = w["top"]
            if ustid_top is None and w["text"].startswith("USt-ID"):
                ustid_top = w["top"]
        if anschrift_top is None or ustid_top is None:
            return None
        # Erste Zeile UNTERHALB von "Anschrift 1" finden (damit der Header selbst nicht im Block landet)
        block_start = anschrift_top + 14  # Fallback: eine Zeilenhöhe (~14pt) überspringen
        for w in sorted(words, key=lambda w: w["top"]):
            if w["top"] > anschrift_top + 5 and w["text"] not in ("Anschrift", "1", "2"):
                block_start = w["top"]
                break
        # Linke Spalte: x < 220 (rechte Anschrift-2-Spalte beginnt bei ~231)
        cropped = page.crop((0, block_start, 220, ustid_top))
        return [z.strip() for z in (cropped.extract_text() or "").splitlines() if z.strip()]
    except Exception:
        return None


def parse_person_seite(text, page=None):
    zeilen = [z.strip() for z in text.splitlines() if z.strip()]

    altpk = ""
    for z in zeilen:
        m = PERSON_RE.search(z)
        if m:
            altpk = f"{m.group(1)}+{m.group(2)}"
            break
    if not altpk:
        return None

    try:
        start = next(i for i, z in enumerate(zeilen) if z.startswith("Anschrift 1"))
        ende  = next(i for i, z in enumerate(zeilen) if z.startswith("USt-ID:"))
    except StopIteration:
        return None

    # Geometrische Extraktion der linken Spalte wenn Seitenobjekt vorhanden
    if page is not None:
        block_links = _block_linke_spalte(page)
        block = block_links if block_links is not None else zeilen[start+1:ende]
    else:
        block = zeilen[start+1:ende]

    iban = ""
    for z in zeilen[ende:]:
        m = IBAN_RE.search(z)
        if m:
            iban = m.group(1)
            break

    anrede = next((z for z in block if z in ANREDEN), "")
    ist_firma = anrede == "Firma"

    firma = vorname1 = nachname1 = anrede1 = titel1 = ""
    vorname2 = nachname2 = anrede2 = titel2 = ""
    anschrift = plz = ort = email1 = email2 = tel1 = tel2 = ""

    rest = block[block.index(anrede)+1:] if anrede in block else block

    namenszeilen = []
    emails, telefone = [], []
    addr_gestartet = False

    for z in rest:
        if PLZ_RE.match(z):
            addr_gestartet = True
            m = PLZ_RE.match(z)
            plz, ort = m.group(1), m.group(2)
        elif addr_gestartet:
            if '@' in z:
                emails.append(z)
            elif ist_telefon(z):
                telefone.append(z)
        else:
            if '@' in z:
                emails.append(z)
                addr_gestartet = True
            elif ist_telefon(z):
                telefone.append(z)
                addr_gestartet = True
            elif re.search(r'\s\d+\w*$', z) and not PLZ_RE.match(z):
                # Straße erkennen: endet auf Hausnummer (z.B. "Dürerstraße 17f", "Am Markt 3")
                anschrift = z
                addr_gestartet = True
            elif anschrift == "":
                namenszeilen.append(z)
            else:
                anschrift = z

    if ist_firma:
        firma = namenszeilen[0] if namenszeilen else ""
        if len(namenszeilen) > 1 and not anschrift:
            anschrift = namenszeilen[1]
    elif anrede in ("Eheleute", "Herr und Frau", "Herren", "Damen", "Familie"):
        # Wenn beide Namen auf einer Zeile stehen ("Maria und Peter Schmidt"),
        # aufteilen – sonst landen beide Vornamen in vorname1.
        # Fall "Maria und Peter Schmidt": teile[0] hat keinen Nachnamen →
        # Nachnamen aus teile[1] übernehmen.
        if len(namenszeilen) == 1 and " und " in namenszeilen[0]:
            teile = namenszeilen[0].split(" und ", 1)
            t0, t1 = teile[0].strip(), teile[1].strip()
            # Wenn erster Teil nur ein Wort hat (nur Vorname), Nachname aus zweitem Teil ergänzen
            if t0 and " " not in t0:
                nachname_geteilt = t1.rsplit(" ", 1)[-1] if " " in t1 else ""
                if nachname_geteilt:
                    t0 = f"{t0} {nachname_geteilt}"
            namenszeilen = [t0, t1]
        if len(namenszeilen) >= 2:
            titel1, vorname1, nachname1 = zerlege_name(namenszeilen[0])
            titel2, vorname2, nachname2 = zerlege_name(namenszeilen[1])
        if anrede == "Herr und Frau":
            anrede1, anrede2 = "Herr", "Frau"
        elif anrede == "Herren":
            anrede1, anrede2 = "Herr", "Herr"
        elif anrede == "Damen":
            anrede1, anrede2 = "Frau", "Frau"
        else:
            anrede1, anrede2 = "", ""  # Eheleute – Geschlecht nicht eindeutig
        for nz in namenszeilen[2:]:
            if not anschrift:
                anschrift = nz
    else:
        anrede1 = anrede
        if namenszeilen:
            titel1, vorname1, nachname1 = zerlege_name(namenszeilen[0])
        for nz in namenszeilen[1:]:
            if not anschrift:
                anschrift = nz

    email1 = emails[0]  if emails   else ""
    email2 = emails[1]  if len(emails)   > 1 else ""
    tel1   = telefone[0] if telefone else ""
    tel2   = telefone[1] if len(telefone) > 1 else ""

    return {
        "person_typ": 100, "ist_firma": "TRUE" if ist_firma else "FALSE",
        "Firma": firma, "Anrede": anrede,
        "Anrede1": anrede1, "Titel1": titel1, "Vorname1": vorname1, "Nachname1": nachname1,
        "Anrede2": anrede2, "Titel2": titel2, "Vorname2": vorname2, "Nachname2": nachname2,
        "Anschrift": anschrift, "PLZ": plz, "Ort": ort,
        "Email1": email1, "Email2": email2, "Telefon1": tel1, "Telefon2": tel2,
        "IBAN": iban, "ALTPK": altpk,
    }


PERSONEN_HEADER = [
    "person_typ","ist_firma","Firma","Anrede","Anrede1","Titel1",
    "Vorname1","Nachname1","Anrede2","Titel2","Vorname2","Nachname2",
    "Anschrift","PLZ","Ort","Email1","Email2","Telefon1","Telefon2",
    "IBAN","ALTPK",
]

PERSONEN_KOMMENTAR = "# person_typ: 100=Eigentümer | 200=Mieter | 300=Kreditor | 400=Sonstiges"


def extrahiere_personen(pdf_pfad: Path, ziel_csv: Path):
    print(f"  Lese {pdf_pfad.name} ...")
    personen = []
    with pdfplumber.open(pdf_pfad) as pdf:
        gesamt = len(pdf.pages)
        for i, seite in enumerate(pdf.pages):
            text = seite.extract_text() or ""
            row = parse_person_seite(text, page=seite)
            if row:
                personen.append(row)
            if (i + 1) % 100 == 0:
                print(f"    {i+1}/{gesamt} Seiten ...")

    with open(ziel_csv, "w", newline="", encoding="utf-8-sig") as f:
        f.write(PERSONEN_KOMMENTAR + "\n")
        w = csv.DictWriter(f, fieldnames=PERSONEN_HEADER, delimiter=";")
        w.writeheader()
        w.writerows(personen)

    print(f"  OK – {len(personen)} Personen -> {ziel_csv.name}")
    return len(personen)


# ---------------------------------------------------------------------------
# Schritt 1b – Einheiten + Verträge aus FlächenSoll-PDF extrahieren
# ---------------------------------------------------------------------------

EINHEIT_TYPEN = {
    "Wohnung": 100, "Gewerbe": 200, "Einzelhandel": 200,
    "Stellplatz": 300, "Tiefgarage": 300, "Garage": 300,
}
FLAECHE_RE  = re.compile(r'^Fl[äa]che\s+(\d+)\s+(.+?)\s+(Wohnung|Gewerbe|Einzelhandel|Stellplatz|Tiefgarage|Garage|Sonstiges)\s*$')
BELEG_RE    = re.compile(r'^Belegung\s+(\d{2}\.\d{2}\.\d{4})\s*-')
SOLL_RE     = re.compile(r'^(\d{2}\.\d{2}\.\d{4})\s+(9[012]\d)\s+\d+\s+\S+\s+\d+\s+\S+\s+([\d\.,]+)\s+EUR')
PLZ_FLRE    = re.compile(r'^\d{5}\s+')
OBJEKT_RE   = re.compile(r'^Objekt\s+0*(\d+)\s+')


def parse_datum(s):
    try:
        return datetime.strptime(s.strip(), "%d.%m.%Y")
    except ValueError:
        return None


def parse_betrag(s):
    # Tausenderpunkt entfernen, Komma als Dezimalzeichen behalten -> "1.234,56" -> "1234,56"
    return s.replace(".", "")


def bereinige_lage(s):
    """Korrigiert Tippfehler in der Lage, z.B. '3, OG' -> '3. OG'"""
    # Komma vor OG/UG/EG/DG durch Punkt ersetzen: "3, OG" -> "3. OG"
    s = re.sub(r'(\d+),\s*(OG|UG|EG|DG|KG)', r'\1. \2', s)
    # Mehrfache Leerzeichen normalisieren
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def parse_flaeche_seite(text, objekt_nr, altpk_prefix):
    zeilen = [z.strip() for z in text.splitlines() if z.strip()]

    flaeche_nr = bez = einheit_typ = lage = ""
    strasse = plz = ort = ""
    belegung_ab = beleg_person = ""
    # Alle Einträge je Kontoklasse sammeln, am Ende nur den neuesten nehmen
    soll_alle = {}  # kkl -> list of (datum, datum_str, betrag)

    i = 0
    while i < len(zeilen):
        z = zeilen[i]

        m = FLAECHE_RE.match(z)
        if m:
            flaeche_nr  = m.group(1)
            bez         = m.group(2).strip()
            einheit_typ = EINHEIT_TYPEN.get(m.group(3), 400)
            i += 1
            continue

        if flaeche_nr and not strasse:
            if (re.search(r'\d', z) and not PLZ_FLRE.match(z)
                    and not z.startswith(("Info","Gr","Belegung","MwSt","Soll","Liste","Objekt","01.0"))):
                strasse = z

        if PLZ_FLRE.match(z) and flaeche_nr and not plz:
            teile = z.split(None, 1)
            plz, ort = teile[0], (teile[1] if len(teile) > 1 else "")

        if z.startswith("Info "):
            rest = z[5:].strip()
            if rest.startswith("Haus"):
                # Altes Format: "Info Haus 1" → Lage steht auf der nächsten Zeile
                if i + 1 < len(zeilen):
                    lage = bereinige_lage(zeilen[i + 1])
            else:
                # Neues Format: "Info EG links" / "Info 1. OG" → Lage direkt dahinter
                lage = bereinige_lage(rest)

        m = BELEG_RE.match(z)
        if m and not belegung_ab:
            belegung_ab = m.group(1)
            mn = re.search(r'\b(\d{3})\b', z[m.end():])
            if mn:
                beleg_person = f"{altpk_prefix}+{mn.group(1)}"
            elif i + 1 < len(zeilen):
                mn2 = re.match(r'^\s*(\d{3})\b', zeilen[i+1])
                if mn2:
                    beleg_person = f"{altpk_prefix}+{mn2.group(1)}"

        m = SOLL_RE.match(z)
        if m:
            datum  = parse_datum(m.group(1))
            kkl    = m.group(2)
            betrag = parse_betrag(m.group(3))
            if datum and (kkl == "900" or "911" <= kkl <= "919"):
                soll_alle.setdefault(kkl, []).append((datum, m.group(1), betrag))
        i += 1

    # Neuesten Eintrag je Kontoklasse wählen
    sollbetraege = []
    for kkl, eintraege in soll_alle.items():
        neuester = max(eintraege, key=lambda x: x[0])
        sollbetraege.append({
            "datum":  neuester[1],
            "kkl":    kkl,
            "betrag": neuester[2],
        })

    if not flaeche_nr:
        return None, []

    einheit = {
        "Objektnummer":  objekt_nr,
        "Eingang":       strasse,
        "Flächennummer": flaeche_nr,
        "Bez. Einheit":  bez,
        "Einheit-Typ":   einheit_typ,
        "Lage":          lage,
    }
    vertraege = [
        {
            "Fl Nr.":       flaeche_nr,
            "Personnummer": beleg_person,
            "ET ab":        belegung_ab,
            "SA":           s["kkl"],
            "Betrag":       s["betrag"],
            "SA ab":        s["datum"],
        }
        for s in sollbetraege
    ]
    return einheit, vertraege


EINHEITEN_HEADER = ["Objektnummer","Eingang","Flächennummer","Bez. Einheit","Einheit-Typ","Lage"]
EINHEITEN_KOMMENTAR = "# Einheit-Typ: 100=Wohnung | 200=Gewerbe | 300=Stellplatz | 400=Sonstiges"
VERTRAEGE_HEADER  = ["Fl Nr.","Personnummer","ET ab","SA","Betrag","SA ab"]


def extrahiere_flaechen(pdf_pfad: Path, objekt_nr, ziel_einheiten: Path, ziel_vertraege: Path):
    print(f"  Lese {pdf_pfad.name} ...")
    einheiten, vertraege = [], []
    altpk_prefix = None

    with pdfplumber.open(pdf_pfad) as pdf:
        gesamt = len(pdf.pages)
        # ALTPK-Prefix aus erster Seite ermitteln (Objektnummer aus PDF)
        erste_seite = pdf.pages[0].extract_text() or ""
        for z in erste_seite.splitlines():
            m = OBJEKT_RE.match(z.strip())
            if m:
                altpk_prefix = m.group(1)
                print(f"  Objekt-Prefix erkannt: {altpk_prefix}")
                break
        if not altpk_prefix:
            altpk_prefix = str(objekt_nr)
            print(f"  Objekt-Prefix nicht erkannt, verwende: {altpk_prefix}")

        for i, seite in enumerate(pdf.pages):
            text = seite.extract_text() or ""
            e, v = parse_flaeche_seite(text, objekt_nr, altpk_prefix)
            if e:
                einheiten.append(e)
                vertraege.extend(v)
            if (i + 1) % 100 == 0:
                print(f"    {i+1}/{gesamt} Seiten ...")

    with open(ziel_einheiten, "w", newline="", encoding="utf-8-sig") as f:
        f.write(EINHEITEN_KOMMENTAR + "\n")
        w = csv.DictWriter(f, fieldnames=EINHEITEN_HEADER, delimiter=";")
        w.writeheader()
        w.writerows(einheiten)

    with open(ziel_vertraege, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=VERTRAEGE_HEADER, delimiter=";")
        w.writeheader()
        w.writerows(vertraege)

    print(f"  OK – {len(einheiten)} Einheiten  -> {ziel_einheiten.name}")
    print(f"  OK – {len(vertraege)} Vertragszeilen (SA 900+911, ab 01.01.2026) -> {ziel_vertraege.name}")
    return len(einheiten), len(vertraege)


# ---------------------------------------------------------------------------
# Schritt 2 – Verträge mit Personen-Ergebnis zusammenführen
# ---------------------------------------------------------------------------

def fuehre_zusammen(ergebnis_csv: Path, vertraege_csv: Path, ziel_csv: Path):
    print(f"  Lese {ergebnis_csv.name} ...")
    with open(ergebnis_csv, encoding="utf-8-sig") as f:
        ergebnis = list(csv.DictReader(f, delimiter=";"))

    # Mapping Personenidentität → neue Personennummer
    id_zu_nr = {}
    for r in ergebnis:
        nr = r.get("personennummer", "").strip()
        if not nr:
            continue
        key = ("firma", r["Firma"].strip()) if r["ist_firma"] == "TRUE" \
              else ("person", r["Nachname1"].strip(), r["Vorname1"].strip())
        id_zu_nr[key] = nr

    # Alle ALTPK → neue Personennummer
    altpk_zu_nr = {}
    for r in ergebnis:
        altpk = r["ALTPK"].strip()
        nr    = r.get("personennummer", "").strip()
        if nr:
            altpk_zu_nr[altpk] = nr
        else:
            key = ("firma", r["Firma"].strip()) if r["ist_firma"] == "TRUE" \
                  else ("person", r["Nachname1"].strip(), r["Vorname1"].strip())
            altpk_zu_nr[altpk] = id_zu_nr.get(key, "")

    # Verträge einlesen und ersetzen
    with open(vertraege_csv, encoding="utf-8-sig") as f:
        vertraege = list(csv.DictReader(f, delimiter=";"))

    nicht_gefunden = []
    for v in vertraege:
        altpk = v["Personnummer"]
        neue  = altpk_zu_nr.get(altpk, "")
        if not neue:
            nicht_gefunden.append(altpk)
        v["Personnummer"] = neue

    with open(ziel_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=VERTRAEGE_HEADER, delimiter=";")
        w.writeheader()
        w.writerows(vertraege)

    print(f"  OK – {len(vertraege)} Zeilen -> {ziel_csv.name}")
    if nicht_gefunden:
        fehlend = sorted(set(nicht_gefunden))
        print(f"  WARNUNG: {len(fehlend)} ALTPK ohne Personennummer: {fehlend}")
    else:
        print("  Alle Personennummern erfolgreich zugeordnet.")


# ---------------------------------------------------------------------------
# Hauptmenü
# ---------------------------------------------------------------------------

def frage_ordner(bezeichnung: str) -> Path:
    """Fragt nach einem Ordnerpfad und prüft ob er existiert."""
    while True:
        eingabe = input(f"  {bezeichnung}: ").strip().strip('"')
        if not eingabe:
            print("  ! Bitte einen Ordnerpfad eingeben.")
            continue
        p = Path(eingabe)
        if not p.exists():
            print(f"  ! Ordner nicht gefunden: {p}")
            continue
        if not p.is_dir():
            print(f"  ! Das ist kein Ordner: {p}")
            continue
        return p


def suche_pdf(ordner: Path, suchbegriff: str) -> Path | None:
    """Sucht im Ordner nach einer PDF die den Suchbegriff im Namen enthält."""
    treffer = [f for f in ordner.glob("*.pdf") if suchbegriff.lower() in f.name.lower()]
    return treffer[0] if len(treffer) == 1 else None


def schritt_1():
    trennlinie("Schritt 1 – PDFs extrahieren")

    ordner = frage_ordner("Ordner mit den PDF-Dateien (z.B. C:\\Import\\AQA)")

    objekt_nr = frage_text("Objektnummer in IMMOCORE (z.B. 10007)")
    if not objekt_nr:
        print("  ! Objektnummer darf nicht leer sein.")
        return

    # PDFs automatisch erkennen oder per Nummer wählen
    print()
    print("  Suche PDFs im Ordner ...")
    alle_pdfs = sorted(ordner.glob("*.pdf"))

    def waehle_pdf(bezeichnung: str, suchbegriff: str) -> Path:
        """Automatisch per Suchbegriff oder per Nummerauswahl aus der Liste."""
        auto = suche_pdf(ordner, suchbegriff)
        if auto:
            print(f"  {bezeichnung} gefunden: {auto.name}")
            return auto
        # Manuelle Auswahl per Nummer
        if alle_pdfs:
            print(f"\n  Welche PDF ist die {bezeichnung}?")
            for i, p in enumerate(alle_pdfs):
                print(f"    [{i+1}] {p.name}")
        while True:
            eingabe = input(f"  Nummer eingeben: ").strip()
            if eingabe.isdigit():
                idx = int(eingabe) - 1
                if 0 <= idx < len(alle_pdfs):
                    return alle_pdfs[idx]
                print(f"  ! Bitte eine Zahl zwischen 1 und {len(alle_pdfs)} eingeben.")
            else:
                # Fallback: vollständiger Dateiname
                p = Path(eingabe.strip('"'))
                if not p.is_absolute():
                    p = ordner / p
                if p.exists():
                    return p
                print(f"  ! Datei nicht gefunden: {p}")

    pdf_personen = waehle_pdf("Personenliste-PDF", "Personenliste")
    pdf_flaechen = waehle_pdf("FlächenSoll-PDF",   "laechen")

    csv_personen  = ordner / f"{objekt_nr} Personen_Import.csv"
    csv_einheiten = ordner / f"{objekt_nr} Einheiten.csv"
    csv_vertraege = ordner / f"{objekt_nr}-Vertraege.csv"

    print()
    extrahiere_personen(pdf_personen, csv_personen)
    extrahiere_flaechen(pdf_flaechen, objekt_nr, csv_einheiten, csv_vertraege)

    print()
    trennlinie()
    print("  Dateien erstellt in:", ordner)
    print(f"    {csv_personen.name}")
    print(f"    {csv_einheiten.name}")
    print(f"    {csv_vertraege.name}")
    print()
    print("  Naechste Schritte:")
    print("  1. Personen importieren  -> IMMOCORE liefert Ergebnis-CSV zurueck")
    print("  2. Einheiten importieren -> IMMOCORE")
    print(f"  3. Ergebnis-CSV in denselben Ordner legen: {ordner}")
    print("  4. Dieses Tool erneut starten -> Schritt 2 waehlen")


def schritt_2():
    trennlinie("Schritt 2 – Verträge finalisieren")

    ordner = frage_ordner("Ordner mit den Import-Dateien (gleicher Ordner wie Schritt 1)")

    def waehle_csv(bezeichnung: str, kandidaten: list) -> Path:
        """Wählt eine CSV: automatisch bei einem Treffer, sonst Nummerauswahl."""
        if len(kandidaten) == 1:
            print(f"  {bezeichnung} gefunden: {kandidaten[0].name}")
            return kandidaten[0]
        alle_csvs = sorted(ordner.glob("*.csv"))
        print(f"\n  Welche Datei ist die {bezeichnung}?")
        liste = kandidaten if kandidaten else alle_csvs
        for i, p in enumerate(liste):
            print(f"    [{i+1}] {p.name}")
        while True:
            eingabe = input("  Nummer eingeben: ").strip()
            if eingabe.isdigit():
                idx = int(eingabe) - 1
                if 0 <= idx < len(liste):
                    return liste[idx]
                print(f"  ! Bitte eine Zahl zwischen 1 und {len(liste)} eingeben.")
            else:
                p = Path(eingabe.strip('"'))
                if not p.is_absolute():
                    p = ordner / p
                if p.exists():
                    return p
                print(f"  ! Datei nicht gefunden: {p}")

    # Ergebnis-CSV automatisch suchen
    ergebnis_kandidaten = sorted(set(
        list(ordner.glob("*ergebnis*.csv")) +
        list(ordner.glob("*Ergebnis*.csv"))
    ))
    ergebnis_csv = waehle_csv("Personen-Ergebnis-CSV von IMMOCORE", ergebnis_kandidaten)

    # Vertrags-CSV automatisch suchen (ohne _final)
    vertraege_kandidaten = [
        f for f in sorted(ordner.glob("*Vertraege*.csv"))
        if "_final" not in f.name
    ]
    vertraege_csv = waehle_csv("Vertraege-CSV aus Schritt 1", vertraege_kandidaten)

    ziel_csv = ordner / (vertraege_csv.stem + "_final.csv")

    print()
    fuehre_zusammen(ergebnis_csv, vertraege_csv, ziel_csv)

    print()
    print(f"  -> Fertig: {ziel_csv}")
    print("     Diese Datei in IMMOCORE als Vertraege importieren.")


def main():
    print()
    print("=" * 44)
    print("     IMMOCORE  Import-Tool  v1.0")
    print("=" * 44)

    while True:
        print()
        print("  [1]  Schritt 1 – PDFs extrahieren")
        print("       (Personen-, Einheiten- und Vertrags-CSV erzeugen)")
        print()
        print("  [2]  Schritt 2 – Verträge finalisieren")
        print("       (Personnummern aus IMMOCORE-Ergebnis eintragen)")
        print()
        print("  [0]  Beenden")
        print()

        wahl = input("  Auswahl: ").strip()

        if wahl == "1":
            schritt_1()
        elif wahl == "2":
            schritt_2()
        elif wahl == "0":
            print("\n  Auf Wiedersehen.")
            break
        else:
            print("  ! Ungültige Eingabe, bitte 0, 1 oder 2 eingeben.")


if __name__ == "__main__":
    main()
