"""
Checkout-Service (Spec v1.1 Kap. 4) — ersetzt Task 4 (Durchführung) und
Task 5 (Beschlussfassung) als manuelle Immocore-Arbeitsschritte.

Vier Schritte, die zusammen den "Notfallpfad"-losen Übergabeweg an das
externe Abstimmtool (Reply-Interact-Keypads) bilden — siehe
``API_VERTRAG_VERSAMMLUNGSTOOL_v1_1.md`` Abschnitt 2 für den Gesamtablauf:

1. ``checkout``              — sperrt TOPs/Teilnehmerliste/Stimmgrundlagen,
                                Status → ``ausgecheckt``.
2. ``checkout_zuruecknehmen`` — Korrekturweg zurück auf
                                ``einladungen_versendet``.
3. ``abschluss``              — Schritt 1/2 der Rückgabe: vergibt
                                Beschlussnummern (ruft
                                ``beschluss_service.uebernimm_in_sammlung``).
4. ``protokoll_upload``       — Schritt 2/2: nimmt das vom Tool erzeugte,
                                fertige Protokoll-PDF entgegen, Status →
                                ``beschluesse_verarbeitet``.
"""
import hashlib

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.dokumente.models import Dokument
from apps.versammlung.services import (
    beschluss_service, ev_service, tagesordnung_service,
)

# Größenlimit für das vom Abstimmtool hochgeladene Protokoll-PDF (Spec v1.1
# Kap. 4D: "Größenlimit z.B. 20MB").
MAX_PROTOKOLL_BYTES = 20 * 1024 * 1024


@transaction.atomic
def checkout(ev, erstellt_von):
    """Checkout: sperrt Tagesordnung/Teilnehmerliste/Stimmgrundlagen, Status
    → ``ausgecheckt``. Voraussetzung: Tagesordnung vollständig UND jeder
    abstimmungspflichtige TOP hat eine Stimmgrundlage.
    """
    probleme = tagesordnung_service.pruefe_vollstaendigkeit(ev)
    if probleme:
        raise ValidationError(
            'Checkout nicht möglich — die Tagesordnung ist nicht '
            'vollständig: ' + ' '.join(probleme)
        )

    ohne_grundlage = list(
        ev.tagesordnung
        .exclude(abstimmungsmodus='kein_beschluss')
        .filter(stimmgrundlage__isnull=True)
        .select_related('eltern')
    )
    if ohne_grundlage:
        raise ValidationError(
            'Checkout nicht möglich — folgenden TOP fehlt eine Stimmgrundlage: '
            + ', '.join(f'TOP {t.nummer_anzeige}' for t in ohne_grundlage)
        )

    # Ohne ermittelte Teilnehmer gäbe es vor Ort niemanden abzustimmen — und das
    # externe Abstimmtool bekäme eine leere Eigentümerliste. Die Ermittlung
    # (stimmkraft_service.ermittle_teilnehmer) gehört vor den Checkout.
    if not ev.teilnehmer.exists():
        raise ValidationError(
            'Checkout nicht möglich — es sind keine Teilnehmer ermittelt. '
            'Bitte zuerst die Teilnehmer und Stimmkraft ermitteln.'
        )

    # Analog zum früheren, inzwischen entfernten Task4/5-Ablauf
    # (durchfuehrung_service.schliesse_durchfuehrung_ab): der erste
    # Statuswechsel weg von 'entwurf' darf auch hier automatisch passieren —
    # eine Versammlung, deren Terminierung/Tagesordnung nie einzeln als
    # "erledigt" markiert wurde, soll trotzdem ausgecheckt werden können.
    if ev.status == 'entwurf':
        ev_service.wechsle_status(
            ev, 'in_bearbeitung', erstellt_von,
            text='Automatisch vor dem Checkout.',
        )

    ev_service.wechsle_status(
        ev, 'ausgecheckt', erstellt_von,
        text='Checkout — Übergabe an das externe Abstimmtool.',
    )
    ev_service.vermerke_ereignis(
        ev, 'checkout', erstellt_von,
        text='Tagesordnung, Teilnehmerliste und Stimmgrundlagen sind gesperrt.',
    )
    ev_service.markiere_task_erledigt(ev, 4, erstellt_von)
    return ev


@transaction.atomic
def checkout_zuruecknehmen(ev, erstellt_von, grund: str):
    """Nimmt den Checkout zurück (Status → ``einladungen_versendet``).

    ``grund`` ist Pflicht, analog ``ev_service.setze_task_zurueck`` — eine
    Rücknahme nach dem Checkout ist ein erklärungsbedürftiger Eingriff
    (verschobener Termin, falsche Stimmgrundlage, verworfene Tool-Daten).
    """
    if not (grund or '').strip():
        raise ValidationError('Für die Checkout-Rücknahme ist ein Grund anzugeben.')

    ev_service.wechsle_status(
        ev, 'einladungen_versendet', erstellt_von,
        text=f'Checkout zurückgenommen: {grund.strip()}',
    )
    ev_service.setze_task_zurueck(ev, 4, erstellt_von, grund)
    ev_service.vermerke_ereignis(
        ev, 'checkout_zurueckgenommen', erstellt_von,
        text=grund.strip(),
    )
    return ev


@transaction.atomic
def abschluss(ev, erstellt_von) -> dict:
    """Schritt 1/2 der Rückgabe (API-Vertrag v1.4 Abschnitt 4.6).

    Ruft ``beschluss_service.uebernimm_in_sammlung`` (bestehende Logik, nicht
    dupliziert) auf und liefert die vergebenen Beschlussnummern je TOP.

    v1.4: Ein beschlusspflichtiger TOP OHNE Abstimmungsergebnis blockiert den
    Abschluss NICHT mehr (früher HTTP 400). Er gilt als "kein Beschluss
    gefasst" (z.B. vertagt oder zurückgezogen): er bekommt keine
    Beschlussnummer und wird im Ereignis-Log vermerkt
    (``abschluss_top_ohne_beschluss``), damit eine versehentlich ausgelassene
    Abstimmung nachvollziehbar bleibt. Das einzige verbleibende 400 ist das
    Status-Gate (Status != ausgecheckt). Hintergrund: Das Tool kann einen TOP
    bewusst ohne Abstimmung lassen; dieses "ohne Abstimmung" wird nicht an
    immocore übertragen, daher darf das Fehlen eines Ergebnisses den Abschluss
    nicht verhindern.
    """
    if ev.status != 'ausgecheckt':
        raise ValidationError(
            f'Abschluss ist nur im Status "ausgecheckt" möglich (aktuell '
            f'"{ev.get_status_display()}").'
        )

    # v1.4: beschlusspflichtige TOPs ohne Ergebnis blockieren nicht mehr — sie
    # gelten als "kein Beschluss gefasst" und werden nur im Ereignis-Log
    # vermerkt (Gegenkontrolle gegen eine versehentlich vergessene Abstimmung).
    for top in (ev.tagesordnung
                .exclude(abstimmungsmodus='kein_beschluss')
                .filter(abstimmungsergebnis='offen')
                .select_related('eltern')):
        ev_service.vermerke_ereignis(
            ev, 'abschluss_top_ohne_beschluss', erstellt_von, top=top,
            text=(f'TOP {top.nummer_anzeige}: kein Beschluss gefasst — '
                  'kein Abstimmungsergebnis beim Abschluss (keine '
                  'Beschlussnummer vergeben).'),
        )

    beschluss_service.uebernimm_in_sammlung(ev, erstellt_von)

    beschluesse = [
        {
            'top_id': str(beschluss.top_id),
            'beschluss_nummer': beschluss.nummer,
            'wortlaut': beschluss.wortlaut,
        }
        for beschluss in ev.beschluesse.filter(top__isnull=False).order_by('nummer')
    ]
    return {'beschluesse': beschluesse}


def _lies_und_validiere_pdf(datei) -> bytes:
    """Magic-Bytes- und Größenprüfung (Spec v1.1 Kap. 4D).

    ``Dokument.save()`` schützt nur vor nachträglichem Austausch, sobald
    ``revisionssicher=True`` gesetzt ist — die Prüfung beim Upload selbst ist
    zusätzlich nötig (genau diese Lücke benennt die Spec).
    """
    datei.seek(0)
    inhalt = datei.read()
    if len(inhalt) > MAX_PROTOKOLL_BYTES:
        raise ValidationError(
            f'Die Datei ist zu groß (> {MAX_PROTOKOLL_BYTES // (1024 * 1024)} MB).'
        )
    if not inhalt[:5].startswith(b'%PDF'):
        raise ValidationError(
            'Die hochgeladene Datei ist kein gültiges PDF (Magic-Bytes '
            '"%PDF" fehlen am Dateianfang).'
        )
    return inhalt


@transaction.atomic
def protokoll_upload(ev, erstellt_von, datei) -> Dokument:
    """Schritt 2/2 der Rückgabe (API-Vertrag v1.1 Abschnitt 3.8).

    Nimmt das vom Abstimmtool erzeugte, fertige Protokoll-PDF entgegen. Legt
    es als revisionssicheres DMS-Dokument ab (``dokument_typ='korrespondenz'``,
    NICHT ``'beschluss'``, das bleibt den Einzel-Beschluss-PDFs vorbehalten).
    Setzt ``ev.protokoll_pdf``, Status → ``beschluesse_verarbeitet``.
    """
    if ev.status != 'ausgecheckt':
        raise ValidationError(
            f'Protokoll-Upload ist nur im Status "ausgecheckt" möglich '
            f'(aktuell "{ev.get_status_display()}").'
        )
    if not ev.abschluss_erledigt_am:
        raise ValidationError(
            'Protokoll-Upload ist erst nach dem Abschluss möglich — bitte '
            'zuerst POST .../abschluss/ aufrufen (die Beschlussnummern müssen '
            'im PDF bereits enthalten sein).'
        )

    inhalt = _lies_und_validiere_pdf(datei)
    pruefsumme = hashlib.sha256(inhalt).hexdigest()
    datum = timezone.localtime(ev.termin).date() if ev.termin else timezone.localdate()
    dateiname = f'Protokoll_EV_Tool_{datum:%Y-%m-%d}.pdf'

    dokument = Dokument.objects.create(
        datei=ContentFile(inhalt, name=dateiname),
        dateiname=dateiname,
        kategorie='EV-Protokoll',
        dokument_typ='korrespondenz',
        beschreibung=(
            f'Protokoll der Eigentümerversammlung vom {datum:%d.%m.%Y} — '
            f'{ev.objekt.bezeichnung} (vom externen Abstimmtool erzeugt und '
            'hochgeladen).'
        ),
        objekt=ev.objekt,
        hochgeladen_von=erstellt_von,
        sha256=pruefsumme,
        revisionssicher=True,
        revisionssicher_seit=timezone.now(),
    )

    ev.protokoll_pdf = dokument
    ev.save(update_fields=['protokoll_pdf'])
    ev_service.wechsle_status(
        ev, 'beschluesse_verarbeitet', erstellt_von,
        text='Protokoll-Upload durch das externe Abstimmtool.',
    )
    ev_service.vermerke_ereignis(
        ev, 'protokoll_hochgeladen', erstellt_von,
        text=f'Protokoll vom Abstimmtool hochgeladen: {dateiname} (sha256 {pruefsumme}).',
        neuer_wert=dateiname,
    )
    return dokument
