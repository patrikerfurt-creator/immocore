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
    """Findet das Sachkonto 18xxx für den Bankabgang/-eingang."""
    from apps.konten.models import Konto

    if ku.objekt is None:
        return None

    if ku.bankkonto and ku.bankkonto.konto_typ == 'ruecklage':
        kontonummern = ['18911', '18000']
    else:
        kontonummern = ['18000', '18911']

    for knr in kontonummern:
        konto = Konto.objects.filter(
            wirtschaftsjahr__objekt=ku.objekt,
            kontonummer=knr,
            aktiv=True,
        ).order_by('-wirtschaftsjahr__jahr').first()
        if konto:
            return konto
    return None


def _ermittle_wirtschaftsjahr(ku):
    """Findet das aktive/neueste Wirtschaftsjahr für das Objekt."""
    from apps.objekte.models import Wirtschaftsjahr

    if ku.objekt is None:
        return None

    return (
        Wirtschaftsjahr.objects.filter(objekt=ku.objekt, status='offen')
        .order_by('-jahr')
        .first()
        or Wirtschaftsjahr.objects.filter(objekt=ku.objekt)
        .order_by('-jahr')
        .first()
    )


def _finde_kreditorkonto(kreditor_rechnungen, objekt):
    """
    Sucht das Sachkonto (70xxx) für einen Kreditor im Kontenplan des Objekts.
    Die Kontonummer entspricht der Kreditorennummer (z.B. '70004').
    """
    from apps.konten.models import Konto
    if not kreditor_rechnungen or not objekt:
        return None
    kreditor_nr = getattr(kreditor_rechnungen, 'kreditorennummer', None)
    if not kreditor_nr:
        return None
    return Konto.objects.filter(
        wirtschaftsjahr__objekt=objekt,
        kontonummer=kreditor_nr,
        aktiv=True,
    ).order_by('-wirtschaftsjahr__jahr').first()


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

    wj = _ermittle_wirtschaftsjahr(ku)
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


def versuche_iban_ev_tilgung(ku):
    """
    Stufe 1b: IBAN-Match auf EigentumsVerhältnis + Betrag = Soll.
    Gibt die erzeugte Buchung zurück oder None.
    """
    from apps.personen.models import Person, EigentumsVerhaeltnis
    from apps.buchhaltung.services.zahlungs_zuordnung_service import verrechne_eingang_manuell

    if ku.betrag <= 0:
        return None

    iban = (ku.auftraggeber_iban or '').strip().replace(' ', '')
    if not iban:
        return None

    person = None
    for p in Person.objects.filter(person_typ='100'):
        ibans = [i.strip().replace(' ', '') for i in (p.ibans or [])]
        if iban in ibans:
            person = p
            break

    if not person:
        return None

    ev = EigentumsVerhaeltnis.objects.filter(
        person=person,
        einheit__objekt=ku.objekt,
        ende__isnull=True,
    ).select_related('personenkonto').first()

    if not ev:
        return None

    try:
        pk = ev.personenkonto
    except Exception:
        return None

    # Betrag-Plausibilitätsprüfung: muss mit Soll übereinstimmen
    hausgeld_soll = ev.hausgeld_soll
    if hausgeld_soll is not None:
        if abs(ku.betrag - Decimal(str(hausgeld_soll))) > Decimal('0.01'):
            return None

    bank_sachkonto = _ermittle_bank_sachkonto(ku)
    if not bank_sachkonto:
        return None

    wj = _ermittle_wirtschaftsjahr(ku)
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

    # ---- Stufe 1c: Kreditor-OP Rechnungsnummer-Match ----
    if ku.betrag < 0:
        try:
            op = versuche_kreditor_op_match(ku)
        except Exception as exc:
            logger.warning("E-Banking Stufe 1c Fehler: %s", exc)
            op = None

        if op:
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
            kreditorkonto = _finde_kreditorkonto(op.kreditor, ku.objekt)

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
            ku.status                       = 'erkannt'
            ku.erkannt_gegenkonto           = regel.gegenkonto
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
            log.gegenkonto_vorschlag  = regel.gegenkonto
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
            kreditorkonto = _finde_kreditorkonto(kred_obj, ku.objekt)

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
            ku.status                 = 'vorschlag'
            ku.erkannt_gegenkonto     = ki.get('gegenkonto')
            ku.erkennungs_quelle      = 'ki'
            ku.erkennungs_konfidenz   = min(ki['konfidenz_decimal'], Decimal('0.85'))
            ku.erkennungs_begruendung = ki.get('begruendung', '')
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
            model=model, max_tokens=256,
            messages=[{'role': 'user', 'content': prompt}],
        )
        raw = msg.content[0].text.strip()
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
