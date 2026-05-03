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

    # Group by (faelligkeitsdatum, seq_typ)
    gruppen: dict[tuple, list] = {}
    for z in lastschriften:
        dt = z['faelligkeitsdatum']
        dt_str = dt.isoformat() if isinstance(dt, date) else str(dt)
        seq = z.get('seq_typ', 'RCUR')
        gruppen.setdefault((dt_str, seq), []).append(z)

    for (dt_str, seq), gruppe in gruppen.items():
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
        _sub(cdtr_id, 'IBAN', glaeubiger['iban'])

        cdtr_agt = _sub(pmt_inf, 'CdtrAgt')
        fin_instn = _sub(cdtr_agt, 'FinInstnId')
        _sub(fin_instn, 'BIC', glaeubiger['bic'])

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
