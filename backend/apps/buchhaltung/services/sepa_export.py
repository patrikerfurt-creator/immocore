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


def exportiere_sepa(
    zahlungen: list[dict] = None,
    auftraggeber: dict = None,
    *,
    gruppen: list[dict] | None = None,
) -> bytes:
    """
    Erstellt SEPA pain.001.001.09 XML.

    Entweder (zahlungen, auftraggeber) für einen Auftraggeber übergeben,
    oder gruppen=[{'auftraggeber': {...}, 'zahlungen': [...]}] für mehrere.

    auftraggeber: {'name', 'iban', 'bic', 'bank_bezeichnung'}
    zahlungen:    [{'betrag', 'empfaenger_name', 'empfaenger_iban', 'empfaenger_bic',
                    'verwendungszweck', 'faelligkeitsdatum', 'end_to_end_id' (opt.)}]
    """
    if gruppen is None:
        gruppen = [{'auftraggeber': auftraggeber, 'zahlungen': zahlungen or []}]

    alle_zahlungen = [z for g in gruppen for z in g['zahlungen']]

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
    _sub(grp_hdr, 'NbOfTxs', len(alle_zahlungen))
    _sub(grp_hdr, 'CtrlSum', f'{sum(z["betrag"] for z in alle_zahlungen):.2f}')
    initiating = _sub(grp_hdr, 'InitgPty')
    _sub(initiating, 'Nm', gruppen[0]['auftraggeber']['name'][:70])

    # Payment Information: ein Block pro (Auftraggeber-IBAN, Fälligkeitsdatum)
    for gruppe in gruppen:
        ag = gruppe['auftraggeber']
        pmt_gruppen: dict[str, list] = {}
        for z in gruppe['zahlungen']:
            dt = z['faelligkeitsdatum']
            dt_str = dt.isoformat() if isinstance(dt, date) else str(dt)
            pmt_gruppen.setdefault(dt_str, []).append(z)

        for dt_str, txs in pmt_gruppen.items():
            pmt_inf = _sub(init, 'PmtInf')
            _sub(pmt_inf, 'PmtInfId', str(uuid.uuid4()).replace('-', '')[:35])
            _sub(pmt_inf, 'PmtMtd', 'TRF')
            _sub(pmt_inf, 'NbOfTxs', len(txs))
            _sub(pmt_inf, 'CtrlSum', f'{sum(z["betrag"] for z in txs):.2f}')

            pmt_tp_inf = _sub(pmt_inf, 'PmtTpInf')
            _sub(_sub(pmt_tp_inf, 'SvcLvl'), 'Cd', 'SEPA')
            _sub(_sub(pmt_tp_inf, 'LclInstrm'), 'Cd', 'CORE')

            _sub(pmt_inf, 'ReqdExctnDt', dt_str)
            _sub(_sub(pmt_inf, 'Dbtr'), 'Nm', ag['name'][:70])

            dbtr_acct = _sub(pmt_inf, 'DbtrAcct')
            _sub(_sub(dbtr_acct, 'Id'), 'IBAN', ag['iban'])

            _sub(_sub(_sub(pmt_inf, 'DbtrAgt'), 'FinInstnId'), 'BICFI', ag['bic'] or 'NOTPROVIDED')

            for z in txs:
                cdt_trf = _sub(pmt_inf, 'CdtTrfTxInf')
                e2e = z.get('end_to_end_id') or str(uuid.uuid4()).replace('-', '')[:35]
                _sub(_sub(cdt_trf, 'PmtId'), 'EndToEndId', e2e[:35])

                instd = _sub(_sub(cdt_trf, 'Amt'), 'InstdAmt', f'{z["betrag"]:.2f}')
                instd.set('Ccy', 'EUR')

                _sub(_sub(_sub(cdt_trf, 'CdtrAgt'), 'FinInstnId'), 'BICFI', z.get('empfaenger_bic', 'NOTPROVIDED'))
                _sub(_sub(cdt_trf, 'Cdtr'), 'Nm', z['empfaenger_name'][:70])
                _sub(_sub(_sub(cdt_trf, 'CdtrAcct'), 'Id'), 'IBAN', z['empfaenger_iban'])
                _sub(_sub(cdt_trf, 'RmtInf'), 'Ustrd', z.get('verwendungszweck', '')[:140])

    xml_str = ET.tostring(doc, encoding='unicode', xml_declaration=False)
    dom = minidom.parseString(f'<?xml version="1.0" encoding="UTF-8"?>{xml_str}')
    return dom.toprettyxml(indent='  ', encoding='UTF-8')
