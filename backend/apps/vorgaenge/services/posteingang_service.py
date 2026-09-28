"""
Posteingang: was ein Mensch mit einer nicht zuordenbaren Mail macht.

Der Mail-Import legt jede Mail sofort im DMS ab, lässt den Kontext aber
offen, wenn er ihn nicht sicher bestimmen kann (siehe
``mail_import_service._lege_im_dms_ab``). Dieses Modul enthält die vier
Entscheidungen, die danach möglich sind:

  - ``lege_vorgang_an``   — aus der Mail wird ein neuer Vorgang
  - ``ordne_vorgang_zu``  — die Mail gehört zu einem laufenden Vorgang
  - ``lege_nur_ab``       — kein Vorgang nötig, aber die Ablage gehört an ein
                            Objekt/eine Einheit/eine Person (Rechnungen,
                            Abrechnungen, Protokolle)
  - ``verwirf``           — irrelevant; die Dokumente werden gelöscht, die
                            Protokollzeile bleibt als Spur

In allen Fällen wird der Kontext auf den zugehörigen Dokumenten
NACHGETRAGEN. Das ist der eigentliche Zweck des Posteingangs: Die Datei
liegt schon da, ihr fehlt nur die Verortung.

Gemeinsames Muster mit ``rechnungen.views_dubletten`` und der
Buchungserkennung: Was das System nicht sicher entscheiden kann, wird
angehalten und einem Menschen vorgelegt — statt geraten.
"""
import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.vorgaenge.models import MailImportProtokoll, Vorgang, VorgangEreignis

logger = logging.getLogger(__name__)

# Aus diesen Zuständen heraus darf im Posteingang entschieden werden.
# 'automatisch' fehlt bewusst: eine beim Import zugeordnete Mail ist fertig
# und soll nicht nachträglich verschoben werden — dafür gibt es die
# Vorgangsmaske.
BEARBEITBAR = {'offen'}


def _pruefe_bearbeitbar(protokoll: MailImportProtokoll):
    if protokoll.posteingang_status not in BEARBEITBAR:
        raise ValidationError(
            f'Diese Mail ist im Posteingang bereits erledigt '
            f'({protokoll.get_posteingang_status_display()}).'
        )


def _setze_dokument_kontext(protokoll: MailImportProtokoll, *, vorgang=None,
                            objekt=None, einheit=None, person=None) -> int:
    """Trägt den Kontext auf allen Dokumenten dieser Mail nach.

    Die Dokumente wurden beim Import kontextlos abgelegt; hier bekommen sie
    ihren Owner. ``mail_import`` bleibt daneben bestehen — die Herkunft
    ändert sich nicht dadurch, dass die Zuordnung gefunden wurde.

    Ein bereits gesetzter Kontext wird NICHT überschrieben: die Owner-Regel
    erlaubt nur einen, und ein Dokument, das schon irgendwo hängt, wurde
    anderswo bewusst verortet.
    """
    geaendert = 0
    for dokument in protokoll.dokumente.all():
        if dokument.objekt_id or dokument.einheit_id or dokument.vorgang_id or dokument.person_id:
            continue
        dokument.vorgang = vorgang
        dokument.objekt = objekt
        dokument.einheit = einheit
        dokument.person = person
        dokument.full_clean()
        dokument.save(update_fields=['vorgang', 'objekt', 'einheit', 'person'])
        geaendert += 1
    return geaendert


def _erledige(protokoll: MailImportProtokoll, status: str, benutzer,
              notiz: str = '') -> MailImportProtokoll:
    protokoll.posteingang_status = status
    protokoll.erledigt_am = timezone.now()
    protokoll.erledigt_von = benutzer
    if notiz:
        protokoll.erledigt_notiz = notiz
    protokoll.save(update_fields=[
        'posteingang_status', 'erledigt_am', 'erledigt_von', 'erledigt_notiz',
    ])
    return protokoll


def _mail_text(protokoll: MailImportProtokoll) -> str:
    """Mailtext für Vorgangsbeschreibung und Ereignis.

    Quelle ist ``body_auszug`` — der volle Text steht nur in der abgelegten
    Originaldatei. Für die Bearbeitung reicht der Auszug; wer alles braucht,
    öffnet das Dokument.
    """
    kopf = [f"Von: {protokoll.absender_name} <{protokoll.absender}>".strip()]
    if protokoll.gesendet_am:
        kopf.append(f"Gesendet: {protokoll.gesendet_am:%d.%m.%Y %H:%M}")
    kopf.append(f"Betreff: {protokoll.betreff}")
    return '\n'.join(kopf) + '\n\n---\n\n' + (protokoll.body_auszug or '(kein Text)')


@transaction.atomic
def lege_vorgang_an(protokoll: MailImportProtokoll, *, typ, benutzer,
                    objekt=None, einheit=None, person=None,
                    betreff: str = '', prioritaet: str = '',
                    notiz: str = '') -> Vorgang:
    """Erzeugt aus der Mail einen neuen Vorgang.

    Kontext (objekt/einheit/person) kommt vom Bearbeiter — genau das, was
    die automatische Erkennung nicht bestimmen konnte. ``Vorgang.clean()``
    verlangt mindestens eines davon und lehnt sonst ab.
    """
    from apps.vorgaenge.services import vorgang_service

    _pruefe_bearbeitbar(protokoll)

    vorgang = vorgang_service.erstelle_vorgang(
        typ=typ,
        betreff=(betreff or protokoll.ki_betreff or protokoll.betreff
                 or '(ohne Betreff)')[:200],
        erstellt_von=benutzer,
        quelle='mail',
        objekt=objekt, einheit=einheit, person=person,
        beschreibung=_mail_text(protokoll),
        prioritaet=prioritaet or None,
        mail_referenz=protokoll.message_id or None,
    )

    protokoll.vorgang = vorgang
    protokoll.save(update_fields=['vorgang'])
    _setze_dokument_kontext(protokoll, vorgang=vorgang)
    _erledige(protokoll, 'zugeordnet', benutzer, notiz)

    logger.info("Posteingang: %s -> neuer Vorgang %s durch %s",
                protokoll.dateiname, vorgang.nummer, benutzer)
    return vorgang


@transaction.atomic
def ordne_vorgang_zu(protokoll: MailImportProtokoll, vorgang: Vorgang, *,
                     benutzer, notiz: str = '') -> Vorgang:
    """Hängt die Mail an einen bestehenden Vorgang.

    Der Mailtext landet als Ereignis im Verlauf — ``intern=True``, weil der
    Text von aussen stammt und Angaben zu Dritten enthalten kann (gleiche
    Regel wie beim automatischen Thread-Treffer).
    """
    _pruefe_bearbeitbar(protokoll)

    VorgangEreignis.objects.create(
        vorgang=vorgang, typ='mail_eingegangen',
        text=f"E-Mail von {protokoll.absender}: {protokoll.betreff}\n\n"
             f"{protokoll.body_auszug}"[:5000],
        erstellt_von=benutzer, intern=True,
    )

    protokoll.vorgang = vorgang
    protokoll.save(update_fields=['vorgang'])
    _setze_dokument_kontext(protokoll, vorgang=vorgang)
    _erledige(protokoll, 'zugeordnet', benutzer, notiz)

    logger.info("Posteingang: %s -> bestehender Vorgang %s durch %s",
                protokoll.dateiname, vorgang.nummer, benutzer)
    return vorgang


@transaction.atomic
def lege_nur_ab(protokoll: MailImportProtokoll, *, benutzer,
                objekt=None, einheit=None, person=None,
                notiz: str = '') -> MailImportProtokoll:
    """Ordnet die Ablage zu, ohne einen Vorgang anzulegen.

    Der häufigste Fall im echten Posteingang: Rechnungen, Abrechnungen,
    Wartungsprotokolle, Angebote. Die gehören an ein Objekt, aber niemand
    muss dazu einen Fall bearbeiten — ein Vorgang wäre nur Ballast, der
    sofort wieder geschlossen würde.
    """
    _pruefe_bearbeitbar(protokoll)

    gesetzt = [w for w in (objekt, einheit, person) if w is not None]
    if len(gesetzt) != 1:
        raise ValidationError(
            'Genau ein Kontext (Objekt, Einheit oder Person) muss angegeben '
            'werden — sonst bleibt die Ablage unauffindbar.'
        )

    protokoll.objekt = objekt
    protokoll.einheit = einheit
    protokoll.person = person
    protokoll.save(update_fields=['objekt', 'einheit', 'person'])
    _setze_dokument_kontext(protokoll, objekt=objekt, einheit=einheit, person=person)
    _erledige(protokoll, 'abgelegt', benutzer, notiz)

    logger.info("Posteingang: %s nur abgelegt durch %s", protokoll.dateiname, benutzer)
    return protokoll


@transaction.atomic
def verwirf(protokoll: MailImportProtokoll, *, benutzer, notiz: str = '') -> dict:
    """Verwirft die Mail: die Dokumente werden gelöscht, die Protokollzeile
    bleibt.

    Bewusst so herum — nach dem Löschen soll nachvollziehbar bleiben, DASS
    eine Mail kam und wer sie verworfen hat. Verschwände auch das Protokoll,
    liesse sich später nicht von einer nie eingegangenen Mail unterscheiden.

    Revisionssichere Dokumente werden NICHT gelöscht (GoBD); sie behalten
    ihren Zustand und die Aktion meldet das zurück.
    """
    _pruefe_bearbeitbar(protokoll)
    if not notiz:
        raise ValidationError(
            'Beim Verwerfen ist eine Begründung erforderlich — sie ist die '
            'einzige Spur, die von der Mail bleibt.'
        )

    geloescht = gesperrt = 0
    for dokument in list(protokoll.dokumente.all()):
        if dokument.revisionssicher:
            gesperrt += 1
            continue
        dokument.delete()
        geloescht += 1

    _erledige(protokoll, 'verworfen', benutzer, notiz)

    logger.info("Posteingang: %s verworfen durch %s (%s Dokument(e) geloescht, "
                "%s revisionssicher)", protokoll.dateiname, benutzer, geloescht, gesperrt)
    return {'geloescht': geloescht, 'gesperrt': gesperrt}


def offene_mails():
    """Die Posteingangsliste: älteste zuerst, damit nichts liegen bleibt."""
    return (MailImportProtokoll.objects
            .filter(posteingang_status='offen')
            .select_related('person', 'objekt', 'einheit', 'vorgang')
            .prefetch_related('dokumente')
            .order_by('gesendet_am', 'verarbeitet_am'))
