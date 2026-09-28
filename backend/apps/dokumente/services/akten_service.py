"""
Akten: Haus-, Wohnungs- und Eigentuemerakte.

GRUNDGEDANKE — Akten sind SICHTEN, keine Ablageorte.

Ein Dokument hat genau einen Owner (Objekt, Einheit, Vorgang oder Person,
siehe ``Dokument.clean``). Es liegt also genau einmal im System. Die Akten
sammeln es ueber den Beziehungsgraphen ein: Ein Kaufvertrag an Einheit W5
erscheint in der Wohnungsakte W5, in der Hausakte des Objekts und in der
Eigentuemerakte dessen, dem W5 gehoert — ohne dass die Datei dreimal
existiert.

Genau das loest die Ueberschneidung, die sonst zum Problem wird: Ein
Eigentuemer mit drei Wohnungen in zwei Objekten hat EINE Eigentuemerakte,
die Dokumente aus beiden Objekten zusammenfuehrt, waehrend dieselben
Dokumente in den jeweiligen Haus- und Wohnungsakten stehen bleiben.

ZEITLICHE ABGRENZUNG DER EIGENTUEMERAKTE (Entscheidung Patrik):

Verkauft jemand seine Wohnung, zeigt seine Akte nur noch Dokumente aus
SEINER Besitzzeit. Der Nachfolger sieht den Schriftwechsel des Vorbesitzers
nicht, und der Vorbesitzer sieht nicht, was danach kam. Persoenliche
Dokumente (SEPA-Mandat, Schriftwechsel mit ihm) bleiben davon unberuehrt —
die haengen an der Person, nicht an der Einheit.

Maßgeblich ist ``Dokument.dokument_datum`` (das fachliche Datum), ersatzweise
``hochgeladen_am``. Der Unterschied ist praktisch: Eine 2019er Rechnung, die
2026 nachgereicht wird, faellt ueber das Ablagedatum in die Zeit des
FALSCHEN Eigentuemers — deshalb sollte das fachliche Datum gepflegt sein.
"""
import logging

from django.db.models import Q

from apps.dokumente.models import Aktenregister, Dokument
from apps.personen.models import EigentumsVerhaeltnis

logger = logging.getLogger(__name__)

# Sammelbezeichnung fuer Dokumente, die noch keinem Register zugeordnet sind.
# Sie duerfen NICHT aus der Akte verschwinden, nur weil niemand sie
# einsortiert hat — sonst waere die Ablage lueckenhaft, ohne dass es auffaellt.
OHNE_REGISTER = 'Ohne Register'


def hausakte(objekt) -> Q:
    """Filter fuer alle Dokumente, die zur Hausakte eines Objekts gehoeren.

    Nutzt ``DokumentQuerySet.fuer_objekt`` — dort steht die Aufloesung des
    Beziehungsgraphen (Objekt, Einheiten, Vorgaenge, Rechnungen).
    """
    return Dokument.objects.fuer_objekt(objekt)


def wohnungsakte(einheit):
    """Alle Dokumente zu einer Einheit, samt Vorgaengen dieser Einheit."""
    return Dokument.objects.fuer_einheit(einheit)


def eigentuemerakte(person, *, nur_aktuelle_evs: bool = False):
    """Dokumente eines Eigentuemers — begrenzt auf seine Besitzzeit.

    Zusammengesetzt aus:

    1. Dokumenten, die direkt an der Person haengen (immer, zeitunabhaengig)
    2. Dokumenten seiner Vorgaenge (immer — er hat sie ausgeloest)
    3. Dokumenten seiner Einheiten, begrenzt auf den jeweiligen
       Eigentumszeitraum

    ``nur_aktuelle_evs=True`` blendet beendete Eigentumsverhaeltnisse aus —
    fuer die Frage "was gehoert dem heute", nicht "was ihn je betraf".
    """
    evs = EigentumsVerhaeltnis.objects.filter(person=person).select_related('einheit')
    if nur_aktuelle_evs:
        evs = evs.filter(ende__isnull=True)

    filter_ausdruck = Q(person=person) | Q(vorgang__person=person)

    for ev in evs:
        zeitraum = Q(einheit=ev.einheit)
        # Datumsgrenzen auf BEIDE Datumsfelder anwenden: das fachliche Datum
        # hat Vorrang, fehlt es, zaehlt das Ablagedatum.
        if ev.beginn:
            zeitraum &= (Q(dokument_datum__gte=ev.beginn)
                         | Q(dokument_datum__isnull=True,
                             hochgeladen_am__date__gte=ev.beginn))
        if ev.ende:
            zeitraum &= (Q(dokument_datum__lte=ev.ende)
                         | Q(dokument_datum__isnull=True,
                             hochgeladen_am__date__lte=ev.ende))
        filter_ausdruck |= zeitraum

    return Dokument.objects.filter(filter_ausdruck).distinct()


def register_einer_akte(aktenart: str, objekt=None):
    """Die Register, die in dieser Akte gelten.

    Zwei Quellen, zusammengefuehrt: die gemeinsame Gliederung (``objekt``
    leer) und die Untergliederung, die jemand fuer GENAU DIESES Objekt
    angelegt hat — das digitale Trennblatt, etwa "05/A Hebeanlage" unter
    "05 Wartung". Ohne ``objekt`` bleiben nur die gemeinsamen Register.
    """
    register = (Aktenregister.objects
                .filter(aktiv=True)
                .filter(Q(aktenart=aktenart) | Q(aktenart=Aktenregister.AKTENART_ALLE)))
    if objekt is not None:
        register = register.filter(Q(objekt__isnull=True) | Q(objekt=objekt))
    else:
        register = register.filter(objekt__isnull=True)
    # Unterregister direkt hinter ihr Elternregister: erst nach dem Rang des
    # Elternteils sortieren, dann innerhalb.
    return register.select_related('eltern', 'objekt').order_by(
        'sortierung', 'code')


def _baumreihenfolge(register: list) -> list:
    """Sortiert flach, aber so, dass jedes Unterregister direkt hinter seinem
    Elternregister steht — sonst stuende "05/A Hebeanlage" irgendwo hinter
    "17 Rechtsangelegenheiten"."""
    kinder: dict = {}
    for r in register:
        kinder.setdefault(r.eltern_id, []).append(r)

    geordnet: list = []

    def anhaengen(eltern_id):
        for r in kinder.get(eltern_id, []):
            geordnet.append(r)
            anhaengen(r.id)

    anhaengen(None)
    # Register, deren Elternteil in dieser Akte nicht sichtbar ist, gehen
    # sonst verloren — hinten anhaengen statt verschlucken.
    fehlend = [r for r in register if r not in geordnet]
    return geordnet + fehlend


def nach_registern(dokumente, aktenart: str, objekt=None) -> list[dict]:
    """Gruppiert eine Dokumentenmenge nach Registern — die Aktenansicht.

    Liefert die Register der Aktenart IN DER GEPFLEGTEN REIHENFOLGE, auch
    die leeren: eine Akte, in der "Versicherungen" fehlt, weil noch nichts
    abgelegt wurde, sieht aus wie eine Akte ohne Versicherungsbedarf. Leere
    Register zeigen dagegen, wo etwas fehlt.

    ``objekt`` blendet zusaetzlich die Untergliederung dieses Objekts ein.

    Dokumente ohne Register kommen am Ende unter ``OHNE_REGISTER``.
    """
    dokumente = list(dokumente.select_related('register'))

    register = _baumreihenfolge(list(register_einer_akte(aktenart, objekt)))

    nach_id: dict = {r.id: [] for r in register}
    ohne: list = []
    for dokument in dokumente:
        if dokument.register_id in nach_id:
            nach_id[dokument.register_id].append(dokument)
        else:
            # Auch Dokumente in einem Register EINER ANDEREN Aktenart landen
            # hier — sie gehen sonst in dieser Sicht verloren.
            ohne.append(dokument)

    def ebene(r) -> int:
        tiefe, knoten = 0, r.eltern
        while knoten is not None:
            tiefe += 1
            knoten = knoten.eltern
        return tiefe

    gruppen = [{
        'register': r,
        'code': r.code,
        'bezeichnung': r.bezeichnung,
        'pfad': r.voller_pfad,
        'eltern_id': r.eltern_id,
        'ebene': ebene(r),
        # Nur fuer dieses Objekt angelegt — in der Oberflaeche kenntlich zu
        # machen, damit niemand eine objektspezifische Untergliederung fuer
        # Teil der gemeinsamen Ordnung haelt.
        'objektspezifisch': r.objekt_id is not None,
        'dokumente': nach_id[r.id],
        'anzahl': len(nach_id[r.id]),
    } for r in register]

    if ohne:
        gruppen.append({
            'register': None,
            'code': '',
            'bezeichnung': OHNE_REGISTER,
            'pfad': OHNE_REGISTER,
            'eltern_id': None,
            'ebene': 0,
            'objektspezifisch': False,
            'dokumente': ohne,
            'anzahl': len(ohne),
        })
    return gruppen
