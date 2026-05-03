import xml.etree.ElementTree as ET
import os

def parse_camt_detail(filepath):
    tree = ET.parse(filepath)
    root = tree.getroot()
    ns_uri = root.tag.split('}')[0].lstrip('{') if '}' in root.tag else ''
    pfx = '{' + ns_uri + '}' if ns_uri else ''

    buchungen = []
    for ntry in root.iter(pfx + 'Ntry'):
        def ft(tag, el=ntry):
            node = el.find('.//' + pfx + tag)
            return node.text.strip() if node is not None and node.text else ''

        betrag = ft('Amt')
        cd     = ft('CdtDbtInd')
        datum  = ft('Dt') or ft('BookgDt')
        name   = ft('Nm')
        iban   = ft('IBAN')
        zweck  = ft('Ustrd') or ft('AddtlNtryInf')

        # Einzeltransaktionen (TxDtls) innerhalb Sammelbuchung
        txs = []
        for txdtls in ntry.iter(pfx + 'TxDtls'):
            tx_betrag = ft('Amt', txdtls)
            tx_name   = ft('Nm', txdtls)
            tx_iban   = ft('IBAN', txdtls)
            tx_zweck  = ft('Ustrd', txdtls) or ft('AddtlTxInf', txdtls)
            tx_mandat = ft('MndtId', txdtls)
            if tx_betrag or tx_name:
                txs.append({
                    'betrag': tx_betrag,
                    'name':   tx_name[:40] if tx_name else '',
                    'iban':   tx_iban,
                    'zweck':  tx_zweck[:60] if tx_zweck else '',
                    'mandat': tx_mandat,
                })

        buchungen.append({
            'datum':  datum[:10] if datum else '',
            'cd':     cd,
            'betrag': betrag,
            'name':   name[:40] if name else '',
            'iban':   iban,
            'zweck':  zweck[:70] if zweck else '',
            'txs':    txs,
            'datei':  os.path.basename(filepath)[:10],
        })
    return buchungen

ordner = r'C:\Projekte\immocore\CamtDAT'
alle = []
for f in sorted(os.listdir(ordner)):
    if f.endswith('.xml'):
        alle += parse_camt_detail(os.path.join(ordner, f))

print('=' * 110)
for e in alle:
    art = 'EINGANG' if e['cd'] == 'CRDT' else 'AUSGANG'
    print(f"  {e['datum']}  {art:<8}  {e['betrag']:>10}  {e['name']}")
    print(f"  {'':>10}  {'':8}  {'':>10}  Verwendung: {e['zweck']}")
    if e['iban']:
        print(f"  {'':>10}  {'':8}  {'':>10}  IBAN: {e['iban']}")
    if e['txs']:
        print(f"  {'':>10}  {'':8}  {'':>10}  Einzelpositionen ({len(e['txs'])}):")
        for tx in e['txs']:
            print(f"  {'':>10}  {'':8}  {tx['betrag']:>10}    > {tx['name']:<35}  {tx['zweck'][:50]}")
            if tx['iban']:
                print(f"  {'':>10}  {'':8}  {'':>10}       IBAN: {tx['iban']}")
    print('-' * 110)

eingaenge = sum(1 for e in alle if e['cd'] == 'CRDT')
ausgaenge = sum(1 for e in alle if e['cd'] == 'DBIT')
print(f"\nGesamt: {len(alle)} Umsaetze  |  Eingaenge: {eingaenge}  |  Ausgaenge: {ausgaenge}")
