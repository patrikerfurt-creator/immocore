"""
Tagesordnungs-Service (Spec v1.1 Kap. 6) — Pflege der ``Tagesordnungspunkt``e
einer EV.

Fachliche Kernregel: nach dem Einladungsversand darf die Tagesordnung
inhaltlich nicht mehr verändert werden. Über einen Gegenstand, der nicht mit
der Einladung angekündigt war, kann kein wirksamer Beschluss gefasst werden
(§ 23 Abs. 2 WEG) — deshalb sperren ``top_anlegen``, ``top_loeschen`` und die
inhaltlichen Felder von ``top_aktualisieren`` ab
``status='einladungen_versendet'``. Rein erläuternde Felder bleiben offen.
"""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max

from apps.versammlung.models import Tagesordnungspunkt
from apps.versammlung.services import ev_service

# Felder, die nach dem Einladungsversand noch geändert werden dürfen.
_FELDER_NACH_VERSAND_ERLAUBT = {'erlaeuterung', 'ergebnis_bemerkung'}

# Alle über diesen Service pflegbaren Felder.
_PFLEGBARE_FELDER = {
    'titel', 'erlaeuterung', 'beschlussvorlage', 'abstimmungsmodus',
    'mehrheit_schwelle', 'triggert_vorgang', 'triggert_wirtschaftsplan',
    'ergebnis_bemerkung',
}


def _pruefe_aenderbar(ev, aktion: str) -> None:
    if ev.status in ev_service.STATI_NACH_VERSAND:
        raise ValidationError(
            f'{aktion} ist nach dem Einladungsversand nicht mehr möglich '
            f'(Status "{ev.get_status_display()}"). Über einen nicht '
            'angekündigten Gegenstand kann kein wirksamer Beschluss gefasst '
            'werden (§ 23 Abs. 2 WEG).'
        )


@transaction.atomic
def top_anlegen(*, ev, titel, erstellt_von, erlaeuterung='', beschlussvorlage='',
                abstimmungsmodus='einfache_mehrheit', mehrheit_schwelle=None,
                nummer=None, triggert_vorgang=False,
                triggert_wirtschaftsplan=False) -> Tagesordnungspunkt:
    """Legt einen TOP an.

    ``nummer=None`` hängt den Punkt hinten an. Wird eine Nummer übergeben, wird
    an dieser Position eingefügt und die Folgepunkte rücken auf — das Verschieben
    läuft absteigend, damit die Unique-Constraint (ev, nummer) nicht kurzzeitig
    verletzt wird.
    """
    _pruefe_aenderbar(ev, 'Das Anlegen eines TOP')

    if nummer is None:
        letzte = ev.tagesordnung.aggregate(m=Max('nummer'))['m'] or 0
        nummer = letzte + 1
    else:
        if nummer < 1:
            raise ValidationError({'nummer': 'TOP-Nummern beginnen bei 1.'})
        for bestehend in ev.tagesordnung.filter(nummer__gte=nummer).order_by('-nummer'):
            bestehend.nummer += 1
            bestehend.save(update_fields=['nummer'])

    top = Tagesordnungspunkt(
        ev=ev, nummer=nummer, titel=titel, erlaeuterung=erlaeuterung,
        beschlussvorlage=beschlussvorlage, abstimmungsmodus=abstimmungsmodus,
        mehrheit_schwelle=mehrheit_schwelle,
        triggert_vorgang=triggert_vorgang,
        triggert_wirtschaftsplan=triggert_wirtschaftsplan,
    )
    top.full_clean()
    top.save()
    ev_service.vermerke_ereignis(
        ev, 'top_angelegt', erstellt_von, top=top,
        text=f'TOP {top.nummer} angelegt: {top.titel}',
    )
    return top


@transaction.atomic
def top_aktualisieren(top, erstellt_von, **felder) -> Tagesordnungspunkt:
    """Ändert einzelne Felder eines TOP.

    Nach dem Einladungsversand sind nur noch ``erlaeuterung`` und
    ``ergebnis_bemerkung`` änderbar; Titel, Beschlussvorlage und
    Abstimmungsmodus sind dann festgeschrieben (§ 23 Abs. 2 WEG).
    Die Nummer wird hier nicht geändert — dafür gibt es ``neu_nummerieren``.
    """
    unbekannt = set(felder) - _PFLEGBARE_FELDER
    if unbekannt:
        raise ValidationError(
            'Nicht pflegbare Felder: ' + ', '.join(sorted(unbekannt))
        )

    nach_versand = top.ev.status in ev_service.STATI_NACH_VERSAND
    if nach_versand:
        gesperrt = set(felder) - _FELDER_NACH_VERSAND_ERLAUBT
        if gesperrt:
            raise ValidationError(
                'Nach dem Einladungsversand nicht mehr änderbar: '
                + ', '.join(sorted(gesperrt))
                + ' — die Tagesordnung ist mit der Einladung festgeschrieben '
                  '(§ 23 Abs. 2 WEG).'
            )

    geaendert = []
    beschreibung = []
    for feld, wert in felder.items():
        alt = getattr(top, feld)
        if alt == wert:
            continue
        setattr(top, feld, wert)
        geaendert.append(feld)
        beschreibung.append(f'{feld}: "{alt}" → "{wert}"')

    if not geaendert:
        return top

    top.full_clean()
    top.save(update_fields=geaendert)
    ev_service.vermerke_ereignis(
        top.ev, 'top_geaendert', erstellt_von, top=top,
        text=f'TOP {top.nummer} geändert — ' + '; '.join(beschreibung),
    )
    return top


@transaction.atomic
def top_loeschen(top, erstellt_von) -> None:
    """Löscht einen TOP und schließt die entstandene Nummernlücke."""
    ev = top.ev
    _pruefe_aenderbar(ev, 'Das Löschen eines TOP')

    nummer, titel = top.nummer, top.titel
    top.delete()
    neu_nummerieren(ev)
    ev_service.vermerke_ereignis(
        ev, 'top_geloescht', erstellt_von,
        text=f'TOP {nummer} gelöscht: {titel}',
    )


@transaction.atomic
def neu_nummerieren(ev) -> int:
    """Nummeriert die Tagesordnung lückenlos ab 1 neu (Reihenfolge bleibt).

    Zweistufig über negative Zwischenwerte, weil (ev, nummer) eindeutig ist und
    eine direkte Umnummerierung sonst mit sich selbst kollidieren würde.
    Rückgabe: Anzahl der Punkte.
    """
    punkte = list(ev.tagesordnung.order_by('nummer'))

    for index, top in enumerate(punkte, start=1):
        top.nummer = -index
        top.save(update_fields=['nummer'])

    for index, top in enumerate(punkte, start=1):
        top.nummer = index
        top.save(update_fields=['nummer'])

    return len(punkte)


def pruefe_vollstaendigkeit(ev) -> list[str]:
    """Prüft die Tagesordnung auf Lücken und liefert eine Liste von Klartext-
    Problemen (leere Liste = in Ordnung).

    Wird von ``ev_service.markiere_task_erledigt`` für Task 2 genutzt und kann
    im Frontend als Vorab-Prüfung angezeigt werden.
    """
    probleme = []
    punkte = list(ev.tagesordnung.order_by('nummer'))

    if not punkte:
        return ['Die Tagesordnung enthält keinen Punkt.']

    nummern = [top.nummer for top in punkte]
    if nummern != list(range(1, len(punkte) + 1)):
        probleme.append(
            'Die TOP-Nummerierung ist nicht lückenlos ab 1 '
            f'(gefunden: {nummern}).'
        )

    for top in punkte:
        if top.abstimmungsmodus != 'kein_beschluss' and not top.beschlussvorlage.strip():
            probleme.append(f'TOP {top.nummer} hat keine Beschlussvorlage.')
        if top.abstimmungsmodus == 'qualifizierte_mehrheit' and not top.mehrheit_schwelle:
            probleme.append(f'TOP {top.nummer} hat keine Mehrheitsschwelle.')

    return probleme
