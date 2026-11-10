"""
SEPA-Lastschriftmandat im Eigentümer-Portal (Architektur-Entscheid
``docs/ARCHITEKTUR_ENTSCHEID_PORTAL_SEPA_MANDAT.md``, Abschnitte b, c, e, f).

Ablauf in zwei Schritten, damit kein Mandat ohne Zustimmung des Kontoinhabers
entsteht (R3):

1. ``stosse_mandat_an`` (Portal-Sitzung): prüft, legt einen Antrag
   (``PortalSepaMandatAenderung``, Status ``offen``) samt Token an und
   versendet den Link an die EIGENE E-Mail-Adresse der Person. Es wird
   KEIN Mandat geschrieben.
2. ``bestaetige_mandat`` (Token aus der Mail, ohne Sitzung): wirkt erst auf
   den ausdrücklichen POST mit Kontoinhaber-Erklärung — nie beim bloßen
   Öffnen des Links (``vorschau`` ist rein lesend und verbraucht nichts).

Fehlerklassen: ``SepaMandatFehler`` für fachliche Ablehnungen mit
Nutzertext (400); ``TokenUngueltig``/``ZugangGesperrt`` aus dem
``zugang_service`` für Link-Fehler. ``StammdatenFehler`` wird bewusst nicht
wiederverwendet: das ist der Fehler der Selbstpflege (Adresse/IBAN) und wird
in den Views anders behandelt.

Portal-Mandate werden immer mit ``sequence_type='RCUR'`` angelegt (Entscheid
(a), Freigabe Patrik 2026-11-04).
"""
import logging
import re
from dataclasses import dataclass, field

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.personen.models import EigentumsVerhaeltnis, Person, SEPAMandat
from apps.personen.services.sepa_mandat import mandate_fuer_evs, sammelmandat_fuer_person
from ..models import PersonStammdatenAenderung, PortalSepaMandatAenderung, PortalToken, PortalZugang
from . import iban_service, mail_service, stammdaten_service, zugang_service
from .einheiten_service import aktive_evs
from .sepa_mandat_text import (  # noqa: F401  (öffentliche Namen dieses Service)
    MANDATSTEXT_VERSION,
    geltungsbereich_text,
    geltungsbereich_text_fuer_antrag,
    maskiere_email,
    maskiere_iban,
    rendere_mandatstext,
    sha256_hex,
)
from .zugang_service import TokenUngueltig, ZugangGesperrt  # noqa: F401

logger = logging.getLogger(__name__)

P = PortalSepaMandatAenderung

SCHLUESSEL_ALLE = 'alle'
AKTION_ERTEILEN = 'erteilen'
AKTION_AENDERN = 'aendern'

_BIC_MUSTER = re.compile(r'^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$')
_PNR_MUSTER = re.compile(r'^[A-Z0-9]{1,20}$')
_LFD_MUSTER = re.compile(r'-(\d+)$')
_MAX_USER_AGENT = 1000

HINDERUNG_KEINE_EMAIL = (
    'Für Ihr Konto ist keine eigene E-Mail-Adresse hinterlegt. '
    'Bitte wenden Sie sich an die Verwaltung.'
)
HINDERUNG_KEIN_EV = (
    'Es sind keine aktuellen Eigentumsverhältnisse hinterlegt. '
    'Bitte wenden Sie sich an die Verwaltung.'
)
HINDERUNG_GETEILT = (
    'Ihr SEPA-Mandat wird gemeinsam mit weiteren Personen geführt. '
    'Bitte wenden Sie sich an die Verwaltung.'
)
_HINDERUNG_GLAEUBIGER_ID = (
    'Für „{objekt}" ist noch keine Gläubiger-ID hinterlegt. '
    'Bitte wenden Sie sich an die Verwaltung.'
)
_NICHT_VERFUEGBAR = 'Die gewählte Einheit steht nicht zur Verfügung.'
_NEU_ANFORDERN = 'Bitte fordern Sie das Mandat neu an.'


class SepaMandatFehler(Exception):
    """Fachliche Ablehnung mit Text für den Eigentümer."""


class _ZustandsKonflikt(Exception):
    """Interner Abbruch: die Lage hat sich seit der Anforderung geändert."""


# ---------------------------------------------------------------------------
# Mandatsreferenz
# ---------------------------------------------------------------------------

def _personen_kennung(person: Person) -> str:
    pnr = (person.personennummer or '').strip().upper()
    if _PNR_MUSTER.match(pnr):
        return pnr
    return 'P' + person.id.hex[:10].upper()


def erzeuge_mandatsreferenz(person: Person) -> str:
    """``PORTAL-{PNR}-{LFD:03d}``, z. B. ``PORTAL-100234-001`` (Entscheid c).

    LFD = höchste laufende Nummer mit diesem Präfix über ``SEPAMandat`` und
    die offenen Anträge + 1. Höchstens 31 Zeichen, nur ``A-Z 0-9 -``.
    """
    praefix = f'PORTAL-{_personen_kennung(person)}-'

    vorhandene = list(
        SEPAMandat.objects
        .filter(mandatsreferenz__startswith=praefix)
        .values_list('mandatsreferenz', flat=True)
    ) + list(
        P.objects
        .filter(mandatsreferenz__startswith=praefix, status=P.STATUS_OFFEN)
        .values_list('mandatsreferenz', flat=True)
    )
    hoechste = 0
    for referenz in vorhandene:
        treffer = _LFD_MUSTER.search(referenz)
        if treffer:
            hoechste = max(hoechste, int(treffer.group(1)))

    laufende_nr = hoechste + 1
    if laufende_nr > 999:
        raise SepaMandatFehler(
            'Es konnte keine Mandatsreferenz vergeben werden. '
            'Bitte wenden Sie sich an die Verwaltung.'
        )
    return f'{praefix}{laufende_nr:03d}'


# ---------------------------------------------------------------------------
# Lage der Person: Geltungsbereiche und Mandate
# ---------------------------------------------------------------------------

@dataclass
class _Bereich:
    schluessel: str
    geltungsbereich: str                      # P.GELTUNG_ALLE | P.GELTUNG_EINHEIT
    ev: EigentumsVerhaeltnis | None
    mandat: SEPAMandat | None                 # ``alle``: Sammelmandat, ``ev:``: Einheitenmandat
    wirksam_ueber: str | None = None          # nur ``ev:``: einheit | alle | keins

    @property
    def aktion(self) -> str:
        return AKTION_AENDERN if self.mandat is not None else AKTION_ERTEILEN


@dataclass
class _Lage:
    evs: list = field(default_factory=list)
    bereiche: list = field(default_factory=list)
    hinderungsgrund: str | None = None


def _ist_geteilt(mandat: SEPAMandat, person: Person) -> bool:
    """Mandat gehört (auch) einer anderen Person → Portal darf es nicht ändern.

    ``person_id`` leer (Bestandsmandat ohne Zuordnung) gilt als nicht geteilt,
    solange nur diese Person es über ``Person.sepa_mandat`` referenziert.
    """
    if mandat.person_id not in (None, person.id):
        return True
    return mandat.personen.exclude(pk=person.pk).exists()


def _hinderungsgrund(person: Person, evs: list, mandate: list) -> str | None:
    if not zugang_service.person_email(person):
        return HINDERUNG_KEINE_EMAIL
    if not evs:
        return HINDERUNG_KEIN_EV
    if any(_ist_geteilt(m, person) for m in mandate):
        return HINDERUNG_GETEILT
    for ev in evs:
        objekt = ev.einheit.objekt
        if not (objekt.glaeubiger_id or '').strip():
            return _HINDERUNG_GLAEUBIGER_ID.format(objekt=objekt.bezeichnung)
    return None


def _ermittle_lage(person: Person) -> _Lage:
    """Geltungsbereiche mit Aktion und Mandat (Entscheid f), eine Quelle für
    Statusanzeige UND Anforderung — der Client leitet nichts selbst ab (R8)."""
    evs = list(aktive_evs(person))
    sammel = sammelmandat_fuer_person(person)
    einheitenmandate = {
        m.eigentumsverhaeltnis_id: m
        for m in SEPAMandat.objects.filter(aktiv=True, eigentumsverhaeltnis__in=evs)
    }
    lage = _Lage(
        evs=evs,
        hinderungsgrund=_hinderungsgrund(
            person, evs,
            ([sammel] if sammel else []) + list(einheitenmandate.values()),
        ),
    )
    if not evs:
        return lage

    alle = _Bereich(SCHLUESSEL_ALLE, P.GELTUNG_ALLE, None, sammel)
    if len(evs) == 1:
        # Bei genau einer Einheit nur ein Eintrag: Einheitenmandat vorhanden →
        # ändern, sonst legt ``alle`` ein Sammelmandat an (das auch
        # ``hat_aktives_mandat`` und Legacy-Leser sehen).
        einziges = einheitenmandate.get(evs[0].id)
        if einziges is not None:
            lage.bereiche = [_ev_bereich(evs[0], einziges, None)]
        else:
            lage.bereiche = [alle]
        return lage

    wirksam = mandate_fuer_evs(evs)
    lage.bereiche = [alle] + [
        _ev_bereich(ev, einheitenmandate.get(ev.id), wirksam.get(ev.id)) for ev in evs
    ]
    return lage


def _ev_bereich(ev, einheitenmandat, wirksames_mandat) -> _Bereich:
    if einheitenmandat is not None:
        wirksam = 'einheit'
    elif wirksames_mandat is not None:
        wirksam = 'alle'
    else:
        wirksam = 'keins'
    return _Bereich(f'ev:{ev.id}', P.GELTUNG_EINHEIT, ev, einheitenmandat, wirksam)


# ---------------------------------------------------------------------------
# Status (GET /portal/sepa-mandat/)
# ---------------------------------------------------------------------------

def _mandat_dict(mandat: SEPAMandat | None) -> dict | None:
    if mandat is None:
        return None
    return {
        'mandatsreferenz': mandat.mandatsreferenz,
        'iban_maskiert': maskiere_iban(mandat.iban),
        'bic': mandat.bic,
        'unterzeichnet_am': mandat.unterzeichnet_am,
        'quelle': mandat.quelle,
    }


def _bereich_dict(bereich: _Bereich) -> dict:
    if bereich.ev is None:
        return {
            'schluessel': bereich.schluessel,
            'ev_id': None,
            'bezeichnung': 'Alle Einheiten',
            'aktion': bereich.aktion,
            'mandat': _mandat_dict(bereich.mandat),
        }
    einheit = bereich.ev.einheit
    objekt = einheit.objekt
    return {
        'schluessel': bereich.schluessel,
        'ev_id': str(bereich.ev.id),
        'bezeichnung': geltungsbereich_text(P.GELTUNG_EINHEIT, bereich.ev),
        'objekt_bezeichnung': objekt.bezeichnung,
        'einheit_nr': einheit.einheit_nr,
        'lage': einheit.lage,
        'aktion': bereich.aktion,
        'mandat': _mandat_dict(bereich.mandat),
        'wirksam_ueber': bereich.wirksam_ueber,
    }


def _verfalle_abgelaufene_antraege(zugang: PortalZugang) -> None:
    """Offene Anträge mit abgelaufenem/entwertetem Token auf ``verfallen``
    setzen (lazy, kein Cron)."""
    for antrag in P.objects.filter(zugang=zugang, status=P.STATUS_OFFEN).select_related('token'):
        if antrag.token is None or not antrag.token.ist_gueltig():
            antrag.status = P.STATUS_VERFALLEN
            antrag.save(update_fields=['status'])


def _schluessel_von(antrag: PortalSepaMandatAenderung) -> str:
    if antrag.geltungsbereich == P.GELTUNG_EINHEIT:
        return f'ev:{antrag.eigentumsverhaeltnis_id}'
    return SCHLUESSEL_ALLE


def _aktion_von(antrag: PortalSepaMandatAenderung) -> str:
    return AKTION_AENDERN if antrag.aktion == P.AKTION_AENDERUNG else AKTION_ERTEILEN


def status_fuer_zugang(zugang: PortalZugang) -> dict:
    """Antwort für ``GET /portal/sepa-mandat/`` (Form: Entscheid f)."""
    person = zugang.person
    _verfalle_abgelaufene_antraege(zugang)
    lage = _ermittle_lage(person)

    offen = (
        P.objects.filter(zugang=zugang, status=P.STATUS_OFFEN)
        .select_related('token').first()
    )
    email = zugang_service.person_email(person)
    return {
        'kann_erteilen': lage.hinderungsgrund is None,
        'hinderungsgrund': lage.hinderungsgrund,
        'empfaenger_email_maskiert': maskiere_email(email) if email else None,
        'kopfzeile_aktion': (
            AKTION_AENDERN if any(b.aktion == AKTION_AENDERN for b in lage.bereiche)
            else AKTION_ERTEILEN
        ),
        'auswahl_noetig': len(lage.evs) > 1,
        'geltungsbereiche': [_bereich_dict(b) for b in lage.bereiche],
        'offene_anfrage': None if offen is None else {
            'schluessel': _schluessel_von(offen),
            'aktion': _aktion_von(offen),
            'erstellt_am': offen.erstellt_am,
            'gueltig_bis': offen.token.gueltig_bis if offen.token else None,
        },
    }


# ---------------------------------------------------------------------------
# Anfordern
# ---------------------------------------------------------------------------

def _abgedeckte_glaeubiger(evs) -> list[dict]:
    """Je Objekt: Gläubiger (Objekt-Bezeichnung) + Gläubiger-ID + EV-IDs."""
    je_objekt: dict = {}
    for ev in evs:
        objekt = ev.einheit.objekt
        eintrag = je_objekt.setdefault(objekt.id, {
            'objekt_id': str(objekt.id),
            'bezeichnung': objekt.bezeichnung,
            'glaeubiger_id': (objekt.glaeubiger_id or '').strip(),
            'ev_ids': [],
        })
        eintrag['ev_ids'].append(str(ev.id))
    return sorted(je_objekt.values(), key=lambda e: (e['bezeichnung'], e['objekt_id']))


def _normalisiere_bic(bic: str) -> str:
    bic = (bic or '').replace(' ', '').strip().upper()
    if bic and not _BIC_MUSTER.match(bic):
        raise SepaMandatFehler('Diese BIC ist ungültig.')
    return bic


def _finde_bereich(lage: _Lage, schluessel: str) -> _Bereich:
    # Nur gegen die EIGENE Liste auflösen (R8): eine fremde oder erfundene
    # ID erreicht nie ein fremdes Eigentumsverhältnis.
    for bereich in lage.bereiche:
        if bereich.schluessel == (schluessel or '').strip():
            return bereich
    raise SepaMandatFehler(_NICHT_VERFUEGBAR)


@transaction.atomic
def stosse_mandat_an(
    zugang: PortalZugang, schluessel: str, iban: str, bic: str, *,
    ip: str | None, user_agent: str, session_id,
) -> PortalSepaMandatAenderung:
    """Legt einen Antrag an und versendet den Bestätigungslink (Entscheid e).

    Der Mailversand ist der letzte Schritt INNERHALB der Transaktion: jede
    Ausnahme (auch ein SMTP-Fehler) rollt Antrag und Token zurück, es bleibt
    kein toter Link zurück. Es wird kein Mandat geschrieben.
    """
    # Zugang sperren: serialisiert parallele Anforderungen derselben Person
    # (sonst Verstoß gegen ``uniq_offene_sepa_anfrage_je_zugang`` → 500).
    PortalZugang.objects.select_for_update().get(pk=zugang.pk)
    person = zugang.person

    pruefung = iban_service.pruefe_iban(iban)
    if not pruefung['valid']:
        raise SepaMandatFehler(pruefung['error'])
    iban_norm = iban_service.normalisiere_iban(pruefung['iban'])
    bic_norm = _normalisiere_bic(bic)

    _verfalle_abgelaufene_antraege(zugang)
    lage = _ermittle_lage(person)
    bereich = _finde_bereich(lage, schluessel)
    if lage.hinderungsgrund is not None:
        raise SepaMandatFehler(lage.hinderungsgrund)

    aenderung = bereich.mandat is not None
    abgedeckt_evs = lage.evs if bereich.ev is None else [bereich.ev]

    P.objects.filter(zugang=zugang, status=P.STATUS_OFFEN).update(
        status=P.STATUS_VERWORFEN, verworfen_grund='Neue Anfrage',
    )
    zugang_service._entwerte_offene_token(zugang, PortalToken.TYP_SEPA_MANDAT)

    referenz = bereich.mandat.mandatsreferenz if aenderung else erzeuge_mandatsreferenz(person)
    glaeubiger = _abgedeckte_glaeubiger(abgedeckt_evs)
    kontoinhaber = person.name[:140]
    text = rendere_mandatstext({
        'glaeubiger': glaeubiger,
        'mandatsreferenz': referenz,
        'kontoinhaber_name': kontoinhaber,
        'iban': iban_norm,
        'bic': bic_norm,
        'geltungsbereich_text': geltungsbereich_text(bereich.geltungsbereich, bereich.ev),
        'aenderung': aenderung,
    })

    token = zugang_service.erzeuge_sepa_mandat_token(zugang)
    antrag = P.objects.create(
        zugang=zugang,
        person=person,
        geltungsbereich=bereich.geltungsbereich,
        eigentumsverhaeltnis=bereich.ev,
        aktion=P.AKTION_AENDERUNG if aenderung else P.AKTION_ANLAGE,
        ziel_mandat=bereich.mandat if aenderung else None,
        token=token,
        mandatsreferenz=referenz,
        iban=iban_norm,
        bic=bic_norm,
        kontoinhaber_name=kontoinhaber,
        mandatstext=text,
        mandatstext_version=MANDATSTEXT_VERSION,
        mandatstext_sha256=sha256_hex(text),
        abgedeckte_glaeubiger=glaeubiger,
        empfaenger_email=zugang_service.person_email(person),
        anforderung_ip=ip,
        anforderung_user_agent=(user_agent or '')[:_MAX_USER_AGENT],
        portal_session_id=session_id,
    )

    mail_service.versende_sepa_mandat_link(antrag)
    antrag.mail_versendet_am = timezone.now()
    antrag.save(update_fields=['mail_versendet_am'])
    return antrag


# ---------------------------------------------------------------------------
# Vorschau (GET, verbraucht nichts)
# ---------------------------------------------------------------------------

def _lade_offenen_antrag(token: PortalToken, *, sperren: bool = False) -> PortalSepaMandatAenderung:
    abfrage = P.objects.select_related(
        'person', 'zugang', 'eigentumsverhaeltnis__einheit__objekt', 'ziel_mandat',
    )
    if sperren:
        abfrage = abfrage.select_for_update(of=('self',))
    antrag = abfrage.filter(token=token).first()
    if antrag is None or antrag.status != P.STATUS_OFFEN:
        raise TokenUngueltig('Dieser Link ist ungültig oder abgelaufen.')
    return antrag


def vorschau(token_wert: str) -> dict:
    """Inhalt für die Bestätigungsseite. Rein lesend: Mail-Scanner dürfen den
    Link abrufen, ohne dass der Token verbraucht wird."""
    token = zugang_service.pruefe_token(token_wert, (PortalToken.TYP_SEPA_MANDAT,))
    antrag = _lade_offenen_antrag(token)
    return {
        'mandatstext': antrag.mandatstext,
        'mandatsreferenz': antrag.mandatsreferenz,
        'iban_maskiert': maskiere_iban(antrag.iban),
        'bic': antrag.bic,
        'geltungsbereich': antrag.geltungsbereich,
        'geltungsbereich_text': geltungsbereich_text_fuer_antrag(antrag),
        'aktion': _aktion_von(antrag),
        'kontoinhaber_name': antrag.kontoinhaber_name,
        'gueltig_bis': token.gueltig_bis,
    }


# ---------------------------------------------------------------------------
# Bestätigen
# ---------------------------------------------------------------------------

def _pruefe_zustand(antrag: PortalSepaMandatAenderung, person: Person) -> SEPAMandat | None:
    """Erneute Prüfung beim Bestätigen (Entscheid e, schließt B1).

    Zwischen Anforderung und Klick kann sich alles geändert haben. Bei einer
    Abweichung wird NICHT umgedeutet, sondern verworfen. Gibt bei einer
    Änderung das gesperrte Zielmandat zurück.
    """
    if antrag.person_id != person.id:
        raise _ZustandsKonflikt('Der Antrag gehört nicht zu diesem Zugang.')

    aktive = list(aktive_evs(person))
    if antrag.geltungsbereich == P.GELTUNG_EINHEIT:
        ev = next((e for e in aktive if e.id == antrag.eigentumsverhaeltnis_id), None)
        if ev is None:
            raise _ZustandsKonflikt('Die Einheit gehört nicht mehr zu Ihren aktuellen Einheiten.')
        abgedeckt_evs = [ev]
    else:
        if not aktive:
            raise _ZustandsKonflikt('Es sind keine aktuellen Einheiten mehr hinterlegt.')
        abgedeckt_evs = aktive

    # Der Eigentümer hat dem Text mit bestimmten Gläubigern zugestimmt.
    def _schluessel(liste):
        return {(str(e['objekt_id']), e['glaeubiger_id']) for e in liste}

    if _schluessel(_abgedeckte_glaeubiger(abgedeckt_evs)) != _schluessel(antrag.abgedeckte_glaeubiger):
        raise _ZustandsKonflikt('Ihre Einheiten oder die Gläubiger haben sich seit der Anforderung geändert.')

    if antrag.aktion == P.AKTION_ANLAGE:
        if antrag.geltungsbereich == P.GELTUNG_EINHEIT:
            vorhanden = SEPAMandat.objects.filter(
                aktiv=True, eigentumsverhaeltnis_id=antrag.eigentumsverhaeltnis_id,
            ).exists()
        else:
            vorhanden = sammelmandat_fuer_person(person) is not None
        if vorhanden:
            raise _ZustandsKonflikt('Für diesen Bereich existiert inzwischen bereits ein SEPA-Mandat.')
        return None

    ziel = (
        SEPAMandat.objects.select_for_update()
        .filter(pk=antrag.ziel_mandat_id, aktiv=True).first()
    )
    if ziel is None or ziel.mandatsreferenz != antrag.mandatsreferenz:
        raise _ZustandsKonflikt('Das zu ändernde Mandat ist nicht mehr aktiv.')
    gleicher_bereich = (
        ziel.eigentumsverhaeltnis_id == antrag.eigentumsverhaeltnis_id
        if antrag.geltungsbereich == P.GELTUNG_EINHEIT
        else ziel.ist_sammelmandat and sammelmandat_fuer_person(person) == ziel
    )
    if not gleicher_bereich:
        raise _ZustandsKonflikt('Das Mandat gilt inzwischen für einen anderen Bereich.')
    if _ist_geteilt(ziel, person):
        raise _ZustandsKonflikt('Das Mandat wird inzwischen gemeinsam mit weiteren Personen geführt.')
    return ziel


def _lege_mandat_an(antrag: PortalSepaMandatAenderung, person: Person) -> SEPAMandat:
    try:
        with transaction.atomic():  # Savepoint: IntegrityError bricht nicht die Außen-Transaktion
            mandat = SEPAMandat.objects.create(
                mandatsreferenz=antrag.mandatsreferenz,
                iban=antrag.iban,
                bic=antrag.bic,
                unterzeichnet_am=timezone.localdate(),
                aktiv=True,
                sequence_type='RCUR',
                person=person,
                eigentumsverhaeltnis=antrag.eigentumsverhaeltnis,
                quelle=SEPAMandat.QUELLE_PORTAL,
            )
    except IntegrityError:
        # Nicht still neu nummerieren (Entscheid c).
        raise _ZustandsKonflikt('Die Mandatsreferenz oder das Mandat ist inzwischen vergeben.')
    if mandat.ist_sammelmandat:
        # Legacy-Spiegel des Sammelmandats; Einheitenmandate fassen ihn nie an.
        person.sepa_mandat = mandat
        person.save(update_fields=['sepa_mandat'])
    return mandat


def _aendere_mandat(ziel: SEPAMandat, antrag: PortalSepaMandatAenderung) -> SEPAMandat:
    # In-place: Referenz, Unterzeichnungsdatum und Sequenztyp bleiben.
    ziel.iban = antrag.iban
    ziel.bic = antrag.bic
    ziel.save(update_fields=['iban', 'bic'])
    return ziel


def _wende_an(
    antrag: PortalSepaMandatAenderung, person: Person,
    ip: str | None, user_agent: str, forwarded_roh: str,
) -> SEPAMandat:
    ziel = _pruefe_zustand(antrag, person)

    alte_iban = iban_service.normalisiere_iban(stammdaten_service.erste_iban(person))
    if antrag.aktion == P.AKTION_ANLAGE:
        alter_mandatswert = ''
        mandat = _lege_mandat_an(antrag, person)
    else:
        alter_mandatswert = f'{ziel.mandatsreferenz} {maskiere_iban(ziel.iban)}'
        mandat = _aendere_mandat(ziel, antrag)

    # R7: neue IBAN an Position 0, bisherige bleiben (E-Banking-Zuordnung).
    if antrag.iban != alte_iban:
        stammdaten_service.pflege_ibans(person, antrag.iban)
        stammdaten_service.protokolliere(
            person, 'iban', alte_iban, antrag.iban,
            quelle=PersonStammdatenAenderung.QUELLE_PORTAL_MAGIC_LINK,
        )
    # R6: GoBD-Eintrag mit Verweis auf den Nachweis.
    stammdaten_service.protokolliere(
        person, 'sepa_mandat', alter_mandatswert,
        f'{mandat.mandatsreferenz} {maskiere_iban(mandat.iban)} Nachweis {antrag.pk}',
        quelle=PersonStammdatenAenderung.QUELLE_PORTAL_MAGIC_LINK,
    )

    antrag.status = P.STATUS_BESTAETIGT
    antrag.bestaetigt_am = timezone.now()
    antrag.bestaetigung_ip = ip
    antrag.bestaetigung_user_agent = (user_agent or '')[:_MAX_USER_AGENT]
    antrag.forwarded_for_roh = (forwarded_roh or '')[:255]
    antrag.kontoinhaber_erklaerung = True
    antrag.mandat = mandat
    antrag.save(update_fields=[
        'status', 'bestaetigt_am', 'bestaetigung_ip', 'bestaetigung_user_agent',
        'forwarded_for_roh', 'kontoinhaber_erklaerung', 'mandat',
    ])
    return mandat


@transaction.atomic
def _bestaetige_in_transaktion(
    token_wert: str, ip: str | None, user_agent: str, forwarded_roh: str,
) -> SEPAMandat:
    token = zugang_service.loese_token_ein(token_wert, (PortalToken.TYP_SEPA_MANDAT,))
    antrag = _lade_offenen_antrag(token, sperren=True)
    try:
        mandat = _wende_an(antrag, token.zugang.person, ip, user_agent, forwarded_roh)
    except _ZustandsKonflikt as konflikt:
        konflikt.antrag_id = antrag.pk
        raise
    transaction.on_commit(lambda: _sende_bestaetigungsmail(antrag))
    return mandat


def _sende_bestaetigungsmail(antrag: PortalSepaMandatAenderung) -> None:
    """Nach dem Commit; ein Mailfehler macht das erteilte Mandat nicht ungültig."""
    try:
        mail_service.versende_sepa_mandat_bestaetigung(antrag)
    except Exception:
        logger.exception(
            'Portal: Bestätigungsmail zum SEPA-Mandat (Antrag %s) fehlgeschlagen.', antrag.pk,
        )


def _verwirf_nach_konflikt(antrag_id, grund: str) -> None:
    """Eigene Transaktion: die Verwerfung muss den Rollback des Bestätigungsversuchs überleben."""
    with transaction.atomic():
        antrag = (
            P.objects.select_for_update()
            .filter(pk=antrag_id, status=P.STATUS_OFFEN).first()
        )
        if antrag is None:
            return
        antrag.status = P.STATUS_VERWORFEN
        antrag.verworfen_grund = grund[:200]
        antrag.save(update_fields=['status', 'verworfen_grund'])
        if antrag.token_id:
            PortalToken.objects.filter(
                pk=antrag.token_id, verbraucht_am__isnull=True,
            ).update(verbraucht_am=timezone.now())


def bestaetige_mandat(
    token_wert: str, *, ip: str | None, user_agent: str, forwarded_roh: str,
    kontoinhaber_erklaerung: bool,
) -> SEPAMandat:
    """Macht den Antrag wirksam — nur auf ausdrückliche Erklärung des Kontoinhabers.

    Ohne ``kontoinhaber_erklaerung`` passiert nichts, der Token bleibt
    gültig. Die Datenbankarbeit läuft atomar in ``_bestaetige_in_transaktion``;
    diese Funktion ist bewusst nicht selbst atomar, damit das Verwerfen bei
    einem Zustandskonflikt (eigene Transaktion) nicht mit zurückgerollt wird.
    """
    if not kontoinhaber_erklaerung:
        raise SepaMandatFehler(
            'Bitte bestätigen Sie, dass Sie Inhaber des angegebenen Kontos sind.'
        )
    try:
        mandat = _bestaetige_in_transaktion(token_wert, ip, user_agent, forwarded_roh)
    except _ZustandsKonflikt as konflikt:
        antrag_id = getattr(konflikt, 'antrag_id', None)
        if antrag_id is not None:
            _verwirf_nach_konflikt(antrag_id, str(konflikt))
        raise SepaMandatFehler(f'{konflikt} {_NEU_ANFORDERN}') from konflikt
    return mandat


def bestaetigungs_antwort(mandat: SEPAMandat) -> dict:
    """Antwortdaten nach erfolgreicher Bestätigung (für die View)."""
    antrag = (
        mandat.portal_nachweise.filter(status=P.STATUS_BESTAETIGT)
        .select_related('eigentumsverhaeltnis__einheit__objekt')
        .order_by('-bestaetigt_am').first()
    )
    aenderung = antrag is not None and antrag.aktion == P.AKTION_AENDERUNG
    return {
        'detail': (
            'Ihr SEPA-Lastschriftmandat wurde geändert.' if aenderung
            else 'Ihr SEPA-Lastschriftmandat wurde erteilt.'
        ),
        'mandatsreferenz': mandat.mandatsreferenz,
        'geltungsbereich_text': geltungsbereich_text_fuer_antrag(antrag) if antrag else '',
        'aktion': _aktion_von(antrag) if antrag else AKTION_ERTEILEN,
    }
