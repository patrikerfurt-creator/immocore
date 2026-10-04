"""Celery-Tasks des Moduls Vorlagen & Korrespondenz (Spec 7.3).

Die Tasks enthalten KEINE eigene Statuslogik: sie laden die Objekte und
delegieren an ``schreiben_service`` bzw. ``serienlauf_service``. Kein Task
wirft je durch - ein Fehler wird protokolliert und im Rückgabewert gemeldet.

BETRIEBSHINWEIS: Der Celery-Worker lädt Modelle und Tasks einmalig beim Start.
Nach Migrationen an Korrespondenz-Modellen und nach neuen Tasks
``docker restart immocore_celery_worker``.
"""
import logging

from celery import shared_task
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)


def _lade_user(user_id):
    if user_id is None:
        return None
    return get_user_model().objects.filter(pk=user_id).first()


@shared_task(name='korrespondenz.versende_schreiben')
def versende_schreiben(schreiben_id, user_id=None, kanal=None):
    """Versendet ein freigegebenes Schreiben (E-Mail oder Brief -> Druckstapel).

    Rückgabe: ``{'ok': bool, 'ergebnis': str, 'hinweis': str}``.
    """
    from apps.korrespondenz.models import Schreiben
    from apps.korrespondenz.services import schreiben_service

    try:
        schreiben = Schreiben.objects.get(pk=schreiben_id)
        ergebnis = schreiben_service.versenden(schreiben, _lade_user(user_id), kanal=kanal)
    except Schreiben.DoesNotExist:
        logger.warning('versende_schreiben: Schreiben %s existiert nicht (mehr).', schreiben_id)
        return {'ok': False, 'ergebnis': 'nicht_gefunden', 'hinweis': ''}
    except Exception as exc:  # noqa: BLE001 - Tasks werfen nie durch
        logger.exception('versende_schreiben: Schreiben %s fehlgeschlagen.', schreiben_id)
        return {'ok': False, 'ergebnis': 'fehler', 'hinweis': str(exc)}
    return {
        'ok': ergebnis.ergebnis != 'fehlgeschlagen',
        'ergebnis': ergebnis.ergebnis, 'hinweis': ergebnis.hinweis,
    }


@shared_task(name='korrespondenz.serienlauf_verarbeiten')
def serienlauf_verarbeiten(serienlauf_id, user_id=None):
    """Verarbeitet einen freigegebenen Serienlauf (Mails raus, Briefe in den Druckstapel).

    Rückgabe: ``{'ok': bool, 'status': str}``.
    """
    from apps.korrespondenz.models import Serienlauf
    from apps.korrespondenz.services import serienlauf_service

    try:
        lauf = Serienlauf.objects.get(pk=serienlauf_id)
        user = _lade_user(user_id) or lauf.freigegeben_von
        lauf = serienlauf_service.verarbeite(lauf, user)
    except Serienlauf.DoesNotExist:
        logger.warning('serienlauf_verarbeiten: Serienlauf %s existiert nicht (mehr).', serienlauf_id)
        return {'ok': False, 'status': 'nicht_gefunden'}
    except Exception:  # noqa: BLE001 - Tasks werfen nie durch
        logger.exception('serienlauf_verarbeiten: Serienlauf %s fehlgeschlagen.', serienlauf_id)
        return {'ok': False, 'status': 'fehler'}
    return {'ok': lauf.status == 'versendet', 'status': lauf.status}
