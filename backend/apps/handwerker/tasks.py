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
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives, send_mail
from django.template.loader import render_to_string
from django.utils import timezone

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
    return True


@shared_task(name='handwerker.versende_auftragsmail')
def versende_auftragsmail(auftrag_id):
    """Rendert HTML- und Text-Variante der Auftragsmail und versendet sie an
    ``auftrag.kreditor.email``.

    Links (Frontend-Route, NICHT der API-Endpunkt — die Spec verlinkt
    fälschlich auf die API, der Handwerker sähe rohes JSON) OHNE Auftrags-ID
    in der URL (keine ID-Preisgabe/aufzählbare Nummer an Mail-Gateways):
    ``{FRONTEND_BASE_URL}/auftrag-bestaetigung/{accept_token|reject_token}/``.

    Erfolg → ``auftrag_service.markiere_versendet``.
    Misserfolg → ``auftrag_service.protokolliere_versandfehler`` (Status
    bleibt unverändert, i.d.R. ``entwurf``). Wirft niemals durch.
    """
    from apps.handwerker.models import Handwerkerauftrag
    from apps.handwerker.services import auftrag_service

    try:
        auftrag = Handwerkerauftrag.objects.select_related('objekt', 'kreditor', 'token').get(pk=auftrag_id)
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

        token = getattr(auftrag, 'token', None)
        if token is None:
            logger.error(
                "versende_auftragsmail: Auftrag %s hat keinen Auftragsbestätigungs-Token.",
                auftrag.nummer,
            )
            try:
                auftrag_service.protokolliere_versandfehler(
                    auftrag, "Kein Auftragsbestätigungs-Token vorhanden.",
                )
            except Exception:
                logger.exception(
                    "Konnte Versandfehler für Auftrag %s nicht protokollieren.", auftrag.nummer,
                )
            return

        accept_url = f"{settings.FRONTEND_BASE_URL}/auftrag-bestaetigung/{token.accept_token}/"
        reject_url = f"{settings.FRONTEND_BASE_URL}/auftrag-bestaetigung/{token.reject_token}/"

        kontext = {
            'auftrag': auftrag,
            'objekt': auftrag.objekt,
            'kreditor': auftrag.kreditor,
            'accept_url': accept_url,
            'reject_url': reject_url,
            'gueltig_bis': token.gueltig_bis,
            'rechnung_empfang_email': settings.RECHNUNG_EMPFANG_EMAIL,
        }
    except Exception as exc:
        # Sicherheitsnetz für alle übrigen, hier nicht einzeln erwarteten
        # Zugriffe (Token-/Settings-Zugriff, Kontextaufbau) — vom Eintritt in
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
            subject=f"Handwerkerauftrag {auftrag.nummer} — {auftrag.titel}",
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


@shared_task(name='handwerker.benachrichtige_intern')
def benachrichtige_intern(auftrag_id, art):
    """Informiert intern per Mail über eine Handwerker-Antwort
    (Annahme/Ablehnung) über den Bestätigungslink.

    Empfänger: ``auftrag.erstellt_von.email`` falls vorhanden, sonst alle
    Staff-User mit gesetzter E-Mail-Adresse. Ein Fehler wird nur geloggt —
    die Status-Änderung selbst ist zu diesem Zeitpunkt bereits verbucht.
    """
    from apps.handwerker.models import Handwerkerauftrag

    try:
        auftrag = Handwerkerauftrag.objects.select_related('erstellt_von', 'kreditor').get(pk=auftrag_id)
    except Handwerkerauftrag.DoesNotExist:
        logger.warning("benachrichtige_intern: Auftrag %s existiert nicht (mehr).", auftrag_id)
        return
    except Exception:
        # Wie bei versende_auftragsmail: veraltetes Schema-Wissen des Worker
        # nach einer Migration darf hier ebenfalls nicht durchwerfen — es gibt
        # für interne Benachrichtigungen kein Ereignis-Ziel, daher nur loggen.
        logger.exception(
            "benachrichtige_intern: Laden von Auftrag %s fehlgeschlagen.", auftrag_id,
        )
        return

    try:
        if auftrag.erstellt_von_id and auftrag.erstellt_von.email:
            empfaenger = [auftrag.erstellt_von.email]
        else:
            User = get_user_model()
            empfaenger = list(
                User.objects.filter(is_staff=True).exclude(email='').values_list('email', flat=True)
            )

        if not empfaenger:
            logger.info(
                "benachrichtige_intern: keine Empfänger für Auftrag %s ermittelbar.", auftrag.nummer,
            )
            return

        art_text = 'angenommen' if art == 'angenommen' else 'abgelehnt'
        text = (
            f"Der Handwerkerauftrag {auftrag.nummer} ({auftrag.titel}) für "
            f"{auftrag.kreditor.name} wurde vom Handwerker {art_text}."
        )
        if art == 'abgelehnt' and auftrag.ablehnung_grund:
            text += f"\n\nGrund: {auftrag.ablehnung_grund}"
    except Exception:
        logger.exception(
            "benachrichtige_intern: Empfängerermittlung/Textaufbau für Auftrag %s fehlgeschlagen.",
            auftrag_id,
        )
        return

    # Gleiche Produktions-Sperre wie in versende_auftragsmail (siehe
    # _versand_konfiguriert): es ist nur eine interne Info-Mail, kein
    # Auftragszustand hängt daran — daher genügt hier ein Log statt eines
    # Ereignisses.
    if not settings.DEBUG and not _versand_konfiguriert():
        logger.warning(
            "benachrichtige_intern: E-Mail-Versand ist nicht konfiguriert "
            "(EMAIL_BACKEND=%r, EMAIL_HOST=%r) — interne Benachrichtigung für "
            "Auftrag %s wird NICHT versendet.",
            settings.EMAIL_BACKEND, settings.EMAIL_HOST, auftrag.nummer,
        )
        return

    try:
        send_mail(
            subject=f"Handwerkerauftrag {auftrag.nummer} wurde {art_text}",
            message=text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=empfaenger,
        )
    except Exception:
        logger.exception("Interne Benachrichtigung für Auftrag %s fehlgeschlagen.", auftrag.nummer)


@shared_task(name='handwerker.pruefe_abgelaufene_auftraege')
def pruefe_abgelaufene_auftraege():
    """Setzt alle Aufträge mit Status ``versendet``, deren Bestätigungs-Token
    abgelaufen (aber nicht verbraucht) ist, automatisch auf ``abgelaufen``.

    Läuft täglich über Celery Beat (siehe ``CELERY_BEAT_SCHEDULE`` in
    ``config/settings.py``). Ein Fehler bei einem einzelnen Auftrag darf die
    Verarbeitung der übrigen nicht abbrechen — daher try/except pro Auftrag
    (Muster: ``apps.vorgaenge.tasks.pruefe_wiedervorlagen``).
    """
    from apps.handwerker.models import Handwerkerauftrag
    from apps.handwerker.services import auftrag_service

    jetzt = timezone.now()
    try:
        # list(...) statt lazy QuerySet: die eigentliche DB-Auswertung (z.B.
        # ein Schemafehler nach einer Migration, gegen die der Worker/Beat-
        # Prozess noch nicht neu gestartet wurde) soll hier abgefangen werden
        # und nicht erst irgendwo mitten in der Schleife unten durchschlagen.
        kandidaten = list(Handwerkerauftrag.objects.filter(
            status='versendet',
            token__verbraucht_am__isnull=True,
            token__gueltig_bis__lt=jetzt,
        ))
    except Exception:
        logger.exception("pruefe_abgelaufene_auftraege: Auswertung des Querysets fehlgeschlagen.")
        return {'verarbeitet': 0, 'fehler': 0}

    verarbeitet = fehler = 0
    for auftrag in kandidaten:
        try:
            auftrag_service.wechsle_status(
                auftrag, 'abgelaufen', erstellt_von=None,
                ereignis_typ='system_abgelaufen', _system_ausloeser=True,
            )
            verarbeitet += 1
        except Exception:
            fehler += 1
            logger.exception("Ablaufprüfung für Auftrag %s fehlgeschlagen.", auftrag.pk)

    logger.info(
        "pruefe_abgelaufene_auftraege abgeschlossen: %s verarbeitet, %s Fehler.",
        verarbeitet, fehler,
    )
    return {'verarbeitet': verarbeitet, 'fehler': fehler}
