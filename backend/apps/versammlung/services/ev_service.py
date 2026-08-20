"""
EV-Service (Spec v1.1 Kap. 6) — Anlage, Terminierung, Task-Fortschritt und
Statuswechsel einer ``Eigentuemerversammlung``.

Statuswechsel laufen AUSSCHLIESSLICH über ``wechsle_status`` und Task-Flags
ausschließlich über ``markiere_task_erledigt``/``setze_task_zurueck`` — nie
durch direktes Setzen der Felder. Nur so ist garantiert, dass jede Änderung
einen Audit-Eintrag (``EVEreignis``) hinterlässt; Beschlüsse sind binnen eines
Monats anfechtbar (§ 45 WEG), da darf nichts still passieren.
"""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.versammlung.models import EVEreignis, Eigentuemerversammlung

# Erlaubte Statusübergänge (Spec v1.1 Kap. 4.1). 'archiviert' ist terminal.
_ERLAUBTE_UEBERGAENGE = {
    'entwurf':                 {'in_bearbeitung', 'archiviert'},
    # 'in_bearbeitung' → 'durchgefuehrt' ist bewusst erlaubt: eine Versammlung
    # kann stattfinden, ohne dass der Versand über IMMOCORE dokumentiert wurde
    # (Ladung außerhalb des Systems, Vollversammlung mit allen Eigentümern).
    # Der Umweg über 'einladungen_versendet' würde die EV sonst fälschlich als
    # versendet ausweisen.
    'in_bearbeitung':          {'einladungen_versendet', 'durchgefuehrt', 'archiviert'},
    'einladungen_versendet':   {'durchgefuehrt', 'archiviert'},
    'durchgefuehrt':           {'beschluesse_verarbeitet', 'archiviert'},
    'beschluesse_verarbeitet': {'archiviert'},
    'archiviert':              set(),
}

# Ab diesem Status ist die Einladung heraus — inhaltliche Änderungen an der
# Tagesordnung sind dann nicht mehr zulässig (§ 23 Abs. 2 WEG, siehe
# tagesordnung_service).
STATI_NACH_VERSAND = {'einladungen_versendet', 'durchgefuehrt',
                      'beschluesse_verarbeitet', 'archiviert'}

_TASK_FELDER = {
    1: ('task1_terminierung_erledigt',     'Terminierung'),
    2: ('task2_tagesordnung_erledigt',     'Tagesordnung'),
    3: ('task3_einladung_erledigt',        'Einladung'),
    4: ('task4_durchfuehrung_erledigt',    'Durchführung'),
    5: ('task5_beschlussfassung_erledigt', 'Beschlussfassung'),
}

EINLADUNGSTEXT_VORLAGE = (
    'Sehr geehrte Damen und Herren,\n\n'
    'hiermit laden wir Sie zur Eigentümerversammlung der oben genannten '
    'Wohnungseigentümergemeinschaft ein.\n\n'
    'Die Tagesordnung mit den Beschlussvorlagen finden Sie auf den folgenden '
    'Seiten. Sollten Sie nicht persönlich teilnehmen können, haben Sie die '
    'Möglichkeit, sich vertreten zu lassen; bitte legen Sie in diesem Fall '
    'eine schriftliche Vollmacht vor.\n\n'
    'Mit freundlichen Grüßen\n'
    'Ihre Hausverwaltung'
)


def vermerke_ereignis(ev, typ, erstellt_von=None, *, text='', alter_wert='',
                      neuer_wert='', top=None) -> EVEreignis:
    """Schreibt einen Audit-Eintrag zur EV.

    ``erstellt_von=None`` bedeutet ausdrücklich "systemgeneriert" (Celery) und
    ist kein Fehler.
    """
    return EVEreignis.objects.create(
        ev=ev, top=top, typ=typ, text=text,
        alter_wert=str(alter_wert or ''), neuer_wert=str(neuer_wert or ''),
        erstellt_von=erstellt_von,
    )


@transaction.atomic
def erstelle_ev(*, objekt, erstellt_von, arbeitsname='', art='ordentlich',
                stimmprinzip='kopf', stimm_verteilerschluessel=None,
                stimm_wirtschaftsjahr=0,
                einladungstext=None) -> Eigentuemerversammlung:
    """Legt einen neuen EV-Prozess an (Status ``entwurf``, alle Tasks offen).

    ``einladungstext`` wird mit ``EINLADUNGSTEXT_VORLAGE`` vorbelegt, damit
    Task 3 nicht auf einem leeren Feld startet; der Text ist danach frei
    editierbar.
    """
    ev = Eigentuemerversammlung(
        objekt=objekt,
        arbeitsname=arbeitsname,
        art=art,
        stimmprinzip=stimmprinzip,
        stimm_verteilerschluessel=stimm_verteilerschluessel,
        stimm_wirtschaftsjahr=stimm_wirtschaftsjahr,
        einladungstext=EINLADUNGSTEXT_VORLAGE if einladungstext is None else einladungstext,
        erstellt_von=erstellt_von,
    )
    ev.full_clean()
    ev.save()
    vermerke_ereignis(
        ev, 'erstellt', erstellt_von,
        text=f'EV angelegt (Stimmprinzip: {ev.get_stimmprinzip_display()}).',
    )
    return ev


@transaction.atomic
def aktualisiere_terminierung(ev, erstellt_von, *, termin=None, ort=None,
                              raum_buchung_notizen=None,
                              terminvorschlaege=None) -> Eigentuemerversammlung:
    """Aktualisiert die Terminierungsdaten (Task 1).

    Nur übergebene Felder werden geändert (``None`` = unverändert). Jede
    Änderung an Termin oder Ort wird protokolliert — das ist bei einer
    Ladungsfrist-Diskussion der entscheidende Nachweis.
    """
    alter_termin, alter_ort = ev.termin, ev.ort
    felder = []

    if termin is not None:
        ev.termin = termin
        felder.append('termin')
    if ort is not None:
        ev.ort = ort
        felder.append('ort')
    if raum_buchung_notizen is not None:
        ev.raum_buchung_notizen = raum_buchung_notizen
        felder.append('raum_buchung_notizen')
    if terminvorschlaege is not None:
        ev.terminvorschlaege = terminvorschlaege
        felder.append('terminvorschlaege')

    if not felder:
        return ev

    ev.full_clean()
    ev.save(update_fields=felder)

    if 'termin' in felder or 'ort' in felder:
        vermerke_ereignis(
            ev, 'termin_geaendert', erstellt_von,
            alter_wert=f'{alter_termin or "-"} / {alter_ort or "-"}',
            neuer_wert=f'{ev.termin or "-"} / {ev.ort or "-"}',
        )
    return ev


def _task_feld(task_nr: int) -> tuple[str, str]:
    if task_nr not in _TASK_FELDER:
        raise ValidationError(f'Unbekannte Task-Nummer: {task_nr} (erlaubt: 1–5).')
    return _TASK_FELDER[task_nr]


def _pruefe_task_voraussetzungen(ev, task_nr: int) -> None:
    """Prüft, ob die Daten des Tasks selbst vorliegen.

    Bewusst KEINE Reihenfolge-Prüfung — die Tasks dürfen in beliebiger Folge
    abgearbeitet werden (Spec v1.1 Kap. 4.1). Geprüft wird nur, ob der Task
    inhaltlich überhaupt erledigt sein kann: eine "erledigte" Terminierung
    ohne Termin wäre eine falsche Fortschrittsanzeige.
    """
    if task_nr == 1:
        fehlend = []
        if not ev.termin:
            fehlend.append('Termin')
        if not ev.ort.strip():
            fehlend.append('Ort')
        if fehlend:
            raise ValidationError(
                'Task 1 (Terminierung) kann nicht erledigt werden — es fehlt: '
                + ', '.join(fehlend) + '.'
            )
    elif task_nr == 2:
        # Import lokal: tagesordnung_service importiert seinerseits nichts aus
        # diesem Modul, der lokale Import hält die Abhängigkeit trotzdem
        # eindeutig gerichtet.
        from apps.versammlung.services import tagesordnung_service

        probleme = tagesordnung_service.pruefe_vollstaendigkeit(ev)
        if probleme:
            raise ValidationError(
                'Task 2 (Tagesordnung) kann nicht erledigt werden: '
                + ' '.join(probleme)
            )


@transaction.atomic
def markiere_task_erledigt(ev, task_nr: int, erstellt_von) -> Eigentuemerversammlung:
    """Markiert Task ``task_nr`` (1–5) als erledigt.

    Der erste erledigte Task hebt den Status von ``entwurf`` auf
    ``in_bearbeitung``. Weitergehende Statuswechsel gehören zu den Fachschritten
    (Versand in Phase B, Durchführung/Beschlussfassung in Phase D) und passieren
    hier absichtlich nicht.
    """
    feld, label = _task_feld(task_nr)
    if getattr(ev, feld):
        return ev

    _pruefe_task_voraussetzungen(ev, task_nr)

    setattr(ev, feld, True)
    ev.save(update_fields=[feld])
    vermerke_ereignis(
        ev, 'task_erledigt', erstellt_von,
        text=f'Task {task_nr} ({label}) als erledigt markiert.',
        alter_wert='offen', neuer_wert='erledigt',
    )

    if ev.status == 'entwurf':
        wechsle_status(ev, 'in_bearbeitung', erstellt_von,
                       text='Automatisch mit dem ersten erledigten Task.')
    return ev


@transaction.atomic
def setze_task_zurueck(ev, task_nr: int, erstellt_von, grund: str) -> Eigentuemerversammlung:
    """Setzt einen erledigten Task wieder auf offen.

    ``grund`` ist Pflicht: eine Rücksetzung nach dem Einladungsversand ist ein
    erklärungsbedürftiger Eingriff und muss im Verlauf lesbar begründet sein.
    """
    if not (grund or '').strip():
        raise ValidationError('Für die Rücksetzung eines Tasks ist ein Grund anzugeben.')

    feld, label = _task_feld(task_nr)
    if not getattr(ev, feld):
        return ev

    setattr(ev, feld, False)
    ev.save(update_fields=[feld])
    vermerke_ereignis(
        ev, 'task_zurueckgesetzt', erstellt_von,
        text=f'Task {task_nr} ({label}) zurückgesetzt: {grund.strip()}',
        alter_wert='erledigt', neuer_wert='offen',
    )
    return ev


def task_status(ev) -> dict:
    """Fortschritt aller fünf Tasks als Dict.

    Rückgabe: ``{'task1': {'erledigt': bool, 'bezeichnung': str}, …,
    'anzahl_erledigt': int}``.
    """
    ergebnis = {}
    anzahl = 0
    for nr, (feld, label) in _TASK_FELDER.items():
        erledigt = bool(getattr(ev, feld))
        anzahl += 1 if erledigt else 0
        ergebnis[f'task{nr}'] = {'erledigt': erledigt, 'bezeichnung': label}
    ergebnis['anzahl_erledigt'] = anzahl
    return ergebnis


@transaction.atomic
def wechsle_status(ev, neuer_status: str, erstellt_von, *, text='') -> Eigentuemerversammlung:
    """Einziger erlaubter Weg, ``Eigentuemerversammlung.status`` zu ändern.

    Setzt zusätzlich die zum Status gehörenden Zeitstempel
    (``einladung_versendet_am``, ``durchgefuehrt_am``), damit Status und
    Zeitpunkt nicht auseinanderlaufen können.
    """
    if neuer_status not in dict(Eigentuemerversammlung.STATUS_CHOICES):
        raise ValidationError(f'Unbekannter Status: {neuer_status}')

    alter_status = ev.status
    if neuer_status == alter_status:
        return ev

    erlaubt = _ERLAUBTE_UEBERGAENGE.get(alter_status, set())
    if neuer_status not in erlaubt:
        raise ValidationError(
            f'Statuswechsel "{alter_status}" → "{neuer_status}" ist nicht '
            f'vorgesehen (erlaubt: {", ".join(sorted(erlaubt)) or "keiner"}).'
        )

    felder = ['status']
    ev.status = neuer_status
    if neuer_status == 'einladungen_versendet' and not ev.einladung_versendet_am:
        ev.einladung_versendet_am = timezone.now()
        felder.append('einladung_versendet_am')
    if neuer_status == 'durchgefuehrt' and not ev.durchgefuehrt_am:
        ev.durchgefuehrt_am = timezone.now()
        felder.append('durchgefuehrt_am')

    ev.save(update_fields=felder)
    vermerke_ereignis(
        ev, 'statuswechsel', erstellt_von, text=text,
        alter_wert=alter_status, neuer_wert=neuer_status,
    )
    return ev
