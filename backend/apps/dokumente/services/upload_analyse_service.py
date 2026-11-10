"""
Analyse eines frisch hochgeladenen Dokuments VOR dem Anlegen.

Fuehrt zwei bestehende Vorschlagsdienste an der Upload-Maske zusammen:

  1. Kontext (Objekt/Einheit/Person)  -> ``kontext_vorschlag_service``
  2. Aktenregister                     -> ``register_vorschlag_service``

Beide bekommen denselben extrahierten Dateitext. Es wird NICHTS angelegt und
NICHTS gesetzt: der Dienst liefert nur Vorschlaege zurueck, die der Nutzer in
der Maske bestaetigt oder aendert. Das eigentliche Anlegen laeuft danach ueber
den normalen ``POST /dokumente/`` mit den bestaetigten Werten.
"""
import logging
import os
import tempfile

from apps.dokumente.models import Aktenregister, Dokument
from apps.dokumente.services import akten_service
from apps.dokumente.services import kontext_vorschlag_service
from apps.dokumente.services import register_vorschlag_service

logger = logging.getLogger(__name__)

# Nur diese Endungen werden ueberhaupt textuell ausgelesen. Alles andere laeuft
# ohne Inhalt durch (dann traegt nur der Dateiname zur Zuordnung bei).
_PDF_BILD = {'.pdf', '.png', '.jpg', '.jpeg', '.tif', '.tiff'}
_TEXT = {'.txt', '.csv', '.md', '.eml'}

_TEXT_MAX = 20000

# Owner-Feld -> Aktenart, die die passende Registerliste bestimmt.
_AKTENART_JE_OWNER = {
    'objekt': Aktenregister.AKTENART_HAUS,
    'einheit': Aktenregister.AKTENART_WOHNUNG,
    'person': Aktenregister.AKTENART_EIGENTUEMER,
}


def extrahiere_text(pfad: str, dateiname: str) -> str:
    """Bester verfuegbarer Text einer Datei — leer, wenn nicht lesbar.

    PDFs und Bilder laufen ueber den bestehenden Rechnungs-Parser (PyMuPDF,
    ersatzweise OCR); reine Textdateien werden direkt dekodiert. Wirft nie:
    eine nicht lesbare Datei soll den Upload nicht blockieren, sie liefert
    dann eben keinen Inhalt fuer die Zuordnung.
    """
    ext = os.path.splitext(dateiname or '')[1].lower()
    try:
        if ext in _PDF_BILD:
            from apps.rechnungen.services.invoice_parser import extract_text
            return (extract_text(pfad) or '')[:_TEXT_MAX]
        if ext in _TEXT:
            with open(pfad, 'r', encoding='utf-8', errors='ignore') as fh:
                return fh.read(_TEXT_MAX)
    except Exception:
        logger.exception('Textextraktion für %s fehlgeschlagen.', dateiname)
    return ''


def _owner_objekt(kontext: dict):
    """Das Objekt, dessen Registerliste gilt — aus dem gewaehlten Owner."""
    if kontext['owner'] == 'objekt':
        return kontext['objekt']
    if kontext['owner'] == 'einheit' and kontext['einheit'] is not None:
        return kontext['einheit'].objekt
    return None


def _ref(instanz) -> dict | None:
    if instanz is None:
        return None
    ref = {'id': str(instanz.id), 'label': str(instanz)}
    # Bei einer Einheit das uebergeordnete Objekt mitgeben, damit die
    # Oberflaeche die Einheiten-Auswahlliste dieses Objekts laden kann.
    objekt_id = getattr(instanz, 'objekt_id', None)
    if objekt_id is not None:
        ref['objekt'] = str(objekt_id)
    return ref


def analysiere(datei, dateiname: str, beschreibung: str = '',
               dokument_typ: str = 'sonstiges') -> dict:
    """Analysiert eine hochgeladene Datei und liefert Kontext- und
    Registervorschlag als serialisierbares Dict.

    ``datei`` ist das offene Upload-Objekt (Django ``UploadedFile``).
    """
    # Inhalt einmal auf Platte spiegeln — der Parser arbeitet pfadbasiert.
    ext = os.path.splitext(dateiname or '')[1].lower()
    inhalt_text = ''
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        for chunk in datei.chunks():
            tmp.write(chunk)
        tmp_pfad = tmp.name
    try:
        inhalt_text = extrahiere_text(tmp_pfad, dateiname)
    finally:
        try:
            os.unlink(tmp_pfad)
        except OSError:
            pass

    kontext = kontext_vorschlag_service.schlage_kontext_vor(
        dateiname, beschreibung, inhalt_text)

    # Registervorschlag auf einem ungespeicherten Dokument: der Dienst liest
    # nur Attribute (Dateiname, Beschreibung, Typ) und faellt ueber die fehlende
    # Rechnung sauber auf die KI-Stufe zurueck.
    probe = Dokument(dateiname=dateiname, beschreibung=beschreibung or '',
                     dokument_typ=dokument_typ or 'sonstiges')
    objekt = _owner_objekt(kontext)
    aktenart = _AKTENART_JE_OWNER.get(kontext['owner'], Aktenregister.AKTENART_HAUS)
    register_liste = list(akten_service.register_einer_akte(aktenart, objekt))
    register = register_vorschlag_service.schlage_register_vor(
        probe, register_liste, zusatztext=inhalt_text)

    treffer = register['register']
    return {
        'inhalt_erkannt': bool(inhalt_text.strip()),
        'kontext': {
            'owner': kontext['owner'],
            'objekt': _ref(kontext['objekt']),
            'einheit': _ref(kontext['einheit']),
            'person': _ref(kontext['person']),
            'quelle': kontext['quelle'],
            'konfidenz': kontext['konfidenz'],
            'begruendung': kontext['begruendung'],
            'fehler': kontext['fehler'],
        },
        'register': {
            'register_id': str(treffer.id) if treffer else None,
            'code': treffer.code if treffer else '',
            'bezeichnung': treffer.bezeichnung if treffer else '',
            'aktenart': aktenart,
            'quelle': register['quelle'],
            'konfidenz': register['konfidenz'],
            'begruendung': register['begruendung'],
            'fehler': register['fehler'],
        },
    }
