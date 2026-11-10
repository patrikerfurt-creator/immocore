"""
Herkunftsangaben eines HTTP-Requests (IP) für Nachweise.
"""
import ipaddress


def _ist_ip(wert: str) -> bool:
    try:
        ipaddress.ip_address(wert)
    except ValueError:
        return False
    return True


def client_ip(request) -> tuple[str | None, str]:
    """Client-IP hinter dem Reverse Proxy.

    Reihenfolge: ``X-Real-IP`` → erster Eintrag von ``X-Forwarded-For`` →
    ``REMOTE_ADDR``. Ungültige Werte werden übersprungen (das Ergebnis geht in
    ein ``GenericIPAddressField``). Zweiter Rückgabewert: der unveränderte
    ``X-Forwarded-For``-Header (oder ''), als Beleg für spätere Nachprüfung.

    Die Header sind fälschbar, solange das Backend direkt erreichbar ist —
    der Proxy (nginx) muss sie setzen bzw. überschreiben.
    """
    meta = request.META
    forwarded_roh = (meta.get('HTTP_X_FORWARDED_FOR') or '').strip()
    erster_forwarded = forwarded_roh.split(',')[0].strip() if forwarded_roh else ''

    kandidaten = (
        (meta.get('HTTP_X_REAL_IP') or '').strip(),
        erster_forwarded,
        (meta.get('REMOTE_ADDR') or '').strip(),
    )
    for kandidat in kandidaten:
        if kandidat and _ist_ip(kandidat):
            return kandidat, forwarded_roh
    return None, forwarded_roh
