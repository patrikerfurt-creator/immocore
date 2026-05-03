"""
3-stufige Rechnungserkennung mit lernender Buchungslogik.

Erkennungs-Stufen:
  1 (erkannt)       — Kreditor + Objekt + Buchungskonto alle eindeutig
  2 (pruefung_match) — mind. 1, aber nicht alle 3 Dimensionen erkannt
  3 (nicht_erkannt)  — keine Dimension sicher zugeordnet
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from django.db.models import Q
from django.utils import timezone

# ----- Schwellwerte --------------------------------------------------------

SCHWELLE_KREDITOR      = 0.90
SCHWELLE_OBJEKT        = 0.85
SCHWELLE_KONTO         = 1.00   # nur Match-Regel gilt als eindeutig
AUTO_KONFIDENZ_SCHWELLE = 0.95  # min. Konfidenz aller drei Dim. für Auto-Buchung

# ----- Deutsche Stoppwörter (Kurzliste, erweiterbar) -----------------------

DE_STOPWORDS = frozenset({
    'und', 'oder', 'die', 'der', 'das', 'ein', 'eine', 'fuer', 'mit',
    'von', 'auf', 'im', 'in', 'an', 'am', 'zu', 'ist', 'sind', 'des',
    'dem', 'den', 'als', 'bei', 'bis', 'aus', 'nach', 'zur', 'zum',
    'sowie', 'inkl', 'zzgl', 'netto', 'brutto', 'mwst', 'ust',
})


# ===========================================================================
# Text-Normalisierung + Hash
# ===========================================================================

def normalisiere_leistungstext(text: str) -> str:
    """Bereinigt Leistungstext für stabilen Vergleich."""
    text = text.lower()
    text = re.sub(r'\d{1,2}[./]\d{1,2}[./]\d{2,4}', '', text)        # Datum
    text = re.sub(r'\b(q[1-4]|kw\s?\d{1,2})\b', '', text)            # Quartal/KW
    text = re.sub(r'(rg|re|rechnung|beleg)[-.\s]?\d+', '', text)      # Belegnr
    text = re.sub(r'\b\d{4,}\b', '', text)                            # lange Zahlen
    text = re.sub(r'[^a-z0-9äöüß ]+', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    text = ' '.join(t for t in text.split() if t not in DE_STOPWORDS)
    return text


def leistungstext_hash(text: str) -> str:
    return hashlib.sha256(
        normalisiere_leistungstext(text).encode('utf-8')
    ).hexdigest()


# ===========================================================================
# MatchResult-Datenklasse
# ===========================================================================

@dataclass
class MatchResult:
    kandidat: object = None
    konfidenz: float = 0.0
    match_typ: str = 'kein_treffer'

    @property
    def eindeutig(self) -> bool:
        return self.kandidat is not None and self.konfidenz >= _schwelle_fuer(self)

    @classmethod
    def empty(cls) -> 'MatchResult':
        return cls(kandidat=None, konfidenz=0.0, match_typ='kein_treffer')

    @classmethod
    def treffer(cls, kandidat, konfidenz: float, match_typ: str = 'treffer') -> 'MatchResult':
        return cls(kandidat=kandidat, konfidenz=konfidenz, match_typ=match_typ)


def _schwelle_fuer(result: MatchResult) -> float:
    # Wird von aufrufer explizit geprüft — Hilfsfunktion nur intern
    return 0.0


# ===========================================================================
# Match-Funktionen
# ===========================================================================

def match_kreditor(rechnung) -> MatchResult:
    """
    Kreditor-Erkennung in drei Stufen:
      1. IBAN-Match (= 1.0)
      2. Name + USt-IdNr. (= 0.92)
      3. Fuzzy-Name (max 0.85)
    """
    from .models import Kreditor

    # 1. IBAN-Match
    if rechnung.lieferant_iban:
        iban = rechnung.lieferant_iban.replace(' ', '').upper()
        k = Kreditor.objects.filter(iban=iban, aktiv=True).first()
        if k:
            return MatchResult.treffer(k, 1.0, 'iban')

    # 2. Normierter Name
    if rechnung.lieferant_normalisiert:
        norm = rechnung.lieferant_normalisiert.lower().strip()
        k = Kreditor.objects.filter(
            name_normalisiert__iexact=norm, aktiv=True
        ).first()
        if k:
            return MatchResult.treffer(k, 0.92, 'name_exakt')

    # 3. Fuzzy-Name (einfache Enthaltensein-Prüfung → max 0.85)
    if rechnung.lieferant_name and len(rechnung.lieferant_name) >= 4:
        kandidaten = Kreditor.objects.filter(
            name__icontains=rechnung.lieferant_name[:20], aktiv=True
        )[:5]
        for k in kandidaten:
            score = _fuzzy_score(rechnung.lieferant_name, k.name)
            if score >= SCHWELLE_KREDITOR:
                return MatchResult.treffer(k, min(score, 0.85), 'fuzzy')

    return MatchResult.empty()


def match_objekt(rechnung) -> MatchResult:
    """
    Objekt-Erkennung:
      1. Objekt bereits gesetzt (= 1.0)
      2. Anschrift-Match gegen Eingang-Adressen (= 0.90)
      3. Historie: letztes Objekt desselben Kreditors (max 0.70)
    """
    from apps.objekte.models import Objekt, Eingang

    # 1. Objekt bereits gesetzt (aus OCR oder vorangegangenem Lauf)
    if rechnung.objekt_id:
        try:
            obj = Objekt.objects.get(pk=rechnung.objekt_id)
            return MatchResult.treffer(obj, 1.0, 'direkt')
        except Objekt.DoesNotExist:
            pass

    # 2. Anschrift-Match: Liefer-/Rechnungsadresse gegen Eingänge
    text = (rechnung.textauszug or '') + ' ' + (rechnung.leistungstext or '')
    text_lower = text.lower()
    beste_konfidenz = 0.0
    bestes_objekt = None
    for eingang in Eingang.objects.select_related('objekt').filter(objekt__status='aktiv'):
        if eingang.strasse and len(eingang.strasse) > 5:
            if eingang.strasse.lower() in text_lower:
                konfidenz = 0.90
                if konfidenz > beste_konfidenz:
                    beste_konfidenz = konfidenz
                    bestes_objekt = eingang.objekt

    if bestes_objekt and beste_konfidenz >= SCHWELLE_OBJEKT:
        return MatchResult.treffer(bestes_objekt, beste_konfidenz, 'anschrift')

    # 3. Letzte Rechnung dieses Kreditors (schwaches Signal → max 0.70)
    if rechnung.kreditor_id:
        from .models import Rechnung
        letzte = (
            Rechnung.objects
            .filter(kreditor_id=rechnung.kreditor_id, objekt__isnull=False)
            .exclude(pk=rechnung.pk)
            .order_by('-erstellt_am')
            .select_related('objekt')
            .first()
        )
        if letzte and letzte.objekt:
            return MatchResult.treffer(letzte.objekt, 0.70, 'historie')

    return MatchResult.empty()


def match_konto_historie(kreditor, objekt) -> MatchResult:
    """
    Konto-Vorschlag aus KreditorRegel (alter Lernmechanismus).
    Liefert max. 0.70 — kein eindeutiger Treffer, bleibt Stufe 2.
    """
    from .models import KreditorRegel
    if not kreditor or not objekt:
        return MatchResult.empty()
    regel = (
        KreditorRegel.objects
        .filter(kreditor=kreditor, objekt=objekt, konto__isnull=False)
        .order_by('-treffer')
        .select_related('konto')
        .first()
    )
    if regel and regel.konto:
        return MatchResult.treffer(regel.konto, 0.70, 'kreditor_regel_historie')
    return MatchResult.empty()


# ===========================================================================
# Haupt-Pipeline
# ===========================================================================

def fuehre_erkennung_aus(rechnung) -> object:
    """
    Führt die 3-stufige Erkennungs-Pipeline durch und routet die Rechnung.
    Gibt die (gespeicherte) Rechnung zurück.
    """
    from .models import RechnungsErkennungsLog, RechnungsMatchRegel

    log_dimensionen: dict = {}

    # --- Kreditor ---
    kreditor_match = match_kreditor(rechnung)
    log_dimensionen['kreditor'] = {
        'match_typ':   kreditor_match.match_typ,
        'kandidat_id': str(kreditor_match.kandidat.id) if kreditor_match.kandidat else None,
        'konfidenz':   kreditor_match.konfidenz,
    }

    # Kreditor sofort setzen, damit match_objekt (Stufe 3) davon profitiert
    if kreditor_match.konfidenz >= SCHWELLE_KREDITOR:
        rechnung.kreditor = kreditor_match.kandidat

    # --- Objekt ---
    objekt_match = match_objekt(rechnung)
    log_dimensionen['objekt'] = {
        'match_typ':   objekt_match.match_typ,
        'kandidat_id': str(objekt_match.kandidat.id) if objekt_match.kandidat else None,
        'konfidenz':   objekt_match.konfidenz,
    }

    # --- Konto (nur wenn Kreditor + Objekt eindeutig) ---
    konto_match = MatchResult.empty()
    regel_treffer = None

    kreditor_eindeutig = kreditor_match.konfidenz >= SCHWELLE_KREDITOR
    objekt_eindeutig   = objekt_match.konfidenz   >= SCHWELLE_OBJEKT

    if kreditor_eindeutig and objekt_eindeutig:
        text_hash = leistungstext_hash(rechnung.leistungstext or rechnung.leistungsbeschreibung or '')
        rechnung.leistungstext_hash = text_hash

        # Primär: aktive RechnungsMatchRegel
        regel_treffer = RechnungsMatchRegel.objects.filter(
            kreditor=kreditor_match.kandidat,
            objekt=objekt_match.kandidat,
            leistungstext_hash=text_hash,
            status='aktiv',
        ).first()

        if regel_treffer:
            konto_match = MatchResult.treffer(regel_treffer.buchungskonto, 1.0, 'match_regel')
        else:
            # Fallback: KreditorRegel-Historie (max 0.70 → kein eindeutiger Treffer)
            konto_match = match_konto_historie(
                kreditor_match.kandidat,
                objekt_match.kandidat,
            )

    log_dimensionen['konto'] = {
        'match_typ':   konto_match.match_typ,
        'kandidat_id': str(konto_match.kandidat.id) if konto_match.kandidat else None,
        'konfidenz':   konto_match.konfidenz,
    }

    konto_eindeutig = konto_match.konfidenz >= SCHWELLE_KONTO

    # --- Stufenableitung v1.2 (Sub-Stufen 2a / 2b) ---
    if kreditor_eindeutig and objekt_eindeutig and konto_eindeutig:
        rechnung.status           = 'erkannt'
        rechnung.erkennungs_stufe = '1'
    elif objekt_eindeutig:
        # Objekt erkannt (ggf. auch Kreditor) → Objektbetreuer
        rechnung.status           = 'pruefung_match'
        rechnung.erkennungs_stufe = '2a'
    elif kreditor_eindeutig:
        # Nur Kreditor erkannt, Objekt fehlt → Frontoffice
        rechnung.status           = 'pruefung_match'
        rechnung.erkennungs_stufe = '2b'
    else:
        rechnung.status           = 'nicht_erkannt'
        rechnung.erkennungs_stufe = '3'

    # --- Felder setzen ---
    rechnung.kreditor      = kreditor_match.kandidat if kreditor_eindeutig else rechnung.kreditor
    rechnung.objekt        = objekt_match.kandidat   if objekt_eindeutig   else rechnung.objekt
    rechnung.buchungskonto = konto_match.kandidat    if konto_eindeutig    else None
    rechnung.match_regel   = regel_treffer
    rechnung.erkennungs_konfidenz = {
        'kreditor': kreditor_match.konfidenz,
        'objekt':   objekt_match.konfidenz,
        'konto':    konto_match.konfidenz,
    }

    # --- Routing ---
    auto_gebucht = route_rechnung(rechnung)

    rechnung.save()

    # --- Log ---
    RechnungsErkennungsLog.objects.create(
        rechnung=rechnung,
        stufe=rechnung.erkennungs_stufe,
        routing_ziel=rechnung.routing_ziel,
        auto_gebucht=auto_gebucht,
        dimensionen=log_dimensionen,
        regel_treffer=regel_treffer,
        ergebnis_status=rechnung.status,
    )

    return rechnung


# ===========================================================================
# Routing
# ===========================================================================

def route_rechnung(rechnung) -> bool:
    """
    Phase B: Routing anhand Stufe und Konfidenz.
    Setzt rechnung.routing_ziel + rechnung.zugewiesen_an — kein save().
    Gibt True zurück wenn auto-gebucht.
    """
    if rechnung.status == 'erkannt':
        rechnung.routing_ziel = 'limit_workflow'
        return _route_limit_workflow(rechnung)

    # Stufe 2a → Objektbetreuer; 2b + 3 → Frontoffice
    if rechnung.erkennungs_stufe == '2a':
        rechnung.routing_ziel  = 'objektbetreuer'
        rechnung.zugewiesen_an = _ermittle_betreuer(rechnung)
    else:
        rechnung.routing_ziel  = 'frontoffice'
        rechnung.zugewiesen_an = None   # geteilte Queue
    return False


def _konfidenz_min(rechnung) -> float:
    k = rechnung.erkennungs_konfidenz or {}
    return min(
        k.get('kreditor', 0.0),
        k.get('objekt',   0.0),
        k.get('konto',    0.0),
    )


def _route_limit_workflow(rechnung) -> bool:
    """
    Limit-Workflow für Stufe-1-Rechnungen.
    Gibt True zurück wenn auto-gebucht.
    """
    grenzen = _lade_grenzen(rechnung)
    stufe   = _ermittle_freigabestufe(rechnung.betrag_brutto or 0, grenzen)

    if stufe['rolle'] == 'auto' and _konfidenz_min(rechnung) >= AUTO_KONFIDENZ_SCHWELLE:
        # Auto-Buchung: alle drei Dim. ≥ 95 % + Betrag unter Auto-Limit
        rechnung.status        = 'gebucht'
        rechnung.zugewiesen_an = None
        return True

    # Konfidenz unter 95 % ODER manueller Limit-Schritt erforderlich
    # → ersten manuellen Schritt ermitteln wenn stufe['rolle'] == 'auto'
    if stufe['rolle'] == 'auto':
        stufe = _naechste_manuelle_stufe(_lade_grenzen(rechnung))

    rechnung.status        = 'in_pruefung'
    rechnung.zugewiesen_an = _ermittle_freigabeperson(rechnung, stufe)
    return False


def _naechste_manuelle_stufe(grenzen: list) -> dict:
    """Gibt die erste nicht-auto Freigabestufe zurück."""
    for s in sorted(grenzen, key=lambda s: s.get('bis') or float('inf')):
        if s.get('rolle') != 'auto':
            return s
    return {'rolle': 'geschaeftsfuehrer', 'frist_tage': 5}


def _ermittle_betreuer(rechnung):
    """Gibt den Objektbetreuer zurück, bei Abwesenheit die Vertretung."""
    if rechnung.objekt and rechnung.objekt.betreuer_id:
        betreuer = rechnung.objekt.betreuer
        try:
            abwesend = betreuer.mitarbeiter_profil.abwesend
        except Exception:
            abwesend = False
        if abwesend and rechnung.objekt.betreuer_vertretung_id:
            return rechnung.objekt.betreuer_vertretung
        return betreuer
    # Fallback: erster Superuser (mandant_default_pruefer)
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.filter(is_superuser=True).order_by('id').first()


def _lade_grenzen(rechnung) -> list:
    """Lädt Freigabelimits aus Objekt oder globalen Defaults."""
    from .models import FreigabelimitDefault
    if rechnung.objekt and rechnung.objekt.zahlungsfreigabe_grenzen:
        grenzen = rechnung.objekt.zahlungsfreigabe_grenzen
        if isinstance(grenzen, list) and grenzen:
            return grenzen
    return FreigabelimitDefault.lade().grenzen


def _ermittle_freigabestufe(betrag, grenzen: list) -> dict:
    """Gibt die passende Freigabe-Stufe für den Betrag zurück."""
    from decimal import Decimal
    betrag = Decimal(str(betrag))
    for stufe in sorted(grenzen, key=lambda s: s.get('bis') or float('inf')):
        bis = stufe.get('bis')
        if bis is None or betrag <= Decimal(str(bis)):
            return stufe
    return grenzen[-1] if grenzen else {'rolle': 'geschaeftsfuehrer', 'frist_tage': 5}


def _ermittle_freigabeperson(rechnung, stufe: dict):
    """Gibt den zuständigen Freigeber für eine Stufe zurück."""
    from django.contrib.auth import get_user_model
    from apps.mitarbeiter.models import MitarbeiterObjektZuordnung
    User = get_user_model()

    rolle = stufe.get('rolle', '')

    if rolle == 'sachbearbeiter' and rechnung.objekt:
        zuordnung = (
            MitarbeiterObjektZuordnung.objects
            .filter(objekt=rechnung.objekt, aufgabe='objektmanagement')
            .select_related('mitarbeiter__user')
            .first()
        )
        if zuordnung:
            return zuordnung.mitarbeiter.user

    if rolle in ('objektmanager', 'sachbearbeiter') and rechnung.objekt:
        gf = User.objects.filter(
            groups__name='Objektmanager', is_active=True
        ).first()
        if gf:
            return gf

    gf = (
        User.objects.filter(groups__name='Geschaeftsfuehrer', is_active=True).first()
        or User.objects.filter(is_superuser=True).order_by('id').first()
    )
    return gf


# ===========================================================================
# Doppelfunktion: darf_betreuer_direkt_freigeben
# ===========================================================================

def darf_betreuer_direkt_freigeben(rechnung, betreuer) -> bool:
    """
    True  → Button 'Identifizieren + Freigeben' aktiv.
    False → Nur 'Identifizieren + Speichern' verfügbar.

    Frontoffice-User dürfen wie Sachbearbeiter freigeben (Spec v1.2 §6.3).
    """
    if not rechnung.objekt:
        # Ohne Objekt kann kein Limit ermittelt werden
        return betreuer.groups.filter(name='Frontoffice').exists()

    grenzen = _lade_grenzen(rechnung)
    stufe   = _ermittle_freigabestufe(rechnung.betrag_brutto or 0, grenzen)
    rolle   = stufe.get('rolle', '')

    if rolle == 'auto':
        return True

    if rolle in ('sachbearbeiter', 'objektmanager'):
        # Frontoffice darf wie Sachbearbeiter freigeben
        if betreuer.groups.filter(name='Frontoffice').exists():
            return True
        from apps.mitarbeiter.models import MitarbeiterObjektZuordnung
        if MitarbeiterObjektZuordnung.objects.filter(
            mitarbeiter__user=betreuer, objekt=rechnung.objekt,
        ).exists():
            return True
        if betreuer.groups.filter(name__in=['Objektmanager', 'Sachbearbeiter']).exists():
            return True

    if rolle == 'geschaeftsfuehrer':
        return betreuer.groups.filter(name='Geschaeftsfuehrer').exists()

    return False


# ===========================================================================
# Lern-Logik: Regel anlegen / aktualisieren
# ===========================================================================

def lege_match_regel_an(
    rechnung,
    erstellt_durch,
    erstellt_aus: str,
    lernen: bool = True,
) -> Optional[object]:
    """
    Erzeugt oder aktualisiert eine RechnungsMatchRegel.
    Gibt None zurück wenn lernen=False oder Pflichtdaten fehlen.
    """
    from .models import RechnungsMatchRegel

    if not lernen:
        return None
    if not (rechnung.kreditor and rechnung.objekt and rechnung.buchungskonto):
        return None

    text_hash = rechnung.leistungstext_hash or leistungstext_hash(
        rechnung.leistungstext or rechnung.leistungsbeschreibung or ''
    )
    if not rechnung.leistungstext_hash:
        rechnung.leistungstext_hash = text_hash
        rechnung.save(update_fields=['leistungstext_hash'])

    # Idempotenz: existiert bereits eine aktive Regel mit gleichem Konto?
    existing = RechnungsMatchRegel.objects.filter(
        kreditor=rechnung.kreditor,
        objekt=rechnung.objekt,
        leistungstext_hash=text_hash,
        status='aktiv',
    ).first()

    if existing:
        if existing.buchungskonto_id == rechnung.buchungskonto_id:
            # Gleiches Konto → nur Trefferzahl hochzählen
            existing.trefferzahl += 1
            existing.letzte_anwendung = timezone.now()
            existing.save(update_fields=['trefferzahl', 'letzte_anwendung'])
            return existing
        else:
            # Anderes Konto → alte Regel veralten, neue anlegen
            existing.status = 'veraltet'
            existing.save(update_fields=['status'])

    regel = RechnungsMatchRegel.objects.create(
        kreditor=rechnung.kreditor,
        objekt=rechnung.objekt,
        leistungstext_hash=text_hash,
        leistungstext_sample=rechnung.leistungstext or rechnung.leistungsbeschreibung or '',
        buchungskonto=rechnung.buchungskonto,
        status='aktiv',
        trefferzahl=1,
        erstellt_durch=erstellt_durch,
        erstellt_aus=erstellt_aus,
        letzte_anwendung=timezone.now(),
    )
    return regel


# ===========================================================================
# Hilfsfunktionen
# ===========================================================================

def _fuzzy_score(a: str, b: str) -> float:
    """Einfacher Similarity-Score ohne externe Bibliothek."""
    a, b = a.lower().strip(), b.lower().strip()
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    # Teilstring
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if shorter in longer:
        return 0.85
    # Zeichen-Overlap (Jaccard auf Bigramme)
    def bigramme(s):
        return {s[i:i+2] for i in range(len(s)-1)}
    bg_a, bg_b = bigramme(a), bigramme(b)
    if not bg_a or not bg_b:
        return 0.0
    return len(bg_a & bg_b) / len(bg_a | bg_b)
