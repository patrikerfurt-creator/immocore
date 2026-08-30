"""
Anhalten und Entscheiden von Kreditor-Dublettenverdacht.

Drei Ausgänge, wie mit Patrik festgelegt:

``als_neu_anlegen``   doch eine eigene Firma → Kreditor wird angelegt
``zuordnen``          derselbe Lieferant → bestehender Kreditor wird gesetzt
``ablehnen``          Beleg wird zurückgestellt, kein Kreditor entsteht

Alle drei schreiben die Entscheidung samt Benutzer und Zeitpunkt fest.
Solange keine gefallen ist, bleibt die Rechnung ohne Kreditor und damit
nicht buchbar.
"""
import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import (
    Kreditor,
    KreditorBankverbindung,
    KreditorDublettenPruefung,
    Rechnung,
)
from ..normalisierung import normalisiere_iban
from . import kreditor_matching

logger = logging.getLogger(__name__)


class DublettenPruefungFehler(Exception):
    """Fachlicher Fehler bei der Entscheidung."""


@transaction.atomic
def lege_pruefung_an(rechnung: Rechnung, ergebnis, name: str, iban: str) -> KreditorDublettenPruefung:
    """Hält die Kreditor-Anlage an und legt den Prüffall an.

    ``update_or_create``: eine erneute Verarbeitung derselben Rechnung
    (z.B. OCR-Wiederholung nach fehlender Internetverbindung) soll den
    offenen Fall aktualisieren statt an der OneToOne-Beziehung zu
    scheitern. Eine bereits entschiedene Prüfung wird dabei NICHT
    überschrieben — sonst ginge die getroffene Entscheidung verloren.
    """
    bestehend = getattr(rechnung, 'dubletten_pruefung', None)
    if bestehend is not None and bestehend.status != KreditorDublettenPruefung.STATUS_OFFEN:
        return bestehend

    pruefung, _ = KreditorDublettenPruefung.objects.update_or_create(
        rechnung=rechnung,
        defaults={
            'erkannter_name': (name or '')[:255],
            'erkannte_iban': normalisiere_iban(iban)[:34],
            'anlass': ergebnis.anlass,
            'kandidaten': [k.as_dict() for k in ergebnis.kandidaten],
            'status': KreditorDublettenPruefung.STATUS_OFFEN,
        },
    )
    logger.info(
        'Kreditor-Dublettenverdacht (%s) fuer Rechnung %s: %s Kandidat(en)',
        ergebnis.anlass, rechnung.pk, len(ergebnis.kandidaten),
    )
    return pruefung


def _abschluss(pruefung, status, kreditor, benutzer, notiz):
    pruefung.status = status
    pruefung.ergebnis_kreditor = kreditor
    pruefung.entschieden_von = benutzer
    pruefung.entschieden_am = timezone.now()
    if notiz:
        pruefung.notiz = notiz
    pruefung.save(update_fields=[
        'status', 'ergebnis_kreditor', 'entschieden_von', 'entschieden_am', 'notiz',
    ])


def _pruefe_offen(pruefung: KreditorDublettenPruefung) -> None:
    if pruefung.status != KreditorDublettenPruefung.STATUS_OFFEN:
        raise DublettenPruefungFehler(
            f'Diese Prüfung wurde bereits entschieden ({pruefung.get_status_display()}).'
        )


@transaction.atomic
def als_neu_anlegen(pruefung: KreditorDublettenPruefung, benutzer, notiz: str = '') -> Kreditor:
    """Der Lieferant ist doch eine eigene Firma."""
    _pruefe_offen(pruefung)

    iban = pruefung.erkannte_iban
    if iban and Kreditor.objects.filter(iban=iban).exists():
        # Kreditor.iban ist unique — ohne diese Prüfung liefe der Nutzer in
        # einen Integrity-Fehler statt in eine verständliche Meldung.
        raise DublettenPruefungFehler(
            'Diese IBAN ist bereits einem anderen Kreditor zugeordnet. '
            'Bitte stattdessen zuordnen oder die IBAN korrigieren.'
        )

    kreditor = Kreditor.objects.create(
        name=pruefung.erkannter_name,
        iban=iban or None,
    )
    _abschluss(pruefung, KreditorDublettenPruefung.STATUS_NEU_ANGELEGT,
               kreditor, benutzer, notiz)

    rechnung = pruefung.rechnung
    rechnung.kreditor = kreditor
    rechnung.save(update_fields=['kreditor'])
    return kreditor


@transaction.atomic
def zuordnen(pruefung: KreditorDublettenPruefung, kreditor_id, benutzer,
             iban_uebernehmen: bool = True, notiz: str = '') -> Kreditor:
    """Derselbe Lieferant — die Rechnung bekommt den bestehenden Kreditor.

    Ist die erkannte IBAN dort noch nicht bekannt, wird sie als weitere
    Bankverbindung ergänzt (``iban_uebernehmen``). Die primäre
    ``Kreditor.iban`` bleibt unangetastet: sie zu überschreiben würde die
    Zuordnung bereits laufender Zahlungen verändern, und genau das darf
    ein Beleg nicht nebenbei auslösen.
    """
    _pruefe_offen(pruefung)

    try:
        kreditor = Kreditor.objects.get(pk=kreditor_id)
    except (Kreditor.DoesNotExist, ValidationError, ValueError):
        raise DublettenPruefungFehler('Der gewählte Kreditor existiert nicht.')

    iban = pruefung.erkannte_iban
    if iban_uebernehmen and iban and not kreditor_matching.gleiche_iban(kreditor, iban):
        if Kreditor.objects.filter(iban=iban).exclude(pk=kreditor.pk).exists() or \
           KreditorBankverbindung.objects.filter(iban=iban).exclude(kreditor=kreditor).exists():
            raise DublettenPruefungFehler(
                'Diese IBAN gehört bereits zu einem anderen Kreditor. '
                'Bitte zuerst dort klären.'
            )
        if not (kreditor.iban or '').strip():
            # Der Kreditor hatte noch gar keine Bankverbindung — dann ist
            # die erkannte die primäre.
            kreditor.iban = iban
            kreditor.save(update_fields=['iban'])
        else:
            KreditorBankverbindung.objects.create(
                kreditor=kreditor, iban=iban,
                bemerkung=f'Aus Rechnung übernommen ({pruefung.rechnung.rechnungsnummer or "ohne Nummer"})',
                erfasst_durch=benutzer,
            )

    _abschluss(pruefung, KreditorDublettenPruefung.STATUS_ZUGEORDNET,
               kreditor, benutzer, notiz)

    rechnung = pruefung.rechnung
    rechnung.kreditor = kreditor
    rechnung.save(update_fields=['kreditor'])
    return kreditor


@transaction.atomic
def ablehnen(pruefung: KreditorDublettenPruefung, benutzer, notiz: str = '') -> None:
    """Beleg zurückstellen — es entsteht kein Kreditor.

    Die Rechnung wird auf ``abgelehnt`` gesetzt; ohne Kreditor kann sie
    ohnehin nicht weiterlaufen, und ein stiller Verbleib in der Inbox
    würde den Fall nur wieder auftauchen lassen.
    """
    _pruefe_offen(pruefung)
    _abschluss(pruefung, KreditorDublettenPruefung.STATUS_ABGELEHNT,
               None, benutzer, notiz)

    rechnung = pruefung.rechnung
    rechnung.status = 'abgelehnt'
    rechnung.save(update_fields=['status'])
