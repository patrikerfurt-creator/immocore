"""
camt.054-Abzweig (STUB v1.0).

Erkennt camt.054-Dateien (Wurzelelement <BkToCstmrDbtCdtNtfctn>),
parkt sie als CamtImportLog mit typ='camt054' und Status 'pending_mahnwesen_spec'.
Vollständige R-Transactions-Verarbeitung ist Teil der Mahnwesen-Spec.
"""
import logging
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

CAMT054_ROOT_TAGS = {
    'BkToCstmrDbtCdtNtfctn',
}
CAMT053_ROOT_TAGS = {
    'BkToCstmrStmt',
}


def erkenne_camt_typ(xml_bytes: bytes) -> str:
    """
    Erkennt ob eine XML-Datei camt.053 oder camt.054 ist.
    Gibt 'camt053' oder 'camt054' zurück.
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return 'camt053'

    local_name = root.tag.split('}')[-1] if '}' in root.tag else root.tag

    if local_name in CAMT054_ROOT_TAGS:
        return 'camt054'

    # Auch direkte Kinder prüfen (manche camt.054 haben Document als Root)
    for child in root:
        child_local = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        if child_local in CAMT054_ROOT_TAGS:
            return 'camt054'

    return 'camt053'


def verarbeite_camt054(camt_import_log) -> None:
    """
    STUB v1.0 — vollständige R-Transactions-Verarbeitung
    ist Teil der Mahnwesen-Spec (siehe HAUSGELD_NEBENBUCH v1.1 Kap. 11).

    Parkt den Import mit Status 'pending_mahnwesen_spec'.
    Kein BankBuchung / Kontoumsatz wird erzeugt.
    """
    # Nur Eintrag-Zahl mitzählen (leichtgewichtig)
    xml_inhalt = getattr(camt_import_log, '_xml_inhalt', '')
    anzahl_entries = _zaehle_ntry(xml_inhalt) if xml_inhalt else 0

    camt_import_log.typ    = 'camt054'
    camt_import_log.status = 'pending_mahnwesen_spec'
    camt_import_log.notiz  = (
        f"camt.054 angenommen ({anzahl_entries} Einträge). "
        f"Verarbeitung erfolgt mit Mahnwesen-Spec."
    )
    camt_import_log.save(update_fields=['typ', 'status', 'notiz'])

    logger.warning(
        "camt.054 import %s parked — implementation pending (Mahnwesen-Spec).",
        camt_import_log.id,
    )


def _zaehle_ntry(xml_inhalt: str) -> int:
    return xml_inhalt.count('<Ntry>')
