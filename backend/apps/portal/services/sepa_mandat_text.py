"""
Darstellung und Mandatstext des Portal-SEPA-Mandats.

Reine Aufbereitung ohne Datenbankzugriff (außer dem Zugriff auf bereits
geladene Modellobjekte), damit ``mail_service`` und ``sepa_mandat_service``
beide darauf zugreifen können, ohne sich gegenseitig zu importieren.
``sepa_mandat_service`` exportiert die öffentlichen Namen erneut.

Der Mandatstext ist ein Template (``email/sepa_mandat_text.txt``) und kann
ohne Codeänderung rechtlich angepasst werden. Wird die Fassung geändert,
muss ``MANDATSTEXT_VERSION`` mitgezogen werden — die Version steht im
Nachweis (``PortalSepaMandatAenderung.mandatstext_version``).
"""
import hashlib

from django.conf import settings
from django.template.loader import render_to_string

MANDATSTEXT_VERSION = 'SEPA-CORE-PORTAL-1'
MANDATSTEXT_TEMPLATE = 'email/sepa_mandat_text.txt'


def formatiere_iban(iban: str) -> str:
    """IBAN in 4er-Gruppen (``DE89 3704 0044 …``)."""
    kompakt = (iban or '').replace(' ', '')
    return ' '.join(kompakt[i:i + 4] for i in range(0, len(kompakt), 4))


def maskiere_iban(iban: str) -> str:
    """Erste 4 und letzte 4 Zeichen sichtbar, Rest ``*``, in 4er-Gruppen.

    ``DE89370400440532013000`` → ``DE89 **** **** **** **30 00``.
    """
    kompakt = (iban or '').replace(' ', '')
    if len(kompakt) <= 8:
        return formatiere_iban(kompakt)
    maskiert = kompakt[:4] + '*' * (len(kompakt) - 8) + kompakt[-4:]
    return formatiere_iban(maskiert)


def maskiere_email(email: str) -> str:
    """``peter@example.de`` → ``p***@example.de``."""
    lokal, trenner, domain = (email or '').partition('@')
    if not trenner:
        return '***'
    return f'{lokal[:1]}***@{domain}'


def geltungsbereich_text(geltungsbereich: str, ev=None) -> str:
    """Lesbare Beschreibung, für welche Einheiten das Mandat gilt."""
    if geltungsbereich == 'einheit' and ev is not None:
        einheit = ev.einheit
        lage = f' ({einheit.lage})' if einheit.lage else ''
        return f'Einheit {einheit.einheit_nr}{lage}, {einheit.objekt.bezeichnung}'
    return 'Alle Ihre Einheiten (Sammelmandat)'


def geltungsbereich_text_fuer_antrag(antrag) -> str:
    return geltungsbereich_text(antrag.geltungsbereich, antrag.eigentumsverhaeltnis)


def _kontext_aus(quelle) -> dict:
    """Vereinheitlicht ``dict`` oder Antrag-Objekt auf den Template-Kontext."""
    if isinstance(quelle, dict):
        daten = dict(quelle)
    else:
        daten = {
            'glaeubiger': quelle.abgedeckte_glaeubiger,
            'mandatsreferenz': quelle.mandatsreferenz,
            'kontoinhaber_name': quelle.kontoinhaber_name,
            'iban': quelle.iban,
            'bic': quelle.bic,
            'geltungsbereich_text': geltungsbereich_text_fuer_antrag(quelle),
            'aenderung': quelle.aktion == 'aenderung',
        }
    return {
        'glaeubiger': daten.get('glaeubiger') or [],
        'verwalter_name': settings.PORTAL_VERWALTER_NAME,
        'mandatsreferenz': daten['mandatsreferenz'],
        'kontoinhaber_name': daten['kontoinhaber_name'],
        'iban': formatiere_iban(daten['iban']),
        'bic': daten.get('bic') or '',
        'geltungsbereich_text': daten.get('geltungsbereich_text', ''),
        'aenderung': bool(daten.get('aenderung')),
    }


def rendere_mandatstext(quelle) -> str:
    """Rendert den vollständigen Mandatstext.

    ``quelle``: ein ``PortalSepaMandatAenderung`` oder ein ``dict`` mit den
    Schlüsseln ``glaeubiger`` (Liste aus ``bezeichnung``/``glaeubiger_id``),
    ``mandatsreferenz``, ``kontoinhaber_name``, ``iban``, ``bic``,
    ``geltungsbereich_text``, ``aenderung`` (bool).
    """
    return render_to_string(MANDATSTEXT_TEMPLATE, _kontext_aus(quelle)).strip() + '\n'


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()
