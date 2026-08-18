"""
Handwerkerauftrag-Service (Phase B, Umsetzung von
docs/CLAUDE_CODE_ANLEITUNG_HANDWERKERAUFTRAG_v1_0.md, Kap. 2/3 — mit
verbindlichen Korrekturen gegenüber der Spec, siehe Orchestrator-Auftrag).

Business-Logik rund um Anlage, Statuswechsel, Token-basierte Bestätigung
(Annahme/Ablehnung durch den Handwerker ohne Login), erneuten Mailversand und
Rechnungszuordnung eines ``Handwerkerauftrag``. Statuswechsel laufen
AUSSCHLIESSLICH über ``wechsle_status`` — analog
``apps.vorgaenge.services.vorgang_service`` — damit ungültige Übergänge und
fehlende Audit-Einträge (``HandwerkerauftragEreignis``) ausgeschlossen sind
(GoBD-Prinzip: keine stille Änderung).

KEINE Django-Signals: der Mailversand wird explizit über
``transaction.on_commit`` aus dem jeweiligen Service-Aufruf heraus ausgelöst.
"""
import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.handwerker.models import (
    AuftragsbestaetigungsToken,
    Handwerkerauftrag,
    HandwerkerauftragEreignis,
)
from apps.vorgaenge.models import VorgangEreignis

logger = logging.getLogger(__name__)


class TokenAbgelaufen(Exception):
    """Der Bestätigungs-Token ist über seine Gültigkeitsfrist hinaus, wurde
    aber (noch) nicht verbraucht. Von der API auf HTTP 410 zu mappen."""


class TokenVerbraucht(Exception):
    """Der Bestätigungs-Token wurde bereits für eine Annahme/Ablehnung
    verwendet (Einmalverwendung). Von der API auf HTTP 409 zu mappen."""


# Erlaubte Statusübergänge (Orchestrator-Vorgabe Schritt 2 — die Spec hat
# hier KEINE Übergangstabelle). Terminal-Stati (abgeschlossen, storniert)
# haben eine leere Zielmenge.
_ERLAUBTE_UEBERGAENGE = {
    'entwurf':       {'versendet', 'storniert'},
    'versendet':     {'angenommen', 'abgelehnt', 'abgelaufen', 'storniert'},
    'angenommen':    {'in_arbeit', 'abgeschlossen', 'storniert'},
    'in_arbeit':     {'abgeschlossen', 'storniert'},
    'abgelehnt':     {'storniert'},
    'abgelaufen':    {'versendet', 'storniert'},
    'abgeschlossen': set(),
    'storniert':     set(),
}

_ZEITSTEMPEL_FELD_JE_STATUS = {
    'versendet':     'versendet_am',
    'angenommen':    'angenommen_am',
    'abgelehnt':     'abgelehnt_am',
    'abgeschlossen': 'abgeschlossen_am',
}

# Beauftragungsvermerk im Vorgangs-Verlauf (Orchestrator-Vorgabe: alle
# Handwerker-Schritte sind für den Eigentümer sichtbar). ``versendet`` ist
# bewusst NICHT hier gelistet — der Beauftragungsvermerk (Typ
# 'handwerker_beauftragt') wird ausschließlich in ``markiere_versendet``
# geschrieben (dort mit eigener Einmaligkeitsprüfung), nicht bei jedem
# generischen Übergang nach 'versendet'.
_VORGANG_EREIGNIS_JE_STATUS = {
    'angenommen':    ('handwerker_angenommen', 'Handwerker hat den Auftrag angenommen'),
    'abgelehnt':     ('handwerker_abgelehnt', 'Handwerker hat den Auftrag abgelehnt'),
    'abgeschlossen': ('handwerker_abgeschlossen', 'Handwerkerauftrag abgeschlossen'),
    'abgelaufen':    ('handwerker_abgelaufen', 'Auftragsbestätigung abgelaufen'),
}


def _handwerker_beauftragt_bereits_vermerkt(auftrag: Handwerkerauftrag) -> bool:
    """Prüft, ob für diesen Auftrag bereits ein Beauftragungsvermerk
    (``VorgangEreignis`` Typ ``handwerker_beauftragt``) im Vorgangs-Verlauf
    existiert — Einmaligkeitsschutz gegen doppelte Vermerke bei erneutem
    Versand (``versende_erneut`` -> ``markiere_versendet``).

    Lösung: Suche über die (eindeutige, unveränderliche) Auftragsnummer im
    Ereignistext statt über ein eigenes Marker-Feld an ``Handwerkerauftrag``
    — kein zusätzliches Modellfeld/keine Migration nötig, und die Nummer ist
    ohnehin Teil des geschriebenen Texts (siehe ``markiere_versendet``).
    """
    if not auftrag.vorgang_id:
        return False
    return VorgangEreignis.objects.filter(
        vorgang_id=auftrag.vorgang_id, typ='handwerker_beauftragt',
        text__contains=auftrag.nummer,
    ).exists()


def _vermerke_handwerker_ereignis(auftrag: Handwerkerauftrag, typ: str, text: str) -> None:
    """Schreibt einen Handwerker-Meilenstein (Beauftragung, Zusage, Ablehnung,
    Abschluss, Ablauf) als ``VorgangEreignis`` in den Verlauf des verknüpften
    Vorgangs — NUR wenn ``auftrag.vorgang_id`` gesetzt ist (Aufträge ohne
    Vorgang haben keinen Verlauf, in dem sie stehen könnten).

    Darf den Auftragsablauf NIEMALS zum Scheitern bringen: eigener Savepoint
    (``transaction.atomic()`` innerhalb der bereits laufenden Transaktion)
    plus try/except mit Logging — analog der Beleg-Kopplung in
    ``apps.rechnungen.services.verarbeitung`` (dort ebenfalls: eine
    Nebenwirkung darf den Hauptvorgang nicht blockieren, daher eigener
    Savepoint statt Ausbreitung der Exception in die äußere Transaktion).

    ``erstellt_von=None``: alle Aufrufer sind Token-/Systemauslöser (Versand,
    Handwerker-Bestätigung ohne Login, Ablauf-Task) — kein eingeloggter
    Mitarbeiter. ``intern=False`` immer (Patrik-Entscheidung: beim Handwerker
    sind ALLE Schritte für den Eigentümer sichtbar).
    """
    if not auftrag.vorgang_id:
        return
    try:
        with transaction.atomic():
            VorgangEreignis.objects.create(
                vorgang_id=auftrag.vorgang_id, typ=typ, text=text,
                erstellt_von=None, intern=False,
            )
    except Exception:
        logger.exception(
            "Vorgangs-Ereignis '%s' für Handwerkerauftrag %s konnte nicht "
            "geschrieben werden.", typ, auftrag.nummer,
        )


@transaction.atomic
def erstelle_auftrag(*, kreditor, titel, erstellt_von, vorgang=None, objekt=None,
                      beschreibung='', gewuenscht_ab=None, prioritaet=None,
                      geschaetzte_kosten=None) -> Handwerkerauftrag:
    """Legt einen neuen ``Handwerkerauftrag`` an (Status immer ``entwurf``).

    Objektermittlung (Korrektur gegenüber der Spec, die blind
    ``objekt=vorgang.objekt`` setzt): explizit übergebenes ``objekt`` hat
    Vorrang; sonst ``vorgang.objekt``; sonst ``vorgang.einheit.objekt``; wenn
    nichts davon greift, wird ein klarer ``ValidationError`` geworfen statt
    eines DB-Fehlers beim Speichern.

    ``prioritaet`` wird, sofern nicht übergeben, aus ``vorgang.prioritaet``
    vorbelegt, sonst mit ``'normal'``.

    Erzeugt zusätzlich den ``AuftragsbestaetigungsToken`` und löst den
    Mailversand NACH erfolgreichem Commit aus (Celery, ``transaction.on_commit``)
    — die Spec versendet synchron im Request und macht den Statuswechsel vom
    Rückgabewert abhängig, was bei einem SMTP-Timeout den Auftrag still in
    ``entwurf`` hängen ließe.
    """
    if objekt is None and vorgang is not None:
        if vorgang.objekt_id:
            objekt = vorgang.objekt
        elif vorgang.einheit_id:
            objekt = vorgang.einheit.objekt

    if objekt is None:
        raise ValidationError(
            "Aus diesem Vorgang kann kein Handwerkerauftrag erstellt werden, weil kein "
            "Objektbezug besteht. Objekt bitte am Vorgang ergänzen oder im Dialog auswählen."
        )

    if prioritaet is None:
        prioritaet = vorgang.prioritaet if vorgang is not None else 'normal'

    auftrag = Handwerkerauftrag(
        kreditor=kreditor, titel=titel, erstellt_von=erstellt_von,
        vorgang=vorgang, objekt=objekt, beschreibung=beschreibung,
        gewuenscht_ab=gewuenscht_ab, prioritaet=prioritaet,
        geschaetzte_kosten=geschaetzte_kosten, status='entwurf',
    )
    auftrag.full_clean()
    auftrag.save()

    # gueltig_bis und die Tokens füllt das Modell selbst (AuftragsbestaetigungsToken.save()).
    AuftragsbestaetigungsToken.objects.create(auftrag=auftrag)

    from apps.handwerker.tasks import versende_auftragsmail
    transaction.on_commit(lambda: versende_auftragsmail.delay(str(auftrag.id)))

    return auftrag


@transaction.atomic
def wechsle_status(auftrag: Handwerkerauftrag, neuer_status: str, *, erstellt_von,
                    kommentar: str | None = None, ereignis_typ: str = 'statuswechsel',
                    _system_ausloeser: bool = False) -> Handwerkerauftrag:
    """Wechselt den Status eines ``Handwerkerauftrag`` gemäß der expliziten
    Übergangstabelle (siehe ``_ERLAUBTE_UEBERGAENGE`` oben — die Spec hat
    keine Übergangstabelle).

    - Ungültiger Übergang → ``ValidationError``, KEINE DB-Änderung (alle
      Prüfungen laufen VOR jeder Mutation).
    - ``erstellt_von`` darf nur ``None`` sein, wenn der Wechsel NICHT von
      einem Sachbearbeiter über die API/das UI ausgelöst wird, sondern durch
      einen automatisierten/Token-Auslöser dieses Service-Moduls selbst
      (Ablauf-Task, Mailversand-Bestätigung, Token-Annahme/-Ablehnung durch
      den Handwerker — der kein User ist). Dafür MUSS der interne Parameter
      ``_system_ausloeser=True`` gesetzt werden; er ist bewusst nicht Teil der
      öffentlichen Signatur, die eine künftige API (Phase C) nutzen würde,
      damit von dort niemals unbemerkt ``erstellt_von=None`` durchgereicht
      werden kann.
    - Zeitstempel werden passend gesetzt (``versendet_am``, ``angenommen_am``,
      ``abgelehnt_am``, ``abgeschlossen_am``).
    - Jeder (gültige) Wechsel erzeugt genau ein ``HandwerkerauftragEreignis``.
    """
    alter_status = auftrag.status

    if neuer_status not in _ERLAUBTE_UEBERGAENGE.get(alter_status, set()):
        raise ValidationError(
            f"Statuswechsel von '{alter_status}' nach '{neuer_status}' ist nicht erlaubt."
        )
    if erstellt_von is None and not _system_ausloeser:
        raise ValidationError(
            "erstellt_von darf nur None sein bei automatisierten/Token-Auslösern."
        )

    # Ab hier ausschließlich Mutationen — alle Validierungen sind bereits durch.
    auftrag.status = neuer_status

    zeitstempel_feld = _ZEITSTEMPEL_FELD_JE_STATUS.get(neuer_status)
    if zeitstempel_feld:
        setattr(auftrag, zeitstempel_feld, timezone.now())

    auftrag.full_clean()
    auftrag.save()

    HandwerkerauftragEreignis.objects.create(
        auftrag=auftrag, typ=ereignis_typ, text=kommentar,
        alter_wert=alter_status, neuer_wert=neuer_status, erstellt_von=erstellt_von,
    )

    vorgang_ereignis = _VORGANG_EREIGNIS_JE_STATUS.get(neuer_status)
    if vorgang_ereignis:
        vorgang_typ, label = vorgang_ereignis
        text = f"{label}: {auftrag.kreditor.name} ({auftrag.nummer})"
        if neuer_status == 'abgelehnt' and auftrag.ablehnung_grund:
            text += f" — Grund: {auftrag.ablehnung_grund}"
        _vermerke_handwerker_ereignis(auftrag, vorgang_typ, text)

    return auftrag


@transaction.atomic
def markiere_versendet(auftrag: Handwerkerauftrag) -> Handwerkerauftrag:
    """Verbucht einen erfolgreichen Mailversand (ausschließlich von
    ``apps.handwerker.tasks.versende_auftragsmail`` nach erfolgreichem
    ``mail.send()`` aufgerufen).

    Wechselt den Status nach ``versendet``, sofern der Auftrag noch nicht in
    diesem Status ist (``entwurf``/``abgelaufen`` → ``versendet``). War der
    Auftrag bereits ``versendet`` (erneuter Versand über ``versende_erneut``
    ohne dass sich der Status ändert), wird kein Statuswechsel vollzogen
    (``versendet`` → ``versendet`` ist kein gültiger Übergang), sondern nur
    ``versendet_am`` aktualisiert und ein ``versand``-Ereignis geschrieben.

    Beauftragungsvermerk (``VorgangEreignis`` Typ ``handwerker_beauftragt``,
    NUR wenn ``auftrag.vorgang_id`` gesetzt ist): wird HIER geschrieben — beim
    tatsächlichen (erfolgreichen) Versand — und NICHT bereits bei
    ``erstelle_auftrag``, sonst stünde „beauftragt“ im Verlauf, obwohl die
    Mail nie rausging. Nur EINMAL je Auftrag (Einmaligkeitsprüfung über
    ``_handwerker_beauftragt_bereits_vermerkt``) — ein erneuter Versand
    (dieser Funktions-Zweig hier, zweiter Aufruf desselben Auftrags) erzeugt
    KEINEN zweiten Vermerk.
    """
    if auftrag.status in ('entwurf', 'abgelaufen'):
        auftrag = wechsle_status(
            auftrag, 'versendet', erstellt_von=None, ereignis_typ='versand',
            _system_ausloeser=True,
        )
    else:
        auftrag.versendet_am = timezone.now()
        auftrag.full_clean()
        auftrag.save()
        HandwerkerauftragEreignis.objects.create(
            auftrag=auftrag, typ='versand', erstellt_von=None,
            text='Auftragsmail erneut versendet.',
        )

    if not _handwerker_beauftragt_bereits_vermerkt(auftrag):
        _vermerke_handwerker_ereignis(
            auftrag, 'handwerker_beauftragt',
            f"Handwerker beauftragt: {auftrag.kreditor.name} ({auftrag.nummer})",
        )

    return auftrag


@transaction.atomic
def protokolliere_versandfehler(auftrag: Handwerkerauftrag, fehlertext: str) -> HandwerkerauftragEreignis:
    """Verbucht einen fehlgeschlagenen Mailversand: KEIN Statuswechsel (Auftrag
    bleibt in seinem aktuellen Status, i.d.R. ``entwurf``), nur ein
    ``versand_fehlgeschlagen``-Ereignis mit dem Fehlertext."""
    return HandwerkerauftragEreignis.objects.create(
        auftrag=auftrag, typ='versand_fehlgeschlagen', erstellt_von=None,
        text=fehlertext,
    )


@transaction.atomic
def versende_erneut(auftrag: Handwerkerauftrag, erstellt_von) -> Handwerkerauftrag:
    """Löst den Mailversand für einen Auftrag erneut aus — aus ``entwurf``,
    ``abgelaufen`` oder ``versendet`` zulässig.

    ``entwurf`` ist bewusst zusätzlich erlaubt (Korrektur aus der Phase-D-
    Abnahme, Orchestrator): schlägt der ERSTE Versand fehl (SMTP nicht
    erreichbar, Kreditor-Mail fehlte im Moment des Versands o.Ä.), bleibt der
    Auftrag korrekt in ``entwurf`` mit einem ``versand_fehlgeschlagen``-Ereignis
    (siehe ``protokolliere_versandfehler``) — ohne diese Erweiterung gäbe es
    dann KEINEN Weg mehr, den Versand erneut auszulösen, der Auftrag bliebe
    dauerhaft unversendbar hängen. ``markiere_versendet`` behandelt ``entwurf``
    bereits heute als gültigen Ausgangsstatus für einen ERFOLGREICHEN Versand
    (siehe oben) — diese Funktion muss den erneuten VERSUCH ebenso zulassen.

    Entscheidung Token-Neuaufbau (Patrik/Orchestrator-Vorgabe: entscheiden und
    begründen): der ALTE Token wird GELÖSCHT und ein komplett NEUER erzeugt
    (nicht überschrieben). Begründung: dadurch werden alte, dem Handwerker
    bereits zugestellte Links (die z.B. in einem Mail-Postfach oder
    Gateway-Log liegen könnten) sofort ungültig, statt nur ihre Gültigkeitsfrist
    stillschweigend zu verlängern — sauberer Audit-Schnitt statt Wiederverwendung
    derselben Geheimnisse. ``AuftragsbestaetigungsToken`` ist zudem kein
    Audit-Objekt (siehe Modell-Docstring), Löschen ist hier also unproblematisch.
    """
    if auftrag.status not in ('entwurf', 'abgelaufen', 'versendet'):
        raise ValidationError(
            f"Erneuter Versand ist aus Status '{auftrag.status}' nicht möglich "
            "(nur aus 'entwurf' (nach Versandfehler), 'abgelaufen' oder 'versendet')."
        )

    AuftragsbestaetigungsToken.objects.filter(auftrag=auftrag).delete()
    AuftragsbestaetigungsToken.objects.create(auftrag=auftrag)

    HandwerkerauftragEreignis.objects.create(
        auftrag=auftrag, typ='kommentar', erstellt_von=erstellt_von,
        text='Auftragsmail erneut ausgelöst (neuer Bestätigungs-Token erzeugt, '
             'alter Token ungültig).',
    )

    from apps.handwerker.tasks import versende_auftragsmail
    transaction.on_commit(lambda: versende_auftragsmail.delay(str(auftrag.id)))

    return auftrag


@transaction.atomic
def akzeptiere_via_token(accept_token: str) -> Handwerkerauftrag:
    """Nimmt einen Auftrag im Namen des Handwerkers an (Bestätigungslink ohne
    Login). Lädt den Token per ``select_for_update()`` (Einmalverwendung
    race-sicher gegen gleichzeitige Doppelklicks/Retries).
    """
    token = (
        AuftragsbestaetigungsToken.objects
        .select_for_update()
        .select_related('auftrag')
        .get(accept_token=accept_token)
    )
    if token.verbraucht_am is not None:
        raise TokenVerbraucht("Dieser Bestätigungslink wurde bereits verwendet.")
    if not token.ist_gueltig():
        raise TokenAbgelaufen("Dieser Bestätigungslink ist abgelaufen.")

    token.verbraucht_am = timezone.now()
    token.save(update_fields=['verbraucht_am'])

    auftrag = wechsle_status(
        token.auftrag, 'angenommen', erstellt_von=None,
        kommentar='Auftrag wurde vom Handwerker per Bestätigungslink (Token) angenommen.',
        _system_ausloeser=True,
    )

    from apps.handwerker.tasks import benachrichtige_intern
    transaction.on_commit(lambda: benachrichtige_intern.delay(str(auftrag.id), 'angenommen'))

    return auftrag


@transaction.atomic
def lehne_ab_via_token(reject_token: str, grund: str = '') -> Handwerkerauftrag:
    """Lehnt einen Auftrag im Namen des Handwerkers ab (Ablehnungslink ohne
    Login). Analog ``akzeptiere_via_token`` race-sicher per
    ``select_for_update()``."""
    token = (
        AuftragsbestaetigungsToken.objects
        .select_for_update()
        .select_related('auftrag')
        .get(reject_token=reject_token)
    )
    if token.verbraucht_am is not None:
        raise TokenVerbraucht("Dieser Ablehnungslink wurde bereits verwendet.")
    if not token.ist_gueltig():
        raise TokenAbgelaufen("Dieser Ablehnungslink ist abgelaufen.")

    token.verbraucht_am = timezone.now()
    token.save(update_fields=['verbraucht_am'])

    auftrag = token.auftrag
    auftrag.ablehnung_grund = grund
    auftrag = wechsle_status(
        auftrag, 'abgelehnt', erstellt_von=None,
        kommentar='Auftrag wurde vom Handwerker per Ablehnungslink (Token) abgelehnt.',
        _system_ausloeser=True,
    )

    from apps.handwerker.tasks import benachrichtige_intern
    transaction.on_commit(lambda: benachrichtige_intern.delay(str(auftrag.id), 'abgelehnt'))

    return auftrag


@transaction.atomic
def ordne_rechnung_zu(auftrag: Handwerkerauftrag, rechnung, erstellt_von) -> Handwerkerauftrag:
    """Ordnet eine ``Rechnung`` einem ``Handwerkerauftrag`` zu (Patrik-Entscheidung:
    v1.0 rein manuell, keine OCR-Automatik).

    Weist ab, wenn die Rechnung bereits einem ANDEREN Auftrag zugeordnet ist,
    oder wenn ``rechnung.kreditor`` vom ``auftrag.kreditor`` abweicht (Schutz
    gegen versehentliche Quer-Zuordnung).
    """
    if rechnung.handwerkerauftrag_id and rechnung.handwerkerauftrag_id != auftrag.id:
        raise ValidationError(
            "Diese Rechnung ist bereits einem anderen Handwerkerauftrag zugeordnet."
        )
    if rechnung.kreditor_id != auftrag.kreditor_id:
        raise ValidationError(
            "Der Kreditor der Rechnung stimmt nicht mit dem Kreditor des "
            "Handwerkerauftrags überein — Zuordnung abgelehnt."
        )

    rechnung.handwerkerauftrag = auftrag
    rechnung.save(update_fields=['handwerkerauftrag'])

    HandwerkerauftragEreignis.objects.create(
        auftrag=auftrag, typ='rechnung_zugeordnet', erstellt_von=erstellt_von,
        text=f"Rechnung {rechnung.rechnungsnummer or rechnung.id} zugeordnet.",
    )
    return auftrag


@transaction.atomic
def loese_rechnung_zuordnung(rechnung, erstellt_von) -> None:
    """Hebt die Zuordnung einer ``Rechnung`` zu ihrem ``Handwerkerauftrag``
    wieder auf."""
    auftrag = rechnung.handwerkerauftrag
    if auftrag is None:
        raise ValidationError("Diese Rechnung ist aktuell keinem Handwerkerauftrag zugeordnet.")

    rechnung.handwerkerauftrag = None
    rechnung.save(update_fields=['handwerkerauftrag'])

    HandwerkerauftragEreignis.objects.create(
        auftrag=auftrag, typ='rechnung_zugeordnet', erstellt_von=erstellt_von,
        text=f"Zuordnung zu Rechnung {rechnung.rechnungsnummer or rechnung.id} aufgehoben.",
    )


@transaction.atomic
def kommentiere(auftrag: Handwerkerauftrag, text: str, erstellt_von) -> HandwerkerauftragEreignis:
    """Legt einen Kommentar (``HandwerkerauftragEreignis`` Typ ``kommentar``)
    an. Leerer Text wird abgewiesen."""
    if not text or not text.strip():
        raise ValidationError("Kommentartext darf nicht leer sein.")

    return HandwerkerauftragEreignis.objects.create(
        auftrag=auftrag, typ='kommentar', text=text, erstellt_von=erstellt_von,
    )
