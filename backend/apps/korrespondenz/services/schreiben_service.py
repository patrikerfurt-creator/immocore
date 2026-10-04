"""Schreiben: Erstellung, Freigabe, Versand, Statusübergänge (Spec 7.1-7.3, 3.10).

EINZIGE Stelle für Statusübergänge von ``Schreiben`` (kein Signal, kein
Direktzugriff auf ``status`` anderswo)::

    entwurf -> zur_pruefung -> freigegeben -> versendet
                   |               |
               verworfen     versand_fehlgeschlagen -> (erneut) freigegeben

* ``erstellen``/``erstelle_aus_version``: Kontext bauen, sofort rendern.
  Erfolg -> ``zur_pruefung``; Render-/Layoutfehler -> bleibt ``entwurf`` mit
  ``fehler`` ("nicht erzeugbar").
* ``freigeben``: erzeugt das PDF (``pdf_service``) aus dem gespeicherten
  Endtext - es wird nach der Freigabe nie neu gerendert.
* ``versenden``: E-Mail (PDF als Anhang) oder Brief. Briefe werden nicht hier
  gedruckt, sondern über ``druckstapel_service`` gebündelt; ``versendet`` wird
  ein Brief erst mit ``bestaetige_druckstapel`` ("gedruckt und kuvertiert").
* Ein Schreiben gilt erst als ``versendet``, wenn ALLE Kanalanteile erledigt
  sind: E-Mail gesendet (``mail_message_id``) und, wenn ein Brief nötig ist
  (Kanal Brief, ``beides``, Mahnstufe 3), der Druckstapel bestätigt.

Fehler, die der Nutzer beheben kann, kommen als ``ValidationError``.
"""
import logging
from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.korrespondenz.models import Briefbogen, Druckstapel, Schreiben, SchreibenNummerZaehler
from apps.vorgaenge.models import VorgangEreignis

from . import (
    anlagen_service, brief_layout_service, kanal_service, kontext_service, mail_versand_service,
    pdf_service, render_service, vorlage_service,
)
from .render_service import RenderErgebnis, RenderFehler

logger = logging.getLogger(__name__)

UEBERGAENGE = {
    'entwurf':                {'zur_pruefung', 'verworfen'},
    'zur_pruefung':           {'freigegeben', 'verworfen'},
    'freigegeben':            {'versendet', 'versand_fehlgeschlagen'},
    'versand_fehlgeschlagen': {'freigegeben', 'versendet'},
    'versendet':              set(),
    'verworfen':              set(),
}

# Reservierte Schlüssel in ``Schreiben.kontext_snapshot`` (kollidieren nie mit
# Platzhaltern, deren Namen immer ``gruppe.name`` lauten): Betreff und Datum des
# gerenderten Endtexts, damit Freigabe und Vorschau exakt das Geprüfte drucken.
SNAPSHOT_BETREFF = '_betreff'
SNAPSHOT_DATUM = '_datum'
# Beim Erzeugen aufgelöste Vorlagen-Anlagen (Phase 6b): ``[{'bezeichnung', 'dokument_id'}]``.
SNAPSHOT_ANLAGEN = '_anlagen'


@dataclass
class VersandErgebnis:
    """Ergebnis von ``versenden``.

    ``ergebnis``: ``versendet`` (fertig), ``druckstapel`` (Brief wartet auf
    Druck/Bestätigung) oder ``fehlgeschlagen`` (``hinweis`` nennt die Ursache).
    """
    schreiben: Schreiben
    ergebnis: str
    hinweis: str = ''


# --------------------------------------------------------------------------
# Nummer, Sperre, Statusübergang
# --------------------------------------------------------------------------

@transaction.atomic
def naechste_nummer(jahr: int = None) -> str:
    """Vergibt atomar die nächste Nummer ``KS-YYYY-000123`` (Zähler je Kalenderjahr)."""
    jahr = jahr or timezone.localdate().year
    zaehler, _ = SchreibenNummerZaehler.objects.select_for_update().get_or_create(
        jahr=jahr, defaults={'letzter_zaehler': 0},
    )
    zaehler.letzter_zaehler += 1
    zaehler.save(update_fields=['letzter_zaehler'])
    return f'KS-{jahr}-{zaehler.letzter_zaehler:06d}'


def _sperre(schreiben: Schreiben) -> Schreiben:
    """Sperrt die Zeile (Transaktion nötig) und lädt die Instanz des Aufrufers frisch."""
    Schreiben.objects.select_for_update().get(pk=schreiben.pk)
    schreiben.refresh_from_db()
    return schreiben


def _uebergang(schreiben: Schreiben, neu: str, **felder) -> None:
    """Setzt den neuen Status (nur erlaubte Übergänge) plus weitere Felder und speichert."""
    if neu != schreiben.status and neu not in UEBERGAENGE[schreiben.status]:
        raise ValidationError(
            f'{schreiben.nummer}: Statuswechsel "{schreiben.status}" -> "{neu}" ist nicht erlaubt.'
        )
    schreiben.status = neu
    for name, wert in felder.items():
        setattr(schreiben, name, wert)
    schreiben.save(update_fields=['status', *felder])


def _erwarte_status(schreiben: Schreiben, erlaubt: tuple, aktion: str) -> None:
    if schreiben.status not in erlaubt:
        raise ValidationError(
            f'{schreiben.nummer} ({schreiben.get_status_display()}) kann nicht {aktion} werden.'
        )


# --------------------------------------------------------------------------
# Kontext, Rendern
# --------------------------------------------------------------------------

def _ermittle_objekt(objekt, einheit, eigentumsverhaeltnis, vorgang, mahnung, wechsel):
    """Objekt für die Vorlagen-Auflösung und die Ablage (explizit > Einheit > EV > Vorgang > Mahnung > Wechsel)."""
    if objekt is not None:
        return objekt
    if einheit is not None:
        return einheit.objekt
    if eigentumsverhaeltnis is not None:
        return eigentumsverhaeltnis.einheit.objekt
    if vorgang is not None and vorgang.objekt_id:
        return vorgang.objekt
    if mahnung is not None:
        return mahnung.lauf.objekt
    if wechsel is not None:
        return wechsel.objekt
    return None


def _ermittle_einheit(einheit, eigentumsverhaeltnis, vorgang, wechsel):
    if einheit is not None:
        return einheit
    if eigentumsverhaeltnis is not None:
        return eigentumsverhaeltnis.einheit
    if wechsel is not None:
        return wechsel.einheit
    if vorgang is not None and vorgang.einheit_id:
        return vorgang.einheit
    return None


def _briefbogen_fuer(vorlage):
    """Briefbogen der Vorlage, sonst der aktive Standard-Briefbogen (``None`` = keiner)."""
    if vorlage.briefbogen_id:
        return vorlage.briefbogen
    return Briefbogen.objects.filter(ist_standard=True, aktiv=True).first()


def _baue_kontext(schreiben: Schreiben, briefbogen, heute: date) -> dict:
    version = schreiben.vorlage_version
    # Zustellungsbevollmächtigter: Ist einer hinterlegt, trägt der Brief dessen
    # Anschrift/Name/Anrede. Der Schreiben-Datensatz bleibt beim Eigentümer.
    return kontext_service.baue_kontext(
        version.vorlage.anlass, person=schreiben.empfaenger.zustell_adressat(),
        objekt=schreiben.objekt,
        einheit=schreiben.einheit, eigentumsverhaeltnis=schreiben.eigentumsverhaeltnis,
        mahnung=schreiben.mahnung, eigentuemerwechsel=schreiben.eigentuemerwechsel,
        vorgang=schreiben.vorgang, eingabewerte=schreiben.eingabewerte,
        parameter=version.parameter, unterzeichner=schreiben.unterzeichner,
        briefbogen=briefbogen, schreiben_nummer=schreiben.nummer,
        ihr_zeichen=schreiben.ihr_zeichen, ihr_schreiben_vom=schreiben.ihr_schreiben_vom,
        heute=heute,
    )


def _pruefe_layout(briefbogen, kontext: dict) -> None:
    """Wirft ``RenderFehler``, wenn der Brief auf dem Briefbogen nicht erzeugbar wäre.

    Dieselben Prüfungen wie beim PDF (Fußzeilen-Bankkonto, Anschrift, Anrede,
    Grußformel) - schon beim Erstellen, damit "nicht erzeugbar" im Postausgang
    steht und nicht erst bei der Freigabe auffällt.
    """
    if briefbogen is None:
        raise RenderFehler('Kein Briefbogen vorhanden (weder an der Vorlage noch als Standard).')
    brief_layout_service.baue_fusszeile(briefbogen, kontext)
    brief_layout_service.baue_anschrift(kontext)
    brief_layout_service.baue_anrede(kontext)
    brief_layout_service.baue_schluss(kontext)


def _rendere(schreiben: Schreiben, heute: date, inhalt: list = None):
    """Kontext bauen, Vorlage rendern, Layout prüfen. Gibt ``(ergebnis, kontext, briefbogen)`` zurück.

    ``inhalt``: Blockliste, die statt ``Version.inhalt`` gerendert wird (Textanpassung);
    ohne Angabe gilt ``inhalt_angepasst``, sonst der Inhalt der Version.
    Wirft ``RenderFehler`` mit der Ursache.
    """
    version = schreiben.vorlage_version
    briefbogen = _briefbogen_fuer(version.vorlage)
    kontext = _baue_kontext(schreiben, briefbogen, heute)
    if inhalt is None:
        inhalt = schreiben.inhalt_angepasst if schreiben.inhalt_angepasst is not None else version.inhalt
    quelle = SimpleNamespace(
        betreff=version.betreff, inhalt=inhalt, eingabefelder=version.eingabefelder,
        pflicht_platzhalter=version.pflicht_platzhalter,
    )
    ergebnis = render_service.render(
        quelle, kontext, schreiben.eingabewerte,
        bausteine=vorlage_service.lade_bausteine(inhalt, schreiben.objekt),
    )
    if not ergebnis.ok:
        raise RenderFehler(ergebnis.fehler)
    _pruefe_layout(briefbogen, kontext)
    # Anlagen (Bedingung, Pflicht) jetzt auflösen: fehlt eine Pflichtanlage -> "nicht erzeugbar".
    # Die Auswahl wird eingefroren, Vorschau und Freigabe laden genau diese Dokumente.
    anlagen = anlagen_service.loese_auf(version.vorlage, schreiben.objekt, kontext)
    ergebnis.snapshot[SNAPSHOT_ANLAGEN] = anlagen_service.als_refs(anlagen)
    return ergebnis, kontext, briefbogen


def _uebernimm_rendering(schreiben: Schreiben, ergebnis: RenderErgebnis, heute: date) -> None:
    schreiben.html_gerendert = ergebnis.html
    schreiben.kontext_snapshot = {
        **ergebnis.snapshot, SNAPSHOT_BETREFF: ergebnis.betreff, SNAPSHOT_DATUM: heute.isoformat(),
    }
    schreiben.fehler = ''


def _rekonstruiere(schreiben: Schreiben):
    """Baut aus dem gespeicherten Endtext ``(kontext, ergebnis, briefbogen)`` für das PDF - ohne neu zu rendern."""
    snapshot = schreiben.kontext_snapshot or {}
    if not schreiben.html_gerendert or SNAPSHOT_BETREFF not in snapshot:
        raise RenderFehler('Schreiben ist nicht gerendert.')
    heute = date.fromisoformat(snapshot[SNAPSHOT_DATUM])
    briefbogen = _briefbogen_fuer(schreiben.vorlage_version.vorlage)
    kontext = _baue_kontext(schreiben, briefbogen, heute)
    ergebnis = RenderErgebnis(html=schreiben.html_gerendert, betreff=snapshot[SNAPSHOT_BETREFF])
    return kontext, ergebnis, briefbogen


def _rendere_und_uebernimm(schreiben: Schreiben) -> None:
    """Rendert den Entwurf: Erfolg -> ``zur_pruefung``, Fehler -> bleibt ``entwurf`` mit ``fehler``."""
    heute = timezone.localdate()
    try:
        with transaction.atomic():
            ergebnis, _, _ = _rendere(schreiben, heute)
    except RenderFehler as exc:
        fehler = str(exc)
    except Exception as exc:  # noqa: BLE001 - ein Schreiben darf nie einen ganzen Lauf abbrechen
        logger.exception('Schreiben %s: unerwarteter Fehler beim Erzeugen.', schreiben.nummer)
        fehler = f'Unerwarteter Fehler beim Erzeugen: {exc}'
    else:
        _uebernimm_rendering(schreiben, ergebnis, heute)
        _uebergang(
            schreiben, 'zur_pruefung', html_gerendert=schreiben.html_gerendert,
            kontext_snapshot=schreiben.kontext_snapshot, fehler='',
        )
        return
    schreiben.fehler = fehler
    schreiben.save(update_fields=['fehler'])


# --------------------------------------------------------------------------
# Vorgangsverlauf
# --------------------------------------------------------------------------

def _vermerke_vorgang(schreiben: Schreiben, typ: str, user, *, intern: bool) -> None:
    """Ereignis im Vorgangsverlauf (nur wenn das Schreiben zu einem Vorgang gehört)."""
    if not schreiben.vorgang_id:
        return
    betreff = (schreiben.kontext_snapshot or {}).get(SNAPSHOT_BETREFF, '')
    aktion = 'erstellt' if typ == 'schreiben_erstellt' else 'versendet'
    VorgangEreignis.objects.create(
        vorgang_id=schreiben.vorgang_id, typ=typ, intern=intern, erstellt_von=user,
        neuer_wert=schreiben.nummer,
        text=f'Schreiben {schreiben.nummer} {aktion}' + (f': {betreff}' if betreff else ''),
    )


# --------------------------------------------------------------------------
# Erstellen
# --------------------------------------------------------------------------

@transaction.atomic
def erstelle_aus_version(
    version, empfaenger, *, objekt=None, einheit=None, eigentumsverhaeltnis=None, vorgang=None,
    mahnung=None, eigentuemerwechsel=None, serienlauf=None, eingabewerte=None, kanal=None,
    unterzeichner=None, ihr_zeichen='', ihr_schreiben_vom=None, user=None,
) -> Schreiben:
    """Legt ein Schreiben zu einer festen ``VorlagenVersion`` an und rendert es sofort.

    Rückgabe: ``zur_pruefung`` bei Erfolg, sonst ``entwurf`` mit ``fehler``.
    """
    if version.status != 'freigegeben':
        raise ValidationError(f'{version} ist nicht freigegeben.')
    einheit = _ermittle_einheit(einheit, eigentumsverhaeltnis, vorgang, eigentuemerwechsel)
    objekt = _ermittle_objekt(
        objekt, einheit, eigentumsverhaeltnis, vorgang, mahnung, eigentuemerwechsel,
    )
    # Kanalwahl (Post/E-Mail) richtet sich nach dem tatsächlichen Zusteller.
    entscheidung = kanal_service.kanal_aufloesen(
        version.vorlage, empfaenger.zustell_adressat(), kanal=kanal,
        mahnstufe=mahnung.mahnstufe if mahnung is not None else None,
        letzte_stufe=kanal_service.letzte_stufe_von(mahnung) if mahnung is not None else None,
    )
    schreiben = Schreiben.objects.create(
        nummer=naechste_nummer(), vorlage_version=version, empfaenger=empfaenger,
        objekt=objekt, einheit=einheit, eigentumsverhaeltnis=eigentumsverhaeltnis,
        vorgang=vorgang, mahnung=mahnung, eigentuemerwechsel=eigentuemerwechsel,
        serienlauf=serienlauf, unterzeichner=unterzeichner or user,
        ihr_zeichen=ihr_zeichen or '', ihr_schreiben_vom=ihr_schreiben_vom,
        eingabewerte=eingabewerte or {}, kanal=entscheidung.kanal, status='entwurf',
        erstellt_von=user,
    )
    _rendere_und_uebernimm(schreiben)
    _vermerke_vorgang(schreiben, 'schreiben_erstellt', user, intern=True)
    return schreiben


def erstellen(vorlage_code: str, empfaenger, *, objekt=None, einheit=None,
              eigentumsverhaeltnis=None, vorgang=None, mahnung=None, eigentuemerwechsel=None,
              eingabewerte=None, kanal=None, unterzeichner=None, ihr_zeichen='',
              ihr_schreiben_vom=None, user=None) -> Schreiben:
    """Einzelschreiben (7.1): löst die Vorlage auf, rendert sofort, legt das Schreiben an.

    Raises ``VorlageNichtGefunden`` (keine aktive Vorlage / keine freigegebene Version).
    """
    einheit_ = _ermittle_einheit(einheit, eigentumsverhaeltnis, vorgang, eigentuemerwechsel)
    objekt_ = _ermittle_objekt(objekt, einheit_, eigentumsverhaeltnis, vorgang, mahnung, eigentuemerwechsel)
    vorlage = vorlage_service.aufloesen(vorlage_code, objekt_)
    version = vorlage_service.aktive_version(vorlage)
    return erstelle_aus_version(
        version, empfaenger, objekt=objekt, einheit=einheit,
        eigentumsverhaeltnis=eigentumsverhaeltnis, vorgang=vorgang, mahnung=mahnung,
        eigentuemerwechsel=eigentuemerwechsel, eingabewerte=eingabewerte, kanal=kanal,
        unterzeichner=unterzeichner, ihr_zeichen=ihr_zeichen,
        ihr_schreiben_vom=ihr_schreiben_vom, user=user,
    )


@transaction.atomic
def erneut_erzeugen(schreiben: Schreiben) -> Schreiben:
    """Neuer Versuch für ein "nicht erzeugbares" Schreiben (``entwurf``), z. B. nach Korrektur der Stammdaten."""
    _sperre(schreiben)
    _erwarte_status(schreiben, ('entwurf',), 'erneut erzeugt')
    _rendere_und_uebernimm(schreiben)
    return schreiben


@transaction.atomic
def passe_an(schreiben: Schreiben, inhalt: list) -> Schreiben:
    """Textanpassung: ersetzt den Inhalt (Blockliste) dieses einen Schreibens und rendert neu.

    Nur bei ``Vorlage.einzeln_bearbeitbar`` und Status ``zur_pruefung``. Ist der
    neue Inhalt nicht renderbar, bleibt das Schreiben unverändert (``ValidationError``).
    """
    _sperre(schreiben)
    _erwarte_status(schreiben, ('zur_pruefung',), 'angepasst')
    if not schreiben.vorlage_version.vorlage.einzeln_bearbeitbar:
        raise ValidationError('Diese Vorlage erlaubt keine Textanpassung im Einzelschreiben.')
    if not isinstance(inhalt, list) or not all(isinstance(b, dict) for b in inhalt):
        raise ValidationError('Der Inhalt muss eine Liste von Blöcken sein.')
    heute = date.fromisoformat(schreiben.kontext_snapshot[SNAPSHOT_DATUM])
    try:
        ergebnis, _, _ = _rendere(schreiben, heute, inhalt=inhalt)
    except RenderFehler as exc:
        raise ValidationError(f'Angepasster Text nicht renderbar: {exc}') from exc
    _uebernimm_rendering(schreiben, ergebnis, heute)
    schreiben.inhalt_angepasst = inhalt
    schreiben.save(update_fields=['inhalt_angepasst', 'html_gerendert', 'kontext_snapshot', 'fehler'])
    return schreiben


# --------------------------------------------------------------------------
# Freigeben, Verwerfen
# --------------------------------------------------------------------------

def _anlagen_fuer(schreiben: Schreiben):
    """Anlagen-PDFs hinter dem Schreiben: eingefrorene Vorlagen-Anlagen, dann ggf. Kontoauszug (Mahnschreiben).

    ``None`` ohne Anlagen. Wirft ``RenderFehler``, wenn eine Anlage nicht mehr verfügbar ist.
    """
    anlagen = anlagen_service.lade_pdfs((schreiben.kontext_snapshot or {}).get(SNAPSHOT_ANLAGEN))
    if schreiben.mahnung_id:
        from . import mahn_anbindung_service  # lazy: mahn_anbindung_service importiert dieses Modul
        anlagen += mahn_anbindung_service.anlagen_fuer(schreiben) or []
    return anlagen or None


@transaction.atomic
def _freigeben(schreiben: Schreiben, user) -> Schreiben:
    _sperre(schreiben)
    _erwarte_status(schreiben, ('zur_pruefung',), 'freigegeben')
    kontext, ergebnis, briefbogen = _rekonstruiere(schreiben)
    pdf_service.erzeuge_schreiben_dokument(
        schreiben, kontext, briefbogen, ergebnis, user, anlagen=_anlagen_fuer(schreiben),
    )
    _uebergang(
        schreiben, 'freigegeben', freigegeben_am=timezone.now(), freigegeben_von=user, fehler='',
    )
    return schreiben


def freigeben(schreiben: Schreiben, user) -> Schreiben:
    """``zur_pruefung`` -> ``freigegeben``: erzeugt genau ein revisionssicheres PDF im DMS.

    Ist das PDF nicht erzeugbar, bleibt das Schreiben ``zur_pruefung`` (mit
    ``fehler``) und es wird ein ``ValidationError`` geworfen.
    """
    try:
        return _freigeben(schreiben, user)
    except RenderFehler as exc:
        Schreiben.objects.filter(pk=schreiben.pk).update(fehler=str(exc))
        schreiben.fehler = str(exc)
        raise ValidationError(f'Freigabe nicht möglich, Schreiben nicht erzeugbar: {exc}') from exc


@transaction.atomic
def verwerfen(schreiben: Schreiben, user=None) -> Schreiben:
    """``zur_pruefung`` (oder nicht erzeugbarer ``entwurf``) -> ``verworfen``.

    Ein freigegebenes Schreiben hat ein revisionssicheres PDF und wird nicht verworfen.
    """
    _sperre(schreiben)
    _erwarte_status(schreiben, ('entwurf', 'zur_pruefung'), 'verworfen')
    _uebergang(schreiben, 'verworfen')
    return schreiben


# --------------------------------------------------------------------------
# Versand
# --------------------------------------------------------------------------

def _wunschkanal(schreiben: Schreiben, ueberschreibung) -> str:
    """Kanalwunsch für die erneute Auflösung beim Versand (Zustimmung kann sich geändert haben)."""
    if ueberschreibung == 'brief' or schreiben.kanal == 'brief':
        return 'brief'
    return 'beides' if kanal_service.auch_brief(schreiben) else 'email'


def _lese_pdf(schreiben: Schreiben) -> bytes:
    with schreiben.dokument.datei.open('rb') as datei:
        return datei.read()


def _sende_mail(schreiben: Schreiben) -> tuple:
    """Versendet die Mail. Gibt ``(message_id, fehler)`` zurück - genau eines von beiden ist leer."""
    brief_bleibt_moeglich = ' Der Versand als Brief bleibt möglich.'
    if not mail_versand_service.versand_konfiguriert():
        return '', 'E-Mail-Versand ist auf diesem Server nicht konfiguriert - es wurde nichts versendet.' + brief_bleibt_moeglich
    # Objektbezogenes Versand-Gate (schrittweiser Rollout, wie Handwerkeraufträge/EV-Einladungen).
    # Greift nur bei gesetztem Objekt; ein Schreiben ohne Objekt wird dadurch nicht blockiert.
    if schreiben.objekt_id and not schreiben.objekt.mailversand_aktiv:
        return '', (
            'Das Objekt ist noch nicht für den E-Mail-Versand freigeschaltet '
            '(mailversand_aktiv=False).' + brief_bleibt_moeglich
        )
    betreff = schreiben.kontext_snapshot.get(SNAPSHOT_BETREFF, '')
    briefbogen = _briefbogen_fuer(schreiben.vorlage_version.vorlage)
    message_id = mail_versand_service.neue_message_id()
    try:
        mail_versand_service.sende_schreiben(
            adresse=kanal_service.erste_email(schreiben.empfaenger.zustell_adressat()),
            betreff=betreff,
            text=mail_versand_service.baue_text(
                schreiben.vorlage_version.email_begleittext, betreff=betreff,
                nummer=schreiben.nummer, firma=briefbogen.firma_name if briefbogen else '',
            ),
            pdf=_lese_pdf(schreiben), dateiname=schreiben.dokument.dateiname,
            message_id=message_id,
        )
    except mail_versand_service.MailVersandFehler as exc:
        return '', f'{exc}{brief_bleibt_moeglich}'
    return message_id, ''


def _schliesse_ab_wenn_fertig(schreiben: Schreiben, user) -> bool:
    """Setzt ``versendet``/``versendet_am``, sobald alle Kanalanteile erledigt sind."""
    mail_fertig = schreiben.kanal != 'email' or bool(schreiben.mail_message_id)
    druckstapel = schreiben.druckstapel if schreiben.druckstapel_id else None
    brief_fertig = (
        not kanal_service.braucht_brief(schreiben)
        or (druckstapel is not None and druckstapel.status == 'bestaetigt')
    )
    if not (mail_fertig and brief_fertig) or schreiben.status not in ('freigegeben', 'versand_fehlgeschlagen'):
        return False
    _uebergang(schreiben, 'versendet', versendet_am=timezone.now(), fehler='')
    _vermerke_vorgang(schreiben, 'schreiben_versendet', user, intern=False)
    return True


@transaction.atomic
def versenden(schreiben: Schreiben, user=None, *, kanal: str = None) -> VersandErgebnis:
    """Versendet ein freigegebenes (oder ``versand_fehlgeschlagen``es) Schreiben.

    * Kanal wird neu aufgelöst (``kanal_service``); ``kanal='brief'`` erzwingt den
      Brief, z. B. nach fehlgeschlagener E-Mail.
    * E-Mail: PDF als Anhang. Nicht versandfähig (kein SMTP/Graph, Objekt nicht
      freigeschaltet) -> ``versand_fehlgeschlagen`` mit Hinweis.
    * Brief: bleibt ``freigegeben`` und wartet auf den Druckstapel; ``versendet_am``
      setzt erst ``bestaetige_druckstapel``.
    * Eine bereits versendete Mail wird nie ein zweites Mal gesendet.
    """
    if kanal not in (None, 'brief'):
        raise ValidationError('Ein Kanalwechsel ist nur auf "brief" möglich.')
    _sperre(schreiben)
    _erwarte_status(schreiben, ('freigegeben', 'versand_fehlgeschlagen'), 'versendet')
    if not schreiben.dokument_id:
        raise ValidationError(f'{schreiben.nummer} hat noch kein PDF.')

    mahnstufe = schreiben.mahnung.mahnstufe if schreiben.mahnung_id else None
    entscheidung = kanal_service.kanal_aufloesen(
        schreiben.vorlage_version.vorlage, schreiben.empfaenger.zustell_adressat(),
        kanal=_wunschkanal(schreiben, kanal), mahnstufe=mahnstufe,
        letzte_stufe=kanal_service.letzte_stufe_von(schreiben.mahnung) if schreiben.mahnung_id else None,
    )
    schreiben.kanal = entscheidung.kanal

    if entscheidung.kanal == 'email' and not schreiben.mail_message_id:
        message_id, fehler = _sende_mail(schreiben)
        if fehler:
            _uebergang(schreiben, 'versand_fehlgeschlagen', fehler=fehler, kanal=schreiben.kanal)
            return VersandErgebnis(schreiben, 'fehlgeschlagen', fehler)
        schreiben.mail_message_id = message_id

    _uebergang(
        schreiben, 'freigegeben', fehler='', kanal=schreiben.kanal,
        mail_message_id=schreiben.mail_message_id,
    )
    if _schliesse_ab_wenn_fertig(schreiben, user):
        return VersandErgebnis(schreiben, 'versendet')
    return VersandErgebnis(schreiben, 'druckstapel', entscheidung.hinweis)


@transaction.atomic
def bestaetige_druckstapel(stapel: Druckstapel, user) -> Druckstapel:
    """Bestätigung "gedruckt und kuvertiert": Stapel -> ``bestaetigt``, Schreiben -> ``versendet`` (sofern fertig)."""
    stapel = Druckstapel.objects.select_for_update().get(pk=stapel.pk)
    if stapel.status != 'offen':
        raise ValidationError('Dieser Druckstapel ist bereits bestätigt.')
    stapel.status = 'bestaetigt'
    stapel.bestaetigt_am = timezone.now()
    stapel.bestaetigt_von = user
    stapel.save(update_fields=['status', 'bestaetigt_am', 'bestaetigt_von'])
    for schreiben in stapel.schreiben.select_for_update(of=('self',)).select_related('druckstapel'):
        _schliesse_ab_wenn_fertig(schreiben, user)
    return stapel


# --------------------------------------------------------------------------
# PDF-Ausgabe
# --------------------------------------------------------------------------

def pdf_bytes(schreiben: Schreiben) -> bytes:
    """PDF des Schreibens: das abgelegte Dokument, vor der Freigabe eine (nicht abgelegte) Vorschau.

    Die Vorschau entsteht aus demselben gespeicherten Endtext wie später das
    freigegebene PDF.
    """
    if schreiben.dokument_id:
        return _lese_pdf(schreiben)
    if schreiben.status != 'zur_pruefung':
        raise ValidationError(f'{schreiben.nummer} hat kein PDF ({schreiben.get_status_display()}).')
    try:
        kontext, ergebnis, briefbogen = _rekonstruiere(schreiben)
        return pdf_service.erzeuge_pdf(
            schreiben.vorlage_version, kontext, briefbogen, ergebnis,
            anlagen=_anlagen_fuer(schreiben),
        )
    except RenderFehler as exc:
        raise ValidationError(f'Vorschau nicht erzeugbar: {exc}') from exc
