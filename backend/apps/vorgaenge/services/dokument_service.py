"""
Dokument-Service (Phase B, Spec Vorgang & DMS Kap. 1.6 / 4).

Business-Logik rund um Dokument-Upload und einfache Versionierung:
- genau ein Kontext-FK (objekt/einheit/vorgang/person) pro Dokument,
- SHA-256-Duplikaterkennung als Soft-Warnung (kein Hard-Block, kein unique),
- neue Version = neue Zeile, alte Zeile bleibt unverändert (GoBD).

Konsistent zu ``apps.dokumente.services.beleg_service``: die Datei wird als
``ContentFile`` aus ``datei_bytes``/``dateiname`` angelegt, ``ablage_wurzel``
bleibt auf dem Default ``'media'`` (kein Rechnungen-Bind-Mount hier — das ist
ausschließlich dem Beleg-Pfad vorbehalten).
"""
import hashlib
from dataclasses import dataclass

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction

from apps.dokumente.models import Dokument
from apps.vorgaenge.models import VorgangEreignis

_KONTEXT_FELDER = ('objekt', 'einheit', 'vorgang', 'person')


@dataclass
class DokumentUploadErgebnis:
    """Rückgabe von ``lade_dokument_hoch``: Dokument plus Soft-Warnung bei Duplikat."""
    dokument: Dokument
    duplikat_warnung: bool


def _kontext_aus_kwargs(objekt, einheit, vorgang, person,
                        mail_import=None) -> tuple[str, object] | tuple[None, None]:
    """Prüft die Kontextangabe und gibt (feldname, wert) zurück.

    Regel bleibt: GENAU EIN Kontext. Einzige Ausnahme ist eine eingegangene
    Mail (``mail_import``) — deren Zuordnung trifft später ein Mensch im
    Posteingang, aufbewahrt wird sie aber sofort. Dann ist auch KEIN Kontext
    zulässig und es kommt (None, None) zurück.
    """
    werte = {'objekt': objekt, 'einheit': einheit, 'vorgang': vorgang, 'person': person}
    gesetzt = {feld: wert for feld, wert in werte.items() if wert is not None}

    if not gesetzt and mail_import is not None:
        return None, None

    if len(gesetzt) != 1:
        raise ValidationError(
            'lade_dokument_hoch erfordert genau einen Kontext '
            f'(objekt, einheit, vorgang oder person) — {len(gesetzt)} wurden übergeben.'
        )
    feld, wert = next(iter(gesetzt.items()))
    return feld, wert


def _kontext_von(dokument: Dokument) -> dict:
    """Liest den (laut Constraint höchstens einen) gesetzten Kontext-FK eines
    bestehenden Dokuments aus."""
    for feld in _KONTEXT_FELDER:
        wert = getattr(dokument, feld, None)
        if wert is not None:
            return {feld: wert}
    return {}


def _ist_beleg_dokument(dokument: Dokument) -> bool:
    """True, wenn das Dokument über ``Rechnung.beleg_dokument`` gekoppelt ist
    (GoBD-Beleg — revisionssicher, keine Versionierung)."""
    try:
        dokument.rechnung
        return True
    except ObjectDoesNotExist:
        return False


@transaction.atomic
def lade_dokument_hoch(datei_bytes: bytes, dateiname: str, erstellt_von, *,
                        objekt=None, einheit=None, vorgang=None, person=None,
                        kategorie: str = 'Sonstiges', dokument_typ: str = 'sonstiges',
                        beschreibung: str = '', mail_import=None,
                        register=None, dokument_datum=None,
                        titel: str = '') -> DokumentUploadErgebnis:
    """Lädt ein Dokument mit genau einem Kontext hoch (Spec Kap. 1.6).

    - Berechnet SHA-256 aus ``datei_bytes`` (``Dokument.sha256``).
    - Duplikat = gleicher Hash UND gleicher Kontext-FK → Soft-Warnung im
      Rückgabewert (``duplikat_warnung``), KEIN Hard-Block.
    - Bei Kontext ``vorgang``: zusätzlich ``VorgangEreignis`` Typ
      ``dokument_verknuepft`` am Vorgang.
    """
    kontext_feld, kontext_wert = _kontext_aus_kwargs(
        objekt, einheit, vorgang, person, mail_import)
    sha256 = hashlib.sha256(datei_bytes).hexdigest()

    if kontext_feld is not None:
        kontext = {kontext_feld: kontext_wert}
        duplikat_warnung = Dokument.objects.filter(sha256=sha256, **kontext).exists()
    else:
        # Noch nicht zugeordnete Mail: gegen den Bestand ohne Kontext pruefen,
        # sonst meldet jede erneut eingelesene Mail faelschlich "neu".
        kontext = {}
        duplikat_warnung = Dokument.objects.filter(
            sha256=sha256, mail_import__isnull=False,
        ).exists()

    dokument = Dokument(
        datei=ContentFile(datei_bytes, name=dateiname),
        dateiname=dateiname,
        kategorie=kategorie,
        beschreibung=beschreibung,
        dokument_typ=dokument_typ,
        version=1,
        sha256=sha256,
        hochgeladen_von=erstellt_von,
        mail_import=mail_import,
        register=register,
        dokument_datum=dokument_datum,
        titel=titel,
        **kontext,
    )
    dokument.full_clean()
    dokument.save()

    if kontext_feld == 'vorgang':
        # intern=False (Patrik-Entscheidung): der Hinweis, dass ein Dokument
        # verknüpft wurde, ist für den Eigentümer sichtbar — der Dateiname ist
        # dabei bewusst der einzige preisgegebene Inhalt (siehe
        # ``vorgang_service.portal_ansicht``: kein Datei-Link, keine
        # Dokument-ID, kein Downloadpfad — eine echte Dateifreigabe ist NICHT
        # Teil dieses Mechanismus).
        VorgangEreignis.objects.create(
            vorgang=kontext_wert, typ='dokument_verknuepft',
            text=f"Dokument hochgeladen: {dateiname}",
            erstellt_von=erstellt_von,
            intern=False,
        )

    return DokumentUploadErgebnis(dokument=dokument, duplikat_warnung=duplikat_warnung)


@transaction.atomic
def neue_version_anlegen(altes_dokument: Dokument, datei_bytes: bytes, dateiname: str,
                          erstellt_von) -> Dokument:
    """Legt eine neue Version eines Dokuments an (Spec Kap. 1.6).

    Neue Zeile mit ``version = altes_dokument.version + 1`` und
    ``vorgaenger_version = altes_dokument``, gleicher Kontext-FK wie das alte
    Dokument. Die alte Zeile bleibt UNVERÄNDERT (GoBD). Beleg-Dokumente
    (über ``Rechnung.beleg_dokument`` gekoppelt) sind revisionssicher und
    dürfen nicht versioniert werden.
    """
    if _ist_beleg_dokument(altes_dokument):
        raise ValidationError(
            'Beleg-Dokumente (über Rechnung.beleg_dokument gekoppelt) sind '
            'revisionssicher — Versionierung ist nicht zulässig.'
        )

    kontext_kwargs = _kontext_von(altes_dokument)
    sha256 = hashlib.sha256(datei_bytes).hexdigest()

    neues_dokument = Dokument(
        datei=ContentFile(datei_bytes, name=dateiname),
        dateiname=dateiname,
        kategorie=altes_dokument.kategorie,
        beschreibung=altes_dokument.beschreibung,
        dokument_typ=altes_dokument.dokument_typ,
        version=altes_dokument.version + 1,
        vorgaenger_version=altes_dokument,
        sha256=sha256,
        hochgeladen_von=erstellt_von,
        **kontext_kwargs,
    )
    neues_dokument.full_clean()
    neues_dokument.save()
    return neues_dokument
