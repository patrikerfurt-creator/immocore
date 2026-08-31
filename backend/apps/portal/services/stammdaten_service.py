"""
Selbstpflege der Stammdaten durch den Eigentümer (Spec 1a, Kap. 5).

Jede Änderung erzeugt einen ``PersonStammdatenAenderung``-Eintrag JE FELD
(Spec Kap. 4.2). Unveränderte Felder erzeugen keinen Eintrag — sonst wäre
die Historie nach ein paar Speicherklicks nicht mehr lesbar.

Real-Code-Abweichungen von der Spec (Real-Code-vor-Spec-Prinzip):

* Spec 5.2 nennt "Kontoinhaber". Weder ``Person`` noch ``SEPAMandat``
  haben ein solches Feld (``Bankkonto.kontoinhaber`` gehört zu den
  Objektkonten der Verwaltung, nicht zur Person). Kontoinhaber wird
  deshalb nicht zur Bearbeitung angeboten.
* ``SEPAMandat`` hängt per FK an der ``Person`` (``Person.sepa_mandat``),
  nicht an der Einheit — der Mandat-Sync betrifft folglich genau ein
  Mandat je Person.
"""
import logging

from django.db import transaction

from apps.personen.models import Person, SEPAMandat
from ..models import PersonStammdatenAenderung, PortalZugang
from . import zugang_service

logger = logging.getLogger(__name__)


class StammdatenFehler(Exception):
    """Fachlicher Fehler bei der Selbstpflege."""


# ---------------------------------------------------------------------------
# Lesen: JSON-Listen und Legacy-Felder auf einen Wert zusammenführen
# ---------------------------------------------------------------------------

def _wert_aus_eintrag(eintrag, schluessel: tuple[str, ...]) -> str:
    """Einträge der JSON-Listen sind mal Strings, mal Dicts (Bestandsdaten)."""
    if isinstance(eintrag, str):
        return eintrag.strip()
    if isinstance(eintrag, dict):
        for s in schluessel:
            wert = (eintrag.get(s) or '').strip()
            if wert:
                return wert
    return ''


def erste_telefonnummer(person: Person) -> str:
    for eintrag in (person.telefonnummern or []):
        wert = _wert_aus_eintrag(eintrag, ('nummer', 'telefon', 'wert'))
        if wert:
            return wert
    return (person.telefon or '').strip()


def _setze_ersten_listeneintrag(liste, wert: str, schluessel: tuple[str, ...]) -> list:
    """Setzt ``wert`` an Position 0 und behält die Form des Bestandseintrags.

    Warum die JSON-Liste überhaupt mitgepflegt wird: ``Person.email`` und
    ``Person.telefon`` sind die Legacy-Felder, gelesen wird im Projekt aber
    zuerst aus ``Person.emails``/``Person.telefonnummern``. Würde das Portal
    nur das Legacy-Feld schreiben, liefert die Leselogik weiter den alten
    Wert — bei der E-Mail hieße das: der Login mit der neuen, bestätigten
    Adresse funktioniert nicht.
    """
    liste = list(liste or [])
    if not liste:
        return [wert]

    erster = liste[0]
    if isinstance(erster, dict):
        neu = dict(erster)
        for s in schluessel:
            if s in neu:
                neu[s] = wert
                break
        else:
            neu[schluessel[0]] = wert
        liste[0] = neu
    else:
        liste[0] = wert
    return liste


# ---------------------------------------------------------------------------
# Audit-Log
# ---------------------------------------------------------------------------

def protokolliere(person: Person, feld: str, alter_wert: str, neuer_wert: str) -> None:
    PersonStammdatenAenderung.objects.create(
        person=person,
        feld=feld,
        alter_wert=alter_wert or '',
        neuer_wert=neuer_wert or '',
        quelle=PersonStammdatenAenderung.QUELLE_PORTAL,
    )


# ---------------------------------------------------------------------------
# Adresse und Telefon (Spec 5.1) — sofort wirksam
# ---------------------------------------------------------------------------

# Adressfelder, die der Eigentümer selbst pflegen darf. ``Person.adresse``
# ist bewusst NICHT dabei: der Textblock wird in ``Person.save()`` aus
# diesen Feldern zusammengesetzt.
ADRESSFELDER = ('strasse', 'hausnummer', 'plz', 'ort')


@transaction.atomic
def aktualisiere_kontakt(zugang: PortalZugang, daten: dict) -> Person:
    """Adresse und/oder Telefon ändern. Nur übergebene Schlüssel wirken."""
    person = zugang.person
    zu_speichern: list[str] = []

    for feld in ADRESSFELDER:
        if feld not in daten:
            continue
        neu = (daten[feld] or '').strip()
        alt = (getattr(person, feld) or '').strip()
        if neu != alt:
            setattr(person, feld, neu)
            zu_speichern.append(feld)
            protokolliere(person, feld, alt, neu)

    if 'telefon' in daten:
        neu = (daten['telefon'] or '').strip()
        alt = erste_telefonnummer(person)
        if neu != alt:
            person.telefon = neu
            person.telefonnummern = _setze_ersten_listeneintrag(
                person.telefonnummern, neu, ('nummer', 'telefon', 'wert')
            )
            zu_speichern.extend(['telefon', 'telefonnummern'])
            protokolliere(person, 'telefon', alt, neu)

    if zu_speichern:
        person.save(update_fields=zu_speichern)
    return person


# ---------------------------------------------------------------------------
# Bankverbindung (Spec 5.2) — inkl. SEPA-Mandat-Synchronisation
# ---------------------------------------------------------------------------

def aktives_mandat(person: Person) -> SEPAMandat | None:
    mandat = person.sepa_mandat
    if mandat is not None and mandat.aktiv:
        return mandat
    return None


def erste_iban(person: Person) -> str:
    for eintrag in (person.ibans or []):
        wert = _wert_aus_eintrag(eintrag, ('iban', 'wert'))
        if wert:
            return wert
    mandat = aktives_mandat(person)
    return mandat.iban if mandat else ''


def _normalisiere_iban(wert: str) -> str:
    return (wert or '').replace(' ', '').strip().upper()


@transaction.atomic
def aktualisiere_bankverbindung(zugang: PortalZugang, daten: dict) -> dict:
    """IBAN/BIC ändern und ein aktives SEPA-Mandat mitziehen.

    Aktives Mandat vorhanden → IBAN/BIC werden DIREKT im bestehenden
    Mandat aktualisiert, die ``mandatsreferenz`` bleibt unverändert (Spec
    Kap. 5.2). Der nächste Lastschriftlauf zieht damit automatisch von der
    neuen IBAN ein.

    Kein aktives Mandat → nur die Bankverbindung auf der Person, kein
    Mandat wird angefasst.

    Die bisherige IBAN bleibt in ``Person.ibans`` erhalten (neue an
    Position 0): die E-Banking-Erkennung ordnet Zahlungen über diese Liste
    zu — würde die alte IBAN verschwinden, ließen sich bereits laufende
    Zahlungen von dort nicht mehr automatisch zuordnen.

    Rückgabe: ``{'mandat_aktualisiert': bool, 'mandatsreferenz': str|None}``
    """
    person = zugang.person
    mandat = aktives_mandat(person)

    neue_iban = _normalisiere_iban(daten.get('iban', ''))
    alte_iban = _normalisiere_iban(erste_iban(person))
    iban_geaendert = 'iban' in daten and neue_iban != alte_iban

    if 'iban' in daten and not neue_iban:
        raise StammdatenFehler('Die IBAN darf nicht leer sein.')

    bic_uebergeben = 'bic' in daten
    neue_bic = (daten.get('bic') or '').replace(' ', '').strip().upper()
    alte_bic = (mandat.bic if mandat else '').strip().upper()
    bic_geaendert = bic_uebergeben and neue_bic != alte_bic

    if not iban_geaendert and not bic_geaendert:
        return {'mandat_aktualisiert': False, 'mandatsreferenz': mandat.mandatsreferenz if mandat else None}

    if iban_geaendert:
        bestand = [
            _normalisiere_iban(_wert_aus_eintrag(e, ('iban', 'wert')))
            for e in (person.ibans or [])
        ]
        bestand = [i for i in bestand if i and i != neue_iban]
        person.ibans = [neue_iban] + bestand
        person.save(update_fields=['ibans'])
        protokolliere(person, 'iban', alte_iban, neue_iban)

    mandat_felder: list[str] = []
    if mandat is not None:
        if iban_geaendert:
            mandat.iban = neue_iban
            mandat_felder.append('iban')
        if bic_geaendert:
            protokolliere(person, 'bic', alte_bic, neue_bic)
            mandat.bic = neue_bic
            mandat_felder.append('bic')
        if mandat_felder:
            mandat.save(update_fields=mandat_felder)
            # Eigener Eintrag: dokumentiert, dass die Änderung das
            # Lastschriftmandat mit umfasst hat — die reinen iban/bic-
            # Einträge oben sagen nichts über den Mandatsbezug aus.
            protokolliere(
                person, 'sepa_mandat',
                f'Mandat {mandat.mandatsreferenz} (IBAN {alte_iban})',
                f'Mandat {mandat.mandatsreferenz} (IBAN {mandat.iban}) — '
                f'Mandatsreferenz unverändert',
            )
    elif bic_geaendert:
        # Ohne Mandat gibt es kein Feld, in dem eine BIC gespeichert würde;
        # ein Audit-Eintrag über eine nirgends gespeicherte Änderung wäre
        # irreführend.
        logger.info(
            'Portal: BIC-Änderung ohne aktives SEPA-Mandat für Person %s '
            'wird verworfen (kein Speicherort im Datenmodell).', person.pk,
        )

    return {
        'mandat_aktualisiert': bool(mandat_felder),
        'mandatsreferenz': mandat.mandatsreferenz if mandat else None,
    }


# ---------------------------------------------------------------------------
# E-Mail-Änderung (Spec 5.3) — erst nach Bestätigung wirksam
# ---------------------------------------------------------------------------

@transaction.atomic
def stosse_email_aenderung_an(zugang: PortalZugang, neue_email: str):
    """Trägt die neue Adresse in ``email_pending`` ein und erzeugt den
    Bestätigungs-Token. ``Person.email`` bleibt unangetastet — bis zur
    Bestätigung funktioniert der Login weiter mit der alten Adresse."""
    neue_email = (neue_email or '').strip()
    if not neue_email:
        raise StammdatenFehler('Bitte geben Sie eine E-Mail-Adresse an.')

    person = zugang.person
    if neue_email.lower() == zugang_service.person_email(person).lower():
        raise StammdatenFehler('Das ist bereits Ihre hinterlegte E-Mail-Adresse.')

    fremder = zugang_service.finde_zugang_per_email(neue_email)
    if fremder is not None and fremder.pk != zugang.pk:
        # Zwei Portal-Zugänge mit derselben Login-Adresse wären nicht mehr
        # eindeutig auflösbar.
        raise StammdatenFehler('Diese E-Mail-Adresse kann nicht verwendet werden.')

    zugang.email_pending = neue_email
    zugang.save(update_fields=['email_pending', 'geaendert_am'])

    return zugang_service.erzeuge_email_bestaetigung(zugang, neue_email)


@transaction.atomic
def bestaetige_email(token_wert: str) -> Person:
    """Löst den Bestätigungs-Token ein und übernimmt die neue Adresse."""
    from ..models import PortalToken

    tok = zugang_service.loese_token_ein(
        token_wert, (PortalToken.TYP_EMAIL_BESTAETIGUNG,)
    )
    zugang = tok.zugang
    person = zugang.person

    neue_email = (tok.ziel_email or '').strip()
    if not neue_email:
        raise StammdatenFehler('Dieser Link ist ungültig oder abgelaufen.')

    alt = zugang_service.person_email(person)
    person.email = neue_email
    person.emails = _setze_ersten_listeneintrag(
        person.emails, neue_email, ('adresse', 'email', 'wert')
    )
    person.save(update_fields=['email', 'emails'])
    protokolliere(person, 'email', alt, neue_email)

    zugang.email_pending = ''
    zugang.save(update_fields=['email_pending', 'geaendert_am'])
    return person
