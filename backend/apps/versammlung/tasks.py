"""
Celery-Tasks des EV-Moduls (Spec v1.1 Kap. 6).

Die Tasks enthalten KEINE Business-Logik — sie laden die Objekte und delegieren
an ``einladung_service``. Kein Task darf jemals durchwerfen: ein Fehler beim
Versand darf weder die EV beschädigen noch den Worker abschießen.

BETRIEBSHINWEIS: Der Celery-Worker lädt die Modelldefinitionen beim Start. Nach
JEDER Migration an den hier verwendeten Modellen MUSS der Worker neu gestartet
werden (``docker restart immocore_celery_worker``) — sonst arbeitet er mit
veraltetem Schema-Wissen weiter und ``select_related`` schlägt mit
``ProgrammingError`` fehl.
"""
import logging

from celery import shared_task
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)


@shared_task(name='versammlung.versende_ev_einladungen')
def versende_ev_einladungen(ev_id, user_id, plan=None):
    """Versendet die Einladungen einer EV über die geplanten Kanäle.

    Rückgabe ist die Statistik von ``einladung_service.versende_einladungen``
    bzw. ``None``, wenn schon das Laden fehlschlägt. Jeder Fehlerpfad wird
    protokolliert, keiner wirft durch.
    """
    from apps.versammlung.models import Eigentuemerversammlung
    from apps.versammlung.services import einladung_service, ev_service

    try:
        ev = (
            Eigentuemerversammlung.objects
            .select_related('objekt', 'einladungs_pdf')
            .get(pk=ev_id)
        )
    except Eigentuemerversammlung.DoesNotExist:
        logger.warning('versende_ev_einladungen: EV %s existiert nicht (mehr).', ev_id)
        return None
    except Exception:
        logger.exception(
            'versende_ev_einladungen: Laden der EV %s fehlgeschlagen (evtl. '
            'veraltetes Schema-Wissen des Celery-Workers nach einer Migration '
            '— Worker neu starten).', ev_id,
        )
        return None

    try:
        user = get_user_model().objects.get(pk=user_id)
    except Exception:
        logger.exception(
            'versende_ev_einladungen: Benutzer %s nicht ladbar — Versand für '
            'EV %s abgebrochen (das Protokoll braucht einen Urheber).',
            user_id, ev_id,
        )
        return None

    try:
        return einladung_service.versende_einladungen(ev, user, plan=plan or {})
    except Exception as fehler:
        logger.exception('versende_ev_einladungen: Versand für EV %s fehlgeschlagen.', ev_id)
        try:
            ev_service.vermerke_ereignis(
                ev, 'versand_fehler', user,
                text=f'Versandlauf abgebrochen: {fehler}',
            )
        except Exception:
            logger.exception(
                'Konnte Versandfehler für EV %s nicht protokollieren.', ev_id,
            )
        return None
