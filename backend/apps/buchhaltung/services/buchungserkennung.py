"""
Hybride Buchungserkennung
Stufe 1: Regelbasiert (IBAN-Lookup + Betragsabgleich)
Stufe 2: Claude API Fallback
"""
import json
import logging
from decimal import Decimal

from django.conf import settings

logger = logging.getLogger(__name__)


def erkenne_buchung(bank_import) -> dict | None:
    """
    Versucht einen BankImport-Eintrag einer Buchung zuzuordnen.
    Gibt ein ki_vorschlag-Dict zurück oder None.

    Vorschlag-Format:
    {
        "stufe": 1 oder 2,
        "konfidenz": "hoch" | "mittel" | "niedrig",
        "personenkonto_id": "...",
        "unterkonto_id": "...",
        "soll_konto_id": "...",
        "haben_konto_id": "...",
        "begruendung": "..."
    }
    """
    vorschlag = _stufe1_regelbasiert(bank_import)
    if vorschlag:
        return vorschlag

    return _stufe2_claude(bank_import)


def _stufe1_regelbasiert(bank_import) -> dict | None:
    """
    Regelbasierte Erkennung:
    1. IBAN des Auftraggebers in Person.ibans suchen
    2. Aktives EigentumsVerhaeltnis dieser Person in diesem Objekt finden
    3. Betragsabgleich mit HausgeldHistorie
    """
    from apps.personen.models import Person, EigentumsVerhaeltnis
    from apps.konten.models import Personenkonto, Unterkonto

    iban = bank_import.auftraggeber_iban.strip().replace(' ', '')
    if not iban:
        return None

    # Person mit dieser IBAN suchen
    person = None
    for p in Person.objects.filter(person_typ='Eigentuemer'):
        ibans = [i.replace(' ', '').strip() for i in (p.ibans or [])]
        if iban in ibans:
            person = p
            break

    if not person:
        return None

    # Aktives EigentumsVerhaeltnis im selben Objekt
    ev = EigentumsVerhaeltnis.objects.filter(
        person=person,
        einheit__objekt=bank_import.objekt,
        ende__isnull=True
    ).select_related('einheit', 'personenkonto').first()

    if not ev:
        return None

    try:
        pk = ev.personenkonto
    except Personenkonto.DoesNotExist:
        return None

    # Hausgeld-Unterkonto .900
    unterkonto = Unterkonto.objects.filter(
        personenkonto=pk, suffix='.900'
    ).first()

    if not unterkonto:
        return None

    # Konfidenz: hoch wenn Betrag exakt passt, mittel sonst
    hausgeld = ev.hausgeld_soll
    betrag = abs(bank_import.betrag)
    if hausgeld and abs(Decimal(str(hausgeld)) - betrag) < Decimal('0.01'):
        konfidenz = 'hoch'
    else:
        konfidenz = 'mittel'

    return {
        'stufe': 1,
        'konfidenz': konfidenz,
        'personenkonto_id': str(pk.id),
        'unterkonto_id': str(unterkonto.id),
        'begruendung': (
            f"IBAN {iban} → {person.name}, "
            f"Einheit {ev.einheit.einheit_nr}, "
            f"Hausgeld .900"
        ),
    }


def _stufe2_claude(bank_import) -> dict | None:
    """
    Claude API Fallback: Strukturierte Buchungserkennung per KI.
    """
    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic-Paket nicht installiert — KI-Fallback übersprungen")
        return None

    api_key = getattr(settings, 'ANTHROPIC_API_KEY', None)
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY nicht konfiguriert — KI-Fallback übersprungen")
        return None

    # Sachkonten des Objekts für den Prompt aufbereiten
    from apps.konten.models import Konto, Personenkonto
    konten = list(
        Konto.objects.filter(objekt=bank_import.objekt, aktiv=True)
        .values('id', 'kontonummer', 'kontoname', 'kontoart')
        .order_by('kontonummer')
    )
    personenkonten = list(
        Personenkonto.objects.filter(objekt=bank_import.objekt, status='aktiv')
        .select_related('eigentuemer')
        .values('id', 'kontonummer', 'eigentuemer__vorname', 'eigentuemer__nachname',
                'eigentuemer__firmenname')
    )

    konten_text = '\n'.join(
        f"  {k['kontonummer']} — {k['kontoname']} ({k['kontoart']})"
        for k in konten[:50]
    )
    personen_text = '\n'.join(
        f"  {pk['kontonummer']} — {pk['eigentuemer__firmenname'] or pk['eigentuemer__nachname']}"
        for pk in personenkonten[:30]
    )

    prompt = f"""Du bist ein Buchhalter-Assistent für WEG-Verwaltung.

Analysiere diese Banktransaktion und schlage die passende Buchung vor:

Transaktion:
- Datum: {bank_import.buchungsdatum}
- Betrag: {bank_import.betrag} EUR
- Auftraggeber: {bank_import.auftraggeber_name or '(unbekannt)'}
- Auftraggeber-IBAN: {bank_import.auftraggeber_iban or '(unbekannt)'}
- Verwendungszweck: {bank_import.verwendungszweck or '(leer)'}

Verfügbare Sachkonten:
{konten_text}

Personenkonten (Eigentümer):
{personen_text}

Antworte NUR mit einem JSON-Objekt (kein Markdown) in diesem Format:
{{
  "konfidenz": "hoch" | "mittel" | "niedrig",
  "soll_konto_nr": "...",
  "haben_konto_nr": "...",
  "personenkonto_nr": "..." oder null,
  "begruendung": "kurze Erklärung"
}}"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        model = getattr(settings, 'ANTHROPIC_MODEL', 'claude-sonnet-4-5')
        message = client.messages.create(
            model=model,
            max_tokens=512,
            messages=[{'role': 'user', 'content': prompt}]
        )
        raw = message.content[0].text.strip()
        ki_result = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("Claude API lieferte kein gültiges JSON: %s", raw)
        return None
    except Exception as exc:
        logger.error("Claude API Fehler: %s", exc)
        return None

    # IDs auflösen
    from apps.konten.models import Konto as KontoModel, Personenkonto as PKModel
    result = {'stufe': 2, **ki_result}

    soll_nr = ki_result.get('soll_konto_nr')
    haben_nr = ki_result.get('haben_konto_nr')
    pk_nr = ki_result.get('personenkonto_nr')

    if soll_nr:
        k = KontoModel.objects.filter(
            objekt=bank_import.objekt, kontonummer=soll_nr
        ).first()
        if k:
            result['soll_konto_id'] = str(k.id)

    if haben_nr:
        k = KontoModel.objects.filter(
            objekt=bank_import.objekt, kontonummer=haben_nr
        ).first()
        if k:
            result['haben_konto_id'] = str(k.id)

    if pk_nr:
        pk = PKModel.objects.filter(
            objekt=bank_import.objekt, kontonummer=pk_nr
        ).first()
        if pk:
            result['personenkonto_id'] = str(pk.id)

    return result


def lerne_aus_buchung(bank_import) -> None:
    """
    KI-Lernfunktion: Bestätigte manuelle Zuordnungen werden als Regel gespeichert.
    Aktuell: IBAN → Person-ibans-Liste ergänzen wenn noch nicht vorhanden.
    """
    if bank_import.status != 'manuell':
        return
    if not bank_import.auftraggeber_iban or not bank_import.buchung:
        return

    buchung = bank_import.buchung
    if not buchung.unterkonto:
        return

    try:
        ev = buchung.unterkonto.personenkonto.vertrag
        person = ev.person
    except Exception:
        return

    iban = bank_import.auftraggeber_iban.strip()
    ibans = [i.strip() for i in (person.ibans or [])]
    if iban not in ibans:
        ibans.append(iban)
        person.ibans = ibans
        person.save(update_fields=['ibans'])
        logger.info(
            "Lernfunktion: IBAN %s zu Person %s hinzugefügt", iban, person.name
        )
