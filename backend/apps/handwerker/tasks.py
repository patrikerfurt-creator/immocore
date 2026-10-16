"""
Celery-Tasks für Handwerkeraufträge (Phase B, Auftrag Handwerkerauftrag Kap. 3).

Der eigentliche Statuswechsel läuft AUSSCHLIESSLICH über
``auftrag_service`` — dieser Task enthält bewusst KEINE eigene Statuslogik,
sondern rendert/versendet die Mail und delegiert die Verbuchung des
Ergebnisses an den Service (Architekturprinzip: Business-Logik nur in
``services/``).

Kein Task darf jemals durchwerfen — ein Fehler beim Mailversand darf weder
den Auftrag beschädigen noch den Celery-Worker zum Absturz bringen.

BETRIEBSHINWEIS: Der Celery-Worker lädt die Modelldefinitionen einmalig beim
Start. Nach JEDER Migration, die Felder/Beziehungen an hier verwendeten
Modellen ändert (z.B. ``Kreditor``), MUSS der Worker neu gestartet werden
(``docker restart immocore_celery_worker``) — sonst arbeitet er mit
veraltetem Schema-Wissen weiter und Zugriffe wie ``select_related(...)``
schlagen mit ``ProgrammingError`` (unbekannte Spalte) fehl.
"""
import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

# Backends, die NIE tatsächlich versenden (Konsole/Dummy) oder ein
# unvollständig konfiguriertes SMTP-Backend gelten als "nicht versandfähig".
_NICHT_VERSANDFAEHIGE_BACKENDS = (
    'django.core.mail.backends.console.EmailBackend',
    'django.core.mail.backends.dummy.EmailBackend',
)


def _versand_konfiguriert() -> bool:
    """Prüft, ob ``settings.EMAIL_BACKEND`` tatsächlich versendet.

    Hintergrund (stille Falle): fehlt auf einem Produktionsserver die
    SMTP-Konfiguration in ``.env.prod`` (kein ``EMAIL_BACKEND``/``EMAIL_HOST``),
    greift in ``config/settings.py`` der Default — das Konsolen-Backend. Das
    meldet ``mail.send()`` immer als erfolgreich, obwohl die Mail nur ins
    Container-Log geschrieben wird. Ohne diese Prüfung würde ein
    Handwerkerauftrag als ``versendet`` markiert, ohne dass der Handwerker je
    davon erfährt.

    ``locmem`` (von Django-Tests verwendet) gilt bewusst als versandfähig.
    """
    backend = settings.EMAIL_BACKEND
    if backend in _NICHT_VERSANDFAEHIGE_BACKENDS:
        return False
    if backend == 'django.core.mail.backends.smtp.EmailBackend' and not settings.EMAIL_HOST:
        return False
    if backend == 'config.email_backends.GraphEmailBackend' and not (
        settings.MS_GRAPH_TENANT_ID and settings.MS_GRAPH_CLIENT_ID
        and settings.MS_GRAPH_CLIENT_SECRET
    ):
        return False
    return True


@shared_task(name='handwerker.versende_auftragsmail')
def versende_auftragsmail(auftrag_id):
    """Rendert HTML- und Text-Variante der Auftragsmail und versendet sie an
    ``auftrag.kreditor.email``.

    Die Mail enthält KEINE Bestätigungslinks: der Handwerker antwortet
    formlos per Mail. Als Lieferadresse dient der Eingang
    (``auftrag_service.liefer_eingang``), sonst die Objektadresse.

    Erfolg → ``auftrag_service.markiere_versendet``.
    Misserfolg → ``auftrag_service.protokolliere_versandfehler`` (Status
    bleibt unverändert, i.d.R. ``entwurf``). Wirft niemals durch.
    """
    from apps.handwerker.models import Handwerkerauftrag
    from apps.handwerker.services import auftrag_service

    try:
        auftrag = Handwerkerauftrag.objects.select_related(
            'objekt', 'kreditor', 'vorgang__einheit__eingang',
        ).get(pk=auftrag_id)
    except Handwerkerauftrag.DoesNotExist:
        logger.warning("versende_auftragsmail: Auftrag %s existiert nicht (mehr).", auftrag_id)
        return
    except Exception:
        # Jeder ANDERE Fehler beim Laden (z.B. ProgrammingError nach einer
        # Migration, gegen die der Worker noch nicht neu gestartet wurde —
        # siehe Modul-Docstring) darf den Task nicht durchwerfen lassen. Der
        # Fehler kommt typischerweise vom `select_related` selbst (Zugriff auf
        # eine inzwischen umgebaute Spalte); ein zweiter, minimaler Ladeversuch
        # OHNE `select_related` erlaubt es i.d.R. dennoch, das Auftragsobjekt
        # zu bekommen und daran ein Fehler-Ereignis zu protokollieren.
        logger.exception(
            "versende_auftragsmail: Laden von Auftrag %s fehlgeschlagen (evtl. veraltetes "
            "Schema-Wissen des Celery-Workers nach einer Migration — Worker neu starten).",
            auftrag_id,
        )
        try:
            auftrag = Handwerkerauftrag.objects.get(pk=auftrag_id)
        except Exception:
            logger.exception(
                "versende_auftragsmail: auch der Ladeversuch ohne select_related für "
                "Auftrag %s ist fehlgeschlagen — kein Ereignis protokollierbar.", auftrag_id,
            )
            return
        try:
            auftrag_service.protokolliere_versandfehler(
                auftrag,
                "Versand abgebrochen: Auftrag konnte nicht vollständig geladen werden "
                "(vermutlich veraltetes Schema-Wissen des Celery-Workers nach einer "
                "Migration).",
            )
        except Exception:
            logger.exception(
                "Konnte Versandfehler für Auftrag %s nicht protokollieren.", auftrag_id,
            )
        return

    # Objektbezogenes Versand-Gate (schrittweiser Rollout): Solange das Objekt
    # nicht freigeschaltet ist (Objekt.mailversand_aktiv=False, Default),
    # geht KEINE Auftragsmail raus — bewusst auch lokal (DEBUG), damit
    # Testobjekte nie versehentlich einen echten Handwerker anmailen. Der
    # Status bleibt unverändert (i.d.R. 'entwurf'): nach dem Freischalten des
    # Objekts kann der Auftrag einfach erneut versendet werden.
    if not (auftrag.objekt_id and auftrag.objekt.mailversand_aktiv):
        logger.info(
            "versende_auftragsmail: Objekt %s ist nicht für E-Mail-Versand "
            "freigeschaltet (mailversand_aktiv=False) — Auftrag %s wird NICHT versendet.",
            auftrag.objekt_id, auftrag.nummer,
        )
        try:
            auftrag_service.protokolliere_versandfehler(
                auftrag,
                "Versand zurückgehalten: Das Objekt ist noch nicht für den "
                "E-Mail-Versand freigeschaltet (mailversand_aktiv=False).",
            )
        except Exception:
            logger.exception(
                "Konnte Versand-Zurückhaltung für Auftrag %s nicht protokollieren.",
                auftrag.nummer,
            )
        return

    try:
        # Produktions-Sperre gegen die stille Falle (siehe _versand_konfiguriert):
        # lokal (DEBUG=True) läuft der Versand wie bisher über das
        # Konsolen-Backend durch, in Produktion (DEBUG=False) wird ein nicht
        # versandfähig konfigurierter Mailserver hart blockiert statt einen
        # Auftrag fälschlich als 'versendet' zu markieren.
        if not settings.DEBUG and not _versand_konfiguriert():
            logger.error(
                "versende_auftragsmail: E-Mail-Versand ist nicht konfiguriert "
                "(EMAIL_BACKEND=%r, EMAIL_HOST=%r) — Auftrag %s wird NICHT versendet.",
                settings.EMAIL_BACKEND, settings.EMAIL_HOST, auftrag.nummer,
            )
            try:
                auftrag_service.protokolliere_versandfehler(
                    auftrag,
                    "E-Mail-Versand ist auf diesem Server nicht konfiguriert (SMTP fehlt) — "
                    "der Handwerker wurde NICHT benachrichtigt. Bitte an die Administration wenden.",
                )
            except Exception:
                logger.exception(
                    "Konnte Versandfehler für Auftrag %s nicht protokollieren.", auftrag.nummer,
                )
            return

        # Defensive Prüfung (Orchestrator-Korrektur, Schritt 0): der Kreditor kann
        # sich zwischen Anlage/Statuswechsel und diesem asynchronen Versand
        # geändert haben (ist_handwerker abgewählt oder E-Mail geleert). Ohne
        # diese Prüfung würde ``mail.send()`` an eine leere Adresse versuchen
        # bzw. ein inzwischen ungültiger Kreditor beliefert.
        if not auftrag.kreditor.ist_handwerker or not auftrag.kreditor.email:
            logger.warning(
                "versende_auftragsmail: Kreditor von Auftrag %s ist kein gültiger "
                "Handwerker-Empfänger mehr (ist_handwerker=%s, email=%r) — Versand abgebrochen.",
                auftrag.nummer, auftrag.kreditor.ist_handwerker, auftrag.kreditor.email,
            )
            try:
                auftrag_service.protokolliere_versandfehler(
                    auftrag,
                    "Versand abgebrochen: Kreditor ist nicht (mehr) als Handwerker markiert "
                    "oder hat keine E-Mail-Adresse hinterlegt.",
                )
            except Exception:
                logger.exception(
                    "Konnte Versandfehler für Auftrag %s nicht protokollieren.", auftrag.nummer,
                )
            return

        eingang = auftrag_service.liefer_eingang(auftrag)
        quelle = eingang if eingang is not None else auftrag.objekt

        kontext = {
            'auftrag': auftrag,
            'objekt': auftrag.objekt,
            'kreditor': auftrag.kreditor,
            'liefer_strasse': quelle.strasse,
            'liefer_plz': quelle.plz,
            'liefer_ort': quelle.ort,
            'rechnung_empfang_email': settings.RECHNUNG_EMPFANG_EMAIL,
        }
    except Exception as exc:
        # Sicherheitsnetz für alle übrigen, hier nicht einzeln erwarteten
        # Zugriffe (Eingang-/Settings-Zugriff, Kontextaufbau) — vom Eintritt in
        # den Task bis zum Ende darf kein Pfad ungeschützt bleiben.
        logger.exception(
            "versende_auftragsmail: unerwarteter Fehler vor dem Rendern für Auftrag %s.",
            auftrag.nummer,
        )
        try:
            auftrag_service.protokolliere_versandfehler(auftrag, str(exc))
        except Exception:
            logger.exception(
                "Konnte Versandfehler für Auftrag %s nicht protokollieren.", auftrag.nummer,
            )
        return

    try:
        text_body = render_to_string('email/handwerkerauftrag.txt', kontext)
        html_body = render_to_string('email/handwerkerauftrag.html', kontext)

        mail = EmailMultiAlternatives(
            subject=f"Auftrag {auftrag.nummer} — {auftrag.titel}",
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[auftrag.kreditor.email],
        )
        mail.attach_alternative(html_body, 'text/html')
        mail.send()
    except Exception as exc:
        logger.exception("Mailversand für Handwerkerauftrag %s fehlgeschlagen.", auftrag.nummer)
        try:
            auftrag_service.protokolliere_versandfehler(auftrag, str(exc))
        except Exception:
            logger.exception(
                "Konnte Versandfehler für Auftrag %s nicht protokollieren.", auftrag.nummer,
            )
        return

    try:
        auftrag_service.markiere_versendet(auftrag)
    except Exception:
        logger.exception(
            "Mail für Auftrag %s wurde versendet, Status-Update ist aber fehlgeschlagen.",
            auftrag.nummer,
        )
