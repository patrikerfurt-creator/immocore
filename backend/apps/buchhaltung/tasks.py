import pathlib
import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


def scan_camt_einstellung(einst) -> dict:
    """
    Scannt den Import-Ordner einer CamtImportEinstellung, importiert alle
    passenden XML-Dateien und verschiebt sie danach ins Archiv (oder Fehler-Ordner).
    Gibt ein Dict mit Zählern zurück.
    """
    from .models import Kontoumsatz, CamtImportLog
    from .services.camt053 import parse_camt053
    from .services.buchungserkennung import erkenne_buchung
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

                ku = Kontoumsatz.objects.create(
                    objekt=bankkonto.objekt if bankkonto else None,
                    bankkonto=bankkonto,
                    sha256_hash=txn['sha256_hash'],
                    betrag=txn['betrag'],
                    buchungsdatum=txn['buchungsdatum'],
                    wertstellungsdatum=txn.get('wertstellungsdatum'),
                    auftraggeber_name=txn.get('auftraggeber_name', ''),
                    auftraggeber_iban=txn.get('auftraggeber_iban', ''),
                    empfaenger_iban=empfaenger_iban,
                    verwendungszweck=txn.get('verwendungszweck', ''),
                    import_datei=datei.name,
                )

                vorschlag = erkenne_buchung(ku)
                if vorschlag:
                    ku.ki_vorschlag = vorschlag
                    ku.status = 'erkannt'
                    ku.save(update_fields=['ki_vorschlag', 'status'])
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


@shared_task(name='buchhaltung.erzeuge_faellige_wkz_ops')
def erzeuge_faellige_wkz_ops_task():
    """
    Täglich um 03:00 per Celery Beat: Erzeugt alle fälligen WKZ-OPs
    für alle aktiven Vorlagen mit Fälligkeit im Vorlauf-Fenster.
    """
    from .services.wkz.op_generator_service import erzeuge_faellige_ops
    ergebnis = erzeuge_faellige_ops(stichtag=timezone.now().date())
    logger.info(
        "WKZ-OP-Task abgeschlossen: %s erzeugt, %s Fehler",
        ergebnis.erzeugt, len(ergebnis.fehler),
    )
    return {
        'erzeugt': ergebnis.erzeugt,
        'fehler': ergebnis.fehler,
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
