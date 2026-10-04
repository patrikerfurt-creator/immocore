"""Kontext-Aufbau der Platzhalter-Registry (Spec 4.2, Teil "Funktion").

``baue_kontext`` liest echte Referenzen (Person, Objekt, Einheit, Mahnung,
Eigentümerwechsel, Vorgang, Eingabewerte) und liefert ein reines Datenwörterbuch
``{gruppe: {name: wert}}`` mit Primitiven (str, int, bool, date, Decimal, Listen
und Dicts davon). Die Render-Engine sieht nie Modelle.

Grundsatz "keine leeren oder falschen Werte": ein Wert, der nicht ermittelt
werden kann (kein Betreuer, kein eindeutiges Bankkonto, kein Personenkonto ...),
fehlt im Kontext. Verwendet ihn eine Vorlage, endet der Render kontrolliert mit
einem Fehler ("nicht erzeugbar") statt mit einer leeren Stelle im Brief.
Ausnahmen sind ausdrücklich optionale Angaben (``briefanrede2``, ``ihr_zeichen``).

Jede ``_gruppe_*``-Funktion baut genau eine Gruppe; ``baue_kontext`` filtert
zum Schluss hart auf die in ``registry`` dokumentierten Namen (Test 6).
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.utils import timezone

from . import fristen_service, registry
from .anschrift_service import anschrift_zeilen

VERZUGSZINS_AUFSCHLAG = Decimal('5')  # Verbraucher, wie zinsen.berechne_verzugszinsen


@dataclass
class _Refs:
    """Aufgelöste Referenzen für alle Gruppen-Builder (nur intern)."""
    anlass: str
    person: object
    objekt: object = None
    einheit: object = None
    ev: object = None
    versammlung: object = None
    mahnung: object = None
    wechsel: object = None
    vorgang: object = None
    eingabewerte: dict = None
    parameter: dict = None
    unterzeichner: object = None
    briefbogen: object = None
    schreiben_nummer: str = ''
    ihr_zeichen: str = ''
    ihr_schreiben_vom: date = None
    heute: date = None


# --------------------------------------------------------------------------
# Referenz-Auflösung
# --------------------------------------------------------------------------

def _ermittle_ev(person, einheit, eigentumsverhaeltnis, mahnung, wechsel):
    """Eigentumsverhältnis des Empfängers: explizit > Mahnung > Wechsel > Einheit."""
    if eigentumsverhaeltnis is not None:
        return eigentumsverhaeltnis
    if mahnung is not None:
        return mahnung.personenkonto.vertrag
    if person is None:                    # neutrale EV-Einladung: kein Empfänger
        return None
    if wechsel is not None:
        if wechsel.voreigentuemer_ev.person_id == person.id:
            return wechsel.voreigentuemer_ev
        return wechsel.neueigentuemer_ev
    if einheit is not None:
        from apps.personen.models import EigentumsVerhaeltnis
        return EigentumsVerhaeltnis.objects.filter(
            person=person, einheit=einheit, ende__isnull=True,
        ).first()
    return None


def _ermittle_einheit(einheit, ev, wechsel, vorgang):
    if einheit is not None:
        return einheit
    if ev is not None:
        return ev.einheit
    if wechsel is not None:
        return wechsel.einheit
    if vorgang is not None:
        return vorgang.einheit
    return None


def _ermittle_objekt(objekt, einheit, mahnung, wechsel, vorgang):
    if objekt is not None:
        return objekt
    if einheit is not None:
        return einheit.objekt
    if mahnung is not None:
        return mahnung.lauf.objekt
    if wechsel is not None:
        return wechsel.objekt
    if vorgang is not None:
        return vorgang.objekt
    return None


def _ermittle_personenkonto(r: _Refs):
    """Personenkonto des Empfängers im Objekt; ``None`` wenn nicht eindeutig."""
    if r.mahnung is not None:
        return r.mahnung.personenkonto
    if r.ev is not None:
        # Reverse-OneToOne: RelatedObjectDoesNotExist ist zugleich AttributeError.
        return getattr(r.ev, 'personenkonto', None)
    if r.objekt is None or r.person is None:
        return None
    from apps.konten.models import Personenkonto
    konten = Personenkonto.objects.filter(
        objekt=r.objekt, eigentuemer=r.person, status='aktiv',
    )
    if r.einheit is not None:
        konten = konten.filter(vertrag__einheit=r.einheit)
    konten = list(konten[:2])
    return konten[0] if len(konten) == 1 else None


def _ermittle_briefbogen(briefbogen):
    if briefbogen is not None:
        return briefbogen
    from apps.korrespondenz.models import Briefbogen
    return Briefbogen.objects.filter(ist_standard=True, aktiv=True).first()


def _ermittle_bankkonto(objekt):
    """Zahlungsverkehrskonto des WEG-Objekts; ``None`` bei 0 oder >1 Treffern.

    Regel gemäß Bestandsaufnahme E1 (Patrik 2026-09-29): ``zahlungsverkehr=True``
    und ``aktiv=True`` ersetzt die Sachkonto-18000-Verknüpfung aus Spec 5.4.
    """
    if objekt is None or objekt.objekt_typ != 'WEG':
        return None
    from apps.objekte.models import Bankkonto
    konten = list(Bankkonto.objects.filter(
        objekt=objekt, zahlungsverkehr=True, aktiv=True,
    )[:2])
    return konten[0] if len(konten) == 1 else None


def _bankname_aus_iban(iban: str) -> str:
    """Bankname über schwifty (wie ``config.urls.iban_check``); leer wenn unbekannt."""
    try:
        from schwifty import IBAN
        namen = IBAN(iban).bic.bank_names
        return namen[0] if namen else ''
    except Exception:
        return ''


def _prozent(wert: Decimal) -> str:
    return f"{wert:.2f}".replace('.', ',') + ' %'


# --------------------------------------------------------------------------
# Gruppen
# --------------------------------------------------------------------------

def _gruppe_empfaenger(r: _Refs) -> dict:
    p = r.person
    if p is None:
        return {}
    return {
        'anschrift_zeilen': anschrift_zeilen(p),
        'briefanrede': p.briefanrede,
        'briefanrede2': p.briefanrede2 or '',   # leer = Einzelperson (optional)
        'name': p.name,
        'personennummer': p.personennummer,
    }


def _gruppe_objekt(r: _Refs) -> dict:
    o = r.objekt
    if o is None:
        return {}
    return {
        'objektnummer': o.objektnummer,
        'bezeichnung': o.bezeichnung,
        'anschrift': f'{o.strasse}, {o.plz} {o.ort}',
        'ist_weg': o.objekt_typ == 'WEG',
    }


def _gruppe_einheit(r: _Refs) -> dict:
    e = r.einheit
    if e is None:
        return {}
    return {
        'einheit_nr': e.einheit_nr,
        'flaechennummer': e.flaechennummer,
        'lage': e.lage,
        'typ': e.einheit_typ,
    }


def _unser_zeichen(r: _Refs) -> str:
    konto = _ermittle_personenkonto(r)
    if r.objekt is None or konto is None or not r.objekt.objektnummer:
        return ''
    return f'{r.objekt.objektnummer}/{konto.kontonummer}'


def _gruppe_schreiben(r: _Refs) -> dict:
    return {
        'unser_zeichen': _unser_zeichen(r),
        'ihr_zeichen': r.ihr_zeichen or '',      # optional, darf leer sein
        'ihr_schreiben_vom': r.ihr_schreiben_vom,
        'datum': r.heute,
        'nummer': r.schreiben_nummer,
    }


def _telefon_des(user) -> str:
    profil = getattr(user, 'mitarbeiter_profil', None)
    return profil.telefon if profil is not None else ''


def _gruppe_verwaltung(r: _Refs) -> dict:
    betreuer = r.objekt.betreuer if r.objekt is not None else None
    unterzeichner = r.unterzeichner or betreuer
    briefbogen = _ermittle_briefbogen(r.briefbogen)
    return {
        'firma': briefbogen.firma_name if briefbogen else '',
        'unterzeichner_vorname': unterzeichner.first_name if unterzeichner else '',
        'unterzeichner_nachname': unterzeichner.last_name if unterzeichner else '',
        'betreuer_name': betreuer.get_full_name() if betreuer else '',
        'betreuer_telefon': _telefon_des(betreuer) if betreuer else '',
        'betreuer_email': betreuer.email if betreuer else '',
    }


def _gruppe_bank(r: _Refs) -> dict:
    konto = _ermittle_bankkonto(r.objekt)
    if konto is None:
        return {}
    return {
        'weg_name': r.objekt.bezeichnung,
        'iban': konto.iban,
        'bic': konto.bic,
        'bankname': _bankname_aus_iban(konto.iban) if konto.iban else '',
        'kontoinhaber': konto.kontoinhaber,
        'glaeubiger_id': r.objekt.glaeubiger_id,
    }


def _gruppe_ev(r: _Refs) -> dict:
    if r.person is None:
        return {}
    mandat = r.person.sepa_mandat
    vorhanden = bool(mandat is not None and mandat.aktiv)
    return {
        'beginn': r.ev.beginn if r.ev is not None else None,
        'sepa_mandat_vorhanden': vorhanden,
        'sepa_mandat_fehlt': not vorhanden,
    }


# ``Eigentuemerversammlung.art`` -> Adjektiv für „eine … Eigentümerversammlung“.
_VERSAMMLUNG_ART = {
    'ordentlich': 'ordentliche',
    'ausserordentl': 'außerordentliche',
    'wiederholung': 'wiederholte',
}


def _gruppe_versammlung(r: _Refs) -> dict:
    """Werte aus der Eigentümerversammlung (Spec 9.4) - die EV bleibt die Quelle, nicht das Eingabefeld."""
    v = r.versammlung
    if v is None:
        return {}
    return {
        'termin': timezone.localtime(v.termin) if v.termin else None,
        'ort': (v.ort or '').strip(),
        'tagesordnung': [t.titel for t in v.tagesordnung.order_by('nummer')],
        'art': _VERSAMMLUNG_ART.get(v.art, ''),
    }


def _hausgeld_zeilen(ev, stichtag: date) -> list:
    """Je Abrechnungsart der zum Stichtag letzte Eintrag (Muster: ``hausgeld_alle_aktuell``)."""
    from apps.personen.models import HausgeldHistorie
    return list(
        HausgeldHistorie.objects
        .filter(eigentumsverhaeltnis=ev, gueltig_ab__lte=stichtag)
        .order_by('abrechnungsart__code', '-gueltig_ab', '-erstellt_am')
        .distinct('abrechnungsart__code')
        .values('abrechnungsart__bezeichnung', 'betrag', 'gueltig_ab')
    )


def _gruppe_hausgeld(r: _Refs) -> dict:
    if r.ev is None:
        return {}
    stichtag = r.wechsel.wechsel_datum if r.wechsel is not None else r.heute
    zeilen = _hausgeld_zeilen(r.ev, stichtag)
    if not zeilen:
        return {}
    return {
        'monatsbetrag': sum((z['betrag'] for z in zeilen), Decimal('0')),
        'gueltig_ab': max(z['gueltig_ab'] for z in zeilen),
        'positionen': [
            {'bezeichnung': z['abrechnungsart__bezeichnung'] or '', 'betrag': z['betrag']}
            for z in zeilen
        ],
    }


def _gruppe_wechsel(r: _Refs) -> dict:
    w = r.wechsel
    if w is None:
        return {}
    return {
        'wechsel_datum': w.wechsel_datum,
        'voreigentuemer_name': w.voreigentuemer_ev.person.name,
    }


def _offene_posten_zeilen(personenkonto, stichtag: date) -> list:
    """Offene Posten wie in ``mahnwesen.simuliere_mahnlauf`` (Quelle: ``OffenerPosten``)."""
    ops = personenkonto.offene_posten.filter(
        status__in=['offen', 'teilverrechnet'], faellig_ab__lte=stichtag,
    ).select_related('buchung').order_by('faellig_ab')
    return [
        {
            'faellig_ab': op.faellig_ab,
            'bezeichnung': (op.buchung.buchungstext or op.buchung.verwendungszweck or '').strip(),
            'betrag_ursprung': op.betrag_ursprung,
            'betrag_offen': op.betrag_offen,
        }
        for op in ops
    ]


# Reservierter Schlüssel in ``Schreiben.eingabewerte`` (Unterstrich: kollidiert nie mit einem
# Eingabefeld, ``eingabefelder_service.validiere`` ignoriert ihn): die zum Mahnlauf-Zeitpunkt
# eingefrorenen offenen Posten. Ohne diesen Schlüssel gilt der Live-Stand.
MAHNUNG_OP_SNAPSHOT = '_mahnung_op_snapshot'


def friere_offene_posten_ein(personenkonto, stichtag: date) -> list:
    """JSON-sichere Momentaufnahme der offenen Posten (Mahnlauf-Zeitpunkt).

    Gleiche Auswahl und Zeilenform wie ``_offene_posten_zeilen``; Datum und Beträge
    als Text, damit die Liste in ``Schreiben.eingabewerte`` gespeichert werden kann.
    """
    return [
        {
            'faellig_ab': z['faellig_ab'].isoformat(),
            'bezeichnung': z['bezeichnung'],
            'betrag_ursprung': str(z['betrag_ursprung']),
            'betrag_offen': str(z['betrag_offen']),
        }
        for z in _offene_posten_zeilen(personenkonto, stichtag)
    ]


def _offene_posten_aus_snapshot(snapshot: list) -> list:
    return [
        {
            'faellig_ab': date.fromisoformat(z['faellig_ab']),
            'bezeichnung': z['bezeichnung'],
            'betrag_ursprung': Decimal(z['betrag_ursprung']),
            'betrag_offen': Decimal(z['betrag_offen']),
        }
        for z in snapshot
    ]


def _mahnung_offene_posten(r: _Refs) -> list:
    """Eingefrorene Posten der Mahnung (Snapshot im Schreiben), sonst der Live-Stand."""
    snapshot = (r.eingabewerte or {}).get(MAHNUNG_OP_SNAPSHOT)
    if snapshot is not None:
        return _offene_posten_aus_snapshot(snapshot)
    return _offene_posten_zeilen(r.mahnung.personenkonto, r.heute)


def _mahnfrist(r: _Refs):
    """Datum (Mahnlauf, im Lauf = ``heute``) + Zahlungsfrist der Stufe aus der Staffel, nächster Werktag.

    Die Frist kommt aus ``mahnwesen.MAHNSTUFEN``; nur für eine Stufe außerhalb der Staffel
    (Altbestand) gilt ersatzweise ``frist_tage`` aus den Vorlagen-Parametern.
    """
    from apps.buchhaltung.services.mahnwesen import zahlungsfrist_tage
    frist_tage = zahlungsfrist_tage(r.mahnung.mahnstufe) if r.mahnung is not None else None
    if frist_tage is None:
        frist_tage = (r.parameter or {}).get('frist_tage')
    if frist_tage is None or r.objekt is None:
        return None
    return fristen_service.berechne_frist(r.heute, frist_tage, r.objekt.bundesland)


def _gruppe_mahnung(r: _Refs) -> dict:
    from apps.buchhaltung.services.zinsen import get_basiszinssatz
    m = r.mahnung
    if m is None:
        return {}
    basis = get_basiszinssatz(r.heute)
    return {
        'stufe': m.mahnstufe,
        'offene_posten': _mahnung_offene_posten(r),
        'summe_hauptforderung': m.offene_posten_summe,
        'gebuehr': m.gebuehr,
        'zinsen': m.zinsen,
        'gesamtbetrag': m.offene_posten_summe + m.gebuehr + m.zinsen,
        'frist': _mahnfrist(r),
        'zinssatz': _prozent(basis + VERZUGSZINS_AUFSCHLAG),
        'basiszinssatz': _prozent(basis),
    }


def _gruppe_vorgang(r: _Refs) -> dict:
    v = r.vorgang
    if v is None:
        return {}
    return {'nummer': v.nummer, 'betreff': v.betreff}


def _gruppe_eingabe(r: _Refs) -> dict:
    # Rohwerte; getypt + validiert werden sie erst in render_service.render.
    return {k: v for k, v in (r.eingabewerte or {}).items() if not k.startswith('_')}


_GRUPPEN = {
    'empfaenger': _gruppe_empfaenger,
    'objekt': _gruppe_objekt,
    'einheit': _gruppe_einheit,
    'schreiben': _gruppe_schreiben,
    'verwaltung': _gruppe_verwaltung,
    'bank': _gruppe_bank,
    'ev': _gruppe_ev,
    'versammlung': _gruppe_versammlung,
    'hausgeld': _gruppe_hausgeld,
    'wechsel': _gruppe_wechsel,
    'mahnung': _gruppe_mahnung,
    'vorgang': _gruppe_vorgang,
    'eingabe': _gruppe_eingabe,
}


def _nur_dokumentierte(gruppe: str, werte: dict) -> dict:
    """Harte Grenze: nur in der Registry dokumentierte Namen (Test 6)."""
    if gruppe == 'eingabe':
        return werte
    dokumentiert = {p['name'] for p in registry.PLATZHALTER if p['gruppe'] == gruppe}
    return {k: v for k, v in werte.items() if f'{gruppe}.{k}' in dokumentiert}


def baue_kontext(
    anlass: str, *, person, objekt=None, einheit=None, eigentumsverhaeltnis=None,
    mahnung=None, eigentuemerwechsel=None, vorgang=None, versammlung=None, eingabewerte=None,
    parameter=None, unterzeichner=None, briefbogen=None, schreiben_nummer='',
    ihr_zeichen='', ihr_schreiben_vom=None, heute=None,
) -> dict:
    """Baut das Kontext-Dict ``{gruppe: {name: wert}}`` für einen Anlass.

    ``heute`` ist nur für Tests/Nachberechnung gedacht (Default: heute).
    ``parameter`` = ``VorlagenVersion.parameter`` (z. B. ``{"frist_tage": 14}``).
    ``versammlung`` = ``Eigentuemerversammlung`` (Anlass ``etv_einladung``, Spec 9.4).
    ``person=None`` ist nur für die neutrale EV-Einladung (ohne Empfänger) vorgesehen;
    die personenbezogenen Gruppen fehlen dann.
    Werte, die sich nicht ermitteln lassen, fehlen (siehe Modul-Docstring).
    """
    ev = _ermittle_ev(person, einheit, eigentumsverhaeltnis, mahnung, eigentuemerwechsel)
    einheit = _ermittle_einheit(einheit, ev, eigentuemerwechsel, vorgang)
    objekt = _ermittle_objekt(objekt, einheit, mahnung, eigentuemerwechsel, vorgang)
    refs = _Refs(
        anlass=anlass, person=person, objekt=objekt, einheit=einheit, ev=ev,
        mahnung=mahnung, wechsel=eigentuemerwechsel, vorgang=vorgang, versammlung=versammlung,
        eingabewerte=eingabewerte, parameter=parameter, unterzeichner=unterzeichner,
        briefbogen=briefbogen, schreiben_nummer=schreiben_nummer,
        ihr_zeichen=ihr_zeichen, ihr_schreiben_vom=ihr_schreiben_vom,
        heute=heute or date.today(),
    )
    kontext = {}
    for gruppe in registry.gruppen_fuer(anlass):
        werte = _nur_dokumentierte(gruppe, _ohne_leere_ausser_optional(gruppe, _GRUPPEN[gruppe](refs)))
        if werte:
            kontext[gruppe] = werte
    return kontext


# Ausdrücklich optionale Angaben, die als leerer String im Kontext bleiben.
_OPTIONAL_LEER = {('empfaenger', 'briefanrede2'), ('schreiben', 'ihr_zeichen')}
OPTIONAL_LEER = frozenset(_OPTIONAL_LEER)   # lesender Zugriff für die Layout-Vorschau


def _ohne_leere_ausser_optional(gruppe: str, werte: dict) -> dict:
    return {
        k: v for k, v in werte.items()
        if v is not None and (v != '' or (gruppe, k) in _OPTIONAL_LEER)
    }
