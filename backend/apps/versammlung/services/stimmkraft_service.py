"""
Stimmkraft-Service (Spec v1.1 Kap. 5) — Teilnehmerkreis und Stimmkraft einer EV.

Der Teilnehmerkreis wird aus den aktiven ``EigentumsVerhaeltnis``-Datensätzen
des Objekts abgeleitet (``ende IS NULL``). Je Eigentümer-Person entsteht ein
``EVTeilnehmer``, je zugehöriger Einheit ein ``EVTeilnehmerAnteil``.

Zwei Grundlagen (Patrik-Entscheidung 2026-08-20):

* ``stimmprinzip='kopf'`` — eine Stimme je Eigentümer, unabhängig von der
  Anzahl seiner Einheiten (§ 25 Abs. 2 WEG, gesetzlicher Regelfall).
* ``stimmprinzip='verteilerschluessel'`` — die Stimmkraft kommt aus einem
  beliebigen Verteilerschlüssel des Objekts. Damit deckt ein Codepfad alle
  Regelungen der Teilungserklärung ab: ``030`` (eine Stimme je Einheit),
  ``031`` (nur Wohnungen stimmen mit), ``010`` (MEA/Wertprinzip), ``001``
  (Fläche).

Fehlende Werte oder Einheiten ohne Eigentümer führen zum ABBRUCH, nicht zu
einer stillschweigend kleineren Stimmkraft: eine verlorene Stimme macht jeden
darauf gestützten Beschluss angreifbar.
"""
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.objekte.models import VerteilerschluesselWert
from apps.personen.models import EigentumsVerhaeltnis
from apps.versammlung.models import EVTeilnehmer, EVTeilnehmerAnteil
from apps.versammlung.services import ev_service

_ZWEI = Decimal('0.01')

# Maximal so viele Einheiten werden in einer Fehlermeldung aufgezählt — die
# Muster-Verteilerschlüssel aus konten.services legen MEA/Fläche ohne Werte an,
# das betrifft dann ALLE Einheiten des Objekts.
_MAX_AUFZAEHLUNG = 10


def _kuerze(namen: list) -> str:
    if len(namen) <= _MAX_AUFZAEHLUNG:
        return ', '.join(namen)
    return (', '.join(namen[:_MAX_AUFZAEHLUNG])
            + f' … und {len(namen) - _MAX_AUFZAEHLUNG} weitere')


def _einheiten_nummern(objekt, einheit_ids) -> list:
    return list(
        objekt.einheiten.filter(id__in=einheit_ids)
        .order_by('einheit_nr').values_list('einheit_nr', flat=True)
    )


def vs_werte(ev) -> dict:
    """Liefert ``{einheit_id: Decimal}`` aus dem Stimm-Verteilerschlüssel.

    Prüft dabei die Vollständigkeit des Schlüssels selbst: jede beteiligte
    Einheit braucht einen positiven Wert. Wird nur bei
    ``stimmprinzip='verteilerschluessel'`` aufgerufen.
    """
    vs = ev.stimm_verteilerschluessel
    if vs is None:
        raise ValidationError(
            'Für dieses Stimmprinzip ist kein Verteilerschlüssel gesetzt.'
        )
    if not vs.aktiv:
        raise ValidationError(
            f'Der Verteilerschlüssel "{vs.schluessel} {vs.bezeichnung}" ist '
            'nicht aktiv und kann nicht Grundlage der Stimmkraft sein.'
        )

    zeilen = list(
        VerteilerschluesselWert.objects
        .filter(schluessel=vs, wirtschaftsjahr=ev.stimm_wirtschaftsjahr,
                beteiligt=True)
        .values_list('einheit_id', 'wert')
    )
    if not zeilen:
        raise ValidationError(
            f'Der Verteilerschlüssel "{vs.schluessel} {vs.bezeichnung}" hat für '
            f'das Wirtschaftsjahr {ev.stimm_wirtschaftsjahr} keine beteiligten '
            'Einheiten — als Stimmgrundlage nicht verwendbar.'
        )

    ohne_wert = [eid for eid, wert in zeilen if wert is None or wert <= 0]
    if ohne_wert:
        nummern = _einheiten_nummern(ev.objekt, ohne_wert)
        raise ValidationError(
            f'Im Verteilerschlüssel "{vs.schluessel} {vs.bezeichnung}" '
            f'(Wirtschaftsjahr {ev.stimm_wirtschaftsjahr}) fehlen Werte für '
            f'{len(nummern)} beteiligte Einheiten: {_kuerze(nummern)}. Ohne '
            'gepflegte Werte ist dieser Schlüssel keine Stimmgrundlage — bitte '
            'Werte nachtragen oder das Kopfprinzip verwenden.'
        )

    return {eid: Decimal(wert) for eid, wert in zeilen}


def _pruefe_zuordenbar(ev, werte: dict, verhaeltnisse: list) -> None:
    """Stellt sicher, dass die gesamte Stimmkraft einem Eigentümer zugeordnet ist.

    Hintergrund (Patrik-Entscheidung 2026-08-20): am Objekt 10031 haben 16 von
    32 Einheiten überhaupt kein ``EigentumsVerhaeltnis``. Ohne diese Prüfung
    würde eine EV dort mit halber Stimmkraft rechnen — bei Allstimmigkeit wäre
    gar kein Beschluss mehr möglich, und niemand hätte es gemerkt. Der
    Stammdatenfehler muss vor der Versammlung behoben werden.
    """
    zugeordnet = {v.einheit_id for v in verhaeltnisse}
    offen = [eid for eid in werte if eid not in zugeordnet]
    if not offen:
        return

    nummern = _einheiten_nummern(ev.objekt, offen)
    fehlende_kraft = sum((werte[eid] for eid in offen), Decimal('0'))
    raise ValidationError(
        f'{len(nummern)} Einheiten mit Stimmkraft haben keinen aktiven '
        f'Eigentümer: {_kuerze(nummern)}. Damit wären {fehlende_kraft} von '
        f'{sum(werte.values(), Decimal("0"))} Stimmen nicht vertreten. Bitte '
        'zuerst die Eigentumsverhältnisse pflegen — sonst rechnet die '
        'Versammlung mit einer zu kleinen Stimmkraft.'
    )


def _stimmkraft_kopf(person_verhaeltnisse: list) -> Decimal:
    return Decimal('1')


def _stimmkraft_vs(person_verhaeltnisse: list, werte: dict) -> Decimal:
    summe = Decimal('0')
    for verhaeltnis in person_verhaeltnisse:
        wert = werte.get(verhaeltnis.einheit_id)
        if wert is None:
            # Einheit ist im Schlüssel nicht beteiligt (z.B. Stellplatz in
            # VS 031 "Anzahl Wohnungen") — sie trägt bewusst keine Stimme bei.
            continue
        summe += wert
    return summe


@transaction.atomic
def ermittle_teilnehmer(ev, erstellt_von) -> dict:
    """Erzeugt bzw. aktualisiert Teilnehmer, Anteile und Stimmkraft-Snapshot.

    Idempotent und mehrfach aufrufbar: bestehende Teilnehmer werden
    aktualisiert, neue ergänzt. Personen, die nicht mehr Eigentümer sind,
    behalten ihre Zeile (Nachweis, wer geladen wurde) und erhalten
    ``stimmkraft=0``.

    Rückgabe: ``{'teilnehmer', 'neu', 'entfallen', 'gesamt_stimmkraft',
    'ohne_stimmrecht', 'grundlage'}``.
    """
    verhaeltnisse = list(
        EigentumsVerhaeltnis.objects
        .filter(einheit__objekt=ev.objekt, ende__isnull=True)
        .select_related('einheit', 'person')
    )
    if not verhaeltnisse:
        raise ValidationError(
            f'Objekt "{ev.objekt.bezeichnung}" hat keine aktiven '
            'Eigentumsverhältnisse — es gibt niemanden zu laden.'
        )

    nach_verteilerschluessel = ev.stimmprinzip == 'verteilerschluessel'
    if nach_verteilerschluessel:
        werte = vs_werte(ev)
        _pruefe_zuordenbar(ev, werte, verhaeltnisse)
        grundlage = (
            f'{ev.stimm_verteilerschluessel.schluessel} '
            f'{ev.stimm_verteilerschluessel.bezeichnung}'
        )
    else:
        # Auch beim Kopfprinzip wird ein vorhandener MEA-Schlüssel gelesen, um
        # den Snapshot fürs Protokoll zu füllen — fehlende Werte sind hier
        # unkritisch, weil sie die Stimmkraft nicht bestimmen.
        werte = _mea_snapshot(ev)
        grundlage = 'Kopfprinzip'

    gruppen = defaultdict(list)
    for verhaeltnis in verhaeltnisse:
        gruppen[verhaeltnis.person_id].append(verhaeltnis)

    neu = 0
    gesamt = Decimal('0')
    ohne_stimmrecht = []

    for person_id, liste in gruppen.items():
        teilnehmer, erzeugt = EVTeilnehmer.objects.get_or_create(
            ev=ev, person_id=person_id,
        )
        neu += 1 if erzeugt else 0

        bestehende = {a.eigentumsverhaeltnis_id: a for a in teilnehmer.anteile.all()}
        aktuelle = set()
        for verhaeltnis in liste:
            wert = werte.get(verhaeltnis.einheit_id)
            anteil = bestehende.get(verhaeltnis.id)
            if anteil is None:
                EVTeilnehmerAnteil.objects.create(
                    teilnehmer=teilnehmer,
                    eigentumsverhaeltnis=verhaeltnis,
                    einheit_nr_snapshot=verhaeltnis.einheit.einheit_nr,
                    mea_wert_snapshot=wert,
                )
            else:
                anteil.einheit_nr_snapshot = verhaeltnis.einheit.einheit_nr
                anteil.mea_wert_snapshot = wert
                anteil.save(update_fields=['einheit_nr_snapshot', 'mea_wert_snapshot'])
            aktuelle.add(verhaeltnis.id)

        # Anteile, die nicht mehr zu einem aktiven Verhältnis gehören
        # (Einheit verkauft), fallen weg — die Teilnehmerzeile bleibt.
        for verhaeltnis_id, anteil in bestehende.items():
            if verhaeltnis_id not in aktuelle:
                anteil.delete()

        if nach_verteilerschluessel:
            stimmkraft = _stimmkraft_vs(liste, werte)
        else:
            stimmkraft = _stimmkraft_kopf(liste)

        if stimmkraft == 0:
            # Kein Fehler: bei VS 031 haben reine Stellplatz-Eigentümer
            # bewusst kein Stimmrecht. Sie werden aber geladen und im
            # Ergebnis benannt, damit das nicht unbemerkt passiert.
            ohne_stimmrecht.append(teilnehmer.person.name)

        if teilnehmer.stimmkraft != stimmkraft:
            teilnehmer.stimmkraft = stimmkraft
            teilnehmer.save(update_fields=['stimmkraft'])
        gesamt += stimmkraft

    entfallen = 0
    for teilnehmer in ev.teilnehmer.exclude(person_id__in=gruppen.keys()):
        if teilnehmer.stimmkraft != 0:
            teilnehmer.stimmkraft = Decimal('0')
            teilnehmer.save(update_fields=['stimmkraft'])
        entfallen += 1

    ev_service.vermerke_ereignis(
        ev, 'stimmkraft_ermittelt', erstellt_von,
        text=(
            f'Stimmkraft nach "{grundlage}" ermittelt: {len(gruppen)} '
            f'Teilnehmer ({neu} neu, {entfallen} nicht mehr stimmberechtigt), '
            f'Gesamtstimmkraft {gesamt}.'
            + (f' Ohne Stimmrecht in diesem Schlüssel: '
               f'{_kuerze(ohne_stimmrecht)}.' if ohne_stimmrecht else '')
        ),
        neuer_wert=str(gesamt),
    )

    return {
        'teilnehmer': len(gruppen),
        'neu': neu,
        'entfallen': entfallen,
        'gesamt_stimmkraft': gesamt,
        'ohne_stimmrecht': ohne_stimmrecht,
        'grundlage': grundlage,
    }


def _mea_snapshot(ev) -> dict:
    """MEA-Werte nur als Zusatzinformation für den Anteil-Snapshot.

    Beim Kopfprinzip bestimmt der MEA die Stimmkraft nicht — fehlt der
    Schlüssel oder sind Werte leer, ist das hier folgenlos.
    """
    from apps.objekte.models import Verteilerschluessel

    vs = (
        Verteilerschluessel.objects
        .filter(objekt=ev.objekt, vs_typ='mea', aktiv=True)
        .order_by('schluessel').first()
    )
    if vs is None:
        return {}
    return {
        eid: Decimal(wert)
        for eid, wert in VerteilerschluesselWert.objects
        .filter(schluessel=vs, wirtschaftsjahr=ev.stimm_wirtschaftsjahr,
                beteiligt=True)
        .values_list('einheit_id', 'wert')
        if wert is not None
    }


def stimmkraft_neu_ermitteln(ev, erstellt_von) -> dict:
    """Erneute Ermittlung nach einem Eigentümerwechsel (Spec Kap. 5.3).

    Fachlich identisch zu ``ermittle_teilnehmer`` — eigener Name, weil der
    Aufruf in Task 4 eine andere Bedeutung hat (Korrektur einer bereits
    versendeten Ladung) und im Verlauf so auch gelesen wird.
    """
    return ermittle_teilnehmer(ev, erstellt_von)


def berechne_quorum(ev) -> dict:
    """Anwesende Stimmkraft im Verhältnis zur Gesamtstimmkraft — rein informativ.

    Seit der WEG-Reform (01.12.2020) ist die Versammlung immer beschlussfähig
    (§ 25 Abs. 3 WEG a.F. wurde aufgehoben). Es gibt deshalb bewusst KEIN Feld
    ``quorum_erreicht`` und kein Gate auf die Abstimmungserfassung.
    """
    gesamt = Decimal('0')
    anwesend = Decimal('0')
    anzahl_anwesend = 0
    anzahl_offen = 0

    for teilnehmer in ev.teilnehmer.all():
        gesamt += teilnehmer.stimmkraft
        if teilnehmer.ist_anwesend is True:
            anwesend += teilnehmer.stimmkraft
            anzahl_anwesend += 1
        elif teilnehmer.ist_anwesend is None:
            anzahl_offen += 1

    if gesamt > 0:
        prozent = (anwesend / gesamt * Decimal('100')).quantize(_ZWEI, rounding=ROUND_HALF_UP)
    else:
        prozent = Decimal('0.00')

    return {
        'gesamt_stimmkraft': gesamt,
        'anwesende_stimmkraft': anwesend,
        'anwesend_prozent': prozent,
        'anzahl_teilnehmer': ev.teilnehmer.count(),
        'anzahl_anwesend': anzahl_anwesend,
        'anzahl_anwesenheit_offen': anzahl_offen,
        'hinweis': (
            'Die Versammlung ist unabhängig von der anwesenden Stimmkraft '
            'beschlussfähig (§ 25 Abs. 3 WEG a.F. aufgehoben). Die Angabe '
            'dient der Protokollierung.'
        ),
    }
