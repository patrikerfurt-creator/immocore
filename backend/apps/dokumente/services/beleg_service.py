import hashlib
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.dokumente.models import BelegnummerZaehler, Dokument


@transaction.atomic
def lege_rechnungsbeleg_ab(rechnung, datei_bytes: bytes, dateiname: str,
                           objekt, hochgeladen_von) -> Dokument:
    """Legt das Rechnungs-PDF genau einmal als Dokument ab und koppelt es an die Rechnung.

    Vergibt dabei die globale Belegnummer. Doppelte Ablage auf derselben
    Rechnung ist gesperrt (Idempotenzschutz über beleg_dokument).
    """
    if rechnung.beleg_dokument_id:
        raise ValidationError("Rechnung hat bereits einen Beleg.")

    # Owner-Regel B-Hybrid (Vorgang & DMS Kap. 1.6): Beleg-Dokumente werden OHNE
    # Kontext-FK (objekt/einheit/vorgang/person) angelegt — Owner ist ausschließlich
    # die Rechnung über beleg_dokument. `objekt` bleibt Parameter für Aufrufer-
    # Kompatibilität, wird aber bewusst NICHT mehr auf das Dokument gesetzt.
    dok = Dokument.objects.create(
        datei=ContentFile(datei_bytes, name=dateiname),
        dateiname=dateiname,
        kategorie='Beleg',
        dokument_typ='beleg',
        sha256=hashlib.sha256(datei_bytes).hexdigest(),
        revisionssicher=False,   # Sperre erst bei Freigabe (OP-Buchung)
        hochgeladen_von=hochgeladen_von,
        beleg_nummer=BelegnummerZaehler.naechste_nummer(),
    )
    rechnung.beleg_dokument = dok
    rechnung.save(update_fields=['beleg_dokument'])
    return dok


def rechnungen_root() -> Path:
    """Wurzel des Rechnungen-Bind-Mounts, abgeleitet aus der Import-Ordner-Konfiguration.

    Nutzt ``ImportOrdnerEinstellung`` (bereich='rechnungen', Feld ``archiv_ordner``,
    z. B. ``/app/rechnungen/archiv``) — die Wurzel ist deren Elternordner
    (``/app/rechnungen``). Ohne konfigurierte Einstellung Fallback hart auf
    ``/app/rechnungen`` (Live-Bind-Mount-Pfad).
    """
    from apps.buchhaltung.models import ImportOrdnerEinstellung

    einstellung = ImportOrdnerEinstellung.objects.filter(bereich='rechnungen').first()
    if einstellung and einstellung.archiv_ordner:
        return Path(einstellung.archiv_ordner).parent
    return Path('/app/rechnungen')


@transaction.atomic
def koppel_rechnungsbeleg(rechnung, hochgeladen_von) -> Dokument:
    """Koppelt die bereits im Rechnungen-Archiv liegende Datei (rechnung.pfad)
    als Beleg-Dokument an die Rechnung — reine Referenz-Übernahme, KEINE Datei-Operation.

    Die Logik entspricht dem Neuanlage-Zweig von migriere_rechnungsbelege
    (dort wiederverwendet); die Existenz der physischen Datei wird hier NICHT
    geprüft — das bleibt Aufgabe des Aufrufers (die Pipeline hat die Datei
    gerade erst selbst per shutil.move abgelegt, der Migrations-Command prüft
    davor selbst).
    """
    if rechnung.beleg_dokument_id:
        raise ValidationError("Rechnung hat bereits einen Beleg.")
    if not rechnung.pfad:
        raise ValidationError("Rechnung hat keinen Pfad.")

    root = rechnungen_root()
    try:
        rel = Path(rechnung.pfad).relative_to(root).as_posix()
    except ValueError:
        raise ValidationError(f"Rechnung.pfad liegt außerhalb der Rechnungen-Wurzel '{root}'.")

    # Owner-Regel B-Hybrid (Vorgang & DMS Kap. 1.6): kein Kontext-FK — Owner ist
    # die Rechnung über beleg_dokument (siehe lege_rechnungsbeleg_ab).
    dok = Dokument.objects.create(
        datei=rel,                     # String-Zuweisung: Storage schreibt NICHTS
        ablage_wurzel='rechnungen',
        dateiname=rechnung.dateiname or Path(rechnung.pfad).name,
        kategorie='Beleg',
        dokument_typ='beleg',
        sha256=rechnung.sha256_hash or None,
        hochgeladen_von=hochgeladen_von,
        revisionssicher=False,
        beleg_nummer=BelegnummerZaehler.naechste_nummer(),
    )
    rechnung.beleg_dokument = dok
    rechnung.save(update_fields=['beleg_dokument'])
    return dok


def dokument_pfad(dokument: Dokument) -> Path:
    """Einzige erlaubte Pfadauflösung für Dokument.datei (berücksichtigt ablage_wurzel)."""
    wurzeln = {'media': Path(settings.MEDIA_ROOT), 'rechnungen': rechnungen_root()}
    return wurzeln[dokument.ablage_wurzel] / dokument.datei.name


def sperre_beleg_revisionssicher(dokument: Dokument) -> Dokument:
    """Setzt die GoBD-Sperre (Löschen/Datei-Austausch) auf einem Beleg-Dokument. Idempotent."""
    if dokument.revisionssicher:
        return dokument
    dokument.revisionssicher = True
    dokument.revisionssicher_seit = timezone.now()
    dokument.save(update_fields=['revisionssicher', 'revisionssicher_seit'])
    return dokument


def loeschsperre_grund(dokument: Dokument) -> str | None:
    """Einzige Quelle für die Lösch-Entscheidung eines Dokuments (API-Vertrag
    Belegübersicht-Anreicherung, Nachtrag v1.1). Wird sowohl vom DokumentSerializer
    (Felder `loeschbar`/`loeschsperre_grund`) als auch von DokumentViewSet.destroy()
    genutzt — die Regel liegt damit an genau einer Stelle und beide können nicht
    auseinanderdriften.

    Regelreihenfolge (erste zutreffende gewinnt), gibt `None` zurück, wenn nichts
    gegen ein Löschen spricht:
    1. `revisionssicher` (GoBD, unumkehrbar).
    2. verknüpfte Rechnung ist geprüft (`Rechnung.STATUS_GEPRUEFT`) — der Dokumenttyp
       ist dabei irrelevant, entscheidend ist allein die vorhandene Verknüpfung
       (anders als bei der Belegübersicht-Anreicherung, die zusätzlich
       `dokument_typ == 'beleg'` verlangt, weil sie nur echte Belegzeilen mit
       Rechnungsdaten füllen soll — hier geht es um die reine Löschbarkeit).
    3. verknüpfte Rechnung vorhanden, aber (noch) ungeprüft.
    """
    if dokument.revisionssicher:
        return 'Revisionssicherer Beleg (GoBD) — Löschen nicht zulässig.'

    try:
        rechnung = dokument.rechnung
    except ObjectDoesNotExist:
        return None

    if rechnung.ist_geprueft:
        return (
            f'Rechnung ist geprüft (Status: {rechnung.get_status_display()}) — '
            'Beleg muss erhalten bleiben.'
        )
    return 'Beleg ist mit einer Rechnung verknüpft — zuerst die Rechnung entfernen.'
