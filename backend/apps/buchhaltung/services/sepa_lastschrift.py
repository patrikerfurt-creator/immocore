"""
SEPA pain.008.003.02 — SEPA Direct Debit Initiation
Erzeugt SEPA-Lastschrift XML für Hausgeldeinzüge.
Kompatibel mit: Windata, S-Firm, StarMoney, Profi cash
"""
import uuid
from datetime import date
from xml.etree import ElementTree as ET
from xml.dom import minidom


NS = 'urn:iso:std:iso:20022:tech:xsd:pain.008.003.02'
XSI = 'http://www.w3.org/2001/XMLSchema-instance'
SCHEMA_LOC = (
    'urn:iso:std:iso:20022:tech:xsd:pain.008.003.02 '
    'pain.008.003.02.xsd'
)


def _sub(parent, tag, text=None):
    el = ET.SubElement(parent, tag)
    if text is not None:
        el.text = str(text)
    return el


def exportiere_lastschrift(lastschriften: list[dict], glaeubiger: dict) -> bytes:
    """
    Erstellt SEPA pain.008.003.02 XML für Lastschriften.

    glaeubiger: {
        'name': str,
        'iban': str,
        'bic': str,
        'glaeubiger_id': str,   # DE98ZZZ09999999999
    }

    lastschriften: Liste von {
        'betrag': Decimal,
        'schuldner_name': str,
        'schuldner_iban': str,
        'schuldner_bic': str,
        'mandatsreferenz': str,
        'mandat_datum': date,
        'verwendungszweck': str,
        'faelligkeitsdatum': date,
        'seq_typ': str,         # 'FRST' oder 'RCUR' (default: 'RCUR')
        'end_to_end_id': str    # optional
    }

    Gibt UTF-8 kodierte XML-Bytes zurück.
    """
    ET.register_namespace('', NS)

    doc = ET.Element('Document', attrib={
        'xmlns': NS,
        'xmlns:xsi': XSI,
        'xsi:schemaLocation': SCHEMA_LOC,
    })

    init = _sub(doc, 'CstmrDrctDbtInitn')

    # Group Header
    grp_hdr = _sub(init, 'GrpHdr')
    msg_id = str(uuid.uuid4()).replace('-', '')[:35]
    _sub(grp_hdr, 'MsgId', msg_id)
    _sub(grp_hdr, 'CreDtTm', date.today().isoformat() + 'T00:00:00')
    _sub(grp_hdr, 'NbOfTxs', len(lastschriften))
    ctrl_sum = sum(z['betrag'] for z in lastschriften)
    _sub(grp_hdr, 'CtrlSum', f'{ctrl_sum:.2f}')
    initiating = _sub(grp_hdr, 'InitgPty')
    _sub(initiating, 'Nm', glaeubiger['name'][:70])

    # Group by (faelligkeitsdatum, seq_typ, kreditorkonto_iban).
    # kreditorkonto_iban erlaubt pro Position eine abweichende Gläubiger-IBAN
    # (z.B. unterschiedliche Bankkonten für Bewirtschaftung vs. Rücklagen).
    gruppen: dict[tuple, list] = {}
    for z in lastschriften:
        dt = z['faelligkeitsdatum']
        dt_str = dt.isoformat() if isinstance(dt, date) else str(dt)
        seq = z.get('seq_typ', 'RCUR')
        kreditor_iban = z.get('kreditorkonto_iban', glaeubiger['iban'])
        gruppen.setdefault((dt_str, seq, kreditor_iban), []).append(z)

    for (dt_str, seq, kreditor_iban), gruppe in gruppen.items():
        eff_iban = gruppe[0].get('kreditorkonto_iban', glaeubiger['iban'])
        eff_bic  = gruppe[0].get('kreditorkonto_bic',  glaeubiger['bic'])

        pmt_inf = _sub(init, 'PmtInf')
        pmt_inf_id = str(uuid.uuid4()).replace('-', '')[:35]
        _sub(pmt_inf, 'PmtInfId', pmt_inf_id)
        _sub(pmt_inf, 'PmtMtd', 'DD')
        _sub(pmt_inf, 'NbOfTxs', len(gruppe))
        _sub(pmt_inf, 'CtrlSum', f'{sum(z["betrag"] for z in gruppe):.2f}')

        pmt_tp_inf = _sub(pmt_inf, 'PmtTpInf')
        svc_lvl = _sub(pmt_tp_inf, 'SvcLvl')
        _sub(svc_lvl, 'Cd', 'SEPA')
        lcl_instrm = _sub(pmt_tp_inf, 'LclInstrm')
        _sub(lcl_instrm, 'Cd', 'CORE')
        _sub(pmt_tp_inf, 'SeqTp', seq)

        _sub(pmt_inf, 'ReqdColltnDt', dt_str)

        cdtr = _sub(pmt_inf, 'Cdtr')
        _sub(cdtr, 'Nm', glaeubiger['name'][:70])

        cdtr_acct = _sub(pmt_inf, 'CdtrAcct')
        cdtr_id = _sub(cdtr_acct, 'Id')
        _sub(cdtr_id, 'IBAN', eff_iban)

        cdtr_agt = _sub(pmt_inf, 'CdtrAgt')
        fin_instn = _sub(cdtr_agt, 'FinInstnId')
        _sub(fin_instn, 'BIC', eff_bic)

        # Gläubiger-ID
        cdtr_schme = _sub(pmt_inf, 'CdtrSchmeId')
        cdtr_schme_id = _sub(cdtr_schme, 'Id')
        prv_id = _sub(cdtr_schme_id, 'PrvtId')
        othr = _sub(prv_id, 'Othr')
        _sub(othr, 'Id', glaeubiger['glaeubiger_id'])
        schme_nm = _sub(othr, 'SchmeNm')
        _sub(schme_nm, 'Prtry', 'SEPA')

        for z in gruppe:
            drct_dbt = _sub(pmt_inf, 'DrctDbtTxInf')

            pmt_id = _sub(drct_dbt, 'PmtId')
            e2e = z.get('end_to_end_id') or str(uuid.uuid4()).replace('-', '')[:35]
            _sub(pmt_id, 'EndToEndId', e2e[:35])

            instd_amt = _sub(drct_dbt, 'InstdAmt', f'{z["betrag"]:.2f}')
            instd_amt.set('Ccy', 'EUR')

            drct_dbt_tx = _sub(drct_dbt, 'DrctDbtTx')
            mndt = _sub(drct_dbt_tx, 'MndtRltdInf')
            _sub(mndt, 'MndtId', z['mandatsreferenz'][:35])
            mandat_dt = z['mandat_datum']
            _sub(mndt, 'DtOfSgntr', mandat_dt.isoformat() if isinstance(mandat_dt, date) else str(mandat_dt))

            dbtr_agt = _sub(drct_dbt, 'DbtrAgt')
            dbtr_fin = _sub(dbtr_agt, 'FinInstnId')
            _sub(dbtr_fin, 'BIC', z.get('schuldner_bic', 'NOTPROVIDED'))

            dbtr = _sub(drct_dbt, 'Dbtr')
            _sub(dbtr, 'Nm', z['schuldner_name'][:70])

            dbtr_acct = _sub(drct_dbt, 'DbtrAcct')
            dbtr_acct_id = _sub(dbtr_acct, 'Id')
            _sub(dbtr_acct_id, 'IBAN', z['schuldner_iban'])

            rmt_inf = _sub(drct_dbt, 'RmtInf')
            _sub(rmt_inf, 'Ustrd', z.get('verwendungszweck', '')[:140])

    xml_str = ET.tostring(doc, encoding='unicode', xml_declaration=False)
    dom = minidom.parseString(f'<?xml version="1.0" encoding="UTF-8"?>{xml_str}')
    return dom.toprettyxml(indent='  ', encoding='UTF-8')


# ---------------------------------------------------------------------------
# Hilfsfunktionen für Lastschrift aus dem Hausgeld-Nebenbuch (Phase C)
# ---------------------------------------------------------------------------

def bestimme_suffix(bankkonto_id, objekt) -> str:
    """
    Bestimmt den EndToEnd-Suffix für eine Sollstellung.
    'B' für Bewirtschaftungskonto, 'R{n}' für Rücklagenkonto Nr. n.
    """
    from apps.objekte.models import Bankkonto
    bk = Bankkonto.objects.get(pk=bankkonto_id)
    if bk.konto_typ == 'bewirtschaftung':
        return 'B'
    elif bk.konto_typ == 'ruecklage':
        return f'R{bk.reihenfolge - 1}'
    raise ValueError(f"Unbekannter Bankkonto-Typ: {bk.konto_typ}")


def commite_lastschriftlauf(
    objekt,
    stichtag,
    kandidaten: list,
    user,
    lauf_quelle: str = 'manuell',
):
    """
    Erstellt einen LastschriftLauf aus einer Liste von HausgeldSollstellungen.
    Alle OPOS eines EV werden zu einer einzigen SEPA-Position zusammengefasst
    (Einzug auf das Bewirtschaftungskonto des Objekts).

    Returns: LastschriftLauf
    """
    from decimal import Decimal
    from apps.buchhaltung.models import LastschriftLauf
    from apps.objekte.models import Bankkonto as BKModel

    # Bewirtschaftungskonto als einziges Zielkonto für alle Einzüge
    hauptkonto = BKModel.objects.filter(
        objekt=objekt, konto_typ='bewirtschaftung', aktiv=True
    ).first()
    if not hauptkonto:
        raise ValueError(f'Kein aktives Bewirtschaftungs-Bankkonto für Objekt {objekt}')

    positionen = []
    gesamt = Decimal('0')
    sollstellungslauf = kandidaten[0].sollstellungslauf if kandidaten else None
    faelligkeitsdatum_str = stichtag.isoformat() if hasattr(stichtag, 'isoformat') else str(stichtag)
    periode_str = stichtag.strftime('%m/%Y') if hasattr(stichtag, 'strftime') else str(stichtag)

    # Gruppierung nach EV: alle Sollstellungen einer Person → eine SEPA-Position
    ev_map: dict = {}

    for ss in kandidaten:
        ev = ss.eigentumsverhaeltnis
        ev_id = str(ev.id)
        person = ev.person
        mandat = person.sepa_mandat

        if ev_id not in ev_map:
            try:
                personenkonto_id = str(ev.personenkonto.id)
            except Exception:
                personenkonto_id = None
            ev_map[ev_id] = {
                'betrag':          Decimal('0'),
                'sollstellung_ids': [],
                'primary_opos_nr': ss.opos_nr,
                'schuldner_name':  person.name,
                'schuldner_iban':  mandat.iban,
                'schuldner_bic':   mandat.bic or 'NOTPROVIDED',
                'mandatsreferenz': mandat.mandatsreferenz,
                'mandat_datum':    mandat.unterzeichnet_am.isoformat(),
                'personenkonto_id': personenkonto_id,
                'einheit_nr':      ev.einheit.einheit_nr,
            }

        # Gesamtbetrag aller Splits summieren
        split_sum = sum(
            s.betrag for s in ss.splits.all() if s.bankkonto_ziel is not None
        )
        if not split_sum:
            split_sum = ss.soll_betrag  # Fallback wenn keine Splits vorhanden

        ev_map[ev_id]['betrag'] += split_sum
        ev_map[ev_id]['sollstellung_ids'].append(str(ss.id))

    # Eine Position je EV erzeugen
    objekt_kurz = objekt.kurzbezeichnung or objekt.bezeichnung
    for ev_id, data in ev_map.items():
        if data['betrag'] <= 0:
            continue
        verwendungszweck = (
            f"Hausgeld {periode_str} - {data['einheit_nr']} - Objekt {objekt_kurz}"
        )
        pos = {
            'sollstellung_ids':   data['sollstellung_ids'],
            'sollstellung_id':    data['sollstellung_ids'][0],
            'end_to_end_id':      data['primary_opos_nr'],
            'betrag':             str(data['betrag']),
            'schuldner_name':     data['schuldner_name'],
            'schuldner_iban':     data['schuldner_iban'],
            'schuldner_bic':      data['schuldner_bic'],
            'mandatsreferenz':    data['mandatsreferenz'],
            'mandat_datum':       data['mandat_datum'],
            'verwendungszweck':   verwendungszweck,
            'faelligkeitsdatum':  faelligkeitsdatum_str,
            'seq_typ':            'RCUR',
            'kreditorkonto_iban': hauptkonto.iban,
            'kreditorkonto_bic':  hauptkonto.bic or 'NOTPROVIDED',
            'personenkonto_id':   data['personenkonto_id'],
        }
        positionen.append(pos)
        gesamt += data['betrag']

    bezeichnung = f'Hausgeld {periode_str}'
    lauf = LastschriftLauf.objects.create(
        objekt=objekt,
        hausgeld_sollstellungslauf=sollstellungslauf,
        bezeichnung=bezeichnung,
        faelligkeitsdatum=stichtag,
        erstellt_von=user,
        anzahl_positionen=len(positionen),
        gesamt_summe=gesamt,
        positionen=positionen,
        lauf_quelle=lauf_quelle,
    )
    return lauf


def generiere_pain008(lastschriftlauf) -> str:
    """
    Generiert pain.008 XML-String aus einem LastschriftLauf.
    Gibt einen UTF-8 dekodierten String zurück.
    """
    from decimal import Decimal
    from datetime import date as date_type
    from apps.objekte.models import Bankkonto

    bankkonto = Bankkonto.objects.filter(
        objekt=lastschriftlauf.objekt,
        zahlungsverkehr=True,
        aktiv=True,
    ).first()
    if not bankkonto:
        raise ValueError(
            f'Kein aktives Zahlungsverkehr-Bankkonto für Objekt {lastschriftlauf.objekt}'
        )

    glaeubiger = {
        'name': bankkonto.kontoinhaber or lastschriftlauf.objekt.bezeichnung,
        'iban': bankkonto.iban,
        'bic': bankkonto.bic or 'NOTPROVIDED',
        'glaeubiger_id': lastschriftlauf.objekt.glaeubiger_id or '',
    }

    lastschriften = []
    for pos in lastschriftlauf.positionen:
        p = dict(pos)
        p['betrag'] = Decimal(p['betrag'])
        p['faelligkeitsdatum'] = date_type.fromisoformat(p['faelligkeitsdatum'])
        p['mandat_datum'] = date_type.fromisoformat(p['mandat_datum'])
        lastschriften.append(p)

    xml_bytes = exportiere_lastschrift(lastschriften, glaeubiger)
    return xml_bytes.decode('utf-8')


def erstelle_lastschrift_buchungen(lastschriftlauf, user):
    """
    Erstellt Buchungen (Soll 13650 / Haben Personenkonto) und gleicht alle
    offenen OPOS des jeweiligen Personenkontos aus.

    Idempotent: tut nichts, wenn buchungen_erstellt bereits True ist.
    Wird von der Auto-Pipeline direkt nach generiere_pain008() aufgerufen
    und vom manuellen xml-Endpoint (LastschriftLaufViewSet.xml).
    """
    from decimal import Decimal
    from django.db import transaction as db_transaction
    from apps.buchhaltung.models import Buchung, OffenerPosten
    from apps.konten.models import Konto, Personenkonto as PKModel
    from apps.objekte.models import Wirtschaftsjahr

    if lastschriftlauf.buchungen_erstellt:
        return  # Idempotent

    objekt = lastschriftlauf.objekt
    wj = Wirtschaftsjahr.objects.filter(
        objekt=objekt, jahr=lastschriftlauf.faelligkeitsdatum.year
    ).first()
    gegenkonto = Konto.objects.filter(
        wirtschaftsjahr__objekt=objekt, kontonummer='13650'
    ).first()
    if not gegenkonto:
        raise ValueError(f'Konto 13650 (DCL-Debitor) nicht im Kontenplan für Objekt {objekt}')

    prefix = f'LS-{lastschriftlauf.faelligkeitsdatum.year}-'
    last_belegnr = (
        Buchung.objects.filter(belegnr__startswith=prefix)
        .order_by('-belegnr').values_list('belegnr', flat=True).first()
    )
    try:
        lfd = int(last_belegnr.rsplit('-', 1)[-1]) + 1 if last_belegnr else 1
    except ValueError:
        lfd = 1

    positionen_updated = []
    with db_transaction.atomic():
        for p in lastschriftlauf.positionen:
            pk_id = p.get('personenkonto_id')
            if not pk_id:
                positionen_updated.append(p)
                continue
            try:
                pk_obj = PKModel.objects.get(id=pk_id)
            except PKModel.DoesNotExist:
                positionen_updated.append(p)
                continue

            betrag = Decimal(str(p['betrag']))
            belegnr = f'{prefix}{lfd:05d}'
            lfd += 1

            buchung = Buchung.objects.create(
                objekt=objekt,
                soll_konto=gegenkonto,
                personenkonto=pk_obj,
                betrag=betrag,
                buchungsdatum=lastschriftlauf.faelligkeitsdatum,
                buchungstext=(
                    p.get('verwendungszweck')
                    or f"SEPA-Lastschrift {p['schuldner_name']}"
                ),
                belegnr=belegnr,
                beleg_referenz=f'LS-{str(lastschriftlauf.id)[:8]}',
                wirtschaftsjahr=wj,
                status='festgeschrieben',
                erstellt_von=user,
            )

            # Alle offenen OPOS des Personenkontos ausgleichen
            opos = list(OffenerPosten.objects.filter(
                personenkonto=pk_obj,
                status__in=['offen', 'teilverrechnet'],
            ))
            for op in opos:
                op.betrag_offen = Decimal('0')
                op.status = 'verrechnet'
                op.save(update_fields=['betrag_offen', 'status'])

            positionen_updated.append({
                **p,
                'buchung_id': str(buchung.id),
                'belegnr': belegnr,
                'opos_ausgeglichen': len(opos),
            })

        lastschriftlauf.buchungen_erstellt = True
        lastschriftlauf.buchungen_datum = lastschriftlauf.faelligkeitsdatum
        lastschriftlauf.positionen = positionen_updated
        lastschriftlauf.status = 'exportiert'
        lastschriftlauf.save(update_fields=[
            'buchungen_erstellt', 'buchungen_datum', 'positionen', 'status'
        ])


def baue_verwendungszweck(ss, suffix: str) -> str:
    """
    Menschenlesbarer Verwendungszweck ohne OPOS-Nr.
    Format: {Zweck} {MM/YYYY} - {Einheit_Nr} - Objekt {Kurzbez}
    """
    einheit_nr = ss.eigentumsverhaeltnis.einheit.einheit_nr
    objekt_kurz = ss.objekt.kurzbezeichnung or ss.objekt.bezeichnung
    periode_str = ss.periode.strftime('%m/%Y')

    if ss.sollstellungs_typ == 'hausgeld':
        zweck = 'Rücklage' if suffix.startswith('R') else 'Hausgeld'
    elif ss.sollstellungs_typ == 'sonderumlage':
        bezeichnung = getattr(ss, 'bezeichnung', '') or ''
        zweck = f'Sonderumlage {bezeichnung}'.strip()
    else:
        zweck = f'Abrechnung {ss.periode.year}'

    return f"{zweck} {periode_str} - {einheit_nr} - Objekt {objekt_kurz}"
