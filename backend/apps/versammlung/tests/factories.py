"""
Testdaten-Bausteine für die EV-Tests.

Bewusst schlanke Funktionen statt einer Basisklasse: jeder Test baut sich genau
die Konstellation, die er prüft (eine Person mit drei Einheiten, zwei Personen
mit je einer, MEA gepflegt/ungepflegt …).

``personennummer`` und ``objektnummer`` werden immer explizit gesetzt — beide
Felder sind ``unique=True, blank=True`` ohne Auto-Vergabe, ein zweiter
Datensatz mit Leerwert würde also an der Unique-Constraint scheitern.
"""
from datetime import date
from decimal import Decimal
from itertools import count

from django.contrib.auth import get_user_model

from apps.objekte.models import (
    Einheit, Objekt, Verteilerschluessel, VerteilerschluesselWert,
)
from apps.personen.models import EigentumsVerhaeltnis, Person

User = get_user_model()

_zaehler = count(1)


def user(username=None):
    return User.objects.create_user(
        username=username or f'ev-tester-{next(_zaehler)}', password='x',
    )


def objekt(*, typ='WEG', bezeichnung='Test-WEG Versammlung', nummer=None):
    return Objekt.objects.create(
        objektnummer=nummer or f'EV{next(_zaehler):04d}',
        objekt_typ=typ,
        bezeichnung=bezeichnung,
        strasse='Teststraße 1',
        plz='12345',
        ort='Teststadt',
        verwaltung_seit=date(2020, 1, 1),
    )


def einheit(obj, *, nr=None, lage='EG links'):
    laufend = next(_zaehler)
    return Einheit.objects.create(
        objekt=obj,
        einheit_nr=nr or f'{laufend:03d}',
        flaechennummer=f'{laufend:05d}',
        einheit_typ='Wohnung',
        lage=lage,
    )


def person(*, nachname=None, vorname='Max'):
    """Person mit standardmäßig EINDEUTIGEM Nachnamen.

    Der Default ist bewusst durchnummeriert: mit drei gleichnamigen
    "Max Mustermann" in einer EV lassen sich Teilnehmerzeilen in Tests nicht
    mehr über den Namen auseinanderhalten, und Fehlschläge zeigen dann auf die
    falsche Zeile.
    """
    laufend = next(_zaehler)
    return Person.objects.create(
        personennummer=f'P{laufend:05d}',
        person_typ='100',
        anrede='Herr',
        vorname=vorname,
        nachname=nachname or f'Mustermann{laufend:03d}',
    )


def eigentuemer(obj, pers=None, *, nr=None, beginn=date(2021, 1, 1)):
    """Legt eine Einheit an und macht ``pers`` zum aktiven Eigentümer.

    Ohne ``pers`` wird eine neue Person erzeugt. Rückgabe:
    ``(einheit, eigentumsverhaeltnis)``.
    """
    pers = pers or person()
    eh = einheit(obj, nr=nr)
    verhaeltnis = EigentumsVerhaeltnis.objects.create(
        einheit=eh, person=pers, beginn=beginn,
    )
    return eh, verhaeltnis


def verteilerschluessel(obj, werte, *, schluessel='030', vs_typ='kopf',
                        bezeichnung='Anzahl Einheiten Gesamt', wirtschaftsjahr=0,
                        aktiv=True):
    """Legt einen Verteilerschlüssel mit Werten an.

    ``werte``: ``{einheit: Decimal|str|None}`` — ``None`` erzeugt bewusst einen
    beteiligten Eintrag ohne Wert (Prüfung der Fehlerbehandlung). Einheiten,
    die nicht im Dict stehen, sind am Schlüssel nicht beteiligt.
    """
    vs = Verteilerschluessel.objects.create(
        objekt=obj, schluessel=schluessel, bezeichnung=bezeichnung,
        vs_typ=vs_typ, aktiv=aktiv,
    )
    for eh, wert in werte.items():
        VerteilerschluesselWert.objects.create(
            schluessel=vs, einheit=eh, wirtschaftsjahr=wirtschaftsjahr,
            beteiligt=True,
            wert=None if wert is None else Decimal(str(wert)),
        )
    return vs


def einheiten_schluessel(obj, einheiten, **kwargs):
    """VS 030 "Anzahl Einheiten Gesamt": jede Einheit mit Wert 1 — entspricht
    dem Objektprinzip (eine Stimme je Einheit)."""
    return verteilerschluessel(obj, {eh: '1' for eh in einheiten}, **kwargs)


def mea_schluessel(obj, werte, **kwargs):
    """VS 010 "MEA Gesamt" — Wertprinzip."""
    kwargs.setdefault('schluessel', '010')
    kwargs.setdefault('vs_typ', 'mea')
    kwargs.setdefault('bezeichnung', 'MEA Gesamt')
    return verteilerschluessel(obj, werte, **kwargs)


def vs_wert(vs, einheit, wert, *, wirtschaftsjahr=0, beteiligt=True):
    """Ergänzt einen einzelnen Wert an einem bestehenden Verteilerschlüssel —
    z.B. für eine Einheit, die erst nach der Schlüsselanlage dazukommt."""
    return VerteilerschluesselWert.objects.create(
        schluessel=vs, einheit=einheit, wirtschaftsjahr=wirtschaftsjahr,
        beteiligt=beteiligt,
        wert=None if wert is None else Decimal(str(wert)),
    )
