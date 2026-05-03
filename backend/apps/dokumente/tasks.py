import pathlib
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


def scan_dokumente_einstellung(einst) -> dict:
    from apps.dokumente.models import Dokument
    from django.contrib.auth import get_user_model
    from django.core.files import File

    User = get_user_model()
    system_user = User.objects.filter(is_superuser=True).order_by('date_joined').first()
    if not system_user:
        logger.warning("Dokumente-Import: Kein Superuser vorhanden, Import übersprungen")
        return {'importiert': 0, 'fehler': 0, 'dateien': 0}

    ordner = pathlib.Path(einst.import_ordner)
    if not ordner.is_dir():
        logger.warning("Dokumente-Import: Ordner nicht gefunden: %s", ordner)
        return {'importiert': 0, 'fehler': 0, 'dateien': 0}

    archiv = pathlib.Path(einst.archiv_ordner) if einst.archiv_ordner else ordner / 'archiv'
    archiv.mkdir(parents=True, exist_ok=True)

    fehler_dir = pathlib.Path(einst.fehler_ordner) if getattr(einst, 'fehler_ordner', '') else None
    if fehler_dir:
        fehler_dir.mkdir(parents=True, exist_ok=True)

    dateien = sorted([p for p in ordner.iterdir() if p.is_file()])

    importiert = fehler = 0
    for datei in dateien:
        try:
            with open(datei, 'rb') as f:
                Dokument.objects.create(
                    datei=File(f, name=datei.name),
                    dateiname=datei.name,
                    kategorie='auto-import',
                    verknuepfung_typ='Objekt',
                    hochgeladen_von=system_user,
                )
            importiert += 1
            ziel = archiv / datei.name
            if ziel.exists():
                import time
                ziel = archiv / f'{datei.stem}_{int(time.time())}{datei.suffix}'
            datei.rename(ziel)
        except Exception as exc:
            logger.error("Dokumente-Import Fehler bei %s: %s", datei.name, exc)
            fehler += 1
            if fehler_dir and datei.exists():
                try:
                    datei.rename(fehler_dir / datei.name)
                except Exception:
                    pass

    return {'importiert': importiert, 'fehler': fehler, 'dateien': len(dateien)}


@shared_task(name='dokumente.ordner_scan')
def dokumente_ordner_scan(einstellung_id: str | None = None):
    """Wird von Celery Beat alle 5 Minuten oder manuell angestoßen."""
    from apps.buchhaltung.models import ImportOrdnerEinstellung

    if einstellung_id:
        qs = ImportOrdnerEinstellung.objects.filter(pk=einstellung_id, aktiv=True, bereich='dokumente')
    else:
        qs = ImportOrdnerEinstellung.objects.filter(aktiv=True, bereich='dokumente', import_ordner__gt='')

    gesamt = {'importiert': 0, 'fehler': 0, 'dateien': 0}
    for einst in qs:
        result = scan_dokumente_einstellung(einst)
        for k in gesamt:
            gesamt[k] += result.get(k, 0)

    logger.info("Dokumente-Scan abgeschlossen: %s", gesamt)
    return gesamt
