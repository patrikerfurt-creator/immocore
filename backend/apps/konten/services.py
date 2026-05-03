import csv
from pathlib import Path

from django.db.models import Max

from .models import Abrechnungsart, Konto, Personenkonto


FIXTURE_PATH = Path(__file__).resolve().parent.parent.parent / 'fixtures' / 'musterkontenrahmen_weg.csv'

MUSTER_ABRECHNUNGSARTEN = [
    ('900', 'Hausgeld'),
    ('911', 'Rücklage I'),
    ('930', 'Sonderumlage'),
    ('940', 'Mahngebühren'),
    ('941', 'Rücklastschriftgebühren'),
    ('950', 'Abrechnung Vorjahr'),
]

_ROMAN = [(1000,'M'),(900,'CM'),(500,'D'),(400,'CD'),(100,'C'),(90,'XC'),
          (50,'L'),(40,'XL'),(10,'X'),(9,'IX'),(5,'V'),(4,'IV'),(1,'I')]

def _roman(n: int) -> str:
    result = ''
    for v, s in _ROMAN:
        while n >= v:
            result += s
            n -= v
    return result


def personenkonto_anlegen(ev, objekt) -> tuple:
    """Legt Personenkonto für ein EigentumsVerhaeltnis an. Gibt (pk, created) zurück."""
    try:
        return ev.personenkonto, False
    except Personenkonto.DoesNotExist:
        pass

    max_nr = (
        Personenkonto.objects.filter(objekt=objekt)
        .aggregate(m=Max('kontonummer'))['m']
    )
    if max_nr is None:
        naechste = '1000'
    else:
        try:
            naechste = str(int(max_nr) + 1).zfill(4)
        except ValueError:
            used = set(Personenkonto.objects.filter(objekt=objekt).values_list('kontonummer', flat=True))
            n = 1000
            while str(n) in used:
                n += 1
            naechste = str(n)

    pk = Personenkonto.objects.create(
        objekt=objekt,
        eigentuemer=ev.person,
        vertrag=ev,
        kontonummer=naechste,
        status='aktiv',
    )
    return pk, True


def kontenrahmen_anlegen(objekt_id: str) -> dict:
    """Legt alle 70 Muster-Sachkonten für ein WEG-Objekt an. Idempotent."""
    from apps.objekte.models import Objekt
    objekt = Objekt.objects.get(pk=objekt_id)
    if objekt.objekt_typ != 'WEG':
        raise ValueError('Musterkontenrahmen gilt nur für WEG-Objekte.')

    angelegt = 0
    with open(FIXTURE_PATH, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            _, created = Konto.objects.get_or_create(
                objekt=objekt,
                kontonummer=row['kontonummer'],
                defaults={
                    'kontoname':          row['kontoname'],
                    'abrechnungsart':     row['abrechnungsart'] or None,
                    'direktes_buchen':    row['direktes_buchen'] == 'ja',
                    'verteilerschluessel': row['verteilerschluessel'] or None,
                    'kontoart':           row['kontoart'],
                    'arge_konto':         row['arge_konto'] == 'ja',
                    'arge_kostenart':     row['arge_kostenart'] or None,
                    'aktiv':              True,
                },
            )
            if created:
                angelegt += 1
    return {'angelegt': angelegt}


def abrechnungsarten_anlegen(objekt_id: str, ruecklagen: list | None = None) -> int:
    """Legt die 6 Standard-Abrechnungsarten + ggf. Rücklage II+ an. Idempotent."""
    from apps.objekte.models import Objekt
    objekt = Objekt.objects.get(pk=objekt_id)
    angelegt = 0

    for code, bezeichnung in MUSTER_ABRECHNUNGSARTEN:
        _, created = Abrechnungsart.objects.get_or_create(
            objekt=objekt, code=code,
            defaults={'bezeichnung': bezeichnung, 'aktiv': True},
        )
        if created:
            angelegt += 1

    for r in (ruecklagen or []):
        reihenfolge = int(r.get('reihenfolge', 0))
        if reihenfolge <= 1:
            continue
        code = str(910 + reihenfolge)
        _, created = Abrechnungsart.objects.get_or_create(
            objekt=objekt, code=code,
            defaults={'bezeichnung': f'Rücklage {_roman(reihenfolge)}', 'aktiv': True},
        )
        if created:
            angelegt += 1

    return angelegt


MUSTER_VS = [
    # (schluessel, vs_typ, bezeichnung, einheit_einheit, reihenfolge)
    ('001', 'flaeche',   'Wohnfläche',               'qm',  1),
    ('010', 'mea',       'MEA Gesamt',               'TEL', 10),
    ('030', 'kopf',      'Anzahl Einheiten Gesamt',  '',    30),
    ('031', 'kopf',      'Anzahl Wohnungen',         '',    31),
    ('032', 'kopf',      'Anzahl Stellplätze',       '',    32),
    ('100', 'direkt',    'Direktkosten Eigentümer',  '',   100),
    ('140', 'verbrauch', 'Heizkosten nach Verbrauch','kWh',140),
]

_ZEITLOS_TYPEN = {'flaeche', 'mea', 'kopf', 'direkt'}


def verteilerschluessel_anlegen(objekt_id: str) -> int:
    """Legt 7 Muster-Verteilerschlüssel + VSBeteiligung für vorhandene Einheiten an.
    Idempotent. Gibt Anzahl neu angelegter VS zurück.
    """
    import datetime as dt
    from decimal import Decimal
    from apps.objekte.models import Objekt, Verteilerschluessel, VerteilerschluesselWert

    objekt    = Objekt.objects.prefetch_related('einheiten').get(pk=objekt_id)
    einheiten = list(objekt.einheiten.all())
    aktuelles_jahr = dt.date.today().year
    angelegt  = 0

    for schluessel, vs_typ, bezeichnung, einheit_einheit, reihenfolge in MUSTER_VS:
        vs, created = Verteilerschluessel.objects.get_or_create(
            objekt=objekt,
            schluessel=schluessel,
            defaults={
                'bezeichnung':   bezeichnung,
                'vs_typ':        vs_typ,
                'aktiv':         True,
                'schluessel_typ': vs_typ,
                'einheit':       einheit_einheit,
                'reihenfolge':   reihenfolge,
            },
        )
        if created:
            angelegt += 1

        if vs_typ == 'direkt' or not einheiten:
            continue

        wj = 0 if vs_typ in _ZEITLOS_TYPEN else aktuelles_jahr

        for einheit in einheiten:
            beteiligt = True
            if vs_typ == 'kopf' and schluessel == '031':
                beteiligt = einheit.einheit_typ == 'Wohnung'
            elif vs_typ == 'kopf' and schluessel == '032':
                beteiligt = einheit.einheit_typ == 'Stellplatz'

            wert   = None
            quelle = 'stammdaten'
            if vs_typ == 'kopf':
                wert = Decimal('1.0000')
            elif vs_typ == 'verbrauch':
                quelle = 'manuell'

            VerteilerschluesselWert.objects.get_or_create(
                schluessel=vs,
                einheit=einheit,
                wirtschaftsjahr=wj,
                defaults={
                    'beteiligt':          beteiligt,
                    'wert':               wert,
                    'einzelwert_einheit': einheit_einheit,
                    'quelle':             quelle,
                },
            )

    return angelegt


def ruecklagen_konten_anlegen(objekt_id: str, ruecklagen: list) -> int:
    """Legt Sachkonten für Rücklage II+ an (3 Konten je Rücklage).
    ruecklagen: list of dicts mit 'reihenfolge' und 'bezeichnung'.
    Rücklage I (reihenfolge=1) ist bereits im Musterkontenrahmen.
    """
    from apps.objekte.models import Objekt
    objekt = Objekt.objects.get(pk=objekt_id)
    angelegt = 0
    for r in ruecklagen:
        reihenfolge = int(r['reihenfolge'])
        if reihenfolge <= 1:
            continue  # Rücklage I ist im Musterkontenrahmen
        n = 910 + reihenfolge
        assert n != 910, 'Suffix .910 darf niemals vergeben werden'
        abr = str(n)
        konten_defs = [
            {'kontonummer': f'0991{reihenfolge}', 'kontoname': f'Bank {n} Rücklage {reihenfolge}',
             'abrechnungsart': abr, 'direktes_buchen': False, 'verteilerschluessel': None,
             'kontoart': 'standard', 'arge_konto': False},
            {'kontonummer': f'5791{reihenfolge}', 'kontoname': f'Rücklage {reihenfolge}',
             'abrechnungsart': abr, 'direktes_buchen': False, 'verteilerschluessel': '010',
             'kontoart': 'standard', 'arge_konto': False},
            {'kontonummer': f'4191{reihenfolge}', 'kontoname': f'Erlöse Rücklage {reihenfolge}',
             'abrechnungsart': abr, 'direktes_buchen': False, 'verteilerschluessel': None,
             'kontoart': 'standard', 'arge_konto': False},
        ]
        for kd in konten_defs:
            _, created = Konto.objects.get_or_create(
                objekt=objekt, kontonummer=kd['kontonummer'],
                defaults={**kd, 'arge_kostenart': None, 'aktiv': True},
            )
            if created:
                angelegt += 1
    return angelegt
