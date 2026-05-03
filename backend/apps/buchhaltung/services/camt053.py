"""
camt.053 XML-Parser (ISO 20022 Bank-to-Customer Statement)
Unterstützt camt.053.001.02 und camt.053.001.08
"""
import hashlib
from decimal import Decimal
from datetime import date
from xml.etree import ElementTree as ET

NAMESPACES = [
    'urn:iso:std:iso:20022:tech:xsd:camt.053.001.08',
    'urn:iso:std:iso:20022:tech:xsd:camt.053.001.02',
    'urn:iso:std:iso:20022:tech:xsd:camt.053.001.06',
]


def _ns(tag: str, namespace: str) -> str:
    return f'{{{namespace}}}{tag}'


def _find(element, path: str, namespace: str):
    """Namespace-bewusstes find mit Fallback."""
    parts = path.split('/')
    ns_path = '/'.join(f'{{{namespace}}}{p}' for p in parts)
    return element.find(ns_path)


def _findtext(element, path: str, namespace: str, default='') -> str:
    el = _find(element, path, namespace)
    return el.text.strip() if el is not None and el.text else default


def _sha256_transaktion(txn: dict) -> str:
    """Eindeutiger Hash je Transaktion für Duplikatschutz."""
    key = (
        f"{txn['buchungsdatum']}|{txn['betrag']}|"
        f"{txn['auftraggeber_iban']}|{txn['verwendungszweck']}"
    )
    return hashlib.sha256(key.encode('utf-8')).hexdigest()


def parse_camt053(xml_bytes: bytes) -> list[dict]:
    """
    Parst eine camt.053 XML-Datei und gibt eine Liste von Transaktions-Dicts zurück.

    Jedes Dict enthält:
        buchungsdatum, wertstellungsdatum, betrag (Decimal),
        auftraggeber_name, auftraggeber_iban, verwendungszweck, sha256_hash
    """
    root = ET.fromstring(xml_bytes)

    # Namespace automatisch erkennen
    ns = None
    for candidate in NAMESPACES:
        doc_tag = f'{{{candidate}}}Document'
        if root.tag == doc_tag:
            ns = candidate
            break

    # Fallback: Namespace aus Root-Tag extrahieren
    if ns is None and root.tag.startswith('{'):
        ns = root.tag[1:root.tag.index('}')]

    if ns is None:
        raise ValueError("Unbekanntes camt.053-Namespace — Datei nicht parsbar")

    transaktionen = []

    # Statements iterieren (BkToCstmrStmt > Stmt)
    stmt_path = f'{{{ns}}}BkToCstmrStmt/{{{ns}}}Stmt'
    for stmt in root.findall(stmt_path):
        # Eigene Konto-IBAN aus dem Statement-Header lesen
        stmt_iban = _findtext(stmt, 'Acct/Id/IBAN', ns)

        for entry in stmt.findall(f'{{{ns}}}Ntry'):
            # Buchungsdatum + Wertstellungsdatum
            buchungsdatum_str = _findtext(entry, 'BookgDt/Dt', ns)
            wert_str = _findtext(entry, 'ValDt/Dt', ns)

            try:
                buchungsdatum = date.fromisoformat(buchungsdatum_str)
            except (ValueError, TypeError):
                continue

            wertstellungsdatum = None
            if wert_str:
                try:
                    wertstellungsdatum = date.fromisoformat(wert_str)
                except ValueError:
                    pass

            # Betrag mit Vorzeichen (CdtDbtInd: CRDT=positiv, DBIT=negativ)
            betrag_str = _findtext(entry, 'Amt', ns, '0')
            try:
                betrag = Decimal(betrag_str)
            except Exception:
                betrag = Decimal('0')

            cdt_dbt = _findtext(entry, 'CdtDbtInd', ns)
            if cdt_dbt == 'DBIT':
                betrag = -betrag

            # Transaktionsdetails (NtryDtls > TxDtls)
            ntry_dtls = _find(entry, 'NtryDtls', ns)
            if ntry_dtls is not None:
                for tx in ntry_dtls.findall(f'{{{ns}}}TxDtls'):
                    auftraggeber_name = ''
                    auftraggeber_iban = ''

                    # Gegenseite je nach Buchungsrichtung
                    if cdt_dbt == 'CRDT':
                        # Eingang → Auftraggeber ist RltdPties/Dbtr
                        name_path = 'RltdPties/Dbtr/Pty/Nm'
                        iban_path = 'RltdPties/DbtrAcct/Id/IBAN'
                    else:
                        # Ausgang → Auftraggeber ist RltdPties/Cdtr
                        name_path = 'RltdPties/Cdtr/Pty/Nm'
                        iban_path = 'RltdPties/CdtrAcct/Id/IBAN'

                    auftraggeber_name = _findtext(tx, name_path, ns)
                    auftraggeber_iban = _findtext(tx, iban_path, ns)

                    # Verwendungszweck
                    verwendungszweck = _findtext(tx, 'RmtInf/Ustrd', ns)
                    if not verwendungszweck:
                        # Structured reference fallback
                        verwendungszweck = _findtext(tx, 'RmtInf/Strd/CdtrRefInf/Ref', ns)

                    txn = {
                        'buchungsdatum': buchungsdatum,
                        'wertstellungsdatum': wertstellungsdatum,
                        'betrag': betrag,
                        'auftraggeber_name': auftraggeber_name,
                        'auftraggeber_iban': auftraggeber_iban,
                        'empfaenger_iban': stmt_iban,
                        'verwendungszweck': verwendungszweck,
                    }
                    txn['sha256_hash'] = _sha256_transaktion(txn)
                    transaktionen.append(txn)
            else:
                # Einfacher Entry ohne TxDtls
                verwendungszweck = _findtext(entry, 'NtryDtls/TxDtls/RmtInf/Ustrd', ns)
                txn = {
                    'buchungsdatum': buchungsdatum,
                    'wertstellungsdatum': wertstellungsdatum,
                    'betrag': betrag,
                    'auftraggeber_name': '',
                    'auftraggeber_iban': '',
                    'empfaenger_iban': stmt_iban,
                    'verwendungszweck': verwendungszweck,
                }
                txn['sha256_hash'] = _sha256_transaktion(txn)
                transaktionen.append(txn)

    return transaktionen
