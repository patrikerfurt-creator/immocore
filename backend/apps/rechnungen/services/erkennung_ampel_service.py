"""
Verifikations-Ampel für die OCR-Erkennung (Spec Kap. 5.2, Umbau v1.0).

Grundsatz: Rohe LLM-Konfidenz allein trägt KEINE grüne Ampel. Jedes prüfbare
Feld wird gegen harte Fakten validiert; die Validierung überstimmt die
LLM-Konfidenz. Ausschließlich hier die Logik — nicht im Model, nicht in Signals.

Eingabe `ocr_ergebnis`: {feld: {"wert": ..., "konfidenz": 0.0..1.0, ...}}.
Für die Rechenprobe darf `betrag_brutto` zusätzlich `netto`/`ust_betrag` tragen,
für den Kreditor eine `iban`.
Ausgabe: {"ampel", "gesamt_konfidenz", "felder": {feld: {...}}}.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings

# --- Schwellen (Spec 5.2.1) — global, optional je Objekt überschreibbar (B8) ---
AMPEL_GRUEN_AB = getattr(settings, "AMPEL_GRUEN_AB", 95)
AMPEL_GELB_AB = getattr(settings, "AMPEL_GELB_AB", 80)

KRITISCH = {"kreditor", "betrag_brutto", "rechnungsnummer"}


# ===========================================================================
# Konfidenz- und Ampel-Kombinationsregeln
# ===========================================================================

def feld_konfidenz(llm_konfidenz: float, validierung: str) -> float:
    """Kombiniert LLM-Selbstkonfidenz mit dem harten Validierungsergebnis."""
    if validierung == "fehler":
        return 0.0                        # harter Widerspruch → rot, überstimmt LLM
    if validierung == "ok":
        return max(llm_konfidenz, 0.95)   # harte Bestätigung → mind. grün
    return llm_konfidenz                  # 'warnung'/'keine': LLM-Basiswert


def _ampel(feld: dict) -> str:
    """Ampelfarbe eines Feldes. 'warnung' kann nie grün werden (muss bestätigt
    werden, Spec 5.2.6)."""
    v = feld.get("validierung", "keine")
    if v == "fehler":
        return "rot"
    konf = feld.get("konfidenz", 0.0) * 100
    if v == "warnung":
        return "gelb" if konf >= AMPEL_GELB_AB else "rot"
    if konf >= AMPEL_GRUEN_AB:
        return "gruen"
    if konf >= AMPEL_GELB_AB:
        return "gelb"
    return "rot"


def gesamt_ampel(felder: dict) -> tuple[str, float]:
    """Veto-Logik (kein Durchschnitt). Gesamtwert = Minimum der kritischen
    Feld-Konfidenzen. Ein rotes kritisches Feld → Gesamt rot."""
    if any(
        f.get("validierung") == "fehler" and n in KRITISCH
        for n, f in felder.items()
    ):
        return "rot", 0.0
    krit_konf = [f["konfidenz"] for n, f in felder.items() if n in KRITISCH]
    gesamt = round(min(krit_konf) * 100, 2) if krit_konf else 0.0
    if gesamt >= AMPEL_GRUEN_AB and all(_ampel(f) == "gruen" for f in felder.values()):
        return "gruen", gesamt
    if gesamt >= AMPEL_GELB_AB and not any(_ampel(f) == "rot" for f in felder.values()):
        return "gelb", gesamt
    return ("gelb" if gesamt >= AMPEL_GELB_AB else "rot"), gesamt


# ===========================================================================
# Deterministische Feld-Validierungen (Spec 5.2.2)
# ===========================================================================

def _dec(wert):
    if wert is None or wert == "":
        return None
    try:
        return Decimal(str(wert))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _json_safe(wert):
    """Decimal/date → str, damit erkennung_details als JSONField speicherbar ist."""
    if isinstance(wert, Decimal):
        return str(wert)
    if isinstance(wert, (date, datetime)):
        return wert.isoformat()
    return wert


def iban_gueltig(iban: str) -> bool:
    """IBAN-Format + Prüfziffer (ISO 13616, mod-97)."""
    if not iban:
        return False
    cleaned = iban.replace(" ", "").upper()
    if len(cleaned) < 15 or len(cleaned) > 34 or not cleaned[:2].isalpha():
        return False
    umgestellt = cleaned[4:] + cleaned[:4]
    zahl = ""
    for ch in umgestellt:
        if ch.isdigit():
            zahl += ch
        elif ch.isalpha():
            zahl += str(ord(ch) - 55)
        else:
            return False
    try:
        return int(zahl) % 97 == 1
    except ValueError:
        return False


def validiere_kreditor(iban: str) -> tuple[str, str]:
    """(validierung, hinweis). Format+Prüfziffer und Treffer in Stammdaten."""
    if not iban:
        return "warnung", "Keine IBAN zur Prüfung vorhanden."
    if not iban_gueltig(iban):
        return "fehler", "IBAN ungültig (Format/Prüfziffer)."
    from ..models import Kreditor
    from apps.personen.models import Person
    cleaned = iban.replace(" ", "").upper()
    treffer = (
        Kreditor.objects.filter(iban=cleaned).exists()
        or Person.objects.filter(ibans__contains=cleaned).exists()
    )
    if treffer:
        return "ok", "IBAN in Stammdaten gefunden."
    return "warnung", "IBAN gültig, aber nicht in Stammdaten."


def validiere_betrag_brutto(brutto, netto=None, ust_betrag=None) -> tuple[str, str]:
    b = _dec(brutto)
    if b is None or b <= 0:
        return "fehler", "Bruttobetrag fehlt oder ist nicht positiv."
    n, u = _dec(netto), _dec(ust_betrag)
    if n is not None and u is not None:
        if abs((n + u) - b) > Decimal("0.02"):
            return "fehler", f"Rechenprobe netto+USt ({n + u}) ≠ brutto ({b})."
    return "ok", "Bruttobetrag plausibel."


def validiere_rechnungsnummer(nummer, kreditor_id=None, rechnung_id=None) -> tuple[str, str]:
    if not nummer:
        return "fehler", "Rechnungsnummer fehlt."
    if kreditor_id:
        from ..models import Rechnung
        qs = Rechnung.objects.filter(kreditor_id=kreditor_id, rechnungsnummer=nummer)
        if rechnung_id:
            qs = qs.exclude(pk=rechnung_id)
        if qs.exists():
            return "fehler", "Rechnungsnummer für diesen Kreditor bereits erfasst."
    return "ok", "Rechnungsnummer frei."


def validiere_rechnungsdatum(datum, heute=None) -> tuple[str, str]:
    if not datum:
        return "warnung", "Kein Rechnungsdatum."
    if isinstance(datum, str):
        try:
            datum = date.fromisoformat(datum)
        except ValueError:
            return "warnung", "Rechnungsdatum nicht lesbar."
    heute = heute or date.today()
    if datum > heute:
        return "warnung", "Rechnungsdatum liegt in der Zukunft."
    if datum < heute - timedelta(days=730):
        return "warnung", "Rechnungsdatum älter als 24 Monate."
    return "ok", "Rechnungsdatum plausibel."


def validiere_skonto(prozent, betrag, faellig_bis, brutto, rechnungsdatum=None) -> tuple[str, str]:
    p, s, b = _dec(prozent), _dec(betrag), _dec(brutto)
    if p is None and s is None and faellig_bis is None:
        return "keine", ""
    if p is not None and s is not None and b is not None:
        erwartet = (b * p / Decimal("100")).quantize(Decimal("0.01"))
        if abs(erwartet - s) > Decimal("0.02"):
            return "warnung", f"Skontobetrag {s} weicht von {erwartet} (aus %) ab."
    if faellig_bis and rechnungsdatum:
        fb = date.fromisoformat(faellig_bis) if isinstance(faellig_bis, str) else faellig_bis
        rd = date.fromisoformat(rechnungsdatum) if isinstance(rechnungsdatum, str) else rechnungsdatum
        if fb < rd:
            return "warnung", "Skontofrist liegt vor dem Rechnungsdatum."
    return "ok", "Skonto konsistent."


def validiere_betrag_haushaltsnah(wert, brutto) -> tuple[str, str]:
    w, b = _dec(wert), _dec(brutto)
    if w is None:
        return "keine", ""
    if b is not None and w > b:
        return "fehler", "§35a-Betrag übersteigt den Bruttobetrag."
    return "ok", "§35a-Betrag plausibel."


def validiere_kostenverursacher(einheit_id, objekt_id) -> tuple[str, str]:
    if not einheit_id:
        return "keine", ""
    from apps.objekte.models import Einheit
    einheit = Einheit.objects.filter(pk=einheit_id).values_list("objekt_id", flat=True).first()
    if einheit is None:
        return "fehler", "Einheit nicht gefunden."
    if objekt_id and str(einheit) != str(objekt_id):
        return "fehler", "Einheit gehört nicht zum Objekt der Rechnung."
    return "ok", "Kostenverursacher gehört zum Objekt."


# ===========================================================================
# Orchestrierung
# ===========================================================================

_VALIDATOR_MAP = {
    "kreditor": lambda o, obj, r: validiere_kreditor(
        o.get("kreditor", {}).get("iban") or o.get("kreditor", {}).get("wert")
    ),
    "betrag_brutto": lambda o, obj, r: validiere_betrag_brutto(
        o.get("betrag_brutto", {}).get("wert"),
        o.get("betrag_netto", {}).get("wert"),
        o.get("betrag_brutto", {}).get("ust_betrag") or o.get("ust_betrag", {}).get("wert"),
    ),
    "rechnungsnummer": lambda o, obj, r: validiere_rechnungsnummer(
        o.get("rechnungsnummer", {}).get("wert"),
        kreditor_id=getattr(r, "kreditor_id", None) if r else o.get("kreditor", {}).get("id"),
        rechnung_id=getattr(r, "id", None) if r else None,
    ),
    "rechnungsdatum": lambda o, obj, r: validiere_rechnungsdatum(
        o.get("rechnungsdatum", {}).get("wert")
    ),
    "skonto": lambda o, obj, r: validiere_skonto(
        o.get("skonto_prozent", {}).get("wert"),
        o.get("skonto_betrag", {}).get("wert"),
        o.get("skonto_faellig_bis", {}).get("wert"),
        o.get("betrag_brutto", {}).get("wert"),
        o.get("rechnungsdatum", {}).get("wert"),
    ),
    "betrag_haushaltsnah": lambda o, obj, r: validiere_betrag_haushaltsnah(
        o.get("betrag_haushaltsnah", {}).get("wert"),
        o.get("betrag_brutto", {}).get("wert"),
    ),
    "kostenverursacher": lambda o, obj, r: validiere_kostenverursacher(
        o.get("kostenverursacher", {}).get("wert"),
        getattr(obj, "id", None),
    ),
}


def ampel_eingabe_aus_ocr(felder: dict, rechnung=None) -> dict:
    """Übersetzt die OCR-Feldstruktur {feld: {wert, konfidenz}} in die
    Eingabe für berechne_ampel (kritische Feldnamen, USt aus netto·satz)."""
    felder = felder or {}

    def g(k):
        return felder.get(k) or {}

    netto = _dec(g("betrag_netto").get("wert"))
    satz = _dec(g("mwst_satz").get("wert"))
    ust = (netto * satz / Decimal("100")).quantize(Decimal("0.01")) \
        if netto is not None and satz is not None else None

    eingabe = {
        "kreditor": {
            "wert": g("lieferant_name").get("wert"),
            "konfidenz": g("lieferant_name").get("konfidenz", 0.0),
            "iban": g("lieferant_iban").get("wert"),
        },
        "betrag_brutto": {
            "wert": g("betrag_brutto").get("wert"),
            "konfidenz": g("betrag_brutto").get("konfidenz", 0.0),
            "ust_betrag": str(ust) if ust is not None else None,
        },
        "betrag_netto": {"wert": g("betrag_netto").get("wert")},
        "rechnungsnummer": {
            "wert": g("rechnungsnummer").get("wert"),
            "konfidenz": g("rechnungsnummer").get("konfidenz", 0.0),
            "id": getattr(rechnung, "kreditor_id", None) if rechnung else None,
        },
        "rechnungsdatum": {
            "wert": g("rechnungsdatum").get("wert"),
            "konfidenz": g("rechnungsdatum").get("konfidenz", 0.0),
        },
    }
    for k in ("skonto_prozent", "skonto_betrag", "skonto_faellig_bis", "betrag_haushaltsnah"):
        if g(k).get("wert") not in (None, ""):
            eingabe[k] = {"wert": g(k).get("wert"), "konfidenz": g(k).get("konfidenz", 0.0)}
    return eingabe


def berechne_ampel(ocr_ergebnis: dict, objekt=None, rechnung=None) -> dict:
    """Berechnet je Feld Validierung + Konfidenz + Ampel und die Gesamtampel.
    Wird beim OCR-Aufruf und nach jeder Feldänderung erneut aufgerufen."""
    ocr_ergebnis = ocr_ergebnis or {}
    felder: dict[str, dict] = {}

    for feld, validator in _VALIDATOR_MAP.items():
        # Skonto/§35a/Kostenverursacher nur bewerten, wenn im OCR-Ergebnis vertreten
        quelle_key = {
            "skonto": "skonto_prozent",
            "betrag_haushaltsnah": "betrag_haushaltsnah",
            "kostenverursacher": "kostenverursacher",
        }.get(feld, feld)
        if feld not in KRITISCH and quelle_key not in ocr_ergebnis:
            continue

        validierung, hinweis = validator(ocr_ergebnis, objekt, rechnung)
        if validierung == "keine":
            continue
        llm = float(ocr_ergebnis.get(quelle_key, {}).get("konfidenz", 0.0) or 0.0)
        konf = feld_konfidenz(llm, validierung)
        felder[feld] = {
            "wert": _json_safe(ocr_ergebnis.get(quelle_key, {}).get("wert")),
            "llm_konfidenz": llm,
            "validierung": validierung,
            "hinweis": hinweis,
            "konfidenz": konf,
        }
        felder[feld]["ampel"] = _ampel(felder[feld])

    ampel, gesamt = gesamt_ampel(felder)
    return {"ampel": ampel, "gesamt_konfidenz": gesamt, "felder": felder}


def _rechnung_zu_felder(rechnung) -> dict:
    """Baut aus den (manuell erfassten) Rechnungsfeldern die OCR-Feldstruktur.
    Manuelle Eingabe → LLM-Konfidenz 1.0; die deterministischen Prüfungen
    (IBAN, Rechenprobe, Duplikat) gaten trotzdem."""
    kred = rechnung.kreditor if rechnung.kreditor_id else None
    rd = rechnung.rechnungsdatum
    sfb = rechnung.skonto_faellig_bis
    return {
        "lieferant_name": {"wert": kred.name if kred else rechnung.lieferant_name, "konfidenz": 1.0},
        "lieferant_iban": {"wert": (kred.iban if kred else rechnung.lieferant_iban) or ""},
        "betrag_netto": {"wert": rechnung.betrag_netto},
        "betrag_brutto": {"wert": rechnung.betrag_brutto, "konfidenz": 1.0},
        "mwst_satz": {"wert": rechnung.mwst_satz},
        "rechnungsnummer": {"wert": rechnung.rechnungsnummer, "konfidenz": 1.0},
        "rechnungsdatum": {"wert": rd.isoformat() if rd else None, "konfidenz": 1.0},
        "skonto_prozent": {"wert": rechnung.skonto_prozent, "konfidenz": 1.0},
        "skonto_betrag": {"wert": rechnung.skonto_betrag, "konfidenz": 1.0},
        "skonto_faellig_bis": {"wert": sfb.isoformat() if sfb else None, "konfidenz": 1.0},
        "betrag_haushaltsnah": {"wert": rechnung.betrag_haushaltsnah, "konfidenz": 1.0},
    }


def berechne_und_speichere_ampel(rechnung) -> dict:
    """Berechnet die Ampel aus den aktuellen Rechnungsfeldern und schreibt
    erkennung_ampel / _gesamt_konfidenz / _details auf die Instanz (ohne save).
    Wird nach jeder Feldänderung/Erfassung aufgerufen (Spec 5.2.5)."""
    eingabe = ampel_eingabe_aus_ocr(_rechnung_zu_felder(rechnung), rechnung=rechnung)
    ergebnis = berechne_ampel(eingabe, objekt=rechnung.objekt if rechnung.objekt_id else None,
                              rechnung=rechnung)
    rechnung.erkennung_ampel = ergebnis["ampel"]
    rechnung.erkennung_gesamt_konfidenz = ergebnis["gesamt_konfidenz"]
    rechnung.erkennung_details = ergebnis["felder"]
    return ergebnis
