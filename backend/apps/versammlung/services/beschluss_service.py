"""
Beschluss-Service (Spec v1.1 Kap. 6 und 9) — Task 5: angenommene TOPs in die
Beschluss-Sammlung übernehmen, Folgeaufgaben anlegen, Protokoll erzeugen.

Grundsätze:

* **§ 24 Abs. 7 WEG:** Die Beschluss-Sammlung wird fortlaufend je Objekt
  geführt. Einträge werden nie gelöscht und ihr Wortlaut nie geändert;
  Anfechtung und gerichtliche Aufhebung werden ausschließlich vermerkt.
* **Atomar:** Die Übernahme läuft in einer Transaktion. Scheitert ein Schritt,
  bleibt Task 5 offen — eine halb gefüllte Beschluss-Sammlung wäre schlimmer
  als keine.
* **Kein Nachbau vorhandener Logik:** Der Wirtschaftsplan-Beschluss entsteht
  weiterhin über ``buchhaltung.wirtschaftsplan_beschluss_service`` (dort hängen
  Sollstellungskorrektur und HausgeldHistorie). Task 5 legt dafür nur die
  Aufgabe an. Ein Handwerkerauftrag entsteht ebenfalls nicht automatisch —
  ``handwerker.auftrag_service.erstelle_auftrag`` verlangt zwingend einen
  Kreditor, den nur ein Mensch auswählen kann.
"""
import logging

import weasyprint
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.dokumente.models import Dokument
from apps.versammlung.models import Beschluss
from apps.versammlung.services import ev_service, stimmkraft_service

logger = logging.getLogger(__name__)

# Vorgangs-Typ für Folgeaufgaben aus Beschlüssen. Wird per Datenmigration
# (versammlung/0002_seed_vorgangtyp_ev_beschluss) angelegt; der get_or_create
# unten ist nur das Sicherheitsnetz für Umgebungen, in denen der Seed fehlt.
VORGANGTYP_CODE = 'ev-beschluss'
VORGANGTYP_BEZEICHNUNG = 'Beschluss-Umsetzung (EV)'


def _vorgangtyp():
    from apps.vorgaenge.models import VorgangTyp

    typ, erzeugt = VorgangTyp.objects.get_or_create(
        code=VORGANGTYP_CODE,
        defaults={
            'bezeichnung': VORGANGTYP_BEZEICHNUNG,
            'standard_prioritaet': 'normal',
            'sortierung': 60,
            'aktiv': True,
        },
    )
    if erzeugt:
        logger.warning(
            'VorgangTyp "%s" fehlte und wurde zur Laufzeit angelegt — '
            'die Seed-Migration der App versammlung ist offenbar nicht gelaufen.',
            VORGANGTYP_CODE,
        )
    return typ


def anwesenheitsliste(ev) -> list:
    """Teilnehmer mit Stimmkraft, Anwesenheit und Vertretung — für das Protokoll."""
    zeilen = []
    for teilnehmer in (
        ev.teilnehmer.select_related('person', 'vertreten_durch')
        .prefetch_related('anteile').all()
    ):
        vertretung = ''
        if teilnehmer.vertreten_durch_id:
            vertretung = teilnehmer.vertreten_durch.name
        elif teilnehmer.vertreter_name:
            vertretung = teilnehmer.vertreter_name
        zeilen.append({
            'name': teilnehmer.person.name,
            'einheiten': ', '.join(
                a.einheit_nr_snapshot for a in teilnehmer.anteile.all()
            ),
            'stimmkraft': teilnehmer.stimmkraft,
            'anwesend': teilnehmer.ist_anwesend,
            'vertretung': vertretung,
            'hat_vollmacht_dokument': bool(teilnehmer.vollmacht_dokument_id),
        })
    return zeilen


def _beschluss_pdf(beschluss, erstellt_von) -> Dokument:
    """Rendert den Beschluss als eigenes, revisionssicheres DMS-Dokument."""
    html = render_to_string('versammlung/beschluss.html', {
        'beschluss': beschluss,
        'ev': beschluss.ev,
        'objekt': beschluss.objekt,
        'top': beschluss.top,
        'erstellt_am': timezone.now(),
    })
    pdf_bytes = weasyprint.HTML(string=html).write_pdf()
    dateiname = (
        f'Beschluss_{beschluss.nummer:04d}_{beschluss.beschluss_datum:%Y-%m-%d}.pdf'
    )
    return Dokument.objects.create(
        datei=ContentFile(pdf_bytes, name=dateiname),
        dateiname=dateiname,
        kategorie='EV-Beschluss',
        dokument_typ='beschluss',
        beschreibung=(
            f'Beschluss {beschluss.nummer} vom '
            f'{beschluss.beschluss_datum:%d.%m.%Y} — {beschluss.objekt.bezeichnung}'
        ),
        # Owner-Regel B-Hybrid: ausschließlich objekt.
        objekt=beschluss.objekt,
        hochgeladen_von=erstellt_von,
        # § 24 Abs. 7 WEG / GoBD: Beschlüsse sind ab Anlage unveränderlich.
        revisionssicher=True,
        revisionssicher_seit=timezone.now(),
    )


@transaction.atomic
def erzeuge_folgevorgaenge(beschluss, erstellt_von) -> list:
    """Legt die Folgeaufgaben zu einem angenommenen Beschluss an.

    * ``top.triggert_vorgang`` → Vorgang zur Umsetzung (daraus entsteht der
      Handwerkerauftrag später manuell, mit Kreditorauswahl)
    * ``top.triggert_wirtschaftsplan`` → Vorgang zur Erfassung des
      Wirtschaftsplan-Beschlusses über den bestehenden Buchhaltungs-Service

    ``Beschluss.vorgang`` zeigt auf den ersten angelegten Vorgang; bei zwei
    Triggern nennen beide Vorgänge die Beschlussnummer im Text.
    """
    from apps.vorgaenge.services import vorgang_service

    top = beschluss.top
    if top is None:
        return []

    objekt = beschluss.objekt
    betreuer = objekt.betreuer
    erzeugte = []

    if top.triggert_vorgang:
        erzeugte.append(vorgang_service.erstelle_vorgang(
            typ=_vorgangtyp(),
            betreff=f'Beschluss {beschluss.nummer} umsetzen: {top.titel}'[:200],
            erstellt_von=erstellt_von,
            quelle='beschluss',
            objekt=objekt,
            zugewiesen_an=betreuer,
            beschreibung=(
                f'Aus der Eigentümerversammlung vom '
                f'{beschluss.beschluss_datum:%d.%m.%Y}, TOP {top.nummer}.\n\n'
                f'Beschlusswortlaut:\n{beschluss.wortlaut}\n\n'
                f'Abstimmung: Ja {beschluss.ergebnis_ja}, '
                f'Nein {beschluss.ergebnis_nein}, '
                f'Enthaltung {beschluss.ergebnis_enthaltung}.\n\n'
                'Ein Handwerkerauftrag wird bewusst nicht automatisch erzeugt — '
                'dafür muss ein Handwerker ausgewählt werden.'
            ),
        ))

    if top.triggert_wirtschaftsplan:
        erzeugte.append(vorgang_service.erstelle_vorgang(
            typ=_vorgangtyp(),
            betreff=f'Wirtschaftsplan-Beschluss {beschluss.nummer} erfassen'[:200],
            erstellt_von=erstellt_von,
            quelle='beschluss',
            objekt=objekt,
            zugewiesen_an=betreuer,
            beschreibung=(
                f'Beschluss {beschluss.nummer} vom '
                f'{beschluss.beschluss_datum:%d.%m.%Y} (TOP {top.nummer}) ist '
                'anzulegen über Buchhaltung → Wirtschaftsplan-Beschluss '
                '(wirtschaftsplan_beschluss_service). Dort laufen auch die '
                'rückwirkende Sollstellungskorrektur und die '
                'Hausgeld-Historie.\n\n'
                f'Beschlusswortlaut:\n{beschluss.wortlaut}'
            ),
        ))

    if erzeugte and beschluss.vorgang_id is None:
        beschluss.vorgang = erzeugte[0]
        beschluss.save(update_fields=['vorgang'])

    for vorgang in erzeugte:
        ev_service.vermerke_ereignis(
            beschluss.ev, 'vorgang_erzeugt', erstellt_von, top=top,
            text=f'{vorgang.nummer}: {vorgang.betreff}',
            neuer_wert=vorgang.nummer,
        )
    return erzeugte


@transaction.atomic
def uebernimm_in_sammlung(ev, erstellt_von) -> dict:
    """Task 5: angenommene TOPs in die Beschluss-Sammlung übernehmen.

    Je angenommenem TOP entsteht genau ein ``Beschluss`` mit fortlaufender
    Nummer je Objekt, dazu ein revisionssicheres PDF im DMS und die
    konfigurierten Folgeaufgaben. Zum Schluss wird das Protokoll erzeugt und
    der Status auf ``beschluesse_verarbeitet`` gesetzt.

    Idempotent: TOPs, die schon einen Beschluss haben, werden übersprungen —
    ein zweiter Aufruf verdoppelt die Sammlung nicht.
    """
    if ev.status not in ('durchgefuehrt', 'beschluesse_verarbeitet'):
        raise ValidationError(
            'Beschlüsse können erst nach der Durchführung übernommen werden '
            f'(Status ist "{ev.get_status_display()}").'
        )
    if not ev.termin:
        raise ValidationError(
            'Ohne Termin kann kein Beschlussdatum vergeben werden (§ 24 Abs. 7 WEG '
            'verlangt Datum und Ort).'
        )

    angenommen = list(
        ev.tagesordnung.filter(abstimmungsergebnis='angenommen').order_by('nummer')
    )
    ergebnis = {
        'beschluesse': 0, 'uebersprungen': 0, 'vorgaenge': 0,
        'mit_vorgang_trigger': 0, 'mit_wp_trigger': 0, 'nummern': [],
    }

    for top in angenommen:
        if hasattr(top, 'beschluss'):
            ergebnis['uebersprungen'] += 1
            continue

        beschluss = Beschluss(
            objekt=ev.objekt, ev=ev, top=top,
            beschluss_datum=timezone.localtime(ev.termin).date(),
            ort=ev.ort,
            wortlaut=top.beschlussvorlage,
            ergebnis_ja=top.abstimmung_ja,
            ergebnis_nein=top.abstimmung_nein,
            ergebnis_enthaltung=top.abstimmung_enthaltung,
            erstellt_von=erstellt_von,
        )
        beschluss.full_clean()
        beschluss.save()

        beschluss.dokument = _beschluss_pdf(beschluss, erstellt_von)
        beschluss.save(update_fields=['dokument'])

        ergebnis['beschluesse'] += 1
        ergebnis['nummern'].append(beschluss.nummer)
        ev_service.vermerke_ereignis(
            ev, 'beschluss_erzeugt', erstellt_von, top=top,
            text=f'Beschluss {beschluss.nummer} aus TOP {top.nummer}: {top.titel}',
            neuer_wert=str(beschluss.nummer),
        )

        vorgaenge = erzeuge_folgevorgaenge(beschluss, erstellt_von)
        ergebnis['vorgaenge'] += len(vorgaenge)
        if top.triggert_vorgang:
            ergebnis['mit_vorgang_trigger'] += 1
        if top.triggert_wirtschaftsplan:
            ergebnis['mit_wp_trigger'] += 1

    protokoll = erzeuge_protokoll_pdf(ev, erstellt_von)
    ergebnis['protokoll_dokument_id'] = str(protokoll.id)

    if ev.status == 'durchgefuehrt':
        ev_service.wechsle_status(
            ev, 'beschluesse_verarbeitet', erstellt_von,
            text=f'{ergebnis["beschluesse"]} Beschluss/Beschlüsse übernommen.',
        )
    ev_service.markiere_task_erledigt(ev, 5, erstellt_von)
    return ergebnis


@transaction.atomic
def erzeuge_protokoll_pdf(ev, erstellt_von) -> Dokument:
    """Erzeugt das Versammlungsprotokoll und legt es am Objekt ab.

    Enthält Anwesenheitsliste mit Stimmkraft und Vertretungen, die
    Quorum-Angabe (informativ, § 25 Abs. 3 WEG a.F. ist aufgehoben) sowie je
    TOP das Ergebnis und den Beschlusswortlaut.

    Eine erneute Erzeugung ersetzt die Verknüpfung ``ev.protokoll_pdf``; die
    alte Fassung bleibt als Dokument im DMS (GoBD).
    """
    kontext = {
        'ev': ev,
        'objekt': ev.objekt,
        'tagesordnung': list(ev.tagesordnung.order_by('nummer')),
        'anwesenheit': anwesenheitsliste(ev),
        'quorum': stimmkraft_service.berechne_quorum(ev),
        'beschluesse': list(ev.beschluesse.order_by('nummer')),
        'erstellt_am': timezone.now(),
    }
    html = render_to_string('versammlung/protokoll.html', kontext)
    pdf_bytes = weasyprint.HTML(string=html).write_pdf()

    datum = timezone.localtime(ev.termin).date() if ev.termin else timezone.localdate()
    dateiname = f'Protokoll_EV_{datum:%Y-%m-%d}.pdf'
    dokument = Dokument.objects.create(
        datei=ContentFile(pdf_bytes, name=dateiname),
        dateiname=dateiname,
        kategorie='EV-Protokoll',
        dokument_typ='korrespondenz',
        beschreibung=(
            f'Protokoll der Eigentümerversammlung vom {datum:%d.%m.%Y} — '
            f'{ev.objekt.bezeichnung}'
        ),
        objekt=ev.objekt,
        hochgeladen_von=erstellt_von,
    )

    ev.protokoll_pdf = dokument
    ev.save(update_fields=['protokoll_pdf'])
    ev_service.vermerke_ereignis(
        ev, 'protokoll_erzeugt', erstellt_von,
        text=f'Protokoll erzeugt ({len(kontext["beschluesse"])} Beschluss/Beschlüsse).',
        neuer_wert=dateiname,
    )
    return dokument


@transaction.atomic
def vermerke_anfechtung(beschluss, erstellt_von, *, anfechtung_status,
                        notiz='', aufgehoben_am=None, gerichtlicher_hinweis=''):
    """Vermerkt Anfechtung bzw. gerichtliche Aufhebung (§ 24 Abs. 7 WEG).

    Der Wortlaut des Beschlusses bleibt unangetastet — auch ein aufgehobener
    Beschluss bleibt mit seinem Wortlaut in der Sammlung stehen und wird nur
    als aufgehoben gekennzeichnet.
    """
    erlaubt = dict(Beschluss.ANFECHTUNG_CHOICES)
    if anfechtung_status not in erlaubt:
        raise ValidationError(
            f'Unbekannter Anfechtungsstatus: {anfechtung_status} '
            f'(erlaubt: {", ".join(erlaubt)})'
        )
    if anfechtung_status == 'aufgehoben' and not aufgehoben_am:
        raise ValidationError(
            'Für einen gerichtlich aufgehobenen Beschluss ist das Datum der '
            'Aufhebung anzugeben.'
        )

    alt = beschluss.anfechtung_status
    beschluss.anfechtung_status = anfechtung_status
    beschluss.anfechtung_notiz = notiz
    beschluss.aufgehoben_am = aufgehoben_am if anfechtung_status == 'aufgehoben' else None
    beschluss.gerichtlicher_hinweis = gerichtlicher_hinweis
    beschluss.save(update_fields=[
        'anfechtung_status', 'anfechtung_notiz', 'aufgehoben_am',
        'gerichtlicher_hinweis',
    ])

    if beschluss.ev_id:
        ev_service.vermerke_ereignis(
            beschluss.ev, 'kommentar', erstellt_von,
            text=(
                f'Beschluss {beschluss.nummer}: Anfechtungsstatus '
                f'"{erlaubt[anfechtung_status]}". {notiz}'.strip()
            ),
            alter_wert=alt, neuer_wert=anfechtung_status,
        )
    return beschluss
