import pathlib
import logging
import traceback
from datetime import date
from celery import shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Auto-Pipeline Hausgeld-Sollstellung & SEPA-Lastschrift
# ---------------------------------------------------------------------------

@shared_task(name='buchhaltung.auto_hausgeld_pipeline', bind=True, max_retries=0)
def task_auto_hausgeld_pipeline(self):
    """
    Täglich 02:00 Uhr. Prüft, ob heute der konfigurierte Stichtag im Monat
    ist. Wenn ja: Hausgeld-Sollstellungen + SEPA-Lastschriften für alle
    Objekte mit auto_pipeline_aktiv=True erzeugen.
    """
    if not getattr(settings, 'SEPA_AUTOPILOT_AKTIV', True):
        logger.info('Auto-Pipeline deaktiviert (SEPA_AUTOPILOT_AKTIV=false).')
        return

    heute = timezone.localdate()
    if not _ist_stichtag_oder_nachholtag(heute):
        return

    periode = _naechste_periode(heute)

    from apps.objekte.models import Objekt
    from apps.buchhaltung.models import AutoLaufProtokoll
    from apps.buchhaltung.services.auto_pipeline_service import run_objekt
    from django.contrib.auth import get_user_model

    User = get_user_model()
    try:
        autopilot_user = User.objects.get(username='immocore-autopilot')
    except User.DoesNotExist:
        logger.error('System-User "immocore-autopilot" nicht gefunden — Migration ausführen!')
        return

    objekte = Objekt.objects.filter(auto_pipeline_aktiv=True, status='aktiv')
    logger.info('Auto-Pipeline gestartet: %d Objekte, Periode %s', objekte.count(), periode)

    for objekt in objekte:
        try:
            run_objekt(objekt=objekt, periode=periode, user=autopilot_user)
        except Exception:
            logger.exception('Auto-Pipeline %s fehlgeschlagen', objekt.objektnummer)
            AutoLaufProtokoll.objects.create(
                objekt=objekt,
                ausgefuehrt_am=timezone.now(),
                periode=periode,
                status='fehler',
                fehler=traceback.format_exc(),
            )


@shared_task(name='buchhaltung.archiviere_alte_pain_dateien')
def task_archiviere_alte_pain_dateien():
    """
    Verschiebt pain.008-Dateien älter als 90 Tage aus SEPA_OUTPUT_DIR
    nach SEPA_OUTPUT_ARCHIVE_DIR. Wöchentlich montags 03:00 Uhr.
    """
    import shutil
    from datetime import timedelta
    from pathlib import Path

    output_dir = Path(getattr(settings, 'SEPA_OUTPUT_DIR', ''))
    archive_dir = Path(getattr(settings, 'SEPA_OUTPUT_ARCHIVE_DIR', ''))
    grenze = timezone.localdate() - timedelta(days=90)

    if not output_dir.is_dir():
        return

    archive_dir.mkdir(parents=True, exist_ok=True)
    verschoben = 0

    for datei in output_dir.glob('*.xml'):
        try:
            aenderungsdatum = date.fromtimestamp(datei.stat().st_mtime)
            if aenderungsdatum < grenze:
                shutil.move(str(datei), str(archive_dir / datei.name))
                verschoben += 1
        except OSError as exc:
            logger.warning('Archivierung fehlgeschlagen für %s: %s', datei, exc)

    logger.info('Archivierung abgeschlossen: %d Dateien verschoben.', verschoben)


def _ist_stichtag_oder_nachholtag(heute: date) -> bool:
    """
    True wenn heute der konfigurierte Stichtag ist, oder wenn der Stichtag
    erst kürzlich verpasst wurde und noch kein Lauf für diese Periode existiert.
    """
    from apps.buchhaltung.models import AutoLaufProtokoll

    stichtag = getattr(settings, 'SEPA_AUTOPILOT_STICHTAG', 25)
    if heute.day == stichtag:
        return True

    # Nachholtag: bis zu 5 Tage nach dem Stichtag, wenn noch kein Lauf
    if stichtag < heute.day <= stichtag + 5:
        periode = _naechste_periode(heute)
        bereits_gelaufen = AutoLaufProtokoll.objects.filter(
            periode=periode,
            status__in=['erfolg', 'teilweise_erfolg', 'uebersprungen'],
        ).exists()
        return not bereits_gelaufen

    return False


def _naechste_periode(heute: date) -> date:
    """Erster Tag des Folgemonats (= Sollstellungs-Periode)."""
    if heute.month == 12:
        return date(heute.year + 1, 1, 1)
    return date(heute.year, heute.month + 1, 1)


def scan_camt_einstellung(einst) -> dict:
    """
    Scannt den Import-Ordner einer CamtImportEinstellung, importiert alle
    passenden XML-Dateien und verschiebt sie danach ins Archiv (oder Fehler-Ordner).
    Gibt ein Dict mit Zählern zurück.
    """
    from .models import Kontoumsatz, CamtImportLog
    from .services.camt053 import parse_camt053
    from .services.ebanking_erkennungs_service import fuehre_erkennung_aus
    from apps.objekte.models import Bankkonto

    ordner = pathlib.Path(einst.import_ordner)
    if not ordner.is_dir():
        logger.warning("CAMT-Import: Ordner nicht gefunden: %s", ordner)
        CamtImportLog.objects.create(
            einstellung=einst,
            import_ordner=str(ordner),
            fehler_details=[{'datei': '—', 'meldung': f'Ordner nicht gefunden: {ordner}'}],
            anzahl_fehler=1,
        )
        return {'importiert': 0, 'duplikate': 0, 'erkannt': 0, 'fehler': 1, 'dateien': 0}

    archiv = pathlib.Path(einst.archiv_ordner) if einst.archiv_ordner else None
    fehler_dir = pathlib.Path(einst.fehler_ordner) if einst.fehler_ordner else None

    if archiv:
        archiv.mkdir(parents=True, exist_ok=True)
    if fehler_dir:
        fehler_dir.mkdir(parents=True, exist_ok=True)

    muster_liste = [m.strip() for m in (einst.datei_muster or '*.xml').split(',')]
    dateien = []
    for muster in muster_liste:
        dateien.extend(ordner.glob(muster))
    dateien = sorted(dateien)

    importiert = duplikate = erkannt = fehler_count = 0
    letzte_datei = ''
    fehler_details = []

    for datei in dateien:
        try:
            xml_bytes = datei.read_bytes()
            transaktionen = parse_camt053(xml_bytes)

            for txn in transaktionen:
                if Kontoumsatz.objects.filter(sha256_hash=txn['sha256_hash']).exists():
                    duplikate += 1
                    continue

                empfaenger_iban = txn.get('empfaenger_iban', '')
                bankkonto = None
                if empfaenger_iban:
                    bankkonto = Bankkonto.objects.select_related('objekt').filter(
                        iban=empfaenger_iban
                    ).first()

                objekt = bankkonto.objekt if bankkonto else getattr(einst, 'objekt', None)

                ku = Kontoumsatz.objects.create(
                    objekt=objekt,
                    bankkonto=bankkonto,
                    sha256_hash=txn['sha256_hash'],
                    betrag=txn['betrag'],
                    buchungsdatum=txn['buchungsdatum'],
                    wertstellungsdatum=txn.get('wertstellungsdatum'),
                    auftraggeber_name=txn.get('auftraggeber_name', ''),
                    auftraggeber_iban=txn.get('auftraggeber_iban', ''),
                    empfaenger_iban=empfaenger_iban,
                    verwendungszweck=txn.get('verwendungszweck', ''),
                    end_to_end_id=txn.get('end_to_end_id', ''),
                    import_datei=datei.name,
                    status='unbekannt' if objekt is None else 'importiert',
                )

                if objekt is not None:
                    try:
                        fuehre_erkennung_aus(ku)
                    except Exception as exc:
                        logger.error("E-Banking Erkennung Fehler: %s", exc)
                    if ku.status not in ('importiert', 'unbekannt'):
                        erkannt += 1

                importiert += 1

            letzte_datei = datei.name
            if archiv:
                datei.rename(archiv / datei.name)

        except Exception as exc:
            logger.error("CAMT-Import Fehler bei %s: %s", datei.name, exc)
            fehler_details.append({'datei': datei.name, 'meldung': str(exc)})
            fehler_count += 1
            if fehler_dir:
                try:
                    datei.rename(fehler_dir / datei.name)
                except Exception:
                    pass

    einst.letzter_import_am = timezone.now()
    if letzte_datei:
        einst.letzter_import_datei = letzte_datei
    einst.save(update_fields=['letzter_import_am', 'letzter_import_datei'])

    CamtImportLog.objects.create(
        einstellung=einst,
        import_ordner=str(ordner),
        anzahl_dateien=len(dateien),
        anzahl_importiert=importiert,
        anzahl_duplikate=duplikate,
        anzahl_erkannt=erkannt,
        anzahl_fehler=fehler_count,
        fehler_details=fehler_details,
    )

    return {
        'importiert': importiert,
        'duplikate': duplikate,
        'erkannt': erkannt,
        'fehler': fehler_count,
        'dateien': len(dateien),
    }


@shared_task(name='buchhaltung.camt_ordner_scan')
def camt_ordner_scan(einstellung_id: str | None = None):
    """Wird von Celery Beat alle 2 Stunden oder manuell angestoßen."""
    from .models import CamtImportEinstellung

    if einstellung_id:
        qs = CamtImportEinstellung.objects.filter(pk=einstellung_id, aktiv=True)
    else:
        qs = CamtImportEinstellung.objects.filter(aktiv=True, import_ordner__gt='')

    gesamt = {'importiert': 0, 'duplikate': 0, 'erkannt': 0, 'fehler': 0, 'dateien': 0}
    for einst in qs:
        result = scan_camt_einstellung(einst)
        for k in gesamt:
            gesamt[k] += result.get(k, 0)

    logger.info("CAMT-Scan abgeschlossen: %s", gesamt)
    return gesamt
