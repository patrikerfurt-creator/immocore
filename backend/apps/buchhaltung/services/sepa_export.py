"""
SEPA pain.001.001.09 Export
Erzeugt SEPA-Lastschrift/Überweisung XML aus Buchungen.
Kompatibel mit: Windata, S-Firm, StarMoney, Profi cash
"""
import uuid
from datetime import date
from decimal import Decimal
from xml.etree import ElementTree as ET
from xml.dom import minidom


NS = 'urn:iso:std:iso:20022:tech:xsd:pain.001.001.09'
XSI = 'http://www.w3.org/2001/XMLSchema-instance'
SCHEMA_LOC = (
    'urn:iso:std:iso:20022:tech:xsd:pain.001.001.09 '
    'pain.001.001.09.xsd'
)


def _sub(parent, tag, text=None):
    el = ET.SubElement(parent, tag)
    if text is not None:
        el.text = str(text)
    return el


def exportiere_sepa(zahlungen: list[dict], auftraggeber: dict) -> bytes:
    """
    Erstellt SEPA pain.001.001.09 XML.

    auftraggeber: {
        'name': str,
        'iban': str,
        'bic': str,
        'bank_bezeichnung': str
    }

    zahlungen: Liste von {
        'betrag': Decimal,
        'empfaenger_name': str,
        'empfaenger_iban': str,
        'empfaenger_bic': str,
        'verwendungszweck': str,
        'faelligkeitsdatum': date,
        'end_to_end_id': str (optional)
    }

    Gibt UTF-8 kodierte XML-Bytes zurück.
    """
    ET.register_namespace('', NS)

    doc = ET.Element('Document', attrib={
        'xmlns': NS,
        'xmlns:xsi': XSI,
        'xsi:schemaLocation': SCHEMA_LOC,
    })

    init = _sub(doc, 'CstmrCdtTrfInitn')

    # Group Header
    grp_hdr = _sub(init, 'GrpHdr')
    msg_id = str(uuid.uuid4()).replace('-', '')[:35]
    _sub(grp_hdr, 'MsgId', msg_id)
    _sub(grp_hdr, 'CreDtTm', date.today().isoformat() + 'T00:00:00')
    _sub(grp_hdr, 'NbOfTxs', len(zahlungen))

    ctrl_sum = sum(z['betrag'] for z in zahlungen)
    _sub(grp_hdr, 'CtrlSum', f'{ctrl_sum:.2f}')

    initiating = _sub(grp_hdr, 'InitgPty')
    _sub(initiating, 'Nm', auftraggeber['name'][:70])

    # Payment Information (ein Block pro Fälligkeitsdatum)
    gruppen: dict[str, list] = {}
    for z in zahlungen:
        dt = z['faelligkeitsdatum']
        if isinstance(dt, date):
            dt_str = dt.isoformat()
        else:
            dt_str = str(dt)
        gruppen.setdefault(dt_str, []).append(z)

    for dt_str, gruppe in gruppen.items():
        pmt_inf = _sub(init, 'PmtInf')
        pmt_inf_id = str(uuid.uuid4()).replace('-', '')[:35]
        _sub(pmt_inf, 'PmtInfId', pmt_inf_id)
        _sub(pmt_inf, 'PmtMtd', 'TRF')
        _sub(pmt_inf, 'NbOfTxs', len(gruppe))
        _sub(pmt_inf, 'CtrlSum', f'{sum(z["betrag"] for z in gruppe):.2f}')

        pmt_tp_inf = _sub(pmt_inf, 'PmtTpInf')
        svc_lvl = _sub(pmt_tp_inf, 'SvcLvl')
        _sub(svc_lvl, 'Cd', 'SEPA')
        lcl_instrm = _sub(pmt_tp_inf, 'LclInstrm')
        _sub(lcl_instrm, 'Cd', 'CORE')

        _sub(pmt_inf, 'ReqdExctnDt', dt_str)

        dbtr = _sub(pmt_inf, 'Dbtr')
        _sub(dbtr, 'Nm', auftraggeber['name'][:70])

        dbtr_acct = _sub(pmt_inf, 'DbtrAcct')
        dbtr_id = _sub(dbtr_acct, 'Id')
        _sub(dbtr_id, 'IBAN', auftraggeber['iban'])

        dbtr_agt = _sub(pmt_inf, 'DbtrAgt')
        fin_instn = _sub(dbtr_agt, 'FinInstnId')
        _sub(fin_instn, 'BICFI', auftraggeber['bic'])

        for z in gruppe:
            cdt_trf = _sub(pmt_inf, 'CdtTrfTxInf')

            pmt_id = _sub(cdt_trf, 'PmtId')
            e2e = z.get('end_to_end_id') or str(uuid.uuid4()).replace('-', '')[:35]
            _sub(pmt_id, 'EndToEndId', e2e[:35])

            amt = _sub(cdt_trf, 'Amt')
            instd = _sub(amt, 'InstdAmt', f'{z["betrag"]:.2f}')
            instd.set('Ccy', 'EUR')

            cdtr_agt = _sub(cdt_trf, 'CdtrAgt')
            cdtr_fin = _sub(cdtr_agt, 'FinInstnId')
            _sub(cdtr_fin, 'BICFI', z.get('empfaenger_bic', 'NOTPROVIDED'))

            cdtr = _sub(cdt_trf, 'Cdtr')
            _sub(cdtr, 'Nm', z['empfaenger_name'][:70])

            cdtr_acct = _sub(cdt_trf, 'CdtrAcct')
            cdtr_id = _sub(cdtr_acct, 'Id')
            _sub(cdtr_id, 'IBAN', z['empfaenger_iban'])

            rmt_inf = _sub(cdt_trf, 'RmtInf')
            verwendungszweck = z.get('verwendungszweck', '')[:140]
            _sub(rmt_inf, 'Ustrd', verwendungszweck)

    # Schön formatiertes XML
    xml_str = ET.tostring(doc, encoding='unicode', xml_declaration=False)
    dom = minidom.parseString(f'<?xml version="1.0" encoding="UTF-8"?>{xml_str}')
    return dom.toprettyxml(indent='  ', encoding='UTF-8')
