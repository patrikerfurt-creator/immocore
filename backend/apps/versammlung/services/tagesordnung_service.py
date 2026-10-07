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
from collections import defaultdict

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max

from apps.versammlung.models import Tagesordnungspunkt
from apps.versammlung.services import ev_service

# Felder, die nach dem Einladungsversand noch geändert werden dürfen.
_FELDER_NACH_VERSAND_ERLAUBT = {'erlaeuterung', 'ergebnis_bemerkung'}

# Alle über diesen Service pflegbaren Felder. 'stimmgrundlage' gehört dazu
# (Spec v1.1 Kap. 3) und ist NACH Einladungsversand gesperrt — die Einladung
# muss die Stimmgrundlage je TOP nennen, sie darf sich danach nicht mehr
# ändern (analog zur Sperre der übrigen inhaltlichen Felder).
_PFLEGBARE_FELDER = {
    'titel', 'erlaeuterung', 'beschlussvorlage', 'abstimmungsmodus',
    'mehrheit_schwelle', 'triggert_vorgang', 'triggert_wirtschaftsplan',
    'ergebnis_bemerkung', 'stimmgrundlage',
}


def _vorbelegte_stimmgrundlage(ev, eltern, nummer: int):
    """Vorbelegung für einen neuen TOP (Spec v1.1 Kap. 3).

    Vorrang hat der vorherige Punkt DERSELBEN Ebene (gleicher ``eltern``, nach
    ``nummer``). Hat ein neuer Unterpunkt keinen Vorgänger in seiner Ebene,
    erbt er die Stimmgrundlage des übergeordneten TOP. Sonst greift die als
    ``ist_standard=True`` markierte Stimmgrundlage der EV. Liefert ``None``,
    wenn die EV (noch) keine Stimmgrundlage hat — nur bei Alt-/Testdaten.
    """
    vorheriger = (
        ev.tagesordnung.filter(eltern=eltern, nummer__lt=nummer)
        .order_by('-nummer').first()
    )
    if vorheriger is not None and vorheriger.stimmgrundlage_id:
        return vorheriger.stimmgrundlage
    if eltern is not None and eltern.stimmgrundlage_id:
        return eltern.stimmgrundlage
    return ev.stimmgrundlagen.filter(ist_standard=True).first()


def _pruefe_aenderbar(ev, aktion: str) -> None:
    if ev.status in ev_service.STATI_NACH_VERSAND:
        raise ValidationError(
            f'{aktion} ist nach dem Einladungsversand nicht mehr möglich '
            f'(Status "{ev.get_status_display()}"). Über einen nicht '
            'angekündigten Gegenstand kann kein wirksamer Beschluss gefasst '
            'werden (§ 23 Abs. 2 WEG).'
        )


def _mache_zum_gliederungspunkt(eltern, erstellt_von) -> None:
    """Wandelt einen Haupt-TOP in einen Gliederungspunkt um, sobald er seinen
    ersten Unterpunkt bekommt: über ihn wird dann nicht mehr abgestimmt (die
    Abstimmung erfolgt auf den Unterpunkten). Ergebnislose Umstellung — hatte
    der TOP bereits ein Abstimmungsergebnis, wird das Anlegen abgelehnt.
    """
    if eltern.abstimmungsmodus == 'kein_beschluss':
        return
    eltern.abstimmungsmodus = 'kein_beschluss'
    eltern.mehrheit_schwelle = None
    eltern.triggert_vorgang = False
    eltern.triggert_wirtschaftsplan = False
    eltern.save(update_fields=[
        'abstimmungsmodus', 'mehrheit_schwelle',
        'triggert_vorgang', 'triggert_wirtschaftsplan',
    ])
    ev_service.vermerke_ereignis(
        eltern.ev, 'top_geaendert', erstellt_von, top=eltern,
        text=f'TOP {eltern.nummer_anzeige} ist jetzt ein Gliederungspunkt — '
             'die Abstimmung erfolgt auf den Unterpunkten.',
    )


@transaction.atomic
def top_anlegen(*, ev, titel, erstellt_von, erlaeuterung='', beschlussvorlage='',
                abstimmungsmodus='einfache_mehrheit', mehrheit_schwelle=None,
                nummer=None, eltern=None, triggert_vorgang=False,
                triggert_wirtschaftsplan=False,
                stimmgrundlage=None) -> Tagesordnungspunkt:
    """Legt einen TOP an — als Haupt-TOP oder, mit ``eltern``, als Unterpunkt.

    ``nummer=None`` hängt den Punkt hinten an SEINE Ebene an (Haupt-TOPs bzw.
    die Unterpunkte von ``eltern``). Wird eine Nummer übergeben, wird an dieser
    Position der Ebene eingefügt und die Folgepunkte derselben Ebene rücken auf
    — das Verschieben läuft absteigend, damit die Unique-Constraint
    (ev, eltern, nummer) nicht kurzzeitig verletzt wird.

    ``eltern`` muss zur selben EV gehören und selbst ein Haupt-TOP sein (nur
    eine Ebene). Bekommt ein Haupt-TOP seinen ersten Unterpunkt, wird er zum
    Gliederungspunkt (kein_beschluss) — hat er bereits ein Ergebnis, wird
    abgelehnt.

    ``stimmgrundlage=None`` (Spec v1.1 Kap. 3): wird automatisch vorbelegt —
    Vorgänger derselben Ebene, sonst der übergeordnete TOP, sonst die
    ``ist_standard=True``-Stimmgrundlage. Explizit übergeben überschreibt die
    Vorbelegung, muss aber zur eigenen EV gehören.
    """
    _pruefe_aenderbar(ev, 'Das Anlegen eines TOP')

    if eltern is not None:
        if eltern.ev_id != ev.id:
            raise ValidationError({
                'eltern': 'Der übergeordnete TOP gehört zu einer anderen Versammlung.',
            })
        if eltern.eltern_id is not None:
            raise ValidationError({
                'eltern': 'Unterpunkte lassen sich nicht weiter unterteilen '
                          '— es ist nur eine Ebene vorgesehen (z.B. TOP 3.1).',
            })
        if eltern.abstimmungsergebnis != 'offen':
            raise ValidationError({
                'eltern': f'TOP {eltern.nummer_anzeige} hat bereits ein '
                          'Abstimmungsergebnis und kann nicht mehr in einen '
                          'Gliederungspunkt umgewandelt werden.',
            })

    geschwister = ev.tagesordnung.filter(eltern=eltern)
    if nummer is None:
        letzte = geschwister.aggregate(m=Max('nummer'))['m'] or 0
        nummer = letzte + 1
    else:
        if nummer < 1:
            raise ValidationError({'nummer': 'TOP-Nummern beginnen bei 1.'})
        for bestehend in geschwister.filter(nummer__gte=nummer).order_by('-nummer'):
            bestehend.nummer += 1
            bestehend.save(update_fields=['nummer'])

    if stimmgrundlage is None:
        stimmgrundlage = _vorbelegte_stimmgrundlage(ev, eltern, nummer)
    elif stimmgrundlage.ev_id != ev.id:
        raise ValidationError({
            'stimmgrundlage': 'Die Stimmgrundlage gehört zu einer anderen Versammlung.',
        })

    top = Tagesordnungspunkt(
        ev=ev, eltern=eltern, nummer=nummer, titel=titel,
        erlaeuterung=erlaeuterung,
        beschlussvorlage=beschlussvorlage, abstimmungsmodus=abstimmungsmodus,
        mehrheit_schwelle=mehrheit_schwelle,
        triggert_vorgang=triggert_vorgang,
        triggert_wirtschaftsplan=triggert_wirtschaftsplan,
        stimmgrundlage=stimmgrundlage,
    )
    top.full_clean()
    top.save()

    if eltern is not None:
        _mache_zum_gliederungspunkt(eltern, erstellt_von)

    ev_service.vermerke_ereignis(
        ev, 'top_angelegt', erstellt_von, top=top,
        text=f'TOP {top.nummer_anzeige} angelegt: {top.titel}',
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
        text=f'TOP {top.nummer_anzeige} geändert — ' + '; '.join(beschreibung),
    )
    return top


@transaction.atomic
def top_loeschen(top, erstellt_von) -> None:
    """Löscht einen TOP und schließt die entstandene Nummernlücke.

    Ein Gliederungspunkt wird mitsamt seiner Unterpunkte gelöscht
    (``eltern``-CASCADE); die Nummerierung wird danach je Ebene geschlossen.
    """
    ev = top.ev
    _pruefe_aenderbar(ev, 'Das Löschen eines TOP')

    anzeige, titel = top.nummer_anzeige, top.titel
    top.delete()
    neu_nummerieren(ev)
    ev_service.vermerke_ereignis(
        ev, 'top_geloescht', erstellt_von,
        text=f'TOP {anzeige} gelöscht: {titel}',
    )


def _gruppiert_nach_ebene(ev) -> dict:
    """Alle TOPs der EV, gruppiert nach ``eltern_id`` (None = Haupt-TOPs),
    je Gruppe nach ``nummer`` sortiert."""
    gruppen = defaultdict(list)
    for top in ev.tagesordnung.all():
        gruppen[top.eltern_id].append(top)
    for tops in gruppen.values():
        tops.sort(key=lambda t: t.nummer)
    return gruppen


@transaction.atomic
def neu_nummerieren(ev) -> int:
    """Nummeriert die Tagesordnung je Ebene lückenlos ab 1 neu (Reihenfolge
    bleibt).

    Haupt-TOPs und die Unterpunkte jedes TOP werden getrennt gezählt.
    Zweistufig über negative Zwischenwerte, weil (ev, eltern, nummer) eindeutig
    ist und eine direkte Umnummerierung sonst mit sich selbst kollidieren würde.
    Rückgabe: Gesamtzahl der Punkte.
    """
    anzahl = 0
    for tops in _gruppiert_nach_ebene(ev).values():
        for index, top in enumerate(tops, start=1):
            top.nummer = -index
            top.save(update_fields=['nummer'])
        for index, top in enumerate(tops, start=1):
            top.nummer = index
            top.save(update_fields=['nummer'])
        anzahl += len(tops)
    return anzahl


def geordnete_tagesordnung(ev) -> list:
    """Die TOPs der EV in Anzeige-Reihenfolge (Baum): jeder Haupt-TOP, direkt
    gefolgt von seinen Unterpunkten, je Ebene nach ``nummer``.

    Einzige maßgebliche Reihenfolge für Anzeige, Einladung und Protokoll —
    ``Meta.ordering = ['ev', 'nummer']`` würde Haupt-TOPs und Unterpunkte sonst
    nach bloßer Nummer vermischen.
    """
    kinder = defaultdict(list)
    for top in ev.tagesordnung.select_related('eltern', 'stimmgrundlage').all():
        kinder[top.eltern_id].append(top)
    for tops in kinder.values():
        tops.sort(key=lambda t: t.nummer)

    reihenfolge = []
    for haupt in kinder.get(None, []):
        reihenfolge.append(haupt)
        reihenfolge.extend(kinder.get(haupt.id, []))
    return reihenfolge


def pruefe_vollstaendigkeit(ev) -> list[str]:
    """Prüft die Tagesordnung auf Lücken und liefert eine Liste von Klartext-
    Problemen (leere Liste = in Ordnung).

    Prüft je Ebene (Haupt-TOPs und die Unterpunkte jedes TOP getrennt) auf eine
    lückenlose Nummerierung ab 1. Wird von ``ev_service.markiere_task_erledigt``
    für Task 2 genutzt und kann im Frontend als Vorab-Prüfung angezeigt werden.
    """
    gruppen = _gruppiert_nach_ebene(ev)
    if not gruppen:
        return ['Die Tagesordnung enthält keinen Punkt.']

    probleme = []
    tops_nach_id = {t.id: t for tops in gruppen.values() for t in tops}

    for eltern_id, tops in gruppen.items():
        nummern = [top.nummer for top in tops]
        if nummern != list(range(1, len(tops) + 1)):
            if eltern_id is None:
                ebene = 'Die TOP-Nummerierung'
            else:
                ebene = (
                    'Die Unterpunkt-Nummerierung von TOP '
                    f'{tops_nach_id[eltern_id].nummer}'
                )
            probleme.append(
                f'{ebene} ist nicht lückenlos ab 1 (gefunden: {nummern}).'
            )

    for top in tops_nach_id.values():
        if top.abstimmungsmodus != 'kein_beschluss' and not top.beschlussvorlage.strip():
            probleme.append(f'TOP {top.nummer_anzeige} hat keine Beschlussvorlage.')
        if top.abstimmungsmodus == 'qualifizierte_mehrheit' and not top.mehrheit_schwelle:
            probleme.append(f'TOP {top.nummer_anzeige} hat keine Mehrheitsschwelle.')

    return probleme
