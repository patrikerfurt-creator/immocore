import pathlib
import logging
from celery import shared_task

logger = logging.getLogger(__name__)

ERLAUBTE_ENDUNGEN = {'.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.tif'}


def scan_rechnungen_einstellung(einst) -> dict:
    from apps.rechnungen.services.verarbeitung import verarbeite_datei

    ordner = pathlib.Path(einst.import_ordner)
    if not ordner.is_dir():
        logger.warning("Rechnungen-Import: Ordner nicht gefunden: %s", ordner)
        return {'importiert': 0, 'duplikate': 0, 'prueffaelle': 0, 'fehler': 0, 'dateien': 0}

    archiv = pathlib.Path(einst.archiv_ordner) if einst.archiv_ordner else ordner / 'archiv'
    archiv.mkdir(parents=True, exist_ok=True)

    fehler_dir = pathlib.Path(einst.fehler_ordner) if getattr(einst, 'fehler_ordner', '') else None
    if fehler_dir:
        fehler_dir.mkdir(parents=True, exist_ok=True)

    seen: set[str] = set()
    dateien: list[pathlib.Path] = []
    for ext in ERLAUBTE_ENDUNGEN:
        for p in ordner.glob(f'*{ext}'):
            if p.name.lower() not in seen:
                seen.add(p.name.lower())
                dateien.append(p)
        for p in ordner.glob(f'*{ext.upper()}'):
            if p.name.lower() not in seen:
                seen.add(p.name.lower())
                dateien.append(p)
    dateien = sorted(dateien)

    importiert = duplikate = prueffaelle = fehler = 0
    for datei in dateien:
        try:
            result = verarbeite_datei(str(datei), archiv)
            status = result['status']
            if status in ('importiert', 'erkannt'):
                importiert += 1
            elif status == 'duplikat':
                duplikate += 1
            elif status in ('prueffall', 'pruefung_match', 'nicht_erkannt'):
                prueffaelle += 1
        except Exception as exc:
            logger.error("Rechnungen-Import Fehler bei %s: %s", datei.name, exc)
            fehler += 1
            if fehler_dir and datei.exists():
                try:
                    datei.rename(fehler_dir / datei.name)
                except Exception:
                    pass

    return {
        'importiert': importiert,
        'duplikate': duplikate,
        'prueffaelle': prueffaelle,
        'fehler': fehler,
        'dateien': len(dateien),
    }


@shared_task(name='rechnungen.ordner_scan')
def rechnungen_ordner_scan(einstellung_id: str | None = None):
    """Wird von Celery Beat alle 5 Minuten oder manuell angestoßen."""
    from apps.buchhaltung.models import ImportOrdnerEinstellung

    if einstellung_id:
        qs = ImportOrdnerEinstellung.objects.filter(pk=einstellung_id, aktiv=True, bereich='rechnungen')
    else:
        qs = ImportOrdnerEinstellung.objects.filter(aktiv=True, bereich='rechnungen', import_ordner__gt='')

    gesamt = {'importiert': 0, 'duplikate': 0, 'prueffaelle': 0, 'fehler': 0, 'dateien': 0}
    for einst in qs:
        result = scan_rechnungen_einstellung(einst)
        for k in gesamt:
            gesamt[k] += result.get(k, 0)

    logger.info("Rechnungen-Scan abgeschlossen: %s", gesamt)
    return gesamt
