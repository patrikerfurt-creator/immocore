"""
Durchführungs-Service (Spec v1.1 Kap. 6.1) — Anwesenheit und Abstimmung am
Tag der Versammlung.

Zwei Dinge, die hier bewusst anders sind als in Spec v1.0:

1. **Kein Quorum-Gate.** Seit der WEG-Reform (01.12.2020) ist die Versammlung
   immer beschlussfähig (§ 25 Abs. 3 WEG a.F. aufgehoben). Das Quorum wird
   berechnet und protokolliert, blockiert aber nie eine Abstimmung.
2. **Enthaltungen zählen nicht in den Nenner.** Bei einfacher und
   qualifizierter Mehrheit entscheiden die abgegebenen Ja/Nein-Stimmen.

Jede Erfassung und jede Korrektur erzeugt ein ``EVEreignis`` — Beschlüsse sind
binnen eines Monats anfechtbar (§ 45 WEG), da muss nachvollziehbar bleiben, wer
was wann eingetragen hat.
"""
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.versammlung.models import EVStimme
from apps.versammlung.services import ev_service, stimmkraft_service

_ZWEI = Decimal('0.01')

# Ab diesen Stati ist die Durchführung abgeschlossen bzw. verarbeitet —
# Anwesenheit und Ergebnisse werden dann nicht mehr angefasst.
_ABGESCHLOSSEN = {'beschluesse_verarbeitet', 'archiviert'}


def _pruefe_offen(ev) -> None:
    if ev.status in _ABGESCHLOSSEN:
        raise ValidationError(
            f'Die Versammlung ist im Status "{ev.get_status_display()}" — '
            'Anwesenheit und Abstimmungen sind nicht mehr änderbar.'
        )


def _prozent(teil: Decimal, ganz: Decimal) -> Decimal:
    if ganz <= 0:
        return Decimal('0.00')
    return (teil / ganz * Decimal('100')).quantize(_ZWEI, rounding=ROUND_HALF_UP)


@transaction.atomic
def erfasse_anwesenheit(teilnehmer, erfasst_von, *, ist_anwesend,
                        vertreten_durch=None, vertreter_name=None,
                        vollmacht_dokument=None):
    """Erfasst Anwesenheit und ggf. Vertretung eines Teilnehmers.

    ``ist_anwesend=None`` setzt die Erfassung wieder auf "offen" zurück (z.B.
    nach einem Eingabefehler). Die Stimmkraft bleibt beim Vertretenen und wird
    dem Vertreter NICHT zusätzlich angerechnet — der Vertreter stimmt mit
    fremder Stimmkraft ab, verdoppelt sie aber nicht.
    """
    ev = teilnehmer.ev
    _pruefe_offen(ev)

    if ist_anwesend not in (True, False, None):
        raise ValidationError('ist_anwesend muss true, false oder null sein.')

    alter_wert = {True: 'anwesend', False: 'abwesend', None: 'offen'}[teilnehmer.ist_anwesend]

    teilnehmer.ist_anwesend = ist_anwesend
    teilnehmer.anwesenheit_erfasst_am = timezone.now() if ist_anwesend is not None else None
    felder = ['ist_anwesend', 'anwesenheit_erfasst_am']

    if vertreten_durch is not None or vertreter_name is not None:
        teilnehmer.vertreten_durch = vertreten_durch
        teilnehmer.vertreter_name = vertreter_name or ''
        felder += ['vertreten_durch', 'vertreter_name']
    if vollmacht_dokument is not None:
        teilnehmer.vollmacht_dokument = vollmacht_dokument
        felder.append('vollmacht_dokument')

    teilnehmer.full_clean()
    teilnehmer.save(update_fields=felder)

    neuer_wert = {True: 'anwesend', False: 'abwesend', None: 'offen'}[ist_anwesend]
    vertretung = ''
    if teilnehmer.vertreten_durch_id:
        vertretung = f' (vertreten durch {teilnehmer.vertreten_durch.name})'
    elif teilnehmer.vertreter_name:
        vertretung = f' (vertreten durch {teilnehmer.vertreter_name})'

    ev_service.vermerke_ereignis(
        ev, 'anwesenheit_erfasst', erfasst_von,
        text=f'{teilnehmer.person.name}: {neuer_wert}{vertretung}',
        alter_wert=alter_wert, neuer_wert=neuer_wert,
    )
    return teilnehmer


@transaction.atomic
def erfasse_zusage(teilnehmer, erfasst_von, *, zusage_status, quelle='manuell'):
    """Erfasst Zu- oder Absage eines Teilnehmers.

    ``quelle='manuell'`` = von der Verwaltung eingetragen (Rückruf, Brief),
    ``quelle='portal'`` = vom Eigentümer selbst (Phase C). Anders als die
    Anwesenheit ist die Zusage auch nach der Versammlung noch erfassbar — sie
    ist eine Rückmeldung, kein Abstimmungsfaktor.
    """
    erlaubt = dict(teilnehmer.ZUSAGE_CHOICES)
    if zusage_status not in erlaubt:
        raise ValidationError(
            f'Unbekannter Zusage-Status: {zusage_status} '
            f'(erlaubt: {", ".join(erlaubt)})'
        )
    if quelle not in ('manuell', 'portal'):
        raise ValidationError('quelle muss "manuell" oder "portal" sein.')

    alt = teilnehmer.zusage_status
    teilnehmer.zusage_status = zusage_status
    teilnehmer.zusage_am = timezone.now() if zusage_status != 'offen' else None
    teilnehmer.zusage_quelle = quelle if zusage_status != 'offen' else ''
    teilnehmer.save(update_fields=['zusage_status', 'zusage_am', 'zusage_quelle'])

    ev_service.vermerke_ereignis(
        teilnehmer.ev, 'zusage_erfasst', erfasst_von,
        text=f'{teilnehmer.person.name}: {erlaubt[zusage_status]} ({quelle})',
        alter_wert=alt, neuer_wert=zusage_status,
    )
    return teilnehmer


def bewerte_ergebnis(top, ja: Decimal, nein: Decimal, enthaltung: Decimal,
                     gesamt_stimmkraft: Decimal) -> str:
    """Liefert ``'angenommen'`` oder ``'abgelehnt'`` (Spec v1.1 Kap. 6.1).

    * ``einfache_mehrheit``      — Ja > Nein
    * ``qualifizierte_mehrheit`` — Ja-Anteil an den abgegebenen Stimmen
                                   erreicht ``top.mehrheit_schwelle``
    * ``einstimmigkeit``         — keine Nein-Stimme und mindestens eine
                                   Ja-Stimme unter den abgegebenen Stimmen
    * ``allstimmigkeit``         — Ja erreicht die GESAMTE Stimmkraft der
                                   Gemeinschaft, auch die der Abwesenden

    Enthaltungen werden bei den ersten beiden Modi nicht mitgezählt.
    """
    abgegeben = ja + nein
    modus = top.abstimmungsmodus

    if modus == 'kein_beschluss':
        raise ValidationError(
            f'TOP {top.nummer} ist ohne Beschlussfassung angelegt — dafür kann '
            'kein Abstimmungsergebnis erfasst werden.'
        )
    if modus == 'einfache_mehrheit':
        return 'angenommen' if ja > nein else 'abgelehnt'
    if modus == 'qualifizierte_mehrheit':
        if abgegeben <= 0:
            return 'abgelehnt'
        return 'angenommen' if _prozent(ja, abgegeben) >= top.mehrheit_schwelle else 'abgelehnt'
    if modus == 'einstimmigkeit':
        return 'angenommen' if (nein == 0 and ja > 0) else 'abgelehnt'
    if modus == 'allstimmigkeit':
        return 'angenommen' if (gesamt_stimmkraft > 0 and ja >= gesamt_stimmkraft) else 'abgelehnt'

    raise ValidationError(f'Unbekannter Abstimmungsmodus: {modus}')


def _pruefe_summen(ev, ja: Decimal, nein: Decimal, enthaltung: Decimal) -> dict:
    if min(ja, nein, enthaltung) < 0:
        raise ValidationError('Stimmen können nicht negativ sein.')

    quorum = stimmkraft_service.berechne_quorum(ev)
    summe = ja + nein + enthaltung
    anwesend = quorum['anwesende_stimmkraft']
    if summe > anwesend:
        raise ValidationError(
            f'Die erfassten Stimmen ({summe}) übersteigen die anwesende '
            f'Stimmkraft ({anwesend}). Bitte zuerst die Anwesenheit prüfen.'
        )
    return quorum


@transaction.atomic
def erfasse_abstimmung(top, erfasst_von, *, ja, nein, enthaltung=0, bemerkung=None):
    """Erfasst das Summenergebnis eines TOP und bewertet es.

    Eine erneute Erfassung überschreibt das Ergebnis und wird als Korrektur
    protokolliert (``abstimmung_korrigiert`` statt ``abstimmung_erfasst``).
    """
    ev = top.ev
    _pruefe_offen(ev)

    ja, nein, enthaltung = Decimal(str(ja)), Decimal(str(nein)), Decimal(str(enthaltung))
    quorum = _pruefe_summen(ev, ja, nein, enthaltung)

    war_erfasst = top.abstimmungsergebnis != 'offen'
    alt = (
        f'{top.abstimmung_ja}/{top.abstimmung_nein}/{top.abstimmung_enthaltung}'
        f' → {top.abstimmungsergebnis}'
    )

    ergebnis = bewerte_ergebnis(top, ja, nein, enthaltung, quorum['gesamt_stimmkraft'])

    top.abstimmung_ja = ja
    top.abstimmung_nein = nein
    top.abstimmung_enthaltung = enthaltung
    top.abstimmungsergebnis = ergebnis
    felder = ['abstimmung_ja', 'abstimmung_nein', 'abstimmung_enthaltung',
              'abstimmungsergebnis']
    if bemerkung is not None:
        top.ergebnis_bemerkung = bemerkung
        felder.append('ergebnis_bemerkung')
    top.save(update_fields=felder)

    ev_service.vermerke_ereignis(
        ev, 'abstimmung_korrigiert' if war_erfasst else 'abstimmung_erfasst',
        erfasst_von, top=top,
        text=(
            f'TOP {top.nummer} ({top.get_abstimmungsmodus_display()}): '
            f'Ja {ja}, Nein {nein}, Enthaltung {enthaltung} → {ergebnis.upper()}'
        ),
        alter_wert=alt if war_erfasst else '',
        neuer_wert=f'{ja}/{nein}/{enthaltung} → {ergebnis}',
    )
    return top


@transaction.atomic
def erfasse_einzelstimmen(top, erfasst_von, voten: dict):
    """Erfasst namentliche Einzelvoten und leitet das Summenergebnis daraus ab.

    ``voten``: ``{teilnehmer_id: 'ja'|'nein'|'enthaltung'}``. Nicht genannte
    Teilnehmer gelten als nicht abgegeben. Abwesende dürfen nicht abstimmen —
    ein Votum für einen Abwesenden ist ein Eingabefehler und wird abgewiesen,
    nicht stillschweigend verworfen.

    Vorhandene Einzelstimmen des TOP werden ersetzt; das Summenergebnis läuft
    danach über ``erfasse_abstimmung``, damit es genau einen Bewertungspfad gibt.
    """
    ev = top.ev
    _pruefe_offen(ev)

    teilnehmer_nach_id = {str(t.id): t for t in ev.teilnehmer.select_related('person')}
    unbekannt = set(map(str, voten)) - set(teilnehmer_nach_id)
    if unbekannt:
        raise ValidationError(
            'Unbekannte Teilnehmer in der Abstimmung: ' + ', '.join(sorted(unbekannt))
        )

    erlaubte_voten = {'ja', 'nein', 'enthaltung'}
    summen = {'ja': Decimal('0'), 'nein': Decimal('0'), 'enthaltung': Decimal('0')}
    abwesende = []

    top.stimmen.all().delete()

    for teilnehmer_id, votum in voten.items():
        if votum not in erlaubte_voten:
            raise ValidationError(f'Unbekanntes Votum: {votum}')
        teilnehmer = teilnehmer_nach_id[str(teilnehmer_id)]
        if teilnehmer.ist_anwesend is not True:
            abwesende.append(teilnehmer.person.name)
            continue

        EVStimme.objects.create(
            top=top, teilnehmer=teilnehmer, votum=votum,
            stimmkraft=teilnehmer.stimmkraft, erfasst_von=erfasst_von,
        )
        summen[votum] += teilnehmer.stimmkraft

    if abwesende:
        raise ValidationError(
            'Für abwesende Teilnehmer kann kein Votum erfasst werden: '
            + ', '.join(sorted(abwesende))
            + '. Bitte zuerst die Anwesenheit erfassen.'
        )

    return erfasse_abstimmung(
        top, erfasst_von,
        ja=summen['ja'], nein=summen['nein'], enthaltung=summen['enthaltung'],
    )


@transaction.atomic
def schliesse_durchfuehrung_ab(ev, erfasst_von):
    """Schließt Task 4 ab: Status → ``durchgefuehrt``.

    Offene TOPs (Ergebnis ``offen``) werden benannt statt übergangen — ein
    vergessener TOP fällt sonst erst bei der Beschlussfassung auf, und dann
    fehlt er im Protokoll. ``kein_beschluss``-Punkte brauchen kein Ergebnis.
    """
    _pruefe_offen(ev)

    offen = list(
        ev.tagesordnung
        .exclude(abstimmungsmodus='kein_beschluss')
        .filter(abstimmungsergebnis='offen')
        .values_list('nummer', flat=True)
    )
    if offen:
        raise ValidationError(
            'Für folgende TOP fehlt noch ein Ergebnis: '
            + ', '.join(f'TOP {n}' for n in offen)
            + '. Alternativ als vertagt oder entfallen kennzeichnen.'
        )

    if ev.status == 'entwurf':
        ev_service.wechsle_status(
            ev, 'in_bearbeitung', erfasst_von,
            text='Automatisch beim Abschluss der Durchführung.',
        )
    if ev.status in ('in_bearbeitung', 'einladungen_versendet'):
        # Aus 'in_bearbeitung' geht es direkt weiter — eine Versammlung ohne
        # über IMMOCORE dokumentierten Versand wird NICHT nachträglich als
        # "Einladungen versendet" ausgewiesen (siehe ev_service).
        ev_service.wechsle_status(ev, 'durchgefuehrt', erfasst_von)

    ev_service.markiere_task_erledigt(ev, 4, erfasst_von)
    return ev


@transaction.atomic
def setze_ergebnis_status(top, erfasst_von, ergebnis: str, bemerkung=''):
    """Kennzeichnet einen TOP als ``vertagt`` oder ``entfallen``.

    Getrennt von ``erfasse_abstimmung``, weil hier gerade NICHT abgestimmt
    wurde — die Stimmenfelder bleiben auf 0.
    """
    _pruefe_offen(top.ev)
    if ergebnis not in ('vertagt', 'entfallen'):
        raise ValidationError(
            'Über diesen Weg sind nur "vertagt" und "entfallen" setzbar; '
            'ein Abstimmungsergebnis entsteht über erfasse_abstimmung.'
        )

    alt = top.abstimmungsergebnis
    top.abstimmungsergebnis = ergebnis
    top.ergebnis_bemerkung = bemerkung
    top.save(update_fields=['abstimmungsergebnis', 'ergebnis_bemerkung'])

    ev_service.vermerke_ereignis(
        top.ev, 'abstimmung_erfasst', erfasst_von, top=top,
        text=f'TOP {top.nummer} als {ergebnis} gekennzeichnet. {bemerkung}'.strip(),
        alter_wert=alt, neuer_wert=ergebnis,
    )
    return top
