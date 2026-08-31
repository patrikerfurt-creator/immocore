"""
E-Banking Erkennungspipeline (Phase B).

Verarbeitet jeden neu importierten Kontoumsatz durch bis zu 5 Stufen:
  1a  EndToEndId-Match → Nebenbuch-Tilgung (Hausgeld)
  1b  IBAN-Match auf EigentumsVerhältnis → Nebenbuch-Tilgung (Hausgeld)
  2   BankMatchRegel
  3   IBAN-Match auf Kreditor (Person, person_typ=300)
  4   KI-Vorschlag (Claude API, synchron; Phase D: async via Celery)
  5   Unklar
"""
import hashlib
import logging
import re
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Normalisierung + Hashing Verwendungszweck
# ---------------------------------------------------------------------------

def normalisiere_verwendungszweck(text: str) -> str:
    """
    Entfernt Belegnummern, Datumsangaben, Sollstellungs-Referenzen,
    Mehrfach-Whitespace und macht alles lowercase.
    """
    s = text.lower()
    s = re.sub(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", "", s)
    s = re.sub(r"\b(re|rg|nr|nummer|kdnr|kdn|beleg)[-\s:]*\d+\b", "", s)
    s = re.sub(r"\b\d{4,}\b", "", s)
    s = re.sub(r"[^a-zäöüß\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def verwendungszweck_hash(text: str) -> str:
    norm = normalisiere_verwendungszweck(text or "")
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Hausgeld-Tilgung Hilfsfunktionen (Stufe 1a / 1b)
# ---------------------------------------------------------------------------

def _ermittle_bank_sachkonto(ku):
    """
    Findet das Sachkonto 18xxx des Bankkontos, zu dem der Umsatz gehört —
    strikt im Wirtschaftsjahr des Umsatzdatums. Bankumsätze werden immer am
    Datum aus der camt-Datei gebucht, nie in einem anderen WJ. Fehlt das
    Konto im Umsatz-WJ → None (Umsatz bleibt zur manuellen Bearbeitung).
    """
    from apps.konten.models import Konto

    if ku.objekt is None:
        return None

    if ku.bankkonto and ku.bankkonto.konto_typ == 'ruecklage':
        kontonummern = ['18911', '18000']
    else:
        kontonummern = ['18000', '18911']

    buchungs_jahr = ku.buchungsdatum.year if ku.buchungsdatum else None

    for knr in kontonummern:
        qs = Konto.objects.filter(
            wirtschaftsjahr__objekt=ku.objekt,
            kontonummer=knr,
            aktiv=True,
        )
        if buchungs_jahr:
            konto = qs.filter(wirtschaftsjahr__jahr=buchungs_jahr).first()
        else:
            konto = qs.order_by('-wirtschaftsjahr__jahr').first()
        if konto:
            return konto
    return None


def _ermittle_wirtschaftsjahr(ku):
    """
    Gibt das Wirtschaftsjahr zum Umsatzdatum zurück — strikt, kein Fallback
    in ein anderes Jahr. Fehlt das WJ → None (Auto-Verbuchung überspringen).
    """
    from apps.objekte.models import Wirtschaftsjahr

    if ku.objekt is None or not ku.buchungsdatum:
        return None

    return Wirtschaftsjahr.objects.filter(
        objekt=ku.objekt, jahr=ku.buchungsdatum.year,
    ).first()


def _ermittle_konto(objekt, kontonummer, buchungsdatum=None):
    """
    Findet ein Sachkonto — strikt im WJ des Buchungsdatums (kein Fallback in
    ein anderes Jahr). Ohne Datum: neuestes WJ.
    """
    from apps.konten.models import Konto
    qs = Konto.objects.filter(wirtschaftsjahr__objekt=objekt, kontonummer=kontonummer, aktiv=True)
    if buchungsdatum:
        return qs.filter(wirtschaftsjahr__jahr=buchungsdatum.year).first()
    return qs.order_by('-wirtschaftsjahr__jahr').first()


def _finde_kreditorkonto(kreditor_rechnungen, objekt, buchungsdatum=None):
    """
    Sucht das Sachkonto (70xxx) für einen Kreditor im Kontenplan des Objekts.
    Die Kontonummer entspricht der Kreditorennummer (z.B. '70004').
    Wählt bevorzugt das WJ das zum Buchungsdatum passt.
    """
    from apps.konten.models import Konto
    if not kreditor_rechnungen or not objekt:
        return None
    kreditor_nr = getattr(kreditor_rechnungen, 'kreditorennummer', None)
    if not kreditor_nr:
        return None
    qs = Konto.objects.filter(
        wirtschaftsjahr__objekt=objekt,
        kontonummer=kreditor_nr,
        aktiv=True,
    )
    if buchungsdatum:
        # strikt im WJ des Buchungsdatums — kein Fallback in ein anderes Jahr
        return qs.filter(wirtschaftsjahr__jahr=buchungsdatum.year).first()
    return qs.order_by('-wirtschaftsjahr__jahr').first()


def _ist_zahllauf_ausgleich(op) -> bool:
    """
    True, wenn die Verbindlichkeit dieses OP bereits über einen Zahllauf gegen
    13600 ausgeglichen wurde (rechnung_zahlung_service Phase 2:
    Soll 70xxx / Haben 13600).

    Der spätere Bankabgang gehört dann gegen 13600 (Phase 3: Soll 13600 /
    Haben Bank) — ein erneuter Vorschlag auf das Kreditorkonto würde den
    Kreditor ein zweites Mal belasten.
    """
    if op is None or op.status != 'bezahlt' or not op.zahlung_buchung_id:
        return False
    zb = op.zahlung_buchung
    return any(k is not None and k.kontonummer == '13600'
               for k in (zb.soll_konto, zb.haben_konto))


def _finde_zahllauf_clearing(ku, kreditor):
    """
    Liefert (Konto 13600, OP), wenn der Bankabgang zu einem bereits per Zahllauf
    ausgeglichenen KreditorOP dieses Kreditors passt — sonst (None, None).

    Ein noch offener OP mit gleichem Betrag hat Vorrang: dort ist die
    kreditorische Buchung korrekt und der OP soll ausgeglichen werden.
    """
    from apps.buchhaltung.models import KreditorOP
    if not kreditor or not ku.objekt or (ku.betrag or 0) >= 0:
        return None, None
    abs_betrag = abs(ku.betrag)
    basis = KreditorOP.objects.filter(objekt=ku.objekt, kreditor=kreditor)
    for op in basis.filter(status__in=('offen', 'teilbezahlt')):
        if abs(op.betrag_offen - abs_betrag) <= Decimal('0.01'):
            return None, None
    for op in basis.filter(status='bezahlt').select_related(
            'zahlung_buchung__soll_konto', 'zahlung_buchung__haben_konto'):
        if abs(op.betrag_ursprung - abs_betrag) <= Decimal('0.01') and _ist_zahllauf_ausgleich(op):
            return _ermittle_konto(ku.objekt, '13600', ku.buchungsdatum), op
    return None, None


def _setze_zahllauf_clearing(ku, log, konto_13600, op, stufe):
    """Gemeinsamer Ergebnis-Setter für den 13600-Fall (Stufe 1c und 3)."""
    ku.status                 = 'erkannt'
    ku.erkannt_gegenkonto     = konto_13600
    ku.erkennungs_quelle      = 'zahllauf_clearing'
    ku.erkennungs_konfidenz   = Decimal('0.95')
    ku.erkennungs_begruendung = (
        f"OP {op.op_nummer} ({op.kreditor.name}) wurde bereits über den Zahllauf "
        f"ausgeglichen — Buchung Soll {op.kreditor.kreditorennummer} / Haben 13600. "
        f"Der Bankabgang gehört deshalb gegen das Zahlungsausgang-Clearing 13600, "
        f"nicht erneut gegen das Kreditorkonto."
    )
    log.stufe_erreicht       = stufe
    log.quelle               = 'zahllauf_clearing'
    log.konfidenz            = Decimal('0.95')
    log.gegenkonto_vorschlag = konto_13600
    log.details_json         = {
        'op_nummer': op.op_nummer,
        'op_id': str(op.id),
        'op_status': op.status,
        'kreditor_name': op.kreditor.name,
        'kreditorkonto_uebersprungen': op.kreditor.kreditorennummer,
        'zahlung_buchung_id': str(op.zahlung_buchung_id),
    }


def _get_system_user():
    """Gibt den ersten Superuser oder Admin-User zurück."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return (
        User.objects.filter(is_superuser=True).order_by('id').first()
        or User.objects.filter(is_staff=True).order_by('id').first()
        or User.objects.order_by('id').first()
    )


def versuche_e2e_tilgung(ku):
    """
    Stufe 1a: EndToEndId-Match auf offene HausgeldSollstellung.
    Format der EndToEndId: '{opos_nr}-{suffix}' (z.B. '2600000001-B').
    Gibt die erzeugte Buchung zurück oder None.
    """
    from apps.buchhaltung.models import HausgeldSollstellung
    from apps.buchhaltung.services.zahlungs_zuordnung_service import verrechne_eingang_manuell

    e2e = (ku.end_to_end_id or '').strip()
    if not e2e or '-' not in e2e or ku.betrag <= 0:
        return None

    opos_nr_candidate = e2e.rsplit('-', 1)[0]

    try:
        ss = HausgeldSollstellung.objects.select_related(
            'eigentumsverhaeltnis__personenkonto',
        ).get(
            opos_nr=opos_nr_candidate,
            storniert_am__isnull=True,
        )
    except HausgeldSollstellung.DoesNotExist:
        return None
    except HausgeldSollstellung.MultipleObjectsReturned:
        return None

    rest = ss.soll_betrag - ss.ist_betrag
    if rest <= Decimal('0.00'):
        return None

    try:
        pk = ss.eigentumsverhaeltnis.personenkonto
    except Exception:
        return None

    bank_sachkonto = _ermittle_bank_sachkonto(ku)
    if not bank_sachkonto:
        return None

    try:
        wj = _ermittle_wirtschaftsjahr(ku)
    except Exception:
        wj = None  # kein WJ zum Umsatzjahr -> Auto-Verbuchung ueberspringen
    if not wj:
        return None

    system_user = _get_system_user()
    buchung = verrechne_eingang_manuell(
        personenkonto=pk,
        bank_sachkonto=bank_sachkonto,
        betrag=ku.betrag,
        buchungsdatum=ku.buchungsdatum,
        buchungstext=f"Hausgeld {ss.opos_nr} — E2E",
        wirtschaftsjahr=wj,
        user=system_user,
    )
    return buchung


def versuche_kreditor_op_match(ku):
    """
    Stufe 1c: OP-Nummer oder Rechnungsnummer im Verwendungszweck + Betragsabgleich.
    Nur für Zahlungsausgänge (betrag < 0).
    Gibt das eindeutig gematchte KreditorOP zurück oder None.
    """
    from apps.buchhaltung.models import KreditorOP

    if ku.betrag >= 0:
        return None

    vz = (ku.verwendungszweck or '').strip()
    if not vz:
        return None

    zahlen = set(re.findall(r'\b\d{4,}\b', vz))
    if not zahlen:
        return None

    abs_betrag = abs(ku.betrag)

    basis_qs = KreditorOP.objects.select_related('kreditor', 'rechnung')
    if ku.objekt:
        basis_qs = basis_qs.filter(objekt=ku.objekt)

    def _betrag_ok(op):
        # Offene OPs: betrag_offen muss passen; bereits bezahlte: betrag_ursprung
        if op.status in ('offen', 'teilbezahlt'):
            return abs(op.betrag_offen - abs_betrag) <= Decimal('0.01')
        return abs(op.betrag_ursprung - abs_betrag) <= Decimal('0.01')

    kandidaten = []
    seen_ids = set()
    for zahl in zahlen:
        for op in basis_qs.filter(op_nummer=zahl):
            if op.pk not in seen_ids and _betrag_ok(op):
                kandidaten.append(op)
                seen_ids.add(op.pk)
        for op in basis_qs.filter(rechnung__rechnungsnummer=zahl):
            if op.pk not in seen_ids and _betrag_ok(op):
                kandidaten.append(op)
                seen_ids.add(op.pk)

    return kandidaten[0] if len(kandidaten) == 1 else None


def finde_ev_per_iban(ku):
    """
    EigentumsVerhältnis zur Auftraggeber-IBAN eines Eingangs — ohne
    Betragsprüfung.

    Basis für Stufe 1b (Auto-Tilgung bei Betrag == Soll) und Stufe 2b
    (Vorschlag bei abweichendem Betrag, z.B. Teilzahlung oder runder
    Dauerauftrag). Eine Person kann mehrere IBANs haben — auch die eines
    zahlenden Angehörigen.
    """
    from apps.personen.models import Person, EigentumsVerhaeltnis

    iban = (ku.auftraggeber_iban or '').strip().replace(' ', '')
    if not iban or not ku.objekt:
        return None

    person = None
    for p in Person.objects.filter(person_typ='100'):
        ibans = [i.strip().replace(' ', '') for i in (p.ibans or [])]
        if iban in ibans:
            person = p
            break

    if not person:
        return None

    return EigentumsVerhaeltnis.objects.filter(
        person=person,
        einheit__objekt=ku.objekt,
        ende__isnull=True,
    ).select_related('personenkonto').first()


def hausgeld_soll_zum_stichtag(ev, stichtag):
    """
    Hausgeld-Soll eines EigentumsVerhältnisses zu einem bestimmten Stichtag.

    Bewusst nicht ev.hausgeld_soll: die Property nimmt date.today(). Für die
    Zuordnung eines Kontoumsatzes zählt der Satz, der am Buchungsdatum galt —
    sonst schlägt der Abgleich fehl, sobald ein neuer Wirtschaftsplan greift.
    """
    betraege = ev.hausgeld_alle_aktuell(stichtag=stichtag)
    return sum(betraege.values(), Decimal('0')) if betraege else None


def versuche_iban_ev_tilgung(ku):
    """
    Stufe 1b: IBAN-Match auf EigentumsVerhältnis + Betrag = Soll.
    Gibt die erzeugte Buchung zurück oder None.
    """
    from apps.buchhaltung.services.zahlungs_zuordnung_service import verrechne_eingang_manuell

    if ku.betrag <= 0:
        return None

    ev = finde_ev_per_iban(ku)
    if not ev:
        return None

    try:
        pk = ev.personenkonto
    except Exception:
        return None

    # Betrag-Plausibilitätsprüfung gegen das Soll, das zum BUCHUNGSDATUM galt.
    # ev.hausgeld_soll nimmt date.today() als Stichtag — damit schlüge der
    # Abgleich für jeden Umsatz aus einem früheren Wirtschaftsjahr fehl, sobald
    # ein neuer Wirtschaftsplan greift (z.B. Umsatz 04/2025 gegen den ab
    # 01/2026 gültigen Satz).
    hausgeld_soll = hausgeld_soll_zum_stichtag(ev, ku.buchungsdatum)
    if hausgeld_soll is not None:
        if abs(ku.betrag - Decimal(str(hausgeld_soll))) > Decimal('0.01'):
            return None

    bank_sachkonto = _ermittle_bank_sachkonto(ku)
    if not bank_sachkonto:
        return None

    try:
        wj = _ermittle_wirtschaftsjahr(ku)
    except Exception:
        wj = None  # kein WJ zum Umsatzjahr -> Auto-Verbuchung ueberspringen
    if not wj:
        return None

    system_user = _get_system_user()
    buchung = verrechne_eingang_manuell(
        personenkonto=pk,
        bank_sachkonto=bank_sachkonto,
        betrag=ku.betrag,
        buchungsdatum=ku.buchungsdatum,
        buchungstext=f"Hausgeld {ev.einheit.einheit_nr} — IBAN-Match",
        wirtschaftsjahr=wj,
        user=system_user,
    )
    return buchung


# ---------------------------------------------------------------------------
# Lernregel anlegen / aktualisieren
# ---------------------------------------------------------------------------

def regel_anlegen_oder_aktualisieren(ku, gegenkonto, erstellt_aus: str, user):
    """
    Legt eine neue BankMatchRegel an oder aktualisiert die bestehende (Idempotenz).
    Bei abweichendem Gegenkonto: alte Regel → 'veraltet', neue anlegen.
    """
    from apps.buchhaltung.models import BankMatchRegel

    iban_key = (ku.auftraggeber_iban or '').strip().replace(' ', '') or 'NO_IBAN'
    vz_hash  = verwendungszweck_hash(ku.verwendungszweck or '')

    bestehend = BankMatchRegel.objects.filter(
        bankkonto=ku.bankkonto,
        kontrahent_iban=iban_key,
        verwendungszweck_hash=vz_hash,
        status='aktiv',
    ).first()

    if bestehend:
        if bestehend.gegenkonto_id == gegenkonto.id:
            bestehend.trefferzahl += 1
            bestehend.letzte_anwendung = timezone.now()
            bestehend.save(update_fields=['trefferzahl', 'letzte_anwendung'])
            return bestehend
        else:
            bestehend.status = 'veraltet'
            bestehend.save(update_fields=['status'])

    return BankMatchRegel.objects.create(
        bankkonto=ku.bankkonto,
        kontrahent_iban=iban_key,
        verwendungszweck_hash=vz_hash,
        gegenkonto=gegenkonto,
        kreditor=ku.erkannt_kreditor,
        eigentumsverhaeltnis=ku.erkannt_eigentumsverhaeltnis,
        status='aktiv',
        erstellt_aus=erstellt_aus,
        trefferzahl=1,
        letzte_anwendung=timezone.now(),
        erstellt_von=user,
    )


# ---------------------------------------------------------------------------
# Hauptpipeline
# ---------------------------------------------------------------------------

@transaction.atomic
def fuehre_erkennung_aus(ku):
    """
    Führt die 5-stufige Erkennungspipeline für einen Kontoumsatz durch.
    Schreibt BankErkennungsLog und speichert Ergebnis-Felder auf ku.

    Stufen 1a/1b delegieren an bestehende Nebenbuch-Services.
    Auto-Booking bei Stufe 2 + Konf. 1.00 + auto_verbuchen_aktiv.
    """
    from apps.buchhaltung.models import BankErkennungsLog, BankMatchRegel
    from apps.buchhaltung.services.ebanking_buchungs_service import verbuche

    log = BankErkennungsLog(kontoumsatz=ku, auto_verbucht=False)

    # ---- Stufe 1a: EndToEndId-Match ----
    if ku.end_to_end_id and ku.betrag > 0:
        try:
            buchung = versuche_e2e_tilgung(ku)
        except Exception as exc:
            logger.warning("E-Banking Stufe 1a Fehler: %s", exc)
            buchung = None

        if buchung:
            ku.status                 = 'verbucht'
            ku.erkennungs_quelle      = 'e2e_id'
            ku.erkennungs_konfidenz   = Decimal('1.00')
            ku.buchung                = buchung
            ku.verbucht_am            = timezone.now()
            log.stufe_erreicht  = '1a'
            log.quelle          = 'e2e_id'
            log.konfidenz       = Decimal('1.00')
            log.auto_verbucht   = True
            _save_all(ku, log)
            return ku

    # ---- Stufe 1b: IBAN-Match auf EigentumsVerhältnis ----
    if ku.auftraggeber_iban and ku.betrag > 0:
        try:
            buchung = versuche_iban_ev_tilgung(ku)
        except Exception as exc:
            logger.warning("E-Banking Stufe 1b Fehler: %s", exc)
            buchung = None

        if buchung:
            ku.status                       = 'verbucht'
            ku.erkennungs_quelle            = 'iban_ev'
            ku.erkennungs_konfidenz         = Decimal('1.00')
            ku.buchung                      = buchung
            ku.verbucht_am                  = timezone.now()
            log.stufe_erreicht  = '1b'
            log.quelle          = 'iban_ev'
            log.konfidenz       = Decimal('1.00')
            log.auto_verbucht   = True
            _save_all(ku, log)
            return ku

    # ---- Stufe 1b2: Sammellastschrift-Match (Betrag = LastschriftLauf.gesamt_summe) ----
    if ku.betrag > 0 and ku.objekt:
        try:
            konto_13650 = _ermittle_konto(ku.objekt, '13650', ku.buchungsdatum)
            if konto_13650:
                from apps.buchhaltung.models import LastschriftLauf
                from datetime import timedelta
                toleranz = timedelta(days=7)
                lauf = LastschriftLauf.objects.filter(
                    objekt=ku.objekt,
                    gesamt_summe=ku.betrag,
                    faelligkeitsdatum__gte=ku.buchungsdatum - toleranz,
                    faelligkeitsdatum__lte=ku.buchungsdatum + toleranz,
                ).first()
                if lauf:
                    ku.erkannt_gegenkonto     = konto_13650
                    ku.erkennungs_quelle      = 'sammellastschrift'
                    ku.erkennungs_konfidenz   = Decimal('1.00')
                    ku.erkennungs_begruendung = (
                        f"Betrag {ku.betrag} € stimmt mit LastschriftLauf {lauf.bezeichnung or str(lauf.id)[:8]} "
                        f"(Fälligkeit {lauf.faelligkeitsdatum}) überein → Konto 13650."
                    )
                    ku.status = 'erkannt'
                    log.stufe_erreicht = '1b2'
                    log.quelle         = 'sammellastschrift'
                    log.konfidenz      = Decimal('1.00')
                    _save_all(ku, log)
                    return ku
        except Exception as exc:
            logger.warning("E-Banking Stufe 1b2 (Sammellastschrift) Fehler: %s", exc)

    # ---- Stufe 1b3: Sammelüberweisung (Ausgang) → 13600 ----
    # Spiegel zur Sammellastschrift: ein ausgehender Batch (Rechnungen + WKZ-
    # Überweisungen) wird gegen das Zahlungsausgang-Clearing 13600 gebucht.
    # Textbasiert, weil eine Sammelüberweisung mehrere Zahlläufe bündelt und der
    # Betrag nie exakt zu einem einzelnen passt.
    if ku.betrag < 0 and ku.objekt:
        try:
            vz = (ku.verwendungszweck or '').lower()
            ist_sammel = 'sammel' in vz and ('ueberw' in vz or 'überw' in vz or 'uberw' in vz)
            if ist_sammel:
                konto_13600 = _ermittle_konto(ku.objekt, '13600', ku.buchungsdatum)
                if konto_13600:
                    ku.erkannt_gegenkonto     = konto_13600
                    ku.erkennungs_quelle      = 'sammelueberweisung'
                    ku.erkennungs_konfidenz   = Decimal('0.90')
                    ku.erkennungs_begruendung = (
                        'SEPA-Sammelüberweisung (Verwendungszweck) → Zahlungsausgang-Clearing 13600. '
                        'Bitte gegen die offenen 13600-Posten (bezahlte Rechnungen / veranlasste '
                        'WKZ-Überweisungen) plausibilisieren.'
                    )
                    ku.status = 'vorschlag'
                    log.stufe_erreicht = '1b3'
                    log.quelle         = 'sammelueberweisung'
                    log.konfidenz      = Decimal('0.90')
                    _save_all(ku, log)
                    return ku
        except Exception as exc:
            logger.warning("E-Banking Stufe 1b3 (Sammelüberweisung) Fehler: %s", exc)

    # ---- Stufe 1c0: WKZ-Lastschrift-Bankabgang → WKZ-OP schließen ----
    # Ein Bankabgang, der zu einer offenen Lastschrift-WKZ-OP des Kreditors passt
    # (Betrag/Fälligkeit in Toleranz), schließt die WKZ-OP und bucht den Aufwand
    # (Kassenprinzip). Vorrang vor dem generischen iban_kreditor-Match.
    if ku.betrag < 0 and ku.objekt:
        try:
            from apps.buchhaltung.services.wkz.bank_match_service import (
                finde_kandidaten, ist_eindeutiger_auto_match,
            )
            from apps.buchhaltung.services.wkz.buchungs_service import (
                verbuche_wkz_lastschrift_bankabgang,
            )
            kand = [k for k in finde_kandidaten(ku) if k.vorlage.zahlweg == 'lastschrift']
            eindeutig = [k for k in kand if ist_eindeutiger_auto_match(k, ku)]
            if len(eindeutig) == 1:
                op = eindeutig[0]
                buchung = verbuche_wkz_lastschrift_bankabgang(op, ku, _get_system_user())
                ku.status                 = 'verbucht'
                ku.buchung                = buchung
                ku.verbucht_am            = timezone.now()
                ku.erkennungs_quelle      = 'wkz_bankabgang'
                ku.erkennungs_konfidenz   = Decimal('1.00')
                ku.erkennungs_begruendung = (
                    f"WKZ-Lastschrift '{op.vorlage.bezeichnung}' ({op.periode_von.strftime('%m/%Y')}) "
                    f"→ Aufwand gebucht, WKZ-OP geschlossen."
                )
                log.stufe_erreicht = '1c0'
                log.quelle         = 'wkz_bankabgang'
                log.konfidenz      = Decimal('1.00')
                log.auto_verbucht  = True
                _save_all(ku, log)
                return ku
        except Exception as exc:
            logger.warning("E-Banking Stufe 1c0 (WKZ-Lastschrift-Bankabgang) Fehler: %s", exc)

    # ---- Stufe 1c: Kreditor-OP Rechnungsnummer-Match ----
    if ku.betrag < 0:
        try:
            op = versuche_kreditor_op_match(ku)
        except Exception as exc:
            logger.warning("E-Banking Stufe 1c Fehler: %s", exc)
            op = None

        if op:
            # Bereits per Zahllauf ausgeglichen? Dann gehört der Bankabgang
            # gegen 13600 — die kreditorische Buchung ist schon erfolgt.
            konto_13600 = (_ermittle_konto(ku.objekt, '13600', ku.buchungsdatum)
                           if ku.objekt and _ist_zahllauf_ausgleich(op) else None)
            if konto_13600:
                _setze_zahllauf_clearing(ku, log, konto_13600, op, '1c')
                _save_all(ku, log)
                return ku

            # Kreditor-Person per IBAN suchen (erkannt_kreditor FK → Person)
            person_kreditor = None
            if op.kreditor.iban:
                from apps.personen.models import Person
                kred_iban = op.kreditor.iban.strip().replace(' ', '')
                for p in Person.objects.filter(person_typ='300'):
                    if kred_iban in [i.strip().replace(' ', '') for i in (p.ibans or [])]:
                        person_kreditor = p
                        break

            # Kreditorkonto (70xxx) automatisch nachschlagen
            kreditorkonto = _finde_kreditorkonto(op.kreditor, ku.objekt, ku.buchungsdatum)

            ku.status                 = 'erkannt' if kreditorkonto else 'vorschlag'
            ku.erkannt_kreditor       = person_kreditor
            ku.erkannt_gegenkonto     = kreditorkonto
            ku.erkennungs_quelle      = 'kreditor_op_nr'
            ku.erkennungs_konfidenz   = Decimal('0.95')
            ku.erkennungs_begruendung = (
                f"OP-Nr {op.op_nummer} / Rechnungsnr. "
                f"{op.rechnung.rechnungsnummer if op.rechnung else '—'} "
                f"im Verwendungszweck erkannt, Betrag {abs(ku.betrag):.2f} € stimmt überein."
                + (f" Konto {kreditorkonto.kontonummer} automatisch gesetzt." if kreditorkonto else " Gegenkonto bitte manuell wählen.")
            )
            log.stufe_erreicht        = '1c'
            log.quelle                = 'kreditor_op_nr'
            log.konfidenz             = Decimal('0.95')
            log.gegenkonto_vorschlag  = kreditorkonto
            log.details_json          = {
                'op_nummer': op.op_nummer,
                'op_id': str(op.id),
                'op_status': op.status,
                'kreditor_name': op.kreditor.name,
                'kreditorkonto': kreditorkonto.kontonummer if kreditorkonto else None,
                'kreditor_op_id': str(op.id),
            }
            _save_all(ku, log)
            return ku

    # ---- Stufe 2: BankMatchRegel ----
    if ku.bankkonto:
        iban_key = (ku.auftraggeber_iban or '').strip().replace(' ', '') or 'NO_IBAN'
        vz_hash  = verwendungszweck_hash(ku.verwendungszweck or '')

        regel = BankMatchRegel.objects.filter(
            bankkonto=ku.bankkonto,
            kontrahent_iban=iban_key,
            verwendungszweck_hash=vz_hash,
            status='aktiv',
        ).first()

        if regel:
            # BankMatchRegel.gegenkonto zeigt auf ein Konto EINES Wirtschafts-
            # jahres. Ohne Auflösung bucht eine gelernte Regel nach dem Jahres-
            # wechsel weiter in das Jahr, in dem sie angelegt wurde.
            from apps.konten.services import konto_im_jahr
            regel_gegenkonto = konto_im_jahr(regel.gegenkonto, ku.buchungsdatum.year)

            ku.status                       = 'erkannt'
            ku.erkannt_gegenkonto           = regel_gegenkonto
            ku.erkannt_kreditor             = regel.kreditor
            ku.erkannt_eigentumsverhaeltnis = regel.eigentumsverhaeltnis
            ku.erkennungs_quelle            = 'bank_match_regel'
            ku.erkennungs_konfidenz         = Decimal('1.00')
            ku.erkennungs_begruendung       = (
                f"Gelernte Regel #{regel.id} (Treffer #{regel.trefferzahl + 1})"
            )
            ku.match_regel = regel
            regel.trefferzahl += 1
            regel.letzte_anwendung = timezone.now()
            regel.save(update_fields=['trefferzahl', 'letzte_anwendung'])

            log.stufe_erreicht        = '2'
            log.quelle                = 'bank_match_regel'
            log.konfidenz             = Decimal('1.00')
            log.gegenkonto_vorschlag  = regel_gegenkonto
            log.regel_treffer         = regel

            # Auto-Booking
            auto_aktiv = getattr(ku.bankkonto.objekt, 'auto_verbuchen_aktiv', False)
            if auto_aktiv and ku.erkennungs_konfidenz == Decimal('1.00'):
                try:
                    verbuche(ku, verbucht_von=_get_system_user())
                    log.auto_verbucht = True
                except Exception as exc:
                    logger.error("E-Banking Auto-Booking Fehler: %s", exc)

            _save_all(ku, log)
            return ku

    # ---- Stufe 2b: Eigentümer per IBAN erkannt, Betrag weicht vom Soll ab ----
    # Stufe 1b verlangt Betrag == hausgeld_soll und verbucht dann automatisch.
    # Zahlt ein Eigentümer abweichend (Teilzahlung, runder Dauerauftrag), lief
    # der Umsatz bisher bis zur KI durch und kam ohne Personenbezug heraus.
    # Hier wird er wenigstens der Person zugeordnet — bewusst nur als
    # Vorschlag, nie automatisch gebucht, weil die Aufteilung auf Perioden und
    # Erlöskonten offen ist. Muss VOR Stufe 3 stehen: ein Eigentümer kann
    # zugleich Kreditor sein und würde dort sonst als solcher erkannt.
    if ku.betrag > 0 and ku.auftraggeber_iban:
        try:
            ev_abweichend = finde_ev_per_iban(ku)
        except Exception as exc:
            logger.warning("E-Banking Stufe 2b Fehler: %s", exc)
            ev_abweichend = None

        if ev_abweichend:
            from apps.buchhaltung.models import HausgeldSollstellung
            offen = (HausgeldSollstellung.objects
                     .filter(eigentumsverhaeltnis=ev_abweichend,
                             status_cached__in=('offen', 'teilbezahlt'))
                     .order_by('periode').first())
            offen_txt = (
                f" Älteste unbeglichene Sollstellung: {offen.periode} über "
                f"{offen.soll_betrag} € ({offen.status_cached})."
                if offen else " Derzeit keine offene Sollstellung."
            )
            ku.status                       = 'vorschlag'
            ku.erkannt_eigentumsverhaeltnis = ev_abweichend
            ku.erkennungs_quelle            = 'iban_ev_abweichend'
            ku.erkennungs_konfidenz         = Decimal('0.70')
            ku.erkennungs_begruendung = (
                f"IBAN gehört zu {ev_abweichend.person} "
                f"(Personenkonto {ev_abweichend.personenkonto}). Der Betrag "
                f"{ku.betrag} € weicht vom Soll ab — keine automatische Tilgung."
                + offen_txt + " Bitte Zuordnung und Aufteilung prüfen."
            )
            log.stufe_erreicht = '2b'
            log.quelle         = 'iban_ev_abweichend'
            log.konfidenz      = Decimal('0.70')
            _save_all(ku, log)
            return ku

    # ---- Stufe 3: IBAN-Match auf Kreditor ----
    if ku.auftraggeber_iban:
        from apps.personen.models import Person
        from apps.rechnungen.models import Kreditor as KreditorModel

        cdtr_iban = ku.auftraggeber_iban.strip().replace(' ', '')

        # Person (person_typ=300) suchen die diese IBAN hat
        person_kreditor = None
        for p in Person.objects.filter(person_typ='300'):
            ibans = [i.strip().replace(' ', '') for i in (p.ibans or [])]
            if cdtr_iban in ibans:
                person_kreditor = p
                break

        # Rechnungs-Kreditor direkt per IBAN suchen (unabhängig von Person)
        kred_obj = KreditorModel.objects.filter(
            iban=cdtr_iban,
            aktiv=True,
        ).first()

        if person_kreditor or kred_obj:
            # Bankabgang zu einer bereits per Zahllauf beglichenen Rechnung?
            # Dann 13600 statt Kreditorkonto (sonst Doppelbelastung).
            konto_13600, zl_op = _finde_zahllauf_clearing(ku, kred_obj)
            if konto_13600:
                _setze_zahllauf_clearing(ku, log, konto_13600, zl_op, '3')
                _save_all(ku, log)
                return ku

            kreditorkonto = _finde_kreditorkonto(kred_obj, ku.objekt, ku.buchungsdatum)

            if person_kreditor:
                anzeigename = _person_anzeigename(person_kreditor)
            elif kred_obj:
                anzeigename = kred_obj.name
            else:
                anzeigename = cdtr_iban

            ku.status               = 'erkannt' if kreditorkonto else 'vorschlag'
            ku.erkannt_kreditor     = person_kreditor
            ku.erkannt_gegenkonto   = kreditorkonto
            ku.erkennungs_quelle    = 'iban_kreditor'
            ku.erkennungs_konfidenz = Decimal('0.80')
            ku.erkennungs_begruendung = (
                f"IBAN identifiziert Kreditor {anzeigename}"
                + (f", Konto {kreditorkonto.kontonummer} automatisch gesetzt." if kreditorkonto else ", Gegenkonto bitte manuell wählen.")
            )
            log.stufe_erreicht       = '3'
            log.quelle               = 'iban_kreditor'
            log.konfidenz            = Decimal('0.80')
            log.gegenkonto_vorschlag = kreditorkonto
            _save_all(ku, log)
            return ku

    # ---- Stufe 4: KI-Vorschlag ----
    try:
        ki = _ki_vorschlag(ku)
        if ki and ki.get('konfidenz_decimal', Decimal('0')) >= Decimal('0.50'):
            ki_gegenkonto = ki.get('gegenkonto')
            ki_begruendung = ki.get('begruendung', '')
            # Regel: Eingänge dürfen nur bei Lastschrift gegen 13650 gebucht werden.
            # Eine Überweisung/Gutschrift gehört direkt aufs Personenkonto (Debitor-Weg).
            # Ein KI-Vorschlag auf 13650 bei einem Eingang wird daher verworfen.
            if (ku.betrag or 0) > 0 and ki_gegenkonto is not None and ki_gegenkonto.kontonummer == '13650':
                ki_gegenkonto = None
                ki_begruendung = (
                    (ki_begruendung + ' — ') if ki_begruendung else ''
                ) + 'Regel: Eingang direkt aufs Personenkonto buchen (Debitor); 13650 nur bei Lastschrift.'
            ku.status                 = 'vorschlag'
            ku.erkannt_gegenkonto     = ki_gegenkonto
            ku.erkennungs_quelle      = 'ki'
            ku.erkennungs_konfidenz   = min(ki['konfidenz_decimal'], Decimal('0.85'))
            ku.erkennungs_begruendung = ki_begruendung
            log.stufe_erreicht  = '4'
            log.quelle          = 'ki'
            log.konfidenz       = ku.erkennungs_konfidenz
            log.details_json    = ki.get('raw_response')
            if ki.get('gegenkonto'):
                log.gegenkonto_vorschlag = ki['gegenkonto']
            _save_all(ku, log)
            return ku
    except Exception as exc:
        logger.warning("E-Banking KI-Fehler: %s", exc)
        log.details_json = {'ki_error': str(exc)}

    # ---- Stufe 5: unklar ----
    ku.status               = 'unklar'
    ku.erkennungs_quelle    = 'keine'
    ku.erkennungs_konfidenz = Decimal('0.00')
    log.stufe_erreicht      = '5'
    log.quelle              = 'keine'
    log.konfidenz           = Decimal('0.00')
    _save_all(ku, log)
    return ku


# ---------------------------------------------------------------------------
# Private Hilfsfunktionen
# ---------------------------------------------------------------------------

def _save_all(ku, log):
    ku.save()
    log.save()


def _person_anzeigename(person) -> str:
    if person.firmenname:
        return person.firmenname
    parts = [person.vorname, person.nachname]
    return ' '.join(p for p in parts if p) or str(person.id)


def _ki_vorschlag(ku) -> dict | None:
    """
    Stufe 4: Claude API. Gibt dict mit 'konfidenz_decimal', 'gegenkonto',
    'begruendung', 'raw_response' zurück oder None.
    """
    import json
    from django.conf import settings

    api_key = getattr(settings, 'ANTHROPIC_API_KEY', None)
    if not api_key:
        return None

    try:
        import anthropic
    except ImportError:
        return None

    from apps.konten.models import Konto

    konten_qs = Konto.objects.filter(
        wirtschaftsjahr__objekt=ku.objekt,
        aktiv=True,
        direktes_buchen=True,
    ).order_by('kontonummer').values('id', 'kontonummer', 'kontoname')[:50]

    konten_text = '\n'.join(
        f"  {k['kontonummer']} — {k['kontoname']}" for k in konten_qs
    )

    prompt = f"""Du bist ein Buchhalter-Assistent für WEG-Verwaltung.
Analysiere diese Bankbuchung und schlage das Gegenkonto vor.

Datum: {ku.buchungsdatum}
Betrag: {ku.betrag} EUR ({'Eingang' if ku.betrag > 0 else 'Ausgang'})
Kontrahent: {ku.auftraggeber_name or '(unbekannt)'}
IBAN: {ku.auftraggeber_iban or '(unbekannt)'}
Verwendungszweck: {ku.verwendungszweck or '(leer)'}

Verfügbare Konten (direktes Buchen):
{konten_text}

Antworte NUR mit JSON (kein Markdown):
{{"konfidenz": 0.0-1.0, "gegenkonto_nr": "12345" oder null, "begruendung": "kurz"}}"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        model = getattr(settings, 'ANTHROPIC_MODEL', 'claude-haiku-4-5-20251001')
        msg = client.messages.create(
            model=model, max_tokens=4000,  # claude-sonnet-5 denkt zuerst — Budget für Thinking + JSON
            messages=[{'role': 'user', 'content': prompt}],
        )
        raw = next((b.text for b in msg.content if getattr(b, 'type', None) == 'text'), '').strip()
        ki_result = json.loads(raw)
    except Exception as exc:
        logger.warning("KI-Vorschlag Fehler: %s", exc)
        return None

    konfidenz = Decimal(str(ki_result.get('konfidenz', 0)))
    gegenkonto_nr = ki_result.get('gegenkonto_nr')
    gegenkonto = None

    if gegenkonto_nr and ku.objekt:
        from apps.konten.models import Konto
        gegenkonto = Konto.objects.filter(
            wirtschaftsjahr__objekt=ku.objekt,
            kontonummer=gegenkonto_nr,
            aktiv=True,
        ).order_by('-wirtschaftsjahr__jahr').first()

    return {
        'konfidenz_decimal': konfidenz,
        'gegenkonto':        gegenkonto,
        'begruendung':       ki_result.get('begruendung', ''),
        'raw_response':      ki_result,
    }
