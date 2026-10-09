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
            f'TOP {top.nummer_anzeige} ist ohne Beschlussfassung angelegt — dafür kann '
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


def _pruefe_summen(top, ja: Decimal, nein: Decimal, enthaltung: Decimal) -> dict:
    if min(ja, nein, enthaltung) < 0:
        raise ValidationError('Stimmen können nicht negativ sein.')

    # Spec v1.1 Kap. 2: die Quorum-/Summenprüfung läuft je Stimmgrundlage des
    # TOP, nicht mehr EV-weit — sonst würde eine zweite Stimmgrundlage mit
    # abweichender Gesamtstimmkraft (z.B. Kopfprinzip neben MEA) falsche
    # Ergebnisse liefern. Fehlt die Stimmgrundlage (Alt-/Testdaten ohne
    # Datenmigration), bleibt der bisherige EV-weite Weg als Fallback.
    if top.stimmgrundlage_id:
        quorum = stimmkraft_service.berechne_quorum(top.ev, top.stimmgrundlage)
    else:
        quorum = stimmkraft_service.berechne_quorum(top.ev)
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
    quorum = _pruefe_summen(top, ja, nein, enthaltung)

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
            f'TOP {top.nummer_anzeige} ({top.get_abstimmungsmodus_display()}): '
            f'Ja {ja}, Nein {nein}, Enthaltung {enthaltung} → {ergebnis.upper()}'
        ),
        alter_wert=alt if war_erfasst else '',
        neuer_wert=f'{ja}/{nein}/{enthaltung} → {ergebnis}',
    )
    return top


def _stimmkraft_fuer(teilnehmer, top) -> Decimal:
    """Stimmkraft eines Teilnehmers für die Stimmgrundlage DIESES TOP.

    Bevorzugt den mehrdimensionalen ``EVTeilnehmerStimmkraft``-Snapshot zur
    ``top.stimmgrundlage`` (Spec v1.1 Kap. 2) — so ist die namentliche
    Einzelstimme korrekt gewichtet, wenn der TOP z.B. nach MEA statt nach Kopf
    abgestimmt wird. Fällt auf den Legacy-Einzelwert ``teilnehmer.stimmkraft``
    zurück, falls der TOP keine Stimmgrundlage hat oder kein Snapshot existiert
    (Alt-/Testdaten ohne Datenmigration).
    """
    if top.stimmgrundlage_id:
        snapshot = (
            teilnehmer.stimmkraft_snapshots
            .filter(stimmgrundlage_id=top.stimmgrundlage_id)
            .first()
        )
        if snapshot is not None:
            return snapshot.stimmkraft
    return teilnehmer.stimmkraft


@transaction.atomic
def _uebernehme_tool_ergebnis(top, erfasst_von, ergebnis: dict,
                              einzelstimmen_summen: dict):
    """Übernimmt das vom Abstimmtool final bewertete Ergebnis 1:1.

    immocore bewertet hier NICHT neu (``bewerte_ergebnis`` wird bewusst nicht
    aufgerufen) — das Tool ist die Beschluss-Autorität (API-Vertrag v1.3). Die
    namentlichen Einzelstimmen bleiben als Nachweis erhalten; weicht ihre Summe
    von den gelieferten Werten ab, wird das als Warnung im Ereignis-Log
    vermerkt, ohne den Vorgang abzubrechen.
    """
    ja = Decimal(str(ergebnis['ja']))
    nein = Decimal(str(ergebnis['nein']))
    enthaltung = Decimal(str(ergebnis.get('enthaltung') or 0))
    entscheidung = ergebnis['ergebnis']
    bemerkung = ergebnis.get('bemerkung')

    war_erfasst = top.abstimmungsergebnis != 'offen'
    alt = (
        f'{top.abstimmung_ja}/{top.abstimmung_nein}/{top.abstimmung_enthaltung}'
        f' → {top.abstimmungsergebnis}'
    )

    top.abstimmung_ja = ja
    top.abstimmung_nein = nein
    top.abstimmung_enthaltung = enthaltung
    top.abstimmungsergebnis = entscheidung
    felder = ['abstimmung_ja', 'abstimmung_nein', 'abstimmung_enthaltung',
              'abstimmungsergebnis']
    if bemerkung:
        top.ergebnis_bemerkung = bemerkung
        felder.append('ergebnis_bemerkung')
    top.save(update_fields=felder)

    # Weiche Konsistenzprüfung: die Summe der namentlichen Stimmen (immocore
    # rechnet mit Decimal-Snapshots, das Tool mit Fließkomma) sollte dem
    # gemeldeten Ergebnis entsprechen. Kleine Rundungsdifferenzen sind
    # unkritisch; nur echte Abweichungen werden vermerkt.
    abweichung = ''
    toleranz = Decimal('0.01')
    erwartet = (
        einzelstimmen_summen['ja'], einzelstimmen_summen['nein'],
        einzelstimmen_summen['enthaltung'],
    )
    if any(abs(a - b) > toleranz for a, b in
           zip(erwartet, (ja, nein, enthaltung))):
        abweichung = (
            f' [Hinweis: Einzelstimmen-Summe '
            f'{erwartet[0]}/{erwartet[1]}/{erwartet[2]} weicht vom gemeldeten '
            f'Ergebnis ab]'
        )

    ev_service.vermerke_ereignis(
        top.ev, 'abstimmung_korrigiert' if war_erfasst else 'abstimmung_erfasst',
        erfasst_von, top=top,
        text=(
            f'TOP {top.nummer_anzeige} ({top.get_abstimmungsmodus_display()}): '
            f'Ja {ja}, Nein {nein}, Enthaltung {enthaltung} → '
            f'{entscheidung.upper()} (vom Abstimmtool übernommen){abweichung}'
        ),
        alter_wert=alt if war_erfasst else '',
        neuer_wert=f'{ja}/{nein}/{enthaltung} → {entscheidung}',
    )
    return top


@transaction.atomic
def erfasse_einzelstimmen(top, erfasst_von, voten: dict, ergebnis: dict | None = None,
                          beschlusstext: str | None = None):
    """Erfasst namentliche Einzelvoten als Nachweis und setzt das Ergebnis.

    ``voten``: ``{teilnehmer_id: 'ja'|'nein'|'enthaltung'}``. Nicht genannte
    Teilnehmer gelten als nicht abgegeben. Abwesende dürfen nicht abstimmen —
    ein Votum für einen Abwesenden ist ein Eingabefehler und wird abgewiesen,
    nicht stillschweigend verworfen.

    ``ergebnis`` (API-Vertrag v1.3): das vom Abstimmtool final bewertete
    Ergebnis ``{ja, nein, enthaltung, ergebnis}``. Ist es gesetzt, übernimmt
    immocore es 1:1 und bewertet NICHT neu (das Tool ist die Beschluss-
    Autorität). Fehlt es, leitet immocore das Summenergebnis wie bisher über
    ``erfasse_abstimmung`` ab — dann aber gewichtet nach ``top.stimmgrundlage``.

    ``beschlusstext`` (API-Vertrag v1.4+): der im Abstimmtool final formulierte
    Beschlusswortlaut. Ist er gesetzt (not None), übernimmt immocore ihn OHNE
    Nachfrage in ``top.beschlussvorlage`` — das Tool ist auch die Autorität für
    den vor Ort verkündeten Wortlaut. So landet der in der Versammlung geänderte
    Text später über ``uebernimm_in_sammlung`` als Beschluss-Wortlaut in der
    Sammlung. ``None`` (Feld nicht gesendet) lässt den vorhandenen Text
    unangetastet; ein leerer String ist eine bewusste Leerung.

    Vorhandene Einzelstimmen des TOP werden in beiden Fällen ersetzt.
    """
    ev = top.ev
    _pruefe_offen(ev)

    if beschlusstext is not None and beschlusstext != top.beschlussvorlage:
        top.beschlussvorlage = beschlusstext
        top.save(update_fields=['beschlussvorlage'])

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

        stimmkraft = _stimmkraft_fuer(teilnehmer, top)
        EVStimme.objects.create(
            top=top, teilnehmer=teilnehmer, votum=votum,
            stimmkraft=stimmkraft, erfasst_von=erfasst_von,
        )
        summen[votum] += stimmkraft

    if abwesende:
        raise ValidationError(
            'Für abwesende Teilnehmer kann kein Votum erfasst werden: '
            + ', '.join(sorted(abwesende))
            + '. Bitte zuerst die Anwesenheit erfassen.'
        )

    if ergebnis is not None:
        return _uebernehme_tool_ergebnis(top, erfasst_von, ergebnis, summen)

    return erfasse_abstimmung(
        top, erfasst_von,
        ja=summen['ja'], nein=summen['nein'], enthaltung=summen['enthaltung'],
    )


def pruefe_ergebnisse_vollstaendig(ev) -> list:
    """Liefert die Nummern abstimmungspflichtiger TOP ohne Ergebnis.

    Wiederverwendet von ``checkout_service.abschluss`` (Spec v1.1 Kap. 4C) —
    ein vergessener TOP darf dort nicht unbemerkt bleiben. ``kein_beschluss``-
    Punkte brauchen kein Ergebnis.

    Nacharbeits-Auftrag (2026-09-26): der frühere zweite Aufrufer
    ``schliesse_durchfuehrung_ab`` (alter Task4/5-Ablauf über den Status
    ``durchgefuehrt``) wurde entfernt — der einzige Weg zu einer
    abgeschlossenen Abstimmung ist seither ``checkout_service.abschluss``.

    Rückgabe: Anzeige-Nummern (z.B. "3.1") der betroffenen TOPs.
    """
    offen = (
        ev.tagesordnung
        .exclude(abstimmungsmodus='kein_beschluss')
        .filter(abstimmungsergebnis='offen')
        .select_related('eltern')
    )
    return [top.nummer_anzeige for top in offen]


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
        text=f'TOP {top.nummer_anzeige} als {ergebnis} gekennzeichnet. {bemerkung}'.strip(),
        alter_wert=alt, neuer_wert=ergebnis,
    )
    return top
