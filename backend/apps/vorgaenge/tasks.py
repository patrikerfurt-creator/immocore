"""
Celery-Beat-Task für die automatische Wiedervorlage-Rückführung
(Spec Vorgang & DMS Kap. 3, Phase C).

Der Übergang selbst läuft AUSSCHLIESSLICH über
``vorgang_service.wechsle_status`` — dieser Task enthält bewusst KEINE
eigene Statuslogik, sondern iteriert nur über die fälligen Vorgänge und
delegiert an den Service (Architekturprinzip: Business-Logik nur in
``services/``).
"""
import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name='vorgaenge.pruefe_wiedervorlagen')
def pruefe_wiedervorlagen():
    """Führt alle fälligen Wiedervorlagen (``status='wiedervorlage'`` und
    ``wiedervorlage_am <= heute``) automatisch nach ``in_bearbeitung`` zurück.

    Läuft täglich über Celery Beat (siehe ``CELERY_BEAT_SCHEDULE`` in
    ``config/settings.py``). Ein Fehler bei einem einzelnen Vorgang darf die
    Verarbeitung der übrigen Vorgänge nicht abbrechen — daher try/except pro
    Vorgang.

    Benachrichtigung an ``vorgang.zugewiesen_an``: Im Projekt existiert
    aktuell KEIN Benachrichtigungs-/Notification-Mechanismus (geprüft per
    Suche über den gesamten Backend-Code). Es wird daher bewusst KEIN eigener
    Mechanismus erfunden, sondern nur geloggt — die eigentliche
    Benachrichtigung ist nachzurüsten, sobald ein solcher Mechanismus im
    Projekt existiert.
    """
    from apps.vorgaenge.models import Vorgang
    from apps.vorgaenge.services import vorgang_service

    heute = timezone.localdate()
    faellige = Vorgang.objects.filter(status='wiedervorlage', wiedervorlage_am__lte=heute)

    verarbeitet = fehler = 0
    for vorgang in faellige:
        try:
            vorgang_service.wechsle_status(
                vorgang, neuer_status='in_bearbeitung',
                ereignis_typ='system_wiedervorlage_faellig', erstellt_von=None,
            )
            verarbeitet += 1

            # Benachrichtigung folgt, sobald ein Notification-Mechanismus im
            # Projekt existiert (siehe Docstring oben) — bis dahin nur Log.
            if vorgang.zugewiesen_an_id:
                logger.info(
                    "Wiedervorlage fällig: Vorgang %s an %s zurückgeführt "
                    "(Benachrichtigung ausstehend, kein Notification-Mechanismus vorhanden).",
                    vorgang.nummer, vorgang.zugewiesen_an,
                )
            else:
                logger.info(
                    "Wiedervorlage fällig: Vorgang %s zurückgeführt (keine Zuweisung).",
                    vorgang.nummer,
                )
        except Exception:
            fehler += 1
            logger.exception(
                "Wiedervorlage-Rückführung für Vorgang %s fehlgeschlagen.", vorgang.pk,
            )

    logger.info(
        "pruefe_wiedervorlagen abgeschlossen: %s verarbeitet, %s Fehler.",
        verarbeitet, fehler,
    )
    return {'verarbeitet': verarbeitet, 'fehler': fehler}


@shared_task(name='vorgaenge.erzeuge_antwort_vorschlag')
def erzeuge_antwort_vorschlag(vorgang_id):
    """Erzeugt asynchron einen KI-Antwortvorschlag für einen frisch angelegten
    Vorgang (ausgelöst über ``transaction.on_commit`` in
    ``vorgang_service.erstelle_vorgang``, NUR wenn
    ``vorgang.typ.antwort_vorschlag_aktiv``).

    KEIN Beat-Schedule — rein event-getrieben. Ein Fehler hier (auch der
    seltene Fall, dass der Vorgang zwischenzeitlich gelöscht wurde) darf die
    Vorgangsanlage NIE beeinträchtigen; ``antwort_vorschlag_service.erzeuge_vorschlag``
    fängt API-/Netzwerkfehler bereits selbst ab (status='fehlgeschlagen').
    """
    from apps.vorgaenge.models import Vorgang
    from apps.vorgaenge.services import antwort_vorschlag_service

    try:
        vorgang = Vorgang.objects.select_related('typ', 'objekt', 'einheit', 'person').get(pk=vorgang_id)
    except Vorgang.DoesNotExist:
        logger.warning("erzeuge_antwort_vorschlag: Vorgang %s existiert nicht (mehr).", vorgang_id)
        return

    try:
        antwort_vorschlag_service.erzeuge_vorschlag(vorgang, erstellt_von=None)
    except Exception:
        logger.exception(
            "erzeuge_antwort_vorschlag für Vorgang %s unerwartet fehlgeschlagen.", vorgang.nummer,
        )


@shared_task(name='vorgaenge.mail_ordner_scan')
def mail_ordner_scan(einstellung_id: str | None = None):
    """Scannt den Mail-Posteingangs-Ordner (Muster: ``rechnungen.ordner_scan``).

    Konfiguriert wird der Ordner über ``ImportOrdnerEinstellung`` mit
    ``bereich='mails'`` — dieselbe Stelle wie Rechnungs- und Dokument-Import.
    Ohne aktive Einstellung passiert nichts; der Task ist damit gefahrlos im
    Beat-Schedule, auch wenn niemand einen Ordner hinterlegt hat.
    """
    from apps.buchhaltung.models import ImportOrdnerEinstellung
    from apps.vorgaenge.services import mail_import_service

    if einstellung_id:
        qs = ImportOrdnerEinstellung.objects.filter(
            pk=einstellung_id, aktiv=True, bereich='mails')
    else:
        qs = ImportOrdnerEinstellung.objects.filter(
            aktiv=True, bereich='mails', import_ordner__gt='')

    gesamt = {'dateien': 0, 'vorgang_neu': 0, 'thread_zuordnung': 0,
              'duplikat': 0, 'nicht_zugeordnet': 0, 'fehler': 0,
              'uebersprungen': 0}
    for einst in qs:
        ergebnis = mail_import_service.scan_ordner(
            einst.import_ordner, einst.archiv_ordner, einst.fehler_ordner,
        )
        for schluessel in gesamt:
            gesamt[schluessel] += ergebnis.get(schluessel, 0)

    logger.info("Mail-Scan abgeschlossen: %s", gesamt)
    return gesamt
