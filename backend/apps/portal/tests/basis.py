"""
Gemeinsame Testdaten für die Portal-Tests.

``cache.clear()`` gehört in jedes ``setUp``: sowohl der DRF-``ScopedRateThrottle``
als auch der Zähler des fachlichen Rate-Limits (Spec Kap. 3.3) liegen im
Django-Cache (hier echtes Redis) — der wird NICHT durch die Test-Transaktion
zurückgerollt. Ohne Zurücksetzen scheitern wiederholte Testläufe innerhalb
derselben Stunde am Limit.
"""
from datetime import date

from apps.objekte.models import Einheit, Objekt, Verteilerschluessel, VerteilerschluesselWert
from apps.personen.models import EigentumsVerhaeltnis, Person, SEPAMandat


def erstelle_objekt(nr='PORTAL001', bezeichnung='WEG Portalweg 1') -> Objekt:
    return Objekt.objects.create(
        objektnummer=nr, objekt_typ='WEG', bezeichnung=bezeichnung,
        strasse='Portalweg 1', plz='12345', ort='Musterstadt',
        verwaltung_seit=date(2020, 1, 1),
    )


def erstelle_einheit(objekt, nr='0001', lage='EG links', mea=None) -> Einheit:
    einheit = Einheit.objects.create(
        objekt=objekt, einheit_nr=nr, einheit_typ='Wohnung', lage=lage,
    )
    if mea is not None:
        schluessel, _ = Verteilerschluessel.objects.get_or_create(
            objekt=objekt, bezeichnung='MEA',
            defaults={'schluessel': '010', 'vs_typ': 'mea'},
        )
        VerteilerschluesselWert.objects.create(
            schluessel=schluessel, einheit=einheit, wirtschaftsjahr=0,
            beteiligt=True, wert=mea,
        )
    return einheit


def erstelle_eigentuemer(
    nachname='Musterfrau', email='eigentuemer@example.org',
    personennummer='P-PORTAL-1', strasse='Altstraße', hausnummer='1',
    plz='12345', ort='Altstadt', telefon='0123 4567',
) -> Person:
    return Person.objects.create(
        personennummer=personennummer, person_typ='100', anrede='Frau',
        vorname='Erika', nachname=nachname,
        email=email, emails=[email],
        telefon=telefon, telefonnummern=[telefon],
        # 'adresse' setzt Person.save() aus diesen Feldern zusammen.
        strasse=strasse, hausnummer=hausnummer, plz=plz, ort=ort,
    )


def verknuepfe(person, einheit, beginn=date(2021, 1, 1), ende=None) -> EigentumsVerhaeltnis:
    return EigentumsVerhaeltnis.objects.create(
        person=person, einheit=einheit, beginn=beginn, ende=ende,
    )


def erstelle_mandat(person, referenz='MND-PORTAL-1', iban='DE02120300000000202051',
                    bic='BYLADEM1001', aktiv=True) -> SEPAMandat:
    mandat = SEPAMandat.objects.create(
        mandatsreferenz=referenz, iban=iban, bic=bic,
        unterzeichnet_am=date(2021, 1, 1), aktiv=aktiv,
    )
    person.sepa_mandat = mandat
    person.ibans = [iban]
    person.save(update_fields=['sepa_mandat', 'ibans'])
    return mandat
