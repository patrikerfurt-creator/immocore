"""Testdaten für die Korrespondenz-Tests (Phase 2).

Ein einziges, vollständiges Szenario (WEG mit Betreuer, Zahlungsverkehrskonto,
Eigentümerwechsel, Mahnung mit offenem Posten ...), damit Test 6 prüfen kann,
dass ALLE dokumentierten Platzhalter eines Anlasses befüllt werden.
"""
from datetime import date
from decimal import Decimal
from itertools import count
from types import SimpleNamespace

from django.contrib.auth import get_user_model

from apps.buchhaltung.models import (
    Basiszinssatz, Buchung, EigentuemerwechselVorgang, Mahnlauf, Mahnung, OffenerPosten,
)
from apps.konten.models import Abrechnungsart, Personenkonto
from apps.mitarbeiter.models import Mitarbeiter
from apps.objekte.models import Bankkonto, Einheit, Objekt
from apps.personen.models import EigentumsVerhaeltnis, HausgeldHistorie, Person, SEPAMandat
from apps.vorgaenge.models import Vorgang, VorgangTyp

User = get_user_model()
_z = count(1)

# Valide deutsche IBAN (Frankfurter Volksbank) - Bankname wird per schwifty abgeleitet.
TEST_IBAN = 'DE02501900006300211010'


def szenario(*, wechsel=True, mahnung=True, vorgang=True, mandat=False):
    """Baut das Gesamtszenario und liefert es als ``SimpleNamespace``."""
    n = next(_z)
    betreuer = User.objects.create_user(
        f'betreuer{n}', password='x', first_name='Anna', last_name='Beispiel',
        email='a.beispiel@demme-immobilien.de',
    )
    Mitarbeiter.objects.create(user=betreuer, telefon='069-96 75 20 90')
    ersteller = User.objects.create_user(f'ersteller{n}', password='x')

    objekt = Objekt.objects.create(
        objektnummer=f'K{n:03d}', objekt_typ='WEG', bezeichnung='WEG Musterstraße 1',
        strasse='Musterstraße 1', plz='60311', ort='Frankfurt am Main',
        verwaltung_seit=date(2020, 1, 1), bundesland='HE', betreuer=betreuer,
        glaeubiger_id='DE98ZZZ09999999999',
    )
    Bankkonto.objects.create(
        objekt=objekt, konto_typ='bewirtschaftung', bezeichnung='Bewirtschaftung',
        iban=TEST_IBAN, bic='FFVBDEFFXXX', kontoinhaber='WEG Musterstraße 1',
        zahlungsverkehr=True,
    )
    einheit = Einheit.objects.create(
        objekt=objekt, einheit_nr='12', flaechennummer='0012',
        einheit_typ='Wohnung', lage='Wohnung 2. OG links',
    )

    person = Person.objects.create(
        personennummer=f'PK{n:04d}', person_typ='100', anrede='Eheleute', titel='Dr.',
        vorname='Max', nachname='Mustermann', vorname2='Erika',
        strasse='Musterweg', hausnummer='5', plz='60311', ort='Frankfurt am Main',
    )
    if mandat:
        person.sepa_mandat = SEPAMandat.objects.create(
            mandatsreferenz=f'MR{n:05d}', iban=TEST_IBAN, unterzeichnet_am=date(2026, 1, 1),
        )
        person.save()

    ev = EigentumsVerhaeltnis.objects.create(einheit=einheit, person=person, beginn=date(2026, 9, 1))
    # Das Personenkonto legt das post_save-Signal von EigentumsVerhaeltnis selbst an.
    konto = Personenkonto.objects.get(vertrag=ev)
    art = Abrechnungsart.objects.create(objekt=objekt, code='900', bezeichnung='Hausgeld')
    HausgeldHistorie.objects.create(
        eigentumsverhaeltnis=ev, abrechnungsart=art, betrag=Decimal('300.00'),
        gueltig_ab=date(2026, 9, 1), quelle='import', import_referenz='test',
        erstellt_von=ersteller,
    )

    ns = SimpleNamespace(
        betreuer=betreuer, ersteller=ersteller, objekt=objekt, einheit=einheit,
        person=person, ev=ev, konto=konto, briefbogen=SimpleNamespace(firma_name='Demme Immobilien Verwaltung GmbH'),
        wechsel=None, mahnung=None, vorgang=None,
    )
    if wechsel:
        ns.wechsel = _wechsel(ns, n)
    if mahnung:
        ns.mahnung = _mahnung(ns)
    if vorgang:
        ns.vorgang = _vorgang(ns)
    return ns


def _wechsel(ns, n):
    vor = Person.objects.create(
        personennummer=f'PV{n:04d}', person_typ='100', anrede='Herr',
        vorname='Hans', nachname='Alt',
    )
    # Der Voreigentümer war bis zum Wechsel aktiv; die Einheit trägt nur EIN aktives EV.
    vor_ev = EigentumsVerhaeltnis.objects.create(
        einheit=ns.einheit, person=vor, beginn=date(2010, 1, 1), ende=date(2026, 8, 31),
    )
    return EigentuemerwechselVorgang.objects.create(
        objekt=ns.objekt, einheit=ns.einheit, voreigentuemer_ev=vor_ev,
        neueigentuemer_ev=ns.ev, wechsel_datum=date(2026, 9, 1),
        meldedatum=date(2026, 9, 5), erstellt_von=ns.ersteller,
    )


def _mahnung(ns):
    Basiszinssatz.objects.get_or_create(gueltig_ab=date(2020, 1, 1), defaults={'satz': Decimal('3.62')})
    lauf = Mahnlauf.objects.create(objekt=ns.objekt, ausgefuehrt_von=ns.ersteller)
    buchung = Buchung.objects.create(
        objekt=ns.objekt, betrag=Decimal('350.00'), buchungsdatum=date(2026, 8, 1),
        buchungstext='Hausgeld 08/2026',
    )
    OffenerPosten.objects.create(
        buchung=buchung, personenkonto=ns.konto, betrag_ursprung=Decimal('350.00'),
        betrag_offen=Decimal('350.00'), faellig_ab=date(2026, 8, 1),
    )
    return Mahnung.objects.create(
        lauf=lauf, personenkonto=ns.konto, mahnstufe=1,
        offene_posten_summe=Decimal('350.00'), gebuehr=Decimal('5.00'), zinsen=Decimal('1.20'),
    )


def _vorgang(ns):
    typ, _ = VorgangTyp.objects.get_or_create(code='test', defaults={'bezeichnung': 'Test'})
    return Vorgang.objects.create(
        typ=typ, objekt=ns.objekt, einheit=ns.einheit, person=ns.person,
        betreff='Schaden im Treppenhaus', erstellt_von=ns.ersteller,
    )
