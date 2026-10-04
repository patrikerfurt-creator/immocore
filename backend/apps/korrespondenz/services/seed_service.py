"""Seed für Vorlagen & Korrespondenz (Phase 7, Spec 12.8).

Legt nur NEUE Datensätze an und ist idempotent:

* Standard-Briefbogen samt Logo-``Dokument`` - nur, wenn noch kein Standard-Briefbogen
  existiert (ein vorhandener wird nie verändert).
* Mustervorlagen - je ``code`` (global, ``objekt`` leer) nur, wenn es die Vorlage noch nicht
  gibt. Eine vorhandene Vorlage samt Versionen bleibt unberührt.

Alle Vorlagen entstehen als Version 1 im Status ``entwurf``; es wird NIE freigegeben und
NIE ``aktive_version`` gesetzt (juristische Prüfung durch Patrik steht aus).
"""
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from django.core.files.base import ContentFile
from django.db import transaction

from apps.dokumente.models import Dokument
from apps.korrespondenz.models import Briefbogen, Vorlage, VorlageAnlage, VorlagenVersion

from . import blockstruktur_service, eingabefelder_service, seed_daten

ASSETS = Path(__file__).resolve().parent.parent / 'assets'


@dataclass
class SeedErgebnis:
    """Was der Seed-Lauf getan hat (leere Listen = nichts Neues angelegt)."""
    briefbogen_angelegt: bool = False
    briefbogen_vorhanden: str = ''
    vorlagen_angelegt: list = field(default_factory=list)
    vorlagen_vorhanden: list = field(default_factory=list)


def _logo_dokument(user) -> Dokument:
    """Legt das Logo als ``Dokument`` an (Datei landet unter MEDIA_ROOT/dokumente/)."""
    inhalt = (ASSETS / seed_daten.LOGO_DATEI).read_bytes()
    return Dokument.objects.create(
        datei=ContentFile(inhalt, name=seed_daten.LOGO_DATEI),
        dateiname=seed_daten.LOGO_DATEI,
        titel='Demme-Logo (Briefbogen)',
        kategorie=seed_daten.LOGO_KATEGORIE,
        dokument_typ='sonstiges',
        sha256=hashlib.sha256(inhalt).hexdigest(),
        hochgeladen_von=user,
    )


def lege_briefbogen_an(user, ergebnis: SeedErgebnis) -> None:
    """Standard-Briefbogen + Logo anlegen, falls noch kein Standard-Briefbogen existiert."""
    vorhanden = Briefbogen.objects.filter(ist_standard=True).first()
    if vorhanden:
        ergebnis.briefbogen_vorhanden = vorhanden.bezeichnung
        return
    werte = dict(seed_daten.BRIEFBOGEN)
    werte['logo'] = _logo_dokument(user)
    werte['fuss_logo'] = None  # Verbandslogo wurde entfernt.
    Briefbogen.objects.create(**werte)
    ergebnis.briefbogen_angelegt = True


def pruefe_vorlagen_daten(daten: dict) -> list:
    """Strukturprüfung einer Seed-Vorlage (Blöcke + Eingabefelddefinition); leer = gültig."""
    return (
        blockstruktur_service.pruefe_blockstruktur(daten['inhalt'])
        + eingabefelder_service.pruefe_definition(daten.get('eingabefelder', []))
    )


def _lege_vorlage_an(daten: dict) -> Vorlage:
    vorlage = Vorlage.objects.create(
        code=daten['code'], bezeichnung=daten['bezeichnung'], anlass=daten['anlass'],
        objekt=None, briefbogen=None, kanal_standard=daten['kanal_standard'],
        einzeln_bearbeitbar=daten['einzeln_bearbeitbar'], aktive_version=None, aktiv=True,
    )
    VorlagenVersion.objects.create(
        vorlage=vorlage, version=1, betreff=daten['betreff'], inhalt=daten['inhalt'],
        email_begleittext=daten.get('email_begleittext', ''),
        eingabefelder=daten.get('eingabefelder', []),
        pflicht_platzhalter=daten.get('pflicht_platzhalter', []),
        parameter=daten.get('parameter', {}), status='entwurf',
    )
    for anlage in daten.get('anlagen', []):
        VorlageAnlage.objects.create(vorlage=vorlage, dokument=None, **anlage)
    return vorlage


def lege_vorlagen_an(ergebnis: SeedErgebnis) -> None:
    """Jede Mustervorlage nur anlegen, wenn es den ``code`` global noch nicht gibt."""
    for daten in seed_daten.VORLAGEN:
        fehler = pruefe_vorlagen_daten(daten)
        if fehler:
            raise ValueError(f"Seed-Vorlage {daten['code']} ungültig: {'; '.join(fehler)}")
        if Vorlage.objects.filter(code=daten['code'], objekt__isnull=True).exists():
            ergebnis.vorlagen_vorhanden.append(daten['code'])
            continue
        _lege_vorlage_an(daten)
        ergebnis.vorlagen_angelegt.append(daten['code'])


@transaction.atomic
def seede(user) -> SeedErgebnis:
    """Führt den gesamten Seed aus. ``user`` = Uploader des Logo-Dokuments."""
    ergebnis = SeedErgebnis()
    lege_briefbogen_an(user, ergebnis)
    lege_vorlagen_an(ergebnis)
    return ergebnis
