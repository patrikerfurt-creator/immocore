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

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db.models import Q

from apps.dokumente.models import Aktenregister, Dokument
from apps.personen.models import EigentumsVerhaeltnis

logger = logging.getLogger(__name__)

# Sammelbezeichnung fuer Dokumente, die noch keinem Register zugeordnet sind.
# Sie duerfen NICHT aus der Akte verschwinden, nur weil niemand sie
# einsortiert hat — sonst waere die Ablage lueckenhaft, ohne dass es auffaellt.
OHNE_REGISTER = 'Ohne Register'

# Gegenstueck fuer die Kreditorenakte: Belege, deren Rechnung kein Objekt
# traegt. Sollte selten sein, darf aber nicht unsichtbar werden.
OHNE_OBJEKT = 'Ohne Objekt'

# Register der Hausakte, unter dem jede Eigentuemerversammlung eine eigene
# Untergliederung bekommt ("16/A", "16/B" …). Siehe Seed-Migration
# dokumente 0013; das Elternregister ist global (objekt=None).
EV_REGISTER_CODE = '16'


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


def kreditorakte(kreditor):
    """Alle Dokumente eines Kreditors.

    Der einzige Weg, auf dem ein Dokument an einem Kreditor haengt, ist der
    Rechnungsbeleg: ``Dokument`` ←(beleg_dokument)– ``Rechnung`` –(kreditor)→
    ``Kreditor``. Deshalb genau dieser eine Lookup — es gibt keinen direkten
    FK vom Dokument auf den Kreditor.
    """
    return (Dokument.objects
            .filter(rechnung__kreditor=kreditor)
            .select_related('rechnung', 'rechnung__objekt', 'rechnung__kreditor')
            .distinct())


def nach_objekten(dokumente) -> list[dict]:
    """Gruppiert die Belege eines Kreditors nach der Liegenschaft ihrer Rechnung.

    Das ist die Sicht der Kreditorenakte: anders als die register-gegliederten
    Akten gibt es hier keine Register, sondern eine Gruppe je Objekt. Belege
    ohne Objekt kommen am Ende unter ``OHNE_OBJEKT`` — sie gehen sonst verloren.
    Nur Objekte mit Belegen erscheinen (keine leeren Gruppen wie bei den
    Registern, denn ein Kreditor hat mit den meisten Objekten nichts zu tun).
    """
    dokumente = list(dokumente)
    nach_id: dict = {}
    reihenfolge: list = []
    ohne: list = []
    for dokument in dokumente:
        try:
            objekt = dokument.rechnung.objekt
        except ObjectDoesNotExist:
            objekt = None
        if objekt is None:
            ohne.append(dokument)
            continue
        if objekt.id not in nach_id:
            nach_id[objekt.id] = {'objekt': objekt, 'dokumente': []}
            reihenfolge.append(objekt.id)
        nach_id[objekt.id]['dokumente'].append(dokument)

    reihenfolge.sort(key=lambda oid: nach_id[oid]['objekt'].objektnummer or '')
    gruppen = [{
        'objekt_id': str(nach_id[oid]['objekt'].id),
        'objektnummer': nach_id[oid]['objekt'].objektnummer or '',
        'bezeichnung': nach_id[oid]['objekt'].bezeichnung,
        'dokumente': nach_id[oid]['dokumente'],
        'anzahl': len(nach_id[oid]['dokumente']),
    } for oid in reihenfolge]

    if ohne:
        gruppen.append({
            'objekt_id': None,
            'objektnummer': '',
            'bezeichnung': OHNE_OBJEKT,
            'dokumente': ohne,
            'anzahl': len(ohne),
        })
    return gruppen


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


# ---------------------------------------------------------------------------
# Untergliederung je Eigentuemerversammlung (16/A, 16/B …)
# ---------------------------------------------------------------------------

def _suffix_zu_zahl(suffix: str) -> int:
    """"A"->1, "Z"->26, "AA"->27 … (bijektive Basis 26, wie Tabellenspalten)."""
    zahl = 0
    for zeichen in suffix:
        zahl = zahl * 26 + (ord(zeichen) - ord('A') + 1)
    return zahl


def _zahl_zu_suffix(zahl: int) -> str:
    """Umkehrung von ``_suffix_zu_zahl``: 1->"A", 26->"Z", 27->"AA"."""
    zeichen = []
    while zahl > 0:
        zahl, rest = divmod(zahl - 1, 26)
        zeichen.append(chr(ord('A') + rest))
    return ''.join(reversed(zeichen))


def _ev_elternregister() -> Aktenregister:
    eltern = (Aktenregister.objects
              .filter(code=EV_REGISTER_CODE, objekt__isnull=True)
              .first())
    if eltern is None:
        raise ValidationError(
            f'Das Hausakten-Register "{EV_REGISTER_CODE}" '
            '(Eigentümerversammlungen) fehlt — bitte die Seed-Migration '
            'dokumente 0013 prüfen.')
    return eltern


def _naechster_suffix(eltern: Aktenregister, objekt) -> str:
    """Naechster freier Buchstabe unter ``eltern`` fuer dieses Objekt.

    Zaehlt vom hoechsten vorhandenen Suffix aus weiter — Luecken durch
    geloeschte Register werden bewusst NICHT wieder aufgefuellt, damit ein
    einmal vergebener Code (und die daran haengenden Dokumente) eindeutig
    bleibt.
    """
    praefix = f'{eltern.code}/'
    hoechste = 0
    for register in eltern.unterregister.filter(objekt=objekt):
        if not register.code.startswith(praefix):
            continue
        suffix = register.code[len(praefix):]
        if suffix and suffix.isalpha() and suffix.isupper():
            hoechste = max(hoechste, _suffix_zu_zahl(suffix))
    return _zahl_zu_suffix(hoechste + 1)


def sync_ev_unterregister(ev) -> Aktenregister:
    """Legt die Hausakten-Untergliederung einer EV an oder zieht ihren Namen nach.

    Aufgerufen beim Erledigen von Task 1 (Terminierung). Idempotent ueber
    ``ev.hausakte_register``:

    * Noch kein Register -> naechstes freies "16/x" fuer das Objekt anlegen,
      Bezeichnung = Arbeitsname.
    * Register vorhanden (z.B. nach Reset + erneutem Erledigen) -> KEIN neues
      anlegen. Nur die Bezeichnung auf den aktuellen Arbeitsnamen nachziehen;
      bereits in "16/x" abgelegte Dokumente bleiben unberuehrt und erscheinen
      sofort unter dem neuen Namen, weil sie am Register haengen, nicht am Text.

    Setzt ``ev.hausakte_register`` NICHT selbst — das uebernimmt der Aufrufer
    (ev_service), damit Flag, Audit-Eintrag und FK in einer Transaktion
    zusammenbleiben. Gibt das Register zurueck.
    """
    bezeichnung = (ev.arbeitsname or '').strip()

    register = ev.hausakte_register
    if register is not None:
        if bezeichnung and register.bezeichnung != bezeichnung:
            register.bezeichnung = bezeichnung
            register.save(update_fields=['bezeichnung'])
        return register

    eltern = _ev_elternregister()
    return Aktenregister.objects.create(
        code=f'{eltern.code}/{_naechster_suffix(eltern, ev.objekt)}',
        objekt=ev.objekt,
        bezeichnung=bezeichnung,
        aktenart=Aktenregister.AKTENART_HAUS,
        eltern=eltern,
        # Gleiche Sortierung wie das Elternregister: die Unterregister
        # bleiben als Gruppe unter "16" und vor "17"; die Reihenfolge
        # untereinander ergibt sich aus dem Code.
        sortierung=eltern.sortierung,
    )
