"""
Jahresabrechnung Schritt 2 — Saldovortrag offener Kreditor-OPs ins Folgejahr.

Hintergrund: Die WEG-Jahresabrechnung folgt dem Abflussprinzip — Kosten
gehören in das Jahr, in dem sie bezahlt wurden. Eine Eingangsrechnung, die
im abzurechnenden Jahr gebucht, aber nicht bezahlt wurde, darf das Jahr
deshalb nicht belasten. Sie wird stattdessen ins Folgejahr vorgetragen:

  Altjahr:    Kreditorkonto (70xxx) Soll  /  Gegenkonto (i.d.R. 15900) Haben
  Folgejahr:  Gegenkonto (15900)    Soll  /  Kreditorkonto (70xxx)     Haben

Beide Konten sind Bestandskonten, die Kostenstelle wird nicht berührt — der
Vortrag ist damit erfolgsneutral. Im Altjahr saldieren die betroffenen Konten
auf null, im Folgejahr steht die Rechnung wieder offen und wird beim
Bezahlen ganz normal auf das Kostenkonto abgerechnet.

Der OP selbst bleibt `offen` — er ist weiterhin zahlbar. Gesetzt wird nur
`vortrag_wj`; die Buchungsprüfung (Schritt 2) blendet OPs aus, die über das
abgerechnete Jahr hinaus vorgetragen sind.

Sonderfall: Existiert im Altjahr keine festgeschriebene Buchung zum OP
(Buchung fehlt oder steht noch im Entwurf), gibt es dort nichts aufzulösen.
Dann wird ausschließlich der OP vorgetragen, ohne Buchungen.
"""
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.buchhaltung.models import Buchung, Buchungsart, KreditorOP
from apps.konten.services import konto_im_jahr
from apps.objekte.models import Wirtschaftsjahr

BA_SALDOVORTRAG = '99'
BELEG_REFERENZ_PREFIX = 'KREDITOR-OP-VORTRAG'


def _belegnr(buchungsdatum: date) -> str:
    """Fortlaufende Belegnummer im Schema KV-<Jahr>-<lfd>."""
    prefix = f'KV-{buchungsdatum.year}-'
    last = (
        Buchung.objects.filter(belegnr__startswith=prefix)
        .order_by('-belegnr')
        .values_list('belegnr', flat=True)
        .first()
    )
    try:
        lfd = int(last.rsplit('-', 1)[-1]) + 1 if last else 1
    except (ValueError, AttributeError):
        lfd = 1
    return f'{prefix}{lfd:05d}'


def folge_wirtschaftsjahr(wj: Wirtschaftsjahr) -> Wirtschaftsjahr:
    """Das Wirtschaftsjahr, in das vorgetragen wird. Fehlt es, ist Schluss."""
    folge = Wirtschaftsjahr.objects.filter(objekt=wj.objekt, jahr=wj.jahr + 1).first()
    if folge is None:
        raise ValidationError(
            f'Für {wj.objekt.bezeichnung} existiert kein Wirtschaftsjahr {wj.jahr + 1}. '
            f'Bitte zuerst das Folgejahr eröffnen, dann den Saldovortrag buchen.'
        )
    if folge.status != 'offen':
        raise ValidationError(
            f'Wirtschaftsjahr {folge.jahr} ist nicht offen (Status: {folge.status}) — '
            f'ein Saldovortrag ist dorthin nicht möglich.'
        )
    return folge


def _gegenkonto(op: KreditorOP, kreditorkonto_nr: str):
    """
    Die Nicht-Kreditor-Seite der Ursprungsbuchung — üblicherweise 15900
    (Schwebende Eingangsrechnungen). Nur so wird im Altjahr genau das
    aufgelöst, was die Rechnung dort angelegt hat.
    """
    b = op.buchung
    kandidaten = [k for k in (b.soll_konto, b.haben_konto) if k is not None]
    gegen = [k for k in kandidaten if k.kontonummer != kreditorkonto_nr]
    if len(gegen) != 1:
        raise ValidationError(
            f'OP-{op.op_nummer}: Gegenkonto der Ursprungsbuchung ist nicht eindeutig '
            f'(Soll: {b.soll_konto}, Haben: {b.haben_konto}). '
            f'Vortrag muss hier manuell gebucht werden.'
        )
    return gegen[0]


@transaction.atomic
def vortrage_kreditor_ops(ja, op_ids: list, user) -> dict:
    """
    Trägt die gewählten offenen Kreditor-OPs ins Folgejahr vor.

    ja      : Jahresabrechnung (Status 'entwurf')
    op_ids  : Liste von KreditorOP.op_nummer (int oder str)
    user    : ausführender Benutzer

    Gibt eine Zusammenfassung je OP zurück.
    """
    from apps.rechnungen.services.rechnung_op_service import get_or_create_kreditor_konto

    if ja.status != 'entwurf':
        raise ValidationError("Saldovortrag nur im Status 'entwurf' möglich.")
    if not op_ids:
        raise ValidationError('Keine Kreditor-OPs ausgewählt.')

    wj_alt = ja.wirtschaftsjahr
    wj_neu = folge_wirtschaftsjahr(wj_alt)
    objekt = ja.objekt

    try:
        nummern = [int(n) for n in op_ids]
    except (TypeError, ValueError):
        raise ValidationError('Ungültige OP-Nummer übergeben.')

    ops = list(
        KreditorOP.objects
        .select_related('kreditor', 'buchung', 'buchung__soll_konto', 'buchung__haben_konto')
        .filter(objekt=objekt, op_nummer__in=nummern)
        .order_by('op_nummer')
    )
    gefunden = {op.op_nummer for op in ops}
    if fehlend := set(nummern) - gefunden:
        raise ValidationError(
            'Kreditor-OP nicht gefunden (oder gehört zu einem anderen Objekt): '
            + ', '.join(f'OP-{n}' for n in sorted(fehlend))
        )

    for op in ops:
        if op.status not in ('offen', 'teilbezahlt'):
            raise ValidationError(
                f'OP-{op.op_nummer} hat den Status "{op.get_status_display()}" und '
                f'kann nicht vorgetragen werden.'
            )
        if op.vortrag_wj_id and op.vortrag_wj.jahr > wj_alt.jahr:
            raise ValidationError(
                f'OP-{op.op_nummer} ist bereits nach {op.vortrag_wj.jahr} vorgetragen.'
            )
        if op.betrag_offen <= 0:
            raise ValidationError(
                f'OP-{op.op_nummer} hat keinen offenen Betrag ({op.betrag_offen} €).'
            )

    ba = Buchungsart.objects.filter(nr=BA_SALDOVORTRAG).first()
    datum_alt = wj_alt.ende_datum
    datum_neu = wj_neu.beginn_datum
    jetzt = timezone.now()
    ergebnisse = []

    for op in ops:
        betrag = op.betrag_offen
        kreditorkonto_alt = get_or_create_kreditor_konto(op.kreditor, objekt, jahr=wj_alt.jahr)
        gebucht = False

        # Nur eine festgeschriebene Ursprungsbuchung hat im Altjahr Spuren
        # hinterlassen, die aufzulösen sind.
        if op.buchung and op.buchung.status == 'festgeschrieben':
            gegen_alt = _gegenkonto(op, kreditorkonto_alt.kontonummer)
            gegen_neu = konto_im_jahr(gegen_alt, wj_neu.jahr)
            if gegen_neu.wirtschaftsjahr.jahr != wj_neu.jahr:
                raise ValidationError(
                    f'OP-{op.op_nummer}: Konto {gegen_alt.kontonummer} existiert im '
                    f'Wirtschaftsjahr {wj_neu.jahr} nicht — Kontenrahmen zuerst ergänzen.'
                )
            kreditorkonto_neu = get_or_create_kreditor_konto(
                op.kreditor, objekt, jahr=wj_neu.jahr)

            text = (
                f'Saldovortrag OP-{op.op_nummer} {op.kreditor.name} — '
                f'offene Eingangsrechnung nach {wj_neu.jahr}'
            )
            gemeinsam = dict(
                objekt=objekt,
                buchungsart=ba,
                betrag=betrag,
                kreditor=op.kreditor,
                beleg_referenz=f'{BELEG_REFERENZ_PREFIX}-{op.op_nummer}',
                status='festgeschrieben',
                erstellt_von=user,
            )
            # Altjahr: Kreditorverbindlichkeit und Schwebeposten auflösen
            Buchung.objects.create(
                soll_konto=kreditorkonto_alt,
                haben_konto=gegen_alt,
                buchungsdatum=datum_alt,
                belegnr=_belegnr(datum_alt),
                buchungstext=f'{text} (Abgang {wj_alt.jahr})',
                wirtschaftsjahr=wj_alt,
                wirtschaftsjahr_nr=wj_alt.jahr,
                **gemeinsam,
            )
            # Folgejahr: Rechnung wieder als offen einstellen
            Buchung.objects.create(
                soll_konto=gegen_neu,
                haben_konto=kreditorkonto_neu,
                buchungsdatum=datum_neu,
                belegnr=_belegnr(datum_neu),
                buchungstext=f'{text} (Zugang {wj_neu.jahr})',
                wirtschaftsjahr=wj_neu,
                wirtschaftsjahr_nr=wj_neu.jahr,
                **gemeinsam,
            )
            gebucht = True

        op.vortrag_wj = wj_neu
        op.vortrag_am = jetzt
        op.vortrag_von = user
        op.save(update_fields=['vortrag_wj', 'vortrag_am', 'vortrag_von'])

        ergebnisse.append({
            'op_nummer': op.op_nummer,
            'kreditor': op.kreditor.name,
            'betrag': str(betrag),
            'gebucht': gebucht,
            'hinweis': '' if gebucht else (
                f'Keine festgeschriebene Buchung im WJ {wj_alt.jahr} — '
                f'nur der offene Posten wurde vorgetragen, ohne Buchung.'
            ),
        })

    return {
        'vorgetragen_nach': wj_neu.jahr,
        'anzahl': len(ergebnisse),
        'summe': str(sum(op.betrag_offen for op in ops)),
        'anzahl_gebucht': sum(1 for e in ergebnisse if e['gebucht']),
        'ops': ergebnisse,
    }
