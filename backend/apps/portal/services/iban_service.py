"""
IBAN-Prüfung und -Aufbereitung für das Eigentümer-Portal.

Eine Stelle für die Prüfung, die vorher inline in ``IbanPruefenView`` und
``BankverbindungSerializer.validate_iban`` stand. Die Meldungen sind
bewusst deutsch und ohne Technikjargon: davor sitzt ein Eigentümer.
"""

IBAN_UNGUELTIG = 'Diese IBAN ist ungültig.'


def normalisiere_iban(roh: str) -> str:
    """Leerzeichen entfernen, Großschreibung — ohne Gültigkeitsprüfung."""
    return (roh or '').replace(' ', '').strip().upper()


def pruefe_iban(roh: str) -> dict:
    """Prüft eine IBAN mit ``schwifty``.

    Gültig: ``{'valid': True, 'iban': str, 'bic': str, 'bank_name': str}``.
    Ungültig/leer: ``{'valid': False, 'error': str}``.

    Ohne die optionale Abhängigkeit ``schwifty`` wird keine Aussage
    vorgetäuscht: die Eingabe gilt als gültig, BIC und Bankname bleiben leer.
    """
    iban_roh = (roh or '').replace(' ', '').upper()
    if not iban_roh:
        return {'valid': False, 'error': 'Keine IBAN angegeben'}

    try:
        from schwifty import IBAN
        iban = IBAN(iban_roh)
    except ImportError:
        return {'valid': True, 'iban': iban_roh, 'bic': '', 'bank_name': ''}
    except Exception:
        # Bewusst ohne die Original-Fehlermeldung (englisch, technisch).
        return {'valid': False, 'error': IBAN_UNGUELTIG}

    bic = ''
    bank_name = ''
    try:
        bic_obj = iban.bic
        if bic_obj:
            bic = str(bic_obj)
            bank_name = getattr(bic_obj, 'bank_name', '') or ''
    except Exception:
        pass

    return {'valid': True, 'iban': str(iban), 'bic': bic, 'bank_name': bank_name}
