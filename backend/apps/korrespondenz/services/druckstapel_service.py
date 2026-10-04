"""Druckstapel: Sammel-PDF der zu druckenden Briefe (Spec 7.3).

* "Druckbereit" ist jedes freigegebene Schreiben, das gedruckt werden muss
  (Kanal Brief, bei E-Mail zusätzlich letzte Mahnstufe / ``beides``), noch in keinem
  Druckstapel liegt und ein PDF (``dokument``) hat.
* ``erzeuge`` bündelt sie zu einem ``Druckstapel`` mit Sammel-PDF (sortiert nach
  Objekt, dann Empfänger). Das Sammel-PDF ist nur eine Druckhilfe - das
  revisionssichere Original bleibt das Einzel-PDF je Schreiben.
* Die Bestätigung "gedruckt und kuvertiert" samt Statusübergang der Schreiben
  liegt in ``schreiben_service.bestaetige_druckstapel`` (dort sitzen alle
  Statusübergänge); dieser Service ändert keinen Schreiben-Status.
"""
import hashlib
from datetime import date

import pymupdf
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.dokumente.models import Dokument
from apps.korrespondenz.models import Druckstapel, Schreiben

from . import kanal_service

DRUCKBEREIT_STATUS = ('freigegeben', 'versand_fehlgeschlagen')
DOKUMENT_KATEGORIE = 'Korrespondenz'


def druckbereite_schreiben(objekt=None):
    """Queryset der Schreiben, die auf den Druck warten (grob; Feinprüfung in ``_pruefe_druckbereit``)."""
    qs = Schreiben.objects.filter(
        status__in=DRUCKBEREIT_STATUS, druckstapel__isnull=True, dokument__isnull=False,
    ).filter(
        Q(kanal='brief')
        | Q(vorlage_version__vorlage__kanal_standard='beides')
        | Q(vorlage_version__vorlage__anlass=kanal_service.STUFE_3_ANLASS)
        | Q(mahnung__mahnstufe__gte=kanal_service.STUFE_3)
        | Q(mahnung__mahnstufe=F('mahnung__personenkonto__objekt__mahn_einstellung__anzahl_mahnstufen'))
    ).select_related('objekt', 'empfaenger', 'einheit', 'dokument', 'vorlage_version__vorlage')
    if objekt is not None:
        qs = qs.filter(objekt=objekt)
    return qs


def _pruefe_druckbereit(schreiben) -> None:
    if schreiben.status not in DRUCKBEREIT_STATUS:
        raise ValidationError(f'{schreiben.nummer}: Status "{schreiben.status}" ist nicht druckbereit.')
    if schreiben.druckstapel_id:
        raise ValidationError(f'{schreiben.nummer} liegt bereits in einem Druckstapel.')
    if not schreiben.dokument_id:
        raise ValidationError(f'{schreiben.nummer} hat noch kein PDF.')
    if not kanal_service.braucht_brief(schreiben):
        raise ValidationError(f'{schreiben.nummer} wird nicht als Brief versendet.')


def sortierschluessel(schreiben) -> tuple:
    """Objekt (Nummer, Bezeichnung), Empfänger (Nachname, Vorname, Firma), Einheit, Nummer."""
    objekt = schreiben.objekt
    person = schreiben.empfaenger
    einheit = schreiben.einheit
    return (
        (objekt.objektnummer or '', objekt.bezeichnung or '') if objekt else ('￿', ''),
        (person.nachname or '').casefold(), (person.vorname or '').casefold(),
        (person.firmenname or '').casefold(),
        (einheit.einheit_nr or '') if einheit else '',
        schreiben.nummer,
    )


def _lese_pdf(schreiben) -> bytes:
    with schreiben.dokument.datei.open('rb') as datei:
        return datei.read()


def baue_sammel_pdf(schreiben_liste) -> bytes:
    """Fügt die Einzel-PDFs in Sortierreihenfolge zu einem PDF zusammen."""
    with pymupdf.open() as ziel:
        for schreiben in sorted(schreiben_liste, key=sortierschluessel):
            with pymupdf.open(stream=_lese_pdf(schreiben), filetype='pdf') as quelle:
                ziel.insert_pdf(quelle)
        return ziel.tobytes(deflate=True)


def _gemeinsames_objekt(schreiben_liste):
    """Objekt-Kontext des Sammel-PDFs, wenn alle Schreiben dasselbe Objekt haben, sonst ``None``."""
    ids = {s.objekt_id for s in schreiben_liste}
    return schreiben_liste[0].objekt if len(ids) == 1 and None not in ids else None


def lege_sammel_pdf_ab(pdf: bytes, schreiben_liste, stapel, user) -> Dokument:
    """Legt das Sammel-PDF als (nicht revisionssicheres) ``Dokument`` ab."""
    dateiname = f'Druckstapel-{date.today():%Y%m%d}-{str(stapel.id)[:8]}.pdf'
    objekt = _gemeinsames_objekt(schreiben_liste)
    return Dokument.objects.create(
        datei=ContentFile(pdf, name=dateiname),
        dateiname=dateiname,
        titel=f'Druckstapel {date.today():%d.%m.%Y} ({len(schreiben_liste)} Briefe)',
        kategorie=DOKUMENT_KATEGORIE,
        dokument_typ='korrespondenz',
        beschreibung='Sammel-PDF zum Druck; Original je Schreiben liegt revisionssicher im DMS.',
        dokument_datum=timezone.localdate(),
        hochgeladen_von=user,
        sha256=hashlib.sha256(pdf).hexdigest(),
        objekt=objekt,
    )


@transaction.atomic
def erzeuge(user, schreiben_ids=None, objekt=None) -> Druckstapel:
    """Erzeugt einen Druckstapel samt Sammel-PDF.

    ``schreiben_ids``: bestimmte Schreiben; ohne Angabe alle druckbereiten
    (optional eingeschränkt auf ``objekt``). Ein nicht druckbereites Schreiben
    in der Auswahl ist ein Fehler (nichts wird stillschweigend ausgelassen).
    """
    if schreiben_ids:
        auswahl = list(
            Schreiben.objects.select_for_update(of=("self",)).filter(pk__in=schreiben_ids)
            .select_related('objekt', 'empfaenger', 'einheit', 'dokument',
                            'vorlage_version__vorlage', 'mahnung')
        )
        fehlend = {str(i) for i in schreiben_ids} - {str(s.pk) for s in auswahl}
        if fehlend:
            raise ValidationError('Schreiben nicht gefunden: ' + ', '.join(sorted(fehlend)))
    else:
        ids = list(druckbereite_schreiben(objekt).values_list('pk', flat=True))
        auswahl = list(
            Schreiben.objects.select_for_update(of=("self",)).filter(pk__in=ids)
            .select_related('objekt', 'empfaenger', 'einheit', 'dokument',
                            'vorlage_version__vorlage', 'mahnung')
        )
    if not auswahl:
        raise ValidationError('Keine druckbereiten Briefe vorhanden.')
    for schreiben in auswahl:
        _pruefe_druckbereit(schreiben)

    stapel = Druckstapel.objects.create(erstellt_von=user)
    pdf = baue_sammel_pdf(auswahl)
    stapel.dokument = lege_sammel_pdf_ab(pdf, auswahl, stapel, user)
    stapel.save(update_fields=['dokument'])
    Schreiben.objects.filter(pk__in=[s.pk for s in auswahl]).update(druckstapel=stapel)
    return stapel
