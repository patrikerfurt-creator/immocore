"""Vorlagen-Auflösung und Versionsverwaltung (Spec 3.2, 3.3, 3.6).

* ``aufloesen``: objektspezifische Vorlage vor globaler; inaktive werden ignoriert.
* Versions-Immutabilität: eine freigegebene (oder abgelöste) ``VorlagenVersion``
  wird nie verändert. "Bearbeiten" erzeugt eine neue Version im Status
  ``entwurf``. Die Sperre liegt bewusst im Service (kein Signal, keine
  Modell-Logik); Änderungen an Versionen laufen ausschließlich über
  ``bearbeiten``/``aktualisiere_entwurf``.
"""
import copy

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.korrespondenz.models import Textbaustein, Vorlage, VorlagenVersion

BEARBEITBARE_FELDER = (
    'betreff', 'inhalt', 'email_begleittext', 'eingabefelder',
    'pflicht_platzhalter', 'parameter',
)
FREIGABE_PERMISSION = 'korrespondenz.vorlage_freigeben'
# Anlässe, deren Vorlagen immer im Einzelschreiben anpassbar sind (Spec 9.3: Antwort im Vorgang).
IMMER_EINZELN_BEARBEITBAR = frozenset({'vorgang_antwort'})


class VorlageNichtGefunden(LookupError):
    """Keine aktive Vorlage zu Code (und Objekt) vorhanden."""


class VersionGesperrt(ValueError):
    """Versuch, eine freigegebene/abgelöste Version zu verändern."""


def aufloesen(code: str, objekt) -> Vorlage:
    """Aktive Vorlage zu ``code``: objektspezifisch vor global (``objekt=None``)."""
    aktive = Vorlage.objects.filter(code=code, aktiv=True)
    if objekt is not None:
        spezifisch = aktive.filter(objekt=objekt).first()
        if spezifisch is not None:
            return spezifisch
    global_ = aktive.filter(objekt__isnull=True).first()
    if global_ is None:
        raise VorlageNichtGefunden(f'Keine aktive Vorlage mit Code "{code}".')
    return global_


def aktive_version(vorlage: Vorlage) -> VorlagenVersion:
    """Die freigegebene Version, mit der ein Schreiben erzeugt werden darf."""
    version = vorlage.aktive_version
    if version is None or version.status != 'freigegeben':
        raise VorlageNichtGefunden(f'Vorlage "{vorlage.code}" hat keine freigegebene Version.')
    return version


def lade_bausteine(bloecke, objekt) -> dict:
    """``{code: inhalt}`` der im Inhalt referenzierten aktiven Textbausteine.

    Objektspezifischer Baustein hat Vorrang vor dem globalen gleichen Codes.
    Nicht auffindbare Codes fehlen im Ergebnis (die Render-Engine meldet sie).
    """
    codes = {b.get('code') for b in bloecke or [] if b.get('typ') == 'baustein'}
    if not codes:
        return {}
    ergebnis = {}
    kandidaten = Textbaustein.objects.filter(code__in=codes, aktiv=True)
    for baustein in kandidaten.filter(objekt__isnull=True):
        ergebnis[baustein.code] = baustein.inhalt
    if objekt is not None:
        for baustein in kandidaten.filter(objekt=objekt):
            ergebnis[baustein.code] = baustein.inhalt
    return ergebnis


def _naechste_versionsnummer(vorlage: Vorlage) -> int:
    letzte = vorlage.versionen.aggregate(m=Max('version'))['m']
    return (letzte or 0) + 1


def _pruefe_felder(aenderungen: dict) -> None:
    unbekannt = set(aenderungen) - set(BEARBEITBARE_FELDER)
    if unbekannt:
        raise ValueError('Nicht änderbare Felder: ' + ', '.join(sorted(unbekannt)))


def aktualisiere_entwurf(version: VorlagenVersion, aenderungen: dict) -> VorlagenVersion:
    """Ändert einen Entwurf in place; jede andere Version ist gesperrt."""
    if version.status != 'entwurf':
        raise VersionGesperrt(
            f'{version} ist {version.get_status_display().lower()} und unveränderlich.'
        )
    _pruefe_felder(aenderungen)
    for feld, wert in aenderungen.items():
        setattr(version, feld, wert)
    version.save(update_fields=list(aenderungen) or None)
    return version


@transaction.atomic
def neue_version_aus(version: VorlagenVersion, user=None, aenderungen: dict = None) -> VorlagenVersion:
    """Legt aus ``version`` eine neue Version (``entwurf``) an; ``version`` bleibt unberührt."""
    aenderungen = aenderungen or {}
    _pruefe_felder(aenderungen)
    vorlage = Vorlage.objects.select_for_update().get(pk=version.vorlage_id)
    werte = {f: copy.deepcopy(getattr(version, f)) for f in BEARBEITBARE_FELDER}
    werte.update(aenderungen)
    return VorlagenVersion.objects.create(
        vorlage=vorlage, version=_naechste_versionsnummer(vorlage),
        status='entwurf', erstellt_von=user, **werte,
    )


def bearbeiten(version: VorlagenVersion, aenderungen: dict, user=None) -> VorlagenVersion:
    """"Bearbeiten": Entwurf wird geändert, jede andere Version erzeugt eine neue.

    Gibt die Version zurück, die die Änderungen trägt.
    """
    if version.status == 'entwurf':
        return aktualisiere_entwurf(version, aenderungen)
    return neue_version_aus(version, user=user, aenderungen=aenderungen)


@transaction.atomic
def freigeben(version: VorlagenVersion, user) -> VorlagenVersion:
    """Gibt einen Entwurf frei, löst die bisher aktive Version ab und macht ihn aktiv."""
    if not user.has_perm(FREIGABE_PERMISSION):
        raise PermissionDenied(f'Berechtigung "{FREIGABE_PERMISSION}" fehlt.')
    vorlage = Vorlage.objects.select_for_update().get(pk=version.vorlage_id)
    version = VorlagenVersion.objects.select_for_update().get(pk=version.pk)
    if version.status != 'entwurf':
        raise VersionGesperrt(f'{version} ist kein Entwurf und kann nicht freigegeben werden.')

    vorlage.versionen.filter(status='freigegeben').update(status='abgeloest')
    version.status = 'freigegeben'
    version.freigegeben_am = timezone.now()
    version.freigegeben_von = user
    version.save(update_fields=['status', 'freigegeben_am', 'freigegeben_von'])
    vorlage.aktive_version = version
    vorlage.save(update_fields=['aktive_version', 'geaendert_am'])
    return version


def lege_vorlage_an(*, code: str, bezeichnung: str, anlass: str, objekt=None, briefbogen=None,
                    kanal_standard: str = 'brief', einzeln_bearbeitbar: bool = False,
                    user=None) -> Vorlage:
    """Legt eine Vorlage (ohne Version) an; ``code`` ist je Objekt (bzw. global) eindeutig."""
    if Vorlage.objects.filter(code=code, objekt=objekt).exists():
        wo = 'für dieses Objekt' if objekt is not None else 'global'
        raise ValidationError(f'Es gibt bereits eine Vorlage mit dem Code "{code}" ({wo}).')
    if anlass in IMMER_EINZELN_BEARBEITBAR:
        einzeln_bearbeitbar = True
    return Vorlage.objects.create(
        code=code, bezeichnung=bezeichnung, anlass=anlass, objekt=objekt, briefbogen=briefbogen,
        kanal_standard=kanal_standard, einzeln_bearbeitbar=einzeln_bearbeitbar, erstellt_von=user,
    )


@transaction.atomic
def lege_version_an(vorlage: Vorlage, user=None, *, basis: VorlagenVersion = None,
                    werte: dict = None) -> VorlagenVersion:
    """Neue Version (immer ``entwurf``) einer Vorlage.

    Mit ``basis``: Kopie dieser Version, überlagert mit ``werte`` (= "Bearbeiten" einer
    freigegebenen Version). Ohne ``basis``: leerer Ausgangspunkt, ``werte['betreff']`` Pflicht.
    """
    werte = werte or {}
    if basis is not None:
        if basis.vorlage_id != vorlage.pk:
            raise ValueError('Die Basisversion gehört zu einer anderen Vorlage.')
        return neue_version_aus(basis, user=user, aenderungen=werte)
    _pruefe_felder(werte)
    if not werte.get('betreff'):
        raise ValueError('Der Betreff fehlt.')
    vorlage = Vorlage.objects.select_for_update().get(pk=vorlage.pk)
    return VorlagenVersion.objects.create(
        vorlage=vorlage, version=_naechste_versionsnummer(vorlage), status='entwurf',
        erstellt_von=user, **werte,
    )
