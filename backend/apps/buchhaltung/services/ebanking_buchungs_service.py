"""
E-Banking Verbuchungsservice (Phase C).

verbuche() schreibt im Hauptbuch eine Buchung und setzt den Kontoumsatz auf 'verbucht'.

Vorzeichen-Logik:
  Betrag > 0 (Eingang):  Soll Bank   / Haben Gegenkonto
  Betrag < 0 (Ausgang):  Soll Gegen. / Haben Bank
"""
import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def _buchungstext(ku, gk, ev, kr) -> str:
    parts = []
    if kr:
        name = kr.firmenname or f"{kr.vorname or ''} {kr.nachname or ''}".strip()
        if name:
            parts.append(name)
    if ev:
        einheit_nr = getattr(getattr(ev, 'einheit', None), 'einheit_nr', None)
        if einheit_nr:
            parts.append(f"WE{einheit_nr}")
    if ku.verwendungszweck:
        parts.append(ku.verwendungszweck[:60])
    return ' — '.join(p for p in parts if p) or 'Banktransaktion'


def _ermittle_bank_sachkonto(ku):
    """Findet Sachkonto 18xxx für den Bankabgang/-eingang."""
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


def _ermittle_wirtschaftsjahr(objekt, datum):
    """
    Findet das Wirtschaftsjahr für ein gegebenes Datum anhand von beginn_monat.
    Fallback: neuestes offenes WJ des Objekts.
    """
    from datetime import date as date_cls
    from apps.objekte.models import Wirtschaftsjahr

    if objekt is None or datum is None:
        return None

    for wj in Wirtschaftsjahr.objects.filter(objekt=objekt).order_by('-jahr'):
        wj_beginn = date_cls(wj.jahr, wj.beginn_monat, 1)
        try:
            wj_ende = date_cls(wj.jahr + 1, wj.beginn_monat, 1)
        except ValueError:
            continue
        if wj_beginn <= datum < wj_ende:
            return wj

    return (
        Wirtschaftsjahr.objects.filter(objekt=objekt, status='offen')
        .order_by('-jahr')
        .first()
    )


@transaction.atomic
def verbuche(ku, verbucht_von,
             gegenkonto=None,
             eigentumsverhaeltnis=None,
             kreditor=None,
             notiz: str = "",
             kreditor_op_id=None):
    """
    Verbucht einen Kontoumsatz im Hauptbuch.

    Optionale Parameter überschreiben erkannte Werte (manueller Eingriff).
    Gibt die erzeugte Buchung zurück.
    """
    from apps.buchhaltung.models import Buchung

    if ku.status == 'verbucht':
        raise ValidationError("Kontoumsatz ist bereits verbucht.")
    if ku.status == 'storniert':
        raise ValidationError("Kontoumsatz ist storniert.")

    gk = gegenkonto or ku.erkannt_gegenkonto
    ev = eigentumsverhaeltnis or ku.erkannt_eigentumsverhaeltnis
    kr = kreditor or ku.erkannt_kreditor

    if not gk:
        raise ValidationError(
            "Gegenkonto fehlt — bitte erst wählen oder bestätigen."
        )

    # Validierungen
    if gk.kontoart == 'summierung':
        raise ValidationError(
            f"Konto {gk.kontonummer} ist ein Summierungskonto — nicht direkt buchbar."
        )
    if not gk.direktes_buchen:
        raise ValidationError(
            f"Konto {gk.kontonummer} hat direktes_buchen=False — nicht direkt buchbar."
        )
    if ku.objekt:
        from apps.konten.models import Konto
        gleich_objekt = Konto.objects.filter(
            pk=gk.pk,
            wirtschaftsjahr__objekt=ku.objekt,
        ).exists()
        if not gleich_objekt:
            raise ValidationError(
                f"Konto {gk.kontonummer} gehört nicht zu Objekt {ku.objekt}."
            )

    bank_konto = _ermittle_bank_sachkonto(ku)
    if not bank_konto:
        raise ValidationError(
            "Kein Bank-Sachkonto (18xxx) für dieses Objekt gefunden."
        )

    wj = _ermittle_wirtschaftsjahr(ku.objekt, ku.buchungsdatum)

    betrag_abs = abs(ku.betrag)

    if ku.betrag > 0:
        # Eingang: Soll Bank / Haben Gegenkonto
        soll_konto, haben_konto = bank_konto, gk
    else:
        # Ausgang: Soll Gegenkonto / Haben Bank
        soll_konto, haben_konto = gk, bank_konto

    buchungstext = _buchungstext(ku, gk, ev, kr)
    if notiz:
        buchungstext = f"{buchungstext} — {notiz[:60]}"

    b = Buchung.objects.create(
        objekt=ku.objekt,
        betrag=betrag_abs,
        soll_konto=soll_konto,
        haben_konto=haben_konto,
        buchungsdatum=ku.buchungsdatum,
        belegdatum=ku.buchungsdatum,
        buchungstext=buchungstext,
        verwendungszweck=ku.verwendungszweck,
        belegnr=f'EB-{ku.buchungsdatum.strftime("%Y%m%d")}-{str(ku.id)[:8].upper()}',
        status='festgeschrieben',
        erstellt_von=verbucht_von,
        wirtschaftsjahr=wj,
    )

    ku.status          = 'verbucht'
    ku.buchung         = b
    ku.verbucht_am     = timezone.now()
    ku.verbucht_von    = verbucht_von
    ku.erkannt_gegenkonto = gk
    if ev:
        ku.erkannt_eigentumsverhaeltnis = ev
    if kr:
        ku.erkannt_kreditor = kr
    if notiz:
        ku.notiz = notiz
    ku.save()

    # OP-Ausgleich wenn Kreditorkonto (70xxx)
    if gk.kontonummer.startswith('70'):
        # Stufe-3b-Erkennung kann den OP bereits direkt zugeordnet haben
        op_id = kreditor_op_id or (
            ku.erkannt_kreditor_op_id if ku.erkannt_kreditor_op_id else None
        )
        _versuche_op_ausgleich(ku, b, gk, explizit_op_id=op_id)

    return b


def _versuche_op_ausgleich(ku, buchung, kreditorkonto, explizit_op_id=None):
    """
    Wenn ein Kreditorkonto (70xxx) als Gegenkonto gebucht wird,
    versuchen wir den offenen OP auszugleichen (AUSGANG: Bezahlung einer Rechnung).
    Analog zu Phase 3 im OP_BUCHUNG-Workflow.
    """
    from apps.buchhaltung.models import KreditorOP

    if explizit_op_id:
        op = KreditorOP.objects.filter(
            pk=explizit_op_id,
            objekt=ku.objekt,
            status__in=('offen', 'teilbezahlt'),
        ).first()
    else:
        op = KreditorOP.objects.filter(
            objekt=ku.objekt,
            betrag_offen=abs(ku.betrag),
            status__in=('offen', 'teilbezahlt'),
        ).first()

    if not op:
        return

    op.zahlung_buchung = buchung
    op.betrag_offen = Decimal('0.00')
    op.status = 'bezahlt'
    op.save(update_fields=['zahlung_buchung', 'betrag_offen', 'status'])

    if op.rechnung:
        op.rechnung.status = 'bezahlt'
        op.rechnung.save(update_fields=['status'])


@transaction.atomic
def storniere(ku, begruendung: str, storniert_von):
    """
    GoBD-konformes Storno einer verbuchten Bankbuchung.
    Erzeugt eine Storno-Buchung und setzt Status auf 'storniert'.
    """
    from apps.buchhaltung.models import Buchung

    if ku.status != 'verbucht':
        raise ValidationError("Nur verbuchte Kontoumsätze können storniert werden.")

    original = ku.buchung
    if not original:
        raise ValidationError("Keine Buchung zum Stornieren gefunden.")

    storno = Buchung.objects.create(
        objekt=ku.objekt,
        betrag=original.betrag,
        soll_konto=original.haben_konto,
        haben_konto=original.soll_konto,
        buchungsdatum=timezone.now().date(),
        belegdatum=timezone.now().date(),
        buchungstext=f"Storno: {original.buchungstext[:80]} — {begruendung[:60]}",
        status='festgeschrieben',
        storno_von=original,
        erstellt_von=storniert_von,
    )

    original.status = 'storniert'
    original.save(update_fields=['status'])

    ku.status = 'storniert'
    ku.save(update_fields=['status'])

    return storno
